(function () {
  'use strict';

  /* ===== 基础工具 ===== */
  class EventBag {
    constructor() { this._off = []; }
    on(t, e, h, o) {
      if (!t) return () => { };
      t.addEventListener(e, h, o || false);
      const off = () => t.removeEventListener(e, h, o || false);
      this._off.push(off);
      return off;
    }
    clear() { while (this._off.length) this._off.pop()(); }
  }

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const esc = v => String(v ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const cssEsc = v => (window.CSS?.escape ? CSS.escape(String(v)) : String(v).replace(/["\\]/g, '\\$&'));
  const hasSel = () => { const s = document.getSelection(); return !!(s && !s.isCollapsed && s.rangeCount); };
  const scrollToEl = (el, off = 80, b = 'smooth') => el && window.scrollTo({ top: Math.max(0, el.getBoundingClientRect().top + scrollY - off), behavior: b });

  const scrollCB = new Set();
  let scrollFrame = 0;
  const runScroll = () => { scrollFrame = 0; scrollCB.forEach(fn => fn()); };
  window.addEventListener('scroll', () => { if (!scrollFrame) scrollFrame = requestAnimationFrame(runScroll); }, { passive: true });
  const onScrollFrame = fn => { scrollCB.add(fn); return () => scrollCB.delete(fn); };

  const findCollection = path => {
    const norm = ReaderPaths.normalizePath(path);
    return (window.LIBRARY_CONFIG || []).find(c => ReaderPaths.startsWithPath(norm, c?.basePath || c?.basepath || `/${c?.id || ''}/`)) || null;
  };

  const getDomHeadings = c => c ? $$('h1,h2,h3,h4,h5,h6', c).filter(h => h.id) : [];
  const getActiveHeading = (headings, t = 200) => {
    if (!headings?.length) return null;
    for (let i = headings.length - 1; i >= 0; i--) if (headings[i].getBoundingClientRect().top <= t) return headings[i].id;
    return headings[0].id;
  };

  const buildTree = headings => {
    const root = { level: 0, children: [] }, stack = [root];
    headings.forEach(item => {
      const node = { ...item, children: [] };
      while (stack.length > 1 && stack[stack.length - 1].level >= item.level) stack.pop();
      stack[stack.length - 1].children.push(node);
      stack.push(node);
    });
    return root.children;
  };

  const expandTo = (el, container) => {
    if (!el || !container) return;
    let p = el.closest('li');
    while (p && container.contains(p)) {
      if (p.classList.contains('sidebar-item--collapsible')) {
        p.setAttribute('data-collapsed', 'false');
        const c = $('.sidebar-caret', p);
        if (c) c.textContent = '\u25be';
      }
      p = p.parentElement?.closest('.sidebar-item');
    }
  };

  const volCache = new Map();
  async function fetchVolData(dir, cache = volCache) {
    const clean = ReaderPaths.normalizePath(dir);
    if (!clean) return null;
    if (cache instanceof Map && cache.has(clean)) return cache.get(clean);
    if (!(cache instanceof Map) && cache[clean]) return cache[clean];

    const load = async d => {
      let data = null;
      try {
        const r = await fetch(new URL(d + '/index.json', location.href).href);
        if (r.ok) data = await r.json();
      } catch { }
      if (data) return data;
      try {
        const r = await fetch(new URL(d + '/index.js', location.href).href);
        const t = r.headers.get('content-type') || '';
        if (!r.ok || /text\/html/i.test(t)) return null;
        const js = await r.text();
        if (!/\bexport\s+default\b/.test(js)) return null;
        const b = URL.createObjectURL(new Blob([js], { type: 'text/javascript' }));
        const m = await import(b);
        URL.revokeObjectURL(b);
        return m?.default || null;
      } catch { return null; }
    };

    const lower = clean.toLowerCase();
    let data = await load(clean);
    if (!data && lower !== clean) {
      if (cache instanceof Map && cache.has(lower)) data = cache.get(lower);
      else if (!(cache instanceof Map) && cache[lower]) data = cache[lower];
      else data = await load(lower);
    }
    if (data) {
      if (cache instanceof Map) cache.set(clean, data);
      else cache[clean] = data;
      if (lower !== clean) {
        if (cache instanceof Map) cache.set(lower, data);
        else cache[lower] = data;
      }
    }
    return data;
  }

  /* ===== 路径处理 ===== */
  class ReaderPaths {
    static specRe = /^(?:mailto|tel|javascript|data|blob):/i;
    static httpRe = /^https?:$/i;

    static normalizePath(v) {
      return String(v || '').replace(/^https?:\/\/[^/]+/i, '').replace(/[?#].*$/, '').replace(/^\/+/, '').replace(/\/+$/, '');
    }
    static normalizeDoc(v) { return this.normalizePath(v).replace(/\.html$/i, ''); }
    static sameDoc(a, b) { return this.normalizeDoc(a).toLowerCase() === this.normalizeDoc(b).toLowerCase(); }
    static samePath(a, b) { return this.normalizePath(a).toLowerCase() === this.normalizePath(b).toLowerCase(); }
    static startsWithPath(p, b) {
      const cp = this.normalizePath(p), cb = this.normalizePath(b);
      return cb ? (cp.startsWith(cb + '/') || cp.toLowerCase().startsWith(cb.toLowerCase() + '/')) : false;
    }
    static safeDecode(v) { try { return decodeURIComponent(v); } catch { return v; } }
    static resolveUrl(h) { try { return new URL(h, location.href).href; } catch { return location.pathname.replace(/[^/]*$/, '') + h; } }
    static docBaseUrl(base = '') {
      const c = this.normalizePath(base);
      return new URL('/' + (c ? c.replace(/\/?$/, '/') : ''), location.origin);
    }
    static docPathFromUrl(url) {
      const rp = this.normalizePath(location.pathname);
      const p = this.safeDecode(url.pathname);
      if (this.samePath(p, rp) && url.searchParams.has('doc')) return url.searchParams.get('doc') || '';
      return p + url.search;
    }
    static resolveDocHref(href, base = '') {
      const raw = String(href || '').trim();
      if (!raw) return null;
      if (raw.startsWith('#')) return { type: 'anchor', href: raw, hash: raw.slice(1) };
      if (this.specRe.test(raw)) return { type: 'external', href: raw };
      let url;
      try { url = new URL(raw, raw.startsWith('?') ? location.href : this.docBaseUrl(base)); }
      catch { return { type: 'external', href: raw }; }
      if (!this.httpRe.test(url.protocol) || url.origin !== location.origin) return { type: 'external', href: url.href };
      const dp = this.docPathFromUrl(url);
      if (!dp) return { type: 'external', href: url.href };
      const hash = url.hash.slice(1);
      const target = this.readerHref(dp);
      return { type: 'doc', href: target + (hash ? '#' + hash : ''), docPath: dp, hash };
    }
    static readerHref(dp, hash = '') {
      const raw = String(dp || '');
      const i = raw.indexOf('#');
      const path = i >= 0 ? raw.slice(0, i) : raw;
      const h = hash || (i >= 0 ? raw.slice(i + 1) : '');
      return location.pathname + '?doc=' + path + (h ? '#' + h : '');
    }
    static resolveCssHref(href, base) {
      if (!href) return '';
      if (/^(https?:|\/\/)/i.test(href)) return href;
      try {
        const dir = String(base || '').replace(/\/?$/, '/');
        const bu = dir.startsWith('/') ? new URL(dir, location.origin) : new URL(dir, location.href);
        const u = new URL(href, bu);
        return u.pathname + u.search + u.hash;
      } catch {
        return [String(base || '').replace(/^\/+|\/+$/g, ''), href.replace(/^\.+\//, '')].filter(Boolean).join('/');
      }
    }
    static lowerPathFallback(v) {
      const raw = String(v || '');
      if (!raw) return raw;
      if (/^[a-z][a-z0-9+.-]*:/i.test(raw) || raw.startsWith('/')) {
        try {
          const u = new URL(raw, location.href);
          if (u.origin === location.origin) {
            const n = new URL(u.href);
            n.pathname = n.pathname.toLowerCase();
            return /^[a-z][a-z0-9+.-]*:/i.test(raw) ? n.href : n.pathname + n.search + n.hash;
          }
        } catch { }
        return raw;
      }
      const qi = raw.indexOf('?'), hi = raw.indexOf('#');
      const sp = [qi, hi].filter(i => i >= 0).sort((a, b) => a - b)[0];
      return sp >= 0 ? raw.slice(0, sp).toLowerCase() + raw.slice(sp) : raw.toLowerCase();
    }
  }

  const nPath = v => ReaderPaths.normalizePath(v);
  const nDoc = v => ReaderPaths.normalizeDoc(v);
  const sameDoc = (a, b) => ReaderPaths.sameDoc(a, b);
  const samePath = (a, b) => ReaderPaths.samePath(a, b);
  const startsWithPath = (p, b) => ReaderPaths.startsWithPath(p, b);
  const resolveUrl = h => ReaderPaths.resolveUrl(h);
  const resolveDocHref = (h, b) => ReaderPaths.resolveDocHref(h, b);
  const readerHref = (dp, h) => ReaderPaths.readerHref(dp, h);
  const resolveCssHref = (h, b) => ReaderPaths.resolveCssHref(h, b);

  async function fetchWithLowerFallback(path, opts) {
    const lower = ReaderPaths.lowerPathFallback(path);
    try {
      const res = await fetch(path, opts);
      if (res.ok || !lower || lower === path) return { res, path, url: path };
      try {
        const fb = await fetch(lower, opts);
        if (fb.ok) return { res: fb, path: lower, url: lower };
      } catch { }
      return { res, path, url: path };
    } catch (err) {
      if (!lower || lower === path) throw err;
      try { return { res: await fetch(lower, opts), path: lower, url: lower }; }
      catch { throw err; }
    }
  }

  /* ===== 标题追踪 ===== */
  class HeadingTracker {
    constructor({ getHeadings, onChange, threshold = 200 }) {
      this.getHeadings = getHeadings;
      this.onChange = onChange;
      this.threshold = threshold;
      this.headings = [];
      this.tops = [];
      this.activeId = null;
      this.frame = 0;
      this.bag = new EventBag();
      this.offScroll = null;
    }
    start() {
      this.stop();
      this.headings = this.getHeadings();
      if (!this.headings.length) return false;
      this.measure();
      const qm = () => { if (!this.frame) this.frame = requestAnimationFrame(() => { this.frame = 0; this.measure(); this.track(true); }); };
      this.bag.on(window, 'resize', qm, { passive: true });
      this.bag.on(window, 'load', qm, { once: true });
      setTimeout(qm, 500);
      this.offScroll = onScrollFrame(() => this.track(false));
      this.track(true);
      return true;
    }
    stop() {
      this.bag.clear();
      if (this.offScroll) this.offScroll();
      this.offScroll = null;
      if (this.frame) cancelAnimationFrame(this.frame);
      this.frame = 0;
      this.headings = []; this.tops = []; this.activeId = null;
    }
    measure() { this.tops = this.headings.map(h => h.getBoundingClientRect().top + scrollY); }
    track(force) {
      if (hasSel()) return;
      const id = this.pick();
      if (force || id !== this.activeId) { this.activeId = id; this.onChange(id); }
    }
    pick() {
      if (!this.tops.length) return this.headings[0]?.id || null;
      const y = scrollY + this.threshold;
      let lo = 0, hi = this.tops.length - 1, best = 0;
      while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        if (this.tops[mid] <= y) { best = mid; lo = mid + 1; } else { hi = mid - 1; }
      }
      return this.headings[best]?.id || null;
    }
  }

  /* ===== 菜单管理 ===== */
  const currentDoc = () => (window.ReaderState?.doc || (typeof state !== 'undefined' ? state.doc : null) || '');

  class MenuManager {
    constructor() {
      this.sidebar = null; this.navTree = null; this.mode = 'libmap';
      this.currentVol = null; this.activeHeadingId = null;
      this.activeSidebarLink = null; this.activeTocLink = null;
      this.lastSyncedId = null; this.linkCache = null;
      this.tracker = null; this.bag = new EventBag();
      this.sidebarObserver = null; this.waitObserver = null;
      this.fadeObserver = null; this.volCache = new Map();
    }

    init() {
      this.sidebar = $('#lsidebar'); this.navTree = $('#nav-tree');
      if (!this.sidebar || !this.navTree) return;
      this.bindEvents();
      this.observeSidebar();
      this.reinit(currentDoc());
    }

    reinit(docPath) {
      this.cleanup();
      this.navTree.innerHTML = '';
      this.currentVol = docPath ? this.detectVolume(docPath) : null;
      if (!docPath) { this.mode = 'libmap'; this.renderLibmap(); }
      else if (this.currentVol) { this.mode = 'epub'; this.renderEpub(docPath); }
      else if (innerWidth < 997 && getDomHeadings($('#content')).length > 1) { this.mode = 'page-toc'; this.renderPageToc(docPath); }
      else { this.mode = 'libmap'; this.renderLibmap(); }
      this.afterRender(docPath);
    }

    cleanup() {
      if (this.tracker) this.tracker.stop();
      this.tracker = null;
      if (this.waitObserver) this.waitObserver.disconnect();
      this.waitObserver = null;
      if (this.fadeObserver) { this.fadeObserver.disconnect(); this.fadeObserver = null; }
      this.activeHeadingId = this.activeSidebarLink = this.activeTocLink = this.lastSyncedId = null;
      this.linkCache = null;
    }

    bindEvents() {
      if (this._bound) return;
      this._bound = true;
      this.navTree.addEventListener('click', e => this.handleClick(e));
      this.navTree.addEventListener('keydown', e => {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        const t = e.target.closest('.sidebar-caret, .sidebar-category-label');
        if (!t) return;
        e.preventDefault();
        this.toggleItem(t.closest('.sidebar-item--collapsible'));
      });
    }

    observeSidebar() {
      if (this.sidebarObserver) return;
      this.sidebarObserver = new MutationObserver(() => {
        if (innerWidth < 997 && this.sidebar.classList.contains('doc-sidebar--open')) {
          this.lastSyncedId = null; this.syncSidebar(this.activeHeadingId);
        }
      });
      this.sidebarObserver.observe(this.sidebar, { attributes: true, attributeFilter: ['class'] });
    }

    handleClick(e) {
      const t = e.target.nodeType === 1 ? e.target : e.target.parentElement;
      const expand = t?.closest('a[data-expand-section]');
      if (expand) { e.preventDefault(); e.stopPropagation(); this.expandSection(expand.dataset.expandSection); return; }
      const toggle = t?.closest('.sidebar-caret, .sidebar-category-label');
      if (toggle && !toggle.closest('a')) {
        const item = toggle.closest('.sidebar-item--collapsible');
        if (item) { e.preventDefault(); e.stopPropagation(); this.toggleItem(item); return; }
      }
      const link = t?.closest('.sidebar-link');
      if (!link) return;
      const href = link.getAttribute('href') || '';
      if (href.startsWith('#')) { e.preventDefault(); this.scrollToHash(href.slice(1), true); return; }
      const url = new URL(href, location.href);
      if (ReaderPaths.samePath(url.pathname, location.pathname) && url.searchParams.has('doc')) {
        const docPath = url.searchParams.get('doc') || '';
        const hash = url.hash.slice(1);
        if (sameDocValue(docPath, currentDoc())) {
          e.preventDefault();
          if (hash) this.scrollToHash(hash, true);
          else window.scrollTo({ top: 0, left: 0, behavior: 'smooth' });
        } else if (hash) {
          sessionStorage.setItem('__reader_pending_anchor', hash);
          sessionStorage.setItem('__reader_pending_doc', docPath);
        }
      }
    }

    toggleItem(item) {
      if (!item) return;
      if (item.dataset.section && !item.dataset.loaded) this.loadSection(item);
      const collapsed = item.getAttribute('data-collapsed') !== 'false';
      item.setAttribute('data-collapsed', collapsed ? 'false' : 'true');
      const c = $('.sidebar-caret', item);
      if (c) c.textContent = collapsed ? '\u25be' : '\u25b8';
    }

    loadSection(item) {
      const col = (window.LIBRARY_CONFIG || []).find(c => c.id === item.dataset.section);
      if (!col) return;
      const html = (col.groups || []).map(g => this.renderGroup(g)).join('');
      if (html) {
        const ul = document.createElement('ul');
        ul.className = 'sidebar-menu sidebar-menu--nested';
        ul.innerHTML = html;
        item.appendChild(ul);
      }
      item.dataset.loaded = 'true';
    }

    expandSection(id) {
      const item = this.navTree.querySelector(`.sidebar-item[data-section="${cssEsc(id)}"]`);
      if (!item) return;
      if (item.getAttribute('data-collapsed') !== 'false') this.toggleItem(item);
      requestAnimationFrame(() => item.scrollIntoView({ block: 'center', behavior: 'smooth' }));
    }

    scrollToHash(hash, push) {
      if (!hash) return;
      const el = document.getElementById(hash) || document.querySelector(`[name="${cssEsc(hash)}"]`);
      if (!el) return;
      scrollToEl(el);
      const url = new URL(location.href);
      url.hash = hash;
      history[push ? 'pushState' : 'replaceState']({}, '', url);
    }

    detectVolume(docPath) {
      const pathNorm = nPath(docPath);
      const docNorm = nDoc(pathNorm);
      const docDir = pathNorm.replace(/\/[^/]+$/, '');
      const docLower = docNorm.toLowerCase();
      const dirLower = docDir.toLowerCase();
      const matchPath = p => {
        if (!p || /^https?:/i.test(p)) return null;
        const ip = nPath(p);
        if (!/\/index\.html$/i.test(ip)) return null;
        const d = ip.replace(/\/index\.html$/i, '').replace(/\/nav\.html$/i, '');
        return (docLower === nDoc(ip).toLowerCase() || docLower === nDoc(d).toLowerCase() || dirLower === d.toLowerCase() || pathNorm.toLowerCase().startsWith(d.toLowerCase() + '/')) ? d : null;
      };
      let best = null;
      const consider = (col, group, item, dir) => {
        if (dir && (!best || dir.length > best.dir.length)) best = { col, group, item, dir };
      };
      for (const col of window.LIBRARY_CONFIG || []) {
        consider(col, null, col, matchPath(col.path));
        for (const group of col.groups || []) {
          consider(col, group, group, matchPath(group.path));
          for (const item of group.items || []) consider(col, group, item, matchPath(item.path));
        }
      }
      return best;
    }

    volumeDocPath(dp = currentDoc()) {
      const p = nPath(dp);
      if (this.currentVol && sameDoc(p, this.currentVol.dir)) return this.currentVol.dir + '/index.html';
      return p;
    }

    volumeDocFile(dp = currentDoc()) {
      return nDoc(this.volumeDocPath(dp)).split('/').pop() || 'index';
    }

    async renderEpub(docPath) {
      const dir = this.currentVol?.dir || '';
      const data = await this.fetchVolumeData(dir);
      if (!data) {
        const np = nPath(docPath);
        const fallback = sameDoc(np, dir) || sameDoc(np, dir + '/index.html') || sameDoc(np, dir + '/nav.html');
        this.mode = fallback ? 'libmap' : (innerWidth < 997 ? 'page-toc' : 'libmap');
        this.mode === 'page-toc' ? this.renderPageToc(docPath) : this.renderLibmap();
        this.afterRender(docPath);
        return;
      }
      this.currentVol.data = data;
      const { col, item } = this.currentVol;
      const parts = [col.path ? { text: col.label, href: readerHref(col.path), expand: col.id } : { text: col.label, expand: col.id }];
      if (item !== col) {
        const vp = item.path || (this.currentVol.dir + '/index.html');
        parts.push({ text: item.label || item.title || data.title || 'Contents', href: readerHref(vp) });
      }
      parts.push({ id: 'page-breadcrumb-link', isPageBadge: window.__PAGE_BAR__?.hasPageAnchors });
      const tree = buildTree(data.headings || []);
      this.navTree.innerHTML = this.renderBreadcrumb(parts) + (tree.length ? this.renderSidebarTree(tree, 'epub-toc', docPath) : '') + this.libmapDivider() + this.buildLibmapHtml();
      this.afterRender(docPath);
    }

    renderPageToc(docPath) {
      const headings = getDomHeadings($('#content'));
      if (headings.length <= 1) { this.mode = 'libmap'; this.renderLibmap(); this.afterRender(docPath); return; }
      const col = this.currentVol?.col || findCollection(docPath);
      const currentFile = nPath(docPath).split('/').pop();
      const nodes = headings.map(h => ({ level: Number(h.tagName[1]) || 2, text: h.textContent.trim(), id: h.id, file: currentFile }));
      const parts = [
        col?.path ? { text: col.label || 'Library', href: readerHref(col.path), expand: col.id } : { text: col?.label || 'Library', expand: col?.id },
        { text: nodes[0]?.text || document.title }
      ];
      this.navTree.innerHTML = this.renderBreadcrumb(parts) + this.renderSidebarTree(buildTree(nodes), 'page-toc', docPath) + this.libmapDivider() + this.buildLibmapHtml();
      this.afterRender(docPath);
    }

    renderLibmap() { this.navTree.innerHTML = this.buildLibmapHtml(); }

    afterRender(docPath) {
      this.linkCache = null;
      this.highlightCurrent(docPath);
      this.renderTocRail();
      this.startTracking();
      this.scrollToPendingAnchor();
      this.initFade();
      if (window.__PAGE_BAR__?.currentPage != null) window.__PAGE_BAR__._updateBadge(window.__PAGE_BAR__.currentPage);
    }

    initFade() {
      if (this.mode !== 'epub' && this.mode !== 'page-toc') return;
      if (this.fadeObserver) { this.fadeObserver.disconnect(); this.fadeObserver = null; }
      const bc = $('.breadcrumb', this.navTree), menu = $('.sidebar-menu', this.navTree);
      if (!bc || !menu) return;
      this.fadeObserver = new IntersectionObserver(entries => {
        entries.forEach(en => bc.classList.toggle('breadcrumb--faded', en.boundingClientRect.bottom < en.rootBounds.top));
      }, { root: this.navTree, threshold: 0 });
      this.fadeObserver.observe(menu);
    }

    async fetchVolumeData(dir) {
      const raw = await fetchVolData(dir, this.volCache);
      if (!raw) return null;
      if (!Array.isArray(raw) && raw.version === 1) return raw;
      if (!Array.isArray(raw)) return null;
      const headings = [];
      raw.forEach(f => (f.headings || []).forEach(h => {
        headings.push({ level: h.level != null ? h.level : 2, text: h.text || '', id: h.id || null, file: h.filename || f.file || f.path || '' });
      }));
      return { version: 1, title: this.currentVol?.item?.label || dir, files: raw, headings };
    }

    renderBreadcrumb(parts) {
      return '<div class="breadcrumb" aria-label="Breadcrumb">' + parts.map((p, i) => {
        const sep = i > 0 || p.id === 'page-breadcrumb-link' ? '<span class="breadcrumb__sep">/</span>' : '';
        if (p.id === 'page-breadcrumb-link' && !p.isPageBadge) return '';
        if (p.id === 'page-breadcrumb-link') return sep + `<a href="#" id="${esc(p.id)}" style="display:none"></a>`;
        if (p.href) return sep + `<a href="${esc(p.href)}"${p.expand ? ` data-expand-section="${esc(p.expand)}"` : ''}>${esc(p.text)}</a>`;
        return sep + `<span>${esc(p.text || '')}</span>`;
      }).join('') + '</div>';
    }

    renderNavLink({ href, path, text, badge = '', className = 'sidebar-link', dataFile = '', dataId = '', extra = '' }) {
      const raw = String(href || path || '').trim();
      const ext = /^(?:http|https):/i.test(raw);
      const clean = !href && !ext ? nPath(raw) : '';
      const final = ext || href ? raw : readerHref(raw);
      const attrs = [
        `href="${esc(final)}"`, !href && clean ? `data-path="${esc('/' + clean)}"` : '',
        dataFile ? `data-file="${esc(dataFile)}"` : '', dataId ? `data-id="${esc(dataId)}"` : '',
        extra, `class="${esc(className)}"`
      ].filter(Boolean).join(' ');
      return `<a ${attrs}>${esc(text || '')}${badge}</a>`;
    }

    renderSidebarTree(nodes, className, docPath) {
      return `<ul class="sidebar-menu ${esc(className)}">${this.renderSidebarNodes(nodes, nDoc(this.volumeDocPath(docPath || currentDoc())))}</ul>`;
    }

    renderSidebarNodes(nodes, currentFull) {
      const volDir = this.currentVol?.dir || '';
      const isPage = this.mode === 'page-toc';
      const curHref = readerHref(this.volumeDocPath(currentDoc()));
      return nodes.map(n => {
        const raw = n.file || '';
        const full = raw && !isPage ? nPath((volDir + '/' + raw).replace(/\/+/g, '/')) : raw;
        const same = isPage || (full && sameDoc(full, currentFull));
        const href = isPage ? (n.id ? `#${esc(n.id)}` : curHref) : same ? (n.id ? `#${esc(n.id)}` : readerHref(full || currentFull)) : readerHref(full, n.id || '');
        const children = n.children?.length ? `<ul class="sidebar-menu sidebar-menu--nested">${this.renderSidebarNodes(n.children, currentFull)}</ul>` : '';
        const caret = children ? '<button class="sidebar-caret" type="button" aria-label="Expand section" tabindex="0">\u25b8</button>' : '';
        const link = this.renderNavLink({ href, text: n.text, dataFile: raw, dataId: n.id || '' });
        return children
          ? `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-collapsed="true"><div class="sidebar-item-row">${link}${caret}</div>${children}</li>`
          : `<li class="sidebar-item">${link}</li>`;
      }).join('');
    }

    buildLibmapHtml() {
      if (!window.LIBRARY_CONFIG?.length) return '<div class="sidebar-menu" style="padding:20px">Navigation unavailable</div>';
      return '<ul class="sidebar-menu">' + (window.LIBRARY_CONFIG || []).map(c => this.renderSection(c)).join('') + '</ul>';
    }

    renderSection(col) {
      const label = esc(col.label || col.title || col.id || '');
      const badge = col.badge ? ` <span class="sidebar-badge">${esc(col.badge)}</span>` : '';
      const groups = col.groups || [];
      if (!groups.length && col.path) return `<li class="sidebar-item">${this.renderNavLink({ path: col.path, text: col.label || col.title || col.id || '', badge })}</li>`;
      if (groups.length) {
        const direct = groups.every(g => g.path && !(g.items || []).length);
        const nested = direct ? `<ul class="sidebar-menu sidebar-menu--nested">${groups.map(g => this.renderGroup(g)).join('')}</ul>` : '';
        return `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-section="${esc(col.id)}" data-collapsed="true"${direct ? ' data-loaded="true"' : ''}><div class="sidebar-item-row"><span class="sidebar-category-label">${label}${badge}</span><button class="sidebar-caret" type="button" aria-label="Expand section" tabindex="0">\u25b8</button></div>${nested}</li>`;
      }
      return `<li class="sidebar-item"><span class="sidebar-category-label">${label}${badge}</span></li>`;
    }

    renderGroup(group) {
      const label = esc(group.label || '');
      const items = group.items || [];
      const raw = String(group.path || '').trim();
      const gp = nPath(group.path);
      if (!items.length) {
        if (!raw) return `<li class="sidebar-item"><span class="sidebar-category-label">${label}</span></li>`;
        return `<li class="sidebar-item">${this.renderNavLink({ path: group.path, text: group.label || '' })}</li>`;
      }
      return `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-group-path="${esc(gp)}" data-collapsed="true"><div class="sidebar-item-row"><span class="sidebar-category-label">${label}</span><button class="sidebar-caret" type="button" aria-label="Expand section" tabindex="0">\u25b8</button></div><ul class="sidebar-menu sidebar-menu--nested">${items.map(item => `<li class="sidebar-item">${this.renderNavLink({ path: item.path || '', text: item.label || item.title || '' })}</li>`).join('')}</ul></li>`;
    }

    libmapDivider() { return '<div class="section-divider"><span>All works</span></div>'; }

    getPageHeadings() {
      if (this.mode === 'epub') {
        const file = this.volumeDocFile();
        const dom = getDomHeadings($('#content'));
        let idx = 0;
        return (this.currentVol?.data?.headings || []).filter(h => sameDoc(nDoc(h.file || '').split('/').pop(), file)).map(h => {
          const id = h.id || dom[idx++]?.id || null;
          return { level: h.level != null ? h.level : 2, text: h.text || '', id };
        }).filter(h => h.id);
      }
      return getDomHeadings($('#content')).map(h => ({ level: Number(h.tagName[1]) || 2, text: h.textContent.trim(), id: h.id }));
    }

    renderTocRail() {
      const nav = $('#toc-desktop-nav');
      if (!nav) return;
      const headings = this.getPageHeadings();
      nav.innerHTML = headings.length ? this.renderTocNodes(buildTree(headings)) : '';
      this.activeTocLink = null;
    }

    renderTocNodes(nodes) {
      if (!nodes.length) return '';
      return '<ul class="theme-doc-toc-desktop-list">' + nodes.map(n =>
        `<li class="theme-doc-toc-desktop-link theme-doc-toc-desktop-link--lvl${n.level}"><a href="#${esc(n.id)}" class="theme-doc-toc-desktop-link__a">${esc(n.text)}</a>${this.renderTocNodes(n.children || [])}</li>`
      ).join('') + '</ul>';
    }

    startTracking() {
      const content = $('#content');
      const start = () => {
        if (this.tracker) this.tracker.stop();
        this.tracker = new HeadingTracker({ getHeadings: () => getDomHeadings(content), onChange: id => this.updateTracking(id) });
        return this.tracker.start();
      };
      if (!content || start()) return;
      const mo = new MutationObserver((_, o) => { if (start()) o.disconnect(); });
      mo.observe(content, { subtree: true, attributes: true, attributeFilter: ['id'] });
      this.waitObserver = mo;
    }

    updateTracking(id) {
      this.activeHeadingId = id;
      this.updateSidebarTracking(id);
      this.updateTocTracking(id);
      this.syncSidebar(id);
    }

    setActive(slot, link, cls) {
      this[slot]?.classList.remove(cls);
      this[slot] = null;
      if (!link) return false;
      link.classList.add(cls);
      this[slot] = link;
      return true;
    }

    getSidebarLinks() {
      const tree = this.navTree.querySelector('.sidebar-menu');
      if (!tree) return [];
      if (!this.linkCache || this.linkCache.tree !== tree) this.linkCache = { tree, links: $$('.sidebar-link', tree) };
      return this.linkCache.links;
    }

    updateSidebarTracking(id) {
      if (this.mode === 'libmap') return;
      const links = this.getSidebarLinks();
      if (!links.length) return;
      const file = this.volumeDocFile();
      const sameFile = a => sameDoc(nDoc(a.dataset.file || '').split('/').pop(), file);
      const exact = id && links.find(a => sameFile(a) && a.dataset.id === id);
      if (exact) {
        if (!this.setActive('activeSidebarLink', exact, 'sidebar-link--active')) return;
        expandTo(exact, this.navTree.querySelector('.sidebar-menu'));
        return;
      }
      // 正文锚点存在但 sidebar 中无对应链接（index 数据未收录），保持之前的高亮
      if (id && this.activeSidebarLink && sameFile(this.activeSidebarLink)) return;
      const match = links.find(a => sameFile(a) && !a.dataset.id) || links.find(sameFile);
      if (!match) return;
      if (!this.setActive('activeSidebarLink', match, 'sidebar-link--active')) return;
      expandTo(match, this.navTree.querySelector('.sidebar-menu'));
    }

    updateTocTracking(id) {
      const nav = $('#toc-desktop-nav');
      if (!nav) return;
      const match = id ? $$('.theme-doc-toc-desktop-link__a', nav).find(a => a.getAttribute('href') === '#' + id) : null;
      if (match) {
        this.setActive('activeTocLink', match, 'theme-doc-toc-desktop-link__a--active');
      } else if (!id) {
        this.setActive('activeTocLink', null, 'theme-doc-toc-desktop-link__a--active');
      }
      // 正文锚点存在但 TOC 中无对应链接时，保持之前的高亮
    }

    syncSidebar(id) {
      if (innerWidth >= 997 || hasSel() || !id || id === this.lastSyncedId) return;
      if (!this.sidebar?.classList.contains('doc-sidebar--open')) return;
      const active = this.activeSidebarLink || $('.sidebar-link.sidebar-link--active', this.navTree);
      if (!active) return;
      this.lastSyncedId = id;
      requestAnimationFrame(() => active.scrollIntoView({ block: 'center', behavior: 'auto' }));
    }

    highlightCurrent(docPath) {
      const tree = this.navTree.querySelector('.sidebar-menu');
      if (!tree || this.mode === 'libmap') return;
      const file = this.volumeDocFile(docPath || currentDoc());
      const hash = location.hash.slice(1);
      const links = $$('.sidebar-link', tree);
      let best = null, score = 0;
      links.forEach(a => {
        const f = nDoc(a.dataset.file || '').split('/').pop();
        const id = a.dataset.id || '';
        let s = 0;
        if (sameDoc(f, file)) {
          s = 1;
          if (id && hash && id === hash) s = 3;
          else if (!id && !hash) s = 2;
        }
        if (s > score) { score = s; best = a; }
      });
      if (best) {
        best.classList.add('sidebar-link--active');
        this.activeSidebarLink = best;
        expandTo(best, tree);
      }
    }

    scrollToPendingAnchor() {
      const hash = sessionStorage.getItem('__reader_pending_anchor');
      const dp = sessionStorage.getItem('__reader_pending_doc');
      if (!hash) return;
      sessionStorage.removeItem('__reader_pending_anchor');
      sessionStorage.removeItem('__reader_pending_doc');
      if (dp && !sameDoc(dp, currentDoc())) return;
      const tryScroll = () => {
        const el = document.getElementById(hash);
        if (!el) return false;
        scrollToEl(el);
        return true;
      };
      if (!tryScroll()) requestAnimationFrame(() => { if (!tryScroll()) setTimeout(tryScroll, 150); });
    }

    findCollectionByCurrentPath() { return findCollection(currentDoc()); }
  }

  /* ===== 导出 ===== */
  const Core = {
    $, $$, esc, cssEsc, EventBag, ReaderPaths, HeadingTracker,
    normalizePath: nPath, normalizeDoc: nDoc, sameDocValue: sameDoc, samePathValue: samePath, startsWithPathValue: startsWithPath,
    fetchWithLowerFallback, hasSelection: hasSel, resolveUrl, resolveDocHref: resolveDocHref, readerHref, resolveCssHref,
    findCollection, scrollToEl, syncFill: el => {
      if (!el) return;
      const min = parseFloat(el.min) || 0, max = parseFloat(el.max) || 100, val = parseFloat(el.value) || 0;
      el.style.setProperty('--_fill', (((val - min) / (max - min)) * 100).toFixed(2) + '%');
    }, onScrollFrame, getDomHeadings, getActiveHeadingId: getActiveHeading, buildHeadingTree: buildTree, expandTo, fetchVolData
  };

  Object.assign(window, {
    ReaderCore: Core, $, $$, on: (t, e, h, o) => t && t.addEventListener(e, h, o || false),
    esc, syncFill: Core.syncFill, resolveUrl, resolveCssHref, fetchWithLowerFallback,
    findCollection, scrollToEl, getDomHeadings, getActiveHeadingId: getActiveHeading,
    hasActiveTextSelection: hasSel, buildHeadingTree: buildTree, expandTo, fetchVolData, onScrollFrame
  });

  window.MenuManager = MenuManager;
})();