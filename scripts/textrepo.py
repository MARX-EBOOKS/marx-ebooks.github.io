import re
from bs4 import BeautifulSoup
#import LENINmelzhcn
#import MEWmelzhcn
class HeadingExtractor:
    """HTML标题层级提取器 (h1-h6)，使用BeautifulSoup"""
    def __init__(self,vol_num,prefix):
        self.headings = []
        self.volnum=vol_num
        self.prefix=prefix
    
    def extract_headings_from_html(self, html_content, source_file, chapter_number,title):
        volume_number=self.volnum
        prefix=self.prefix
        """从HTML内容中提取所有标题层级并添加ID"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
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
                    ncxid= f"{prefix}{volume_number:02d}{chapter_number:03d}-{i+1}"
                    if not anchor_id:
                        anchor_id = ncxid
                        tag['id']=anchor_id
                    text=text.replace("<","&lt;")
                    text=text.replace(">","&gt;")
                    text=re.sub(r'￥￥￥[\S ]+?￥￥￥',r'',text,flags=re.DOTALL|re.IGNORECASE)
                    # 确定标题级别
                    anchor_id=tag.get('id')
                    if not anchor_id:
                        anchor_id = ncxid
                        tag['id']=anchor_id                    
                    level = int(tag.name[1])  # h1->1, h2->2, etc.
                    headings_data.append({
                        'tag': tag.name,
                        'text': text,
                        'level': level,
                        'id': anchor_id,
                        'source_file': source_file,
                        'chapter_number': chapter_number,
                        'ncxid':ncxid
                    })
            
            fixed_content=str(soup.body)
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
</html>"""                
                return content, headings_data
            else:
                return str(soup), headings_data

            
            
            
        except Exception as e:
            print(f"  警告: 解析标题时出错: {e}")
            return html_content, []
