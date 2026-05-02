(function () {
    'use strict';
    const $ = s => document.querySelector(s);

    const state = {
        fs: parseFloat(localStorage.fontSize) || 1,
        lh: parseFloat(localStorage.lineHeight) || 2.0,
        rs: localStorage.rememberScroll !== 'false',
        mob: innerWidth < 768
    };

    const FN_REF_RE = /^#(nref|cref|fn|FN|NA|FA|sd|ed|M|E|F|N|T|a|b|z|c|n|p)[-\d]+?/i;

    const resolveUrl = href => { try { return new URL(href, location.href).href; } catch { return location.pathname.replace(/[^/]*$/, '') + href; } };
    const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

    function initResponsiveContent() {
        try {
            const content = $('#content');
            if (!content) return;
            content.querySelectorAll('table').forEach(table => {
                if (table.parentElement?.classList.contains('table-wrapper')) return;
                const wrapper = document.createElement('div');
                wrapper.className = 'table-wrapper';
                table.parentNode.insertBefore(wrapper, table);
                wrapper.appendChild(table);
            });
            content.querySelectorAll('img').forEach(img => {
                img.style.maxWidth = '100%';
                img.style.height = 'auto';
                img.style.display = 'block';
            });
        } catch (e) { console.warn('[Reader] Responsive init failed:', e); }
    }

    function initHeadingAnchors() {
        try {
            const content = $('#content');
            if (!content) return;
            const skip = new Set(['Karl Marx', 'Friedrich Engels', 'Karl Marx/Friedrich Engels']);
            content.querySelectorAll('h1, h2, h3, h4, h5, h6').forEach((h, i) => {
                const text = h.textContent.trim();
                if (skip.has(text)) return;
                if (!h.id) h.id = 'h' + i;
                if (!h.querySelector('.anchor'))
                    h.insertAdjacentHTML('beforeend', `<a class="anchor" href="#${h.id}" aria-hidden="true" hidden=""></a>`);
            });
        } catch (e) { console.warn('[Reader] Heading anchors init failed:', e); }
    }

    function initProgress() {
        try {
            const bar = $('#progress-bar');
            if (!bar) return;
            window.addEventListener('scroll', () => {
                const h = document.documentElement.scrollHeight - innerHeight;
                bar.style.width = (h > 0 ? (scrollY / h) * 100 : 0) + '%';
            }, { passive: true });
        } catch (e) { console.warn('[Reader] Progress init failed:', e); }
    }

    function initControls() {
        try {
            const slider = $('#font-slider');
            const mobileSlider = $('#mobile-font-slider');
            const setFont = s => {
                s = Math.max(0.75, Math.min(1.5, s));
                state.fs = s;
                document.documentElement.style.setProperty('--fs-user', Math.round(16 * s) + 'px');
                [slider, mobileSlider].forEach(el => { if (el) el.value = s; });
                localStorage.setItem('fontSize', s);
            };
            setFont(state.fs);

            // Line-height control
            const lhSlider = $('#lh-slider');
            const mobileLhSlider = $('#mobile-lh-slider');
            const setLineHeight = v => {
                v = Math.max(1.4, Math.min(2.6, Math.round(v * 10) / 10));
                state.lh = v;
                document.documentElement.style.setProperty('--lh-user', v);
                [lhSlider, mobileLhSlider].forEach(el => { if (el) el.value = v; });
                localStorage.setItem('lineHeight', v);
            };
            setLineHeight(state.lh);

            [['#lh-dec-btn', '#mobile-lh-dec', -0.1], ['#lh-inc-btn', '#mobile-lh-inc', 0.1]].forEach(([d, m, delta]) => {
                $(d)?.addEventListener('click', () => setLineHeight(state.lh + delta));
                $(m)?.addEventListener('click', () => setLineHeight(state.lh + delta));
            });
            [lhSlider, mobileLhSlider].forEach(s => s?.addEventListener('input', e => setLineHeight(parseFloat(e.target.value))));

            [['#font-dec-btn', '#mobile-font-dec', -0.05], ['#font-inc-btn', '#mobile-font-inc', 0.05]].forEach(([d, m, delta]) => {
                $(d)?.addEventListener('click', () => setFont(state.fs + delta));
                $(m)?.addEventListener('click', () => setFont(state.fs + delta));
            });
            [slider, mobileSlider].forEach(s => s?.addEventListener('input', e => setFont(parseFloat(e.target.value))));

            const updateThemeUI = () => {
                const isDark = document.documentElement.dataset.theme === 'dark';
                document.querySelectorAll('.icon-sun').forEach(el => el.style.display = isDark ? 'none' : '');
                document.querySelectorAll('.icon-moon').forEach(el => el.style.display = isDark ? '' : 'none');
                const ind = $('#mobile-theme-indicator');
                if (ind) ind.textContent = isDark ? '\u25CF' : '\u25CB';
            };
            updateThemeUI();

            const toggleTheme = () => {
                const isDark = document.documentElement.dataset.theme === 'dark';
                const newTheme = isDark ? 'light' : 'dark';
                document.documentElement.dataset.theme = newTheme;
                localStorage.theme = newTheme;
                updateThemeUI();
            };
            $('#theme-btn')?.addEventListener('click', toggleTheme);
            $('#sidebar-theme-btn')?.addEventListener('click', toggleTheme);
            $('#mobile-theme')?.addEventListener('click', toggleTheme);

            const remBtn = $('#remember-btn');
            const mobileRemInd = $('#mobile-remember-indicator');
            const updateRemember = () => {
                remBtn?.classList.toggle('clean-btn--active', state.rs);
                if (mobileRemInd) mobileRemInd.textContent = state.rs ? '\u25CF' : '\u25CB';
            };
            updateRemember();

            const toggleRemember = () => {
                state.rs = !state.rs;
                localStorage.rememberScroll = state.rs;
                updateRemember();
            };
            remBtn?.addEventListener('click', toggleRemember);
            $('#mobile-remember')?.addEventListener('click', toggleRemember);

            // Fix dropdown positioning: `position: fixed` ensures correct placement
            // on mobile Safari/Chrome regardless of body overflow or viewport quirks.
            const mobileMenu = $('#mobile-menu');
            if (mobileMenu) mobileMenu.style.position = 'fixed';

            $('#mobile-menu-toggle')?.addEventListener('click', (e) => {
                e.stopPropagation(); // prevent event from bubbling to document click-outside handler
                mobileMenu?.classList.toggle('dropdown--open');
            });
        } catch (e) { console.warn('[Reader] Controls init failed:', e); }
    }

    function initScrollMemory() {
        try {
            const key = 'scroll_' + location.pathname;
            if (state.rs) {
                const saved = localStorage.getItem(key);
                if (saved) requestAnimationFrame(() => window.scrollTo(0, parseInt(saved)));
            }
            window.addEventListener('scroll', debounce(() => {
                if (state.rs) localStorage.setItem(key, scrollY);
            }, 300), { passive: true });
        } catch (e) { console.warn('[Reader] Scroll memory init failed:', e); }
    }

    class FootnotePopup {
        constructor() {
            this.tip = $('#fn-tooltip');
            this._active = false;
            this._trigger = null;
            this._cache = new Map();
            this._sameCache = new Map();
            this._dismiss = this._doDismiss.bind(this);
            this._reposition = () => { if (this._active) this._position(); };
        }

        async show(a, e) {
            if (!this.tip) return;
            const href = a.getAttribute('href');
            if (!href) return;

            let targetId, pageUrl = null, isCross = false;
            if (href.startsWith('#')) targetId = href.slice(1);
            else if (href.includes('#')) { targetId = href.slice(href.indexOf('#') + 1); pageUrl = resolveUrl(href.slice(0, href.indexOf('#'))); isCross = true; }
            else return;

            this._trigger = a;
            const result = await this._resolveTarget(targetId, pageUrl, isCross);
            if (!result) return;
            const { block, target } = result;

            this._render(block, target, href, isCross);
            this._position(e);
            this.tip.classList.add('popover--visible');
            this._active = true;
            document.addEventListener('click', this._dismiss, true);
            document.addEventListener('keydown', this._dismiss);
            window.addEventListener('scroll', this._reposition, { passive: true });
        }

        async _resolveTarget(targetId, pageUrl, isCross) {
            if (isCross && pageUrl) {
                let doc = this._cache.get(pageUrl);
                if (!doc) {
                    try {
                        const res = await fetch(pageUrl);
                        if (!res.ok) return null;
                        doc = new DOMParser().parseFromString(await res.text(), 'text/html');
                        this._cache.set(pageUrl, doc);
                    } catch { return null; }
                }
                const target = doc.getElementById(targetId) || doc.querySelector('a[name="' + CSS.escape(targetId) + '"]');
                if (!target) return null;
                return { target, block: this._toBlock(target) };
            }

            const cached = this._sameCache.get(targetId);
            if (cached) return { target: cached.target || cached.block, block: cached.block };

            let block = document.getElementById(targetId);
            let target;
            if (block) {
                target = block.querySelector('#' + CSS.escape(targetId)) || block.querySelector('a[name="' + CSS.escape(targetId) + '"]') || block;
            }
            if (!block) {
                target = document.getElementById(targetId) || document.querySelector('a[name="' + CSS.escape(targetId) + '"]');
                if (!target) return null;
                block = this._toBlock(target);
            }
            return { target, block };
        }

        _toBlock(target) {
            const tag = target.tagName;
            const notes = '.fni, .footnote, .endnote, .fn, .note';
            if (tag === 'LI' || tag === 'DD' || tag === 'DIV' || ((tag === 'P' || tag === 'SPAN') && target.matches(notes))) return target;
            return target.closest(notes) || target.closest('li, dd') || target.closest('p, div') || target;
        }

        _render(block, target, href, isCross) {
            const viewer = this.tip.querySelector('.popover__body');
            const jumpLink = this.tip.querySelector('.popover__jump');
            if (!viewer) return;

            const clone = block.cloneNode(true);
            const tid = target.id || target.getAttribute('name');
            if (tid) {
                let t = clone.querySelector('#' + CSS.escape(tid));
                if (t) { t.removeAttribute('id'); t.setAttribute('data-fn-scroll', ''); }
                if (!t) {
                    t = clone.querySelector('[name="' + CSS.escape(tid) + '"]');
                    if (t) t.setAttribute('data-fn-scroll', '');
                }
            }
            viewer.innerHTML = '';
            viewer.appendChild(clone);
            requestAnimationFrame(() => {
                const marked = viewer.querySelector('[data-fn-scroll]');
                if (marked) marked.scrollIntoView({ block: 'start', behavior: 'instant' });
            });

            if (jumpLink) {
                jumpLink.href = isCross ? resolveUrl(href) : href;
                jumpLink.textContent = isCross ? '\u2197 Go to note (other page)' : '\u2193 Jump to footnote';
                jumpLink.classList.toggle('popover__jump--cross', isCross);
                jumpLink.style.display = '';
                jumpLink.onclick = () => this.forceClose();
            }
        }

        async preloadCrossPage() {
            const urls = new Set();
            document.querySelectorAll('a[data-fn-ref], #content sup a[href]').forEach(a => {
                const href = a.getAttribute('href') || '';
                if (!href.includes('#') || href.startsWith('#') || href.startsWith('http') || href.startsWith('//')) return;
                urls.add(resolveUrl(href.slice(0, href.indexOf('#'))));
            });
            if (!urls.size) return;
            await Promise.allSettled([...urls].map(async url => {
                if (this._cache.has(url)) return;
                try {
                    const res = await fetch(url);
                    if (res.ok) this._cache.set(url, new DOMParser().parseFromString(await res.text(), 'text/html'));
                } catch { }
            }));
        }

        preloadSamePage() {
            document.querySelectorAll('a[data-fn-ref], #content sup a[href]').forEach(a => {
                const href = a.getAttribute('href') || '';
                if (!href.startsWith('#') || href.length <= 1 || href.startsWith('http') || href.startsWith('//')) return;
                const id = href.slice(1);
                if (this._sameCache.has(id)) return;
                let block = document.getElementById(id);
                let target;
                if (block) target = block.querySelector('#' + CSS.escape(id)) || block.querySelector('a[name="' + CSS.escape(id) + '"]');
                if (!block) {
                    target = document.getElementById(id) || document.querySelector('a[name="' + CSS.escape(id) + '"]');
                    if (!target) return;
                    block = this._toBlock(target);
                }
                if (block) this._sameCache.set(id, { target: target?.cloneNode(true) || null, block: block.cloneNode(true) });
            });
        }

        _position(e) {
            if (!this._trigger) return;
            const rect = this._trigger.getBoundingClientRect();
            const tipW = 340;
            const maxH = Math.min(320, innerHeight * 0.45);
            let left = rect.right + 8;
            if (left + tipW > innerWidth - 12) left = Math.max(12, rect.left - tipW - 8);
            let top = rect.top + scrollY - 10;
            const minTop = scrollY + 4;
            const maxTop = scrollY + innerHeight - maxH - 4;
            this.tip.style.top = (top < minTop ? minTop : top > maxTop ? Math.max(minTop, maxTop) : top) + 'px';
            this.tip.style.left = left + 'px';
            this.tip.style.maxHeight = maxH + 'px';
        }

        _doDismiss(e) {
            if (e?.type === 'keydown' && e.key !== 'Escape') return;
            if (e?.type === 'click' && this.tip.contains(e.target)) return;
            this.tip.classList.remove('popover--visible');
            const viewer = this.tip.querySelector('.popover__body');
            if (viewer) viewer.innerHTML = '';
            const jumpLink = this.tip.querySelector('.popover__jump');
            if (jumpLink) jumpLink.style.display = 'none';
            this._active = false;
            this._trigger = null;
            document.removeEventListener('click', this._dismiss, true);
            document.removeEventListener('keydown', this._dismiss);
            window.removeEventListener('scroll', this._reposition);
        }

        forceClose() { if (this._active) this._doDismiss(); }
    }

    function isFootnoteLink(a) {
        if (a.hasAttribute('data-fn-ref') || a.hasAttribute('data-fn-cross')) return true;
        const href = a.getAttribute('href') || '';
        if (!href.includes('#') || href.startsWith('http') || href.startsWith('//')) return false;
        const inSup = a.closest('sup') || a.querySelector('sup');
        if (!inSup) return false;
        const fragment = href.startsWith('#') ? href : href.slice(href.indexOf('#'));
        return FN_REF_RE.test(fragment);
    }

    function initFootnotes() {
        try {
            const popup = new FootnotePopup();
            const start = () => { popup.preloadCrossPage(); popup.preloadSamePage(); };
            if ('requestIdleCallback' in window) requestIdleCallback(start, { timeout: 2000 });
            else setTimeout(start, 500);

            document.addEventListener('click', e => {
                const a = e.target.closest('a');
                if (!a || !isFootnoteLink(a)) return;
                e.preventDefault();
                e.stopImmediatePropagation();
                popup.show(a, e);
            });

            window.__FN_POPUP__ = popup;
        } catch (e) { console.warn('[Reader] Footnotes init failed:', e); }
    }

    function initGlobalEvents() {
        try {
            window.addEventListener('resize', () => {
                const was = state.mob;
                state.mob = innerWidth < 768;
                if (was !== state.mob) {
                    window.__NAV__?.menu?.close();
                    $('#mobile-menu')?.classList.remove('dropdown--open');
                }
            });

            document.addEventListener('keydown', e => {
                if (e.key === 'Escape') {
                    window.__NAV__?.menu?.close();
                    $('#mobile-menu')?.classList.remove('dropdown--open');
                    window.__FN_POPUP__?.forceClose();
                }
                if ((e.key === 's' || e.key === 'S') && (e.ctrlKey || e.metaKey)) {
                    e.preventDefault();
                    window.__NAV__?.menu?.toggle();
                }
            });

            // Close mobile dropdown when clicking outside of it
            document.addEventListener('click', e => {
                const menu = $('#mobile-menu');
                if (menu?.classList.contains('dropdown--open') && !menu.contains(e.target)) {
                    menu.classList.remove('dropdown--open');
                }
            });

            document.addEventListener('click', e => {
                const a = e.target.closest('a[href]');
                if (!a || !a.closest('#content')) return;
                if (a.hasAttribute('data-fn-ref') || a.hasAttribute('data-fn-cross') || a.classList.contains('fn-ref')) return;
                const href = a.getAttribute('href') || '';
                if (FN_REF_RE.test(href)) return;

                if (href.startsWith('#') && href.length > 1) {
                    e.preventDefault();
                    const target = document.getElementById(href.slice(1));
                    if (target) target.scrollIntoView({ behavior: 'smooth' });
                    return;
                }
                if (href.includes('#') && !href.startsWith('http') && !href.startsWith('//')) {
                    try {
                        const resolved = new URL(href, location.href);
                        if (resolved.pathname === location.pathname) {
                            e.preventDefault();
                            const target = document.getElementById(resolved.hash.slice(1));
                            if (target) target.scrollIntoView({ behavior: 'smooth' });
                        }
                    } catch { /* let browser handle */ }
                }
            });
        } catch (e) { console.warn('[Reader] Global events init failed:', e); }
    }

    // Wrap flat TOC items (<li><a/><button/></li>) into the wrapped
    // layout (<li><div class="toc-item-row"><a/><button/></div></li>)
    // so the button is never pushed to the next line.
    function initTocRowWrap() {
        try {
            document.querySelectorAll('.doc-toc > ul > .toc-item, .doc-toc > ol > .toc-item').forEach(li => {
                // Already wrapped — skip
                if (li.querySelector(':scope > .toc-item-row')) return;
                const a = li.querySelector(':scope > a.toc-link');
                const btn = li.querySelector(':scope > button.toc-caret');
                if (!a) return;
                const row = document.createElement('div');
                row.className = 'toc-item-row';
                row.appendChild(a);
                if (btn) row.appendChild(btn);
                li.insertBefore(row, li.firstChild);
            });
        } catch (e) { console.warn('[Reader] TOC row wrap init failed:', e); }
    }

    // Lightweight heading tracker for volume-index pages (used when
    // nav.js EPUB tracker is not active).  Keeps the TOC link that
    // corresponds to the heading currently in the viewport highlighted.
    function initHeadingTracker() {
        try {
            const toc = document.querySelector('.doc-toc');
            if (!toc) return;
            const headings = Array.from(document.querySelectorAll('#content h1[id], #content h2[id], #content h3[id], #content h4[id], #content h5[id], #content h6[id]'));
            if (!headings.length) return;
            const links = toc.querySelectorAll('a.toc-link');
            if (!links.length) return;

            let lastId = null;
            const onScroll = () => {
                let activeId = null;
                for (let i = headings.length - 1; i >= 0; i--) {
                    if (headings[i].getBoundingClientRect().top <= 200) {
                        activeId = headings[i].id; break;
                    }
                }
                if (!activeId && headings.length) activeId = headings[0].id;
                if (activeId && activeId !== lastId) {
                    lastId = activeId;
                    links.forEach(a => a.classList.remove('toc-link--active'));
                    const match = toc.querySelector(`a[href$="#${CSS.escape(activeId)}"]`);
                    if (match) {
                        match.classList.add('toc-link--active');
                        // Expand parent branches
                        let parent = match.closest('.toc-item--collapsible');
                        while (parent) {
                            parent.setAttribute('data-collapsed', 'false');
                            const caret = parent.querySelector(':scope > .toc-item-row > .toc-caret, :scope > .toc-caret');
                            if (caret) caret.textContent = '\u25be';
                            parent = parent.parentElement?.closest('.toc-item--collapsible');
                        }
                    }
                }
            };

            window.addEventListener('scroll', onScroll, { passive: true });
            requestAnimationFrame(onScroll);
        } catch (e) { console.warn('[Reader] Heading tracker init failed:', e); }
    }


    function init() {
        initResponsiveContent();
        initProgress();
        initHeadingAnchors();
        initControls();
        initScrollMemory();
        initFootnotes();
        initGlobalEvents();
        initTocRowWrap();
        initHeadingTracker();
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();