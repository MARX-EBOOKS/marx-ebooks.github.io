(function () {
  'use strict';

  class EventBag {
    constructor() { this._off = []; }
    on(target, type, handler, options) {
      if (!target) return () => {};
      target.addEventListener(type, handler, options || false);
      const off = () => target.removeEventListener(type, handler, options || false);
      this._off.push(off);
      return off;
    }
    clear() {
      while (this._off.length) this._off.pop()();
    }
  }

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const esc = value => String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
  const cssEsc = value => (window.CSS?.escape ? CSS.escape(String(value)) : String(value).replace(/["\\]/g, '\\$&'));
  const hasSelection = () => {
    const selection = document.getSelection();
    return !!(selection && !selection.isCollapsed && selection.rangeCount);
  };

  class ReaderPaths {
    static specialSchemeRe = /^(?:mailto|tel|javascript|data|blob):/i;
    static httpRe = /^https?:$/i;

    static normalizePath(value) {
      return String(value || '')
        .replace(/^https?:\/\/[^/]+/i, '')
        .replace(/[?#].*$/, '')
        .replace(/^\/+/, '')
        .replace(/\/+$/, '');
    }

    static normalizeDoc(value) {
      return this.normalizePath(value).replace(/\.html$/i, '');
    }

    static sameDoc(a, b) {
      const left = this.normalizeDoc(a);
      const right = this.normalizeDoc(b);
      return left === right || left.toLowerCase() === right.toLowerCase();
    }

    static samePath(a, b) {
      const left = this.normalizePath(a);
      const right = this.normalizePath(b);
      return left === right || left.toLowerCase() === right.toLowerCase();
    }

    static startsWithPath(path, base) {
      const cleanPath = this.normalizePath(path);
      const cleanBase = this.normalizePath(base);
      if (!cleanBase) return false;
      return cleanPath.startsWith(cleanBase + '/') || cleanPath.toLowerCase().startsWith(cleanBase.toLowerCase() + '/');
    }

    static safeDecode(value) {
      try { return decodeURIComponent(value); }
      catch { return value; }
    }

    static resolveUrl(href) {
      try { return new URL(href, location.href).href; }
      catch { return location.pathname.replace(/[^/]*$/, '') + href; }
    }

    static docBaseUrl(basePath = '') {
      const clean = this.normalizePath(basePath);
      if (!clean) return new URL(location.href);
      return new URL('/' + clean.replace(/\/?$/, '/'), location.origin);
    }

    static docPathFromUrl(url) {
      const readerPath = this.normalizePath(location.pathname);
      const path = this.safeDecode(url.pathname);
      if (this.samePath(path, readerPath) && url.searchParams.has('doc')) {
        return url.searchParams.get('doc') || '';
      }
      return path + url.search;
    }

    static resolveDocHref(href, basePath = '') {
      const raw = String(href || '').trim();
      if (!raw) return null;
      if (raw.startsWith('#')) return { type: 'anchor', href: raw, hash: raw.slice(1) };
      if (this.specialSchemeRe.test(raw)) return { type: 'external', href: raw };

      let url;
      try {
        url = new URL(raw, raw.startsWith('?') ? location.href : this.docBaseUrl(basePath));
      } catch {
        return { type: 'external', href: raw };
      }

      if (!this.httpRe.test(url.protocol) || url.origin !== location.origin) return { type: 'external', href: url.href };
      const docPath = this.docPathFromUrl(url);
      if (!docPath) return { type: 'external', href: url.href };
      const hash = url.hash.slice(1);
      const target = this.readerHref(docPath);
      return {
        type: 'doc',
        href: target + (hash ? '#' + hash : ''),
        docPath,
        hash
      };
    }

    static readerHref(docPath, hash = '') {
      const raw = String(docPath || '');
      const i = raw.indexOf('#');
      const path = i >= 0 ? raw.slice(0, i) : raw;
      const anchor = hash || (i >= 0 ? raw.slice(i + 1) : '');
      return location.pathname + '?doc=' + path + (anchor ? '#' + anchor : '');
    }

    static resolveCssHref(href, base) {
      if (!href) return '';
      if (/^(https?:|\/\/)/i.test(href)) return href;
      try {
        const dir = String(base || '').replace(/\/?$/, '/');
        const baseUrl = dir.startsWith('/') ? new URL(dir, location.origin) : new URL(dir, location.href);
        const url = new URL(href, baseUrl);
        return url.pathname + url.search + url.hash;
      } catch {
        return [String(base || '').replace(/^\/+|\/+$/g, ''), href.replace(/^\.+\//, '')].filter(Boolean).join('/');
      }
    }

    static lowerPathFallback(value) {
      const raw = String(value || '');
      if (!raw) return raw;
      if (/^[a-z][a-z0-9+.-]*:/i.test(raw) || raw.startsWith('/')) {
        try {
          const url = new URL(raw, location.href);
          if (url.origin === location.origin) {
            const next = new URL(url.href);
            next.pathname = next.pathname.toLowerCase();
            return /^[a-z][a-z0-9+.-]*:/i.test(raw) ? next.href : next.pathname + next.search + next.hash;
          }
        } catch { }
        return raw;
      }
      const queryIndex = raw.indexOf('?');
      const hashIndex = raw.indexOf('#');
      const splitAt = [queryIndex, hashIndex].filter(i => i >= 0).sort((a, b) => a - b)[0];
      if (splitAt >= 0) return raw.slice(0, splitAt).toLowerCase() + raw.slice(splitAt);
      return raw.toLowerCase();
    }
  }

  const normalizePath = value => ReaderPaths.normalizePath(value);
  const normalizeDoc = value => ReaderPaths.normalizeDoc(value);
  const sameDocValue = (a, b) => ReaderPaths.sameDoc(a, b);
  const samePathValue = (a, b) => ReaderPaths.samePath(a, b);
  const startsWithPathValue = (path, base) => ReaderPaths.startsWithPath(path, base);
  const resolveUrl = href => ReaderPaths.resolveUrl(href);
  const resolveDocHref = (href, basePath = '') => ReaderPaths.resolveDocHref(href, basePath);
  const readerHref = (docPath, hash = '') => ReaderPaths.readerHref(docPath, hash);
  const resolveCssHref = (href, base) => ReaderPaths.resolveCssHref(href, base);
  async function fetchWithLowerFallback(path, options) {
    const lower = ReaderPaths.lowerPathFallback(path);
    try {
      const res = await fetch(path, options);
      if (res.ok || !lower || lower === path) return { res, path, url: path };
      try {
        const fallback = await fetch(lower, options);
        if (fallback.ok) return { res: fallback, path: lower, url: lower };
      } catch { }
      return { res, path, url: path };
    } catch (error) {
      if (!lower || lower === path) throw error;
      try {
        return { res: await fetch(lower, options), path: lower, url: lower };
      } catch {
        throw error;
      }
    }
  }

  const scrollToEl = (el, offset = 80, behavior = 'smooth') => {
    if (!el) return;
    window.scrollTo({ top: Math.max(0, el.getBoundingClientRect().top + scrollY - offset), behavior });
  };
  const syncFill = el => {
    if (!el) return;
    const min = parseFloat(el.min) || 0;
    const max = parseFloat(el.max) || 100;
    const val = parseFloat(el.value) || 0;
    el.style.setProperty('--_fill', (((val - min) / (max - min)) * 100).toFixed(2) + '%');
  };

  const scrollCallbacks = new Set();
  let scrollFrame = 0;
  const runScrollCallbacks = () => {
    scrollFrame = 0;
    scrollCallbacks.forEach(fn => fn());
  };
  window.addEventListener('scroll', () => {
    if (!scrollFrame) scrollFrame = requestAnimationFrame(runScrollCallbacks);
  }, { passive: true });
  const onScrollFrame = fn => {
    scrollCallbacks.add(fn);
    return () => scrollCallbacks.delete(fn);
  };

  function findCollection(path) {
    const norm = normalizePath(path);
    return (window.LIBRARY_CONFIG || []).find(col => startsWithPathValue(norm, col?.basePath || col?.basepath || `/${col?.id || ''}/`)) || null;
  }

  function getDomHeadings(container) {
    return container ? $$('h1,h2,h3,h4,h5,h6', container).filter(h => h.id) : [];
  }

  function getActiveHeadingId(headings, threshold = 200) {
    if (!headings?.length) return null;
    for (let i = headings.length - 1; i >= 0; i--) {
      if (headings[i].getBoundingClientRect().top <= threshold) return headings[i].id;
    }
    return headings[0].id;
  }

  function buildHeadingTree(headings) {
    const root = { level: 0, children: [] };
    const stack = [root];
    headings.forEach(item => {
      const node = { ...item, children: [] };
      while (stack.length > 1 && stack[stack.length - 1].level >= item.level) stack.pop();
      stack[stack.length - 1].children.push(node);
      stack.push(node);
    });
    return root.children;
  }

  function expandTo(el, container) {
    if (!el || !container) return;
    let parent = el.closest('li');
    while (parent && container.contains(parent)) {
      if (parent.classList.contains('sidebar-item--collapsible')) {
        parent.setAttribute('data-collapsed', 'false');
        const caret = $('.sidebar-caret', parent);
        if (caret) caret.textContent = '\u25be';
      }
      parent = parent.parentElement?.closest('.sidebar-item');
    }
  }

  const volumeCache = new Map();
  async function fetchVolData(dir, cache = volumeCache) {
    const cleanDir = normalizePath(dir);
    if (!cleanDir) return null;
    if (cache instanceof Map && cache.has(cleanDir)) return cache.get(cleanDir);
    if (!(cache instanceof Map) && cache[cleanDir]) return cache[cleanDir];

    const load = async candidateDir => {
      let data = null;
      try {
        const res = await fetch(new URL(candidateDir + '/index.json', location.href).href);
        if (res.ok) data = await res.json();
      } catch { }

      if (data) return data;
      try {
        const jsUrl = new URL(candidateDir + '/index.js', location.href).href;
        const res = await fetch(jsUrl);
        const type = res.headers.get('content-type') || '';
        if (!res.ok || /text\/html/i.test(type)) return null;
        const js = await res.text();
        if (!/\bexport\s+default\b/.test(js)) return null;
        const blobUrl = URL.createObjectURL(new Blob([js], { type: 'text/javascript' }));
        const mod = await import(blobUrl);
        URL.revokeObjectURL(blobUrl);
        data = mod?.default || null;
      } catch { }
      return data;
    };

    const lowerDir = cleanDir.toLowerCase();
    let data = await load(cleanDir);
    if (!data && lowerDir !== cleanDir) {
      if (cache instanceof Map && cache.has(lowerDir)) data = cache.get(lowerDir);
      else if (!(cache instanceof Map) && cache[lowerDir]) data = cache[lowerDir];
      else data = await load(lowerDir);
    }

    if (data) {
      if (cache instanceof Map) cache.set(cleanDir, data);
      else cache[cleanDir] = data;
      if (lowerDir !== cleanDir) {
        if (cache instanceof Map) cache.set(lowerDir, data);
        else cache[lowerDir] = data;
      }
    }
    return data;
  }

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
      // 阅读器内容可能异步注入，图片和字体也会改变高度，所以启动后需要重新测量标题位置。
      const queueMeasure = () => {
        if (!this.frame) this.frame = requestAnimationFrame(() => {
          this.frame = 0;
          this.measure();
          this.track(true);
        });
      };
      this.bag.on(window, 'resize', queueMeasure, { passive: true });
      this.bag.on(window, 'load', queueMeasure, { once: true });
      setTimeout(queueMeasure, 500);
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
      this.headings = [];
      this.tops = [];
      this.activeId = null;
    }
    measure() {
      this.tops = this.headings.map(h => h.getBoundingClientRect().top + scrollY);
    }
    track(force) {
      if (hasSelection()) return;
      const id = this.pick();
      if (force || id !== this.activeId) {
        this.activeId = id;
        this.onChange(id);
      }
    }
    pick() {
      if (!this.tops.length) return this.headings[0]?.id || null;
      const y = scrollY + this.threshold;
      // 滚动时用二分查找定位当前标题，保证长文档里追踪仍然轻量。
      let lo = 0;
      let hi = this.tops.length - 1;
      let best = 0;
      while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        if (this.tops[mid] <= y) {
          best = mid;
          lo = mid + 1;
        } else {
          hi = mid - 1;
        }
      }
      return this.headings[best]?.id || null;
    }
  }

  const Core = {
    $, $$, esc, cssEsc, EventBag, ReaderPaths, HeadingTracker,
    normalizePath, normalizeDoc, sameDocValue, samePathValue, startsWithPathValue,
    fetchWithLowerFallback,
    hasSelection, resolveUrl, resolveDocHref, readerHref, resolveCssHref,
    findCollection, scrollToEl, syncFill, onScrollFrame,
    getDomHeadings, getActiveHeadingId, buildHeadingTree, expandTo, fetchVolData
  };

  Object.assign(window, {
    ReaderCore: Core,
    $, $$,
    on: (target, type, handler, options) => target && target.addEventListener(type, handler, options || false),
    esc,
    syncFill,
    resolveUrl,
    resolveCssHref,
    fetchWithLowerFallback,
    findCollection,
    scrollToEl,
    getDomHeadings,
    getActiveHeadingId,
    hasActiveTextSelection: hasSelection,
    buildHeadingTree,
    expandTo,
    fetchVolData,
    onScrollFrame
  });

  const currentDoc = () => (window.ReaderState?.doc || (typeof state !== 'undefined' ? state.doc : null) || '');

  class MenuManager {
    constructor() {
      this.sidebar = null;
      this.navTree = null;
      this.mode = 'libmap';
      this.currentVol = null;
      this.activeHeadingId = null;
      this.activeSidebarLink = null;
      this.activeTocLink = null;
      this.lastSyncedId = null;
      this.linkCache = null;
      this.tracker = null;
      this.bag = new EventBag();
      this.sidebarObserver = null;
      this.waitObserver = null;
      this.fadeObserver = null;
      this.volCache = new Map();
    }

    init() {
      this.sidebar = $('#lsidebar');
      this.navTree = $('#nav-tree');
      if (!this.sidebar || !this.navTree) return;
      this.bindDelegatedEvents();
      this.observeSidebar();
      this.reinit(currentDoc());
    }

    reinit(docPath) {
      this.cleanupRender();
      this.navTree.innerHTML = '';
      this.currentVol = docPath ? this.detectVolume(docPath) : null;
      // reader 用 ?doc= 表示当前文档：有卷册数据时显示卷册目录，否则按本页/总目录降级。
      if (!docPath) {
        this.mode = 'libmap';
        this.renderLibmapMenu();
        this.afterRender(docPath);
      } else if (this.currentVol) {
        this.mode = 'epub';
        this.renderEpubMenu(docPath);
      } else if (innerWidth < 997 && getDomHeadings($('#content')).length > 1) {
        this.mode = 'page-toc';
        this.renderPageTocMenu(docPath);
      } else {
        this.mode = 'libmap';
        this.renderLibmapMenu();
        this.afterRender(docPath);
      }
    }

    cleanupRender() {
      if (this.tracker) this.tracker.stop();
      this.tracker = null;
      if (this.waitObserver) this.waitObserver.disconnect();
      if (this.fadeObserver) this.fadeObserver.disconnect();
      this.waitObserver = null;
      this.fadeObserver = null;
      this.activeHeadingId = null;
      this.activeSidebarLink = null;
      this.activeTocLink = null;
      this.lastSyncedId = null;
      this.linkCache = null;
    }

    bindDelegatedEvents() {
      if (this._delegated) return;
      this._delegated = true;
      this.navTree.addEventListener('click', e => this.handleClick(e));
      this.navTree.addEventListener('keydown', e => {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        const target = e.target.closest('.sidebar-caret, .sidebar-category-label');
        if (!target) return;
        e.preventDefault();
        this.toggleItem(target.closest('.sidebar-item--collapsible'));
      });
    }

    observeSidebar() {
      if (this.sidebarObserver) return;
      this.sidebarObserver = new MutationObserver(() => {
        if (innerWidth < 997 && this.sidebar.classList.contains('doc-sidebar--open')) {
          this.lastSyncedId = null;
          this.syncSidebar(this.activeHeadingId);
        }
      });
      this.sidebarObserver.observe(this.sidebar, { attributes: true, attributeFilter: ['class'] });
    }

    handleClick(e) {
      const target = e.target.nodeType === 1 ? e.target : e.target.parentElement;
      const expandLink = target?.closest('a[data-expand-section]');
      if (expandLink) {
        e.preventDefault();
        e.stopPropagation();
        this.expandSection(expandLink.dataset.expandSection);
        return;
      }

      const toggle = target?.closest('.sidebar-caret, .sidebar-category-label');
      if (toggle && !toggle.closest('a')) {
        const item = toggle.closest('.sidebar-item--collapsible');
        if (item) {
          e.preventDefault();
          e.stopPropagation();
          this.toggleItem(item);
          return;
        }
      }

      const link = target?.closest('.sidebar-link');
      if (!link) return;
      const href = link.getAttribute('href') || '';
      if (href.startsWith('#')) {
        e.preventDefault();
        this.scrollToHash(href.slice(1), true);
        return;
      }
      const url = new URL(href, location.href);
      if (ReaderPaths.samePath(url.pathname, location.pathname) && url.searchParams.has('doc')) {
        const docPath = url.searchParams.get('doc') || '';
        const hash = url.hash.slice(1);
        if (sameDocValue(docPath, currentDoc()) && hash) {
          e.preventDefault();
          this.scrollToHash(hash, true);
        } else if (hash) {
          sessionStorage.setItem('__reader_pending_anchor', hash);
          sessionStorage.setItem('__reader_pending_doc', docPath);
        }
      }
    }

    toggleItem(item) {
      if (!item) return;
      if (item.dataset.section && !item.dataset.loaded) {
        this.loadSection(item);
      }
      const collapsed = item.getAttribute('data-collapsed') !== 'false';
      item.setAttribute('data-collapsed', collapsed ? 'false' : 'true');
      const caret = $('.sidebar-caret', item);
      if (caret) caret.textContent = collapsed ? '\u25be' : '\u25b8';
    }

    loadSection(item) {
      const col = (window.LIBRARY_CONFIG || []).find(c => c.id === item.dataset.section);
      if (!col) return;
      const html = (col.groups || []).map(group => this.renderGroup(group)).join('');
      if (html) {
        const ul = document.createElement('ul');
        ul.className = 'sidebar-menu sidebar-menu--nested';
        ul.innerHTML = html;
        item.appendChild(ul);
      }
      item.dataset.loaded = 'true';
    }

    expandSection(sectionId) {
      const item = this.navTree.querySelector(`.sidebar-item[data-section="${cssEsc(sectionId)}"]`);
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
      const pathNorm = normalizePath(docPath);
      const docNorm = normalizeDoc(pathNorm);
      const docDir = pathNorm.replace(/\/[^/]+$/, '');
      const pathLower = pathNorm.toLowerCase();
      const docLower = docNorm.toLowerCase();
      const dirLower = docDir.toLowerCase();
      const matchPath = path => {
        if (!path || /^https?:/i.test(path)) return null;
        const itemPath = normalizePath(path);
        if (!/\/index\.html$/i.test(itemPath)) return null;
        const dir = itemPath.replace(/\/index\.html$/i, '').replace(/\/nav\.html$/i, '');
        const dirLowerCandidate = dir.toLowerCase();
        return (docLower === normalizeDoc(itemPath).toLowerCase() || docLower === normalizeDoc(dir).toLowerCase() || dirLower === dirLowerCandidate || pathLower.startsWith(dirLowerCandidate + '/')) ? dir : null;
      };
      let best = null;
      const consider = (col, group, item, dir) => {
        if (dir && (!best || dir.length > best.dir.length)) best = { col, group, item, dir };
      };
      for (const col of window.LIBRARY_CONFIG || []) {
        consider(col, null, col, matchPath(col.path));
        for (const group of col.groups || []) {
          consider(col, group, group, matchPath(group.path));
          for (const item of group.items || []) {
            consider(col, group, item, matchPath(item.path));
          }
        }
      }
      return best;
    }

    volumeDocPath(docPath = currentDoc()) {
      const path = normalizePath(docPath);
      if (this.currentVol && sameDocValue(path, this.currentVol.dir)) return this.currentVol.dir + '/index.html';
      return path;
    }

    volumeDocFile(docPath = currentDoc()) {
      return normalizeDoc(this.volumeDocPath(docPath)).split('/').pop() || 'index';
    }

    async renderEpubMenu(docPath) {
      const dir = this.currentVol?.dir || '';
      const data = await this.fetchVolumeData(dir);
      if (!data) {
        const norpath = normalizePath(docPath);
        this.mode = (sameDocValue(norpath, dir) || sameDocValue(norpath, dir + '/index.html') || sameDocValue(norpath, dir + '/nav.html')) ? 'libmap' : (innerWidth < 997 ? 'page-toc' : 'libmap');
        this.mode === 'page-toc' ? this.renderPageTocMenu(docPath) : this.renderLibmapMenu();
        this.afterRender(docPath);
        return;
      }

      this.currentVol.data = data;
      const { col, item } = this.currentVol;
      const colPath = col.path || '';
      const parts = [colPath ? { text: col.label, href: readerHref(colPath), expand: col.id } : { text: col.label, expand: col.id }];
      if (item !== col) {
        const volPath = item.path || (this.currentVol.dir + '/index.html');
        parts.push({ text: item.label || item.title || data.title || 'Contents', href: readerHref(volPath) });
      }
      parts.push({ id: 'page-breadcrumb-link', isPageBadge: window.__PAGE_BAR__?.hasPageAnchors });
      const tree = buildHeadingTree(data.headings || []);
      this.navTree.innerHTML =
        this.renderBreadcrumb(parts) +
        (tree.length ? this.renderSidebarTree(tree, 'epub-toc', docPath) : '') +
        '<div class="section-divider"><span>All works</span></div>' +
        this.buildLibmapHtml();
      this.afterRender(docPath);
    }

    renderPageTocMenu(docPath) {
      const headings = getDomHeadings($('#content'));
      if (headings.length <= 1) {
        this.mode = 'libmap';
        this.renderLibmapMenu();
        this.afterRender(docPath);
        return;
      }
      const col = this.currentVol?.col || this.findCollectionByCurrentPath();
      const currentFile = normalizePath(docPath).split('/').pop();
      const nodes = headings.map(h => ({
        level: Number(h.tagName[1]) || 2,
        text: h.textContent.trim(),
        id: h.id,
        file: currentFile
      }));
      const parts = [
        col?.path ? { text: col.label || 'Library', href: readerHref(col.path), expand: col.id } : { text: col?.label || 'Library', expand: col?.id },
        { text: nodes[0]?.text || document.title }
      ];
      this.navTree.innerHTML =
        this.renderBreadcrumb(parts) +
        this.renderSidebarTree(buildHeadingTree(nodes), 'page-toc', docPath) +
        '<div class="section-divider"><span>All works</span></div>' +
        this.buildLibmapHtml();
      this.afterRender(docPath);
    }

    renderLibmapMenu() {
      this.navTree.innerHTML = this.buildLibmapHtml();
    }

    afterRender(docPath) {
      this.linkCache = null;
      this.highlightCurrent(docPath);
      this.renderTocRail();
      this.startTracking();
      this.initBreadcrumbFade();
      this.scrollToPendingAnchor();
      if (window.__PAGE_BAR__?.currentPage != null) window.__PAGE_BAR__._updateBadge(window.__PAGE_BAR__.currentPage);
    }

    async fetchVolumeData(dir) {
      const raw = await fetchVolData(dir, this.volCache);
      if (!raw) return null;
      if (!Array.isArray(raw) && raw.version === 1) return raw;
      if (!Array.isArray(raw)) return null;
      const headings = [];
      raw.forEach(file => (file.headings || []).forEach(h => {
        headings.push({
          level: h.level !== undefined && h.level !== null ? h.level : 2,
          text: h.text || '',
          id: h.id || null,
          file: h.filename || file.file || file.path || ''
        });
      }));
      return {
        version: 1,
        title: this.currentVol?.item?.label || dir,
        files: raw,
        headings
      };
    }

    renderBreadcrumb(parts) {
      return '<div class="breadcrumb" aria-label="Breadcrumb">' + parts.map((part, i) => {
        const sep = i > 0 || part.id === 'page-breadcrumb-link' ? '<span class="breadcrumb__sep">/</span>' : '';
        if (part.id === 'page-breadcrumb-link' && !part.isPageBadge) return ''
        if (part.id === 'page-breadcrumb-link') return sep + `<a href="#" id="${esc(part.id)}" style="display:none"></a>`;
        if (part.href) return sep + `<a href="${esc(part.href)}"${part.expand ? ` data-expand-section="${esc(part.expand)}"` : ''}>${esc(part.text)}</a>`;

        return sep + `<span>${esc(part.text || '')}</span>`;
      }).join('') + '</div>';
    }

    renderNavLink({ href, path, text, badge = '', className = 'sidebar-link', dataFile = '', dataId = '', extraAttrs = '' }) {
      const raw = href || path || '';
      const resolved = !href && /^https?:/i.test(raw) ? resolveDocHref(raw) : null;
      const external = resolved?.type === 'external';
      const cleanPath = external ? '' : normalizePath(resolved?.docPath || raw);
      const finalHref = href || (resolved?.type === 'doc' ? resolved.href : readerHref(raw));
      const attrs = [
        `href="${esc(finalHref)}"`,
        external ? 'target="_blank" rel="noopener"' : (!href && cleanPath ? `data-path="${esc('/' + cleanPath)}"` : ''),
        dataFile ? `data-file="${esc(dataFile)}"` : '',
        dataId ? `data-id="${esc(dataId)}"` : '',
        extraAttrs,
        `class="${esc(className)}"`
      ].filter(Boolean).join(' ');
      return `<a ${attrs}>${esc(text || '')}${badge}</a>`;
    }

    renderSidebarTree(nodes, className, docPath) {
      const currentFull = normalizeDoc(this.volumeDocPath(docPath || currentDoc()));
      return `<ul class="sidebar-menu ${esc(className)}">${this.renderSidebarNodes(nodes, currentFull)}</ul>`;
    }

    renderSidebarNodes(nodes, currentFull) {
      const volDir = this.currentVol?.dir || '';
      const isPageToc = this.mode === 'page-toc';
      return nodes.map(node => {
        const rawFile = node.file || '';
        const fullFile = rawFile && !isPageToc ? normalizePath((volDir + '/' + rawFile).replace(/\/+/g, '/')) : rawFile;
        const sameFile = isPageToc || (fullFile && sameDocValue(fullFile, currentFull));
        const href = isPageToc
          ? (node.id ? `#${esc(node.id)}` : '#')
          : sameFile
            ? (node.id ? `#${esc(node.id)}` : '#')
            : readerHref(fullFile, node.id || '');
        const children = node.children?.length ? `<ul class="sidebar-menu sidebar-menu--nested">${this.renderSidebarNodes(node.children, currentFull)}</ul>` : '';
        const caret = children ? '<button class="sidebar-caret" type="button" aria-label="Expand section" tabindex="0">\u25b8</button>' : '';
        const link = this.renderNavLink({ href, text: node.text, dataFile: rawFile, dataId: node.id || '' });
        return children
          ? `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-collapsed="true"><div class="sidebar-item-row">${link}${caret}</div>${children}</li>`
          : `<li class="sidebar-item">${link}</li>`;
      }).join('');
    }

    buildLibmapHtml() {
      if (!window.LIBRARY_CONFIG?.length) return '<div class="sidebar-menu" style="padding:20px">Navigation unavailable</div>';
      return '<ul class="sidebar-menu">' + (window.LIBRARY_CONFIG || []).map(col => this.renderSection(col)).join('') + '</ul>';
    }

    renderSection(col) {
      const label = esc(col.label || col.title || col.id || '');
      const badge = col.badge ? ` <span class="sidebar-badge">${esc(col.badge)}</span>` : '';
      const groups = col.groups || [];
      if (!groups.length && col.path) {
        return `<li class="sidebar-item">${this.renderNavLink({ path: col.path, text: col.label || col.title || col.id || '', badge })}</li>`;
      }
      if (groups.length) {
        return `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-section="${esc(col.id)}" data-collapsed="true"><div class="sidebar-item-row"><span class="sidebar-category-label">${label}${badge}</span><button class="sidebar-caret" type="button" aria-label="Expand section" tabindex="0">\u25b8</button></div></li>`;
      }
      return `<li class="sidebar-item"><span class="sidebar-category-label">${label}${badge}</span></li>`;
    }

    renderGroup(group) {
      const label = esc(group.label || '');
      const items = group.items || [];
      const groupPath = normalizePath(group.path);
      if (!items.length) {
        if (!groupPath) return `<li class="sidebar-item"><span class="sidebar-category-label">${label}</span></li>`;
        return `<li class="sidebar-item">${this.renderNavLink({ path: group.path, text: group.label || '' })}</li>`;
      }
      return `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-group-path="${esc(groupPath)}" data-collapsed="true"><div class="sidebar-item-row"><span class="sidebar-category-label">${label}</span><button class="sidebar-caret" type="button" aria-label="Expand section" tabindex="0">\u25b8</button></div><ul class="sidebar-menu sidebar-menu--nested">${items.map(item => {
        return `<li class="sidebar-item">${this.renderNavLink({ path: item.path || '', text: item.label || item.title || '' })}</li>`;
      }).join('')}</ul></li>`;
    }

    getPageHeadings() {
      if (this.mode === 'epub') {
        const file = this.volumeDocFile();
        const domHeadings = getDomHeadings($('#content'));
        let domIndex = 0;
        return (this.currentVol?.data?.headings || []).filter(h => sameDocValue(normalizeDoc(h.file || '').split('/').pop(), file)).map(h => {
          const id = h.id || domHeadings[domIndex++]?.id || null;
          return { level: h.level !== undefined && h.level !== null ? h.level : 2, text: h.text || '', id };
        }).filter(h => h.id);
      }
      return getDomHeadings($('#content')).map(h => ({
        level: Number(h.tagName[1]) || 2,
        text: h.textContent.trim(),
        id: h.id
      }));
    }

    renderTocRail() {
      const nav = $('#toc-desktop-nav');
      if (!nav) return;
      const headings = this.getPageHeadings();
      nav.innerHTML = headings.length ? this.renderTocNodes(buildHeadingTree(headings)) : '';
      this.activeTocLink = null;
    }

    renderTocNodes(nodes) {
      if (!nodes.length) return '';
      return '<ul class="theme-doc-toc-desktop-list">' + nodes.map(node =>
        `<li class="theme-doc-toc-desktop-link theme-doc-toc-desktop-link--lvl${node.level}"><a href="#${esc(node.id)}" class="theme-doc-toc-desktop-link__a">${esc(node.text)}</a>${this.renderTocNodes(node.children || [])}</li>`
      ).join('') + '</ul>';
    }

    startTracking() {
      const content = $('#content');
      const start = () => {
        if (this.tracker) this.tracker.stop();
        this.tracker = new HeadingTracker({
          getHeadings: () => getDomHeadings(content),
          onChange: id => this.updateTracking(id)
        });
        return this.tracker.start();
      };
      if (!content || start()) return;
      const mo = new MutationObserver((_, observer) => {
        if (start()) observer.disconnect();
      });
      mo.observe(content, { subtree: true, attributes: true, attributeFilter: ['id'] });
      this.waitObserver = mo;
    }

    updateTracking(id) {
      this.activeHeadingId = id;
      // 当前标题变化后，同时驱动侧栏、桌面 TOC 和移动端自动滚动。
      this.updateSidebarTracking(id);
      this.updateTocTracking(id);
      this.syncSidebar(id);
    }

    getSidebarLinks() {
      const tree = this.navTree.querySelector('.sidebar-menu');
      if (!tree) return [];
      if (!this.linkCache || this.linkCache.tree !== tree) {
        this.linkCache = { tree, links: $$('.sidebar-link', tree) };
      }
      return this.linkCache.links;
    }

    updateSidebarTracking(id) {
      // 纯 libmap 是总目录，不对应 reader 当前正文，保持无高亮。
      if (this.mode === 'libmap') return;
      const links = this.getSidebarLinks();
      if (!links.length) return;
      this.activeSidebarLink?.classList.remove('sidebar-link--active');
      this.activeSidebarLink = null;
      const file = this.volumeDocFile();
      const sameFile = a => sameDocValue(normalizeDoc(a.dataset.file || '').split('/').pop(), file);
      const match = (id && links.find(a => sameFile(a) && a.dataset.id === id))
        || links.find(a => sameFile(a) && !a.dataset.id)
        || links.find(sameFile);
      if (!match) return;
      // 先限定同一文件，再匹配锚点，避免不同文档里的同名标题互相误亮。
      match.classList.add('sidebar-link--active');
      this.activeSidebarLink = match;
      expandTo(match, this.navTree.querySelector('.sidebar-menu'));
    }

    updateTocTracking(id) {
      const nav = $('#toc-desktop-nav');
      if (!nav) return;
      this.activeTocLink?.classList.remove('theme-doc-toc-desktop-link__a--active');
      this.activeTocLink = null;
      if (!id) return;
      const match = $$('.theme-doc-toc-desktop-link__a', nav).find(a => a.getAttribute('href') === '#' + id);
      if (match) {
        match.classList.add('theme-doc-toc-desktop-link__a--active');
        this.activeTocLink = match;
      }
    }

    syncSidebar(id) {
      if (innerWidth >= 997 || hasSelection() || !id || id === this.lastSyncedId) return;
      if (!this.sidebar?.classList.contains('doc-sidebar--open')) return;
      const active = this.activeSidebarLink || $('.sidebar-link.sidebar-link--active', this.navTree);
      if (!active) return;
      this.lastSyncedId = id;
      requestAnimationFrame(() => active.scrollIntoView({ block: 'center', behavior: 'auto' }));
    }

    highlightCurrent(docPath) {
      const tree = this.navTree.querySelector('.sidebar-menu');
      if (!tree) return;
      if (this.mode === 'libmap') {
        // 总目录模式只负责导航入口，不表达阅读进度，因此不加 active 样式。
        return;
      }
      const file = this.volumeDocFile(docPath || currentDoc());
      const hash = location.hash.slice(1);
      const links = $$('.sidebar-link', tree);
      let best = null;
      let score = 0;
      links.forEach(a => {
        const f = normalizeDoc(a.dataset.file || '').split('/').pop();
        const id = a.dataset.id || '';
        let s = 0;
        if (sameDocValue(f, file)) {
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

    initBreadcrumbFade() {
      if (this.mode !== 'epub' && this.mode !== 'page-toc') return;
      const bc = $('.breadcrumb', this.navTree);
      const menu = $('.sidebar-menu', this.navTree);
      if (!bc || !menu) return;
      const io = new IntersectionObserver(entries => {
        entries.forEach(entry => bc.classList.toggle('breadcrumb--faded', entry.boundingClientRect.bottom < entry.rootBounds.top));
      }, { root: this.navTree, threshold: 0 });
      io.observe(menu);
      this.fadeObserver = io;
    }

    scrollToPendingAnchor() {
      const hash = sessionStorage.getItem('__reader_pending_anchor');
      const docPath = sessionStorage.getItem('__reader_pending_doc');
      if (!hash) return;
      sessionStorage.removeItem('__reader_pending_anchor');
      sessionStorage.removeItem('__reader_pending_doc');
      if (docPath && !sameDocValue(docPath, currentDoc())) return;
      const tryScroll = () => {
        const el = document.getElementById(hash);
        if (!el) return false;
        scrollToEl(el);
        return true;
      };
      if (!tryScroll()) requestAnimationFrame(() => { if (!tryScroll()) setTimeout(tryScroll, 150); });
    }

    findCollectionByCurrentPath() {
      return findCollection(currentDoc());
    }
  }

  window.MenuManager = MenuManager;
})();