class textrep:
    def __init__(self,vol_number,content,bookname):
        self.volume_number=vol_number
        self.content=content
        self.table_count=0
        self.quote_count=0
        self.tables=[]
        self.quotes=[]
        self.bookname=bookname
    def text44_re(self,match):
        match_text=match.group(2)
        recontent=match_text
        if self.volume_number!=58:
            recontent = re.sub(r'[\s\r\n]*((?:1[89][\d]+?)年[\d]{1,2}月[\d]{1,2}日)[\s\r\n]*</h1>', r'''</h1>
<p class="date-l">　　\1</p>''', recontent, flags=re.DOTALL | re.IGNORECASE)
            recontent = re.sub(r'[\s\r\n]*([—到〔〕\[\]不早晚于之或间以前后中年月上下半日初末底和旬\d]{2,}?)[\s\r\n]*</h1>', r'''</h1>
<p class="date">（\1）</p>''', recontent, flags=re.DOTALL | re.IGNORECASE)
            recontent = re.sub(r'[\s\r\n]+([（）（）—到（）\(\)〔〕\[\]不早晚于之或间以前后中年月上下半日初末底和旬\d]{2,}?)[\s\r\n]*</h1>', r'''</h1>
<p class="date">\1</p>''',recontent, flags=re.DOTALL | re.IGNORECASE)
            recontent = re.sub(r'[\s\r\n]*([（）（）—到（）\(\)〔〕\[\]不早晚于之或间以前后中年月上下半日初末底和旬\d]{2,}?)[\s\r\n]*</h1>', r'''</h1>
<p class="date">\1</p>''',recontent, flags=re.DOTALL | re.IGNORECASE)   
        recontent = re.sub(r'</h1>[\s\n\r]*<p>[\s\n\r]*(?:&emsp;)*((?:1[89][\d]+?)年[月日\d]{4,})<br>',r'''</h1>
<p class="date-l">　　\1</p>
<p>''', recontent, flags=re.DOTALL | re.IGNORECASE)
        recontent = re.sub(r'</h1>[\s\n\r]*<p>[\s\n\r]*(?:&emsp;)*((?=.*月)[—到〔〕\[\]不早晚于之或间以前后中年月上下半日初末底和旬\d]{2,})<br>',r'''</h1>
<p class="date">（\1）</p>
<p>''', recontent, flags=re.DOTALL | re.IGNORECASE)

        recontent = re.sub(r'</h1>[\s\n\r]*<p>[\s\n\r]*(?:&emsp;)*((?=.*年)[—到〔〕\[\]不早晚于之或间以前后中年月上下半日初末底和旬\d]{2,})<br>',r'''</h1>
<p class="date">（\1）</p>
<p>''', recontent, flags=re.DOTALL | re.IGNORECASE)
        recontent = re.sub(r'</h1>[\s\n\r]*<p>[\s\n\r]*(?:&emsp;)*((?=.*月)[（）（）—到（）\(\)〔〕\[\]不早晚于之或间以前后中年月上下半日初末底和旬\d]{2,})<br>',r'''</h1>
<p class="date">\1</p>
<p>''', recontent, flags=re.DOTALL | re.IGNORECASE)
        fixed_content= re.sub(r'</h1>[\s\n\r]*<p>[\s\n\r]*(?:&emsp;)*((?=.*年)[（）（）—到（）\(\)〔〕\[\]不早晚于之或间以前后中年月上下半日初末底和旬\d]{2,})<br>',r'''</h1>
<p class="date">\1</p>
<p>''',recontent, flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'(</h[\d]>)(?:<br>)*\s*(<sup><a[ \S]+?</a></sup>)(?:<br>)*',r'\2\1'+'\n',fixed_content,flags=re.DOTALL|re.IGNORECASE) 
        fixed_content=re.sub(r'(</h[\d]>)(?:<br>)*\s*(<p class="date(?:-l)*">[　\S]+?</p>)\s*<p>\s*(<sup><a[ \S]+?</a></sup>)\s*(?:<br>)*',r'\3\1'+'\n'+r'\2'+'\n<p>',fixed_content,flags=re.DOTALL|re.IGNORECASE) 
        fixed_content=re.sub(r"<<br>　　\?>",r"&lt;???&gt;",fixed_content,flags=re.DOTALL|re.IGNORECASE)
        fixed_content=re.sub(r"<<br>　　>",r"&lt;??&gt;",fixed_content,flags=re.DOTALL|re.IGNORECASE)
        fixed_content=fixed_content.replace('<br>','</p>\n<p>') 
        fixed_content=match.group(1)+fixed_content+match.group(3)
        return fixed_content
    def text46_re(self,match):
        match_text=match.group(2)
        fixed_content=match_text.replace('<br>','</p>\n<p>')
        fixed_content=match.group(1)+fixed_content+match.group(3)
        return fixed_content
    def quote_re(self,match):

        match_text=match.group(1)
        table_pattern = r'(?:<p>\s*|<div title="table">\s*)*(<table[^<]+?>[\s\r\n\S]+?</table>)\s*(?:<br>|<p>\s*)*'
        fixed_content=match_text
        #fixed_content=fixed_content.replace("<p>","<br>")
        fixed_content=re.sub(table_pattern,self.save_table,fixed_content, flags=re.DOTALL | re.IGNORECASE)
        p_match=re.match(r'^([　\t]+?[ ]*(?:(?!<br>|<[/]*div|<[/]*p|<table)[\S\s\r\n])*?)<br>$',match_text, flags=re.DOTALL | re.IGNORECASE)
        p2_match=re.match(r'^((?:(?!<br>|<[/]*div|<[/]*p|<table)[\S ])+?)<br>$',match_text, flags=re.DOTALL | re.IGNORECASE)
        if p_match:
            fixed_content=f'<blockquote>{p_match.group(1)}</blockquote>'
            return fixed_content
        if p2_match:
            fixed_content=f'<blockquote>{p2_match.group(1)}</blockquote>'
            return fixed_content

        fixed_content=re.sub(r'((?:[\t]+?[ ]*|[　 ]{2,}?)(?:(?!<br>|<[/]*div|<[/]*p)[\S\s\r\n])*?)<br>',r'<p>\1</p>',fixed_content, flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'^([^<>\r\n]+?)<br>$',r'<p>\1</p>'+'\n',fixed_content, flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'<div (class=[\S]+?)>((?:(?!<div)[\S\r\n\s])+?)(</div>|$)',self.div_re,fixed_content, flags=re.DOTALL | re.IGNORECASE)
        #fixed_content=re.sub(r'<div ((?:align|style)\s*=\s*[\S ]+?)>((?:(?!<[/]*div)[\S\r\n\s])+?)(</div>|$)',self.div_re,fixed_content, flags=re.DOTALL|re.IGNORECASE)
        for i, table in enumerate(self.tables):
            fixed_content=fixed_content.replace(f"<TABLE ID=\"TRP{i:03d}\"></TABLE>",table)
        fixed_content=re.sub(r'<div ((?:align|style)\s*=\s*[\S ]+?)>((?:(?!<[/]*div)[\S\r\n\s])+?)(</div>|$)',self.p_re,fixed_content, flags=re.DOTALL|re.IGNORECASE)
        fixed_content=f'<blockquote>{fixed_content}</blockquote>'
        fixed_content=re.sub(r'<br>\s*</blockquote>',"</blockquote>",fixed_content,flags=re.DOTALL | re.IGNORECASE)

        return fixed_content
    def save_quote(self,match):          
        text=match.group(1)
        pattern=r"<div class=\"quote\">([\s\r\n\S]+?)</div>"
        quote_fix=re.sub(pattern,self.quote_re,text, flags=re.DOTALL | re.IGNORECASE)
        self.quotes.append(quote_fix)            
        replacetable=f"<BLOCKQUOTE ID=\"BQ{self.quote_count:03d}\"></BLOCKQUOTE>"
        self.quote_count+=1
        return replacetable
    def div_re(self,match):
        match_text=match.group(2)
        p_match=re.match(r'^<p>([\t　 \S]+?)</p>$',match_text, flags=re.DOTALL | re.IGNORECASE)
        if p_match:
            fixed_content=p_match.group(1)
        else:
            fixed_content=re.sub(r'<p>([\s\r\n\S]+?)</p>',r'\1<br>',match_text,flags=re.DOTALL | re.IGNORECASE)

        if match.group(1).startswith(("class=","CLASS=")):
            fixed_content=f'<p {match.group(1)}>{fixed_content}</p>'
            fixed_content=re.sub(r'<br[/]*>\s*</p>',r"</p>",fixed_content,flags=re.DOTALL | re.IGNORECASE)
        else:
            fixed_content=f'<div {match.group(1)}>{fixed_content}</div>'
            fixed_content=re.sub(r'<br[/]*>\s*</div>',r"</div>",fixed_content,flags=re.DOTALL | re.IGNORECASE)
        #fixed_content=fixed_content.replace("<br>","<br/>")
        return fixed_content
    def p_re(self,match):
        match_text=match.group(2)
        p_match=re.match(r'^<p>([\t　 \S]+?)</p>$',match_text, flags=re.DOTALL | re.IGNORECASE)
        if p_match:
            fixed_content1=p_match.group(1)
        else:
            fixed_content1=re.sub(r'<p>([\s\r\n\S]+?)</p>',r'\1<br>',match_text,flags=re.DOTALL | re.IGNORECASE)
        search_words1=[r'译',r'文',r"载于",r"第",r"次",r"写于",r"页",r"《"] 
        search_words2=[r'马',r'恩',r"列",r"乌",r"卡",r"弗",r"尼",r"摩",r"·",r".",r"宁</b>",r"年",r"月",r"委员",r"会",r"编辑","你","您","者"] 
        namesfind=re.findall("<br>",fixed_content1,flags=re.DOTALL | re.IGNORECASE)
        if len(namesfind)>3 and match.group(1).endswith(("'rt'","right'",'right"','"rt"')):
            table_fix=f'''<table class="rt"><tbody><tr><td>
{fixed_content1}</td></tr></tbody></table>'''
            table_fix=self.judgesign(table_fix,r'class="rt"')
            table_fix=re.sub("<br></td></tr>","</td></tr>",table_fix,flags=re.DOTALL | re.IGNORECASE)
            return table_fix
        if ("<b>18" in match_text or "<b>[18" in match_text) and "于" in match_text and self.bookname=="MEA":
            fixed_content=f'<p class="add">{fixed_content1}</p>'            
        elif (any(word in match_text for word in search_words1)) and match.group(1).endswith(("'rt'","right'",'right"','"rt"')) and not "编辑" in match_text and not "委员" in match_text:
            fixed_content=f'<p class="src">{fixed_content1}</p>'
        elif any(word in match_text for word in search_words2) and match.group(1).endswith(("'rt'","right'",'right"','"rt"')):
            fixed_content=f'<p class="sign">{fixed_content1}</p>'
        else:
            fixed_content=f'<p {match.group(1)}>{fixed_content1}</p>'
        fixed_content=re.sub(r'<br[/]*>\s*</p>',r"</p>",fixed_content,flags=re.DOTALL | re.IGNORECASE)
        
        #fixed_content=fixed_content.replace("<br>","<br/>")
        return fixed_content
    def repdiv(self,match):
        text=match.group(2)
        text=text.replace("<br>","<br/>")
        text=r"<tr><td"+match.group(1)+text+r"</td></tr>"
        return text
    def head_re(self,match):
        match_text=match.group(3)
        fixed_content=re.sub(r'<p>([\s\r\n\S]+?)</p>'
                                 ,r'<br/>\1<br/>',match_text,flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'([\s\r\n\S]+?)<br>$'
                                 ,r'\1',fixed_content,flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'(<br[/]*>\s*){2,}'
                                 ,r'<br/>',fixed_content,flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'^(<br[/]*>\s*)+'
                                 ,r'',fixed_content,flags=re.DOTALL | re.IGNORECASE)
        fixed_content=f'<{match.group(1)}{match.group(2)}>{fixed_content}</{match.group(1)}>'
        return fixed_content
    def link_td(self,matchs):
        matchtext=matchs.group(5)
        link_match=re.findall(r'<a href=["\']\#[\d]*',matchtext, flags=re.DOTALL | re.IGNORECASE)
        if link_match:
            matchtext=re.sub(r'[· ]*(<a href=["\']\#[\d]*)',r'\1',matchtext,flags=re.DOTALL | re.IGNORECASE)
            matchtext="<div class=\"TCC\">"+matchtext+"</div>"
            return matchtext        
        return matchs.group(0)
    def deletetable(self,matchtext):
        table_fix=matchtext
        matchsingle=re.match(r"""<table class="(?:sign|rt)">\s*<tr>\s*<td>\s*((?:(?!<br>)[\s\r\n\S])+?<br>)\s*</td>""",matchtext, flags=re.DOTALL | re.IGNORECASE)
        if matchsingle:
            table_fix=f"""<p class="rt">{matchsingle.group(1)}</p>"""
            table_fix=re.sub(r"<p (class=[\S]+?)>([\S\s\r\n]+?)</p>",self.p_re,table_fix, flags=re.DOTALL | re.IGNORECASE)
        else:
            matchsingle=re.match(r"""<table class="(?:src rt)">\s*<tr>\s*<td>\s*((?:(?!<br>)[\s\r\n\S])+?<br>)\s*</td>""",matchtext, flags=re.DOTALL | re.IGNORECASE)
            if matchsingle:
                table_fix=f"""<p class="src">{matchsingle.group(1)}</p>"""
        return table_fix
    def td_re(self,matchs):
        matchtext=matchs.group(5)
        table_fix=matchtext+r'<br>'
        table_fix=re.sub(r'(?:<div|<p)([^<]*?>)([\S\s\r\n]+?)</(?:div|p)>(?:<br>)*',self.repdiv,table_fix,flags=re.DOTALL | re.IGNORECASE)
        replace=r'<tr><td>'+r'''\1</td>
</tr>
'''
        table_fix=re.sub(r'([\S 　\t]+?)<br>(?:</div>)+',replace,table_fix,flags=re.DOTALL | re.IGNORECASE)
        table_fix=re.sub(r'([\S 　\t]+?)<br>',replace,table_fix,flags=re.DOTALL | re.IGNORECASE)
        table_fix=table_fix.replace("<br/>","<br>")
        style=f"{matchs.group(2)};{matchs.group(4)};".replace(";;",";")
        table_fix=f'<table{matchs.group(1)}style="{style}"{matchs.group(3)}>'+table_fix+r'</table>'            
        return table_fix
    def judgesign(self,table_fix,classtype):
        if not "宁</b>" in table_fix and not "·" in table_fix and (not "马克思" in table_fix and not "恩格斯" in table_fix and "文" in table_fix and "《" in table_fix) or ("写" in table_fix and ("马克思" in table_fix or "恩格斯" in table_fix)):
            table_fix=re.sub(r'<table class="[\S]+?">',r'<table class="src rt">',table_fix,flags=re.DOTALL | re.IGNORECASE)
            if self.bookname=="MEA":
                table_fix=re.sub(r'<br>[　]+','<br>\n',table_fix,flags=re.DOTALL | re.IGNORECASE)
        elif ("·" in table_fix or "您的" in table_fix or "你的" in table_fix or r"委员" in table_fix or r"会" in table_fix or r"编辑" in table_fix or "宁</b>" in table_fix or "宁<br>" in table_fix or "者" in table_fix) and classtype.endswith(("'rt'",'"rt"')):
            table_fix=re.sub(r'<table class="rt">',r'<table class="sign">',table_fix,flags=re.DOTALL | re.IGNORECASE)
        return table_fix

    def save_table(self,match):        
        pattern=r'''<table([^<]+?)style=["']([\S ]+?)["']([^<]+?)>[\s\r\n]*<tr><td style=["']([\S ]+?)["']>([\S\r\n\s]+?)</td></tr></table>'''
        table_fix=match.group(1)
        table_fix=re.sub(pattern,self.link_td,table_fix, flags=re.DOTALL | re.IGNORECASE)
        table_fix=self.deletetable(table_fix)
        if "载于" in table_fix or "译" in table_fix:
            table_fix=re.sub(r'([\S 　\t]+?)<br>(?:</div>)+',r'\1<br>',table_fix,flags=re.DOTALL | re.IGNORECASE)
        tableclassm=re.match(r'<table class=("[^<]+?")>',table_fix, flags=re.DOTALL | re.IGNORECASE)
        #leninsignmatch=re.match(r"列\s*宁\s*<[/]*b",table_fix, flags=re.DOTALL | re.IGNORECASE)
        if tableclassm:
            if tableclassm.group(1) in ['"rt"','"sign"']:
                table_fix=self.judgesign(table_fix,tableclassm.group(1))
            if tableclassm.group(1) in ['"add rt"']:    
                table_fix=re.sub(r"<br>[\s\r\n]+?","""<br>
""",table_fix, flags=re.DOTALL | re.IGNORECASE)
                #print(table_fix) 
        tableclassm=re.match(r'<table class=("sign"|"rt")>',table_fix, flags=re.DOTALL | re.IGNORECASE) 
               
        #leninsignmatch=re.match(r"列\s*宁\s*<[/]*b",table_fix, flags=re.DOTALL | re.IGNORECASE)
        if tableclassm: 
            table_fix=self.judgesign(table_fix,tableclassm.group(1))
        table_fix=re.sub(r'(<table[^<]+?>)',r'\1<tbody>',table_fix,flags=re.DOTALL | re.IGNORECASE)
        table_fix=re.sub(r'(?:<br>\s*)*</table>',r'</tbody></table>',table_fix,flags=re.DOTALL | re.IGNORECASE)  
        table_fix=re.sub(r'style="margin:1\.5em auto;',r'''style="''',table_fix,flags=re.DOTALL | re.IGNORECASE)
        table_fix=re.sub(r"style='margin:1\.5em auto;",r"style='",table_fix,flags=re.DOTALL | re.IGNORECASE)
        #table_fix=re.sub(r'</td></tr>',r'''</td></tr>''',table_fix,flags=re.DOTALL | re.IGNORECASE)
        self.tables.append(table_fix)
            #print(table_fix)
        replacetable=f"<TABLE ID=\"TRP{self.table_count:03d}\"></TABLE>"
        self.table_count+=1
        return replacetable
    def footnote_handle(self,match):
        text=match.group(1)
        text=re.sub(r"<br>[\s\r\n]+<a ",r"</div>\n<div><a ",text, flags=re.DOTALL | re.IGNORECASE)
        text=re.sub(r"</a>[\s]*[\r\n]+?[\s]*",r"</a> ",text, flags=re.DOTALL | re.IGNORECASE)
        text=re.sub(r"[\s]*[\r\n]+?</div>",r"</div>",text, flags=re.DOTALL | re.IGNORECASE)
        text=re.sub(r"<br>[\r\n]*$",r"</div>",text, flags=re.DOTALL | re.IGNORECASE)
        return r'<aside class="footnote">'+text+r'</aside>'
    def text_re(self,match):
        tablenum=self.table_count
        match_text=match.group(2)
        table_pattern = r'(?:<p>\s*[\r\n]+|<div title="table">\s*)*(<table[^<]+?>[\s\r\n\S]+?</table>)(?:\s*<br>|[\s\r\n]*<[/]*p>)*'
        fixed_content=match_text
        #fixed_content=fixed_content.replace("<p>","<br>")
        fixed_content=re.sub(table_pattern,self.save_table,fixed_content, flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r"""<div class="rt">\s*<center>""",r'<div class="rt">',fixed_content, flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r"</center>\s*</div>",r'</div>',fixed_content, flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r"<center>",r'<div class="ct">',fixed_content, flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r"</center>",r'</div>',fixed_content, flags=re.DOTALL | re.IGNORECASE)
        replacebr=True
        if self.volume_number in range(6,9) and self.bookname=="MEA":
            replacebr=False
        if replacebr==True:
            fixed_content=re.sub(r'((?:[\t]+?[ ]*|[　 ]{2,}?)(?:(?!<br>|<[/]*div|<[/]*p|<[/]*table|<[/]*blockquote|<[/]*h)[\S\s\r\n])+?)<br>',r'<p>\1</p>',fixed_content, flags=re.DOTALL | re.IGNORECASE)
        else:
            fixed_content=re.sub(r'([　]{2,}?(?:(?!<br>|<[/]*div|<[/]*p)[\S\s\r\n])+?)<br>',r'<p>\1</p>',fixed_content, flags=re.DOTALL | re.IGNORECASE)
            #fixed_content=re.sub(r'([　 ]{2,}[\s\r\n\S]+?)<br>',r'<p>\1</p>',fixed_content, flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'^([^<>]+?)<br>$',r'<p>\1</p>',fixed_content, flags=re.MULTILINE|re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'^(?!<(?:p|div|blockquote)[ >])([^p\r\n]+?(?:(?:<[bu]>)+[^<>]+?(?:</[bu]>)+(?:(?!</(?:div|p|blockquote|table)>)[^\r\n])*?)+?)<br>$',r'<p>\1</p>',fixed_content, flags=re.MULTILINE|re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'^(?!<(?:p|div|blockquote)[ >])([^p\r\n]+?(?:<sup><a[^<]>[\S]+?</a></sup>(?:(?!</(?:div|p|blockquote|table)>)[^\r\n])*?)+?)<br>$',r'<p>\1</p>',fixed_content, flags=re.MULTILINE|re.DOTALL | re.IGNORECASE)
        #fixed_content=re.sub(r'^(?!<(?:p|div)[ >])([^p\r\n]+?(?:(?:<[bu]>)+[^<>]+?(?:</[bu]>)+[^pdv\r\n]*?)+?)<br>$',r'<p>\1</p>',fixed_content, flags=re.MULTILINE|re.DOTALL | re.IGNORECASE)
        #fixed_content=re.sub(r'^(?!<(?:p|div)[ >])([^p\r\n]+?(?:<sup><a[^<]>[\S]+?</a></sup>[^pdv\r\n]*?)+?)<br>$',r'<p>\1</p>',fixed_content, flags=re.MULTILINE|re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'<div class="quote">([\s\r\n\S]*?)</div>',self.quote_re,fixed_content, flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'(?:<p>)*<p ((?:style|class)=[\S]+?)>\s*([\S\r\n\s]+?(?:[\S\r\n\s]+?</p>){1,}?[\S\r\n\s]+?)</p>',self.p_re,fixed_content, flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'(?:<p>)*<div (class=[\S]+?)>\s*((?:(?!<[/]*div|<table[^<]+?>)[\S\r\n\s])+?)</div>',self.p_re,fixed_content, flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'(?:<p>)*<div ((?:align|style)\s*=\s*[\S ]+?)>((?:(?!<[/]*div|<table[^<]+?>)[\S\r\n\s])+?)</div>',self.p_re,fixed_content, flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'</p>[\r\n\s]+?',r'''</p>
