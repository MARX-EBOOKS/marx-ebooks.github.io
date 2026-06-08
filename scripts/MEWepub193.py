import os
import re
import uuid
from datetime import datetime
from pathlib import Path
import shutil
from html.parser import HTMLParser
from urllib.parse import urlparse, urljoin
import base64
from bs4 import BeautifulSoup
import zipfile
import csv
import openpyxl
import textrepo
class TitleExtractor(HTMLParser):
    """HTML标题提取器"""
    def __init__(self):
        super().__init__()
        self.title = ""
        self.in_title = False
        self.all_headings = [] 
    
    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'title':
            self.in_title = True
    
    def handle_endtag(self, tag):
        if tag.lower() == 'title':
            self.in_title = False
    
    def handle_data(self, data):
        if self.in_title:
            data=re.sub(r'\[\d+?\]','',data)
            data=re.sub(r'\[注：[\s\S]+?\]','',data)
            self.title += data

class HeadingExtractor:
    """HTML标题层级提取器 (h1-h6)，使用BeautifulSoup"""
    def __init__(self):
        self.headings = []
    
    def extract_headings_from_html(self, html_content, source_file, chapter_number,volume_number):
        """从HTML内容中提取所有标题层级并添加ID"""
        try:
            #soup = BeautifulSoup(html_content, 'html.parser')
            soup = BeautifulSoup(html_content, 'xml')
            headings_data = []
            
            # 查找所有标题标签
            heading_tags = soup.find_all(['h2', 'h3', 'h4', 'h5', 'h6'])
            
            for i, tag in enumerate(heading_tags):
                if 'style' in tag.attrs:
                    del tag['style']
                if 'align' in tag.attrs:
                    del tag['align']
                text = tag.get_text(separator='  ',strip=True)
                if text and len(text) > 0:
                    # 为标题添加锚点ID
                    anchor_id=tag.get('id')

                    if not anchor_id:
                        anchor_id =  f"ME{volume_number:02d}{chapter_number:03d}-{i+1}"
                        tag['id']=anchor_id
                    text=text.replace("<","&lt;")
                    text=text.replace(">","&gt;")
                    text=re.sub(r'￥￥￥[\S ]+?￥￥￥',r'',text,flags=re.DOTALL|re.IGNORECASE)
                    level = int(tag.name[1])  # h1->1, h2->2, etc.
                    headings_data.append({
                        'tag': tag.name,
                        'text': text,
                        'level': level,
                        'id': anchor_id,
                        'source_file': source_file,
                        'chapter_number': chapter_number

                    })
            
            # 返回修改后的HTML和提取的标题数据
            return str(soup), headings_data
            
        except Exception as e:
            print(f"  警告: 解析标题时出错: {e}")
            return html_content, []

class LinkExtractor(HTMLParser):
    """HTML链接提取器"""
    def __init__(self):
        super().__init__()
        self.links = []
        self.current_link = None
        self.in_link = False
        self.link_text = ""
    
    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'a':
            for name, value in attrs:
                if name.lower() == 'href':
                    self.current_link = value
                    self.in_link = True
                    self.link_text = ""
                    break
    
    def handle_endtag(self, tag):
        if tag.lower() == 'a' and self.in_link:
            if self.current_link and self.link_text.strip():
                # 只收集.html链接
                if self.current_link.lower().endswith('.html') or self.current_link.lower().endswith('.htm'):
                    self.links.append({
                        'href': self.current_link,
                        'text': self.link_text.strip()
                    })
            self.in_link = False
            self.current_link = None
            self.link_text = ""
    
    def handle_data(self, data):
        if self.in_link:
            self.link_text += data

class ImageExtractor(HTMLParser):
    """HTML图片提取器"""
    def __init__(self):
        super().__init__()
        self.images = []
    
    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'img':
            src = None
            for name, value in attrs:
                if name.lower() == 'src':
                    src = value
                    break
            if src:
                self.images.append(src)

def extract_title_from_html(html_content):
    """从HTML内容中提取title标签内容"""
    extractor = TitleExtractor()
    try:
        extractor.feed(html_content)
        return extractor.title.strip() if extractor.title.strip() else None
    except:
        return None

def extract_links_from_html(html_content):
    """从HTML内容中提取所有链接"""
    extractor = LinkExtractor()
    try:
        extractor.feed(html_content)
        return extractor.links
    except Exception as e:
        print(f"  警告: 解析链接时出错: {e}")
        return []

def extract_images_from_html(html_content):
    """从HTML内容中提取所有图片链接"""
    extractor = ImageExtractor()
    try:
        extractor.feed(html_content)
        return extractor.images
    except Exception as e:
        print(f"  警告: 解析图片时出错: {e}")
        return []

def natural_sort_key(text):
    """自然排序键，正确处理数字"""
    def convert(text):
        return int(text) if text.isdigit() else text.lower()
    return [convert(c) for c in re.split('([0-9]+)', str(text))]

def fix_html_links(html_content, link_map):
    """修复HTML中的链接路径"""
    # 替换所有的href链接
    for old_href, new_href in link_map.items():
        # 匹配href="old_link"的模式
        pattern = rf'href=["\']({re.escape(old_href)})["\']'
        replacement = f'href="{new_href}"'
        html_content = re.sub(pattern, replacement, html_content, flags=re.IGNORECASE)
    
    return html_content

