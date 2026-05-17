// ===== PageBarManager: 页码锚点追踪与面包屑动态显示 =====
class PageBarManager {
  constructor() {
    this.pageNumbers = [];
    this.currentPage = null;
    this.hasPageAnchors = false;
    this.header = null;
    this.pathbar = null;
    this._io = null;
    this._scrollHandler = null;
    this._clickHandler = null;
    this._touchStartY = 0;
    this._touchStartX = 0;
    this._touchStartTime = 0;
    this._touchHandler = null;
    this._resizeHandler = null;
    this._hideTimer = null;
    this._toastTimer = null;
    this._lastScrollY = 0;
    this._isMobile = innerWidth < 997;
  }

  init() {
    this.header = $('#doc-header');
    this.pathbar = $('#doc-pathbar');
    if (!this.header || !this.pathbar) return;
    this._createTocIndicator();
    this._bindEvents();
    this._checkMobile();
  }

  _createTocIndicator() {
    const tocDesktop = $('#toc-desktop');
    if (!tocDesktop) return;
    // 避免重复创建
    if (document.getElementById('toc-page-indicator')) return;

    const el = document.createElement('div');
    el.id = 'toc-page-indicator';
    el.className = 'toc-page-indicator';
    el.style.display = 'none';
    el.innerHTML = `<span class="toc-page-indicator__label">Page</span>
                    <span class="toc-page-indicator__value" id="toc-page-value">--</span>`;

    const nav = $('#toc-desktop-nav');
    if (nav && nav.parentNode === tocDesktop) {
      tocDesktop.insertBefore(el, nav);
    } else {
      tocDesktop.appendChild(el);
    }
  }

  /* ---- 扫描正文中的页码锚点 <a id="S123"></a> ---- */
  scanContent(container) {
    if (!container) { this._reset(); return; }
    this.pageNumbers = [];
    container.querySelectorAll('a[id^="S"]').forEach(a => {
      const m = a.id.match(/^S(\d+)$/);
      if (m) this.pageNumbers.push({ id: a.id, number: parseInt(m[1], 10), el: a });
    });

    this.hasPageAnchors = this.pageNumbers.length > 0;
    if (this.hasPageAnchors) {
      this._setupObserver();
      this.header.classList.add('pagebar-active');
      $('#article-view')?.classList.add('pagebar-offset');
      this._checkMobile();
    } else {
      this._reset();
    }
  }

