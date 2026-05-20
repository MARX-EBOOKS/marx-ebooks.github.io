// ===== PageBarManager: 页码锚点追踪与面包屑动态显示 =====
class PageBarManager {
  constructor() {
    this.pageNumbers = [];
    this.currentPage = null;
    this.hasPageAnchors = false;
    this._io = null;
    this._citationPopoverTimer = null;
    this._dismissPopoverHandler = null;
    this._pageMarkerEl = null;
    this._pageMarkerTimer = null;
    this._dismissPageMarkerHandler = null;
    this._lastAutoMarkerId = null;
    this._lastAutoMarkerAt = 0;
    this._scrollMarkerReady = false;
    this._scrollMarkerHandler = null;
    this._scrollMarkerRaf = null;
  }

  init() {
    // Page marker is driven by scroll position only.
  }

  /* ---- 扫描正文中的页码锚点 <a id="S123"></a> ---- */
  scanContent(container) {
    if (!container) { this._reset(); return; }
    this.pageNumbers = [];
    container.querySelectorAll('a[id^="S"]').forEach(a => {
      const pageInfo = this._parsePageAnchor(a.id);
      if (pageInfo) this.pageNumbers.push({ id: a.id, ...pageInfo, el: a });
    });

    this.hasPageAnchors = this.pageNumbers.length > 0;
    if (this.hasPageAnchors) {
      this._setupObserver();
    } else {
      this._reset();
    }
  }

  _reset() {
    this._cleanupObserver();
    this.pageNumbers = [];
    this.currentPage = null;
    this.hasPageAnchors = false;
    this._lastAutoMarkerId = null;
    this._lastAutoMarkerAt = 0;
    this._clearPageMarker();
    this._updateBadge(null);
  }

  _setupObserver() {
    this._cleanupObserver();
    if (!this.pageNumbers.length) return;
    this._io = new IntersectionObserver(entries => {
      const visible = entries
        .filter(e => e.isIntersecting)
        .map(e => {
          const p = this.pageNumbers.find(x => x.id === e.target.id);
          return p ? { ...p, top: e.boundingClientRect.top } : null;
        })
        .filter(Boolean);
      if (visible.length) {
        visible.sort((a, b) => a.top - b.top);
        const previousId = this.currentPage?.id || null;
        this.currentPage = visible[0];
        this._updateBadge(this.currentPage);
        if (this._scrollMarkerReady && this.currentPage.id !== previousId) {
          this._showAutoPageMarker(this.currentPage, { source: 'scroll', force: true });
        }
      }
    }, { root: null, rootMargin: '-40% 0px -40% 0px', threshold: 0 });
    this.pageNumbers.forEach(p => this._io.observe(p.el));
    this._scrollMarkerHandler = () => this._queueScrollPageMarker();
    window.addEventListener('scroll', this._scrollMarkerHandler, { passive: true });
    window.addEventListener('resize', this._scrollMarkerHandler, { passive: true });
    this._scrollMarkerReady = false;
    setTimeout(() => {
      this._scrollMarkerReady = true;
      this._queueScrollPageMarker();
    }, 500);
  }

  _cleanupObserver() {
    if (this._io) { this._io.disconnect(); this._io = null; }
    if (this._scrollMarkerHandler) {
      window.removeEventListener('scroll', this._scrollMarkerHandler);
      window.removeEventListener('resize', this._scrollMarkerHandler);
      this._scrollMarkerHandler = null;
    }
    if (this._scrollMarkerRaf) {
      cancelAnimationFrame(this._scrollMarkerRaf);
      this._scrollMarkerRaf = null;
    }
    this._scrollMarkerReady = false;
  }

  _parsePageAnchor(id) {
    const plain = id.match(/^S(\d+)$/);
    if (plain) {
      return {
        page: plain[1],
        label: plain[1],
        citePage: plain[1]
      };
    }

    const scoped = id.match(/^S(.+?)-p?(\d+)$/i);
    if (scoped) {
      const scope = scoped[1].replace(/^[-_]+|[-_]+$/g, '');
      const page = scoped[2];
      return {
        scope,
        page,
        label: `${scope}, S. ${page}`,
        citePage: `${scope}, S. ${page}`
      };
    }

    return null;
  }