def fix_image_paths(html_content, image_map):
    """修复HTML中的图片路径"""
    for old_src, new_src in image_map.items():
        # 匹配src="old_path"的模式
        pattern = rf'src=["\']({re.escape(old_src)})["\']'
        replacement = f'src="{new_src}"'
        html_content = re.sub(pattern, replacement, html_content, flags=re.IGNORECASE)
    
    return html_content

def get_image_type(file_path):
    """根据文件扩展名获取图片MIME类型"""
    ext = file_path.lower().split('.')[-1]
    mime_types = {
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'gif': 'image/gif',
        'bmp': 'image/bmp',
        'webp': 'image/webp',
        'svg': 'image/svg+xml'
    }
    return mime_types.get(ext, 'image/jpeg')

class BookVolume:
    """书卷类"""
    def __init__(self, path, volume_name):
        self.path = Path(path)
        self.volume_name = volume_name
        self.volume_number = self.extract_volume_number(volume_name)
        self.index_content = ""
        self.chapters = []
        self.images = []
        self.has_index = False
        self.chapter_link_map = {}  # 用于存储链接映射关系
        self.image_map = {}  # 用于存储图片映射关系
        self.all_headings = []  # 存储所有标题信息
        self.heading_extractor = textrepo.HeadingExtractor(self.volume_number,"ME")  # 标题提取器
    
    def extract_volume_number(self, volume_name):
        """从卷名中提取数字"""
        match = re.search(r'第(\d+)卷', volume_name)
        return int(match.group(1)) if match else 0
    
    def load_volume_index(self):
        """加载卷的总目录（index.html）"""
        index_path = self.path / f"MEW{self.volume_number}.html"
        if index_path.exists():
            try:
                with open(index_path, 'r', encoding='utf-8-sig') as f:
                    self.index_content = f.read()
                self.has_index = True
                #print(f"  加载卷目录: {self.volume_name}/index.html")
                # 从目录页提取图片
                self.collect_images_from_content(self.index_content, "index.html")
                
            except Exception as e:
                print(f"  警告: 无法读取 {index_path}: {e}")
        else:
            print(f"  注意: {self.volume_name} 没有找到 index.html")
    
    def collect_images_from_content(self, html_content, source_file):
        """从HTML内容中收集图片"""
        images = extract_images_from_html(html_content)
        for img_src in images:
            if not img_src.startswith(('http://', 'https://', 'data:')):
                # 相对路径图片
                img_path = self.path / img_src
                if img_path.exists():
                    img_id = f"MEW{self.volume_number:02d}-img{len(self.images) + 1:03d}"
                    img_ext = img_path.suffix.lower()
                    img_filename = f"{img_id}{img_ext}"
                    
                    self.images.append({
                        'original_path': img_path,
                        'filename': img_filename,
                        'id': img_id,
                        'source_file': source_file
                    })
                    
                    # 建立映射关系
                    self.image_map[img_src] = img_filename
                    #print(f"    收集图片: {img_src} -> {img_filename}")
    
    def scan_chapters(self):
        """通过解析目录页链接来扫描章节文件"""
        if not self.has_index:
            print(f"  {self.volume_name} 没有目录页，跳过")
            return
        
        # 从目录页提取所有链接
        links = extract_links_from_html(self.index_content)
        
        if not links:
            print(f"  {self.volume_name} 目录页中没有找到链接")
            return
        
        #print(f"  从目录页找到 {len(links)} 个链接:")
        chapter_number = 1
        for link in links:
            href = link['href']
            link_text = link['text']
            
            # 构建完整的文件路径
            article_path = self.path / href
            
            if not article_path.exists():
                
                print(f"{self.volume_number}-跳过: {href} (文件不存在)")
                continue
            
            try:
                # 读取文章内容
                with open(article_path, 'r', encoding='utf-8-sig') as f:
                    content = f.read()
                regex_pro=textrepo.textrep(self.volume_number,content,"MEW")
                content=regex_pro.regex_content()
                #content=content.replace("<br>&emsp;&emsp;<br>&emsp;&emsp;","<br>&emsp;&emsp;")
                #content=re.sub(r"<br>&emsp;&emsp;[\s]*</h1>",r"</h1>",content,flags=re.DOTALL|re.IGNORECASE)
                #content=re.sub(r'&emsp;',r'　', content, flags=re.DOTALL | re.IGNORECASE)
                #content=content.replace(" ","　")
                #content=content.replace('</p><p class="quote">','</p><p class="footnote">')
                #content=content.replace('</strong>','</b>')
                #content=content.replace('<strong>','<b>')
                #content=re.sub(r'<a name=',r'<a id=',content ,flags=re.DOTALL | re.IGNORECASE)
                #content=re.sub(r'．',r'.', content, flags=re.DOTALL | re.IGNORECASE)
                #content=self.regex_content(content)
                # 收集文章中的图片
                title = extract_title_from_html(content)            
                if not title or title == "":
                    title = link_text if link_text else f"第{chapter_number}章"
                self.collect_images_from_content(content, href)                
                # 提取标题并修改HTML（添加ID）
                modified_content, headings = self.heading_extractor.extract_headings_from_html(
                    content, href,chapter_number,title
                )
                # 存储标题信息
                self.all_headings.extend(headings)                
                #if headings:
                    #print(f"    第{chapter_number}章: 找到 {len(headings)} 个标题")                
                # 尝试从HTML的title标签提取标题，如果失败则使用链接文本
                
                chapter_filename = f"MEW{self.volume_number}-{chapter_number:03d}.html"
                title=title.replace("<","&lt;")
                title=title.replace(">","&gt;")
                self.chapters.append({
                    'number': chapter_number,
                    'title': title,
                    'content': modified_content,  # 使用修改后的内容（包含标题ID）
                    'filename': chapter_filename,
                    'original_file': href,
                    'link_text': link_text,
                    'headings': headings  # 存储本章的标题信息
                })
                # 建立链接映射关系
                self.chapter_link_map[href] = chapter_filename
                
                chapter_number += 1
                
            except Exception as e:
                print(f"    警告: 无法读取文章文件 {href}: {e}")
                continue
