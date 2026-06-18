const C = window.ReaderCore;
const { $, $$, esc, cssEsc, syncFill, detectVolume, scrollToEl, onScrollFrame, PathResolver, resolveLibraryPath } = C;
const sameDoc = C.sameDocValue;
const fetchReaderResource = C.fetchReaderResource;

const state = {
    fs: parseFloat(localStorage.fontSize) || 1,
    lh: parseFloat(localStorage.lineHeight) || 2.0,
    rs: localStorage.rememberScroll !== 'false',
    sb: false,
    th: localStorage.theme || 'light',
    doc: null,
    mob: innerWidth < 768,
    scrollSaveTimer: null
};
window.ReaderState = state;

const resolveDocLink = (href, base = '') => PathResolver ? PathResolver.resolve(base || state.doc || '', href) : null;

const isFootnoteLink = a => {
    const href = a.getAttribute('href') || '';
    if (!href.includes('#') || /^(https?:|\/\/)/i.test(href)) return false;
    return !!(a.closest('sup') || a.querySelector('sup'));
};

const injectContentLang = (parsed, content) => {
    if (!content) return '';
    const source = parsed?.body?.querySelector('div.prose#content') || parsed?.body || null;
    const lang = [
        parsed?.documentElement?.getAttribute('lang'),
        parsed?.body?.getAttribute('lang'),
        source?.getAttribute?.('lang')
    ].find(v => String(v || '').trim())?.trim() || '';
    if (lang) {
        content.setAttribute('lang', lang);
        return lang
    }
    else {
        content.removeAttribute('lang');
        return ''
    }
};

/* ===== 脚注弹窗 ===== */
class FootnotePopup {
    constructor() {
        this.tip = $('#fn-tooltip');
        this.active = false;
        this.trigger = null;
        this.cache = new Map();
        this.bag = new C.EventBag();
        this.offScroll = null;
    }

    async show(a, event) {
        if (!this.tip) return;
        this.forceClose();
        const href = a.getAttribute('href') || '';
        const parsed = this.parseHref(href);
        if (!parsed) return;
        this.trigger = a;
        this.renderState(parsed.cross ? 'loading-cross' : 'loading');
        this.position();
        this.tip.classList.add('popover--visible');
        this.active = true;
        this.bag.on(document, 'click', e => this.dismiss(e), true);
        this.bag.on(document, 'keydown', e => this.dismiss(e));
        this.offScroll = onScrollFrame(() => this.active && this.position());

        const result = await this.resolveTarget(parsed);
        this.render(result?.block || this.linkFallback(a), href, parsed.cross);
        requestAnimationFrame(() => this.position(event));
    }

    parseHref(href) {
        if (href.startsWith('#')) return { targetId: href.slice(1), pageUrl: null, cross: false };
        const i = href.indexOf('#');
        if (i < 0) return null;
        const before = href.slice(0, i);
        const targetId = href.slice(i + 1);
        const resolved = resolveDocLink(before, state.doc ? state.doc.replace(/\/[^/]*$/, '/') : '');
        const pageUrl = resolved?.type === 'doc' ? resolved.docPath : C.resolveUrl(before);
        return { targetId, pageUrl, cross: true };
    }

    async resolveTarget({ targetId, pageUrl, cross }) {
        if (cross && pageUrl) {
            let parsed = this.cache.get(pageUrl);
            if (!parsed) {
                try {
                    const ctrl = new AbortController();
                    const t = setTimeout(() => ctrl.abort(), 3000);
                    const loaded = await fetchReaderResource(pageUrl, { signal: ctrl.signal });
                    clearTimeout(t);
                    const res = loaded.res;
                    if (!res.ok) return null;
                    parsed = new DOMParser().parseFromString(await res.text(), 'text/html');
                    this.cache.set(pageUrl, parsed);
                    if (loaded.path !== pageUrl) this.cache.set(loaded.path, parsed);
                } catch { return null; }
            }
            const target = parsed.getElementById(targetId) || parsed.querySelector(`a[name="${cssEsc(targetId)}"]`);
            return target ? { target, block: this.toBlock(target) } : null;
        }
        const target = document.getElementById(targetId) || document.querySelector(`a[name="${cssEsc(targetId)}"]`);
        return target ? { target, block: this.toBlock(target) } : null;
    }

