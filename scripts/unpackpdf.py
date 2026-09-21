import base64
import argparse
import shutil
import math
from io import BytesIO
from pathlib import Path
import pymupdf as fitz
from PIL import Image, ImageChops

def list_glyph_masks(page):
    """列出已绘制的图像蒙版候选（同一 xref 的多次放置分别返回）。

    返回字典列表：image_xref、mask_xref、kind、width、height、transform。
    候选仅按 PDF 结构识别，不保证是文字；可据此选择 extract_glyph_mask
    的 xrefs。支持图像 /Mask、/SMask 和独立 /ImageMask。
    不包含颜色键 Mask 数组、内联图像和图形状态中的软蒙版。
    """
    doc = page.parent
    candidates = []
    for info in page.get_image_info(xrefs=True):
        xref = info.get("xref", 0)
        if not xref:
            continue
        mask_xref = None
        kind = None
        if doc.xref_get_key(xref, "ImageMask") == ("bool", "true"):
            mask_xref, kind = xref, "ImageMask"
        else:
            for key in ("SMask", "Mask"):
                value_type, value = doc.xref_get_key(xref, key)
                if value_type == "xref":
                    mask_xref, kind = int(value.split()[0]), key
                    break
        if mask_xref is not None:
            candidates.append(dict(image_xref=xref, mask_xref=mask_xref,
                                   kind=kind, width=info["width"],
                                   height=info["height"], transform=info["transform"]))
    return candidates


def _selected_glyph_masks(page, xrefs):
    candidates = list_glyph_masks(page)
    if xrefs is not None:
        wanted = set(xrefs)
        missing = wanted - {item["image_xref"] for item in candidates}
        if missing:
            raise ValueError(f"页面没有这些前景蒙版 xref: {sorted(missing)}")
        candidates = [item for item in candidates if item["image_xref"] in wanted]
    if not candidates:
        raise ValueError(f"物理页 {page.number + 1}: 没有可提取的图像蒙版")

    return candidates


def _mask_coverage(page, item, max_pixels):
    doc = page.parent
    xref = item["mask_xref"]
    _, bpc = doc.xref_get_key(xref, "BitsPerComponent")
    if bpc != "null" and int(bpc) > 8:
        raise ValueError(f"蒙版 {xref} 超过 8 位，当前解码器不能保证原精度，拒绝降位输出")
    width = int(doc.xref_get_key(xref, "Width")[1])
    height = int(doc.xref_get_key(xref, "Height")[1])
    if width * height > max_pixels:
        raise ValueError(f"蒙版 {width}x{height} 超过 max_pixels={max_pixels}")
    pix = fitz.Pixmap(doc, xref)
    if pix.n != 1:
        raise ValueError(f"蒙版 {xref} 不是单通道图像")
    return Image.frombytes("L", (pix.width, pix.height), pix.samples)


def _validate_mask_options(threshold, max_pixels):
    if threshold is not None and (isinstance(threshold, bool)
            or not isinstance(threshold, int) or not 1 <= threshold <= 255):
        raise ValueError("threshold 必须是 None 或 1..255 的整数")
    if isinstance(max_pixels, bool) or not isinstance(max_pixels, int) or max_pixels <= 0:
        raise ValueError("max_pixels 必须是正整数")


def _coverage_to_ink(coverage, threshold):
    if threshold is not None:
        return coverage.point(lambda v: 0 if v >= threshold else 255, mode="1")
    # 覆盖率转为白底黑字的亮度，是可逆映射，不丢弃灰阶。
    ink = ImageChops.invert(coverage)
    histogram = ink.histogram()
    if not any(histogram[1:255]):
        return ink.convert("1", dither=Image.Dither.NONE)
    return ink


