// ===== Global utilities (exposed on window for reader-ui.js) =====
window.$ = s => document.querySelector(s);
window.$$ = s => [...document.querySelectorAll(s)];
window.on = (t, e, f, o) => t && t.addEventListener(e, f, o || false);
window.esc = t => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
window.onScrollFrame = window.onScrollFrame || (function () {
    const callbacks = new Set();
    let frame = 0;
    const run = () => {
        frame = 0;
        callbacks.forEach(fn => fn());
    };
    const queue = () => {
        if (!frame) frame = requestAnimationFrame(run);
    };
    window.addEventListener('scroll', queue, { passive: true });
    return fn => {
        callbacks.add(fn);
        return () => callbacks.delete(fn);
    };
})();
window.syncFill = function (el) {
    var min = parseFloat(el.min) || 0, max = parseFloat(el.max) || 100, val = parseFloat(el.value) || 0;
    var pct = ((val - min) / (max - min) * 100).toFixed(2) + '%';
    el.style.setProperty('--_fill', pct);
};
window.resolveUrl = function (href) { try { return new URL(href, location.href).href; } catch { return location.pathname.replace(/[^/]*$/, '') + href; } };
window.findCollection = function (path) {
    const norm = path.replace(/^\//, '');
    return window.LIBRARY_CONFIG?.find(c => norm.startsWith((c.basePath || `/${c.id}/`).replace(/^\//, '')));
};
window.resolveCssHref = function (href, base) {
    if (/^https?:\/\//.test(href) || href.startsWith('//')) return href;
    if (href.startsWith('/')) return href.slice(1);
    try {
        const dir = base.endsWith('/') ? base : base + '/';
        const resolved = new URL(href, location.origin + '/' + dir);
        return resolved.pathname.replace(/^\//, '');
    } catch (e) {
        const cleanBase = base.replace(/^\//, '').replace(/\/$/, '');
        const cleanHref = href.replace(/^\.+\//, '');
        return cleanBase ? cleanBase + '/' + cleanHref : cleanHref;
    }
};
window.scrollToEl = function (el) { window.scrollTo({ top: Math.max(0, el.getBoundingClientRect().top + scrollY - 80), behavior: 'smooth' }); };
window.getDomHeadings = function (container) {
    if (!container) return [];
    return Array.from(container.querySelectorAll('h1, h2, h3, h4, h5, h6')).filter(h => h.id);
};
window.getActiveHeadingId = function (headings, threshold) {
    threshold = threshold || 200;
    if (!headings?.length) return null;
    for (let i = headings.length - 1; i >= 0; i--) if (headings[i].getBoundingClientRect().top <= threshold) return headings[i].id;
    return headings[0].id;
};
window.buildHeadingTree = function (headings) {
    const root = { level: 0, children: [] };
    const stack = [root];
    for (const h of headings) {
        const node = { ...h, children: [] };
        while (stack.length > 1 && stack[stack.length - 1].level >= h.level) stack.pop();
        stack[stack.length - 1].children.push(node);
        stack.push(node);
    }
    return root.children;
};
window.fetchVolData = async function (dir, cacheMap) {
    const cleanDir = dir.replace(/^\//, '').replace(/\/$/, '');
    if (cacheMap && cacheMap[cleanDir]) return cacheMap[cleanDir];
    const jsonUrl = '/' + cleanDir + '/index.json';
    try {
        const res = await fetch(jsonUrl);
        if (res.ok) {
            const data = await res.json();
            if (cacheMap) cacheMap[cleanDir] = data;
            return data;
        }
    } catch (e) { /* ignore, fallback below */ }
    const jsUrl = '/' + cleanDir + '/index.js';
    try {
        const mod = await import(jsUrl);
        const data = mod?.default || null;
        if (cacheMap && data) cacheMap[cleanDir] = data;
        return data;
    } catch (e) { console.warn('[fetchVolData] fallback failed', jsUrl, e); }
    return null;
};
window.expandTo = function (el, container) {
    let parent = el.closest('li');
    while (parent && container.contains(parent)) {
        if (parent.classList.contains('sidebar-item--collapsible')) {
            parent.setAttribute('data-collapsed', 'false');
            const caret = parent.querySelector('.sidebar-caret');
            if (caret) caret.textContent = '\u25be';
        }
        parent = parent.parentElement?.closest('.sidebar-item');
    }
};

// ===== MenuManager =====
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
        this._scrollFrame = 0;
        this._sidebarTrackingCache = null;
        this._activeSidebarLink = null;
        this._activeTocLink = null;
        this._lastSyncedNavId = null;
        this._headingTops = [];
        this._headingResizeHandler = null;
        this._headingResizeFrame = 0;
        this._io = null;
        this._sidebarClickHandler = null;
        this._sidebarStateObserver = null;
    }

    init() {
        this.sidebar = $('#lsidebar');
        this.navTree = $('#nav-tree');
        if (!this.sidebar || !this.navTree) return;
        this._observeSidebarOpen();
        this.reinit(state.doc);
    }

    _observeSidebarOpen() {
        if (this._sidebarStateObserver) return;
        this._sidebarStateObserver = new MutationObserver(() => {
            if (innerWidth < 997 && this.sidebar.classList.contains('doc-sidebar--open')) {
                this._lastSyncedNavId = null;
                this._syncNavScroll(this._activeHeadingId);
            }
        });
        this._sidebarStateObserver.observe(this.sidebar, { attributes: true, attributeFilter: ['class'] });
    }

    reinit(docPath) {
        this._cleanup();
        this.navTree.innerHTML = '';
        this._invalidateTrackingCache();
        this._currentVol = docPath ? this._detectVolume(docPath) : null;

        if (!docPath) {
            this._setMode('libmap');
            this._renderLibmapMenu();
            this._highlightLibmapCurrent();
            this._initTocRail();
            this._initScrollTracking();
        } else if (this._currentVol) {
            this._setMode('epub');
            this._renderEpubMenu(docPath);
        } else if (innerWidth < 997 && getDomHeadings($('#content')).length > 0) {
            this._setMode('page-toc');
            this._renderPageTocMenu();
        } else {
            this._setMode('libmap');
            this._renderLibmapMenu();
            this._highlightLibmapCurrent();
            this._initTocRail();
            this._initScrollTracking();
        }
    }

    _cleanup() {
        if (this._tocScrollHandler) {
            if (this._tocScrollHandler._isScrollFrameOff) this._tocScrollHandler();
            else window.removeEventListener('scroll', this._tocScrollHandler, { passive: true });
            this._tocScrollHandler = null;
        }
        if (this._scrollFrame) {
            cancelAnimationFrame(this._scrollFrame);
            this._scrollFrame = 0;
        }
        if (this._headingResizeHandler) {
            window.removeEventListener('resize', this._headingResizeHandler);
            this._headingResizeHandler = null;
        }
        if (this._headingResizeFrame) {
            cancelAnimationFrame(this._headingResizeFrame);
            this._headingResizeFrame = 0;
        }
        if (this._io) { this._io.disconnect(); this._io = null; }
        this._scrollTrackingReady = false;
        this._activeHeadingId = null;
        this._invalidateTrackingCache();
        if (this._sidebarClickHandler && this.navTree) {
            this.navTree.removeEventListener('click', this._sidebarClickHandler);
            this._sidebarClickHandler = null;
        }
    }

    _setMode(m) { this._mode = m; }

    _detectVolume(docPath) {
        const cfg = window.LIBRARY_CONFIG || [];
        const doc = (docPath || '').replace(/^\//, '');
        const docDir = doc.replace(/\/[^\/]+$/, '');
        for (const col of cfg) {
            for (const group of (col.groups || [])) {
                for (const item of (group.items || [])) {
                    const p = item.path || '';
                    if (!p.endsWith('/index.html')) continue;
                    const dir = p.replace(/^\//, '').replace(/\/index\.html$/, '');
                    if (!dir) continue;
                    if (doc === dir + '/index.html' || docDir === dir || doc.startsWith(dir + '/')) {
                        return { col, group, item, dir };
                    }
                }
            }
        }
        return null;
    }

    _buildBreadcrumb(parts) {
        let html = '<div class="breadcrumb" aria-label="Breadcrumb">';
        parts.forEach((p, i) => {
            if (i > 0 && p.id != 'page-breadcrumb-link') html += '<span class="breadcrumb__sep">/</span>';
            if (p.isPageBadge && p.id == 'page-breadcrumb-link') {
                html += `<span class="breadcrumb__sep">/</span>
<a href="#" id="${esc(p.id)}" style="display:none"></a>`;
            } else if (p.href && p.expand) {
                html += `<a href="${esc(p.href)}" data-expand-section="${esc(p.expand)}">${esc(p.text)}</a>`;
            } else if (p.href) {
                html += `<a href="${esc(p.href)}">${esc(p.text)}</a>`;
            } else if (p.text) {
                html += `<span>${esc(p.text)}</span>`;
            }
        });
        html += '</div>';
        return html;
    }


    _expandSectionById(sectionId) {
        const li = this.navTree.querySelector(`li[data-section="${sectionId}"]`);
        if (!li) return;
        const isCollapsed = li.getAttribute('data-collapsed') !== 'false';
        if (isCollapsed) {
            const trigger = li.querySelector('.sidebar-category-label') || li.querySelector('.sidebar-caret');
            if (trigger) trigger.click();
        }
        requestAnimationFrame(() => li.scrollIntoView({ block: 'center', behavior: 'smooth' }));
    }

    _bindBreadcrumbClicks() {
        const bc = this.navTree?.querySelector('.breadcrumb');
        if (!bc) return;
        bc.addEventListener('click', (e) => {
            const el = e.target.nodeType === 1 ? e.target : e.target.parentElement;
            const link = el?.closest('a[data-expand-section]');
            if (!link) return;
            e.preventDefault();
            e.stopPropagation();
            this._expandSectionById(link.dataset.expandSection);
        });
    }

    _postRenderMenu(docPath) {
        this._initSidebarToggles(this.navTree);
        this._initLazySections();
        this._initBreadcrumbFade();
        this._highlightCurrent(docPath);
        this._initTocRail();
        this._initScrollTracking();
        this._bindSidebarLinkClicks(docPath);
        this._bindBreadcrumbClicks();
        this._scrollToPendingAnchor();
        // 同步页码链接状态（菜单重建后恢复当前页码显示）
        if (window.__PAGE_BAR__?.currentPage != null) {
            window.__PAGE_BAR__._updateBadge(window.__PAGE_BAR__.currentPage);
        }
    }

    async _renderEpubMenu(docPath) {
        const { col, group, item, dir } = this._currentVol;
        const data = await this._fetchVolData(dir);
        if (!data) { this._fallbackMenu(); return; }
        this._currentVol.data = data;

        const currentFile = (docPath || '').split('/').pop().replace(/\.html$/i, '');
        const fileHeadings = (data.headings || []).filter(h => (h.file || '').replace(/\.html$/i, '') === currentFile);

        const volTitle = item.label || item.title || data.title || 'Contents';
        const volHref = item.path || (dir + '/index.html');
        const colHref = col.path && !col.path.startsWith('http') ? `?doc=${esc(col.path.replace(/^\//, ''))}` : null;
        const volLink = `?doc=${esc(volHref.replace(/^\//, ''))}`;
        const ispagebadge = window.__PAGE_BAR__.hasPageAnchors;

        let html = this._buildBreadcrumb([
            colHref ? { href: colHref, text: col.label, expand: col.id } : { text: col.label, expand: col.id },
            { href: volLink, text: volTitle },
            { id: 'page-breadcrumb-link', isPageBadge: ispagebadge }
        ]);

        const headings = data.headings || [];
        if (headings.length) html += this._renderSidebarTree(buildHeadingTree(headings), 'epub-toc');
        html += '<div class="section-divider"><span>All works</span></div>' + this._buildLibmapHtml();
        this.navTree.innerHTML = html;
        this._invalidateTrackingCache();
        this._postRenderMenu(docPath);
    }

    _renderPageTocMenu() {
        const headings = getDomHeadings($('#content'));
        if (headings.length <= 1) { this._forceLibmap(); return; }

        const pageTitle = headings[0]?.textContent?.trim() || document.title;
        const col = this._currentVol?.col || this._findCollectionByPath();
        const parts = [{ text: col?.label || 'Library', expand: col?.id }];
        if (col?.path && !col.path.startsWith('http')) parts[0].href = `?doc=${esc(col.path.replace(/^\//, ''))}`;
        if (this._currentVol?.item?.label) {
            parts.push({
                href: this._currentVol.item.path ? `?doc=${esc(this._currentVol.item.path.replace(/^\//, ''))}` : '',
                text: this._currentVol.item.label
            });
        }
        parts.push({ text: pageTitle, isActive: true });

        let html = this._buildBreadcrumb(parts);
        const currentFileName = (state.doc || '').split('/').pop();
        const pageHeadings = headings.map(h => ({
            level: parseInt(h.tagName[1]), text: h.textContent.trim(), id: h.id, file: currentFileName
        }));
        html += this._renderSidebarTree(buildHeadingTree(pageHeadings), 'page-toc');
        html += '<div class="section-divider"><span>All works</span></div>' + this._buildLibmapHtml();
        this.navTree.innerHTML = html;
        this._invalidateTrackingCache();
        this._postRenderMenu(state.doc);
    }

    _forceLibmap() {
        this._setMode('libmap');
        this._renderLibmapMenu();
        this._highlightLibmapCurrent();
        this._initTocRail();
        this._initScrollTracking();
    }

    _fallbackMenu() {
        if (innerWidth < 997) {
            this._renderPageTocMenu();
        } else {
            this._setMode('libmap');
            this._renderLibmapMenu();
            this._highlightLibmapCurrent();
            this._initTocRail();
            this._initScrollTracking();
        }
    }

    async _fetchVolData(dir) {
        const cleanDir = dir.replace(/^\//, '').replace(/\/$/, '');
        const raw = await fetchVolData(cleanDir, this._volCache);
        if (!raw) return null;

        // 新格式：index.js 直接 export default 的 VolumeData 对象
        if (raw && typeof raw === 'object' && !Array.isArray(raw) && raw.version === 1) {
            return raw;
        }

        // 旧格式：index.json 返回的文件数组，需要转换
        return this._convertJsonToVolumeData(raw, cleanDir);
    }

    _convertJsonToVolumeData(json, dir) {
        if (!Array.isArray(json)) return null;
        const vol = this._currentVol;
        const allHeadings = [];
        for (const f of json) {
            for (const h of (f.headings || [])) {
                allHeadings.push({ level: h.level || 2, text: h.text || '', id: h.id || null, file: h.filename || f.file || '' });
            }
        }
        const cleanDir = dir.replace(/^\//, '').replace(/\/$/, '');
        return {
            version: 1, title: vol?.item?.label || vol?.item?.title || cleanDir,
            volumePath: '/' + cleanDir + '/',
            collectionId: vol?.col?.id, collectionLabel: vol?.col?.label, groupLabel: vol?.group?.label,
            navHtml: null, files: json, headings: allHeadings
        };
    }

    _findCollectionByPath() {
        const cfg = window.LIBRARY_CONFIG || [];
        const docPath = (state.doc || '').replace(/^\//, '');
        for (const col of cfg) {
            const basePath = (col.basePath || '').replace(/^\//, '').replace(/\/$/, '');
            if (basePath && docPath.startsWith(basePath)) return col;
            for (const group of (col.groups || [])) {
                for (const item of (group.items || [])) {
                    const p = (item.path || '').replace(/^\//, '');
                    if (p && docPath.startsWith(p.replace(/\/[^\/]+$/, ''))) return col;
                }
            }
        }
        return null;
    }

    _renderSidebarTree(nodes, clsPrefix) {
        const currentFileName = (state.doc || '').split('/').pop().replace(/\.html$/i, '');
        const currentFullPath = (state.doc || '').replace(/\.html$/i, '');
        return `<ul class="sidebar-menu ${clsPrefix}">${this._renderSidebarNodes(nodes, currentFileName, currentFullPath)}</ul>`;
    }

    _renderSidebarNodes(nodes, currentFileName, currentFullPath) {
        const volDir = this._currentVol?.dir || '';
        const isPageToc = this._mode === 'page-toc';
        return nodes.map(n => {
            const fullFile = n.file ? (volDir.replace(/\/?$/, '/') + n.file).replace(/\/+/g, '/') : '';
            const targetFile = fullFile.replace(/\.html$/i, '');
            const isSameFile = !isPageToc && targetFile && targetFile === currentFullPath;
            let href = isPageToc ? (n.id ? `#${esc(n.id)}` : '#')
                : isSameFile ? (n.id ? `#${esc(n.id)}` : '#')
                    : (n.id ? `?doc=${esc(fullFile)}#${esc(n.id)}` : `?doc=${esc(fullFile)}`);
            const hasChildren = n.children.length > 0;
            const childHtml = hasChildren ? `<ul class="sidebar-menu sidebar-menu--nested">${this._renderSidebarNodes(n.children, currentFileName, currentFullPath)}</ul>` : '';
            const active = this._isLinkActive(n, currentFileName) ? ' sidebar-link--active' : '';
            const caretHtml = hasChildren ? `<button class="sidebar-caret" type="button" aria-label="Expand section" tabindex="0">\u25b8</button>` : '';
            const link = `<a href="${href}" data-file="${esc(n.file || '')}" data-id="${esc(n.id || '')}" class="sidebar-link${active}">${esc(n.text)}</a>`;
            if (!hasChildren) return `<li class="sidebar-item">${link}</li>`;
            return `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-collapsed="true">
  <div class="sidebar-item-row">${link}${caretHtml}</div>${childHtml}</li>`;
        }).join('');
    }

    _isLinkActive(n, currentFileName) {
        const nFile = (n.file || '').replace(/\.html$/i, '');
        if (nFile !== currentFileName) return false;
        if (this._activeHeadingId) return n.id === this._activeHeadingId;
        return !n.id;
    }

    _initSidebarToggles(container) {
        if (!container) return;
        container.querySelectorAll('.sidebar-item--collapsible:not([data-section])').forEach(li => {
            const caret = li.querySelector('.sidebar-caret');
            const header = li.querySelector('.sidebar-category-label');
            this._bindCollapsible(li, caret, header);
        });
    }

    _bindCollapsible(li, caret, header, onExpand) {
        const toggleFn = (e) => {
            if (onExpand && !li.dataset.loaded) {
                if (e) { e.preventDefault(); e.stopPropagation(); }
                onExpand(li);
                li.dataset.loaded = 'true';
                li.setAttribute('data-collapsed', 'false');
                if (caret) caret.textContent = '\u25be';
                this._initSidebarToggles(li);
                return;
            }
            if (e) { e.preventDefault(); e.stopPropagation(); }
            const isCollapsed = li.getAttribute('data-collapsed') !== 'false';
            li.setAttribute('data-collapsed', isCollapsed ? 'false' : 'true');
            if (caret) caret.textContent = isCollapsed ? '\u25be' : '\u25b8';
        };
        if (caret) {
            caret.addEventListener('click', toggleFn);
            caret.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleFn(e); }
            });
        }
        const headerIsLink = header && header.tagName === 'A';
        if (header && !headerIsLink) header.addEventListener('click', toggleFn);
    }

    _initBreadcrumbFade() {
        if (this._mode !== 'epub' && this._mode !== 'page-toc') return;
        const bc = this.navTree.querySelector('.breadcrumb');
        const tocTree = this.navTree.querySelector('.sidebar-menu');
        if (!bc || !tocTree || !this.navTree) return;
        this._io = new IntersectionObserver((entries) => {
            entries.forEach(e => {
                const rect = e.boundingClientRect;
                const root = e.rootBounds;
                bc.classList.toggle('breadcrumb--faded', rect.bottom < root.top);
            });
        }, { root: this.navTree, threshold: 0 });
        this._io.observe(tocTree);
    }

    _buildLibmapHtml() {
        if (!window.LIBRARY_CONFIG?.length) {
            return '<div class="sidebar-menu" style="padding:20px">Navigation unavailable</div>';
        }
        return '<ul class="sidebar-menu">' + this._renderLazySections() + '</ul>';
    }

    _renderLibmapMenu() {
        this.navTree.innerHTML = this._buildLibmapHtml();
        this._invalidateTrackingCache();
        this._initLazySections();
    }

    _renderLazySections() {
        return (window.LIBRARY_CONFIG || []).map(col => {
            const id = esc(col.id || '');
            const label = esc(col.label || col.title || col.id || '');
            const badge = col.badge ? ` <span class="sidebar-badge">${esc(col.badge)}</span>` : '';
            const hasGroups = (col.groups || []).length > 0;
            if (!hasGroups && col.path) {
                const ext = col.path.startsWith('http');
                const rawPath = col.path.replace(/^\//, '');
                const href = ext ? col.path : `?doc=${esc(rawPath)}`;
                const dataPath = ext ? '' : ` data-path="${esc('/' + rawPath)}"`;
                return `<li class="sidebar-item"><a href="${esc(href)}"${dataPath} class="sidebar-link"${ext ? ' target="_blank" rel="noopener"' : ''}>${label}${badge}</a></li>`;
            }
            if (hasGroups) {
                return `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-section="${id}" data-base="${esc(col.basePath || '')}" data-collapsed="true">
  <div class="sidebar-item-row"><span class="sidebar-category-label">${label}${badge}</span><button class="sidebar-caret" type="button" aria-label="Expand section" tabindex="0">▸</button></div>
</li>`;
            }
            return `<li class="sidebar-item"><span class="sidebar-category-label">${label}${badge}</span></li>`;
        }).join('');
    }

    _initLazySections() {
        this.navTree.querySelectorAll('.sidebar-item--collapsible[data-section]').forEach(li => {
            const header = li.querySelector('.sidebar-category-label');
            const caret = li.querySelector('.sidebar-caret');
            this._bindCollapsible(li, caret, header, (li) => {
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
            });
        });
    }

    _renderGroup(group) {
        const label = esc(group.label || '');
        const items = group.items || [];
        const groupPath = (group.path || '').replace(/^\//, '');
        if (!items.length) {
            if (!groupPath) return `<li class="sidebar-item"><span class="sidebar-category-label">${label}</span></li>`;
            const isExt = groupPath.startsWith('http');
            const href = isExt ? groupPath : `?doc=${esc(groupPath)}`;
            const dataPath = isExt ? '' : ` data-path="${esc('/' + groupPath)}"`;
            return `<li class="sidebar-item"><a href="${esc(href)}"${dataPath}${isExt ? ' target="_blank" rel="noopener"' : ''} class="sidebar-link">${label}</a></li>`;
        }
        const itemsHtml = items.map(item => {
            const rawPath = (item.path || '').replace(/^\//, '');
            const isExt = rawPath.startsWith('http');
            const href = isExt ? rawPath : `?doc=${esc(rawPath)}`;
            return `<li class="sidebar-item"><a href="${esc(href)}"${isExt ? ' target="_blank" rel="noopener"' : ''} data-path="${esc(rawPath ? '/' + rawPath : '')}" class="sidebar-link">${esc(item.label || item.title || '')}</a></li>`;
        }).join('');
        return `<li class="sidebar-item sidebar-item--category sidebar-item--collapsible" data-group-path="${esc(groupPath)}" data-collapsed="true">
  <div class="sidebar-item-row"><span class="sidebar-category-label">${label}</span><button class="sidebar-caret" type="button" aria-label="Expand section" tabindex="0">▸</button></div>
  <ul class="sidebar-menu sidebar-menu--nested">${itemsHtml}</ul>
</li>`;
    }

    _getPageHeadings() {
        if (this._mode === 'epub') {
            const currentFile = (state.doc || '').split('/').pop().replace(/\.html$/i, '');
            const jsonHeadings = (this._currentVol?.data?.headings || []).filter(h => (h.file || '').replace(/\.html$/i, '') === currentFile);
            const domHeadings = getDomHeadings($('#content'));
            let domIdx = 0;
            return jsonHeadings.map((jh) => {
                let id = jh.id;
                if (!id && domIdx < domHeadings.length) id = domHeadings[domIdx].id || null;
                domIdx++;
                return { level: jh.level, text: jh.text, id };
            }).filter(h => h.id);
        }
        return getDomHeadings($('#content')).map(h => ({
            level: parseInt(h.tagName[1]), text: h.textContent.trim(), id: h.id
        }));
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
        const nav = $('#toc-desktop-nav');
        if (!nav) return;
        nav.innerHTML = '';
        this._activeTocLink = null;
        const headings = this._getPageHeadings();
        if (!headings.length) { this._waitForHeadings(() => this._initTocRail()); return; }
        nav.innerHTML = this._renderTocTree(buildHeadingTree(headings));
        this._activeTocLink = null;
        if (this._scrollTrackingReady) {
            const activeId = getActiveHeadingId(getDomHeadings($('#content')), 200);
            if (activeId) this._updateTracking(activeId);
        }
    }

    _waitForHeadings(cb) {
        const content = $('#content');
        if (!content) return;
        const mo = new MutationObserver((mutations, observer) => {
            if (getDomHeadings(content).length) { observer.disconnect(); cb(); }
        });
        mo.observe(content, { subtree: true, attributes: true, attributeFilter: ['id'] });
    }

    _initScrollTracking() {
        if (this._scrollTrackingReady) return;
        const content = $('#content');
        if (!content) return;
        let headings = getDomHeadings(content);
        if (!headings.length) { this._waitForHeadings(() => this._initScrollTracking()); return; }
        this._scrollTrackingReady = true;
        let lastId = null;
        const measureHeadings = () => {
            this._headingTops = headings.map(h => h.getBoundingClientRect().top + scrollY);
        };
        const queueMeasureHeadings = () => {
            if (!this._headingResizeFrame) this._headingResizeFrame = requestAnimationFrame(() => {
                this._headingResizeFrame = 0;
                measureHeadings();
            });
        };
        measureHeadings();
        this._headingResizeHandler = queueMeasureHeadings;
        window.addEventListener('resize', this._headingResizeHandler, { passive: true });
        window.addEventListener('load', measureHeadings, { once: true });
        setTimeout(measureHeadings, 500);
        const track = () => {
            this._scrollFrame = 0;
            const activeId = this._getActiveHeadingIdFromTops(headings, 200);
            if (activeId !== lastId) { lastId = activeId; this._activeHeadingId = activeId; this._updateTracking(activeId); }
        };
        const onScroll = () => {
            if (!this._scrollFrame) this._scrollFrame = requestAnimationFrame(track);
        };
        if (window.onScrollFrame) {
            const off = window.onScrollFrame(track);
            off._isScrollFrameOff = true;
            this._tocScrollHandler = off;
        } else {
            window.addEventListener('scroll', onScroll, { passive: true });
            this._tocScrollHandler = onScroll;
        }
        this._scrollFrame = requestAnimationFrame(track);
    }

    _syncNavScroll(id) {
        if (innerWidth >= 997) return;
        if (!this.sidebar?.classList.contains('doc-sidebar--open')) return;
        if (!id || id === this._lastSyncedNavId) return;
        const active = this._activeSidebarLink || this.navTree?.querySelector('.sidebar-link.sidebar-link--active');
        if (!active) return;
        expandTo(active, this.navTree.querySelector('.sidebar-menu'));
        this._lastSyncedNavId = id;
        requestAnimationFrame(() => active.scrollIntoView({ block: 'center', behavior: 'auto' }));
    }

    _updateTracking(id) {
        this._updateSidebarTracking(id);
        this._updateTocRailTracking(id);
        this._syncNavScroll(id);
    }

    _updateSidebarTracking(id) {
        if (!this.navTree) return;
        const tree = this.navTree.querySelector('.sidebar-menu');
        if (!tree) return;
        if (this._activeSidebarLink && tree.contains(this._activeSidebarLink)) this._activeSidebarLink.classList.remove('sidebar-link--active');
        else tree.querySelector('.sidebar-link.sidebar-link--active')?.classList.remove('sidebar-link--active');
        this._activeSidebarLink = null;
        const currentFile = (state.doc || '').split('/').pop().replace(/\.html$/i, '') || 'index';
        const links = this._getSidebarTrackingCache(tree).links;
        let match = null;
        if (id) {
            match = links.find(a =>
                (a.dataset.file || '').replace(/\.html$/i, '') === currentFile && a.dataset.id === id
            );
        }
        if (!match) {
            match = links.find(a =>
                (a.dataset.file || '').replace(/\.html$/i, '') === currentFile && !a.dataset.id
            );
        }
        if (!match) {
            match = links.find(a =>
                (a.dataset.file || '').replace(/\.html$/i, '') === currentFile
            );
        }

        if (match) { match.classList.add('sidebar-link--active'); this._activeSidebarLink = match; expandTo(match, tree); }
    }

    _updateTocRailTracking(id) {
        const nav = $('#toc-desktop-nav');
        if (!nav?.innerHTML) return;
        if (this._activeTocLink && nav.contains(this._activeTocLink)) this._activeTocLink.classList.remove('theme-doc-toc-desktop-link__a--active');
        else nav.querySelector('.theme-doc-toc-desktop-link__a--active')?.classList.remove('theme-doc-toc-desktop-link__a--active');
        this._activeTocLink = null;
        if (!id) return;
        const match = [...nav.querySelectorAll('.theme-doc-toc-desktop-link__a')].find(a => a.getAttribute('href') === `#${id}`);
        if (match) { match.classList.add('theme-doc-toc-desktop-link__a--active'); this._activeTocLink = match; }
    }

    _invalidateTrackingCache() {
        this._sidebarTrackingCache = null;
        this._activeSidebarLink = null;
        this._activeTocLink = null;
        this._lastSyncedNavId = null;
    }

    _getSidebarTrackingCache(tree) {
        if (!this._sidebarTrackingCache || this._sidebarTrackingCache.tree !== tree) {
            this._sidebarTrackingCache = { tree, links: [...tree.querySelectorAll('.sidebar-link')] };
        }
        return this._sidebarTrackingCache;
    }

    _getActiveHeadingIdFromTops(headings, threshold = 200) {
        if (!headings.length) return null;
        const y = scrollY + threshold;
        for (let i = this._headingTops.length - 1; i >= 0; i--) {
            if (this._headingTops[i] <= y) return headings[i].id;
        }
        return headings[0]?.id || null;
    }

    _highlightCurrent(docPath) {
        if (this._mode === 'libmap') this._highlightLibmapCurrent();
        else this._highlightFileCurrent(docPath);
    }

    _highlightFileCurrent(docPath) {
        const currentFile = (docPath || '').split('/').pop().replace(/\.html$/i, '');
        const currentHash = location.hash.slice(1);
        const tree = this.navTree?.querySelector('.sidebar-menu');
        if (!tree) return;

        const links = [...tree.querySelectorAll('.sidebar-link')];
        const best = this._pickBestLink(links, currentFile, currentHash);
        if (best) {
            best.classList.add('sidebar-link--active');
            expandTo(best, tree);
            if (innerWidth >= 997) {
                requestAnimationFrame(() => best.scrollIntoView({ block: 'center', behavior: 'instant' }));
            }
        }
    }

    _pickBestLink(links, currentFile, currentHash) {
        let best = null, bestScore = 0;
        links.forEach(a => {
            const file = (a.dataset.file || '').replace(/\.html$/i, '');
            const id = a.dataset.id || '';
            const href = a.getAttribute('href') || '';
            let score = 0;
            if (file === currentFile) {
                score = 1;
                if (id && currentHash && id === currentHash) score = 3;
                else if (!id && !currentHash) score = 2;
            }
            if (!file && href.startsWith('#') && currentHash && href.slice(1) === currentHash) score = 3;
            if (score > bestScore) { bestScore = score; best = a; }
        });
        return best;
    }

    _highlightLibmapCurrent() {
        const currentPath = (state.doc || '').replace(/^\//, '').replace(/\/$/, '');
        if (!currentPath) return;
        let found = false;
        this.navTree.querySelectorAll('a[data-path]').forEach(link => {
            if (found) return;
            let hrefPath = '';
            const rawHref = link.getAttribute('href') || '';
            if (rawHref.startsWith('?doc=')) hrefPath = rawHref.slice(5).replace(/\/$/, '');
            else try { hrefPath = new URL(rawHref, location.origin).pathname.replace(/\/$/, ''); } catch { }
            const dataPath = (link.dataset.path || '').replace(/^\//, '').replace(/\/$/, '');
            if (dataPath !== currentPath && hrefPath !== currentPath) return;
            found = true;
            link.classList.add('sidebar-link--active');
            expandTo(link, this.navTree);
            requestAnimationFrame(() => link.scrollIntoView({ block: 'nearest', behavior: 'smooth' }));
        });
    }

    _bindSidebarLinkClicks(docPath) {
        if (!this.navTree) return;
        if (this._sidebarClickHandler) {
            this.navTree.removeEventListener('click', this._sidebarClickHandler);
        }
        const normalizePath = p => (p || '').replace(/^\//, '').replace(/\.html$/i, '').replace(/\/$/, '');

        this._sidebarClickHandler = (e) => {
            const el = e.target.nodeType === 1 ? e.target : e.target.parentElement;
            const link = el?.closest('.sidebar-link');
            if (!link) return;
            const href = link.getAttribute('href') || '';

            if (href.startsWith('#')) {
                const id = href.slice(1);
                if (id) {
                    e.preventDefault();
                    const el = document.getElementById(id);
                    if (el) {
                        scrollToEl(el);
                        const url = new URL(location.href);
                        url.hash = id;
                        history.replaceState(null, '', url.toString());
                    }
                }
                return;
            }

            if (href.startsWith('?doc=')) {
                const url = new URL(href, location.href);
                const doc = url.searchParams.get('doc');
                const hash = url.hash.slice(1);
                const currentDoc = normalizePath(state.doc);
                const targetDoc = normalizePath(doc);

                if (doc && targetDoc === currentDoc && hash) {
                    e.preventDefault();
                    const el = document.getElementById(hash);
                    if (el) {
                        scrollToEl(el);
                        history.pushState(null, '', href);
                    }
                    return;
                }

                if (hash) {
                    sessionStorage.setItem('__reader_pending_anchor', hash);
                    sessionStorage.setItem('__reader_pending_doc', doc);
                }
            }
        };
        this.navTree.addEventListener('click', this._sidebarClickHandler);
    }

    _scrollToPendingAnchor() {
        const hash = sessionStorage.getItem('__reader_pending_anchor');
        const doc = sessionStorage.getItem('__reader_pending_doc');
        if (!hash) return;
        sessionStorage.removeItem('__reader_pending_anchor');
        sessionStorage.removeItem('__reader_pending_doc');

        const normalize = p => (p || '').replace(/^\//, '').replace(/\.html$/i, '').replace(/\/$/, '');
        if (doc && normalize(doc) !== normalize(state.doc)) return;

        const tryScroll = () => {
            const el = document.getElementById(hash);
            if (el) { scrollToEl(el); return true; }
            return false;
        };
        if (!tryScroll()) {
            requestAnimationFrame(() => {
                if (!tryScroll()) setTimeout(tryScroll, 150);
            });
        }
    }
}
