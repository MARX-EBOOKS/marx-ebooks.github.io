import re
from pathlib import Path
from typing import List, Tuple, Dict, Optional, NamedTuple
from dataclasses import dataclass, field
from bs4 import BeautifulSoup, Tag
import MEWbrief1 as MEWbrief

# ── Footnote dataclass：增加 extra_paras ──────────────────────

@dataclass
class Footnote:
    old_id: str
    old_ref: str
    old_label: str
    content: str
    extra_paras: List[str]
    fn_type: str
    page_num: int
    new_number: int = 0
    preserve_original: bool = False          # ← 新增

    @property
    def new_id(self) -> str:
        if self.preserve_original:
            return self.old_id               # 保留原 id，如 Ma
        return f"{self.fn_type}{self.new_number}"

    @property
    def new_ref(self) -> str:
        if self.preserve_original:
            return f"Z{self.old_id}"         # ZMa
        return f"Z{self.fn_type}{self.new_number}"

    @property
    def new_label(self) -> str:
        if self.preserve_original:
            # 剥去原有 [] 或 ()，统一改成 ()
            label = re.sub(r'^[\[\(]|[\]\)]$', '', self.old_label.strip())
            return f'({label})'
        if self.fn_type in ('M', 'E'):
            return f'({self.new_number})'
        return str(self.new_number)


class FootnoteManager:
    def __init__(self, volume: int = 0):
        self.volume = volume
        self.m_e_footnotes: List[Footnote] = []
        self.f_footnotes: List[Footnote] = []
        self._maps = {'M': {}, 'E': {}, 'F': {}}
        self._counters = {'M': 1, 'E': 1, 'F': 1}
        self._last_volume = None
        self.current_group_pages: Optional[set] = None

    def collect_from_page(self, soup: BeautifulSoup, page_num: int) -> None:
        asides = soup.find_all('aside')
        if not asides:
            return

        for aside in asides:
            groups: List[Tuple[Tag, List[Tag]]] = []
            cur_anchor: Optional[Tag] = None
            cur_paras:  List[Tag]     = []

            for p in aside.find_all(['p','table','blockquote'], recursive=False):
                a_tag = p.find('a', id=re.compile(r'^[MFE]([a-z0-9]+|\*)$'))
                if a_tag:
                    if cur_anchor is not None:
                        groups.append((cur_anchor, cur_paras))
                    cur_anchor = a_tag
                    cur_paras  = [p]
                elif cur_anchor is not None:
                    cur_paras.append(p)
            if cur_anchor is not None:
                groups.append((cur_anchor, cur_paras))

            for a_tag, paras in groups:
                old_id  = a_tag.get('id', '')
                fn_type = old_id[0]

                if (page_num, old_id) not in self._maps[fn_type]:
                    new_num = self._counters[fn_type]
                    self._maps[fn_type][(page_num, old_id)] = new_num
                    self._counters[fn_type] += 1

                    first_content, extra_paras = self._extract_content_multipara(a_tag, paras)
                    preserve_orig = (self.volume in range(23, 26) and fn_type in ('M', 'E')) 

                    fn = Footnote(
                        old_id      = old_id,
                        old_ref     = a_tag.get('href', '').lstrip('#'),
                        old_label   = a_tag.get_text(strip=True),
                        content     = first_content,
                        extra_paras = extra_paras,
                        fn_type     = fn_type,
                        page_num    = page_num,
                        new_number  = new_num,
                        preserve_original= preserve_orig,
                    )

                    if fn_type in ('M', 'E'):
                        self.m_e_footnotes.append(fn)
                    else:
                        self.f_footnotes.append(fn)
    def _extract_content_multipara(self, anchor_tag: Tag, paras: List[Tag]) -> Tuple[str, List[str]]:
        first_content = ""
        extra_paras: List[str] = []

        if paras[0].name == 'p':
            # 首行是 <p>，正常提取除锚点外的文本
            skipped = False
            parts = []
            for elem in paras[0].contents:
                if not skipped and isinstance(elem, Tag) \
                        and elem.name == 'a' \
                        and elem.get('id') == anchor_tag.get('id'):
                    skipped = True
                    continue
                parts.append(str(elem))
            first_content = ''.join(parts).strip()
            
            # 后续标签处理
            for p in paras[1:]:
                if p.name in ('div', 'blockquote', 'table'):
                    extra_paras.append(str(p))      # 保留外壳
                else:
                    extra_paras.append(p.decode_contents())  # <p> 等只取内部
        else:
            # 首行非 <p>（如 blockquote），首行当空，全部丢进 extra_paras
            for p in paras:
                if p.name in ('div', 'blockquote', 'table'):
                    extra_paras.append(str(p))      # 保留外壳
                else:
                    extra_paras.append(p.decode_contents())

        return first_content, extra_paras
    
    def _extract_content_after_link(self, p_tag: Tag) -> str:
        """Extracts everything inside the <p> except the initial anchor"""
        contents = []
        found_initial = False
        for elem in p_tag.contents:
            if not found_initial and isinstance(elem, Tag) and elem.name == 'a':
                found_initial = True
                continue
            contents.append(str(elem))
        return ''.join(contents).strip()

    def get_new_ref_data(self, fn_type: str, old_id: str, page_num: int) -> Optional[Tuple[str, str, str]]:
        """Used by both ContentReader and the internal content patcher"""
        new_num = self._maps[fn_type].get((page_num, old_id))
        if new_num is None:
            return None
        
        source = self.m_e_footnotes if fn_type in ('M', 'E') else self.f_footnotes
        for fn in source:
            if fn.new_number == new_num and fn.page_num == page_num and fn.fn_type == fn_type:
                return (fn.new_ref, fn.new_id, fn.new_label)
        return None