def extract_glyph_masks(page, *, xrefs=None, threshold=None,
                        max_pixels=100_000_000):
    """每个独立蒙版分别原像素直出，返回 Pillow 图像列表。

    默认保留蒙版本身的宽高和解码灰阶：不拼接、不旋转、不裁切、不缩放。
    同一蒙版的重复放置只导出一次，顺序与 list_glyph_masks 去重后相同。
    输出白底黑字（亮度 = 255 - 覆盖率，可逆）；二值数据无损存成 1 位，
    灰阶存成 L。仅显式 threshold 才二值化。原 PDF 压缩字节不保留。
    """
    _validate_mask_options(threshold, max_pixels)
    images = []
    seen = set()
    for item in _selected_glyph_masks(page, xrefs):
        if item["mask_xref"] not in seen:
            images.append(_coverage_to_ink(_mask_coverage(page, item, max_pixels), threshold))
            seen.add(item["mask_xref"])
    return images


def extract_glyph_mask(page, *, xrefs=None, threshold=None, dpi=None,
                       max_pixels=100_000_000, compose=False):
    """默认单蒙版原像素直出；多蒙版请用 extract_glyph_masks 分别导出。

    仅 compose=True 才按页面布局拼接（可能重采样），dpi 仅该模式有效。
    默认 threshold=None 保留灰阶；显式传入整数才二值化。
    """
    if compose:
        return compose_glyph_masks(page, xrefs=xrefs, threshold=threshold,
                                   dpi=dpi, max_pixels=max_pixels)
    if dpi is not None:
        raise ValueError("原像素直出不接受 dpi；页面拼接请显式指定 compose=True")
    images = extract_glyph_masks(page, xrefs=xrefs, threshold=threshold, max_pixels=max_pixels)
    if len(images) != 1:
        raise ValueError("本页有多个蒙版，请用 extract_glyph_masks 分别原像素导出，或显式 compose=True")
    return images[0]


def compose_glyph_masks(page, *, xrefs=None, threshold=None, dpi=None,
                        max_pixels=100_000_000):
    """显式按页面布局拼接蒙版（最近邻重采样），默认仍保留灰阶。

    支持多个局部蒙版、重复放置、旋转、镜像、斜切和页面 CropBox。
    重叠取覆盖率最大值；不重现绘制遮挡、任意路径裁剪、透明组、混合模式。
    dpi=None 使用最高原生像素密度，但布局变换仍可能改变像素。
    """
    _validate_mask_options(threshold, max_pixels)
    if dpi is not None and (not math.isfinite(dpi) or dpi <= 0):
        raise ValueError("dpi 必须是有限正数或 None")
    candidates = _selected_glyph_masks(page, xrefs)

    layers = []
    scale_x = scale_y = 0.0
    for item in candidates:
        coverage = _mask_coverage(page, item, max_pixels)
        transform = (fitz.Matrix(1 / coverage.width, 1 / coverage.height)
                     * fitz.Matrix(item["transform"]) * page.rotation_matrix)
        inverse = fitz.Matrix(transform)
        if inverse.invert():
            raise ValueError(f"图像 {item['image_xref']} 的放置矩阵不可逆")
        # 逆矩阵两列给出页面 X/Y 每点对应的源像素数。
        scale_x = max(scale_x, math.hypot(inverse.a, inverse.b))
        scale_y = max(scale_y, math.hypot(inverse.c, inverse.d))
        layers.append((coverage, transform))
    if dpi is not None:
        scale_x = scale_y = dpi / 72
    width = max(1, math.ceil(page.rect.width * scale_x - 1e-3))
    height = max(1, math.ceil(page.rect.height * scale_y - 1e-3))
    if width * height > max_pixels:
        raise ValueError(f"蒙版画布 {width}x{height} 超过 max_pixels={max_pixels}，请降低 dpi")
    canvas = Image.new("L", (width, height), 0)
    for coverage, transform in layers:
        matrix = transform * fitz.Matrix(scale_x, scale_y)
        inverse = fitz.Matrix(matrix)
        if inverse.invert():
            raise ValueError("输出变换矩阵不可逆")
        placed = coverage.transform(canvas.size, Image.Transform.AFFINE,
                                    (inverse.a, inverse.c, inverse.e,
                                     inverse.b, inverse.d, inverse.f),
                                    resample=Image.Resampling.NEAREST, fillcolor=0)
        canvas = ImageChops.lighter(canvas, placed)
    return _coverage_to_ink(canvas, threshold)


