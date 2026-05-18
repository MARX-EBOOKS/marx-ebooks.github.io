const state = {
    fs: parseFloat(localStorage.fontSize) || 1,
    lh: parseFloat(localStorage.lineHeight) || 2.0,
    rs: localStorage.rememberScroll !== 'false',
    sb: false,
    th: localStorage.theme || 'light',
    doc: null,
    mob: innerWidth < 768,
    tocScrollHandler: null
};

// ── 主题 / 字体 / 行高 ──
function applyTheme(t) {
    document.documentElement.dataset.theme = t;
    localStorage.theme = t;
    const isDark = t === 'dark';
    $$('.icon-sun').forEach(el => el.style.display = isDark ? 'block' : 'none');
    $$('.icon-moon').forEach(el => el.style.display = isDark ? 'none' : 'block');
}

function applyFont(s, save) {
    s = Math.max(.75, Math.min(1.5, s));
    state.fs = s;
    document.documentElement.style.setProperty('--fs-user', Math.round(16 * s) + 'px');
    if (save) localStorage.setItem('fontSize', s);
    ['#font-slider', '#mobile-font-slider'].forEach(sel => {
        const el = document.querySelector(sel);
        if (el) { el.value = s; syncFill(el); }
    });
}

function applyLineHeight(v, save) {
    v = Math.max(1.4, Math.min(2.6, Math.round(v * 10) / 10));
    state.lh = v;
    document.documentElement.style.setProperty('--lh-user', v);
    if (save) localStorage.setItem('lineHeight', v);
    ['#lh-slider', '#mobile-lh-slider'].forEach(sel => {
        const el = document.querySelector(sel);
        if (el) { el.value = v; syncFill(el); }
    });
}

// ── 统一链接解析 ──
function resolveDocLink(href, basePath) {
    if (!href) return null;
    if (href.startsWith('#')) return { type: 'anchor', href, hash: href.slice(1) };
    if (/^(https?:|mailto:|javascript:|\/\/)/i.test(href)) return { type: 'external', href };

    let hash = '';
    let urlPart = href;
    const hashIdx = href.indexOf('#');
    if (hashIdx >= 0) {
        hash = href.slice(hashIdx);
        urlPart = href.slice(0, hashIdx);
    }

    let parts;
    if (urlPart.startsWith('?doc=')) {
        parts = urlPart.slice(5).split('/').filter(Boolean);
    } else if (urlPart.startsWith('/')) {
        parts = urlPart.slice(1).split('/').filter(Boolean);
    } else {
        const baseParts = basePath ? basePath.split('/').filter(Boolean) : [];
        const relParts = urlPart.split('/').filter(p => p && p !== '.');
        parts = [...baseParts, ...relParts];
    }

    const stack = [];
    for (const p of parts) {
        if (p === '..' && stack.length) { stack.pop(); }
        else if (p !== '..') { stack.push(p); }
    }
    const docPath = stack.join('/');

    return {
        type: 'doc',
        href: '?doc=' + docPath + hash,
        docPath,
        hash: hash ? hash.slice(1) : ''
    };
}

// ── 欢迎页卡片 ──
function buildWelcomeCards() {
    const grid = $('#library-cards');
    if (!grid) return;
    LIBRARY_CONFIG.forEach(c => {
        const a = document.createElement('a');
        a.className = 'card';
        a.href = '#';
        a.innerHTML = `<div class="card__tag">${esc(c.label)}${c.badge ? ' \u00b7 ' + esc(c.badge) : ''}</div>
                       <div class="card__heading">${esc(c.title || c.label)}</div>
                       <div class="card__body">${esc(c.desc || '\u70b9\u51fb\u67e5\u770b\u76ee\u5f55')}</div>`;
        a.addEventListener('click', e => {
            e.preventDefault();
            if (innerWidth < 997) { state.sb = true; applySidebar(); }
            const sec = document.querySelector(`.sidebar-item[data-section="${CSS.escape(c.id)}"]`);
            if (!sec) return;
            const caret = sec.querySelector('.sidebar-caret');
            if (caret) caret.dispatchEvent(new Event('click', { bubbles: true }));
            setTimeout(() => sec.scrollIntoView({ behavior: 'smooth', block: 'center' }), 200);
        });
        grid.appendChild(a);
    });
}

// ── 侧边栏 ──
function toggleSidebar() {
    state.sb = !state.sb;
    applySidebar();
}

function closeSidebar() {
    state.sb = false;
    applySidebar();
}

