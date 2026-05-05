import fs from 'fs/promises';
import fsSync from 'fs';
import path from 'path';
import { createRequire } from 'module';
import { fileURLToPath } from 'url';

const require = createRequire(import.meta.url);
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

let cheerio;
try { cheerio = require('cheerio'); } catch (e) { console.log('Tip: cheerio not found, using regex fallback'); }

// ── ConfigLoader ────────────────────────────────────────────────
class ConfigLoader {
  constructor() {
    const args = {
      input: '.', output: 'dist', baseUrl: '', logo: '/favicon.ico', logoText: 'MLCLASSIC',
      concurrency: 4, config: './libmap.js', only: [], skip: [],
      copyOnly: ['en/archive/', 'en/history/', 'docs/VIL/', 'docs/MEW/', 'ru/VIL-UAIO/'],
      template: './template.js', mitt: '', mps:''
    };

    const flagMap = {
      '--input': 'input', '-i': 'input',
      '--output': 'output', '-o': 'output',
      '--config': 'config', '-c': 'config',
      '--template': 'template', '-t': 'template',
      '--logo': 'logo', '--logotext': 'logoText',
      '--concurrency': 'concurrency',
      '--only': 'only', '--skip': 'skip', '-s': 'skip',
      '--copy-only': 'copyOnly', '--base-url':'baseUrl',
      '--mitt':'mitt','--mps':'mps',
    };

    for (let i = 2; i < process.argv.length; i++) {
      const a = process.argv[i];
      const key = flagMap[a];
      if (!key) continue;
      const val = process.argv[++i];
      if (val === undefined) continue;
      if (key === 'concurrency') args.concurrency = parseInt(val) || 4;
      else if (key === 'only' || key === 'skip' || key === 'copyOnly') args[key].push(...val.split(',').map(s => s.trim()).filter(Boolean));
      else args[key] = val;
    }

    const envMap = [
      ['BUILD_ONLY', 'only'], ['BUILD_SKIP', 'skip'], ['BUILD_COPY_ONLY', 'copyOnly'],
      ['BUILD_TEMPLATE', 'template'], ['BUILD_INPUT', 'input'],
      ['BUILD_OUTPUT', 'output']
    ];
    for (const [envKey, argKey] of envMap) {
      const val = process.env[envKey];
      if (!val) continue;
      if (argKey === 'only' || argKey === 'skip' || argKey === 'copyOnly') args[argKey].push(...val.split(',').map(s => s.trim()).filter(Boolean));
      else args[argKey] = val;
    }
    //if (process.env.CF_PAGES_URL) args.baseUrl = process.env.CF_PAGES_URL;

    args.only = [...new Set(args.only)];
    args.skip = [...new Set(args.skip)];
    args.copyOnly = [...new Set(args.copyOnly)];

    this.args = args;
    this.ROOT = path.resolve(args.input);
    this.DIST = path.resolve(args.output);
    this.SITE = (args.baseUrl || '').replace(/\/$/, '');
    this.CONCURRENCY = args.concurrency;
    this.generateTemplate = null;
    this.esc = null;
  }

  loadUserConfig() {
    if (!this.args.config) return [];
    const p = path.resolve(this.args.config);
    if (!fsSync.existsSync(p)) return [];
    try {
      const code = fsSync.readFileSync(p, 'utf-8');
      const mockWindow = {};
      const fn = new Function('window', 'module', 'exports', 'require', 'console', '__dirname', '__filename',
        `${code}\nreturn window.LIBRARY_CONFIG || (typeof LIBRARY_CONFIG !== 'undefined' ? LIBRARY_CONFIG : module.exports);`);
      let config = fn(mockWindow, {}, {}, require, console, path.dirname(p), p);
      if (config && typeof config === 'object' && !Array.isArray(config) && Array.isArray(config.LIBRARY_CONFIG)) config = config.LIBRARY_CONFIG;
      return Array.isArray(config) ? config : [];
    } catch (e) { console.error('Config load failed:', e.message); return []; }
  }

  loadTemplateModule() {
    const templatePath = path.resolve(this.args.template);
    if (!fsSync.existsSync(templatePath)) { console.error(`Template not found: ${templatePath}`); process.exit(1); }

    const tryLoad = () => {
      const m = require(templatePath);
      return { generateTemplate: m.generateTemplate, esc: m.esc };
    };
    const sandboxLoad = () => {
      const code = fsSync.readFileSync(templatePath, 'utf-8');
      const mod = { exports: {} };
      const fn = new Function('module', 'exports', 'require', 'console', '__dirname', '__filename',
        `${code}\nreturn module.exports;`);
      const m = fn(mod, mod.exports, require, console, path.dirname(templatePath), templatePath);
      return {
        generateTemplate: (m && m.generateTemplate) || mod.exports.generateTemplate,
        esc: (m && m.esc) || mod.exports.esc
      };
    };

    try {
      const m = tryLoad();
      this.generateTemplate = m.generateTemplate;
      this.esc = m.esc;
      console.log(`   Template loaded: ${this.args.template}`);
    } catch (e) {
      try {
        const m = sandboxLoad();
        this.generateTemplate = m.generateTemplate;
        this.esc = m.esc;
        if (!this.generateTemplate) throw new Error('generateTemplate not found');
        console.log(`   Template loaded (sandbox): ${this.args.template}`);
      } catch (e2) { console.error('Template load failed:', e2.message); process.exit(1); }
    }
  }
}

