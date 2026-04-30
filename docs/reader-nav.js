// ── MenuManager (EPUB menu + scroll tracking, ported from nav.js) ──
class MenuManager {
    constructor() {
        this.sidebar = null;
        this.navTree = null;
        this._volCache = new Map();
        this._mode = 'libmap';
        this._currentVol = null;
        this._activeHeadingId = null;
        this._scrollTrackingReady = false;
        this._tocScrollHandler = null;
        this._io = null;
    }

    init() {
        this.sidebar = $('#lsidebar');
        this.navTree = $('#nav-tree');
        if (!this.sidebar || !this.navTree) return;
        this.reinit(state.doc);
    }

    reinit(docPath) {
        // cleanup old observers / listeners
        if (this._tocScrollHandler) {
            window.removeEventListener('scroll', this._tocScrollHandler, { passive: true });
            this._tocScrollHandler = null;
        }
        if (this._io) { this._io.disconnect(); this._io = null; }
        this._scrollTrackingReady = false;
        this._activeHeadingId = null;
        this.navTree.innerHTML = '';

        if (!docPath) {
            this._mode = 'libmap';
            buildNav();
            this._highlightLibmapCurrent();
            this._initTocRail();
            return;
        }

        this._currentVol = this._detectVolume(docPath);
        if (this._currentVol) {
            this._mode = 'epub';
            this._renderEpubMenu(docPath);
        } else {
            this._mode = 'libmap';
            buildNav();
            this._highlightLibmapCurrent();
            this._initTocRail();
        }
    }

