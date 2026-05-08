import re
import glob
import os
import uuid
from datetime import datetime
from pathlib import Path
import shutil
from html.parser import HTMLParser
from urllib.parse import urlparse, urljoin
import base64
from bs4 import BeautifulSoup
import zipfile
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
    content = re.sub(r'HREF="([\S]+?).htm', 
                    r'href="\1.html', content, flags=re.IGNORECASE)
    content = re.sub(r'([\d]+?) тома</A>[\s\S]+?<P><HR>\s*?<P ALIGN=RIGHT>ПЕЧАТАЕТСЯ',
                    r'''тома \1</A>
<HR class="chapter" id="s0">
<DIV STYLE="COLOR: RED;TEXT-ALIGN:CENTER;"><i>Пролетарии всех стран, соединяйтесь!</i></DIV>
<H1 STYLE="COLOR: RED">ЛЕНИН</H1>
<H3 ALIGN=CENTER>ПОЛНОЕ<BR>СОБРАНИЕ<BR>СОЧИНЕНИЙ</H3>
<H2 ALIGN=CENTER>\1</H2>
<HR><P ALIGN=RIGHT>ПЕЧАТАЕТСЯ''', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'тома ([\d]+?)</A>[\s\S]+?<P><HR>\s*?<P ALIGN=RIGHT>ПЕЧАТАЕТСЯ',
                    r'''тома \1</A>
<HR class="chapter" id="s0">
<DIV STYLE="COLOR:RED;TEXT-ALIGN:CENTER;"><i>Пролетарии всех стран, соединяйтесь!</i></DIV>
<H1 STYLE="COLOR:RED;">ЛЕНИН</H1>
<H3 ALIGN=CENTER>ПОЛНОЕ<BR>СОБРАНИЕ<BR>СОЧИНЕНИЙ</H3>
<H2 ALIGN=CENTER>\1</H2>
<HR><P ALIGN=RIGHT>ПЕЧАТАЕТСЯ''', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<P><HR><A NAME=s0> </A>',
                    r'<A ID="s0"></A><P><HR>', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<P><HR><A NAME=(s1)> </A><P ALIGN=CENTER>([\dIVXLivxl]+?)\s+?(<P ALIGN=[\S]+?>)',
                    r'''<HR class="chapter" id="\1">
\3''', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<P><HR><A NAME=(s1)> </A>\s*<H',
                    r'''<HR class="chapter" id="\1">
<H''', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<P><HR><A NAME=(s[\dIXVLivxl]+?)> </A><P ALIGN=CENTER>([\dIVXLivxl]+?)\s+?<BR>В. И. ЛЕНИН\s+?<P ALIGN=([\S]+?)>',
                    r'''<HR><DIV CLASS="HEADER" ID="\1">\2　　В. И. ЛЕНИН</DIV>
<P ALIGN=\3>''', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<P><HR><A NAME=(s[\dIXVLivxl]+?)> </A><P ALIGN=CENTER>([\dIVXLivxl]+?)\s+?<BR>В. И. ЛЕНИН\s+?<BLOCKQUOTE>',
                    r'''<HR><DIV CLASS="HEADER" ID="\1">\2　　В. И. ЛЕНИн</DIV>
<BLOCKQUOTE>''', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<P><HR><A NAME=(s[\dIXVLivxl]+?)> </A><P ALIGN=CENTER>([\dIVXLivxl]+?)\s+?<BR>([\S  ]+?)\s+?<P ALIGN=([\S]+?)>',
                    r'''<HR><DIV CLASS="HEADER" ID="\1">\3　　\2</DIV>
<P ALIGN=\4>''', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<P><HR><A NAME=(s[\dIXVLivxl]+?)> </A><P ALIGN=CENTER>([\dIVXLivxl]+?)\s+?<BR>([\S  ]+?)\s+?<BLOCKQUOTE>',
                    r'''<HR><DIV CLASS="HEADER" ID="\1">\3　　\2</DIV>
<BLOCKQUOTE>''', content, flags=re.DOTALL | re.IGNORECASE)
    primechaniya_match = re.search(r'''<P><HR><A NAME=s[\d]+?> </A><A NAME=pprim> </A><P ALIGN=CENTER>[\d]+?[\r\n\s]*?<H2 ALIGN=CENTER>ПРИМЕЧАНИЯ</H2>''', content, flags=re.IGNORECASE)
    if primechaniya_match:
        primechaniya_pos = primechaniya_match.start()
        before_notes = content[:primechaniya_pos]
        after_notes = content[primechaniya_pos:]
        if vol_num in range(46,56):
            before_notes = re.sub(r'<HR><DIV CLASS="HEADER"( ID="s[\d]+?")>',
                                 r'<HR class="chapter"\1><DIV CLASS="HEADER">', 
                                 before_notes, flags=re.DOTALL | re.IGNORECASE)
        else:
            before_notes = re.sub(r'''<P><HR><A NAME=(s[\dIXVLivxl]+?)> </A><P ALIGN=CENTER>([\dIVXLivxl]+?)\s+?<BR>([\S ]+?)\s+?<H''',
                    r'''<HR class="chapter" ID="\1"><DIV CLASS="HEADER">\3 \2</DIV>
<H''', before_notes , flags=re.DOTALL | re.IGNORECASE)
            before_notes  = re.sub(r'''<P><HR><A NAME=(s[\dIXVLivxl]+?)> </A><P ALIGN=CENTER>([\dIVXLivxl]+?)\s+?<BR>В. И. ЛЕНИН\s+?<H''',
                    r'''<HR class="chapter" ID="\1"><DIV CLASS="HEADER">\2　　В. И. ЛЕНИН</DIV>
<H''',before_notes , flags=re.DOTALL | re.IGNORECASE)
        content = before_notes + after_notes
    content = re.sub(r'''<P><HR><A NAME=s[\d]+?> </A><A NAME=(s[\d]+?)> </A><A NAME=([\S]+?)> <P ALIGN=CENTER>([\dIVXLivxl]+?)\s+?(<H[\d]+?) ALIGN=CENTER>''',
                    r'<HR class="chapter" id="\1">\4 ID="\2">', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'''<P><HR><A NAME=s[\d]+?> </A><A NAME=(s[\d]+?)> </A><A NAME=([\S]+?)> </A><P ALIGN=CENTER>([\dIVXLivxl]+?)\s+?(<H[\d]+?) ALIGN=CENTER>''',
                    r'<HR class="chapter" id="\1">\4 ID="\2">', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'''<P><HR><A NAME=(s[\d]+?)> </A><A NAME=([\S]+?)> </A><P ALIGN=CENTER>([\dIVXLivxl]+?)\s+?(<H[\d]+?) ALIGN=CENTER>''',
                    r'''<HR class="chapter" id="\1">\4 ID="\2">''', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'''<P><HR><A NAME=(s[\d]+?)> </A><P ALIGN=CENTER>([\dIVXLivxl]+?)\s+?(<H[\d]+?) ALIGN=CENTER>''',
                    r'<HR class="chapter" ID="\1">\3>', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<P><HR><P ALIGN=CENTER>([\dIVXLivxlХ]+?)\s+?<BR>([\S  ]+?)\s+?<P ALIGN=JUSTIFY>',
                    r'''<HR><DIV CLASS="HEADER-1" id="\1">\1<BR>\2</DIV>
''', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'''<P><HR><P ALIGN=CENTER>([\dIVXLivxlХ]+?)\s+?<BR>([\S ]+?)\s+?<H''',
                    r'''<HR><DIV CLASS="HEADER-1" id="\1">\1<BR>\2</DIV>
<H''', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<P>(<[HT])',r'\1', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<P class=[\S]+?>(<TABLE)',r'\1', content, flags=re.DOTALL | re.IGNORECASE)
    #content = re.sub(r'<HR WIDTH=15% ',r'<HR WIDTH=15%', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'(<p[^>]*>)([\S\r\s\n]+?)(?=<[/]*[phtd][^>]*>|<[/]*small[^>]*>|$)',
                    r'\1\2</p>', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<SMALL><HR WIDTH=15% ALIGN=LEFT>\s*<P ALIGN=JUSTIFY>([\s\r\n\S]+?)<HR',
                    r'<ASIDE>\n<HR><P>\1</ASIDE>'+'\n<HR', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'''<P ALIGN=JUSTIFY>''',r'''<P>''', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'''[\s\r\n]+</P>''','</P>\n', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<P ALIGN=([\S]+?)>([\S ]+?)<P>',
                    r'<DIV STYLE="TEXT-ALIGN:\1;">\2</DIV>', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<P ALIGN=([\S]+?)>',r'<P STYLE="TEXT-ALIGN:\1">', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<A NAME=p([\S]+?)>\s*</A><sup>([\S ]+?)</sup>', r'<SUP><a id="p\1" href="#pref\1">\2</a></SUP>', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<A NAME=', r'<A ID=', content, flags=re.DOTALL | re.IGNORECASE)

    if vol_num > 0:
        content = re.sub(r'<a href="vilall\.htm">', r'<a href="../index.html">', content, flags=re.DOTALL | re.IGNORECASE)
    else:
        content = re.sub(r'<a href="vilall\.htm">', r'<a href="index.html">', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'(href=[\S]+?)\.htm"', r'\1.html"', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'(href=[\S]+?)\.htm#', r'\1.html#', content, flags=re.DOTALL | re.IGNORECASE)
    return content
def open_files(html_files,output_dir):
    temp_con=''
    index=''
    title=''
    total=[]
    output_dir.mkdir(exist_ok=True)
    for idx,file in enumerate(html_files):
        filename=file.name.replace(r'.htm','')
        with open(file,'r',encoding='windows-1251') as f:
            html_content=f.read()
        content=html_content
        vol_num = 0
        match = re.match(r'[0]*(\d{1,2})\.htm', filename)
        if match:
            vol_num = int(match.group(1))
        content=preprocess_html(content, vol_num)
        with open(output_dir / f"{filename}.html", 'w', encoding='utf-8-sig',newline='') as f:
            f.write(content)
        
    
    
input_dir = r"D:\马恩列总装\VILo"
output_dirs =[Path(r"D:\马恩列总装\MARX-ZH-CN.github.io1\docs\VIL"),Path(r"D:\马恩列总装\mlread\docs\VIL")]
htmls=list(Path(input_dir).glob("*.htm"))
for output_dir in output_dirs:
    open_files(htmls,output_dir)