  _reset() {
    this._cleanupObserver();
    this.pageNumbers = [];
    this.currentPage = null;
    this.hasPageAnchors = false;
    if (this.header) {
      this.header.classList.remove(
        'pagebar-active', 'pagebar-floating', 'pagebar-breathing',
        'pagebar-hidden', 'pagebar-breath-in', 'pagebar-breath-out'
      );
    }
    $('#article-view')?.classList.remove('pagebar-offset');
    this._updateBadge(null);
    clearTimeout(this._hideTimer);
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
        this.currentPage = visible[0].number;
        this._updateBadge(this.currentPage);
      }
    }, { root: null, rootMargin: '-40% 0px -40% 0px', threshold: 0 });
    this.pageNumbers.forEach(p => this._io.observe(p.el));
  }

  _cleanupObserver() {
    if (this._io) { this._io.disconnect(); this._io = null; }
  }

  _updateBadge(page) {
    // 1. 面包屑中的页码签
    const badge = document.getElementById('page-badge');
    if (badge) {
      if (page !== null && page !== undefined) {
        badge.textContent = 'S. ' + page;
        badge.style.display = '';
        badge.dataset.page = page;
        this._bindCopy(badge);
      } else {
        badge.textContent = '';
        badge.style.display = 'none';
      }
    }
    // 2. 桌面端右侧栏页码指示器
    const tocInd = document.getElementById('toc-page-indicator');
    const tocVal = document.getElementById('toc-page-value');
    if (tocInd && tocVal) {
      if (page !== null && page !== undefined) {
        tocVal.textContent = 'S. ' + page;
        tocInd.style.display = '';
        tocInd.dataset.page = page;
        this._bindCopy(tocInd);
      } else {
        tocInd.style.display = 'none';
      }
    }
  }

  _findVolumeCitation(path) {
    const cfg = window.LIBRARY_CONFIG || [];
    const doc = (path || '').replace(/^\//, '');
    const docDir = doc.replace(/\/[^\/]+$/, '');
    for (const col of cfg) {
      for (const group of (col.groups || [])) {
        // group 级 citation
        const gCit = group.citation;
        for (const item of (group.items || [])) {
          const p = (item.path || '').replace(/^\//, '');
          const itemDir = p.replace(/\/[^\/]+$/, '');
          if (doc === p || docDir === itemDir || doc.startsWith(itemDir + '/')) {
            // 优先 item.citation，其次 group.citation，再其次 col.citation
            return item.citation || gCit || col.citation || null;
          }
        }
        // 如果 group 有 path 属性且匹配
        const gp = (group.path || '').replace(/^\//, '');
        if (gp && (doc === gp || docDir === gp.replace(/\/[^\/]+$/, '') || doc.startsWith(gp.replace(/\/[^\/]+$/, '') + '/'))) {
          return gCit || col.citation || null;
        }
      }
      // 兜底：collection 级 path 匹配
      const cp = (col.path || '').replace(/^\//, '');
      if (cp && (doc === cp || doc.startsWith(cp.replace(/\/[^\/]+$/, '') + '/'))) {
        return col.citation || null;
      }
    }
    return null;
  }

  _generateCitation(page) {
    const col = findCollection(state.doc);
    const id = col?.id || '';
    const cit = this._findVolumeCitation(state.doc);

    // 如果 libmap 中配置了 citation 对象，按模板生成
    if (cit) {
      let text = cit.prefix || '';
      if (cit.title) text += (text ? ', ' : '') + `《${cit.title}》`;
      if (cit.volume) text += (text ? ', ' : '') + cit.volume;
      if (cit.year) text += (text ? ' ' : '') + `(${cit.year})`;
      const pageParam = cit.pageParam || 'S. ${page}';
      text += (text ? ', ' : '') + pageParam.replace('${page}', page);
      return text;
    }

    // fallback demo：基于 libmap id
    if (id === 'mew') return `MEW, S. ${page}`;
    if (id === 'mega') return `MEGA², S. ${page}`;
    if (id === 'mecw') return `MECW, p. ${page}`;
    if (id === 'mlclassic') return `MLCLASSIC, S. ${page}`;
    // 通用 fallback
    return `${id ? id.toUpperCase() + ', ' : ''}S. ${page}`;
  }

  _showToast(msg) {
    const toast = document.getElementById('copy-toast');
    if (!toast) return;
    toast.textContent = msg;
    toast.style.opacity = '1';
    toast.style.transform = 'translateX(-50%) translateY(0)';
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(-50%) translateY(8px)';
    }, 2200);
  }

  _bindCopy(el) {
    if (!el || el._copyBound) return;
    el._copyBound = true;
    el.title = '点击复制引用格式';
    el.addEventListener('click', (e) => {
      e.stopPropagation();
      const page = parseInt(e.currentTarget.dataset.page, 10);
      if (!page && page !== 0) return;
      const citation = this._generateCitation(page);
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(citation).then(() => {
          this._showToast(`已复制：${citation}`);
        }).catch(() => this._fallbackCopy(e.currentTarget, citation));
      } else {
        this._fallbackCopy(e.currentTarget, citation);
      }
    });
  }

  _fallbackCopy(el, citation) {
    const range = document.createRange();
    range.selectNodeContents(el);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    this._showToast('引用已选中，请手动复制');
  }

  _checkMobile() {
    this._isMobile = innerWidth < 997;
    if (!this.hasPageAnchors || !this.header) return;
    if (this._isMobile) {
      this.header.classList.remove('pagebar-floating', 'pagebar-hidden');
      this.header.classList.add('pagebar-breathing');
    } else {
      this.header.classList.remove('pagebar-breathing', 'pagebar-breath-in', 'pagebar-breath-out');
      this.header.classList.add('pagebar-floating');
    }
  }

  _bindEvents() {
    // 桌面端：随滚动方向上下浮动
    this._scrollHandler = () => {
      if (!this.hasPageAnchors || this._isMobile) return;
      const y = scrollY;
      if (y > this._lastScrollY && y > 90) {
        this.header.classList.add('pagebar-hidden');
      } else {
        this.header.classList.remove('pagebar-hidden');
      }
      this._lastScrollY = y;
    };
    window.addEventListener('scroll', this._scrollHandler, { passive: true });

    // 移动端：点击 或 上滑 浮出面包屑
    this._clickHandler = e => {
      if (!this.hasPageAnchors || !this._isMobile) return;
      // 避开交互元素，避免与按钮/链接/输入框冲突
      if (e.target.closest('a, button, input, textarea, select, .sidebar, .popover, .dropdown, .navbar')) return;
      this._breathe();
    };
    document.addEventListener('click', this._clickHandler);

    // 上滑检测（touchend 判定）
    this._touchHandler = {
      start: e => {
        if (!this.hasPageAnchors || !this._isMobile) return;
        const t = e.changedTouches[0];
        this._touchStartY = t.clientY;
        this._touchStartX = t.clientX;
        this._touchStartTime = Date.now();
      },
      end: e => {
        if (!this.hasPageAnchors || !this._isMobile) return;
        const t = e.changedTouches[0];
        const dy = this._touchStartY - t.clientY;   // 向上为正
        const dx = Math.abs(t.clientX - this._touchStartX);
        const dt = Date.now() - this._touchStartTime;
        // 上滑超过 40px，水平偏移不超过 60px，时间不超过 600ms
        if (dy > 40 && dx < 60 && dt < 600) {
          this._breathe();
        }
      }
    };
    document.addEventListener('touchstart', this._touchHandler.start, { passive: true });
    document.addEventListener('touchend', this._touchHandler.end, { passive: true });

    this._resizeHandler = () => {
      const was = this._isMobile;
      this._isMobile = innerWidth < 997;
      if (was !== this._isMobile) this._checkMobile();
    };
    window.addEventListener('resize', this._resizeHandler);
  }

  _breathe() {
    if (!this.header) return;
    this.header.classList.remove('pagebar-breath-out');
    this.header.classList.add('pagebar-breath-in');
    clearTimeout(this._hideTimer);
    this._hideTimer = setTimeout(() => {
      this.header.classList.remove('pagebar-breath-in');
      this.header.classList.add('pagebar-breath-out');
    }, 2200);
  }

  destroy() {
    this._reset();
    window.removeEventListener('scroll', this._scrollHandler);
    document.removeEventListener('click', this._clickHandler);
    document.removeEventListener('touchstart', this._touchHandler.start);
    document.removeEventListener('touchend', this._touchHandler.end);
    window.removeEventListener('resize', this._resizeHandler);
  }
}

window.PageBarManager = PageBarManager;