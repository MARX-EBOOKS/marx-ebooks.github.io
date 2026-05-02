function esc(t) {
  return String(t)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

const SVG = {
  menu: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>',
  bookmark: '<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>',
  sun: '<svg class="icon-sun" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>',
  moon: '<svg class="icon-moon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display:none"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>',
  dots: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="6" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="12" cy="18" r="1"/></svg>',
  close: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>'
};

/**
 * Generate reader page HTML
 * @param {Object} opts
 * @returns {string} Complete HTML document
 */
function generateTemplate(opts) {
  const {
    title, bodyHtml, headExtras = [], meta, root,
    prev, next, breadcrumb, hasVolIndex,
    volJsPath = '', volLabel = 'Contents',
    logo, logoText, site,
    antiFlash = `<script>(function(){var t=localStorage.getItem('theme')||'light';document.documentElement.setAttribute('data-theme',t);var f=parseFloat(localStorage.getItem('fontSize'));if(f&&f!==1)document.documentElement.style.setProperty('--fs-user',Math.round(16*f)+'px');var lh=parseFloat(localStorage.getItem('lineHeight'));if(lh)document.documentElement.style.setProperty('--lh-user',lh);})();<\/script>`
  } = opts;

  const prevBtn = prev
    ? `<a href="./${esc(prev.file)}" class="pagination-link" id="prev-btn"><span class="pagination-link__dir">\u2190</span><span class="pagination-link__label">${esc(prev.title)}</span></a>`
    : '<div></div>';
  const nextBtn = next
    ? `<a href="./${esc(next.file)}" class="pagination-link pagination-link--next" id="next-btn"><span class="pagination-link__dir">\u2192</span><span class="pagination-link__label">${esc(next.title)}</span></a>`
    : '<div></div>';

  const logoPath = logo ? `<img src="${esc(logo)}"/>` : '';
  const volPreload = hasVolIndex && volJsPath ? `<link rel="preload" href="${esc(volJsPath)}" as="fetch" crossorigin>` : '';

  return `<!DOCTYPE html>
<html lang="zh" data-theme="light">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${esc(title)} \u2014 ${esc(logoText)}</title>
${antiFlash}
${volPreload}
<link rel="stylesheet" href="${site}/assets/reader.css">
${headExtras.join('\n')}
<script>window.__PAGE_META__=${JSON.stringify(meta)};<\/script>
</head>
<body data-site="${esc(site)}">
<div class="scroll-indicator" id="progress-bar"></div>
<nav class="navbar" id="navbar">
  <div class="navbar__brand">
    <button type="button" class="clean-btn" id="sidebar-toggle" title="TOC (Ctrl+S)">
      ${SVG.menu}
    </button>
    <a class="navbar__logo" href="/" style="text-decoration:none;">
      ${logoPath}
      <span>${esc(logoText)}</span>
    </a>
  </div>
  <div class="navbar__items" id="nav-actions">
    <div class="navbar__item">
      <div class="font-control">
        <button type="button" class="font-btn" id="font-dec-btn" title="Decrease font">A\u2212</button>
        <input type="range" id="font-slider" min="0.75" max="1.5" step="0.05" value="1">
        <button type="button" class="font-btn" id="font-inc-btn" title="Increase font">A+</button>
      </div>
      <div class="lh-control">
        <button type="button" class="font-btn" id="lh-dec-btn" title="Decrease line height">\u2195\u2212</button>
        <input type="range" id="lh-slider" min="1.4" max="2.6" step="0.1" value="2.0">
        <button type="button" class="font-btn" id="lh-inc-btn" title="Increase line height">\u2195+</button>
      </div>
      <button type="button" class="clean-btn" id="remember-btn" title="Remember scroll position">
        ${SVG.bookmark}
      </button>
      <button type="button" class="clean-btn" id="theme-btn" title="Toggle theme">
        ${SVG.sun}${SVG.moon}
      </button>
    </div>
    <button type="button" class="clean-btn navbar__toggle" id="mobile-menu-toggle" title="Settings">
      ${SVG.dots}
    </button>
  </div>
</nav>
<div class="dropdown" id="mobile-menu">
  <div class="dropdown__label">Font Size</div>
  <div class="dropdown__row">
    <button type="button" class="stepper" id="mobile-font-dec">\u2212</button>
    <input type="range" id="mobile-font-slider" min="0.75" max="1.5" step="0.05" value="1">
    <button type="button" class="stepper" id="mobile-font-inc">+</button>
  </div>
  <div class="dropdown__rule"></div>
  <div class="dropdown__label">Line Height</div>
  <div class="dropdown__row">
    <button type="button" class="stepper" id="mobile-lh-dec">\u2212</button>
    <input type="range" id="mobile-lh-slider" min="1.4" max="2.6" step="0.1" value="2.0">
    <button type="button" class="stepper" id="mobile-lh-inc">+</button>
  </div>
  <div class="dropdown__rule"></div>
  <div class="dropdown__item" id="mobile-remember">
    <span>Remember Position</span>
    <span class="toggle-indicator" id="mobile-remember-indicator">\u25CB</span>
  </div>
  <div class="dropdown__item" id="mobile-theme">
    <span>Dark Mode</span>
    <span class="toggle-indicator" id="mobile-theme-indicator">\u25CB</span>
  </div>
</div>
<div class="sidebar-overlay" id="sidebar-backdrop"></div>
<div class="doc-wrapper" id="shell">
  <div class="doc-root">
    <aside class="doc-sidebar" id="lsidebar">
      <div class="doc-sidebar__header">
        <a class="doc-sidebar__brand" href="/" style="text-decoration:none;">
          ${logoPath}
          <span>${esc(logoText)}</span>
        </a>
        <div style="display:flex;align-items:center;gap:4px;">
          <button type="button" class="clean-btn" id="sidebar-theme-btn" title="Toggle theme">
            ${SVG.sun}${SVG.moon}
          </button>
          <button type="button" class="clean-btn" id="sidebar-close-btn" title="Close menu">
            ${SVG.close}
          </button>
        </div>
      </div>
      <nav class="sidebar-nav" id="nav-tree"></nav>
    </aside>
    <main class="doc-main" id="main">
      <div class="doc-main-inner">
        <div id="doc-view" style="display:block">
          <div class="doc-content">
            <header class="doc-header" id="doc-header">
              <div class="doc-header__pathbar" id="doc-pathbar">
                ${breadcrumb || '<span style="color:var(--text-3);">Library</span>'}
              </div>
            </header>
            <div class="prose" id="content">
${bodyHtml}
            </div>
            <nav class="doc-footer" id="doc-footer">
              ${prevBtn}
              ${nextBtn}
            </nav>
          </div>
        </div>
        <div class="theme-doc-toc-desktop" id="toc-desktop">
          <nav class="theme-doc-toc-desktop-nav" id="toc-desktop-nav"></nav>
        </div>
      </div>
    </main>
  </div>
</div>
<div class="popover" id="fn-tooltip">
  <div class="popover__body"></div>
  <a class="popover__jump" href="#" style="display:none"></a>
</div>
<script src="${site}/assets/libmap.js"></script>
<script src="${site}/assets/nav.js"></script>
<script src="${site}/assets/reader.js"></script>
<script>(function(){
  function syncFill(el){
    var min=parseFloat(el.min)||0,max=parseFloat(el.max)||100,val=parseFloat(el.value)||0;
    var pct=((val-min)/(max-min)*100).toFixed(2)+'%';
    el.style.setProperty('--_fill',pct);
  }
  document.querySelectorAll('input[type="range"]').forEach(function(el){
    syncFill(el);
    el.addEventListener('input',function(){syncFill(this);});
  });
  // re-sync when nav.js updates slider value programmatically
  var orig=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value');
  if(orig&&orig.set){
    Object.defineProperty(HTMLInputElement.prototype,'value',{
      set:function(v){orig.set.call(this,v);if(this.type==='range')syncFill(this);},
      get:orig.get,configurable:true
    });
  }
})();<\/script>
</body>
</html>`;
}

module.exports = { generateTemplate, esc };