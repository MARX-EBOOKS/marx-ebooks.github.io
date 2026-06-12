按下述要求，识别图片后，严格按照图片编写并检查 HTML 代码：
1. 页眉去除页码后转为 title（如去除页码无内容则用本页最高一级标题作为 title），标题用h1-h6（不用加任何居中类，不要把页眉识别为h1-h6），多行标题，如序号、作者名等务必用 <br> 换行，输出到一个标签中，（首行有缩进的）普通段落用<p>输出，文段的靠右居中用align=，斜体用 <i>，粗体用 <b>，引用用 <blockquote>，表格和分栏务必用 <table>；
2. 脚注统一放 <aside> 容器内，准确识别并区分条目编号为纯数字的编者注和条目编号为星号 * 的作者注，将各条目前编号和对应正文上标转换为可互访的链接，给链接编制序号id：脚注区中，编者注id为Fxx，作者注id为Mxx（Marx）/Exx（Engels），原图中正文的对应上标转换为 <sup> 包裹的链接，id前缀为ZF/ZM/ZE，方括号上标不作为文本显示，转为锚点 <a id="A方括号内数字"></a>；注意保证文件内各链接id的唯一性，本组页面不同页脚注编号相同时，应给各id编制不同序号；图片中，同一页正文中上标编号有重复时，除该编号第一个上标外，应给其他该编号上标的链接id加独立序号后缀，格式为Fxx-x/Mxx-x/Exx-x；注意脚注（编者注与作者注）各条目需用<p>换行；
3. 务必合并跨页的段落、单词、脚注条目，保证在一个段落标签内；
4. 其余文本格式、排版用相应标签的 style 属性还原，如 margin、text-indent、width 等。只需要最纯的HTML，不要加任何<style>或外联css；
5. **结果务必按照下列模版输出**：
```html
<html>
<head>
<title>xxxxx</title>
</head>
<body>
<h1>xxxxxx<br>xxxxxxx</h1>
<p align="center">xxxxx</p>
<p align="right">xxxxx</p>
<p>xxxx......<sup><a id="ZFxx" href="#Fxx">xx</a></sup>xxxx........
</p>
<h2>xxxxxx<br>xxxx</h2>
......
<p>xxxxxx.....<a id="Axx"></a>xxxxx......</p>
.....
<aside>
<p><a id="Mxx" href="#ZMxx">(xx)</a> xxxx.....</p>
<p><a id="Exx" href="#ZExx">(xx)</a> xxxx.....</p>
<p><a id="Lxx" href="#ZLxx">(xx)</a> xxxx.....</p>
.....
</aside>
<aside>
<p><a id="Fxx" href="#ZFxx">xx</a> xxxx.....</p>
<p><a id="Fxx" href="#ZFxx">xx</a> xxxx.....</p>
<p><a id="Fxx" href="#ZFxx">xx</a> xxxx.....</p>
.....
</aside>
</body>
</html>
```
**输出前务必据图校对**。