    toBlock(target) {
        const notes = '.fni, .footnote, .endnote, .fn, .note';
        const blocks = 'li,dd,dt,p,blockquote,pre,figure,figcaption,table,thead,tbody,tfoot,tr,td,th,section,article,aside,div,h1,h2,h3,h4,h5,h6';
        const doc = target.ownerDocument || document;
        const isContainer = el => !el || el === doc.body || el === doc.documentElement || el.id === 'content' || el.id === 'main' || /^(prose|doc-content|doc-main|doc-main-inner)$/.test(el.className);
        const usable = el => el && !isContainer(el) && (el.textContent || '').trim();
        if (target.matches?.(notes) || (target.matches?.(blocks) && usable(target))) return target;
        const block = target.closest(`${notes},${blocks}`);
        if (usable(block)) return block;
        return this.lineFallback(target);
    }

    lineFallback(target) {
        const parent = target.parentNode;
        if (!parent) return null;
        const doc = target.ownerDocument || document;
        const frag = doc.createDocumentFragment();
        const boundary = n => n.nodeType === 1 && (n.tagName === 'BR' || n.matches?.('li,dd,dt,p,blockquote,pre,figure,figcaption,table,thead,tbody,tfoot,tr,td,th,section,article,aside,div,h1,h2,h3,h4,h5,h6'));
        const nodes = [];
        for (let n = target.previousSibling; n; n = n.previousSibling) { if (boundary(n)) break; nodes.unshift(n); }
        nodes.push(target);
        for (let n = target.nextSibling; n; n = n.nextSibling) { if (boundary(n)) break; nodes.push(n); }
        nodes.forEach(n => frag.appendChild(n.cloneNode(true)));
        return (frag.textContent || '').trim() ? frag : null;
    }

    linkFallback(a) {
        const frag = document.createDocumentFragment();
        frag.appendChild(a.cloneNode(true));
        return frag;
    }

    render(block, href, cross) {
        const viewer = $('.popover__body', this.tip);
        const jump = $('.popover__jump', this.tip);
        if (!viewer) return;
        const clone = block.cloneNode(true);
        $$('[id]', clone).forEach(el => el.removeAttribute('id'));
        viewer.replaceChildren(clone);
        if (jump) {
            if (cross) {
                const resolved = resolveDocLink(href, state.doc ? state.doc.replace(/\/[^/]*$/, '/') : '');
                jump.href = resolved?.type === 'doc' ? resolved.href : C.resolveUrl(href);
            } else {
                jump.href = href;
            }
            jump.textContent = cross ? 'Go to note (other page)' : 'Jump to footnote';
            jump.classList.toggle('popover__jump--cross', cross);
            jump.style.display = '';
            jump.onclick = () => this.forceClose();
        }
    }

    renderState(type) {
        const viewer = $('.popover__body', this.tip);
        if (!viewer) return;
        const msgs = { loading: '\u52a0\u8f7d\u4e2d...', 'loading-cross': '\u52a0\u8f7d\u8de8\u9875\u6ce8\u91ca\u4e2d...', error: '\u672a\u627e\u5230\u5bf9\u5e94\u6ce8\u91ca', 'error-cross': '\u8de8\u9875\u6ce8\u91ca\u52a0\u8f7d\u5931\u8d25' };
        viewer.innerHTML = `<div style="color:${type.startsWith('error') ? 'var(--accent)' : 'var(--text-3)'};font-size:13px;padding:4px 0;">${msgs[type]}</div>`;
    }

    position() {
        if (!this.trigger || !this.tip) return;
        const rect = this.trigger.getBoundingClientRect();
        const tipW = 340, maxH = Math.min(320, innerHeight * 0.45);
        let left = rect.right + 8;
        if (left + tipW > innerWidth - 12) left = Math.max(12, rect.left - tipW - 8);
        const minTop = scrollY + 4, maxTop = scrollY + innerHeight - maxH - 4;
        const rawTop = rect.top + scrollY - 10;
        this.tip.style.top = Math.min(Math.max(rawTop, minTop), Math.max(minTop, maxTop)) + 'px';
        this.tip.style.left = left + 'px';
        this.tip.style.maxHeight = maxH + 'px';
    }

    dismiss(e) {
        if (e?.type === 'keydown' && e.key !== 'Escape') return;
        if (e?.type === 'click' && this.tip?.contains(e.target)) return;
        this.forceClose();
    }

    forceClose() {
        if (!this.active) return;
        this.tip?.classList.remove('popover--visible');
        $('.popover__body', this.tip)?.replaceChildren();
        const jump = $('.popover__jump', this.tip);
        if (jump) jump.style.display = 'none';
        this.active = false;
        this.trigger = null;
        this.bag.clear();
        if (this.offScroll) this.offScroll();
        this.offScroll = null;
    }
}

/* ===== 主应用 ===== */
class ReaderApp {
    constructor() {
        this.popup = new FootnotePopup();
        this.resizeTimer = null;
        this.siteTitle = document.title;
    }