class EpubBookBuilder:
    """EPUB图书构建器"""
    def __init__(self, title, author=[], language="zh", cover_images=None,ws=[]):
        self.title = title
        self.author = author
        self.language = language
        self.uuid = str(uuid.uuid4())
        self.volumes = []
        self.all_images = []
        self.cover_images = cover_images if cover_images and isinstance(cover_images, list) else ([cover_images] if cover_images else [])
        self.has_cover = False
        self.cover_filenames = []
        self.global_css = textrepo.publiccss()
        self.ws=ws
    
    def prepare_cover_images(self):
        """准备多个封面图片"""
        cover_filenames = []
        
        if not self.cover_images:
            return cover_filenames
        for i, cover_path in enumerate(self.cover_images):
            if cover_path and Path(cover_path).exists():
                cover_file = Path(cover_path)
                cover_ext = cover_file.suffix.lower()
                cover_filename = f"cover_{i+1:02d}{cover_ext}"
                
                self.all_images.append({
                    'original_path': cover_file,
                    'filename': cover_filename,
                    'id': f'cover-image-{i+1:02d}'
                })
                cover_filenames.append(cover_filename)
                print(f"  添加封面图片 {i+1}: {cover_filename}")
            else:
                print(f"  警告: 封面图片 {i+1} 路径无效或文件不存在: {cover_path}")
        
        if cover_filenames:
            self.has_cover = True
            self.cover_filenames = cover_filenames
        
        return cover_filenames
    
    def scan_book_structure(self, book_dir):
        """扫描整本书的结构"""
        book_path = Path(book_dir)
        if not book_path.exists():
            print(f"错误: 书籍目录 '{book_dir}' 不存在")
            return
        
        #print(f"扫描书籍目录: {book_dir}")
        
        # 查找所有"第n卷"目录
        volume_dirs = []
        for item in book_path.iterdir():
            if item.is_dir() and re.match(r'第\d+卷', item.name):
                volume_dirs.append(item)
        
        if not volume_dirs:
            print("错误: 没有找到符合'第n卷'格式的目录")
            return
        
        # 按卷号排序
        volume_dirs.sort(key=lambda x: natural_sort_key(x.name))
        # 处理每一卷
        for vol_dir in volume_dirs:
            #print(f"\n处理卷: {vol_dir.name}")
            volume = BookVolume(vol_dir, vol_dir.name)
            volume.load_volume_index()
            volume.scan_chapters()
            
            if volume.chapters:
                i=volume.volume_number
                for row in self.ws.iter_rows(min_row=i, max_row=i, values_only=True):
                    volume_info=row[1]
                volume.volume_name=volume_info
                self.volumes.append(volume)
                self.all_images.extend(volume.images)
                #print(f"  完成: 找到 {len(volume.chapters)} 个章节, {len(volume.images)} 张图片")
            else:
                print(f"  警告: {vol_dir.name} 中没有找到有效章节")
    
    def create_mimetype(self):
        """创建mimetype文件"""
        return "application/epub+zip"
    
    def create_container_xml(self):
        """创建META-INF/container.xml"""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>'''
    
    def create_content_opf(self):
        """创建content.opf文件"""
        manifest_items = []
        spine_items = []
        language = self.language
        if isinstance(language, str) and language.lower() == "zh-cn":
            language = "zh-CN"
        
        # 添加导航文件


        
        # 添加封面相关文件
        if self.has_cover:
            # 添加所有封面图片
            for img in self.all_images:
                if img['id'].startswith('cover-image'):
                    img_type = get_image_type(img['filename'])
                    cover_prop = ' properties="cover-image"' if img['id'] == 'cover-image-01' else ''
                    manifest_items.append(f'    <item id="{img["id"]}" href="{img["filename"]}" media-type="{img_type}"{cover_prop}/>')
            
            # 添加封面页面
            manifest_items.append('    <item id="cover" href="cover.html" media-type="application/xhtml+xml"/>')
            spine_items.append('    <itemref idref="cover"/>')
        manifest_items.append('    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>')
        spine_items.append('    <itemref idref="nav"/>')
        # 添加总目录页面
        manifest_items.append('    <item id="tovol" href="tovol.html" media-type="application/xhtml+xml"/>')
        spine_items.append('    <itemref idref="tovol"/>')
        
        # 添加图片文件（非封面图片）
        for img in self.all_images:
            if not img['id'].startswith('cover-image'):  # 封面图片已经添加过了
                img_type = get_image_type(img['filename'])
                manifest_items.append(f'    <item id="{img["id"]}" href="{img["filename"]}" media-type="{img_type}"/>')
        
        # 添加卷目录和章节文件
        for volume in self.volumes:
            # 如果有卷目录，添加卷目录文件
            if volume.has_index:
                vol_index_id = f"MEW{volume.volume_number}"
                vol_index_filename = f"{vol_index_id}-index.html"
                manifest_items.append(f'    <item id="{vol_index_id}" href="{vol_index_filename}" media-type="application/xhtml+xml"/>')
                spine_items.append(f'<itemref idref="{vol_index_id}"/>')
            
            # 添加章节文件
            for chapter in volume.chapters:
                chapter_id = f"MEW{volume.volume_number}-{chapter['number']:03d}"
                chapter_filename = chapter['filename']
                manifest_items.append(f'    <item id="{chapter_id}" href="{chapter_filename}" media-type="application/xhtml+xml"/>')
                spine_items.append(f'<itemref idref="{chapter_id}"/>')
        
        # 构建metadata，如果有封面则添加封面元数据（使用第一张封面图片作为主封面）
        metadata_cover = ""
        if self.has_cover and self.cover_filenames:
            metadata_cover = f'    <meta name="cover" content="cover-image-01"/>'
        manifest_items.append('    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>')
        manifest_items.append('    <item id="global-css" href="styles.css" media-type="text/css"/>')
        dca = ""
        role_meta = ""
        for idx, author in enumerate(self.author, start=1):
            creator_id = f"creator-{idx}"
            author_text = author.strip() if isinstance(author, str) else str(author)
            dca += f'    <dc:creator id="{creator_id}">{author_text}</dc:creator>\n'
            role_meta += f'    <meta refines="#{creator_id}" property="role" scheme="marc:relators">aut</meta>\n'
        return f'''<?xml version="1.0" encoding="utf-8"?>
