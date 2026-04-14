// 极简文库阅读器 —— 悬浮侧边栏版，代码≤500行
const state = { fs: +localStorage.fontSize || 1, rs: localStorage.rememberScroll !== 'false', sb: false, th: localStorage.theme || 'light', doc: null, mob: innerWidth < 768 };
const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)], on = (t, e, f) => t.addEventListener(e, f);
const rs = (a, b) => Object.assign(a.style, b);

// 初始化
on(document, 'DOMContentLoaded', () => {
    applyTheme(state.th); applyFont(state.fs, 0); buildNav();
    buildWelcomeCards();  // ← 加这行
    const d = new URLSearchParams(location.search).get('doc');
    d ? loadDoc(d) : $('#welcome').style.display = 'block';
    bindEvents(); handleResize();
});

// 功能
function applyTheme(t) { document.documentElement.dataset.theme = t; localStorage.theme = t; $('#icon-sun') && (rs($('#icon-sun'), { display: t === 'dark' ? 'block' : 'none' }), rs($('#icon-moon'), { display: t === 'light' ? 'block' : 'none' })); }
function applyFont(s, sv) { s = Math.max(.75, Math.min(1.5, s)); state.fs = s; rs($('#content'), { fontSize: 16 * s + 'px', lineHeight: 1.85 * s + 'em' }); sv && localStorage.setItem('fontSize', s); $('#font-slider').value = s; $('#mobile-font-slider') && ($('#mobile-font-slider').value = s); }
function buildNav() {
    const t = $('#nav-tree');
    t.innerHTML = ''; // 先清空，防止重复

    LIBRARY_CONFIG.forEach(c => {
        // 默认收起：去掉 'open' 类
        const s = document.createElement('div');
        s.className = 'nav-section';  // ← 默认收起，去掉 'open'
        s.dataset.id = c.id;
        s.innerHTML = `<div class="nav-section-header"><span>${c.label}${c.badge ? ` · ${c.badge}` : ''}</span><span class="chevron">›</span></div><div class="nav-section-items" style="display:none"></div>`;

        const i = s.querySelector('.nav-section-items');
        c.groups.forEach(g => {
            // 默认收起：去掉 'open' 类，items 默认 display:none
            
            const r = document.createElement('div');
            r.className = 'nav-group';  // ← 默认收起，去掉 'open'//r.className = 'nav-section open';
            r.innerHTML = `<div class="nav-group-header"><span>${g.label}</span><span class="chevron">›</span></div><div class="nav-group-items" style="display:none"></div>`;

            const m = r.querySelector('.nav-group-items');
            g.items.forEach(x => {
                const a = document.createElement('a');
                a.className = 'nav-item';
                a.textContent = x.label;
                a.href = '?doc=' + x.path.replace(/^\//, '');
                a.dataset.path = x.path.replace(/^\//, '');
                a.onclick = e => {
                    e.preventDefault();
                    history.pushState({}, '', a.href);
                    loadDoc(x.path.replace(/^\//, ''));
                    $$('.nav-item').forEach(n => n.classList.remove('active'));
                    a.classList.add('active');
                    closeSidebar();
                };
                m.appendChild(a);
            });

            // 点击展开/收起
            r.querySelector('.nav-group-header').onclick = () => {
                r.classList.toggle('open');
                r.querySelector('.nav-group-items').style.display = r.classList.contains('open') ? 'block' : 'none';
            };
            i.appendChild(r);
        });

        // 点击展开/收起
        s.querySelector('.nav-section-header').onclick = () => {
            s.classList.toggle('open');
            s.querySelector('.nav-section-items').style.display = s.classList.contains('open') ? 'block' : 'none';
        };
        t.appendChild(s);
    });
}

function buildWelcomeCards() {
    const grid = $('#library-cards');
    if (!grid) return;

    LIBRARY_CONFIG.forEach(c => {
        const a = document.createElement('a');
        a.className = 'library-card';
        a.href = '#';
        a.innerHTML = `
            <div class="card-tag">${c.label}${c.badge ? ' · ' + c.badge : ''}</div>
            <div class="card-title">${c.title || c.label}</div>
            <div class="card-desc">${c.desc || '点击查看目录'}</div>
        `;
        a.onclick = e => {
            e.preventDefault();

            // 打开侧边栏
            openSidebar();

            // 找到对应文集并展开（确保展开）
            const sec = document.querySelector(`.nav-section[data-id="${c.id}"]`);
            if (sec) {
                sec.classList.add('open');  // 强制展开
                // 延迟滚动，等侧边栏动画完成
                setTimeout(() => {
                    sec.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }, 300);
            }
        };
        grid.appendChild(a);
    });
}
function toggleSidebar() { state.sb = !state.sb; applySidebar(); }
function applySidebar() {
    $('#lsidebar').classList.toggle('open', state.sb);
    $('#sidebar-backdrop').classList.toggle('visible', state.sb);
    if (state.mob) document.body.style.overflow = state.sb ? 'hidden' : '';
}
function closeSidebar() { state.sb = false; applySidebar(); }
function openSidebar() { state.sb = true; applySidebar(); }
function handleResize() { const w = state.mob; state.mob = innerWidth < 768; state.sb = false; applySidebar(); $('#mobile-menu')?.classList.remove('visible'); if (!state.mob) $('#sidebar-toggle').style.display = 'flex'; }

// 文档加载
async function loadDoc(p) {
    $('#welcome').style.display = 'none';
    let lt = setTimeout(() => { $('#doc-view').style.display = 'none'; $('#loading').style.display = 'block'; }, 200);
    try {
        const r = await fetch(p); if (!r.ok) throw new Error(r.status);
        const h = await r.text(); clearTimeout(lt); renderDoc(h, p);
    } catch (e) { clearTimeout(lt); showError(p, e.message); }
}
function renderDoc(h, path) {
    const d = new DOMParser().parseFromString(h, 'text/html'), b = path.substring(0, path.lastIndexOf('/') + 1);
    d.querySelectorAll('a[href]').forEach(a => { let x = a.getAttribute('href'); if (!x || x.startsWith('#') || x.match(/^https?:/)) return; const [f, fg] = x.split('#'); a.href = '?doc=' + (f.startsWith('/') ? f.slice(1) : b + f) + (fg ? '#' + fg : ''); if (x.match(/^https?:/)) { a.target = '_blank'; a.rel = 'noopener'; } });
    d.querySelectorAll('[src]').forEach(e => { const s = e.getAttribute('src'); if (s && !s.match(/^(https?:|\/|data:)/)) e.src = b + s; });
    const c = $('#content'); c.innerHTML = d.body.innerHTML;
    c.querySelectorAll('a[name]').forEach(a => { const p = a.parentElement; if (p && !p.id) p.id = a.getAttribute('name'); });
    c.querySelectorAll('h2,h3').forEach((h, i) => { if (!h.id) h.id = 'h' + i; h.querySelector('.anchor') || h.insertAdjacentHTML('beforeend', `<a class="anchor" href="#${h.id}">#</a>`); });
    $('#loading').style.display = 'none'; $('#doc-view').style.display = 'block'; state.doc = path;
    const pts = path.split('/'), col = LIBRARY_CONFIG.find(c => path.startsWith(c.id + '/'));
    $('#doc-collection').textContent = col ? col.label : pts[0]; $('#doc-volume').textContent = pts[1] || ''; $('#doc-filename').textContent = pts[pts.length - 1];
    const t = d.querySelector('title')?.textContent?.trim(); $('#doc-title-display').textContent = t || ''; document.title = t ? t + ' — MLCLASSIC' : '文库阅读器 — MLCLASSIC';
    buildTOC(c); fixOverflow(c);
    if (location.hash) {
        const id = location.hash.slice(1);
        const e = document.getElementById(id) || document.querySelector(`[name="${id}"]`);
        e && scrollToEl(e);
    }
    else if (state.rs) { const s = localStorage.getItem('scroll_' + path); s && window.scrollTo(0, parseInt(s)); }
    else window.scrollTo(0, 0);
    updateNav(path); updatePrevNext(path);
}
function showError(p, m) { $('#loading').style.display = 'none'; $('#doc-view').style.display = 'block'; $('#content').innerHTML = `<p style="color:var(--text-2);padding:40px 0;">无法加载 <code>${p}</code><br><small>${m}</small></p>`; }

// 目录 & 排版
function buildTOC(c) {
    const l = $('#toc-list'), r = $('#rsidebar'); l.innerHTML = ''; const hs = c.querySelectorAll('h2,h3');
    if (!hs.length) { r.style.display = 'none'; return; }
    r.style.display = ''; hs.forEach(h => { const a = document.createElement('a'); a.className = 'toc-item' + (h.tagName === 'H3' ? ' toc-h3' : ''); a.href = '#' + h.id; a.textContent = h.textContent.replace(/#/, '').trim(); a.onclick = e => { e.preventDefault(); scrollToEl(h); history.replaceState(null, '', location.pathname + location.search + '#' + h.id); }; l.appendChild(a); });
    state.toc && state.toc.disconnect(); state.toc = new IntersectionObserver(e => e.forEach(n => { if (n.isIntersecting) { $$('.toc-item').forEach(x => x.classList.remove('active')); const a = l.querySelector(`a[href="#${n.target.id}"]`); a && a.classList.add('active'); } }), { rootMargin: '-15% 0px -75% 0px' }); hs.forEach(h => state.toc.observe(h));
}
function fixOverflow(c) {
    requestAnimationFrame(() => { c.querySelectorAll('table').forEach(t => { if (t.parentElement?.className === 'table-wrapper') return; if (t.offsetWidth > c.offsetWidth) { const w = document.createElement('div'); w.className = 'table-wrapper'; t.parentNode.insertBefore(w, t); w.appendChild(t); } }); });
    c.querySelectorAll('img').forEach(i => { const k = () => { if (i.naturalWidth > i.parentElement.offsetWidth) { i.style.maxWidth = '100%'; i.style.height = 'auto'; } }; i.complete ? k() : i.onload = k; });
}
function scrollToEl(e) { const t = e.getBoundingClientRect().top + scrollY - 80; window.scrollTo({ top: Math.max(0, t), behavior: 'smooth' }); }
function updateNav(p) { $$('.nav-item').forEach(a => a.classList.toggle('active', a.dataset.path === p)); }

// 前后导航
const mf = {};
async function getM(d) { if (mf[d]) return mf[d]; const n = d.replace(/\/$/, '').split('/').pop(); for (const x of ['index.json', `index${n}.json`]) { try { const r = await fetch(d + x); if (r.ok) { const j = await r.json(); mf[d] = j; return j; } } catch (e) { } } return null; }
function updatePrevNext(p) {
    const pr = $('#prev-btn'), n = $('#next-btn'); pr.style.display = n.style.display = 'none';
    const s = p.lastIndexOf('/'), d = p.slice(0, s + 1), f = p.slice(s + 1);
    getM(d).then(m => { if (!m) return fb(d, f, pr, n); const i = m.findIndex(x => x.file === f); if (i < 0) return; i > 0 && setupBtn(pr, d + m[i - 1].file, m[i - 1].title, '←'); i < m.length - 1 && setupBtn(n, d + m[i + 1].file, m[i + 1].title, '→'); });
}
function fb(d, f, p, n) { const m = f.match(/^(.*?)(\d+)(\.[^.]+)$/); if (!m) return; const [, pr, num, ex] = m, pad = num.length, make = x => d + pr + String(x).padStart(pad, '0') + ex; fetch(make(+num - 1), { method: 'HEAD' }).then(r => r.ok && setupBtn(p, make(+num - 1), null, '←')).catch(() => { }); fetch(make(+num + 1), { method: 'HEAD' }).then(r => r.ok && setupBtn(n, make(+num + 1), null, '→')).catch(() => { }); }
function setupBtn(b, p, t, a) { const n = b.querySelector('.doc-name'), d = b.querySelector('.dir'); d.textContent = a; n.textContent = t ? (t.length > 22 ? t.slice(0, 21) + '…' : t) : p.split('/').pop().replace(/\.[^.]+/, ''); n.title = t || ''; if (!t) fetch(p).then(r => r.text()).then(h => { const x = new DOMParser().parseFromString(h, 'text/html').querySelector('title')?.textContent?.trim(); if (x) { n.textContent = x.length > 22 ? x.slice(0, 21) + '…' : x; n.title = x; } }).catch(() => { }); b.style.display = 'flex'; b.onclick = e => { e.preventDefault(); history.pushState({}, '', '?doc=' + p); loadDoc(p); }; }

// 事件绑定
function bindEvents() {
    on($('#sidebar-toggle'), 'click', toggleSidebar); on($('#sidebar-backdrop'), 'click', closeSidebar);

    // 移动端菜单（三点）
    on($('#mobile-menu-toggle'), 'click', () => { $('#mobile-menu').classList.toggle('visible'); $('#mobile-remember-indicator').textContent = state.rs ? '●' : '○'; $('#mobile-remember-indicator').style.color = state.rs ? 'var(--accent)' : 'var(--text-3)'; $('#mobile-theme-indicator').textContent = document.documentElement.dataset.theme === 'dark' ? '●' : '○'; $('#mobile-font-slider').value = state.fs; });

    // 字体调整
    const adj = d => applyFont(state.fs + d);
    [$('#font-dec-btn'), $('#mobile-font-dec')].forEach(b => b && on(b, 'click', () => adj(-.05)));
    [$('#font-inc-btn'), $('#mobile-font-inc')].forEach(b => b && on(b, 'click', () => adj(.05)));
    [$('#font-slider'), $('#mobile-font-slider')].forEach(b => b && on(b, 'input', e => applyFont(parseFloat(e.target.value), 0)));

    // 主题
    const tt = () => applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
    on($('#theme-btn'), 'click', tt); on($('#mobile-theme'), 'click', tt);

    // 记忆滚动
    const tr = () => { state.rs = !state.rs; localStorage.rememberScroll = state.rs; $('#remember-btn')?.classList.toggle('active', state.rs); !state.rs && localStorage.removeItem('scroll_' + state.doc); };
    on($('#remember-btn'), 'click', tr); on($('#mobile-remember'), 'click', tr);

    // 搜索
    const si = $('#search-input'), so = $('#search-overlay');
    if (si) { on(si, 'input', () => { const q = si.value.trim(); if (!q) return so.classList.remove('visible'); const t = $('#content').textContent || '', re = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi'), m = []; let r; while ((r = re.exec(t)) !== null && m.length < 8) m.push(t.slice(Math.max(0, r.index - 40), r.index + q.length + 40)); so.innerHTML = m.length ? m.map(s => `<div class="search-result"><div class="sr-excerpt">…${s.replace(/</g, '&lt;')}…</div></div>`).join('') : '<div class="search-no-results">无结果</div>'; so.classList.add('visible'); }); on(si, 'keydown', e => e.key === 'Escape' && (so.classList.remove('visible'), si.value = '', si.blur())); }

    // 窗口事件
    on(window, 'resize', () => { clearTimeout(window.rt); window.rt = setTimeout(handleResize, 100); });
    on(window, 'popstate', () => {
        const d = new URLSearchParams(location.search).get('doc');
        if (d === state.doc && location.hash) {
            const id = location.hash.slice(1);
            const el = document.getElementById(id) || document.querySelector(`[name="${id}"]`);
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
    on(window, 'scroll', () => { const h = document.documentElement.scrollHeight - innerHeight; rs($('#progress-bar'), { width: (h > 0 ? scrollY / h * 100 : 0) + '%' }); clearTimeout(window.st); window.st = setTimeout(() => state.rs && state.doc && localStorage.setItem('scroll_' + state.doc, scrollY), 300); }, { passive: true });

    // 点击事件
    on(document, 'click', e => {
        const a = e.target.closest('a'); if (!a) return;
        if (a.hash && a.closest('#content') && !a.search?.includes('doc=')) {
            e.preventDefault();
            const id = a.hash.slice(1);
            const t = document.getElementById(id) || document.querySelector(`[name="${id}"]`);
            t && scrollToEl(t);
            return;
        }
        const h = a.getAttribute('href'); if (h && h.match(/^#(fn|FN|M|E|F|a|b|z|c|n|p)/)) { const tip = $('#fn-tooltip'), target = $(h.slice(1)) || document.querySelector(`a[name="${h.slice(1)}"]`); if (target) { tip.innerHTML = target.innerHTML; tip.classList.add('visible'); rs(tip, { left: Math.min(e.clientX + 12, innerWidth - 360) + 'px', top: Math.min(e.clientY + 12, innerHeight - 100) + 'px' }); on(a, 'mouseleave', () => tip.classList.remove('visible'), { once: true }); } }
        if (!$('#mobile-menu').contains(e.target) && !$('#mobile-menu-toggle').contains(e.target)) $('#mobile-menu').classList.remove('visible');
    });

    // 键盘
    on(document, 'keydown', e => {
        if (e.key === 'Escape') { closeSidebar(); $('#mobile-menu')?.classList.remove('visible'); $('#search-overlay')?.classList.remove('visible'); $('#search-input')?.blur(); }
        if (e.key === 's' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); toggleSidebar(); }
        if (e.key === '/' && e.target.tagName !== 'INPUT') { e.preventDefault(); $('#search-input')?.focus(); }
    });
}