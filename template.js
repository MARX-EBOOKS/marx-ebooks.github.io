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
  sun: '<svg id="icon-sun" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>',
  moon: '<svg id="icon-moon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display:none"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>',
  dots: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="6" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="12" cy="18" r="1"/></svg>'
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
    antiFlash = `<script>(function(){var t=localStorage.getItem('theme')||'light';document.documentElement.setAttribute('data-theme',t);var f=parseFloat(localStorage.getItem('fontSize'));if(f&&f!==1)document.documentElement.style.setProperty('--fs-user',Math.round(16*f)+'px');})();<\/script>`
  } = opts;

  const prevBtn = prev
    ? `<a href="./${esc(prev.file)}" class="doc-nav-btn" id="prev-btn"><span class="dir">\u2190</span><span class="doc-name">${esc(prev.title)}</span></a>`
    : '<div></div>';
  const nextBtn = next
    ? `<a href="./${esc(next.file)}" class="doc-nav-btn next" id="next-btn"><span class="doc-name">${esc(next.title)}</span><span class="dir">\u2192</span></a>`
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
<style>
.crumb { text-decoration: none; color: var(--text-2); transition: color 150ms; }
.crumb:hover { text-decoration: none; color: var(--text); }
.crumb.current { color: var(--text); cursor: default; pointer-events: none; }
.crumb-sep { margin: 0 6px; color: var(--text-3); opacity: 0.5; }
</style>
</head>
<body data-site="${esc(site)}">
<div id="progress-bar"></div>
<nav id="navbar">
  <div class="nav-left">
    <button type="button" class="nav-btn active" id="sidebar-toggle" title="TOC (Ctrl+S)">
      ${SVG.menu}
    </button>
    <a id="nav-logo" href="/" style="text-decoration:none;">
      ${logoPath}
      <span class="logo-text">${esc(logoText)}</span>
    </a>
  </div>
  <div id="nav-actions">
    <div class="desktop-tools">
      <div class="font-control-group">
        <button type="button" class="nav-btn font-btn" id="font-dec-btn" title="Decrease font">A\u2212</button>
        <input type="range" id="font-slider" min="0.75" max="1.5" step="0.05" value="1">
        <button type="button" class="nav-btn font-btn" id="font-inc-btn" title="Increase font">A+</button>
      </div>
      <button type="button" class="nav-btn active" id="remember-btn" title="Remember scroll position">
        ${SVG.bookmark}
      </button>
      <button type="button" class="nav-btn" id="theme-btn" title="Toggle theme">
        ${SVG.sun}${SVG.moon}
      </button>
    </div>
    <button type="button" class="nav-btn mobile-menu-btn" id="mobile-menu-toggle" title="Settings">
      ${SVG.dots}
    </button>
  </div>
</nav>
<div id="mobile-menu" class="mobile-dropdown">
  <div class="mobile-menu-header">Font Size</div>
  <div class="mobile-font-slider-wrapper">
    <button type="button" class="font-adjust-btn" id="mobile-font-dec">\u2212</button>
    <input type="range" id="mobile-font-slider" min="0.75" max="1.5" step="0.05" value="1">
    <button type="button" class="font-adjust-btn" id="mobile-font-inc">+</button>
  </div>
  <div class="mobile-divider"></div>
  <div class="mobile-menu-item" id="mobile-remember">
    <span>Remember Position</span>
    <span class="toggle-indicator" id="mobile-remember-indicator">\u25CF</span>
  </div>
  <div class="mobile-menu-item" id="mobile-theme">
    <span>Dark Mode</span>
    <span class="toggle-indicator" id="mobile-theme-indicator">\u25CB</span>
  </div>
</div>
<div id="sidebar-backdrop"></div>
<div id="shell">
<aside id="lsidebar">
  <div id="nav-tree"></div>
</aside>
  <main id="main">
    <div id="doc-view" style="display:block">
      <header id="doc-header">
        <div id="doc-pathbar" style="display:flex;align-items:center;flex-wrap:wrap;gap:4px;font-size:13px;">
          ${breadcrumb || '<span style="color:var(--text-3);">Library</span>'}
        </div>
      </header>
      <div id="content">
${bodyHtml}
      </div>
      <nav id="doc-footer">
        ${prevBtn}
        ${nextBtn}
      </nav>
    </div>
  </main>
</div>
<div id="fn-tooltip">
  <div class="fn-popup-content"></div>
  <a class="fn-jump-link" href="#" style="display:none"></a>
</div>
<script src="${site}/assets/libmap.js"></script>
<script src="${site}/assets/nav.js"></script>
<script src="${site}/assets/reader.js"></script>
</body>
</html>`;
}

module.exports = { generateTemplate, esc };