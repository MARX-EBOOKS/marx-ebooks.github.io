// ===== PageBarManager: 页码锚点追踪与面包屑动态显示 =====
class PageBarManager {
  constructor() {
    this.pageNumbers = [];
    this.currentPage = null;
    this.hasPageAnchors = false;
    this._io = null;
    this._citationPopoverTimer = null;
    this._dismissPopoverHandler = null;
  }

  init() {
    // 页码仅显示在左侧面包屑，无顶部呼吸/浮动逻辑
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
        this.currentPage = visible[0];
        this._updateBadge(this.currentPage);
      }
    }, { root: null, rootMargin: '-40% 0px -40% 0px', threshold: 0 });
    this.pageNumbers.forEach(p => this._io.observe(p.el));
  }

  _cleanupObserver() {
    if (this._io) { this._io.disconnect(); this._io = null; }
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
        this._bindCopy(link);
      } else {
        link.textContent = '';
        link.style.display = 'none';
      }
    }
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
      window.showReaderNotice('Die Quellenangabe wurde in die Zwischenablage kopiert. ✓' + (triggerEl?.dataset.citation || ''));
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
    }, 2200);

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

  _bindCopy(el) {
    if (!el || el._copyBound) return;
    el._copyBound = true;
    el.title = 'Quellenangabe';
    el.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      e.stopImmediatePropagation();
      const page = e.currentTarget.dataset.page;
      if (!page) return;
      const citation = this._generateCitation(page);
      e.currentTarget.dataset.citation = citation;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(citation).then(() => {
          this._showCitationPopover(e.currentTarget);
        }).catch(() => this._fallbackCopy(e.currentTarget, citation));
      } else {
        this._fallbackCopy(e.currentTarget, citation);
      }
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