// ── PathMatcher ─────────────────────────────────────────────────
class PathMatcher {
  constructor(only, copyOnly, skip) {
    this.only = only || [];
    this.copyOnly = copyOnly || [];
    this.skip = skip || [];
  }

  matches(relPath, patterns) {
    if (!patterns?.length) return false;
    const norm = p => p.replace(/\\/g, '/').replace(/\/+$/, '');
    const np = norm(relPath);

    return patterns.some(pat => {
      const cp = norm(pat);
      if (np === cp || np.startsWith(cp + '/')) return true;
      if (patterns == this.only && cp.startsWith(np + '/')) return true;
      if (pat.includes('*')) return new RegExp('^' + pat.replace(/\*/g, '.*') + '$').test(np);
      return false;
    });
  }

  shouldBuild(relPath) {
    if (this.matches(relPath, this.skip)) return false;
    return !this.only.length || this.matches(relPath, this.only);
  }
  isCopyOnly(relPath) { return this.matches(relPath, this.copyOnly); }
}

// ── FileScanner ─────────────────────────────────────────────────
class FileScanner {
  constructor(root, pathMatcher) {
    this.root = root;
    this.pm = pathMatcher;
    this.SKIP_DIRS = new Set(['node_modules', 'dist', '.git', '.github', '.vscode', '.idea', 'assets']);
    this.SKIP_FILES = new Set(['build.js', 'nav.js', 'reader.js', 'reader.css', 'build.cjs', 'libmap.js', 'package.json', 'package-lock.json', 'yarn.lock', '.DS_Store', 'index.json']);
  }

  async *scan(base = '') {
    const dir = base ? path.join(this.root, base) : this.root;
    let entries;
    try { entries = await fs.readdir(dir, { withFileTypes: true }); } catch (e) { return; }

    for (const ent of entries) {
      if (this.SKIP_DIRS.has(ent.name) || ent.name.startsWith('.')) continue;
      const relPath = base ? `${base}/${ent.name}` : ent.name;
      if (!this.pm.shouldBuild(relPath)) continue;
      const fullPath = path.join(dir, ent.name);

      if (ent.isDirectory()) {
        if (this.pm.isCopyOnly(relPath)) yield* this.copyDir(fullPath, relPath);
        else yield* this.scan(relPath);
      } else if (ent.isFile() && !this.SKIP_FILES.has(ent.name)) {
        yield {
          type: this.pm.isCopyOnly(relPath) || !/\.html?$/i.test(ent.name) ? 'copy' : 'render',
          path: relPath, fullPath
        };
      }
    }
  }

  async *copyDir(dir, base) {
    let entries;
    try { entries = await fs.readdir(dir, { withFileTypes: true }); } catch (e) { return; }
    for (const ent of entries) {
      if (ent.name.startsWith('.')) continue;
      const relPath = base ? `${base}/${ent.name}` : ent.name;
      if (!this.pm.shouldBuild(relPath)) continue;
      const fullPath = path.join(dir, ent.name);
      if (ent.isDirectory()) yield* this.copyDir(fullPath, relPath);
      else yield { type: 'copy', path: relPath, fullPath };
    }
  }
}

// ── HTMLProcessor ───────────────────────────────────────────────
class HTMLProcessor {
  static extractHtmlParts(rawHtml) {
    const lang = rawHtml.match(/<html[^>]*lang=["']([^"']+)["']/i)?.[1] || 'zh';
    const title = rawHtml.match(/<title[^>]*>([^<]*)<\/title>/i)?.[1]?.trim() || '';

    let body = '';
    const bodyMatch = rawHtml.match(/<body(?:\s[^>]*)?>([\s\S]*?)<\/body>/i);
    if (bodyMatch) {
      body = bodyMatch[1].trim();
    } else {
      // No body tags — strip document wrappers and use remainder
      body = rawHtml
        .replace(/<!DOCTYPE\s+html[^>]*>/i, '')
        .replace(/<html(?:\s[^>]*)?>[\s\S]*?<head(?:\s[^>]*)?>([\s\S]*?)<\/head>/i, '')
        .replace(/<\/html>/gi, '')
        .replace(/<body(?:\s[^>]*)?>/gi, '')
        .replace(/<\/body>/gi, '');
      body = body.trim();
    }
    body = body.replace(/\$/g, '&#36;');

    let headExtras = '';
    const headMatch = rawHtml.match(/<head[^>]*>([\s\S]*?)<\/head>/i);
    if (headMatch) {
      headExtras = cheerio
        ? HTMLProcessor._headCheerio(headMatch[1])
        : HTMLProcessor._headRegex(headMatch[1]);
    }
    return { lang, title, body, headExtras };
  }

