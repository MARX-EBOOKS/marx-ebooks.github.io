from zai import ZhipuAiClient
import requests as rq, base64
from openai import OpenAI
from bs4 import BeautifulSoup
import re
from pathlib import Path
import json
def divide_html_by_bytes(filepaths, max_bytes=4000):
    """
    按标题分割HTML内容，并按字节大小切割超过阈值的部分
    :param filepaths: HTML文件路径列表
    :param max_bytes: 每个部分的最大字节大小（默认4000字节）
    :return: (原始标题, 切割后的HTML内容列表)
    """
    all_bodies = []
    
    # 读取所有文件的body内容
    for filepath in filepaths:
        file_path = Path(filepath)
        with open(file_path, 'r', encoding='utf-8-sig') as file:
            html_content = file.read()
        soup = BeautifulSoup(html_content, 'html.parser')
        
        body_tag = soup.find('body')
        if body_tag:
            body_content = str(body_tag).replace("<body>", "").replace("</body>", "")
            all_bodies.append(body_content)
    
    # 合并所有body内容
    full_body = '\n'.join(all_bodies)
    
    # 解析合并后的内容
    soup_body = BeautifulSoup(full_body, 'html.parser')
    
    # 获取所有直接子元素
    all_elements = [elem for elem in soup_body.children if elem and elem != '\n']
    
    if not all_elements:
        # 如果没有内容，返回空结果
        original_soup = BeautifulSoup(
            open(filepaths[0], 'r', encoding='utf-8-sig').read(), 'html.parser'
        )
        original_title = str(original_soup.find('title')) if original_soup.find('title') else '<title>No Title</title>'
        return original_title, ['<body></body>']
    
    # 查找标题元素的位置
    header_indices = []
    for i, elem in enumerate(all_elements):
        if hasattr(elem, 'name') and elem.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            header_indices.append(i)
    
    sections = []
    
    if not header_indices:
        # 没有标题，将全部内容作为一个section
        full_content = ''.join(str(elem) for elem in all_elements)
        sections.append(full_content)
    else:
        # 将相邻的标题合并处理
        grouped_headers = []
        current_group = []
        
        for i, idx in enumerate(header_indices):
            if i == 0:
                current_group.append(idx)
            else:
                # 检查当前标题是否与上一个标题相邻
                prev_idx = header_indices[i-1]
                is_adjacent = True
                
                # 检查两个标题之间是否只有其他标题
                for j in range(prev_idx + 1, idx):
                    if j < len(all_elements) and hasattr(all_elements[j], 'name') and \
                       all_elements[j].name not in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                        is_adjacent = False
                        break
                
                if is_adjacent:
                    # 如果相邻（中间没有非标题元素），加入当前组
                    current_group.append(idx)
                else:
                    # 如果不相邻，保存当前组并开始新组
                    if current_group:
                        grouped_headers.append(current_group)
                    current_group = [idx]
        
        # 添加最后一组
        if current_group:
            grouped_headers.append(current_group)
        
        # 处理每个标题组合，按顺序处理文档内容
        processed_up_to = 0
        
        for group in grouped_headers:
            # 收集组内的所有标题和它们之间的内容
            section_parts = []
            
            for i, header_idx in enumerate(group):
                # 添加从上次处理位置到当前标题的内容（如果有的话）
                if header_idx > processed_up_to:
                    for idx in range(processed_up_to, header_idx):
                        if idx < len(all_elements):
                            section_parts.append(str(all_elements[idx]))
                
                # 添加当前标题
                section_parts.append(str(all_elements[header_idx]))
                
                # 计算当前标题之后的内容
                content_start = header_idx + 1
                
                # 如果不是组内最后一个标题，则到下一个组内标题为止
                # 如果是组内最后一个标题，则到下一个组的第一个标题或文档结尾
                content_end = len(all_elements)  # 默认到文档结尾
                
                if i < len(group) - 1:
                    # 组内下一个标题
                    content_end = group[i + 1]
                else:
                    # 如果是组内最后一个标题，检查是否还有其他组
                    next_group_exists = False
                    for next_group in grouped_headers:
                        if next_group[0] > group[-1]:  # 找到第一个在当前组之后的组
                            content_end = next_group[0]
                            next_group_exists = True
                            break
                    
                    # 如果没有更多组，则到文档结尾
                
                # 添加标题后的非标题内容
                for idx in range(content_start, content_end):
                    if idx < len(all_elements) and hasattr(all_elements[idx], 'name') and \
                       all_elements[idx].name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                        # 跳过标题（这些会在后续组中处理）
                        continue
                    elif idx < len(all_elements):
                        section_parts.append(str(all_elements[idx]))
                
                # 更新已处理位置
                processed_up_to = content_end if i == len(group) - 1 else group[i + 1]
            
            # 将这个组合的内容添加到sections
            if section_parts:
                sections.append(''.join(section_parts))
        
        # 处理最后剩余的内容（如果有的话）
        if processed_up_to < len(all_elements):
            remaining_parts = []
            for idx in range(processed_up_to, len(all_elements)):
                elem = all_elements[idx]
                # 不包括标题，因为标题应该已经在前面的组中处理了
                if hasattr(elem, 'name') and elem.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    continue
                else:
                    remaining_parts.append(str(elem))
            
            if remaining_parts:
                sections.append(''.join(remaining_parts))
    
    # ===== 新增功能：按字节大小切割超过阈值的部分 =====
    new_sections = []
    for section in sections:
        # 按字节大小切割
        current = section
        while len(current.encode('utf-8')) > max_bytes:
            # 尝试在字节阈值后找到最近的</p>或<br>标签
            s_bytes = current.encode('utf-8')
            cut_pos = max_bytes
            
            # 搜索</p>标签 (4字节)
            pos_p = s_bytes.find(b'</p>', max_bytes)
            pos_quote = s_bytes.find(b'</blockquote>', max_bytes)
            # 搜索<br>标签 (4字节)
            pos_br = s_bytes.find(b'<br>', max_bytes)
            
            # 选择最近的标签位置
            if pos_p != -1 and pos_quote != -1:
                cut_pos = min(pos_p, pos_quote)
            elif pos_p != -1 and pos_br != -1:
                cut_pos = min(pos_p, pos_br)
            elif pos_p != -1:
                cut_pos = pos_p
            elif pos_br != -1:
                cut_pos = pos_br
            
            # 确保切割点在有效范围内
            cut_pos = max(max_bytes, cut_pos)
            cut_pos = min(cut_pos, len(s_bytes))
            
            # 切割部分
            part1 = current[:cut_pos]
            part2 = current[cut_pos:]
            
            # 添加切割部分（确保不为空）
            if part1.strip():
                new_sections.append(part1)
            current = part2
        
        # 添加剩余部分
        if current.strip():
            new_sections.append(current)
    
    sections = new_sections
    # ===================================================
    
    original_soup = BeautifulSoup(
        open(filepaths[0], 'r', encoding='utf-8-sig').read(), 'html.parser'
    )
    original_title = str(original_soup.find('title')) if original_soup.find('title') else '<title>No Title</title>' 
    
    # 构建contents数组
    contents = []
    for i, section in enumerate(sections):
        final_content = '<body>\n' + section.strip() + '\n</body>'
        contents.append(final_content)
    
    return original_title, contents