# ── FootnoteManager._patch_content_links ───────────────────────
#    脚注内部的交叉引用同样可能带 -N 后缀，剥去后做查找即可；
#    脚注内引用通常唯一，不重新添加后缀。

    def _patch_content_links(self, html_string: str, page_num: int) -> str:
        if '<a' not in html_string:
            return html_string

        content_soup = BeautifulSoup(html_string, 'html.parser')

        for a in content_soup.find_all('a', id=re.compile(r'^Z[MFE]([a-z0-9]+|\*)(-[\S]+)?$')):
            ref_id      = a.get('id', '')
            base_ref_id = re.sub(r'-\d+$', '', ref_id)
            f_type      = base_ref_id[1]
            o_id        = a.get('href', '').lstrip('#')

            new_data = self.get_new_ref_data(f_type, o_id, page_num)
            if new_data:
                a['id']    = new_data[0]
                a['href']  = f'#{new_data[1]}'
                a.string   = new_data[2]

        for a in content_soup.find_all('a', href=re.compile(r'^#[MFE]([a-z0-9]+|\*)$')):
            if a.get('id'):
                continue
            href_val = a.get('href', '').lstrip('#')
            if not href_val or href_val[0] not in ('M', 'F', 'E'):
                continue
            f_type = href_val[0]
            o_id   = href_val

            new_data = self.get_new_ref_data(f_type, o_id, page_num)
            if new_data:
                a['href']  = f'#{new_data[1]}'
                a.string   = new_data[2]

        return "".join([str(c) for c in content_soup.contents])

    def generate_footnotes_html(self) -> str:
        if not self.has_footnotes():
            return ""
        author_lines = []
        if self.m_e_footnotes:
            author_lines.append('<aside>\n<div class="fnt">Fußnoten</div>')

        for fn in self.m_e_footnotes:
            final_first = self._patch_content_links(fn.content, fn.page_num)
            final_first = self._process_refs(final_first)
            if '<div' in final_first or  '<blockquote' in final_first or  '<table' in final_first:
                author_lines.append(f'<p class="fni"><a id="{fn.new_id}" href="#{fn.new_ref}">{fn.new_label}</a></p>')
                author_lines.append(f'<div class="fni">{final_first}</div>')

            else:
                author_lines.append(f'<p class="fni"><a id="{fn.new_id}" href="#{fn.new_ref}">{fn.new_label}</a> {final_first}</p>')
            
            # 处理 extra_paras
            for ep in fn.extra_paras:
                patched_ep = self._patch_content_links(ep, fn.page_num)
                patched_ep = self._process_refs(patched_ep)
                # 直接判断字符串开头是不是这三个块级标签
                if patched_ep.lstrip().lower().startswith(('<div', '<blockquote', '<table')):
                    author_lines.append(patched_ep)            # 块级标签原样输出
                else:
                    author_lines.append(f'<p>{patched_ep}</p>') # 普通文本加 <p>
                    
        if self.m_e_footnotes and self.volume not in range(27,40):
            author_lines.append('</aside>')
            
        editor_lines = []
        if self.f_footnotes and self.volume not in range(27,40):
            editor_lines.append('<aside>\n<div class="fnt">Textvarianten</div>')
        elif (not self.m_e_footnotes) and self.f_footnotes and self.volume in range(27,40):
            editor_lines.append('<aside>\n<div class="fnt">Fußnoten</div>')

        for fn in self.f_footnotes:
            final_first = self._patch_content_links(fn.content, fn.page_num)
            final_first = self._process_refs(final_first)
            if final_first.endswith(" –"):
                final_first = final_first[:-2]
            editor_lines.append(f'<p class="fni"><a id="{fn.new_id}" href="#{fn.new_ref}">{fn.new_label}</a> {final_first}</p>')
            
            for ep in fn.extra_paras:
                patched_ep = self._patch_content_links(ep, fn.page_num)
                patched_ep = self._process_refs(patched_ep)
                if patched_ep.lstrip().lower().startswith(('<div', '<blockquote', '<table')):
                    editor_lines.append(patched_ep)
                else:
                    editor_lines.append(f'<p>{patched_ep}</p>')
                    
        if self.f_footnotes:
            editor_lines.append('</aside>')
        return '\n'.join(author_lines + editor_lines)

    def has_footnotes(self) -> bool:
        return len(self.m_e_footnotes) > 0 or len(self.f_footnotes) > 0


    def _find_page_group(self, volume: int, page: int) -> Optional[list]:
        try:
            return MEWbrief._page_group_map[volume].get(page)
        except (KeyError, TypeError):
            return None
    def _format_href(self, volume: int, start_page: int, group_start: int) -> str:
        """生成 href，自动处理本卷/跨卷路径与 26x 子卷格式"""
        if volume in range(261, 264):
            filename = f"ME26-{volume - 260}{group_start:03d}.html"
            dir_name = "26"
        else:
            filename = f"ME{volume:02d}-{group_start:03d}.html"
            dir_name = f"{volume}"
        # 同一组内直接只用锚点
        if volume == self.volume and self.current_group_pages and start_page in self.current_group_pages:
            if start_page!=group_start:
                return f"#S{start_page}"
            else:
                return ""
        if volume == self.volume:
            href = filename
        else:
            href = f"../{dir_name}/{filename}"
        if start_page != group_start:
            href += f"#S{start_page}"
        return href
    def pageinfo(self,match):
        page_num = int(match.group(2))
        group = self._find_page_group(self._last_volume, page_num)
        if group:
            href = self._format_href(self._last_volume, page_num, group[0])
            if match.group(1) and match.group(1).lower().startswith('s.'):
                pageaddnum = re.sub(r'([\d])\s*[-–]\s*([\d])',r'\1–\2',match.group(0))
                pageaddnum = re.sub(r'S\.([\d])',r'S. \1',pageaddnum)
                return f'<a href="{href}">{pageaddnum}</a>'
            else:
                pageaddnum=""
                if match.group(3):
                    pageaddnum = re.sub(r'([\d])\s*[-–]\s*([\d])',r'\1–\2',match.group(3))
                return f'{match.group(1)}<a href="{href}">{match.group(2)}{pageaddnum}</a>'
        return match.group(0)
    def _replace_ref(self,match):
        band = match.group(1)
        if band.lower().replace(' ','').replace('band,','') == 'vorl.':
            self._last_volume=self.volume
        elif band.lower().replace('band','').replace(' ','').isdigit():
            self._last_volume=int(band.lower().replace('band','').replace(' ',''))
        pagenum=re.sub(r'(S\.\s*|und\s+|,\s*)([\d]+)(\s*[-–/]\s*[\d]+)*',self.pageinfo,match.group(2),flags=re.IGNORECASE|re.DOTALL)

        return match.group(1)+ pagenum

    def _process_refs(self, text: str) -> str:
        if not text:
            return text
        text = re.sub(r"(vorl\. Band,[\s]*|Band [\d]+|ebenda,[\s]*)((?:(?!Band|siehe|vgl\.|note)[\s\S])+)",
            #r"(vorl\. Band,|Band [\d]+?|ebenda,) ((?:und [-–/\d]+|S\.[\s]*[-–/\d]+))+",
            #((?:(?!Band|siehe|vgl\.|note)[\s\S])+(?:und)*)(S.)*\s*([\d]+)([-–/\d]+)*",
            self._replace_ref,
            text,flags=re.IGNORECASE|re.DOTALL)
        return text