class ImageCache:
    """
    管理 PDF 页面的 PNG 缓存
    自动读取 PDF 内嵌页码标签（与阅读器显示一致）
    缓存文件名基于物理页码（连续数字），但可通过标签字符串访问图片
    """
    
    def __init__(self, pdf_path, cache_dir, dpi=300, auto_preprocess=True,
                 invert=False, original_image=True, max_edge=None,
                 trim_white=False, ink_only=False, ink_threshold=None, ink_xrefs=None,
                 ink_compose=False):
        """
        参数:
            pdf_path: PDF 文件路径
            cache_dir: 缓存目录路径
            dpi: 渲染分辨率
            auto_preprocess: 是否在初始化时自动预处理所有页面
            invert: 是否输出反色图片，默认关闭
            original_image: 是否将每页的主内嵌原图按原始像素尺寸保存为 PNG，
                            默认开启（不使用 DPI 改写原图）
            max_edge: 原图模式下允许的最大边长，默认 None（不缩放）。仅当显式指定且原图
                      长边超过此值时才等比缩小；设为 None 时原图直出
            trim_white: 是否在缩放前安全裁掉部分白边，默认关闭。启用后每侧
                        最多裁掉原尺寸的 10%，正文外保留至少 2% 页边
            ink_only: 分别提取前景蒙版，保留原像素宽高及灰阶，输出 PNG。
                      不保留背景中的照片、颜色；不支持的页报错，不静默丢内容。
            ink_threshold: 默认 None 保留灰阶；显式指定 1..255 才二值化。
            ink_compose: 默认 False；True 显式启用页面拼接（可能重采样）。
            ink_xrefs: 可选前景图像 xref 集合；通常仅用于按页调用，
                       整卷各页 xref 往往不同。None 提取所有候选。
        """
        if max_edge is not None and (isinstance(max_edge, bool) or
                                     not isinstance(max_edge, int) or max_edge <= 0):
            raise ValueError("max_edge 必须是正整数或 None")
        self.pdf_path = Path(pdf_path)
        self.cache_dir = Path(cache_dir)
        self.dpi = dpi
        self.invert = invert
        self.original_image = original_image
        self.max_edge = max_edge
        self.trim_white = trim_white
        self.ink_only = ink_only
        self.ink_threshold = ink_threshold
        self.ink_xrefs = ink_xrefs
        self.ink_compose = ink_compose
        _validate_mask_options(ink_threshold, 100_000_000)
        if ink_only and not original_image:
            raise ValueError("ink_only 不能与 original_image=False 同时使用")
        
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
        
        # 构建映射表并生成缓存
        for pdf_idx in range(total_pdf_pages):
            phys_page = pdf_idx + 1          # 物理页码（从1开始）
            page = doc[pdf_idx]
            
            # 获取页面标签（与 PDF 阅读器显示一致）
            label = page.get_label()
            if not label:                     # 若未定义标签，则使用物理页码字符串
                label = str(phys_page)
            if '*' in label or '/' in label  or '\\' in label:  # 标签中不允许包含特殊字符，替换为下划线
                label = str(phys_page) + '_' + label.replace('*', '_').replace('/', '_').replace('\\', '_')+'img'
            
            # 存储映射（标签 → 物理页码 / 物理页码 → 标签）
            self._label_to_phys[label] = phys_page
            self._phys_to_label[phys_page] = label
            
            # 生成图片缓存（文件名基于物理页码）
            img_path = self._label_filename(label,phys_page)
            if self.ink_only or not img_path.exists():
                self._save_page_image(page, img_path)
                print(f"  [OK] 物理页 {phys_page:3d} -> {img_path.name}  (标签: '{label}')")
            #else:
            #   print(f"  ✓ {img_path.name} 已存在 (标签: '{label}')")
        
        doc.close()
        
        min_p, max_p = self.get_phys_page_range()
        print(f"\n[OK] 预处理完成！物理页码范围：{min_p} - {max_p}")
        #print(f"   标签列表：{list(self._label_to_phys.keys())}\n")

    def _save_page_image(self, page, path):
        """渲染页面并保存图片，必要时反色。"""
        if self.ink_only:
            images = ([compose_glyph_masks(page, threshold=self.ink_threshold, xrefs=self.ink_xrefs)]
                      if self.ink_compose else
                      extract_glyph_masks(page, threshold=self.ink_threshold, xrefs=self.ink_xrefs))
            paths = []
            for index, image in enumerate(images):
                if self.trim_white:
                    image = self._trim_white_border(image)
                if self.max_edge is not None and max(image.size) > self.max_edge:
                    image = image.convert("L")
                    image.thumbnail((self.max_edge, self.max_edge), Image.Resampling.LANCZOS)
                if self.invert:
                    was_binary = image.mode == "1"
                    image = ImageChops.invert(image.convert("L"))
                    if was_binary:
                        image = image.convert("1", dither=Image.Dither.NONE)
                target = Path(path) if index == 0 else Path(path).with_name(
                    f"{Path(path).stem}__mask_{index + 1:03d}.png")
                data = self._encode_png(image)
                # 重新核验墨迹缓存，避免沿用旧版 2048 像素或已二值化的结果。
                if not target.exists() or target.read_bytes() != data:
                    target.write_bytes(data)
                paths.append(target)
            return paths
        pix = self._get_original_image(page) if self.original_image else None
        if pix is None:
            pix = page.get_pixmap(dpi=self.dpi)
            if self.invert:
                pix.invert_irect()
            pix.save(str(path))
            return

        if self.invert:
            pix.invert_irect()
        Path(path).write_bytes(self._original_png_bytes(pix))

    @staticmethod
    def _get_ink_image(page):
        """兼容旧调用；公共入口见 extract_glyph_mask。"""
        return extract_glyph_mask(page)

    def _original_png_bytes(self, pix):
        """
        将原图输出为 PNG；可先裁白边，再按最大边长等比缩小。

        trim_white 与 max_edge 独立：前者只裁边，后者只缩放；同时启用时
        固定按“先裁边、后缩放”处理。输出 PNG 不得大于未处理原图 PNG。
        """
        original_png = pix.tobytes("png")
        if not self.trim_white and (self.max_edge is None or
                                    max(pix.width, pix.height) <= self.max_edge):
            return original_png

        with Image.open(BytesIO(original_png)) as source:
            image = source.copy()
        source_colors = image.getcolors(maxcolors=3)
        source_is_binary = source_colors is not None and len(source_colors) <= 2

        if self.trim_white:
            image = self._trim_white_border(image)

        resized = False
        if self.max_edge is not None and max(image.size) > self.max_edge:
            scale = self.max_edge / max(image.size)
            width = max(1, round(image.width * scale))
            height = max(1, round(image.height * scale))
            if image.width >= image.height:
                width = self.max_edge
            else:
                height = self.max_edge
            image = image.resize((width, height), Image.Resampling.LANCZOS)
            resized = True

        if source_is_binary and resized:
            # 1-bit 扫描图经插值会产生灰阶，既显得发虚也会让 PNG 变大。
            image = image.convert("L").point(lambda value: 255 if value >= 192 else 0, mode="1")

        candidate = self._encode_png(image)
        if len(candidate) <= len(original_png):
            return candidate

        for colors in (256, 128, 64, 32, 16, 8, 4, 2):
            candidate = self._encode_png(image.quantize(colors=colors))
            if len(candidate) <= len(original_png):
                return candidate
        raise RuntimeError("无法在保持目标尺寸和 PNG 格式的同时满足文件体积约束")

    @staticmethod
    def _encode_png(image):
        output = BytesIO()
        image.save(output, format="PNG", optimize=True, compress_level=9)
        return output.getvalue()

    @staticmethod
    def _trim_white_border(image, white_threshold=245,
                           max_trim_ratio=0.10, keep_margin_ratio=0.02):
        """忽略边缘噪点，有限裁掉白边，并保留正文、页眉和页码周围余量。"""
        gray = image.convert("L")
        histogram = gray.histogram()
        paper_target = image.width * image.height * 0.85
        cumulative = 0
        paper_luma = 255
        for level, count in enumerate(histogram):
            cumulative += count
            if cumulative >= paper_target:
                paper_luma = level
                break
        if paper_luma < 180:
            return image
        dark_threshold = min(white_threshold, paper_luma - 30)
        dark = gray.point(lambda value: 255 if value < dark_threshold else 0)

        columns = dark.resize((image.width, 1), Image.Resampling.BOX)
        columns = columns.point(lambda value: 255 if value >= 5 else 0)
        column_box = columns.getbbox()
        if column_box is None:
            return image

        content_left, content_right = column_box[0], column_box[2]
        keep_x = round(image.width * keep_margin_ratio)
        # 上下边界不能在整张图上直接做行投影：左右页边的装订阴影、散点
        # 或扫描黑边可能贯穿大量行，使顶部和底部永远被误判为正文。先用
        # 较稳健的列投影找出正文横向范围，再略微向两侧扩展，以保留页眉、
        # 页码等比正文稍宽的内容。
        row_left = max(0, content_left - keep_x)
        row_right = min(image.width, content_right + keep_x)
        row_source = dark.crop((row_left, 0, row_right, image.height))
        rows = row_source.resize((1, image.height), Image.Resampling.BOX)
        rows = rows.point(lambda value: 255 if value >= 1 else 0)
        row_box = rows.getbbox()
        if row_box is None:
            return image

        content_top, content_bottom = row_box[1], row_box[3]
        keep_y = round(image.height * keep_margin_ratio)
        max_trim_x = round(image.width * max_trim_ratio)
        max_trim_y = round(image.height * max_trim_ratio)
        left = min(max_trim_x, max(0, content_left - keep_x))
        top = min(max_trim_y, max(0, content_top - keep_y))
        right = max(image.width - max_trim_x,
                    min(image.width, content_right + keep_x))
        bottom = max(image.height - max_trim_y,
                     min(image.height, content_bottom + keep_y))
        if (left, top, right, bottom) == (0, 0, image.width, image.height):
            return image
        return image.crop((left, top, right, bottom))

    @staticmethod
    def _get_original_image(page):
        """
        按页面内嵌图的原生像素密度输出 PNG，不使用预设 PPI。

        - 单张、无蒙版的图像：直接解码原始像素矩阵并转为 PNG。
        - MRC 分层或带蒙版的页面：以主图的原生像素密度合成整页，
          保留背景层、前景层和软蒙版，不限制 PPI。
        - 无内嵌图或只有小面积复合装饰：返回 None，由调用方回退渲染。
        """
        images = [
            image for image in page.get_image_info(xrefs=True)
            if image.get("xref", 0) > 0
        ]
        if not images:
            return None

        main_image = max(images, key=lambda image: image["width"] * image["height"])
        if len(images) == 1 and not main_image.get("has-mask"):
            pix = fitz.Pixmap(page.parent, main_image["xref"])
            if pix.colorspace and pix.colorspace.n > 3:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            return pix

        image_rect = fitz.Rect(main_image["bbox"])
        visible_rect = image_rect & page.rect
        page_area = page.rect.get_area()
        coverage = visible_rect.get_area() / page_area if page_area else 0
        if coverage < 0.35:
            return None

        a, b, c, d, _, _ = main_image["transform"]
        displayed_width = (a * a + b * b) ** 0.5
        displayed_height = (c * c + d * d) ** 0.5
        if displayed_width <= 0 or displayed_height <= 0:
            return None

        scale_x = main_image["width"] / displayed_width
        scale_y = main_image["height"] / displayed_height
        if abs(b) > 1e-6 or abs(c) > 1e-6:
            # 旋转/斜切图层无法直接对应页面的 X/Y 轴；用较高倍率避免降采样。
            scale_x = scale_y = max(scale_x, scale_y)
        return page.get_pixmap(matrix=fitz.Matrix(scale_x, scale_y), alpha=False)

    def _label_filename(self, label,phys_page=None):
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
        """获取单张图片；多蒙版页请用 get_image_paths 分别读取。"""
        return base64.b64encode(self.get_image_path(phys_page).read_bytes()).decode()

    def get_image_paths(self, phys_page):
        """返回本页全部缓存路径；墨迹默认每个独立蒙版一张原像素 PNG。"""
        path = self._label_filename(phys_page)
        if self.ink_only or not path.exists():
            with fitz.open(str(self.pdf_path)) as doc:
                if not 1 <= phys_page <= len(doc):
                    raise ValueError(f"物理页码 {phys_page} 超出范围")
                path.parent.mkdir(parents=True, exist_ok=True)
                paths = self._save_page_image(doc[phys_page - 1], path)
                if self.ink_only:
                    return paths
        return [path]

    def get_image_path(self, phys_page):
        """获取单张图片路径；多蒙版时明确要求使用复数接口，避免漏图。"""
        paths = self.get_image_paths(phys_page)
        if len(paths) != 1:
            raise ValueError("本页输出多个原像素蒙版，请用 get_image_paths 获取全部路径")
        return paths[0]

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
        print("[OK] 缓存已清空，映射已重置")


