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
      this._mode = 'libmap';         // 'epub' | 'libmap'
      this._currentVol = null;       // { col, group, item, dir, data }
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

      // Still render volume index page content if on a volume index page
      if (location.pathname.endsWith('/index.html')) {
        await this._renderVolumeIndex();
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

      // 1. Breadcrumb: Collection / Group
      html += `<div class="epub-breadcrumb">`;
      if (col.path && !col.path.startsWith('http')) {
        const href = site ? `${site}/${col.path.replace(/^\//, '')}` : col.path;
        html += `<a href="${esc(href)}" class="epub-crumb collection-link">${esc(col.label)}</a>`;
      } else {
        html += `<span class="epub-crumb collection-label">${esc(col.label)}</span>`;
      }
      if (group.label) {
        html += `<span class="epub-crumb-sep">/</span>`;
        if (group.path && !group.path.startsWith('http')) {
          const href = site ? `${site}/${group.path.replace(/^\//, '')}` : group.path;
          html += `<a href="${esc(href)}" class="epub-crumb group-link">${esc(group.label)}</a>`;
        } else {
          html += `<span class="epub-crumb group-label">${esc(group.label)}</span>`;
        }
      }
      html += `</div>`;

      // 2. Volume title — use libmap label for brevity
      const volTitle = item.label || item.title || data.title || 'Contents';
      html += `<div class="epub-vol-title">${esc(volTitle)}</div>`;

      // 3. Headings tree
      const headings = data.headings || [];
      if (!headings.length && data.files?.length) {
        // Fallback for old VOLUME_DATA without headings field
        const flat = [];
        for (const f of data.files) {
          if (!f.headings?.length && f.title) {
            flat.push({ level: 1, text: f.title, id: null, file: f.file || '' });
          } else {
            for (const h of (f.headings || [])) {
              flat.push({ level: h.level || 2, text: h.text || '', id: h.id || null, file: h.filename || f.file || '' });
            }
          }
        }
        html += this._buildEpubTree(flat);
      } else if (headings.length) {
        html += this._buildEpubTree(headings);
      }

      // 4. Other works (lazy libmap sections)
      html += `<div class="epub-divider"><span>Other Works</span></div>`;
      html += `<ul class="nav-menu epub-other-menu">${this._renderLazySections(col.id)}</ul>`;

      this.navTree.innerHTML = html;
      this._initEpubToggles();
      this._initLazySections();
      this._initReadingTracker();
    }

    _buildEpubTree(headings) {
      const root = { level: 0, children: [] };
      const stack = [root];
      const currentFile = location.pathname.split('/').pop();
      for (const h of headings) {
        const node = { ...h, children: [] };
        while (stack.length > 1 && stack[stack.length - 1].level >= h.level) stack.pop();
        stack[stack.length - 1].children.push(node);
        stack.push(node);
      }
      return `<ul class="epub-toc-tree">${this._renderEpubNodes(root.children, currentFile)}</ul>`;
    }

    _renderEpubNodes(nodes, currentFile) {
      return nodes.map(n => {
        const href = n.id ? `${esc(n.file || '')}#${esc(n.id)}` : esc(n.file || '');
        const isCurrentFile = n.file === currentFile;
        const hasChildren = n.children.length > 0;
        const childHtml = hasChildren ? `<ul class="epub-toc-nested">${this._renderEpubNodes(n.children, currentFile)}</ul>` : '';
        const active = isCurrentFile && n.id && n.id === this._activeHeadingId ? ' active' : '';
        return `<li class="epub-toc-item level-${n.level}${isCurrentFile ? ' current-file' : ''}">
  <a href="${href}" data-file="${esc(n.file || '')}" data-id="${esc(n.id || '')}" class="epub-toc-link${active}">${esc(n.text)}</a>
  ${childHtml}
</li>`;
      }).join('');
    }

    _initEpubToggles() {
      this.navTree.querySelectorAll('.epub-toc-item').forEach(li => {
        const nested = li.querySelector(':scope > .epub-toc-nested');
        if (!nested) return;
        li.classList.add('has-nested');
        const toggle = document.createElement('span');
        toggle.className = 'epub-toggle';
        toggle.textContent = '▸';
        const link = li.querySelector(':scope > .epub-toc-link');
        if (link) li.insertBefore(toggle, link);
        nested.classList.add('collapsed');
        toggle.addEventListener('click', e => {
          e.preventDefault();
          e.stopPropagation();
          const collapsed = nested.classList.toggle('collapsed');
          toggle.textContent = collapsed ? '▸' : '▾';
        });
      });
    }

    _initReadingTracker() {
      if (this._mode !== 'epub') return;
      const content = $('#content');
      if (!content) return;
      const headings = content.querySelectorAll('h1, h2, h3, h4, h5, h6');
      if (!headings.length) return;

      let lastId = null;
      const onScroll = () => {
        let activeId = null;
        for (let i = headings.length - 1; i >= 0; i--) {
          const rect = headings[i].getBoundingClientRect();
          if (rect.top <= 200) { activeId = headings[i].id; break; }
        }
        if (!activeId && headings.length) activeId = headings[0].id;
        if (activeId && activeId !== lastId) {
          lastId = activeId;
          this._activeHeadingId = activeId;
          this._updateActiveHeading(activeId);
        }
      };

      window.addEventListener('scroll', onScroll, { passive: true });
      requestAnimationFrame(onScroll);
    }

    _updateActiveHeading(id) {
      if (!this.navTree) return;
      const tree = this.navTree.querySelector('.epub-toc-tree');
      if (!tree) return;
      tree.querySelectorAll('.epub-toc-link').forEach(a => a.classList.remove('active'));
      if (!id) return;
      const match = tree.querySelector(`.epub-toc-link[data-id="${CSS.escape(id)}"]`);
      if (match) {
        match.classList.add('active');
        this._expandTo(match, tree);
      }
    }

    _expandTo(el, container) {
      let parent = el.closest('li');
      while (parent) {
        const nested = parent.querySelector(':scope > .epub-toc-nested');
        if (nested && nested.classList.contains('collapsed')) {
          nested.classList.remove('collapsed');
          const t = parent.querySelector(':scope > .epub-toggle');
          if (t) t.textContent = '▾';
        }
        parent = parent.parentElement?.closest('.epub-toc-item');
        if (!parent || parent.closest('.epub-toc-tree') !== container) break;
      }
    }

    // ── Libmap Menu (lazy) ──────────────────────────────────────
    async _renderLibmapMenu() {
      if (!window.LIBRARY_CONFIG?.length) {
        this.navTree.innerHTML = '<div style="padding:20px;color:var(--text-3);font-size:13px">Navigation unavailable</div>';
        return;
      }
      this.navTree.innerHTML = `<nav class="libmap-menu"><ul class="nav-menu">${this._renderLazySections()}</ul></nav>`;
      this._initLazySections();
    }

    _renderLazySections(skipColId) {
      const site = document.body.dataset.site || '';
      return (window.LIBRARY_CONFIG || []).map(col => {
        if (col.id === skipColId) return '';
        const id = esc(col.id || '');
        const label = esc(col.label || col.title || col.id || '');
        const badge = col.badge ? ` <span class="badge">${esc(col.badge)}</span>` : '';
        const hasGroups = (col.groups || []).length > 0;

        // No groups but has a direct path → render as clickable link
        if (!hasGroups && col.path) {
          const ext = col.path.startsWith('http');
          const href = ext ? col.path : (site ? `${site}/${col.path.replace(/^\//, '')}` : col.path);
          return `<li class="nav-section" data-id="${id}">
  <a href="${esc(href)}" class="nav-section-header"${ext ? ' target="_blank" rel="noopener"' : ''}>${label}${badge}</a>
</li>`;
        }

        // Has groups → lazy-expandable
        if (hasGroups) {
          return `<li class="nav-section lazy" data-id="${id}" data-base="${esc(col.basePath || '')}">
  <span class="nav-section-header"><span class="chevron">▸</span>${label}${badge}</span>
</li>`;
        }

        // Fallback: plain label, no interaction
        return `<li class="nav-section" data-id="${id}">
  <span class="nav-section-header">${label}${badge}</span>
</li>`;
      }).join('');
    }

    _initLazySections() {
      this.navTree.querySelectorAll('.nav-section.lazy > .nav-section-header').forEach(header => {
        header.addEventListener('click', e => {
          const li = e.target.closest('.nav-section');
          if (!li || li.dataset.loaded) {
            li?.classList.toggle('open');
            return;
          }
          e.preventDefault();
          e.stopPropagation();
          const colId = li.dataset.id;
          const col = (window.LIBRARY_CONFIG || []).find(c => c.id === colId);
          if (!col) return;
          const site = document.body.dataset.site || '';
          const groupsHtml = (col.groups || []).map(g => this._renderGroup(g, site)).join('');
          if (groupsHtml) {
            const ul = document.createElement('ul');
            ul.className = 'nav-section-items';
            ul.innerHTML = groupsHtml;
            li.appendChild(ul);
          }
          li.dataset.loaded = 'true';
          li.classList.add('open');
          this._bindTogglesIn(li);
        });
      });
    }

    _bindTogglesIn(container) {
      container.querySelectorAll('.nav-group-header, .vol-expand-toggle').forEach(el => {
        if (el.tagName === 'A') return; // links navigate natively — do not intercept
        el.addEventListener('click', e => {
          e.preventDefault();
          e.stopPropagation();
          if (el.classList.contains('vol-expand-toggle')) {
            const volLi = el.closest('.vol-band');
            if (volLi) this._toggleVolToc(volLi);
            return;
          }
          const parent = el.closest('.nav-group');
          if (parent) parent.classList.toggle('open');
        });
      });
    }

    _renderGroup(group, site) {
      const label = esc(group.label || '');
      const items = group.items || [];
      const groupPath = (group.path || '').replace(/^\//, '');
      if (!items.length) {
        if (!groupPath) return `<li class="nav-group"><span class="nav-group-header"><span class="chevron">▸</span>${label}</span></li>`;
        const href = site ? `${site}/${groupPath}` : `/${groupPath}`;
        return `<li class="nav-group" data-group-path="${esc(groupPath)}"><a href="${esc(href)}" data-path="${esc('/' + groupPath)}" class="nav-group-header">${label}</a></li>`;
      }
      const itemsHtml = items.map(item => {
        const rawPath = (item.path || '').replace(/^\//, '');
        const href = site ? `${site}/${rawPath}` : `/${rawPath}`;
        const isVolume = rawPath.endsWith('/index.html');
        const volJs = isVolume ? '/' + rawPath.replace(/\/index\.html$/, '/index.js') : null;
        return `<li class="vol-band${isVolume ? ' expandable' : ''}"${volJs ? ` data-vol-js="${esc(volJs)}"` : ''}>
    ${isVolume ? '<span class="vol-expand-toggle toc-toggle">▸</span>' : ''}
    <a href="${esc(href)}" data-path="${esc('/' + rawPath)}">${esc(item.label || item.title || '')}</a>
    ${isVolume ? '<ul class="band-toc collapsed"></ul>' : ''}
</li>`;
      }).join('');
      return `<li class="nav-group" data-group-path="${esc(groupPath)}">
  <span class="nav-group-header"><span class="chevron">▸</span>${label}</span>
  <ul class="nav-group-items">${itemsHtml}</ul>
</li>`;
    }

    // ── Vol Toc loading ────────────────────────────────────────
    _toggleVolToc(li) {
      const sub = li.querySelector('.band-toc');
      const toggle = li.querySelector('.vol-expand-toggle');
      if (!sub || !toggle) return;
      const collapsed = sub.classList.contains('collapsed');
      if (!collapsed) {
        sub.classList.add('collapsed');
        toggle.textContent = '▸';
        return;
      }
      if (!li.dataset.loaded) {
        this._loadAndRenderVolToc(li).then(() => {
          sub.classList.remove('collapsed');
          toggle.textContent = '▾';
        });
      } else {
        sub.classList.remove('collapsed');
        toggle.textContent = '▾';
      }
    }

    async _loadAndRenderVolToc(li) {
      const volJs = li.dataset.volJs;
      if (!volJs) return;
      const data = await this._fetchVolData(resolveUrl(volJs));
      if (!data) return;
      const sub = li.querySelector('.band-toc');
      if (!sub) return;
      sub.innerHTML = this._renderBandToc(data);
      this._makeTocFoldable(sub);
      this._highlightTocCurrent(sub);
      li.dataset.loaded = 'true';
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

    _renderBandToc(data) {
      const headings = data.headings || [];
      if (headings.length) return this._buildTreeHtml(headings);
      if (data.files?.length) return this._headingsToToc(data.files);
      if (data.navHtml) return this._navHtmlToItems(data.navHtml);
      return '<li style="color:var(--text-3);font-size:12px;padding:8px 20px">No contents</li>';
    }

    _headingsToToc(files) {
      const all = [];
      for (const f of files) {
        const headings = f.headings || [];
        if (!headings.length && f.title) {
          all.push({ text: f.title, level: 1, file: f.file || '', id: null });
        } else {
          for (const h of headings) all.push({
            text: h.text || '', level: h.level || 2,
            file: h.filename || f.file || '', id: h.id || null
          });
        }
      }
      if (!all.length) return '<li style="color:var(--text-3);font-size:12px;padding:8px 20px">No contents</li>';
      return this._buildTreeHtml(all);
    }

    _buildTreeHtml(headings) {
      const root = { level: 0, children: [] };
      const stack = [root];
      for (const h of headings) {
        const node = { ...h, children: [] };
        while (stack.length > 1 && stack[stack.length - 1].level >= h.level) stack.pop();
        stack[stack.length - 1].children.push(node);
        stack.push(node);
      }
      return this._renderNodes(root.children);
    }

    _renderNodes(nodes) {
      return nodes.map(n => {
        const href = n.id ? `${esc(n.file)}#${esc(n.id)}` : esc(n.file);
        const hasChildren = n.children.length > 0;
        const childHtml = hasChildren ? `<ul>${this._renderNodes(n.children)}</ul>` : '';
        return `<li class="toc-heading${hasChildren ? ' has-nested' : ''}"><a href="${href}">${esc(n.text)}</a>${childHtml}</li>`;
      }).join('');
    }

    _navHtmlToItems(navHtml) {
      const temp = document.createElement('div');
      temp.innerHTML = `<ol>${navHtml}</ol>`;
      const list = temp.querySelector('ol, ul');
      return list ? [...list.children].map(c => c.outerHTML).join('')
        : `<li style="color:var(--text-3);font-size:12px;padding:8px 20px">${navHtml}</li>`;
    }

    _makeTocFoldable(container) {
      container.querySelectorAll('li').forEach(li => {
        const nested = li.querySelector(':scope > ol, :scope > ul');
        if (!nested) return;
        li.classList.add('has-nested');
        const toggle = document.createElement('span');
        toggle.className = 'toc-toggle';
        toggle.textContent = '▸';
        toggle.dataset.collapsed = 'true';
        toggle.setAttribute('role', 'button');
        toggle.setAttribute('aria-label', 'Expand section');
        const link = li.querySelector(':scope > a');
        (link || li).insertBefore(toggle, (link || li).firstChild);
        nested.classList.add('collapsed');
      });
    }

    // ── Volume Index Page ──────────────────────────────────────
    async _renderVolumeIndex() {
      const meta = window.__PAGE_META__ || {};
      const data = await this._fetchVolData(resolveUrl(meta.indexJsPath || './index.js'));
      if (!data) return;
      const content = $('#content');
      if (!content) return;
      if (data.title) document.title = `${data.title} — ${(meta.title || '').split(' — ').pop() || ''}`;
      this._updateBreadcrumb(data);
      const headings = data.headings || [];
      const tocHtml = headings.length ? this._buildTreeHtml(headings) : this._headingsToToc(data.files || []);
      const innerHTMLhead = meta.preNavHtml ? `<div class="vol-index-title">${meta.preNavHtml}</div>` : `<h2 class="vol-index-title">${esc(data.title || 'Contents')}</h2>`;
      content.innerHTML = innerHTMLhead + `<nav class="vol-index-nav">${tocHtml}</nav>`;
      content.querySelectorAll('table').forEach(table => {
        if (table.parentElement?.classList.contains('table-wrapper')) return;
        const wrapper = document.createElement('div');
        wrapper.className = 'table-wrapper';
        wrapper.style.cssText = 'overflow-x:auto;max-width:100%;display:block;';
        table.style.minWidth = '600px';
        table.parentNode.insertBefore(wrapper, table);
        wrapper.appendChild(table);
      });
    }

    _updateBreadcrumb(data) {
      const pathbar = $('#doc-pathbar');
      if (!pathbar || !data.volumePath) return;
      const parts = data.volumePath.replace(/^\/|\/$/g, '').split('/');
      const site = document.body.dataset.site || '';
      const crumbs = parts.map((part, i) => i === parts.length - 1
        ? `<span class="crumb current">${part}</span>`
        : `<a class="crumb" href="${site}/${parts.slice(0, i + 1).join('/')}/index.html">${part}</a>`
      ).join('<span class="crumb-sep">/</span>');
      pathbar.innerHTML = crumbs || '<span style="color:var(--text-3);">Library</span>';
    }

    // ── Highlight Current (legacy libmap mode) ───────────────────
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
        const volBand = link.closest('.vol-band.expandable');
        if (volBand) {
          if (!volBand.dataset.loaded) {
            this._loadAndRenderVolToc(volBand).then(() => {
              volBand.querySelector('.band-toc')?.classList.remove('collapsed');
              volBand.querySelector('.vol-expand-toggle').textContent = '▾';
              this._highlightTocCurrent(volBand.querySelector('.band-toc'));
            });
          } else {
            volBand.querySelector('.band-toc')?.classList.remove('collapsed');
            volBand.querySelector('.vol-expand-toggle').textContent = '▾';
          }
        }
        link.closest('li')?.classList.add('active');
        link.closest('.nav-group')?.classList.add('open');
        link.closest('.nav-section')?.classList.add('open');
        requestAnimationFrame(() => link.scrollIntoView({ block: 'nearest', behavior: 'smooth' }));
      });
    }

    _highlightEpubCurrent() {
      const currentFile = location.pathname.split('/').pop();
      const currentHash = location.hash.slice(1);
      const tree = this.navTree?.querySelector('.epub-toc-tree');
      if (!tree) return;

      let best = null, bestScore = 0;
      tree.querySelectorAll('.epub-toc-link').forEach(a => {
        const file = a.dataset.file || '';
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
      best.classList.add('active');
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
      best.classList.add('active');
      this._expandBranchTo(best, container);
    }

    _expandBranchTo(el, container) {
      let parent = el.parentElement;
      while (parent) {
        if (parent.tagName === 'OL' || parent.tagName === 'UL') {
          if (parent.classList.contains('collapsed')) {
            parent.classList.remove('collapsed');
            const t = parent.closest('li')?.querySelector('.toc-toggle');
            if (t) { t.textContent = '▾'; t.dataset.collapsed = 'false'; }
          }
        }
        parent = parent.parentElement;
        if (parent?.classList?.contains('vol-toc-nav')) break;
        if (parent === container) break;
      }
    }

    // ── Sidebar ────────────────────────────────────────────────
    _bindSidebarToggle() {
      $('#sidebar-toggle')?.addEventListener('click', () => this.toggle());
      this.backdrop?.addEventListener('click', () => this.close());
    }

    toggle() { this.sidebar.classList.contains('open') ? this.close() : this.open(); }

    open() {
      this.sidebar.classList.add('open');
      this.backdrop?.classList.add('visible');
      if (innerWidth < 768) document.body.style.overflow = 'hidden';
      $('#sidebar-toggle')?.classList.add('active');
      if (this._mode === 'epub') {
        this._scrollTocToActive();
      } else {
        this._scrollToReadingLegacy();
      }
    }

    close() {
      this.sidebar.classList.remove('open');
      this.backdrop?.classList.remove('visible');
      document.body.style.overflow = '';
      $('#sidebar-toggle')?.classList.remove('active');
    }

    _scrollTocToActive() {
      if (!this.navTree) return;
      const active = this.navTree.querySelector('.epub-toc-tree .epub-toc-link.active');
      if (!active) return;
      this._expandTo(active, this.navTree.querySelector('.epub-toc-tree'));
      requestAnimationFrame(() => active.scrollIntoView({ block: 'center', behavior: 'smooth' }));
    }

    _scrollToReadingLegacy() {
      if (!this.menuLoaded) return;
      const container = this.navTree;
      const currentFile = location.pathname.split('/').pop();
      let target = null;

      const content = $('#content');
      let visibleH = null;
      if (content) {
        const headings = content.querySelectorAll('h1, h2, h3, h4, h5, h6');
        for (let i = headings.length - 1; i >= 0; i--) {
          if (headings[i].getBoundingClientRect().top <= 200) { visibleH = headings[i]; break; }
        }
        if (!visibleH && headings.length) visibleH = headings[0];
      }
      const hId = visibleH?.id;
      if (hId) {
        container.querySelectorAll('a').forEach(a => {
          if (target) return;
          const href = a.getAttribute('href') || '';
          const [file, hash] = href.split('#');
          if ((file.split('/').pop() === currentFile && hash === hId) || (!file && href === '#' + hId)) target = a;
        });
      }
      if (!target) {
        container.querySelectorAll('a').forEach(a => {
          if (target) return;
          const href = a.getAttribute('href') || '';
          if (href.split('#')[0].split('/').pop() === currentFile && !href.includes('#')) target = a;
        });
      }
      if (!target) target = container.querySelector('a.active');
      if (!target) return;
      this._expandBranchTo(target, container);
      requestAnimationFrame(() => target.scrollIntoView({ block: 'center', behavior: 'smooth' }));
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
        const docName = btn.querySelector('.doc-name');
        if (docName && data.title) docName.textContent = data.title;
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