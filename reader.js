// 极简文库阅读器 —— 悬浮侧边栏版
const state = {
    fs: +localStorage.fontSize || 1,
    rs: localStorage.rememberScroll !== 'false',
    sb: false,
    th: localStorage.theme || 'light',
    doc: null,
    mob: innerWidth < 768
};

const $ = s => document.querySelector(s),
    $$ = s => [...document.querySelectorAll(s)],
    on = (t, e, f) => t.addEventListener(e, f),
    css = (el, obj) => Object.assign(el.style, obj);

// Shadow root for nav isolation — set by buildNav(), used everywhere nav items are queried
let navRoot;
const $nav = s => navRoot.querySelector(s);
const $$nav = s => [...navRoot.querySelectorAll(s)];

// ── 共用：用 basePath 匹配文集 ──────────────────────────────
function findCollection(path) {
    const norm = path.replace(/^\//, '');
    return LIBRARY_CONFIG.find(c => norm.startsWith((c.basePath || `/${c.id}/`).replace(/^\//, '')));
}

// ── 初始化 ─────────────────────────────────────────────────
on(document, 'DOMContentLoaded', () => {
    applyTheme(state.th);
    applyFont(state.fs, 0);
    buildNav();
    buildWelcomeCards();
    const d = new URLSearchParams(location.search).get('doc');
    d ? loadDoc(d) : ($('#welcome').style.display = 'block');
    bindEvents();
    handleResize();
});

// ── 主题与字体 ──────────────────────────────────────────────
function applyTheme(t) {
    document.documentElement.dataset.theme = t;
    localStorage.theme = t;
    css($('#icon-sun'), { display: t === 'dark' ? 'block' : 'none' });
    css($('#icon-moon'), { display: t === 'light' ? 'block' : 'none' });
}

function applyFont(s, sv) {
    s = Math.max(.75, Math.min(1.5, s));
    state.fs = s;
    css($('#content'), { fontSize: 16 * s + 'px', lineHeight: 1.85 * s + 'em' });
    if (sv) localStorage.setItem('fontSize', s);
    $$('#font-slider, #mobile-font-slider').forEach(el => el && (el.value = s));
}

// ── 导航树 ─────────────────────────────────────────────────
function buildNav() {
    const tree = $('#nav-tree');
    tree.innerHTML = '';

    // 创建可折叠节点的通用辅助
    function makeCollapsible(cls, headerHTML, childrenHTML) {
        const el = document.createElement('div');
        el.className = cls;
        el.innerHTML = `<div class="${cls}-header">${headerHTML}<span class="chevron">›</span></div>
                        <div class="${cls}-items" style="display:none">${childrenHTML}</div>`;
        el.querySelector(`.${cls}-header`).onclick = () => {
            el.classList.toggle('open');
            el.querySelector(`.${cls}-items`).style.display =
                el.classList.contains('open') ? 'block' : 'none';
        };
        return el;
    }

    LIBRARY_CONFIG.forEach(c => {
        const sec = document.createElement('div');
        sec.className = 'nav-section';
        sec.dataset.id = c.id;
        sec.innerHTML = `<div class="nav-section-header">
                           <span>${c.label}${c.badge ? ` · ${c.badge}` : ''}</span>
                           <span class="chevron">›</span>
                         </div>
                         <div class="nav-section-items" style="display:none"></div>`;

        sec.querySelector('.nav-section-header').onclick = () => {
            sec.classList.toggle('open');
            sec.querySelector('.nav-section-items').style.display =
                sec.classList.contains('open') ? 'block' : 'none';
        };

        const secItems = sec.querySelector('.nav-section-items');

        c.groups.forEach(g => {
            const grp = document.createElement('div');
            grp.className = 'nav-group';
            grp.innerHTML = `<div class="nav-group-header">
                               <span>${g.label}</span>
                               <span class="chevron">›</span>
                             </div>
                             <div class="nav-group-items" style="display:none"></div>`;

            grp.querySelector('.nav-group-header').onclick = () => {
                grp.classList.toggle('open');
                grp.querySelector('.nav-group-items').style.display =
                    grp.classList.contains('open') ? 'block' : 'none';
            };

            const grpItems = grp.querySelector('.nav-group-items');
            g.items.forEach(x => {
                const path = x.path.replace(/^\//, '');
                const a = document.createElement('a');
                a.className = 'nav-item';
                a.textContent = x.label;
                a.href = '?doc=' + path;
                a.dataset.path = path;
                a.onclick = e => {
                    e.preventDefault();
                    history.pushState({}, '', a.href);
                    loadDoc(path);
                    $$('.nav-item').forEach(n => n.classList.remove('active'));
                    a.classList.add('active');
                    closeSidebar();
                };
                grpItems.appendChild(a);
            });

            secItems.appendChild(grp);
        });

        tree.appendChild(sec);
    });
}

// ── 欢迎页卡片 ─────────────────────────────────────────────
function buildWelcomeCards() {
    const grid = $('#library-cards');
    if (!grid) return;

    LIBRARY_CONFIG.forEach(c => {
        const a = document.createElement('a');
        a.className = 'library-card';
        a.href = '#';
        a.innerHTML = `<div class="card-tag">${c.label}${c.badge ? ' · ' + c.badge : ''}</div>
                       <div class="card-title">${c.title || c.label}</div>
                       <div class="card-desc">${c.desc || '点击查看目录'}</div>`;

        a.onclick = e => {
            e.preventDefault();
            state.sb = true;
            applySidebar();

            const sec = document.querySelector(`.nav-section[data-id="${c.id}"]`);
            if (!sec) return;

            sec.classList.add('open');
            sec.querySelector('.nav-section-items').style.display = 'block';
            sec.style.background = 'var(--accent-bg)';
            setTimeout(() => sec.style.background = '', 1200);

            setTimeout(() => {
                sec.scrollIntoView({ behavior: 'smooth', block: 'center' });
                if (c.groups?.length === 1) {
                    const grp = sec.querySelector('.nav-group');
                    if (grp) {
                        grp.classList.add('open');
                        grp.querySelector('.nav-group-items').style.display = 'block';
                    }
                }
            }, 350);
        };

        grid.appendChild(a);
    });
}

// ── 侧边栏 ─────────────────────────────────────────────────
function toggleSidebar() { state.sb = !state.sb; applySidebar(); }
function closeSidebar() { state.sb = false; applySidebar(); }

function applySidebar() {
    $('#lsidebar').classList.toggle('open', state.sb);
    $('#sidebar-backdrop').classList.toggle('visible', state.sb);
    if (state.mob) document.body.style.overflow = state.sb ? 'hidden' : '';
}

function handleResize() {
    const was = state.mob;
    state.mob = innerWidth < 768;
    if (was !== state.mob) state.sb = false;
    applySidebar();
    $('#mobile-menu')?.classList.remove('visible');
    if (!state.mob) $('#sidebar-toggle').style.display = 'flex';
}

// ── 文档加载 ───────────────────────────────────────────────
// 解析 CSS href（相对路径以文档所在目录 base 为基准）
function resolveCssHref(href, base) {
    // 1. 绝对路径原样返回
    if (/^https?:\/\//.test(href) || href.startsWith('//')) return href;

    // 2. 根路径（去掉开头的 / 以配合你的调用逻辑）
    if (href.startsWith('/')) return href.slice(1);

    try {
        // 3. 关键：确保 base 以 / 结尾（强制为目录），否则 ../ 会回退到错误层级
        const dir = base.endsWith('/') ? base : base + '/';

        // 4. 使用 URL API 正确解析相对路径（支持 ./、../、甚至 ../../../../）
        const resolved = new URL(href, location.origin + '/' + dir);

        // 5. 返回相对于根目录的路径（去掉开头的 /）
        //    如果 href=../style.css，base=lenin/works/，返回 lenin/style.css
        return resolved.pathname.replace(/^\//, '');
    } catch (e) {
        // 6. 极端兜底：如果 URL 构造失败（如 href 含非法字符），
        //    尝试直接拼接，但仍需处理 ../ 以防污染
        console.warn('CSS path resolve failed:', href, base, e);

        // 清理 base 和 href，防止 ../ 污染
        const cleanBase = base.replace(/^\//, '').replace(/\/$/, '');
        const cleanHref = href.replace(/^\.+\//, ''); // 简单移除前导 ./ 和 ../

        return cleanBase ? cleanBase + '/' + cleanHref : cleanHref;
    }
}

async function loadDoc(docPath) {
    $('#welcome').style.display = 'none';
    $$('.dynamic-doc-css, .dynamic-doc-style').forEach(el => el.remove());

    const col = findCollection(docPath);

    // 注入文集级 CSS（head 最前，reader.css 在后可覆盖颜色变量）
    for (const css of col?.stylesheets ?? []) {
        const colBase = (col.basePath || `/${col.id}/`).replace(/^\//, '');
        const link = Object.assign(document.createElement('link'), {
            rel: 'stylesheet', type: 'text/css', className: 'dynamic-doc-css',
            href: resolveCssHref(css, colBase)
        });
        document.head.insertBefore(link, document.head.firstChild);
        await new Promise(r => { link.onload = link.onerror = r; setTimeout(r, 800); });
    }

    const lt = setTimeout(() => {
        $('#doc-view').style.display = 'none';
        $('#loading').style.display = 'block';
    }, 200);

    try {
        const res = await fetch(docPath);
        if (!res.ok) throw new Error(res.status);
        renderDoc(await res.text(), docPath);
    } catch (e) {
        showError(docPath, e.message);
    } finally {
        clearTimeout(lt);
    }
}

function renderDoc(h, path) {
    const d = new DOMParser().parseFromString(h, 'text/html'),
        b = path.substring(0, path.lastIndexOf('/') + 1);

    // 注入文档自带 <link> 和 <style>（追加到 head 末尾）
    $$('.dynamic-doc-style').forEach(el => el.remove());

    d.querySelectorAll('link[rel="stylesheet"]').forEach(lk => {
        const href = lk.getAttribute('href');
        if (!href) return;
        document.head.appendChild(Object.assign(document.createElement('link'), {
            rel: 'stylesheet', className: 'dynamic-doc-style',
            href: resolveCssHref(href, b)
        }));
    });

    d.querySelectorAll('style').forEach(st => {
        const el = document.createElement('style');
        el.className = 'dynamic-doc-style';
        el.textContent = st.textContent;
        document.head.appendChild(el);
    });

    // 修正文档内链接路径
    d.querySelectorAll('a[href]').forEach(a => {
        const x = a.getAttribute('href');
        if (!x || x.startsWith('#') || x.match(/^https?:/)) return;
        const [f, fg] = x.split('#');
        a.href = '?doc=' + (f.startsWith('/') ? f.slice(1) : b + f) + (fg ? '#' + fg : '');
    });

    d.querySelectorAll('[src]').forEach(e => {
        const s = e.getAttribute('src');
        if (s && !s.match(/^(https?:|\/|data:)/)) e.src = b + s;
    });

    const c = $('#content');
    c.innerHTML = d.body.innerHTML;

    // a[name] → 父元素 id（锚点兼容）
    c.querySelectorAll('a[name]').forEach(a => {
        if (a.parentElement && !a.parentElement.id)
            a.parentElement.id = a.getAttribute('name');
    });

    // 标题锚点
    c.querySelectorAll('h2,h3').forEach((h, i) => {
        if (!h.id) h.id = 'h' + i;
        if (!h.querySelector('.anchor'))
            h.insertAdjacentHTML('beforeend', `<a class="anchor" href="#${h.id}">#</a>`);
    });

    $('#loading').style.display = 'none';
    $('#doc-view').style.display = 'block';
    state.doc = path;

    // 面包屑
    const col = findCollection(path);
    const pts = path.split('/');
    $('#doc-collection').textContent = col ? col.label : pts[0];
    $('#doc-volume').textContent = pts[pts.length - 2] || '';
    $('#doc-filename').textContent = pts[pts.length - 1];

    const title = d.querySelector('title')?.textContent?.trim();
    $('#doc-title-display').textContent = title || '';
    document.title = title ? title + ' — MLCLASSIC' : '文库阅读器 — MLCLASSIC';

    buildTOC(c);
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

    updateNav(path.replace(/^\//, ''));
    updatePrevNext(path);
}

function showError(p, m) {
    $('#loading').style.display = 'none';
    $('#doc-view').style.display = 'block';
    $('#content').innerHTML =
        `<p style="color:var(--text-2);padding:40px 0;">无法加载 <code>${p}</code><br><small>${m}</small></p>`;
}

// ── 目录（TOC）与排版 ───────────────────────────────────────
function buildTOC(c) {
    const list = $('#toc-list'), rsb = $('#rsidebar');
    list.innerHTML = '';
    const hs = c.querySelectorAll('h2,h3');
    if (!hs.length) { rsb.style.display = 'none'; return; }

    rsb.style.display = '';
    hs.forEach(h => {
        const a = document.createElement('a');
        a.className = 'toc-item' + (h.tagName === 'H3' ? ' toc-h3' : '');
        a.href = '#' + h.id;
        a.textContent = h.textContent.replace(/#/, '').trim();
        a.onclick = e => {
            e.preventDefault();
            scrollToEl(h);
            history.replaceState(null, '', location.pathname + location.search + '#' + h.id);
        };
        list.appendChild(a);
    });

    state.toc?.disconnect();
    state.toc = new IntersectionObserver(entries => entries.forEach(n => {
        if (!n.isIntersecting) return;
        $$('.toc-item').forEach(x => x.classList.remove('active'));
        list.querySelector(`a[href="#${n.target.id}"]`)?.classList.add('active');
    }), { rootMargin: '-15% 0px -75% 0px' });

    hs.forEach(h => state.toc.observe(h));
}

function fixOverflow(c) {
    requestAnimationFrame(() =>
        c.querySelectorAll('table').forEach(t => {
            if (t.parentElement?.className === 'table-wrapper') return;
            if (t.offsetWidth > c.offsetWidth) {
                const w = document.createElement('div');
                w.className = 'table-wrapper';
                t.parentNode.insertBefore(w, t);
                w.appendChild(t);
            }
        })
    );

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

function scrollToEl(e) {
    window.scrollTo({ top: Math.max(0, e.getBoundingClientRect().top + scrollY - 80), behavior: 'smooth' });
}

function updateNav(p) {
    $$('.nav-item').forEach(a => a.classList.toggle('active', a.dataset.path === p));
}

// ── 前后卷导航 ─────────────────────────────────────────────
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
    const [prev, next] = [$('#prev-btn'), $('#next-btn')];
    prev.style.display = next.style.display = 'none';

    const s = p.lastIndexOf('/');
    if (s === -1) return;
    const dir = p.slice(0, s + 1), file = p.slice(s + 1);

    getM(dir).then(m => {
        if (!m || !Array.isArray(m)) return fallbackNav(dir, file, prev, next);
        const i = m.findIndex(x => x.file === file || x.path?.includes(file));
        if (i < 0) return fallbackNav(dir, file, prev, next);
        if (i > 0) setupBtn(prev, dir + m[i - 1].file, m[i - 1].title, '←');
        if (i < m.length - 1) setupBtn(next, dir + m[i + 1].file, m[i + 1].title, '→');
    }).catch(() => fallbackNav(dir, file, prev, next));
}

function fallbackNav(dir, file, prev, next) {
    const m = file.match(/^(.*?)(\d+)(\.[^.]+)$/);
    if (!m) return;
    const [, prefix, num, ext] = m, pad = num.length;
    const make = n => dir + prefix + String(n).padStart(pad, '0') + ext;
    const tryBtn = async (btn, path) => {
        try { if ((await fetch(path, { method: 'GET', mode: 'same-origin' })).ok) setupBtn(btn, path, null, btn === prev ? '←' : '→'); }
        catch { }
    };
    if (parseInt(num) > 1) tryBtn(prev, make(parseInt(num) - 1));
    tryBtn(next, make(parseInt(num) + 1));
}

function setupBtn(btn, path, title, arrow) {
    if (!btn) return;
    const nameEl = btn.querySelector('.doc-name'),
        dirEl = btn.querySelector('.dir');
    dirEl.textContent = arrow;

    const truncate = t => t.length > 22 ? t.slice(0, 21) + '…' : t;
    nameEl.textContent = title ? truncate(title) : path.split('/').pop().replace(/\.[^.]+$/, '');
    nameEl.title = title || '';

    if (!title) {
        fetch(path).then(r => r.text()).then(h => {
            const t = new DOMParser().parseFromString(h, 'text/html').querySelector('title')?.textContent?.trim();
            if (t) { nameEl.textContent = truncate(t); nameEl.title = t; }
        }).catch(() => { });
    }

    btn.style.display = 'flex';
    btn.onclick = e => { e.preventDefault(); history.pushState({}, '', '?doc=' + path); loadDoc(path); };
}

// ── 事件绑定 ───────────────────────────────────────────────
function bindEvents() {
    on($('#sidebar-toggle'), 'click', toggleSidebar);
    on($('#sidebar-backdrop'), 'click', closeSidebar);

    on($('#mobile-menu-toggle'), 'click', e => {
        e.stopPropagation();
        const menu = $('#mobile-menu');
        const opening = !menu.classList.contains('visible');
        menu.classList.toggle('visible');
        if (opening) updateMobileMenuIndicators();
    });

    // 字号
    const adj = d => applyFont(state.fs + d);
    [['#font-dec-btn', '#mobile-font-dec', -.05], ['#font-inc-btn', '#mobile-font-inc', .05]].forEach(([a, b, d]) => {
        [$(a), $(b)].forEach(el => el && on(el, 'click', () => adj(d)));
    });
    [[$('#font-slider'), 0], [$('#mobile-font-slider'), 0]].forEach(([el]) =>
        el && on(el, 'input', e => applyFont(parseFloat(e.target.value), 0)));

    // 记忆滚动位置
    const toggleRemember = e => {
        e?.stopPropagation();
        state.rs = !state.rs;
        localStorage.rememberScroll = state.rs;
        $('#remember-btn')?.classList.toggle('active', state.rs);
        if ($('#remember-btn')) $('#remember-btn').title = state.rs ? '记忆阅读位置：已开启' : '记忆阅读位置：已关闭';
        setIndicator('#mobile-remember-indicator', state.rs);
        if (!state.rs && state.doc) localStorage.removeItem('scroll_' + state.doc);
    };

    // 切换主题
    const toggleTheme = e => {
        e?.stopPropagation();
        const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
        applyTheme(next);
        setIndicator('#mobile-theme-indicator', next === 'dark');
    };

    [$('#remember-btn'), $('#mobile-remember')].forEach(el => el && on(el, 'click', toggleRemember));
    [$('#theme-btn'), $('#mobile-theme')].forEach(el => el && on(el, 'click', toggleTheme));

    // 搜索
    const si = $('#search-input'), so = $('#search-overlay');
    if (si) {
        on(si, 'input', () => {
            const q = si.value.trim();
            if (!q) return so.classList.remove('visible');
            const text = $('#content').textContent || '';
            const re = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
            const hits = []; let r;
            while ((r = re.exec(text)) !== null && hits.length < 8)
                hits.push(text.slice(Math.max(0, r.index - 40), r.index + q.length + 40));
            so.innerHTML = hits.length
                ? hits.map(s => `<div class="search-result"><div class="sr-excerpt">…${s.replace(/</g, '&lt;')}…</div></div>`).join('')
                : '<div class="search-no-results">无结果</div>';
            so.classList.add('visible');
        });
        on(si, 'keydown', e => e.key === 'Escape' && (so.classList.remove('visible'), si.value = '', si.blur()));
    }

    // 窗口 / 滚动 / 历史
    on(window, 'resize', () => { clearTimeout(window.rt); window.rt = setTimeout(handleResize, 100); });

    on(window, 'popstate', () => {
        const d = new URLSearchParams(location.search).get('doc');
        if (d === state.doc && location.hash) {
            const el = document.getElementById(location.hash.slice(1)) ||
                document.querySelector(`[name="${location.hash.slice(1)}"]`);
            el && scrollToEl(el);
        } else if (d) {
            loadDoc(d);
        } else {
            $('#doc-view').style.display = 'none';
            $('#welcome').style.display = 'block';
            document.title = '文库阅读器 — MLCLASSIC';
            state.doc = null;
        }
    });

    on(window, 'scroll', () => {
        const h = document.documentElement.scrollHeight - innerHeight;
        css($('#progress-bar'), { width: (h > 0 ? scrollY / h * 100 : 0) + '%' });
        clearTimeout(window.st);
        window.st = setTimeout(() => state.rs && state.doc && localStorage.setItem('scroll_' + state.doc, scrollY), 300);
    }, { passive: true });

    // 文档内点击：锚点 + 脚注提示 + 关闭移动菜单
    on(document, 'click', e => {
        const a = e.target.closest('a');

        if (a?.hash && a.closest('#content') && !a.search?.includes('doc=')) {
            e.preventDefault();
            const el = document.getElementById(a.hash.slice(1)) ||
                document.querySelector(`[name="${a.hash.slice(1)}"]`);
            el && scrollToEl(el);
        }

        if (a) {
            const h = a.getAttribute('href');
            if (h?.match(/^#(fn|FN|M|E|F|a|b|z|c|n|p)/)) {
                const tip = $('#fn-tooltip');
                const target = $(h.slice(1)) || document.querySelector(`a[name="${h.slice(1)}"]`);
                if (target) {
                    tip.innerHTML = target.innerHTML;
                    tip.classList.add('visible');
                    css(tip, {
                        left: Math.min(e.clientX + 12, innerWidth - 360) + 'px',
                        top: Math.min(e.clientY + 12, innerHeight - 100) + 'px'
                    });
                    on(a, 'mouseleave', () => tip.classList.remove('visible'), { once: true });
                }
            }
        }

        if (!$('#mobile-menu').contains(e.target) && !$('#mobile-menu-toggle').contains(e.target))
            $('#mobile-menu').classList.remove('visible');
    });

    on(document, 'keydown', e => {
        if (e.key === 'Escape') {
            closeSidebar();
            $('#mobile-menu')?.classList.remove('visible');
            $('#search-overlay')?.classList.remove('visible');
            $('#search-input')?.blur();
        }
        if (e.key === 's' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); toggleSidebar(); }
        if (e.key === '/' && e.target.tagName !== 'INPUT') { e.preventDefault(); $('#search-input')?.focus(); }
    });
}

// ── 移动端菜单指示器 ────────────────────────────────────────
function setIndicator(sel, active) {
    const el = $(sel);
    if (!el) return;
    el.textContent = active ? '●' : '○';
    el.style.color = active ? 'var(--accent)' : 'var(--text-3)';
}

function updateMobileMenuIndicators() {
    setIndicator('#mobile-remember-indicator', state.rs);
    setIndicator('#mobile-theme-indicator', document.documentElement.dataset.theme === 'dark');
    const fs = $('#mobile-font-slider');
    if (fs) fs.value = state.fs;
}