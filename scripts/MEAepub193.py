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
            #data=re.sub(r'\[\d+?\]','',data)
            #data=re.sub(r'([\s\S]+?)\s+\d{1,3}',r'\1',data)
            data=re.sub(r'(\(\d+?\))','',data)
            #data=re.sub(r'\[注：[\s\S]+?\]','',data)
            self.title += data

class HeadingExtractor:
    """HTML标题层级提取器 (h1-h6)，使用BeautifulSoup"""
    def __init__(self):
        self.headings = []
    
    def extract_headings_from_html(self, html_content, source_file, chapter_number,volume_number):
        """从HTML内容中提取所有标题层级并添加ID"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            headings_data = []
            
            # 查找所有标题标签
            heading_tags = soup.find_all(['h2', 'h3', 'h4', 'h5', 'h6'])
            title_tag=soup.find('title')
            if title_tag:
                title=title_tag.get_text(separator='  ',strip=True)

            for i, tag in enumerate(heading_tags):
                if 'style' in tag.attrs:
                    del tag['style']
                if 'align' in tag.attrs:
                    del tag['align']
                text = tag.get_text(separator='  ',strip=True)
                if text and len(text) > 0:
                    # 为标题添加锚点ID
                    level = int(tag.name[1])  # h1->1, h2->2, etc.
                    if volume_number in [26] and level==2:
                        continue
                    anchor_id=tag.get('id')
                    ncxid=f"ME{volume_number:02d}{chapter_number:03d}-{i+1}"
                    if not anchor_id:
                        anchor_id =ncxid
                        tag['id'] = anchor_id
                    text=text.replace("<","&lt;")
                    text=text.replace(">","&gt;")
                    text=re.sub(r'￥￥￥[\S ]+?￥￥￥',r'',text,flags=re.DOTALL|re.IGNORECASE)                   
                    headings_data.append({
                        'tag': tag.name,
                        'text': text,
                        'level': level,
                        'id': anchor_id,
                        'source_file': source_file,
                        'chapter_number': chapter_number,
                        'ncxid':ncxid
                    })
            # 返回修改后的HTML和提取的标题数据
            fixed_content=str(soup.body).replace("<body><h1","<body>\n<h1")
            if fixed_content:
                content=f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="zh-cn" xml:lang="zh-cn">
<head>
    <meta charset="UTF-8"/>
    <title>{title}</title>
    <link rel="stylesheet" type="text/css" href="styles.css"/>
</head>
{fixed_content}
</html>
"""                
                return content, headings_data
            else:
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
        self.heading_extractor = HeadingExtractor()  # 标题提取器
        self.volumetext=""
    
    def extract_volume_number(self, volume_name):
        """从卷名中提取数字"""
        match = re.search(r'(\d{1,3})', volume_name)
        return int(match.group(1)) if match else 0
    
    def load_volume_index(self):
        """加载卷的总目录（index.html）"""
        index_path = self.path / f"index.html"
        if index_path.exists():
            try:
                with open(index_path, 'r', encoding='utf-8') as f:
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
                    img_id = f"MEA{self.volume_number:02d}-img{len(self.images) + 1:03d}"
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
    def regex_content(self,content):
        tables=[]
        table_count=0
        quotes=[]
        quote_count=0
        def quote_re(match):
            match_text=match.group(1)
            fixed_content=match_text
            p_match=re.match(r'^([　\t]+?[ ]*(?:(?!<br>|<[/]*div|<[/]*p)[\S\s\r\n])*?)<br>$',match_text,flags=re.DOTALL|re.IGNORECASE)
            p2_match=re.match(r'^((?:(?!<br>|<[/]*div|<[/]*p)[\S ])+?)<br>$',match_text, flags=re.DOTALL | re.IGNORECASE)
            if p_match:
                fixed_content=f'<blockquote>{p_match.group(1)}</blockquote>'
                return fixed_content
            if p2_match:
                fixed_content=f'<blockquote>{p2_match.group(1)}</blockquote>'
                return fixed_content
            fixed_content=re.sub(r'((?:[\t]+?[ ]*|[　 ]{2,}?)(?:(?!<br>|<[/]*div|<[/]*p|<[/]*h[\d])[\S\s\r\n])*?)<br>',r'<p>\1</p>',fixed_content,flags=re.DOTALL | re.IGNORECASE)
            fixed_content=re.sub(r'^([^<>\r\n]+?)<br>$',r'<p>\1</p>'+'\n',fixed_content, flags=re.DOTALL | re.IGNORECASE)
            fixed_content=re.sub(r'<div (class=[\S]+?)>((?:(?!<div)[\S\r\n\s])+?)(</div>|$)',div_re,fixed_content, flags=re.DOTALL | re.IGNORECASE)
            fixed_content=re.sub(r'<div ((?:align|style)\s*=\s*[\S ]+?)>((?:(?!<[/]*div)[\S\r\n\s])+?)(</div>|$)',div_re,fixed_content, flags=re.DOTALL|re.IGNORECASE)
            fixed_content=f'<blockquote>{fixed_content}</blockquote>'
            fixed_content=re.sub(r'<br>\s*</blockquote>',"</blockquote>",fixed_content,flags=re.DOTALL | re.IGNORECASE)
            return fixed_content
        def save_quote(match):
            nonlocal quote_count            
            text=match.group(1)
            pattern=r"<div class=\"quote\">([\s\r\n\S]+?)</div>"
            quote_fix=re.sub(pattern,quote_re,text,flags=re.DOTALL|re.IGNORECASE)
            quotes.append(quote_fix)            
            replacetable=f"<BLOCKQUOTE ID=\"BQ{quote_count:03d}\"></BLOCKQUOTE>"
            quote_count+=1
            return replacetable
        def div_re(match):
            match_text=match.group(2)
            fixed_content=match_text
            p_match=re.match(r'^<p>([　 \S]+?)</p>$',match_text,flags=re.DOTALL|re.IGNORECASE)
            if p_match:
                fixed_content=p_match.group(1)
                fixed_content=f'<p {match.group(1)}>{fixed_content}</p>'
                return fixed_content
            fixed_content=re.sub(r'<p>([\s\r\n\S]+?)</p>'
                                 ,r'\1<br>',fixed_content,flags=re.DOTALL | re.IGNORECASE)
            if match.group(1).startswith(("class=","CLASS=")):
                fixed_content=f'<p {match.group(1)}>{fixed_content}</p>'
            else:
                fixed_content=f'<div {match.group(1)}>{fixed_content}</div>'
                fixed_content=re.sub(r'<br>\s*</div>',"</div>",fixed_content,flags=re.DOTALL | re.IGNORECASE)
            return fixed_content
        def head_re(match):
            match_text=match.group(3)
            fixed_content=re.sub(r'<p>([\s\r\n\S]+?)</p>'
                                 ,r'<br>\1',match_text,flags=re.DOTALL | re.IGNORECASE)
            fixed_content=re.sub(r'([\s\r\n\S]+?)<br>$'
                                 ,r'\1',fixed_content,flags=re.DOTALL | re.IGNORECASE)
            if match.group(2):
                fixed_content=f'<{match.group(1)}{match.group(2)}>{fixed_content}</{match.group(1)}>'
            else:
                fixed_content=f'<{match.group(1)}>{fixed_content}</{match.group(1)}>'
            return fixed_content
        def td_re(matchs):
            matchtext=matchs.group(5)
            table_fix=matchtext+r'<br>'
            link_match=re.findall(r'<a href=["\']\#[\d]*',matchtext,flags=re.DOTALL|re.IGNORECASE)
            if link_match:
                matchtext=re.sub(r'[· ]*(<a href=["\']\#[\d]*)',r'\1',matchtext,flags=re.DOTALL | re.IGNORECASE)
                matchtext="<div class=\"TCC\">"+matchtext+"</div>"
                return matchtext
            replace=r'<tr><td>'+r'\1</td></tr>'+'\n'
            table_fix=re.sub(r'((?:(?!<br>|<[/]*div|<[/]*p)[\S 　])+?)<br>',replace,table_fix,flags=re.DOTALL | re.IGNORECASE)
            style=f"{matchs.group(2)};{matchs.group(4)};".replace(";;",";")
            table_fix=f'<table{matchs.group(1)}style="{style}"{matchs.group(3)}>'+table_fix+r'</table>'            
            return table_fix
        def save_table(match):
            nonlocal table_count            
            pattern=r'''<table([\S ]+?)style=["']([\S ]+?)["']([\S ]+?)>[\s\r\n]*<tr><td style=["']([\S ]+?)["']>([\S\r\n\s]+?)</td></tr></table>'''
            text=match.group(1)
            table_fix=re.sub(pattern,td_re,text, flags=re.DOTALL | re.IGNORECASE)
            tables.append(table_fix)
            #print(table_fix)
            replacetable=f"<TABLE ID=\"TRP{table_count:03d}\"></TABLE>"
            table_count+=1
            return replacetable
        def save_table_test(match):
            nonlocal table_count            
            text=match.group(1)
            tables.append(text)            
            replacetable=f"<TABLE ID=\"TRP{table_count:03d}\"></TABLE>"
            table_count+=1
            return replacetable
        def text_re(match):
            match_text=match.group(2)
            table_pattern = r'(<table[\S ]+?>[\s\r\n\S]+?</table>)(?:<br>)*'
            fixed_content=match_text
            fixed_content=re.sub(table_pattern,save_table,fixed_content,flags=re.DOTALL|re.IGNORECASE)
            if self.volume_number not in range(6,9):
                fixed_content=re.sub(r'((?:[\t]+?[ ]*|[　 ]{2,}?)(?:(?!<br>|<[/]*div|<[/]*p)[\S\s\r\n])*?)<br>',r'<p>\1</p>',fixed_content, flags=re.DOTALL | re.IGNORECASE)
            else:
                fixed_content=re.sub(r'([　]{2,}?(?:(?!<br>|<[/]*div|<[/]*p)[\S\s\r\n])*?)<br>',r'<p>\1</p>',fixed_content, flags=re.DOTALL | re.IGNORECASE)
            #fixed_content=re.sub(r'([　 ]{2,}[\s\r\n\S]+?)<br>',r'<p>\1</p>',fixed_content, flags=re.DOTALL | re.IGNORECASE)
            fixed_content=re.sub(r'<div (class="quote")>([\s\r\n\S]*?)</div>',quote_re,fixed_content,flags=re.DOTALL|re.IGNORECASE)
            fixed_content=re.sub(r'<div (class=[\S]+?)>((?:(?!<[/]*div)[\S\r\n\s])+?)</div>',div_re,fixed_content,flags=re.DOTALL|re.IGNORECASE)
            fixed_content=re.sub(r'<div (align|style\s*=\s*[\S ]+?)>((?:(?!<[/]*div)[\S\r\n\s])+?)</div>',div_re,fixed_content, flags=re.DOTALL | re.IGNORECASE)
            fixed_content=re.sub(r'<(h[\d])([\S ]*?)>([\s\r\n\S]*?)</h[\d]>',head_re,fixed_content,flags=re.DOTALL|re.IGNORECASE)
            fixed_content=re.sub(r'</p>[\r\n\s]+?',r'''</p>
''', fixed_content, flags=re.DOTALL | re.IGNORECASE)
            fixed_content=re.sub(r'<br>\s*</p>',r"</p>",fixed_content,flags=re.DOTALL | re.IGNORECASE)
            fixed_content=re.sub(r'(</(?:blockquote|p|div|h[\d])>)[\s\r\n]*((?:(?!<[/hpd]{1,2}[\d]*|<center>)[\S ])+?)<br>',r'\1'+'\n'+r'<p>\2</p>',fixed_content, flags=re.DOTALL | re.IGNORECASE)
            fixed_content=re.sub(r'^([^<>]+?)<br>$',r'<p>\1</p>'+'\n',fixed_content, flags=re.DOTALL | re.IGNORECASE)
            #fixed_content=re.sub(r'<p>(?:[\t]{1,}[　]*|[　\t]{3,})','<p>　　',fixed_content, flags=re.DOTALL | re.IGNORECASE)
            for i, table in enumerate(tables):
                fixed_content=fixed_content.replace(f"<TABLE ID=\"TRP{i:03d}\"></TABLE>",table)
            fixed_content=match.group(1)+fixed_content+match.group(3)
            return fixed_content
        if self.volume_number not in range(6,9):
            quote_pattern = r'(<div class="quote">(?:(?!div class="quote")[\s\r\n\S])+?(?:</div>)*</div>)(?:<br>)*'
            content=re.sub(quote_pattern,save_quote,content,flags=re.DOTALL|re.IGNORECASE)
        content=re.sub(r'(<body>|</h1>)\s*([\s\r\n\S]+?)(<hr[\S ]*?><p class="quote">\s*<span style="font-size:1.2em[;]*">【|<aside class="quote">\s*<span style="font-size:1.2em[;]*">【|</body>)'
                            ,text_re,content,flags=re.DOTALL|re.IGNORECASE)
        #content=re.sub(r'\t',r"　　",content ,flags=re.DOTALL | re.IGNORECASE)    
        #content=re.sub(r'(<br>[\s\r\n ]*){2,}<br>',r'<br>　　',content ,flags=re.DOTALL | re.IGNORECASE)
        #content=re.sub(r'(<br>[\s\r\n ]*){2,}',r'<br>　　',content ,flags=re.DOTALL | re.IGNORECASE)
        if self.volume_number in (26,30):
            content=re.sub(r'(<body>\s*<h[123]>[\S ]+?</h[123]>)\s*([\s\r\n\S]+?)(<hr[\S ]*?><p class="quote">\s*<span style="font-size:1.2em[;]*">【|<aside class="quote">\s*<span style="font-size:1.2em[;]*">【|</body>)'
                               ,text_re,content,flags=re.DOTALL|re.IGNORECASE)  
        content=re.sub(r'<br>\s*<a id=',f'<br>\n<a id=',content ,flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'<br>\s*<a href=',f'<br>\n<a href=',content ,flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'[　 ]+<h','\n<h',content,flags=re.DOTALL|re.IGNORECASE)
        content=re.sub(r'(<h[\d]) style=["\']*text-align:center[;]*["\']*>',r'\1>',content,flags=re.DOTALL|re.IGNORECASE)   
        content=re.sub(r"<br>[\s]*</h1>",r"</h1>",content,flags=re.DOTALL|re.IGNORECASE)
        content=re.sub(r'<a name=["\']*([\S]+?)["\']*></a>[\s\r\n]*(?:<br>)*?[\s\r\n]*(<h[\d])',r'\2 id="\1"', content,flags=re.DOTALL|re.IGNORECASE)
        #content=re.sub(r'<p class="quote">　　',r'<p class="quote">',content,flags=re.DOTALL|re.IGNORECASE)
        content=re.sub(r'(<hr[\S]*?>)*<aside class="quote">\s*<span style="font-size:1.2em[;]*">【作者注】</span><br>','''
\n<P class=\"footnote\">\n<span class=\"style2\">作者原注</span><BR><BR>''', content, flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'(<hr[\S ]*?>)*<(aside|p) class="quote">\s*<span style="font-size:1.2em[;]*">【脚注】</span><br>','''
\n<P class=\"footnote\">\n<span class=\"style2\">脚　　注</span><BR><BR>''', content, flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'(<hr[\S ]*?>)*<(aside|p) class="quote">\s*<span style="font-size:1.2em[;]*">【注释】</span><br>','''
\n<P class=\"footnote\">\n<span class=\"style2\">注　　释</span><BR><BR>''', content, flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'(?:<br>\s*)+(</(?:p|div|h[\d])>[\r\n]*)',r'\1'+'\n',content,flags=re.DOTALL|re.IGNORECASE)
        fixed_content=re.sub(r'(</(?:p|div|h[\d])>\s*)(?:<br>[\r\n]*)+',r'\1'+'\n',fixed_content,flags=re.DOTALL|re.IGNORECASE)

        content=fixed_content.replace('</aside>','</p>')
        content=re.sub(r'(</h[\d]>)<p>',r'\1'+f'\n<p>',content,flags=re.DOTALL|re.IGNORECASE)    
        recontent=re.sub(r'<title>《马克思恩格斯文集》第[一二三四五六七八九十]卷——+?([\s\S]+?)</title>',r'<title>\1</title>',content ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<title>马恩全集第[一二三四五六七八九十]+?卷——[\S]+?——[\S]+?——[\S]+?——([\s\S]+?)</title>',r'<title>\1</title>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<title>马恩全集第[一二三四五六七八九十]+?卷——[\S]+?——[\S]+?——([\s\S]+?)</title>',r'<title>\1</title>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<title>马恩全集第[一二三四五六七八九十]+?卷——[\S]+?——([\s\S]+?)</title>',r'<title>\1</title>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<title>马恩全集第[一二三四五六七八九十]+?卷——+?([\s\S]+?)</title>',r'<title>\1</title>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(<title>[\s\S]+?)<br>[\s 　]*</title>',r'\1</title>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(<title>[\s\S]+?)<br>&emsp;&emsp;[\s 　]*</title>',r'\1</title>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(<title>[\s\S]+?)<br>[\s 　]*</title>',r'\1</title>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(<title>[\s\S]+?)(&emsp;)?[\s 　]+</title>',r'\1</title>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(<title>[\s\S]+?)\[[\d]+\]([\s\S]*?</title>)',r'\1\2',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(<title>[\s\S]+?)\[注：[\s\S]+?\]([\s\S]*?</title>)',r'\1\2',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<p class="title0">《反杜林论》材料</p>',r'<div style="text-align:center">《反杜林论》材料</div>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'[\s\r\n]+(<sup><a)',r'\1',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(</a></sup>)[\s\r\n]+',r'\1',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'・',r'·',recontent ,flags=re.DOTALL|re.IGNORECASE)
        recontent=re.sub(r'<div class="mbp_pagebreak" id="[\S ]+?"></div>',r'',recontent ,flags=re.DOTALL | re.IGNORECASE)
        
        recontent=re.sub(r'<a></a>',r'',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent = recontent.replace("［", "[")
        recontent =recontent.replace("］", "]")
        recontent = recontent.replace("<sup>", "￥￥￥<sup>")
        recontent = recontent.replace("</sup>", "</sup>￥￥￥")
        fixed_content=re.sub(r'(<h1>)[\s\r\n]+',r'\1',fixed_content,flags=re.DOTALL|re.IGNORECASE)
        fixed_content=re.sub(r'[\s\r\n]+(</h1>)',r'\1',fixed_content,flags=re.DOTALL|re.IGNORECASE)
        if self.volume_number not in range(6,9):
            for i, quote in enumerate(quotes):
                recontent=recontent.replace(f"<BLOCKQUOTE ID=\"BQ{i:03d}\"></BLOCKQUOTE>",quote) 
        return recontent
          
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
                content=content.replace("<br>&emsp;&emsp;<br>&emsp;&emsp;","<br>&emsp;&emsp;")
                content=re.sub(r"<br>&emsp;&emsp;[\s]*</h1>",r"</h1>",content,flags=re.DOTALL|re.IGNORECASE)
                content=content.replace('</p><p class="quote">','</p><p class="footnote">')
                if self.volume_number in (7,8):
                    content=re.sub(r'[ 　]+[\d]{1,3}</title>',r'</title>', content, flags=re.DOTALL | re.IGNORECASE)
                    content=re.sub(r'([\S 　]+?)[　 ][\d]{1,3}([\S 　]+?)</title>',r'\1 \2</title>', content, flags=re.DOTALL | re.IGNORECASE)
                content=re.sub(r'</p>\s*</body>','</p>\n<HR>\n</body>', content, flags=re.DOTALL | re.IGNORECASE)
                content=re.sub(r'<br>\s*<a id=',f'<br>\n<a id=',content ,flags=re.DOTALL | re.IGNORECASE)
                content=re.sub(r'<br>\s*<a href=',f'<br>\n<a href=',content ,flags=re.DOTALL | re.IGNORECASE)
                content=re.sub(r'(<br>[\s\r\n 　]*){2,}<br>',r'<br>　　',content ,flags=re.DOTALL | re.IGNORECASE)
                content=re.sub(r'(<br>[\s\r\n ]*){2,}',r'<br>　　',content ,flags=re.DOTALL | re.IGNORECASE)
                regex_pro=textrepo.textrep(self.volume_number,content,"MEA")
                content=regex_pro.regex_meacontent()

                #content=self.regex_content(content)
                # 收集文章中的图片
                self.collect_images_from_content(content, href)
                
                # 提取标题并修改HTML（添加ID）
                modified_content, headings = self.heading_extractor.extract_headings_from_html(
                    content, href, chapter_number,self.volume_number
                )

                # 存储标题信息
                self.all_headings.extend(headings)
                
                #if headings:
                    #print(f"    第{chapter_number}章: 找到 {len(headings)} 个标题")
                
                # 尝试从HTML的title标签提取标题，如果失败则使用链接文本
                title = extract_title_from_html(content)
                if not title or title == "":
                    title = link_text if link_text else f"第{chapter_number}章"
                
                chapter_filename = f"MEA{self.volume_number}-{chapter_number:03d}.html"
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
    def __init__(self, title, author=[], language="zh", cover_images=None):
        self.title = title
        self.author = author
        self.language = language
        self.uuid = str(uuid.uuid4())
        self.volumes = []
        self.all_images = []
        self.cover_images = cover_images if cover_images and isinstance(cover_images, list) else ([cover_images] if cover_images else [])
        self.has_cover = False
        self.cover_filenames = []
        self.global_css = """body {
    font-family:"华文中宋","宋体","Times New Roman",serif;
    line-height: 1.6;
    margin: 0;
    padding: 1em;
    font-size: 1em;
    text-align:justify;
}
.style2 {font-size: 1.25em}
p.quote,div.quote,span.quote,blockquote,.footnote {
    font-size: 0.75em;
    margin: 1.5em 1px 1.5em 1px;
    text-align:justify;
}
table.quote,table.footnote,blockquote table {
    font-size: 0.75em;
    margin: 1.5em auto 1.5em auto;
}
blockquote p {line-height:1.2;}
h1, h2, h3, h4, h5, h6 {
    margin-top: 1.5em;
    margin-bottom: 0.5em;
    font-weight: bold;
    text-align:center;
}
b {
 font-family:华文中宋,黑体,宋体,Times New Roman,sans serif;
}

p.date,div.date {
    font-size: 0.75em;
    margin: 1.5em auto 1.5em auto;
    text-align:center;
}
.sign {text-align:right;}
.TCC {width: 20%;font-size: 0.75em;text-align:justify;margin:1em auto;}
.TOC {width: 85%;text-align:justify;margin:1em auto;}
span.cq,div.cq {
text-align:center;
display: block;
text-indent:0;
}
img {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 1em auto;
}
p {margin:0;text-align:justify;}
table {
    max-width: 97vw;!important
    margin: 1.5em auto 1.5em auto;
}
hr {
    margin: 1em auto 1em auto;
    text-align:center;
}
.cover-image {
            max-width: 100%;
            height: auto;
            margin: 20px 0;
            box-shadow: 0 4px 8px rgba(0,0,0,0.3);
        }
span[align="center"] {
display: block;
}
div[align="right"] table,div.quote[align="right"] {margin: 1.5em 0 1.5em auto;}
div[align="right"] table.quote,div.quote[align="right"] {display:table;}
div[align="right"] table.quote td {text-align:left;}"""
    
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
            if item.is_dir() and re.match(r'[\d]{1,2}', item.name):
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
                if i==1:
                    volume.volume_name=f"（1843-1848）"
                if i==2:
                    volume.volume_name=f"（1848-1859）"
                if i==3:
                    volume.volume_name=f"（1864-1883）"
                if i==4:
                    volume.volume_name=f"（1884-1895）"
                if i==26:
                    volume.volume_name=f"（反杜林论、自然辩证法）"
                if i==5:
                    volume.volume_name=f"（资本论第{i-4}卷）"
                if i in (6,7):
                    volume.volume_name=f"（资本论第{i-4}卷）"
                if i==8:
                    volume.volume_name=f"（资本论手稿选编）"
                if i==10:
                    volume.volume_name=f"（书信选编）"
                if i==30:
                    volume.volume_name=f"（1857―1858年经济学手稿前半部分）"
                volume.volumetext=f"第{volume.volume_number}卷{volume.volume_name}"
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
        
        # 添加导航文件

        # 添加封面相关文件
        if self.has_cover:
            # 添加所有封面图片
            for img in self.all_images:
                if img['id'].startswith('cover-image'):
                    img_type = get_image_type(img['filename'])
                    manifest_items.append(f'    <item id="{img["id"]}" href="{img["filename"]}" media-type="{img_type}"/>')
            
            # 添加封面页面
            manifest_items.append('    <item href="cover.html" id="cover" media-type="application/xhtml+xml"/>')
            spine_items.append('    <itemref idref="cover"/>')

        spine_items.append('    <itemref idref="nav"/>')
        # 添加总目录页面
        manifest_items.append('    <item href="tovol.html" id="tovol" media-type="application/xhtml+xml"/>')
        spine_items.append('    <itemref idref="tovol"/>')
        
        # 添加图片文件（非封面图片）
        for img in self.all_images:
            if not img['id'].startswith('cover-image'):  # 封面图片已经添加过了
                img_type = get_image_type(img['filename'])
                manifest_items.append(f'    <item href="{img["filename"]}" id="{img["id"]}" media-type="{img_type}"/>')
        
        # 添加卷目录和章节文件
        for volume in self.volumes:
            # 如果有卷目录，添加卷目录文件
            if volume.has_index:
                vol_index_id = f"MEA{volume.volume_number}"
                vol_index_filename = f"{vol_index_id}-index.html"
                manifest_items.append(f'    <item href="{vol_index_filename}" id="{vol_index_id}" media-type="application/xhtml+xml"/>')
                spine_items.append(f'    <itemref idref="{vol_index_id}"/>')
            
            # 添加章节文件
            for chapter in volume.chapters:
                chapter_id = f"MEA{volume.volume_number}-{chapter['number']:03d}"
                chapter_filename = chapter['filename']
                manifest_items.append(f'<item href="{chapter_filename}" id="{chapter_id}" media-type="application/xhtml+xml"/>')
                spine_items.append(f'<itemref idref="{chapter_id}"/>')
        
        # 构建metadata，如果有封面则添加封面元数据（使用第一张封面图片作为主封面）
        metadata_cover = ""
        if self.has_cover and self.cover_filenames:
            metadata_cover = f'    <meta name="cover" content="cover-image-01"/>'
        manifest_items.append(' <item href="toc.ncx" id="ncx" media-type="application/x-dtbncx+xml"/>')
        manifest_items.append(' <item href="nav.xhtml" id="nav" media-type="application/xhtml+xml" properties="nav"/>')
        manifest_items.append(' <item href="styles.css" id="global-css" media-type="text/css"/>')
        dca=""
        for author in self.author:    
            dca+=f"<dc:creator opf:role=\"aut\">{author}</dc:creator>\n"
        return f'''<?xml version="1.0" encoding="utf-8"?>
<package version="3.0" unique-identifier="BookId" xmlns="http://www.idpf.org/2007/opf">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <meta name="generator" content="MEWEPUB-PY"/>
    {metadata_cover}
    <dc:identifier id="BookId" opf:scheme="UUID">urn:uuid:{self.uuid}</dc:identifier>
    <dc:title>{self.title}</dc:title>
    <dc:language>{self.language}</dc:language>
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
        <text>各卷目录</text>
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
            if i==5:
                i+=39
            vol_nav_point = f'''<navPoint id="MEA{volume.volume_number}" playOrder="{play_order}">
      <navLabel>
        <text>{volume.volumetext}</text>
      </navLabel>'''
   
            if volume.has_index:
                vol_index_filename = f"MEA{volume.volume_number}-index.html"
                vol_nav_point += f'''
      <content src="{vol_index_filename}"/>'''
            elif volume.chapters:
                vol_nav_point += f'''
      <content src="{volume.chapters[0]["filename"]}"/>'''
            
            play_order += 1
            
            # 基于实际HTML结构创建导航，支持ID跳转
            chapter_nav_points = []
            for chapter in volume.chapters:
                chapter_nav_id = f"MEA{volume.volume_number}-{chapter['number']:03d}"
                
                # 章节主导航点
                chapter_nav_point = f'''      <navPoint id="{chapter_nav_id}" playOrder="{play_order}">
            <navLabel>
              <text>{chapter['title']}</text>
            </navLabel>
            <content src="{chapter['filename']}"/>'''
                play_order += 1
                if chapter['title'] in [r"人名索引",r"文学作品和神话中的人物索引",r"文献索引",r"报刊索引"]:
                    chapter_nav_point+="</navPoint>"
                    chapter_nav_points.append(chapter_nav_point)
                    continue
                # 为章节内的标题创建子导航点
                heading_nav_points = []
                nav_stack=[]
                for i, heading in enumerate(chapter['headings']):
                    heading_nav_id = f"{heading['ncxid']}"
                    while nav_stack and nav_stack[-1]['level']>=heading['level']:
                        heading_nav_points.append("</navPoint>")
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
                    heading_nav_points.append("</navPoint>")
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
    <meta name="dtb:depth" content="0"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
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
        
        play_order=0
        nav_content="<ul>\n"
        # 添加封面导航点
        if self.has_cover:
            nav_content+=f'<li><a href="cover.html">封面</a></li>\n'
            play_order += 1
        

        # 添加总目录导航点
        nav_content+=f'<li><a href="tovol.html">各卷目录</a></li>\n'
        nav_content+=f'<li><a href="tovol.html#00a">凡例</a></li>\n'
        nav_content+=f'<li><a href="nav.xhtml">总目录</a></li>\n'
        nav_content+= '</ul>\n<ol>\n'
        def sub_navpoint(headings):
            """使用 while 循环构建嵌套导航结构"""
            result = ""
            stack=[]
            i=0
            while i<len(headings):
                heading=headings[i]
                filename=heading['filename']
                if heading["tag"]=="title":
                    resultplus= f'<li><a href="{filename}">{heading["text"]}</a>'
                else:
                    resultplus= f'<li><a href="{filename}#{heading["id"]}">{heading["text"]}</a>'

                if heading["text"] in [r"人名索引",r"文学作品和神话中的人物索引",r"文献索引",r"报刊索引"]:
                    result+=resultplus+'</li>\n'
                    break
                result+=resultplus
                sub_headings = []
                next_index = headings.index(heading) + 1
                j=next_index
                while j < len(headings) and headings[j]['level'] > heading['level']:
                    sub_headings.append(headings[j])
                    j += 1
                if sub_headings:
                    result += '<ol>\n' + sub_navpoint(sub_headings) + '</ol>\n'
                    i+=len(sub_headings)+1
                else:
                    i+=1
                result += '</li>\n'
            return result
        for volume in self.volumes:
            i=volume.volume_number
            vol_nav_point=''
            if volume.has_index:
                vol_index_filename = f"MEA{volume.volume_number}-index.html"           
                if i==10:
                    vol_nav_point += f'''<li id="MEA{i}"><a href="{vol_index_filename}">{volume.volumetext}</a>\n'''
                    vol_nav_point+=(f'<ul><li><a href="{volume.chapters[0]["filename"]}">{volume.chapters[0]["title"]}</a></li></ul>\n<ol>')
                else:
                    vol_nav_point += f'''<li id="MEA{i}"><a href="{vol_index_filename}">{volume.volumetext}</a><ol>\n'''
            elif volume.chapters:
                vol_nav_point += f'''<li id="MEA{i}"><a href="{volume.chapters[0]["filename"]}">{volume.volumetext}</a><ol>\n'''
            play_order += 1
            # 基于实际HTML标题结构创建导航，支持ID跳转
            chapter_nav_points = []
            headings = []
            for chapter in volume.chapters:
                chapter_number=chapter['number']
                title=chapter['title']
                if i==10:
                    if chapter['title'] in [r"第十卷说明"]:
                        continue
                    title=re.sub(r"^[\d]{1,3}\.","",chapter['title'],flags=re.DOTALL|re.IGNORECASE)
                if i not in [8,30] or (i in [8,30] and not chapter['headings']) or (chapter['title'] in [r"人名索引",r"文学作品和神话中的人物索引",r"文献索引",r"报刊索引"]):
                    headings.append({
                    'tag': 'title',
                    'text': title,
                    'level':1,
                    'id':f"onlyfortitle",
                    'source_file': chapter['original_file'],
                    'chapter_number':chapter_number,
                    'filename':chapter['filename']
                    })                                        
                    
                for heading in chapter['headings']:
                    headings.append({
                    'tag':heading['tag'],
                    'text':heading['text'],
                    'level':heading['level'],
                    'id':heading['id'],
                    'source_file': heading['source_file'],
                    'chapter_number':chapter_number,
                    'filename':chapter['filename']
                    })
            vol_nav_point +='\n'+sub_navpoint(headings)
            vol_nav_point += '</ol></li>'
            nav_content+=vol_nav_point
        nav_content+='</ol>'     
        return f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="zh-cn" xml:lang="zh-cn">
  <head>
  <meta charset="utf-8"/>
    <title>{self.title}总目录</title>
    <link rel="stylesheet" type="text/css" href="styles.css"/>
  </head>
<body>
<h1>{self.title}</h1>
<h2>总目录</h2>
<h2 style="color: #DC3545;font-family:Times New Roman;">Proletarier aller Länder, vereinigt euch!</h2>
<h2 style="color: #DC3545;">全世界无产者，联合起来！</h2>
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
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" epub:prefix="z3998: http://www.daisy.org/z3998/2012/vocab/structure/#" lang="zh-cn" xml:lang="zh-cn">
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
        volume_links = []
        for volume in self.volumes:
            i=volume.volume_number     
            if volume.has_index:
                link_href = f"MEA{volume.volume_number}-index.html"
            elif volume.chapters:
                link_href = volume.chapters[0]['filename']
            else:
                continue
            
            volume_links.append(f'        <a href="{link_href}">{volume.volumetext}</a><br>')
        #<h2 style="color: #FF0000;"><a href="http://www.mzdbl.cn" target="_blank"><img src="biaoti1-2.gif" alt="mzdbl" class="cover-image"/></a>整理制作</h2>
        volcont=f'''<?xml version="1.0" encoding="utf-8"?>
        <!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" epub:prefix="z3998: http://www.daisy.org/z3998/2012/vocab/structure/#" lang="zh-cn" xml:lang="zh-cn">
<head>
    <meta charset="UTF-8"/>
    <title>{self.title} - 目录</title>
    <link rel="stylesheet" type="text/css" href="styles.css"/>
</head>
<body>
<p>
        <h1 style="color: #DC3545;">Proletarier aller Länder, vereinigt euch!<br>
全世界无产者，联合起来！</h1>
<h2>马克思恩格斯文集<br>马克思恩格斯全集（第二版）26、30卷<br>&emsp;卷目</h2>

{chr(10).join(volume_links)}

<h3>编辑说明</h3>
<p>
　　一、《马克思恩格斯文集》是马克思主义理论研究和建设工程的重点项目，旨在为深入学习和研究马克思主义理论提供译文更准确、资料更翔实的基础文本。为了编辑这部文集，经中共中央批准，马克思主义理论研究和建设工程成立马克思主义经典作家重点著作译文审核和修订课题组，由中央编译局组织实施。<br>
　　二、《马克思恩格斯文集》编为十卷，精选了马克思和恩格斯在各个时期写的有代表性的重要著作。文集的内容涵盖了马克思主义哲学、政治经济学和科学社会主义，以及马克思和恩格斯在政治、法学、史学、教育、科学技术、文学艺术、军事、民族、宗教等方面的重要论述，并体现了马克思主义理论体系形成和发展的历史进程。<br>
　　三、《马克思恩格斯文集》所收的著作按编年和重要专著单独设卷相结合的方式编排：第一卷收入马克思和恩格斯在1843年至1848年期间的著作；第二卷收入马克思和恩格斯在1848年至1859年期间的著作；第三卷收入马克思和恩格斯在1864年至1883年期间的著作，第四卷收入恩格斯在1884年至1895年期间的著作；第五、六、七卷为马克思的《资本论》第一、二、三卷；第八卷为《资本论》手稿选编（本电子书中附有马恩全集第二版30卷），第九卷收入恩格斯的两部专著《反杜林论》和《自然辩证法》（本电子书以马恩全集第二版26卷代替），第十卷为马克思和恩格斯的书信选编。<br>
　　四、《马克思恩格斯文集》所收著作的译文选自《马克思，恩格斯全集》中文第一版和第二版以及《马克思恩格斯选集》中文第二版。为了保证译文的准确性，课题组根据最权威、最可靠的外文版本对全部译文重新作了审核和修订。校订所依据的外文版本主要有：《马克思恩格斯全集》历史考证版（MEGA2）、《马克思恩格斯全集》德文版（柏林）和《马克思恩格斯全集》英文版（莫斯科、伦敦、纽约）。部分文献还参照了国外有关机构按照马克思和恩格斯的手稿编辑出版的专题文集和单行本。<br>
　　五、《马克思恩格斯文集》各卷均附有注释、人名索引、文献索引和名目索引，第十卷还附有《马克思恩格斯生平大事年表》。课题组对原有的各类资料作了审核和修订，力求资料更翔实、考证更严谨。在注释部分，重新编写了全部著作的题注，增加了对各篇著作主要理论观点的介绍，以便读者把握这些著作的要义。在对各篇著作的写作和出版流传情况的介绍中，增加了对重要著作中译本出版情况的介绍，以便读者了解和研究这些著作在中国的传播情况。<br>
　　六、《马克思恩格斯文集》的技术规格沿用《马克思恩格斯全集》中文第二版的相关规定：在目录和正文中，凡标有星花*的标题都是编者加的，引文中尖括号< >内的文字和标点符号是马克思、恩格斯加的，引文中加圈点处是马克思、恩格斯加着重号的地方；目录和正文中方括号门内的文字是编者加的；未注明“编者注”的脚注是马克思、恩格斯的原注。<br>
　　七、马克思主义理论研究和建设工程咨询委员会对文集的整体方案、各卷文献篇目、译文修订标准以及各篇著作的题注进行了认真审议并提出了许多宝贵意见，这对提高文集编译工作的质量起了重要作用。<br>
<br>
<br>
<h3 style="text-align: center">马克思主义理论研究和建设工程</h3>
<p align="center">马克思主义经典作家重点著作<br>
译文审核和修订课题组</p>
<br>
<br>
<div align="center"><table border="0" cellspacing="0" cellpadding="0"><tr><td style="line-height: 200%"><b>首席专家</b> 韦建桦<br>
<br>
	<b>主要成员</b>　顾锦屏　王学东　李其庆　周亮勋<br>
王锡君　蒋仁祥　胡永钦　翟民刚<br>
章丽莉　张钟朴　冯文光　柴方国<br>
<br>
<br>
《马克思恩格斯文集》编审委员会<br>
<br>
<br>
<b>主　编　</b>韦建桦<br>
<b>副主编　</b>顾锦屏<br>
<b>编　委</b>（以姓氏笔画为序）<br>
王学东　王栋华　王锡君　冯文光<br>
李其庆　沈红文　张钟朴　张海滨<br>
周亮勋　胡永钦　柴方国　夏　静<br>
徐　洋　章　林　章丽莉　蒋仁祥<br>
<br>
<br>
第—卷编审人员<br>
<b>文献选辑和编篡</b><br>
韦建桦　顾锦屏　李其庆　周亮勋<br>
王锡君　蒋仁祥　胡永钦　章丽莉<br>
张钟朴　冯文光　<br>
柴方国<br>
<br>
<b>译文审核和修订</b><br>
韦建桦　顾锦屏　柴方国　徐　洋<br>
<br>
<b>题注和说明</b><br>
韦建桦　顾锦屏　王学东　柴方国<br>
<br>
<b>资料审核和修订</b><br>
章丽莉　王栋华　胡永钦　蒋仁祥<br>
章　林　徐　洋　刘洪涛　沈　延<br>
单志澄　李　楠　张凤凤　张红山<br>
朱　毅　周弘利<br>
<br>
<b>全卷译文和资料审定</b><br>
韦建桦</td></tr></table></div></p>
<h3 id="00a">凡例</h3><p>
&emsp;&emsp;1.正文和附录中的文献分别按写作或发表时间编排。在个别情况下，为了保持一部著作或一组文献的完整性和有机联系，编排顺序则作变通处理。<br>
&emsp;&emsp;2.目录和正文中凡标有星花*的标题，都是编者加的。<br>
&emsp;&emsp;3.在引文中尖括号&lt;&gt;内的文字和标点符号是马克思或恩格斯加的，引文中加圈点。处（本电子书以下划线或加粗代替），是马克思或恩格斯加着重号的地方。<br>
&emsp;&emsp;4.在目录和正文中方括号[]内的文字是编者加的。<br>&emsp;&emsp;5.未说明是编者加的脚注为马克思或恩格斯的原注（本电子书除资本论第1卷区分作者注和编者注栏，作者注编号使用圆角括号、编者注采用FN开头的编号外，其余均为作者注与编者注共同并入脚注栏，采用圆角括号编号）。<br>&emsp;&emsp;
<span>（文本与排版来源：https://www.marxists.org/chinese/marx-engels2/）</span></p>
</body>
</html>'''
        volcont=volcont.replace("<br>","<br/>")
        return volcont
    
    def build_epub_folder(self, output_folder):
        """构建EPUB文件夹结构"""
        if not self.volumes:
            print("错误: 没有找到任何卷，无法生成EPUB")
            return
        
        # 准备封面图片
        cover_filenames = self.prepare_cover_images()
        
        output_path = Path(output_folder)
        
        if output_path.exists():
            shutil.rmtree(output_path)
        
        output_path.mkdir(parents=True, exist_ok=True)
        (output_path / "META-INF").mkdir()
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
            f.write(textrepo.publiccss())
            #f.write(self.global_css)
        
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
            if volume.has_index==True:
                vol_index_filename = f"MEA{volume.volume_number}-index.html"
            i=volume.volume_number
            selftitle=self.title
            nameindex=''
            ifvolVIII=''
            if i in [8]:
                ifvolVIII=r'<br>&emsp;&emsp;相关作品：<a href="MEA30-index.html" target=_blank>马克思恩格斯全集第二版第30卷（1857-1858经济学手稿前半部分）</a><br>\n'
            if i in [30]:
                ifvolVIII=r'<br>&emsp;&emsp;相关作品：<a href="MEA8-index.html" target=_blank>马克思恩格斯文集第8卷（资本论手稿选编）</a><br>\n'
            if i in (5,26,30):
                selftitle=r"马克思恩格斯全集第二版"
                if i==5:
                    i=44
                # 修复目录页中的链接路径
                #<h3 style="color: #FF0000;"><a href="http://www.mzdbl.cn" target="_blank"><img src="biaoti1-2.gif" alt="mzdbl" class="cover-image"/></a>整理制作</h3>
            for chapter in volume.chapters:
                nameindex+=f'<a href="{chapter['filename']}">{chapter['filename'].replace('.html','')}</a>　　{chapter['title']}<br>\n'               
            index_content = f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" epub:prefix="z3998: http://www.daisy.org/z3998/2012/vocab/structure/#" lang="zh-cn" xml:lang="zh-cn">
<head>
    <meta charset="UTF-8"/>
    <title>{volume.volumetext} - 目录</title>
    <link rel="stylesheet" type="text/css" href="styles.css"/>
</head>
<body>
<h3 style="color: #DC3545;font-family:Times New Roman;">Proletarier aller Länder, vereinigt euch!</h3>
<h3 style="color: #DC3545;">全世界无产者，联合起来！</h3>
<h1 style="color:#DC3545;margin:0;">{selftitle}<br>第{i}卷</h1>
<h3 style="margin:0;">{volume.volume_name}</h3>
<h1 style="margin-top:0;"><a href="nav.xhtml#MEA{volume.volume_number}">目录</a></h1>
<p>{ifvolVIII}左侧为网页文件名，即以MEA为前缀的卷数、序号，右侧为对应文件标题。<br>
{nameindex}
</p>
</body>
</html>'''
            index_content=index_content .replace("<br>","<br/>")

            with open(output_path / "OEBPS" / vol_index_filename, 'w', encoding='utf-8', newline='\r\n') as f:
                f.write(index_content)
                #print(f"  处理卷目录: {vol_index_filename} (修复了 {len(volume.chapter_link_map)} 个链接)")
            
            # 处理章节文件
            for chapter in volume.chapters:
                # 修复章节中的图片路径，删除原有CSS，并添加新CSS链接
                fixed_content = fix_image_paths(chapter['content'], volume.image_map)
                if volume.volume_number==5:
                    fixed_content=re.sub(r'<a href="#[\s\S]+?-([ab]*z[\S]+)" id="[\s\S]+?-([ab]*z[\S]+)">',f'<a href="#\\1" id="\\2">',
                                         fixed_content ,flags=re.DOTALL | re.IGNORECASE)


                # 删除原有的CSS样式
                fixed_content=re.sub(r'</aside>',r'</p>', fixed_content, flags=re.DOTALL | re.IGNORECASE)
                fixed_content=fixed_content.replace(r'<br/>　　<a href=',f'<br/>\n<a href=')
                fixed_content=fixed_content.replace('<br>','<br/>')
                fixed_content=re.sub(r'<hr/>\s*</body>',r'</body>',fixed_content ,flags=re.DOTALL | re.IGNORECASE)
                fixed_content=re.sub(r'(?:<br/>[\s\r\n]*)+</p>[\r\s\n]*</body>',r'''<br/>
</p>
</body>''', fixed_content, flags=re.DOTALL | re.IGNORECASE)
                fixed_content=fixed_content.replace(r'￥￥￥','')
                      
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
        # 使用 rglob 递归遍历所有文件
        for file_path in source_path.rglob('*'):
            if file_path.is_file():
                # 关键：计算文件在ZIP包中的相对路径
                arcname = file_path.relative_to(source_path)
                if file_path.name=='mimetype':
                    zipf.write(file_path, arcname,compress_type=zipfile.ZIP_STORED)
                else:
                    zipf.write(file_path, arcname)
def main():
    """主程序"""
    print("=== 完整书籍到EPUB转换器 (支持多封面图片) ===\n")
    
    # 配置参数
    book_title = "马克思恩格斯文集"  # 修改为你的书名
    book_author = ["Karl Marx" ,"Friedrich Engels"," 中共中央马克思、恩格斯、列宁、斯大林著作编译局"]      # 修改为作者名
    book_dir = r"D:\Epic Games\mea"  # 修改为你的书籍根目录
    
    # 封面图片配置 - 支持多种方式:
    # 方式1: 单张封面图片
    # cover_images = "cover.jpg"
    
    # 方式2: 多张封面图片
    cover_images = [
        r"D:\马恩列总装\MEA.jpeg",
        r"D:\马恩列总装\KARLMARX.jpg",
        r"D:\马恩列总装\FRIEDRICHENGELS.jpg", 
        
    ]
    
    # 方式3: 不使用封面
    # cover_images = None
    
    output_dir = "MEATEST1"  # 输出目录名
    
    # 创建构建器
    builder = EpubBookBuilder(book_title, book_author, "zh-cn", cover_images)
    
    # 扫描书籍结构
    builder.scan_book_structure(book_dir)
    output_zip_file = "./MARX-ZH-CN.github.io1/epub/MEA.epub"
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