def _parse_max_edge(value):
    if value.strip().casefold() == "none":
        return None
    try:
        edge = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer or 'none'") from exc
    if edge <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer or 'none'")
    return edge


def parse_args():
    parser = argparse.ArgumentParser(description="Automatically extract PDF pages into an image cache.")
    parser.add_argument("--pdf", type=str, help="Source PDF file.")
    parser.add_argument("--cache_dir", type=str, help="Destination image-cache directory.")
    parser.add_argument("--dpi", type=int, default=225, help="Fallback render DPI (default: 225).")
    parser.add_argument("--rendered", action="store_true", help="Use DPI rendering instead of original-image extraction.")
    parser.add_argument("--invert", action="store_true", help="Invert output images.")
    parser.add_argument("--ink-only", action=argparse.BooleanOptionalAction, default=True, help="Extract each mask at native dimensions, preserving gray levels (default: enabled).")
    parser.add_argument("--ink-threshold", type=int, default=None, choices=range(1, 256), metavar="1..255", help="Explicitly binarize mask coverage; default preserves gray levels.")
    parser.add_argument("--ink-compose", action="store_true", help="Explicitly assemble masks into a page; may resample pixels.")
    parser.add_argument("--ink-xrefs", type=int, nargs="+", help="Select foreground image xrefs; each selected xref must exist on the processed page.")
    parser.add_argument("--max-edge", type=_parse_max_edge, default=None, help="Explicit maximum edge; default 'none' preserves original dimensions.")
    parser.add_argument("--trim-white", action="store_true", help="Crop safe white borders before optional --max-edge scaling.")
    parser.add_argument("--clear-cache", action="store_true", help="Delete the specified cache directory before extraction.")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.dpi <= 0:
        raise SystemExit("--dpi must be a positive integer")
    dpi=args.dpi if args.dpi else None
    pdf_input = None
    pdf_input = Path(r"pdfstylecatcher/mew_band25.pdf")
    #pdf_input = Path("./马恩全集德文/mew_band29.pdf")
    pdf_path = Path(args.pdf) if args.pdf else pdf_input
    cache=Path("cache_images251")
    cache_dir = Path(args.cache_dir) if args.cache_dir else cache
    if not pdf_path.is_file():
        raise SystemExit(f"PDF 文件不存在：{pdf_path}")
    max_edge = args.max_edge
    #max_edge=2048
    trim_white = args.trim_white
    ink_only = args.ink_only
    if ink_only and args.rendered:
        raise SystemExit("--ink-only cannot be combined with --rendered")
    if ink_only and not cache_dir:
        cache_dir = pdf_path.parent / (pdf_path.stem + "_ink")
    if args.clear_cache and cache_dir.exists():
        shutil.rmtree(cache_dir)
    ImageCache(
        pdf_path,
        cache_dir,
        dpi=dpi,
        auto_preprocess=True,
        invert=args.invert,
        original_image=not args.rendered,
        max_edge=max_edge,
        trim_white=trim_white,
        ink_only=ink_only,
        ink_threshold=args.ink_threshold,
        ink_xrefs=args.ink_xrefs,
        ink_compose=args.ink_compose,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
