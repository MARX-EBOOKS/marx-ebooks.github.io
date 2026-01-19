(function () {
  'use strict';

 
  const CONFIG = {
    enableTableScroll: true,
    enableProgress: true,
    saveInterval: 1000,
    storagePrefix: 'reader-progress:',
    restoreOffset: 0
  };

   
  function getPageKey() {
    return (
      location.pathname +
      location.search +
      location.hash.replace(/#.*/, '')
    );
  }

  function storageKey() {
    return CONFIG.storagePrefix + getPageKey();
  }

  function restoreProgress() {
    if (!CONFIG.enableProgress) return;

    const saved = localStorage.getItem(storageKey());
    if (!saved) return;

    const y = parseInt(saved, 10);
    if (isNaN(y)) return;

    requestAnimationFrame(() => {
      window.scrollTo(0, Math.max(0, y - CONFIG.restoreOffset));
    });
  }

  function bindProgressSaver() {
    if (!CONFIG.enableProgress) return;

    let timer = null;
    window.addEventListener(
      'scroll',
      function () {
        if (timer) return;
        timer = setTimeout(() => {
          localStorage.setItem(storageKey(), window.scrollY);
          timer = null;
        }, CONFIG.saveInterval);
      },
      { passive: true }
    );
  }

  function makeTablesScrollable() {
  document.querySelectorAll('table').forEach(function (table) {
    if (table.parentNode.classList.contains('table-scroll')) return;

    var wrapper = document.createElement('div');
    wrapper.className = 'table-scroll';
    wrapper.style.overflowX = 'auto';
    wrapper.style.maxWidth = '100%';
    wrapper.style.webkitOverflowScrolling = 'touch';
    table.parentNode.insertBefore(wrapper, table);
    wrapper.appendChild(table);
  });
}
function makeImgScrollable() {
  document.querySelectorAll('img').forEach(function (img) {
    if (!img.parentNode) return;
    if (img.parentNode.classList?.contains('img-scroll')) return;
    var d = document.createElement('div');
    d.className = 'img-scroll';
    d.style.overflowX = 'auto';
    d.style.webkitOverflowScrolling = 'touch';
    d.style.maxWidth = '100%';
    img.parentNode.insertBefore(d, img);
    d.appendChild(img);
  });
}
  function init() {
    restoreProgress();
    bindProgressSaver();
    makeTablesScrollable();
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
