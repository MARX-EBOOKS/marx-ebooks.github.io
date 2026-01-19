(function () {
  'use strict';

  /* ===== 配置 ===== */
  var KEY = 'reader-progress:' + location.pathname;
  var SAVE_DELAY = 1000;
  var timer = null;

  /* ===== 阅读进度 ===== */
  function restoreProgress() {
    var y = localStorage.getItem(KEY);
    if (y) scrollTo(0, y | 0);
  }

  function bindProgressSaver() {
    addEventListener(
      'scroll',
      function () {
        if (timer) return;
        timer = setTimeout(function () {
          localStorage.setItem(KEY, scrollY);
          timer = null;
        }, SAVE_DELAY);
      },
      { passive: true }
    );
  }

  /* ===== table 横滚 ===== */
  function makeTablesScrollable() {
    document.querySelectorAll('table').forEach(function (el) {
      if (el.parentNode.classList.contains('table-scroll')) return;

      var d = document.createElement('div');
      d.className = 'table-scroll';
      d.style.overflowX = 'auto';
      d.style.webkitOverflowScrolling = 'touch';

      el.parentNode.insertBefore(d, el);
      d.appendChild(el);
    });
  }

  /* ===== img 横滚（表格图） ===== */
  function makeImgsScrollable() {
    document.querySelectorAll('img').forEach(function (el) {
      if (!el.parentNode || el.parentNode.classList.contains('img-scroll')) return;

      var d = document.createElement('div');
      d.className = 'img-scroll';
      d.style.overflowX = 'auto';
      d.style.webkitOverflowScrolling = 'touch';

      el.parentNode.insertBefore(d, el);
      d.appendChild(el);
    });
  }

  /* ===== 初始化顺序 ===== */

  // DOM 结构安全
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', makeTablesScrollable);
  } else {
    makeTablesScrollable();
  }

  // 布局完全稳定
  addEventListener('load', function () {
    makeImgsScrollable();
    restoreProgress();
    bindProgressSaver();
  });
})();
