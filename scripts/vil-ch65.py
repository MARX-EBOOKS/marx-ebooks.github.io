import re
import json
from pathlib import Path
from bs4 import BeautifulSoup
from io import StringIO
import VILo2
def preprocess_html(content, vol_num):
    # 保持原有的预处理函数不变
    content = re.sub(r'<meta http-equiv=["]*Content-Type["]* content="text/html; charset=windows-1251">', 
                    r'''<meta http-equiv="Content-Type" content="text/html; charset=utf-8">
<META name="viewport" content="width=device-width, initial-scale=1.0"/>''', content, flags=re.IGNORECASE)
    content = content.replace("<a>","</a>")
    content = content.replace("<A>","</A>")
    content = re.sub(r'\s*<A HREF="#p([\S]+?)"><SUP>([\S]+?)</SUP></A>', 
                    r'<SUP><A HREF="#p\1" id="pref\1">\2</A></SUP>', content, flags=re.IGNORECASE)
    content = re.sub(r'\s*<A HREF=("#[\S]+?")><SUP>([\S]+?)</SUP></A>', 
                    r'<SUP><A HREF=\1>\2</A></SUP>', content, flags=re.IGNORECASE)
    #content = re.sub(r'HREF="([\S]+?).htm', 
    #                r'href="\1.html', content, flags=re.IGNORECASE)
    content = re.sub(r'([\d]+?) тома</A>[\s\S]+?<P><HR>\s*?<P ALIGN=RIGHT>ПЕЧАТАЕТСЯ',
                    r'''тома \1</A>
<DIV class="chapter" id="s0"></DIV>
<DIV STYLE="COLOR: RED;TEXT-ALIGN:CENTER;"><i>Пролетарии всех стран, соединяйтесь!</i></DIV>
<H1 STYLE="COLOR: RED">ЛЕНИН</H1>
<H3 ALIGN=CENTER>ПОЛНОЕ<BR>СОБРАНИЕ<BR>СОЧИНЕНИЙ</H3>
<H2 ALIGN=CENTER>\1</H2>
<HR><P ALIGN=RIGHT>ПЕЧАТАЕТСЯ''', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'тома ([\d]+?)</A>[\s\S]+?<P><HR>\s*?<P ALIGN=RIGHT>ПЕЧАТАЕТСЯ',
                    r'''тома \1</A>
<DIV class="chapter" id="s0"></DIV>
<DIV STYLE="COLOR:#DC3545;TEXT-ALIGN:CENTER;"><i>Пролетарии всех стран, соединяйтесь!</i></DIV>
<H1 STYLE="COLOR:#DC3545;">ЛЕНИН</H1>
<H3 ALIGN=CENTER>ПОЛНОЕ<BR>СОБРАНИЕ<BR>СОЧИНЕНИЙ</H3>
<H2 ALIGN=CENTER>\1</H2>
<HR><P ALIGN=RIGHT>ПЕЧАТАЕТСЯ''', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<P><HR><A NAME=s0> </A>',
                    r'<A ID="s0"></A><P><HR>', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<P><HR><A NAME=(s1)> </A><P ALIGN=CENTER>([\dIVXLivxl]+?)\s+?(<P ALIGN=[\S]+?>)',
                    r'''<DIV class="chapter-r" id="\1">1</DIV>
\3''', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<P><HR><A NAME=(s1)> </A>\s*<H',
                    r'''<DIV class="chapter-r" id="\1">1</DIV>
<H''', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<P><HR><A NAME=(s[\dIXVLivxl]+?)> </A><P ALIGN=CENTER>([\dIVXLivxl]+?)\s+?<BR>В\. И\. ЛЕНИН\s+?<P ALIGN=([\S]+?)>',
                    r'''<DIV CLASS="HD" ID="\1"><span class="lp">\2</span>В. И. ЛЕНИН<span></span></DIV>
<P ALIGN=\3>''', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<P><HR><A NAME=(s[\dIXVLivxl]+?)> </A><P ALIGN=CENTER>([\dIVXLivxl]+?)\s+?<BR>В\. И\. ЛЕНИН\s+?<BLOCKQUOTE>',
                    r'''<DIV CLASS="HD" ID="\1"><span class="lp">\2</span>В. И. ЛЕНИН<span></span></DIV>
<BLOCKQUOTE>''', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<P><HR><A NAME=(s[\dIXVLivxl]+?)> </A><P ALIGN=CENTER>([\dIVXLivxl]+?)\s+?<BR>([\S  ]+?)\s+?<P ALIGN=([\S]+?)>',
                    r'''<DIV CLASS="HD" ID="\1"><span></span>\3<span class="rp">\2</span></DIV>
<P ALIGN=\4>''', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<P><HR><A NAME=(s[\dIXVLivxl]+?)> </A><P ALIGN=CENTER>([\dIVXLivxl]+?)\s+?<BR>(В\. И\. ЛЕНИН)\s+?<BLOCKQUOTE>',
                    r'''<DIV CLASS="HD" ID="\1"><span class="lp">\2</span>\3<span></span></DIV>
<BLOCKQUOTE>''', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<P><HR><A NAME=(s[\dIXVLivxl]+?)> </A><P ALIGN=CENTER>([\dIVXLivxl]+?)\s+?<BR>([\S  ]+?)\s+?<BLOCKQUOTE>',
                    r'''<DIV CLASS="HD" ID="\1"><span></span>\3<span class="rp">\2</span></DIV>
<BLOCKQUOTE>''', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<P><HR><A NAME=(s[\dIXVLivxl]+?)> </A><P ALIGN=CENTER>([\dIVXLivxl]+?)\s+?<BR>(В\. И\. ЛЕНИН)\s+?<P',
                    r'''<DIV CLASS="HD" ID="\1"><span class="lp">\2</span>\3<span></span></DIV>
<P''', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<P><HR><A NAME=(s[\dIXVLivxl]+?)> </A><P ALIGN=CENTER>([\dIVXLivxl]+?)\s+?<BR>([\S  ]+?)\s+?<P',
                    r'''<DIV CLASS="HD" ID="\1"><span></span>\3<span class="rp">\2</span></DIV>
<P''', content, flags=re.DOTALL | re.IGNORECASE)
    primechaniya_match = re.search(r'''<P><HR>(?:<A NAME=s[\d]+?> </A>)+<A NAME=pprim> </A><P ALIGN=CENTER>[\d]+?[\r\n\s]*?<H2 ALIGN=CENTER>ПРИМЕЧАНИЯ</H2>''', content, flags=re.DOTALL | re.IGNORECASE)
    if primechaniya_match:
        primechaniya_pos = primechaniya_match.start()
        before_notes = content[:primechaniya_pos]
        after_notes = content[primechaniya_pos:]
        #before_notes= re.sub(r'<P><HR><A NAME=(s[\dIXVLivxl]+?)> </A><P ALIGN=CENTER>([\dIVXLivxl]+?)\s+?<BR>(В. И. ЛЕНИН)\s+?<H',r'''<HR class="chapter" ID="\1"><DIV CLASS="HEADER">\2　　\3</DIV><H''', before_notes, flags=re.DOTALL | re.IGNORECASE)
        #before_notes= re.sub(r'<P><HR><A NAME=(s[\dIXVLivxl]+?)> </A><P ALIGN=CENTER>([\dIVXLivxl]+?)\s+?<BR>([\S  ]+?)\s+?<H',r'''<HR class="chapter" ID="\1"><DIV CLASS="HEADER">\3　　\2</DIV><H''',before_notes, flags=re.DOTALL | re.IGNORECASE)
        before_notes  = re.sub(r'<P><HR><A NAME=(s[\dIXVLivxl]+?)> </A><P ALIGN=CENTER>([\dIVXLivxl]+?)[\s\r\n]+?<BR>В\. И\. ЛЕНИН[\s\r\n]+?<H',r'''<DIV class="chapter-1" ID="\1"><span class="lp">\2</span>В. И. ЛЕНИН<span></span></DIV>
<H''',before_notes , flags=re.DOTALL | re.IGNORECASE)
        before_notes = re.sub(r'<P><HR><A NAME=(s[\dIXVLivxl]+?)> </A><P ALIGN=CENTER>([\dIVXLivxl]+?)[\s\r\n]+?<BR>([\S ]+?)[\s\r\n]+?<H',
                    r'''<DIV CLASS="chapter-1" ID="\1"><span></span>\3<span class="rp">\2</span></DIV>
<H''', before_notes , flags=re.DOTALL | re.IGNORECASE)
        before_notes= re.sub(r'<P><HR><A NAME=(s[\dIXVLivxl]+?)> </A><P ALIGN=CENTER>([\dIVXLivxl]+?)[\s\r\n]+?<P ALIGN=CENTER>([\S  ]+?)[\s\r\n]+<H',
                    r'''<DIV CLASS="chapter-1" ID="\1"><span></span>\3<span class="rp">\2</span></DIV>
<H''', before_notes, flags=re.DOTALL | re.IGNORECASE)
        before_notes= re.sub(r'<P><HR><A NAME=(s[\dIXVLivxl]+?)> </A><P ALIGN=CENTER>([\dIVXLivxl]+?)[\s\r\n]+?<P ALIGN=CENTER>В\. И\. ЛЕНИН[\s\r\n]+?<H',
                    r'''<DIV CLASS="chapter-1" ID="\1"><span class="lp">\2</span>В. И. ЛЕНИН<span></span></DIV>
<H''', before_notes, flags=re.DOTALL | re.IGNORECASE)
        if vol_num in range(46,56):
            before_notes = re.sub(r'<DIV CLASS="HD" (ID="s[\d]+?")>',r'<DIV class="chapter-1" \1>',before_notes, flags=re.DOTALL | re.IGNORECASE)
        content = before_notes + after_notes
    #content = re.sub(r'''<P><HR><A NAME=(s[\d]+?)> </A><P ALIGN=CENTER>([\d]+?)[\r\n\s]+?<P ALIGN=CENTER>([\S ]+?)[\s\r\n]+<HR class="chapter"( ID="s[\d]+?")><DIV CLASS="HEADER">''',r'''<HR class="chapter" ID="\1"><DIV CLASS="HEADER-1">\2</DIV><P style="text-align:CENTER">\3</P><HR><DIV CLASS="HEADER"\3>''', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'''<P><HR><A NAME=s[\d]+?> </A><A NAME=(s[\d]+?)> </A><A NAME=([\S]+?)> <P ALIGN=CENTER>([\d]*?[02468])\s+?(<H[\d]+?) ALIGN=CENTER>''',
                    r'<DIV class="chapter-l" id="\1">\3</DIV>\4 ID="\2">', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'''<P><HR><A NAME=s[\d]+?> </A><A NAME=(s[\d]+?)> </A><A NAME=([\S]+?)> </A><P ALIGN=CENTER>([\d]*?[13579])\s+?(<H[\d]+?) ALIGN=CENTER>''',
                    r'<DIV class="chapter-r" id="\1">\3</DIV>\4 ID="\2">', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'''<P><HR><A NAME=(s[\d]+?)> </A><A NAME=([\S]+?)> </A><P ALIGN=CENTER>([\d]*?[13579])\s+?(<H[\d]+?) ALIGN=CENTER>''',r'''<DIV class="chapter-r" id="\1">\3</DIV>\4 ID="\2">''', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'''<P><HR><A NAME=(s[\d]+?)> </A><P ALIGN=CENTER>([\d]*?[13579])\s+?(<H[\d]+?) ALIGN=CENTER>''',
                    r'<DIV class="chapter-r" id="\1">\2</DIV>\3>', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'''<P><HR><A NAME=(s[\d]+?)> </A><A NAME=([\S]+?)> </A><P ALIGN=CENTER>([\d]*?[02468])\s+?(<H[\d]+?) ALIGN=CENTER>''',r'''<DIV class="chapter-r" id="\1">\3</DIV>\4 ID="\2">''', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'''<P><HR><A NAME=(s[\d]+?)> </A><P ALIGN=CENTER>([\d]*?[02468])\s+?(<H[\d]+?) ALIGN=CENTER>''',
                    r'<DIV class="chapter-l" id="\1">\2</DIV>\3>', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'''<P><HR><A NAME=(s[\d]+?)> </A><P ALIGN=CENTER>([\dIVXLivxl]+?)\s+?(<H[\d]+?) ALIGN=CENTER>''',
                    r'<DIV class="chapter-r" id="\1">\2</DIV>\3>', content, flags=re.DOTALL | re.IGNORECASE)
    content=re.sub(r'<P><HR><P ALIGN=CENTER>([\dIVXLivxlХ]+?)\s+?<BR>([\S  ]+?)\s+?<P ALIGN=JUSTIFY>',
                    r'''<DIV CLASS="HD-1" id="\1">\1<BR>\2</DIV>
''', content, flags=re.DOTALL | re.IGNORECASE)
    content=re.sub(r'''<P><HR><P ALIGN=CENTER>([\dIVXLivxlХ]+?)\s+?<BR>([\S ]+?)\s+?<H''',
                    r'''<DIV CLASS="HD-1" id="\1">\1<BR>\2</DIV>
<H''', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<P>(<[HT])',r'\1', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<P class=[\S]+?>(<TABLE)',r'\1', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<P align=CENTER>(<TABLE[^>]*)>',r'\1 style="margin:auto auto;">', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<P align=RIGHT>(<TABLE[^>]*)>',r'\1 style="margin:auto 0 auto auto;">', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<P align=LEFT>(<TABLE[^>]*>)',r'\1', content, flags=re.DOTALL | re.IGNORECASE)
    #content = re.sub(r'<HR WIDTH=15% ',r'<HR WIDTH=15%', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'(<p[^>]*>)([\S\r\s\n]+?)(?=<[/]*[phtd][^>]*>|<[/]*small[^>]*>|$)',
                    r'\1\2</p>', content, flags=re.DOTALL | re.IGNORECASE)
    
    content = re.sub(r'<SMALL><HR WIDTH=15% ALIGN=LEFT>\s*<P ALIGN=JUSTIFY>([\s\r\n\S]+?)(<DIV class="[CH])',
                    r'<aside>\n<HR><P>\1</aside>'+'\n'+r'\2', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'''<P ALIGN=JUSTIFY>''',r'''<P>''', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'''[\s\r\n]+</P>''','</P>\n', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<P ALIGN=([\S]+?)>([\S ]+?)<P>',
                    r'<DIV STYLE="TEXT-ALIGN:\1;">\2</DIV>', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<P ALIGN=([\S]+?)>',r'<P STYLE="TEXT-ALIGN:\1">', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<A NAME=p([\S]+?)>\s*</A><sup>([\S ]+?)</sup>', r'<SUP><a id="p\1" href="#pref\1">\2</a></SUP>', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<A NAME=', r'<A ID=', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'COLOR[\s]*:[\s]*RED', r'COLOR: #DC3545', content, flags=re.DOTALL | re.IGNORECASE)

    if vol_num > 0:
        content = re.sub(r'<a href="vilall\.htm">', r'<a href="../index.html">', content, flags=re.DOTALL | re.IGNORECASE)
    else:
        content = re.sub(r'<a href="vilall\.htm">', r'<a href="index.html">', content, flags=re.DOTALL | re.IGNORECASE)
    return content

class BatchHTMLSplitter:
    def __init__(self, input_dir, output_dirs=[], min_file_size_kb=3):
        self.input_dir = Path(input_dir)
        self.output_dirs = output_dirs
        self.min_file_size_bytes = min_file_size_kb * 1024  # 转换为字节
        self.anchor_to_file = {}
        self.file_splits = {}
        self.file_info = {}  # 新增：存储文件信息的字典
        self.page_info = {}  # 新增：存储页码信息的字典
        
    def process_batch(self):
        html_files = list(self.input_dir.glob("*.htm")) + list(self.input_dir.glob("*.html"))
        
        if not html_files:
            print(f"在目录 {self.input_dir} 中未找到HTML文件")
            return
        print(f"找到 {len(html_files)} 个HTML文件")
        for output_dir in self.output_dirs:
            output_dir.mkdir(parents=True, exist_ok=True)
        
        # 第一步：读取所有文件内容到file_info字典
        print("\n第一步：读取文件信息...")
        self._read_file_info(html_files)
        
        # 第二步：扫描所有文件，建立锚点映射和智能合并
        print("\n第二步：扫描文件并制定智能拆分方案...")
        self._scan_and_plan_smart_splits()
        
        # 第三步：处理每个文件，拆分并更新链接
        print("\n第三步：拆分文件并更新链接...")
        for file_name in self.file_info.keys():
            print(f"\n处理文件: {file_name}")
            self._process_single_file(file_name)
        
        # 创建索引页面
        
        print(f"\n批量处理完成！共处理 {len(self.file_info)} 个文件")
        print(f"输出目录: {self.output_dirs}")
    
    def _read_file_info(self, html_files):
        """读取所有文件内容到file_info字典"""
        for html_file in html_files:
            file_name = html_file.name
            # 提取卷号
            vol_num = 0
            match = re.match(r'[0]*(\d{1,2})\.htm', file_name)
            if match:
                vol_num = int(match.group(1))
            
            # 读取文件内容并预处理
            html_content = html_file.read_text(encoding='windows-1251')
            html_content = VILo2.preprocess_html(html_content, vol_num)
            
            # 存储到file_info字典
            self.file_info[file_name] = {
                'vol_num': vol_num,
                'file_name': file_name,
                'content': html_content
            }
    
    def _scan_and_plan_smart_splits(self):
        """扫描所有文件，建立锚点映射，并制定智能拆分方案"""
        for file_name, file_data in self.file_info.items():
            vol_num = file_data['vol_num']
            if vol_num == 0:
                continue  # 卷号为0的文件不拆分
            content = file_data['content']
            file_base = Path(file_name).stem
            
            soup = BeautifulSoup(content, 'html.parser')
            
            # 查找所有class="chapter"的hr标签
            chapter_hrs = soup.find_all('div', class_=['chapter-l','chapter-r', 'chapter-1','chapter'])
            
            if not chapter_hrs:
                # 没有章节标记，整个文件作为一个章节
                self._handle_no_chapters(file_name, file_base, soup, vol_num)
                continue
            
            # 有章节标记的情况 - 智能合并
            self._plan_smart_splits(file_name, file_base, soup, chapter_hrs, vol_num)
    
    def _handle_no_chapters(self, file_name, file_base, soup, vol_num):
        """处理没有章节标记的文件"""
        page_num = "1"
        new_filename = f"VL{file_base}-{page_num}.html"       
        self.file_splits[file_name] = [{
            'page_num': page_num,
            'new_filename': new_filename,
            'start_hr': None,
            'end_hr': None,
            'vol_num': vol_num
        }]
        
        # 扫描所有锚点
        all_anchors = self._find_all_anchors(soup)
        for anchor in all_anchors:
            # 更新anchor_to_file结构
            anchor_s_match = re.match(r'^s([\dIXVLivxl]+?)$', anchor, re.IGNORECASE|re.DOTALL)
            if anchor_s_match:
                anchor_page = anchor_s_match.group(1)
            
            # 调用页码信息处理函数
            anchor_info = self._process_page_info(file_name, anchor, new_filename, page_num, vol_num)
            self.anchor_to_file[f"{file_name}#{anchor}"] = anchor_info
        
        # 文件本身的映射
        file_info = self._process_page_info(file_name, None, new_filename, page_num, vol_num)
        self.anchor_to_file[file_name] = file_info
    
    def _plan_smart_splits(self, file_name, file_base, soup, chapter_hrs, vol_num):
        """制定智能拆分方案：在拆分前就合并小章节"""
        
        html_str = str(soup)
        splits = []
        notes_start_index = -1
        
        # 查找注释区开始位置
        notes_pattern = r'<H2[^>]*>ПРИМЕЧАНИЯ</H2>'
        notes_match = re.search(notes_pattern, html_str, re.IGNORECASE)
        if notes_match:
            notes_start_index = notes_match.start()
        
        # 分析每个章节
        for i, hr in enumerate(chapter_hrs):
            chapter_id = hr.get('id', '')
            
            # 确定章节内容范围
            hr_str = str(hr)
            hr_start = html_str.find(hr_str)
            if hr_start == -1:
                continue
            
            # 检查是否为注释区章节
            is_notes_chapter = False
            if notes_start_index > 0 and hr_start >= notes_start_index:
                is_notes_chapter = True
            # 提取章节内容以便计算大小
            if i == len(chapter_hrs) - 1:
                chapter_content = html_str[hr_start:]
            else:
                next_hr = chapter_hrs[i + 1]
                next_hr_str = str(next_hr)
                next_hr_start = html_str.find(next_hr_str, hr_start + len(hr_str))
                if next_hr_start != -1:
                    chapter_content = html_str[hr_start:next_hr_start]
                else:
                    chapter_content = html_str[hr_start:]
            
            # 计算章节大小（UTF-8 BOM编码）
            chapter_size = len(self._encode_with_bom(chapter_content))
            
            splits.append({
                'index': i,
                'chapter_id': chapter_id,
                'hr': hr,
                'hr_start': hr_start,
                'content': chapter_content,
                'size': chapter_size,
                'is_notes': is_notes_chapter,
                'anchors': self._find_anchors_in_content(chapter_content),
                'vol_num': vol_num
            })
        
        # 智能合并：在拆分前合并小章节
        merged_splits = self._smart_merge_splits(splits, file_base, vol_num)
        
        # 更新文件拆分方案
        self.file_splits[file_name] = merged_splits
        
        # 建立锚点映射
        for split in merged_splits:
            new_filename = split['new_filename']
            page_num = split['page_num']
            chapter_id = split.get('chapter_id')
            
            # 章节ID的映射
            if chapter_id:
                anchor_info = self._process_page_info(file_name, chapter_id, new_filename, page_num, vol_num)
                self.anchor_to_file[f"{file_name}#{chapter_id}"] = anchor_info
            
            # 章节内所有锚点的映射
            for anchor in split.get('merged_anchors', []):
                anchor_info = self._process_page_info(file_name, anchor, new_filename, page_num, vol_num)
                self.anchor_to_file[f"{file_name}#{anchor}"] = anchor_info
        
        # 文件本身的映射（指向第一个章节）
        if merged_splits:
            first_split = merged_splits[0]
            file_info = self._process_page_info(
                file_name, 
                None, 
                first_split['new_filename'], 
                first_split['page_num'], 
                vol_num
            )
            if r'<h2 id="psoder">СОДЕРЖАНИЕ</h2>' in first_split['content']:
                file_info['new_filename'] = f"index.html"
            self.anchor_to_file[file_name] = file_info
    
    def _smart_merge_splits(self, splits, file_base, vol_num):
        """智能合并小章节"""
        if not splits:
            return []
        
        merged_splits = []
        i = 0
        
        while i < len(splits):
            current = splits[i]
            
            # 如果是注释区章节，单独处理
            if current['is_notes']:
                page_num = self._extract_page_num(current['chapter_id'], current['index'])
                new_filename = f"VL{file_base}-{page_num}.html"
                if r'<h2 id="psoder">СОДЕРЖАНИЕ</h2>' in current['content']:
                    new_filename = f"index.html"
                merged_splits.append({
                    'page_num': page_num,
                    'new_filename': new_filename,
                    'chapter_id': current['chapter_id'],
                    'hr': current['hr'],
                    'content': current['content'],
                    'size': current['size'],
                    'merged_anchors': current['anchors'],
                    'merged_indices': [current['index']],
                    'is_notes': True,
                    'vol_num': vol_num
                })
                i += 1
                continue
            
            # 非注释区章节：检查是否需要合并
            if current['size'] < self.min_file_size_bytes:
                # 小章节，尝试与后续章节合并
                merged_indices = [current['index']]
                merged_content = current['content']
                merged_anchors = set(current['anchors'])
                total_size = current['size']
                j = i + 1
                
                # 尝试合并后续的非注释区章节
                while j < len(splits) and total_size < self.min_file_size_bytes:
                    next_chapter = splits[j]
                    
                    # 如果下一个章节是注释区，停止合并
                    if next_chapter['is_notes']:
                        break
                    
                    # 合并内容
                    merged_content += next_chapter['content']
                    merged_anchors.update(next_chapter['anchors'])
                    total_size = len(self._encode_with_bom(merged_content))
                    merged_indices.append(next_chapter['index'])
                    j += 1
                
                # 如果合并后还是太小，且后面是注释区，则尝试与前面的章节合并
                if total_size < self.min_file_size_bytes and j < len(splits) and splits[j]['is_notes']:
                    if merged_splits:  # 前面有章节
                        last_split = merged_splits[-1]
                        if not last_split.get('is_notes', False):
                            # 合并到前一个章节
                            last_split['content'] += merged_content
                            last_split['size'] = len(self._encode_with_bom(last_split['content']))
                            last_split['merged_anchors'].update(merged_anchors)
                            last_split['merged_indices'].extend(merged_indices)
                            i = j  # 跳过已处理的章节
                            continue
                
                # 使用第一个章节的信息
                page_num = self._extract_page_num(current['chapter_id'], current['index'])
                new_filename = f"VL{file_base}-{page_num}.html"
                
                merged_splits.append({
                    'page_num': page_num,
                    'new_filename': new_filename,
                    'chapter_id': current['chapter_id'],
                    'hr': current['hr'],
                    'content': merged_content,
                    'size': total_size,
                    'merged_anchors': merged_anchors,
                    'merged_indices': merged_indices,
                    'is_notes': False,
                    'vol_num': vol_num
                })
                
                i = j  # 跳过已合并的章节
            else:
                # 大章节，直接保留
                page_num = self._extract_page_num(current['chapter_id'], current['index'])
                new_filename = f"VL{file_base}-{page_num}.html"
                
                merged_splits.append({
                    'page_num': page_num,
                    'new_filename': new_filename,
                    'chapter_id': current['chapter_id'],
                    'hr': current['hr'],
                    'content': current['content'],
                    'size': current['size'],
                    'merged_anchors': set(current['anchors']),
                    'merged_indices': [current['index']],
                    'is_notes': False,
                    'vol_num': vol_num
                })
                i += 1
        
        return merged_splits
    
    def _process_page_info(self, original_file, anchor, new_filename, page_num, vol_num):
        """
        处理页码信息，生成优化的链接信息字典
        
        参数:
            original_file: 原始文件名
            anchor: 锚点名称 (如 "s1", "s2", "p123" 等)
            new_filename: 新文件名 (如 "VL001-1.html")
            page_num: 页面编号 (从文件名中提取的页码)
            vol_num: 卷号
        
        返回:
            优化后的链接信息字典
        """
        info = {
            'vol_num': vol_num,
            'new_filename': new_filename,
            'original_file': original_file,
            'anchor': anchor
        }
        
        # 如果锚点是s开头且包含页码信息
        if anchor and anchor.startswith('s'):
            # 提取锚点中的页码
            anchor_match = re.match(r'^s(\d+)$', anchor)
            if anchor_match:
                anchor_page = anchor_match.group(1)
                # 提取新文件名中的页码
                filename_match = re.search(r'-(\d+)\.html$', new_filename)
                if filename_match:
                    filename_page = filename_match.group(1)
                    
                    # 如果锚点页码和新文件页码一致，则不需要锚点
                    if anchor_page == filename_page:
                        info['need_anchor'] = False
                        info['anchor_in_new_file'] = None
                    else:
                        info['need_anchor'] = True
                        info['anchor_in_new_file'] = anchor
                else:
                    info['need_anchor'] = True
                    info['anchor_in_new_file'] = anchor
            else:
                info['need_anchor'] = True
                info['anchor_in_new_file'] = anchor
        elif anchor:
            # 非s锚点，需要锚点
            info['need_anchor'] = True
            info['anchor_in_new_file'] = anchor
        else:
            # 没有锚点，指向文件开头
            info['need_anchor'] = False
            info['anchor_in_new_file'] = None
        
        return info
    
    def _find_anchors_in_content(self, content):
        """在内容中查找所有锚点"""
        soup = BeautifulSoup(content, 'html.parser')
        anchors = set()
        
        for tag in soup.find_all(id=True):
            anchor_id = tag.get('id')
            if anchor_id:
                anchors.add(anchor_id)
        
        for a_tag in soup.find_all('a'):
            if a_tag.get('id'):
                anchors.add(a_tag.get('id'))
        
        return anchors
    
    def _encode_with_bom(self, content):
        """使用UTF-8 BOM编码内容"""
        return content.encode('utf-8-sig')
    
    def _process_single_file(self, file_name):
        """处理单个HTML文件"""
        file_data = self.file_info[file_name]
        vol_num = file_data['vol_num']
        file_base = Path(file_name).stem
        
        splits = []
        if vol_num != 0:
            splits = self.file_splits.get(file_name, [])
            if not splits:
                return
        
        if vol_num == 0:
            file_name_html = re.sub(r".htm$", r".html", file_name)
            content = file_data['content']
            soup = BeautifulSoup(content, 'html.parser')
            self._update_all_links(soup, file_name, vol_num)
            title=soup.title.string if soup.title else file_base
            full_content = str(soup.body).replace('<body>', '').replace('</body>', '')
            full_content = re.sub(r'(<[^>]+?)/>', r'\1>', full_content, flags=re.DOTALL | re.IGNORECASE)
            full_html = self._create_full_html(full_content, title, 9999, None, None)
            for output_dir in self.output_dirs:
                output_path = Path(output_dir) / file_name_html
                output_path.write_text(full_html, encoding='utf-8-sig', newline='')
            return
        
        # 对于每个合并后的章节，创建独立的HTML文件
        i = 0
        while splits and i < len(splits):
            # 创建完整的HTML文档
            split = splits[i]
            vol_num = split['vol_num']
            # 更新链接
            soup = BeautifulSoup(split['content'], 'html.parser')
            self._update_all_links(soup, file_name, vol_num)
            full_content = str(soup)
            full_content = re.sub(r'(<[^>]+?)/>', r'\1>', full_content, flags=re.DOTALL | re.IGNORECASE)
            full_html = self._create_full_html(full_content, file_base, split['page_num'], 
                                               splits[i-1] if i > 0 else None, 
                                               splits[i+1] if i != len(splits)-1 else None)
            for output_dir in self.output_dirs:
                vol_path = Path(output_dir) / f"{vol_num}"
                vol_path.mkdir(exist_ok=True)
                output_path = vol_path / split['new_filename']
                output_path.write_text(full_html, encoding='utf-8-sig', newline='')
            i += 1
    
    def _create_full_html(self, chapter_content, file_base, page_num, prev, next):
        """创建完整的HTML文档"""
        click_link = ""
        if prev and next:
            click_link = f"""<div class="nav"><a href="{prev['new_filename']}">Назад</a> | <a href="index.html">СОДЕРЖАНИЕ</a> | <a href="{next['new_filename']}">Вперед</a></div>"""
        if next and not prev:
            click_link = f"""<div class="nav"><a href="index.html">СОДЕРЖАНИЕ</a> | <a href="{next['new_filename']}">Вперед</a></div>
<HR>"""
        if page_num == 0:
            page = "ПРЕДИСЛОВИЕ"
        else:
            page = f"{page_num}"
        if page_num != 9999:
            chapter_content = re.sub(r'<A HREF="pic/', r'<A HREF="../pic/', chapter_content, flags=re.DOTALL | re.IGNORECASE)
            chapter_content = re.sub(r'src="pic/', r'src="../pic/', chapter_content, flags=re.DOTALL | re.IGNORECASE)
            template = f'''<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ленин ПСС издание 5-ТОМ {file_base}-{page}</title>
<link rel="stylesheet" type="text/css" href="/vil.css">
<script src="/mlr.js"></script>
</head>
<body>
{click_link}
{chapter_content}
<HR>
{click_link}
</body>
</html>'''
        if page_num == 9999:
            template = f'''<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{file_base}</title>
<link rel="stylesheet" type="text/css" href="/vil.css">
<script src="/mlr.js"></script>
<body>
{chapter_content}
</body>
</html>'''
        return template
    
    def _update_all_links(self, soup, current_filename, vol_num):
        """更新soup中的所有链接"""
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            new_href = self._resolve_link(href, current_filename, vol_num)
            if new_href != href:
                a_tag['href'] = new_href
    
    def _resolve_link(self, link, current_filename, vol_num):
        """解析链接，返回更新后的链接"""
        if not link or link.startswith(('http://', 'https://', 'mailto:', 'tel:', 'javascript:', 'data:')):
            return link
        vol_back=''
        if vol_num>0:
            vol_back='../'        
        if link.startswith('#'):
            anchor = link[1:]
            key = f"{current_filename}#{anchor}"
            if key in self.anchor_to_file:
                anchor_info = self.anchor_to_file[key]
                target_file = anchor_info['new_filename']
                need_anchor = anchor_info.get('need_anchor', True)               
                if need_anchor:
                    if anchor_info['vol_num'] == vol_num:
                        return f"{target_file}#{anchor}"
                    else:
                        return f"{vol_back}{anchor_info['vol_num']}/{target_file}#{anchor}"
                else:
                    if anchor_info['vol_num'] == vol_num:
                        return target_file
                    else:
                        return f"{vol_back}{anchor_info['vol_num']}/{target_file}"
            return link
        
        # 解析带有锚点的链接
        if '.htm#' in link:
            file_part, anchor = link.split('.htm#', 1)
            file_part += '.htm'
        elif '.html#' in link:
            file_part, anchor = link.split('.html#', 1)
            file_part += '.htm'
        else:
            file_part, anchor = link, None
        
        # 处理外部引用（五位数编号的链接）
        if re.match(r'^[\d]{5}', file_part):
            link = file_part + 'l#' + anchor if anchor else file_part + 'l'
            return r'../' + link      
        if not file_part.endswith(('.html', '.htm')):
            return link
        target_file = Path(file_part).name     
        if anchor:
            key = f"{target_file}#{anchor}"
            if key in self.anchor_to_file:
                anchor_info = self.anchor_to_file[key]
                target_file_path = anchor_info['new_filename']
                need_anchor = anchor_info.get('need_anchor', True)                
                if need_anchor:
                    if anchor_info['vol_num'] == vol_num:
                        return f"{target_file_path}#{anchor}"
                    else:
                        return f"{vol_back}{anchor_info['vol_num']}/{target_file_path}#{anchor}"
                else:
                    if anchor_info['vol_num'] == vol_num:
                        return target_file_path
                    else:
                        return f"{vol_back}{anchor_info['vol_num']}/{target_file_path}"
        
        # 处理vilall.html的链接
        if current_filename == "vilall.html" or current_filename == "vilall.htm":
            vonm = re.match(r'^[0]*([\d]{1,2})\.htm[l]*$', file_part)
            vol_n = vonm.group(1) if vonm else None
            if vol_n:
                path = f'{vol_n}/index.html'
                return path
        
        if target_file in self.anchor_to_file:
            anchor_info = self.anchor_to_file[target_file]
            target_file_path = anchor_info['new_filename']
            need_anchor = anchor_info.get('need_anchor', False)
            
            if anchor:
                if need_anchor:
                    if anchor_info['vol_num'] == vol_num:
                        return f"{target_file_path}#{anchor}"
                    else:
                        return f"{vol_back}{anchor_info['vol_num']}/{target_file_path}#{anchor}"
                else:
                    if anchor_info['vol_num'] == vol_num:
                        return target_file_path
                    else:
                        return f"{vol_back}{anchor_info['vol_num']}/{target_file_path}"
            else:
                if anchor_info['vol_num'] == vol_num:
                    return target_file_path
                else:
                    return f"{vol_back}{anchor_info['vol_num']}/{target_file_path}"
        
        # 默认处理
        if anchor:
            return f"{file_part}l#{anchor}" if file_part.endswith('.htm') else f"{file_part}.html#{anchor}" if not file_part.endswith('.html') else f"{file_part}#{anchor}"
        else:
            return file_part + 'l' if file_part.endswith('.htm') else file_part + '.html' if not file_part.endswith('.html') else link
    
    def _extract_page_num(self, chapter_id, index):
        """从章节ID中提取页码"""
        if chapter_id and chapter_id.startswith('s'):
            match = re.search(r's(\d+)', chapter_id)
            if match:
                return match.group(1)
        return str(index + 1)
    
    def _find_all_anchors(self, soup):
        """查找soup中的所有锚点"""
        anchors = set()
        
        for tag in soup.find_all(id=True):
            anchor_id = tag.get('id')
            if anchor_id:
                anchors.add(anchor_id)
        
        for a_tag in soup.find_all('a'):
            if a_tag.get('id'):
                anchors.add(a_tag.get('id'))
        
        return anchors
    

def main():
    """主函数"""
    input_directory = Path("./VILo")
    output_folders = [Path("./MARX-ZH-CN.github.io1/ru/VIL-UAIO"), Path("./LENINPSS-HTML-FB2-SPLITED/ru/VIL-UAIO")]
    #output_folders = [Path("./VIL-UAIO")]
    
    if not input_directory.exists():
        print(f"输入目录不存在: {input_directory}")
        print("请创建目录并放入要处理的HTML文件")
        return
    
    # 设置最小文件大小为0.8KB
    processor = BatchHTMLSplitter(input_directory, output_folders, min_file_size_kb=0.8)
    processor.process_batch()

if __name__ == "__main__":
    main()