class ContentReader:
    def __init__(self, footnote_manager: FootnoteManager):
        self.fn_manager = footnote_manager
        # (fn_type, new_id_str) -> 已出现次数，如 ('F', 'F3') -> 2
        self._ref_occurrence_counter: Dict[Tuple[str, str], int] = {}

    def read_and_process_page(self, html_content:str, page_num: int):
        if not html_content: 
            return ""
        # 1. 收集脚注
        soup = BeautifulSoup(html_content, 'html.parser')
        self.fn_manager.collect_from_page(soup, page_num)

        body = soup.find('body')
        if not body: 
            return ''

        # 移除原始脚注区
        for aside in body.find_all('aside'):
            aside.decompose()

        # 2. 替换正文引用
        #    正则同时匹配  ZF1  和  ZF1-3  两种形式
        for a_tag in body.find_all('a', id=re.compile(r'^Z[MFE]([a-z0-9]+|\*)(-\d+)?$')):
            old_ref_id = a_tag.get('id', '')
            # 剥去旧后缀，取基础 id（如 ZF1-3 → ZF1）
            base_ref_id = re.sub(r'-\d+$', '', old_ref_id)
            fn_type = base_ref_id[1]            # M / F / E
            old_id  = a_tag.get('href', '').lstrip('#')  # 仍指向同一脚注锚点

            new_info = self.fn_manager.get_new_ref_data(fn_type, old_id, page_num)
            if not new_info:
                continue
            new_ref, new_id, new_label = new_info   # e.g. 'ZF3', 'F3', '3'

            # 按出现顺序决定后缀：第1次无后缀，第2次 -1，第3次 -2 …
            key   = (fn_type, new_id)
            count = self._ref_occurrence_counter.get(key, 0)
            self._ref_occurrence_counter[key] = count + 1

            a_tag['id']     = new_ref if count == 0 else f"{new_ref}-{count}"
            a_tag['href']   = f'#{new_id}'
            a_tag.string    = new_label

        return ''.join(str(child) for child in body.children).strip()


