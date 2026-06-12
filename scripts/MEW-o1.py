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
from MEWmede import EpubBookBuilder
import openpyxl
def process_recontent(content):
    """处理recontent的正则替换逻辑"""
    def font2(match):
        recontent=match.group(1)
        recontent=re.sub(r"""<font size=["]*2["]*>((?:(?!<p|<font size=["]*2)[\s\r\n\S])+?)(?:</font>)*""",r"\1",recontent,flags=re.DOTALL|re.IGNORECASE)
        recontent=re.sub(r"[\s\r\n]+$",r"",recontent,flags=re.DOTALL|re.IGNORECASE)
        tags=""
        recontent=re.sub(r"(<dir>[\s\r\n]*)+[\s\r\n]+<p>","\n"+r"""<p class="poem">""",recontent,flags=re.DOTALL|re.IGNORECASE)
        recontent=re.sub(r"(<dir>[\s\r\n]*)+<p>",r"""<p class="poem">""",recontent,flags=re.DOTALL|re.IGNORECASE)
        recontent=re.sub(r"""(?:</font>)[\s\r\n]*(<font size=["]*[^2<]+["]*>)""",r"\1",recontent,flags=re.DOTALL|re.IGNORECASE)
        if match.group(2) and "dir" not in match.group(2):
            tags=match.group(2)
        if "</p>" not in recontent and "</P>" not in recontent:
            recontent=r"<blockquote>"+recontent+tags+r"</blockquote>"
        else:
            recontent=r"<blockquote><p>"+recontent+tags+r"</p></blockquote>"
        return recontent
    def repagenum(recontent):
        recontent=re.sub(r'''<b>\s*<p([\S ]*?)>([\S ]+?)</p>\s*<p><a name=("S[\d]+?")>(?:(&lt;)|\|)[\d]+?(?:(&gt;)|\|)[\s\*]*</a></b>''',r'<div\1><b>\2</b></div><a id=\3></a><p>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<b><p><a name=("S[\S]+?")>\s*(?:&lt;|\|)[\d]+?(?:&gt;|\|)[\s\*]*</a></b>\s*<small>',r'<small><p><a id=\1></a>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<b>\s*<p><a name=("S[\d]+?")>\s*(?:(&lt;)|\|)\s*[\d]+?\s*(?:(&gt;)|\|)[\s\*]*</[ab]>\s*</[ab]>',r'<p><a id=\1></a>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<B><P><A NAME=["]*(S[\d]+?)["]*></A>\s*(?:(&lt;)|\|)\s*[\d]+?\s*(?:(&gt;)|\|)[\s\*]*</B>',r'<p><a id="\1"></a>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<B><P><A NAME=["]*(S[\d]+?)["]*>\s*(?:(&lt;)|\|)\s*[\d]+?\s*(?:(&gt;)|\|)[\s\*]*(</[AB]>\s*){2}',
                                 r'<p><a id="\1"></a>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'[ ]+<A NAME=["]*(S[\d]+?)["]*>(</[\S]+?>)+<B>(?:(&lt;)|\|)[\d]+?(?:(&gt;)|\|)[\*\s]*(</[AB]\s*>){2}[ ]+',
                                 r'\2<a id="\1"></a> ',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'[ ]+<A (NAME|id)=["]*(S[\d]+?)["]*><B>(?:(&lt;)|\|)[\d]+?(?:(&gt;)|\|)[\*\s]*(</[AB]>\s*){2}[ ]+',
                                 r'<a id="\2"></a> ',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'[ ]+<B><A (NAME|id)=["]*(S[\d]+?)["]*>(?:(&lt;)|\|)[\d]+?(?:(&gt;)|\|)[\*\s]*(</[AB]>){2}[ ]+',
                                 r'<a id="\2"></a> ',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<A\s*(NAME|id)=\s*["]*(S[\d]+?)["]*>\s*</a>\s*<B>(?:(&lt;)|\|)[\d]+?(?:(&gt;)|\|)[\*\s]*</B>',
                                 r'<a id="\2"></a> ',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<A\s*NAME=\s*["]*(S[\d]+?)["]*>\s*(</[\S]+?>)+\s*<B>(?:(&lt;)|\|)[\d]+?(?:(&gt;)|\|)[\*\s]*(</[AB]>\s*){2}',
                                 r'\2<a id="\1"></a> ',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<A\s*(NAME|id)=["]*(S[\d]+?)["]*>\s*<B>\s*(?:(&lt;)|\|)[\d]+?(?:(&gt;)|\|)[\*\s]*(</[AB]>\s*){2}',
                                 r'<a id="\2"></a>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<B>\s*<A (NAME|id)=["]*(S[\d]+?)["]*>\s*(?:(&lt;)|\|)[\d]+?(?:(&gt;)|\|)[\*\s]*(</[AB]>){2}',
                                 r'<a id="\2"></a>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<B>\s*<A (NAME|id)=["]*(S[\d]+?)["]*>\s*</A>(?:(&lt;)|\|)[\d]+?(?:(&gt;)|\|)[\s\*]*</B>',
                                 r'<a id="\2"></a>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<B>\s*<A NAME=["]*(S[\d]+?)["]*>\s*</A>\s*(?:(&lt;)|\|)[\d]+?(?:(&gt;)|\|)[\s\*]*</B>',
                                 r'<a id="\1"></a>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<B>(<FONT SIZE=[\S]+?>)<P><a name=["]*(S[\d]+?)["]*>\s*(?:&lt;|\|)\s*([\d]+?)\s*(?:&gt;|\|)[\s\*]*</[ab]></[ab]>'
                         ,r'\1<p><a id="\2"></a>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<a name=("S[\d]+?")>\s*<[^<]+?>\s*(?:&lt;|\|)\s*([\d]+?)(?:&gt;|\|)[\s\*]*</[ab]></([ab]|[^<]{4,6})>'
                         ,r'<a id=\1></a>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<b><p>\s*(?:&lt;|\|)([\d]+?)(?:&gt;|\|)[\s\*]*</b>\s*<small>',r'<small><p><a id=S\1></a>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<B>\s*<P>\s*(?:&lt;|\|)\s*([\d]+?)\s*(?:&gt;|\|)[\s\*]*(?:</p>)*</b>(?:</p>)*'
                         ,'\n'+r'<p><a id="S\1"></a>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<[\S]{1,6}><a name=("S[\d]+?")>(?:(&lt;)|\|)[\d]+?(?:(&gt;)|\|)</[\S]></[\S]{1,6}>',r'<a id=\1></a>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<B>(<[\S]{1,6}>)<P>(?:&lt;|\|)([\d]+?)(?:&gt;|\|)[\s\*]*</[\S]{1,6}>',r'\1<P><a id="S\2"></a>',recontent,flags=re.DOTALL|re.IGNORECASE)
        recontent=re.sub(r'<B>(<[\S]{1,6}>)\s*&lt;[\d]+?&gt;\s*</B>(<small>)*',r'\2\1',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'[-]*[ ]{0,2}<B>(<[\S]{1,6}>)*\s*\|[\d]+?\|\s*</B>',r'\1',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'[-]*[ ]{0,2}<B>\s*(<[\S]{1,6}>)*\s*<P>\s*&lt;[\d]+?&gt;[\s\*]*</[\S]{1,6}>',r'\1<P>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<A name=["]*S([\d]+?)["]*>\s*\|[\d]+?\|\s*</a>',r'<a id="S\1"></a>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<A name=["]*S([\d]+?)["]*>\s*&lt;[\d]+?&gt;\s*</a>',r'<a id="S\1"></a>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        
        recontent=re.sub(r'[\|]{0,1}\s*<B>\s*[\|]{0,1}\s*([\d]+?)\s*[\|]{0,1}\s*</B>\s*[\|]{0,1}',r'<A ID="S\1"></a>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<B>\s*&lt;\s*([\d]+?)\s*&gt;\s*</B>',r'<A ID="S\1"></a>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        
        recontent=re.sub(r'<font size=[\S]+?><p>([\S ]+?)</p>\s*</font><b><p><a name=("S[\S]+?")>\s*(?:&lt;|\|)[\d]+?(?:&gt;|\|)[\s\*]*</a></b>'
                         ,r'''<blockquote>\1</blockquote>
<p><a id=\2></a>''',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<font size=[\S]+?><p><a name=["]*(S[\S]+?)["]*>([\S ]+?)</p>\s*</font><b><p>\s*(?:&lt;|\|)[\d]+?(?:&gt;|\|)[\s\*]*</a></b>'
                         ,r'''<blockquote>\2</blockquote>
<p><a id="\1"></a>''',recontent ,flags=re.DOTALL | re.IGNORECASE)
        return recontent
    def renote(recontent):
        recontent=re.sub(r'<small><sup>\s*((?:&lt;|\(|\{|\||\[)[\S]{1,5}(?:&gt;|\)|\}|\||\]))\s*(?:</sup>|</small>)</a>(?:</sup>|</small>)',r'\1</a>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<small><sup>\s*((?:&lt;|\(|\{|\||\[)[\S]{1,5}(?:&gt;|\)|\}|\||\]))\s*</a>(?:</sup>|</small>){2}',r'\1</a>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<small><sup>\s*((?:&lt;|\(|\{|\||\[)[\S]{1,5}(?:&gt;|\)|\}|\||\]))\s*(?:</sup>|</small>){2}',r'\1',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<small><sup>\s*(<a name=[ \S]+?(?:&lt;|\(|\{|\||\[)[\S]{1,5}(?:&gt;|\)|\}|\||\]))\s*(?:</sup>|</small>|</a>){2,3}',r'\1</a>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<small>\s*((?:&lt;|\(|\{|\||\[)[\S]{1,5}(?:&gt;|\)|\}|\||\]))\s*(?:</small>)',r'\1',recontent ,flags=re.DOTALL | re.IGNORECASE)

        recontent=re.sub(r'(<a (?:name|id)=[\S]+? href=[\S]+?>)<sup>([\S ]+?)</sup></a>',r'<sup>\1\2</a></sup>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<sup>\s*((?:&lt;|\(|\{|\||\[)[\S]{1,5}(?:&gt;|\)|\}|\||\]))\s*(?:</sup>)',r'\1' ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'</font>\s*<a (?:name|id)=([\S]+?)>\s*<a href=([\S]+?)>\s*<font size=["]*2["]*>\s*((?:&lt;|\(|\{|\|)[\S]{1,5}(?:&gt;|\)|\}|\|))\s*</font>\s*</a>\s*</a>\s*</p>',r'<sup><a id=\1 href=\2>\3</a></sup></p></font>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<a (?:name|id)=([\S]+?)>\s*</font>\s*<a href=([\S]+?)>\s*<font size=["]*2["]*>\s*((?:&lt;|\(|\{|\|)[\S]{1,5}(?:&gt;|\)|\}|\|))\s*</font>\s*</a>\s*</a>\s*</p>',r'<sup><a id=\1 href=\2>\3</a></sup></p></font>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(?:</font>)*<a (?:name|id)=([\S]+?)>\s*(?:</font>)<a href=([\S]+?)>\s*<font size=["]*2["]*>\s*((?:&lt;|\(|\{|\|)[\S]{1,5}(?:&gt;|\)|\}|\|))\s*</font>\s*</a>\s*</a>\s*(?:<font size=["]*2["]*>)+',r'<sup><a id=\1 href=\2>\3</a></sup>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<a name=("[\S]+?")>\s*(</i>)\s*<a href=("[\S]+?")>\s*(?:<[^<]+?>)*\s*((?:&lt;|\(|\{|\||\[)[\S]{1,5}(?:&gt;|\)|\}|\||\]))\s*(</[^<]+?>){1,3}',r'\2<sup><a id=\1 href=\3>\4</a></sup>\5' ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<a (?:name|id)=([\S]+?)>\s*<a href=([\S]+?)>\s*((?:&lt;|\(|\{|\||\[)[\S]{1,5}(?:&gt;|\)|\}|\||\]))\s*</a>\s*</a>',r'<sup><a id=\1 href=\2>\3</a></sup>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<a href=([\S]+?)>\s*<a (?:name|id)=([\S]+?)>\s*((?:&lt;|\(|\{|\||\[)[\S]{1,5}(?:&gt;|\)|\}|\||\]))\s*</a>\s*</a>',r'<sup><a id=\2 href=\1>\3</a></sup>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<a name=("[\S]+?")>\s*(<[/]*(?:small|font|span|p)[^<]*?>){0,2}<a href=("[\S]+?")>\s*(?:<[^<]+?>)*\s*((?:&lt;|\(|\{|\||\[)[\S]{1,5}(?:&gt;|\)|\}|\||\]))\s*(?:</small|font|span|a>){1,3}',r'<sup><a id=\1 href=\3>\4</a></sup>\2' ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        #recontent=re.sub(r'<a href=([\S]+?)>\s*(<[/]*(?:small|font|span|i|p)[^<]*?>){0,2}\s*<a name=([\S]+?)>\s*(?:<[^<]+?>)*\s*((?:&lt;|\(|\{|\||\[)[\S]{1,4}(?:&gt;|\)|\}|\||\]))\s*(</[^<]+?>){1,3}' ,r'<sup><a id=\3 href=\1>\4</a></sup>\2\5',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<a name=("[\S]+?")>\s*(<[/]*(?:small|font|span|p)[^<]*?>){0,2}<a href=("[\S]+?")>\s*(?:<[^<]+?>)*\s*((?:&lt;|\(|\{|\||\[)[\S]{1,5}(?:&gt;|\)|\}|\||\]))\s*(?:</a>)*(</p>)*(?:</a>)*',r'<sup><a id=\1 href=\3>\4</a></sup>\2\5' ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        #recontent=re.sub(r'<a (?:name|id)=["]*([\S]+?)["]*>\s*(<[/]*[^<]*?>){0,2}<a href=["]*([\S]+?)["]*>\s*<(?:font|span|p) (?:class|size)=[\S]+?>\s*((?:(&lt;)|\(|\{)[\S]{1,4}(?:(&gt;)|\)|\}))\s*(</(?:a|span|font|p|small)>){1,3}',r'<sup><a id=\1 href=\3>\4</a></sup>\2',recontent ,flags=re.DOTALL | re.IGNORECASE)
        #recontent=re.sub(r'<a (?:name|id)=["]*([\S]+?)["]*>\s*</a>(</[\S]{1,6}>){0,3}<a href=["]*([\S]+?)["]*>\s*<(?:font|span|p) (?:class|size)=[\S]+?>\s*((?:(&lt;)|\(|\{)[\S]{1,4}(?:(&gt;)|\)|\}))\s*(</(?:a|span|font|p|small)>){1,3}'
        # ,r'<sup><a id=\1 href=\3>\4</a></sup>\2' ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<a href=([\S]+?)>(?:<(?:small|font)[^<]*?>)<a (?:name|id)=([\S]+?)>\s*((?:&lt;|\(|\{|\||\[)[\S]{1,5}(?:&gt;|\)|\}|\||\]))\s*(?:</a>|</small>|</font>){1,3}',r'<sup><a id=\2 href=\1>\3</a></sup>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<a href=([\S]+?)>(?:<(?:small|font)[^<]*?>)<a (?:name|id)=([\S]+?)>\s*((?:&lt;|\(|\{|\||\[)[\S]{1,5}(?:&gt;|\)|\}|\||\]))\s*(</[A-Za-z]+?>){1,3}',r'<sup><a id=\2 href=\1>\3</a></sup>\4',recontent ,flags=re.DOTALL | re.IGNORECASE)


        recontent=re.sub(r'<a (?:name|id)=["]*([\S]+?)["]*>\s*</a>\s*<a href=["]*([\S]+?)["]*>\s*((?:&lt;|\(|\{|\||\[)[\S]{1,5}(?:&gt;|\)|\}|\||\]))\s*</a>'
                                 ,r'<sup><a id=\1 href=\2>\3</a></sup>'
                                 ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<a (?:name|id)=["]*([\S]+?)["]*>\s*(</[\S]{1,6}>){0,3}<a href=["]*([\S]+?)["]*>\s*<(?:font|span|p) (?:class|size)=[\S]+?>\s*((?:&lt;|\(|\{|\||\[)[\S]{1,5}(?:&gt;|\)|\}|\||\]))\s*(</(?:a|span|font|p|small)>){1,3}'
                                 ,r'<sup><a id=\1 href=\3>\4</a></sup>\2'
                                 ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<a name=([\S]+? href=[\S]+?>\s*(?:&lt;|\(|\{|\||\[)[\S]{1,5}(?:&gt;|\)|\}|\||\])\s*</a>)',r'<sup><a id=\1</sup>',recontent ,flags=re.DOTALL | re.IGNORECASE) 
        recontent=re.sub(r'<a (href=[\S]+?) name=([\S]+?>\s*(?:&lt;|\(|\{|\||\[)[\S]{1,5}(?:&gt;|\)|\}|\||\])\s*</a>)',r'<sup><a \1 id=\2</sup>',recontent ,flags=re.DOTALL | re.IGNORECASE) 
        recontent=re.sub(r'<a href="#([\S]+?")>((?:&lt;|\(|\{|\||\[)[\S]{1,4}(?:&gt;|\)|\}|\||\]))</a><A (?:name|id)=["]*(Z[\S]+?)["]*></a>',r'<sup><a id=\3 href="#\1>\2</a></sup>',recontent ,flags=re.DOTALL | re.IGNORECASE)

        recontent=re.sub(r'<a href="#([\S]+?")>((?:(&lt;)|\(|\{)[\S]{1,4}(?:(&gt;)|\)|\}))</a>',r'<sup><a id="Z\1 href="#\1>\2</a></sup>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'</small>(<sup><a[ \S]+?</a></sup>)<small>',r'\1',recontent ,flags=re.DOTALL | re.IGNORECASE) 
        recontent=re.sub(r'</small>(<sup><a[ \S]+?</a></sup>)',r'\1</small>',recontent ,flags=re.DOTALL | re.IGNORECASE)             
        #recontent=re.sub(r'<a href=("[\S]+?")></a><a name=("[\S]+?")>((?:(&lt;)|\(|\{)[\S]{1,4}(?:(&gt;)|\)|\}))</a>'
        #                ,r'<a id=\1 href=\2><sup>\3</sup></a>'
        #               ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        

        
        recontent=re.sub(r'<small><sup><p>(<[\S ]+?)((</sup>)|(</small>)|(</p>)){2,3}',r'<p>\1',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<span [\S]+?><a (?:name|id)=([\S]+?)>((?:&lt;|\(|\{|\||\[)[\S]{1,5}(?:&gt;|\)|\}|\||\]))</a></span>*[ ]*((?:(?!<a name)[\S\r\n ])+?)<a href=("#[\S]+?")>&lt;=</a>',
                                 r'<p class="fni"><a id="\1" href="\4">\2</a> \3</p>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(?:<p>\s*)<a name=["]*([^<]+?)["]*>\s*(?:<[^<]+?>)*\s*((?:&lt;|\(|\{|\||\[)[\S]{1,5}(?:&gt;|\)|\}|\||\]))\s*(?:</[^<]+?>)*[ ]*((?:(?!<a name)[\S\r\n ])+?)<a href=["]*([^<]+?)["]*>&lt;=</a>\s*(?:</p>)*', r'<p class="fni"><a id="\1" href="\4">\2</a> \3</p>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(?:<p>\s*)<a name=["]*([^<]+?)["]*>\s*((?:&lt;|\(|\{|\||\[)[\S]{1,5}(?:&gt;|\)|\}|\||\]))\s*(?:</[^<]+?>)*[ ]*((?:(?!<a name)[\S\r\n ])+?)<a href=["]*([^<]+?)["]*>&lt;=</a>\s*(?:</p>)*', r'<p class="fni"><a id="\1" href="\4">\2</a> \3</p>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(?:<p>\s*)<a (?:name|id)=["]*([\S]+?)["]*>\s*((?:&lt;|\(|\{|\||\[)[\S]{1,5}(?:&gt;|\)|\}|\||\]))\s*(?:</a>)*[ ]*((?:(?!<a name)[\S\r\n ])+?)<a href=["]*([\S]+?)["]*>&lt;=</a>\s*(?:</p>)*',
                                 r'<p class="fni"><a id="\1" href="\4">\2</a> \3</p>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<a name=["]*([^<]+?)["]*>\s*(?:<[^<]+?>)*\s*((?:&lt;|\(|\{|\||\[)[\S]{1,5}(?:&gt;|\)|\}|\||\]))\s*(?:</[^<]+?>)*[ ]*([\S\r\n ]+?)<a href=["]*([^<]+?)["]*>&lt;=</a>',
                                 r'<p class="fni"><a id="\1" href="\4">\2</a> \3</p>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(</[\S]{1,6}>)+\s*<a name=["]*([\S]+?)["]*>(<[a-z][\S]{1,5}>)+',r'\1'+'\n'+r'\3<a name="\2">',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<a (?:name|id)=["]*([\S]+?)["]*>\s*((?:&lt;|\(|\{|\||\[)[\S]{1,5}(?:&gt;|\)|\}|\||\]))\s*(?:</a>)*[ ]*([\S\r\n ]+?)<a href=["]*([\S]+?)["]*>&lt;=</a>',
                                 r'<p class="fni"><a id="\1" href="\4">\2</a> \3</p>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'(?:<p>)*Textvarianten(?:</p>)','''<HR class="fn">
<div class="fnt">Textvarianten</div>''', recontent, flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'<P>[\s\r\n]*<HR[^<]*?>[\s\r\n]*</P>[\s\r\n]*<P>(Anmerkungen[ \S]+?)</P>',r'''<HR class="fn">
<div class="fnt">\1</div>''', fixed_content, flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'(?:<p>)*Fu[\S]+?noten von Friedrich Engels</p>','''<HR class="fn">
<div class="fnt">Fußnoten von Engels</div>''', fixed_content, flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'(?:<p>)*Fu[\S]+?noten von Engels</p>','''<HR class="fn">
<div class="fnt">Fußnoten von Engels</div>''', fixed_content, flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'<p>(Randnotizen von Friedrich Engels)</p>','''<HR class="fn">
<div class="fnt">\1</div>''', fixed_content, flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'(?:<p>)*Fu[\S]+?noten von Marx und Engels</p>','''<HR class="fn">
<div class="fnt">Fußnoten von Marx und Engels</div>''', fixed_content, flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'(?:<p>)*Fu[\S]+?noten von Marx</p>','''<HR class="fn">
<div class="fnt">Fußnoten von Marx</div>''', fixed_content, flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'(?:<p>)*Fu[\S]+?noten von Karl Marx</p>','''<HR class="fn">
<div class="fnt">Fußnoten von Marx</div>''', fixed_content, flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(?:<p>)*Fu[\S]+?noten</p>','''<HR class="fn">
<div class="fnt">Fußnoten</div>''', fixed_content, flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(?:<p>[\s\r\n]*)*<HR[^<]*?>[\s\r\n]*(?:</p>[\s\r\n]*)*(<p><a (?:id|name|href)=[\S]+? (?:id|name|href)=[\S]+?>[\S\r\n\s]+?<(?:/p|br)>)\s*</body>',r'<aside class="fn">\1</aside>'+'\n</body>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<HR class="fn">\s+(<div class="fnt">[\S\r\n\s]+?)\s*(</body>|<HR[^<]*?>)',r'<aside class="fn">\1</aside>'+'\n'+r'\2',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(?:<p>[\s\r\n]*)*<HR[^<]*?>[\s\r\n]*(?:</p>[\s\r\n]*)*(<p><a (?:id|name|href)=[\S]+? (?:id|name|href)=[\S]+?>[\S\r\n\s]+?<(?:/p|br)>)\s*<HR[^<]*?>',r'<aside class="fn">\1</aside>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        return recontent
    def retitle(content):
        recontent=re.sub(r'''(<h[\d][\S ]*?>)<p[\S ]*?>([\S\r\n\s]+?)</p>(</h[\d]>)''',r'\1\2\3',content ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<(h[\d]) align=["']*center["']*>(?:<[^<]+?>)<a (?:name|id)=(["'][\S]+?["']*)>([\S\r\n\s]+?)</h[\d]>''',r'<\1 id=\2>\3</\1>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<(h[\d])([\S ]+?)><[\S ]*?><a (?:name|id)=(["'][\S]+?["']*)>([\S ]+?)</h[\d]>''',r'<\1 \2 id=\3>\4</\1>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<(h[\d]) align=["']*center["']*><a (?:name|id)=(["'][\S]+?["']*)>([\S\r\n\s]+?)</h[\d]>''',r'<\1 id=\2>\3</\1>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<(h[\d])><a (?:name|id)=(["'][\S]+?["']*)>([\S\r\n\s]+?)</h[\d]>''',r'<\1 id=\2>\3</\1>' ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''(<font size=["]*[^2]["]*>[\s\r\n]*)+<p align=["']*center["']*>\s*((?:(?!<p|_)[\S\r\n\s])+?)</p>[\s\r\n]*(</[^>]+?>)*[\s\r\n]*(<[^<]+?>)*[\s\r\n]*<p align=["']*center["']*>\s*((?:(?!<p|_|[IVXL]{2,})[\S\r\n\s]){2,}?)</p>''',r'''<h2>\1\2\3<br>\4\5</h2>''',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''(<font[^<]>[\s\r\n]*)*<p align=["']*center["']*>\s*((?:(?!<p|__)[\S\r\n\s])+?)</p>[\s\r\n]*(</[^>]+?>)*[\s\r\n]*(<[^<]+?>)*[\s\r\n]*<p align=["']*center["']*>\s*((?:(?!<p|_|[IVXL]{2,})[\S\r\n\s]){2,}?)</p>''',r'''<p align="center">\1\2\3<br>\4\5</p>''',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p align=["']*center["']*>\s*((?:(?!<p|__)[\S\r\n\s])+?)</p>[\s\r\n]*(</[^>]+?>)*[\s\r\n]*(<[^<]+?>)*[\s\r\n]*<p align=["']*center["']*>\s*((?:(?!<p|_|[IVXL]{2,})[\S\r\n\s]){2,}?)</p>''',r'''<p align="center">\1\2<br>\3\4</p>''',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p align=["']*center["']*>\s*<a (?:name|id)=(["'][IVX]+?["']*)>([\S\r\n\s]+?)(</p>\s*)''',r'<h2 id=\1>\2</h2>' ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p align=["']*center["']*>\s*<a (?:name|id)=(["']*Kap_[\S]+?_[\S]+?_[\S]+?_[\S]+?_[\S]+?_[\S]+?["']*)>([\S\r\n\s]+?)</p>'''
                         ,r'<h6 id=\1>\2</h6>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p[^<]*?>\s*<a (?:name|id)=(["']*Kap_[\S]+?_[\S]+?_[\S]+?_[\S]+?_[\S]+?_[\S]+?["']*)>([\S\r\n\s]+?)</p>'''
                         ,r'<h6 id=\1>\2</h6>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p[^<]*?>\s*<a (?:name|id)=(["']*Kap_[\S]+?_[\S]+?_[\S]+?_[\S]+?_[\S]+?["']*)>([\S\r\n\s]+?)</p>'''
                         ,r'<h5 id=\1>\2</h5>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p[^<]*?>\s*<a (?:name|id)=(["']*Kap_[\S]+?_[\S]+?_[\S]+?_[\S]+?["']*)>([\S\r\n\s]+?)</p>'''
                         ,r'<h4 id=\1>\2</h4>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p[^<]*?>\s*<a (?:name|id)=(["']*Kap_[\S]+?_[\S]+?_[\S]+?["']*)>([\S\r\n\s]+?)</p>'''
                         ,r'<h3 id=\1>\2</h3>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p[^<]*?>\s*<a (?:name|id)=(["']*Kap_[\S]+?_[\S]+?["']*)>([\S\r\n\s]+?)</p>'''
                         ,r'<h2 id=\1>\2</h2>',recontent ,flags=re.DOTALL | re.IGNORECASE)      
        recontent=re.sub(r'''<p align=["']*center["']*>\s*<a (?:name|id)=(["'][\S]+?_[\S]+?_[\S]+?_[\S]+?_[\S]+?["']*)>([\S\r\n\s]+?)(</[ap]>\s*){1,2}'''
                         ,r'<h5 id=\1>\2</h5>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p align=["']*center["']*>\s*<a (?:name|id)=(["'][\S]+?_[\S]+?_[\S]+?_[\S]+?["']*)>([\S\r\n\s]+?)(</[ap]>\s*){1,2}'''
                         ,r'<h4 id=\1>\2</h4>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p align=["']*center["']*>\s*<a (?:name|id)=(["'][\S]+?_[\S]+?_[\S]+?["']*)>([\S\r\n\s]+?)(</[ap]>\s*){1,2}'''
                         ,r'<h3 id=\1>\2</h3>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p align=["']*center["']*>\s*<a (?:name|id)=(["'][\S]+?_[\S]+?["']*)>([\S\r\n\s]+?)(</[ap]>\s*){1,2}''',r'<h2 id=\1>\2</h2>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p align=["']*center["']*>\s*<a (?:name|id)=(["']K[\d]+?["']*)>([\S\r\n\s]+?)(</[ap]>\s*){1,2}''',r'<h2 id=\1>\2</h2>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p align=["']*center["']*>\s*<a (?:name|id)=(["'][\S]+?["']*)>([\S\r\n\s]+?)(</[ap]>\s*){1,2}''',r'<h1 id=\1>\2</h1>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p[\S ]+?>\s*<[\S ]+?>\s*<a (?:name|id)=(["'][\S]+?_[\S]+?_[\S]+?_[\S]+?_[\S]+?_[\S]+?_[\S]+?["']*)>([\S\r\n\s]+?)(</p>\s*)'''
                         ,r'<h6 id=\1>\2</h6>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p[^<]+?>\s*<[^<]+?>\s*<a (?:name|id)=(["'][\S]+?_[\S]+?_[\S]+?_[\S]+?_[\S]+?_[\S]+?["']*)>([\S\r\n\s]+?)(</p>\s*)'''
                         ,r'<h6 id=\1>\2</h6>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p[^<]+?>\s*<[^<]+?>\s*<a (?:name|id)=(["'][\S]+?_[\S]+?_[\S]+?_[\S]+?_[\S]+?["']*)>([\S\r\n\s]+?)(</p>\s*)'''
                         ,r'<h5 id=\1>\2</h5>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p[^<]+?>\s*<[^<]+?>\s*<a (?:name|id)=(["'][\S]+?_[\S]+?_[\S]+?_[\S]+?["']*)>([\S\r\n\s]+?)(</p>\s*)'''
                         ,r'<h4 id=\1>\2</h4>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p align=["']*center["']*>\s*<[^<]+?>\s*<a (?:name|id)=(["']K[\d]+?["']*)>([\S\r\n\s]+?)\s*</p>\s*''',r'<h2 id=\1>\2</h2>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p align=["']*center["']*>\s*<[\S ]+?>\s*<a (?:name|id)=(["'](?:(?!_)[\S])+?["']*)>([\S\r\n\s]+?)(</p>\s*)'''
                         ,r'<h1 id=\1>\2</h1>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        
        recontent=re.sub(r'''<a (?:name|id)=(["'][\S]+?_[\S]+?_[\S]+?["']*)>\s*<p align=["']*center["']*>([\S\r\n\s]+?)(</[ap]>\s*){2}'''
                         ,r'<h3 id=\1>\2</h3>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<a (?:name|id)=(["'][\S]+?_[\S]+?["']*)>\s*<p align=["']*center["']*>\s*([\S\r\n\s]+?)(</[ap]>\s*)''',r'<h2 id=\1>\2</h2>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<a (?:name|id)=(["'][\S]+?["']*)>\s*<p align=["']*center["']*>\s*([\S\r\n\s]+?)(</[ap]>\s*)''',r'<h1 id=\1>\2</h1>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)

        recontent=re.sub(r'''<a (?:name|id)=(["']*Kap_[\S]+?_[\S]+?_[\S]+?_[\S]+?["']*)>\s*<p align=["']*center["']*>([\S\r\n\s]+?)(</[ap]>\s*){2}'''
                         ,r'<h4 id=\1>\2</h4>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<a (?:name|id)=(["']*Kap_[\S]+?_[\S]+?_[\S]+?["']*)>\s*<p align=["']*center["']*>([\S\r\n\s]+?)(</[ap]>\s*){2}'''
                         ,r'<h3 id=\1>\2</h3>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<a (?:name|id)=(["']*Kap_[\S]+?_[\S]+?["']*)>\s*<p align=["']*center["']*>([\S\r\n\s]+?)(</[ap]>\s*){2}''',r'<h2 id=\1>\2</h2>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<a (?:name|id)=(["'][\S]+?["']*)><(h[\d]) align=["']*center["']*>''',r'<\2 id=\1>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<a (?:name|id)=(["'][\S]+?_[\S]+?_[\S]+?_[\S]+?_[\S]+?_[\S]+?_[\S]+?["']*)>\s*<p align=["']*center["']*>([\S\r\n\s]+?)(</[ap]>\s*){2}'''
                         ,r'<h6 id=\1>\2</h6>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<a (?:name|id)=(["'][\S]+?_[\S]+?_[\S]+?_[\S]+?_[\S]+?_[\S]+?["']*)>\s*<p align=["']*center["']*>([\S\r\n\s]+?)(</[ap]>\s*){2}'''
                         ,r'<h6 id=\1>\2</h6>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<a (?:name|id)=(["'][\S]+?_[\S]+?_[\S]+?_[\S]+?_[\S]+?["']*)>\s*<p align=["']*center["']*>([\S\r\n\s]+?)(</[ap]>\s*){2}'''
                         ,r'<h5 id=\1>\2</h5>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p align=["']*center["']*>\s*<a (?:name|id)=(["']*I_III_[\S]+?_[\S]+?_[\S]+?_[\S]+?_[\S]+?_[\S]+?["']*)>([\S\r\n\s]+?)</a>\s*</p>'''
                         ,r'<h6 id=\1>\2</h6>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p align=["']*center["']*>\s*<a (?:name|id)=(["']*I_III_[\S]+?_[\S]+?_[\S]+?_[\S]+?_[\S]+?["']*)>([\S\r\n\s]+?)</a>\s*</p>'''
                         ,r'<h6 id=\1>\2</h6>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p align=["']*center["']*>\s*<a (?:name|id)=(["']*I_III_[\S]+?_[\S]+?_[\S]+?_[\S]+?["']*)>([\S\r\n\s]+?)</a>\s*</p>'''
                         ,r'<h5 id=\1>\2</h5>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p align=["']*center["']*>\s*<a (?:name|id)=(["']*I_III_[\S]+?_[\S]+?_[\S]+?["']*)>([\S\r\n\s]+?)</a>\s*</p>'''
                         ,r'<h4 id=\1>\2</h4>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p align=["']*center["']*>\s*<a (?:name|id)=(["']*I_III_[\S]+?_[\S]+?["']*)>([\S\r\n\s]+?)</a>\s*</p>'''
                         ,r'<h3 id=\1>\2</h3>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p align=["']*center["']*>\s*<a (?:name|id)=(["']*I_III_[\S]+?["']*)>([\S\r\n\s]+?)</a>\s*</p>'''
                         ,r'<h2 id=\1>\2</h2>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p align=["']*center["']*>\s*<a (?:name|id)=(["'][\S]+?_[\S]+?_[\S]+?_[\S]+?_[\S]+?_[\S]+?_[\S]+?["']*)>([\S\r\n\s]+?)(</[ap]>\s*){2}'''
                         ,r'<h6 id=\1>\2</h6>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p align=["']*center["']*>\s*<a (?:name|id)=(["'][\S]+?_[\S]+?_[\S]+?_[\S]+?_[\S]+?_[\S]+?["']*)>([\S\r\n\s]+?)(</[ap]>\s*){2}'''
                         ,r'<h6 id=\1>\2</h6>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p[\S ]*?>\s*<a (?:name|id)=(["'][\S]+?_[\S]+?_[\S]+?_[\S]+?_[\S]+?["']*)>([\S\r\n\s]+?)(</[ap]>\s*)'''
                         ,r'<h5 id=\1>\2</h5>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p[\S ]*?>\s*<[\S ]*?><a (?:name|id)=(["'][\S]+?_[\S]+?_[\S]+?_[\S]+?_[\S]+?["']*)>([\S\r\n\s]+?)(</[ap]>\s*)'''
                         ,r'<h5 id=\1>\2</h5>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p[\S ]*?>\s*<a (?:name|id)=(["'][\S]+?_[\S]+?_[\S]+?_[\S]+?["']*)>([\S\r\n\s]+?)(</[ap]>\s*)'''
                         ,r'<h4 id=\1>\2</h4>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<a (?:name|id)=(["'][\S]+?_[\S]+?_[\S]+?["']*)>\s*<p[\S ]*?>([\S\r\n\s]+?)(</[ap]>\s*)'''
                         ,r'<h3 id=\1>\2</h3>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<a (?:name|id)=(["'][\S]+?_[\S]+?["']*)>\s*<p[\S ]*?>\s*([\S\r\n\s]+?)(</[ap]>\s*)''',r'<h2 id=\1>\2</h2>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p align=["]*center["]*>\s*([IVXL]+?)\s*</p>''',r'<h2>\1</h2>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p align=["]*center["]*>\s*([IVXL]+?)\s*(</[^>]+?>)*<br>\s*((?:(?!<p)[\S\r\n\s])+?)\s*</p>''',r'<h2>\1<br>\2</h2>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''(<font[^<]+?>)[\s\r\n]*(<h[\d][^<]*?>)''',r'\2\1'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<font size=["]*5["]*><p>([\S\s\r\n]+?)</p>\s*</font>''',r'<h1>\1</h1>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<font size=["]*5["]*><p align=["]*center["]*>([\S\s\r\n]+?)</p>\s*</font>''',r'<h1>\1</h1>'
                         ,recontent ,flags=re.DOTALL | re.IGNORECASE)
        return recontent
    def requotes(recontent):
        recontent=re.sub(r'<small>(<a id="[\S]+?"></a>)</small>',r'\1',recontent,flags=re.DOTALL|re.IGNORECASE)
        recontent=re.sub(r"<p><small></p>[\s\r\n]*<p>","<small><p>",recontent,flags=re.DOTALL|re.IGNORECASE)
        recontent=re.sub(r"</p>[\s\r\n]*<p></small></p>","</small></p>",recontent,flags=re.DOTALL|re.IGNORECASE)
        recontent=re.sub(r"<i>[\s\r\n]*</p>[\s\r\n]*(<font size=[^<]+?><p>)","</p>\n"+r"\1<i>",recontent,flags=re.DOTALL|re.IGNORECASE)
        recontent=re.sub(r"</p>[\s\r\n]*</i>[\s\r\n]*</font>","</i></p></font>\n",recontent,flags=re.DOTALL|re.IGNORECASE)
        
        recontent=re.sub(r"""(?:<font color=[^<]+?|<font size=[^<]+?|<small)>[\s\r\n]*</p>[\s\r\n]*(</[^pf>]+>)*[\s\r\n]*</font>""",r"\1"+"</p>\n",recontent,flags=re.DOTALL|re.IGNORECASE)
        recontent=re.sub(r"""(<font color=[^<]+?|<font size=[^<]+?|<small)></p>[\s\r\n]*<p>""","</p>\n"+r"\1><p>",recontent,flags=re.DOTALL|re.IGNORECASE)
        recontent=re.sub(r"""</font><font[^<]+?size="2"[^<]*?>[\s\r\n]+</font><font size="2">"""," ",recontent,flags=re.DOTALL|re.IGNORECASE)
        recontent=re.sub(r"""</font><font[^<]+?size="2"[^<]*?></font><font size="2">""","",recontent,flags=re.DOTALL|re.IGNORECASE)
        recontent=re.sub(r"""</font><font[^<]+?size="2"[^<]*?>((?:(?!<p>)[\s\r\n\S])+?)</font><font[^<]+?>""",r"\1",recontent,flags=re.DOTALL|re.IGNORECASE)
        recontent=re.sub(r'<font size=["]*2["]*>[\s\r\n]*([\.,;\(\) ])[\s\r\n]*</font>',r'\1</font>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(?:<font color=[^<]+?>|<font size=[^<]+?>)[\s\r\n]+</font>',r' ',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(?:<font color=[^<]+?>|<font size=[^<]+?>)</font>',r'',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(<[ib]>)(<font size=["]*2["]*><p>)',r'\2\1',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''(?:<dir>[\s\r\n]*)+<font size=["']*2["']*><p>((?:(?!<font)[\s\r\n\S])+?)(?:</p>[\s\r\n]*(?:<[/]*dir>[\s\r\n]*)+</font>|</font>[\s\r\n]*(?:<[/]*dir>[\s\r\n]*)+</p>)''','\n'+r'<blockquote><p class="poem">\1</p></blockquote>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(?:<dir>[\s\r\n]*)+<p><font size=["\']*2["\']*>((?:(?!<font)[\s\r\n\S])+?)(?:</p>[\s\r\n]*(?:<[/]*dir>[\s\r\n]*)*</font>|</font>[\s\r\n]*(?:<[/]*dir>[\s\r\n]*)+</p>)','\n'+r'<blockquote><p class="poem">\1</p></blockquote>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''(?!<(?:td[^<]|<font[^<]|sup)>[\s\r\n]*)<font size=["']*2["']*><p>((?:(?!<[/]*td)[\s\r\n\S])+?)</(?:p|font)>[\s\r\n]*(</[^pf>\r\n]+?>)*</(?:p|font)>''',font2,recontent,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''(?!<td[^<]>[\s\r\n]*)<p><font size=["']*2["']*>((?:(?!<p>|<[/]*td)[\s\r\n\S])+?)</(?:p|font)>[\s\r\n]*(</[^pf>\r\n]+?>)*</(?:p|font)>''',font2,recontent,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(?!<td[^<]>[\s\r\n]*)<p><small>((?:(?!<p>|</td)[\s\r\n\S])+?)(?:</small>[\s\r\n]*</p>|</p>(?:[\s\r\n]+)*</small>)',r'<blockquote>\1</blockquote>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(?!<td[^<]>[\s\r\n]*)<small><p>((?:(?!<p>|</td)[\s\r\n\S])+?)(?:</small>[\s\r\n]*</p>|</p>(?:[\s\r\n]+)*</small>)',r'<blockquote>\1</blockquote>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''(?!<td[^<]>[\s\r\n]*)<font size=["']*2["']*><p((?:(?!<font[^<]+size=["]*2["]*|zizat|blockquote|</td)[\s\r\n\S]){40,}?)[\s\r\n]*</(?:p|font)>[\s\r\n]*(</[^p>\r\n]+?>[\s\r\n]*)*</(?:p|font)>''',r'<blockquote><p\1\2</p></blockquote>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''(?!<td[^<]>[\s\r\n]*)(<p[^<]*?>)<font size=["']*2["']*>((?:(?!<font[^<]+size=["]*2["]*|zizat|blockquote|</td)[\s\r\n\S]){40,}?)</(?:p|font)>[\s\r\n]*(</[^p>\r\n]+?>[\s\r\n]*)*</(?:p|font)>''',r'<blockquote>\1\2\3</p></blockquote>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''(?!<td[^<]>[\s\r\n]*)<font size=["']*2["']*><p((?:(?!<font[^<]+size=["]*2["]*|zizat|blockquote|</td)[\s\r\n\S]){40,}?)[\s\r\n]*(</font>)*[\s\r\n]*(</p>)+''',r'<blockquote><p\1\3</blockquote>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(?!<td[^<]>[\s\r\n]*)(<p[^<]*?>)<font size=["\']*2["\']*>((?:(?!<font[^<]+size=["]*2["]*|zizat|blockquote|</td)[\s\r\n\S]){40,}?)[\s\r\n]*(</font>)*[\s\r\n]*(</p>)+',r'<blockquote>\1\2\4</blockquote>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''(?!<(td[^<]|<font[^<]|sup)>[\s\r\n]*)<font size=["']*2["']*><p((?:(?!zizat|blockquote|</td)[\s\r\n\S]){20,}?)(?:</FONT>)*(<font size(?:(?!=2|="2")[\S])+?>(?:(?!<font size=["]*2|zizat|blockquote|</td)[\s\r\n\S]){2,}?)<font size=["]*2["]*>((?:(?!zizat|blockquote|</td)[\s\r\n\S]){20,}?)[\s\r\n]*(?:</font>)*[\s\r\n]*(</p>)+[\s\r\n]*(?:</font>)*''',r'<blockquote><p\1\2\3\4</blockquote>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<small><p((?:(?!<small|<font|zizat|blockquote|</td)[\s\r\n\S]){40,}?)[\s\r\n]*</small>'
                         ,r'<blockquote><p\1</blockquote>',recontent ,flags=re.DOTALL | re.IGNORECASE)  
        recontent=re.sub(r'<p><small>((?:(?!<small|<font|zizat|blockquote|</td)[\s\r\n\S]){40,}?)[\s\r\n]*</small>'
                         ,r'<blockquote><p>\1</blockquote>',recontent ,flags=re.DOTALL | re.IGNORECASE)  
        recontent=re.sub(r'<(?:p|div) class="zitat">((?:(?!<p|<div|blockquote)[\s\r\n\S])+?)</(?:p|div)>'
                         ,r'<blockquote>\1</blockquote>',recontent ,flags=re.DOTALL | re.IGNORECASE) 
        recontent=re.sub(r"<blockquote>(Geschrieb(?:(?!<p|<div|blockquote)[\s\r\n\S])+?)</blockquote>",
                         r"""<p class="zitat">\1</p>""",recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<small>((?:(?!<small|<font|blockquote)[ \S]){25,}?)(?:[\s\r\n]+)*</small>'
                         ,r'<blockquote>\1</blockquote>',recontent ,flags=re.DOTALL | re.IGNORECASE)  
        #recontent=re.sub(r"""<blockquote>(\["(?:(?!<p|<div|blockquote)[\s\r\n\S])+?\])</blockquote>""",r"""<p class="zitat">\1</p>""",recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r"""<blockquote>((?:(?!<p|<div|blockquote)[\s\r\n\S])*?aus [d]*em (?:(?!<p|<div|blockquote)[\s\r\n\S])+?)</blockquote>""",
                         r"""<p class="zitat">\1</p>""",recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r"""<blockquote>(Nach\:(?:(?!<p|<div|blockquote)[\s\r\n\S])+?)</blockquote>""",
                         r"""<p class="zitat">\1</p>""",recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r"""<blockquote>(Nach [d]*em(?:(?!<p|<div|blockquote)[\s\r\n\S])+?)</blockquote>""",
                         r"""<p class="zitat">\1</p>""",recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r"""(<td[^<]*?>[\s\r\n]*)<blockquote>""",r"\1",recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r"""</blockquote></td>""",r"</td>",recontent ,flags=re.DOTALL | re.IGNORECASE)
        return recontent
    def regex(recontent):
        recontent=re.sub(r'<body[^<]+?>',r'<body>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<!--[\s\S\r\n]*?-->',r'',recontent ,flags=re.DOTALL | re.IGNORECASE) 
        recontent=re.sub(r'<P><SMALL>Pfad[ \S]+?me/me[\S ]+?</[\S]{1,4}>[\s\r\n]*<HR[\S ]*?>',r'',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<P><SMALL>Pfad[ \S]+?me/me[\S ]+?<[^<]+?>[\s\r\n\S]*</small>[\s\r\n]*</p>[\s\r\n]*<HR[^<]*?>',r'',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<table ((?:cellspacing="0"\s*)|(?:cellpadding="0"\s*)){2}>\s*<tr>\s*<td valign="top"><small>Seitenzahlen',
                 r'''<table \1 class="seitenzahlen">
<tr>
<td valign="top">Seitenzahlen''',recontent,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<font[ \S]+?><p>(Seitenzahlen(?:(?!<p|<font)[\s\r\n\S])+?)(?:</font>\s*|</p>\s*){2}',r'<div class="seitenzahlen">\1</div>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<SMALL><P>(Seitenzahlen(?:(?!<p|<small)[\s\r\n\S])+?)(?:</small>\s*|</p>\s*){2}',r'<div class="seitenzahlen">\1</div>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<P><SMALL>(Seitenzahlen(?:(?!<p|<small)[\s\r\n\S])+?)(?:</small>\s*|</p>\s*){2}',r'<div class="seitenzahlen">\1</div>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r"<strong>",r"<b>",recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r"</strong>",r"</b>",recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<span class="top">([\S ]+?)</span>',r'\1',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r"&nbsp;",r" ",recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=repagenum(recontent)

        #recontent=re.sub(r'(<b><p><a name="S[\d]+?">\|[\d]+?\|</a>)</p>(</b>[ \S]+?)[\r\n]',r'\1</p>\2',recontent ,flags=re.DOTALL | re.IGNORECASE)
       

        recontent=re.sub(r'<p[^<]*>\s*</p>',r'',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=renote(recontent)

        #recontent=re.sub(r'/web/[\d]+?/[\S]+?/me/me[0]*([\d]+?)/me([\d]*?)_([\d]+?.htm)([#]*)',r'../\1/ME\2-\3l\4',recontent ,flags=re.DOTALL | re.IGNORECASE)
        #recontent=re.sub(r'/web/[\d]+?/[\S]+?/\.\./me_([\S]+?.htm)([#]*)',r'../../ME-\1l\2',recontent  ,flags=re.DOTALL | re.IGNORECASE)
        #recontent=re.sub(r'[\./]*(?:/me/)*me[0]*([\d]+?)/me([\d]+?)_([\d]+?.htm)([#]*)',r'../\1/ME\2-\3l\4',recontent,flags=re.DOTALL | re.IGNORECASE)
        #recontent=re.sub(r'[-]*[ ]{0,2}<[\S]{1,6}>\|[\d]+?\|</[\S]{1,6}>','',recontent ,flags=re.DOTALL | re.IGNORECASE)

        recontent=re.sub(r'<A name=["]*([\S]+?)["]*>\|[\d]+?\|</a>',r'<a id="\1"></a>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<A name=([\S]+?)>&lt;[\d]+?&gt;</a>',r'<a id=\1></a>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'[-]*[ ]{0,2}<a id=("S[\d]+?")></a>',r'<a id=\1></a>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'([a-zA-Z])[ ]+(<sup><a[^<]+?>[\S]+?</a></sup>)[ ]*([a-zA-Z&])',r'\1\2 \3',recontent ,flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'[-]*\s+(<a id=["]*S[\S]+?["]*></a>)[ ]+',r'\1 ',content ,flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'[-]+\s+(<a id=["]*S[\S]+?["]*></a>)([a-zA-Z])',r'\1\2',content ,flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'([a-zA-Z])[ ]+(<sup><a[^<]+?>[\S]+?</a></sup>)[ ]*([\.,;])',r'\1\2\3',content ,flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'([a-zA-Z])[ ]+(<sup><a[^<]+?>[\S]+?</a></sup>)[ ]*<',r'\1\2<',content ,flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'[\.]+[ ]*(<sup><a[^<]+?>[\S]+?</a></sup>)[ ]+',r'\1. ',content ,flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'[\.]+[ ]*(<sup><a[^<]+?>[\S]+?</a></sup>)',r'\1.',content ,flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'>[ ]*(<sup><a[^<]+?>[\S]+?</a></sup>)[ ]+([\.,;])',r'>\1\2',content ,flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'[ ]+(<sup><a[^<]+?>[\S]+?</a></sup>)</h',r'>\1</h',content ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(</(?:p|blockquote)>)[\s\r\n]*(<sup><a[^<]+?>[\S]+?</a></sup>)',r'\2\1',content ,flags=re.DOTALL | re.IGNORECASE)
        
        recontent=re.sub(r'<a name=',r'<a id=',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''src="/web/[\S ]+?/me/me[\d]+?/([\S]+?)"''',r'src="\1"',recontent ,flags=re.DOTALL | re.IGNORECASE) 
        recontent=re.sub(r'</font><font size=["]*2["]*>[\s\r\n]+<br>[\s\r\n]+?</font>',r'</font><br>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'</font><font size=["]*2["]*>[\s\r\n]+(</[\S]+?>)[\s\r\n]+?</font>',r'</font>\1',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'</font><font size=["]*2["]*>[\s\r\n]+(<[^<]+?>)[\s\r\n]+?</font>',f'</font>\n'+r'\1',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=retitle(recontent)
        recontent=requotes(recontent)  
        #recontent=re.sub(r'<p class="zitat">([\s\S]+?)</p>',r'<div class="zitat">\1</div>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''<p align=["']*CENTER["']*>([\S ]+?)<br>\s+(<font size="\+2">[\S\r\n ]+?</font>)</p>'''
                         ,r'<h1>\1<br>\2</h1>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<p align=["\']*center["\']*>([\s\S]+?)</p>',r'<p class="ctr">\1</p>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<p align=["\']*right["\']*>([\s\S]+?)</p>',r'<p class="rgt">\1</p>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<p align=["\']*lft["\']*>([\s\S]+?)</p>',r'<p class="lft">\1</p>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        #recontent=re.sub(r'<p (class=[\S]+?)>([\s\S]+?)</p>',r'<p \1>\2</p>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        #recontent=re.sub(r'<p>([\r\n\s\S]+?)</p>',r'<br>\1<br>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(</h[d]>)<p',r'\1'+'\n<p',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent = recontent.replace(r"&szlig;", r"ß")
        recontent = recontent.replace(r"&ouml;", r"ö")
        recontent = recontent.replace(r"&auml;", r"ä")
        recontent = recontent.replace(r"&uuml;", r"ü")
        recontent = recontent.replace(r"&Szlig;", r"ẞ")
        recontent = recontent.replace(r"&Ouml;", r"Ö")
        recontent = recontent.replace(r"&Auml;", r"Ä")
        recontent = recontent.replace(r"&Uuml;", r"Ü")
        recontent = recontent.replace(r"[…]",r"[...]")
        recontent=re.sub(r'(<[\S]+?>)[ ]*(<sup><a href=[\S]+? id=[\S]+?>[\S]+?</a></sup>)[ ]*([\.,;"])',r'\3\2\1<br>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(<[\S]+?>)[ ]*(<sup><a id=[\S]+? href=[\S]+?>[\S]+?</a><sup>)[ ]*([\.,;"])',r'\3\2\1',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(<sup><a id=[\S]+? href=[\S]+?>[\S]+?</a></sup>)([\.,;"])[ ]*(<[\S]{2}>)',r'\2\1\3'+f'\n',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(<sup><a id=[\S]+? href=[\S]+?>[\S]+?</a></sup>)([\.,;"])[ ]*</font><br>',r'\2\1</font>'+'<br>\n',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent = re.sub(r"<(h[\d]>)([ \r\n\S]+?)</h[\d]>",r"<\1\2</\1",recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r"[\s\r\n]+(</(?:blockquote|p|font)>)<p>",r'\1'+'\n<p>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r"(</(?:blockquote|p|font)>)<p>",r'\1'+'\n<p>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent = re.sub(r"<([/]*)em>",r"<\1i>",recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r"(<[ib]>)[\s\r\n]*(</p>|</h[\d]>|</blockquote>|<br>)[\s\r\n]*?(<p[^<]*>)",r"\2"+"\n"+r"\3\1",recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r"(<[ib]>)(<p|<h[\d]|<blockquote|<br)([^<]*?)>",r"\2\3>\1",recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r"(</p>|</h[\d]>|</blockquote>|<br>)[ ]*?(</[ib]>)",r"\2\1",recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r"(</p>|</h[\d]>|</blockquote>|<br>)[\s\r\n]+?(</[ib]>)[\r\n]+?",r"\2\1\n",recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r"(</p>|</h[\d]>|</blockquote>|<br>)[\s\r\n]+?(</[ib]>)",r"\2\1\n",recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r"[ ]*<i>[ ]+?</i>[ ]*"," ",recontent,flags=re.DOTALL|re.IGNORECASE)
        recontent=re.sub(r"<i>[\r\n\s]+?</i>","",recontent,flags=re.DOTALL|re.IGNORECASE)
        recontent =recontent.replace(r"］", r"]")
        recontent=re.sub(r'<table(?:(?!<table)[\S\r\n\s])*?href="[\S]+?">[\S ]+?MLWerke(?:(?!<table)[\S\r\n\s])*?</table>',r'',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<table(?:(?!<table)[\S\r\n\s])*?href="[\S]+?">[\S ]+?MLWerke(?:(?!<table)[\S\r\n\s])*?</TR>[\s\r\n]*<table',r'<table',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<table(?:(?!<table)[\S\r\n\s])*?href="[\S]+?">[\S ]+?MLWerke(?:(?!<table)[\S\r\n\s])*?</TR>',r'',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<table(?:(?!<table)[\S\r\n\s])*?href="[\S]+?">[\S ]+?inh[\S]lt(?:(?!<table)[\S\r\n\s])*?</table>',r'',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<table(?:(?!<table)[\S\r\n\s])*?href="[\S]+?shtml">(?:(?!<table)[\S\r\n\s])*?</table>',r'',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r"""([a-züäöß,."!])[ ]*[\r\n]+?([a-züäöß])""",r'\1 \2',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''[\s\r\n]+bgcolor="#(ffffee|99CC99|6C6C6C)"''','',recontent, flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'''(?:<br>[\s\r\n]*)+</P>''',r'</P>',recontent, flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<FONT size="2" color="#006600">',r'',recontent, flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<body>[\s\r\n]*<p>[\s\r\n]*<table',r'''<body>
<table''',recontent, flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'[ ]+?</p>[\s\r\n]+',r'''</p>
''',recontent, flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r"""(</h[\d]>|</blockquote>|</font>)(<[hp\df]+?)""",r"\1"+"\n"+r"\2",recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r"""(</blockquote>|</p>)(</body>)""",r"\1"+"\n"+r"\2",recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'></title>',r'</title>',recontent, flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(?:<p>[\s\r\n]*)*<HR[^<]*?>[\s\r\n]*(?:</p>[\s\r\n]*)*<aside',r'<aside',recontent, flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'</aside>[\s\r\n]*(?:<p>[\s\r\n]*)*<HR[^<]*?>[\s\r\n]*(?:</p>)*',r'</aside>',recontent, flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(?:<p[^<]*?>[\s\r\n]*)*(<HR[^<]*?>)[\s\r\n]*(?:</p>[\s\r\n]*)*<p><a href="',r'\1<p class="TCC"><a href="',recontent, flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(?:<p>[\s\r\n]*)*Inhalt:',r'<p class="TCC">Inhalt:',recontent, flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<p>[\s\r\n]*(<a href="[\S]+?">[\S ]+?</a><br[/]*>)',r'<p class="TCC">\1',recontent, flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<p class="ctr">(?:<center>)*<table',r'<table',recontent, flags=re.DOTALL | re.IGNORECASE)
        #recontent=re.sub(r"""<body>((?:(?!<aside)[\s\r\n\S]+?))<p class="fni">([\s\r\n\S]+?)</body>""",r'''<body>\1
#<aside class="fn">
#<p class="fni">
#\2</aside>
#</body>''',recontent ,flags=re.DOTALL|re.IGNORECASE)
        recontent=re.sub(r"(?:<hr[^<]*?>[\s\r\n]*)*[\s\r\n]*</body>",r"</body>",recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r"<body>[\s\r\n]*(?:<hr[^<]*?>[\s\r\n]*)*",r"<body>"+'\n',recontent ,flags=re.DOTALL | re.IGNORECASE)
        return recontent 
    return regex(content)     
def brief(recontent,filename):
    def detecttitle(match):
        text=match.group(0)

        #datematch=re.findall(r" – ",recontent,flags=re.DOTALL|re.IGNORECASE)
        #if not datematch and not filename.startswith("ME26"):
        #    print(filename+" 无日期！")
        return recontent
    def asidepatch(match):
        text=match.group(0)
        if """<div class="fnt">Textvarianten</div>""" in text:
            if "siehe " in text or "Siehe " in text:
                text=re.sub(r"""<div class="fnt">Textvarianten</div>""","""<div class="fnt">Textvarianten und Verweise</div>""",text,flags=re.DOTALL|re.IGNORECASE)
        recontent=text
        recontent=re.sub(r"<aside>",r"""<aside class="fn">""",recontent,flags=re.DOTALL|re.IGNORECASE)
        return recontent
    recontent=re.sub(r"""<p align="right"><div class="fnt">Textvarianten</div>([\S\s\r\n]+?)</p>[\s\r\n]+<p align="right">([\S ]+?)</p>""",r"""<p class="rgt">\1<br>\2</p>""",recontent,flags=re.DOTALL|re.IGNORECASE)
    recontent=re.sub(r"""<p align="center">""",r"""<p class="ctr">""",recontent,flags=re.DOTALL|re.IGNORECASE)
    recontent=re.sub(r"""<p align="right">""",r"""<p class="rgt">""",recontent,flags=re.DOTALL|re.IGNORECASE)
    recontent=re.sub(r"<br/>",r"<br>",recontent,flags=re.DOTALL|re.IGNORECASE)
    recontent=re.sub(r"""<aside>[\S\r\n\s]+?</aside>""",asidepatch,recontent,flags=re.DOTALL|re.IGNORECASE)
    return recontent
def open_files(html_files,input_dir,output_dir):

    output_dir.mkdir(exist_ok=True)
    for idx,file in enumerate(html_files):
        filename=file.name
        if 'me42' in filename:
            continue        
        relative_path = file.relative_to(input_dir)
        if relative_path in ['261','262','263']:
            continue
        output_path = output_dir / relative_path  
        # 创建输出文件的目录
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:      
            encodings = ['utf-8','iso-8859-1',  'gbk', 'cp1252']
            for encoding in encodings:
                with open(file, 'r', encoding=encoding, errors='ignore') as f:
                    content = f.read()
                break  # 成功读取后跳出循环
        except Exception as e:
            raise Exception(f"所有解码尝试都失败: {e}") 
        if file.parent.name.startswith("me"):
            content=process_recontent(content)
        else:
            content=brief(content,filename)
        #content=re.sub(r'<P>',r'<P>',content,flags=re.IGNORECASE)
        #content=re.sub(r'<A NAME=',r'<A ID=',content,flags=re.IGNORECASE)
        with open(output_path, 'w', encoding='utf-8-sig',newline='') as f:
            f.write(content)
def main():
    input_dir1 = r"D:\马恩列总装\mewerke"
    input_dir2 = r"D:\马恩列总装\MEWB1"
    output_d =Path(r"D:\马恩列总装\MEW-O")
    htmls1=list(Path(input_dir1).rglob("*.htm"))
    htmls2=list(Path(input_dir2).rglob("*.html"))
    open_files(htmls1,input_dir1,output_d)
    open_files(htmls2,input_dir2,output_d)
    #output_dirs = [r"./mlread/docs/MEW",r"./MARX-ZH-CN.github.io1/docs/MEW"] 
    # 配置参数
    book_title = "KARL MARX FRIEDRICH ENGELS WERKE"  # 修改为你的书名
    book_author = "Karl Marx & Friedrich Engels & 中共中央马克思、恩格斯、列宁、斯大林著作编译局"      # 修改为作者名
    #output_dirs = [r"./de/MEW"]  # 输出目录名
    output_dirs = [r"./mlread/docs/MEW",r"./MARX-ZH-CN-node/MEW"] 
    #output_dirs = [r"./MARX-ZH-CN.github.io1/MEW"] 

    excel_file=Path(r"LENIN-toc.xlsx")
    # 创建构建器
    wb = openpyxl.load_workbook(excel_file)            
    sheet = wb.active
    ws = wb['Sheet1']    
    # 创建构建器
    builder = EpubBookBuilder(book_title, book_author, "de",ws)

    # 扫描书籍结构
    builder.scan_book_structure(output_d)
    
    if builder.volumes:
        # 构建EPUB
        builder.build_epub_folder(output_dirs)  
main()    