  _updateBadge(pageInfo) {
    const link = document.getElementById('page-breadcrumb-link');
    if (link) {
      if (pageInfo !== null && pageInfo !== undefined) {
        const info = typeof pageInfo === 'object' ? pageInfo : { label: pageInfo, citePage: pageInfo };
        link.textContent = info.scope ? info.label : 'S. ' + info.label;
        link.style.display = '';
        link.dataset.page = info.citePage || info.label;
        if (info.id) link.dataset.pageAnchorId = info.id;
        this._bindCopy(link);
      } else {
        link.textContent = '';
        link.style.display = 'none';
        delete link.dataset.pageAnchorId;
      }
    }
  }

  _clearPageMarker() {
    clearTimeout(this._pageMarkerTimer);
    this._pageMarkerTimer = null;
    if (this._pageMarkerEl) {
      this._pageMarkerEl.remove();
      this._pageMarkerEl = null;
    }
    if (this._dismissPageMarkerHandler) {
      document.removeEventListener('click', this._dismissPageMarkerHandler, true);
      this._dismissPageMarkerHandler = null;
    }
  }

  _showAutoPageMarker(pageInfo, options = {}) {
    const info = this._resolvePageInfo(pageInfo);
    if (!info) return false;

    const now = Date.now();
    if (!options.force && now - this._lastAutoMarkerAt < 650) {
      return false;
    }
    if (!options.force && info.id === this._lastAutoMarkerId && now - this._lastAutoMarkerAt < 1800) {
      return false;
    }

    this._lastAutoMarkerId = info.id;
    this._lastAutoMarkerAt = now;
    this.currentPage = info;
    this._updateBadge(info);
    return this._showPageMarker(info, options);
  }

  _queueScrollPageMarker() {
    if (!this._scrollMarkerReady || this._scrollMarkerRaf) return;
    this._scrollMarkerRaf = requestAnimationFrame(() => {
      this._scrollMarkerRaf = null;
      this._syncScrollPageMarker();
    });
  }

  _syncScrollPageMarker() {
    if (!this.pageNumbers.length) return false;

    const readingLine = Math.max(80, innerHeight * 0.42);
    let current = null;
    for (const pageInfo of this.pageNumbers) {
      const rect = pageInfo.el.getBoundingClientRect();
      if (rect.top <= readingLine) {
        current = pageInfo;
      } else {
        break;
      }
    }
    current = current || this.pageNumbers[0];

    this.currentPage = current;
    this._updateBadge(current);
    return this._showAutoPageMarker(current, { source: 'scroll', force: true });
  }

