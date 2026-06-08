import os
import re
import uuid
from datetime import datetime
from pathlib import Path
import shutil
from html.parser import HTMLParser
from urllib.parse import unquote
import base64
from bs4 import BeautifulSoup
from collections import defaultdict
import csv
import openpyxl
import json
class TitleExtractor(HTMLParser):
    """HTML标题提取器"""
    def __init__(self):
        super().__init__()
        self.title = ""
        self.in_title = False
    
    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'title':
            self.in_title = True
    
    def handle_endtag(self, tag):
        if tag.lower() == 'title':
            self.in_title = False
    
    def handle_data(self, data):
        if self.in_title:
            data = re.sub(r'\[\d+?\]', '', data)
            data = re.sub(r'\[注：[\s\S]+?\]', '', data)
            self.title += data

class HeadingExtractor:
    """HTML标题层级提取器 (h1-h6)，使用BeautifulSoup"""
    def __init__(self):
        self.headings = []
        self.headings_dict= {}
    
    def extract_headings_from_html(self, html_content, source_file, chapter_number, volume_number,href):
        """从HTML内容中提取所有标题层级并添加ID"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            headings_data = []
            heading_tags = soup.find_all(['h1','h2','h3','h4','h5','h6'])
            i=1
            self.headings_dict[source_file]=defaultdict()
            for tag in heading_tags:
                if 'style' in tag.attrs:
                    del tag['style']
                if 'align' in tag.attrs:
                    del tag['align']
                text = tag.get_text(separator='  ', strip=True)
                if text and len(text) > 0:
                    if text==r'Contents':
                        continue
                    anchor_id=tag.get('id')
                    new_id=f"ME{volume_number}-{chapter_number}-{i}"                    
                    if anchor_id:                       
                        self.headings_dict.setdefault(source_file, {})[anchor_id]=new_id
                    tag['id']=new_id                    
                    text = text.replace("<", "&lt;").replace(">", "&gt;")
                    #text = re.sub(r'([\s\S]+?)\s+\d{1,3}', r'\1', text)
                    text = re.sub(r'(\[\d+?\])', '', text)
                    text = re.sub(r'\s*FN\d+?\s*','', text)
                    level = int(tag.name[1])
                    if volume_number<=37:
                        headings_data.append({
                        'tag': tag.name,
                        'text': text,
                        'level': level,
                        'id': new_id,
                        'source_file': source_file,
                        'chapter_number': chapter_number
                        })
                    i+=1
            
            return str(soup), headings_data,self.headings_dict
            
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
                src=decode_url_encoding(src)
                self.images.append(src)

def decode_url_encoding(text):
    """解码URL编码的字符（包括%xx格式和Unicode转义）"""
    try:
        # 首先使用unquote解码标准URL编码（如%20, %C3%A9等）
        decoded = unquote(text)
        return decoded
    except:
        return text

def sanitize_filename(filename):
    """清理文件名，解码URL编码，移除非法字符，补齐.html后缀，限制长度"""    
    # 解码URL编码
    filename = decode_url_encoding(filename)
    
    # 移除或替换非法字符
    cleaned = re.sub(r'[<>:"|?*\x00-\x1f]', '', filename, flags=re.DOTALL | re.IGNORECASE)
    cleaned=re.sub(r'([\S ]+?);\s*[\S ]+?\.html', r'\1.html',cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned=re.sub(r'([\S ]+?);\s*[\S ]+?', r'\1.html',cleaned, flags=re.DOTALL | re.IGNORECASE)
    # 处理路径分隔符
    matchlink=re.match(r'([\S ]+?)#([\S ]+?).html',cleaned, flags=re.DOTALL | re.IGNORECASE)
    if matchlink:
        relinkhref=f'{matchlink.group(1)}.html#{matchlink.group(2)}'
        cleaned=relinkhref
    parts = cleaned.split('/')
    parts = [re.sub(r'[\\/]', '', part) if part not in ['', '..'] else part for part in parts]
        # 补齐.html后缀
    cleaned = '/'.join(parts)
    

    #if cleaned and not cleaned.lower().endswith(('.html', '.htm')) and not re.search(r'\.\w+$', cleaned):
    if cleaned and not cleaned.lower().endswith(('.html', '.htm','.jpg','.png','.gif','.pdf')) and '#' not in cleaned:
        cleaned += '.html'
    cleaned=re.sub(r'[\.]{2,}html', r'.html', cleaned, flags=re.DOTALL | re.IGNORECASE)
    
    # 限制长度到200字节
    if len(cleaned.encode('utf-8')) > 200 and '/' not in cleaned:
        name, ext = os.path.splitext(cleaned)
        max_name_bytes = 200 - len(ext.encode('utf-8'))
        while len(name.encode('utf-8')) > max_name_bytes:
            name = name[:-1]
        cleaned = name + ext
        
    return cleaned
def process_recontent(content, volume_number,title,source):
    #recontent=re.sub(r'[“”]',r'"', content, flags=re.DOTALL | re.IGNORECASE)
    content=re.sub(r'<link rel="stylesheet" type="text/css" href="MECW.css"/>',r'<link rel="stylesheet" type="text/css" href="../MECW.css"/>', content, flags=re.DOTALL | re.IGNORECASE)
    return content
def process_recontent1(content, volume_number,title,source):
    """处理recontent的正则替换逻辑"""
    recontent = re.sub(r'<div class="printfooter">Retrieved from "<a[\r\n\S\s]+?</a>"</div>\s*<div class="catlinks" data-mw="interface" id="catlinks">[\r\n\s\S]+?</script>\s*</body>\s*</div>\s*</html>',
                       '', content, flags=re.DOTALL|re.IGNORECASE)
    recontent = re.sub(r'<html [\S ]+?>[\s\r\n]*?<head>[\s\r\n]*<meta charset="utf-8"/>[\s\S\r\n]+?<h1'
                     , r'<h1', recontent, flags=re.DOTALL|re.IGNORECASE)
    recontent = re.sub(r'''<a[\S ]+?marx[\S ]+?gif"[\S ]+?</a>''',
                       '', recontent, flags=re.DOTALL|re.IGNORECASE)
    recontent = re.sub(r'''<div class="noprint" id="siteSub">From Marxists-en[\s\r\n]*</div>[\s\r\n]*<div id="contentSub">[\S\r\n\s]*?</div>[\s\r\n]*<div id="contentSub2">[\S\s\r\n]*?</div>[\S\s\r\n]*?<div id="jump-to-nav">[\S\s\r\n]*?</div>[\S\s\r\n]*?<a class="mw-jump-link" href="#mw-head">Jump to navigation</a>[\s\r\n]*<a class="mw-jump-link" href="#searchInput">Jump to search</a>'''
                     ,'', recontent, flags=re.DOTALL|re.IGNORECASE)
    recontent = re.sub(r' <html [\S ]+?>[\s\r\n]*<head>[\s\r\n]*<meta charset="utf-8"/>[\s\S\r\n]+?<hr class="clearhr"/>'
                     , '', recontent, flags=re.DOTALL|re.IGNORECASE)
    recontent = re.sub(r'<html [\S ]+?>[\s\r\n]*<head>[\s\r\n]*<meta charset="utf-8"/>[\s\S\r\n]+?<a[\S ]+?>Jump to navigation</a>\s*<a[\S ]+?>Jump to search</a>'
                       , '', recontent, flags=re.DOTALL|re.IGNORECASE)
    recontent = re.sub(r'<html [\S ]+?>[\s\r\n]*<head>[\s\r\n]*<meta charset="utf-8"/>[\s\S\r\n]+?<hr class="clearhr"/>', '', recontent, flags=re.DOTALL|re.IGNORECASE)
    recontent = re.sub(r'''<img alt=""[\S ]+?src="/texts/en/w/images/7/77/Icon-torn-page.png" width="35"/>'''
                       ,'', recontent, flags=re.DOTALL|re.IGNORECASE)
    recontent = re.sub(r'''<span class="mw-editsection"><span class="mw-editsection-bracket">\[</span><a href="[\s\S]+?section[\S]+?" title=["']*Edit[\s\S]+?["']*>edit source</a><span class="mw-editsection-bracket">\]</span></span>''',
                       '', recontent, flags=re.DOTALL|re.IGNORECASE)
    recontent = re.sub(r'(<title>[\s\S]+?)<br>&emsp;&emsp;[\s ]*</title>', r'\1</title>', recontent, flags=re.DOTALL | re.IGNORECASE)
    recontent = re.sub(r'(<title>[\s\S]+?)<br>[\s ]*</title>', r'\1</title>', recontent, flags=re.DOTALL | re.IGNORECASE)
    recontent = re.sub(r'(<title>[\s\S]+?)(&emsp;)?[\s ]+</title>', r'\1</title>', recontent, flags=re.DOTALL | re.IGNORECASE)
    recontent = re.sub(r'(<title>[\s\S]+?)\[[\d]+\]([\s\S]*?</title>)', r'\1\2', recontent, flags=re.DOTALL | re.IGNORECASE)
    recontent=re.sub(r'<a\s*href="/texts/en/Collection:[ \S]+?"\s*title=[\s\S]+?>([\S ]+?)</a>',r'\1', recontent, flags=re.DOTALL | re.IGNORECASE)
    recontent=re.sub(r'<a\s*class="mw-redirect"\s*href="/texts/en/Collection:[ \S]+?"\s*title=[\s\S]+?>([\S ]+?)</a>',r'\1', recontent, flags=re.DOTALL | re.IGNORECASE)
    recontent = re.sub(r'<sup class="reference" id=("[\S]+?")><a (href="#[\S]+?")>([\S ]+?)</a></sup>',
                       r'<sup class="reference"><a id=\1 \2>\3</a></sup> ', recontent, flags=re.DOTALL | re.IGNORECASE)    
    recontent = re.sub(r'[\s\r\n]*(<sup[^<]*?><a[\S ]+?</a></sup>)[\s\r\n]+([,\.;:\?!”’\'"]+)[ ]+', r'\2\1 ', recontent, flags=re.DOTALL | re.IGNORECASE)
    recontent = re.sub(r'[\s\r\n]*(<sup[^<]*?><a[\S ]+?</a></sup>)[\s\r\n]+([,\.;:\?!”’\'"]+)', r'\2\1', recontent, flags=re.DOTALL | re.IGNORECASE)
    recontent = re.sub(r'(<sup[^<]*?><a[\S ]+?</a></sup>)[\s\r\n]+([,\.\?!;:”’\'"]+)', r'\2\1 ', recontent, flags=re.DOTALL | re.IGNORECASE)
    recontent = re.sub(r'(<sup[^<]*?><a[\S ]+?</a></sup>)[\s\r\n]+([\)\]]+)', r'\2\1', recontent, flags=re.DOTALL | re.IGNORECASE)
    recontent = re.sub(r'(</a></sup>)[\s\r\n]+', r'\1 ', recontent, flags=re.DOTALL | re.IGNORECASE)
    recontent = re.sub(r'[\s\r\n]+(<sup[^<]*?><a)', r'\1', recontent, flags=re.DOTALL | re.IGNORECASE)
    recontent = re.sub(r'\s+</p><p>', f'</p>\n<p>', recontent, flags=re.DOTALL | re.IGNORECASE)
    recontent = re.sub(r'</p><p>', f'</p>\n<p>', recontent, flags=re.DOTALL | re.IGNORECASE)
    #recontent = re.sub(r'<p>', r'<br>', recontent, flags=re.DOTALL | re.IGNORECASE)
    recontent = re.sub(r'<sup class="reference" id=("[\S]+?")><a (href="#[\S]+?")>([\S ]+?)</a></sup>',
                       r'<sup class="reference"><a id=\1 \2>\3</a></sup> ', recontent, flags=re.DOTALL | re.IGNORECASE)
    recontent=re.sub(r'<a href="/texts/en/Author:[\S]+?" title=["\']*Author:[\S ]+?["\']*>([\S ]+?)</a>',
                     r'\1', recontent, flags=re.DOTALL | re.IGNORECASE)
    recontent=re.sub(r'<a class=[\S]+? href="/texts/en/Author:[\S]+?" title=["\']*Author:[\S ]+?["\']*>([\S ]+?)</a>',
                     r'\1', recontent, flags=re.DOTALL | re.IGNORECASE)
    recontent=re.sub(r'Source:\s*<a href="[\S]+?">([ \S]+?)</a>([\S ]+?)<br[\s]*/>',r'Source: \1\2', recontent, flags=re.DOTALL | re.IGNORECASE)
    recontent=re.sub(r'Publisher:\s*<a href="[\S]+?">([ \S]+?)</a>([\S ]+?)<br[\s]*/>',r'Publisher: \1\2', recontent, flags=re.DOTALL | re.IGNORECASE)
    recontent=re.sub(r'First Published:\s*<a href="[\S]+?">([ \S]+?)</a>([\S ]+?)<br[\s]*/>',r'First Published: \1\2', recontent, flags=re.DOTALL | re.IGNORECASE)
    recontent=re.sub(r'<!--[\S\s\r\n]+?-->','',recontent,flags=re.DOTALL|re.IGNORECASE)
    
    recontent=re.sub(r'<!DOCTYPE html>',r'', recontent, flags=re.DOTALL | re.IGNORECASE)
    recontent=re.sub(r'''<div data-mw-wikirouge-preview='[\S]+?'></div>''',r'', recontent, flags=re.DOTALL | re.IGNORECASE)
    recontent=re.sub(r'''<div class="Keywords donotprint"><em>[\s]*Keywords[\s\S]+?</em>[\s\S]+?</a>[\s\S]+?</div>''',
                     r'', recontent, flags=re.DOTALL | re.IGNORECASE)
    recontent=re.sub(r'''<(h[\d])><span (id="[\S]+?")></span><span class="mw-headline" (id="[\S]+?")>([\S\s\r\n]+?)</span></h[\d]>''',
                     r'<\1 \3 class="mw-headline">\4</\1><a \2></a>', recontent, flags=re.DOTALL | re.IGNORECASE)
    recontent=re.sub(r'''<(h[\d])><span class="mw-headline" (id="[\S]+?")>([\S\s\r\n]+?)</span></h[\d]>''',
                     r'<\1 \2 class="mw-headline">\3</\1>', recontent, flags=re.DOTALL | re.IGNORECASE)
    recontent=re.sub(r'''<(h[\d])><span class="mw-headline" (id="[\S]+?")>([\S\s\r\n]+?)</span></h[\d]>''',
                     r'<\1 \2 class="mw-headline">\3</\1>', recontent, flags=re.DOTALL | re.IGNORECASE)
    recontent= re.sub(r'''<div[\S ]+?CreateSubpage" style="display:none;">[\s\r\n]*?<div class="NavFrame" style="clear:both; margin-bottom:1em[\S\r\n\s]+?</form>[\r\n\s]*?</div>[\r\n\s]*?<div class="NavEnd" style="height: 0; clear: both;">[\s]*</div>[\r\n\s]*?</div></div>'''
                , '',recontent, flags=re.DOTALL|re.IGNORECASE)
    recontent=re.sub(r'''<div class="mw-content-ltr" dir="ltr" id="mw-content-text" lang="en"><div class="mw-parser-output"><div class="TextHeader"><div class="Metadata"><div class="LittleColLeft">''', '', recontent, flags=re.DOTALL|re.IGNORECASE)
    recontent=re.sub(r'<div id="SummaryPage"><div class="subpagelist subpagelist-empty"></div></div>','',recontent, flags=re.DOTALL|re.IGNORECASE)
    recontent=re.sub(r'''<div[\S ]+?class="noprint"[\S ]+?>From Marxists-en</div>\s*<div[\S ]+?><span class="subpages">[\S ]+?<a[\S ]+?>[\S ]+?</a></span></div>\s*<div[\S ]+?></div>\s*<div[\S ]+?"jump-to-nav"[\S ]+?></div>\s*<a[\S ]+?>Jump to navigation</a>\s*<a[\S ]+?>Jump to search</a>''',
                     r'', recontent, flags=re.DOTALL | re.IGNORECASE)
    recontent=re.sub(r'''<div[\S ]+?class="keywordredirlink"[\S ]+?><a[\S ]+?class="new"[\S ]+?href="[\S ]+?">Keywords:[\S ]+?</a></div><a[\S ]+?class="external text"[\S ]+?rel="nofollow noreferrer noopener" target="_blank">[\S ]+?</a></div><div class="TextHeader"><div data-mw-wikirouge-preview='[\S ]+?'></div>''',r'', recontent, flags=re.DOTALL | re.IGNORECASE)
    recontent=re.sub(r'<div data-mw-wikirouge-preview=[\S ]+?></div>','', recontent, flags=re.DOTALL | re.IGNORECASE)
    recontent=re.sub(r'''<div class="mw-body-content" id="bodyContent">\s*<div class="mw-content-ltr" dir="ltr" id="mw-content-text" lang="en"><div class="mw-parser-output"><div class="TextHeader"><div class="Metadata"><div class="LittleColLeft">''', '', recontent, flags=re.DOTALL|re.IGNORECASE)
    recontent=re.sub(r'''<div class="mw-body-content" id="bodyContent">''', '', recontent, flags=re.DOTALL|re.IGNORECASE)
    recontent=re.sub(r'<([/]*)em>',r"<\1i>", recontent, flags=re.DOTALL | re.IGNORECASE)
    if volume_number not in range(28,35):
        recontent=re.sub(r'''<div id="GlobalSummary"><div class="subpagelist">[\S\s\r\n]+?</div></div>''',r'', recontent, flags=re.DOTALL | re.IGNORECASE)
    edit=source.replace('.html','')
    recontent=f"""<html lang="en">
