// 配置:需要记录位置的页面路径正则表达式
const ALLOWED_PATHS = [
  /\/docs\/.+/,     
  /\/LENIN\/.+/,      
  /\/MEW-ZH\/.+/,     
  /\/MEW\/.+/,        
  /\/MEA\/.+/,        
  /\/VIL\/.+/,
  /\/en\/.+/
];

function isPathAllowed() {
  const path = window.location.pathname;
  return ALLOWED_PATHS.some(function(regex) {
    return regex.test(path);
  });
}

function shouldRestore() {
  const params = new URLSearchParams(window.location.search);
  return !params.has('rd');
}

window.addEventListener('load', function() {
  if (!isPathAllowed()) return;
  if (!shouldRestore()) return;
  
  const key = 'scroll_' + window.location.pathname;
  const saved = localStorage.getItem(key);
  if (saved) {
    window.scrollTo(0, parseInt(saved));
  }
});

window.addEventListener('scroll', function() {
  if (!isPathAllowed()) return;
  if (!shouldRestore()) return;
  
  const key = 'scroll_' + window.location.pathname;
  localStorage.setItem(key, window.scrollY);
});

function addParamToLinks() {
  const params = new URLSearchParams(window.location.search);
  
  if (params.has('rd')) {
    document.querySelectorAll('a').forEach(function(link) {
      const href = link.getAttribute('href');
      
      if (link.dataset.paramAdded) return;
      
      if (href && !href.startsWith('http') && !href.startsWith('javascript:') && !href.startsWith('mailto:')) {
        const hashIndex = href.indexOf('#');
        let path = hashIndex > -1 ? href.substring(0, hashIndex) : href;
        let hash = hashIndex > -1 ? href.substring(hashIndex) : '';
        
        if (path && !path.includes('?')) {
          link.href = path + '?rd' + hash;
          link.dataset.paramAdded = 'true';
        }
      }
    });
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', addParamToLinks);
} else {
  addParamToLinks();
}

window.addEventListener('load', function() {
  document.querySelectorAll('table').forEach(function(table) {
    if (table.offsetWidth > table.parentElement.offsetWidth) {
      const wrapper = document.createElement('div');
      wrapper.className = 'table-wrapper';
      table.parentNode.insertBefore(wrapper, table);
      wrapper.appendChild(table);
    }
  });
  document.querySelectorAll('img').forEach(function(img) {
    if (img.style.maxWidth) return;
    if (img.complete) {
      checkImageWidth(img);
    } else {
      img.addEventListener('load', function() {
        checkImageWidth(img);
      });
    }
  });
});

function checkImageWidth(img) {
  const containerWidth = img.parentElement.offsetWidth;
  const imageWidth = img.naturalWidth || img.width;

  if (imageWidth > containerWidth) {
    img.style.maxWidth = '100%';
    img.style.height = 'auto';
  }
}