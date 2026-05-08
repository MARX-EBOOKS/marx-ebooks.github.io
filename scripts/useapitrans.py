import requests as rq
from openai import OpenAI
import re
import base64
import json
import httpx
from bs4 import BeautifulSoup
from pathlib import Path
def read_htmlcontent(filepaths): 
    """
    读取HTML文件内容，提取title和body部分，并支持多个文件拼接、输入。
    """
    cleanedtext=""
    for i,filepath in enumerate(filepaths):
        file_path = Path(filepath)
        with open(file_path, 'r', encoding='utf-8-sig') as file:
            html_content = file.read()
        soup = BeautifulSoup(html_content, 'html.parser')
        if i==0:
            title=str(soup.find('title'))
        cleanedtext+='\n'+str(soup.find('body')).replace("<body>","").replace("</body>","")
    return title+'\n'+'<body>\n'+cleanedtext+'\n</body>'
def useaiapi(file_content):
    client = OpenAI(
    base_url="http://localhost:17117/v1",
    api_key="sk-no-key-required",
    timeout=httpx.Timeout(
    connect=10.0,
    read=3600.0,
    write=3600.0,
    pool=10.0)
    )
    print("正在调用AI接口，请稍等...")
    response = client.chat.completions.create(
    model="qwen3",
    messages=[
        {"role": "system", "content": "你是一个德、俄、英三语文本翻译专家，精通哲学、社科类文本的翻译。你会根据文本内容自动识别语言，并将其翻译成中文。同时你也是一个网络出版编辑兼前端开发者，可以帮我识别、标记、输出一些最基本的影响文本格式的html标签，让输出的网页内容可以流畅阅读、传达原文原排版包含的所有信息。"},
        {"role": "user", "content": r"请帮我把以下网页内容翻译成中文后输出为html代码，只需输出<title>和<body>的代码即可，省略html、head部分。注意保留各种网页的标签及排版样式，如各层级标题h1-h6、引用<blockquote>、表格、注释<sup>+<a等。如遇外文用斜体<i>或<em>的地方请改用粗体<b>输出。html文本代码如下:"+'\n'+f"{file_content}"}],
    max_tokens=2048,  
    temperature=0.2,
    stream=False,

)
    return response.choices[0].message.content
def save_htmlcontent(filepath,filename,content):
    """
    把ai翻译、处理后的内容保存成完整的html文件，即补全html标签，以及加入css样式表。
    """
    Path(filepath).mkdir(parents=True, exist_ok=True)
    file_path = Path(filepath)/filename
    content=re.sub(r'<title>',r'''<html lang="zh-CN">
<head>
<META name="viewport" content="width=device-width, initial-scale=1.0"/>
<META content="text/html; charset=UTF-8" http-equiv="Content-Type"/>
    <title>''',content,flags=re.IGNORECASE|re.DOTALL)
    content=re.sub(r'</title>',r'''</title>
<link rel="stylesheet" type="text/css" href="styles.css"/>
</head>
''',content,flags=re.IGNORECASE|re.DOTALL)
    content=re.sub(r'</body>',r'''</body>
</html>''',content,flags=re.IGNORECASE|re.DOTALL)
    with open(file_path, 'w', encoding='utf-8-sig',newline='\r\n') as file:
        file.write(content)
def main():
    base_path=r'./LENINPSS-HTML-FB2-SPLITED/ru/VIL-FB2/' #你要翻译的文件主目录
    fileexactvol=3 #卷目录（一般为卷号，除en文件夹外）
    files_merge=[f'{fileexactvol}/VL{fileexactvol:02d}-G010.html']
    files=[]
    for f in files_merge:
        files.append(base_path+f) #你要翻译的文件
    content=read_htmlcontent(files) #把文件名作为字符串数组传进去
    content_out=useaiapi(content) #调用ai
    save_htmlcontent(r'./aioutput',f'NAMEYOURSELF.html',content_out) #需要保存的目录和文件名，可自行命名
if __name__ == "__main__":
    main()