    _detectVolume(docPath) {
        const cfg = window.LIBRARY_CONFIG || [];
        for (const col of cfg) {
            for (const group of (col.groups || [])) {
                for (const item of (group.items || [])) {
                    const p = item.path || '';
                    if (!p.endsWith('/index.html')) continue;
                    const dir = p.replace(/^\//, '').replace(/\/index\.html$/, '');
                    if (!dir) continue;
                    if (docPath === dir + '/index.html' || docPath.startsWith(dir + '/')) {
                        return { col, group, item, dir };
                    }
                }
            }
        }
        return null;
    }

    async _renderEpubMenu(docPath) {
        const { col, group, item, dir } = this._currentVol;
        const data = await this._fetchVolData(dir);
        if (!data) {
            buildNav();
            return;
        }
        this._currentVol.data = data;

        let html = `<div class="breadcrumb" aria-label="Breadcrumb">`;
        if (col.path && !col.path.startsWith('http')) {
            html += `<a href="?doc=${esc(col.path.replace(/^\//, ''))}">${esc(col.label)}</a>`;
        } else {
            html += `<span>${esc(col.label)}</span>`;
        }
        const volTitle = item.label || item.title || data.title || 'Contents';
        const volHref = item.path || ('/' + dir + '/index.html');
        html += `<span class="breadcrumb__sep">/</span>`;
        html += `<a href="?doc=${esc(volHref.replace(/^\//, ''))}">${esc(volTitle)}</a>`;
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
        this._highlightEpubCurrent(docPath);
        this._initTocRail();
        this._initScrollTracking();
    }

    async _fetchVolData(dir) {
        const base = '/' + dir.replace(/^\//, '').replace(/\/$/, '') + '/';

        // Try raw index.json
        try {
            const res = await fetch(base + 'index.json');
            if (res.ok) {
                const json = await res.json();
                return this._convertJsonToVolumeData(json, dir);
            }
        } catch (e) { }

        // Try alternative names
        const vol = base.replace(/\/$/, '').split('/').pop();
        for (const name of [`index${vol}.json`, `${vol}/index.json`]) {
            try {
                const res = await fetch(base + name);
                if (res.ok) {
                    const json = await res.json();
                    return this._convertJsonToVolumeData(json, dir);
                }
            } catch { }
        }

        return null;
    }

    _convertJsonToVolumeData(json, dir) {
        if (!Array.isArray(json)) return null;
        const vol = this._currentVol;
        const allHeadings = [];
        for (const f of json) {
            for (const h of (f.headings || [])) {
                allHeadings.push({
                    level: h.level || 2,
                    text: h.text || '',
                    id: h.id || null,
                    file: h.filename || f.file || ''
                });
            }
        }
        return {
            version: 1,
            title: vol?.item?.label || vol?.item?.title || dir,
            volumePath: '/' + dir.replace(/^\//, '').replace(/\/?$/, '/') + '/',
            collectionId: vol?.col?.id,
            collectionLabel: vol?.col?.label,
            groupLabel: vol?.group?.label,
            navHtml: null,
            files: json,
            headings: allHeadings
        };
    }

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
        const currentFile = (state.doc || '').split('/').pop().replace(/\.html$/i, '');
        return `<ul class="sidebar-menu ${clsPrefix}">${this._renderSidebarNodes(nodes, currentFile)}</ul>`;
    }

    _renderSidebarNodes(nodes, currentFile) {
        return nodes.map(n => {
            const href = n.id ? `?doc=${esc(n.file || '')}#${esc(n.id)}` : `?doc=${esc(n.file || '')}`;
            const isCurrentFile = (n.file || '').replace(/\.html$/i, '') === currentFile;
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
            const caret = li.querySelector('.sidebar-caret');
            const nested = li.querySelector(':scope > ul, :scope > ol');
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

    _initBreadcrumbFade() {
        if (this._mode !== 'epub') return;
        const bc = this.navTree.querySelector('.breadcrumb');
        const tocTree = this.navTree.querySelector('.sidebar-menu');
        if (!bc || !tocTree || !this.navTree) return;

        // 统一用 .sidebar-nav（this.navTree）作为 root：
        // 桌面端和移动端实际滚动都发生在 navTree 内部，其 top 均为 var(--nav-h)
        this._io = new IntersectionObserver((entries) => {
            entries.forEach(e => {
                const rect = e.boundingClientRect;
                const root = e.rootBounds;
                const fullyAbove = rect.bottom < root.top;
                bc.classList.toggle('breadcrumb--faded', fullyAbove);
            });
        }, { root: this.navTree, threshold: 0 });

        this._io.observe(tocTree);
    }

    _renderLazySections(skipColId) {
        return (window.LIBRARY_CONFIG || []).map(col => {
            if (col.id === skipColId) return '';
            const id = esc(col.id || '');
            const label = esc(col.label || col.title || col.id || '');
            const badge = col.badge ? ` <span class="sidebar-badge">${esc(col.badge)}</span>` : '';
            const hasGroups = (col.groups || []).length > 0;

            if (!hasGroups && col.path) {
                const ext = col.path.startsWith('http');
                const rawPath = col.path.replace(/^\//, '');
                const href = ext ? col.path : `?doc=${esc(rawPath)}`;
                const dataPath = ext ? '' : ` data-path="${esc('/' + rawPath)}"`;
                return `<li class="sidebar-item">
  <a href="${esc(href)}"${dataPath} class="sidebar-link"${ext ? ' target="_blank" rel="noopener"' : ''}>${label}${badge}</a>
</li>`;
            }

            if (hasGroups) {
                // 有子条目时 label 必须是 span（caret 单独负责展开），不能是 a
                return `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-section="${id}" data-base="${esc(col.basePath || '')}" data-collapsed="true">
  <div class="sidebar-item-row">
    <span class="sidebar-category-label">${label}${badge}</span>
    <button class="sidebar-caret" type="button" aria-label="Expand section" tabindex="0">▸</button>
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
                const groupsHtml = (col.groups || []).map(g => this._renderGroup(g)).join('');
                if (groupsHtml) {
                    const ul = document.createElement('ul');
                    ul.className = 'sidebar-menu sidebar-menu--nested';
                    ul.innerHTML = groupsHtml;
                    li.appendChild(ul);
                }
                li.dataset.loaded = 'true';
                li.setAttribute('data-collapsed', 'false');
                if (caret) caret.textContent = '\u25be';
                this._bindTogglesIn(li);
            };

            const headerIsLink = header && header.tagName === 'A';
            // header 是 <a> 链接时，只给 caret 绑 toggle，让 label 正常导航
            if (header && !headerIsLink) header.addEventListener('click', toggleFn);
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
            const headerIsLink = header && header.tagName === 'A';
            // header 是 <a> 链接时，只给 caret 绑 toggle，让 label 正常导航
            if (header && !headerIsLink) header.addEventListener('click', toggleFn);
        });
    }

    _renderGroup(group) {
        const label = esc(group.label || '');
        const items = group.items || [];
        const groupPath = (group.path || '').replace(/^\//, '');

        // 无子条目：直接渲染为链接（外部链接新开标签页）
        if (!items.length) {
            if (!groupPath) return `<li class="sidebar-item"><span class="sidebar-category-label">${label}</span></li>`;
            const isExt = groupPath.startsWith('http');
            const href = isExt ? groupPath : `?doc=${esc(groupPath)}`;
            const dataPath = isExt ? '' : ` data-path="${esc('/' + groupPath)}"`;
            return `<li class="sidebar-item"><a href="${esc(href)}"${dataPath}${isExt ? ' target="_blank" rel="noopener"' : ''} class="sidebar-link">${label}</a></li>`;
        }

        // 子条目：识别外部链接，避免错误地套成 ?doc= 路由
        const itemsHtml = items.map(item => {
            const rawPath = (item.path || '').replace(/^\//, '');
            const isExt = rawPath.startsWith('http');
            const href = isExt ? rawPath : `?doc=${esc(rawPath)}`;
            return `<li class="sidebar-item">
    <a href="${esc(href)}"${isExt ? ' target="_blank" rel="noopener"' : ''} data-path="${esc(rawPath ? '/' + rawPath : '')}" class="sidebar-link">${esc(item.label || item.title || '')}</a>
</li>`;
        }).join('');

        // 有内部 path 时 label 做成可点击链接（caret 单独负责展开）；无 path 时 span + caret
        // 有子条目时 label 必须是 span（caret 单独负责展开），不能是 a
        return `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-group-path="${esc(groupPath)}" data-collapsed="true">
  <div class="sidebar-item-row">
    <span class="sidebar-category-label">${label}</span>
    <button class="sidebar-caret" type="button" aria-label="Expand section" tabindex="0">▸</button>
  </div>
  <ul class="sidebar-menu sidebar-menu--nested">${itemsHtml}</ul>
</li>`;
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

    _getPageHeadings() {
        if (this._mode !== 'epub') {
            return this._getDomHeadings().map(h => ({
                level: parseInt(h.tagName[1]),
                text: h.textContent.trim(),
                id: h.id
            }));
        }

        const currentFile = (state.doc || '').split('/').pop().replace(/\.html$/i, '');
        const jsonHeadings = (this._currentVol?.data?.headings || []).filter(h => {
            const hFile = (h.file || '').replace(/\.html$/i, '');
            return hFile === currentFile;
        });

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

    _initTocRail() {
        const nav = document.getElementById('toc-desktop-nav');
        if (!nav) return;
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

        if (this._scrollTrackingReady) {
            const activeId = this._getActiveHeadingId(this._getDomHeadings(), 200);
            if (activeId) {
                this._updateNavTracking(activeId);
                this._syncNavScroll(activeId);
            }
        }
    }

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
                this._updateNavTracking(activeId);
                this._syncNavScroll(activeId);
            }
        };

        window.addEventListener('scroll', onScroll, { passive: true });
        this._tocScrollHandler = onScroll;
        requestAnimationFrame(() => {
            onScroll();
            this._syncNavScroll(lastId);
        });
    }

    _syncNavScroll(activeId) {
        if (innerWidth >= 997) return;
        if (!this.navTree) return;
        const active = this.navTree.querySelector('.sidebar-link.sidebar-link--active');
        if (!active) return;
        this._expandTo(active, this.navTree.querySelector('.sidebar-menu'));
        requestAnimationFrame(() => active.scrollIntoView({ block: 'center', behavior: 'smooth' }));
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

        const rawFile = (state.doc || '').split('/').pop();
        const currentFile = rawFile ? rawFile.replace(/\.html$/i, '') : 'index';

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

    _highlightCurrent() {
        if (this._mode === 'epub') {
            this._highlightEpubCurrent(state.doc);
        } else {
            this._highlightLibmapCurrent();
        }
    }

    _highlightEpubCurrent(docPath) {
        const currentFile = (docPath || '').split('/').pop().replace(/\.html$/i, '');
        const currentHash = location.hash.slice(1);
        const tree = this.navTree?.querySelector('.sidebar-menu');
        if (!tree) return;

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

    _highlightLibmapCurrent() {
        const currentPath = (state.doc || '').replace(/^\//, '').replace(/\/$/, '');
        if (!currentPath) return;
        let found = false;
        this.navTree.querySelectorAll('a[data-path]').forEach(link => {
            if (found) return;
            let hrefPath = '';
            const rawHref = link.getAttribute('href') || '';
            if (rawHref.startsWith('?doc=')) {
                hrefPath = rawHref.slice(5).replace(/\/$/, '');
            } else {
                try { hrefPath = new URL(rawHref, location.origin).pathname.replace(/\/$/, ''); } catch { }
            }
            const dataPath = (link.dataset.path || '').replace(/^\//, '').replace(/\/$/, '');
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
}