def divide_html_by_headings(filepaths):
    """
    增强版函数，更准确地按标题拆分内容
    """
    all_bodies = []
    
    # 读取所有文件的body内容
    for filepath in filepaths:
        file_path = Path(filepath)
        with open(file_path, 'r', encoding='utf-8-sig') as file:
            html_content = file.read()
        soup = BeautifulSoup(html_content, 'html.parser')
        
        body_tag = soup.find('body')
        if body_tag:
            body_content = str(body_tag).replace("<body>", "").replace("</body>", "")
            all_bodies.append(body_content)
    
    # 合并所有body内容
    full_body = '\n'.join(all_bodies)
    
    # 解析合并后的内容
    soup_body = BeautifulSoup(full_body, 'html.parser')
    
    # 获取所有直接子元素
    all_elements = [elem for elem in soup_body.children if elem and elem != '\n']
    
    if not all_elements:
        # 如果没有内容，返回空结果
        original_soup = BeautifulSoup(
            open(filepaths[0], 'r', encoding='utf-8-sig').read(), 'html.parser'
        )
        original_title = str(original_soup.find('title')) if original_soup.find('title') else '<title>No Title</title>'
        return original_title, ['<body></body>']
    
    # 查找标题元素的位置
    header_indices = []
    for i, elem in enumerate(all_elements):
        if hasattr(elem, 'name') and elem.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            header_indices.append(i)
    
    sections = []
    
    if not header_indices:
        # 没有标题，将全部内容作为一个section
        full_content = ''.join(str(elem) for elem in all_elements)
        sections.append(full_content)
    else:
        # 将相邻的标题合并处理
        grouped_headers = []
        current_group = []
        
        for i, idx in enumerate(header_indices):
            if i == 0:
                current_group.append(idx)
            else:
                # 检查当前标题是否与上一个标题相邻
                prev_idx = header_indices[i-1]
                is_adjacent = True
                
                # 检查两个标题之间是否只有其他标题
                for j in range(prev_idx + 1, idx):
                    if j < len(all_elements) and hasattr(all_elements[j], 'name') and \
                       all_elements[j].name not in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                        is_adjacent = False
                        break
                
                if is_adjacent:
                    # 如果相邻（中间没有非标题元素），加入当前组
                    current_group.append(idx)
                else:
                    # 如果不相邻，保存当前组并开始新组
                    if current_group:
                        grouped_headers.append(current_group)
                    current_group = [idx]
        
        # 添加最后一组
        if current_group:
            grouped_headers.append(current_group)
        
        # 处理每个标题组合，按顺序处理文档内容
        processed_up_to = 0
        
        for group in grouped_headers:
            # 收集组内的所有标题和它们之间的内容
            section_parts = []
            
            for i, header_idx in enumerate(group):
                # 添加从上次处理位置到当前标题的内容（如果有的话）
                if header_idx > processed_up_to:
                    for idx in range(processed_up_to, header_idx):
                        if idx < len(all_elements):
                            section_parts.append(str(all_elements[idx]))
                
                # 添加当前标题
                section_parts.append(str(all_elements[header_idx]))
                
                # 计算当前标题之后的内容
                content_start = header_idx + 1
                
                # 如果不是组内最后一个标题，则到下一个组内标题为止
                # 如果是组内最后一个标题，则到下一个组的第一个标题或文档结尾
                content_end = len(all_elements)  # 默认到文档结尾
                
                if i < len(group) - 1:
                    # 组内下一个标题
                    content_end = group[i + 1]
                else:
                    # 如果是组内最后一个标题，检查是否还有其他组
                    next_group_exists = False
                    for next_group in grouped_headers:
                        if next_group[0] > group[-1]:  # 找到第一个在当前组之后的组
                            content_end = next_group[0]
                            next_group_exists = True
                            break
                    
                    # 如果没有更多组，则到文档结尾
                
                # 添加标题后的非标题内容
                for idx in range(content_start, content_end):
                    if idx < len(all_elements) and hasattr(all_elements[idx], 'name') and \
                       all_elements[idx].name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                        # 跳过标题（这些会在后续组中处理）
                        continue
                    elif idx < len(all_elements):
                        section_parts.append(str(all_elements[idx]))
                
                # 更新已处理位置
                processed_up_to = content_end if i == len(group) - 1 else group[i + 1]
            
            # 将这个组合的内容添加到sections
            if section_parts:
                sections.append(''.join(section_parts))
        
        # 处理最后剩余的内容（如果有的话）
        if processed_up_to < len(all_elements):
            remaining_parts = []
            for idx in range(processed_up_to, len(all_elements)):
                elem = all_elements[idx]
                # 不包括标题，因为标题应该已经在前面的组中处理了
                if hasattr(elem, 'name') and elem.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    continue
                else:
                    remaining_parts.append(str(elem))
            
            if remaining_parts:
                sections.append(''.join(remaining_parts))
    original_soup = BeautifulSoup(
        open(filepaths[0], 'r', encoding='utf-8-sig').read(), 'html.parser'
    )
    original_title = str(original_soup.find('title')) if original_soup.find('title') else '<title>No Title</title>' 
    # 构建contents数组
    contents = []
    for i,section in enumerate(sections):
        final_content ='<body>\n' + section.strip() + '\n</body>'
        contents.append(final_content)
    return original_title,contents
