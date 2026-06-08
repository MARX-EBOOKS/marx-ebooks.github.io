(function () {
  'use strict';

  const C = window.ReaderCore || {};
  const $ = C.$ || (s => document.querySelector(s));
  const $$ = C.$$ || ((s, r = document) => Array.from(r.querySelectorAll(s)));
  const esc = C.esc || (v => String(v ?? '').replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch])));
  const syncFill = C.syncFill || (() => {});
  const onScrollFrame = C.onScrollFrame || (fn => {
    window.addEventListener('scroll', fn, { passive: true });
    return () => window.removeEventListener('scroll', fn);
  });
  const scrollToEl = C.scrollToEl || (el => el?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
  const cssEsc = C.cssEsc || (v => (window.CSS?.escape ? CSS.escape(String(v)) : String(v).replace(/["\\]/g, '\\$&')));
  const PathResolver = C.PathResolver;
  const state = {
    fs: parseFloat(localStorage.fontSize) || 1,
    lh: parseFloat(localStorage.lineHeight) || 2.0,
    rs: localStorage.rememberScroll !== 'false',
    mob: innerWidth < 768,
    saveTimer: null
  };

  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
  const resolveUrl = href => PathResolver.path(location.pathname, href);
  const lowerUrlFallback = value => {
    try {
      const url = new URL(value, location.href);
      if (url.origin !== location.origin) return value;
      const lower = new URL(url.href);
      lower.pathname = lower.pathname.toLowerCase();
      return lower.href;
    } catch {
      return value;
    }
  };
  const samePath = (a, b) => {
    try {
      const left = PathResolver.stripRoot(a).replace(/\/+$/, '');
      const right = PathResolver.stripRoot(b).replace(/\/+$/, '');
      return left === right || left.toLowerCase() === right.toLowerCase();
    } catch {
      return String(a || '') === String(b || '') || String(a || '').toLowerCase() === String(b || '').toLowerCase();
    }
  };
  async function fetchWithLowerFallback(url, options) {
    const lower = lowerUrlFallback(url);
    try {
      const res = await fetch(url, options);
      if (res.ok || lower === url) return { res, url };
      try {
        const fallback = await fetch(lower, options);
        if (fallback.ok) return { res: fallback, url: lower };
      } catch { }
      return { res, url };
    } catch (error) {
      if (lower === url) throw error;
      try {
        return { res: await fetch(lower, options), url: lower };
      } catch {
        throw error;
      }
    }
  }

  function setupResponsiveContent() {
    const content = $('#content');
    if (!content) return;
    $$('table', content).forEach(table => {
      if (table.parentElement?.classList.contains('table-wrapper')) return;
      const wrapper = document.createElement('div');
      wrapper.className = 'table-wrapper';
      table.before(wrapper);
      wrapper.appendChild(table);
    });
    $$('img', content).forEach(img => {
      img.style.maxWidth = '100%';
      img.style.height = 'auto';
      img.style.display = 'block';
    });
  }

  function setupHeadingAnchors() {
    const content = $('#content');
    if (!content) return;
    const skip = new Set(['Karl Marx', 'Friedrich Engels', 'Karl Marx/Friedrich Engels']);
    $$('h1,h2,h3,h4,h5,h6', content).forEach((heading, i) => {
      const text = heading.textContent.trim();
      if (skip.has(text)) return;
      if (!heading.id) heading.id = 'h' + i;
      if (!heading.querySelector('.anchor')) {
        heading.insertAdjacentHTML('beforeend', `<a class="anchor" href="#${esc(heading.id)}" aria-hidden="true" hidden=""></a>`);
      }
    });
  }

  function setupProgress() {
    const bar = $('#progress-bar');
    if (!bar) return;
    onScrollFrame(() => {
      const max = document.documentElement.scrollHeight - innerHeight;
      bar.style.width = (max > 0 ? (scrollY / max) * 100 : 0) + '%';
    });
  }

  function applyFont(value, save = true) {
    state.fs = clamp(value, 0.75, 1.5);
    document.documentElement.style.setProperty('--fs-user', Math.round(16 * state.fs) + 'px');
    if (save) localStorage.setItem('fontSize', state.fs);
    ['#font-slider', '#mobile-font-slider'].forEach(selector => {
      const el = $(selector);
      if (el) { el.value = state.fs; syncFill(el); }
    });
  }

  function applyLineHeight(value, save = true) {
    state.lh = clamp(Math.round(value * 10) / 10, 1.4, 2.6);
    document.documentElement.style.setProperty('--lh-user', state.lh);
    if (save) localStorage.setItem('lineHeight', state.lh);
    ['#lh-slider', '#mobile-lh-slider'].forEach(selector => {
      const el = $(selector);
      if (el) { el.value = state.lh; syncFill(el); }
    });
  }

  function updateThemeUI() {
    const dark = document.documentElement.dataset.theme === 'dark';
    $$('.icon-sun').forEach(el => el.style.display = dark ? 'none' : '');
    $$('.icon-moon').forEach(el => el.style.display = dark ? '' : 'none');
    const indicator = $('#mobile-theme-indicator');
    if (indicator) indicator.textContent = dark ? '\u25cf' : '\u25cb';
  }

  function toggleTheme() {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    localStorage.theme = next;
    updateThemeUI();
  }

  function updateRememberUI() {
    $('#remember-btn')?.classList.toggle('clean-btn--active', state.rs);
    const indicator = $('#mobile-remember-indicator');
    if (indicator) indicator.textContent = state.rs ? '\u25cf' : '\u25cb';
  }

  function toggleRemember() {
    state.rs = !state.rs;
    localStorage.rememberScroll = state.rs;
    updateRememberUI();
  }

  function setupControls() {
    applyFont(state.fs, false);
    applyLineHeight(state.lh, false);
    updateThemeUI();
    updateRememberUI();

    [['font-dec-btn', 'mobile-font-dec', -0.05], ['font-inc-btn', 'mobile-font-inc', 0.05]].forEach(([a, b, delta]) => {
      $('#' + a)?.addEventListener('click', () => applyFont(state.fs + delta));
      $('#' + b)?.addEventListener('click', () => applyFont(state.fs + delta));
    });
    [['lh-dec-btn', 'mobile-lh-dec', -0.1], ['lh-inc-btn', 'mobile-lh-inc', 0.1]].forEach(([a, b, delta]) => {
      $('#' + a)?.addEventListener('click', () => applyLineHeight(state.lh + delta));
      $('#' + b)?.addEventListener('click', () => applyLineHeight(state.lh + delta));
    });
    ['#font-slider', '#mobile-font-slider'].forEach(selector => $(selector)?.addEventListener('input', e => applyFont(parseFloat(e.target.value))));
    ['#lh-slider', '#mobile-lh-slider'].forEach(selector => $(selector)?.addEventListener('input', e => applyLineHeight(parseFloat(e.target.value))));
    ['theme-btn', 'sidebar-theme-btn', 'mobile-theme'].forEach(id => $('#' + id)?.addEventListener('click', toggleTheme));
    $('#remember-btn')?.addEventListener('click', toggleRemember);
    $('#mobile-remember')?.addEventListener('click', toggleRemember);

    const menu = $('#mobile-menu');
    if (menu) menu.style.position = 'fixed';
    $('#mobile-menu-toggle')?.addEventListener('click', e => {
      e.preventDefault();
      e.stopPropagation();
      menu?.classList.toggle('dropdown--open');
      updateRememberUI();
      updateThemeUI();
    });
  }

  function setupScrollMemory() {
    const key = 'scroll_' + location.pathname;
    if (state.rs) {
      const saved = parseInt(localStorage.getItem(key), 10);
      if (Number.isFinite(saved)) requestAnimationFrame(() => window.scrollTo(0, saved));
    }
    onScrollFrame(() => {
      clearTimeout(state.saveTimer);
      state.saveTimer = setTimeout(() => {
        if (state.rs) localStorage.setItem(key, String(scrollY));
      }, 300);
    });
  }

  class FootnotePopup {
    constructor() {
      this.tip = $('#fn-tooltip');
      this.active = false;
      this.trigger = null;
      this.cache = new Map();
      this.sameCache = new Map();
      this.bag = new (C.EventBag || class {
        constructor() { this.off = []; }
        on(t, e, f, o) { t?.addEventListener(e, f, o || false); this.off.push(() => t?.removeEventListener(e, f, o || false)); }
        clear() { while (this.off.length) this.off.pop()(); }
      })();
      this.offScroll = null;
    }

    async show(a) {
      if (!this.tip) return;
      this.forceClose();
      const href = a.getAttribute('href') || '';
      const parsed = this.parseHref(href);
      if (!parsed) return;
      this.trigger = a;
      const result = await this.resolveTarget(parsed);
      this.render(result?.block || this.linkFallback(a), result?.target || null, href, parsed.cross);
      this.position();
      this.tip.classList.add('popover--visible');
      this.active = true;
      this.bag.on(document, 'click', e => this.dismiss(e), true);
      this.bag.on(document, 'keydown', e => this.dismiss(e));
      this.offScroll = onScrollFrame(() => this.active && this.position());
    }

    parseHref(href) {
      if (href.startsWith('#')) return { targetId: href.slice(1), pageUrl: null, cross: false };
      const i = href.indexOf('#');
      if (i < 0) return null;
      return { targetId: href.slice(i + 1), pageUrl: resolveUrl(href.slice(0, i)), cross: true };
    }

    async resolveTarget({ targetId, pageUrl, cross }) {
      if (cross && pageUrl) {
        let parsed = this.cache.get(pageUrl);
        if (!parsed) {
          try {
            const loaded = await fetchWithLowerFallback(pageUrl);
            const res = loaded.res;
            if (!res.ok) return null;
            parsed = new DOMParser().parseFromString(await res.text(), 'text/html');
            this.cache.set(pageUrl, parsed);
            if (loaded.url !== pageUrl) this.cache.set(loaded.url, parsed);
          } catch {
            return null;
          }
        }
        const target = parsed.getElementById(targetId) || parsed.querySelector(`a[name="${cssEsc(targetId)}"]`);
        return target ? { target, block: this.toBlock(target) } : null;
      }
      const cached = this.sameCache.get(targetId);
      if (cached) return cached;
      const target = document.getElementById(targetId) || document.querySelector(`a[name="${cssEsc(targetId)}"]`);
      if (!target) return null;
      const result = { target, block: this.toBlock(target) };
      this.sameCache.set(targetId, result);
      return result;
    }

    toBlock(target) {
      const notes = '.fni, .footnote, .endnote, .fn, .note';
      const blocks = 'li,dd,dt,p,blockquote,pre,figure,figcaption,table,thead,tbody,tfoot,tr,td,th,section,article,aside,div,h1,h2,h3,h4,h5,h6';
      const doc = target.ownerDocument || document;
      const isContainer = el => {
        if (!el || el === doc.body || el === doc.documentElement) return true;
        return el.id === 'content' || el.id === 'main' || el.classList?.contains('prose') ||
          el.classList?.contains('doc-content') || el.classList?.contains('doc-main') ||
          el.classList?.contains('doc-main-inner');
      };
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
      const boundary = n => n.nodeType === 1 && (n.tagName === 'BR' ||
        n.matches?.('li,dd,dt,p,blockquote,pre,figure,figcaption,table,thead,tbody,tfoot,tr,td,th,section,article,aside,div,h1,h2,h3,h4,h5,h6'));
      const before = [];
      for (let n = target.previousSibling; n; n = n.previousSibling) {
        if (boundary(n)) break;
        before.unshift(n);
      }
      const nodes = before.concat(target);
      for (let n = target.nextSibling; n; n = n.nextSibling) {
        if (boundary(n)) break;
        nodes.push(n);
      }
      nodes.forEach(n => frag.appendChild(n.cloneNode(true)));
      return (frag.textContent || '').trim() ? frag : null;
    }

    linkFallback(a) {
      const frag = document.createDocumentFragment();
      frag.appendChild(a.cloneNode(true));
      return frag;
    }

    render(block, target, href, cross) {
      const viewer = $('.popover__body', this.tip);
      const jump = $('.popover__jump', this.tip);
      if (!viewer) return;
      const clone = block.cloneNode(true);
      $$('[id]', clone).forEach(el => el.removeAttribute('id'));
      viewer.replaceChildren(clone);
      if (jump) {
        jump.href = cross ? resolveUrl(href) : href;
        jump.textContent = cross ? '\u2197 Go to note (other page)' : '\u2193 Jump to footnote';
        jump.classList.toggle('popover__jump--cross', cross);
        jump.style.display = '';
        jump.onclick = () => this.forceClose();
      }
    }

    position() {
      if (!this.trigger) return;
      const rect = this.trigger.getBoundingClientRect();
      const tipW = 340;
      const maxH = Math.min(320, innerHeight * 0.45);
      let left = rect.right + 8;
      if (left + tipW > innerWidth - 12) left = Math.max(12, rect.left - tipW - 8);
      const top = Math.min(Math.max(rect.top + scrollY - 10, scrollY + 4), Math.max(scrollY + 4, scrollY + innerHeight - maxH - 4));
      this.tip.style.left = left + 'px';
      this.tip.style.top = top + 'px';
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

  function isFootnoteLink(a) {
    const href = a.getAttribute('href') || '';
    if (!href.includes('#') || /^(https?:|\/\/)/i.test(href)) return false;
    return !!(a.closest('sup') || a.querySelector('sup'));
  }

  function setupFootnotes() {
    const popup = new FootnotePopup();
    document.addEventListener('click', e => {
      const a = e.target.closest('a');
      if (!a || !isFootnoteLink(a)) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      popup.show(a);
    });
    window.__FN_POPUP__ = popup;
  }

  function setupGlobalEvents() {
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') {
        window.__NAV__?.menu?.close();
        $('#mobile-menu')?.classList.remove('dropdown--open');
        window.__FN_POPUP__?.forceClose();
      }
      if ((e.key === 's' || e.key === 'S') && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        const menu = window.__NAV__?.menu;
        const isOpen = menu?.sidebar?.classList.contains('doc-sidebar--open');
        isOpen ? menu.close() : menu.open();
      }
    });
    window.addEventListener('resize', () => {
      const was = state.mob;
      state.mob = innerWidth < 768;
      if (was !== state.mob) {
        window.__NAV__?.menu?.close();
        $('#mobile-menu')?.classList.remove('dropdown--open');
      }
    }, { passive: true });
    document.addEventListener('click', e => {
      const menu = $('#mobile-menu');
      const toggle = $('#mobile-menu-toggle');
      if (menu?.classList.contains('dropdown--open') && !menu.contains(e.target) && !toggle?.contains(e.target)) {
        menu.classList.remove('dropdown--open');
      }
      const a = e.target.closest('a[href]');
      if (!a || !a.closest('#content')) return;
      if (isFootnoteLink(a)) return;
      const href = a.getAttribute('href') || '';
      if (href.startsWith('#') && href.length > 1) {
        e.preventDefault();
        const target = document.getElementById(href.slice(1)) || document.querySelector(`[name="${cssEsc(href.slice(1))}"]`);
        if (target) scrollToEl(target);
        return;
      }
      if (href.includes('#') && !/^(https?:|\/\/)/i.test(href)) {
        try {
          const resolved = PathResolver.resolve(location.pathname, href);
          if (resolved?.type === 'doc' && samePath(resolved.href, location.href) && resolved.hash) {
            e.preventDefault();
            const target = document.getElementById(resolved.hash);
            if (target) scrollToEl(target);
          }
        } catch { }
      }
    });
  }

  function setupTocRowWrap() {
    $$('.doc-toc > ul > .toc-item, .doc-toc > ol > .toc-item').forEach(li => {
      if (li.querySelector(':scope > .toc-item-row')) return;
      const link = li.querySelector(':scope > a.toc-link');
      const caret = li.querySelector(':scope > button.toc-caret');
      if (!link) return;
      const row = document.createElement('div');
      row.className = 'toc-item-row';
      row.appendChild(link);
      if (caret) row.appendChild(caret);
      li.insertBefore(row, li.firstChild);
    });
  }

  function init() {
    setupResponsiveContent();
    setupHeadingAnchors();
    setupProgress();
    setupControls();
    setupScrollMemory();
    setupFootnotes();
    setupGlobalEvents();
    setupTocRowWrap();
  }

  document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', init) : init();
})();
