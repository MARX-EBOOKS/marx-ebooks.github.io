(function () {
  'use strict';

  /* reader-nav.js - SPA sidebar navigation
   *  Works with: reader-ui.js, reader-pagebar.js
   *  Link scheme: ?doc=<path>#<hash> */

  /* 基础工具 (unified) */
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const esc = v => String(v ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const cssEsc = v => (window.CSS?.escape ? CSS.escape(String(v)) : String(v).replace(/["\\]/g, '\\$&'));
  const hasSel = () => {
    const s = document.getSelection();
    return !!(s && !s.isCollapsed && s.rangeCount);
  };
  const scrollToEl = (el, off, b = 'smooth') => {
    if (!el) return;
    const offset = off != null ? off : (document.querySelector('.navbar')?.offsetHeight || 80);
    window.scrollTo({ top: Math.max(0, el.getBoundingClientRect().top + scrollY - offset), behavior: b });
  };
  const syncFill = el => {
    if (!el) return;
    const min = parseFloat(el.min) || 0, max = parseFloat(el.max) || 100, val = parseFloat(el.value) || 0;
    el.style.setProperty('--_fill', (((val - min) / (max - min)) * 100).toFixed(2) + '%');
  };

  /* 滚动帧回调 (unified) */
  const scrollCbs = new Set();
  let scrollFrame = 0;
  window.addEventListener('scroll', () => {
    if (!scrollFrame) scrollFrame = requestAnimationFrame(() => { scrollFrame = 0; scrollCbs.forEach(fn => fn()); });
  }, { passive: true });
  const onScrollFrame = fn => {
    scrollCbs.add(fn)
    return () => scrollCbs.delete(fn)
  };

  /* EventBag (unified) */
  class EventBag {
    constructor() { this._off = []; }
    on(t, e, h, o) {
      if (!t) return () => { }
      t.addEventListener(e, h, o || false)
      const off = () => t.removeEventListener(e, h, o || false)
      this._off.push(off)
      return off
    }
    clear() {
      while (this._off.length) this._off.pop()()
    }
  }

  /* DOM 标题工具 (unified) */
  const getHeadings = c => c ? $$('h1,h2,h3,h4,h5,h6', c).filter(h => h.id) : [];
  function buildTree(items) {
    const root = { level: 0, children: [] }, stack = [root];
    items.forEach(it => {
      const n = { ...it, children: [] };
      while (stack.length > 1 && stack[stack.length - 1].level >= it.level) stack.pop();
      stack[stack.length - 1].children.push(n);
      stack.push(n);
    });
    return root.children;
  }
  function expandTo(el, container) {
    for (let li = el?.closest('li'); li && container.contains(li); li = li.parentElement?.closest('.sidebar-item')) {
      if (li.classList.contains('sidebar-item--collapsible')) {
        li.setAttribute('data-collapsed', 'false');
        const c = $('.sidebar-caret', li);
        if (c) c.textContent = '\u25be';
      }
    }
  }

  /* 合集查找 */
  const findCollection = path => {
    const norm = PathUtils.normalizePath(path);
    return (window.LIBRARY_CONFIG || []).find(c => PathUtils.startsWithPath(norm, c?.path || '')) || null;
  };

  /* 路径处理 (SPA 专用，统一收口到 PathUtils) */
  const PathUtils = {
    specRe: /^(?:mailto|tel|javascript|data|blob):/i,
    httpRe: /^https?:$/i,

    normalizePath(v) { return String(v || '').replace(/^https?:\/\/[^/]+/i, '').replace(/[?#].*$/, '').replace(/^\/+/, '').replace(/\/+$/, ''); },
    normalizeDoc(v) { return this.normalizePath(v).replace(/\.x?html?$/i, ''); },
    sameDoc(a, b) { return this.normalizeDoc(a).toLowerCase() === this.normalizeDoc(b).toLowerCase(); },
    samePath(a, b) { return this.normalizePath(a).toLowerCase() === this.normalizePath(b).toLowerCase(); },
    startsWithPath(p, b) {
      const cp = this.normalizePath(p), cb = this.normalizePath(b);
      return cb ? (cp.startsWith(cb + '/') || cp.toLowerCase().startsWith(cb.toLowerCase() + '/')) : false;
    },
    safeDecode(v) { try { return decodeURIComponent(v); } catch { return v; } },
    resolveUrl(h) { try { return new URL(h, location.href).href; } catch { return location.pathname.replace(/[^/]*$/, '') + h; } },
    splitHash(v) {
      const raw = String(v || '');
      const i = raw.indexOf('#');
      return i >= 0 ? { path: raw.slice(0, i), hash: raw.slice(i + 1) } : { path: raw, hash: '' };
    },
    isSpecial(raw) { return this.specRe.test(String(raw || '')) || /^[a-z][a-z0-9+.-]*:/i.test(String(raw || '')); },
    rootPath(path) {
      const raw = String(path || '').trim();
      if (!raw || raw.startsWith('/') || raw.startsWith('?') || this.isSpecial(raw)) return raw;
      return '/' + raw.replace(/^\.?\//, '');
    }
  };

  // 常用别名 (解构自 PathUtils)
  const normPath = v => PathUtils.normalizePath(v);
  const normDoc = v => PathUtils.normalizeDoc(v);
  const sameDoc = (a, b) => PathUtils.sameDoc(a, b);
  const makeHref = (dp, h) => PathResolver.makeSpa(dp, h);
  const resolveDocHref = (h, b) => PathResolver.resolve(b || '', h);

  const PathResolver = {
    special: /^(?:mailto|tel|javascript|data|blob):/i,

    split(v) {
      const raw = String(v || '').trim();
      const h = raw.indexOf('#');
      if (h >= 0) {
        return { path: raw.slice(0, h), hash: raw.slice(h + 1) };
      }
      return { path: raw, hash: '' };
    },

    doc(v) {
      const parts = this.split(v);
      let raw = parts.path.replace(/^https?:\/\/[^/]+/i, '');
      const q = raw.indexOf('?');
      const query = q >= 0 ? raw.slice(q + 1) : '';
      const doc = query ? new URLSearchParams(query).get('doc') : '';
      const result = (doc || raw) + (parts.hash ? '#' + parts.hash : '');
      return result;
    },

    dir(base) {
      const p = this.split(this.doc(base)).path.replace(/[?#].*$/, '');
      if (!p || p.endsWith('/')) {
        return p;
      }
      return p.slice(0, p.lastIndexOf('/') + 1);
    },

    path(base, href) {
      const parts = this.split(this.doc(href));
      const raw = parts.path;
      if (!raw || raw.startsWith('/') || raw.startsWith('?')) {
        return raw + (parts.hash ? '#' + parts.hash : '');
      }
      let domain = (base && /^(?:[\S]+?:)?\/\//i.test(base) && !base.startsWith(location.origin)) ? base.replace(/^((?:[\S]+?:)?\/\/[^/?#]+).*/, '$1') : '';
      let dir = this.dir(base);
      let rel = raw.replace(/^\.\//, '');
      for (; rel.startsWith('../'); rel = rel.slice(3)) {
        dir = dir.replace(/\/?[^/]+\/?$/, '/');
      }
      domain = (domain && !dir.startsWith('/')) ? domain + '/' : domain;
      const result = domain + (dir.replace(/\/?$/, '/') + rel).replace(/\/+/g, '/').replace(/^([^/])/, '/$1');
      return result + (parts.hash ? '#' + parts.hash : '');
    },

    makeSpa(path, hash = '') {
      const p = this.split(this.doc(path));
      const h = hash || p.hash;
      const spaPath = location.pathname + '?doc=' + this.path('', p.path) + (h ? '#' + h : '');
      return spaPath;
    },

    resolve(base, href) {
      const raw = String(href || '').trim();
      if (!raw) return null;
      if (raw.startsWith('#')) {
        return { type: 'anchor', href: raw, hash: raw.slice(1) };
      }
      if (this.special.test(raw) || (/^(?:https?:)?\/\//i.test(raw) && !raw.startsWith(location.origin))) {
        return { type: 'external', href: raw };
      }
      const p = this.path(this.doc(base), raw);
      const h = this.split(p).hash;
      return {
        type: 'doc',
        href: this.makeSpa(p),
        docPath: this.split(p).path,
        hash: h,
      };
    },

    resolveResource(base, href) {
      const raw = String(href || '').trim();
      if (!raw || this.special.test(raw) || (/^(?:https?:)?\/\//i.test(raw) && !raw.startsWith(location.origin))) {
        return raw;
      }
      return this.path(base, raw);
    },
  };
  /* 带大小写回退的 fetch */
  async function fetchWithLowerFallback(path, opts) {
    const rawPath = String(path || '').trim();
    const external = PathResolver.special.test(rawPath) || (/^(?:https?:)?\/\//i.test(rawPath) && !rawPath.startsWith(location.origin));
    const finalPath = external ? PathResolver.split(rawPath).path : (PathResolver.split(PathResolver.path('', PathResolver.doc(rawPath))).path || '/');
    const lower = (() => {
      if (!finalPath || finalPath.startsWith('?')) return finalPath;
      try {
        const u = new URL(finalPath, location.href);
        if (u.origin !== location.origin) return finalPath;
        u.pathname = u.pathname.toLowerCase();
        return /^[a-z][a-z0-9+.-]*:/i.test(finalPath) ? u.href : u.pathname + u.search;
      } catch {
        const q = finalPath.indexOf('?');
        return q >= 0 ? finalPath.slice(0, q).toLowerCase() + finalPath.slice(q) : finalPath.toLowerCase();
      }
    })();
    const paths = [finalPath, lower].filter((v, i, arr) => v && arr.indexOf(v) === i);
    const tryFetch = async (i, firstErr = null, firstResult = null) => {
      const p = paths[i];
      if (!p) {
        if (firstResult) return firstResult;
        throw firstErr;
      }
      try {
        const res = await fetch(p, opts);
        const result = { res, path: p, url: res.url || p };
        return (res.ok || i === paths.length - 1) ? result : tryFetch(i + 1, firstErr, result);
      } catch (err) {
        if (i === paths.length - 1) {
          if (firstResult) return firstResult;
          throw (firstErr || err);
        }
        return tryFetch(i + 1, firstErr || err, firstResult);
      }
    };
    return tryFetch(0);
  }

  /* 卷册数据获取 (SPA 版：index.json + index.js 双回退) */
  const volCache = new Map();
  async function fetchVolData(dir, cache = volCache) {
    const clean = normPath(dir);
    if (!clean) return null;
    if (cache instanceof Map ? cache.has(clean) : cache[clean]) return cache instanceof Map ? cache.get(clean) : cache[clean];

    const load = async d => {
      try {
        const r = await fetch(new URL('/' + d + '/index.json', location.origin).href)
        if (r.ok) return await r.json()
      }
      catch {
      }
      try {
        const r = await fetch(new URL('/' + d + '/index.js', location.origin).href);
        if (!r.ok || /text\/html/i.test(r.headers.get('content-type') || '')) return null;
        const js = await r.text(); if (!/\bexport\s+default\b/.test(js)) return null;
        const b = URL.createObjectURL(new Blob([js], { type: 'text/javascript' })), m = await import(b);
        URL.revokeObjectURL(b); return m?.default || null;
      } catch { return null; }
    };

    const lower = clean.toLowerCase();
    let data = await load(clean);
    if (!data && lower !== clean) {
      if (cache instanceof Map ? cache.has(lower) : cache[lower]) data = cache instanceof Map ? cache.get(lower) : cache[lower];
      else data = await load(lower);
    }
    if (data) {
      if (cache instanceof Map) {
        cache.set(clean, data)
        if (lower !== clean) cache.set(lower, data)
      }
      else {
        cache[clean] = data
        if (lower !== clean) cache[lower] = data
      }
    }
    return data;
  }

  /* 标题追踪 (unified) */
  class HeadingTracker {
    constructor({ getHeadings: gh, onChange }) {
      this.getHeadings = gh; this.onChange = onChange;
      this.headings = []; this.tops = []; this.activeId = null; this.frame = 0;
      this.bag = new EventBag(); this.offScroll = null;
    }
    start() {
      this.stop(); this.headings = this.getHeadings();
      if (!this.headings.length) return false;
      this.measure();
      const qm = () => {
        if (!this.frame) this.frame = requestAnimationFrame(() => { this.frame = 0; this.measure(); this.track(true); })
      };
      this.bag.on(window, 'resize', qm, { passive: true });
      this.bag.on(window, 'load', qm, { once: true });
      setTimeout(qm, 500);
      this.offScroll = onScrollFrame(() => this.track(false));
      this.track(true); return true;
    }
    stop() {
      this.bag.clear(); if (this.offScroll) this.offScroll(); this.offScroll = null;
      if (this.frame) cancelAnimationFrame(this.frame); this.frame = 0;
      this.headings = []; this.tops = []; this.activeId = null;
    }
    measure() { this.tops = this.headings.map(h => h.getBoundingClientRect().top + scrollY); }
    track(force) {
      if (hasSel()) return;
      const id = this.pick();
      if (force || id !== this.activeId) {
        this.activeId = id
        this.onChange(id)
      }
    }
    pick() {
      if (!this.tops.length) return null;
      const y = scrollY + 80, bottom = y + innerHeight;
      let best = -1;
      for (let i = 0; i < this.tops.length; i++) {
        const t = this.tops[i];
        if (t >= y && t <= bottom) {
          if (best < 0 || t < this.tops[best]) best = i
        }
      }
      if (best < 0) {
        for (let i = this.tops.length - 1; i >= 0; i--) {
          if (this.tops[i] <= y) {
            best = i;
            break;
          }
        }
      }
      return best >= 0 ? (this.headings[best]?.id || null) : null;
    }
  }

  /* MenuManager - SPA 版 */
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
      this.lastWidth = innerWidth;
    }

    /* 生命周期 */
    init() {
      this.sidebar = $('#lsidebar'); this.navTree = $('#nav-tree');
      if (!this.sidebar || !this.navTree) return;
      this.bindEvents(); this.observeSidebar(); this.reinit(currentDoc());
    }

    reinit(docPath) {
      this.cleanup(); this.navTree.innerHTML = '';
      this.currentVol = docPath ? this.detectVolume(docPath) : null;
      if (!docPath) {
        this.mode = 'libmap'
        this.navTree.innerHTML = this.buildLibmap()
      }
      else if (this.currentVol) {
        this.mode = 'epub'
        this.renderEpub(docPath)
      }
      else if (innerWidth < 997 && getHeadings($('#content')).length > 1 && !this._isHome()) {
        this.mode = 'page-toc'
        this.renderPageToc(docPath)
      }
      else {
        this.mode = 'libmap'
        this.navTree.innerHTML = this.buildLibmap()
      }
      this.afterRender(docPath);
    }

    cleanup() {
      if (this.tracker) this.tracker.stop(); this.tracker = null;
      if (this.waitObserver) this.waitObserver.disconnect(); this.waitObserver = null;
      if (this.fadeObserver) {
        this.fadeObserver.disconnect()
        this.fadeObserver = null
      }
      this.activeHeadingId = this.activeSidebarLink = this.activeTocLink = this.lastSyncedId = null;
      this.linkCache = null;
    }

    afterRender(docPath) {
      this.linkCache = null; this.highlight(); this.renderToc();
      this.startTrack(); this.scrollToPendingAnchor(); this.initFade();
      if (window.__PAGE_BAR__?.currentPage != null) window.__PAGE_BAR__._updateBadge(window.__PAGE_BAR__.currentPage);
    }

    /* 事件绑定 */
    bindEvents() {
      if (this._bound) return; this._bound = true;
      this.navTree.addEventListener('click', e => this.handleClick(e));
      this.navTree.addEventListener('keydown', e => {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        const t = e.target.closest('.sidebar-caret, .sidebar-category-label');
        if (!t || t.closest('a')) return; e.preventDefault(); this.toggleItem(t.closest('.sidebar-item--collapsible'));
      });
      window.addEventListener('resize', () => this.handleResize(), { passive: true });
    }
    observeSidebar() {
      if (this.sidebarObserver) return;
      this.sidebarObserver = new MutationObserver(() => {
        if (innerWidth < 997 && this.sidebar.classList.contains('doc-sidebar--open')) {
          this.lastSyncedId = null
          this.syncSidebar(this.activeHeadingId)
        }
      });
      this.sidebarObserver.observe(this.sidebar, { attributes: true, attributeFilter: ['class'] });
    }

    /* SPA 文档信息 */
    _isHome() {
      return !currentDoc();
    }

    /* 响应式断点切换 */
    async handleResize() {
      const w = innerWidth, crossed = (this.lastWidth < 997 && w >= 997) || (this.lastWidth >= 997 && w < 997);
      this.lastWidth = w;
      if (crossed) {
        this.reinit(currentDoc());
        this.syncSidebar(this.activeHeadingId);
      }
    }

    /* 点击处理 (SPA: 截获 ?doc= 导航) */
    handleClick(e) {
      const t = e.target.nodeType === 1 ? e.target : e.target.parentElement;
      const expand = t?.closest('a[data-expand-section]');
      if (expand) {
        e.preventDefault()
        e.stopPropagation()
        this.expandSection(expand.dataset.expandSection)
        return
      }
      const toggle = t?.closest('.sidebar-caret, .sidebar-category-label');
      if (toggle && !toggle.closest('a')) {
        e.preventDefault()
        e.stopPropagation()
        this.toggleItem(toggle.closest('.sidebar-item--collapsible'))
        return
      }
      const link = t?.closest('.sidebar-link'); if (!link) return;
      const href = link.getAttribute('href') || '';
      if (href.startsWith('#')) {
        e.preventDefault()
        this.scrollToHash(href.slice(1), true)
        return
      }
      const url = new URL(href, location.href);
      if (normPath(url.pathname).toLowerCase() === normPath(location.pathname).toLowerCase() && url.searchParams.has('doc')) {
        const docPath = url.searchParams.get('doc') || '', hash = url.hash.slice(1);
        if (normDoc(docPath).toLowerCase() === normDoc(currentDoc()).toLowerCase()) {
          e.preventDefault()
          hash ? this.scrollToHash(hash, true) : window.scrollTo({ top: 0, left: 0, behavior: 'smooth' })
        }
        else if (hash) {
          e.preventDefault()
        }
      }
    }

    /* 折叠/展开 */
    toggleItem(item) {
      if (!item) return;
      if (item.dataset.section && !item.dataset.loaded) this.loadSection(item);
      const collapsed = item.getAttribute('data-collapsed') !== 'false';
      item.setAttribute('data-collapsed', collapsed ? 'false' : 'true');
      const c = $('.sidebar-caret', item); if (c) c.textContent = collapsed ? '\u25be' : '\u25b8';
    }
    loadSection(item) {
      const col = (window.LIBRARY_CONFIG || []).find(c => c.id === item.dataset.section); if (!col) return;
      const html = (col.groups || []).map(g => this.renderGroup(g)).join(''); if (!html) return;
      const ul = document.createElement('ul'); ul.className = 'sidebar-menu sidebar-menu--nested'; ul.innerHTML = html;
      item.appendChild(ul); item.dataset.loaded = 'true';
    }
    expandSection(id) {
      const item = this.navTree.querySelector(`.sidebar-item[data-section="${cssEsc(id)}"]`); if (!item) return;
      if (item.getAttribute('data-collapsed') !== 'false') this.toggleItem(item);
      requestAnimationFrame(() => item.scrollIntoView({ block: 'center', behavior: 'smooth' }));
    }
    scrollToHash(hash, push) {
      if (!hash) return;
      const el = document.getElementById(hash) || document.querySelector(`[name="${cssEsc(hash)}"]`); if (!el) return;
      scrollToEl(el, 80, 'auto');
      const url = new URL(location.href); url.hash = hash;
      history[push ? 'pushState' : 'replaceState']({}, '', url);
      this.tracker?.measure?.();
      this.updateTrack(hash);
    }

    /* 卷册检测 (SPA: 带 docPath 参数) */
    detectVolume(docPath) {
      const pn = normPath(docPath), dn = normDoc(pn), dd = pn.replace(/\/[^/]+$/, '');
      const dl = dn.toLowerCase(), drl = dd.toLowerCase();
      const matchPath = p => {
        if (!p || /^https?:/i.test(p)) return null;
        const ip = normPath(p); if (!/\/index\.html?$/i.test(ip)) return null;
        const d = ip.replace(/\/index\.html?$/i, '').replace(/\/nav\.x?html?$/i, '');
        return (dl === normDoc(ip).toLowerCase() || dl === normDoc(d).toLowerCase() || drl === d.toLowerCase() || pn.toLowerCase().startsWith(d.toLowerCase() + '/')) ? d : null;
      };
      let best = null;
      const consider = (col, group, item, dir) => {
        if (dir && (!best || dir.length > best.dir.length)) best = { col, group, item, dir }
      };
      for (const col of window.LIBRARY_CONFIG || []) {
        consider(col, null, col, matchPath(col.path));
        for (const group of col.groups || []) {
          consider(col, group, group, matchPath(group.path))
          for (const item of group.items || []) consider(col, group, item, matchPath(item.path))
        }
      }
      return best;
    }

    /* SPA 文档路径辅助 */
    volumeDocPath(dp = currentDoc()) {
      const p = normPath(dp)
      return (this.currentVol && normDoc(p).toLowerCase() === normDoc(this.currentVol.dir).toLowerCase()) ? this.currentVol.dir + '/index.html' : p
    }
    /* SPA 文档信息 (unified with nav.js _volInfo, adapted for SPA) */
    _volInfo() {
      const c = normPath(currentDoc()), v = this.currentVol;
      const path = (v && c === v.dir) ? v.dir + '/index.html' : c;
      const file = path.split('/').pop().replace(/\.x?html?$/i, '') || 'index';
      const isVol = v ? (c === v.dir || c === v.dir + '/index.html') : false;
      return { path, dir: v?.dir || '', file, isVol };
    }

    /* 面包屑 parts 构建 */
    _breadcrumbParts(col, item, data, extra) {
      const parts = [col.path ? { text: col.label, href: makeHref(col.path), expand: col.id } : { text: col.label, expand: col.id }];
      if (item && item !== col) parts.push({ text: item.label || item.title || (data?.title) || 'Contents', href: makeHref(item.path || (this.currentVol?.dir + '/index.html')) });
      if (extra) parts.push(extra);
      parts.push({ id: 'page-breadcrumb-link', isPageBadge: window.__PAGE_BAR__?.hasPageAnchors });
      return parts;
    }

    /* 渲染入口 */
    async renderEpub(docPath) {
      const dir = this.currentVol?.dir || '', data = await this.fetchVolData(dir);
      if (!data) {
        const np = normPath(docPath), fallback = normDoc(np).toLowerCase() === normDoc(dir).toLowerCase() || normDoc(np).toLowerCase() === normDoc(dir + '/index.html').toLowerCase() || normDoc(np).toLowerCase() === normDoc(dir + '/nav.html').toLowerCase();
        this.mode = fallback ? 'libmap' : (innerWidth < 997 ? 'page-toc' : 'libmap');
        this.mode === 'page-toc' ? this.renderPageToc(docPath) : (this.navTree.innerHTML = this.buildLibmap());
        this.afterRender(docPath); return;
      }
      this.currentVol.data = data;
      const { col, item } = this.currentVol, tree = buildTree(data.headings || []), parts = this._breadcrumbParts(col, item, data);
      this.navTree.innerHTML = this.renderBreadcrumb(parts) + (tree.length ? this.renderTree(tree, 'epub-toc', docPath) : '') + '<div class="section-divider"><span>All works</span></div>' + this.buildLibmap();
      this.afterRender(docPath);
    }

    renderPageToc(docPath) {
      const headings = getHeadings($('#content'));
      if (headings.length <= 1) {
        this.mode = 'libmap'
        this.navTree.innerHTML = this.buildLibmap()
        this.afterRender(docPath)
        return
      }
      const col = this.currentVol?.col || findCollection(docPath), curFile = normPath(docPath).split('/').pop();
      const nodes = headings.map(h => ({ level: Number(h.tagName[1]) || 2, text: h.textContent.trim(), id: h.id, file: curFile }));
      const parts = [col?.path ? { text: col.label || 'Library', href: makeHref(col.path), expand: col.id } : { text: col?.label || 'Library', expand: col?.id }, { text: nodes[0]?.text || document.title }];
      this.navTree.innerHTML = this.renderBreadcrumb(parts) + this.renderTree(buildTree(nodes), 'page-toc', docPath) + '<div class="section-divider"><span>All works</span></div>' + this.buildLibmap();
      this.afterRender(docPath);
    }
    /* 数据 */
    async fetchVolData(dir) {
      const raw = await fetchVolData(dir, this.volCache); if (!raw) return null;
      if (!Array.isArray(raw) && raw.version === 1) return raw;
      if (!Array.isArray(raw)) return null;
      const headings = [];
      raw.forEach(f => (f.headings || []).forEach(h => headings.push({ level: h.level != null ? h.level : 2, text: h.text || '', id: h.id || null, file: h.filename || f.file || f.path || '' })));
      return { version: 1, title: this.currentVol?.item?.label || dir, files: raw, headings };
    }

    /* 渲染：面包屑 & 链接 */
    renderBreadcrumb(parts) {
      return '<div class="breadcrumb" aria-label="Breadcrumb">' + parts.map((p, i) => {
        const sep = (i > 0 || p.id === 'page-breadcrumb-link') ? '<span class="breadcrumb__sep">/</span>' : '';
        if (p.id === 'page-breadcrumb-link' && !p.isPageBadge) return '';
        if (p.id === 'page-breadcrumb-link') return sep + `<a href="#" id="${esc(p.id)}" style="display:none"></a>`;
        if (p.href) return sep + `<a href="${esc(p.href)}"${p.expand ? ` data-expand-section="${esc(p.expand)}"` : ''}>${esc(p.text)}</a>`;
        return sep + `<span>${esc(p.text || '')}</span>`;
      }).join('') + '</div>';
    }

    _renderLink({ href, path, text, badge = '', dataFile = '', dataId = '', extra = '' }) {
      const raw = String(href || path || '').trim(), ext = /^(?:https?:)?\/\//i.test(raw) || PathUtils.isSpecial(raw);
      const clean = !href && !ext ? normPath(raw) : '', final = ext || href ? raw : makeHref(raw);
      const attrs = [`href="${esc(final)}"`, !href && clean ? `data-path="${esc('/' + clean)}"` : '', dataFile ? `data-file="${esc(dataFile)}"` : '', dataId ? `data-id="${esc(dataId)}"` : '', extra, 'class="sidebar-link"', ext ? `target="_blank"` : ''].filter(Boolean).join(' ');
      return `<a ${attrs}>${esc(text || '')}${badge}</a>`;
    }

    /* 渲染：树 */
    renderTree(nodes, cls, docPath) {
      const effectiveDoc = docPath || currentDoc();
      return `<ul class="sidebar-menu ${esc(cls)}">${this.renderNodes(nodes, normDoc(this.volumeDocPath(effectiveDoc)), effectiveDoc)}</ul>`;
    }

    renderNodes(nodes, currentFull, docPath) {
      const volDir = this.currentVol?.dir || '', isPage = this.mode === 'page-toc';
      const curDoc = docPath || currentDoc();
      const curHref = makeHref(this.volumeDocPath(curDoc));
      return nodes.map(n => {
        const raw = n.file || '', full = raw && !isPage ? normPath((volDir + '/' + raw).replace(/\/+/g, '/')) : raw;
        const same = isPage || (full && normDoc(full).toLowerCase() === normDoc(currentFull).toLowerCase());
        const href = isPage ? (n.id ? `#${esc(n.id)}` : curHref) : same ? (n.id ? `#${esc(n.id)}` : makeHref(full || currentFull)) : makeHref(full, n.id || '');
        const children = n.children?.length ? `<ul class="sidebar-menu sidebar-menu--nested">${this.renderNodes(n.children, currentFull)}</ul>` : '';
        const caret = children ? '<button class="sidebar-caret" type="button" aria-label="Expand section" tabindex="0">\u25b8</button>' : '';
        const link = this._renderLink({ href, text: n.text, dataFile: raw, dataId: n.id || '' });
        return children ? `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-collapsed="true"><div class="sidebar-item-row">${link}${caret}</div>${children}</li>` : `<li class="sidebar-item">${link}</li>`;
      }).join('');
    }

    /* 渲染：libmap */
    buildLibmap() {
      if (!window.LIBRARY_CONFIG?.length) return '<div class="sidebar-menu" style="padding:20px">Navigation unavailable</div>';
      return '<ul class="sidebar-menu">' + (window.LIBRARY_CONFIG || []).map(c => this.renderSection(c)).join('') + '</ul>';
    }

    renderSection(col) {
      const label = esc(col.label || col.title || col.id || ''), badge = col.badge ? ` <span class="sidebar-badge">${esc(col.badge)}</span>` : '';
      const groups = col.groups || [];
      if (!groups.length && col.path) return `<li class="sidebar-item">${this._renderLink({ path: col.path, text: col.label || col.title || col.id || '', badge })}</li>`;
      if (groups.length) {
        const direct = groups.every(g => g.path && !(g.items || []).length);
        const nested = direct ? `<ul class="sidebar-menu sidebar-menu--nested">${groups.map(g => this.renderGroup(g)).join('')}</ul>` : '';
        const head = `<span class="sidebar-category-label">${label}${badge}</span>`;
        return `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-section="${esc(col.id)}" data-collapsed="true"${direct ? ' data-loaded="true"' : ''}><div class="sidebar-item-row">${head}<button class="sidebar-caret" type="button" aria-label="Expand section" tabindex="0">\u25b8</button></div>${nested}</li>`;
      }
      return `<li class="sidebar-item"><span class="sidebar-category-label">${label}${badge}</span></li>`;
    }

    renderGroup(group) {
      const label = esc(group.label || ''), items = group.items || [], raw = String(group.path || '').trim(), gp = normPath(group.path);
      if (!items.length) return raw ? `<li class="sidebar-item">${this._renderLink({ path: group.path, text: group.label || '' })}</li>` : `<li class="sidebar-item"><span class="sidebar-category-label">${label}</span></li>`;
      const head = raw ? this._renderLink({ path: group.path, text: group.label || '' }) : `<span class="sidebar-category-label">${label}</span>`;
      return `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-group-path="${esc(gp)}" data-collapsed="true"><div class="sidebar-item-row">${head}<button class="sidebar-caret" type="button" aria-label="Expand section" tabindex="0">\u25b8</button></div><ul class="sidebar-menu sidebar-menu--nested">${items.map(item => `<li class="sidebar-item">${this._renderLink({ path: item.path || '', text: item.label || item.title || '' })}</li>`).join('')}</ul></li>`;
    }

    /* TOC */
    pageHeadings() {
      if (this.mode === 'epub') {
        const { file: curFile } = this._volInfo();
        return (this.currentVol?.data?.headings || []).filter(h => normDoc((h.file || '').replace(/\.x?html?$/i, '')).toLowerCase() === normDoc(curFile).toLowerCase()).map(h => ({
          level: h.level || 2, text: h.text || '', id: h.id || null
        }));
      }
      return getHeadings($('#content')).map(h => ({ level: Number(h.tagName[1]) || 2, text: h.textContent.trim(), id: h.id }));
    }

    renderToc() {
      const nav = $('#toc-desktop-nav'); if (!nav) return;
      const headings = this.pageHeadings(); nav.innerHTML = headings.length ? this.renderTocNodes(buildTree(headings)) : '';
      this.activeTocLink = null;
    }

    renderTocNodes(nodes) {
      if (!nodes.length) return '';
      return '<ul class="theme-doc-toc-desktop-list">' + nodes.map(n => {
        const href = n.id ? `#${esc(n.id)}` : '#';
        return `<li class="theme-doc-toc-desktop-link theme-doc-toc-desktop-link--lvl${n.level}"><a href="${esc(href)}" data-id="${esc(n.id || '')}" class="theme-doc-toc-desktop-link__a">${esc(n.text)}</a>${this.renderTocNodes(n.children || [])}</li>`;
      }).join('') + '</ul>';
    }

    /* 追踪 */
    startTrack() {
      const content = $('#content');
      const start = () => {
        this.tracker = new HeadingTracker({ getHeadings: () => getHeadings(content), onChange: (id) => this.updateTrack(id) });
        return this.tracker.start();
      };
      if (!content || start()) return;
      this.waitObserver = new MutationObserver((_, o) => { if (start()) o.disconnect(); });
      this.waitObserver.observe(content, { subtree: true, attributes: true, attributeFilter: ['id'] });
    }

    updateTrack(id) {
      this.activeHeadingId = id;
      this.updateSidebar(id);
      this.updateToc(id);
      this.syncSidebar(id);
    }

    setActive(slot, link, cls) {
      this[slot]?.classList.remove(cls)
      this[slot] = null
      if (!link) return false
      link.classList.add(cls)
      this[slot] = link
      return true
    }
    sidebarLinks() {
      const tree = this.navTree.querySelector('.sidebar-menu'); if (!tree) return [];
      if (!this.linkCache || this.linkCache.tree !== tree) this.linkCache = { tree, links: $$('.sidebar-link', tree) };
      return this.linkCache.links;
    }
    _pickClosest(links, targetTop, getTop) {
      let best = null, bestTop = -Infinity;
      for (const link of links) {
        const t = getTop(link)
        if (t <= targetTop && t > bestTop) { bestTop = t; best = link; }
      }
      return best;
    }

    _elementTop(id) {
      if (!id) return 0;
      const el = document.getElementById(id);
      return el ? el.getBoundingClientRect().top + scrollY : -Infinity;
    }

    updateSidebar(id) {
      if (this.mode === 'libmap') return;
      const links = this.sidebarLinks();
      if (!links.length) return;
      const { file } = this._volInfo(), fileLinks = links.filter(l => normDoc((l.dataset.file || '').replace(/\.x?html?$/i, '')).toLowerCase() === normDoc(file).toLowerCase());
      let best = id ? fileLinks.find(l => l.dataset.id === id) : null;
      if (!best) {
        const y = scrollY + 80;
        best = this._pickClosest(fileLinks, y, l => this._elementTop(l.dataset.id));
      }
      if (!best) {
        best = fileLinks.find(l => !l.dataset.id) || fileLinks[0] || null;
      }
      if (best && this.setActive('activeSidebarLink', best, 'sidebar-link--active')) {
        expandTo(best, this.navTree.querySelector('.sidebar-menu'));
      }
    }
    updateToc(id) {
      const nav = $('#toc-desktop-nav');
      if (!nav) return;
      const links = $$('.theme-doc-toc-desktop-link__a', nav);
      let best = id ? links.find(a => a.dataset.id === id) : null;
      if (!best) {
        const y = scrollY + 80;
        best = this._pickClosest(links, y, a => this._elementTop(a.dataset.id));
      }
      if (!best) {
        best = links.find(a => !a.dataset.id) || links[0] || null;
      }
      if (best) {
        this.setActive('activeTocLink', best, 'theme-doc-toc-desktop-link__a--active');
      } else {
        this.setActive('activeTocLink', null, 'theme-doc-toc-desktop-link__a--active');
      }
    }

    syncSidebar(id) {
      if (innerWidth >= 997 || hasSel() || !id || id === this.lastSyncedId) return;
      if (!this.sidebar?.classList.contains('doc-sidebar--open')) return;
      const active = this.activeSidebarLink || $('.sidebar-link.sidebar-link--active', this.navTree); if (!active) return;
      this.lastSyncedId = id;
      requestAnimationFrame(() => active.scrollIntoView({ block: 'center', behavior: 'auto' }));
    }

    highlight() {
      if (this.mode === 'libmap') return;
      const tree = this.navTree.querySelector('.sidebar-menu'); if (!tree) return;
      const { file } = this._volInfo(), hash = location.hash.slice(1);
      let best = null, score = 0;
      $$('.sidebar-link', tree).forEach(a => {
        const f = (a.dataset.file || '').replace(/\.x?html?$/i, ''), id = a.dataset.id || ''; let s = 0;
        if (normDoc(f).toLowerCase() === normDoc(file).toLowerCase()) {
          s = 1;
          if (id && hash && id === hash) s = 3;          // exact hash match
          else if (!id && !hash) s = 2;                  // file-level heading, no hash
          else if (!id && hash) s = 0;                   // file-level heading but URL has hash -> skip
        }
        if (s > score) { score = s; best = a; }
      });
      // If no best yet (e.g. hash doesn't match any id), fall back to file-level heading
      if (!best && !hash) {
        best = $$('.sidebar-link', tree).find(a => normDoc((a.dataset.file || '').replace(/\.x?html?$/i, '')).toLowerCase() === normDoc(file).toLowerCase() && !a.dataset.id);
      }
      if (best) {
        best.classList.add('sidebar-link--active')
        this.activeSidebarLink = best
        expandTo(best, tree)
      }
    }

    initFade() {
      if (this.mode !== 'epub' && this.mode !== 'page-toc') return;
      const bc = $('.breadcrumb', this.navTree), menu = $('.sidebar-menu', this.navTree); if (!bc || !menu) return;
      this.fadeObserver = new IntersectionObserver(entries => { entries.forEach(en => bc.classList.toggle('breadcrumb--faded', en.boundingClientRect.bottom < en.rootBounds.top)); }, { root: this.navTree, threshold: 0 });
      this.fadeObserver.observe(menu);
    }

    /* SPA 特有：跨文档锚点待处理 */
    scrollToPendingAnchor() {
      const hash = sessionStorage.getItem('__reader_pending_anchor'), dp = sessionStorage.getItem('__reader_pending_doc');
      if (!hash) return;
      sessionStorage.removeItem('__reader_pending_anchor'); sessionStorage.removeItem('__reader_pending_doc');
      if (dp && !(normDoc(dp).toLowerCase() === normDoc(currentDoc()).toLowerCase())) return;
      const tryScroll = () => {
        const el = document.getElementById(hash)
        if (!el) return false
        scrollToEl(el)
        return true
      };
      if (!tryScroll()) requestAnimationFrame(() => { if (!tryScroll()) setTimeout(tryScroll, 150); });
    }
  }

  /* 导出 */
  const Core = {
    $, $$, esc, cssEsc, EventBag, PathUtils, PathResolver, HeadingTracker,
    normalizePath: normPath, normalizeDoc: normDoc, sameDocValue: PathUtils.sameDoc.bind(PathUtils),
    samePathValue: PathUtils.samePath.bind(PathUtils), startsWithPathValue: PathUtils.startsWithPath.bind(PathUtils),
    fetchWithLowerFallback, hasSelection: hasSel, resolveUrl: PathUtils.resolveUrl.bind(PathUtils),
    resolveDocHref, readerHref: makeHref,
    findCollection, scrollToEl, syncFill, onScrollFrame,
    getDomHeadings: getHeadings, getActiveHeadingId: (headings, t = 200) => {
      for (let i = (headings || []).length - 1; i >= 0; i--) if (headings[i].getBoundingClientRect().top <= t) return headings[i].id
      return headings[0]?.id || null
    },
    buildHeadingTree: buildTree, expandTo, fetchVolData
  };

  Object.assign(window, {
    ReaderCore: Core, $, $$, on: (t, e, h, o) => t && t.addEventListener(e, h, o || false),
    esc, syncFill: Core.syncFill, resolveUrl: Core.resolveUrl,
    fetchWithLowerFallback, findCollection, scrollToEl, getDomHeadings: getHeadings,
    getActiveHeadingId: Core.getActiveHeadingId, hasActiveTextSelection: hasSel,
    buildHeadingTree: buildTree, expandTo, fetchVolData, onScrollFrame
  });

  window.MenuManager = MenuManager;
})();