def save_htmlcontent(title,filepath,filename,contents):
    """
    把ai翻译、处理后的内容保存成完整的html文件，即补全html标签，以及加入css样式表。
    """
    Path(filepath).mkdir(parents=True, exist_ok=True)
    content_finalout = f'''<html lang="zh-CN">
    <head>
    <META name="viewport" content="width=device-width, initial-scale=1.0"/>
    <META content="text/html; charset=UTF-8" http-equiv="Content-Type"/>
    <title>{title}</title>
    <link rel="stylesheet" type="text/css" href="styles.css"/>
    </head>
    <body>'''
    for content in contents:
        content=re.sub(r'<body>',r'',content,flags=re.IGNORECASE|re.DOTALL)
        content=re.sub(r'</body>',r'',content,flags=re.IGNORECASE|re.DOTALL)
        content_finalout+=content
    content_finalout+='\n</body>\n</html>'
    file_path = Path(filepath)/filename
    with open(file_path, 'w', encoding='utf-8-sig',newline='\r\n') as file:
        file.write(content_finalout)
def useapi_OPENAI_form(file_content):
    """
    调用ai的api借口
    """
    client = OpenAI(
  base_url = "https://integrate.api.nvidia.com/v1",
  api_key = "nvapi-xxxxxx"
)
    print("正在调用AI接口，请稍等...") 
    completion = client.chat.completions.create(
   model="z-ai/glm5",
  messages=[{"role": "system", "content": "你是一个德、俄、英三语文本翻译专家，精通哲学、社科类文本的翻译。你会根据文本内容自动识别语言，并将其翻译成中文。同时你也是一个网络出版编辑兼前端开发者，可以帮我识别、标记、输出一些最基本的影响文本格式的html标签，让输出的网页内容可以流畅阅读、传达原文原排版包含的所有信息。"},
    {"role": "user", "content": r"请帮我把以下网页内容翻译成中文后输出为html代码，只需输出<title>和<body>的代码即可，省略html、head部分。注意保留各种网页的标签及排版样式，如各层级标题h1-h6、引用<blockquote>、表格、注释<sup>+<a等。如遇外文用斜体<i>或<em>的地方请改用粗体<b>输出。html文本代码如下:"+'\n'+f"{file_content}"}],
  temperature=1,
  top_p=1,
  max_tokens=32000,
  stream=False
)
    for chunk in completion:
        if not getattr(chunk, "choices", None):
            continue
        reasoning = getattr(chunk.choices[0].delta, "reasoning_content", None)
        if reasoning:
            print(reasoning, end="")
        if chunk.choices and chunk.choices[0].delta.content is not None:
            print(chunk.choices[0].delta.content, end="")
    return completion.choices[0].message.content
