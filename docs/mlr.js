
// 配置:需要记录位置的页面路径正则表达式
const ALLOWED_PATHS = [
  /\/LENIN\/.+/,      
  /\/MEW-ZH\/.+/,   
   /\/MEA\/.+/,        
  /\/MEW\/.+/,        
  /\/MEW-ZENO\/.+/,     
  /\/HEGEL\/.+/,     
  /\/VIL\/.+/,
  /\/VIL-UAIO\/.+/,
  /\/VIL-FB2\/.+/,
  /\/MECW\/.+/,
  /\/archieve\/.+/,
  /\/history\/.+/
];

function isPathAllowed() {
  const path = window.location.pathname;
  return ALLOWED_PATHS.some(function(regex) {
    return regex.test(path);
  });
}

// 默认不记录,只有加?rd才记录
function shouldRestore() {
  const params = new URLSearchParams(window.location.search);
  return params.has('rd');
}

// 1. 记录和恢复阅读位置
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

// 2. 传递?rd参数到所有链接
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

// 3. 给超宽表格加滚动条,超宽图片限制宽度
window.addEventListener('load', function() {
  // 处理表格
  document.querySelectorAll('table').forEach(function(table) {
    if (table.offsetWidth > table.parentElement.offsetWidth) {
      const wrapper = document.createElement('div');
      wrapper.className = 'table-wrapper';
      table.parentNode.insertBefore(wrapper, table);
      wrapper.appendChild(table);
    }
  });
  
  // 处理超宽图片
  document.querySelectorAll('img').forEach(function(img) {
    // 如果图片已有max-width样式,跳过
    if (img.style.maxWidth) return;
    
    // 等图片加载完成后检查
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
  
  // 只有图片宽度超过容器时才限制
  if (imageWidth > containerWidth) {
    img.style.maxWidth = '100%';
    img.style.height = 'auto';
  }
}