  static _headCheerio(headString) {
    try {
      const $ = cheerio.load(`<head>${headString}</head>`, { decodeEntities: false });
      let out = '';
      $('link[rel="stylesheet"], style').each((i, el) => {
        const tag = $(el).prop('tagName');
        const keep = tag === 'LINK'
          ? !/reader\.css|libmap\.js/i.test($(el).attr('href') || '')
          : tag === 'STYLE';
        if (keep) out += $.html(el).replace(/\$/g, '&#36;') + '\n';
      });
      return out;
    } catch (e) { return HTMLProcessor._headRegex(headString); }
  }

  static _headRegex(headString) {
    const links = headString.match(/<link\s[^>]*rel=["']stylesheet["'][^>]*\/?>/gi) || [];
    const styles = headString.match(/<style[\s\S]*?<\/style>/gi) || [];
    return [...links, ...styles].filter(t => !/reader\.css/i.test(t)).join('\n').replace(/\$/g, '&#36;');
  }

  static extractHeadings(bodyHtml) {
    return cheerio
      ? HTMLProcessor._headingsCheerio(bodyHtml)
      : HTMLProcessor._headingsRegex(bodyHtml);
  }

  static _headingsCheerio(bodyHtml) {
    try {
      const $ = cheerio.load(bodyHtml, { decodeEntities: false });
      const skip = new Set(['Karl Marx', 'Friedrich Engels', 'Karl Marx/Friedrich Engels']);
      const headings = [];
      $('h1, h2, h3, h4, h5, h6').each((i, el) => {
        let text = $(el).text().trim()
          .replace(/</g, '&lt;').replace(/>/g, '&gt;')
          .replace(/\(\d+?\)/g, '').replace(/\s*FN\d+?\s*/g, '').trim();
        if (!text || skip.has(text)) return;
        let id = $(el).attr('id') || null;
        if (!id) id = 'h' + i;
        headings.push({ tag: el.tagName.toLowerCase(), text, level: parseInt(el.tagName[1]), id });
      });
      return headings;
    } catch (e) { return []; }
  }

  static _headingsRegex(bodyHtml) {
    const headings = [];
    const skip = new Set(['Karl Marx', 'Friedrich Engels', 'Karl Marx/Friedrich Engels']);
    const re = /<(h[1-6])[^>]*(?:\s+id=["']([^"']*)["'])?[^>]*>([\s\S]*?)<\/\1>/gi;
    let m, i = -1;
    while ((m = re.exec(bodyHtml)) !== null) {
      i++;
      let text = m[3].replace(/<[^>]+>/g, '').trim()
        .replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/\(\d+?\)/g, '').replace(/\s*FN\d+?\s*/g, '').trim();
      if (!text || skip.has(text)) continue;
      headings.push({
        tag: m[1].toLowerCase(), text, level: parseInt(m[1][1]),
        id: m[2] || ('h' + i)
      });
    }
    return headings;
  }

  static processFootnoteRefs(html) {
    if (!html) return html;
    return cheerio
      ? HTMLProcessor._fnCheerio(html)
      : HTMLProcessor._fnRegex(html);
  }

  static _fnCheerio(html) {
    try {
      const $ = cheerio.load(html, { decodeEntities: false });
      let modified = false;

      $('a[href]').each((i, el) => {
        const $a = $(el);
        const href = $a.attr('href') || '';
        if (!$a.closest('sup').length && !$a.find('sup').length) return;
        if (!href.includes('#') || href.startsWith('http') || href.startsWith('//')) return;

        if (!$a.attr('data-fn-ref')) { $a.attr('data-fn-ref', ''); modified = true; }
        if (!href.startsWith('#') && !$a.attr('data-fn-cross')) { $a.attr('data-fn-cross', ''); modified = true; }

        if (href.startsWith('#')) {
          const targetId = href.slice(1);
          if (!targetId) return;
          let target = $('[id]').filter((j, el) => $(el).attr('id') === targetId);
          if (!target.length) target = $('a[name]').filter((j, el) => $(el).attr('name') === targetId);
          if (!target.length) return;

          let block = target.closest('.fni');
          if (!block.length) block = target.closest('.endnote, .fn, .note');
          if (!block.length) {
            const t = target[0];
            if (/^LI|DD|P|DIV|SPAN$/i.test(t.tagName)) block = target;
          }
          if (!block.length) block = target.closest('li, dd');
          if (!block.length) block = target.closest('p, div');
          if (!block.length) block = target;

          if (target.attr('id') === targetId && !block.attr('id')) {
            target.removeAttr('id');
            block.attr('id', targetId);
            modified = true;
          }
        }
      });

      return modified ? $('body').html() : html;
    } catch (e) { return HTMLProcessor._fnRegex(html); }
  }

  static _fnRegex(html) {
    let result = html, offset = 0;
    const re = /<a\s+([^>]*?)href\s*=\s*"([^"]*)"([^>]*?)>/gi;
    let match;
    while ((match = re.exec(html)) !== null) {
      const [full, pre, href, post] = match;
      if (full.includes('data-fn-ref')) continue;
      if (!href.includes('#') || href.startsWith('http') || href.startsWith('//')) continue;
      const preceding = html.substring(Math.max(0, match.index - 200), match.index);
      if (preceding.lastIndexOf('<sup') <= preceding.lastIndexOf('</sup>')) continue;

      let extra = ' data-fn-ref';
      if (!href.startsWith('#')) extra += ' data-fn-cross';
      const replacement = `<a ${pre}href="${href}"${post}${extra}>`;
      const idx = match.index + offset;
      result = result.substring(0, idx) + replacement + result.substring(idx + full.length);
      offset += replacement.length - full.length;
    }
    return result;
  }
}