def use_zai(file_content):
    """
    调用ai的api借口
    """
    client = ZhipuAiClient(api_key="xxxxx")
    print("正在调用AI接口，请稍等...")
    response = client.chat.completions.create(
    #model="glm-4.7",
    model="glm-4.7-flash", #调什么模型
    messages=[
        {"role": "system", "content": "你是一个德、俄、英三语文本翻译专家，精通哲学、社科类文本的翻译。你会根据文本内容自动识别语言，并将其翻译成中文。同时你也是一个网络出版编辑兼前端开发者，可以帮我识别、标记、输出一些最基本的影响文本格式的html标签，让输出的网页内容可以流畅阅读、传达原文原排版包含的所有信息。"},
        {"role": "user", "content": r"请帮我把以下网页内容翻译成中文后输出为html代码，只需输出<body>的代码即可，省略html、head部分。注意保留各种网页的标签及排版样式，如各层级标题h1-h6、引用<blockquote>、表格、注释<sup>+<a等。如遇外文用斜体<i>或<em>的地方请改用粗体<b>输出。html文本代码如下:"+'\n'+f"{file_content}"}],
    max_tokens=32000,  
    temperature=0.2,
    stream=False  
)
    return response.choices[0].message.content
def split_test(content):
    return content
def main():
    title,contents=divide_html_by_bytes([r'./MARX-ZH-CN.github.io1/ru/VIL-FB2/3/VL03-G078.html'],16384) #你需要要的文件的路径
    #title,contents=divide_html_by_headings([r'./MARX-ZH-CN.github.io1/docs/MEW/3/ME03-101.html']) #你需要要的文件的路径
    content_outs = []

    for content in contents:
        #content_out=split_test(content) 
        #content_out=use_zai(content) #zai调用ai方式
        content_out=useapi_OPENAI_form(content) #OpenAI调用方式
        content_outs.append(content_out)
    print(len(content_outs))
    save_htmlcontent(title,r'./aioutput',r'VL01-G027.html',content_outs) #你需要保存的目录和文件名
if __name__ == "__main__":
    main()