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
  }
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
  /* 路径处理 (SPA 专用，统一收口到 PathUtils) */
  let libmapBase = '';
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
  const makeHref = (dp, h) => PathResolver.makeHref(dp, h);
  const resolveDocHref = (h, b) => PathResolver.resolve(b || '', h);
  const resolveLibraryPath = (col, group, item) => {
    if (!libmapBase) {
      const src = Array.from(document.scripts || []).map(s => s.src).find(v => v.split(/[?#]/)[0].endsWith('/libmap.js'));
      libmapBase = PathResolver.dir(src || location.href) || '/';
    }
    const raw = String(item?.path || '').trim();
    if (raw) return raw.startsWith('?') || PathUtils.isSpecial(raw) || /^(?:https?:)?\/\//i.test(raw) || raw.startsWith('/') ? raw : PathResolver.path(libmapBase, raw);
    [group, col].forEach(target => {
      if (target && 'basePath' in target) {
        const basePath = String(target.basePath || '').trim();
        target.basePath = !basePath || basePath.startsWith('?') || PathUtils.isSpecial(basePath) || /^(?:https?:)?\/\//i.test(basePath) || basePath.startsWith('/') ? basePath : PathResolver.path(libmapBase, basePath);
      }
    });
    const base = item?.basePath || group?.basePath || col?.basePath || '';
    const dir = String(item?.dir || '').trim();
    const homePage = item?.homePage || item?.homeName || 'index.html';
    const id = item?.id;
    const isIndex = !homePage || homePage === 'index.html';
    const relDir = item?.reldir != null
      ? String(item.reldir).trim()
      : (typeof id === 'number' || (typeof id === 'string' && /^\d+$/.test(id)) ? String(id) : '');
    const rel = relDir || id;
    const tail = isIndex ? String(rel ?? '').replace(/\/?$/, '/') : [rel, homePage].filter(v => v != null && String(v) !== '').join('/');
    if (base && relDir) {
      return PathResolver.path(String(base).replace(/\/?$/, '/'), tail || '.');
    }
    if (dir) {
      const resolvedDir = dir.startsWith('?') || PathUtils.isSpecial(dir) || /^(?:https?:)?\/\//i.test(dir) || dir.startsWith('/') ? dir : PathResolver.path(libmapBase, dir);
      return homePage === 'index.html' ? resolvedDir : PathResolver.path(String(resolvedDir || '/').replace(/\/?$/, '/'), homePage);
    }
    if (id == null || id === '') return '';
    if (!base) return raw;
    return PathResolver.path(String(base).replace(/\/?$/, '/'), tail || '.');
  };
  const resolveLibraryEntry = (col, group, item) => {
    const raw = resolveLibraryPath(col, group, item);
    if (!raw || /^https?:/i.test(raw) || PathUtils.isSpecial(raw)) return null;
    const rawPath = PathUtils.splitHash(raw).path.replace(/[?#].*$/, '');
    const path = normPath(rawPath.replace(/^\/+/, ''));
    const dir = /\/$/.test(rawPath) ? path : path.replace(/\/[^/]+$/, '');
    return dir ? { path, dir } : null;
  };
  /* 卷册检测 (SPA: 带 docPath 参数) */
  class VolumeIndex {
    constructor() {
      this.source = null;
      this.entries = [];
      this.byDir = new Map();
    }

    ensure() {
      const source = window.LIBRARY_CONFIG || [];
      if (this.source === source) return this.entries;
      const entries = [];
      const byDir = new Map();
      const rank = entry => entry.kind === 'collection' ? 3 : entry.kind === 'group' ? 2 : 1;
      const add = (col, group, item, kind) => {
        const resolved = resolveLibraryEntry(col, group, item);
        if (!resolved) return;
        if (!(col.basePath && resolved.dir.startsWith(normPath(col.basePath)))) return;
        let entry = { col, group, item, path: resolved.path, dir: resolved.dir, colPath: col ? resolveLibraryPath(col, null, col) : '', kind };
        if (entry.col && !entry.col.basePath) { 
          if (entry.col === entry.item) entry.item = null;
          entry.col = null;
        };
        entries.push(entry);
        const key = resolved.dir.replace(/^\/+/, '').toLowerCase();
        const previous = byDir.get(key);
        if (!previous || rank(entry) > rank(previous)) byDir.set(key, entry);
      };
      for (const col of source) {
        add(col, null, col, 'collection');
        for (const group of col.groups || []) {
          add(col, group, group, 'group');
          for (const item of group.items || []) add(col, group, item, 'item');
        }
      }
      this.source = source;
      this.entries = entries;
      this.byDir = byDir;
      return this.entries;
    }

    detectVolume(docPath, findcol = false) {
      let dir = normPath(String(docPath || '').replace(/[?#].*$/, '').replace(/^\/+/, ''));
      dir = /\.[^/]+$/.test(dir.split('/').pop() || '') ? dir.replace(/\/[^/]+$/, '') : dir;
      if (!dir) return null;
      this.ensure();
      let best = null;
      for (;;) {
        const entry = this.byDir.get(dir.replace(/^\/+/, '').toLowerCase());
        if (entry) {
          if (findcol && entry.col && entry.col.basePath) return entry.col;
          best = entry;
          break;
        }
        const next = dir.replace(/\/[^/]+$/, '');
        if (!next || next === dir) break;
        dir = next;
      }
      return best;
    }
  }
  const volumeIndex = new VolumeIndex();
  const detectVolume = docPath => volumeIndex.detectVolume(docPath, false);
  const findCollection = path => volumeIndex.detectVolume(path, true);

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

    makeHref(path, hash = '') {
      const p = this.split(this.doc(path));
      const h = hash || p.hash;
      let spaPath = location.pathname + '?doc=' + this.path('', p.path) + (h ? '#' + h : '');
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
        href: this.makeHref(p),
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
  async function fetchReaderResource(path, opts) {
    const rawPath = String(path || '').trim();
    const external = PathResolver.special.test(rawPath) || (/^(?:https?:)?\/\//i.test(rawPath) && !rawPath.startsWith(location.origin));
    const finalPath = external ? PathResolver.split(rawPath).path : (PathResolver.split(PathResolver.path('', PathResolver.doc(rawPath))).path || '/');
    const res = await fetch(finalPath, opts);
    return { res, path: finalPath, url: res.url || finalPath };
  }

  /* 卷册数据获取：全局唯一请求与缓存 */
  async function loadVolData(clean) {
    try {
      const r = await fetch(new URL('/' + clean + '/index.json', location.origin).href);
      if (r.ok) return await r.json();
    } catch { }
    try {
      const r = await fetch(new URL('/' + clean + '/index.js', location.origin).href);
      if (!r.ok || /text\/html/i.test(r.headers.get('content-type') || '')) return null;
      const js = await r.text();
      if (!/\bexport\s+default\b/.test(js)) return null;
      const url = URL.createObjectURL(new Blob([js], { type: 'text/javascript' }));
      try { return (await import(url))?.default || null; }
      finally { URL.revokeObjectURL(url); }
    } catch { return null; }
  }

  function normalizeVolData(raw, dir, title) {
    if (!raw) return null;
    if (!Array.isArray(raw) && raw.version === 1) return raw;
    if (!Array.isArray(raw)) return null;
    const headings = [];
    raw.forEach(f => (f.headings || []).forEach(h => headings.push({ level: h.level ?? 2, text: h.text || '', id: h.id || null, file: h.filename || f.file || f.path || '' })));
    return { version: 1, title: title || dir, files: raw, headings };
  }

  const VolDataStore = {
    cache: new Map(),
    key(dir) { return normPath(dir); },

    async fetchVolData(dir) {
      const clean = this.key(dir);
      if (!clean) return null;
      let entry = this.cache.get(clean);
      if (!entry) {
        entry = { raw: null, volume: null, promise: loadVolData(clean).then(data => (entry.raw = data || null)) };
        this.cache.set(clean, entry);
      }
      return entry.promise;
    },

    async fetchVolume(dir, title) {
      const clean = this.key(dir);
      if (!clean) return null;
      const raw = await this.fetchVolData(clean), entry = this.cache.get(clean);
      return entry.volume || (entry.volume = normalizeVolData(raw, clean, title));
    },

    clear() { this.cache.clear(); }
  };

  /* 标题追踪 (unified) */
  class HeadingTracker {
    constructor({ content, header, getHeadings: gh, onChange }) {
      this.content = content; this.header = header;
      this.getHeadings = gh; this.onChange = onChange;
      this.headings = []; this.activeId = null; this.frame = 0;
      this.bag = new EventBag(); this.offScroll = null;
    }
    start() {
      this.stop(); this.headings = this.getHeadings();
      if (!this.headings.length) return false;
      const qm = () => {
        if (!this.frame) this.frame = requestAnimationFrame(() => { this.frame = 0; this.headings = this.getHeadings(); this.track(true); })
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
      this.headings = []; this.activeId = null;
    }
    visibleRange() {
      const contentTop = this.content ? this.content.getBoundingClientRect().top : 0;
      const contentBottom = this.content ? this.content.getBoundingClientRect().bottom : innerHeight;
      const headerBottom = this.header ? Math.max(0, this.header.getBoundingClientRect().bottom) : 0;
      const visibleTop = Math.max(0, headerBottom, contentTop);
      const visibleBottom = Math.min(innerHeight, contentBottom);
      return [visibleTop, Math.max(visibleTop, visibleBottom)];
    }
    track(force) {
      if (hasSel()) return;
      const id = this.pick();
      if (force || id !== this.activeId) {
        this.activeId = id
        this.onChange(id)
      }
    }
    pick() {
      if (!this.headings.length) return null;
      const [visibleTop, visibleBottom] = this.visibleRange();
      let visible = -1, fallback = 0;
      for (let i = 0; i < this.headings.length; i++) {
        const start = this.headings[i].getBoundingClientRect().top;
        if (start < visibleTop) fallback = i;
        else if (start <= visibleBottom) {
          visible = i;
          break;
        }
        else break;
      }
      const best = visible >= 0 ? visible : fallback;
      return this.headings[best]?.id || null;
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
      this.fadeObserver = null;
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
      this.currentVol = docPath ? detectVolume(docPath) : null;
      if (!docPath) {
        this.mode = 'libmap'
        this.navTree.innerHTML = this.buildLibmap()
      }
      else if (this.currentVol) {
        this.mode = 'epub';
        this.renderEpub(docPath);
      }
      else if (innerWidth < 997 && getHeadings($('#content')).length > 1 && !(/\/(?:index\.x?html?|nav\.x?html?)?$/i.test(docPath)) && currentDoc()) {
        this.mode = 'page-toc';
        this.renderPageToc(docPath);
      }
      else {
        this.mode = 'libmap';
        this.navTree.innerHTML = this.buildLibmap();
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
      this.startTrack(); 
      this.scrollToPendingAnchor(); 
      this.initFade();
      if (window.__PAGE_BAR__?.currentPage != null) window.__PAGE_BAR__.updateBadge(window.__PAGE_BAR__.currentPage);
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

    /* 响应式断点切换 */
    async handleResize() {
      const w = innerWidth, crossed = (this.lastWidth < 997 && w >= 997) || (this.lastWidth >= 997 && w < 997);
      this.lastWidth = w;
      if (crossed) {
        this.reinit(currentDoc());
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
      const html = (col.groups || []).map(g => this.renderGroup(g, col)).join(''); if (!html) return;
      const ul = document.createElement('ul'); ul.className = 'sidebar-menu sidebar-menu--nested'; ul.innerHTML = html;
      item.appendChild(ul); item.dataset.loaded = 'true';
    }
    expandSection(id) {
      const item = this.navTree.querySelector(`.sidebar-item[data-section="${cssEsc(id)}"]`); if (!item) return;
      if (item.getAttribute('data-collapsed') !== 'false') this.toggleItem(item);
      const scroller = this.navTree.closest('.sidebar-nav') || this.navTree;
      requestAnimationFrame(() => this.scrollInside(scroller, item, 'smooth'));
    }

    scrollInside(container, el, behavior = 'auto') {
      if (!container || !el) return;
      const cr = container.getBoundingClientRect(), er = el.getBoundingClientRect();
      const max = Math.max(0, container.scrollHeight - container.clientHeight);
      const top = container.scrollTop + er.top - cr.top - (container.clientHeight - el.offsetHeight) / 2;
      container.scrollTo({ top: Math.max(0, Math.min(max, top)), behavior });
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
      const isVol = v ? (c.toLowerCase() === v.dir.toLowerCase() || c.toLowerCase() === v.dir.toLowerCase() + '/index.html') : false;
      return { path, dir: v?.dir || '', file, isVol };
    }

    /* 渲染入口 */
    async renderEpub(docPath) {
      const dir = this.currentVol?.dir || '', data = await VolDataStore.fetchVolume(dir, this.currentVol?.item?.label || dir);
      if (!data) {
        const np = normPath(docPath), fallback = normDoc(np).toLowerCase() === normDoc(dir).toLowerCase() || normDoc(np).toLowerCase() === normDoc(dir + '/index.html').toLowerCase() || normDoc(np).toLowerCase() === normDoc(dir + '/nav.html').toLowerCase();
        this.mode = fallback ? 'libmap' : (innerWidth < 997 ? 'page-toc' : 'libmap');
        this.mode === 'page-toc' ? this.renderPageToc(docPath) : (this.navTree.innerHTML = this.buildLibmap());
        this.afterRender(docPath); return;
      }
      this.currentVol.data = data;
      const { col, item, colPath, path } = this.currentVol, tree = buildTree(data.headings || []);
      let parts = [colPath ? { text: col.label, href: makeHref(colPath), expand: col.id } : { text: col.label, expand: col.id }];
      if (item && item !== col) parts.push({ text: item.label || (data?.title) || 'Contents', href: makeHref(path + '/')});
      parts.push({ id: 'page-breadcrumb-link', isPageBadge: window.__PAGE_BAR__?.hasPageAnchors });
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
      const col = this.currentVol?.col || null;
      const curFile = normPath(docPath).split('/').pop();
      const nodes = headings.map(h => ({ level: Number(h.tagName[1]) || 2, text: h.textContent.trim(), id: h.id, file: curFile }));
      const colPath = this.currentVol?.colPath || '';
      const parts = [colPath ? { text: col?.label || 'Library', href: makeHref(colPath), expand: col?.id } : { text: col?.label || 'Library', href: colPath ? sitePath(colPath) : '#', expand: col?.id }, { text: nodes[0]?.text || document.title }];
      this.navTree.innerHTML = this.renderBreadcrumb(parts) + this.renderTree(buildTree(nodes), 'page-toc', docPath) + '<div class="section-divider"><span>All works</span></div>' + this.buildLibmap();
      this.afterRender(docPath);
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
      const colPath = resolveLibraryPath(col, null, col);
      if (!groups.length && colPath) return `<li class="sidebar-item">${this._renderLink({ path: colPath, text: col.label || col.title || col.id || '', badge })}</li>`;
      if (groups.length) {
        const direct = groups.every(g => g.path && !(g.items || []).length);
        const nested = direct ? `<ul class="sidebar-menu sidebar-menu--nested">${groups.map(g => this.renderGroup(g, col)).join('')}</ul>` : '';
        const head = `<span class="sidebar-category-label">${label}${badge}</span>`;
        return `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-section="${esc(col.id)}" data-collapsed="true"${direct ? ' data-loaded="true"' : ''}><div class="sidebar-item-row">${head}<button class="sidebar-caret" type="button" aria-label="Expand section" tabindex="0">\u25b8</button></div>${nested}</li>`;
      }
      return `<li class="sidebar-item"><span class="sidebar-category-label">${label}${badge}</span></li>`;
    }

    renderGroup(group, col = null) {
      const label = esc(group.label || ''), items = group.items || [], groupPath = resolveLibraryPath(null, null, group), gp = normPath(groupPath);
      if (!items.length) return groupPath ? `<li class="sidebar-item">${this._renderLink({ path: groupPath, text: group.label || '' })}</li>` : `<li class="sidebar-item"><span class="sidebar-category-label">${label}</span></li>`;
      const head = groupPath ? this._renderLink({ path: groupPath, text: group.label || '' }) : `<span class="sidebar-category-label">${label}</span>`;
      return `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-group-path="${esc(gp)}" data-collapsed="true"><div class="sidebar-item-row">${head}<button class="sidebar-caret" type="button" aria-label="Expand section" tabindex="0">\u25b8</button></div><ul class="sidebar-menu sidebar-menu--nested">${items.map(item => `<li class="sidebar-item">${this._renderLink({ path: resolveLibraryPath(col, group, item), text: item.label })}</li>`).join('')}</ul></li>`;
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
        this.tracker = new HeadingTracker({ content, header: $('#navbar') || $('header'), getHeadings: () => this.trackHeadings(content), onChange: (id) => this.updateTrack(id) });
        return this.tracker.start();
      };
      if (!content || start()) return;
      this.waitObserver = new MutationObserver((_, o) => { if (start()) o.disconnect(); });
      this.waitObserver.observe(content, { subtree: true, attributes: true, attributeFilter: ['id'] });
    }

    trackHeadings(content) {
      if (!content) return [];
      if (this.mode !== 'epub') return getHeadings(content);
      return this.pageHeadings().map(h => {
        if (!h.id) return { id: null, getBoundingClientRect: () => content.getBoundingClientRect() };
        const el = document.getElementById(h.id);
        return el && content.contains(el) ? el : null;
      }).filter(Boolean);
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
    updateSidebar(id) {
      if (this.mode === 'libmap') return;
      const links = this.sidebarLinks();
      if (!links.length) return;
      const { file } = this._volInfo(), fileLinks = links.filter(l => normDoc((l.dataset.file || '').replace(/\.x?html?$/i, '')).toLowerCase() === normDoc(file).toLowerCase());
      let best = id ? fileLinks.find(l => l.dataset.id === id) : null;
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
        best = links.find(a => !a.dataset.id) || links[0] || null;
      }
      if (best) {
        this.setActive('activeTocLink', best, 'theme-doc-toc-desktop-link__a--active');
      } else {
        this.setActive('activeTocLink', null, 'theme-doc-toc-desktop-link__a--active');
      }
    }

    syncSidebar(id) {
      if (innerWidth >= 997 || hasSel()) return;
      if (!this.sidebar?.classList.contains('doc-sidebar--open')) return;
      const active = this.activeSidebarLink || $('.sidebar-link.sidebar-link--active', this.navTree); if (!active) return;
      const links = this.sidebarLinks();
      const key = id || `${active.dataset.file || ''}#${active.dataset.id || ''}@${links.indexOf(active)}`;
      if (key === this.lastSyncedId) return;
      this.lastSyncedId = key;
      const scroller = this.navTree.closest('.sidebar-nav') || this.navTree;
      requestAnimationFrame(() => this.scrollInside(scroller, active));
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
    fetchReaderResource, hasSelection: hasSel, resolveUrl: PathUtils.resolveUrl.bind(PathUtils),
    resolveDocHref, readerHref: makeHref, findCollection, resolveLibraryPath, resolveLibraryEntry,
    detectVolume, scrollToEl, syncFill, onScrollFrame,
    getDomHeadings: getHeadings, getActiveHeadingId: (headings, t = 200) => {
      for (let i = (headings || []).length - 1; i >= 0; i--) if (headings[i].getBoundingClientRect().top <= t) return headings[i].id
      return headings[0]?.id || null
    },
    buildHeadingTree: buildTree, expandTo, VolDataStore
  };

  Object.assign(window, {
    ReaderCore: Core, $, $$, on: (t, e, h, o) => t && t.addEventListener(e, h, o || false),
    esc, syncFill: Core.syncFill, resolveUrl: Core.resolveUrl,
    fetchReaderResource, findCollection, detectVolume: Core.detectVolume, scrollToEl, getDomHeadings: getHeadings,
    getActiveHeadingId: Core.getActiveHeadingId, hasActiveTextSelection: hasSel,
    buildHeadingTree: buildTree, expandTo, VolDataStore, onScrollFrame
  });

  window.MenuManager = MenuManager;
})();
