// 极简 SPA 阅读器 —— 壳子对齐 SSG reader.css
const state = {
    fs: parseFloat(localStorage.fontSize) || 1,
    rs: localStorage.rememberScroll !== 'false',
    sb: false,
    th: localStorage.theme || 'light',
    doc: null,
    mob: innerWidth < 768,
    tocScrollHandler: null
};

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const on = (t, e, f) => t && t.addEventListener(e, f);
const esc = t => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
// ── Range slider fill sync ──
function syncFill(el) {
    const min = parseFloat(el.min) || 0;
    const max = parseFloat(el.max) || 100;
    const val = parseFloat(el.value) || 0;
    const pct = ((val - min) / (max - min) * 100).toFixed(2) + '%';
    el.style.setProperty('--_fill', pct);
}

const resolveUrl = href => { try { return new URL(href, location.href).href; } catch { return location.pathname.replace(/[^/]*$/, '') + href; } };

// ── 文集匹配 ──
function findCollection(path) {
    const norm = path.replace(/^\//, '');
    return window.LIBRARY_CONFIG?.find(c => norm.startsWith((c.basePath || `/${c.id}/`).replace(/^\//, '')));
}

// ── 初始化 ──
on(document, 'DOMContentLoaded', () => {
    // 确保侧边栏类名存在（兼容旧 HTML）
    const sidebar = $('#lsidebar');
    if (sidebar && !sidebar.classList.contains('doc-sidebar')) sidebar.classList.add('doc-sidebar');

    applyTheme(state.th);
    applyFont(state.fs, false);
    window.__NAV__ = new MenuManager();
    window.__NAV__.init();
    buildWelcomeCards();

    const d = new URLSearchParams(location.search).get('doc');
    if (d) {
        loadDoc(d);
    } else {
        $('#welcome-view').style.display = 'block';
        $('#article-view').style.display = 'none';
    }
    bindEvents();
    handleResize();
});

// ── 主题 / 字体 ──
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
    $$('#font-slider, #mobile-font-slider').forEach(el => {
        if (el) {
            el.value = s;
            syncFill(el);
        }
    });
}

// ── 导航树（简单手风琴，类名对齐 reader.css） ──
function buildNav() {
    const tree = $('#nav-tree');
    tree.innerHTML = '<ul class="sidebar-menu"></ul>';
    const root = tree.querySelector('.sidebar-menu');

    LIBRARY_CONFIG.forEach(col => {
        const hasGroups = (col.groups || []).length > 0;
        const colPath = (col.path || '').replace(/^\//, '');
        const isExt = colPath.startsWith('http');

        // 无 groups 但有 path → 直接渲染为链接
        if (!hasGroups && colPath) {
            const li = document.createElement('li');
            li.className = 'sidebar-item';
            const badge = col.badge ? ` <span class="sidebar-badge">${esc(col.badge)}</span>` : '';
            const href = isExt ? col.path : `?doc=${esc(colPath)}`;
            li.innerHTML = `<a href="${esc(href)}"${isExt ? ' target="_blank" rel="noopener"' : ''} data-path="${esc('/' + colPath)}" class="sidebar-link">${esc(col.label)}${badge}</a>`;
            const a = li.querySelector('a');
            if (!isExt) {
                a.addEventListener('click', ev => {
                    ev.preventDefault();
                    history.pushState({}, '', a.href);
                    loadDoc(colPath);
                    updateNavActive(colPath);
                    if (innerWidth < 997) closeSidebar();
                });
            }
            root.appendChild(li);
            return;
        }

        // 无 groups 也无 path → 纯文本 label
        if (!hasGroups && !colPath) {
            const li = document.createElement('li');
            li.className = 'sidebar-item';
            const badge = col.badge ? ` <span class="sidebar-badge">${esc(col.badge)}</span>` : '';
            li.innerHTML = `<span class="sidebar-category-label">${esc(col.label)}${badge}</span>`;
            root.appendChild(li);
            return;
        }

        // 有 groups → 可折叠结构
        const li = document.createElement('li');
        li.className = 'sidebar-item sidebar-item--category sidebar-item--collapsible';
        li.dataset.collapsed = 'true';
        li.dataset.section = col.id;

        const badge = col.badge ? ` <span class="sidebar-badge">${esc(col.badge)}</span>` : '';
        li.innerHTML = `
          <div class="sidebar-item-row">
            <span class="sidebar-category-label">${esc(col.label)}${badge}</span>
            <button class="sidebar-caret" type="button" aria-label="Expand" tabindex="0">\u25b8</button>
          </div>`;

        const row = li.querySelector('.sidebar-item-row');
        const caret = li.querySelector('.sidebar-caret');

        const toggle = (e) => {
            e.stopPropagation();
            const collapsed = li.getAttribute('data-collapsed') !== 'false';
            li.setAttribute('data-collapsed', collapsed ? 'false' : 'true');
            caret.textContent = collapsed ? '\u25be' : '\u25b8';

            if (collapsed && !li.dataset.loaded && hasGroups) {
                const nested = document.createElement('ul');
                nested.className = 'sidebar-menu sidebar-menu--nested';
                col.groups.forEach(g => {
                    const hasItems = (g.items || []).length > 0;
                    const groupPath = (g.path || '').replace(/^\//, '');
                    const isExt = groupPath.startsWith('http');

                    // Case 1: no items but has path → render as direct link
                    if (!hasItems && groupPath) {
                        const gLi = document.createElement('li');
                        gLi.className = 'sidebar-item';
                        const href = isExt ? g.path : `?doc=${esc(groupPath)}`;
                        gLi.innerHTML = `<a href="${esc(href)}"${isExt ? ' target="_blank" rel="noopener"' : ''} data-path="${esc('/' + groupPath)}" class="sidebar-link">${esc(g.label)}</a>`;
                        const a = gLi.querySelector('a');
                        if (!isExt) {
                            a.addEventListener('click', ev => {
                                ev.preventDefault();
                                history.pushState({}, '', a.href);
                                loadDoc(groupPath);
                                updateNavActive(groupPath);
                                if (innerWidth < 997) closeSidebar();
                            });
                        }
                        nested.appendChild(gLi);
                        return;
                    }

                    // Case 2: no items and no path → render as plain text label
                    if (!hasItems && !groupPath) {
                        const gLi = document.createElement('li');
                        gLi.className = 'sidebar-item';
                        gLi.innerHTML = `<span class="sidebar-category-label">${esc(g.label)}</span>`;
                        nested.appendChild(gLi);
                        return;
                    }

                    // Case 3: has items → collapsible structure
                    const gLi = document.createElement('li');
                    gLi.className = 'sidebar-item sidebar-item--category sidebar-item--collapsible';
                    gLi.dataset.collapsed = 'true';
                    gLi.innerHTML = `
                      <div class="sidebar-item-row">
                        <span class="sidebar-category-label">${esc(g.label)}</span>
                        <button class="sidebar-caret" type="button" aria-label="Expand" tabindex="0">\u25b8</button>
                      </div>`;
                    const items = document.createElement('ul');
                    items.className = 'sidebar-menu sidebar-menu--nested';
                    (g.items || []).forEach(x => {
                        const path = (x.path || '').replace(/^\//, '');
                        const iLi = document.createElement('li');
                        iLi.className = 'sidebar-item';
                        iLi.innerHTML = `<a href="?doc=${esc(path)}" data-path="${esc(path)}" class="sidebar-link">${esc(x.label || x.title || '')}</a>`;
                        const a = iLi.querySelector('a');
                        a.addEventListener('click', ev => {
                            ev.preventDefault();
                            history.pushState({}, '', a.href);
                            loadDoc(path);
                            updateNavActive(path);
                            if (innerWidth < 997) closeSidebar();
                        });
                        items.appendChild(iLi);
                    });
                    gLi.appendChild(items);

                    const gRow = gLi.querySelector('.sidebar-item-row');
                    const gCaret = gLi.querySelector('.sidebar-caret');
                    const gToggle = (ev) => {
                        ev.stopPropagation();
                        const gCol = gLi.getAttribute('data-collapsed') !== 'false';
                        gLi.setAttribute('data-collapsed', gCol ? 'false' : 'true');
                        gCaret.textContent = gCol ? '\u25be' : '\u25b8';
                    };
                    gRow.addEventListener('click', gToggle);
                    gCaret.addEventListener('click', gToggle);
                    gCaret.addEventListener('keydown', ev => {
                        if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); gToggle(ev); }
                    });
                    nested.appendChild(gLi);
                });
                li.appendChild(nested);
                li.dataset.loaded = 'true';
            }
        };

        row.addEventListener('click', toggle);
        caret.addEventListener('click', toggle);
        caret.addEventListener('keydown', ev => {
            if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); toggle(ev); }
        });
        root.appendChild(li);
    });
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
    // 强制确保基础 CSS 类存在（HTML 可能未写）
    if (!sidebar.classList.contains('doc-sidebar')) sidebar.classList.add('doc-sidebar');

    const isMobile = innerWidth < 997;
    if (isMobile) {
        // 同时兼容旧版 .open 和 SSG 版 .doc-sidebar--open
        sidebar.classList.toggle('open', state.sb);
        sidebar.classList.toggle('doc-sidebar--open', state.sb);
        // 防御性修复：关闭 sidebar 时禁用 pointer-events，防止其不可见区域
        //（transform 移出屏幕后）拦截 navbar 的汉堡按钮点击
        sidebar.style.pointerEvents = state.sb ? 'auto' : 'none';
        backdrop && backdrop.classList.toggle('visible', state.sb);
        backdrop && backdrop.classList.toggle('sidebar-overlay--visible', state.sb);
        // 注意：不设置 body.style.overflow，避免 iOS Safari 等浏览器中
        // overflow:hidden 导致 position:fixed 元素定位异常（需滚回顶部才可见）
    } else {
        sidebar.classList.remove('open');
        sidebar.classList.remove('doc-sidebar--open');
        sidebar.style.pointerEvents = '';
        backdrop && backdrop.classList.remove('visible');
        backdrop && backdrop.classList.remove('sidebar-overlay--visible');
    }
}

function handleResize() {
    const was = state.mob;
    state.mob = innerWidth < 768;
    if (was !== state.mob) {
        $('#mobile-menu')?.classList.remove('dropdown--open');
    }
    applySidebar();
}

// ── CSS 路径解析 ──
function resolveCssHref(href, base) {
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
}

// ── 文档加载 ──
async function loadDoc(docPath) {
    $('#welcome-view').style.display = 'none';
    $('#article-view').style.display = 'block';
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
        if (!x || x.startsWith('#') || x.match(/^https?:/)) return;
        const [f, fg] = x.split('#');
        a.href = '?doc=' + (f.startsWith('/') ? f.slice(1) : base + f) + (fg ? '#' + fg : '');
    });

    d.querySelectorAll('[src]').forEach(e => {
        const s = e.getAttribute('src');
        if (s && !s.match(/^(https?:|\/|data:)/)) e.src = base + s;
    });

    const c = $('#content');
    c.innerHTML = d.body.innerHTML;

    c.querySelectorAll('a[name]').forEach(a => {
        if (a.parentElement && !a.parentElement.id)
            a.parentElement.id = a.getAttribute('name');
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

    if (location.hash) {
        const el = document.getElementById(location.hash.slice(1)) ||
            document.querySelector(`[name="${location.hash.slice(1)}"]`);
        el && scrollToEl(el);
    } else if (state.rs) {
        const s = localStorage.getItem('scroll_' + path);
        s && window.scrollTo(0, parseInt(s));
    } else {
        window.scrollTo(0, 0);
    }

    updatePrevNext(path);
    window.__NAV__?.reinit(state.doc);
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
        parts.push(`<span class="crumb-sep">/</span><span class="crumb">${esc(pts[i])}</span>`);
    }
    const file = pts[pts.length - 1];
    if (file) parts.push(`<span class="crumb-sep">/</span><span class="crumb crumb--active">${esc(file)}</span>`);
    if (title) parts.push(`<span class="crumb-sep">/</span><span class="crumb crumb--active">${esc(title)}</span>`);
    bar.innerHTML = parts.join('');
}

// ── 桌面端 TOC（右侧栏） ──
function buildTocDesktop(container) {
    const nav = $('#toc-desktop-nav');
    const wrap = $('#toc-desktop');
    nav.innerHTML = '';

    const hs = Array.from(container.querySelectorAll('h1[id],h2[id],h3[id],h4[id],h5[id],h6[id]'));
    if (!hs.length) { wrap.style.display = 'none'; return; }

    wrap.style.display = '';
    let html = '<div class="theme-doc-toc-desktop-header">On this page</div>';
    html += '<ul class="theme-doc-toc-desktop-list">';
    hs.forEach(h => {
        const lvl = parseInt(h.tagName[1]);
        const cls = 'theme-doc-toc-desktop-link theme-doc-toc-desktop-link--lvl' + (lvl - 1);
        html += `<li class="${esc(cls)}"><a href="#${esc(h.id)}" class="theme-doc-toc-desktop-link__a">${esc(h.textContent.replace(/#/, '').trim())}</a></li>`;
    });
    html += '</ul>';
    nav.innerHTML = html;

    if (state.tocScrollHandler) window.removeEventListener('scroll', state.tocScrollHandler, { passive: true });
    let lastId = null;
    const onScroll = () => {
        let activeId = null;
        for (let i = hs.length - 1; i >= 0; i--) {
            if (hs[i].getBoundingClientRect().top <= 200) { activeId = hs[i].id; break; }
        }
        if (!activeId && hs.length) activeId = hs[0].id;
        if (activeId && activeId !== lastId) {
            lastId = activeId;
            nav.querySelectorAll('.theme-doc-toc-desktop-link__a').forEach(a => a.classList.remove('theme-doc-toc-desktop-link__a--active'));
            const match = nav.querySelector(`a[href="#${CSS.escape(activeId)}"]`);
            if (match) match.classList.add('theme-doc-toc-desktop-link__a--active');
        }
    };
    state.tocScrollHandler = onScroll;
    window.addEventListener('scroll', onScroll, { passive: true });
    requestAnimationFrame(onScroll);

    nav.querySelectorAll('a').forEach(a => {
        a.addEventListener('click', e => {
            e.preventDefault();
            const id = a.getAttribute('href').slice(1);
            const el = document.getElementById(id);
            if (el) {
                el.scrollIntoView({ behavior: 'smooth' });
                history.replaceState(null, '', location.pathname + location.search + '#' + id);
            }
        });
    });
}

function fixOverflow(c) {
    requestAnimationFrame(() => {
        c.querySelectorAll('table').forEach(t => {
            if (t.parentElement?.classList.contains('table-wrapper')) return;
            if (t.offsetWidth > c.offsetWidth) {
                const w = document.createElement('div');
                w.className = 'table-wrapper';
                t.parentNode.insertBefore(w, t);
                w.appendChild(t);
            }
        });
    });
    c.querySelectorAll('img').forEach(img => {
        const clamp = () => {
            if (img.naturalWidth > img.parentElement.offsetWidth) {
                img.style.maxWidth = '100%';
                img.style.height = 'auto';
            }
        };
        img.complete ? clamp() : (img.onload = clamp);
    });
}

function scrollToEl(el) {
    window.scrollTo({ top: Math.max(0, el.getBoundingClientRect().top + scrollY - 80), behavior: 'smooth' });
}

function updateNavActive(p) {
    $$('.sidebar-link').forEach(a => a.classList.toggle('sidebar-link--active', a.dataset.path === p));
}

function showError(p, m) {
    $('#content').innerHTML = `<p style="color:var(--text-2);padding:40px 0;">无法加载 <code>${esc(p)}</code><br><small>${esc(m)}</small></p>`;
    $('#content').style.display = 'block';
    $('#content').style.opacity = '1';
}

// ── 前后篇导航 ──
const mf = {};

async function getM(dir) {
    if (mf[dir]) return mf[dir];
    const base = (dir.startsWith('/') ? dir : '/' + dir).replace(/\/?$/, '/');
    const vol = base.replace(/\/$/, '').split('/').pop();
    for (const name of ['index.json', `index${vol}.json`, `/${vol}/index.json`]) {
        try {
            const r = await fetch(base + name.replace(/^\//, ''));
            if (r.ok) return (mf[dir] = await r.json());
        } catch { }
    }
    return null;
}

function updatePrevNext(p) {
    const prev = $('#prev-btn'), next = $('#next-btn');
    prev.style.display = next.style.display = 'none';

    const s = p.lastIndexOf('/');
    if (s === -1) return;
    const dir = p.slice(0, s + 1), file = p.slice(s + 1);

    getM(dir).then(m => {
        if (!m || !Array.isArray(m)) return fallbackNav(dir, file, prev, next);
        const i = m.findIndex(x => x.file === file || x.path?.includes(file));
        if (i < 0) return fallbackNav(dir, file, prev, next);
        if (i > 0) setupPaginationBtn(prev, dir + m[i - 1].file, m[i - 1].title, 'prev');
        if (i < m.length - 1) setupPaginationBtn(next, dir + m[i + 1].file, m[i + 1].title, 'next');
    }).catch(() => fallbackNav(dir, file, prev, next));
}

function fallbackNav(dir, file, prev, next) {
    const m = file.match(/^(.*?)(\d+)(\.[^.]+)$/);
    if (!m) return;
    const [, prefix, num, ext] = m, pad = num.length;
    const make = n => dir + prefix + String(n).padStart(pad, '0') + ext;
    const tryBtn = async (btn, path) => {
        try {
            const r = await fetch(path, { method: 'HEAD', mode: 'same-origin' });
            if (r.ok) setupPaginationBtn(btn, path, null, btn === prev ? 'prev' : 'next');
        } catch { }
    };
    if (parseInt(num) > 1) tryBtn(prev, make(parseInt(num) - 1));
    tryBtn(next, make(parseInt(num) + 1));
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
        fetch(path).then(r => r.text()).then(h => {
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

// ── 脚注判定（纯 <sup> 包裹） ──
function isFootnoteLink(a) {
    if (a.hasAttribute('data-fn-ref') || a.hasAttribute('data-fn-cross')) return true;
    const href = a.getAttribute('href') || '';
    if (!href.includes('#') || href.startsWith('http') || href.startsWith('//')) return false;
    const inSup = a.closest('sup') || a.querySelector('sup');
    return !!inSup;
}

// ── 脚注弹窗（先显示 loading，再异步加载；跨页 3s timeout） ──
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
            // SPA 路由格式 ?doc=path → 提取实际文件路径，避免 fetch 壳子 reader.html
            if (beforeHash.startsWith('?doc=')) {
                pageUrl = beforeHash.slice(5);
            } else {
                pageUrl = resolveUrl(beforeHash);
            }
            isCross = true;
        } else {
            return;
        }

        this._trigger = a;

        // 立即显示弹窗（loading），避免跨页 fetch 时"好几秒没反应"
        this._renderLoading(isCross);
        this._position(e);
        this.tip.classList.add('popover--visible');
        this._active = true;
        document.addEventListener('click', this._dismiss, true);
        document.addEventListener('keydown', this._dismiss);
        window.addEventListener('scroll', this._reposition, { passive: true });

        const result = await this._resolveTarget(targetId, pageUrl, isCross);
        if (!result) {
            this._renderError(isCross);
            return;
        }
        this._render(result.block, href, isCross);
        // 内容高度变化后重新定位，防止溢出视口
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

    // 优先返回包含 target 的最近块级元素，且位于 notes 容器内
    _toBlock(target) {
        const notes = '.fni, .footnote, .endnote, .fn, .note';
        const tag = target.tagName;

        // 1. 自身就是合适的块级容器
        if (tag === 'LI' || tag === 'DD') return target;
        if ((tag === 'DIV' || tag === 'P') && target.closest(notes)) return target;

        // 2. 向上找第一个 div/p/li/dd；
        //    如果该元素自身就是 notes 容器，返回它（包含全部子内容）
        //    如果它是 notes 的后代，返回它（比 notes 容器更精确）
        let el = target.parentElement;
        while (el && el !== document.body) {
            const t = el.tagName;
            if (t === 'DIV' || t === 'P' || t === 'LI' || t === 'DD') {
                if (el.matches(notes)) return el;          // 例如 <div class="footnote">
                if (el.closest(notes)) return el;            // 例如 <div> 嵌套在 <aside class="footnote"> 内
                break;                                       // 找到块级元素但不在 notes 内，停止
            }
            el = el.parentElement;
        }

        // 3. 兜底：返回 notes 容器或 target 自身
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

    _renderLoading(isCross) {
        const viewer = this.tip.querySelector('.popover__body');
        if (!viewer) return;
        viewer.innerHTML = `<div style="color:var(--text-3);font-size:13px;padding:4px 0;">${isCross ? '\u52a0\u8f7d\u8de8\u9875\u6ce8\u91ca\u4e2d\u2026' : '\u52a0\u8f7d\u4e2d\u2026'}</div>`;
    }

    _renderError(isCross) {
        const viewer = this.tip.querySelector('.popover__body');
        if (!viewer) return;
        viewer.innerHTML = `<div style="color:var(--accent);font-size:13px;padding:4px 0;">${isCross ? '\u8de8\u9875\u6ce8\u91ca\u52a0\u8f7d\u5931\u8d25\uff08\u8d85\u65f6\u6216\u65e0\u6cd5\u8bbf\u95ee\uff09' : '\u672a\u627e\u5230\u5bf9\u5e94\u6ce8\u91ca'}</div>`;
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
        // 强制 fixed 定位：避免滚动后 absolute 定位被正文层叠上下文干扰
        menu.style.position = 'fixed';
        menu.style.top = 'calc(var(--nav-h) + 6px)';
        menu.classList.toggle('dropdown--open');
        if (menu.classList.contains('dropdown--open')) updateMobileMenuIndicators();
    };
    const toggleBtn = $('#mobile-menu-toggle');
    if (toggleBtn) {
        toggleBtn.addEventListener('click', toggleMobileMenu);
        // touchend 兜底：部分移动端浏览器滚动后 click 事件丢失
        toggleBtn.addEventListener('touchend', (e) => {
            e.preventDefault();
            toggleMobileMenu(e);
        }, { passive: false });
    }

    // 字号
    const adj = d => applyFont(state.fs + d, true);
    [['font-dec-btn', 'mobile-font-dec', -.05], ['font-inc-btn', 'mobile-font-inc', .05]].forEach(([a, b, d]) => {
        const elA = document.getElementById(a);
        const elB = document.getElementById(b);
        if (elA) on(elA, 'click', () => adj(d));
        if (elB) on(elB, 'click', () => adj(d));
    });
    ['font-slider', 'mobile-font-slider'].forEach(id => {
        const el = document.getElementById(id);
        if (el) on(el, 'input', e => applyFont(parseFloat(e.target.value), true));
    });

    // 记忆滚动
    const toggleRemember = e => {
        e?.stopPropagation();
        state.rs = !state.rs;
        localStorage.rememberScroll = state.rs;
        $('#remember-btn')?.classList.toggle('clean-btn--active', state.rs);
        setIndicator('#mobile-remember-indicator', state.rs);
        if (!state.rs && state.doc) localStorage.removeItem('scroll_' + state.doc);
    };

    // 主题
    const toggleTheme = e => {
        e?.stopPropagation();
        const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
        applyTheme(next);
        setIndicator('#mobile-theme-indicator', next === 'dark');
    };

    on($('#remember-btn'), 'click', toggleRemember);
    on($('#mobile-remember'), 'click', toggleRemember);
    on($('#theme-btn'), 'click', toggleTheme);
    on($('#sidebar-theme-btn'), 'click', toggleTheme);
    on($('#mobile-theme'), 'click', toggleTheme);

    // 窗口 / 历史 / 滚动
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
            const el = document.getElementById(location.hash.slice(1)) ||
                document.querySelector(`[name="${location.hash.slice(1)}"]`);
            el && scrollToEl(el);
        }
    });

    on(window, 'scroll', () => {
        const h = document.documentElement.scrollHeight - innerHeight;
        const bar = $('#progress-bar');
        if (bar) bar.style.width = (h > 0 ? (scrollY / h) * 100 : 0) + '%';
        clearTimeout(window.st);
        window.st = setTimeout(() => {
            if (state.rs && state.doc) localStorage.setItem('scroll_' + state.doc, scrollY);
        }, 300);
    }, { passive: true });

    // 全局点击：脚注 + 锚点 + 路由 + 关闭菜单
    on(document, 'click', e => {
        const a = e.target.closest('a');
        if (!a) {
            const menu = $('#mobile-menu');
            if (menu && !menu.contains(e.target) && !$('#mobile-menu-toggle').contains(e.target))
                menu.classList.remove('dropdown--open');
            return;
        }

        // 1) 脚注弹窗（最高优先级）
        if (isFootnoteLink(a)) {
            e.preventDefault();
            e.stopImmediatePropagation();
            popup.show(a, e);
            return;
        }

        // 2) 文档内部锚点
        const href = a.getAttribute('href') || '';
        if (href.startsWith('#') && href.length > 1 && a.closest('#content')) {
            e.preventDefault();
            const el = document.getElementById(href.slice(1)) || document.querySelector(`[name="${href.slice(1)}"]`);
            el && scrollToEl(el);
            return;
        }

        // 3) SPA 路由拦截
        if (href.startsWith('?doc=')) {
            e.preventDefault();
            const docPath = href.slice(5).split('#')[0];
            const hash = href.includes('#') ? href.slice(href.indexOf('#')) : '';
            history.pushState({}, '', href);
            loadDoc(docPath);
            if (hash) setTimeout(() => {
                const el = document.getElementById(hash.slice(1));
                el && scrollToEl(el);
            }, 100);
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
    const fs = $('#mobile-font-slider');
    if (fs) fs.value = state.fs;
}