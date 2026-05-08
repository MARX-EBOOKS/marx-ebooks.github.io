import base64
import shutil
from pathlib import Path
import fitz

class ImageCache:
    """
    管理 PDF 页面的 PNG 缓存
    自动读取 PDF 内嵌页码标签（与阅读器显示一致）
    缓存文件名基于物理页码（连续数字），但可通过标签字符串访问图片
    """
    
    def __init__(self, pdf_path, cache_dir, dpi=300, auto_preprocess=True):
        """
        参数:
            pdf_path: PDF 文件路径
            cache_dir: 缓存目录路径
            dpi: 渲染分辨率
            auto_preprocess: 是否在初始化时自动预处理所有页面
        """
        self.pdf_path = Path(pdf_path)
        self.cache_dir = Path(cache_dir)
        self.dpi = dpi
        
        # 页码映射：标签（字符串） → 物理页码（int）
        self._label_to_phys = {}
        # 物理页码 → 标签（字符串）
        self._phys_to_label = {}
        
        if auto_preprocess:
            self._auto_preprocess()
    
    def _auto_preprocess(self):
        """启动时读取 PDF 页码标签并生成缓存（所有页面均生成）"""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"\n{'='*60}")
        print(f"正在读取 PDF 页码标签...")
        print(f"PDF 路径：{self.pdf_path}")
        print(f"缓存目录：{self.cache_dir}")
        print(f"{'='*60}\n")
        
        doc = fitz.open(str(self.pdf_path))
        total_pdf_pages = len(doc)
        
        print(f"PDF 总页数：{total_pdf_pages}")
        print()
        
        # 构建映射表并生成缓存
        for pdf_idx in range(total_pdf_pages):
            phys_page = pdf_idx + 1          # 物理页码（从1开始）
            page = doc[pdf_idx]
            
            # 获取页面标签（与 PDF 阅读器显示一致）
            label = page.get_label()
            if not label:                     # 若未定义标签，则使用物理页码字符串
                label = str(phys_page)
            
            # 存储映射（标签 → 物理页码 / 物理页码 → 标签）
            self._label_to_phys[label] = phys_page
            self._phys_to_label[phys_page] = label
            
            # 生成图片缓存（文件名基于物理页码）
            img_path = self._label_filename(label)
            if not img_path.exists():
                pix = page.get_pixmap(dpi=self.dpi)
                pix.save(str(img_path))
                print(f"  ✓ 物理页 {phys_page:3d} → {img_path.name}  (标签: '{label}')")
            #else:
            #   print(f"  ✓ {img_path.name} 已存在 (标签: '{label}')")
        
        doc.close()
        
        min_p, max_p = self.get_phys_page_range()
        print(f"\n✅ 预处理完成！物理页码范围：{min_p} - {max_p}")
        #print(f"   标签列表：{list(self._label_to_phys.keys())}\n")
    def _label_filename(self, label):
        """根据物理页码生成缓存文件路径"""
        try:
            num = int(label)
            return self.cache_dir / f"page_{num:04d}.png"
        except ValueError:
            return self.cache_dir / f"page_{label}.png"
    def _phys_filename(self, phys_page):
        """根据物理页码生成缓存文件路径"""
        return self.cache_dir / f"page_{phys_page:04d}.png"
    
    # ---------- 物理页码相关方法 ----------
    def page_exists(self, phys_page):
        """检查物理页码对应的缓存图片是否存在"""
        return self._label_filename(phys_page).is_file()
    
    def get_image_b64(self, phys_page):
        """根据物理页码获取图片 base64（若缓存不存在则实时生成）"""
        path = self._label_filename(phys_page)
        if not path.exists():
            # 缓存缺失，从 PDF 实时生成
            pdf_page = phys_page - 1  # 转换为 0-based 索引
            doc = fitz.open(str(self.pdf_path))
            if 0 <= pdf_page < len(doc):
                page = doc[pdf_page]
                pix = page.get_pixmap(dpi=self.dpi)
                path.parent.mkdir(parents=True, exist_ok=True)
                pix.save(str(path))
                doc.close()
            else:
                doc.close()
                raise ValueError(f"物理页码 {phys_page} 超出范围")
        
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    
    def get_image_path(self, phys_page):
        """根据物理页码获取图片路径（若缓存不存在则实时生成）"""
        path = self._label_filename(phys_page)
        if not path.exists():
            pdf_page = phys_page - 1
            doc = fitz.open(str(self.pdf_path))
            if 0 <= pdf_page < len(doc):
                page = doc[pdf_page]
                pix = page.get_pixmap(dpi=self.dpi)
                path.parent.mkdir(parents=True, exist_ok=True)
                pix.save(str(path))
                doc.close()
            else:
                doc.close()
                raise ValueError(f"物理页码 {phys_page} 超出范围")
        return path
    
    def get_label_by_phys_page(self, phys_page):
        """物理页码 → 标签字符串"""
        return self._phys_to_label.get(phys_page)
    
    def get_phys_page_range(self):
        """获取物理页码范围"""
        if not self._phys_to_label:
            return (0, 0)
        return (min(self._phys_to_label.keys()), max(self._phys_to_label.keys()))
    
    def get_all_phys_pages(self):
        """获取所有物理页码列表"""
        return sorted(self._phys_to_label.keys())
    
    # ---------- 标签相关方法 ----------
    def get_phys_page_by_label(self, label):
        """标签字符串 → 物理页码"""
        return self._label_to_phys.get(label)
    
    def get_image_b64_by_label(self, label):
        """根据标签获取图片 base64"""
        phys_page = self.get_phys_page_by_label(label)
        if phys_page is None:
            raise KeyError(f"标签 '{label}' 不存在")
        return self.get_image_b64(phys_page)
    
    def get_image_path_by_label(self, label):
        """根据标签获取图片路径"""
        phys_page = self.get_phys_page_by_label(label)
        if phys_page is None:
            raise KeyError(f"标签 '{label}' 不存在")
        return self.get_image_path(phys_page)
    
    def get_all_labels(self):
        """获取所有标签列表（按物理页码排序）"""
        return sorted(self._label_to_phys.keys(), key=lambda x: self._label_to_phys[x])
    
    # ---------- 缓存管理 ----------
    def clear_cache(self):
        """清空缓存目录并重置映射"""
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._label_to_phys.clear()
        self._phys_to_label.clear()
        print("✅ 缓存已清空，映射已重置")


# ==================== 独立运行入口 ====================
if __name__ == "__main__":
    import sys
    
    pdf_path = r"D:\马恩列总装\马恩全集德文\mew_band21.pdf"
    cache_dir = "./cache_images21"
    dpi = 150
    
    if not Path(pdf_path).exists():
        print(f"❌ 文件不存在：{pdf_path}")
        sys.exit(1)
    
    # 询问是否清空已有缓存
    if Path(cache_dir).exists() and any(Path(cache_dir).iterdir()):
        resp = input("⚠️  缓存目录已有图片，是否删除？(y/N): ").strip().lower()
        if resp == 'y':
            shutil.rmtree(cache_dir)
            print("缓存已清空")
    
    image_cache = ImageCache(pdf_path, cache_dir, dpi, auto_preprocess=True)
    
    print("\n" + "="*60)
    print("✅ ImageCache 独立运行完成")
    print("="*60)
    
    # 示例：获取所有标签并显示
    print("\n所有页码标签：")
    for label in image_cache.get_all_labels():
        phys = image_cache.get_phys_page_by_label(label)
        print(f"  标签 '{label}' → 物理页 {phys}")