// ── PrevNextResolver ────────────────────────────────────────────
class PrevNextResolver {
  constructor(root) { this.root = root; this.cache = new Map(); }
  async getLocalPrevNext(filePath) {
    const dir = path.dirname(filePath);
    if (this.cache.has(dir)) return this.cache.get(dir);

    let files = [];
    try {
      const entries = await fs.readdir(path.join(this.root, dir), { withFileTypes: true });
      files = entries.filter(e => e.isFile() && /\.html?$/i.test(e.name)).map(e => e.name).sort();
    } catch (e) { }

    const titleMap = Object.fromEntries(await Promise.all(
      files.map(async f => [f, await this.parseTitle(path.join(this.root, dir, f))])
    ));

    const map = {};
    files.forEach((f, i) => {
      map[f] = {
        prev: i > 0 ? { file: files[i - 1], title: titleMap[files[i - 1]] } : null,
        next: i < files.length - 1 ? { file: files[i + 1], title: titleMap[files[i + 1]] } : null
      };
    });

    this.cache.set(dir, map);
    return map;
  }

  async parseTitle(filePath) {
    try {
      const buf = Buffer.alloc(2048);
      const fd = await fs.open(filePath, 'r');
      const { bytesRead } = await fd.read(buf, 0, 2048, 0);
      await fd.close();
      const m = buf.toString('utf-8', 0, bytesRead).match(/<title[^>]*>([^<]+)<\/title>/i);
      return m?.[1]?.trim() || this.fallbackName(filePath);
    } catch (e) { return this.fallbackName(filePath); }
  }

  fallbackName(p) { return path.basename(p).replace(/\.html?$/i, ''); }
}

