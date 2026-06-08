import xml.etree.ElementTree as ET
from pathlib import Path
import urllib.parse
from typing import Dict, List, Tuple, Optional, Any, Set
import html
import re


class FB2ToHTMLSplitter:
    def __init__(self, fb2_file):
        self.tree = ET.parse(fb2_file)
        self.root = self.tree.getroot()
        # FB2命名空间
        self.ns = {'fb': 'http://www.gribuser.ru/xml/fictionbook/2.0',
                   'l': 'http://www.w3.org/1999/xlink'}
        # 存储二进制文件
        self.binaries = {}
        # 存储锚点映射
        self.anchor_map: Dict[str, Tuple[str, str]] = {}
        # 存储注释
        self.notes_map: Dict[str, Dict] = {}
        self.author_notes_map: Dict[str, Dict] = {}
        # 存储注释引用
        self.note_refs_map: Dict[str, List[Dict]] = {}
        self.author_note_refs_map: Dict[str, List[Dict]] = {}
        # 当前处理的卷号
        self.volume_num = ""
        self.current_file_info = {}
        # 存储每个section的标题和内容
        self.section_contents: Dict[str, Dict] = {}
        # 用于跟踪注释引用计数
        self.note_ref_counter = 1
        self.author_note_ref_counter = 1
        # 存储所有body元素
        self.bodies = {}
        # 存储叶子节点信息
        self.leaf_sections_info = []
        # 存储文件到引用ID的映射
        self.file_ref_map: Dict[str, List[Dict]] = {}
        # 存储叶子节点是否有标题的状态
        self.leaf_has_title = {}

    def set_volume_info(self, volume_num: str):
        """设置卷号信息"""
        self.volume_num = volume_num

    def get_book_info(self):
        """提取书籍基本信息"""
        desc = self.root.find('fb:description', self.ns)
        title_info = desc.find('fb:title-info', self.ns) if desc else None

        title = "未知书名"
        author = ""

        if title_info:
            title_elem = title_info.find('fb:book-title', self.ns)
            if title_elem is not None and title_elem.text:
                title = title_elem.text

            author_elem = title_info.find('fb:author', self.ns)
            if author_elem is not None:
                last = author_elem.find('fb:last-name', self.ns)
                first = author_elem.find('fb:first-name', self.ns)
                middle = author_elem.find('fb:middle-name', self.ns)
                last_name = last.text if last is not None and last.text else ""
                first_name = first.text if first is not None and first.text else ""
                middle_name = middle.text if middle is not None and middle.text else ""
                author = f"{last_name} {first_name} {middle_name}".strip()

        return {'title': title, 'author': author}
    
    def _extract_text(self, element):
        """递归提取元素的文本内容，在p标签之间添加空格"""
        if element is None:
            return ""
        
        text = element.text or ''
        for child in element:
            # 如果子元素是p标签，在其后添加空格作为分隔
            child_tag = child.tag.split('}')[-1]
            if child_tag == 'p':
                text += self._extract_text(child)
                text += ' '  # p标签之间用空格分隔
            else:
                text += self._extract_text(child)
            if child.tail:
                text += child.tail
        return text
    
    def _extract_binaries(self):
        """提取FB2中的二进制文件（图片等）"""
        import base64
        for binary in self.root.findall('fb:binary', self.ns):
            binary_id = binary.get('id', '')
            content_type = binary.get('content-type', 'image/jpeg')

            if binary.text:
                binary_data = binary.text.strip().replace('\n', '').replace('\r', '')
                self.binaries[binary_id] = {
                    'data': binary_data,
                    'content_type': content_type
                }

    # ==================== 新的处理算法 ====================

    def process_section_tree(self, section_element, parent_path="", depth=1, current_top_parent=None):
        """
        递归处理section树结构，将父节点内容合并到第一个叶子节点中
        
        参数:
            section_element: 当前section元素
            parent_path: 父节点路径
            depth: 当前深度
            
        返回:
            list: 处理后的叶子节点列表
        """
        leaf_sections = []
        
        # 生成当前section的唯一标识
        section_id = section_element.get('id', '')
        section_idx = len(self.section_contents)
        current_path = f"{parent_path}_{section_idx}"
        
        # 提取当前section的标题和内容
        title_elem = section_element.find('fb:title', self.ns)
        plain_title = ""
        if title_elem is not None:
            plain_title = self._extract_text(title_elem).strip()
        plain_title = re.sub(r"[\[\{][\d]+?[\]\}]", '', plain_title)
            
        # 提取当前section的直接内容（不包含子section）
        direct_content = self._extract_direct_content(section_element)
        
        # 存储当前section的信息
        self.section_contents[current_path] = {
            'element': section_element,
            'plain_title': plain_title,
            'title_elem': title_elem,
            'direct_content': direct_content,
            'depth': depth,
            'path': current_path,
            'parent_path': parent_path
        }
        
        # 查找当前section的所有直接子section
        child_sections = section_element.findall('fb:section', self.ns)
        
        # 跳过注释section
        valid_child_sections = []
        for child in child_sections:
            child_id = child.get('id', '')
            if child_id and (child_id.startswith('n-') or child_id.startswith('c-') or 
                            child_id.startswith('n_') or child_id.startswith('c_')):
                continue
            valid_child_sections.append(child)
        
        if not valid_child_sections:
            # 当前section本身就是叶子节点
            leaf_section_info = {
                'element': section_element,
                'path': current_path,
                'depth': depth,
                'plain_title': plain_title,
                'title_elem': title_elem,
                'section_id': section_id,
                'is_first_leaf': True,  # 标记为这个分支的第一个叶子节点
                'accumulated_content': [{
                    'path': current_path,
                    'plain_title': plain_title,
                    'title_elem': title_elem,
                    'direct_content': direct_content,
                    'depth': depth
                }],
                'top_parent_title': plain_title,  # 最上层父节点的标题
                'has_title': bool(plain_title.strip())  # 是否有标题
            }
            
            # 如果没有标题，记录为无标题叶子节点
            if not leaf_section_info['has_title']:
                leaf_section_info['has_title'] = False
                
            leaf_sections.append(leaf_section_info)
        else:
            # 有子section，递归处理每个子section
            for child_idx, child_section in enumerate(valid_child_sections):
                child_leaves = self.process_section_tree(
                    child_section, 
                    current_path, 
                    depth + 1
                )
                
                # 对于第一个子section的第一个叶子节点，需要添加当前section的内容
                if child_idx == 0 and child_leaves:
                    # 第一个子section的第一个叶子节点继承当前section的内容
                    first_child_leaf = child_leaves[0]

                    # 将当前section的内容添加到accumulated_content的开头
                    current_section_content = {
                        'path': current_path,
                        'plain_title': plain_title,
                        'title_elem': title_elem,
                        'direct_content': direct_content,
                        'depth': depth
                    }
                    
                    first_child_leaf['accumulated_content'].insert(0, current_section_content)
                    # 标记这个叶子节点需要包含祖先内容
                    first_child_leaf['needs_ancestor_content'] = True
                    # 更新最上层父节点标题
                    if re.match(r'[\d]{4}\s*г\.', plain_title):
                        first_child_leaf['top_parent_title'] = first_child_leaf['accumulated_content'][1]['plain_title']
                    else:
                        first_child_leaf['top_parent_title'] = plain_title
                        
                    # 更新是否有标题的状态
                    # 如果当前section有标题，那么第一个子叶子节点视为有标题
                    first_child_leaf['has_title'] = bool(plain_title.strip())
                    
                leaf_sections.extend(child_leaves)
        
        return leaf_sections
    
    def merge_titleless_leaves(self, leaf_sections):
        """
        合并无标题的叶子节点到前一个有标题的叶子节点中
        
        参数:
            leaf_sections: 叶子节点列表
            
        返回:
            list: 合并后的叶子节点列表
        """
        if not leaf_sections:
            return []
            
        merged_leaves = []
        i = 0
        
        while i < len(leaf_sections):
            current_leaf = leaf_sections[i]
            
            # 如果当前叶子节点有标题，直接添加到结果中
            if current_leaf.get('has_title', False):
                merged_leaves.append(current_leaf)
                i += 1
                continue
                
            # 当前叶子节点无标题，需要合并到前一个节点
            if merged_leaves:
                # 合并到前一个叶子节点
                previous_leaf = merged_leaves[-1]
                
                # 将当前叶子节点的内容添加到前一个叶子节点
                current_content = current_leaf.get('accumulated_content', [])
                previous_leaf['accumulated_content'].extend(current_content)
                
                # 更新合并标记
                if 'merged_from' not in previous_leaf:
                    previous_leaf['merged_from'] = []
                previous_leaf['merged_from'].append(i)
                
                # 标记为已合并
                previous_leaf['merged_titleless'] = True
                
                # 跳过当前叶子节点
                i += 1
            else:
                # 第一个叶子节点就无标题，无法合并到前一个节点，只能保留
                merged_leaves.append(current_leaf)
                i += 1
        
        return merged_leaves
    
    def calculate_leaf_content_size(self, leaf_info, current_filename=""):
        """
        Calculate the size of leaf content in bytes (excluding HTML structure)
        
        Returns:
            int: Size in bytes of the actual content
        """
        accumulated_content = leaf_info.get('accumulated_content', [])
        content_parts = []
        
        # Process accumulated content
        for content_item in accumulated_content:
            # Add title text
            item_html_title = content_item.get('title_elem')
            if item_html_title is not None:
                title_text = self._extract_text(item_html_title)
                content_parts.append(title_text)
            
            # Add content elements
            item_content_elements = content_item.get('direct_content', [])
            for elem in item_content_elements:
                # Extract text from element recursively
                elem_text = self._extract_text(elem)
                content_parts.append(elem_text)
        
        # Join all content and calculate byte size
        full_text = ''.join(content_parts)
        content_size = len(full_text.encode('utf-8'))
        
        return content_size
    
    def merge_small_leaves(self, leaf_sections, min_size_kb=2):
        """
        Merge consecutive small leaves to ensure each resulting leaf is at least min_size_kb
        
        Parameters:
            leaf_sections: List of leaf section info
            min_size_kb: Minimum size in KB (default 2KB)
        
        Returns:
            List of merged leaf sections
        """
        min_size_bytes = min_size_kb * 1024
        merged_leaves = []
        i = 0
        
        while i < len(leaf_sections):
            current_leaf = leaf_sections[i]
            current_size = self.calculate_leaf_content_size(current_leaf)
            
            # If current leaf is large enough, add it directly
            if current_size >= min_size_bytes:
                merged_leaves.append(current_leaf)
                i += 1
                continue
            
            # Current leaf is too small, try to merge with next leaves
            merged_leaf = {
                'element': current_leaf['element'],
                'path': current_leaf['path'],
                'depth': current_leaf['depth'],
                'plain_title': current_leaf['plain_title'],
                'title_elem': current_leaf['title_elem'],
                'section_id': current_leaf['section_id'],
                'is_first_leaf': current_leaf.get('is_first_leaf', True),
                'accumulated_content': current_leaf.get('accumulated_content', []).copy(),
                'top_parent_title': current_leaf.get('top_parent_title', current_leaf['plain_title']),
                'has_title': current_leaf.get('has_title', False),
                'merged_from': [i]  # Track which leaves were merged
            }
            
            total_size = current_size
            j = i + 1
            
            # Keep merging until we reach min_size or run out of leaves
            while j < len(leaf_sections) and total_size < min_size_bytes:
                next_leaf = leaf_sections[j]
                next_size = self.calculate_leaf_content_size(next_leaf)
                
                # Add next leaf's content to merged leaf
                next_accumulated = next_leaf.get('accumulated_content', [])
                merged_leaf['accumulated_content'].extend(next_accumulated)
                merged_leaf['merged_from'].append(j)
                
                # 如果合并的叶子节点有标题，更新标题信息
                if next_leaf.get('has_title', False):
                    merged_leaf['has_title'] = True
                    merged_leaf['plain_title'] = next_leaf.get('plain_title', '')
                
                total_size += next_size
                j += 1
            
            merged_leaves.append(merged_leaf)
            i = j
        
        return merged_leaves
    
    def _extract_direct_content(self, section_element):
        """
        提取section的直接内容（不包含子section）
        
        返回:
            list: 内容元素列表，每个元素是(p, blockquote, 等标签的HTML)
        """
        content_elements = []
        for elem in section_element:
            tag = elem.tag.split('}')[-1]
            if tag == 'title':
                continue
            elif tag == 'section':
                # 跳过子section
                continue
            else:
                content_elements.append(elem)
    
        return content_elements
    
    def _element_to_html_content(self, elem, current_filename, current_note_id=None, current_note_type=None):
        tag = elem.tag.split('}')[-1]
        
        if tag == 'p':
            text = self._paragraph_to_html(elem, current_filename, current_note_id, current_note_type)
            if text.strip():
                p_id = elem.get('id')
                if p_id and not p_id.startswith(('n-', 'c-', 'n_', 'c_')):
                    return f'<p id="{p_id}">{text}</p>\n'
                else:
                    return f"<p>{text}</p>\n"
            return ""
            
        elif tag == 'empty-line':
            return "<br/>\n"
            
        elif tag == 'epigraph':
            epigraph_html = ""
            for ep_elem in elem:
                ep_tag = ep_elem.tag.split('}')[-1]
                if ep_tag == 'p':
                    text = self._paragraph_to_html(ep_elem, current_filename, current_note_id, current_note_type)
                    epigraph_html += f"<p>{text}</p>\n"
                elif ep_tag == 'text-author':
                    text = self._paragraph_to_html(ep_elem, current_filename, current_note_id, current_note_type)
                    epigraph_html += f"<p><em>{text}</em></p>\n"
            return f'<blockquote>{epigraph_html}</blockquote>\n'
            
        elif tag == 'cite':
            cite_html = ""
            for cite_elem in elem:
                cite_tag = cite_elem.tag.split('}')[-1]
                if cite_tag == 'p':
                    text = self._paragraph_to_html(cite_elem, current_filename, current_note_id, current_note_type)
                    cite_html += f"<p>{text}</p>\n"
                elif cite_tag == 'text-author':
                    text = self._paragraph_to_html(cite_elem, current_filename, current_note_id, current_note_type)
                    cite_html += f"<p><em>{text}</em></p>\n"
                elif cite_tag == 'empty-line':
                    cite_html += "<br/>\n"
            return f'<blockquote>{cite_html}</blockquote>\n'
            
        elif tag == 'poem':
            poem_html = "<div class='poem'>\n"
            for poem_elem in elem:
                poem_tag = poem_elem.tag.split('}')[-1]
                if poem_tag == 'title':
                    title_text = self._title_to_html(poem_elem, current_filename, current_note_id, current_note_type)
                    poem_html += f"<p><strong>{title_text}</strong></p>\n"
                elif poem_tag == 'stanza':
                    poem_html += self._handle_stanza(poem_elem, current_filename, current_note_id, current_note_type)
                elif poem_tag == 'text-author':
                    text = self._paragraph_to_html(poem_elem, current_filename, current_note_id, current_note_type)
                    poem_html += f"<p><em>{text}</em></p>\n"
            poem_html += "</div>\n"
            return poem_html
            
        elif tag == 'stanza':
            return self._handle_stanza(elem, current_filename, current_note_id, current_note_type)
            
        elif tag == 'subtitle':
            text = self._paragraph_to_html(elem, current_filename, current_note_id, current_note_type)
            return f"<h4>{text}</h4>\n"
            
        elif tag == 'text-author':
            text = self._paragraph_to_html(elem, current_filename, current_note_id, current_note_type)
            return f"<p><em>{text}</em></p>\n"
            
        elif tag == 'image':
            return self._handle_image(elem, current_filename, current_note_id, current_note_type)
            
        elif tag == 'table':
            return self._handle_table(elem, current_filename, current_note_id, current_note_type)
            
        else:
            # 对于未知标签，递归处理其内容
            return f"<div>{self._paragraph_to_html(elem, current_filename, current_note_id, current_note_type)}</div>\n"

    def _handle_stanza(self, stanza_elem, current_filename, current_note_id=None, current_note_type=None):
        """处理诗节"""
        stanza_html = "<p class='stanza'>\n"
        for v_elem in stanza_elem:
            v_tag = v_elem.tag.split('}')[-1]
            if v_tag == 'v':
                text = self._paragraph_to_html(v_elem, current_filename, current_note_id, current_note_type)
                stanza_html += f"{text}<br/>\n"
            elif v_tag == 'empty-line':
                stanza_html += "<br/>\n"
        stanza_html += "</p>\n"
        return stanza_html

    def _handle_table(self, table_elem, current_filename, current_note_id=None, current_note_type=None):
        """处理表格"""
        table_html = "<table border='1'>\n"
        for tr_elem in table_elem:
            tr_tag = tr_elem.tag.split('}')[-1]
            if tr_tag == 'tr':
                table_html += "<tr>\n"
                for td_elem in tr_elem:
                    td_tag = td_elem.tag.split('}')[-1]
                    if td_tag in ['td', 'th']:
                        text = self._paragraph_to_html(td_elem, current_filename, current_note_id, current_note_type)
                        tag_name = 'th' if td_tag == 'th' else 'td'
                        table_html += f"<{tag_name}>{text}</{tag_name}>\n"
                table_html += "</tr>\n"
        table_html += "</table>\n"
        return table_html

    def _title_to_html(self, title_element, current_filename=None, current_note_id=None, current_note_type=None):
        """将title元素转换为HTML，正确处理p标签换行"""
        if title_element is None:
            return ""
        
        # 首先检查是否只有单个p标签包裹（没有其他内容）
        # 如果是，直接提取p标签内的内容，不添加<br>
        children = list(title_element)
        has_direct_text = bool((title_element.text or '').strip())
        
        # 过滤出p标签
        p_children = [child for child in children if child.tag.split('}')[-1] == 'p']
        non_p_children = [child for child in children if child.tag.split('}')[-1] != 'p']
        
        # 检查是否只有单个p标签且没有其他内容
        if len(p_children) == 1 and not has_direct_text and not non_p_children:
            # 只有单个p标签，直接提取其内容，不添加<br>
            single_p = p_children[0]
            p_content = ""
            if single_p.text:
                p_content += self.escape_html(single_p.text)
            
            for subchild in single_p:
                p_content += self.element_to_html(subchild, current_filename, current_note_id, current_note_type)
                if subchild.tail:
                    p_content += self.escape_html(subchild.tail)
            
            # 添加p标签后的tail文本（如果有）
            if single_p.tail:
                p_content += self.escape_html(single_p.tail)
            
            return p_content
        
        # 否则，按原来的逻辑处理多个p标签或混合内容
        html_content = ""
        
        # 处理title的直接文本
        if title_element.text:
            html_content += self.escape_html(title_element.text)
        
        # 处理title的子元素
        for child in title_element:
            tag = child.tag.split('}')[-1]  # 获取标签名（去掉命名空间）
            
            if tag == "p":
                # 处理p标签：提取内容并添加<br>
                p_content = ""
                if child.text:
                    p_content += self.escape_html(child.text)
                
                # 递归处理p标签内的子元素
                for subchild in child:
                    p_content += self.element_to_html(subchild, current_filename, current_note_id, current_note_type)
                    if subchild.tail:
                        p_content += self.escape_html(subchild.tail)
                
                # 添加p标签的内容
                if p_content.strip():
                    html_content += p_content
                    # 在p标签后添加<br>
                    html_content += "<br>"
            else:
                # 处理其他标签
                html_content += self.element_to_html(child, current_filename, current_note_id, current_note_type)
            
            # 处理tail文本
            if child.tail:
                html_content += self.escape_html(child.tail)
        
        return html_content

    def element_to_html(self, element, current_filename=None, 
                        current_note_id=None, current_note_type=None):
        """将FB2元素转换为HTML"""
        if element is None:
            return ""

        tag = element.tag.split('}')[-1]

        # 处理各种元素类型
        handlers = {
            'image': self._handle_image,
            'a': self._handle_link,
            'emphasis': self._handle_emphasis,
            'strong': self._handle_strong,
            'sup': self._handle_sup,
            'sub': self._handle_sub,
            'strikethrough': self._handle_strikethrough,
            'code': self._handle_code,
        }

        handler = handlers.get(tag)
        if handler:
            return handler(element, current_filename, current_note_id, current_note_type)
        
        # 默认处理：递归处理子元素
        result = element.text or ''
        for child in element:
            result += self.element_to_html(child, current_filename, 
                                         current_note_id, current_note_type)
            if child.tail:
                result += child.tail
        return result

    def _paragraph_to_html(self, p_element, current_filename=None, 
                          current_note_id=None, current_note_type=None):
        """将段落元素转换为HTML"""
        html_content = p_element.text or ''
        for child in p_element:
            html_content += self.element_to_html(child, current_filename, 
                                               current_note_id, current_note_type)
            if child.tail:
                html_content += self.escape_html(child.tail)
        
        return html_content

    # 以下是处理各种元素的函数
    def _handle_image(self, element, current_filename=None, current_note_id=None, current_note_type=None):
        """处理图片元素"""
        href = element.get('{http://www.w3.org/1999/xlink}href', '')
        image_id = href.lstrip('#')
        ext = '.jpg'
        
        if image_id in self.binaries:
            content_type = self.binaries[image_id]['content_type']
            ext_map = {
                'image/jpeg': '.jpg',
                'image/jpg': '.jpg',
                'image/png': '.png',
                'image/gif': '.gif',
                'image/bmp': '.bmp',
            }
            ext = ext_map.get(content_type, '.jpg')

        return f'<img src="images/{image_id}{ext}" alt="{image_id}" />'

    def _handle_link(self, element, current_filename, current_note_id, current_note_type):
        """处理链接元素"""
        href = element.get('{http://www.w3.org/1999/xlink}href', '')
        text = self._extract_text(element)
        
        if href.startswith('#'):
            return self._handle_internal_link(href, text, current_filename, 
                                            current_note_id, current_note_type)
        else:
            return f'<a href="{href}">{text}</a>'

    def _handle_internal_link(self, href, text, current_filename, 
                            current_note_id, current_note_type):
        """处理内部链接（锚点）"""
        anchor_id = href[1:]
        
        # 统一注释ID格式
        if anchor_id.startswith('n_'):
            anchor_id = 'n-' + anchor_id[2:]
        elif anchor_id.startswith('c_'):
            anchor_id = 'c-' + anchor_id[2:]
        
        # 处理注释链接
        if anchor_id.startswith('n-'):
            return self._handle_note_link(anchor_id, text, 'author_notes', 
                                        current_filename, current_note_id, 
                                        current_note_type)
        elif anchor_id.startswith('c-'):
            return self._handle_note_link(anchor_id, text, 'notes', 
                                        current_filename, current_note_id, 
                                        current_note_type)
        
        # 处理普通锚点
        if anchor_id in self.anchor_map:
            target_filename, target_title = self.anchor_map[anchor_id]
            if target_filename == current_filename:
                return f'<a href="#{anchor_id}">{text}</a>'
            else:
                safe_filename = urllib.parse.quote(target_filename)
                return f'<a href="{safe_filename}#{anchor_id}">{text}</a>'
        
        return f'<a href="{href}">{text}</a>'

    def _handle_note_link(self, note_id, text, note_type, current_filename, 
                         current_note_id, current_note_type):
        """处理注释链接"""
        if note_type == 'notes':
            refs_map = self.note_refs_map
            target_file = 'primechaniya.html'
            prefix = 'cref'
            ref_id = f"cref-{self.note_ref_counter}"
            self.note_ref_counter += 1
        else:
            refs_map = self.author_note_refs_map
            target_file = 'kommentariy.html'
            prefix = 'nref'
            ref_id = f"nref-{self.author_note_ref_counter}"
            self.author_note_ref_counter += 1
        
        # 记录引用信息
        if note_id not in refs_map:
            refs_map[note_id] = []
        
        ref_info = self._create_ref_info(note_id, ref_id, text, current_filename, 
                                       current_note_id, current_note_type)
        refs_map[note_id].append(ref_info)
        
        # 如果是正文中的引用，记录到文件引用映射中
        if current_filename and current_filename.startswith('VL'):
            if current_filename not in self.file_ref_map:
                self.file_ref_map[current_filename] = []
            self.file_ref_map[current_filename].append({
                'ref_id': ref_id,
                'note_id': note_id,
                'note_type': note_type,
                'link_text': text
            })
        
        return f'<sup><a href="{target_file}#{note_id}" id="{ref_id}">{text}</a></sup>'

    def _create_ref_info(self, note_id, ref_id, text, current_filename, 
                        current_note_id, current_note_type):
        """创建引用信息"""

        ref_info={}
        if current_filename and current_filename.startswith('VL'):
            # 来自正文的引用
            ref_info={            
                'ref_id': ref_id,
            'link_text': text,
            'note_id': note_id,
            'note_type': 'n-' if note_id.startswith('n-') else 'c-',
                'filename': current_filename,
                'file_title': self.current_file_info.get('title', ''),
                'source': 'text'
            }
        elif current_note_id and current_note_type:
            # 来自其他注释的引用
            if current_note_type == 'n-':
                source_file = 'kommentariy.html'
                source = "authornote"
                source_display = "Комментарии"
            else:
                source_file = 'primechaniya.html'
                source = "note"
                source_display = "ПРИМЕЧАНИЯ"
            
            ref_info={
                 'ref_id': ref_id,
                'link_text': text,
                    'note_id': note_id,
                'note_type': 'n-' if note_id.startswith('n-') else 'c-',
                'filename': source_file,
                'file_title': f"{source_display} {current_note_id[2:]}",
                'source': source,
                'source_note_id': current_note_id,
                'source_note_type': current_note_type
            }
        else:        
            ref_info = {
            'ref_id': ref_id,
            'link_text': text,
            'note_id': note_id,
            'note_type': 'n-' if note_id.startswith('n-') else 'c-',
            'source': 'unknown'
        }
        
        return ref_info

    # 其他处理函数
    def _handle_emphasis(self, element, *args):
        text = self._extract_text(element)
        return f'<em>{self.escape_html(text)}</em>'

    def _handle_strong(self, element, *args):
        text = self._extract_text(element)
        return f'<strong>{self.escape_html(text)}</strong>'

    def _handle_sup(self, element, *args):
        text = self._extract_text(element)
        return f'<sup>{self.escape_html(text)}</sup>'

    def _handle_sub(self, element, *args):
        text = self._extract_text(element)
        return f'<sub>{self.escape_html(text)}</sub>'

    def _handle_strikethrough(self, element, *args):
        text = self._extract_text(element)
        return f'<del>{self.escape_html(text)}</del>'

    def _handle_code(self, element, *args):
        text = self._extract_text(element)
        return f'<code>{self.escape_html(text)}</code>'

    def escape_html(self, text):
        """转义HTML特殊字符"""
        return html.escape(text or "")

    # ==================== 处理叶子节点 ====================

    def process_leaf_section(self, leaf_info, book_info, filename):
        """
        处理一个叶子section，生成HTML
        
        参数:
            leaf_info: 叶子结点信息
            book_info: 书籍信息
            filename: 输出文件名
        """
        element = leaf_info['element']
        plain_title = leaf_info['plain_title']
        section_id = leaf_info['section_id']
        accumulated_content = leaf_info.get('accumulated_content', [])
        top_parent_title = leaf_info.get('top_parent_title', plain_title)
        
        # 如果标题为空，尝试从内容中提取第一个段落作为标题
        if not top_parent_title.strip():
            # 从累计内容中查找第一个非空段落
            for content_item in accumulated_content:
                # 先检查标题元素
                if content_item.get('plain_title', '').strip():
                    top_parent_title = content_item['plain_title']
                    break
                
                # 再检查内容中的第一个段落
                for elem in content_item.get('direct_content', []):
                    if elem.tag.split('}')[-1] == 'p':
                        first_para_text = self._extract_text(elem).strip()
                        if first_para_text:
                            # 取前50个字符作为标题
                            top_parent_title = first_para_text[:50] + "..."
                            break
                if top_parent_title:
                    break
        
        self.current_file_info = {
            'filename': filename,
            'title': top_parent_title  # 使用合并后的标题
        }
        
        # 收集锚点
        self._collect_anchors(element, filename, top_parent_title)
        
        # 生成HTML内容
        html_parts = []
        
        # 处理积累的内容（父节点的内容）
        if accumulated_content:
            for content_item in accumulated_content:
                # 添加标题
                item_html_title = content_item.get('title_elem')
                item_depth = content_item.get('depth', 1)
                if item_html_title is not None:
                    html_title = self._title_to_html(item_html_title, filename)  # 传入 filename
                    if html_title:
                        html_parts.append(f'<h{min(item_depth, 6)}>{html_title}</h{min(item_depth, 6)}>')
                # 添加内容
                item_content_elements = content_item.get('direct_content', [])
                for elem in item_content_elements:
                    html_content = self._element_to_html_content(elem, filename)
                    if html_content:
                        html_parts.append(html_content)
        
        # 生成完整HTML文档
        html_content = self._create_html_document(
            top_parent_title, book_info['title'], html_parts
        )
        
        return top_parent_title, plain_title, html_content

    def _collect_anchors(self, element, filename, title):
        """收集元素中的所有锚点"""
        elem_id = element.get('id')
        if elem_id and not elem_id.startswith(('n-', 'c-', 'n_', 'c_')):
            self.anchor_map[elem_id] = (filename, title)
        
        for child in element:
            self._collect_anchors(child, filename, title)

    def _create_html_document(self, chapter_title, book_title, content_parts):
        """创建完整的HTML文档"""
        return f'''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>{chapter_title if chapter_title else ' '}</title>
</head>
<body>
{''.join(content_parts)}
</body>
</html>'''

    # ==================== 修改的注释提取逻辑 ====================

    def extract_notes_from_body(self, notes_body):
        """
        从notes body中提取所有注释
        
        支持两种结构：
        1. 扁平结构：body直接包含注释section
        2. 分层结构：body包含Примечания和Комментарии两个顶级section
        
        参数:
            notes_body: notes body元素
        """
        if not notes_body:
            print("警告: notes body 不存在")
            return
        
        print(f"开始提取注释，body名称: {notes_body.get('name')}")
        
        # 获取body的title
        body_title_elem = notes_body.find('fb:title', self.ns)
        body_title = ""
        if body_title_elem is not None:
            body_title = self._extract_text(body_title_elem).strip()
            print(f"Body标题: '{body_title}'")
        
        # 获取notes body下的所有section
        all_sections = notes_body.findall('fb:section', self.ns)
        print(f"找到 {len(all_sections)} 个section")
        
        if not all_sections:
            print("警告: notes body中没有找到任何section")
            return
        
        # 检查第一个section，判断结构类型
        first_section = all_sections[0]
        first_section_id = first_section.get('id', '')
        
        # 判断是否是扁平结构（直接是注释条目）
        # 注释条目的ID通常以 n- 或 c- 或 n_ 或 c_ 开头
        is_flat_structure = (
            first_section_id.startswith(('n-', 'c-', 'n_', 'c_')) or
            first_section_id.replace('_', '-').startswith(('n-', 'c-'))
        )
        
        if is_flat_structure:
            print("检测到扁平结构：body直接包含注释条目")
            # 扁平结构：根据body标题判断注释类型
            if "Примечания" in body_title:
                print(f"  -> 根据body标题识别为Примечания类型，将生成primechaniya.html")
                notes_type = 'author_notes'
            elif "Комментарии" in body_title:
                print(f"  -> 根据body标题识别为Комментарии类型，将生成kommentariy.html")
                notes_type = 'notes'
            else:
                # 默认根据第一个注释的ID判断
                if first_section_id.startswith(('c-', 'c_')):
                    print(f"  -> 根据注释ID识别为Комментарии类型（c-前缀），将生成primechaniya.html")
                    notes_type = 'notes'
                else:
                    print(f"  -> 根据注释ID识别为Примечания类型（n-前缀），将生成kommentariy.html")
                    notes_type = 'author_notes'
            
            # 直接提取所有section作为注释
            self._extract_notes_directly(all_sections, notes_type)
        else:
            print("检测到分层结构：body包含顶级分类section")
            # 分层结构：有Примечания和Комментарии两个顶级section
            for section in all_sections:
                # 检查section的标题
                title_elem = section.find('fb:title', self.ns)
                if title_elem is None:
                    print("警告: 找到没有标题的顶级section")
                    continue
                
                # 提取标题文本（会自动处理p标签）
                section_title = self._extract_text(title_elem).strip()
                print(f"处理顶级section: '{section_title}'")
                
                # 根据标题判断是哪种注释
                if "Примечания" in section_title:
                    print(f"  -> 识别为Примечания类型，将生成primechaniya.html")
                    self._extract_notes_from_section(section, 'author_notes')
                elif "Комментарии" in section_title:
                    print(f"  -> 识别为Комментарии类型，将生成kommentariy.html")
                    self._extract_notes_from_section(section, 'notes')
                else:
                    print(f"  -> 未识别的注释类型，标题为: '{section_title}'")

    def _extract_notes_directly(self, note_sections, notes_type):
        """
        直接从section列表提取注释（扁平结构）
        
        参数:
            note_sections: 注释section列表
            notes_type: 注释类型，'notes'或'author_notes'
        """
        print(f"在'{notes_type}'中找到 {len(note_sections)} 个注释")
        
        for note_section in note_sections:
            note_id = note_section.get('id', '')
            if not note_id:
                print("警告: 找到没有ID的注释section")
                continue
            
            print(f"处理{notes_type}注释: {note_id}")
            
            # 统一注释ID格式
            if note_id.startswith('n_'):
                note_id = 'n-' + note_id[2:]
            elif note_id.startswith('c_'):
                note_id = 'c-' + note_id[2:]
            
            # 提取注释标题
            title_elem = note_section.find('fb:title', self.ns)
            plain_title = ""
            html_title = ""
            
            if title_elem is not None:
                plain_title = self._extract_text(title_elem).strip()
                # 传递note相关参数
                current_filename = 'primechaniya.html' if notes_type == 'notes' else 'kommentariy.html'
                current_note_type = 'n-' if notes_type == 'author_notes' else 'c-'
                html_title = self._title_to_html(title_elem, current_filename, note_id, current_note_type)
            
            # 提取注释内容
            content_elements = []
            current_filename = 'primechaniya.html' if notes_type == 'notes' else 'kommentariy.html'
            current_note_type = 'n-' if notes_type == 'author_notes' else 'c-'
            
            for elem in note_section:
                tag = elem.tag.split('}')[-1]
                
                if tag == 'title':
                    continue
                elif tag == 'section':
                    # 注释中可能还有嵌套的section
                    sub_content = self._process_note_subsections(elem, notes_type, note_id)
                    content_elements.append(sub_content)
                else:
                    # 使用统一的元素处理方法，支持所有类型的标签
                    html_content = self._element_to_html_content(elem, current_filename, note_id, current_note_type)
                    if html_content:
                        content_elements.append(html_content)
            
            # 存储注释
            if notes_type == 'notes':
                self.notes_map[note_id] = {
                    'plain_title': plain_title,
                    'html_title': html_title,
                    'content': content_elements
                }
            else:
                self.author_notes_map[note_id] = {
                    'plain_title': plain_title,
                    'html_title': html_title,
                    'content': content_elements
                }
            
            print(f"成功提取{notes_type}注释 {note_id}: {plain_title[:50] if plain_title else '无标题'}...")

    def _extract_notes_from_section(self, section_element, notes_type):
        """
        从顶级section中提取注释
        
        参数:
            section_element: 顶级section元素
            notes_type: 注释类型，'notes'或'author_notes'
        """
        # 获取顶级section下的所有子section（这些就是注释）
        note_sections = section_element.findall('fb:section', self.ns)
        print(f"在'{notes_type}'中找到 {len(note_sections)} 个注释")
        
        for note_section in note_sections:
            note_id = note_section.get('id', '')
            if not note_id:
                print("警告: 找到没有ID的注释section")
                continue
            
            print(f"处理{notes_type}注释: {note_id}")
            
            # 统一注释ID格式
            if note_id.startswith('n_'):
                note_id = 'n-' + note_id[2:]
            elif note_id.startswith('c_'):
                note_id = 'c-' + note_id[2:]
            
            # 提取注释标题
            title_elem = note_section.find('fb:title', self.ns)
            plain_title = ""
            html_title = ""
            
            if title_elem is not None:
                plain_title = self._extract_text(title_elem).strip()
                # 传递note相关参数
                current_filename = 'primechaniya.html' if notes_type == 'notes' else 'kommentariy.html'
                current_note_type = 'n-' if notes_type == 'author_notes' else 'c-'
                html_title = self._title_to_html(title_elem, current_filename, note_id, current_note_type)
            
            # 提取注释内容
            content_elements = []
            current_filename = 'primechaniya.html' if notes_type == 'notes' else 'kommentariy.html'
            current_note_type = 'n-' if notes_type == 'author_notes' else 'c-'
            
            for elem in note_section:
                tag = elem.tag.split('}')[-1]
                
                if tag == 'title':
                    continue
                elif tag == 'section':
                    # 注释中可能还有嵌套的section
                    sub_content = self._process_note_subsections(elem, notes_type, note_id)
                    content_elements.append(sub_content)
                else:
                    # 使用统一的元素处理方法，支持所有类型的标签
                    html_content = self._element_to_html_content(elem, current_filename, note_id, current_note_type)
                    if html_content:
                        content_elements.append(html_content)
            
            # 存储注释
            if notes_type == 'notes':
                self.notes_map[note_id] = {
                    'plain_title': plain_title,
                    'html_title': html_title,
                    'content': content_elements
                }
            else:
                self.author_notes_map[note_id] = {
                    'plain_title': plain_title,
                    'html_title': html_title,
                    'content': content_elements
                }
            
            print(f"成功提取{notes_type}注释 {note_id}: {plain_title[:50] if plain_title else '无标题'}...")

    def _process_note_subsections(self, section_element, notes_type, parent_note_id):
        """处理注释中的子section"""
        html_parts = []
        
        current_filename = 'primechaniya.html' if notes_type == 'notes' else 'kommentariy.html'
        current_note_type = 'c-' if notes_type == 'notes' else 'n-'
        
        # 提取子section标题
        title_elem = section_element.find('fb:title', self.ns)
        if title_elem is not None:
            html_title = self._title_to_html(title_elem, current_filename, parent_note_id, current_note_type)
            html_parts.append(f'<h3>{html_title}</h3>')
        
        # 提取内容
        for elem in section_element:
            tag = elem.tag.split('}')[-1]
            
            if tag == 'title':
                continue
            else:
                # 使用统一的元素处理方法
                html_content = self._element_to_html_content(elem, current_filename, parent_note_id, current_note_type)
                if html_content:
                    html_parts.append(html_content)
        
        return ''.join(html_parts)
    
    def _generate_notes_html(self, output_path, book_info, notes_type):
        """生成注释HTML文件"""
        if notes_type == 'notes':
            notes_map = self.notes_map
            refs_map = self.note_refs_map
            filename = 'primechaniya.html'
            title = 'ПРИМЕЧАНИЯ'
            note_prefix = 'n-'
            note_display = "注释"
        else:
            notes_map = self.author_notes_map
            refs_map = self.author_note_refs_map
            filename = 'kommentariy.html'
            title = 'Комментарии'
            note_prefix = 'c-'
            note_display = "Комментарии"
        
        if not notes_map:
            print(f"没有找到{title}内容，不生成{filename}")
            return
        
        print(f"开始生成{filename}，共有{len(notes_map)}个{note_display}")
        
        # 生成注释内容
        content_parts = f'<h1>{title}</h1>\n'
        
        # 按注释ID排序（按数字顺序）
        def note_id_key(note_id):
            try:
                # 提取数字部分
                num_part = note_id.split('-')[1]
                return int(num_part)
            except:
                return 0
        
        sorted_note_ids = sorted(notes_map.keys(), key=note_id_key)
        
        for note_id in sorted_note_ids:
            note_info = notes_map[note_id]
            plain_title = note_info['plain_title']
            html_title = note_info['html_title']
            note_cont = note_info['content']
            note_content = ''.join(note_cont)
            # 添加注释标题
            note_num = note_id.split('-')[1] if '-' in note_id else note_id
            if html_title:
                # 保留html_title中的<br>标签，但移除多余的空格和换行
                note_text = html_title.replace('\n', '').strip()
                # 如果html_title以<br>结尾，去掉最后的<br>
                if note_text.endswith('<br>'):
                    note_text = note_text[:-4]
            else:
                note_text = f'{note_num}'
        
            if note_id in refs_map and refs_map[note_id]:

                ref_links = []
                for ref_info in refs_map[note_id]:
                    ref_id = ref_info['ref_id']
                    source = ref_info['source']
                    link_text = ref_info.get('link_text', '↑')
                    if source == 'text':
                        ref_filename = ref_info['filename']
                    if source == 'text':
                        # 来自正文的引用                    
                        ref_filename = ref_info['filename']
                        ref_title = ref_info.get('file_title', '')
                        # 这里使用ref_id作为锚点，确保能跳转到具体的引用点
                        ref_links.append([f'<a href="{ref_filename}#{ref_id}"', f'{ref_title} ({link_text})</a>'])
                    elif source == 'note':
                        # 来自其他普通注释的引用
                        source_note_id = ref_info.get('source_note_id', '')
                        source_note_num = source_note_id.split('-')[1] if '-' in source_note_id else source_note_id
                        # 这里使用ref_id作为锚点
                        ref_links.append([f'<a href="primechaniya.html#{ref_id}"', f'ПРИМЕЧАНИЯ {source_note_num} ({link_text})</a>'])
                    elif source == 'authornote':
                        # 来自作者注释的引用
                        source_note_id = ref_info.get('source_note_id', '')
                        source_note_num = source_note_id.split('-')[1] if '-' in source_note_id else source_note_id
                        # 这里使用ref_id作为锚点
                        ref_links.append([f'<a href="kommentariy.html#{ref_id}"', f'Комментарии {source_note_num} ({link_text})</a>'])
                
                if len(ref_links) == 1:
                    note_content='<p><sup>'+ref_links[0][0]+f' id="{note_id}">{note_text}</a></sup> '+ note_content[3:-5] +ref_links[0][0]+">↩</a>" +'</p>\n'
                elif len(ref_links) > 1:
                    note_content='<p><sup>'+ref_links[0][0]+f' id="{note_id}">{note_text}</a></sup> '+ note_content[3:-5] +'<br>'
                    note_content += 'Вернуться: '
                    for lin in ref_links:
                        note_content += '↩' + lin[0] + lin[1] + ' '
                    note_content+= '</p>'
            else:
                note_content = f'<p><a id="{note_id}">{note_text}</a> ' + note_content[3:-5] + '</p>\n'    
            content_parts += note_content
            #content_parts.append('<hr/>\n')
        
        # 生成完整HTML文档
        html_content = f'''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>{title} - {book_info['title']}</title>
</head>
<body>
{content_parts}
</body>
</html>'''
        
        with open(output_path / filename, 'w', encoding='utf-8-sig', newline='') as f:
            f.write(html_content)
        
        print(f"成功生成注释文件: {filename}")

    # ==================== 主要处理流程 ====================

    def split_to_html(self, output_dir='output'):
        """拆分FB2为多个HTML文件（按叶子结点）"""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)

        # 初始化
        self._extract_binaries()
        book_info = self.get_book_info()
        
        # 找到所有body
        bodies = self.root.findall('fb:body', self.ns)
        print(f"找到 {len(bodies)} 个body元素")
        
        main_body = None
        notes_body = None
        
        for body in bodies:
            body_name = body.get('name')
            print(f"body名称: '{body_name}'")
            
            if body_name == 'notes':
                notes_body = body
                self.bodies['notes'] = body
            elif body_name is None or body_name not in ['notes']:
                # 第一个没有name或name不是'notes'的body作为正文
                if main_body is None:
                    main_body = body
                    self.bodies['main'] = body
        
        if main_body is None and bodies:
            main_body = bodies[0]
            self.bodies['main'] = main_body
        
        if main_body is None:
            print("错误: 找不到正文body元素")
            return

        # 清空之前的映射
        self.anchor_map = {}
        self.notes_map = {}
        self.author_notes_map = {}
        self.note_refs_map = {}
        self.author_note_refs_map = {}
        self.section_contents = {}
        self.note_ref_counter = 1
        self.author_note_ref_counter = 1
        self.leaf_sections_info = []
        self.file_ref_map = {}

        # 处理整个section树（先确定HTML内容结构）
        leaf_sections = []
        
        # 处理body下的直接子section
        sections = main_body.findall('fb:section', self.ns)
        print(f"\n正文body有 {len(sections)} 个直接子section")
        
        for i, section in enumerate(sections):
            # 跳过注释section
            section_id = section.get('id', '')
            if section_id and (section_id.startswith('n-') or section_id.startswith('c-') or 
                              section_id.startswith('n_') or section_id.startswith('c_')):
                continue
            if i < 5:
                section_text = ''.join(section.itertext())
                if r"Пролетарии всех стран, соединяйтесь" in section_text and r"Издание пятое" in section_text:
                    continue
                elif i == 1 and r"Печатается по постановлению Центрального Комитета" in section_text:
                    continue
            
            # 递归处理section树
            section_leaves = self.process_section_tree(section, parent_path="body", depth=1)
            leaf_sections.extend(section_leaves)
        
        print(f"\n找到 {len(leaf_sections)} 个叶子结点section")
        
        # 第一步：合并无标题叶子节点
        print("\n合并无标题叶子结点...")
        merged_by_title = self.merge_titleless_leaves(leaf_sections)
        print(f"合并无标题结点后剩余 {len(merged_by_title)} 个叶子结点")
        
        # 第二步：合并小于2KB的叶子结点
        #print("\n合并小于2KB的叶子结点...")
        #merged_leaves = self.merge_small_leaves(merged_by_title, min_size_kb=2)
        #print(f"最终合并后剩余 {len(merged_leaves)} 个叶子结点")
        merged_leaves=merged_by_title
        self.leaf_sections_info = merged_leaves
        
        # 现在处理正文内容并生成HTML文件
        toc = []
        file_counter = 0
        
        print("\n开始提取注释并建立映射表...")
        self.extract_notes_from_body(notes_body)
        
        print(f"提取到 {len(self.notes_map)} 个普通注释 (Примечания)")
        print(f"提取到 {len(self.author_notes_map)} 个作者注释 (Комментарии)")
        
        for idx, leaf_info in enumerate(self.leaf_sections_info, 1):
            file_counter += 1
            filename = f"VL{self.volume_num}-G{file_counter:03d}.html"
            filepath = output_path / filename
            
            # 处理叶子节点并生成HTML
            display_title, html_title, html_content = self.process_leaf_section(
                leaf_info, book_info, filename
            )
            
            with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
                f.write(html_content)
            
            # 添加到目录
            depth = leaf_info['depth']
            indent = "    " * (depth - 1)
            parent_info = ""
            
            toc.append((file_counter, depth, parent_info, 
                       display_title, filename, indent))
            
            if idx % 10 == 0:
                print(f"已处理 {idx}/{len(self.leaf_sections_info)} 个叶子结点")
        
        # 保存二进制文件
        self._save_binaries(output_path)
        
        # 生成注释文件
        print("\n生成注释文件...")
        self._generate_notes_html(output_path, book_info, 'notes')
        self._generate_notes_html(output_path, book_info, 'author_notes')
        
        # 生成目录
        self._generate_toc(output_path, toc, book_info)
        
        print(f"\n完成! 共生成 {file_counter} 个HTML文件")

    def _save_binaries(self, output_path):
        """保存二进制文件"""
        if not self.binaries:
            return

        images_dir = output_path / 'images'
        images_dir.mkdir(exist_ok=True)

        import base64
        for binary_id, binary_info in self.binaries.items():
            ext_map = {
                'image/jpeg': '.jpg',
                'image/jpg': '.jpg',
                'image/png': '.png',
                'image/gif': '.gif',
                'image/bmp': '.bmp',
            }
            ext = ext_map.get(binary_info['content_type'], '.bin')
            filename = f"{binary_id}{ext}"
            filepath = images_dir / filename

            try:
                binary_data = base64.b64decode(binary_info['data'])
                with open(filepath, 'wb') as f:
                    f.write(binary_data)
            except Exception as e:
                print(f"保存图片失败 {filename}: {e}")

    def _generate_toc(self, output_path, toc, book_info):
        """生成目录"""
        toc_html = f'''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>СОДЕРЖАНИЕ - {book_info['title']}</title>
</head>
<body>
<h1>{book_info['title']}</h1>
<h2>СОДЕРЖАНИЕ</h2>
<ul>
'''

        for idx, depth, parent_info, title, filename, indent in toc:
            toc_html += f'{indent}<li><a href="{filename}">{title}</a> {parent_info}</li>\n'

        toc_html += '''</ul>
'''
        if self.author_notes_map:
            toc_html += '<p><a href="kommentariy.html">Комментарии</a></p>\n'
        if self.notes_map:
            toc_html += '<p><a href="primechaniya.html">ПРИМЕЧАНИЯ</a></p>\n'


        toc_html += '''</body>
</html>'''

        with open(output_path / 'index.html', 'w', encoding='utf-8-sig', newline='') as f:
            f.write(toc_html)

        print(f"目录页: index.html")


def all_fb2(input_dir):
    """批量处理FB2文件"""
    fb2_files = list(Path(input_dir).glob("*.fb2"))
    output_path = Path("./vilpss-ch")
    output_path.mkdir(exist_ok=True)

    print(f"找到 {len(fb2_files)} 个FB2文件")

    for fb2 in fb2_files:
        # 提取卷号
        volume_num = fb2.name.replace(".fb2", "").replace("pss_vil_", "")
        print(f"\n处理第 {volume_num} 卷: {fb2.name}")

        # 创建分卷处理器
        splitter = FB2ToHTMLSplitter(fb2)
        splitter.set_volume_info(volume_num)

        # 创建输出目录
        output_dir = output_path / volume_num
        output_dir.mkdir(exist_ok=True)

        # 按叶子结点拆分
        splitter.split_to_html(output_dir=output_dir)


if __name__ == '__main__':
    # 处理所有FB2文件
    all_fb2(r'./pssvil')