class PageMerger:
    """
    页面合并器
    负责管理整个合并流程
    """
    
    def __init__(self, volume: int, input_dir: Path, output_dir: Path):
        self.volume = volume
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.page_group = MEWbrief.page_group[volume]
    
    def _get_filename_for_page(self, page_num: int) -> Path:
        """根据页码生成文件路径"""
        if self.volume in range(261, 264):
            filename = f"ME26-{self.volume - 260}{page_num:03d}.html"
        else:
            filename = f"ME{self.volume:02d}-{page_num:03d}.html"
        return self.input_dir / filename
    
    def merge_group(self, group_idx: int, page_list: List[int]) -> Tuple[str, str]:
        """
        合并一个页码组
        返回: (合并后的HTML内容, 标题)
        """
        # 为该组创建新的脚注管理器
        fn_manager=FootnoteManager(self.volume)
        fn_manager.current_group_pages = set(page_list)
        content_reader = ContentReader(fn_manager)
        
        main_contents = []
        has_title =False
        title_temp=""

        
        for page_num in page_list:
            html_file = self._get_filename_for_page(page_num)
            if not html_file.exists():
                continue
            html_content=html_file.read_text(encoding='utf-8')
            # 读取并处理页面
            if self.volume in range(27,40):
                title_temp=self.get_title(html_content)

            page_content= content_reader.read_and_process_page(html_content, page_num)
            if page_content:
                # 添加页码标记
                if has_title:
                    if MEWbrief.mergepa[self.volume] and not page_num in MEWbrief.mergepa[self.volume]:
                        main_contents.append(f'\n<a id="S{page_num}"></a>\n')
                    else:
                        main_contents.append(f'\n<a id="S{page_num}" class="mergepa"></a>\n')
                else:
                    has_title = True
                main_contents.append(page_content)
        
        # 生成脚注HTML
        footnotes_html = fn_manager.generate_footnotes_html()
        start_page = page_list[0]
        end_page = page_list[-1]
        # 构建完整HTML
        merged_html= self._build_process_full_html('\n'.join(main_contents), 
                                           footnotes_html,title_temp,start_page,end_page)
        
        return merged_html
    def get_title(self,html_content:str) -> Optional[str]:
        """获取HTML文件的标题"""
        if not html_content:
            return None
        if self.volume in range(27,40):
            title_match=re.search(r"<title>([\S\r\n\s]+?)</title>",html_content,flags=re.IGNORECASE|re.DOTALL)
            if not title_match:
                print(html_content)
            title=title_match.group(1)
            title=re.sub(r"""^[\d]{1,4}[\s]*[·•][\s]*""",r"",title,flags=re.DOTALL|re.IGNORECASE)
            title=re.sub(r"""[\s]*[·•,][\s]*([\S\s]+?)$""",r" – \1", title,flags=re.DOTALL|re.IGNORECASE)
            title=re.sub(r"""[\s]*-[\s]+([\S\s]+?)$""",r" – \1", title,flags=re.DOTALL|re.IGNORECASE)
            return title
        soup = BeautifulSoup(html_content, 'html.parser')
        title_tag = soup.find(['h1','h2','h3','h4','h5','h6'])
        if title_tag:
            title=title_tag.get_text(strip=True,separator=" ")
            return title

        return None    

    def _build_process_full_html(self, body_content: str, 
                        footnotes_html: str,title_temp:str,start_page:int,end_page:int) -> str:
        """构建完整的HTML文档"""
        recontent=re.sub(r' style="(?:text-indent|margin-left): 2em;"',r'',body_content,flags=re.IGNORECASE|re.DOTALL)
        recontent=re.sub(r'''<div class="pa"></div>''',r"",recontent,flags=re.IGNORECASE|re.DOTALL)
        recontent=re.sub(r'''<br/>''',r"<br>",recontent,flags=re.IGNORECASE|re.DOTALL)
        recontent=re.sub(r'''[\s\r\n]*</p>[\s\r\n]+<(a id="S[\d]+") class="mergepa"></a>[\s\r\n]+<p>''',r" <\1></a>",recontent,flags=re.IGNORECASE|re.DOTALL)
        recontent=re.sub(r'''[\s\r\n]*</p>[\s\r\n]*</blockquote>[\s\r\n]+<(a id="S[\d]+") class="mergepa"></a>[\s\r\n]+<blockquote>[\s\r\n]*<p>''',r" <\1></a>",recontent,flags=re.IGNORECASE|re.DOTALL)
        recontent=re.sub(r'''[\s\r\n]*</blockquote>[\s\r\n]+<(a id="S[\d]+") class="mergepa"></a>[\s\r\n]+<blockquote>''',r" <\1></a>",recontent,flags=re.IGNORECASE|re.DOTALL)
        recontent=re.sub(r'''[\s\r\n]*</p>[\s\r\n]*</blockquote>[\s\r\n]+<(a id="S[\d]+") class="mergepa"></a>[\s\r\n]+<p>([\s\S]+?)</p>''',r" \1"+r"\2"+"</p></blockquote>",recontent,flags=re.IGNORECASE|re.DOTALL)
        
        recontent=re.sub(r"""([a-zA-Zßäöü,;])[\s\r\n]*</p>[\s\r\n]+(<a id="S[\d]+"></a>)[\s\r\n]+<p>""",r"\1 \2",recontent,flags=re.IGNORECASE|re.DOTALL)
        recontent=re.sub(r"""([a-zA-Zßäöü,;])(</i>)*[\s\r\n]*</p>[\s\r\n]+(<a id="S[\d]+"></a>)[\s\r\n]+<p>(<i>)*""",r"\1\2 \3\4",recontent,flags=re.IGNORECASE|re.DOTALL)
        recontent=re.sub(r"""([a-zA-Zßäöü,;](?:</i>)*)[\s\r\n]*(?:</p>)[\s\r\n]*?</blockquote>[\s\r\n]+(<a id="S[\d]+"></a>)[\s\r\n]+<blockquote>[\s\r\n]*?(?:<p>)((?:<i>)*[a-zA-Zßäöü])""",r"\1"+r"\2 \3",recontent,flags=re.IGNORECASE|re.DOTALL)
        #recontent=re.sub(r"""([a-zA-Zßäöü,;](?:</i>)*(?:</p>)[\s\r\n]*?)</blockquote>[\s\r\n]+(<a id="S[\d]+"></a>)[\s\r\n]+<blockquote>[\s\r\n]*?(?:<p>)(<i>)*""",r"\1</p>"+"\n"+r"\2<p>\3",recontent,flags=re.IGNORECASE|re.DOTALL)
        recontent=re.sub(r"""( [a-zA-Zßäöü]+?)-[\s\r\n]*</p>[\s\r\n]*?</blockquote>[\s\r\n]+(<a id="S[\d]+"></a>)[\s\r\n]+<p>([a-zA-Zßäöü][\S\s]+?</p>)""",r"\2\1"+r"\3</blockquote>",recontent,flags=re.IGNORECASE|re.DOTALL)
        #recontent=re.sub(r"""( [a-zA-Zßäöü,;]+-</i>)[\s\r\n]*</p>[\s\r\n]+(<a id="S[\d]+"></a>)[\s\r\n]+<p>""",r"\2 \1",recontent,flags=re.IGNORECASE|re.DOTALL)
        #recontent=re.sub(r"""</sup></p>[\s\r\n]+(<a id="S[\d]+"></a>)[\s\r\n]+<p>""",r"</sup> \1",recontent,flags=re.IGNORECASE|re.DOTALL)
        recontent=re.sub(r"""[\s\r\n]*</p>[\s\r\n]*</blockquote>[\s\r\n]+(<a id="S[\d]+"></a>)[\s\r\n]+<blockquote>[\s\r\n]*<p>""",r"</p>"+"\n"+r"\1"+"\n<p>",recontent,flags=re.IGNORECASE|re.DOTALL)
        recontent=re.sub(r"""([a-zA-Zßäöü,;](?:</i>)*)[\s\r\n]*</blockquote>[\s\r\n]+(<a id="S[\d]+"></a>)[\s\r\n]+<blockquote>""",r"\1 \2",recontent,flags=re.IGNORECASE|re.DOTALL)
        recontent=re.sub(r"""([a-zA-Zßäöü,;](?:</i>)*)[\s\r\n]*</blockquote>[\s\r\n]+(<a id="S[\d]+"></a>)[\s\r\n]+<p>((?:<i>)*[a-zA-Zßäöü][\s\S]+?)</p>""",r"\1 \2\3</blockquote>",recontent,flags=re.IGNORECASE|re.DOTALL)
        recontent=re.sub(r"""([a-zA-Zßäöü,;](?:</i>)*)[\s\r\n]*</p>[\s\r\n]*</blockquote>[\s\r\n]+(<a id="S[\d]+"></a>)[\s\r\n]+<p>((?:<i>)*[a-zA-Zßäöü][\s\S]+?)</p>""",r"\1 \2\3</blockquote>",recontent,flags=re.IGNORECASE|re.DOTALL)
        recontent=re.sub(r"""([a-zA-Zßäöü,;](?:</i>)*)</blockquote>[\s\r\n]+(<a id="S[\d]+"></a>)[\s\r\n]+<blockquote>""",r"\1 \2",recontent,flags=re.IGNORECASE|re.DOTALL)
        recontent=re.sub(r""" ([a-zA-Zßäöü,;]+)-[\s\r\n]*</p>[\s\r\n]+(<a id="S[\d]+"></a>)[\s\r\n]+<p>""",r"\2 \1",recontent,flags=re.IGNORECASE|re.DOTALL)
        recontent=re.sub(r""" ([\S]+?)-</i>[\s\r\n]*</p>[\s\r\n]+(<a id="S[\d]+"></a>)[\s\r\n]+<p><i>""",r"\2 \1",recontent,flags=re.IGNORECASE|re.DOTALL)
        recontent=re.sub(r""" ([\S]+?)-</i>[\s\r\n]*</p>[\s\r\n]+(<a id="S[\d]+"></a>)[\s\r\n]+<p>([\S\s]+?)([\.,]|<[^<>]+?>)""",r"\2 \1\3</i>\4",recontent,flags=re.IGNORECASE|re.DOTALL)
        recontent=re.sub(r""" ([\S]+?)-</i>[\s\r\n]*</p>[\s\r\n]+(<a id="S[\d]+"></a>)[\s\r\n]+<p>([\S]+?) """,r"\2 \1\3</i> ",recontent,flags=re.IGNORECASE|re.DOTALL)
        recontent=re.sub(r'''„([^<>]+?)"''',r'„\1“',recontent,flags=re.IGNORECASE|re.DOTALL)
        recontent=re.sub(r'''„((?:[^<>]+?<[^<]+?"[^<]+?">[\S ]+?</[\S]+?>)+?[^<>]+?)"''',r'„\1“',recontent,flags=re.IGNORECASE|re.DOTALL)
        if self.volume in range(261,264):
            recontent=re.sub(r"""<(?:p align="center"|h[\d](?: align="center")*)>((?:<i>)*[\[\d]+[\.\)\]]+[\S\s\r\n]+?)</(?:p|h[\d])>""",r"<h3>\1</h3>",recontent,flags=re.IGNORECASE|re.DOTALL)
            recontent=re.sub(r"""<(?:p align="center"|h[\d](?: align="center")*)>((?:<i>)*[\[a-k]+[\.\)\]]+[\S\s\r\n]+?)</(?:p|h[\d])>""",r"<h4>\1</h4>",recontent,flags=re.IGNORECASE|re.DOTALL)
            recontent=re.sub(r"""<(?:p align="center"|h[\d](?: align="center")*)>((?:<i>)*[\[\u03B1-\u03C9]+[\.\)\]]+[\S\s\r\n]+?)</(?:p|h[\d])>""",r"<h5>\1</h5>",recontent,flags=re.IGNORECASE|re.DOTALL)
            recontent=re.sub(r"\|\|[\s]*([\d]+?)\]",r"||\1|",recontent,flags=re.IGNORECASE|re.DOTALL) 
            recontent=re.sub(r"Ricardo\]",r"Ric[ardo]",recontent,flags=re.IGNORECASE|re.DOTALL)
            recontent=re.sub(r"\|\|[\s]*([\d]+?)\|\|",r"||\1|",recontent,flags=re.IGNORECASE|re.DOTALL)
        recontent=re.sub(r"</i>[\s\r\n]+<i>",r" ",recontent,flags=re.IGNORECASE|re.DOTALL)
        recontent=re.sub(r"\n{3,}","\n\n",recontent,flags=re.IGNORECASE|re.DOTALL)
        recontent=re.sub(r"""(<h[\d]) align="center">""",r"\1>",recontent,flags=re.DOTALL|re.IGNORECASE)
        recontent=re.sub(r"""<p>(?:<[\S]>)*(Aus dem [\S]+?en.)(?:</[\S]>)*</p>""",r"""<div class="que">\1</div>""",recontent,flags=re.DOTALL|re.IGNORECASE)
        recontent=re.sub(r"""<p>(Aus dem [\S]+?en und [\S]+?en.)</p>""",r"""<div class="que">\1</div>""",recontent,flags=re.DOTALL|re.IGNORECASE)
        if not self.volume in range(27,40):
            title=self.get_title(recontent)    
        if self.volume in range(261,264):
                vol=f"26.{self.volume-260}"
        else:
            vol=f"{self.volume}"
        if start_page==end_page:
            source=f"""<div class="que">Quelle: Marx/Engels: Werke, Bd. {vol}, Berlin: Dietz Verlag {MEWbrief.bookjahre[self.volume]}, S. {start_page}.</div>"""
        else:
            source=f"""<div class="que">Quelle: Marx/Engels: Werke, Bd. {vol}, Berlin: Dietz Verlag {MEWbrief.bookjahre[self.volume]}, S. {start_page}-{end_page}.</div>"""  
        recontent=re.sub(r"""<p[^<]*?>(?:<i>)*(Nach(?::[\s\r\n\S]+?| de[mr] (?:[\S]+?[ ]*){1,4}\.[\s\r\n]*(?:<br>[\S ]+?)*))[\s\r\n]*</p>""",r"""<div class="que">\1</div>""",recontent,flags=re.DOTALL|re.IGNORECASE)
        #recontent=re.sub(r"""<p(?: align="right")*>(Nach(?::[\s\r\n\S]+?| de[mr] (?:[\S]+?[ ]*){1,4}\.[\s\r\n]*(?:<br>Aus dem [\S]+?en.)*))[\s\r\n]*</p>""",r"""<div class="que">\1</div>""",recontent,flags=re.DOTALL|re.IGNORECASE)
        if self.volume in range(27,40):
            title=title_temp
            recontent=re.sub(r"""<(?:p align="center"|h[\d])>([\d]{1,4})</(?:p|h[\d])>[\s\r\n]+<h[\d]>([\S ]+?)</h[\d]>""",r"<h1>\1<br>\2</h1>",recontent,flags=re.DOTALL|re.IGNORECASE)
            recontent=re.sub(r"""<h[\d]>([\d]{1,4}<br>[\S ]+?)</h[\d]>[\s\r\n]+<(?:p align="center"|h[\d])>([\S ]{1,4})</(?:p|h[\d])>""",r"<h1>\1<br>\2</h1>",recontent,flags=re.DOTALL|re.IGNORECASE)
            recontent=re.sub(r"""<h[\d]>([\d]{4})<br>([\S ]+?)</h[\d]>""",r"""<h2>\1</h2>
<h1>\2</h1>""",recontent,flags=re.DOTALL|re.IGNORECASE)
            
            recontent=re.sub(r"""<p>((?:Meine|Lieber|Dear)(?: [\S]+?){1,4})<br>[\s\r\n]*""",r"""<p>\1</p>
<p>""",recontent,flags=re.DOTALL|re.IGNORECASE)
            return f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>{title}</title>
