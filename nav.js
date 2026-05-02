(function () {
  'use strict';
  const $ = s => document.querySelector(s);
  const esc = t => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const resolveUrl = href => { try { return new URL(href, location.href).href; } catch { return location.pathname.replace(/[^/]*$/, '') + href; } };

  class MenuManager {
    constructor() {
      this.sidebar = null;
      this.navTree = null;
      this.backdrop = null;
      this._volCache = new Map();
      this._mode = 'libmap';
      this._currentVol = null;
      this._activeHeadingId = null;
      this._lastWidth = innerWidth;
      window.addEventListener('resize', () => this._onResize());
    }

    async init() {
      this.sidebar = $('#lsidebar');
      this.backdrop = $('#sidebar-backdrop');
      this.navTree = $('#nav-tree');
      if (!this.sidebar || !this.navTree) return;
      this._bindSidebarToggle();
      if (!window.LIBRARY_CONFIG?.length) try { await this._loadLibmapConfig(); } catch (e) { }
      await this._buildMenu();
      this._initTocRail();
      this._initScrollTracking();
      const docToc = document.querySelector('.doc-toc');
      if (docToc) {
        this._initTocToggles(docToc);
        this._highlightTocCurrent(docToc);
      }
    }

    async _buildMenu() {
      this._currentVol = this._detectVolume();
      if (this._currentVol) {
        this._mode = 'epub';
        await this._renderEpubMenu();
      } else {
        const pageName = location.pathname.split('/').pop().toLowerCase();
        const isHome = pageName === 'index.html' || pageName === 'nav.html' || pageName === '';
        if (isHome) {
          this._mode = 'libmap';
          this._renderLibmapMenu();
        } else if (innerWidth < 997) {
          this._mode = 'page-toc';
          await this._renderPageTocMenu();
        } else {
          this._mode = 'libmap';
          this._renderLibmapMenu();
        }
      }
      this._highlightCurrent();
    }

    _onResize() {
      const w = innerWidth;
      if ((this._lastWidth < 997 && w >= 997) || (this._lastWidth >= 997 && w < 997)) {
        this._lastWidth = w;
        this._buildMenu().then(() => {
          if (this.sidebar.classList.contains('doc-sidebar--open')) this._syncNavScroll(this._activeHeadingId);
        });
      } else {
        this._lastWidth = w;
      }
    }

    _detectVolume() {
      const path = location.pathname;
      for (const col of (window.LIBRARY_CONFIG || [])) {
        for (const g of (col.groups || [])) {
          for (const item of (g.items || [])) {
            const p = item.path || '';
            if (!p.endsWith('/index.html')) continue;
            const dir = p.replace(/^\//, '').replace(/\/index\.html$/, '');
            if (!dir) continue;
            const curDir = path.replace(/\/[^\/]+$/, '');
            if (curDir === dir || path.startsWith('/' + dir + '/')) return { col, group: g, item, dir };
          }
        }
      }
      return null;
    }

    async _renderEpubMenu() {
      const { col, item, dir } = this._currentVol;
      const site = document.body.dataset.site || '';
      const volJs = '/' + dir + '/index.js';
      const data = await this._fetchVolData(resolveUrl(volJs));
      if (!data) {
        if (innerWidth >= 997) { this._mode = 'libmap'; this._renderLibmapMenu(); }
        else await this._renderPageTocMenu();
        return;
      }
      this._currentVol.data = data;
      const colHref = col.path && !col.path.startsWith('http') ? (site ? `${site.replace(/\/$/, '')}/${col.path.replace(/^\//, '')}` : col.path) : '#';
      const volTitle = item.label || item.title || data.title || 'Contents';
      const volHref = item.path || ('/' + dir + '/index.html');
      const volLink = site ? `${site.replace(/\/$/, '')}/${volHref.replace(/^\//, '')}` : volHref;
      const html = this._buildBreadcrumb(col.label, volTitle, colHref, volLink) +
        this._renderSidebarTree(this._buildHeadingTree(data.headings || []), 'epub-toc') +
        '<div class="section-divider"><span>Other Works</span></div>' +
        `<ul class="sidebar-menu related-toc">${this._renderLazySections(col.id)}</ul>`;
      this.navTree.innerHTML = html;
      this._initSidebarToggles(this.navTree);
      this._initLazySections();
      this._initBreadcrumbFade();
    }

    async _renderPageTocMenu() {
      this._mode = 'page-toc';
      const headings = this._getPageHeadings();
      const col = this._currentVol?.col || this._findCollectionByPath();

      if (headings.length <= 1) {
        this._renderLibmapMenu();
        return;
      }

      const pageTitle = headings[0]?.text || document.title;
      const colLabel = col?.label || col?.title || 'Library';
      const colHref = col?.path ? (col.path.startsWith('http') ? col.path : (document.body.dataset.site ? `${document.body.dataset.site.replace(/\/$/, '')}/${col.path.replace(/^\//, '')}` : col.path)) : '#';
      const breadcrumb = this._buildBreadcrumb(colLabel, pageTitle, colHref, '');

      // 本页目录树（不带“本页目录”文字）
      const pageTocHtml = this._renderSidebarTree(this._buildHeadingTree(headings), 'page-toc');

      const html = breadcrumb +
        pageTocHtml +
        (window.LIBRARY_CONFIG?.length ? '<div class="section-divider"><span>Other Works</span></div>' + `<ul class="sidebar-menu related-toc">${this._renderLazySections(col?.id)}</ul>` : '');
      this.navTree.innerHTML = html;
      this._initSidebarToggles(this.navTree);
      this._initLazySections();
      this._initBreadcrumbFade();
    }

    _buildBreadcrumb(label1, label2, href1, href2) {
      const span = l => `<span>${esc(l)}</span>`;
      const a = (l, h) => h ? `<a href="${esc(h)}">${esc(l)}</a>` : span(l);
      return `<div class="breadcrumb" aria-label="Breadcrumb">${a(label1, href1)}<span class="breadcrumb__sep">/</span>${a(label2, href2)}</div>`;
    }

    _initBreadcrumbFade() {
      const bc = this.navTree?.querySelector('.breadcrumb');
      const menu = this.navTree?.querySelector('.sidebar-menu');
      if (!bc || !menu) return;
      const io = new IntersectionObserver(entries => {
        entries.forEach(e => bc.classList.toggle('breadcrumb--faded', !e.isIntersecting));
      }, { root: this.navTree, threshold: 0 });
      io.observe(menu);
    }

    _getDomHeadings() {
      const c = $('#content');
      if (!c) return [];
      return [...c.querySelectorAll('h1,h2,h3,h4,h5,h6')].map((h, i) => { if (!h.id) h.id = 'auto-h' + i; return h; });
    }

    _getActiveHeadingId(headings, threshold = 200) {
      for (let i = headings.length - 1; i >= 0; i--) if (headings[i].getBoundingClientRect().top <= threshold) return headings[i].id;
      return headings[0]?.id || null;
    }

    _getPageHeadings() {
      if (this._mode !== 'epub') return this._getDomHeadings().map(h => ({ level: +h.tagName[1], text: h.textContent.trim(), id: h.id }));
      const curFile = location.pathname.split('/').pop().replace(/\.html$/i, '');
      const jsonH = (this._currentVol?.data?.headings || []).filter(h => (h.file || '').replace(/\.html$/i, '') === curFile);
      const domAll = [...($('#content')?.querySelectorAll('h1,h2,h3,h4,h5,h6') || [])];
      let di = 0;
      return jsonH.map(jh => {
        let id = jh.id;
        if (!id && di < domAll.length) id = domAll[di].id || null;
        di++;
        return { level: jh.level, text: jh.text, id };
      }).filter(h => h.id);
    }

    _buildHeadingTree(headings) {
      const root = { level: 0, children: [] }, stack = [root];
      headings.forEach(h => {
        const node = { ...h, children: [] };
        while (stack.length > 1 && stack[stack.length - 1].level >= h.level) stack.pop();
        stack[stack.length - 1].children.push(node);
        stack.push(node);
      });
      return root.children;
    }

    _renderSidebarTree(nodes, cls) {
      const cf = location.pathname.split('/').pop().replace(/\.html$/i, '');
      return `<ul class="sidebar-menu ${cls}">${this._renderSidebarNodes(nodes, cf)}</ul>`;
    }

    _renderSidebarNodes(nodes, cf) {
      return nodes.map(n => {
        const href = n.id ? `${esc(n.file || '')}#${esc(n.id)}` : esc(n.file || '');
        const isFile = n.file === cf, hasKids = n.children.length > 0;
        const kidsHtml = hasKids ? `<ul class="sidebar-menu sidebar-menu--nested">${this._renderSidebarNodes(n.children, cf)}</ul>` : '';
        const active = (this._mode === 'page-toc' ? (n.id && n.id === this._activeHeadingId) : (isFile && ((this._activeHeadingId && n.id === this._activeHeadingId) || (!this._activeHeadingId && !n.id)))) ? ' sidebar-link--active' : '';
        const caret = hasKids ? `<button class="sidebar-caret" tabindex="0" aria-label="Expand">\u25b8</button>` : '';
        const link = `<a href="${href}"${n.file ? ` data-file="${esc(n.file)}"` : ''}${n.id ? ` data-id="${esc(n.id)}"` : ''} class="sidebar-link${active}">${esc(n.text)}</a>`;
        return hasKids ? `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-collapsed="true"><div class="sidebar-item-row">${link}${caret}</div>${kidsHtml}</li>`
          : `<li class="sidebar-item">${link}</li>`;
      }).join('');
    }

    _initSidebarToggles(container) {
      container.querySelectorAll('.sidebar-item--collapsible').forEach(li => {
        const caret = li.querySelector('.sidebar-caret'), nested = li.querySelector(':scope > ul');
        if (!caret || !nested) return;
        const toggle = e => {
          e?.preventDefault(); e?.stopPropagation();
          const collapsed = li.getAttribute('data-collapsed') !== 'false';
          li.setAttribute('data-collapsed', collapsed ? 'false' : 'true');
          caret.textContent = collapsed ? '\u25be' : '\u25b8';
        };
        caret.addEventListener('click', toggle);
        caret.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); } });
      });
    }

    _initScrollTracking() {
      if (this._scrollTrackingReady) return;
      const c = $('#content'); if (!c) return;
      let hds = this._getDomHeadings();
      if (!hds.length) {
        const mo = new MutationObserver(() => { if (this._getDomHeadings().length) { mo.disconnect(); this._initScrollTracking(); } });
        mo.observe(c, { subtree: true, attributes: true, attributeFilter: ['id'] });
        return;
      }
      this._scrollTrackingReady = true;
      let last = null;
      window.addEventListener('scroll', () => {
        const id = this._getActiveHeadingId(hds, 200);
        if (id !== last) { last = id; this._activeHeadingId = id; this._updateNavTracking(id); this._syncNavScroll(id); }
      }, { passive: true });
      requestAnimationFrame(() => { this._updateNavTracking(last); this._syncNavScroll(last); });
    }

    _initTocRail() {
      const nav = document.getElementById('toc-desktop-nav');
      if (!nav) return;
      const hds = this._getPageHeadings();
      if (!hds.length) return;
      nav.innerHTML = this._renderTocTree(this._buildHeadingTree(hds));
      if (this._scrollTrackingReady) {
        const id = this._getActiveHeadingId(this._getDomHeadings(), 200);
        if (id) this._updateNavTracking(id);
      }
    }

    _renderTocTree(nodes) {
      if (!nodes.length) return '';
      return '<ul class="theme-doc-toc-desktop-list">' + nodes.map(n => {
        const cls = 'theme-doc-toc-desktop-link theme-doc-toc-desktop-link--lvl' + n.level;
        return `<li class="${cls}"><a href="#${n.id}" class="theme-doc-toc-desktop-link__a">${esc(n.text)}</a>${this._renderTocTree(n.children)}</li>`;
      }).join('') + '</ul>';
    }

    _syncNavScroll(id) {
      if (innerWidth >= 997 || !this.navTree) return;   // 桌面端不滚动侧边栏
      const a = this.navTree.querySelector('.sidebar-link.sidebar-link--active');
      if (!a) return;
      this._expandTo(a, this.navTree.querySelector('.sidebar-menu'));
      requestAnimationFrame(() => a.scrollIntoView({ block: 'center', behavior: 'smooth' }));
    }

    _updateNavTracking(id) {
      this._updateSidebarTracking(id);
      this._updateTocRailTracking(id);
    }

    _updateSidebarTracking(id) {
      if (!this.navTree) return;
      const tree = this.navTree.querySelector('.sidebar-menu');
      if (!tree) return;
      tree.querySelectorAll('.sidebar-link').forEach(a => a.classList.remove('sidebar-link--active'));

      if (this._mode === 'page-toc') {
        if (!id) return;
        const m = tree.querySelector(`.sidebar-link[data-id="${id}"]`);
        if (m) { m.classList.add('sidebar-link--active'); this._expandTo(m, tree); }
        return;
      }

      const curFile = location.pathname.split('/').pop().replace(/\.html$/i, '') || 'index';

      if (innerWidth >= 997) {
        // 桌面端智能高亮：判断当前文件在卷中是否为独立顶级章节
        const fileHeadings = this._getPageHeadings();
        const volHeadings = this._currentVol?.data?.headings || [];
        const fileMinLevel = Math.min(...volHeadings.filter(h => (h.file || '').replace(/\.html$/i, '') === curFile).map(h => h.level));
        const firstLevel = fileHeadings[0]?.level;
        const isTopChapter = firstLevel === fileMinLevel;   // 当前文件的第一标题层级等于该文件在卷中的最浅层级

        if (isTopChapter) {
          // 只高亮文件入口链接（不展开子目录）
          const fileLink = [...tree.querySelectorAll('.sidebar-link')].find(a => (a.dataset.file || '').replace(/\.html$/i, '') === curFile);
          if (fileLink) {
            fileLink.classList.add('sidebar-link--active');
            this._expandTo(fileLink, tree);
          }
        } else {
          // 高亮具体标题链接
          const targetId = fileHeadings[0]?.id || id;
          const match = tree.querySelector(`.sidebar-link[data-id="${targetId}"]`);
          if (match) {
            match.classList.add('sidebar-link--active');
            this._expandTo(match, tree);
          } else {
            // 回退到文件链接
            const fileLink = [...tree.querySelectorAll('.sidebar-link')].find(a => (a.dataset.file || '').replace(/\.html$/i, '') === curFile);
            if (fileLink) { fileLink.classList.add('sidebar-link--active'); this._expandTo(fileLink, tree); }
          }
        }
        return;
      }

      // 移动端的原有逻辑
      const fallback = () => {
        const f = [...tree.querySelectorAll('.sidebar-link')].find(a => (a.dataset.file || '').replace(/\.html$/i, '') === curFile && !a.dataset.id);
        if (f) { f.classList.add('sidebar-link--active'); this._expandTo(f, tree); return; }
        const cand = [...tree.querySelectorAll('.sidebar-link')].filter(a => (a.dataset.file || '').replace(/\.html$/i, '') === curFile && a.dataset.id);
        if (cand.length) { cand[cand.length - 1].classList.add('sidebar-link--active'); this._expandTo(cand[cand.length - 1], tree); }
      };

      if (!id) { fallback(); return; }
      const match = tree.querySelector(`.sidebar-link[data-id="${id}"]`);
      if (match) { match.classList.add('sidebar-link--active'); this._expandTo(match, tree); }
      else fallback();
    }

    _updateTocRailTracking(id) {
      const nav = document.getElementById('toc-desktop-nav');
      if (!nav?.innerHTML) return;
      nav.querySelectorAll('.theme-doc-toc-desktop-link__a').forEach(a => a.classList.remove('theme-doc-toc-desktop-link__a--active'));
      if (!id) return;
      const m = nav.querySelector(`a[href="#${id}"]`);
      if (m) m.classList.add('theme-doc-toc-desktop-link__a--active');
    }

    _expandTo(el, container) {
      let p = el.closest('li');
      while (p && container.contains(p)) {
        if (p.classList.contains('sidebar-item--collapsible')) {
          p.setAttribute('data-collapsed', 'false');
          const c = p.querySelector('.sidebar-caret'); if (c) c.textContent = '\u25be';
        }
        p = p.parentElement?.closest('.sidebar-item');
      }
    }

    _findCollectionByPath() {
      const path = location.pathname;
      for (const col of (window.LIBRARY_CONFIG || [])) {
        if (col.basePath) {
          const bp = ('/' + col.basePath.replace(/^\/|\/$/g, '') + '/').replace(/\/+/g, '/');
          if (path.startsWith(bp)) return col;
        }
      }
      for (const col of (window.LIBRARY_CONFIG || [])) {
        for (const g of (col.groups || [])) {
          for (const item of (g.items || [])) {
            const dir = (item.path || '').replace(/\/[^\/]*$/, '');
            if (dir && path.startsWith('/' + dir.replace(/^\//, '') + '/')) return col;
          }
        }
      }
      return null;
    }

    _renderLibmapMenu() {
      if (!window.LIBRARY_CONFIG?.length) {
        this.navTree.innerHTML = '<div class="sidebar-menu" style="padding:20px">Navigation unavailable</div>';
        return;
      }
      this.navTree.innerHTML = '<ul class="sidebar-menu">' + this._renderLazySections() + '</ul>';
      this._initLazySections();
    }

    _renderLazySections(skipColId) {
      const site = document.body.dataset.site || '';
      return (window.LIBRARY_CONFIG || []).map(col => {
        if (col.id === skipColId) return '';
        const badge = col.badge ? ` <span class="sidebar-badge">${esc(col.badge)}</span>` : '';
        if (!col.groups?.length && col.path) {
          const ext = col.path.startsWith('http');
          const href = ext ? col.path : (site ? `${site.replace(/\/$/, '')}/${col.path.replace(/^\//, '')}` : col.path);
          return `<li class="sidebar-item"><a href="${esc(href)}" class="sidebar-link"${ext ? ' target="_blank" rel="noopener"' : ''}>${esc(col.label || col.title || col.id)}${badge}</a></li>`;
        }
        if (col.groups?.length) {
          return `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-section="${esc(col.id)}" data-collapsed="true">
            <div class="sidebar-item-row"><span class="sidebar-category-label">${esc(col.label || col.title || col.id)}${badge}</span><button class="sidebar-caret" tabindex="0">\u25b8</button></div></li>`;
        }
        return `<li class="sidebar-item"><span class="sidebar-category-label">${esc(col.label || col.title || col.id)}${badge}</span></li>`;
      }).join('');
    }

    _initLazySections() {
      this.navTree.querySelectorAll('.sidebar-item--collapsible[data-section]').forEach(li => {
        const header = li.querySelector('.sidebar-category-label'), caret = li.querySelector('.sidebar-caret');
        const toggle = e => {
          if (li.dataset.loaded) {
            const coll = li.getAttribute('data-collapsed') !== 'false';
            li.setAttribute('data-collapsed', coll ? 'false' : 'true');
            if (caret) caret.textContent = coll ? '\u25be' : '\u25b8';
            return;
          }
          e.preventDefault(); e.stopPropagation();
          const col = (window.LIBRARY_CONFIG || []).find(c => c.id === li.dataset.section);
          if (!col) return;
          const site = document.body.dataset.site || '';
          const html = (col.groups || []).map(g => this._renderGroup(g, site)).join('');
          if (html) { const ul = document.createElement('ul'); ul.className = 'sidebar-menu sidebar-menu--nested'; ul.innerHTML = html; li.appendChild(ul); }
          li.dataset.loaded = 'true'; li.setAttribute('data-collapsed', 'false');
          if (caret) caret.textContent = '\u25be';
          this._bindTogglesIn(li);
        };
        if (header) header.addEventListener('click', toggle);
        if (caret) { caret.addEventListener('click', toggle); caret.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(e); } }); }
      });
    }

    _bindTogglesIn(container) {
      container.querySelectorAll('.sidebar-item--collapsible').forEach(li => {
        const caret = li.querySelector('.sidebar-caret'), header = li.querySelector('.sidebar-category-label');
        if (!caret) return;
        const toggle = e => {
          e.preventDefault(); e.stopPropagation();
          const coll = li.getAttribute('data-collapsed') !== 'false';
          li.setAttribute('data-collapsed', coll ? 'false' : 'true');
          caret.textContent = coll ? '\u25be' : '\u25b8';
        };
        caret.addEventListener('click', toggle);
        caret.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(e); } });
        if (header) header.addEventListener('click', toggle);
      });
    }

    _renderGroup(group, site) {
      const label = esc(group.label || ''), items = group.items || [], gp = (group.path || '').replace(/^\//, '');
      if (!items.length) {
        if (!gp) return `<li class="sidebar-item"><span class="sidebar-category-label">${label}</span></li>`;
        const isExt = gp.startsWith('http'), href = isExt ? gp : (site ? `${site.replace(/\/$/, '')}/${gp}` : `/${gp}`);
        return `<li class="sidebar-item"><a href="${esc(href)}" data-path="${esc('/' + gp)}" class="sidebar-link">${label}</a></li>`;
      }
      const itemsHtml = items.map(i => {
        const p = (i.path || '').replace(/^\//, ''), href = site ? `${site.replace(/\/$/, '')}/${p}` : `/${p}`;
        return `<li class="sidebar-item"><a href="${esc(href)}" data-path="${esc('/' + p)}" class="sidebar-link">${esc(i.label || i.title || '')}</a></li>`;
      }).join('');
      return `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-group-path="${esc(gp)}" data-collapsed="true">
        <div class="sidebar-item-row"><span class="sidebar-category-label">${label}</span><button class="sidebar-caret" tabindex="0">\u25b8</button></div>
        <ul class="sidebar-menu sidebar-menu--nested">${itemsHtml}</ul></li>`;
    }

    async _fetchVolData(url) {
      if (this._volCache.has(url)) return this._volCache.get(url);
      try {
        const res = await fetch(url); if (!res.ok) throw new Error();
        const win = {}; new Function('window', await res.text())(win);
        const data = win.VOLUME_DATA || null; if (data) this._volCache.set(url, data);
        return data;
      } catch { return null; }
    }

    _highlightCurrent() {
      if (this._mode === 'epub') return this._highlightEpubCurrent();
      if (this._mode === 'page-toc') return this._highlightPageTocCurrent();
      // libmap
      const cp = location.pathname.replace(/\/$/, '');
      let found = false;
      this.navTree.querySelectorAll('a[data-path]').forEach(link => {
        if (found) return;
        const dp = (link.dataset.path || '').replace(/\/$/, '');
        if (dp === cp) {
          found = true;
          link.classList.add('sidebar-link--active');
          this._expandTo(link, this.navTree.querySelector('.sidebar-menu'));
          // 桌面端自动滚动到高亮项
          if (innerWidth >= 997) {
            requestAnimationFrame(() => link.scrollIntoView({ block: 'center', behavior: 'instant' }));
          }
        }
      });
    }

    _highlightEpubCurrent() {
      const curFile = location.pathname.split('/').pop().replace(/\.html$/i, ''), hash = location.hash.slice(1);
      const tree = this.navTree?.querySelector('.sidebar-menu'); if (!tree) return;

      if (innerWidth >= 997) {
        // 桌面端智能高亮并聚焦
        const fileHeadings = this._getPageHeadings();
        const volHds = this._currentVol?.data?.headings || [];
        const fileMinLevel = Math.min(...volHds.filter(h => (h.file || '').replace(/\.html$/i, '') === curFile).map(h => h.level));
        const firstLevel = fileHeadings[0]?.level;
        const isTop = firstLevel === fileMinLevel;

        let el = null;
        if (isTop) {
          el = [...tree.querySelectorAll('.sidebar-link')].find(a => (a.dataset.file || '').replace(/\.html$/i, '') === curFile);
        } else {
          const id = fileHeadings[0]?.id || hash;
          el = tree.querySelector(`.sidebar-link[data-id="${id}"]`);
          if (!el) el = [...tree.querySelectorAll('.sidebar-link')].find(a => (a.dataset.file || '').replace(/\.html$/i, '') === curFile);
        }

        if (el) {
          el.classList.add('sidebar-link--active');
          this._expandTo(el, tree);
          requestAnimationFrame(() => el.scrollIntoView({ block: 'center', behavior: 'instant' }));
        }
        return;
      }

      // 移动端
      let best = null, bestScore = 0;
      tree.querySelectorAll('.sidebar-link').forEach(a => {
        const f = (a.dataset.file || '').replace(/\.html$/i, ''), id = a.dataset.id || '', href = a.getAttribute('href') || '';
        let score = 0;
        if (f === curFile) { score = 1; if (id && id === hash) score = 3; else if (!id && !hash) score = 2; }
        if (!f && href.startsWith('#') && hash && href.slice(1) === hash) score = 3;
        if (score > bestScore) { bestScore = score; best = a; }
      });
      if (best) { best.classList.add('sidebar-link--active'); this._expandTo(best, tree); }
    }

    _highlightPageTocCurrent() {
      const hash = location.hash.slice(1), tree = this.navTree?.querySelector('.sidebar-menu'); if (!tree) return;
      let best = hash ? tree.querySelector(`.sidebar-link[data-id="${hash}"]`) : null;
      if (!best) best = tree.querySelector('.sidebar-link');
      if (best) { best.classList.add('sidebar-link--active'); this._expandTo(best, tree); if (innerWidth < 997) requestAnimationFrame(() => best.scrollIntoView({ block: 'center', behavior: 'instant' })); }
    }

    _highlightTocCurrent(container) {
      if (!container) return;
      const cur = location.pathname.split('/').pop(), hash = location.hash.slice(1);
      let best = null, bestScore = 0;
      container.querySelectorAll('a').forEach(a => {
        const href = a.getAttribute('href') || '';
        const idx = href.indexOf('#'), f = (idx >= 0 ? href.slice(0, idx) : href).split('/').pop(), h = idx >= 0 ? href.slice(idx + 1) : '';
        let score = 0;
        if (f === cur) { score = 1; if (h && hash && h === hash) score = 3; else if (h && hash && hash.startsWith(h)) score = 2; else if (!h && !hash) score = 3; }
        if (!f && href.startsWith('#') && hash) { const hh = href.slice(1); if (hh === hash) score = 3; else if (hash.startsWith(hh)) score = 2; }
        if (score > bestScore) { bestScore = score; best = a; }
      });
      if (best) { best.classList.add('toc-link--active'); this._expandBranchTo(best, container); }
    }

    _expandBranchTo(el, container) {
      let p = el.parentElement;
      while (p) {
        if (p.classList?.contains('toc-item--collapsible')) {
          p.setAttribute('data-collapsed', 'false');
          const c = p.querySelector(':scope > .toc-item-row > .toc-caret') || p.querySelector(':scope > .toc-caret');
          if (c) c.textContent = '\u25be';
        }
        p = p.parentElement;
        if (p?.classList?.contains('doc-toc') || p === container) break;
      }
    }
    _initTocToggles(container) {
      container.querySelectorAll('.toc-item--collapsible').forEach(li => {
        const nested = li.querySelector(':scope > ul, :scope > ol'), caret = li.querySelector(':scope > .toc-item-row > .toc-caret') || li.querySelector(':scope > .toc-caret');
        if (!nested || !caret) return;
        const toggle = e => {
          e.preventDefault(); e.stopPropagation();
          const coll = li.getAttribute('data-collapsed') !== 'false';
          li.setAttribute('data-collapsed', coll ? 'false' : 'true');
          caret.textContent = coll ? '\u25be' : '\u25b8';
        };
        caret.addEventListener('click', toggle);
        caret.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); } });
      });
    }
    _bindSidebarToggle() {
      $('#sidebar-toggle')?.addEventListener('click', () => this.toggle());
      this.backdrop?.addEventListener('click', () => this.close());
      $('#sidebar-close-btn')?.addEventListener('click', () => this.close());
    }

    toggle() { this.sidebar.classList.contains('doc-sidebar--open') ? this.close() : this.open(); }
    open() { if (innerWidth < 997) { this.sidebar.classList.add('doc-sidebar--open'); this.backdrop?.classList.add('sidebar-overlay--visible'); this._syncNavScroll(this._activeHeadingId); } }
    close() { if (innerWidth < 997) { this.sidebar.classList.remove('doc-sidebar--open'); this.backdrop?.classList.remove('sidebar-overlay--visible'); } }

    async _loadLibmapConfig() {
      if (window.LIBRARY_CONFIG) return;
      const s = document.querySelector('script[src*="/assets/libmap.js"]'); if (s) { await new Promise(r => setTimeout(r, 50)); if (window.LIBRARY_CONFIG) return; }
      const res = await fetch(`${document.body.dataset.site || ''}/assets/libmap.js`); if (!res.ok) throw new Error();
      new Function(await res.text())();
    }
  }

  // NavigationManager 保持原样
  class NavigationManager {
    init() {
      const meta = window.__PAGE_META__ || {};
      ['prev', 'next'].forEach(dir => {
        const btn = $(`#${dir}-btn`), data = meta[dir];
        if (!btn || !data) return;
        const label = btn.querySelector('.pagination-link__label');
        if (label && data.title) label.textContent = data.title;
        if (data.file) btn.href = data.file.startsWith('/') ? data.file : location.pathname.replace(/[^/]*$/, '') + data.file;
      });
    }
  }

  const menu = new MenuManager(), nav = new NavigationManager();
  window.__NAV__ = { menu, nav };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => { menu.init(); nav.init(); });
  else { menu.init(); nav.init(); }
})();