function applySidebar() {
    const sidebar = $('#lsidebar');
    const backdrop = $('#sidebar-backdrop');
    if (!sidebar) return;
    if (!sidebar.classList.contains('doc-sidebar')) sidebar.classList.add('doc-sidebar');

    const isMobile = innerWidth < 997;
    if (isMobile) {
        sidebar.classList.toggle('open', state.sb);
        sidebar.classList.toggle('doc-sidebar--open', state.sb);
        sidebar.style.pointerEvents = state.sb ? 'auto' : 'none';
        backdrop && backdrop.classList.toggle('visible', state.sb);
        backdrop && backdrop.classList.toggle('sidebar-overlay--visible', state.sb);
    } else {
        sidebar.classList.remove('open', 'doc-sidebar--open');
        sidebar.style.pointerEvents = '';
        backdrop && backdrop.classList.remove('visible', 'sidebar-overlay--visible');
    }
}

function handleResize() {
    const was = state.mob;
    state.mob = innerWidth < 768;
    if (was !== state.mob) $('#mobile-menu')?.classList.remove('dropdown--open');
    applySidebar();
}

// ── 文档加载 ──
async function loadDoc(docPath) {
    $('#welcome-view').style.display = 'none';
    $('#article-view').style.display = 'block';
    $('#toc-desktop').style.display = 'none';
    $('#toc-desktop-nav').innerHTML = '';
    const skeleton = $('#doc-skeleton');
    skeleton.classList.add('active');
    skeleton.style.display = 'block';
    $('#content').style.display = 'none';
    $('#doc-footer').style.display = 'none';

    $$('.dynamic-doc-css, .dynamic-doc-style').forEach(el => el.remove());

    const col = findCollection(docPath);
    for (const css of col?.stylesheets ?? []) {
        const colBase = (col.basePath || `/${col.id}/`).replace(/^\//, '');
        const link = Object.assign(document.createElement('link'), {
            rel: 'stylesheet', type: 'text/css', className: 'dynamic-doc-css',
            href: resolveCssHref(css, colBase)
        });
        document.head.insertBefore(link, document.head.firstChild);
        await new Promise(r => { link.onload = link.onerror = r; setTimeout(r, 800); });
    }

    updateBreadcrumb(docPath, null);

    try {
        const res = await fetch(docPath);
        if (!res.ok) throw new Error(res.status);
        const html = await res.text();

        skeleton.style.transition = 'opacity 150ms ease';
        skeleton.style.opacity = '0';

        renderDoc(html, docPath);

        requestAnimationFrame(() => {
            skeleton.classList.remove('active');
            skeleton.style.opacity = '1';
            skeleton.style.display = 'none';
            const content = $('#content');
            content.style.display = 'block';
            content.style.opacity = '0';
            content.style.transition = 'opacity 200ms ease';
            requestAnimationFrame(() => {
                content.style.opacity = '1';
                $('#doc-footer').style.display = 'flex';

                // 统一滚动：必须在 content 可见后执行，否则 getBoundingClientRect 为 0
                const hash = location.hash.slice(1);
                if (hash) {
                    const el = document.getElementById(hash) || document.querySelector(`[name="${hash}"]`);
                    if (el) scrollToEl(el);
                } else if (state.rs) {
                    const s = localStorage.getItem('scroll_' + state.doc);
                    s && window.scrollTo(0, parseInt(s));
                } else {
                    window.scrollTo(0, 0);
                }
            });
        });
    } catch (e) {
        skeleton.classList.remove('active');
        skeleton.style.display = 'none';
        showError(docPath, e.message);
    }
}

function renderDoc(h, path) {
    const d = new DOMParser().parseFromString(h, 'text/html');
    const base = path.substring(0, path.lastIndexOf('/') + 1);

    $$('.dynamic-doc-style').forEach(el => el.remove());
    d.querySelectorAll('link[rel="stylesheet"]').forEach(lk => {
        const href = lk.getAttribute('href');
        if (!href) return;
        document.head.appendChild(Object.assign(document.createElement('link'), {
            rel: 'stylesheet', className: 'dynamic-doc-style',
            href: resolveCssHref(href, base)
        }));
    });
    d.querySelectorAll('style').forEach(st => {
        const el = document.createElement('style');
        el.className = 'dynamic-doc-style';
        el.textContent = st.textContent;
        document.head.appendChild(el);
    });

    d.querySelectorAll('a[href]').forEach(a => {
        const x = a.getAttribute('href');
        const r = resolveDocLink(x, base);
        if (r && r.type === 'doc') a.href = r.href;
    });

    d.querySelectorAll('[src]').forEach(e => {
        const s = e.getAttribute('src');
        if (s && !s.match(/^(https?:|\/|data:)/)) e.src = base + s;
    });

    const c = $('#content');
    c.innerHTML = d.body.innerHTML;

    c.querySelectorAll('a[name]').forEach(a => {
        if (a.parentElement && !a.parentElement.id) a.parentElement.id = a.getAttribute('name');
    });

    const skip = new Set(['Karl Marx', 'Friedrich Engels', 'Karl Marx/Friedrich Engels']);
    c.querySelectorAll('h1,h2,h3,h4,h5,h6').forEach((h, i) => {
        const text = h.textContent.trim();
        if (skip.has(text)) return;
        if (!h.id) h.id = 'h' + i;
        if (!h.querySelector('.anchor'))
            h.insertAdjacentHTML('beforeend', `<a class="anchor" href="#${h.id}" aria-hidden="true" hidden=""></a>`);
    });

    state.doc = path;
    const title = d.querySelector('title')?.textContent?.trim();
    document.title = title ? title + ' \u2014 MLCLASSIC' : '\u6587\u5e93\u9605\u8bfb\u5668 \u2014 MLCLASSIC';
    updateBreadcrumb(path, title);

    fixOverflow(c);

    updatePrevNext(path);
    window.__NAV__?.reinit(state.doc);
    window.__PAGE_BAR__?.scanContent($('#content'));
    const tocDesktop = $('#toc-desktop');
    if (tocDesktop) tocDesktop.style.display = '';
}


function updateBreadcrumb(path, title) {
    const bar = $('#doc-pathbar');
    const col = findCollection(path);
    const pts = path.split('/');
    const parts = [];
    if (col) {
        const colPath = (col.path || '').replace(/^\//, '');
        parts.push(`<a class="crumb" href="?doc=${esc(colPath)}">${esc(col.label)}</a>`);
    } else if (pts[0]) {
        parts.push(`<span class="crumb">${esc(pts[0])}</span>`);
    }
    for (let i = 1; i < pts.length - 1; i++) {
        const subPath = pts.slice(0, i + 1).join('/').replace(/^\//, '');
        parts.push(`<span class="crumb-sep">/</span>`);
        parts.push(`<a class="crumb" href="?doc=${esc(subPath)}">${esc(pts[i])}</a>`);
    }
    const file = pts[pts.length - 1];
    if (file) parts.push(`<span class="crumb-sep">/</span><span class="crumb crumb--active">${esc(file)}</span>`);
    if (title) parts.push(`<span class="crumb-sep">/</span><span class="crumb crumb--active">${esc(title)}</span>`);
    bar.innerHTML = parts.join('');
}

function fixOverflow(c) {
    c.querySelectorAll('table').forEach(table => {
        if (table.parentElement?.classList.contains('table-wrapper')) return;
        const wrapper = document.createElement('div');
        wrapper.className = 'table-wrapper';
        table.parentNode.insertBefore(wrapper, table);
        wrapper.appendChild(table);
    });
    c.querySelectorAll('img').forEach(img => {
        img.style.maxWidth = '100%';
        img.style.height = 'auto';
        img.style.display = 'block';
    });
}

function showError(p, m) {
    $('#toc-desktop').style.display = 'none';
    $('#toc-desktop-nav').innerHTML = '';
    $('#content').innerHTML = `<p style="color:var(--text-2);padding:40px 0;">无法加载 <code>${esc(p)}</code><br><small>${esc(m)}</small></p>`;
    $('#content').style.display = 'block';
    $('#content').style.opacity = '1';
}

// ── 轻量通知：给页码引用复制等非阻塞反馈使用 ──
function showReaderNotice(message, options = {}) {
    let notice = document.getElementById('reader-notice');
    if (!notice) {
        notice = document.createElement('div');
        notice.id = 'reader-notice';
        notice.setAttribute('role', 'status');
        notice.setAttribute('aria-live', 'polite');
        document.body.appendChild(notice);
    }

    clearTimeout(showReaderNotice._timer);
    notice.textContent = message;
    notice.style.cssText = `
        position: fixed !important;
        left: 50% !important;
        bottom: 24px !important;
        transform: translateX(-50%) translateY(12px) !important;
        max-width: min(420px, calc(100vw - 32px)) !important;
        padding: 10px 14px !important;
        border: 1px solid var(--border) !important;
        border-radius: 10px !important;
        background: var(--bg-card) !important;
        color: ${options.type === 'error' ? 'var(--accent)' : 'var(--text)'} !important;
        box-shadow: var(--shadow-md) !important;
        font: 13px/1.5 var(--font-ui) !important;
        text-align: center !important;
        white-space: normal !important;
        overflow-wrap: anywhere !important;
        opacity: 0 !important;
        pointer-events: none !important;
        z-index: 900 !important;
        transition: opacity 160ms ease, transform 160ms ease !important;
    `;

    requestAnimationFrame(() => {
        notice.style.setProperty('opacity', '1', 'important');
        notice.style.setProperty('transform', 'translateX(-50%) translateY(0)', 'important');
    });

    showReaderNotice._timer = setTimeout(() => {
        notice.style.setProperty('opacity', '0', 'important');
        notice.style.setProperty('transform', 'translateX(-50%) translateY(12px)', 'important');
    }, options.duration || 2400);
}
window.showReaderNotice = showReaderNotice;

// ── 前后篇导航 ──
const mf = {};

async function fetchManifest(dir) {
    const cleanDir = dir.replace(/^\//, '').replace(/\/$/, '');
    if (mf[cleanDir]) return mf[cleanDir];
    const data = await fetchVolData(cleanDir, mf);
    return data;
}

function updatePrevNext(p) {
    const prev = $('#prev-btn'), next = $('#next-btn');
    prev.style.display = next.style.display = 'none';

    // ── 1. 解析路径 ──
    let dir = '', file = p;
    const s = p.lastIndexOf('/');
    if (s !== -1) {
        dir = p.slice(0, s + 1);
        file = p.slice(s + 1);
    } else {
        // 无目录前缀时，尝试从集合配置推断
        const col = findCollection(p);
        if (col) {
            const colPath = (col.path || col.basePath || '').replace(/^\//, '').replace(/\/$/, '');
            if (colPath) dir = colPath + '/';
        }
    }

    const cleanFile = file.replace(/\.html(?:#.*)?$/i, '');
    const col = findCollection(p);
    const colDir = col ? (col.path || col.basePath || '').replace(/^\//, '').replace(/\/$/, '') : '';
    const currentDir = dir.replace(/^\//, '').replace(/\/$/, '');
    const pageDir = location.pathname.split('/').slice(1, -1).join('/');

    // ── 2. 候选 manifest 目录（去重） ──
    const candidates = [];
    const addCandidate = d => { if (d && !candidates.includes(d)) candidates.push(d); };
    addCandidate(currentDir);   // 当前文件所在目录
    addCandidate(colDir);       // 集合配置目录
    addCandidate(pageDir);      // 当前页面所在目录

    // ── 3. 顺序尝试加载 manifest，成功即停 ──
    let chain = Promise.resolve(null);
    for (const d of candidates) {
        chain = chain.then(async result => {
            if (result) return result;
            try {
                const raw = await fetchManifest(d);
                if (raw && (Array.isArray(raw) || Array.isArray(raw?.files))) {
                    return {
                        data: Array.isArray(raw) ? raw : raw.files,
                        manifestDir: d
                    };
                }
            } catch (e) { }
            return null;
        });
    }

    // ── 4. 处理 manifest ──
    chain.then(result => {
        if (!result || !result.data?.length) return fallbackNav(dir, file, prev, next);

        const m = result.data;
        const manifestDir = result.manifestDir;

        // 在 manifest 中查找当前文件（支持 basename 匹配，忽略 .html 和 #hash）
        let i = m.findIndex(x => {
            const f = x.file || x.path || x.url || x.filename || '';
            const src = x.source_file || x.filename || '';
            const cleanF = f.replace(/\.html(?:#.*)?$/i, '');
            const cleanSrc = src.replace(/\.html(?:#.*)?$/i, '');
            const fBase = f.split('/').pop().replace(/\.html(?:#.*)?$/i, '');
            const srcBase = src.split('/').pop().replace(/\.html(?:#.*)?$/i, '');

            return f === p || f === file || cleanF === cleanFile ||
                fBase === cleanFile || srcBase === cleanFile ||
                cleanSrc === cleanFile;
        });

        // 第二遍：宽松子串匹配
        if (i < 0) {
            i = m.findIndex(x => {
                const f = x.file || x.path || x.url || x.filename || '';
                const src = x.source_file || x.filename || '';
                return f.includes(file) || file.includes(f.replace(/\.html(?:#.*)?$/i, '')) ||
                    src.includes(file) || file.includes(src.replace(/\.html(?:#.*)?$/i, ''));
            });
        }

        // 生成路径：相对路径保留；纯文件名用 manifest 所在目录拼接
        const makePath = item => {
            const f = item.file || item.path || item.url || item.filename || '';
            const r = resolveDocLink(f, manifestDir ? manifestDir + '/' : '');
            if (r && r.type === 'doc') return r.docPath;
            return f;
        };

        if (i >= 0) {
            // 有 index.json 时优先使用，不再 fallback 到编号加减一
            if (i > 0) setupPaginationBtn(prev, makePath(m[i - 1]), m[i - 1].title, 'prev');
            if (i < m.length - 1) setupPaginationBtn(next, makePath(m[i + 1]), m[i + 1].title, 'next');
            return;
        }

        // index.json 存在但匹配不到当前文件：按文件名排序找邻居
        console.warn('[PrevNext] index.json loaded but no exact match for', file, '; trying sorted neighbors');
        const entries = m.map(x => ({
            file: x.file || x.path || x.url || x.filename || '',
            title: x.title,
            clean: (x.file || x.path || x.url || x.filename || '').replace(/\.html(?:#.*)?$/i, '')
        })).filter(x => x.file);

        if (!entries.length) return fallbackNav(dir, file, prev, next);

        entries.sort((a, b) => a.clean.localeCompare(b.clean, undefined, { numeric: true }));

        const pos = entries.findIndex(e => e.clean === cleanFile || e.file.includes(file) || file.includes(e.clean));
        if (pos < 0) return fallbackNav(dir, file, prev, next);

        if (pos > 0) setupPaginationBtn(prev, makePath(entries[pos - 1]), entries[pos - 1].title, 'prev');
        if (pos < entries.length - 1) setupPaginationBtn(next, makePath(entries[pos + 1]), entries[pos + 1].title, 'next');
    }).catch(() => fallbackNav(dir, file, prev, next));
}

function fallbackNav(dir, file, prev, next) {
    const baseFile = file.split('#')[0];
    const m = baseFile.match(/^(.*?)(\d+)(\.[^.]+)$/);
    if (!m) return;
    const [, prefix, num, ext] = m, pad = num.length;
    const make = n => dir + prefix + String(n).padStart(pad, '0') + ext;
    const tryBtn = async (btn, path) => {
        try {
            const r = await fetch(path, { method: 'HEAD', mode: 'same-origin' });
            if (r.ok) setupPaginationBtn(btn, path, null, btn === prev ? 'prev' : 'next');
        } catch { }
    };
    const n = parseInt(num);
    if (n > 1) tryBtn(prev, make(n - 1));
    tryBtn(next, make(n + 1));
}

function setupPaginationBtn(btn, path, title, dir) {
    if (!btn) return;
    const labelEl = btn.querySelector('.pagination-link__label');
    const dirEl = btn.querySelector('.pagination-link__dir');
    btn.style.display = 'flex';
    dirEl.textContent = dir === 'prev' ? '\u2190 Previous' : 'Next \u2192';

    const truncate = t => t && t.length > 40 ? t.slice(0, 39) + '\u2026' : (t || '');
    labelEl.textContent = truncate(title);
    labelEl.title = title || '';

    if (!title) {
        const fetchPath = path.split('#')[0];
        fetch(fetchPath).then(r => r.text()).then(h => {
            const t = new DOMParser().parseFromString(h, 'text/html').querySelector('title')?.textContent?.trim();
            if (t) { labelEl.textContent = truncate(t); labelEl.title = t; }
        }).catch(() => { });
    }

    btn.onclick = e => {
        e.preventDefault();
        history.pushState({}, '', '?doc=' + path);
        loadDoc(path);
    };
}
// ── 脚注判定 ──
function isFootnoteLink(a) {
    if (a.hasAttribute('data-fn-ref') || a.hasAttribute('data-fn-cross')) return true;
    const href = a.getAttribute('href') || '';
    if (!href.includes('#') || href.startsWith('http') || href.startsWith('//')) return false;
    const inSup = a.closest('sup') || a.querySelector('sup');
    return !!inSup;
}

// ── 脚注弹窗 ──
class FootnotePopup {
    constructor() {
        this.tip = $('#fn-tooltip');
        this._active = false;
        this._trigger = null;
        this._cache = new Map();
        this._dismiss = this._doDismiss.bind(this);
        this._reposition = () => { if (this._active) this._position(); };
    }

    async show(a, e) {
        if (!this.tip) return;
        const href = a.getAttribute('href');
        if (!href) return;

        let targetId, pageUrl = null, isCross = false;
        if (href.startsWith('#')) {
            targetId = href.slice(1);
        } else if (href.includes('#')) {
            targetId = href.slice(href.indexOf('#') + 1);
            const beforeHash = href.slice(0, href.indexOf('#'));
            pageUrl = beforeHash.startsWith('?doc=') ? beforeHash.slice(5) : resolveUrl(beforeHash);
            isCross = true;
        } else return;

        this._trigger = a;
        this._renderState('loading', isCross);
        this._position(e);
        this.tip.classList.add('popover--visible');
        this._active = true;
        document.addEventListener('click', this._dismiss, true);
        document.addEventListener('keydown', this._dismiss);
        window.addEventListener('scroll', this._reposition, { passive: true });

        const result = await this._resolveTarget(targetId, pageUrl, isCross);
        if (!result) { this._renderState('error', isCross); return; }
        this._render(result.block, href, isCross);
        requestAnimationFrame(() => this._position(e));
    }

    async _resolveTarget(targetId, pageUrl, isCross) {
        if (isCross && pageUrl) {
            let doc = this._cache.get(pageUrl);
            if (!doc) {
                try {
                    const controller = new AbortController();
                    const timer = setTimeout(() => controller.abort(), 3000);
                    const res = await fetch(pageUrl, { signal: controller.signal });
                    clearTimeout(timer);
                    if (!res.ok) return null;
                    doc = new DOMParser().parseFromString(await res.text(), 'text/html');
                    this._cache.set(pageUrl, doc);
                } catch { return null; }
            }
            const target = doc.getElementById(targetId) || doc.querySelector(`a[name="${CSS.escape(targetId)}"]`);
            if (!target) return null;
            return { target, block: this._toBlock(target) };
        }
        const target = document.getElementById(targetId) || document.querySelector(`a[name="${CSS.escape(targetId)}"]`);
        if (!target) return null;
        return { target, block: this._toBlock(target) };
    }

    _toBlock(target) {
        const notes = '.fni, .footnote, .endnote, .fn, .note';
        const tag = target.tagName;
        if (tag === 'LI' || tag === 'DD') return target;
        if ((tag === 'DIV' || tag === 'P') && target.closest(notes)) return target;
        let el = target.parentElement;
        while (el && el !== document.body) {
            const t = el.tagName;
            if (t === 'DIV' || t === 'P' || t === 'LI' || t === 'DD') {
                if (el.matches(notes) || el.closest(notes)) return el;
                break;
            }
            el = el.parentElement;
        }
        return target.closest(notes) || target.closest('li, dd') || target.closest('p, div') || target;
    }

    _render(block, href, isCross) {
        const viewer = this.tip.querySelector('.popover__body');
        const jumpLink = this.tip.querySelector('.popover__jump');
        if (!viewer) return;
        const clone = block.cloneNode(true);
        clone.querySelectorAll('[id]').forEach(el => el.removeAttribute('id'));
        viewer.innerHTML = '';
        viewer.appendChild(clone);

        if (jumpLink) {
            jumpLink.href = isCross ? resolveUrl(href) : href;
            jumpLink.textContent = isCross ? '↗ Go to note (other page)' : '↓ Jump to footnote';
            jumpLink.classList.toggle('popover__jump--cross', isCross);
            jumpLink.style.display = '';
            jumpLink.onclick = () => this.forceClose();
        }
    }

    _renderState(type, isCross) {
        const viewer = this.tip.querySelector('.popover__body');
        if (!viewer) return;
        const msgs = {
            loading: { text: isCross ? '\u52a0\u8f7d\u8de8\u9875\u6ce8\u91ca\u4e2d\u2026' : '\u52a0\u8f7d\u4e2d\u2026', color: 'var(--text-3)' },
            error: { text: isCross ? '\u8de8\u9875\u6ce8\u91ca\u52a0\u8f7d\u5931\u8d25\uff08\u8d85\u65f6\u6216\u65e0\u6cd5\u8bbf\u95ee\uff09' : '\u672a\u627e\u5230\u5bf9\u5e94\u6ce8\u91ca', color: 'var(--accent)' }
        };
        const m = msgs[type];
        viewer.innerHTML = `<div style="color:${m.color};font-size:13px;padding:4px 0;">${m.text}</div>`;
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

    _doDismiss(ev) {
        if (ev?.type === 'keydown' && ev.key !== 'Escape') return;
        if (ev?.type === 'click' && this.tip.contains(ev.target)) return;
        this.tip.classList.remove('popover--visible');
        const viewer = this.tip.querySelector('.popover__body');
        if (viewer) viewer.innerHTML = '';
        this._active = false;
        this._trigger = null;
        document.removeEventListener('click', this._dismiss, true);
        document.removeEventListener('keydown', this._dismiss);
        window.removeEventListener('scroll', this._reposition);
    }

    forceClose() { if (this._active) this._doDismiss(); }
}

// ── 事件绑定辅助 ──
function bindStepperGroup({ stateKey, applyFn, step, decIds, incIds, sliderIds }) {
    const adjust = delta => applyFn(state[stateKey] + delta, true);
    decIds.forEach(id => on($('#' + id), 'click', () => adjust(-step)));
    incIds.forEach(id => on($('#' + id), 'click', () => adjust(step)));
    sliderIds.forEach(id => on($('#' + id), 'input', e => applyFn(parseFloat(e.target.value), true)));
}

function bindToggle({ btnIds, itemIds, getNext, apply }) {
    const toggle = e => {
        e?.stopPropagation();
        apply(getNext());
    };
    btnIds.forEach(id => on($('#' + id), 'click', toggle));
    itemIds.forEach(id => on($('#' + id), 'click', toggle));
}

// ── 事件绑定 ──
function bindEvents() {
    const popup = new FootnotePopup();

    on($('#sidebar-toggle'), 'click', toggleSidebar);
    on($('#sidebar-backdrop'), 'click', closeSidebar);
    on($('#sidebar-close-btn'), 'click', closeSidebar);

    const toggleMobileMenu = (e) => {
        e.preventDefault();
        e.stopPropagation();
        const menu = $('#mobile-menu');
        menu.style.position = 'fixed';
        menu.style.top = 'calc(var(--nav-h) + 6px)';
        menu.classList.toggle('dropdown--open');
        if (menu.classList.contains('dropdown--open')) updateMobileMenuIndicators();
    };
    const toggleBtn = $('#mobile-menu-toggle');
    if (toggleBtn) {
        toggleBtn.addEventListener('click', toggleMobileMenu);
        toggleBtn.addEventListener('touchend', (e) => { e.preventDefault(); toggleMobileMenu(e); }, { passive: false });
    }

    bindStepperGroup({ stateKey: 'fs', applyFn: applyFont, step: 0.05, decIds: ['font-dec-btn', 'mobile-font-dec'], incIds: ['font-inc-btn', 'mobile-font-inc'], sliderIds: ['font-slider', 'mobile-font-slider'] });
    bindStepperGroup({ stateKey: 'lh', applyFn: applyLineHeight, step: 0.1, decIds: ['lh-dec-btn', 'mobile-lh-dec'], incIds: ['lh-inc-btn', 'mobile-lh-inc'], sliderIds: ['lh-slider', 'mobile-lh-slider'] });

    bindToggle({
        btnIds: ['remember-btn'], itemIds: ['mobile-remember'],
        getNext: () => !state.rs,
        apply: (next) => {
            state.rs = next;
            localStorage.rememberScroll = next;
            $('#remember-btn')?.classList.toggle('clean-btn--active', next);
            setIndicator('#mobile-remember-indicator', next);
            if (!next && state.doc) localStorage.removeItem('scroll_' + state.doc);
        }
    });
    bindToggle({
        btnIds: ['theme-btn', 'sidebar-theme-btn'], itemIds: ['mobile-theme'],
        getNext: () => document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark',
        apply: (next) => {
            applyTheme(next);
            setIndicator('#mobile-theme-indicator', next === 'dark');
        }
    });

    on(window, 'resize', () => { clearTimeout(window.rt); window.rt = setTimeout(handleResize, 100); });

    on(window, 'popstate', () => {
        const d = new URLSearchParams(location.search).get('doc');
        if (!d) {
            $('#article-view').style.display = 'none';
            $('#welcome-view').style.display = 'block';
            $('#toc-desktop').style.display = 'none';
            $('#toc-desktop-nav').innerHTML = '';
            document.title = '\u6587\u5e93\u9605\u8bfb\u5668 \u2014 MLCLASSIC';
            state.doc = null;
        } else if (d !== state.doc) {
            loadDoc(d);
        } else if (location.hash) {
            const el = document.getElementById(location.hash.slice(1)) || document.querySelector(`[name="${location.hash.slice(1)}"]`);
            el && scrollToEl(el);
        }
    });

    on(window, 'scroll', () => {
        const h = document.documentElement.scrollHeight - innerHeight;
        const bar = $('#progress-bar');
        if (bar) bar.style.width = (h > 0 ? (scrollY / h) * 100 : 0) + '%';
        clearTimeout(window.st);
        window.st = setTimeout(() => { if (state.rs && state.doc) localStorage.setItem('scroll_' + state.doc, scrollY); }, 300);
    }, { passive: true });

    on(document, 'click', e => {
        const a = e.target.closest('a');
        if (!a) {
            const menu = $('#mobile-menu');
            if (menu && !menu.contains(e.target) && !$('#mobile-menu-toggle').contains(e.target))
                menu.classList.remove('dropdown--open');
            return;
        }

        if (a.closest('#nav-tree') && innerWidth < 997) closeSidebar();

        if (a.classList.contains('navbar__logo') || a.classList.contains('doc-sidebar__brand')) {
            e.preventDefault();
            if ($('#welcome-view').style.display !== 'block') {
                history.pushState({}, '', location.pathname);
                $('#article-view').style.display = 'none';
                $('#welcome-view').style.display = 'block';
                $('#toc-desktop').style.display = 'none';
                $('#toc-desktop-nav').innerHTML = '';
                document.title = '文库阅读器 — MLCLASSIC';
                state.doc = null;
                window.__NAV__?.reinit(null);
                window.__PAGE_BAR__?.scanContent(null);
            }
            closeSidebar();
            return;
        }

        if (isFootnoteLink(a)) {
            e.preventDefault();
            e.stopImmediatePropagation();
            popup.show(a, e);
            return;
        }

        const href = a.getAttribute('href') || '';
        if (href.startsWith('#') && href.length > 1) {
            e.preventDefault();
            const id = href.slice(1);
            const el = document.getElementById(id) || document.querySelector(`[name="${id}"]`);
            if (el) {
                scrollToEl(el);
                const url = new URL(location.href);
                url.hash = id;
                history.replaceState({}, '', url.toString());
            }
            return;
        }

        if (href.startsWith('?doc=')) {
            e.preventDefault();
            const r = resolveDocLink(href, '');
            if (!r || r.type !== 'doc') return;

            const normalize = p => (p || '').replace(/\.html$/i, '').replace(/^\//, '').replace(/\/$/, '');

            // 同页带锚点：直接滚动，不重新加载
            if (normalize(r.docPath) === normalize(state.doc)) {
                if (r.hash) {
                    const el = document.getElementById(r.hash);
                    if (el) {
                        scrollToEl(el);
                        history.pushState({}, '', r.href);
                    }
                }
                return;
            }

            // 跨页跳转：pushState 后 loadDoc，loadDoc 会在 content 显示后自动处理 hash 滚动
            history.pushState({}, '', r.href);
            loadDoc(r.docPath);
            return;
        }
    });

    on(document, 'keydown', e => {
        if (e.key === 'Escape') {
            closeSidebar();
            $('#mobile-menu')?.classList.remove('dropdown--open');
            popup.forceClose();
        }
        if (e.key === 's' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); toggleSidebar(); }
    });
}

// ── 移动端指示器 ──
function setIndicator(sel, active) {
    const el = document.querySelector(sel);
    if (!el) return;
    el.textContent = active ? '\u25cf' : '\u25cb';
    el.style.color = active ? 'var(--accent)' : 'var(--text-3)';
}

function updateMobileMenuIndicators() {
    setIndicator('#mobile-remember-indicator', state.rs);
    setIndicator('#mobile-theme-indicator', document.documentElement.dataset.theme === 'dark');
    ['#mobile-font-slider'].forEach(sel => {
        const el = document.querySelector(sel);
        if (el) { el.value = state.fs; syncFill(el); }
    });
    ['#mobile-lh-slider'].forEach(sel => {
        const el = document.querySelector(sel);
        if (el) { el.value = state.lh; syncFill(el); }
    });
}

// ── 初始化 ──
on(document, 'DOMContentLoaded', () => {
    const sidebar = $('#lsidebar');
    if (sidebar && !sidebar.classList.contains('doc-sidebar')) sidebar.classList.add('doc-sidebar');

    applyTheme(state.th);
    applyFont(state.fs, false);
    applyLineHeight(state.lh, false);
    window.__NAV__ = new MenuManager();
    window.__NAV__.init();
    window.__PAGE_BAR__ = new PageBarManager();
    window.__PAGE_BAR__.init();
    buildWelcomeCards();

    const d = new URLSearchParams(location.search).get('doc');
    if (d) loadDoc(d);
    else {
        $('#welcome-view').style.display = 'block';
        $('#article-view').style.display = 'none';
    }
    bindEvents();
    handleResize();
});
