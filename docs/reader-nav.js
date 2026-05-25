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
  const normalizePath = value => String(value || '')
    .replace(/^https?:\/\/[^/]+/i, '')
    .replace(/[?#].*$/, '')
    .replace(/^\/+/, '')
    .replace(/\/+$/, '');
  const normalizeDoc = value => normalizePath(value).replace(/\.html$/i, '');
  const normalizeLowerPath = value => normalizePath(value).toLowerCase();
  const sameDocValue = (a, b) => {
    const left = normalizeDoc(a);
    const right = normalizeDoc(b);
    return left === right || left.toLowerCase() === right.toLowerCase();
  };
  const hasSelection = () => {
    const selection = document.getSelection();
    return !!(selection && !selection.isCollapsed && selection.rangeCount);
  };
  const resolveUrl = href => {
    try { return new URL(href, location.href).href; }
    catch { return location.pathname.replace(/[^/]*$/, '') + href; }
  };
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

  function resolveCssHref(href, base) {
    if (!href) return '';
    if (/^(https?:|\/\/)/i.test(href)) return href;
    if (href.startsWith('/')) return href;
    try {
      const dir = String(base || '').replace(/^\/+/, '').replace(/\/?$/, '/');
      const url = new URL(href, new URL(dir, location.href));
      return url.pathname + url.search + url.hash;
    } catch {
      return [String(base || '').replace(/^\/+|\/+$/g, ''), href.replace(/^\.+\//, '')].filter(Boolean).join('/');
    }
  }

  function findCollection(path) {
    const norm = normalizePath(path);
    const match = (window.LIBRARY_CONFIG || []).find(col => {
      const base = normalizePath(col.basePath || col.basepath || `/${col.id}/`);
      return base && norm.startsWith(base);
    });
    if (match) return match;
    const lower = norm.toLowerCase();
    return (window.LIBRARY_CONFIG || []).find(col => {
      const base = normalizeLowerPath(col.basePath || col.basepath || `/${col.id}/`);
      return base && lower.startsWith(base);
    }) || null;
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
    $, $$, esc, cssEsc, EventBag, HeadingTracker,
    normalizePath, normalizeDoc, hasSelection, resolveUrl, resolveCssHref,
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
      if (href.startsWith('?doc=')) {
        const url = new URL(href, location.href);
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
      const matchPath = (path, lowerFallback = false) => {
        if (!path || /^https?:/i.test(path)) return null;
        const itemPath = lowerFallback ? normalizeLowerPath(path) : normalizePath(path);
        if (!/\/index\.html$/i.test(itemPath)) return null;
        const dir = itemPath.replace(/\/index\.html$/i, '').replace(/\/nav\.html$/i, '');
        const currentPath = lowerFallback ? pathNorm.toLowerCase() : pathNorm;
        const currentDoc = lowerFallback ? docNorm.toLowerCase() : docNorm;
        const currentDir = lowerFallback ? docDir.toLowerCase() : docDir;
        return (currentDoc === normalizeDoc(itemPath) || currentDoc === normalizeDoc(dir) || currentDir === dir || currentPath.startsWith(dir + '/')) ? dir : null;
      };
      let best = null;
      const consider = (col, group, item, dir) => {
        if (dir && (!best || dir.length > best.dir.length)) best = { col, group, item, dir };
      };
      const scan = lowerFallback => {
        for (const col of window.LIBRARY_CONFIG || []) {
          consider(col, null, col, matchPath(col.path, lowerFallback));
          for (const group of col.groups || []) {
            consider(col, group, group, matchPath(group.path, lowerFallback));
            for (const item of group.items || []) {
              consider(col, group, item, matchPath(item.path, lowerFallback));
            }
          }
        }
      };
      scan(false);
      if (!best) scan(true);
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
      const colPath = normalizePath(col.path);
      const parts = [colPath ? { text: col.label, href: '?doc=' + esc(colPath), expand: col.id } : { text: col.label, expand: col.id }];
      if (item !== col) {
        const volPath = normalizePath(item.path || (this.currentVol.dir + '/index.html'));
        parts.push({ text: item.label || item.title || data.title || 'Contents', href: '?doc=' + esc(volPath) });
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
        col?.path ? { text: col.label || 'Library', href: '?doc=' + esc(normalizePath(col.path)), expand: col.id } : { text: col?.label || 'Library', expand: col?.id },
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
            : (node.id ? `?doc=${esc(fullFile)}#${esc(node.id)}` : `?doc=${esc(fullFile)}`);
        const children = node.children?.length ? `<ul class="sidebar-menu sidebar-menu--nested">${this.renderSidebarNodes(node.children, currentFull)}</ul>` : '';
        const caret = children ? '<button class="sidebar-caret" type="button" aria-label="Expand section" tabindex="0">\u25b8</button>' : '';
        const link = `<a href="${href}" data-file="${esc(rawFile)}" data-id="${esc(node.id || '')}" class="sidebar-link">${esc(node.text)}</a>`;
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
        const ext = /^https?:/i.test(col.path);
        const path = normalizePath(col.path);
        const href = ext ? col.path : '?doc=' + esc(path);
        return `<li class="sidebar-item"><a href="${esc(href)}"${ext ? ' target="_blank" rel="noopener"' : ` data-path="${esc('/' + path)}"`} class="sidebar-link">${label}${badge}</a></li>`;
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
        const ext = /^https?:/i.test(group.path);
        return `<li class="sidebar-item"><a href="${ext ? esc(group.path) : '?doc=' + esc(groupPath)}"${ext ? ' target="_blank" rel="noopener"' : ` data-path="${esc('/' + groupPath)}"`} class="sidebar-link">${label}</a></li>`;
      }
      return `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-group-path="${esc(groupPath)}" data-collapsed="true"><div class="sidebar-item-row"><span class="sidebar-category-label">${label}</span><button class="sidebar-caret" type="button" aria-label="Expand section" tabindex="0">\u25b8</button></div><ul class="sidebar-menu sidebar-menu--nested">${items.map(item => {
        const raw = item.path || '';
        const ext = /^https?:/i.test(raw);
        const path = normalizePath(raw);
        return `<li class="sidebar-item"><a href="${ext ? esc(raw) : '?doc=' + esc(path)}"${ext ? ' target="_blank" rel="noopener"' : ` data-path="${esc('/' + path)}"`} class="sidebar-link">${esc(item.label || item.title || '')}</a></li>`;
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
      const path = normalizePath(currentDoc());
      for (const col of window.LIBRARY_CONFIG || []) {
        const base = normalizePath(col.basePath || col.basepath || '');
        if (base && path.startsWith(base)) return col;
      }
      const lower = path.toLowerCase();
      for (const col of window.LIBRARY_CONFIG || []) {
        const base = normalizeLowerPath(col.basePath || col.basepath || '');
        if (base && lower.startsWith(base)) return col;
      }
      return findCollection(path);
    }
  }

  window.MenuManager = MenuManager;
})();
