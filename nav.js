(function () {
  'use strict';
  const $ = s => document.querySelector(s);
  const esc = t => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const resolveUrl = href => { try { return new URL(href, location.href).href; } catch { return location.pathname.replace(/[^/]*$/, '') + href; } };

  // ── MenuManager ─────────────────────────────────────────────────
  class MenuManager {
    constructor() {
      this.sidebar = null;
      this.navTree = null;
      this.backdrop = null;
      this.menuLoaded = false;
      this._volCache = new Map();
      this._mode = 'libmap';
      this._currentVol = null;
      this._activeHeadingId = null;
    }

    async init() {
      this.sidebar = $('#lsidebar');
      this.backdrop = $('#sidebar-backdrop');
      this.navTree = $('#nav-tree');
      if (!this.sidebar || !this.navTree) return;

      this._bindSidebarToggle();
      if (!window.LIBRARY_CONFIG?.length) {
        try { await this._loadLibmapConfig(); } catch (e) { console.error('[Menu]', e); }
      }

      this._currentVol = this._detectVolume();
      if (this._currentVol) {
        this._mode = 'epub';
        await this._renderEpubMenu();
      } else {
        this._mode = 'libmap';
        await this._renderLibmapMenu();
      }
      this.menuLoaded = true;
      this._highlightCurrent();
      this._initTocRail();
      this._initScrollTracking();

      // Bind toggles & highlight for build-time rendered volume-index TOC
      const docToc = document.querySelector('.doc-toc');
      if (docToc) {
        this._initTocToggles(docToc);
        this._highlightTocCurrent(docToc);
      }
    }

    // ── Volume detection ────────────────────────────────────────
    _detectVolume() {
      const currentPath = location.pathname;
      const cfg = window.LIBRARY_CONFIG || [];
      for (const col of cfg) {
        for (const group of (col.groups || [])) {
          for (const item of (group.items || [])) {
            const p = item.path || '';
            if (!p.endsWith('/index.html')) continue;
            const dir = p.replace(/^\//, '').replace(/\/index\.html$/, '');
            if (!dir) continue;
            const curDir = currentPath.replace(/\/[^\/]+$/, '');
            if (curDir === dir || currentPath.startsWith('/' + dir + '/')) {
              return { col, group, item, dir };
            }
          }
        }
      }
      return null;
    }

    // ── EPUB Menu ────────────────────────────────────────────────
    async _renderEpubMenu() {
      const { col, group, item, dir } = this._currentVol;
      const site = document.body.dataset.site || '';
      const volJs = '/' + dir + '/index.js';
      const data = await this._fetchVolData(resolveUrl(volJs));
      if (!data) {
        this._renderLibmapMenu();
        return;
      }
      this._currentVol.data = data;

      let html = '';
      html += `<div class="breadcrumb" aria-label="Breadcrumb">`;
      if (col.path && !col.path.startsWith('http')) {
        const href = site ? `${site}/${col.path.replace(/^\//, '')}` : col.path;
        html += `<a href="${esc(href)}">${esc(col.label)}</a>`;
      } else {
        html += `<span>${esc(col.label)}</span>`;
      }
      const volTitle = item.label || item.title || data.title || 'Contents';
      const volHref = item.path || ('/' + dir + '/index.html');
      const volLink = site ? `${site}/${volHref.replace(/^\//, '')}` : volHref;
      html += `<span class="breadcrumb__sep">/</span>`;
      html += `<a href="${esc(volLink)}">${esc(volTitle)}</a>`;
      html += `</div>`;

      const headings = data.headings || [];
      if (headings.length) {
        html += this._renderSidebarTree(this._buildHeadingTree(headings), 'epub-toc');
      }

      html += `<div class="section-divider"><span>Other Works</span></div>`;
      html += `<ul class="sidebar-menu related-toc">${this._renderLazySections(col.id)}</ul>`;

      this.navTree.innerHTML = html;
      this._initSidebarToggles(this.navTree);
      this._initLazySections();
      this._initBreadcrumbFade();
    }

    _initBreadcrumbFade() {
      const bc = this.navTree?.querySelector('.breadcrumb');
      const tocMenu = this.navTree?.querySelector('.sidebar-menu');
      if (!bc || !tocMenu || !this.navTree) return;

      // Fade the breadcrumb only when the entire first sidebar-menu
      // (the epub TOC) has scrolled out of the nav viewport.
      const io = new IntersectionObserver((entries) => {
        entries.forEach(e => {
          bc.classList.toggle('breadcrumb--faded', !e.isIntersecting);
        });
      }, { root: this.navTree, threshold: 0 });

      io.observe(tocMenu);
    }
    _getDomHeadings() {
      const content = $('#content');
      if (!content) return [];
      return Array.from(content.querySelectorAll('h1, h2, h3, h4, h5, h6')).filter(h => h.id);
    }

    _getActiveHeadingId(headings, threshold = 200) {
      if (!headings?.length) return null;
      for (let i = headings.length - 1; i >= 0; i--) {
        if (headings[i].getBoundingClientRect().top <= threshold) {
          return headings[i].id;
        }
      }
      return headings[0].id;
    }

    _getEpubHeadings() {
      if (!this._currentVol?.data?.headings) return [];
      const currentFile = location.pathname.split('/').pop().replace(/\.html$/i, '');
      return this._currentVol.data.headings.filter(h => {
        const hFile = (h.file || '').replace(/\.html$/i, '');
        return hFile === currentFile && h.id;
      });
    }

    // Unified heading source: JSON provides text/level, DOM provides id.
    // For headings whose JSON id is null, we borrow the id from the
    // corresponding DOM heading (matched by order). Both arrays follow
    // the same document order and skip logic, so index pairing is safe.
    _getPageHeadings() {
      if (this._mode !== 'epub') {
        return this._getDomHeadings().map(h => ({
          level: parseInt(h.tagName[1]),
          text: h.textContent.trim(),
          id: h.id
        }));
      }

      const currentFile = location.pathname.split('/').pop().replace(/\.html$/i, '');
      const jsonHeadings = (this._currentVol?.data?.headings || []).filter(h => {
        const hFile = (h.file || '').replace(/\.html$/i, '');
        return hFile === currentFile;
      });

      // Use raw DOM headings (including those without id) so that a missing
      // id in the middle of the page doesn't throw off the pairing index.
      const content = $('#content');
      const domHeadingsAll = content ? Array.from(content.querySelectorAll('h1, h2, h3, h4, h5, h6')) : [];
      let domIdx = 0;

      return jsonHeadings.map((jh) => {
        let id = jh.id;
        if (!id && domIdx < domHeadingsAll.length) {
          id = domHeadingsAll[domIdx].id || null;
        }
        domIdx++;
        return { level: jh.level, text: jh.text, id };
      }).filter(h => h.id);
    }

    _renderTocTree(nodes) {
      if (!nodes.length) return '';
      return '<ul class="theme-doc-toc-desktop-list">' + nodes.map(n => {
        const cls = 'theme-doc-toc-desktop-link theme-doc-toc-desktop-link--lvl' + n.level;
        const children = this._renderTocTree(n.children);
        return `<li class="${cls}"><a href="#${n.id}" class="theme-doc-toc-desktop-link__a">${esc(n.text)}</a>${children}</li>`;
      }).join('') + '</ul>';
    }

    // ── Unified scroll tracking (single listener drives both rails) ──
    _initScrollTracking() {
      if (this._scrollTrackingReady) return;
      const content = $('#content');
      if (!content) return;

      let headings = this._getDomHeadings();
      if (!headings.length) {
        const mo = new MutationObserver((mutations, observer) => {
          if (this._getDomHeadings().length) {
            observer.disconnect();
            this._initScrollTracking();
          }
        });
        mo.observe(content, { subtree: true, attributes: true, attributeFilter: ['id'] });
        return;
      }

      this._scrollTrackingReady = true;
      let lastId = null;
      const onScroll = () => {
        const activeId = this._getActiveHeadingId(headings, 200);
        if (activeId !== lastId) {
          lastId = activeId;
          this._activeHeadingId = activeId;
          this._updateNavTracking(activeId);   // highlight both rails
          this._syncNavScroll(activeId);         // scroll the visible rail into view
        }
      };

      window.addEventListener('scroll', onScroll, { passive: true });
      requestAnimationFrame(() => {
        onScroll();
        this._syncNavScroll(lastId);
      });
    }


    // ── Desktop TOC Rail ("On this page") ───────────────────────
    _initTocRail() {
      const nav = document.getElementById('toc-desktop-nav');
      if (!nav) return;

      // Reset on every call so page switches always rebuild
      nav.innerHTML = '';

      const headings = this._getPageHeadings();
      if (!headings.length) {
        const content = $('#content');
        if (content) {
          const mo = new MutationObserver((mutations, observer) => {
            if (this._getPageHeadings().length) {
              observer.disconnect();
              this._initTocRail();
            }
          });
          mo.observe(content, { subtree: true, attributes: true, attributeFilter: ['id'] });
        }
        return;
      }

      nav.innerHTML = this._renderTocTree(this._buildHeadingTree(headings));

      // If scroll tracking is already running, highlight & scroll current position immediately
      if (this._scrollTrackingReady) {
        const activeId = this._getActiveHeadingId(this._getDomHeadings(), 200);
        if (activeId) {
          this._updateNavTracking(activeId);
          this._syncNavScroll(activeId);
        }
      }
    }

    // Build nested heading tree from flat array (shared by sidebar + TOC rail)
    _buildHeadingTree(headings) {
      const root = { level: 0, children: [] };
      const stack = [root];
      for (const h of headings) {
        const node = { ...h, children: [] };
        while (stack.length > 1 && stack[stack.length - 1].level >= h.level) stack.pop();
        stack[stack.length - 1].children.push(node);
        stack.push(node);
      }
      return root.children;
    }

    _renderSidebarTree(nodes, clsPrefix) {
      const currentFile = location.pathname.split('/').pop().replace(/\.html$/i, '');
      return `<ul class="sidebar-menu ${clsPrefix}">${this._renderSidebarNodes(nodes, currentFile)}</ul>`;
    }

    _renderSidebarNodes(nodes, currentFile) {
      return nodes.map(n => {
        const href = n.id ? `${esc(n.file || '')}#${esc(n.id)}` : esc(n.file || '');
        const isCurrentFile = n.file === currentFile;
        const hasChildren = n.children.length > 0;
        const childHtml = hasChildren
          ? `<ul class="sidebar-menu sidebar-menu--nested">${this._renderSidebarNodes(n.children, currentFile)}</ul>`
          : '';
        const active = isCurrentFile && (
          (this._activeHeadingId && n.id === this._activeHeadingId) ||
          (!this._activeHeadingId && !n.id)
        ) ? ' sidebar-link--active' : '';
        const caretHtml = hasChildren
          ? `<button class="sidebar-caret" type="button" aria-label="Expand section" tabindex="0">\u25b8</button>`
          : '';

        const linkContent = `<a href="${href}" data-file="${esc(n.file || '')}" data-id="${esc(n.id || '')}" class="sidebar-link${active}">${esc(n.text)}</a>`;

        if (hasChildren) {
          return `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-collapsed="true">
  <div class="sidebar-item-row">
    ${linkContent}
    ${caretHtml}
  </div>
  ${childHtml}
</li>`;
        } else {
          return `<li class="sidebar-item">
  ${linkContent}
</li>`;
        }
      }).join('');
    }

    _initSidebarToggles(container) {
      if (!container) return;
      container.querySelectorAll('.sidebar-item--collapsible').forEach(li => {
        // 改：不限定直接子元素，全局查找
        const caret = li.querySelector('.sidebar-caret');
        const nested = li.querySelector(':scope > ul, :scope > ol'); // :scope > 依然有效，因为 ul 是 li 的直接子元素
        if (!nested || !caret) return;

        const toggleFn = (e) => {
          if (e) { e.preventDefault(); e.stopPropagation(); }
          const isCollapsed = li.getAttribute('data-collapsed') !== 'false';
          li.setAttribute('data-collapsed', isCollapsed ? 'false' : 'true');
          caret.textContent = isCollapsed ? '\u25be' : '\u25b8';
        };
        caret.addEventListener('click', toggleFn);
        caret.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleFn(); }
        });
      });
    }

    // ── Unified scroll sync (mobile sidebar only; desktop TOC never auto-scrolls) ──
    _syncNavScroll(activeId) {
      // Desktop: TOC rail never auto-scrolls — stays completely static
      if (innerWidth >= 997) return;
      // Mobile: scroll sidebar into view when menu opens
      if (!this.navTree) return;
      const active = this.navTree.querySelector('.sidebar-link.sidebar-link--active');
      if (!active) return;
      this._expandTo(active, this.navTree.querySelector('.sidebar-menu'));
      requestAnimationFrame(() => active.scrollIntoView({ block: 'center', behavior: 'smooth' }));
    }

    // Desktop TOC rail: scroll the active item into the center of the rail viewport

    // ── Unified nav tracking (single entry for both sidebar & TOC rail) ──
    _updateNavTracking(id) {
      this._updateSidebarTracking(id);
      this._updateTocRailTracking(id);
    }

    _updateSidebarTracking(id) {
      if (!this.navTree) return;
      const tree = this.navTree.querySelector('.sidebar-menu');
      if (!tree) return;
      tree.querySelectorAll('.sidebar-link').forEach(a => a.classList.remove('sidebar-link--active'));

      const rawFile = location.pathname.split('/').pop();
      const currentFile = rawFile ? rawFile.replace(/\.html$/i, '') : 'index';

      // Desktop: always highlight the shallowest (first) heading for this file
      if (innerWidth >= 997) {
        const fileLinks = [...tree.querySelectorAll('.sidebar-link')].filter(a => {
          const f = (a.dataset.file || '').replace(/\.html$/i, '');
          return f === currentFile;
        });
        if (fileLinks.length) {
          fileLinks[0].classList.add('sidebar-link--active');
          this._expandTo(fileLinks[0], tree);
        }
        return;
      }

      // Mobile: track by heading id
      const fallbackToFile = () => {
        const fileLink = [...tree.querySelectorAll('.sidebar-link')].find(a => {
          const f = (a.dataset.file || '').replace(/\.html$/i, '');
          const hid = a.dataset.id || '';
          return f === currentFile && !hid;
        });
        if (fileLink) {
          fileLink.classList.add('sidebar-link--active');
          this._expandTo(fileLink, tree);
          return;
        }
        const candidates = [...tree.querySelectorAll('.sidebar-link')].filter(a => {
          return (a.dataset.file || '').replace(/\.html$/i, '') === currentFile && a.dataset.id;
        });
        if (candidates.length) {
          const deepest = candidates[candidates.length - 1];
          deepest.classList.add('sidebar-link--active');
          this._expandTo(deepest, tree);
        }
      };

      if (!id) { fallbackToFile(); return; }

      let match = tree.querySelector(`.sidebar-link[data-id="${id}"]`);
      if (!match) { fallbackToFile(); return; }

      match.classList.add('sidebar-link--active');
      this._expandTo(match, tree);
    }

    _updateTocRailTracking(id) {
      const nav = document.getElementById('toc-desktop-nav');
      if (!nav || !nav.innerHTML) return;
      nav.querySelectorAll('.theme-doc-toc-desktop-link__a').forEach(a => {
        a.classList.remove('theme-doc-toc-desktop-link__a--active');
      });
      if (!id) return;
      const match = nav.querySelector(`a[href="#${id}"]`);
      if (match) match.classList.add('theme-doc-toc-desktop-link__a--active');
    }

    _expandTo(el, container) {
      let parent = el.closest('li');
      while (parent && container.contains(parent)) {
        if (parent.classList.contains('sidebar-item--collapsible')) {
          parent.setAttribute('data-collapsed', 'false');
          const caret = parent.querySelector('.sidebar-caret');
          if (caret) caret.textContent = '\u25be';
        }
        parent = parent.parentElement?.closest('.sidebar-item');
      }
    }

    // ── Libmap Menu (lazy) ──────────────────────────────────────
    async _renderLibmapMenu() {
      if (!window.LIBRARY_CONFIG?.length) {
        this.navTree.innerHTML = '<div style="padding:20px;color:var(--text-3);font-size:13px">Navigation unavailable</div>';
        return;
      }
      this.navTree.innerHTML = `<ul class="sidebar-menu">${this._renderLazySections()}</ul>`;
      this._initLazySections();
    }

    _renderLazySections(skipColId) {
      const site = document.body.dataset.site || '';
      return (window.LIBRARY_CONFIG || []).map(col => {
        if (col.id === skipColId) return '';
        const id = esc(col.id || '');
        const label = esc(col.label || col.title || col.id || '');
        const badge = col.badge ? ` <span class="sidebar-badge">${esc(col.badge)}</span>` : '';
        const hasGroups = (col.groups || []).length > 0;

        if (!hasGroups && col.path) {
          const ext = col.path.startsWith('http');
          const href = ext ? col.path : (site ? `${site}/${col.path.replace(/^\//, '')}` : col.path);
          return `<li class="sidebar-item">
  <a href="${esc(href)}" class="sidebar-link"${ext ? ' target="_blank" rel="noopener"' : ''}>${label}${badge}</a>
</li>`;
        }

        if (hasGroups) {
          return `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-section="${id}" data-base="${esc(col.basePath || '')}" data-collapsed="true">
  <div class="sidebar-item-row">
    <span class="sidebar-category-label">${label}${badge}</span>
    <button class="sidebar-caret" type="button" aria-label="Expand section" tabindex="0">\u25b8</button>
  </div>
</li>`;
        }

        return `<li class="sidebar-item">
  <span class="sidebar-category-label">${label}${badge}</span>
</li>`;
      }).join('');
    }

    _initLazySections() {
      this.navTree.querySelectorAll('.sidebar-item--collapsible[data-section]').forEach(li => {
        const header = li.querySelector('.sidebar-category-label');
        const caret = li.querySelector('.sidebar-caret');

        const toggleFn = (e) => {
          if (li.dataset.loaded) {
            // 已经加载过，仅切换折叠
            const isCollapsed = li.getAttribute('data-collapsed') !== 'false';
            li.setAttribute('data-collapsed', isCollapsed ? 'false' : 'true');
            if (caret) caret.textContent = isCollapsed ? '\u25be' : '\u25b8';
            return;
          }
          e.preventDefault();
          e.stopPropagation();
          const colId = li.dataset.section;
          const col = (window.LIBRARY_CONFIG || []).find(c => c.id === colId);
          if (!col) return;
          const site = document.body.dataset.site || '';
          const groupsHtml = (col.groups || []).map(g => this._renderGroup(g, site)).join('');
          if (groupsHtml) {
            const ul = document.createElement('ul');
            ul.className = 'sidebar-menu sidebar-menu--nested';
            ul.innerHTML = groupsHtml;
            li.appendChild(ul);
          }
          li.dataset.loaded = 'true';
          li.setAttribute('data-collapsed', 'false');
          if (caret) caret.textContent = '\u25be';
          this._bindTogglesIn(li); // 给新加载的二级分组绑定事件
        };

        if (header) header.addEventListener('click', toggleFn);
        if (caret) {
          caret.addEventListener('click', toggleFn);
          caret.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleFn(e); }
          });
        }
      });
    }

    _bindTogglesIn(container) {
      container.querySelectorAll('.sidebar-item--collapsible').forEach(li => {
        const caret = li.querySelector('.sidebar-caret');
        const header = li.querySelector('.sidebar-category-label');
        if (!caret) return;

        const toggleFn = (e) => {
          e.preventDefault();
          e.stopPropagation();
          const isCollapsed = li.getAttribute('data-collapsed') !== 'false';
          li.setAttribute('data-collapsed', isCollapsed ? 'false' : 'true');
          caret.textContent = isCollapsed ? '\u25be' : '\u25b8';
        };
        caret.addEventListener('click', toggleFn);
        caret.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleFn(e); }
        });
        if (header) header.addEventListener('click', toggleFn);
      });
    }

    _renderGroup(group, site) {
      const label = esc(group.label || '');
      const items = group.items || [];
      const groupPath = (group.path || '').replace(/^\//, '');
      if (!items.length) {
        if (!groupPath) return `<li class="sidebar-item"><span class="sidebar-category-label">${label}</span></li>`;
        const isExt = groupPath.startsWith('http');
        const href = isExt ? groupPath : (site ? `${site}/${groupPath}` : `/${groupPath}`);
        const dataPath = isExt ? '' : ` data-path="${esc('/' + groupPath)}"`;

        return `<li class="sidebar-item"><a href="${esc(href)}"${dataPath} class="sidebar-link">${label}</a></li>`;
      }
      const itemsHtml = items.map(item => {
        const rawPath = (item.path || '').replace(/^\//, '');
        const href = site ? `${site}/${rawPath}` : `/${rawPath}`;
        return `<li class="sidebar-item">
    <a href="${esc(href)}" data-path="${esc('/' + rawPath)}" class="sidebar-link">${esc(item.label || item.title || '')}</a>
</li>`;
      }).join('');
      return `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-group-path="${esc(groupPath)}" data-collapsed="true">
  <div class="sidebar-item-row">
    <span class="sidebar-category-label">${label}</span>
    <button class="sidebar-caret" type="button" aria-label="Expand section" tabindex="0">\u25b8</button>
  </div>
  <ul class="sidebar-menu sidebar-menu--nested">${itemsHtml}</ul>
</li>`;
    }

    async _fetchVolData(url) {
      if (this._volCache.has(url)) return this._volCache.get(url);
      try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const win = {};
        new Function('window', await res.text())(win);
        const data = win.VOLUME_DATA || null;
        if (data) this._volCache.set(url, data);
        return data;
      } catch (e) {
        console.warn('[Menu] Volume data fetch failed:', e);
        return null;
      }
    }

    _initTocToggles(container) {
      if (!container) return;
      container.querySelectorAll('.toc-item--collapsible').forEach(li => {
        const nested = li.querySelector(':scope > ul, :scope > ol');
        // Caret may be inside .toc-item-row (wrapped layout) or direct child (legacy)
        const caret = li.querySelector(':scope > .toc-item-row > .toc-caret')
          || li.querySelector(':scope > .toc-caret');
        if (!nested || !caret) return;

        const toggleFn = (e) => {
          if (e) { e.preventDefault(); e.stopPropagation(); }
          const isCollapsed = li.getAttribute('data-collapsed') !== 'false';
          li.setAttribute('data-collapsed', isCollapsed ? 'false' : 'true');
          caret.textContent = isCollapsed ? '\u25be' : '\u25b8';
        };
        caret.addEventListener('click', toggleFn);
        caret.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleFn(); }
        });
      });
    }

    // ── Highlight Current ─────────────────────────────────────────
    _highlightCurrent() {
      if (this._mode === 'epub') {
        this._highlightEpubCurrent();
        return;
      }
      const currentPath = location.pathname.replace(/\/$/, '');
      if (!currentPath) return;
      let found = false;
      this.navTree.querySelectorAll('a[data-path]').forEach(link => {
        if (found) return;
        let hrefPath = '';
        try { hrefPath = new URL(link.getAttribute('href'), location.origin).pathname.replace(/\/$/, ''); } catch { }
        const dataPath = (link.dataset.path || '').replace(/\/$/, '');
        if (dataPath !== currentPath && hrefPath !== currentPath) return;
        found = true;
        link.classList.add('sidebar-link--active');
        let parent = link.closest('.sidebar-item');
        while (parent) {
          if (parent.classList.contains('sidebar-item--collapsible')) {
            parent.setAttribute('data-collapsed', 'false');
            const caret = parent.querySelector('.sidebar-caret');
            if (caret) caret.textContent = '\u25be';
          }
          parent = parent.parentElement?.closest('.sidebar-item');
        }
        requestAnimationFrame(() => link.scrollIntoView({ block: 'nearest', behavior: 'smooth' }));
      });
    }

    _highlightEpubCurrent() {
      const currentFile = location.pathname.split('/').pop().replace(/\.html$/i, '');
      const currentHash = location.hash.slice(1);
      const tree = this.navTree?.querySelector('.sidebar-menu');
      if (!tree) return;

      // Desktop: highlight the shallowest (first) heading for this file
      if (innerWidth >= 997) {
        const fileLinks = [...tree.querySelectorAll('.sidebar-link')].filter(a => {
          const f = (a.dataset.file || '').replace(/\.html$/i, '');
          return f === currentFile;
        });
        if (fileLinks.length) {
          fileLinks[0].classList.add('sidebar-link--active');
          this._expandTo(fileLinks[0], tree);
          requestAnimationFrame(() => fileLinks[0].scrollIntoView({ block: 'center', behavior: 'instant' }));
        }
        return;
      }

      let best = null, bestScore = 0;
      tree.querySelectorAll('.sidebar-link').forEach(a => {
        const file = (a.dataset.file || '').replace(/\.html$/i, '');
        const id = a.dataset.id || '';
        const href = a.getAttribute('href') || '';
        let score = 0;
        if (file === currentFile) {
          score = 1;
          if (id && currentHash && id === currentHash) score = 3;
          else if (!id && !currentHash) score = 2;
        }
        if (!file && href.startsWith('#') && currentHash) {
          const h = href.slice(1);
          if (h === currentHash) score = 3;
        }
        if (score > bestScore) { bestScore = score; best = a; }
      });

      if (!best) return;
      best.classList.add('sidebar-link--active');
      this._expandTo(best, tree);
    }

    _highlightTocCurrent(container) {
      if (!container) return;
      const currentFile = location.pathname.split('/').pop();
      const currentHash = location.hash.slice(1);
      let best = null, bestScore = 0;

      container.querySelectorAll('a').forEach(a => {
        const href = a.getAttribute('href') || '';
        const hashIdx = href.indexOf('#');
        const linkFile = (hashIdx >= 0 ? href.slice(0, hashIdx) : href).split('/').pop();
        const linkHash = hashIdx >= 0 ? href.slice(hashIdx + 1) : '';
        let score = 0;
        if (linkFile === currentFile) {
          score = 1;
          if (linkHash && currentHash && linkHash === currentHash) score = 3;
          else if (linkHash && currentHash && currentHash.startsWith(linkHash)) score = 2;
          else if (!linkHash && !currentHash) score = 3;
        }
        if (!linkFile && href.startsWith('#') && currentHash) {
          const h = href.slice(1);
          if (h === currentHash) score = 3;
          else if (currentHash.startsWith(h)) score = 2;
        }
        if (score > bestScore) { bestScore = score; best = a; }
      });

      if (!best) return;
      best.classList.add('toc-link--active');
      this._expandBranchTo(best, container);
    }

    _expandBranchTo(el, container) {
      let parent = el.parentElement;
      while (parent) {
        if (parent.classList && parent.classList.contains('toc-item--collapsible')) {
          parent.setAttribute('data-collapsed', 'false');
          // Caret may be inside .toc-item-row (wrapped) or direct child (legacy)
          const caret = parent.querySelector(':scope > .toc-item-row > .toc-caret')
            || parent.querySelector(':scope > .toc-caret');
          if (caret) caret.textContent = '\u25be';
        }
        parent = parent.parentElement;
        if (parent?.classList?.contains('doc-toc')) break;
        if (parent === container) break;
      }
    }

    // ── Sidebar open/close (overlay mode) ─────────────────────────
    _bindSidebarToggle() {
      $('#sidebar-toggle')?.addEventListener('click', () => this.toggle());
      this.backdrop?.addEventListener('click', () => this.close());
      $('#sidebar-close-btn')?.addEventListener('click', () => this.close());
    }

    toggle() { this.sidebar.classList.contains('doc-sidebar--open') ? this.close() : this.open(); }

    open() {
      if (innerWidth >= 997) return;
      this.sidebar.classList.add('doc-sidebar--open');
      this.backdrop?.classList.add('sidebar-overlay--visible');
      this._syncNavScroll(this._activeHeadingId);
    }

    close() {
      if (innerWidth >= 997) return;
      this.sidebar.classList.remove('doc-sidebar--open');
      this.backdrop?.classList.remove('sidebar-overlay--visible');
    }

    async _loadLibmapConfig() {
      if (window.LIBRARY_CONFIG) return;
      const existing = document.querySelector('script[src*="/assets/libmap.js"]');
      if (existing) { await new Promise(r => setTimeout(r, 50)); if (window.LIBRARY_CONFIG) return; }
      const res = await fetch(`${document.body.dataset.site || ''}/assets/libmap.js`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      new Function(await res.text())();
    }
  }

  // ── NavigationManager (Prev/Next) ─────────────────────────────
  class NavigationManager {
    init() {
      const meta = window.__PAGE_META__ || {};
      ['prev', 'next'].forEach(dir => {
        const btn = $(`#${dir}-btn`);
        const data = meta[dir];
        if (!btn || !data) return;
        const label = btn.querySelector('.pagination-link__label');
        if (label && data.title) label.textContent = data.title;
        if (data.file) btn.href = data.file.startsWith('/') ? data.file : location.pathname.replace(/[^/]*$/, '') + data.file;
      });
    }
  }

  // ── Boot ──────────────────────────────────────────────────────
  const menu = new MenuManager();
  const nav = new NavigationManager();
  window.__NAV__ = { menu, nav };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => { menu.init(); nav.init(); });
  } else {
    menu.init();
    nav.init();
  }
})();