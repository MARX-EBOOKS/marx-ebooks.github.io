(function () {
  'use strict';

  const doc = document;
  const win = window;

  class EventBag {
    constructor() { this.off = []; }
    on(target, type, handler, options) {
      if (!target) return () => {};
      target.addEventListener(type, handler, options || false);
      const cleanup = () => target.removeEventListener(type, handler, options || false);
      this.off.push(cleanup);
      return cleanup;
    }
    clear() { while (this.off.length) this.off.pop()(); }
  }

  const $ = (selector, root = doc) => root.querySelector(selector);
  const $$ = (selector, root = doc) => Array.from(root.querySelectorAll(selector));
  const esc = value => String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
  const cssEsc = value => (win.CSS?.escape ? CSS.escape(String(value)) : String(value).replace(/["\\]/g, '\\$&'));
  const normalizePath = value => String(value || '')
    .replace(/^https?:\/\/[^/]+/i, '')
    .replace(/[?#].*$/, '')
    .replace(/^\/+/, '')
    .replace(/\/+$/, '');
  const normalizeDoc = value => normalizePath(value).replace(/\.html$/i, '');
  const withoutDocs = value => normalizePath(value).replace(/^docs\//, '');
  const resolveUrl = href => { try { return new URL(href, location.href).href; } catch { return href; } };
  const hasSelection = () => {
    const selection = doc.getSelection();
    return !!(selection && !selection.isCollapsed && selection.rangeCount);
  };
  const scrollToEl = (el, offset = 80, behavior = 'smooth') => {
    if (!el) return;
    win.scrollTo({ top: Math.max(0, el.getBoundingClientRect().top + scrollY - offset), behavior });
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
  win.addEventListener('scroll', () => {
    if (!scrollFrame) scrollFrame = requestAnimationFrame(() => {
      scrollFrame = 0;
      scrollCallbacks.forEach(fn => fn());
    });
  }, { passive: true });
  const onScrollFrame = fn => {
    scrollCallbacks.add(fn);
    return () => scrollCallbacks.delete(fn);
  };

  function getDomHeadings(container) {
    return container ? $$('h1,h2,h3,h4,h5,h6', container).filter(h => h.id) : [];
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

  class HeadingTracker {
    constructor({ getHeadings, onChange, threshold = 200 }) {
      this.getHeadings = getHeadings;
      this.onChange = onChange;
      this.threshold = threshold;
      this.headings = [];
      this.tops = [];
      this.activeId = null;
      this.bag = new EventBag();
      this.frame = 0;
      this.offScroll = null;
    }
    start() {
      this.stop();
      this.headings = this.getHeadings();
      if (!this.headings.length) return false;
      this.measure();
      const queueMeasure = () => {
        if (!this.frame) this.frame = requestAnimationFrame(() => {
          this.frame = 0;
          this.measure();
          this.track(true);
        });
      };
      this.bag.on(win, 'resize', queueMeasure, { passive: true });
      this.bag.on(win, 'load', queueMeasure, { once: true });
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

  const ReaderCore = win.ReaderCore || {
    $, $$, esc, cssEsc, EventBag, HeadingTracker,
    normalizePath, normalizeDoc, withoutDocs, resolveUrl, hasSelection,
    scrollToEl, syncFill, onScrollFrame, getDomHeadings, buildHeadingTree, expandTo
  };
  Object.assign(win, { ReaderCore, $, $$, esc, syncFill, onScrollFrame });

  class MenuManager {
    constructor() {
      this.sidebar = null;
      this.backdrop = null;
      this.navTree = null;
      this.mode = 'libmap';
      this.currentVol = null;
      this.activeHeadingId = null;
      this.activeSidebarLink = null;
      this.activeTocLink = null;
      this.lastSyncedId = null;
      this.linkCache = null;
      this.volCache = new Map();
      this.tracker = null;
      this.waitObserver = null;
      this.fadeObserver = null;
      this.lastWidth = innerWidth;
    }

    async init() {
      this.sidebar = $('#lsidebar');
      this.backdrop = $('#sidebar-backdrop');
      this.navTree = $('#nav-tree');
      if (!this.sidebar || !this.navTree) return;
      this.bindChrome();
      this.bindDelegatedEvents();
      if (!win.LIBRARY_CONFIG?.length) await this.loadLibmap();
      await this.buildMenu();
      this.initSourceToc();
    }

    bindChrome() {
      $('#sidebar-toggle')?.addEventListener('click', () => this.toggle());
      this.backdrop?.addEventListener('click', () => this.close());
      $('#sidebar-close-btn')?.addEventListener('click', () => this.close());
      win.addEventListener('resize', () => this.handleResize(), { passive: true });
    }

    bindDelegatedEvents() {
      this.navTree.addEventListener('click', e => this.handleClick(e));
      this.navTree.addEventListener('keydown', e => {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        const target = e.target.closest('.sidebar-caret, .sidebar-category-label');
        if (!target || target.closest('a')) return;
        e.preventDefault();
        this.toggleItem(target.closest('.sidebar-item--collapsible'));
      });
    }

    async handleResize() {
      const width = innerWidth;
      if ((this.lastWidth < 997 && width >= 997) || (this.lastWidth >= 997 && width < 997)) {
        this.lastWidth = width;
        await this.buildMenu();
        this.syncSidebar(this.activeHeadingId);
      } else {
        this.lastWidth = width;
      }
    }

    async buildMenu() {
      this.cleanupRender();
      this.currentVol = this.detectVolume();
      if (this.currentVol) {
        this.mode = 'epub';
        await this.renderEpubMenu();
      } else if (innerWidth < 997 && getDomHeadings($('#content')).length > 1 && !this.isHomePage()) {
        this.mode = 'page-toc';
        this.renderPageTocMenu();
      } else {
        this.mode = 'libmap';
        this.renderLibmapMenu();
      }
      this.afterRender();
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

    afterRender() {
      this.highlightCurrent();
      this.renderTocRail();
      this.startTracking();
      this.initBreadcrumbFade();
    }

    isHomePage() {
      const page = location.pathname.split('/').pop().toLowerCase();
      return !page || page === 'index.html' || page === 'nav.html';
    }

    handleClick(e) {
      const target = e.target.nodeType === 1 ? e.target : e.target.parentElement;
      const expand = target?.closest('a[data-expand-section]');
      if (expand) {
        e.preventDefault();
        this.expandSection(expand.dataset.expandSection);
        return;
      }
      const toggle = target?.closest('.sidebar-caret, .sidebar-category-label');
      if (toggle && !toggle.closest('a')) {
        e.preventDefault();
        e.stopPropagation();
        this.toggleItem(toggle.closest('.sidebar-item--collapsible'));
        return;
      }
      const link = target?.closest('.sidebar-link');
      if (!link) return;
      const href = link.getAttribute('href') || '';
      if (href.startsWith('#')) {
        e.preventDefault();
        this.scrollToHash(href.slice(1));
      } else {
        try {
          const url = new URL(href, location.href);
          if (url.pathname === location.pathname && url.hash) {
            e.preventDefault();
            this.scrollToHash(url.hash.slice(1));
          }
        } catch { }
      }
    }

    toggleItem(item) {
      if (!item) return;
      if (item.dataset.section && !item.dataset.loaded) this.loadSection(item);
      const collapsed = item.getAttribute('data-collapsed') !== 'false';
      item.setAttribute('data-collapsed', collapsed ? 'false' : 'true');
      const caret = $('.sidebar-caret', item);
      if (caret) caret.textContent = collapsed ? '\u25be' : '\u25b8';
    }

    loadSection(item) {
      const col = (win.LIBRARY_CONFIG || []).find(c => c.id === item.dataset.section);
      if (!col) return;
      const html = (col.groups || []).map(group => this.renderGroup(group)).join('');
      if (html) {
        const ul = doc.createElement('ul');
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

    scrollToHash(hash) {
      const el = doc.getElementById(hash) || doc.querySelector(`[name="${cssEsc(hash)}"]`);
      if (!el) return;
      scrollToEl(el);
      history.replaceState({}, '', '#' + hash);
    }

    detectVolume() {
      const current = normalizePath(location.pathname);
      const currentNoDocs = withoutDocs(current);
      for (const col of win.LIBRARY_CONFIG || []) {
        for (const group of col.groups || []) {
          for (const item of group.items || []) {
            const itemPath = normalizePath(item.path);
            if (!/\/index\.html$/i.test(itemPath)) continue;
            const dir = itemPath.replace(/\/index\.html$/i, '');
            const dirNoDocs = withoutDocs(dir);
            if (current === itemPath || current.startsWith(dir + '/') || currentNoDocs.startsWith(dirNoDocs + '/')) {
              return { col, group, item, dir };
            }
          }
        }
      }
      return null;
    }

    async renderEpubMenu() {
      const data = await this.fetchVolumeData(this.currentVol.dir);
      if (!data) {
        this.mode = innerWidth < 997 ? 'page-toc' : 'libmap';
        this.mode === 'page-toc' ? this.renderPageTocMenu() : this.renderLibmapMenu();
        return;
      }
      this.currentVol.data = data;
      const { col, item } = this.currentVol;
      this.navTree.innerHTML =
        this.renderBreadcrumb([
          { text: col.label, href: this.sitePath(col.path), expand: col.id },
          { text: item.label || item.title || data.title || 'Contents', href: this.sitePath(item.path || (this.currentVol.dir + '/index.html')) }
        ]) +
        this.renderSidebarTree(buildHeadingTree(data.headings || []), 'epub-toc') +
        '<div class="section-divider"><span>All works</span></div>' +
        this.buildLibmapHtml();
    }

    renderPageTocMenu() {
      const headings = getDomHeadings($('#content'));
      if (headings.length <= 1) {
        this.mode = 'libmap';
        this.renderLibmapMenu();
        return;
      }
      const col = this.findCollectionByPath();
      const nodes = headings.map(h => ({ level: Number(h.tagName[1]) || 2, text: h.textContent.trim(), id: h.id, file: location.pathname.split('/').pop() }));
      this.navTree.innerHTML =
        this.renderBreadcrumb([
          { text: col?.label || 'Library', href: col?.path ? this.sitePath(col.path) : '#', expand: col?.id },
          { text: nodes[0]?.text || doc.title }
        ]) +
        this.renderSidebarTree(buildHeadingTree(nodes), 'page-toc') +
        '<div class="section-divider"><span>All works</span></div>' +
        this.buildLibmapHtml();
    }

    renderLibmapMenu() {
      this.navTree.innerHTML = this.buildLibmapHtml();
    }

    async fetchVolumeData(dir) {
      const cleanDir = normalizePath(dir);
      if (this.volCache.has(cleanDir)) return this.volCache.get(cleanDir);
      const raw = await this.importVolumeData(cleanDir);
      const data = this.normalizeVolumeData(raw, cleanDir);
      if (data) this.volCache.set(cleanDir, data);
      return data;
    }

    async importVolumeData(cleanDir) {
      const urls = [];
      const meta = win.__PAGE_META__ || {};
      if (meta.indexJsPath) urls.push(new URL(meta.indexJsPath, location.href).href);
      urls.push(new URL(this.sitePath(cleanDir + '/index.js'), location.href).href);
      for (const url of [...new Set(urls)]) {
        try {
          const mod = await import(url);
          if (mod?.default) return mod.default;
        } catch { }
      }
      return null;
    }

    normalizeVolumeData(raw, dir) {
      if (!raw) return null;
      if (!Array.isArray(raw) && raw.version === 1) return raw;
      if (!Array.isArray(raw)) return null;
      const headings = [];
      raw.forEach(file => (file.headings || []).forEach(h => headings.push({
        level: h.level || 2,
        text: h.text || '',
        id: h.id || null,
        file: h.filename || file.file || file.path || ''
      })));
      return { version: 1, title: this.currentVol?.item?.label || dir, files: raw, headings };
    }

    renderBreadcrumb(parts) {
      return '<div class="breadcrumb" aria-label="Breadcrumb">' + parts.map((part, i) => {
        const sep = i ? '<span class="breadcrumb__sep">/</span>' : '';
        if (part.href) return sep + `<a href="${esc(part.href)}"${part.expand ? ` data-expand-section="${esc(part.expand)}"` : ''}>${esc(part.text)}</a>`;
        return sep + `<span>${esc(part.text || '')}</span>`;
      }).join('') + '</div>';
    }

    renderSidebarTree(nodes, className) {
      return `<ul class="sidebar-menu ${esc(className)}">${this.renderSidebarNodes(nodes)}</ul>`;
    }

    renderSidebarNodes(nodes) {
      const currentFile = location.pathname.split('/').pop().replace(/\.html$/i, '');
      return nodes.map(node => {
        const rawFile = node.file || '';
        const fullFile = rawFile && this.mode !== 'page-toc' ? normalizePath((this.currentVol.dir + '/' + rawFile).replace(/\/+/g, '/')) : rawFile;
        const file = rawFile.replace(/\.html$/i, '');
        const sameFile = this.mode === 'page-toc' || file === currentFile || !rawFile;
        const href = this.mode === 'page-toc'
          ? (node.id ? '#' + esc(node.id) : '#')
          : sameFile
            ? (node.id ? '#' + esc(node.id) : this.sitePath(fullFile || rawFile))
            : (node.id ? this.sitePath(fullFile) + '#' + esc(node.id) : this.sitePath(fullFile));
        const children = node.children?.length ? `<ul class="sidebar-menu sidebar-menu--nested">${this.renderSidebarNodes(node.children)}</ul>` : '';
        const caret = children ? '<button class="sidebar-caret" tabindex="0" aria-label="Expand">\u25b8</button>' : '';
        const link = `<a href="${href}" data-file="${esc(rawFile)}" data-id="${esc(node.id || '')}" class="sidebar-link">${esc(node.text)}</a>`;
        return children
          ? `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-collapsed="true"><div class="sidebar-item-row">${link}${caret}</div>${children}</li>`
          : `<li class="sidebar-item">${link}</li>`;
      }).join('');
    }

    buildLibmapHtml() {
      if (!win.LIBRARY_CONFIG?.length) return '<div class="sidebar-menu" style="padding:20px">Navigation unavailable</div>';
      return '<ul class="sidebar-menu">' + win.LIBRARY_CONFIG.map(col => this.renderSection(col)).join('') + '</ul>';
    }

    renderSection(col) {
      const label = esc(col.label || col.title || col.id || '');
      const badge = col.badge ? ` <span class="sidebar-badge">${esc(col.badge)}</span>` : '';
      if (!col.groups?.length && col.path) {
        const external = /^https?:/i.test(col.path);
        return `<li class="sidebar-item"><a href="${external ? esc(col.path) : this.sitePath(col.path)}" class="sidebar-link"${external ? ' target="_blank" rel="noopener"' : ` data-path="${esc('/' + normalizePath(col.path))}"`}>${label}${badge}</a></li>`;
      }
      if (col.groups?.length) {
        return `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-section="${esc(col.id)}" data-collapsed="true"><div class="sidebar-item-row"><span class="sidebar-category-label">${label}${badge}</span><button class="sidebar-caret" tabindex="0">\u25b8</button></div></li>`;
      }
      return `<li class="sidebar-item"><span class="sidebar-category-label">${label}${badge}</span></li>`;
    }

    renderGroup(group) {
      const label = esc(group.label || '');
      const items = group.items || [];
      if (!items.length) {
        const external = /^https?:/i.test(group.path || '');
        const path = normalizePath(group.path);
        return `<li class="sidebar-item"><a href="${external ? esc(group.path) : this.sitePath(path)}" class="sidebar-link"${external ? ' target="_blank" rel="noopener"' : ` data-path="${esc('/' + path)}"`}>${label}</a></li>`;
      }
      return `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-collapsed="true"><div class="sidebar-item-row"><span class="sidebar-category-label">${label}</span><button class="sidebar-caret" tabindex="0">\u25b8</button></div><ul class="sidebar-menu sidebar-menu--nested">${items.map(item => {
        const external = /^https?:/i.test(item.path || '');
        const path = normalizePath(item.path);
        return `<li class="sidebar-item"><a href="${external ? esc(item.path) : this.sitePath(path)}" class="sidebar-link"${external ? ' target="_blank" rel="noopener"' : ` data-path="${esc('/' + path)}"`}>${esc(item.label || item.title || '')}</a></li>`;
      }).join('')}</ul></li>`;
    }

    sitePath(path) {
      if (!path) return '#';
      if (/^https?:/i.test(path)) return path;
      const site = (doc.body.dataset.site || '').replace(/\/$/, '');
      const clean = normalizePath(path);
      return site ? `${site}/${clean}` : '/' + clean;
    }

    getPageHeadings() {
      if (this.mode === 'epub') {
        const currentFile = location.pathname.split('/').pop().replace(/\.html$/i, '');
        const domHeadings = getDomHeadings($('#content'));
        let domIndex = 0;
        return (this.currentVol?.data?.headings || []).filter(h => (h.file || '').replace(/\.html$/i, '') === currentFile).map(h => {
          const id = h.id || domHeadings[domIndex++]?.id || null;
          return { level: h.level || 2, text: h.text || '', id };
        }).filter(h => h.id);
      }
      return getDomHeadings($('#content')).map(h => ({ level: Number(h.tagName[1]) || 2, text: h.textContent.trim(), id: h.id }));
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
        this.tracker = new HeadingTracker({
          getHeadings: () => getDomHeadings(content),
          onChange: id => this.updateTracking(id)
        });
        return this.tracker.start();
      };
      if (!content || start()) return;
      this.waitObserver = new MutationObserver((_, observer) => {
        if (start()) observer.disconnect();
      });
      this.waitObserver.observe(content, { subtree: true, attributes: true, attributeFilter: ['id'] });
    }

    updateTracking(id) {
      this.activeHeadingId = id;
      this.updateSidebarTracking(id);
      this.updateTocTracking(id);
      this.syncSidebar(id);
    }

    getSidebarLinks() {
      const tree = this.navTree.querySelector('.sidebar-menu');
      if (!tree) return [];
      if (!this.linkCache || this.linkCache.tree !== tree) this.linkCache = { tree, links: $$('.sidebar-link', tree) };
      return this.linkCache.links;
    }

    updateSidebarTracking(id) {
      const links = this.getSidebarLinks();
      if (!links.length) return;
      this.activeSidebarLink?.classList.remove('sidebar-link--active');
      this.activeSidebarLink = null;
      const currentFile = location.pathname.split('/').pop().replace(/\.html$/i, '');
      const sameFile = link => (link.dataset.file || '').replace(/\.html$/i, '') === currentFile;
      const match = (id && links.find(link => sameFile(link) && link.dataset.id === id))
        || links.find(link => sameFile(link) && !link.dataset.id)
        || links.find(sameFile);
      if (!match) return;
      match.classList.add('sidebar-link--active');
      this.activeSidebarLink = match;
      expandTo(match, this.navTree.querySelector('.sidebar-menu'));
    }

    updateTocTracking(id) {
      const nav = $('#toc-desktop-nav');
      this.activeTocLink?.classList.remove('theme-doc-toc-desktop-link__a--active');
      this.activeTocLink = null;
      if (!nav || !id) return;
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

    highlightCurrent() {
      const tree = this.navTree.querySelector('.sidebar-menu');
      if (!tree) return;
      if (this.mode === 'libmap') {
        const current = normalizePath(location.pathname);
        const match = $$('a[data-path]', tree).find(a => {
          const path = normalizePath(a.dataset.path);
          return path === current || withoutDocs(path) === withoutDocs(current);
        });
        if (match) {
          match.classList.add('sidebar-link--active');
          this.activeSidebarLink = match;
          expandTo(match, tree);
        }
        return;
      }
      const file = location.pathname.split('/').pop().replace(/\.html$/i, '');
      const hash = location.hash.slice(1);
      let best = null;
      let score = 0;
      $$('.sidebar-link', tree).forEach(link => {
        const linkFile = (link.dataset.file || '').replace(/\.html$/i, '');
        const id = link.dataset.id || '';
        let s = 0;
        if (linkFile === file) {
          s = 1;
          if (id && hash && id === hash) s = 3;
          else if (!id && !hash) s = 2;
        }
        if (s > score) { score = s; best = link; }
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
      this.fadeObserver = new IntersectionObserver(entries => {
        entries.forEach(entry => bc.classList.toggle('breadcrumb--faded', entry.boundingClientRect.bottom < entry.rootBounds.top));
      }, { root: this.navTree, threshold: 0 });
      this.fadeObserver.observe(menu);
    }

    initSourceToc() {
      const toc = $('.doc-toc');
      if (!toc) return;
      toc.addEventListener('click', e => {
        const caret = e.target.closest('.toc-caret');
        if (!caret) return;
        const item = caret.closest('.toc-item--collapsible');
        if (!item) return;
        e.preventDefault();
        e.stopPropagation();
        const collapsed = item.getAttribute('data-collapsed') !== 'false';
        item.setAttribute('data-collapsed', collapsed ? 'false' : 'true');
        caret.textContent = collapsed ? '\u25be' : '\u25b8';
      });
    }

    findCollectionByPath() {
      const path = normalizePath(location.pathname);
      return (win.LIBRARY_CONFIG || []).find(col => {
        const base = normalizePath(col.basePath || col.basepath || '');
        return base && (path.startsWith(base) || withoutDocs(path).startsWith(withoutDocs(base)));
      }) || null;
    }

    toggle() { this.sidebar?.classList.contains('doc-sidebar--open') ? this.close() : this.open(); }
    open() {
      if (innerWidth >= 997) return;
      this.sidebar?.classList.add('doc-sidebar--open');
      this.backdrop?.classList.add('sidebar-overlay--visible');
      this.lastSyncedId = null;
      this.syncSidebar(this.activeHeadingId);
    }
    close() {
      if (innerWidth >= 997) return;
      this.sidebar?.classList.remove('doc-sidebar--open');
      this.backdrop?.classList.remove('sidebar-overlay--visible');
    }

    async loadLibmap() {
      const script = doc.querySelector('script[src*="/assets/libmap.js"]');
      if (script) {
        await new Promise(resolve => setTimeout(resolve, 50));
        if (win.LIBRARY_CONFIG) return;
      }
      const res = await fetch(`${doc.body.dataset.site || ''}/assets/libmap.js`);
      if (res.ok) new Function(await res.text())();
    }
  }

  class NavigationManager {
    init() {
      const meta = win.__PAGE_META__ || {};
      ['prev', 'next'].forEach(kind => {
        const btn = $('#' + kind + '-btn');
        const data = meta[kind];
        if (!btn || !data) return;
        const label = $('.pagination-link__label', btn);
        if (label && data.title) label.textContent = data.title;
        if (data.file) btn.href = data.file.startsWith('/') ? data.file : location.pathname.replace(/[^/]*$/, '') + data.file;
      });
    }
  }

  const menu = new MenuManager();
  const nav = new NavigationManager();
  win.__NAV__ = { menu, nav };
  const init = () => { menu.init(); nav.init(); };
  doc.readyState === 'loading' ? doc.addEventListener('DOMContentLoaded', init) : init();
})();
