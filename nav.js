(function () {
  'use strict';

  /* nav.js — SSG sidebar navigation
   *  Works with: reader.js
   *  Link scheme: /site/<path>.html#<hash>
   *
   *  Naming unified with reader-nav.js (SPA counterpart).
   *  Identical logic blocks are character-for-character identical.*/

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

  /* 路径工具 (SSG 版：轻量) */
  const normPath = v => String(v || '').replace(/^https?:\/\/[^/]+/i, '').replace(/[?#].*$/, '').replace(/^\/+/, '').replace(/\/+$/, '');
  const normDoc = v => normPath(v).replace(/\.x?html?$/i, '');
  const resolveUrl = h => { try { return new URL(h, location.href).href; } catch { return h; } };

  /* SSG 链接生成 */
  const siteRoot = () => (document.body.dataset.site || '').replace(/\/$/, '');
  const PathResolver = {
    special: /^(?:mailto|tel|javascript|data|blob):/i,
    split(v) {
      const raw = String(v || '').trim();
      const h = raw.indexOf('#');
      return h >= 0
        ? { path: raw.slice(0, h), hash: raw.slice(h + 1) }
        : { path: raw, hash: '' };
    },
    stripRoot(v) {
      const root = siteRoot();
      const raw = String(v || '').replace(/^https?:\/\/[^/]+/i, '').replace(/[?#].*$/, '');
      const path = root && raw.startsWith(root + '/') ? raw.slice(root.length) : raw;
      return path.replace(/^\/+/, '');
    },
    dir(base) {
      const p = this.stripRoot(base == null ? location.pathname : base);
      return !p || p.endsWith('/') ? p : p.slice(0, p.lastIndexOf('/') + 1);
    },
    logical(base, href) {
      const parts = this.split(href);
      const raw = parts.path.replace(/^https?:\/\/[^/]+/i, '');
      if (!raw || raw.startsWith('?')) return raw + (parts.hash ? '#' + parts.hash : '');
      if (raw.startsWith('/')) return this.stripRoot(raw) + (parts.hash ? '#' + parts.hash : '');
      else {
        let dir = this.dir(base), rel = raw.replace(/^\.\//, '');
        for (; rel.startsWith('../'); rel = rel.slice(3)) {
          dir = dir.replace(/\/?[^/]+\/?$/, '');
        }
        return (dir.replace(/\/?$/, '/') + rel).replace(/\/+/g, '/').replace(/^\/+/, '') + (parts.hash ? '#' + parts.hash : '');
      }
    },
    path(base, href) {
      const raw = String(href || '').trim();
      if (raw.startsWith('#')) return raw;
      if (!raw || this.special.test(raw) || /^(?:https?:)?\/\//i.test(raw)) return raw || '#';
      const logical = this.logical(base, raw);
      const root = siteRoot();
      return (root ? root + '/' : '/') + logical.replace(/^\/+/, '');
    },
    resolve(base, href) {
      const raw = String(href || '').trim();
      if (!raw) return null;
      if (raw.startsWith('#')) return { type: 'anchor', href: raw, hash: raw.slice(1) };
      if (this.special.test(raw) || /^(?:https?:)?\/\//i.test(raw)) return { type: 'external', href: raw };
      const hrefOut = this.path(base, raw);
      const parts = this.split(hrefOut);
      return { type: 'doc', href: hrefOut, path: parts.path, hash: parts.hash };
    }
  };
  const sitePath = p => PathResolver.path('', p);

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

  /* ReaderCore (unified 导出) */
  const ReaderCore = window.ReaderCore || {
    $, $$, esc, cssEsc, EventBag, HeadingTracker, PathResolver,
    normalizePath: normPath, normalizeDoc: normDoc, resolveUrl, hasSelection: hasSel,
    scrollToEl, syncFill, onScrollFrame, getDomHeadings: getHeadings, buildHeadingTree: buildTree, expandTo
  };
  Object.assign(window, { ReaderCore, $, $$, esc, syncFill, onScrollFrame });

  /* MenuManager — SSG 版 */
  class MenuManager {
    constructor() {
      this.sidebar = null; this.backdrop = null; this.navTree = null; this.mode = 'libmap';
      this.currentVol = null; this.activeHeadingId = null;
      this.activeSidebarLink = null; this.activeTocLink = null;
      this.lastSyncedId = null; this.linkCache = null;
      this.volCache = new Map(); this.tracker = null;
      this.waitObserver = null; this.fadeObserver = null;
      this.lastWidth = innerWidth;
    }

    /*  生命周期 */
    async init() {
      this.sidebar = $('#lsidebar'); this.backdrop = $('#sidebar-backdrop'); this.navTree = $('#nav-tree');
      if (!this.sidebar || !this.navTree) return;
      this.bindEvents();
      if (!window.LIBRARY_CONFIG?.length) await this.loadLibmap();
      await this.buildMenu();
      this.initSourceToc();
    }

    async buildMenu() {
      this.cleanup(); this.currentVol = this.detectVolume();
      if (this.currentVol) {
        this.mode = 'epub'
        await this.renderEpub()
      }
      else if (innerWidth < 997 && getHeadings($('#content')).length > 1 && !(() => { const p = location.pathname.split('/').pop().toLowerCase(); return !p || p === 'index.html' || p === 'nav.html'; })()) {
        this.mode = 'page-toc'
        this.renderPageToc()
      }
      else {
        this.mode = 'libmap'
        this.navTree.innerHTML = this.buildLibmap(); 
      }
      this.afterBuild();
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

    afterBuild() {
      this.highlight()
      this.renderToc()
      this.startTrack()
      this.initFade()
    }

    /*  事件绑定 */
    bindEvents() {
      $('#sidebar-toggle')?.addEventListener('click', () => { this.sidebar?.classList.contains('doc-sidebar--open') ? this.close() : this.open(); });
      this.backdrop?.addEventListener('click', () => this.close());
      $('#sidebar-close-btn')?.addEventListener('click', () => this.close());
      window.addEventListener('resize', () => this.handleResize(), { passive: true });
      this.navTree.addEventListener('click', e => this.handleClick(e));
      this.navTree.addEventListener('keydown', e => {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        const t = e.target.closest('.sidebar-caret, .sidebar-category-label');
        if (!t || t.closest('a')) return; e.preventDefault(); this.toggleItem(t.closest('.sidebar-item--collapsible'));
      });
    }

    async handleResize() {
      const w = innerWidth, crossed = (this.lastWidth < 997 && w >= 997) || (this.lastWidth >= 997 && w < 997);
      this.lastWidth = w;
      if (crossed) {
        await this.buildMenu();
        this.syncSidebar(this.activeHeadingId);
      }
    }

    /*  SSG 文档信息 */
    _volInfo() {
      const c = normPath(PathResolver.stripRoot(location.pathname)), v = this.currentVol;
      const path = (v && c === v.dir) ? v.dir + '/index.html' : c;
      const file = path.split('/').pop().replace(/\.x?html?$/i, '') || 'index';
      const isVol = v ? (c === v.dir || c === v.dir + '/index.html') : false;
      return { path, dir: v?.dir || '', file, isVol };
    }

    /*  点击处理 (SSG: 直接跳转) */
    handleClick(e) {
      const t = e.target.nodeType === 1 ? e.target : e.target.parentElement;
      const expand = t?.closest('a[data-expand-section]');
      if (expand) {
        e.preventDefault()
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
        this.scrollToHash(href.slice(1))
        return
      }
      try {
        const url = new URL(href, location.href);
        if (url.pathname === location.pathname && url.hash) {
          e.preventDefault()
          this.scrollToHash(url.hash.slice(1))
        }
        else if (normDoc(url.pathname).toLowerCase() === normDoc(location.pathname).toLowerCase() && url.search === location.search && !url.hash) {
          e.preventDefault()
          this.scrollToTop(url)
        }
      } catch { }
    }

    /*  折叠/展开 (unified) */
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

    /*  滚动 */
    scrollToHash(hash) {
      const el = document.getElementById(hash) || document.querySelector(`[name="${cssEsc(hash)}"]`); if (!el) return;
      scrollToEl(el, 80, 'auto');
      this.tracker?.measure?.();
      this.updateTrack(hash);
      history.replaceState({}, '', '#' + hash);
    }
    scrollToTop(url = location) {
      window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
      this.tracker?.measure?.();
      history.replaceState({}, '', location.pathname + location.search);
    }

    /*  卷册检测 (unified 算法) */
    detectVolume() {
      const cur = normPath(PathResolver.stripRoot(location.pathname)), curL = cur.toLowerCase();
      const matchPath = p => {
        if (!p || /^https?:/i.test(p)) return null;
        const ip = normPath(p); if (!/\/index\.html?$/i.test(ip)) return null;
        const d = ip.replace(/\/index\.html$/i, ''), dl = d.toLowerCase();
        return (curL === ip.toLowerCase() || curL === dl || curL.startsWith(dl + '/')) ? d : null;
      };
      let best = null;
      const consider = (col, group, item, dir) => {
        if (dir && (!best || dir.length > best.dir.length)) best = { col, group, item, dir }
      };
      for (const col of window.LIBRARY_CONFIG || []) {
        consider(col, null, col, matchPath(col.path));
        for (const g of col.groups || []) {
          consider(col, g, g, matchPath(g.path))
          for (const it of g.items || []) consider(col, g, it, matchPath(it.path))
        }
      }
      return best;
    }

    /*  数据加载 (SSG: import only) */
    async fetchVolData(dir) {
      const d = normPath(dir); if (this.volCache.has(d)) return this.volCache.get(d);
      const dl = d.toLowerCase(); if (dl !== d && this.volCache.has(dl)) return this.volCache.get(dl);
      const raw = await this._importVolData(d), data = this._normalizeVolData(raw, d);
      if (data) {
        this.volCache.set(d, data)
        if (dl !== d) this.volCache.set(dl, data)
      }
      return data;
    }
    async _importVolData(d) {
      const urls = [], meta = window.__PAGE_META__ || {};
      if (meta.indexJsPath) urls.push(PathResolver.path(location.pathname, meta.indexJsPath));
      const dirs = [d], dl = d.toLowerCase(); if (dl !== d) dirs.push(dl);
      dirs.forEach(dir => urls.push(new URL(sitePath(dir + '/index.js'), location.href).href));
      for (const url of [...new Set(urls)]) { try { const m = await import(url); if (m?.default) return m.default; } catch { } }
      return null;
    }
    _normalizeVolData(raw, dir) {
      if (!raw) return null;
      if (!Array.isArray(raw) && raw.version === 1) return raw;
      if (!Array.isArray(raw)) return null;
      const headings = [];
      raw.forEach(f => (f.headings || []).forEach(h => headings.push({ level: h.level || 2, text: h.text || '', id: h.id || null, file: h.filename || f.file || f.path || '' })));
      return { version: 1, title: this.currentVol?.item?.label || dir, files: raw, headings };
    }

    /*  面包屑 parts 构建 */
    _breadcrumbParts(col, item, data) {
      const parts = [{ text: col.label, href: sitePath(col.path), expand: col.id }];
      if (item && item !== col) parts.push({ text: item.label || item.title || data?.title || 'Contents', href: sitePath(item.path || (this.currentVol.dir + '/index.html')) });
      return parts;
    }

    /*  渲染入口 */
    async renderEpub() {
      const data = await this.fetchVolData(this.currentVol.dir);
      if (!data) {
        if (this._volInfo().isVol) {
          this.mode = 'libmap'
          this.navTree.innerHTML = this.buildLibmap(); 
          return
        }
        this.mode = innerWidth < 997 ? 'page-toc' : 'libmap';
        this.mode === 'page-toc' ? this.renderPageToc() : this.navTree.innerHTML = this.buildLibmap(); return;
      }
      this.currentVol.data = data;
      const { col, item } = this.currentVol, tree = buildTree(data.headings || []), parts = this._breadcrumbParts(col, item, data);
      this.navTree.innerHTML = this.renderBreadcrumb(parts) + this.renderTree(tree, 'epub-toc') + '<div class="section-divider"><span>All works</span></div>' + this.buildLibmap();
    }

    renderPageToc() {
      const headings = getHeadings($('#content'));
      if (headings.length <= 1) {
        this.mode = 'libmap'
        this.navTree.innerHTML = this.buildLibmap(); 
        return
      }
      const col = this._findCollection(), nodes = headings.map(h => ({ level: Number(h.tagName[1]) || 2, text: h.textContent.trim(), id: h.id, file: location.pathname.split('/').pop() }));
      const parts = [{ text: col?.label || 'Library', href: col?.path ? sitePath(col.path) : '#', expand: col?.id }, { text: nodes[0]?.text || document.title }];
      this.navTree.innerHTML = this.renderBreadcrumb(parts) + this.renderTree(buildTree(nodes), 'page-toc') + '<div class="section-divider"><span>All works</span></div>' + this.buildLibmap();
    }

    /*  渲染：面包屑 & 链接 */
    renderBreadcrumb(parts) {
      return '<div class="breadcrumb" aria-label="Breadcrumb">' + parts.map((p, i) => {
        const sep = i ? '<span class="breadcrumb__sep">/</span>' : '';
        if (p.href) return sep + `<a href="${esc(p.href)}"${p.expand ? ` data-expand-section="${esc(p.expand)}"` : ''}>${esc(p.text)}</a>`;
        return sep + `<span>${esc(p.text || '')}</span>`;
      }).join('') + '</div>';
    }
    _renderLink(path, label, badge = '') {
      const ext = /^https?:/i.test(path || ''), p = normPath(path);
      const href = ext ? esc(path) : sitePath(p);
      const attrs = ext ? ' target="_blank" rel="noopener"' : ` data-path="${esc('/' + p)}"`;
      return `<a href="${href}" class="sidebar-link"${attrs}>${esc(label || '')}${badge}</a>`;
    }

    /*  渲染：树 (unified 结构) */
    renderTree(nodes, cls) {
      return `<ul class="sidebar-menu ${esc(cls)}">${this.renderNodes(nodes)}</ul>`;
    }
    renderNodes(nodes) {
      const { file: curFile } = this._volInfo(), curPath = sitePath(this._volInfo().path);
      return nodes.map(n => {
        const raw = n.file || '', full = raw && this.mode !== 'page-toc' ? normPath((this.currentVol.dir + '/' + raw).replace(/\/+/g, '/')) : raw;
        const file = raw.replace(/\.x?html?$/i, '');
        const same = this.mode === 'page-toc' || !raw || normDoc(file).toLowerCase() === normDoc(curFile).toLowerCase();
        const href = this.mode === 'page-toc'
          ? (n.id ? '#' + esc(n.id) : curPath)
          : same ? (n.id ? '#' + esc(n.id) : (full || raw ? sitePath(full || raw) : curPath))
            : (n.id ? sitePath(full) + '#' + esc(n.id) : sitePath(full));
        const children = n.children?.length ? `<ul class="sidebar-menu sidebar-menu--nested">${this.renderNodes(n.children)}</ul>` : '';
        const caret = children ? '<button class="sidebar-caret" tabindex="0" aria-label="Expand">\u25b8</button>' : '';
        const link = `<a href="${href}" data-file="${esc(raw)}" data-id="${esc(n.id || '')}" class="sidebar-link">${esc(n.text)}</a>`;
        return children ? `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-collapsed="true"><div class="sidebar-item-row">${link}${caret}</div>${children}</li>` : `<li class="sidebar-item">${link}</li>`;
      }).join('');
    }

    /*  渲染：libmap (unified 结构) */
    buildLibmap() {
      if (!window.LIBRARY_CONFIG?.length) return '<div class="sidebar-menu" style="padding:20px">Navigation unavailable</div>';
      return '<ul class="sidebar-menu">' + window.LIBRARY_CONFIG.map(c => this.renderSection(c)).join('') + '</ul>';
    }
    renderSection(col) {
      const label = esc(col.label || col.title || col.id || ''), badge = col.badge ? ` <span class="sidebar-badge">${esc(col.badge)}</span>` : '';
      const groups = col.groups || [];
      if (!groups.length && col.path) return `<li class="sidebar-item">${this._renderLink(col.path, col.label || col.title || col.id || '', badge)}</li>`;
      if (groups.length) return `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-section="${esc(col.id)}" data-collapsed="true"><div class="sidebar-item-row"><span class="sidebar-category-label">${label}${badge}</span><button class="sidebar-caret" tabindex="0">\u25b8</button></div></li>`;
      return `<li class="sidebar-item"><span class="sidebar-category-label">${label}${badge}</span></li>`;
    }
    renderGroup(g) {
      const label = esc(g.label || ''), items = g.items || [];
      if (!items.length) return `<li class="sidebar-item">${this._renderLink(g.path, label)}</li>`;
      return `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-collapsed="true"><div class="sidebar-item-row"><span class="sidebar-category-label">${label}</span><button class="sidebar-caret" tabindex="0">\u25b8</button></div><ul class="sidebar-menu sidebar-menu--nested">${items.map(it => `<li class="sidebar-item">${this._renderLink(it.path, it.label || it.title || '')}</li>`).join('')}</ul></li>`;
    }

    /*  TOC (unified) */
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
      const h = this.pageHeadings(); nav.innerHTML = h.length ? this.renderTocNodes(buildTree(h)) : '';
      this.activeTocLink = null;
    }
    renderTocNodes(nodes) {
      if (!nodes.length) return '';
      return '<ul class="theme-doc-toc-desktop-list">' + nodes.map(n => {
        const href = n.id ? '#' + esc(n.id) : '#';
        return `<li class="theme-doc-toc-desktop-link theme-doc-toc-desktop-link--lvl${n.level}"><a href="${esc(href)}" data-id="${esc(n.id || '')}" class="theme-doc-toc-desktop-link__a">${esc(n.text)}</a>${this.renderTocNodes(n.children || [])}</li>`;
      }).join('') + '</ul>';
    }

    /*  追踪 (unified) */
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
      const { file } = this._volInfo(), fileLinks = links.filter(link => normDoc((link.dataset.file || '').replace(/\.x?html?$/i, '')).toLowerCase() === normDoc(file).toLowerCase());
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
          else if (!id && hash) s = 0;                   // file-level heading but URL has hash → skip
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

    /*  SSG 特有：源目录折叠 */
    initSourceToc() {
      const toc = $('.doc-toc'); if (!toc) return;
      toc.addEventListener('click', e => {
        const caret = e.target.closest('.toc-caret'); if (!caret) return;
        const item = caret.closest('.toc-item--collapsible'); if (!item) return;
        e.preventDefault(); e.stopPropagation();
        const collapsed = item.getAttribute('data-collapsed') !== 'false';
        item.setAttribute('data-collapsed', collapsed ? 'false' : 'true');
        caret.textContent = collapsed ? '\u25be' : '\u25b8';
      });
    }

    /*  SSG 特有：合集查找 */
    _findCollection() {
      const path = normPath(PathResolver.stripRoot(location.pathname));
      return (window.LIBRARY_CONFIG || []).find(c => {
        const b = normPath(c.path || '');
        return b && (path.startsWith(b) || path.toLowerCase().startsWith(b.toLowerCase()));
      }) || null;
    }

    /*  SSG 特有：侧边栏开关 */
    open() {
      if (innerWidth >= 997) return
      this.sidebar?.classList.add('doc-sidebar--open')
      this.backdrop?.classList.add('sidebar-overlay--visible')
      this.lastSyncedId = null
      this.syncSidebar(this.activeHeadingId)
    }
    close() {
      if (innerWidth >= 997) return
      this.sidebar?.classList.remove('doc-sidebar--open')
      this.backdrop?.classList.remove('sidebar-overlay--visible')
    }

    /*  SSG 特有：动态加载 libmap */
    async loadLibmap() {
      const s = document.querySelector('script[src*="/assets/libmap.js"]');
      if (s) {
        await new Promise(r => setTimeout(r, 50))
        if (window.LIBRARY_CONFIG) return
      }
      const res = await fetch(`${document.body.dataset.site || ''}/assets/libmap.js`);
      if (res.ok) new Function(await res.text())();
    }
  }

  /* NavigationManager — 上一页/下一页 */
  class NavigationManager {
    init() {
      const meta = window.__PAGE_META__ || {};
      ['prev', 'next'].forEach(k => {
        const btn = $('#' + k + '-btn'), data = meta[k]; if (!btn || !data) return;
        const label = $('.pagination-link__label', btn);
        if (label && data.title) label.textContent = data.title;
        if (data.file) btn.href = PathResolver.path(location.pathname, data.file);
      });
    }
  }

  /* 初始化 */
  const menu = new MenuManager(), nav = new NavigationManager();
  window.__NAV__ = { menu, nav };
  const init = () => { menu.init(); nav.init(); };
  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', init) : init();
})();