<head>
<meta charset="utf-8"/>
<META name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{title}</title>
<link rel="stylesheet" type="text/css" href="../MECW.css"/>
<script src="/mlr.js"></script>
</head>
<body>
{recontent}
</body>
</html>"""
    recontent=re.sub(r'[“”]',r'"', recontent, flags=re.DOTALL | re.IGNORECASE)
    recontent=re.sub(r'[’‘]',r"'", recontent, flags=re.DOTALL | re.IGNORECASE)
    return recontent

def process_fixed_content(content, volume_number, chapter_number):
    """处理fixed_content的正则替换逻辑"""
    #pattern1 = r"""<html>\s*<head>\s*<meta http-equiv=["']Content-Language["'] content=["']zh-cn["'][/]*><meta http-equiv=["']Content-Type["'] content=["']text/htmlml; charset=utf-8["'][/]*>"""
    #pattern2 = r"""<html>\s*<head>\s*<meta content=["']zh-cn["'] http-equiv=["']Content-Language["'][/]*><meta content=["']text/htmlml; charset=utf-8["'] http-equiv=["']Content-Type["'][/]*>"""
    #replacement =
    """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" epub:prefix="z3998: http://www.daisy.org/z3998/2012/vocab/structure/#" lang="en" xml:lang="en">"""
    
    #fixed_content = re.sub(pattern1, replacement, content, flags=re.DOTALL | re.IGNORECASE)
    #fixed_content = re.sub(pattern2, replacement, fixed_content, flags=re.DOTALL | re.IGNORECASE)
    #fixed_content=re.sub(r' title="[\S ]+?"',r'', fixed_content, flags=re.DOTALL | re.IGNORECASE)
    fixed_content = re.sub(r'(<br/>[\s\r\n ]*){2,}<br/>', '<br>', content, flags=re.DOTALL | re.IGNORECASE)
    fixed_content = re.sub(r'(<br/>[\s\r\n ]*){2,}', '<br>', fixed_content, flags=re.DOTALL | re.IGNORECASE)
    fixed_content = fixed_content.replace(r'<br/>  <a href=', '<br/>\n<a href=').replace('<br/>', '<br>')
    fixed_content=re.sub(r'[“”]',r'"',fixed_content, flags=re.DOTALL | re.IGNORECASE)
    fixed_content=re.sub(r'[’‘]',r"'", fixed_content, flags=re.DOTALL | re.IGNORECASE)
    
    return fixed_content

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

def fix_image_paths(html_content, image_map):
    """修复HTML中的图片路径"""
    for old_src, new_src in image_map.items():
        pattern = rf'src=["\']({re.escape(old_src)})["\']'
        replacement = f'src="{new_src}"'
        html_content = re.sub(pattern, replacement, html_content, flags=re.IGNORECASE)
    
    return html_content

class BookVolume:
    """书卷类"""
    def __init__(self, base_path, volume_name):
        self.base_path = Path(base_path)  # 总路径
        self.volume_name = volume_name
        self.volume_number = self.extract_volume_number(volume_name)
        self.index_content = ""
        self.chapters = []
        self.images = []
        self.has_index = False
        self.chapter_link_map = defaultdict(dict)
        self.image_map = {}
        self.all_headings = []
        self.all_headings_dict = {}
        self.heading_extractor = HeadingExtractor()
        self.volume_info=[]
    
    def extract_volume_number(self, volume_name):
        """从卷名中提取数字"""
        match = re.search(r'Volume_(\d+)', volume_name, re.IGNORECASE)
        return int(match.group(1)) if match else 0    
    def load_volume_index(self):
        """加载卷的总目录（从总路径/Collection-Marx-Engels_Collected_Works/读取）"""
        # 目录文件在总路径的Collection子目录中
        index_path = self.base_path / "CollectionMarx-Engels_Collected_Works" / f"{self.volume_name}.html"
        
        if index_path.exists():
            try:
                with open(index_path, 'r', encoding='utf-8-sig') as f:
                    self.index_content = f.read()
                
                # 清理HTML内容
                index = re.sub(r'<div class="printfooter">Retrieved from "<a[\S\s]+?</a>"</div>[\s\S]+?</script></body></div></html>', '', self.index_content, flags=re.DOTALL|re.IGNORECASE)
                index = re.sub(r'<html[\S ]+?>\s*<head>\s*<meta charset="utf-8"/>[\s\S]+?<a href="/texts/en/w/index\.php\?title=Collection:Marx-Engels_Collected_Works/Volume_[\S]+?&amp;action=edit&amp;section=1.html" title="Edit section:[\S ]+?">edit source</a><span class="mw-editsection-bracket">\]</span></span></h2>', '', index, flags=re.DOTALL|re.IGNORECASE)
                index = re.sub(r'<html[\S ]+?>\s*<head>\s*<meta charset="utf-8"/>[\s\S]+?<hr class="clearhr"/>', '', index, flags=re.DOTALL|re.IGNORECASE)
                index = re.sub(r'''<span class="mw-editsection"><span class="mw-editsection-bracket">\[</span><a href="[\S ]+?" title="Edit section[\S ]+?">edit source</a><span class="mw-editsection-bracket">\]</span></span>''', '', index, flags=re.DOTALL|re.IGNORECASE)
                index=re.sub(r'([\S ]+?)\.(jpg|png|gif|pdf)\.html',r'\1.\2',index,flags=re.DOTALL | re.IGNORECASE)
                index=re.sub(r'([\S ]+?)#([\S ]+?)\.html',r'\1.html#\2',index,flags=re.DOTALL | re.IGNORECASE)
                index=re.sub(r'([\S ]+?)[\.]{2,}html',r'\1.html',index,flags=re.DOTALL | re.IGNORECASE)
                # 移除/texts/en/路径前缀
                index = re.sub(r'/texts/en/', '', index, flags=re.DOTALL|re.IGNORECASE)
                index=re.sub(r'<tr[ S]+?><td[ S]+?>',r'',index,flags=re.DOTALL | re.IGNORECASE)
                index=re.sub(r'</td></tr>',r'',index,flags=re.DOTALL | re.IGNORECASE)
                self.index_content = index
                self.has_index = True
                self.collect_images_from_content(self.index_content, "index.html")
                
                #print(f"  成功加载卷目录: {self.volume_name}")
                
            except Exception as e:
                print(f"  警告: 无法读取 {index_path}: {e}")
        else:
            print(f"  注意: {self.volume_name} 没有找到目录文件: {index_path}")
    
    def collect_images_from_content(self, html_content, source_file):
        """从HTML内容中收集图片"""
        images = extract_images_from_html(html_content)
        for img_src in images:
            if not img_src.startswith(('http', 'https','https://','http://', 'data:')):
                # 图片路径也从总路径查找
                img_path = self.base_path / img_src
                if img_path.exists():
                    img_id = f"MECW{self.volume_number:02d}-img{len(self.images) + 1:03d}"
                    img_ext = img_path.suffix.lower()
                    img_filename = f"{img_id}{img_ext}"
                    
                    self.images.append({
                        'original_path': img_path,
                        'filename': img_filename,
                        'id': img_id,
                        'vol_num':self.volume_number,
                        'source_file': source_file
                    })
                    
                    self.image_map[img_src] = img_filename
    
    def scan_chapters(self):
        """通过解析目录页链接来扫描章节文件（从总路径读取）"""
        if not self.has_index:
            print(f"  {self.volume_name} 没有目录页，跳过")
            return
        links = extract_links_from_html(self.index_content)
        if not links:
            print(f"  {self.volume_name} 目录页中没有找到链接")
            return
        #processed_links=list({l['href']: l for l in links}.values())
        print(f"开始扫描 {self.volume_name} 的章节...")
        chapter_number = 1
        for link in links:
            href = link['href']
            cleaned_href = sanitize_filename(href)
            matchlink=re.match(r'([\S ]+?)#([\S ]+?)',cleaned_href,flags=re.DOTALL | re.IGNORECASE)
            relinkhref=cleaned_href
            key=cleaned_href
            if matchlink:
                relinkhref=f'{matchlink.group(1)}'
            if self.volume_number<=37 and self.chapter_link_map[relinkhref]:
                continue
            link['href']=relinkhref
            link_text = link['text']
            # 解码URL编码并清理文件名                                                    
            # 从总路径查找文章文件
            article_path = self.base_path /relinkhref
            if article_path.suffix in ['.jpg','.png','.gif','.pdf']:
                continue
            
            if not article_path.exists():
                print(f"    第{chapter_number}章-跳过: {cleaned_href} (文件不存在)")
                continue
            
            try:
                with open(article_path, 'r', encoding='utf-8-sig') as f:
                    content = f.read()
                content = re.sub(r'(<title>[\s\S]+?) - Marxists-en</title>', r'\1</title>', content, flags=re.DOTALL | re.IGNORECASE)
                                
                title = extract_title_from_html(content)
                if not title or title == "":
                    title = link_text if link_text else f"Chapter {chapter_number}"                                
                # 基础内容处理
                
                content = content.replace("<br>&emsp;&emsp;<br>&emsp;&emsp;", "<br>&emsp;&emsp;")
                content = re.sub(r"<br>&emsp;&emsp;[\s]*</h1>", r"</h1>", content, flags=re.DOTALL|re.IGNORECASE)
                content = content.replace('<aside', '<p').replace('</aside>', '</p>')
                content = content.replace('</strong>', '</b>').replace('<strong>', '<b>')
                # 清理HTML

                content = process_recontent(content,self.volume_number,title,href)
                
                self.collect_images_from_content(content,cleaned_href)
                modified_content, headings,headings_map = self.heading_extractor.extract_headings_from_html(
                    content, relinkhref, chapter_number, self.volume_number,href
                )
                self.all_headings.extend(headings)
                chapter_filename = f"MECW{self.volume_number:02d}-{chapter_number:03d}.html"
                title = title.replace("<", "&lt;").replace(">", "&gt;")
                merge=headings_map
                merge.update(self.all_headings_dict)
                self.all_headings_dict=merge
                self.chapters.append({
                    'number': chapter_number,
                    'title': title,
                    'content': modified_content,
                    'filename': chapter_filename,
                    'original_file':relinkhref,
                    'link_text': link_text,
                    'original_link':cleaned_href,
                    'headings': headings
                })                
                # 建立链接映射（原始href和清理后的都要映射）
                self.chapter_link_map[cleaned_href] = [chapter_filename,self.volume_number]
                if cleaned_href!=relinkhref:
                    self.chapter_link_map[relinkhref] = [chapter_filename,self.volume_number]               
                if relinkhref!= href and cleaned_href!=href:
                    self.chapter_link_map[href] =[chapter_filename,self.volume_number] 
                # 同时映射解码后的URL
                decoded_href = decode_url_encoding(href)
                if decoded_href != href:
                    self.chapter_link_map[decoded_href] =[chapter_filename,self.volume_number] 
                
                #print(f"    第{chapter_number}章: {title[:50]}...")
                chapter_number += 1
                
            except Exception as e:
                print(f"    警告: 无法读取文章文件 {cleaned_href}: {e}")
                continue
        
        #print(f"  完成扫描，共找到 {len(self.chapters)} 个章节\n  ")


class EpubBookBuilder:
    """EPUB图书构建器"""
    def __init__(self, title, author=[], language="en", cover_images=None,ws=[]):
        self.title = title
        self.author = author
        self.language = language
        self.uuid = str(uuid.uuid4())
        self.volumes = []
        self.all_images = []
        self.cover_images = cover_images if cover_images and isinstance(cover_images, list) else ([cover_images] if cover_images else [])
        self.has_cover = False
        self.cover_filenames = []
        self.global_file_map = {}
        self.global_headings_dict={}
        self.global_css = """body {
    font-family: Georgia, Times New Roman, serif;
    line-height: 1.6;
    margin: 2em;
    padding: 0;
}"""
        self.ws=ws
        self.suplte=''
    
    def build_global_map(self):
        """构建全局链接映射，支持跨卷引用"""
        for volume in self.volumes:
            merge=volume.chapter_link_map
            merge.update(self.global_file_map)
            self.global_file_map=merge
            merge=volume.all_headings_dict
            merge.update(self.global_headings_dict)
            self.global_headings_dict=merge
            merge=volume.all_headings_dict
            merge.update(self.global_headings_dict)
            self.global_headings_dict=merge
            #self.all_images.extend(volume.image_map)
            
        #print(self.global_headings_dict)
        print(f"\n全局链接映射表已构建: {len(self.global_file_map)} 个条目")    
    def fix_html_links_volume(self,old_href, link_map):
        new_href_map=link_map.get(old_href)
        if new_href_map:
            new_href=new_href_map[0]
            return new_href
        else:
            return old_href
    def normalize_link_path(self,filename,link_href,volume_num):
        if '#' in link_href:
            link_href, anchor = link_href.split('#', 1)
        else:
            anchor = None
        new_anchor=None
        if not link_href:
            if anchor:
                new_anchor=self.global_headings_dict.get(filename, {}).get(anchor)
                return f"#{new_anchor}" if new_anchor else f"#{anchor}"
            else:
                return ""

        # 处理绝对路径：去掉 "/texts/en/" 前缀
        if link_href.startswith('/texts/en/'):
            # 移除开头的绝对路径前缀，得到相对路径
            link_href = link_href[10:]  # 去掉 "/texts/en/"
        if "archive/marx" in link_href:
            link_href=re.sub(r"http[s]*://[\S]*?marxist[\S]+?/archive",r"../../archive",link_href,flags=re.DOTALL|re.IGNORECASE)
            link_href=re.sub(r"\.htm(?!l)\b",r".html",link_href,flags=re.DOTALL|re.IGNORECASE)
            return link_href
        if link_href.startswith(r'https://') or link_href.startswith(r'http://'):
            return link_href
        # 解码URL编码
        decoded_link = decode_url_encoding(link_href)
        cleaned_link = sanitize_filename(decoded_link)
        new_linkmap=(self.global_file_map.get(link_href) or 
               self.global_file_map.get(decoded_link) or
               self.global_file_map.get(cleaned_link) or
               self.global_file_map.get(Path(link_href).name) or
               self.global_file_map.get(Path(decoded_link).name))
        new_link=""
        new_anchor=""
        if not new_linkmap:
            relinkref=cleaned_link
            matchlink=re.match(r'([\S ]+?)#([\S ]+?)',cleaned_link, flags=re.DOTALL | re.IGNORECASE)
            if matchlink:
                relinkref=f'{matchlink.group(1)}'
            new_linkmap = (self.global_file_map.get(link_href) or 
               self.global_file_map.get(decoded_link.replace("-","_").replace("'","’")) or
               self.global_file_map.get(cleaned_link.replace("-","_").replace("'","’")) or
               self.global_file_map.get(Path(link_href).name) or
               self.global_file_map.get(Path(decoded_link).name)) or self.global_file_map.get(relinkref)
         # 尝试多种方式查找映射 
        volprefix=""      
        if new_linkmap:
            new_link = new_linkmap[0]
            if volume_num!=new_linkmap[1]:
                volprefix=f"../{new_linkmap[1]}/"

        if anchor:
            new_anchor=self.global_headings_dict.get(link_href, {}).get(anchor) or self.global_headings_dict.get(cleaned_link, {}).get(anchor) or self.global_headings_dict.get(decoded_link, {}).get(anchor)
        

        if new_link and new_anchor:# 返回新的文件名（可能带有卷文件夹路径）
            return volprefix+f"{new_link}#{new_anchor}" 
        elif new_link:
            return volprefix+f"{new_link}#{anchor}" if anchor else volprefix+new_link  
        else:# 如果没有找到映射，返回清理后的链接
            new_link=link_href.replace('.html','')
            new_link=new_link.replace("'","’")
            if r'.php' not in link_href or r'index' not in link_href:
                self.suplte+=f"<a href=\"https://wikirouge.net/texts/en/{new_link}\">https://wikirouge.net/texts/en/{new_link}</a>  补<br>"
            if new_link==r"MECW":
                return f"index.html"
            return f"https://wikirouge.net/texts/en/{new_link}#{anchor}" if anchor else f"https://wikirouge.net/texts/en/{new_link}"
    
    def fix_html_links_global(self, filename,html_content,volume_num):
        """使用全局映射修复HTML中的所有链接"""
         # 提取所有链接
        links = extract_links_from_html(html_content)# 记录需要替换的链接
        link_replacements = {}
        for link in links:
            old_href = link['href']# 跳过外部链接、数据URI和纯锚点
            match=re.match(r"^#cite_",old_href, flags=re.IGNORECASE)
            if match:
                continue
            if old_href.startswith(('mailto:', 'data:', 'javascript:','#cite_')):
                continue# 标准化链接路径
            if old_href.endswith((r'.jpg', r'.gif', r'.png', r'.pdf', r'.jpeg', 'javascript:')):
                continue# 标准化链接路径

            new_href = self.normalize_link_path(filename,old_href,volume_num)
            #print(new_href)
             # 如果新旧链接不同，记录替换
            if new_href != old_href:
                link_replacements[old_href] = new_href# 执行替换
        for old_href, new_href in link_replacements.items():
            # 转义特殊字符用于正则表达式
            escaped_old = re.escape(old_href)# 替换 href 属性
            pattern1 = rf'href\s*=\s*["\']{escaped_old}["\']'
            html_content = re.sub(pattern1, f'href="{new_href}"', html_content, flags=re.IGNORECASE) # 替换 name 属性（如果需要）
            pattern2 = rf'name\s*=\s*["\']{escaped_old}["\']'
            html_content = re.sub(pattern2, f'name="{new_href}"', html_content, flags=re.IGNORECASE)
    
        return html_content

      
    def scan_book_structure(self, book_dir):
        """扫描整本书的结构"""
        book_path = Path(book_dir)
        if not book_path.exists():
            print(f"错误: 书籍目录 '{book_dir}' 不存在")
            return
        
        volume_index_files = []
        vol_dir=book_dir
        volume_index=book_dir+r"/Collection-Marx-Engels_Collected_Works"
        
        volume_index_files=list(Path(volume_index).glob("*.html"))
        volume_index_files.sort(key=lambda x: natural_sort_key(x.name))
        
        for ctl_idx,vol_file in enumerate(volume_index_files):
            #if ctl_idx not in range(0,7):
            #if ctl_idx not in range(27,37):
            #    continue
            volume = BookVolume(vol_dir,vol_file.name.replace('.html',''))
            i = volume.volume_number
            for row in self.ws.iter_rows(min_row=i, max_row=i, values_only=True):
                volume.volume_info=[row[3],row[4]]
            volume.load_volume_index()
            volume.scan_chapters()
            if volume.chapters:
                volume.volume_name = f"Volume {i}"
                self.volumes.append(volume)
                self.all_images.extend(volume.images)
            else:
                print(f"  警告: {vol_dir} 中没有找到有效章节")
            
        self.build_global_map()   
        #self.build_global_link_map()
    def build_epub_folder(self, output_folders):
        """构建EPUB文件夹结构"""
        if not self.volumes:
            print("错误: 没有找到任何卷，无法生成EPUB")
            return
        output_paths = []
        imagedir="images" 
        for output_folder in output_folders:
            output_path = Path(output_folder)
            output_path.mkdir(parents=True, exist_ok=True)
            output_paths.append(output_path)
            image_path=output_path/imagedir
            image_path.mkdir(exist_ok=True)

        #if output_path.exists():
        #    shutil.rmtree(output_path)

        '''with open(output_path / "index.html", 'w', encoding='utf-8-sig', newline='') as f:
            f.write(self.create_contents_html())'''

        
        total_chapters = 0
        seen=[]
        total_index=''
        def sub_navpoint(headings):
            """使用 while 循环构建嵌套导航结构"""
            result = ""
            stack=[]
            i=0
            while i<len(headings):
                heading=headings[i]
                filename=heading['filename']
                if heading["tag"]=="title" or not heading["id"]:
                    resultplus= f'<li><a href="{filename}" target=_blank>{heading["text"]}</a>'
                else:
                    resultplus= f'<li><a href="{filename}#{heading["id"]}" target=_blank>{heading["text"]}</a>'
                if heading["text"] in [r"Contents",r"文学作品和神话中的人物索引",r"文献索引",r"报刊索引"]:
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
            voldir=str(volume.volume_number)
            if volume.has_index:
                vol_index_filename = r"index.html"               
                if volume.volume_info[0] and not volume.volume_info[1]:
                    display=f"{volume.volume_info[0]}"
                    display_title="<h3>"+display+"</h3>\n<h2>"
                if not volume.volume_info[0] and volume.volume_info[1]:
                    display=f"({volume.volume_info[1]})"
                    display_title="<h3>"+display+"</h3>\n<h2>"
                if volume.volume_info[0] and volume.volume_info[1]:
                    display=f"{volume.volume_info[0]} ({volume.volume_info[1]})"
                    display_title=f"<h3>{volume.volume_info[0]}</h3>\n<h4>({volume.volume_info[1]})</h4>\n<h2>"
                if volume.volume_info[1]==r'Letters':
                    display=f"Letters: {volume.volume_info[0]}"
                    display_title="<h3>"+display+"</h3>\n<h2>"
                total_index+=f'<li><a href="{voldir}/{vol_index_filename}" target=_blank>{volume.volume_name}</a> {display}</li>\n'
                index_css=r"{font-family:Times New Roman;margin:0;}"
                index_content = f'''<html lang="en">
<head>
<meta charset="utf-8"/>
<META name="viewport" content="width=device-width, initial-scale=1.0"/>
    <title>{volume.volume_name} - Content</title>
<link rel="stylesheet" type="text/css" href="../MECW.css"/>
<script src="/mlr.js"></script>
<style type="text/css">
<!--
h2,h3,h4 {index_css}
--></style>
</head>
  <body>
    <h2>Marx & Engels Collected Works<br>Volume {volume.volume_number}</h2>
{display_title}Contents</h2>
    <nav class="volc">
    <ol>'''
            headings = []
            json_list=[]
            for output_path in output_paths:
                volpath=output_path/voldir
                volpath.mkdir(exist_ok=True)
            for chapter in volume.chapters:
                headings_final=[]
                chapter_path = f"{chapter['filename']}"
                fileref=chapter['original_file']
                #matches=re.match(r"([\S ]+?).html#([\S ]+?)",chapter['original_link'], flags=re.DOTALL | re.IGNORECASE) 
          
                if volume.volume_number<=37:                        
                    if self.global_file_map.get(fileref)[0]!=chapter['filename']:
                        fixed_content=r'usecited#'                        
                        chapter_path=self.normalize_link_path(fileref,chapter['original_link'],volume.volume_number)
                        text=re.sub(r'[“”]',r'"',chapter['link_text'], flags=re.DOTALL | re.IGNORECASE)
                        text=re.sub(r'[’‘]',r"'", text, flags=re.DOTALL | re.IGNORECASE)       
                        headings_final.append({
                            'tag': 'title',
                            'text':chapter['link_text'],
                            'level':0,
                            'id':None,
                            'source_file': chapter_path,
                            'chapter_number':chapter['number'],
                            'filename':chapter_path
                        })
                        json_list.append({
            "file":  chapter_path,
            "title":    chapter['title'],
            "headings":  headings_final
        })
                        continue
                fixed_content=self.fix_html_links_global(chapter['original_file'],chapter['content'], volume.volume_number)
                fixed_content=process_fixed_content(fixed_content, volume.volume_number, chapter['number'])
                if fixed_content!=r'usecited#':
                    fixed_content = fix_image_paths(fixed_content,volume.image_map)
                    for output_path in output_paths:
                        with open(output_path/voldir/chapter['filename'], 'w', encoding='utf-8-sig', newline='\r\n') as f:
                            f.write(fixed_content)
                            total_chapters += 1 
                h1text=''                   
                if chapter['headings'] and fixed_content!=r'usecited#':
                    for heading in chapter['headings']:
                        headid=heading['id']
                        level=heading['level']
                        text=heading['text']
                        text=re.sub(r'[“”]',r'"',text, flags=re.DOTALL | re.IGNORECASE) 
                        text=re.sub(r'[’‘]',r"'",text, flags=re.DOTALL | re.IGNORECASE)       
                        if text==h1text:
                            continue
                        if heading['id'].endswith(r'-1'):
                            headid=None
                            h1text=text
                            level=0
                            if h1text in ("Preface","Prefaces"):
                                if volume.volume_number not in range(28,38) and volume.volume_number not in [25]:
                                    text=chapter['link_text']
                        headings_final.append({
                        'tag':heading['tag'],
                        'text':text,
                        'level':level,
                        'id':headid,
                        'source_file':chapter_path,
                        'chapter_number':chapter['number'],
                        'filename':chapter['filename']
                        })
                else:
                    text=re.sub(r'[“”]',r'"',chapter['title'], flags=re.DOTALL | re.IGNORECASE) 
                    text=re.sub(r'[’‘]',r"'",text, flags=re.DOTALL | re.IGNORECASE)  
                    headings_final.append({
                    'tag': 'title',
                    'text': text,
                    'level':0,
                    'id':None,
                    'source_file':chapter_path,
                    'chapter_number':chapter['number'],
                    'filename':chapter['filename']
                    }) 
                seen.append(chapter)
                json_list.append({
            "file":     chapter['filename'],
            "title":    chapter['title'],
            "headings":  headings_final
        })
                headings.extend(headings_final)
            index_content += '\n'
            index_content+='\n'+sub_navpoint(headings)
            index_content += '</ol>\n'                            
            index_content += '</nav>\n  </body>\n</html>' 
            manifest_json = json.dumps(json_list, ensure_ascii=False, indent=None)
            for output_path in output_paths:
                with open(output_path /voldir/vol_index_filename, 'w', encoding='utf-8-sig', newline='\r\n') as f:
                    f.write(index_content)
                with open(output_path /voldir/f"index.json", 'w', encoding='utf-8') as f:
                    f.write(manifest_json)
        toindex=f"""<html lang="en">
<head>
<meta charset="utf-8"/>
<META name="viewport" content="width=device-width, initial-scale=1.0"/>
    <title>Marx & Engels Collected Works - Volumes</title>
<link rel="stylesheet" type="text/css" href="MECW.css"/>
</head>
  <body>
    <h2 style="font-family:Times New Roman;">Marx & Engels Collected Works<br>Volumes Index</h2>
<nav class="volc">
{total_index}
</nav>
</body>
</html>""" 
          
        for output_path in output_paths:
            
            with open(output_path  / 'index.html', 'w', encoding='utf-8-sig', newline='\r\n') as f:
                f.write(toindex)
            
        for img in self.all_images:
            try:
                for output_path in output_paths:
                    dest_path = output_path /f'{img['vol_num']}'/ img['filename']
                    shutil.copy2(img['original_path'], dest_path)
            except Exception as e:
                print(f"  警告: 复制图片失败 {img['original_path']}: {e}")
        #with open(output_path/"suplte.html",'w',encoding='utf-8-sig',newline='') as f:
        #    f.write(self.suplte)
        print(f"\nEPUB构建完成!")
        print(f"- 总卷数: {len(self.volumes)}")
        print(f"- 总章节数: {total_chapters}")
        print(f"- 总图片数: {len([img for img in self.all_images if not img['id'].startswith('cover-image')])}")

def main():
    """主程序"""
    print("=== 完整书籍到EPUB转换器 (支持跨卷链接修复) ===\n")
    
    book_title = "马克思恩格斯全集（第一版）"
    book_author = ["Karl Marx", "Friedrich Engels", " 中共中央马克思、恩格斯、列宁、斯大林著作编译局"]
    book_dir = r"D:\马恩列总装\Marx_html\texts\en"
    
    cover_images = [
    ]
    excel_file=Path(r"MECW-TOC.xlsx")
    # 创建构建器
    wb = openpyxl.load_workbook(excel_file)            
    sheet = wb.active
    ws = wb['Sheet1']
    output_dirs = [r"./MEEN/en/MECW",r"./MARX-ZH-CN-node/en/MECW"]
    #output_dirs = [r"./en/MECW"]

    builder = EpubBookBuilder(book_title, book_author, "en-GB", cover_images,ws)
    
    builder.scan_book_structure(book_dir)
    
    if builder.volumes:
        builder.build_epub_folder(output_dirs)
        print(f"\n=== 处理完成 ===")
    else:
        print("\n错误: 没有找到有效的书籍结构")

if __name__ == "__main__":
    main()


    
        
