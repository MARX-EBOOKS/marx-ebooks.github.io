// 1. 记录和恢复阅读位置
window.addEventListener('load', function() {
  const key = 'scroll_' + window.location.pathname;
  const saved = localStorage.getItem(key);
  if (saved) {
    window.scrollTo(0, parseInt(saved));
  }
});

window.addEventListener('scroll', function() {
  const key = 'scroll_' + window.location.pathname;
  localStorage.setItem(key, window.scrollY);
});

// 2. 给超宽表格加滚动条
window.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('table').forEach(function(table) {
    if (table.offsetWidth > table.parentElement.offsetWidth) {
      const wrapper = document.createElement('div');
      wrapper.className = 'table-wrapper';
      table.parentNode.insertBefore(wrapper, table);
      wrapper.appendChild(table);
    }
  });
});

// 2. 给超宽表格加滚动条
window.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('table').forEach(function(table) {
    if (table.offsetWidth > table.parentElement.offsetWidth) {
      const wrapper = document.createElement('div');
      wrapper.className = 'table-wrapper';
      table.parentNode.insertBefore(wrapper, table);
      wrapper.appendChild(table);
    }
  });
  
  // 3. 给超宽图片加滚动条
  document.querySelectorAll('img').forEach(function(img) {
    img.addEventListener('load', function() {
      if (img.naturalWidth > img.parentElement.offsetWidth) {
        const wrapper = document.createElement('div');
        wrapper.className = 'image-wrapper';
        img.parentNode.insertBefore(wrapper, img);
        wrapper.appendChild(img);
      }
    });
  });
});