// ── VolumeIndexBuilder ──────────────────────────────────────────
class VolumeIndexBuilder {
  constructor(config) {
    this.config = config;
    this.esc = config.esc || ((t) => String(t)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;'));
  }

  _eachItem(libraryConfig, cb) {
    for (const col of libraryConfig) {
      for (const group of (col.groups || [])) {
        for (const item of (group.items || [])) cb(col, group, item);
      }
    }
  }

  collectVolumePaths(libraryConfig) {
    const pm = new PathMatcher(this.config.args.only || [], this.config.args.copyOnly || [], this.config.args.skip || []);
    const paths = new Set();
    this._eachItem(libraryConfig, (_col, _group, item) => {
      const p = item.path || '';
      if (!p.endsWith('/index.html')) return;
      const dir = p.replace(/^\//, '').replace(/\/index\.html$/, '');
      if (pm.isCopyOnly(dir)) return;
      paths.add(dir + '/index.html');
    });
    return paths;
  }

  _collectVolumes(libraryConfig) {
    const volumes = new Map();
    this._eachItem(libraryConfig, (col, group, item) => {
      const p = item.path || '';
      if (!p.endsWith('/index.html')) return;
      const dir = p.replace(/^\//, '').replace(/\/index\.html$/, '');
      if (!dir || volumes.has(dir)) return;
      volumes.set(dir, {
        dir, path: p, label: item.label || item.title || '',
        collectionId: col.id, collectionLabel: col.label, groupLabel: group.label
      });
    });
    return [...volumes.values()];
  }

  // TOC generation (migrated from nav.js for build-time rendering)
  _buildTreeHtml(headings) {
    const root = { level: 0, children: [] };
    const stack = [root];
    for (const h of headings) {
      const node = { ...h, children: [] };
      while (stack.length > 1 && stack[stack.length - 1].level >= h.level) stack.pop();
      stack[stack.length - 1].children.push(node);
      stack.push(node);
    }
    return this._renderNodes(root.children);
  }

  _renderNodes(nodes) {
    return nodes.map(n => {
      const href = n.id ? `${this.esc(n.file || '')}#${this.esc(n.id)}` : this.esc(n.file || '');
      const hasChildren = n.children.length > 0;
      const childHtml = hasChildren ? `<ul>${this._renderNodes(n.children)}</ul>` : '';
      const caretHtml = hasChildren
        ? `<button class="toc-caret" type="button" aria-label="Expand section" tabindex="0">\u25be</button>`
        : '';
      return `<li class="toc-item${hasChildren ? ' toc-item--collapsible' : ''}" data-collapsed="false">
  <div class="toc-item-row">
    <a href="${href}" class="toc-link">${this.esc(n.text)}</a>
    ${caretHtml}
  </div>
  ${childHtml}
</li>`;
    }).join('');
  }

  _headingsToToc(files) {
    const all = [];
    for (const f of files) {
      for (const h of (f.headings || [])) {
        all.push({
          text: h.text || '', level: h.level != null ? h.level : 2,
          file: h.filename || f.file || '', id: h.id || null
        });
      }
    }
    if (!all.length) return '<li style="color:var(--text-3);font-size:12px;padding:8px 20px">No contents</li>';
    return this._buildTreeHtml(all);
  }

  async buildAll(libraryConfig, dist) {
    const pm = new PathMatcher(this.config.args.only || [], this.config.args.copyOnly || [], this.config.args.skip || []);
    const volumes = this._collectVolumes(libraryConfig).filter(v => (!pm.isCopyOnly(v.dir) && pm.shouldBuild(v.dir)));
    let generated = 0;
    for (const vol of volumes) {
      if (await this._buildOne(vol, dist)) generated++;
    }
    return { generated, volumes };
  }

  async _buildOne(vol, dist) {
    const sourceDir = path.join(this.config.ROOT, vol.dir);
    const outputJs = path.join(dist, vol.dir, 'index.js');
    const outputHtml = path.join(dist, vol.dir, 'index.html');

    let navHtml = null, files = [], title = vol.label;
    let preNavHtml = '';   // everything before the first <nav>
    let lang = 'zh';       // extracted from original <html lang="...">
    let headExtras = '';   // original CSS links/styles from source index.html

    // ── 1. ALWAYS try index.json first ──
    const jsonPath = path.join(sourceDir, 'index.json');
    let jsonSuccess = false;
    if (fsSync.existsSync(jsonPath)) {
      try {
        const jsonData = JSON.parse(await fs.readFile(jsonPath, 'utf-8'));
        if (Array.isArray(jsonData)) {
          files = jsonData.map(e => ({
            file: e.file || '',
            title: e.title || '',
            headings: (e.headings || []).map(h => ({
              tag: h.tag || 'h2', text: h.text || '', level: h.level != null ? h.level : 2,
              id: h.id || null, filename: h.filename || e.file || ''
            }))
          }));
          jsonSuccess = true;
        }
      } catch (e) {
        console.warn(`[Index] JSON parse failed for ${jsonPath}: ${e.message}`);
      }
    }

    // ── 2. Pre‑nav HTML (only from original index.html, if exists) ──
    const htmlPath = path.join(sourceDir, 'index.html');
    if (fsSync.existsSync(htmlPath)) {
      const rawHtml = await fs.readFile(htmlPath, 'utf-8');
      const { title: htmlTitle, body, lang: htmlLang, headExtras: htmlHeadExtras } = HTMLProcessor.extractHtmlParts(rawHtml);
      if (htmlTitle) title = htmlTitle;
      if (htmlLang) lang = htmlLang;
      if (htmlHeadExtras) headExtras = htmlHeadExtras;
      if (body) {
        const navIdx = body.search(/<nav\b/i);
        preNavHtml = (navIdx === -1) ? body.trim() : body.slice(0, navIdx).trim();
      }
      if (!jsonSuccess) {
        // ── FALLBACK: no valid index.json → use HTMLProcessor for title + headings ──
        const headings = HTMLProcessor.extractHeadings(body || '');
        if (headings.length > 0) {
          files = [{
            file: 'index.html',
            title: htmlTitle || title,
            headings: headings.map(h => ({
              tag: h.tag, text: h.text, level: h.level,
              id: h.id || null, filename: 'index.html'
            }))
          }];
        } else if (files.length === 0) {
          console.warn(`[Index] No headings or files for ${vol.dir}, skipping`);
          return false;
        }
      }

      // preNavHtml: always extract nav‑before content with simple string cut
    } else if (!jsonSuccess) {
      console.warn(`[Index] No index.html or index.json for ${vol.dir}, skipping`);
      return false;
    }

    // ── 3. Build VOLUME_DATA ──
    const allHeadings = [];
    for (const f of files) {
      for (const h of (f.headings || [])) {
        allHeadings.push({
          level: h.level != null ? h.level : 2,
          text: h.text || '',
          id: h.id || null,
          file: h.filename || f.file || ''
        });
      }
    }

    const data = {
      version: 1,
      title,
      volumePath: '/' + vol.dir + '/',
      collectionId: vol.collectionId,
      collectionLabel: vol.collectionLabel,
      groupLabel: vol.groupLabel,
      navHtml,
      files,
      headings: allHeadings
    };

    await ensure(path.dirname(outputJs));
    await fs.writeFile(outputJs, `window.VOLUME_DATA=${JSON.stringify(data)};`, 'utf-8');

    // ── 4. Generate index.html (build-time rendering) ──
    if (this.config.generateTemplate) {
      const depth = vol.dir.split('/').length;
      const rootPrefix = Array(depth).fill('..').join('/');

      // Build TOC HTML at build time (migrated from nav.js)
      const tocHtml = data.headings?.length
        ? this._buildTreeHtml(data.headings)
        : this._headingsToToc(data.files || []);

      // Extract h1-h6 heading tags from preNavHtml for centered title block
      let titleBlockHtml = '';
      let remainingPreNav = preNavHtml;
      if (preNavHtml) {
        const headingRegex = /<h[1-6]\b[^>]*>[\s\S]*?<\/h[1-6]>/gi;
        const headingMatches = preNavHtml.match(headingRegex);
        if (headingMatches && headingMatches.length) {
          titleBlockHtml = `<div class="vol-index-headings">${headingMatches.join('')}</div>`;
          remainingPreNav = preNavHtml.replace(headingRegex, '').trim();
        }
      }
      const innerHTMLhead = titleBlockHtml || `<h2 class="vol-index-title">${this.esc(data.title || 'Contents')}</h2>`;
      const bodyHtml = innerHTMLhead
        + (remainingPreNav ? remainingPreNav : '')
        + `<nav class="doc-toc doc-toc--continuous" aria-label="Volume Contents"><ul>${tocHtml}</ul></nav>`;

      // Build breadcrumb from volume path (e.g. /chinese/MEW12/ → chinese / MEW12)
      const breadcrumbParts = data.volumePath.replace(/^\/|\/$/g, '').split('/');
      const breadcrumbHtml = breadcrumbParts.map((part, i) => i === breadcrumbParts.length - 1
        ? `<span class="crumb crumb--active">${this.esc(part)}</span>`
        : `<a class="crumb" href="${this.config.SITE ? this.config.SITE + '/' : '/'}${breadcrumbParts.slice(0, i + 1).join('/')}/index.html">${this.esc(part)}</a>`
      ).join('<span class="crumb-sep">/</span>');

      const meta = {
        path: vol.path,
        collection: vol.collectionId,
        title,
        lang,
        isVolumeIndex: true,
        indexJsPath: './index.js'
      };

      await fs.writeFile(outputHtml, this.config.generateTemplate({
        title,
        bodyHtml,
        headExtras: headExtras ? headExtras.split('\n').filter(Boolean) : [],
        meta,
        root: this.config.SITE || rootPrefix || '.',
        breadcrumb: breadcrumbHtml,
        hasToc: false,
        hasVolIndex: true,
        volJsPath: './index.js',
        volLabel: title,
        logo: this.config.args.logo,
        logoText: this.config.args.logoText,
        site: this.config.SITE
      }), 'utf-8');
    }
    return true;
  }
}

// ── PageRenderer ────────────────────────────────────────────────
class PageRenderer {
  constructor(config, prevNextResolver, libraryConfig) {
    this.config = config;
    this.prevNext = prevNextResolver;
    this.libraryConfig = libraryConfig || [];
    this._volCache = new Map();
  }

  _getVolumeInfo(itemPath) {
    const dir = path.dirname(itemPath).replace(/\\/g, '/');
    if (this._volCache.has(dir)) return this._volCache.get(dir);

    let bestLen = 0, bestJs = null, bestLabel = null, bestDir = null;

    for (const col of this.libraryConfig) {
      for (const group of (col.groups || [])) {
        for (const item of (group.items || [])) {
          const itemDir = (item.path || '')
            .replace(/^\/+|\/+$/g, '')
            .replace(/\\/g, '/')
            .replace(/\/index\.html$/i, '');
          if (!itemDir) continue;
          if (dir !== itemDir && !dir.startsWith(itemDir + '/')) continue;
          if (itemDir.length <= bestLen) continue;

          bestLen = itemDir.length;
          const depth = dir.split('/').length - itemDir.split('/').length;
          bestJs = depth === 0 ? './index.js' : '../'.repeat(depth) + 'index.js';
          bestLabel = item.label || item.title || null;
          bestDir = itemDir;
        }
      }
    }

    const info = { jsPath: bestJs, label: bestLabel || 'Contents', volDir: bestDir };
    this._volCache.set(dir, info);
    return info;
  }

  async render(item) {
    const { generateTemplate, esc, SITE } = this.config;
    const rawHtml = await fs.readFile(item.fullPath, 'utf-8');
    const { lang, title: pageTitle, body, headExtras } = HTMLProcessor.extractHtmlParts(rawHtml);
    const processedBody = HTMLProcessor.processFootnoteRefs(body);

    const colId = item.path.split('/')[0];
    const localNav = await this.prevNext.getLocalPrevNext(item.path);
    const curFile = item.path.split('/').pop();
    const local = localNav[curFile] || {};

    const parts = item.path.split('/');
    const breadcrumb = parts.map((part, i) => {
      if (i === parts.length - 1) return `<span class="crumb current">${esc(part)}</span>`;
      const href = (SITE ? `${SITE}/` : '/') + parts.slice(0, i + 1).join('/') + '/index.html';
      return `<a class="crumb" href="${esc(href)}">${esc(part)}</a>`;
    }).join('<span class="crumb-sep">/</span>');

    const volInfo = this._getVolumeInfo(item.path);
    const hasVolIndex = !!volInfo.jsPath;

    const finalHtml = generateTemplate({
      title: pageTitle, bodyHtml: processedBody,
      headExtras: headExtras.split('\n').filter(Boolean),
      meta: {
        path: item.path, collection: colId, title: pageTitle, lang,
        prev: local.prev || null, next: local.next || null,
        volPath: volInfo.jsPath ? `/${volInfo.volDir}/index.html` : null,
        parentDir: null
      },
      root: SITE || '.',
      prev: local.prev || null, next: local.next || null,
      breadcrumb, hasToc: false, hasVolIndex,
      volJsPath: volInfo.jsPath || '', volLabel: '',
      logo: this.config.args.logo, logoText: this.config.args.logoText,
      site: SITE
    });

    const outPath = path.join(this.config.DIST, item.path);
    await ensure(path.dirname(outPath));
    await fs.writeFile(outPath, finalHtml, 'utf-8');
    return 'rendered';
  }

  generateCardIndex(libraryConfig) {
    const { esc, SITE } = this.config;
    const cards = libraryConfig.map(col => {
      let href;
      const isExternal = col.path && /^https?:\/\//.test(col.path);
      if (isExternal) href = col.path;
      else if (col.basePath) {
        const base = col.basePath.replace(/^\//, '').replace(/\/$/, '');
        href = SITE ? `${SITE}/${base}/index.html` : `/${base}/index.html`;
      } else if (col.path) {
        href = col.path.startsWith('/') ? (SITE ? `${SITE}${col.path}` : col.path) : (SITE ? `${SITE}/${col.path}` : `/${col.path}`);
      } else href = SITE ? `${SITE}/` : '/';

      return `<a href="${esc(href)}" class="library-card"${isExternal ? ' target="_blank" rel="noopener"' : ''}>
        <div class="card-header"><span class="card-badge">${esc(col.badge || col.id.toUpperCase())}</span>
        <h3 class="card-title">${esc(col.label)}</h3></div>
        <p class="card-desc">${esc(col.desc || col.title)}</p></a>`;
    }).join('');

    const themeScript = `(function(){var t=localStorage.getItem('theme')||'light';document.documentElement.setAttribute('data-theme',t);var f=parseFloat(localStorage.getItem('fontSize'));if(f&&f!==1)document.documentElement.style.setProperty('--fs-user',Math.round(16*f)+'px');})();`;
    const styles = `body{margin:0;background:var(--bg);color:var(--text);font-family:var(--font-ui);}.index-container{max-width:1200px;margin:0 auto;padding:60px 20px;text-align:center;}.index-title{font-size:2.5rem;font-weight:600;margin-bottom:12px;font-family:var(--font-serif);}.library-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:24px;text-align:left;margin-top:40px;}.library-card{display:block;background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:24px;text-decoration:none;color:inherit;transition:all 200ms;}.library-card:hover{border-color:var(--accent);transform:translateY(-2px);box-shadow:var(--shadow-md);}.card-badge{font-size:11px;font-weight:700;padding:4px 8px;background:var(--accent-bg);color:var(--accent);border-radius:4px;font-family:var(--font-mono);}.card-title{font-size:1.25rem;font-weight:600;margin:12px 0 8px;color:var(--text);}.card-desc{font-size:0.95rem;color:var(--text-2);line-height:1.6;margin:0;}`;
    const BAMITT = this.config.args.mitt ? `<a href="https://beian.miit.gov.cn/" target="_blank">${this.config.args.mitt}</a>`:''
    const BAMPS_NUM = this.config.args.mps?.match(/^[\S]公网安备(\d+)号$/)?.[1] || null
    const BAMPS = BAMPS_NUM ? `<a href="https://beian.mps.gov.cn/#/query/webSearch?code=${BAMPS_NUM}" rel="noreferrer" target="_blank">${this.config.args.mps}</a>`:''
    const BEIAN = BAMITT ? (BAMPS ? '<p>' + BAMITT + '<br>' + BAMPS + '</p>' : '<p>' + BAMITT + '</p>'):''

    return `<!DOCTYPE html><html lang="zh-CN" data-theme="light"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>${esc(this.config.args.logoText)}</title><script>${themeScript}</script><link rel="stylesheet" href="${SITE}/assets/reader.css"><style>${styles}</style></head><body><div class="index-container"><h1 class="index-title">${esc(this.config.args.logoText)}</h1><p>Proletarier aller Länder, vereinigt euch!<br>Пролетарии всех стран, соединяйтесь!<br>全世界无产者，联合起来！</p><div class="library-grid">${cards}</div>${BEIAN}</div></body></html>`;
  }
}

// ── Utilities ───────────────────────────────────────────────────
const ensure = async dir => { try { await fs.mkdir(dir, { recursive: true }); } catch (e) { } };

async function copyProcessor(item, dist) {
  const outputPath = path.join(dist, item.path);
  try { await ensure(path.dirname(outputPath)); await fs.copyFile(item.fullPath, outputPath); } catch (e) { }
  return 'copied';
}

// ── BuildEngine ─────────────────────────────────────────────────
class BuildEngine {
  async build() {
    const start = Date.now();
    const config = new ConfigLoader();
    const { args, ROOT, DIST, SITE, CONCURRENCY } = config;

    console.log(`\nBuild started (lightweight mode)`);
    if (args.only.length) console.log(`   Build only: ${args.only.join(', ')}`);
    if (args.skip.length) console.log(`   Skip: ${args.skip.join(', ')}`);
    if (args.copyOnly.length) console.log(`   Copy-only: ${args.copyOnly.join(', ')}`);
    console.log(`   Source: ${ROOT} -> Output: ${DIST}`);

    config.loadTemplateModule();
    if (!config.generateTemplate) { console.error('Template not loaded'); process.exit(1); }

    await ensure(DIST);
    await ensure(path.join(DIST, 'assets'));

    const rawConfig = config.loadUserConfig();
    console.log(`   Loaded ${rawConfig.length} collection(s) from config`);

    const pathMatcher = new PathMatcher(args.only, args.copyOnly, args.skip);
    const scanner = new FileScanner(ROOT, pathMatcher);
    const prevNextResolver = new PrevNextResolver(ROOT);
    const renderer = new PageRenderer(config, prevNextResolver, rawConfig);
    const volBuilder = new VolumeIndexBuilder(config);
    const volIndexPaths = volBuilder.collectVolumePaths(rawConfig);
    const { generated: volIndexCount } = await volBuilder.buildAll(rawConfig, DIST);
    console.log(`   Volume index.js: ${volIndexCount} generated`);
    // Deploy assets
    console.log('\nDeploying reader shell assets');
    for (const asset of ['nav.js', 'reader.js', 'reader.css']) {
      const src = path.join(__dirname, asset);
      if (fsSync.existsSync(src)) {
        await fs.copyFile(src, path.join(DIST, 'assets', asset));
        console.log(`   ${asset}`);
      } else { console.warn(`   Not found: ${src}`); }
    }

    // Browser-wrapped libmap.js
    const libmapSrc = path.resolve(args.config);
    if (fsSync.existsSync(libmapSrc)) {
      const code = fsSync.readFileSync(libmapSrc, 'utf-8');
      const match = code.match(/LIBRARY_CONFIG\s*=\s*(\[[\s\S]*\]);/);
      const out = match ? `window.LIBRARY_CONFIG=${match[1]};` : code;
      await fs.writeFile(path.join(DIST, 'assets', 'libmap.js'), out, 'utf-8');
      console.log(`   libmap.js -> assets/libmap.js (${match ? 'browser-wrapped' : 'raw copy'})`);
    }

    // Scan & process with concurrency limit
    let rendered = 0, copied = 0;
    const executing = new Set();

    for await (const item of scanner.scan()) {
      if (volIndexPaths.has(item.path)) continue;

      const p = (async () => {
        if (item.type === 'render') {
          if (await renderer.render(item) === 'rendered') rendered++;
        } else {
          await copyProcessor(item, DIST);
          copied++;
        }
      })().finally(() => executing.delete(p));
      executing.add(p);
      if (executing.size >= CONCURRENCY) await Promise.race(executing);

      const total = rendered + copied;
      if (total % 1000 === 0) process.stdout.write(`\rProgress: rendered ${rendered} | copied ${copied}   `);
    }
    await Promise.all(executing);
    process.stdout.write(`\rProgress: rendered ${rendered} | copied ${copied}   \n`);
    await fs.writeFile(path.join(DIST, 'index.html'), renderer.generateCardIndex(rawConfig));

    console.log(`\nDone: ${rendered} pages rendered | ${copied} assets copied | vol indexes ${volIndexCount} | ${((Date.now() - start) / 1000).toFixed(1)}s`);
  }
}

new BuildEngine().build().catch(e => { console.error('\nBuild failed:', e); process.exit(1); });