<package version="3.0" unique-identifier="BookId" xmlns="http://www.idpf.org/2007/opf">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <meta name="generator" content="MEWEPUB-PY"/>
    {metadata_cover}
    <dc:identifier id="BookId" opf:scheme="UUID">urn:uuid:{self.uuid}</dc:identifier>
    <dc:title>{self.title}</dc:title>
    <dc:language>{language}</dc:language>
    {dca}
    <dc:date opf:event="modification">{datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")}</dc:date>
  </metadata>
  <manifest>
{chr(10).join(manifest_items)}
  </manifest>
  <spine toc="ncx">
{chr(10).join(spine_items)}
  </spine>
</package>'''
    def create_toc_ncx(self):
        """创建toc.ncx导航文件 - 基于HTML标题结构并支持ID跳转"""
        nav_points = []
        play_order = 1

        # 添加封面导航点
        if self.has_cover:
            nav_points.append(f'''    <navPoint id="cover" playOrder="{play_order}">
      <navLabel>
        <text>马克思恩格斯全集封面</text>
      </navLabel>
      <content src="cover.html"/>
    </navPoint>''')
            play_order += 1

        # 添加总目录导航点
        nav_points.append(f'''<navPoint id="nav" playOrder="{play_order}">
      <navLabel>
        <text>总目录</text>
      </navLabel>
      <content src="nav.xhtml"/>
    </navPoint>''')
        play_order += 1
        nav_points.append(f'''<navPoint id="tovol" playOrder="{play_order}">
      <navLabel>
        <text>卷目</text>
      </navLabel>
      <content src="tovol.html"/>
    </navPoint>''')
        play_order += 1
        nav_points.append(f'''<navPoint id="00a" playOrder="{play_order}">
      <navLabel>
        <text>凡例</text>
      </navLabel>
      <content src="tovol.html#00a"/>
    </navPoint>''')
        play_order += 1

        for volume in self.volumes:
            i=volume.volume_number
            volumetext=f'第{i}卷'+volume.volume_name 
            if i==20:
                volumetext=f"第{i}卷（反杜林论、自然辩证法）"
            if i==23:
                volumetext=f"第{i}卷（资本论第一卷）"
            if i==24:
                volumetext=f"第{i}卷（资本论第二卷）"
            if i==25:
                volumetext=f"第{i}卷（资本论第三卷）"
            if i==26:
                volumetext=f"第{i}卷（剩余价值理论）"     
            vol_nav_point = f'''<navPoint id="MEW{volume.volume_number}" playOrder="{play_order}">
      <navLabel>
        <text>{volumetext}</text>
      </navLabel>'''
   
            if volume.has_index:
                vol_index_filename = f"MEW{volume.volume_number}-index.html"
                vol_nav_point += f'''
      <content src="{vol_index_filename}"/>'''
            elif volume.chapters:
                vol_nav_point += f'''
      <content src="{volume.chapters[0]["filename"]}"/>'''
            
            play_order += 1
            
            # 基于实际HTML结构创建导航，支持ID跳转
            chapter_nav_points = []
            for chapter in volume.chapters:
                chapter_nav_id = f"MEW{volume.volume_number}-{chapter['number']:03d}"
                
                # 章节主导航点
                chapter_nav_point = f'''      <navPoint id="{chapter_nav_id}" playOrder="{play_order}">
            <navLabel>
              <text>{chapter['title']}</text>
            </navLabel>
            <content src="{chapter['filename']}"/>'''
                play_order += 1
                
                # 为章节内的标题创建子导航点
                heading_nav_points = []
                nav_stack=[]
                for heading in chapter['headings']:
                    heading_nav_id = f"{heading['ncxid']}"
                    heading_nav_point = f'''<navPoint id="{heading_nav_id}" playOrder="{play_order}">
                <navLabel>
                  <text>{heading['text']}</text>
                </navLabel>
                <content src="{chapter['filename']}#{heading['id']}"/>
            </navPoint>'''
                    while nav_stack and nav_stack[-1]['level']>=heading['level']:
                        heading_nav_points.append("      </navPoint>")
                        nav_stack.pop()
                    open_nav_point = f'''<navPoint id="{heading_nav_id}" playOrder="{play_order}">
          <navLabel>
            <text>{heading['text']}</text>
          </navLabel>
          <content src="{chapter['filename']}#{heading['id']}"/>'''
                    heading_nav_points.append(open_nav_point)
                    nav_stack.append({'level': heading['level'], 'id': heading_nav_id})
                    play_order += 1
                while nav_stack:
                    heading_nav_points.append("      </navPoint>")
                    nav_stack.pop()
                
                # 如果有标题子导航点，添加到章节导航点中
                if heading_nav_points:
                    chapter_nav_point += '\n' + '\n'.join(heading_nav_points)
                
                chapter_nav_point += '\n          </navPoint>'
                chapter_nav_points.append(chapter_nav_point)
            
            if chapter_nav_points:
                vol_nav_point += '\n' + '\n'.join(chapter_nav_points) + '\n'
            
            vol_nav_point += '</navPoint>'
            nav_points.append(vol_nav_point)

        return f'''<?xml version="1.0" encoding="utf-8"?>
<ncx version="2005-1" xmlns="http://www.daisy.org/z3986/2005/ncx/">
  <head>
    <meta name="dtb:uid" content="urn:uuid:{self.uuid}"/>
    <meta name="dtb:depth" content="4"/>
  </head>
  <docTitle>
    <text>{self.title}</text>
  </docTitle>
  <navMap>
{chr(10).join(nav_points)}
  </navMap>
</ncx>'''
    
    def create_nav_xhtml(self):
        """创建toc.ncx导航文件 - 基于HTML标题结构并支持ID跳转"""
        nav_content = '<ol>\n'
        play_order=0
        
        # 添加封面导航点
        if self.has_cover:
            nav_content+=(f'<li><a href="cover.html">封面</a></li>\n')
            play_order += 1

        # 添加总目录导航点
        nav_content+=(f'<li><a href="tovol.html">各卷目录</a></li>\n')
        nav_content+=(f'<li><a href="tovol.html#00a">凡例</a></li>\n')
        nav_content+=(f'<li><a href="nav.xhtml">总目录</a></li>\n')
        def sub_navpoint(filename, headings):
            """使用 while 循环构建嵌套导航结构"""
            result = ""
            stack=[]
            for heading in headings:
                while stack and stack[-1]['level']>=heading['level']:
                    result += '</ol></li>'
                    stack.pop()
                result += f'<li><a href="{filename}#{heading["id"]}">{heading["text"]}</a>'
                next_index = headings.index(heading) + 1
                if next_index < len(headings) and headings[next_index]['level'] > heading['level']:
                    result += '<ol>\n'
                    stack.append(heading)
                else:
                    result += '</li>\n'
            while stack:
                result += '</ol></li>\n'
                stack.pop()
            return result
        for volume in self.volumes:
            i=volume.volume_number
            volumetext=f'第{i}卷'+volume.volume_name 
            if i==1:
                volumetext=f'第{i}卷（第二版）'
            if i==20:
                volumetext=f"第{i}卷（反杜林论、自然辩证法）"
            if i==23:
                volumetext=f"第{i}卷（资本论第一卷）"
            if i==24:
                volumetext=f"第{i}卷（资本论第二卷）"
            if i==25:
                volumetext=f"第{i}卷（资本论第三卷）"
            if i==26:
                volumetext=f"第{i}卷（剩余价值理论）"
            vol_nav_point=''
            if volume.has_index:
                vol_index_filename = f"MEW{volume.volume_number}-index.html"
                vol_nav_point += f'''<li id="MEW{i}"><a href="{vol_index_filename}">{volumetext}</a><ol>'''
            elif volume.chapters:
                vol_nav_point += f'''<li id="MEW{i}"><a href="{volume.chapters[0]["filename"]}">{volumetext}</a><ol>'''
            play_order += 1
            # 基于实际HTML标题结构创建导航，支持ID跳转
            chapter_nav_points = []
            for chapter in volume.chapters:
                title=chapter['title']
                if volume.volume_number in range(37,40):
                    title=re.sub(r"^[\d]{1,3}[\.．]","",chapter['title'],flags=re.DOTALL|re.IGNORECASE)
                chapter_nav_point = f'<li><a href="{chapter['filename']}">{title}</a>'
                if chapter['headings']:
                    chapter_nav_point+='<ol>\n'
                    chapter_nav_point+=sub_navpoint(chapter['filename'],chapter['headings'])
                    chapter_nav_point+='</ol>'
                chapter_nav_point += '</li>'
                chapter_nav_points.append(chapter_nav_point)
            
            if chapter_nav_points:
                vol_nav_point += '\n' + '\n'.join(chapter_nav_points) + '\n'
            
            vol_nav_point += '</ol></li>\n'
            nav_content+=vol_nav_point
        nav_content+='</ol>\n'


        return f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="zh-cn" xml:lang="zh-cn">
  <head>
  <meta charset="utf-8"/>
    <title>{self.title}</title>
    <link rel="stylesheet" type="text/css" href="styles.css"/>
  </head>
<body>
<h1 style="color:#DC3545;">马克思恩格斯全集（第一版）总目录</h1>
<h2 style="color:#DC3545;font-family:Times New Roman;">Proletarier aller Länder, vereinigt euch!</h2>
<h2 style="color:#DC3545;">全世界无产者，联合起来！</h2>
   <nav epub:type="toc" id="toc" role="doc-toc">
{nav_content}
    </nav>
  </body>
</html>'''
    
    def create_cover_html(self, cover_filenames=None):
        """创建封面页面HTML，支持多张图片"""
        cover_images_html = ""
        
        if cover_filenames and len(cover_filenames) > 0:
            if len(cover_filenames) == 1:
                # 单张图片，居中显示
                cover_images_html = f'<img src="{cover_filenames[0]}" alt="封面" class="cover-image"/>'
            else:
                # 多张图片，使用灵活布局
                image_items = []
                for i, filename in enumerate(cover_filenames):
                    image_items.append(f'''
            <div class="cover-image-item">
                <img src="{filename}" alt="封面图片 {i+1}" class="cover-image"/>
            </div>''')
                cover_images_html = f'''
        <div class="cover-images-container">
{chr(10).join(image_items)}
        </div>'''
        
        return f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="zh-cn" xml:lang="zh-cn">
<head>
    <meta charset="UTF-8"/>
    <meta name="cover" content="cover"/>
    <title>{self.title} - 封面</title>
    <link rel="stylesheet" type="text/css" href="styles.css"/>
</head>
<body>
    <div>
        {cover_images_html}
    </div>
</body>
</html>'''
    
    def create_contents_html(self):
        """创建总目录页面HTML"""
        volume_link =''
        for volume in self.volumes:
            i=volume.volume_number
            volumetext=f'第{i}卷'+volume.volume_name     
            if volume.has_index:
                link_href = f"MEW{volume.volume_number}-index.html"
            elif volume.chapters:
                link_href = volume.chapters[0]['filename']
            else:
                continue
            
            volume_link+=f'<a href="{link_href}">{volumetext}</a><br>\n'

        vol_con= r'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="zh-cn" xml:lang="zh-cn">
<head>
    <meta charset="UTF-8"/>
'''
        vol_con+= f'''<title>{self.title} - 目录</title>'''
        vol_con+=r'''
    <link rel="stylesheet" type="text/css" href="styles.css"/>
</head>
<body>
<h2 style="color:#DC3545;font-family:Times New Roman;">Proletarier aller Länder, vereinigt euch!</h2>
<h2 style="color:#DC3545;">全世界无产者，联合起来！</h2>
<h1 style="color:#DC3545;">马克思恩格斯全集（第一版）</h1>
<h3>卷目</h3>
<p class="TOC">
'''
        vol_con+=volume_link
        vol_con+= r'''
</p>
<h3 id="00a">凡例</h3>
<p>
　　1.正文和附录中的文献分别按写作或发表时间编排。在个别情况下，为了保持一部著作或一组文献的完整性和有机联系，编排顺序则作变通处理。<br>
　　2.目录和正文中凡标有星花*的标题，都是编者加的。<br>
　　3.在引文中尖括号&lt;&gt;内的文字和标点符号是马克思或恩格斯加的，引文中加圈点。处（本电子书以下划线或加粗代替），是马克思或恩格斯加着重号的地方。<br>
　　4.在目录和正文中方括号[]内的文字是编者加的。<br>
　　5.未说明是编者加的脚注为马克思或恩格斯的原注（本电子书中编者或译者加的注，以footnote缩写加编号如<a id="00a-bz123" href="#00a-bzref123">FN123</a>标注，并归入脚注栏，马克思或恩格斯本人的注以括号编号如<a id="00a-az123" href="#00a-azref123">(123)</a>标注，并单独归入作者注栏）。<br>　　
<span>（文本来源：https://cpc.people.com.cn/GB/64184/209964/，排版来源：https://www.marxists.org/chinese/marx-engels/）</span>
</p>
</body>
</html>'''
        vol_con=vol_con.replace("<br>","<br/>")
        return vol_con
    
    def build_epub_folder(self, output_folder):
        """构建EPUB文件夹结构"""
        if not self.volumes:
            print("错误: 没有找到任何卷，无法生成EPUB")
            return
        
        # 准备封面图片
        cover_filenames = self.prepare_cover_images()
        
        output_path = Path(output_folder)
        

        
        output_path.mkdir(parents=True, exist_ok=True)
        (output_path / "META-INF").mkdir(exist_ok=True)
        if Path(output_path/"OEBPS").exists():
            shutil.rmtree(output_path/"OEBPS")
        (output_path / "OEBPS").mkdir()
        print(f"\n构建EPUB文件夹: {output_folder}")
        
        # 创建基础文件
        with open(output_path / "mimetype", 'w', encoding='utf-8') as f:
            f.write(self.create_mimetype())
        
        with open(output_path / "META-INF" / "container.xml", 'w', encoding='utf-8') as f:
            f.write(self.create_container_xml())
        
        with open(output_path / "OEBPS" / "content.opf", 'w', encoding='utf-8') as f:
            f.write(self.create_content_opf())
        with open(output_path / "OEBPS" / "nav.xhtml", 'w', encoding='utf-8', newline='\r\n') as f:
            f.write(self.create_nav_xhtml())
        
        with open(output_path / "OEBPS" / "toc.ncx", 'w', encoding='utf-8') as f:
            f.write(self.create_toc_ncx())
            
        with open(output_path / "OEBPS" / "styles.css", 'w', encoding='utf-8') as f:
            f.write(self.global_css)
        
        # 创建封面页面
        if self.has_cover:
            with open(output_path / "OEBPS" / "cover.html", 'w', encoding='utf-8', newline='\r\n') as f:
                f.write(self.create_cover_html(cover_filenames))
            print(f"  创建封面页面: cover.html (包含 {len(cover_filenames)} 张图片)")
        
        # 创建总目录页面
        with open(output_path / "OEBPS" / "tovol.html", 'w', encoding='utf-8', newline='\r\n') as f:
            f.write(self.create_contents_html())
        print(f"  创建总目录页面: contents.html")
        
        # 复制图片文件
        for img in self.all_images:
            try:
                dest_path = output_path / "OEBPS" / img['filename']
                shutil.copy2(img['original_path'], dest_path)
                #if img['id'].startswith('cover-image'):
                    #print(f"  复制封面图片: {img['filename']}")
                #else:
                   # print(f"  复制图片: {img['filename']}")
            except Exception as e:
                print(f"  警告: 复制图片失败 {img['original_path']}: {e}")
        
        # 创建内容文件 - 修复链接路径
        total_chapters = 0
        
        for volume in self.volumes:
            # 处理卷目录文件
            nameindex=''
            i=volume.volume_number
            if volume.has_index:
                vol_index_filename = f"MEW{volume.volume_number}-index.html"
                ed='一'
                if volume.volume_number==1:
                    ed='二'
                for chapter in volume.chapters:
                    nameindex+=f'<a href="{chapter['filename']}">{chapter['filename'].replace('.html','')}</a>　　{chapter['title']}<br/>\n'
                
                # 修复目录页中的链接路径
                index_content = r'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="zh-cn" xml:lang="zh-cn">
<head>
    <meta charset="UTF-8"/>'''
                index_content+=f'''
    <title>第{i}卷{volume.volume_name} - 目录</title>
    <link rel="stylesheet" type="text/css" href="styles.css"/>
</head>
<body>
<h3 style="color:#DC3545;font-family:Times New Roman;">Proletarier aller Länder, vereinigt euch!</h3>
<h3 style="color:#DC3545;">全世界无产者，联合起来！</h3>
<h1 style="color:#DC3545;margin:0;">马克思恩格斯全集<br/>第{ed}版<br/>第{i}卷</h1>
<h3 style="margin:0;">{volume.volume_name}</h3>
<h1 style="margin-top:0;"><a href="nav.xhtml#MEW{volume.volume_number}">目录</a></h1>
<p>左侧为网页文件名，即以MEW为前缀的卷数、序号，右侧为对应文件标题。<br/>
{nameindex}
</p>
</body>
</html>'''

                with open(output_path / "OEBPS" / vol_index_filename, 'w', encoding='utf-8', newline='\r\n') as f:
                    f.write(index_content)
                #print(f"  处理卷目录: {vol_index_filename} (修复了 {len(volume.chapter_link_map)} 个链接)")
            
            # 处理章节文件
            for chapter in volume.chapters:
                # 修复章节中的图片路径，删除原有CSS，并添加新CSS链接
                fixed_content = fix_image_paths(chapter['content'], volume.image_map)
                
                # 删除原有的CSS样式

                if volume.volume_number in range(46,50):
                    fixed_content=re.sub(r'<a href="#[\s\S]+?-([ab]*z[\S]+)" id="[\s\S]+?-([ab]*z[\S]+)">',f'<a href="#\\1" id="\\2">',
                                         fixed_content ,flags=re.DOTALL | re.IGNORECASE)
                
                #fixed_content = re.sub(r'<link[^>]*rel=["\']stylesheet["\'][^>]*>', '<link rel="stylesheet" type="text/css" href="styles.css"/>', fixed_content, flags=re.IGNORECASE)
                #fixed_content = re.sub(r'<style[^>]*>.*?</style>', '<link rel="stylesheet" type="text/css" href="styles.css"/>', fixed_content, flags=re.DOTALL | re.IGNORECASE)
                fixed_content=re.sub(r'(?:<br/>[\s\r\n]*)+</p>[\r\s\n]*</body>',r'''<br/>
</p>
</body>''', fixed_content, flags=re.DOTALL | re.IGNORECASE)
                #fixed_content = re.sub(r'\s+style=["\'][^"\']*["\']', '<link rel="stylesheet" type="text/css" href="styles.css"/>\n', fixed_content, flags=re.IGNORECASE)
                #fixed_content=re.sub(r

#,fixed_content ,flags=re.DOTALL | re.IGNORECASE)
                #fixed_content=re.sub(r

#,fixed_content ,flags=re.DOTALL | re.IGNORECASE)
                
                

                #if '<head>' in fixed_content:
                    #fixed_content = fixed_content.replace('<head>', '<head>')&
                #elif '<html>' in fixed_content:
                    #fixed_content = fixed_content.replace('<html>', '<html>\n<head>\n    <link rel="stylesheet" type="text/css" href="styles.css"/>\n</head>')
                fixed_content= fixed_content.replace("￥￥￥", "")
                with open(output_path / "OEBPS" / chapter['filename'], 'w', encoding='utf-8', newline='\r\n') as f:
                    f.write(fixed_content)
                total_chapters += 1
        
        print(f"\nEPUB构建完成!")
        print(f"- 总卷数: {len(self.volumes)}")
        print(f"- 总章节数: {total_chapters}")
        print(f"- 总图片数: {len([img for img in self.all_images if not img['id'].startswith('cover-image')])}")
        if self.has_cover:
            print(f"- 封面图片数: {len(self.cover_filenames)}")
        print(f"- 包含总目录页面")
        print(f"- 输出目录: {output_folder}")
        
        # 显示详细的章节信息
        print(f"\n章节详情:")
        if self.has_cover:
            print("    ├── cover.html (封面页)")
            print("    ├── cover_01.jpg, cover_02.jpg, ... (封面图片)")

def zip_directory_with_pathlib(source_dir, output_zip):
    """
    使用 pathlib 和 zipfile 压缩整个文件夹，保留目录结构
    import pathlib
    :param source_dir: 要压缩的源文件夹路径 (字符串或 pathlib.Path 对象)
    :param output_zip: 输出的ZIP文件路径 (字符串或 pathlib.Path 对象)
    """
    source_path = Path(source_dir)
    output_path = Path(output_zip)
    
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
        mimetype_path = source_path / 'mimetype'
        zipf.write(mimetype_path, 'mimetype', compress_type=zipfile.ZIP_STORED)
        for file_path in source_path.rglob('*'):
            if '.git' in file_path.parts:
                continue
            if file_path.is_file() and file_path.name != 'mimetype':
                zipf.write(file_path, file_path.relative_to(source_path))
def main():
    """主程序"""
    print("=== 完整书籍到EPUB转换器 (支持多封面图片) ===\n")
    
    # 配置参数
    book_title = "马克思恩格斯全集（第一版）"  # 修改为你的书名
    book_author = ["Karl Marx" ,"Friedrich Engels"," 中共中央马克思、恩格斯、列宁、斯大林著作编译局"]      # 修改为作者名
    book_dir = r"D:\马恩列总装\MLASSMBLE-EPUB\马恩全集"  # 修改为你的书籍根目录
    
    # 封面图片配置 - 支持多种方式:
    # 方式1: 单张封面图片
    # cover_images = "cover.jpg"
    
    # 方式2: 多张封面图片
    cover_images = [
        r"D:\马恩列总装\MEWCOVER.jpg",
        r"D:\马恩列总装\KARLMARX.jpg",
        r"D:\马恩列总装\FRIEDRICHENGELS.jpg", 
        
    ]
    
    # 方式3: 不使用封面
    # cover_images = None
    excel_file=Path(r"LENIN-toc.xlsx")
    # 创建构建器
    wb = openpyxl.load_workbook(excel_file)            
    sheet = wb.active
    ws = wb['Sheet1']
    output_dir = "MEWTEST1"  # 输出目录名
    
    # 创建构建器
    builder = EpubBookBuilder(book_title, book_author, "zh-cn", cover_images,ws)
    
    # 扫描书籍结构
    builder.scan_book_structure(book_dir)
    output_zip_file = "./MARX-ZH-CN.github.io1/epub/MEW.epub"
    if builder.volumes:
        # 构建EPUB
        builder.build_epub_folder(output_dir)
        zip_directory_with_pathlib(output_dir, output_zip_file)
        print(f"\n=== 处理完成 ===")
        print("EPUB文件夹已创建，现在包含:")
        if builder.has_cover:
            print(f"- 封面页面 (包含 {len(builder.cover_filenames)} 张图片)")
            if len(builder.cover_filenames) == 1:
                print("  * 单张图片居中显示")
            else:
                print("  * 多张图片使用灵活布局显示")
        

    else:
        print("\n错误: 没有找到有效的书籍结构")
        print("请确保:")
        print("1. 有'第n卷'格式的文件夹")
        print("2. 每卷中有MEWn.html和对应的文章文件")
        print("3. HTML文件包含有效的title标签")
        print("4. 如需封面，请提供封面图片文件")

if __name__ == "__main__":
    main()
