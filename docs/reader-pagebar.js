(function () {
  'use strict';

  const C = window.ReaderCore || {};
  const { $, $$, onScrollFrame, hasSelection, scrollToEl } = C;
  const navMenu = () => window.__NAV__?.menu || window.__NAV__ || null;

  class PageBarManager {
    constructor() {
      this.pageNumbers = [];
      this.currentPage = null;
      this.hasPageAnchors = false;
      this.content = null;
      this.marker = null;
      this.lastMarkerId = null;
      this.lastMarkerAt = 0;
      this.ready = false;
      this.scrollOff = null;
      this.resizeFrame = 0;
      this.scrollFrame = 0;
      this.markerTimer = null;
      this.noticeTimer = null;
      this.quietUntil = 0;
      this.bag = new C.EventBag();
      this.lang = this.detectContentLang();
    }

    init() {}

    scanContent(container, lang) {
      this.reset(false);
      this.content = container || null;
      this.lang = this.detectContentLang(container, lang);
      if (!container) return;
      this.pageNumbers = $$('a[id^="S"]', container)
        .filter(anchor => !this.isFootnoteAsideElement(anchor))
        .map(anchor => {
          const parsed = this.parsePageAnchor(anchor.id);
          return parsed ? { id: anchor.id, el: anchor, ...parsed, top: 0 } : null;
        })
        .filter(Boolean);
      this.hasPageAnchors = this.pageNumbers.length > 0;
      if (!this.hasPageAnchors) {
        this.updateBadge(null);
        return;
      }
      this.setup();
    }

    detectContentLang(container = this.content, lang = null) {
      return [
        lang,
        container?.getAttribute?.('lang'),
        document.body?.getAttribute('lang'),
        document.documentElement?.getAttribute('lang')
      ].find(v => String(v || '').trim())?.trim().toLowerCase() || '';
    }

    reset(clearContent = true) {
      this.bag.clear();
      if (this.scrollOff) this.scrollOff();
      this.scrollOff = null;
      if (this.resizeFrame) cancelAnimationFrame(this.resizeFrame);
      if (this.scrollFrame) cancelAnimationFrame(this.scrollFrame);
      clearTimeout(this.markerTimer);
      this.resizeFrame = 0;
      this.scrollFrame = 0;
      this.markerTimer = null;
      this.ready = false;
      this.pageNumbers = [];
      this.currentPage = null;
      this.hasPageAnchors = false;
      this.lastMarkerId = null;
      this.lastMarkerAt = 0;
      this.clearMarker();
      this.updateBadge(null);
      if (clearContent) this.content = null;
    }

    setup() {
      const quiet = () => {
        this.quietUntil = Date.now() + 900;
        clearTimeout(this.markerTimer);
      };
      ['touchstart', 'touchmove', 'touchend', 'touchcancel'].forEach(type => {
        this.bag.on(this.content, type, quiet, { passive: true });
      });
      this.bag.on(this.content, 'click', e => this.handleContentClick(e));
      this.bag.on(document, 'selectionchange', () => this.handleSelectionChange());
      this.bag.on(window, 'resize', () => this.queueMeasure(), { passive: true });
      this.scrollOff = onScrollFrame(() => this.queueScrollUpdate());
      setTimeout(() => {
        this.measure();
        this.ready = true;
        this.queueScrollUpdate();
      }, 350);
    }

    parsePageAnchor(id) {
      let match = String(id).match(/^S(\d+)$/);
      if (match) return { page: match[1], label: match[1], citePage: match[1] };
      match = String(id).match(/^S(.+?)-p?(\d+)$/i);
      if (!match) return null;
      const scope = match[1].replace(/^[-_]+|[-_]+$/g, '');
      const page = match[2];
      return { scope, page, label: `${scope}, S. ${page}`, citePage: `${scope}, S. ${page}` };
    }

    queueMeasure() {
      if (this.resizeFrame) return;
      this.resizeFrame = requestAnimationFrame(() => {
        this.resizeFrame = 0;
        this.measure();
        this.queueScrollUpdate();
      });
    }

    measure() {
      this.pageNumbers.forEach(item => {
        item.top = item.el.getBoundingClientRect().top + scrollY;
      });
      this.pageNumbers.sort((a, b) => a.top - b.top);
    }

    queueScrollUpdate() {
      if (!this.ready || this.scrollFrame) return;
      this.scrollFrame = requestAnimationFrame(() => {
        this.scrollFrame = 0;
        this.updateFromScroll();
      });
    }

    updateFromScroll() {
      if (!this.ready || hasSelection()) return;
      this.reveal({ rect: this.pointRect(Math.max(80, innerHeight * 0.42)), source: 'scroll' });
    }

    handleContentClick(e) {
      const target = e.target?.nodeType === 1 ? e.target : e.target?.parentElement;
      if (!target || this.shouldIgnoreTarget(target) || hasSelection()) return;
      this.reveal({ rect: this.pointRect(e.clientY), source: 'content-click', force: true, toggleAny: true, sticky: true });
    }

    handleSelectionChange() {
      clearTimeout(this.markerTimer);
      if (Date.now() < this.quietUntil) return;
      this.markerTimer = setTimeout(() => this.showMarkerNearSelection(), 120);
    }

    pointRect(y) {
      return { top: y, bottom: y };
    }

    showMarkerNearSelection() {
      if (Date.now() < this.quietUntil) return false;
      const selection = document.getSelection();
      if (!selection || selection.isCollapsed || !selection.rangeCount) return false;
      const range = selection.getRangeAt(0);
      const common = range.commonAncestorContainer?.nodeType === 1
        ? range.commonAncestorContainer
        : range.commonAncestorContainer?.parentElement;
      if (!common || this.shouldIgnoreTarget(common)) return false;
      const rects = Array.from(range.getClientRects()).filter(rect => rect.width || rect.height);
      if (!rects.length) return false;
      return this.reveal({
        rect: {
          top: Math.min(...rects.map(rect => rect.top)),
          bottom: Math.max(...rects.map(rect => rect.bottom))
        },
        source: 'content-selection',
        force: true
      });
    }

    reveal(options = {}) {
      const info = options.pageInfo ? this.resolvePageInfo(options.pageInfo) : this.findPageForRect(options.rect);
      if (!info) return false;
      const now = Date.now();
      if (!options.force && info.id === this.lastMarkerId && now - this.lastMarkerAt < 1800) return false;
      if (!options.force && info.id !== this.lastMarkerId && now - this.lastMarkerAt < 120) return false;
      if (options.toggleAny && this.marker) {
        this.clearMarker();
        return true;
      }
      if (options.toggle && this.marker?.dataset.pageAnchorId === info.id) {
        this.clearMarker();
        return true;
      }
      this.currentPage = info;
      this.lastMarkerId = info.id;
      this.lastMarkerAt = now;
      this.updateBadge(info);
      return this.showMarker(info, options);
    }

    findPageForRect(rect) {
      if (!this.pageNumbers.length || !rect) return null;
      if (this.pageNumbers.some(item => !Number.isFinite(item.top))) this.measure();
      const y = scrollY + (rect.top + rect.bottom) / 2;
      let lo = 0;
      let hi = this.pageNumbers.length - 1;
      let best = 0;
      while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        if (this.pageNumbers[mid].top <= y) {
          best = mid;
          lo = mid + 1;
        } else {
          hi = mid - 1;
        }
      }
      return this.pageNumbers[best] || this.pageNumbers[0];
    }

    resolvePageInfo(target) {
      if (!target) return this.currentPage;
      if (typeof target === 'object') return target;
      const id = String(target).replace(/^#/, '');
      const known = this.pageNumbers.find(item => item.id === id);
      if (known) return known;
      const anchor = document.getElementById(id);
      const parsed = this.parsePageAnchor(id);
      return anchor && parsed ? { id, el: anchor, ...parsed } : null;
    }

    highlightPageAnchor(target, options = {}) {
      const info = this.resolvePageInfo(target);
      if (!info) return false;
      this.currentPage = info;
      this.updateBadge(info);
      const anchor = info.el || document.getElementById(info.id);
      if (anchor && options.scroll !== false) scrollToEl(anchor);
      return this.showMarker(info, { ...options, force: true });
    }

    showMarker(info, options = {}) {
      const anchor = info.el || document.getElementById(info.id);
      if (!anchor || this.isFootnoteAsideElement(anchor)) return false;
      this.clearMarker();
      this.ensureStyles();

      const marker = document.createElement('div');
      marker.className = 'reader-page-marker reader-page-marker--pointer-left';
      marker.setAttribute('role', 'button');
      marker.setAttribute('aria-live', 'polite');
      marker.tabIndex = 0;
      marker.textContent = this.formatCitationPage(info);
      marker.setAttribute('aria-label', marker.textContent + ' Quellenangabe kopieren');
      marker.dataset.page = info.citePage || info.label;
      marker.dataset.pageAnchorId = info.id || '';
      marker.addEventListener('click', e => {
        e.preventDefault();
        e.stopPropagation();
        this.copyCitation(marker, marker.dataset.page);
      });
      marker.addEventListener('keydown', e => {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        e.preventDefault();
        this.copyCitation(marker, marker.dataset.page);
      });

      marker.style.visibility = 'hidden';
      document.body.appendChild(marker);
      this.marker = marker;
      this.placeMarker(marker, anchor, options);
      if (!options.sticky) {
        this.markerTimer = setTimeout(() => {
          marker.classList.add('reader-page-marker--leaving');
          this.markerTimer = setTimeout(() => this.clearMarker(), 320);
        }, 1900);
      }
      return true;
    }

    placeMarker(marker, anchor, options) {
      const anchorRect = anchor.getClientRects()[0] || anchor.getBoundingClientRect();
      const contentRect = this.content?.getBoundingClientRect() || $('#content')?.getBoundingClientRect();
      const anchorLeft = Number.isFinite(anchorRect.left) && anchorRect.left > 0
        ? anchorRect.left + scrollX
        : (contentRect?.left ?? 24) + scrollX;
      const viewportRight = Math.max(anchorLeft - scrollX, Number.isFinite(anchorRect.right) ? anchorRect.right : anchorLeft - scrollX);
      const margin = 8;
      const gap = 9;
      const width = Math.min(marker.offsetWidth || 0, 240);
      const rightBoundary = Math.min(innerWidth - margin, (contentRect?.right ?? innerWidth) - margin);
      const rightLeft = viewportRight + gap;
      const fallbackLeft = contentRect ? Math.min(Math.max(contentRect.left, margin), innerWidth - width - margin) : margin;
      const left = (rightLeft + width <= rightBoundary ? rightLeft : fallbackLeft) + scrollX;
      marker.style.left = `${Math.max(8, left)}px`;
      marker.style.top = `${Math.max(0, anchorRect.top + scrollY)}px`;
      marker.style.maxWidth = `min(240px, calc(100vw - ${Math.max(24, left - scrollX + 16)}px))`;
      marker.style.zIndex = innerWidth < 997 && document.querySelector('.doc-sidebar--open') || options.underMenu ? '90' : '250';
      marker.style.visibility = '';
    }

    clearMarker() {
      clearTimeout(this.markerTimer);
      this.markerTimer = null;
      if (this.marker) {
        this.marker.remove();
        this.marker = null;
      }
    }

    updateBadge(pageInfo) {
      const link = $('#page-breadcrumb-link');
      if (!link) return;
      if (pageInfo == null) {
        link.textContent = '';
        link.style.display = 'none';
        delete link.dataset.page;
        delete link.dataset.pageAnchorId;
        return;
      }
      const info = typeof pageInfo === 'object' ? pageInfo : { label: pageInfo, citePage: pageInfo };
      link.textContent = this.formatCitationPage(info);
      link.style.display = '';
      link.dataset.page = info.citePage || info.label;
      if (info.id) link.dataset.pageAnchorId = info.id;
      this.bindCopy(link);
    }

    bindCopy(el, options = {}) {
      if (!el || el._readerCopyBound) return;
      el._readerCopyBound = true;
      el.title = 'Quellenangabe';
      el.addEventListener('click', e => {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        if (options.highlight !== false) this.highlightPageAnchor(e.currentTarget.dataset.pageAnchorId || this.currentPage, { scroll: false });
        this.copyCitation(e.currentTarget, e.currentTarget.dataset.page);
      });
    }

    copyCitation(el, page) {
      if (!page) return;
      const citation = this.generateCitation(page);
      el.dataset.citation = citation;
      if (navigator.clipboard?.writeText) {
        navigator.clipboard.writeText(citation).then(() => this.showCopyNotice(el)).catch(() => this.fallbackCopy(el, citation));
      } else {
        this.fallbackCopy(el, citation);
      }
    }

    fallbackCopy(el, citation) {
      const ta = document.createElement('textarea');
      ta.value = citation;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      let copied = false;
      try { copied = document.execCommand('copy'); } catch { }
      ta.remove();
      copied ? this.showCopyNotice(el) : this.showCopyError(citation);
    }

    showCopyNotice(el) {
      if (typeof window.showReaderNotice === 'function') {
        window.showReaderNotice('Die Quellenangabe wurde in die Zwischenablage kopiert: ' + (el?.dataset.citation || '.'));
        return;
      }
      this.showFallbackNotice('Copied citation.');
    }

    showCopyError(citation) {
      if (typeof window.showReaderNotice === 'function') {
        window.showReaderNotice('Copy failed. Please copy manually: ' + citation, { type: 'error', duration: 3600 });
        return;
      }
      this.showFallbackNotice('Copy failed.');
    }

    showFallbackNotice(text) {
      let notice = $('#citation-popover');
      if (!notice) {
        notice = document.createElement('div');
        notice.id = 'citation-popover';
        notice.className = 'popover';
        notice.innerHTML = '<div class="popover__body" style="margin-bottom:0"></div>';
        document.body.appendChild(notice);
      }
      $('.popover__body', notice).textContent = text;
      notice.style.cssText = 'display:block!important;position:fixed!important;left:12px!important;bottom:12px!important;z-index:500!important;';
      notice.classList.add('popover--visible');
      clearTimeout(this.noticeTimer);
      this.noticeTimer = setTimeout(() => {
        notice.classList.remove('popover--visible');
        notice.style.cssText = '';
      }, 1100);
    }

    currentDocPath() {
      const stateDoc = window.ReaderState?.doc || (typeof state !== 'undefined' ? state.doc : '');
      if (stateDoc) return stateDoc;
      const menu = navMenu();
      if (menu?._volInfo) {
        try { return menu._volInfo().path || location.pathname; } catch { }
      }
      const stripRoot = C.PathResolver?.stripRoot;
      return typeof stripRoot === 'function' ? stripRoot(location.pathname) : location.pathname;
    }
      
    generateCitation(page) {
      const path = this.currentDocPath();
      const vol = this.detectVolume(path);
      const cit = this.findCitation(path, vol);
      const col = vol?.col || null;
      const pageText = this.formatCitationPage(page, cit?.pageParam);
      if (cit && (cit.prefix || cit.title || cit.year || cit.volume || cit.publisher)) {
        return [cit.prefix, cit.title, cit.volume, cit.publisher, cit.year].filter(Boolean).join(', ') + ', ' + pageText;
      }
      const id = col?.id || '';
      if (id === 'mew') return 'MEW, ' + pageText;
      if (id === 'mew-zh') return '《马克思恩格斯全集》, ' + pageText;
      if (id === 'mega') return 'MEGA, ' + pageText;
      if (id === 'mecw') return 'MECW, ' + pageText;
      if (id === 'hegel') return 'G.W.F.Hegel Werke, ' + pageText;
      return (id ? id.toUpperCase() + ', ' : '') + pageText;
    }

    formatCitationPage(pageInfo, pattern) {
      const info = typeof pageInfo === 'object' ? pageInfo : null;
      if (info?.scope) return info.label;
      const value = String(info ? (info.label ?? info.page ?? '') : pageInfo);
      const lang = this.lang || '';
      const pagenumtext = pattern?.replace('${page}', value)
        || (lang.startsWith('de') ? 'S. ' + value
        : lang.startsWith('ru') ? 'стр. ' + value
          : lang.startsWith('zh') ? '第' + value + '页'
            : 'p. ' + value);
      return /(^|,\s)((S|p)\.\s|стр\.\s)|第.+页/i.test(value) ? value : pagenumtext;
    }

    findCitation(path, vol = this.detectVolume(path)) {
      if (!vol) return null;
      return {
        ...(vol.col?.citation || {}),
        ...(vol.group?.citation || {}),
        ...(vol.item?.citation || {}),
        volume: vol.item?.volume || vol.group?.volume || vol.col?.volume || null
      };
    }

    detectVolume(path = this.currentDocPath()) {
      const menu = navMenu();
      if (menu?.currentVol) return menu.currentVol;
      if (menu?.detectVolume) {
        try { return menu.detectVolume(path, false) || null; } catch { }
      }
      if (typeof C.detectVolume === 'function') {
        try { return C.detectVolume(path) || null; } catch { }
      }
      return null;
    }

    shouldIgnoreTarget(target) {
      const content = this.content || $('#content');
      if (!content || !content.contains(target)) return true;
      if (this.isFootnoteAsideElement(target)) return true;
      return !!target.closest('.reader-page-marker, #sidebar-backdrop, .sidebar-overlay, a, button, input, select, textarea, summary, [role="button"], .doc-sidebar, .dropdown, .popover, .navbar');
    }

    isFootnoteAsideElement(el) {
      const aside = el?.closest?.('aside');
      if (!aside) return false;
      const marker = `${aside.className || ''} ${aside.id || ''} ${aside.getAttribute('role') || ''} ${aside.getAttribute('aria-label') || ''}`;
      return /\b(fn|fni|footnote|endnote|note|notes)\b/i.test(marker)
        || aside.matches('[epub\\:type~="footnote"], [epub\\:type~="endnote"], [role="doc-footnote"], [role="doc-endnote"]');
    }

    ensureStyles() {
      if ($('#reader-page-marker-style')) return;
      const style = document.createElement('style');
      style.id = 'reader-page-marker-style';
      style.textContent = `
        .reader-page-marker{position:absolute;padding:7px 11px;border-radius:8px;background:color-mix(in srgb,var(--bg-card,#fff) 88%,var(--accent-bg,#fef3c7));border:1px solid color-mix(in srgb,var(--accent-border,#78350f) 64%,transparent);color:var(--text,#1c1917);box-shadow:var(--shadow-md,0 10px 28px rgba(0,0,0,.18));font:700 13px/1.25 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;white-space:nowrap;transform:translateY(-50%);cursor:pointer;pointer-events:auto;opacity:1;transition:opacity 260ms ease,transform 260ms ease;animation:readerPageMarkerBreathe 1600ms ease-in-out infinite}
        .reader-page-marker::before{content:"";position:absolute;top:50%;width:9px;height:9px;background:inherit;border:inherit;transform:translateY(-50%) rotate(45deg)}
        .reader-page-marker--pointer-left{border-left:4px solid var(--accent,#b45309)}
        .reader-page-marker--pointer-left::before{left:-5px;border-top:0;border-right:0}
        .reader-page-marker--leaving{opacity:0;transform:translateY(-50%) scale(.98)}
        @keyframes readerPageMarkerBreathe{0%,100%{box-shadow:var(--shadow-md,0 10px 28px rgba(0,0,0,.16))}50%{box-shadow:var(--shadow-md,0 10px 28px rgba(0,0,0,.16)),0 0 0 3px color-mix(in srgb,var(--accent,#b45309) 24%,transparent)}}
        @media (prefers-reduced-motion:reduce){.reader-page-marker{animation:none!important}}
      `;
      document.head.appendChild(style);
    }

    destroy() {
      this.reset();
    }
  }

  window.PageBarManager = PageBarManager;
})();