  _resolvePageInfo(target) {
    if (!target) return this.currentPage;
    if (typeof target === 'object') return target;

    const id = String(target).replace(/^#/, '');
    const known = this.pageNumbers.find(p => p.id === id);
    if (known) return known;

    const anchor = document.getElementById(id);
    const pageInfo = this._parsePageAnchor(id);
    return anchor && pageInfo ? { id, ...pageInfo, el: anchor } : null;
  }

  highlightPageAnchor(target, options = {}) {
    const info = this._resolvePageInfo(target);
    if (!info) return false;
    this.currentPage = info;
    this._updateBadge(info);
    this._highlightPageAnchor(info, options);
    return true;
  }

  _highlightPageAnchor(pageInfo, options = {}) {
    const shouldScroll = options.scroll !== false;
    const info = this._resolvePageInfo(pageInfo);
    const anchor = info?.el || (info?.id ? document.getElementById(info.id) : null);
    if (!anchor) return false;

    if (shouldScroll) {
      if (typeof window.scrollToEl === 'function') {
        window.scrollToEl(anchor);
      } else {
        anchor.scrollIntoView({ block: 'center', behavior: 'smooth' });
      }
    }

    return this._showPageMarker(info, options);
  }

  _showPageMarker(pageInfo, options = {}) {
    const info = this._resolvePageInfo(pageInfo);
    const anchor = info?.el || (info?.id ? document.getElementById(info.id) : null);
    if (!info || !anchor) return false;

    this._clearPageMarker();
    this._ensureMarkerStyles();

    const marker = document.createElement('div');
    marker.className = 'reader-page-marker';
    marker.setAttribute('role', 'button');
    marker.setAttribute('aria-live', 'polite');
    marker.tabIndex = 0;
    marker.textContent = info.scope ? info.label : 'S. ' + info.label;
    marker.setAttribute('aria-label', marker.textContent + ' Quellenangabe kopieren');
    marker.dataset.page = info.citePage || info.label;
    if (info.id) marker.dataset.pageAnchorId = info.id;
    marker.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      const page = e.currentTarget.dataset.page;
      if (page) this._copyCitation(e.currentTarget, page);
    });
    marker.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      e.preventDefault();
      const page = e.currentTarget.dataset.page;
      if (page) this._copyCitation(e.currentTarget, page);
    });

    const anchorRect = anchor.getClientRects()[0] || anchor.getBoundingClientRect();
    const contentRect = document.getElementById('content')?.getBoundingClientRect();
    const sidebarOpen = innerWidth < 997 && document.querySelector('.doc-sidebar--open');
    const labelLeft = Number.isFinite(anchorRect.left) && anchorRect.left > 0
      ? anchorRect.left + scrollX
      : (contentRect?.left ?? 24) + scrollX;
    const labelTop = Math.max(0, anchorRect.top + scrollY);

    marker.style.left = `${Math.max(8, labelLeft)}px`;
    marker.style.top = `${labelTop}px`;
    marker.style.maxWidth = `min(240px, calc(100vw - ${Math.max(24, labelLeft - scrollX + 16)}px))`;
    marker.style.zIndex = sidebarOpen || options.underMenu ? '90' : '250';

    document.body.appendChild(marker);
    this._pageMarkerEl = marker;
    setTimeout(() => {
      if (this._pageMarkerEl !== marker) return;
      this._dismissPageMarkerHandler = (e) => {
        const target = e.target?.nodeType === 1 ? e.target : e.target?.parentElement;
        const mobileSidebarOpen = innerWidth < 997 && document.querySelector('.doc-sidebar--open');
        if (mobileSidebarOpen) return;
        if (target?.closest('.reader-page-marker, #sidebar-backdrop, .sidebar-overlay, a, button, input, select, textarea, summary, [role="button"], .doc-sidebar, .dropdown, .popover, .navbar')) return;
        this._clearPageMarker();
      };
      document.addEventListener('click', this._dismissPageMarkerHandler, true);
    }, 0);

    this._pageMarkerTimer = setTimeout(() => {
      marker.classList.add('reader-page-marker--leaving');
      this._pageMarkerTimer = setTimeout(() => this._clearPageMarker(), 320);
    }, 1900);

    return true;
  }

  _ensureMarkerStyles() {
    if (document.getElementById('reader-page-marker-style')) return;
    const style = document.createElement('style');
    style.id = 'reader-page-marker-style';
    style.textContent = `
      .reader-page-marker {
        position: absolute;
        padding: 7px 11px;
        border-radius: 8px;
        background: color-mix(in srgb, var(--bg-card, #ffffff) 88%, var(--accent-bg, #fef3c7));
        border: 1px solid color-mix(in srgb, var(--accent-border, #78350f) 64%, transparent);
        border-left: 4px solid var(--accent, #b45309);
        color: var(--text, #1c1917);
        box-shadow: var(--shadow-md, 0 10px 28px rgba(0, 0, 0, .18));
        font: 700 13px/1.25 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        white-space: nowrap;
        transform: translateY(-50%);
        cursor: pointer;
        pointer-events: auto;
        opacity: 1;
        animation: readerPageMarkerBreathe 1600ms ease-in-out infinite;
        transition: opacity 260ms ease, transform 260ms ease;
      }
      .reader-page-marker--leaving {
        opacity: 0;
        transform: translateY(-50%) scale(.98);
      }
      @keyframes readerPageMarkerBreathe {
        0%, 100% {
          box-shadow: var(--shadow-md, 0 10px 28px rgba(0, 0, 0, .16));
        }
        50% {
          box-shadow:
            var(--shadow-md, 0 10px 28px rgba(0, 0, 0, .16)),
            0 0 0 3px color-mix(in srgb, var(--accent, #b45309) 24%, transparent);
        }
      }
      @media (prefers-reduced-motion: reduce) {
        .reader-page-marker { animation: none !important; }
      }
    `;
    document.head.appendChild(style);
  }

  _findVolumeCitation(path) {
    const cfg = window.LIBRARY_CONFIG || [];
    const doc = (path || '').replace(/^\//, '');
    const docDir = doc.replace(/\/[^\/]+$/, '');
    for (const col of cfg) {
      for (const group of (col.groups || [])) {
        const gCit = group.citation || {};
        const gVol = group.volume || null;
        for (const item of (group.items || [])) {
          const p = (item.path || '').replace(/^\//, '');
          const itemDir = p.replace(/\/[^\/]+$/, '');
          if (doc === p || docDir === itemDir || doc.startsWith(itemDir + '/')) {
            // 合并 citation：全集 → 分组 → 条目；volume 独立提取
            const merged = {
              ...(col.citation || {}),
              ...gCit,
              ...(item.citation || {}),
              volume: item.volume || gVol || col.volume || null
            };
            return merged;
          }
        }
        const gp = (group.path || '').replace(/^\//, '');
        if (gp && (doc === gp || docDir === gp.replace(/\/[^\/]+$/, '') || doc.startsWith(gp.replace(/\/[^\/]+$/, '') + '/'))) {
          return {
            ...(col.citation || {}),
            ...gCit,
            volume: gVol || col.volume || null
          };
        }
      }
      const cp = (col.path || '').replace(/^\//, '');
      if (cp && (doc === cp || doc.startsWith(cp.replace(/\/[^\/]+$/, '/') || ''))) {
        return {
          ...(col.citation || {}),
          volume: col.volume || null
        };
      }
    }
    return null;
  }

  _formatCitationPage(page, pageParam) {
    const pageText = String(page);
    if (/(^|,\s)(S|p)\.\s/i.test(pageText)) return pageText;
    return pageParam.replace('${page}', pageText);
  }

  _generateCitation(page) {
    const cit = this._findVolumeCitation(state.doc);

    // 如果有任意有效 citation 字段（prefix / title / year / volume），使用它
    if (cit && (cit.prefix || cit.title || cit.year || cit.volume)) {
      let text = cit.prefix || '';
      if (cit.title) text += (text ? ', ' : '') + `${cit.title}`;
      if (cit.volume) text += (text ? ', ' : '') + cit.volume;
      if (cit.publisher) text += (text ? ', ' : '') + cit.publisher;
      if (cit.year) text += (text ? ' ' : '') + `${cit.year}`;
      const pageParam = cit.pageParam || 'S. ${page}';
      text += (text ? ', ' : '') + this._formatCitationPage(page, pageParam);
      return text;
    }

    // 全集级 fallback：按 collection id 匹配
    const col = findCollection(state.doc);
    const id = col?.id || '';
    const pageText = this._formatCitationPage(page, 'S. ${page}');
    if (id === 'mew') return `MEW, ${pageText}`;
    if (id === 'mega') return `MEGA², ${pageText}`;
    if (id === 'mecw') return `MECW, ${this._formatCitationPage(page, 'p. ${page}')}`;
    if (id === 'hegel') return `G.W.F.Hegel Werke, ${pageText}`;
    if (id === 'mlclassic') return `MLCLASSIC, ${pageText}`;
    return `${id ? id.toUpperCase() + ', ' : ''}${pageText}`;
  }

  _showCitationPopover(triggerEl) {
    if (typeof window.showReaderNotice === 'function') {
      window.showReaderNotice('Die Quellenangabe wurde in die Zwischenablage kopiert' +(': '+triggerEl?.dataset.citation || '.') +' ✓');
      return;
    }

    let popover = document.getElementById('citation-popover');
    if (!popover) {
      popover = document.createElement('div');
      popover.id = 'citation-popover';
      popover.className = 'popover';
      popover.innerHTML = '<div class="popover__body" style="margin-bottom:0">Die Quellenangabe wurde in die Zwischenablage kopiert. ✓</div>';
      document.body.appendChild(popover);
    }

    const rect = triggerEl.getBoundingClientRect();
    const sidebar = document.querySelector('.doc-sidebar');
    let maxWidth = 340;
    if (sidebar) {
      const sbRect = sidebar.getBoundingClientRect();
      if (sbRect.width > 50) {
        maxWidth = Math.min(340, sbRect.width - 24);
      }
    }

    const left = Math.max(8, Math.min(rect.left, innerWidth - maxWidth - 8));
    const top = rect.bottom + 4;

    // 使用 cssText 强制覆盖外部 CSS 的 !important（尤其是移动端媒体查询）
    popover.style.cssText = `
      display: block !important;
      position: fixed !important;
      top: ${top}px !important;
      left: ${left}px !important;
      right: auto !important;
      bottom: auto !important;
      width: ${maxWidth}px !important;
      max-height: none !important;
      overflow: visible !important;
      z-index: 500 !important;
    `;

    popover.classList.add('popover--visible');

    clearTimeout(this._citationPopoverTimer);
    this._citationPopoverTimer = setTimeout(() => {
      popover.classList.remove('popover--visible');
      popover.style.cssText = '';
    }, 1000);

    if (this._dismissPopoverHandler) {
      document.removeEventListener('click', this._dismissPopoverHandler, true);
    }
    this._dismissPopoverHandler = (e) => {
      if (popover.contains(e.target) || e.target === triggerEl) return;
      popover.classList.remove('popover--visible');
      popover.style.cssText = '';
      document.removeEventListener('click', this._dismissPopoverHandler, true);
      this._dismissPopoverHandler = null;
    };
    setTimeout(() => {
      if (popover.classList.contains('popover--visible')) {
        document.addEventListener('click', this._dismissPopoverHandler, true);
      }
    }, 50);
  }

  _copyCitation(el, page) {
    const citation = this._generateCitation(page);
    el.dataset.citation = citation;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(citation).then(() => {
        this._showCitationPopover(el);
      }).catch(() => this._fallbackCopy(el, citation));
    } else {
      this._fallbackCopy(el, citation);
    }
  }

  _bindCopy(el, options = {}) {
    if (!el || el._copyBound) return;
    el._copyBound = true;
    el.title = 'Quellenangabe';
    el.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      e.stopImmediatePropagation();
      const page = e.currentTarget.dataset.page;
      if (!page) return;
      if (options.highlight !== false) {
        this.highlightPageAnchor(e.currentTarget.dataset.pageAnchorId || this.currentPage, { source: e.currentTarget.dataset.copySource || 'sidebar' });
      }
      this._copyCitation(e.currentTarget, page);
    });
  }

  _fallbackCopy(el, citation) {
    const ta = document.createElement('textarea');
    ta.value = citation;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    let copied = false;
    try { copied = document.execCommand('copy'); } catch (e) { }
    document.body.removeChild(ta);
    if (copied) {
      this._showCitationPopover(el);
    } else if (typeof window.showReaderNotice === 'function') {
      window.showReaderNotice('复制被浏览器拦截，请手动复制：' + citation, { type: 'error', duration: 3600 });
    } else {
      this._showCitationPopover(el);
    }
  }

  destroy() {
    this._reset();
  }
}

window.PageBarManager = PageBarManager;
