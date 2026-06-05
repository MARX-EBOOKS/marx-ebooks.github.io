(function () {
  'use strict';

  /* 工具函数 */
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const esc = v => String(v ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');

  const cssEsc = v => window.CSS?.escape
    ? CSS.escape(String(v))
    : String(v).replace('/["\]/g', '\\$&');

  const normPath = v => String(v || '')  // 统一路径格式：去协议、去参数、去前后斜杠
    .replace(/^https?:\/\/[^/]+/i, '')
    .replace(/[?#].*$/, '')
    .replace(/^\/+/, '')
    .replace(/\/+$/, '');

  const normDoc = v => normPath(v).replace(/\.html$/i, '');

  const sameDoc = (a, b) => {  // 比较两路径是否指向同一文档（忽略大小写和 .html）
    const l = normDoc(a), r = normDoc(b);
    return l === r || l.toLowerCase() === r.toLowerCase();
  };

  const resolveUrl = h => { try { return new URL(h, location.href).href; } catch { return h; } };

  const hasSel = () => {
    const s = document.getSelection();
    return !!(s && !s.isCollapsed && s.rangeCount);
  };

  const scrollToEl = (el, off = 80, beh = 'smooth') => {
    if (!el) return;
    window.scrollTo({ top: Math.max(0, el.getBoundingClientRect().top + scrollY - off), behavior: beh });
  };

  const syncFill = el => {
    if (!el) return;
    const min = parseFloat(el.min) || 0;
    const max = parseFloat(el.max) || 100;
    const val = parseFloat(el.value) || 0;
    el.style.setProperty('--_fill', (((val - min) / (max - min)) * 100).toFixed(2) + '%');
  };

  /* 滚动帧回调 */
  const scrollCbs = new Set();
  let scrollFrame = 0;
  window.addEventListener('scroll', () => {
    if (!scrollFrame) scrollFrame = requestAnimationFrame(() => {
      scrollFrame = 0;
      scrollCbs.forEach(fn => fn());
    });
  }, { passive: true });
  const onScrollFrame = fn => { scrollCbs.add(fn); return () => scrollCbs.delete(fn); };  // 注册/注销滚动帧回调

  /* DOM 辅助 */
  const getHeadings = c => c ? $$('h1,h2,h3,h4,h5,h6', c).filter(h => h.id) : [];  // 提取带 id 的标题

  function buildTree(items) {  // 按 heading level 构建嵌套树
    const root = { level: 0, children: [] };
    const stack = [root];
    items.forEach(it => {
      const n = { ...it, children: [] };
      while (stack.length > 1 && stack[stack.length - 1].level >= it.level) stack.pop();
      stack[stack.length - 1].children.push(n);
      stack.push(n);
    });
    return root.children;
  }

  function expandTo(el, container) {  // 沿 DOM 向上展开所有折叠的 sidebar 父项
    for (let li = el?.closest('li'); li && container.contains(li); li = li.parentElement?.closest('.sidebar-item')) {
      if (li.classList.contains('sidebar-item--collapsible')) {
        li.setAttribute('data-collapsed', 'false');
        const c = $('.sidebar-caret', li);
        if (c) c.textContent = '\u25be';
      }
    }
  }

  /* EventBag */
  class EventBag {
    constructor() { this.off = []; }
    on(target, type, handler, options) {  // 绑定事件并自动收集清理函数
      if (!target) return () => { };
      target.addEventListener(type, handler, options || false);
      const cleanup = () => target.removeEventListener(type, handler, options || false);
      this.off.push(cleanup);
      return cleanup;
    }
    clear() { while (this.off.length) this.off.pop()(); }
  }

  /* HeadingTracker */
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
      const queue = () => {
        if (!this.frame) this.frame = requestAnimationFrame(() => {
          this.frame = 0;
          this.measure();
          this.track(true);
        });
      };
      this.bag.on(window, 'resize', queue, { passive: true });
      this.bag.on(window, 'load', queue, { once: true });
      setTimeout(queue, 500);
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

    measure() { this.tops = this.headings.map(h => h.getBoundingClientRect().top + scrollY); }

    track(force) {
      if (hasSel()) return;
      const id = this.pick();
      if (force || id !== this.activeId) { this.activeId = id; this.onChange(id); }
    }

    pick() {  // 二分查找当前视口对应的最近标题
      if (!this.tops.length) return this.headings[0]?.id || null;
      const y = scrollY + this.threshold;
      let lo = 0, hi = this.tops.length - 1, best = 0;
      while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        if (this.tops[mid] <= y) { best = mid; lo = mid + 1; }
        else { hi = mid - 1; }
      }
      return this.headings[best]?.id || null;
    }
  }

  /* ReaderCore 暴露 */
  const ReaderCore = window.ReaderCore || {
    $, $$, esc, cssEsc, EventBag, HeadingTracker,
    normalizePath: normPath, normalizeDoc: normDoc, resolveUrl, hasSelection: hasSel,
    scrollToEl, syncFill, onScrollFrame, getDomHeadings: getHeadings, buildHeadingTree: buildTree, expandTo
  };
  Object.assign(window, { ReaderCore, $, $$, esc, syncFill, onScrollFrame });

  /* MenuManager */
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
      this.suppressUntil = 0;
    }

    async init() {  // 初始化：绑定事件 → 加载 libmap → 构建菜单 → 初始化源目录
      this.sidebar = $('#lsidebar');
      this.backdrop = $('#sidebar-backdrop');
      this.navTree = $('#nav-tree');
      if (!this.sidebar || !this.navTree) return;
      this.bindEvents();
      if (!window.LIBRARY_CONFIG?.length) await this.loadLibmap();
      await this.buildMenu();
      this.initSourceToc();
    }

    bindEvents() {
      $('#sidebar-toggle')?.addEventListener('click', () => this.toggle());
      this.backdrop?.addEventListener('click', () => this.close());
      $('#sidebar-close-btn')?.addEventListener('click', () => this.close());
      window.addEventListener('resize', () => this.handleResize(), { passive: true });
      this.navTree.addEventListener('click', e => this.onTreeClick(e));
      this.navTree.addEventListener('keydown', e => {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        const t = e.target.closest('.sidebar-caret, .sidebar-category-label');
        if (!t || t.closest('a')) return;
        e.preventDefault();
        this.toggleItem(t.closest('.sidebar-item--collapsible'));
      });
    }

    async handleResize() {
      const w = innerWidth;
      const crossed = (this.lastWidth < 997 && w >= 997) || (this.lastWidth >= 997 && w < 997);
      this.lastWidth = w;
      if (crossed) { await this.buildMenu(); this.syncSidebar(this.activeHeadingId); }
    }

    async buildMenu() {  // 检测当前卷册 → 按场景渲染 epub/page-toc/libmap 菜单
      this.cleanup();
      this.currentVol = this.detectVolume();
      if (this.currentVol) {
        this.mode = 'epub';
        await this.renderEpub();
      } else if (innerWidth < 997 && getHeadings($('#content')).length > 1 && !this.isHome()) {
        this.mode = 'page-toc';
        this.renderPageToc();
      } else {
        this.mode = 'libmap';
        this.renderLibmap();
      }
      this.afterBuild();
    }

    cleanup() {  // 清理 tracker、observer、缓存等状态，防止内存泄漏
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

    afterBuild() {
      this.highlight();
      this.renderToc();
      this.startTrack();
      this.initFade();
    }

    isHome() {
      const p = location.pathname.split('/').pop().toLowerCase();
      return !p || p === 'index.html' || p === 'nav.html';
    }

    volPath() {
      const c = normPath(location.pathname);
      if (this.currentVol && c === this.currentVol.dir) return this.currentVol.dir + '/index.html';
      return c;
    }

    volDir() {
      const c = normPath(location.pathname);
      if (!this.currentVol) return false;
      const d = this.currentVol.dir, i = d + '/index.html';
      return c === d || c === i;
    }

    volFile() {
      return this.volPath().split('/').pop().replace(/\.html$/i, '') || 'index';
    }

    /* 点击处理 */
    onTreeClick(e) {
      const t = e.target.nodeType === 1 ? e.target : e.target.parentElement;
      const ex = t?.closest('a[data-expand-section]');
      if (ex) { e.preventDefault(); this.expandSection(ex.dataset.expandSection); return; }
      const toggle = t?.closest('.sidebar-caret, .sidebar-category-label');
      if (toggle && !toggle.closest('a')) {
        e.preventDefault();
        e.stopPropagation();
        this.toggleItem(toggle.closest('.sidebar-item--collapsible'));
        return;
      }
      const link = t?.closest('.sidebar-link');
      if (!link) return;
      const href = link.getAttribute('href') || '';
      if (href.startsWith('#')) { e.preventDefault(); this.scrollToHash(href.slice(1)); return; }
      try {
        const url = new URL(href, location.href);
        if (url.pathname === location.pathname && url.hash) {
          e.preventDefault();
          this.scrollToHash(url.hash.slice(1));
        } else if (sameDoc(url.pathname, location.pathname) && url.search === location.search && !url.hash) {
          e.preventDefault();
          this.scrollToTop(url);
        }
      } catch { }
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
      if (!html) return;
      const ul = document.createElement('ul');
      ul.className = 'sidebar-menu sidebar-menu--nested';
      ul.innerHTML = html;
      item.appendChild(ul);
      item.dataset.loaded = 'true';
    }

    expandSection(id) {
      const item = this.navTree.querySelector(`.sidebar-item[data-section="${cssEsc(id)}"]`);
      if (!item) return;
      if (item.getAttribute('data-collapsed') !== 'false') this.toggleItem(item);
      requestAnimationFrame(() => item.scrollIntoView({ block: 'center', behavior: 'smooth' }));
    }

    scrollToHash(hash) {
      const el = document.getElementById(hash) || document.querySelector(`[name="${cssEsc(hash)}"]`);
      if (!el) return;
      this.suppressUntil = Date.now() + 900;
      scrollToEl(el, 80, 'auto');
      this.tracker?.measure?.();
      if (this.tracker) this.tracker.activeId = hash;
      this.updateTrack(hash);
      history.replaceState({}, '', '#' + hash);
    }

    scrollToTop(url = location) {
      this.suppressUntil = Date.now() + 900;
      window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
      this.tracker?.measure?.();
      history.replaceState({}, '', location.pathname + location.search);
    }

    /* 卷册检测 */
    detectVolume() {  // 遍历 LIBRARY_CONFIG 找到当前路径所属的最深层卷册
      const cur = normPath(location.pathname), curL = cur.toLowerCase();
      const match = path => {
        if (!path || /^https?:/i.test(path)) return null;
        const p = normPath(path);
        if (!/\/index\.html$/i.test(p)) return null;
        const d = p.replace(/\/index\.html$/i, '');
        const dl = d.toLowerCase();
        return (curL === p.toLowerCase() || curL === dl || curL.startsWith(dl + '/')) ? d : null;
      };
      let best = null;
      const consider = (col, group, item, dir) => {
        if (dir && (!best || dir.length > best.dir.length)) best = { col, group, item, dir };
      };
      for (const col of window.LIBRARY_CONFIG || []) {
        consider(col, null, col, match(col.path));
        for (const g of col.groups || []) {
          consider(col, g, g, match(g.path));
          for (const it of g.items || []) consider(col, g, it, match(it.path));
        }
      }
      return best;
    }

    /* 菜单渲染 */
    async renderEpub() {  // 加载卷册数据并渲染面包屑 + 章节树 + 总目录
      const data = await this.fetchVolData(this.currentVol.dir);
      if (!data) {
        if (this.volDir()) { this.mode = 'libmap'; this.renderLibmap(); return; }
        this.mode = innerWidth < 997 ? 'page-toc' : 'libmap';
        this.mode === 'page-toc' ? this.renderPageToc() : this.renderLibmap();
        return;
      }
      this.currentVol.data = data;
      const { col, item } = this.currentVol;
      const parts = [{ text: col.label, href: this.sitePath(col.path), expand: col.id }];
      if (item !== col) {
        parts.push({
          text: item.label || item.title || data.title || 'Contents',
          href: this.sitePath(item.path || (this.currentVol.dir + '/index.html'))
        });
      }
      this.navTree.innerHTML =
        this.renderBreadcrumb(parts) +
        this.renderTree(buildTree(data.headings || []), 'epub-toc') +
        '<div class="section-divider"><span>All works</span></div>' +
        this.buildLibmap();
    }

    renderPageToc() {
      const headings = getHeadings($('#content'));
      if (headings.length <= 1) { this.mode = 'libmap'; this.renderLibmap(); return; }
      const col = this.findCollection();
      const nodes = headings.map(h => ({
        level: Number(h.tagName[1]) || 2,
        text: h.textContent.trim(),
        id: h.id,
        file: location.pathname.split('/').pop()
      }));
      this.navTree.innerHTML =
        this.renderBreadcrumb([
          { text: col?.label || 'Library', href: col?.path ? this.sitePath(col.path) : '#', expand: col?.id },
          { text: nodes[0]?.text || document.title }
        ]) +
        this.renderTree(buildTree(nodes), 'page-toc') +
        '<div class="section-divider"><span>All works</span></div>' +
        this.buildLibmap();
    }

    renderLibmap() { this.navTree.innerHTML = this.buildLibmap(); }

    /* 数据加载 */
    async fetchVolData(dir) {  // 带缓存的卷册数据获取
      const d = normPath(dir);
      if (this.volCache.has(d)) return this.volCache.get(d);
      const dl = d.toLowerCase();
      if (dl !== d && this.volCache.has(dl)) return this.volCache.get(dl);
      const raw = await this.importVolData(d);
      const data = this.normalizeVolData(raw, d);
      if (data) { this.volCache.set(d, data); if (dl !== d) this.volCache.set(dl, data); }
      return data;
    }

    async importVolData(d) {  // 尝试从 index.js 或 __PAGE_META__ 路径导入卷册数据
      const urls = [], meta = window.__PAGE_META__ || {};
      if (meta.indexJsPath) urls.push(new URL(meta.indexJsPath, location.href).href);
      const dirs = [d]; const dl = d.toLowerCase(); if (dl !== d) dirs.push(dl);
      dirs.forEach(dir => urls.push(new URL(this.sitePath(dir + '/index.js'), location.href).href));
      for (const url of [...new Set(urls)]) {
        try { const m = await import(url); if (m?.default) return m.default; }
        catch { }
      }
      return null;
    }

    normalizeVolData(raw, dir) {  // 兼容旧版数组格式与新版 {version:1} 格式
      if (!raw) return null;
      if (!Array.isArray(raw) && raw.version === 1) return raw;
      if (!Array.isArray(raw)) return null;
      const headings = [];
      raw.forEach(f => (f.headings || []).forEach(h => headings.push({
        level: h.level || 2, text: h.text || '', id: h.id || null,
        file: h.filename || f.file || f.path || ''
      })));
      return { version: 1, title: this.currentVol?.item?.label || dir, files: raw, headings };
    }

    /* 渲染辅助 */
    renderBreadcrumb(parts) {
      return '<div class="breadcrumb" aria-label="Breadcrumb">' + parts.map((p, i) => {
        const sep = i ? '<span class="breadcrumb__sep">/</span>' : '';
        if (p.href) return sep + `<a href="${esc(p.href)}"${p.expand ? ` data-expand-section="${esc(p.expand)}"` : ''}>${esc(p.text)}</a>`;
        return sep + `<span>${esc(p.text || '')}</span>`;
      }).join('') + '</div>';
    }

    renderTree(nodes, cls) {
      return `<ul class="sidebar-menu ${esc(cls)}">${this.renderNodes(nodes)}</ul>`;
    }

    renderNodes(nodes) {  // 生成 sidebar 节点 HTML，处理同页锚点与跨文件链接
      const curFile = this.volFile();
      const curPath = this.sitePath(this.volPath());
      return nodes.map(n => {
        const raw = n.file || '';
        const full = raw && this.mode !== 'page-toc'
          ? normPath((this.currentVol.dir + '/' + raw).replace(/\/+/g, '/'))
          : raw;
        const file = raw.replace(/\.html$/i, '');
        const same = this.mode === 'page-toc' || !raw || sameDoc(file, curFile);
        const href = this.mode === 'page-toc'
          ? (n.id ? '#' + esc(n.id) : curPath)
          : same
            ? (n.id ? '#' + esc(n.id) : (full || raw ? this.sitePath(full || raw) : curPath))
            : (n.id ? this.sitePath(full) + '#' + esc(n.id) : this.sitePath(full));
        const children = n.children?.length ? `<ul class="sidebar-menu sidebar-menu--nested">${this.renderNodes(n.children)}</ul>` : '';
        const caret = children ? '<button class="sidebar-caret" tabindex="0" aria-label="Expand">\u25b8</button>' : '';
        const link = `<a href="${href}" data-file="${esc(raw)}" data-id="${esc(n.id || '')}" class="sidebar-link">${esc(n.text)}</a>`;
        return children
          ? `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-collapsed="true"><div class="sidebar-item-row">${link}${caret}</div>${children}</li>`
          : `<li class="sidebar-item">${link}</li>`;
      }).join('');
    }

    buildLibmap() {
      if (!window.LIBRARY_CONFIG?.length) return '<div class="sidebar-menu" style="padding:20px">Navigation unavailable</div>';
      return '<ul class="sidebar-menu">' + window.LIBRARY_CONFIG.map(c => this.renderCol(c)).join('') + '</ul>';
    }

    renderCol(col) {
      const label = esc(col.label || col.title || col.id || '');
      const badge = col.badge ? ` <span class="sidebar-badge">${esc(col.badge)}</span>` : '';
      const ext = p => /^https?:/i.test(p);
      const path = p => ext(p) ? esc(p) : this.sitePath(normPath(p));
      const attrs = p => ext(p) ? ' target="_blank" rel="noopener"' : ` data-path="${esc('/' + normPath(p))}"`;
      if (!col.groups?.length && col.path) {
        return `<li class="sidebar-item"><a href="${path(col.path)}" class="sidebar-link"${attrs(col.path)}>${label}${badge}</a></li>`;
      }
      if (col.groups?.length) {
        return `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-section="${esc(col.id)}" data-collapsed="true"><div class="sidebar-item-row"><span class="sidebar-category-label">${label}${badge}</span><button class="sidebar-caret" tabindex="0">\u25b8</button></div></li>`;
      }
      return `<li class="sidebar-item"><span class="sidebar-category-label">${label}${badge}</span></li>`;
    }

    renderGroup(g) {
      const label = esc(g.label || '');
      const items = g.items || [];
      if (!items.length) {
        const ext = /^https?:/i.test(g.path || '');
        const p = normPath(g.path);
        return `<li class="sidebar-item"><a href="${ext ? esc(g.path) : this.sitePath(p)}" class="sidebar-link"${ext ? ' target="_blank" rel="noopener"' : ` data-path="${esc('/' + p)}"`}>${label}</a></li>`;
      }
      return `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-collapsed="true"><div class="sidebar-item-row"><span class="sidebar-category-label">${label}</span><button class="sidebar-caret" tabindex="0">\u25b8</button></div><ul class="sidebar-menu sidebar-menu--nested">${items.map(it => {
        const ext = /^https?:/i.test(it.path || '');
        const p = normPath(it.path);
        return `<li class="sidebar-item"><a href="${ext ? esc(it.path) : this.sitePath(p)}" class="sidebar-link"${ext ? ' target="_blank" rel="noopener"' : ` data-path="${esc('/' + p)}"`}>${esc(it.label || it.title || '')}</a></li>`;
      }).join('')}</ul></li>`;
    }

    sitePath(p) {  // 拼接站点根路径与相对路径
      if (!p) return '#';
      if (/^https?:/i.test(p)) return p;
      const site = (document.body.dataset.site || '').replace(/\/$/, '');
      const c = normPath(p);
      return site ? `${site}/${c}` : '/' + c;
    }

    /* TOC 与跟踪 */
    pageHeadings() {  // 获取当前页标题：epub 模式从数据过滤，否则从 DOM 提取
      if (this.mode === 'epub') {
        const curFile = this.volFile();
        const dom = getHeadings($('#content'));
        let di = 0;
        return (this.currentVol?.data?.headings || [])
          .filter(h => sameDoc((h.file || '').replace(/\.html$/i, ''), curFile))
          .map(h => {
            const id = h.id || dom[di++]?.id || null;
            return { level: h.level || 2, text: h.text || '', id };
          })
          .filter(h => h.id);
      }
      return getHeadings($('#content')).map(h => ({
        level: Number(h.tagName[1]) || 2,
        text: h.textContent.trim(),
        id: h.id
      }));
    }

    renderToc() {
      const nav = $('#toc-desktop-nav');
      if (!nav) return;
      const h = this.pageHeadings();
      nav.innerHTML = h.length ? this.renderTocNodes(buildTree(h)) : '';
      this.activeTocLink = null;
    }

    renderTocNodes(nodes) {
      if (!nodes.length) return '';
      return '<ul class="theme-doc-toc-desktop-list">' + nodes.map(n =>
        `<li class="theme-doc-toc-desktop-link theme-doc-toc-desktop-link--lvl${n.level}"><a href="#${esc(n.id)}" class="theme-doc-toc-desktop-link__a">${esc(n.text)}</a>${this.renderTocNodes(n.children || [])}</li>`
      ).join('') + '</ul>';
    }

    startTrack() {  // 启动标题跟踪，正文未就绪时通过 MutationObserver 等待
      const content = $('#content');
      const start = () => {
        this.tracker = new HeadingTracker({
          getHeadings: () => getHeadings(content),
          onChange: id => this.updateTrack(id)
        });
        return this.tracker.start();
      };
      if (!content || start()) return;
      this.waitObserver = new MutationObserver((_, o) => { if (start()) o.disconnect(); });
      this.waitObserver.observe(content, { subtree: true, attributes: true, attributeFilter: ['id'] });
    }

    updateTrack(id) {  // 同步更新 sidebar 高亮、TOC 高亮、移动端滚动同步
      if (Date.now() < this.suppressUntil && id !== this.tracker?.activeId) return;
      this.activeHeadingId = id;
      this.updateSidebar(id);
      this.updateToc(id);
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

    sidebarLinks() {
      const tree = this.navTree.querySelector('.sidebar-menu');
      if (!tree) return [];
      if (!this.linkCache || this.linkCache.tree !== tree) this.linkCache = { tree, links: $$('.sidebar-link', tree) };
      return this.linkCache.links;
    }

    updateSidebar(id) {  // 在 sidebar 中定位当前文件/锚点并高亮
      if (this.mode === 'libmap') return;
      const links = this.sidebarLinks();
      if (!links.length) return;
      const curFile = this.volFile();
      const same = l => sameDoc((l.dataset.file || '').replace(/\.html$/i, ''), curFile);
      const exact = id && links.find(l => same(l) && l.dataset.id === id);
      if (exact) {
        if (!this.setActive('activeSidebarLink', exact, 'sidebar-link--active')) return;
        expandTo(exact, this.navTree.querySelector('.sidebar-menu'));
        return;
      }
      // 正文锚点存在但 sidebar 中无对应链接（index 数据未收录），保持之前的高亮
      if (id && this.activeSidebarLink && same(this.activeSidebarLink)) return;
      const match = links.find(l => same(l) && !l.dataset.id) || links.find(same);
      if (!match) return;
      if (!this.setActive('activeSidebarLink', match, 'sidebar-link--active')) return;
      expandTo(match, this.navTree.querySelector('.sidebar-menu'));
    }

    updateToc(id) {  // 在桌面 TOC 中高亮当前阅读位置
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

    syncSidebar(id) {  // 移动端：打开 sidebar 时自动滚动到高亮项
      if (innerWidth >= 997 || hasSel() || !id || id === this.lastSyncedId) return;
      if (!this.sidebar?.classList.contains('doc-sidebar--open')) return;
      const active = this.activeSidebarLink || $('.sidebar-link.sidebar-link--active', this.navTree);
      if (!active) return;
      this.lastSyncedId = id;
      requestAnimationFrame(() => active.scrollIntoView({ block: 'center', behavior: 'auto' }));
    }

    highlight() {  // 初始加载时根据 URL hash 匹配最佳 sidebar 项并高亮
      if (this.mode === 'libmap') return;
      const tree = this.navTree.querySelector('.sidebar-menu');
      if (!tree) return;
      const file = this.volFile(), hash = location.hash.slice(1);
      let best = null, score = 0;
      $$('.sidebar-link', tree).forEach(l => {
        const lf = (l.dataset.file || '').replace(/\.html$/i, ''), id = l.dataset.id || '';
        let s = 0;
        if (sameDoc(lf, file)) {
          s = 1;
          if (id && hash && id === hash) s = 3;
          else if (!id && !hash) s = 2;
        }
        if (s > score) { score = s; best = l; }
      });
      if (best) {
        best.classList.add('sidebar-link--active');
        this.activeSidebarLink = best;
        expandTo(best, tree);
      }
    }

    initFade() {  // 面包屑呼吸效果：滚动时自动淡化
      if (this.mode !== 'epub' && this.mode !== 'page-toc') return;
      const bc = $('.breadcrumb', this.navTree), menu = $('.sidebar-menu', this.navTree);
      if (!bc || !menu) return;
      this.fadeObserver = new IntersectionObserver(e => {
        e.forEach(en => bc.classList.toggle('breadcrumb--faded', en.boundingClientRect.bottom < en.rootBounds.top));
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

    findCollection() {  // 根据当前路径反向查找所属合集
      const path = normPath(location.pathname);
      const find = fn => (window.LIBRARY_CONFIG || []).find(c => {
        const b = fn(c.basePath || c.basepath || '');
        return b && path.startsWith(b);
      });
      const r = find(normPath);
      if (r) return r;
      const l = normPath(location.pathname).toLowerCase();
      return find(p => normPath(p).toLowerCase()) || null;
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

    async loadLibmap() {  // 动态加载 libmap.js 配置
      const s = document.querySelector('script[src*="/assets/libmap.js"]');
      if (s) { await new Promise(r => setTimeout(r, 50)); if (window.LIBRARY_CONFIG) return; }
      const res = await fetch(`${document.body.dataset.site || ''}/assets/libmap.js`);
      if (res.ok) new Function(await res.text())();
    }
  }

  /* NavigationManager */
  class NavigationManager {
    init() {  // 根据 __PAGE_META__ 设置上一页/下一页导航按钮
      const meta = window.__PAGE_META__ || {};
      ['prev', 'next'].forEach(k => {
        const btn = $('#' + k + '-btn'), data = meta[k];
        if (!btn || !data) return;
        const label = $('.pagination-link__label', btn);
        if (label && data.title) label.textContent = data.title;
        if (data.file) btn.href = data.file.startsWith('/') ? data.file : location.pathname.replace(/[^/]*$/, '') + data.file;
      });
    }
  }

  /* 初始化 */
  const menu = new MenuManager(), nav = new NavigationManager();
  window.__NAV__ = { menu, nav };
  const init = () => { menu.init(); nav.init(); };
  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', init) : init();
})();