''', fixed_content, flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'<br>\s*</p>',r"</p>",fixed_content,flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'<(h[\d])([^<]*?)>((?:(?!<[/]*h[\d]>)[\S\r\n\s])+?)</h[\d]>',self.head_re,fixed_content, flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'(</(?:blockquote|p|div|h[\d])>)[\s\r\n]*((?:(?!<[/hpd]{1,2}[\d]*|<center>)[\S 　\t])+?)<br>',r'\1'+'\n'+r'<p>\2</p>',fixed_content, flags=re.DOTALL | re.IGNORECASE)
            #fixed_content=re.sub(r'<p>(?:[\t]{1,}[　]*|[　\t]{3,})','<p>　　',fixed_content, flags=re.DOTALL | re.IGNORECASE)
        i=tablenum
        while i<len(self.tables):
            table=self.tables[i]
            fixed_content=fixed_content.replace(f"<TABLE ID=\"TRP{i:03d}\"></TABLE>",table)
            i+=1
        fixed_content=match.group(1)+fixed_content+match.group(3)
        fixed_content= fixed_content.replace("<br/>", "<br>")
        return fixed_content
    def regex_content(self):
        content=self.content.replace("<br>&emsp;&emsp;<br>&emsp;&emsp;","<br>&emsp;&emsp;")
        content=re.sub(r"<br>&emsp;&emsp;[\s]*</h1>",r"</h1>",content,flags=re.DOTALL|re.IGNORECASE)
        content=content.replace('</p><p class="quote">','</div><div>')
        content=content.replace('</strong>','</b>')
        content=content.replace('<strong>','<b>')
        content=content.replace(r'','　') 
        content=content.replace(r'','　') 
        content=content.replace(r' ','　')           
        content=re.sub(r'</p>\s*</body>','</p>\n</body>', content, flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'<br\s*/\s*>\s*','<br>　　', content, flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'([“”\u4e00-\u9fa5！。’，）；？》])>',r'\1&gt;', content, flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'<([《“”\u4e00-\u9fa5！。，（‘；？])',r'&lt;\1', content, flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'<[\?!]>',r'&lt;?&gt;', content, flags=re.DOTALL | re.IGNORECASE)
        content = content.replace("［", "[")
        content =content.replace("］", "]")
        content=re.sub(r"<meta http-equiv=[\"']*Content-Language[\"']* content=[\"']*zh-cn[\"']*>",r"",content,flags=re.DOTALL|re.IGNORECASE)
        content=re.sub(r"<meta http-equiv=[\"']*Content-Type[\"']* content=[\"']*text/htmlml; charset=utf-8[\"']*>[\r\n\s]*?",r"",content,flags=re.DOTALL|re.IGNORECASE)
        content=re.sub(r"<meta content=[\"']*text/htmlml; charset=utf-8[\"']* http-equiv=[\"']*Content-Type[\"']*>[\r\n\s]*?",r"",content,flags=re.DOTALL|re.IGNORECASE)
        content=re.sub(r'&emsp;',r'　', content, flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'．',r'.', content, flags=re.DOTALL | re.IGNORECASE)
        fixed_content=content
        fixed_content=re.sub(r'<td style="line-height:150%[ ]*">',r'<td style="line-height:150%;">',fixed_content,flags=re.DOTALL|re.IGNORECASE) 
        fixed_content=re.sub(r'<p class="skip">\s*</p>(\s*<br>)*[\r\n]',r'',fixed_content,flags=re.DOTALL|re.IGNORECASE)
        fixed_content=re.sub(r'<a name=["\']*([\S]+?)["\']*></a>[\s\r\n]*(?:<br>)*?[\s\r\n]*(<h[\d])([ >])',r'\2 id="\1"\3',fixed_content,flags=re.DOTALL|re.IGNORECASE)
        fixed_content=re.sub(r'<a name=["\']*([\S]+?)["\']*></a>[\s\r\n]*(?:<br>)*?[\s\r\n]*(<hr[^<]+?>(?:<br>)*)[\s\r\n]*(<h[\d])([ >])',r'\2'+'\n'+r'\3 id="\1"\4',fixed_content,flags=re.DOTALL|re.IGNORECASE)
        fixed_content=re.sub(r'(<h[\d]) style=["\']*text-align:[\s]*center[;]*["\'\s]*>',r'\1>', fixed_content,flags=re.DOTALL|re.IGNORECASE)
        if (self.bookname=="VIL" and self.volume_number not in range(44,61)) or (self.bookname=="MEW" and self.volume_number not in range(46,50)):
            quote_pattern = r'(<div class="quote">(?:(?!div class="quote")[\s\r\n\S])+?(?:</div>)*</div>)(?:<br>)*'
            fixed_content=re.sub(quote_pattern,self.save_quote,fixed_content, flags=re.DOTALL|re.IGNORECASE)

        #fixed_content=re.sub(r'(<br>[\s\r\n 　]*){2,}<br>',r'<br>　　',fixed_content ,flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'<a name=',r'<a id=',fixed_content ,flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'(<br>[\s\r\n 　]*){2,}',r'<br>　　',fixed_content ,flags=re.DOTALL | re.IGNORECASE)  
        fixed_content=re.sub(r"\[注\]",r"",fixed_content, flags=re.DOTALL | re.IGNORECASE)
        fixed_content=fixed_content.replace(r'<br>　　<a href=',f'<br>\n<a href=')
        fixed_content=fixed_content.replace(r'<br>　　<a id=',f'<br>\n<a id=')
        fixed_content=re.sub(r'<p([^<]*?)style=("[^<]+?)[;]*"([^<]*?>)[\s\r\n]*<span style="([^<]+?)">([\s\r\n\S]+?)</span>',r'<p\1style=\2;\4;"\3\5',fixed_content ,flags=re.DOTALL | re.IGNORECASE) 
        fixed_content=re.sub(r'<p([^<]*?)>[\s\r\n]*<span style="([^<]+?)">([\s\r\n\S]+?)</span>',r'<p\1 style="\2;">\3',fixed_content ,flags=re.DOTALL | re.IGNORECASE) 
        fixed_content=re.sub(r'<td([^<]*?)style=("[^<]+?)[;]*"([^<]*?>)[\s\r\n]*<p style="([^<]+?)">([\s\r\n\S]+?)',r'<td\1style=\2;\4;"\3\5',fixed_content ,flags=re.DOTALL | re.IGNORECASE) 
        fixed_content=re.sub(r'<td([^<]*?)>[\s\r\n]*<p style="([^<]+?)">([\s\r\n\S]+?)',r'<td\1 style="\2;">\3',fixed_content ,flags=re.DOTALL | re.IGNORECASE) 
        #fixed_content=fixed_content.replace(r'<br></div>','<br> </div>') 
        if (self.bookname=="VIL" and self.volume_number in range(54,61)):
            fixed_content=re.sub(r'(</h[\d]>)(?:<br>)*\s*(<sup><a[ \S]+?</a></sup>)(?:<br>)*',r'\2\1'+'\n',fixed_content,flags=re.DOTALL|re.IGNORECASE) 
            fixed_content=re.sub(r'(</h[\d]>)(?:<br>)*\s*(?:<p>)*\s*(<sup><a[ \S]+?</a></sup>)\s*(?:</p>)*\s*(<aside class=)*',r'\2\1'+'\n'+r'\3',fixed_content,flags=re.DOTALL|re.IGNORECASE)   
            fixed_content=re.sub(r'(</h[\d]>)(?:<br>)*\s*(<p>)*\s*(<(?:p|div)[^<]+?>\s*)*(<sup><a[ \S]+?</a></sup>)\s*<br>[\r\n\s]+',r'\4\1'+'\n'+r'\2'+'\n'+r'\3',fixed_content,flags=re.DOTALL|re.IGNORECASE)   
            fixed_content=re.sub(r'(</h[\d]>)(?:<br>)*\s*(<p>)*\s*(?:<(?:p|div)[^<]+?>\s*)*(<sup><a[ \S]+?</a></sup>)\s*(?:</div>|</p>)*',r'\3\1'+'\n'+r'\2',fixed_content,flags=re.DOTALL|re.IGNORECASE)   
        if (self.bookname=="VIL" and self.volume_number not in range(44,61)) or (self.bookname=="MEW" and self.volume_number not in range(46,50)): 
            fixed_content=re.sub(r'(<body>|</h1>)\s*(?:<br>[\r\n]*)*<p(?: title="start")*>([\s\r\n\S]*?)(<aside class="quote">\s*<span style="font-size:1.2em">【|</body>)',self.text_re,fixed_content,flags=re.DOTALL|re.IGNORECASE)           
            for i, quote in enumerate(self.quotes):
                fixed_content=fixed_content.replace(f"<BLOCKQUOTE ID=\"BQ{i:03d}\"></BLOCKQUOTE>",quote) 
        fixed_content=re.sub(r'<aside class="quote">\s*<span style="font-size:1.2em">【作者注】</span><br>','''