    init() {
        $('#lsidebar')?.classList.add('doc-sidebar');
        this.applyTheme(state.th);
        this.applyFont(state.fs, false);
        this.applyLineHeight(state.lh, false);
        window.__NAV__ = new MenuManager();
        window.__NAV__.init();
        window.__PAGE_BAR__ = new PageBarManager();
        window.__PAGE_BAR__.init();
        this.buildWelcomeCards();
        this.bindEvents();
        this.handleResize();
        const initialDoc = (new URLSearchParams(location.search).get('doc') || '') + location.hash;
        initialDoc ? this.loadDoc(initialDoc) : this.showHome(false);
    }

    normalizeDocPath(path) { return String(path || '').replace(/#.*$/, ''); }

    updateDesktopToc(clear = false) {
        $('#toc-desktop').style.display = innerWidth <= 997 ? 'none' : '';
        if (clear) $('#toc-desktop-nav').innerHTML = '';
    }

    applyTheme(theme) {
        document.documentElement.dataset.theme = theme;
        localStorage.theme = theme;
        const isDark = theme === 'dark';
        $$('.icon-sun').forEach(el => el.style.display = isDark ? 'block' : 'none');
        $$('.icon-moon').forEach(el => el.style.display = isDark ? 'none' : 'block');
        this.setIndicator('#mobile-theme-indicator', isDark);
    }

    applyFont(value, save = true) {
        state.fs = Math.max(0.75, Math.min(1.5, value));
        document.documentElement.style.setProperty('--fs-user', Math.round(16 * state.fs) + 'px');
        if (save) localStorage.setItem('fontSize', state.fs);
        ['#font-slider', '#mobile-font-slider'].forEach(sel => {
            const el = $(sel);
            if (el) { el.value = state.fs; syncFill(el); }
        });
    }

    applyLineHeight(value, save = true) {
        state.lh = Math.max(1.4, Math.min(2.6, Math.round(value * 10) / 10));
        document.documentElement.style.setProperty('--lh-user', state.lh);
        if (save) localStorage.setItem('lineHeight', state.lh);
        ['#lh-slider', '#mobile-lh-slider'].forEach(sel => {
            const el = $(sel);
            if (el) { el.value = state.lh; syncFill(el); }
        });
    }

    setIndicator(sel, active) {
        const el = $(sel);
        if (!el) return;
        el.textContent = active ? '\u25cf' : '\u25cb';
        el.style.color = active ? 'var(--accent)' : 'var(--text-3)';
    }

    buildWelcomeCards() {
        const grid = $('#library-cards');
        if (!grid || !window.LIBRARY_CONFIG) return;
        grid.replaceChildren();
        window.LIBRARY_CONFIG.forEach(col => {
            const card = document.createElement('a');
            card.className = 'card';
            card.href = '#';
            card.dataset.section = col.id || '';
            card.dataset.path = resolveLibraryPath?.(col, null, col) || '';
            card.innerHTML = `<div class="card__tag">${esc(col.label)}${col.badge ? ' &middot; ' + esc(col.badge) : ''}</div><div class="card__heading">${esc(col.title || col.label)}</div><div class="card__body">${esc(col.desc || '\u70b9\u51fb\u67e5\u770b\u76ee\u5f55')}</div>`;
            grid.appendChild(card);
        });
    }

    bindEvents() {
        $('#sidebar-toggle')?.addEventListener('click', () => this.toggleSidebar());
        $('#sidebar-backdrop')?.addEventListener('click', () => this.closeSidebar());
        $('#sidebar-close-btn')?.addEventListener('click', () => this.closeSidebar());

        const mobileToggle = $('#mobile-menu-toggle');
        const toggleMenu = e => {
            e.preventDefault(); e.stopPropagation();
            const menu = $('#mobile-menu');
            if (!menu) return;
            menu.style.position = 'fixed';
            menu.style.top = 'calc(var(--nav-h) + 6px)';
            menu.classList.toggle('dropdown--open');
            if (menu.classList.contains('dropdown--open')) this.updateMobileMenuIndicators();
        };
        mobileToggle?.addEventListener('click', toggleMenu);
        mobileToggle?.addEventListener('touchend', toggleMenu, { passive: false });

        this.bindStepper('fs', 0.05, v => this.applyFont(v), ['font-dec-btn', 'mobile-font-dec'], ['font-inc-btn', 'mobile-font-inc'], ['font-slider', 'mobile-font-slider']);
        this.bindStepper('lh', 0.1, v => this.applyLineHeight(v), ['lh-dec-btn', 'mobile-lh-dec'], ['lh-inc-btn', 'mobile-lh-inc'], ['lh-slider', 'mobile-lh-slider']);
        $('#remember-btn')?.addEventListener('click', () => this.toggleRemember());
        $('#mobile-remember')?.addEventListener('click', () => this.toggleRemember());
        ['theme-btn', 'sidebar-theme-btn', 'mobile-theme'].forEach(id => {
            $('#' + id)?.addEventListener('click', () => this.applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'));
        });

        window.addEventListener('resize', () => {
            clearTimeout(this.resizeTimer);
            this.resizeTimer = setTimeout(() => this.handleResize(), 100);
        }, { passive: true });
        window.addEventListener('popstate', () => this.handlePopState());
        document.addEventListener('click', e => this.handleDocumentClick(e));
        document.addEventListener('keydown', e => this.handleKeydown(e));
        onScrollFrame(() => this.updateScrollState());
    }

    bindStepper(key, step, apply, decIds, incIds, sliderIds) {
        decIds.forEach(id => $('#' + id)?.addEventListener('click', () => apply(state[key] - step)));
        incIds.forEach(id => $('#' + id)?.addEventListener('click', () => apply(state[key] + step)));
        sliderIds.forEach(id => $('#' + id)?.addEventListener('input', e => apply(parseFloat(e.target.value))));
    }

    toggleRemember() {
        state.rs = !state.rs;
        localStorage.rememberScroll = state.rs;
        $('#remember-btn')?.classList.toggle('clean-btn--active', state.rs);
        this.setIndicator('#mobile-remember-indicator', state.rs);
        if (!state.rs && state.doc) localStorage.removeItem('scroll_' + state.doc);
    }

    updateMobileMenuIndicators() {
        this.setIndicator('#mobile-remember-indicator', state.rs);
        this.setIndicator('#mobile-theme-indicator', document.documentElement.dataset.theme === 'dark');
        ['#mobile-font-slider', '#mobile-lh-slider'].forEach(sel => { const el = $(sel); if (el) syncFill(el); });
    }

    handleResize() {
        const wasMobile = state.mob;
        state.mob = innerWidth < 768;
        if (wasMobile !== state.mob) $('#mobile-menu')?.classList.remove('dropdown--open');
        this.applySidebar();
        this.updateDesktopToc();
    }

    updateScrollState() {
        const max = document.documentElement.scrollHeight - innerHeight;
        const progress = $('#progress-bar');
        if (progress) progress.style.width = (max > 0 ? (scrollY / max) * 100 : 0) + '%';
        clearTimeout(state.scrollSaveTimer);
        state.scrollSaveTimer = setTimeout(() => {
            if (state.rs && state.doc) localStorage.setItem('scroll_' + state.doc, String(scrollY));
        }, 300);
    }

    toggleSidebar() { state.sb = !state.sb; this.applySidebar(); }
    openSidebar() { state.sb = true; this.applySidebar(); }
    closeSidebar() { state.sb = false; this.applySidebar(); }

    applySidebar() {
        const sidebar = $('#lsidebar'), backdrop = $('#sidebar-backdrop');
        if (!sidebar) return;
        const mobile = innerWidth < 997;
        if (mobile) {
            sidebar.classList.toggle('open', state.sb);
            sidebar.classList.toggle('doc-sidebar--open', state.sb);
            sidebar.style.pointerEvents = state.sb ? 'auto' : 'none';
            backdrop?.classList.toggle('visible', state.sb);
            backdrop?.classList.toggle('sidebar-overlay--visible', state.sb);
        } else {
            sidebar.classList.remove('open', 'doc-sidebar--open');
            sidebar.style.pointerEvents = '';
            backdrop?.classList.remove('visible', 'sidebar-overlay--visible');
        }
    }

    clearDynamicStyles() { 
        $$('.dynamic-doc-css, .dynamic-doc-style').forEach(el => el.remove()); 
    }

    async loadDoc(rawPath) {
        let docPath = PathResolver.path('', rawPath);
        this.showLoading(docPath);
        this.clearDynamicStyles();
        this.updateBreadcrumb(docPath, null);
        try {
            const loaded = await fetchReaderResource(docPath);
            const res = loaded.res;
            if (!res.ok) throw new Error(String(res.status));
            const html = await res.text();
            const hash = rawPath.includes('#') ? rawPath.split('#')[1] : '';
            const actualUrl = loaded.url || loaded.path || docPath;
            if (!/\/$/i.test(docPath) && (/\/$/i.test(actualUrl))) docPath = docPath.replace(/\/([^/]+\.[^/]+|index)$/ , '') + '/';
            history.replaceState(history.state || {}, '', PathResolver.makeHref(docPath,hash));
            await this.renderDoc(html, hash ? docPath+'#'+hash : docPath, actualUrl);
            this.revealLoadedContent();
        } catch (error) {
            this.showError(docPath, error.message);
        }
    }

    showLoading(docPath) {
        window.__PAGE_BAR__?.reset?.();
        this.popup.forceClose();
        $('#welcome-view').style.display = 'none';
        $('#article-view').style.display = 'block';
        this.updateDesktopToc(true);
        $('#content').style.display = 'none';
        $('#doc-footer').style.display = 'none';
        const skeleton = $('#doc-skeleton');
        skeleton.classList.add('active');
        skeleton.style.display = 'block';
        skeleton.style.opacity = '1';
        state.doc = docPath;
    }

    revealLoadedContent() {
        const skeleton = $('#doc-skeleton');
        skeleton.style.transition = 'opacity 150ms ease';
        skeleton.style.opacity = '0';
        requestAnimationFrame(() => {
            skeleton.classList.remove('active');
            skeleton.style.display = 'none';
            skeleton.style.opacity = '1';
            const content = $('#content');
            content.style.display = 'block';
            content.style.opacity = '0';
            content.style.transition = 'opacity 200ms ease';
            requestAnimationFrame(() => {
                content.style.opacity = '1';
                $('#doc-footer').style.display = 'flex';
                this.restorePositionOrHash();
            });
        });
    }

    async renderDoc(html, docPath, finalUrl) {
        const parsed = new DOMParser().parseFromString(html, 'text/html');
        this.rewriteDocUrls(parsed, docPath);
        this.rewriteDocAssets(parsed, finalUrl);
        await this.injectDocStyles(parsed, finalUrl);
        const content = $('#content');
        const lang = injectContentLang(parsed, content);
        content.innerHTML = (parsed.body.querySelector('div.prose#content') || parsed.body).innerHTML;
        this.prepareAnchors(content);
        state.doc = docPath;
        const title = parsed.querySelector('title')?.textContent?.trim();
        document.title = title ? title + ' - ' + this.siteTitle : this.siteTitle;
        window.__NAV__?.reinit(docPath);
        this.updateBreadcrumb(docPath, title);
        this.fixOverflow(content);
        this.updatePrevNext(docPath);
        window.__PAGE_BAR__?.scanContent(content, lang);

        this.updateDesktopToc();
    }

    async injectDocStyles(parsed, finalUrl) {
        $$('.dynamic-doc-style').forEach(el => el.remove());
        let waits=[];
        parsed.querySelectorAll('link[rel="stylesheet"]').forEach(link => {
            const href = link.getAttribute('href');
            if (!href || /\/?reader\.css(?:[?#].*)?$/i.test(href)) return;
            const el = link.cloneNode(false);
            el.classList.add('dynamic-doc-style');
            el.href = PathResolver.resolveResource(finalUrl, href);
            waits.push(new Promise(resolve => { el.onload = el.onerror = resolve; setTimeout(resolve, 5000); }));
            document.head.appendChild(el);
        });
        await Promise.allSettled(waits);
        parsed.querySelectorAll('style').forEach(style => {
            const el = style.cloneNode(true);
            el.classList.add('dynamic-doc-style');
            document.head.appendChild(el);
        });
    }

    rewriteDocUrls(parsed, finalUrl) {
        parsed.querySelectorAll('a[href]').forEach(a => {
            const href = a.getAttribute('href') || '';
            const resolved = PathResolver.resolve(finalUrl || state.doc || '', href);
            if (resolved?.type === 'doc') a.setAttribute('href', resolved.href);
        });
    }

    rewriteDocAssets(parsed, finalUrl) {
        parsed.querySelectorAll('img[src],script[src],iframe[src],video[src],audio[src],source[src],track[src]').forEach(el => {
            el.setAttribute('src', PathResolver.resolveResource(finalUrl || state.doc || '', el.getAttribute('src')));
        });
        parsed.querySelectorAll('[srcset]').forEach(el => {
            const srcset = (el.getAttribute('srcset') || '').split(',').map(part => {
                const bits = part.trim().split(/\s+/), url = bits.shift();
                return [PathResolver.resolveResource(finalUrl || state.doc || '', url), ...bits].join(' ');
            }).join(', ');
            el.setAttribute('srcset', srcset);
        });
    }

    prepareAnchors(content) {
        content.querySelectorAll('a[name]').forEach(a => {
            if (a.parentElement && !a.parentElement.id) a.parentElement.id = a.getAttribute('name');
        });
        const skip = new Set(['Karl Marx', 'Friedrich Engels', 'Karl Marx/Friedrich Engels']);
        content.querySelectorAll('h1,h2,h3,h4,h5,h6').forEach((h, i) => {
            const text = h.textContent.trim();
            if (skip.has(text)) return;
            if (!h.id) h.id = 'h' + i;
            if (!h.querySelector('.anchor')) h.insertAdjacentHTML('beforeend', `<a class="anchor" href="#${esc(h.id)}" aria-hidden="true" hidden=""></a>`);
        });
    }

    fixOverflow(content) {
        content.querySelectorAll('table').forEach(table => {
            if (table.parentElement?.classList.contains('table-wrapper')) return;
            const wrapper = document.createElement('div');
            wrapper.className = 'table-wrapper';
            table.before(wrapper);
            wrapper.appendChild(table);
        });
        content.querySelectorAll('img').forEach(img => {
            img.style.maxWidth = '100%';
            img.style.height = 'auto';
            img.style.display = 'block';
        });
    }

    restorePositionOrHash() {
        const hash = location.hash.slice(1);
        if (hash) {
            const el = document.getElementById(hash) || document.querySelector(`[name="${cssEsc(hash)}"]`);
            if (!window.__PAGE_BAR__?.highlightPageAnchor(hash) && el) scrollToEl(el);
            return;
        }
        if (state.rs && state.doc) {
            const saved = parseInt(localStorage.getItem('scroll_' + state.doc), 10);
            if (Number.isFinite(saved)) window.scrollTo(0, saved);
        } else {
            window.scrollTo(0, 0);
        }
    }

    updateBreadcrumb(path, title) {
        const bar = $('#doc-pathbar');
        if (!bar) return;
        const parts = [];
        const displayPath = path.replace(/^\/+/, '').replace(/[?#].*$/, '');
        const pieces = displayPath.split('/').filter(Boolean);
        const currentVol = window.__NAV__?.currentVol || null;
        const currentVolPath = currentVol ? C.normalizePath(resolveLibraryPath(currentVol.col, currentVol.group, currentVol.item).replace(/[?#].*$/, '')) : '';
        for (let i = 0; i < pieces.length - 1; i++) {
            const sub = (path.startsWith('/') ? '/' : '') + pieces.slice(0, i + 1).join('/');
            // 目录层级面包屑：中间层级链接到对应目录
            const subDir = C.normalizePath(sub);
            const hit = detectVolume(sub);
            const final = (currentVolPath && !(subDir === currentVolPath) && hit) ? resolveLibraryPath(hit.col, hit.group, hit.item).replace(/[?#].*$/, '') : (sub + '/');
            if (parts.length) parts.push('<span class="crumb-sep">/</span>');
            parts.push(`<a class="crumb" href="${esc(PathResolver.makeHref(final))}">${esc(pieces[i])}</a>`);
        }
        if (pieces.length) {
            if (parts.length) parts.push('<span class="crumb-sep">/</span>');
            parts.push(`<span class="crumb current">${esc(pieces.at(-1))}</span>`);
        }
        if (title) parts.push(`<span class="crumb-sep">/</span><span class="crumb current">${esc(title)}</span>`);
        bar.innerHTML = parts.join('') || '<span style="color:var(--text-3);">Library</span>';
    }

    async updatePrevNext(path) {
        const prev = $('#prev-btn'), next = $('#next-btn');
        [prev, next].forEach(btn => { if (btn) btn.style.display = 'none'; });
        const dir = path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : '';
        const file = path.split('/').pop();
        const manifest = await this.findManifest(path, dir);
        if (manifest?.items?.length) {
            const i = this.findManifestIndex(manifest.items, path, file);
            if (i >= 0) {
                if (i > 0) this.setupPagination(prev, this.manifestItemPath(manifest.items[i - 1], manifest.dir), manifest.items[i - 1].title, 'prev');
                if (i < manifest.items.length - 1) this.setupPagination(next, this.manifestItemPath(manifest.items[i + 1], manifest.dir), manifest.items[i + 1].title, 'next');
                return;
            }
        }
        this.setupFallbackPagination(dir, file, prev, next);
    }

    async findManifest(path, dir) {
        const col = window.__NAV__.currentVol?.col || null;
        const candidates = [...new Set([dir, resolveLibraryPath?.(col, null, col)?.replace(/^\/+|\/+$/g, ''), location.pathname.split('/').slice(1, -1).join('/')].filter(Boolean))];
        for (const c of candidates) {
            try {
                const raw = await C.VolDataStore.fetchVolData(c);
                const items = Array.isArray(raw) ? raw : raw?.files;
                if (items?.length) return { items, dir: c };
            } catch { }
        }
        return null;
    }

    findManifestIndex(items, path, file) {
        const cleanPath = path.replace(/\.x?html?(?:#.*)?$/i, '');
        const cleanFile = file.replace(/\.x?html?(?:#.*)?$/i, '');
        return items.findIndex(item => {
            const f = item.file || item.path || item.url || item.filename || '';
            const src = item.source_file || item.filename || '';
            const candidates = [f, src, f.split('/').pop(), src.split('/').pop()].map(x => x.replace(/\.x?html?(?:#.*)?$/i, ''));
            return sameDoc(f, path) || sameDoc(f, file) || candidates.some(c => sameDoc(c, cleanPath) || sameDoc(c, cleanFile));
        });
    }

    manifestItemPath(item, baseDir) {
        const f = item.file || item.path || item.url || item.filename || '';
        const resolved = resolveDocLink(f, baseDir ? baseDir + '/' : '');
        return resolved?.type === 'doc' ? resolved.docPath : this.normalizeDocPath(f);
    }

    setupFallbackPagination(dir, file, prev, next) {
        const match = file.split('#')[0].match(/^(.*?)(\d+)(\.[^.]+)$/);
        if (!match) return;
        const [, prefix, number, ext] = match;
        const make = n => [dir, prefix + String(n).padStart(number.length, '0') + ext].filter(Boolean).join('/');
        const current = parseInt(number, 10);
        const tryBtn = async (btn, p, kind) => {
            try {
                const { res, path: lp } = await fetchReaderResource(p, { method: 'HEAD', mode: 'same-origin' });
                if (res.ok) this.setupPagination(btn, lp, null, kind);
            } catch { }
        };
        if (current > 1) tryBtn(prev, make(current - 1), 'prev');
        tryBtn(next, make(current + 1), 'next');
    }

    setupPagination(btn, path, title, kind) {
        if (!btn) return;
        const label = $('.pagination-link__label', btn);
        const dir = $('.pagination-link__dir', btn);
        btn.style.display = 'flex';
        if (dir) dir.textContent = kind === 'prev' ? '\u2190 Previous' : 'Next \u2192';
        const setTitle = v => {
            const text = v && v.length > 40 ? v.slice(0, 39) + '\u2026' : (v || '');
            if (label) { label.textContent = text; label.title = v || ''; }
        };
        setTitle(title);
        if (!title) {
            fetchReaderResource(path.split('#')[0]).then(({ res }) => res.text()).then(html => {
                setTitle(new DOMParser().parseFromString(html, 'text/html').querySelector('title')?.textContent?.trim());
            }).catch(() => { });
        }
        btn.onclick = e => {
            e.preventDefault();
            const normalized = this.normalizeDocPath(path);
            history.pushState({}, '', PathResolver.makeHref(normalized));
            this.loadDoc(normalized);
        };
    }

    showError(path, message) {
        $('#doc-skeleton').style.display = 'none';
        this.updateDesktopToc(true);
        const content = $('#content');
        content.innerHTML = `<p style="color:var(--text-2);padding:40px 0;">Cannot load <code>${esc(path)}</code><br><small>${esc(message)}</small></p>`;
        content.style.display = 'block';
        content.style.opacity = '1';
    }

    showHome(push = true) {
        this.clearDynamicStyles();
        this.popup.forceClose();
        window.__PAGE_BAR__?.reset?.();
        const skeleton = $('#doc-skeleton');
        if (skeleton) { skeleton.classList.remove('active'); skeleton.style.display = 'none'; skeleton.style.opacity = '1'; }
        const content = $('#content');
        if (content) { content.innerHTML = ''; content.style.display = 'block'; content.style.opacity = '1'; }
        $('#doc-footer').style.display = 'none';
        $('#article-view').style.display = 'none';
        $('#welcome-view').style.display = 'block';
        this.updateDesktopToc(true);
        document.title = this.siteTitle;;
        state.doc = null;
        if (push) history.pushState({}, '', location.pathname);
        window.__NAV__?.reinit(null);
        window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
    }

    handlePopState() {
        const docPath = (new URLSearchParams(location.search).get('doc') || '') + location.hash;
        if (!docPath) this.showHome(false);
        else if (!sameDoc(docPath, state.doc)) this.loadDoc(docPath);
        else if (location.hash) {
            const hash = location.hash.slice(1);
            const el = document.getElementById(hash) || document.querySelector(`[name="${cssEsc(hash)}"]`);
            if (!window.__PAGE_BAR__?.highlightPageAnchor(hash) && el) scrollToEl(el);
        }
    }

    handleDocumentClick(event) {
        const target = event.target.nodeType === 1 ? event.target : event.target.parentElement;
        const menu = $('#mobile-menu'), toggle = $('#mobile-menu-toggle');
        const a = target?.closest('a');
        if (!a) {
            if (menu && !menu.contains(target) && !toggle?.contains(target)) menu.classList.remove('dropdown--open');
            return;
        }
        const welcomeCard = a.closest('#library-cards .card[data-section]');
        if (welcomeCard) {
            event.preventDefault();
            this.openSidebar();
            window.__NAV__?.expandSection(welcomeCard.dataset.section);
            $('#mobile-menu')?.classList.remove('dropdown--open');
            return;
        }
        const navTreeLink = a.closest('#nav-tree');
        if (navTreeLink && innerWidth < 997) this.closeSidebar();
        if (a.classList.contains('navbar__logo') || a.classList.contains('doc-sidebar__brand')) {
            event.preventDefault();
            this.showHome(true);
            this.closeSidebar();
            return;
        }
        if (isFootnoteLink(a)) {
            event.preventDefault();
            event.stopImmediatePropagation();
            this.popup.show(a, event);
            return;
        }
        const href = a.getAttribute('href') || '';
        const resolved = resolveDocLink(href, state.doc || '');
        if (event.defaultPrevented && (!navTreeLink || resolved?.type !== 'doc' || sameDoc(resolved.docPath, state.doc))) return;
        if (href.startsWith('#') && href.length > 1) {
            event.preventDefault();
            this.scrollToAnchor(href.slice(1), false);
            return;
        }
        if (resolved?.type === 'doc') {
            event.preventDefault();
            if (sameDoc(resolved.docPath, state.doc)) {
                if (resolved.hash) this.scrollToAnchor(resolved.hash, true);
                else this.scrollToTop(resolved.href, true);
                return;
            }
            history.pushState({}, '', resolved.href);
            const final_href = resolved.hash ? resolved.docPath+'#' + resolved.hash : resolved.docPath
            this.loadDoc(final_href);
        }
    }

    scrollToTop(href, push) {
        window.scrollTo({ top: 0, left: 0, behavior: 'smooth' });
        if (!href) return;
        history[push ? 'pushState' : 'replaceState']({}, '', href);
    }

    scrollToAnchor(hash, push) {
        const el = document.getElementById(hash) || document.querySelector(`[name="${cssEsc(hash)}"]`);
        if (!el) return;
        if (!window.__PAGE_BAR__?.highlightPageAnchor(hash)) scrollToEl(el);
        const url = new URL(location.href);
        url.hash = hash;
        history[push ? 'pushState' : 'replaceState']({}, '', url);
    }

    handleKeydown(event) {
        if (event.key === 'Escape') {
            this.closeSidebar();
            $('#mobile-menu')?.classList.remove('dropdown--open');
            this.popup.forceClose();
        }
        if ((event.key === 's' || event.key === 'S') && (event.ctrlKey || event.metaKey)) {
            event.preventDefault();
            this.toggleSidebar();
        }
    }

    showReaderNotice(message, options = {}) {
        let notice = $('#reader-notice');
        if (!notice) {
            notice = document.createElement('div');
            notice.id = 'reader-notice';
            notice.setAttribute('role', 'status');
            notice.setAttribute('aria-live', 'polite');
            document.body.appendChild(notice);
        }
        clearTimeout(this.noticeTimer);
        notice.textContent = message;
        notice.style.cssText = `position:fixed!important;left:50%!important;bottom:24px!important;transform:translateX(-50%) translateY(12px)!important;max-width:min(420px,calc(100vw - 32px))!important;padding:10px 14px!important;border:1px solid var(--border)!important;border-radius:10px!important;background:var(--bg-card)!important;color:${options.type === 'error' ? 'var(--accent)' : 'var(--text)'}!important;box-shadow:var(--shadow-md)!important;font:13px/1.5 var(--font-ui)!important;text-align:center!important;white-space:normal!important;overflow-wrap:anywhere!important;opacity:0!important;pointer-events:none!important;z-index:900!important;transition:opacity 160ms ease,transform 160ms ease!important;`;
        requestAnimationFrame(() => {
            notice.style.setProperty('opacity', '1', 'important');
            notice.style.setProperty('transform', 'translateX(-50%) translateY(0)', 'important');
        });
        this.noticeTimer = setTimeout(() => {
            notice.style.setProperty('opacity', '0', 'important');
            notice.style.setProperty('transform', 'translateX(-50%) translateY(12px)', 'important');
        }, options.duration || 2400);
    }
}

const app = new ReaderApp();
window.ReaderApp = app;
window.loadDoc = path => app.loadDoc(path);
window.showReaderNotice = (message, options) => app.showReaderNotice(message, options);

document.addEventListener('DOMContentLoaded', () => app.init());