<link rel="stylesheet" type="text/css" href="../mewde.css"/>
</head>
<body>
{recontent}
{footnotes_html}
{source}
</body>
</html>'''
        if not title:
            title=f"MEW Band {self.volume}"
        recontent=re.sub(r"""<p(?:(?!right)[^<])*>([\[]*Karl Marx[\]]*|[\[]*Friedrich Engels[\]]*|[\[]*Karl Marx/Friedrich Engels[\]]*)</p>[\s\r\n]+<h[\d][^<]*?>([\s\S]+?)</h[\d]>""",r"<h1>\1<br>\2</h1>",recontent,flags=re.IGNORECASE|re.DOTALL)
        recontent=re.sub(r"<p[^<]*>(Geschrieben (?:[\S ]+?)*(?:[\s\r\n]*<br>[\S\s\r\n]+?)*)</p>",r"""<div class="que">\1</div>""",recontent,flags=re.DOTALL|re.IGNORECASE)
        recontent=re.sub(r'<div class="que">((?:(?!<div[^<]*?>)[\S\s\r\n])+?)</div>[\s\r\n]*<div class="que">',r'<div class="que">\1<br>',recontent,flags=re.IGNORECASE|re.DOTALL)
        title=re.sub(r"(Karl Marx|Friedrich Engels|Karl Marx/Friedrich Engels)[\s]+",r"\1 – ",title,flags=re.DOTALL|re.IGNORECASE)
        if self.volume in range(23,26):
            title=re.sub(r" (KAPITEL|ABSCHNITT) ",r" \1. ",title,flags=re.DOTALL|re.IGNORECASE)
        return f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>{title}</title>
<link rel="stylesheet" type="text/css" href="../mewde.css"/>
</head>
<body>
{recontent}
{footnotes_html}
{source}
</body>
</html>'''
    
    def run(self) -> None:
        """执行合并操作"""
        self.output_dir.mkdir(exist_ok=True, parents=True)
        
        print(f"处理第 {self.volume} 卷，共 {len(self.page_group)} 个组")
        index_content=""
        for group_idx, page_list in enumerate(self.page_group):
            if not page_list:
                continue
            
            start_page = page_list[0]
            end_page = page_list[-1]
            
            print(f"  处理组 {group_idx + 1}/{len(self.page_group)}: 页 {start_page}-{end_page}")
            
            # 合并页面
            merged_html= self.merge_group(group_idx, page_list)
            output_filename = f"ME{self.volume:02d}-{start_page:03d}.html"
            if self.volume in range(261, 264):
                output_filename = f"ME26-{self.volume - 260}{start_page:03d}.html"  
            index_content+=f'<a href="{output_filename}">{start_page}</a><br>\n'
            output_path = self.output_dir / output_filename
            output_path.write_text(merged_html, encoding='utf-8', newline='\n')
            
            print(f"    已保存: {output_filename}")
        if self.volume not in range(261,264):
            index_file=self.output_dir / "index.html"
            index_file.write_text(index_content, encoding='utf-8', newline='\n')
        print(f"\n完成！输出目录: {self.output_dir}")


def main():
    """主函数 - 程序入口"""
    # 配置
    #volumes = [261,262,263]
    #volumes = [263]
    #volumes=[5,6,7,8,23,24,25]
    #volumes=list(range(4,9))+list(range(16,26))+list(range(261,264))
    volumes =list(range(4,9))+list(range(16,26))+list(range(261,264))+list(range(27,40))
    #volumes = [23,24,25]
    volumes = [16]
    #volumes = [22]
    #volumes=range(27,40)
    for volume in volumes:
        input_dir = Path(f'./MEW_BRIEF/{volume}')
        #
        output_dir = Path(f'./MEWB1/{volume}')
        if volume in range(261,264):
            output_dir = Path(f'./MEWB1/26')
        merger = PageMerger(volume, input_dir, output_dir)
        merger.run()

if __name__ == "__main__":
    main()