\n<aside class=\"quote\">\n<div class=\"style2\">作者原注</div><BR><BR><br>''', fixed_content, flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'<aside class="quote">\s*<span style="font-size:1.2em">【脚注】</span><br>','''
\n<aside class=\"quote\">\n<div class=\"style2\">脚　　注</div><BR><BR><br>''', fixed_content, flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'<aside class="quote">\s*<span style="font-size:1.2em">【注释】</span><br>','''
\n<aside class=\"quote\">\n<div class=\"style2\">注　　释</div><BR><BR><br>''', fixed_content, flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'・',r'·',fixed_content,flags=re.DOTALL|re.IGNORECASE)
        fixed_content=re.sub(r'<aside class="quote">([\s\r\n\S]+?)</aside>',self.footnote_handle, fixed_content, flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'(?:<br>\s*)+(</(?:p|div|h[\d])>)\s*',r'\1'+'\n',fixed_content,flags=re.DOTALL|re.IGNORECASE)
        fixed_content=re.sub(r'(</(?:p|div|h[\d])>)\s*(?:<br>\s*)+',r'\1'+'\n',fixed_content,flags=re.DOTALL|re.IGNORECASE)
        #fixed_content=re.sub(r'(<h1>)[\s\r\n]+',r'\1',fixed_content,flags=re.DOTALL|re.IGNORECASE)
        #fixed_content=re.sub(r'[\s\r\n]+(</h1>)',r'\1',fixed_content,flags=re.DOTALL|re.IGNORECASE)
        fixed_content=re.sub(r'(?:<p>\s*)*(<t[rd]>)',r'\1',fixed_content,flags=re.DOTALL | re.IGNORECASE)
        #fixed_content=fixed_content.replace('</aside>','</p>')
        if (self.bookname=="VIL" and self.volume_number not in range(44,61)) or (self.bookname=="MEW" and self.volume_number not in range(46,50)):
            fixed_content= fixed_content.replace("<sup>", "￥￥￥<sup>")
            fixed_content= fixed_content.replace("</sup>", "</sup>￥￥￥") 
            fixed_content=re.sub(r'(</h[\d]>)[\s\r\n]*<br>',r'\1',fixed_content,flags=re.DOTALL|re.IGNORECASE) 
            fixed_content=re.sub(r'(</h[\d]>|<blockquote>|</table>)<p>',r'\1'+f'\n<p>',fixed_content,flags=re.DOTALL|re.IGNORECASE)  
            fixed_content=re.sub(r'</table>(<h[\d])',f'</table>\n'+r'\1',fixed_content,flags=re.DOTALL|re.IGNORECASE)  
            fixed_content=re.sub(r'</p>[ 　\t]*(<h[\d]|</blockquote>|<p)','</p>\n'+r'\1',fixed_content,flags=re.DOTALL|re.IGNORECASE)  
            return fixed_content
        if self.bookname=="VIL":
            recontent=re.sub(r'(<body>|</h1>\s*<p>)([\s\r\n\S]*?)(<aside class="footnote">\s*<div class="style2">|</body>)',self.text44_re,fixed_content,flags=re.DOTALL|re.IGNORECASE)
        if self.bookname=="MEW":
            recontent=re.sub(r'(<body>|</h1>\s*<p>)([\s\r\n\S]*?)(<aside class="footnote">\s*<div class="style2">|</body>)',self.text46_re,fixed_content,flags=re.DOTALL|re.IGNORECASE)
        recontent=re.sub(r'(<a[ \S]+?>[\S]+?</a>)\s+([\S\s]+?)\s*<br>',r'\1 \2<br>'+f'\n',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(<title>[\s\S]+?)<br>&emsp;&emsp;[\s 　]*</title>',r'\1</title>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(<title>[\s\S]+?)<br>[\s 　]*</title>',r'\1</title>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(<title>[\s\S]+?)(&emsp;)?[\s 　]+</title>',r'\1</title>',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(<title>[\s\S]+?)\[[\d]+\]([\s\S]*?</title>)',r'\1\2',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(<title>[\s\S]+?)\[注：[\s\S]+?\]([\s\S]*?</title>)',r'\1\2',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'<p>[\s\r\n]+　　',r'<p>　　',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'[\s\r\n]+(<sup><a)',r'\1',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'(</a></sup>)[\s\r\n]+',r'\1',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent=re.sub(r'[ 　]+</h1>[\s\r\n]*<p>\s*(<aside class="footnote)',f'</h1>\n\\1',recontent,flags=re.DOTALL|re.IGNORECASE)
        recontent=re.sub(r'</title>\s*</head>',r'''</title>
<style type = "text/css">
<!--
.quote {font-size:0.75em;margin:1.5em 1px;}
-->
</style>
</head>''',recontent ,flags=re.DOTALL | re.IGNORECASE)
        recontent= recontent.replace("<sup>", "￥￥￥<sup>")
        recontent= recontent.replace("</sup>", "</sup>￥￥￥") 
        return recontent 
    def regex_meacontent(self):
        content=re.sub(r'&emsp;',r'　', self.content, flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'<br>\s*<a id=',f'<br>\n<a id=',content ,flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'<br>\s*<a href=',f'<br>\n<a href=',content ,flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'<div align="right"><table border="0" cellspacing="0" cellpadding="0"><tr><td style="line-height: 200%">',r'<table class="rt"><tr><td>',content ,flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'<div align="right"><table border="0" cellspacing="0" cellpadding="0" width="450"><tr><td style="line-height: 200%">',r'<table class="rt"><tr><td>',content ,flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'<div align="right"><table border="0" cellspacing="0" cellpadding="0" (width="[\S]+?")><tr><td style="line-height: 200%">',r'<table class="rt" \1><tr><td>',content ,flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'<div align="center"><table border="0" cellspacing="0" cellpadding="0"><tr><td style="line-height: 200%">',r'<table class="tnb"><tr><td>',content ,flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'<div align="center"><table border="0" cellspacing="0" cellpadding="0" (width="[\S]+?")><tr><td style="line-height: 200%">',r'<table class="tnb" \1><tr><td>',content ,flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'<p align="right">([\S\s\r\n]+?)</p>',r'<div class="rt">\1</div>',content ,flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'<p align="center">',r'<p class="ct">',content ,flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'<p style="text-align:center;">',r'<p class="ct">',content ,flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'<p style="text-align:right;">([\S\s\r\n]+?)</p>',r'<div class="rt">\1</div>',content ,flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'<div align="right">',r'<div class="rt">',content ,flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'<div align="center">',r'<div class="ct">',content ,flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'<div style="text-align:center;">',r'<div class="ct">',content ,flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'<div style="text-align:right;">',r'<div class="rt">',content ,flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'<!--[\S\r\n\s]+?-->',r'',content ,flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'([“”\u4e00-\u9fa5！。’，）；？》])>',r'\1&gt;', content, flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'<([《“”\u4e00-\u9fa5！。，（‘；？])',r'&lt;\1', content, flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'<a (?:name|id)=["\']*([\S]+?)["\']*></a>[\s\r\n]*(?:<br>)*?[\s\r\n]*(<h[\d])([ >])',r'\2 id="\1"\3',content,flags=re.DOTALL|re.IGNORECASE)
        content=re.sub(r'<a (?:name|id)=["\']*([\S]+?)["\']*></a>[\s\r\n]*(?:<br>)*?[\s\r\n]*(<hr[^<]+?>(?:<br>)*)[\s\r\n]*(<h[\d])([ >])',r'\2'+'\n'+r'\3 id="\1"\4',content,flags=re.DOTALL|re.IGNORECASE)
        if self.volume_number not in range(6,9):
            quote_pattern = r'(<div class="quote">(?:(?!div class="quote")[\s\r\n\S])+?(?:</div>)*</div>)(?:<br>)*'
            content=re.sub(quote_pattern,self.save_quote,content,flags=re.DOTALL|re.IGNORECASE)
        content=re.sub(r'(<body>|</h1>)\s*(?:<p>)*([\s\r\n\S]+?)(<hr[\S ]*?><p class="quote">\s*<span style="font-size:1.2em[;]*">【|<aside class="quote">\s*<span style="font-size:1.2em[;]*">【|</body>)',self.text_re,content,flags=re.DOTALL|re.IGNORECASE)
        #content=re.sub(r'\t',r"　　",content ,flags=re.DOTALL | re.IGNORECASE)    
        #content=re.sub(r'(<br>[\s\r\n ]*){2,}<br>',r'<br>　　',content ,flags=re.DOTALL | re.IGNORECASE)
        #content=re.sub(r'(<br>[\s\r\n ]*){2,}',r'<br>　　',content ,flags=re.DOTALL | re.IGNORECASE)
        if self.volume_number in (26,30):
            content=re.sub(r'(<body>\s*<h[123]>[\S ]+?</h[123]>)\s*([\s\r\n\S]+?)(<hr[\S ]*?><p class="quote">\s*<span style="font-size:1.2em[;]*">【|<aside class="quote">\s*<span style="font-size:1.2em[;]*">【|</body>)'
                               ,self.text_re,content,flags=re.DOTALL|re.IGNORECASE)  
        content=re.sub(r'[　 ]+<h','\n<h',content,flags=re.DOTALL|re.IGNORECASE)
        content=re.sub(r'(<h[\d]) style=["\']*text-align:center[;]*["\']*>',r'\1>',content,flags=re.DOTALL|re.IGNORECASE)   
        content=re.sub(r"<br>[\s]*</h1>",r"</h1>",content,flags=re.DOTALL|re.IGNORECASE)
        content=re.sub(r'<a name=["\']*([\S]+?)["\']*></a>[\s\r\n]*(?:<br>)*?[\s\r\n]*(<h[\d])',r'\2 id="\1"', content,flags=re.DOTALL|re.IGNORECASE)
        #content=re.sub(r'<p class="quote">　　',r'<p class="quote">',content,flags=re.DOTALL|re.IGNORECASE)
        content=re.sub(r'(?:<hr[^<]*?>)*<(?:aside|p) class="quote">\s*<span style="font-size:1.2em[;]*">【作者注】</span><br>','''
\n<aside class=\"quote\">\n<div class=\"style2\">作者原注</div><BR>''', content, flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'(?:<hr[^<]*?>)*<(?:aside|p) class="quote">\s*<span style="font-size:1.2em[;]*">【脚注】</span><br>','''
\n<aside class=\"quote\">\n<div class=\"style2\">脚　　注</div><BR>''', content, flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'(?:<hr[^<]*?>)*<(?:aside|p) class="quote">\s*<span style="font-size:1.2em[;]*">【注释】</span><br>','''
\n<aside class=\"quote\">\n<div class=\"style2\">注　　释</div><BR>''', content, flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'</p>[\s]*[\r\n]+[\s]*<aside ',r'</aside>\n<aside ', content, flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'<aside class="quote">([\s\r\n\S]+?)</(?:aside|p)>(?!<p class="footnote">)',self.footnote_handle, content, flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'</p><p class="footnote">',r'</div><div>', content, flags=re.DOTALL | re.IGNORECASE)
        content=re.sub(r'[\r\n]+</aside>',r'</div></aside>', content, flags=re.DOTALL | re.IGNORECASE)
        fixed_content=re.sub(r'(?:<br>\s*)+(</(?:p|div|h[\d])>[\r\n]*)',r'\1'+'\n',content,flags=re.DOTALL|re.IGNORECASE)
        fixed_content=re.sub(r'(</(?:p|div|h[\d])>\s*)(?:<br>[\r\n]*)+',r'\1'+'\n',fixed_content,flags=re.DOTALL|re.IGNORECASE)
        #content=fixed_content.replace('</aside>','</p>')
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
        recontent = recontent.replace("<sup>", "￥￥￥<sup>")
        recontent = recontent.replace("</sup>", "</sup>￥￥￥")
        recontent=re.sub(r'(<h1>)[\s\r\n]+',r'\1',recontent,flags=re.DOTALL|re.IGNORECASE)
        recontent=re.sub(r'[\s\r\n]+(</h1>)',r'\1',recontent,flags=re.DOTALL|re.IGNORECASE)
        if self.volume_number==5:
            recontent=re.sub(r'<a href="#[\s\S]+?-([ab]*z[\S]+)" id="[\s\S]+?-([ab]*z[\S]+)">',f'<a href="#\\1" id="\\2">',
                                         recontent,flags=re.DOTALL | re.IGNORECASE)
        if self.volume_number not in range(6,9):
            for i, quote in enumerate(self.quotes):
                recontent=recontent.replace(f"<BLOCKQUOTE ID=\"BQ{i:03d}\"></BLOCKQUOTE>",quote) 
        return recontent
def publiccss():
    return """body {font-family:"华文中宋","宋体","Times New Roman",serif;line-height: 1.6;margin: 0;padding: 1em;font-size: 1em;text-align:justify;}
p {margin:0;text-align:justify;}
h1,h2,h3,h4,h5,h6 {margin-top: 1.5em;margin-bottom: 0.5em;font-weight: bold;text-align:center;}
table {max-width: 97vw !important;margin: 1.5em auto 1.5em auto;}
.quote,.footnote,blockquote,.src {font-size: 0.75em;margin: 1.5em 0;line-height:150%;}
.footnote,.sign {margin-top:2em;}
table.quote,table.footnote,blockquote table,.add td,.src td,.date {font-size: 0.75em;margin: 1.5em auto;line-height:150%;}
blockquote p {line-height:150%;}
b {font-family:华文中宋,黑体,宋体,Times New Roman,sans serif;}
.style2 {font-weight: bold;font-size: 1.25em;}
.TCC {width:20%;font-size: 0.75em;text-align:justify;margin:1em auto;}
.TOC {width:85%;text-align:justify;margin:1em auto;}
img {max-width: 100%;height: auto;display: block;margin: 1em auto;}
hr {margin: 1em auto 1em auto;text-align:center;}
.cover-image {max-width: 100%;height: auto;margin: 20px 0;box-shadow: 0 4px 8px rgba(0,0,0,0.3);}
.ct {margin:auto auto;}
p.date,div.date,p.ct,div.ct {margin: 1.5em auto;text-align:center;}
.rt {margin-right:0;margin-left:auto;}
p.add,p.src,table.src {max-width:60%;width:60%;margin:1.5em 0 1.5em auto;}
p.rt,div.rt,.sign,p.add {text-align:right;}
span.ct,span.rt {display: block;}
table.tnb,.rt table,table.rt {border-collapse: collapse; border: none;line-height:200%;}
table.rt,table.sign {margin:1.5em 0 1.5em auto;font-size:1em;}
table.src.rt table.add.rt,table.quote.rt {margin:1.5em 0 1.5em auto;}
.tnb td {padding:0;}
.rt td,.sign td,.rt table td {text-align:left;padding:0;}"""
#if __name__ == "__main__":
    #LENINmelzhcn.main()
    #MEWmelzhcn.main()