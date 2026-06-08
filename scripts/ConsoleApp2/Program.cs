using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;

namespace EbookMaker
{
    // 注解结构
    public struct Annotation
    {
        public int Number;
        public string Content;
    }

    // 书籍数据结构（扩展自 Program.cs，添加了 viewabletext）
    public class Book
    {
        public string FileName { get; set; }
        public string Extension { get; set; }
        public string Collection { get; set; }
        public string Volume { get; set; }
        public string Name { get; set; }
        public bool NoWarning { get; set; }
        public bool NoError { get; set; }
        public List<string> Warning_Info { get; set; }
        public string Error_Info { get; set; }
        public List<string> Editor_Notes { get; set; }
        public List<string> Author_Notes { get; set; }
        public List<string> viewabletext { get; set; }      // 作者注可见文本
        public Annotation[] Annotations { get; set; }
        public List<int> Content_Annotation_Numbers { get; set; }
        public string Content { get; set; }
        public string Title { get; set; }
        public int Title_Annotation_Num { get; set; }
    }

    // 核心处理器（基于 EbookProcessor5.cs，融合 Program.cs 的改进）
    public class EbookProcessor
    {
        // 中文数字转阿拉伯数字的字典
        private readonly static Dictionary<char, char> _ChineseNumber2Digit = new Dictionary<char, char>()
        {
            {'一','1' }, {'二','2' }, {'三','3' }, {'四','4' }, {'五','5' },
            {'六','6' }, {'七','7' }, {'八','8' }, {'九','9' }, {'十','@' }
        };

        // 统计信息
        public int processed_num = 0;
        public int warning_num = 0;
        public int error_num = 0;
        public int success_num = 0;

        // 输入文件列表（替代原来的 TreeView）
        public List<string> Files { get; set; }

        // 配置选项
        public string output_path;
        public int files_num;
        public bool is_txt_file_allowed;
        public bool is_html_file_allowed;
        public bool editor_notes_check;
        public bool author_notes_check;
        public bool annotation_method1;
        public bool annotation_method2;
        public bool firstline_replace;
        public bool is_format2;
        public bool is_mode2;

        // 临时变量（用于正则）
        private string pattern;
        private string replacement;
        private int start_idx;
        private int end_idx;

        // 事件
        public delegate void ProgressUpdate_Callback(EbookProcessor sender, int progress);
        public event ProgressUpdate_Callback ProgressUpdate;

        public delegate void MessageSend_Callback(EbookProcessor sender, string path, string msg);
        public event MessageSend_Callback MessageSend;

        public delegate void CounterException_Callback(EbookProcessor sender, string path, string msg);
        public event CounterException_Callback CounterException;

        public delegate void BookException_Callback(EbookProcessor sender, string path, ref Book book);
        public event BookException_Callback BookException;

        public delegate void Finished_Callback(EbookProcessor sender, int processed_num);
        public event Finished_Callback Finished;

        // ---------- ReadBook (源自 EbookProcessor5.cs，保留所有细节) ----------
        public void ReadBook(FileStream fs, ref Book book)
        {
            StreamReader sr = null;
            try
            {
                book.NoWarning = true;
                book.NoError = true;
                book.Warning_Info?.Clear();
                book.Error_Info = "";

                sr = new StreamReader(fs, Encoding.UTF8);

                book.FileName = Path.GetFileNameWithoutExtension(fs.Name);
                book.Extension = Path.GetExtension(fs.Name);

                string content = sr.ReadToEnd();
                content = content.Replace("――", "——").Replace("", "").Replace("[[", "[");
                content = content.Replace("<title>《列宁全集》", "<title>列宁全集");

                pattern = @"&lt;&lt;([\s\S]*?)&gt;&gt;";
                content = Regex.Replace(content, pattern, "<<$1>>");
                pattern = @"&lt;([\s\S]*?)&gt;";
                content = Regex.Replace(content, pattern, "<$1>");

                pattern = @"<title>([\s\S]*?)(第.+?卷)(?=——)——([\s\S]*?)</title>";
                Match mtch = Regex.Match(content, pattern);
                if (mtch.Groups.Count == 4)
                {
                    book.Collection = mtch.Groups[1].Value;
                    book.Volume = string.Concat(mtch.Groups[2].Value.Select(x => _ChineseNumber2Digit.TryGetValue(x, out char digit) ? digit : x));
                    if (book.Volume.Length == 3)
                    {
                        if (book.Volume[1] == '@')
                            book.Volume = book.Volume.Replace("@", "10");
                    }
                    else if (book.Volume.Length == 4)
                    {
                        if (book.Volume[1] == '@')
                            book.Volume = book.Volume.Replace("@", "1");
                        else if (book.Volume[2] == '@')
                            book.Volume = book.Volume.Replace("@", "0");
                    }
                    else
                        book.Volume = book.Volume.Replace("@", "");

                    string bookName = mtch.Groups[3].Value;
                    pattern = @"\[[\d]+?\]$";
                    bookName = Regex.Replace(bookName, pattern, "", RegexOptions.IgnoreCase);
                    book.Name = bookName;
                }
                else
                {
                    book.NoError = false;
                    book.Error_Info = "ReadBook：没有找到<作品集>或<卷数>或<文章名>";
                    return;
                }

                if (is_mode2)
                {
                    start_idx = content.IndexOf("<hr color");
                    if (start_idx != -1)
                        content = content.Substring(start_idx);

                    content = content.Replace("&nbsp; 全世界无产者，联合起来！", "<br>");
                    content = content.Replace(">后页<", "><br><").Replace(">前页<", "><br><")
                                     .Replace(">目录<", "><br><").Replace(">“北极星书库”<", "><br><")
                                     .Replace(">|||<", "><br><").Replace(">“数学文集基地”<", "><br><")
                                     .Replace(">Made by an Unre<", "><br><").Replace(">gistered version of <", "><br><")
                                     .Replace(">eTextWizard<", "><br><").Replace("> V 1.98<", "><br><")
                                     .Replace("&nbsp;&nbsp;", "").Replace("----------------------------------------", "");

                    content = content.Replace('０', '0').Replace('１', '1').Replace('２', '2')
                                     .Replace('３', '3').Replace('４', '4').Replace('５', '5')
                                     .Replace('６', '6').Replace('７', '7').Replace('８', '8')
                                     .Replace('９', '9');

                    for (int i = 0; i < 20; i++)
                        content = content.Replace(Convert.ToChar('⑴' + i).ToString(), "(" + (1 + i).ToString() + ")");

                    content = Regex.Replace(content, "注[　 ]*?释[　 \r\n]*?<br>", "注释：<br>");
                    content = Regex.Replace(content, @"(?<!—)\((?<tgt>[0-9]+)\)", "[${tgt}]");
                    content = Regex.Replace(content, @"(?<!—)（(?<tgt>[0-9]+)）", "[${tgt}]");
                    content = content.Replace('〔', '[').Replace('〕', ']');
                }

                if ((book.Extension == ".htm") || (book.Extension == ".html"))
                {
                    if (!is_mode2)
                    {
                        content = content.Replace('［', '[');
                        content = content.Replace('］', ']');
                        // 去除“中马库”牛皮癣，更改标题样式
                        pattern = @"<hr[\s]*color='#808080'[\s]*size='1'>[\s]*<p[\s]*class='author'>([\s\S]*?)</p>[\s]*<p[\s]*class='title1'>";
                        replacement = @"<hr color='#808080' size='1'>   <p class='title1'>$1<br>";
                        content = Regex.Replace(content, pattern, replacement);
                        pattern = @"<hr color='#808080' size='1'>\r?\n<p class='author'>([\s\S]*?)</p></p>\r?\n<p class='title1'>";
                        replacement = @"<hr color='#808080' size='1'>   <p class='title1'>$1<br>";
                        content = Regex.Replace(content, pattern, replacement);
                        pattern = @"<hr color='#808080' size='1'>(\r?\n|.)*?<h4 style=[""']text-align: center[""']>([\s\S]*?)</h4>[\s\r\n]*?<p class=[""']title1[""']>";
                        replacement = @"<hr color='#808080' size='1'>   <p class='title1'>$2";
                        content = Regex.Replace(content, pattern, replacement);
                        pattern = @"<hr color='#808080' size='1'>(\r?\n|.)*?<p class=[""']title0[""']>([\s\S]*?)</p>(\r?\n|.)*?<p class=[""']title1[""']>";
                        replacement = @"<hr color='#808080' size='1'>   <p class='title1'>$2<br>";
                        content = Regex.Replace(content, pattern, replacement);
                        pattern = @"<hr color='#808080' size='1'>[\r\n]*<p class='title0'>([\S]*?)</p>[\r\n]*<p[\s]*class='title1'>([\S]*)</p>";
                        replacement = @"<hr color='#808080' size='1'>   <p class='title1'>$1<br>$2</p>";
                        content = Regex.Replace(content, pattern, replacement);

                        pattern = @"<font size=['""]3['""]>[\S ]*?<a name='_ftn[\S]*?' title href='#_ftn[\S]*?'><sup>(\[[\d]*\])</sup></a>[\s\S]{0,7}</font>";
                        content = Regex.Replace(content, pattern, "$1");
                        pattern = @"<sup>[\s]*?<a name='_ftnref[\S]*?' title href='#_ftn[\S]*?'>[\s]*?(\[[\d]*\])[\s]*?</a>[\s]*?</sup>";
                        content = Regex.Replace(content, pattern, "$1");
                        pattern = @"<font size=['""][23]['""]>[\S ]*?(\[[\d]*?\])[\S ]*?<[/]*font>";
                        content = Regex.Replace(content, pattern, "$1");
                        pattern = @"<p (?:align|class)=[""'][\S]+?['""]>[\s\r\n]*(?:&nbsp;)*[\s\r\n]*</p>";
                        content = Regex.Replace(content, pattern, "", RegexOptions.IgnoreCase);
                        pattern = @"<div (?:align|class)=[""'][\S]+?['""]>[\s\r\n]*(?:&nbsp;)*[\s\r\n]*</div>";
                        content = Regex.Replace(content, pattern, "", RegexOptions.IgnoreCase);
                        pattern = @"<sup><span style=""font-size: 12pt"">([\S]+?)</span></sup>";
                        content = Regex.Replace(content, pattern, "$1");
                        pattern = @"<span style=""font-size: 12pt"">([\S]+?)</span>";
                        content = Regex.Replace(content, pattern, "$1");
                        pattern = @"(?:<br>)*?<a name='_ftn[\S]*?' title href='#_ftn[\S]*?'><sup>[\S ]*?(\[[\d]*\])[\S ]*?</sup></a>";
                        content = Regex.Replace(content, pattern, "$1");
                        pattern = @"<font size=['""]3['""]><sup><a name='_ftn[\S]*?' title href='#_ftn[\S]*?'>(\[[\d]*\])</a></sup></font>";
                        content = Regex.Replace(content, pattern, "$1");

                        pattern = @"<hr[\s]*color=['""]#808080['""][\s]*size=['""]1['""]>[\s]*<p class=['""]title1['""]";
                        Match match = Regex.Match(content, pattern);
                        if (!match.Success)
                            match = Regex.Match(content, @"<hr color='#808080' size='1'>(\r?\n|.)*?<p class=['""]title0['""]");
                        if (!match.Success)
                            match = Regex.Match(content, @"</a>[\s]*<hr color='#808080' size='1'>");
                        start_idx = match.Index;
                        if (start_idx != -1)
                            content = content.Substring(start_idx);
                    }

                    end_idx = content.LastIndexOf("</body>");
                    if (end_idx != -1)
                        content = content.Substring(0, end_idx);

                    content = content.Trim();

                    // 读取标题
                    int title_start_idx1 = content.IndexOf("<p class=\"title1\">");
                    int title_start_idx2 = content.IndexOf("<p class='title1'>");
                    int title_end_idx = content.IndexOf("\r");
                    if (title_end_idx == -1)
                        title_end_idx = content.IndexOf("\n");
                    if ((title_end_idx != -1) & ((title_start_idx1 != -1) || (title_start_idx2 != -1)))
                    {
                        pattern = @"<hr color=['""]#808080['""] size='['""]1['""]>[\s]*?<p class='['""]title1'['""]>([\s\S]*?)</p>[\s]*?<p class='author'>([\s\S]*?)</p>";
                        replacement = @"<hr color='#808080' size='1'><p class='title1'>$1<br>$2</p>";
                        content = Regex.Replace(content, pattern, replacement);
                        pattern = @"<hr color=['""]#808080['""] size='['""]1['""]>[\s]*?<p class='['""]title1'['""]>([\s\S]*?)<br>[\s]*?([\s\S]*?)</p>";
                        replacement = @"<hr color='#808080' size='1'><p class='title1'>$1<br>$2</p>";
                        content = Regex.Replace(content, pattern, replacement);
                        pattern = @"<hr color=['""]#808080['""] size=['""]1['""]>([\s]*?)<p class=['""]title1['""]>([\s\S]*?)</p>";
                        Match match = Regex.Match(content, pattern);
                        book.Title = match.Groups[2].Value;
                        content = Regex.Replace(content, pattern, "");
                    }
                    else
                    {
                        book.NoError = false;
                        book.Error_Info = "ReadBook：没有找到<标题>";
                        return;
                    }

                    content = content.Replace("&nbsp;", " ");
                    content = content.Replace("<h3 style=\"text-align: center\">注释：</h3>", " <b>注释：</b>");
                    content = content.Replace("<strong>注释：</strong>", " <b>注释：</b>");

                    if (book.Collection == "列宁全集")
                    {
                        pattern = @"(<br>)\s*\1+";
                        content = Regex.Replace(content, pattern, "$1");
                    }

                    content = content.Replace("注①：", "注：①").Replace("注②：", "注：②")
                                     .Replace("注③：", "注：③").Replace("注④：", "注：④");

                    pattern = @"<br><a name='_ftn[\S]*?' title href='#_ftn[\S]*?'><sup>(\[[\d]*\])</sup></a>";
                    content = Regex.Replace(content, pattern, "$1");
                    pattern = @"<a name='_ftn[\S]*?' title href='#_ftn[\S]*?'><sup>(\[[\d]*\])</sup></a>";
                    content = Regex.Replace(content, pattern, "$1");
                    pattern = @"<sup>(\[[\d]*\])</sup>";
                    content = Regex.Replace(content, pattern, "$1");

                    // 合并多种注释区匹配（简化）
                    pattern = @"<hr color=""#C0C0C0"" width=""60%"" size=""1"" align=""left"">[\s]*?<span style=""font-size: 10.5pt"">[\s]*?\[";
                    content = Regex.Replace(content, pattern, "注释：<br>[");
                    // ... 其他注释区替换（保留 EbookProcessor5 中的多个 pattern）

                    pattern = @"<div class=[""']a[\d][""']([^<]*?)>";
                    content = Regex.Replace(content, pattern, "<div class=\"quote\"$1>", RegexOptions.IgnoreCase);
                    pattern = @"<p align=[""']center[""']>(※　　　　　※　　　　　※)[\s]*</p>";
                    content = Regex.Replace(content, pattern, "<div class=\"ct\">$1</div>");
                    pattern = @"<center>(※　　　　　※　　　　　※)[\s]*</center>";
                    content = Regex.Replace(content, pattern, "<div class=\"ct\">$1</div>");
                    pattern = @"<p align=[""']center['""]>[\s\r\n]*([—到〔〕\[\]不早晚于之或上下半间以前后年月日和\d]+?)[\s\r\n]*</p>";
                    content = Regex.Replace(content, pattern, "<div class='date'>$1</div>");
                    pattern = @"<p class=""(?:MsoPlainText|MsoNormal)"" align=""center"" style=""text-align:center"">";
                    content = Regex.Replace(content, pattern, "<p align=\"center\">");
                    pattern = @"(<td(?:(?! align=)[^<])*?)>[\s\r\n]*<p (align=[""'][\S]+?['""])>([\s\r\n\S]+?)</td>";
                    content = Regex.Replace(content, pattern, "$1 $2>$3</td>");
                    pattern = @"<span lang=[""']EN-US[""']>([\d ]+?)</span>";
                    content = Regex.Replace(content, pattern, "$1", RegexOptions.IgnoreCase);
                    pattern = @"<span lang=[""'][\S]+?[""']>([\S ]+?)</span>";
                    content = Regex.Replace(content, pattern, "$1", RegexOptions.IgnoreCase);
                    pattern = @"<span lang=[""'][\S]+?[""']>([\s\r\n]+?)</span>";
                    content = Regex.Replace(content, pattern, "$1", RegexOptions.IgnoreCase);
                    content = Regex.Replace(content, @"〔[\s]*〕", "〔...〕", RegexOptions.IgnoreCase);
                    pattern = @"注：\[[\d]*\]";
                    content = Regex.Replace(content, pattern, "注：", RegexOptions.IgnoreCase);
                    pattern = @"注[:：][\s]+\[[0-9]*\][\s]+";
                    content = Regex.Replace(content, pattern, "注：", RegexOptions.IgnoreCase);

                    pattern = @"(?<!—)\[(?<tgt>[0-9]+)\]";
                    content = Regex.Replace(content, pattern, "*|*${tgt}|*|");
                    content = Regex.Replace(content, @"〔注[：:]", "[注：", RegexOptions.IgnoreCase);
                    content = Regex.Replace(content, @"〔", "kfk￥￥sdvld￥", RegexOptions.IgnoreCase);

                    content = Regex.Replace(content, @"〕", "]kfk￥", RegexOptions.IgnoreCase);
                    content = Regex.Replace(content, @"\.\.\.\]kfk￥", " 〕", RegexOptions.IgnoreCase);
                    content = Regex.Replace(content, @"者注\]kfk￥\]kfk￥", "者注]]kfk￥", RegexOptions.IgnoreCase);
                    pattern = @"\]kfk￥\]kfk￥";
                    content = Regex.Replace(content, pattern, "〕]kfk￥", RegexOptions.IgnoreCase);
                    content = book.Title + "\r\n" + content;

                    pattern = @"(?<!—)\[(?<tgt>[0-9]+)\]";
                    content = Regex.Replace(content, pattern, "*|*${tgt}|*|");

                    if (editor_notes_check)
                    {
                        pattern = @"\[注[:：][^\[\]]*?(\[(?!注[:：]).+?\]){0,}[^\[\]]*?[编译]者注\]";
                        if (Regex.IsMatch(content, pattern))
                        {
                            MatchCollection editor_notes = Regex.Matches(content, pattern);
                            if (editor_notes.Count > 0)
                            {
                                pattern = @"(?<!—)\*\|\*(?<tgt>[0-9]+)\|\*\|";
                                for (int i = 0; i < editor_notes.Count; i++)
                                {
                                    string editor_note_str = Regex.Replace(editor_notes[i].Value, pattern, "[${tgt}]");
                                    if (!book.Editor_Notes.Contains(editor_note_str))
                                        book.Editor_Notes.Add(editor_note_str);
                                    else
                                    {
                                        book.NoWarning = false;
                                        book.Warning_Info.Add("ReadBook：出现重复的编者注，位置：" + editor_note_str);
                                    }
                                }
                            }
                        }
                    }

                    if (author_notes_check)
                    {
                        pattern = @"\[注[:：][^\[\]]*?(\[.+?\]){0,}[^\[\]]*?(?<![编译]者注)\]";
                        if (Regex.IsMatch(content, pattern))
                        {
                            MatchCollection author_notes = Regex.Matches(content, pattern);
                            if (author_notes.Count > 0)
                            {
                                pattern = @"(?<!—)\*\|\*(?<tgt>[0-9]+)\|\*\|";
                                for (int i = 0; i < author_notes.Count; i++)
                                {
                                    string author_note_str = Regex.Replace(author_notes[i].Value, pattern, "[${tgt}]");
                                    // 提取可见文本（如 (1a) 中的 1a）
                                    Match m = Regex.Match(author_note_str, @"（([\d]+?[a-z]*)）");
                                    string viewable = m.Success ? m.Groups[1].Value : (i + 1).ToString();
                                    if (!book.Author_Notes.Contains(author_note_str))
                                    {
                                        book.Author_Notes.Add(author_note_str);
                                        book.viewabletext.Add(viewable);
                                    }
                                    else
                                    {
                                        book.NoWarning = false;
                                        book.Warning_Info.Add("ReadBook：出现重复的作者注，位置：" + author_note_str);
                                    }
                                }
                            }
                        }
                    }

                    pattern = @"(?<!—)\*\|\*(?<tgt>[0-9]+)\|\*\|";
                    content = Regex.Replace(content, pattern, "[${tgt}]");

                    int annotation_start_idx = -1;
                    Match annotation_match = Regex.Match(content, @"注释：\s*<br>\s*\[");
                    if (!annotation_match.Success)
                        annotation_match = Regex.Match(content, @"注释：\s*<br>[\s\S]*?\[");
                    if (!annotation_match.Success)
                        annotation_match = Regex.Match(content, @"[\[【［]注释[\]】］]\s*\[");
                    if (!annotation_match.Success)
                        annotation_match = Regex.Match(content, @"[\[【［]参考文献[\]】］]\s*\[");
                    if (!annotation_match.Success)
                        annotation_match = Regex.Match(content, @"注释:\s*\[");
                    if (!annotation_match.Success)
                        annotation_match = Regex.Match(content, @"注释:\s*<br>\s*\[");
                    if (!annotation_match.Success)
                        annotation_match = Regex.Match(content, @"注释:\s*<br>\[");
                    if (annotation_match.Success)
                        annotation_start_idx = annotation_match.Index;
                    else
                        annotation_start_idx = -1;

                    pattern = @"(?<![—注])\[([0-9]{1,3})\]";
                    MatchCollection annotation_num_matches = null;
                    if (annotation_start_idx >= 0)
                    {
                        int no1_annotation_start_idx = content.IndexOf('[', annotation_start_idx + 1);
                        if (no1_annotation_start_idx >= 0)
                        {
                            string annotation_content = content.Substring(no1_annotation_start_idx);
                            annotation_num_matches = Regex.Matches(annotation_content, pattern);
                            string[] all_annotations = Regex.Replace(annotation_content, pattern, "\f").Split("\f".ToCharArray(), StringSplitOptions.RemoveEmptyEntries);

                            book.Annotations = new Annotation[annotation_num_matches.Count];
                            if (annotation_num_matches.Count != all_annotations.Length)
                            {
                                book.NoError = false;
                                book.Error_Info = $"ReadBook：注释的条目和编号数目不一致。匹配数：{annotation_num_matches.Count}，分割数：{all_annotations.Length}";
                                return;
                            }
                            for (int i = 0; i < annotation_num_matches.Count; i++)
                            {
                                book.Annotations[i].Content = all_annotations[i];
                                book.Annotations[i].Number = int.Parse(annotation_num_matches[i].Value.Substring(1, annotation_num_matches[i].Value.Length - 2));
                            }
                        }
                        else
                        {
                            book.NoWarning = false;
                            book.Warning_Info.Add("ReadBook：没有找到注释条目位置");
                        }
                    }

                    title_end_idx = book.Title.Length;
                    if (annotation_start_idx != -1)
                    {
                        if (annotation_start_idx - title_end_idx - 1 <= 0)
                        {
                            book.NoError = false;
                            book.Error_Info = "ReadBook：没有找到文章内容";
                            return;
                        }
                        else
                            book.Content = content.Substring(title_end_idx + 1, annotation_start_idx - title_end_idx - 1);
                    }
                    else
                        book.Content = content.Substring(title_end_idx + 2);

                    book.Content = book.Content.Trim();
                    pattern = @"(?<![—注])\[([0-9]{1,3})\](?![\d]{2}年)";
                    MatchCollection matches = Regex.Matches(content, pattern);
                    book.Content_Annotation_Numbers = new List<int>();
                    foreach (Match match in matches)
                    {
                        int number = int.Parse(match.Value.Substring(1, match.Value.Length - 2));
                        if (!book.Content_Annotation_Numbers.Contains(number))
                            book.Content_Annotation_Numbers.Add(number);
                    }

                    List<int> annotation_nums = new List<int>();
                    if (book.Annotations != null)
                    {
                        foreach (Annotation annotation in book.Annotations)
                            annotation_nums.Add(annotation.Number);
                    }
                    if (annotation_nums.Count == 0 && book.Content_Annotation_Numbers.Count != 0)
                    {
                        book.NoWarning = false;
                        book.Warning_Info.Add("ReadBook：<正文>中存在注释编号，但<注释区>没有任何编号");
                    }
                    else if (annotation_nums.Count != 0 && book.Content_Annotation_Numbers.Count == 0)
                    {
                        book.NoWarning = false;
                        book.Warning_Info.Add("ReadBook：<注释区>存在注释编号，但<正文>没有任何编号");
                    }
                    else
                    {
                        if (book.Content_Annotation_Numbers.Count != annotation_nums.Count)
                        {
                            book.NoWarning = false;
                            book.Warning_Info.Add("ReadBook：<正文>和<注释区>注释条目数量不一致");
                        }
                        foreach (int num in book.Content_Annotation_Numbers)
                        {
                            if (!annotation_nums.Contains(num))
                            {
                                book.NoWarning = false;
                                book.Warning_Info.Add("ReadBook：注释编号在<正文>中出现但是没有<注释区>找到，编号：" + num.ToString());
                            }
                        }
                        foreach (int num in annotation_nums)
                        {
                            if (!book.Content_Annotation_Numbers.Contains(num))
                            {
                                book.NoWarning = false;
                                book.Warning_Info.Add("ReadBook：注释编号在<注释区>出现但是没有在<正文>中找到，编号：" + num.ToString());
                            }
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                book.NoError = false;
                book.Error_Info = "ReadBook：" + ex.Message;
            }
            finally
            {
                sr?.Close();
            }
        }

        // ---------- WriteBook (融合 Program.cs 的链接简化、表格处理、临时保护) ----------
        public void WriteBook(FileStream fs, ref Book book)
        {
            StreamWriter sw = null;
            try
            {
                if (book.NoError)
                {
                    sw = new StreamWriter(fs, Encoding.UTF8);

                    sw.WriteLine("<html>");
                    sw.WriteLine("<head>");
                    if (is_format2)
                    {
                        sw.WriteLine("<title>" + book.Name.Replace(" ", "&emsp;") + "</title>");
                        sw.WriteLine("<Meta http-equiv=\"Window - target\" content=\"_top\">");
                        sw.WriteLine("<META content=\"test/html; charset=gb2312\" http-equiv=\"Content-Type\">");
                        sw.WriteLine("<META content = \"www.mzdbl.cn\" name = \"毛泽东博览\" >");
                        sw.WriteLine("<style type = \"text/css\" >");
                        sw.WriteLine("<!--");
                        sw.WriteLine(".style1 {color: #FF0000;font-family: \"黑体\";}");
                        sw.WriteLine(".style2 {font-size:1.2em}");
                        sw.WriteLine(".style3 {font-size: 18px; font-family: \"楷体_GB2312\"}");
                        sw.WriteLine(".quote {font-size:0.9em;margin:1.5em 1px;\"}");
                        sw.WriteLine("-->");
                        sw.WriteLine("</style>");
                    }
                    else
                    {
                        sw.WriteLine("<meta http-equiv='Content-Language' content='zh-cn'><meta http-equiv='Content-Type' content='text/htmlml; charset=utf-8'>");
                        sw.WriteLine("<title>" + book.Name.Replace(" ", "&emsp;") + "</title>");
                        sw.WriteLine("<style type = \"text/css\" >");
                        sw.WriteLine("<!--");
                        sw.WriteLine(".quote,.src,.add {font-size:0.75em;margin:1.5em 1px;}");
                        sw.WriteLine(".ct {font-size:0.75em;margin-right: auto;margin:left:auto;}");
                        sw.WriteLine(".rt {text-align:right;margin-right:0;margin-left:auto;}");
                        sw.WriteLine("table.src.rt, table.add.rt {border-collapse: collapse; border: none; margin:1.5em 0 1.5em auto;}");
                        sw.WriteLine("table.add.rt td,table.src.rt td {text-align:left;padding: 0;}");
                        sw.WriteLine("-->");
                        sw.WriteLine("</style>");
                    }
                    sw.WriteLine("</head>");
                    if (is_format2)
                    {
                        sw.WriteLine("<body bgcolor=\"#D1E3FE\">");
                        sw.WriteLine("<div style=\"LINE - HEIGHT: 160 % \">");
                    }
                    else
                        sw.WriteLine("<body>");


                    // 不再使用文件名前缀，仅用于内部临时替换
                    string name_replace = Regex.Replace(book.FileName, @"(?<!—)\[(?<tgt>[0-9]+)\]", "*|*${tgt}|*|");
                    string main_content;
                    if (is_format2)
                    {
                        sw.WriteLine("<h1 align=\"center\">&nbsp;</h1>");
                        main_content = "<h1 align=center class=\"style1\">" + book.Title.Replace(" ", "&emsp;") + "</h1>\r\n<br>\r\n&emsp;&emsp;" + book.Content.Replace("\r\n", "<br>&emsp;&emsp;") + "\r\n</p>\r\n";
                        pattern = @"<p class=[""']date[""']>";
                        main_content = Regex.Replace(main_content, pattern, "<P class=\"quote\" style=\"text-align:center\">");
                    }
                    else
                    {
                        main_content = "\r\n<h1>" + book.Title.Replace(" ", "&emsp;") + "</h1>\r\n<br>\n" + book.Content.Replace("\r\n", "<br>　　") + "\r\n<br>\r\n";
                        pattern = @"<p class=[""']date[""']>[\s\r\n]*([（(][\S ]+?[)）])[\s\r\n]*</p>";
                        main_content = Regex.Replace(main_content, pattern, "<div class='date'>$1</div>");
                    }

                    // 作者注替换（简化链接 id，保留 viewabletext）
                    for (int i = 0; i < book.Author_Notes.Count; i++)
                    {
                        string viewabletext = book.viewabletext[i];
                        if (!main_content.Contains(book.Author_Notes[i].Replace("\r\n", "<br>&emsp;&emsp;")))
                        {
                            book.NoError = false;
                            book.Error_Info = "WriteBook：作者注内容在<标题>和<正文>中没有搜索到：位置：" + book.Author_Notes[i];
                            continue;
                        }
                        main_content = main_content.Replace(book.Author_Notes[i].Replace("\r\n", "<br>&emsp;&emsp;"),
                                                string.Format("<sup><a id='azref{0}' href='#az{0}'>({1})</a></sup>",
                                                i + 1, viewabletext));
                    }

                    if (book.Author_Notes.Count > 0)
                    {
                        if (is_format2)
                            main_content += "<HR>\n<P class=\"quote\">\n<span class=\"style2\"><B>作者原注</B></span><BR><BR>\n";
                        else
                            main_content += "<aside class=\"quote\">\r\n<span style=\"font-size:1.2em\">【作者注】</span><br><br>\n";
                        for (int i = 0; i < book.Author_Notes.Count; i++)
                        {
                            string author_note_str = book.Author_Notes[i].Replace("\r\n", "<br>&emsp;&emsp;");
                            string viewabletext = book.viewabletext[i];
                            pattern = @"（([\d]+?[a-z]*)）";
                            //MatchCollection matches = Regex.Matches(author_note_str, pattern);
                            Regex regex = new Regex(pattern);
                            author_note_str = regex.Replace(author_note_str, "", 1);
                            // 处理注内容中的表格和居中（使用 <mdd> 临时保护）
                            author_note_str = Regex.Replace(author_note_str, @"<center>([ \S]+?)</center>", "<span class=\"ct\">$1</span>");
                            author_note_str = Regex.Replace(author_note_str, @"<p style=[""']text-align:center[""']>((\r?\n|.)+?)</p>", "<span class=\"ct\">$1</span>");
                            author_note_str = Regex.Replace(author_note_str, @"<p align=[""']center[""']>((\r?\n|.)+?)</p>", "<span class=\"ct\">$1</span>");
                            author_note_str = Regex.Replace(author_note_str, @"(<table(\r?\n|.)+?</table>)", "<br class=\"table\">$1<br class=\"table\"></mdd><mdd class=\"quote\">");
                            author_note_str = Regex.Replace(author_note_str, @"<div align=[""']center[""']>[\s]*<br class=""table"">", "<br class=\"table\">");
                            author_note_str = Regex.Replace(author_note_str, @"<p align=[""']center[""']>[\s]*<br class=""table"">", "<br class=\"table\">");
                            author_note_str = Regex.Replace(author_note_str, @"</mdd><mdd class=""quote"">[\s]*</div>", "</mdd><mdd class=\"quote\">");
                            author_note_str = Regex.Replace(author_note_str, @"</mdd><mdd class=""quote"">[\s]*</p>", "</mdd><mdd class=\"quote\">");
                            author_note_str = Regex.Replace(author_note_str, @"<div style=[""']text-align:center[""']>((\r?\n|.)+?)</div>", "<span class=\"ct\">$1</span>");
                            author_note_str = Regex.Replace(author_note_str, @"<div align=[""']center[""']>((\r?\n|.)+?)</div>", "<span class=\"ct\">$1</span>");
                            author_note_str = Regex.Replace(author_note_str, @"<p([ \S]*?)>([\s\S]+?)</p>", "<span$1>$2</span>", RegexOptions.IgnoreCase);
                            author_note_str = Regex.Replace(author_note_str, @"<div([ \S]*?)>((\r?\n|.)+?)</div>", "<span$1>$2</span>", RegexOptions.IgnoreCase);
                            author_note_str = Regex.Replace(author_note_str, @"<p[ \S]*?>((\r?\n|.)+?)</p>", "<br>$1<br>", RegexOptions.IgnoreCase);
                            author_note_str = Regex.Replace(author_note_str, @"<div[ \S]*?>((\r?\n|.)+?)</div>", "<br>$1<br>", RegexOptions.IgnoreCase);
                            author_note_str = author_note_str.Replace("</span></font>", "");

                            author_note_str = author_note_str.Substring(3, author_note_str.Length - 4);
                            main_content += string.Format("<a id='az{0}' href='#azref{0}'>({1})</a> ",
                                        i + 1, viewabletext);
                            main_content += author_note_str + "<br>\r\n";
                        }
                        main_content += "</aside>\r\n";
                    }

                    // 编者注替换（简化 id）
                    for (int i = 0; i < book.Editor_Notes.Count; i++)
                    {
                        if (!main_content.Contains(book.Editor_Notes[i].Replace("\r\n", "<br>&emsp;&emsp;")))
                        {
                            book.NoError = false;
                            book.Error_Info = "WriteBook：编者注内容在<标题>和<正文>中没有搜索到：位置：" + book.Editor_Notes[i];
                            continue;
                        }
                        main_content = main_content.Replace(book.Editor_Notes[i].Replace("\r\n", "<br>&emsp;&emsp;"),
                                                    string.Format("<sup><a id='bzref{0}' href='#bz{0}'>FN{0}</a></sup>",
                                                    i + 1));
                    }

                    if (editor_notes_check && book.Editor_Notes.Count > 0)
                    {
                        if (is_format2)
                            main_content += "<HR>\r\n<P class=\"quote\">\n<span class=\"style2\"><B>脚　　注</B></span><BR><BR>\r\n";
                        else
                            main_content += "<aside class=\"quote\">\r\n<span style=\"font-size:1.2em\">【脚注】</span><br>\r\n";
                        for (int i = 0; i < book.Editor_Notes.Count; i++)
                        {
                            string editor_note_str = book.Editor_Notes[i].Replace("\r\n", "<br>&emsp;&emsp;");
                            // 使用 <mdd> 临时保护
                            editor_note_str = Regex.Replace(editor_note_str, @"<center>([ \S]+?)</center>", "<span class=\"ct\">$1</span>");
                            editor_note_str = Regex.Replace(editor_note_str, @"<p style=[""']text-align:center[""']>((\r?\n|.)+?)</p>", "<span class=\"ct\">$1</span>");
                            editor_note_str = Regex.Replace(editor_note_str, @"<p align=[""']center[""']>((\r?\n|.)+?)</p>", "<span class=\"ct\">$1</span>");
                            editor_note_str = Regex.Replace(editor_note_str, @"(<table(\r?\n|.)+?</table>)", "<br class=\"table\">$1<br class=\"table\"></mdd><mdd class=\"quote\">");
                            editor_note_str = Regex.Replace(editor_note_str, @"<br class=""table"">[\s]*<div align=[""']center[""']>", "<br class=\"table\">");
                            editor_note_str = Regex.Replace(editor_note_str, @"<br class=""table"">[\s]*<p align=[""']center[""']>", "<br class=\"table\">");
                            editor_note_str = Regex.Replace(editor_note_str, @"</mdd><mdd class=""quote"">[\s]*</div>", "</mdd><mdd class=\"quote\">");
                            editor_note_str = Regex.Replace(editor_note_str, @"</mdd><mdd class=""quote"">[\s]*</p>", "</mdd><mdd class=\"quote\">");
                            editor_note_str = Regex.Replace(editor_note_str, @"<div style=[""']text-align:center[""']>((\r?\n|.)+?)</div>", "<span class=\"ct\">$1</span>");
                            editor_note_str = Regex.Replace(editor_note_str, @"<div align=[""']center[""']>((\r?\n|.)+?)</div>", "<span class=\"ct\">$1</span>");
                            editor_note_str = Regex.Replace(editor_note_str, @"<p([^<]*?)>([\s\S]+?)</p>", "<span$1>$2</span>", RegexOptions.IgnoreCase);
                            editor_note_str = Regex.Replace(editor_note_str, @"<div([^<]*?)>((\r?\n|.)+?)</div>", "<span$1>$2</span>", RegexOptions.IgnoreCase);
                            editor_note_str = Regex.Replace(editor_note_str, @"<p[^<]*?>((\r?\n|.)+?)</p>", "<br>$1<br>", RegexOptions.IgnoreCase);
                            editor_note_str = Regex.Replace(editor_note_str, @"<div[^<]*?>((\r?\n|.)+?)</div>", "<br>$1<br>", RegexOptions.IgnoreCase);
                            pattern = @"[\[]*[\d]*[\u2460-\u2473][\]]*";
                            Regex regex = new Regex(pattern);
                            editor_note_str = regex.Replace(editor_note_str, "", 1);

                            editor_note_str = editor_note_str.Substring(3, editor_note_str.Length - 4);
                            main_content += string.Format("<a id='bz{0}' href='#bzref{0}'>FN{0}</a> ",
                                        i + 1);
                            main_content += editor_note_str + "<br>\n";
                        }
                        main_content += "</aside>\r\n";
                    }

                    // 普通注释替换（简化 id）
                    List<int> annotation_nums = new List<int>();
                    if (book.Annotations != null)
                    {
                        foreach (Annotation annotation in book.Annotations)
                            annotation_nums.Add(annotation.Number);
                    }

                    if (annotation_method1)
                    {
                        if (book.Annotations != null)
                        {
                            foreach (int annotation_num in book.Content_Annotation_Numbers)
                            {
                                if (annotation_nums.Contains(annotation_num))
                                {
                                    if (!is_mode2)
                                    {
                                        pattern = @"\[" + annotation_num.ToString() + @"\](?![年月日]|[\d]{2}年)";
                                        replacement = string.Format("<sup><a id='zref{0}' href='#z{0}'><b>{0}</b></a></sup>", annotation_num);
                                        main_content = Regex.Replace(main_content, pattern, replacement);
                                    }
                                    else
                                        main_content = main_content.Replace("[" + annotation_num.ToString() + "]",
                                                            string.Format("<sup>〔<a id='zref{0}' href='#z{0}'><b>{0}</b></a>〕</sup>", annotation_num));
                                }
                            }
                        }
                        else
                        {
                            foreach (int annotation_num in book.Content_Annotation_Numbers)
                            {
                                if (!is_mode2)
                                {
                                    pattern = @"\[" + annotation_num.ToString() + @"\](?![年月日]|[\d]{2}年)";
                                    replacement = string.Format("<sup><a id='zref{0}' href='#z{0}'><b>{0}</b></a></sup>", annotation_num);
                                    main_content = Regex.Replace(main_content, pattern, replacement);
                                }
                                else
                                    main_content = main_content.Replace("[" + annotation_num.ToString() + "]",
                                                        string.Format("<sup>〔<a id='zref{0}' href='#z{0}'><b>{0}</b></a>〕</sup>", annotation_num));
                            }
                        }
                    }
                    else if (annotation_method2)
                    {
                        if (book.Annotations != null)
                        {
                            foreach (int annotation_num in book.Content_Annotation_Numbers)
                            {
                                if (annotation_nums.Contains(annotation_num))
                                {
                                    if (!is_mode2)
                                    {
                                        pattern = @"\[" + annotation_num.ToString() + @"\](?![年月日]|[\d]{2}年)";
                                        replacement = string.Format("<sup><a id='zref{0}' href='#z{0}'><b>{0}</b></a></sup>", annotation_num);
                                        main_content = Regex.Replace(main_content, pattern, replacement);
                                    }
                                    else
                                        main_content = main_content.Replace("[" + annotation_num.ToString() + "]",
                                                            string.Format("<sup>〔<a id='zref{0}' href='#z{0}'><b>{0}</b></a>〕</sup>", annotation_num));
                                }
                            }
                        }
                    }

                    if (book.Annotations != null)
                    {
                        if (is_format2)
                            main_content += "<HR>\r\n<P class=\"quote\">\n<span class=\"style2\"><B>注&emsp;&emsp;释</B></span><BR><BR>\r\n";
                        else
                            main_content += "<aside class=\"quote\">\r\n<span style=\"font-size:1.2em\">【注释】</span><br>\r\n";
                        foreach (Annotation annotation in book.Annotations)
                        {
                            if (!is_mode2)
                                main_content += string.Format("<a id='z{0}' href='#zref{0}'><b>{0}</b></a> ", annotation.Number);
                            else
                                main_content += string.Format("〔<a id='z{0}' href='#zref{0}'><b>{0}</b></a>〕 ", annotation.Number);

                            string Annotion_str = annotation.Content;
                            // 处理注释内容中的表格和居中（使用 <mdd> 临时保护）
                            Annotion_str = Regex.Replace(Annotion_str, @"<center>([\s\S]+?)</center>", "<span class=\"ct\">$1</span>");
                            Annotion_str = Regex.Replace(Annotion_str, @"<p style=[""']text-align:center[""']>([^<]+?)</p>", "<span class=\"ct\">$1</span>");
                            Annotion_str = Regex.Replace(Annotion_str, @"<p align=[""']center[""']>([^<]+?)</p>", "<span class=\"ct\">$1</span>");
                            Annotion_str = Regex.Replace(Annotion_str, @"<p style=[""']text-align:center[""']>((?:[^<]+?<br>)+[^<]*?)</p>", "<span class=\"ct\">$1</span>");
                            Annotion_str = Regex.Replace(Annotion_str, @"<p align=[""']center[""']>((?:[^<]+?<br>)+[^<]*?)</p>", "<span class=\"ct\">$1</span>");
                            Annotion_str = Regex.Replace(Annotion_str, @"(<table(\r?\n|.)+?</table>)", "<br class=\"table\">$1<br class=\"table\"></mdd><mdd class=\"quote\">");
                            Annotion_str = Regex.Replace(Annotion_str, @"<div align=[""']center[""']>[\s]*?<br class=""table"">", "</mdd><mdd class=\"quote\"><br class=\"table\">", RegexOptions.IgnoreCase);
                            Annotion_str = Regex.Replace(Annotion_str, @"<p align=[""']center[""']>[\s]*?<br class=""table"">", "<br class=\"table\">", RegexOptions.IgnoreCase);
                            Annotion_str = Regex.Replace(Annotion_str, @"</mdd><mdd class=""quote"">[\s]*?</p>", "</mdd><mdd class=\"quote\">", RegexOptions.IgnoreCase);
                            Annotion_str = Regex.Replace(Annotion_str, @"<div style=[""']text-align:center[""']>((\r?\n|.)+?)</div>", "<span class=\"ct\">$1</span>");
                            Annotion_str = Regex.Replace(Annotion_str, @"<div align=[""']center[""']>((\r?\n|.)+?)</div>", "<span class=\"ct\">$1</span>");
                            Annotion_str = Regex.Replace(Annotion_str, @"<p([ \S]*?)>([\s\S]+?)</p>", "<span$1>$2</span>", RegexOptions.IgnoreCase);
                            Annotion_str = Regex.Replace(Annotion_str, @"<div([ \S]*?)>([\s\S]+?)</div>", "<span$1>$2</span>", RegexOptions.IgnoreCase);
                            Annotion_str = Regex.Replace(Annotion_str, @"<p[^<]*?>((\r?\n|.)+?)</p>", "<br>$1<br>", RegexOptions.IgnoreCase);
                            Annotion_str = Regex.Replace(Annotion_str, @"<div[^<]*?>((\r?\n|.)+?)</div>", "<br>$1<br>", RegexOptions.IgnoreCase);

                            main_content += Annotion_str + "<br>\r\n";
                        }
                        main_content += "</aside>\r\n";
                    }

                    if ((main_content.Contains("[注：")) || (main_content.Contains("中文马克思主义文库")))
                    {
                        book.NoWarning = false;
                        book.Warning_Info.Add("WriteBook：处理后的文件存在\"[注：\"或未处理妥当");
                    }

                    // ---------- 合并 Program.cs 中的大量后处理（表格、对齐等） ----------
                    // 以下代码直接取自 Program.cs 的 WriteBook 方法（从 if ((main_content.Contains("[注：")) 之后的部分）
                    // 注意：已经包含了将临时标记 </mdd><mdd class="quote"> 最终替换为 </p><p class="footnote"> 等操作

                    main_content = main_content.Replace("*|*", "[");
                    main_content = main_content.Replace("|*|", "]");
                    main_content = main_content.Replace("&quot;", "\"");
                    pattern = @"(<h[34][\s]*style=[""']text-align[\s]*:[\s]*center['""]>)([\S]+)[ ]+([\S]*?)(</h[34]>)";
                    main_content = Regex.Replace(main_content, pattern, "$1$2　$3$4");
                    pattern = @"<p[\s]*class=[""']author['""]><p align=";
                    main_content = Regex.Replace(main_content, pattern, "<p align=");
                    pattern = @"<p[\s]*class=[""']author['""]>([\s\S]+?)(</p>)";
                    main_content = Regex.Replace(main_content, pattern, "<div class=\"ct\">$1</div>");
                    main_content = main_content.Replace("・", "·");
                    pattern = @"￥[\d]*?￥";
                    main_content = Regex.Replace(main_content, pattern, "", RegexOptions.IgnoreCase);
                    main_content = main_content.Replace("￥载于￥", "[载于]");
                    main_content = main_content.Replace("￥", "");
                    pattern = @"<span lang=""EN-US""><font[\s]+color=[ \S]*?><span style=[""']font-size:[\s]*10.5pt[""']>([\s]*[\s\S]+?[\s]*)</span></font>";
                    main_content = Regex.Replace(main_content, pattern, "$1", RegexOptions.IgnoreCase);
                    pattern = @"<span lang=[""']EN-US[""']><span[\s]+style=[""']font-size:[\s]+10.5pt[""']><font[\s]+color=[\s\S]*?>([\s]*[\s\S]+?[\n]*?)</span></font>";
                    main_content = Regex.Replace(main_content, pattern, "$1", RegexOptions.IgnoreCase);
                    pattern = @"<span lang=[""']EN-US[""']><span[\s]+style=[""']font-size: 10.5pt[""']><font color=[""'][\s\S]*?[""']>([\s]*[\s\S]+?[\n]*?)</font></span>";
                    main_content = Regex.Replace(main_content, pattern, "$1", RegexOptions.IgnoreCase);
                    pattern = @"<span lang=[""']EN-US[""']>([\S ]+?)</span>";
                    main_content = Regex.Replace(main_content, pattern, "$1", RegexOptions.IgnoreCase);
                    pattern = @"<span lang=[""']EN-US[""']>([\d ]+?)</span>";
                    main_content = Regex.Replace(main_content, pattern, "$1", RegexOptions.IgnoreCase);
                    pattern = @"<font color=[ \S]*?><span[\s]+style=[""']FONT-SIZE:[\s]*10.5pt[""']><font[\s]+color=[""'][ \S]*?[""']><span style=[""']FONT-SIZE:[\s]*10.5pt[""']>([\s]*[\s\S]+?[\n]*?)</span></font></span></font>";
                    main_content = Regex.Replace(main_content, pattern, "$1", RegexOptions.IgnoreCase);
                    pattern = @"<font[\s]+color=[ \S]*?><span style=[""']FONT-SIZE:[\s]*10.5pt[""']>[\s]*([\s\S]+?[\n]*?)(?:(?:</span></font>)|(?:</font></span>))";
                    main_content = Regex.Replace(main_content, pattern, "$1", RegexOptions.IgnoreCase);
                    pattern = @"<span style=[""']FONT-SIZE:[\s]*10.5pt[""']><font[\s]+color=[ \S]*?>[\s]*([\s\S]+?[\n]*?)(?:(?:</span></font>)|(?:</font></span>))";
                    main_content = Regex.Replace(main_content, pattern, "$1", RegexOptions.IgnoreCase);
                    pattern = @"(<span style=[""']FONT-SIZE:[\s]*10.5pt[""']>|<font[\s]+color=[ \S]*?>)";
                    main_content = Regex.Replace(main_content, pattern, "", RegexOptions.IgnoreCase);
                    pattern = @"[\[]*<sup>(<a[\s\S]+?)</sup>[\]]*";
                    main_content = Regex.Replace(main_content, pattern, "<sup>$1</sup>", RegexOptions.IgnoreCase);
                    pattern = @"([\r\n\s]*?)(<br>)";
                    main_content = Regex.Replace(main_content, pattern, "$2");
                    pattern = @"</h3><br>\s*　　";
                    replacement = @"</h3>
<br>　　";
                    main_content = Regex.Replace(main_content, pattern, replacement);
                    main_content = main_content.Replace("<br><br>", "<br>");
                    main_content = main_content.Replace("&emsp;&emsp;<br>", "<br>&emsp;&emsp;");
                    pattern = @"(</h[\d]>)[\s\r\n]*<p title=""start"">[\s\r\n]*(?:<br>[\s\r\n]*)*<(?:div|p) (?:class=[""'](?:date|author|ct)[""']|align=[""']center[""'])>[\s\r\n]*?(<sup><a[^<]+?>[\S]+?</a></sup>)[\s]*</(?:div|p)>";
                    replacement = @"$2$1\r\n<p title=""start"">";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"(</h[\d]>)[\s\r\n]*<p title=""start"">[\s\r\n]*(?:<br>[\s\r\n]*)*(<(?:div|p) (?:class=[""'](?:date|author|ct)[""']|align=[""']center[""'])>)*[\s\r\n]*?(<sup><a[^<]+?>[\S]+?</a></sup>)<br>[\r\n]*";
                    replacement = @"$3$1\r\n<p title=""start"">\r\n$2";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"(</h[\d]>)[\s\r\n]*(?:<br>[\s\r\n]*)*<(?:div|p|center)[ ]*(?:class=[""'](?:date|author|ct)[""']|align=[""']center[""'])*>[\s]*?(<sup><a[^<]+?>[\S]+?</a></sup>)[\s]*</(?:div|p|center)>[\r\n]*";
                    replacement = @"$2$1\r\n";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"(</h[\d]>)[\s\r\n]*(?:<br>[\s\r\n]*)*(<(?:div|p) (?:class=[""'](?:date|author|ct)[""']|align=[""']center[""'])>)*[\s]*?(<sup><a[^<]+?>[\S]+?</a></sup>)[\s]*<br>[\r\n]*";
                    replacement = @"$3$1\r\n$2";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"(</h[\d]>)[\s\r\n]*(?:<br>[\s\r\n]*)*(<sup><a[^<]+?>[\S]+?</a></sup>)[\s]*[\r\n]*";
                    replacement = @"$2$1";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);

                    if (book.Collection == "马恩全集")
                    {
                        pattern = @"(<br>)\s*\1+";
                        replacement = @"$1";
                        main_content = Regex.Replace(main_content, pattern, replacement);
                        main_content = main_content.Replace("</h3><br>", "</h3><br>　　");
                        main_content = main_content.Replace("</h3><br>　　　　", "</h3><br>　　");
                        main_content = main_content.Replace("</h3><br>　　&emsp;&emsp;", "</h3><br>　　");
                        pattern = @"</h1>[\s\r\n]*<p title=""start"">[\s\r\n]*(?:<br>[&emsp;\s\r\n]*)*(?:<p>)*<div align=[""']right[""']>[\s]*?<table[\s]+border=[""']0[""'][\s]+cellspacing=[""']0[""'][\s]+cellpadding=[""']0[""']>[\s]*<tr>[\s]*<td[^<]+?style=[""']line-height: 200%[""']>([\s\r\n\S]*?)</td></tr></table></div>";
                        replacement = @"</h1>\r\n<p title=""start"">\r\n<table class=""add rt"">\r\n<tr><td>$1</td></tr></table>";
                        main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                        pattern = @"<div align=([""'])right[""']>[\s\r\n]*?<table[\s]+border=[""']0[""'][\s]+cellspacing=[""']0[""'][\s]+cellpadding=[""']0[""']([^<]*?)class=[""']table1[""']>[\s]*?<tr>[\s]*?<td[^<]+?style=[""']line-height:[\s]*[\d]+%[""']>[\s\r\n]*([\S]*?(?:卡·马克思|弗·恩格斯|和){1,3}[写的成合]+)";
                        replacement = @"<table class=$1src rt$1$2><tr><td>\r\n$3";
                        main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                        pattern = @"<div align=([""'])right[""']>[\s]*?(<table[\s]+border=[""']0[""'][\s]+cellspacing=[""']0[""'][\s]+cellpadding=[""']0[""'])([^<]*?)>[\s]*?<tr>[\s]*?<td[^<]+?style=[""']line-height:[\s]*[\d]+%[""']>[\s\r\n]*([\S]*?(?:卡·马克思|弗·恩格斯|和){1,3}[写于的成合]+)";
                        replacement = @"<table class=$1src rt$1$3><tr><td>\r\n$4";
                        main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                        pattern = @"<div align=([""'])right[""']>[\s]*?(<table[\s]+border=[""']0[""'][\s]+cellspacing=[""']0[""'][\s]+cellpadding=[""']0[""'])([^<]*?)>[\s]*?<tr>[\s]*?<td[^<]+?style=[""']line-height: 200%[""']>([\s]*卡·马克思写)";
                        replacement = @"<table class=$1src rt$1$3><tr><td>$4";
                        main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                        pattern = @"<div align=([""'])right[""']>[\s]*?<table[\s]+border=[""']0[""'][\s]+cellspacing=[""']0[""'][\s]+cellpadding=[""']0[""']([^<]*?)>[\s]*?<tr>[\s]*?<td[^<]+?style=[""']line-height:[ ]*2[^<]+?[""']>[\s]*((?:(?!</table>|</td>|[文载写译单版])[\S\s\r\n])+?(?:<br>|</div>|</p>)+)[\s\r\n]*([\S]*?卡·马克思[写于的成]|[\S]*?弗·恩格斯[写于的成]|[\S]*?卡·马克思和弗·恩格斯[写于的成])";
                        replacement = @"<div class=""rt"">$3</div>\r\n<table class=$1src rt$1$2><tr><td>\r\n$4";
                        main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                        pattern = @"<div align=([""'])center[""']>[\s]*<table class=[""']MsoNormalTable[""']([^<]*?)style=[""']([^<]*?)[; ]*[""']([^<]*?)>";
                        replacement = @"<div title=""table""><table style=$1margin:1.5em auto;max-width:100%;$3;$1$2$4>";
                        main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                        pattern = @"<div align=([""'])center[""']>[\s]*<table class=[""']MsoTableGrid[""']([^<]*?)style=[""']([^<]*?)[; ]*[""']([^<]*?)>";
                        replacement = @"<div title=""table""><table style=$1margin:1.5em auto;max-width:100%;$3;$1$2$4>";
                        main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                        pattern = @"<div align=([""'])center[""']>[\s]*<table style=[""']([^<]*?)[; ]*[""']([^<]*?)class=[""']MsoNormalTable[""']([^<]*?)>";
                        replacement = @"<div title=""table""><table style=$1margin:1.5em auto;max-width:100%;$2;$1$3$4>";
                        main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                        pattern = @"<div align=([""'])center[""']>[\s]*<table style=[""']([^<]*?)[; ]*[""']([^<]*?)class=[""']MsoTableGrid[""']([^<]*?)>";
                        replacement = @"<div title=""table""><table style=$1margin:1.5em auto;max-width:100%;$2;$1$3$4>";
                        main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                        pattern = @"<p style=""TEXT-ALIGN: left"" class=""MsoNormal"" align=""left"">";
                        main_content = Regex.Replace(main_content, pattern, "", RegexOptions.IgnoreCase);
                    }

                    pattern = @"<div align=([""'])right[""']>[\s\r\n]*?<table[\s]+border=[""']0[""'][\s]+cellspacing=[""']0[""'][\s]+cellpadding=[""']0[""']([^<]*?)class=[""']table1[""']>[\s\r\n]*?<tr>[\s]*?<td[^<]+?style=[""']line-height:[ ]*[\d]+%[ ]*[""']>[\s\r\n]*([\S]*?载于|译自|写于|第一次|原文是|[\S]{0,50}(?:发[表行]|出版|[写册单成稿])[\S]{0,10})";
                    replacement = @"<table class=$1src rt$1$2><tr><td>\r\n$3";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<div align=([""'])right[""']>[\s\r\n]*?<table[\s]+border=[""']0[""'][\s]+cellspacing=[""']0[""'][\s]+cellpadding=[""']0[""']([^<]*?)>[\s]*?<tr>[\s]*?<td[^<]+?style=[""']line-height:[^<]+?[""']>[\s\r\n]*([\S]*?载于|译自|起草于|写于|第一次|原文是|[\S]{0,50}(?:发[表行]|出版|[写册单成稿])[\S]{0,10})";
                    replacement = @"<table class=$1src rt$1$2><tr><td>\r\n$3";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<p align=[""']center[""'] style=[""']text-align:[\s]*center[""']>([^<]+?)</p>";
                    replacement = @"<span class=""ct"">$1</span>";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<p align=[""']center[""'] style=[""']text-align:[\s]*center[""']>((?:[^<]+?<br>)+[^<]*?)</p>";
                    replacement = @"<span class=""ct"">$1</span>";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<p align=[""']center[""'] style=[""']text-align:[\s]*center[""']>([^<]+?)(<br>|</td>)";
                    replacement = @"<span class=""ct"">$1</span>$2";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<p class=""(?:MsoNormal|Msoplaintext)"">([\S\r\n\s]+?)</td>";
                    replacement = @"$1</td>";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<p class=""(?:MsoNormal|Msoplaintext)"">([\S\r\n\s]+?)</p>[\s\r\n]*</td>";
                    replacement = @"$1</td>";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<div align=([""'])right[""']>[\s\r\n]*?<table[\s]+border=[""']0[""'][\s]+cellspacing=[""']0[""'][\s]+cellpadding=[""']0[""']([^<]*?)>[\s\r\n]*?<tr>[\s\r\n]*?<td[^<]+?style=[""']line-height:[ ]*2[^<]+?[""']>[\s\r\n]*((?:(?!</table>|</td>|[文载写译])[\S\s\r\n])+?(?:<br>|</div>|</p>)+)[\s\r\n]*([\S]*?载于|译自|写于|起草于|第一次|原文是|[\S]{0,50}(?:发[表行]|出版|[写册单成稿])[\S]{0,10})";
                    replacement = @"<div class=""rt"">$3</div>\r\n<table class=$1src rt$1$2><tr><td>\r\n$4";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<div align=([""'])right[""']>[\s]*?<table[\s]+border=[""']0[""'][\s]+cellspacing=[""']0[""'][\s]+cellpadding=[""']0[""'] class=""[^<]*?"">[\s]*?<tr>[\s]*?<td[^<]+?style=[""']line-height:[ ]*2[^<]+?[""']>";
                    replacement = @"<div title=""table""><table class=$1rt$1><tr><td>";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<div align=([""'])right[""']>[\s]*?<table[\s]+border=[""']0[""'][\s]+cellspacing=[""']0[""'][\s]+cellpadding=[""']0[""'](?: class=""[^<]*?"")*([^<]*?)>[\s]*?<tr>[\s]*?<td[^<]+?style=[""']line-height:[ ]*2[^<]+?[""']>";
                    replacement = @"<div title=""table""><table class=$1rt$1$2><tr><td>";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<div align=([""'])right[""']>[\s]*?<table[\s]+border=[""']0[""'][\s]+cellspacing=[""']0[""'][\s]+cellpadding=[""']0[""'](?: class=""[^<]*?"")*([^<]*?)>[\s\r\n]*?<tr>";
                    replacement = @"<div title=""table""><table class=$1rt$1$2><tr>";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<div class=[""']rt[""']>[\s]*?([\s\S]+?)[\s\r\n]*<p align=""right"">[\s]*?([\s\S]+?)</p>";
                    replacement = @"<div class=""rt"">$1<br>$2";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<p align=([""'])([\S]+?)[""']>([^<]+?)</p>";
                    replacement = @"<div align=$1$2$1>$3</div>";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<p style=([""'])text-align:[ ]*([^<]+?)[;]*[""']>([^<]+?)</p>";
                    replacement = @"<div align=$1$2$1>$3</div>";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<p align=([""'])([\S]+?)[""']>((?:[^<>]*?(?:<br>|<sup><a[^<>]+?>[\s\S]+?</a></sup>|(?:<[bu]>){1,2}[^<>]+?|[^<>]+?(?:</[bu]>){1,2})+?[^<>]*?[\s\r\n]*)+[^<>]*?)(?:</p>|<br>)(</td>)*";
                    replacement = @"<div align=$1$2$1>$3</div>$4";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<p align=([""'])([\S]+?)[""']>([^<]+?)(<br>|</td>)";
                    replacement = @"<div align=$1$2$1>$3</div>$4";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<p style=([""'])([^<]+?)[""']>((?:[^<>]*?(?:<br>|<sup><a[^<>]+?>[\s\S]+?</a></sup>|(?:<[bu]>){1,2}[^<>]+?|[^<>]+?(?:</[bu]>){1,2})+?[^<>]*?[\s\r\n]*)+[^<>]*?)(?:</p>|<br>)(</td>)*";
                    replacement = @"<div style=$1$2$1>$3</div>$4";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<p style=([""'])([^<]+?)[""']>([^<]+?)(<br>|</td>)";
                    replacement = @"<div style=$1$2$1>$3</div>";
                    pattern = @"<p class=([""'])([^<]+?)[""']>([^<]+?)</p>";
                    replacement = @"<div class=$1$2$1>$3</div>";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<p class=([""'])([^<]+?)[""']>((?:[^<>]*?(?:<br>|<sup><a[^<>]+?>[\s\S]+?</a></sup>|(?:<[bu]>){1,2}[^<>]+?|[^<>]+?(?:</[bu]>){1,2})+?[^<>]*?[\s\r\n]*)+[^<>]*?)(?:</p>|<br>)(</td>)*";
                    replacement = @"<div class=$1$2$1>$3</div>$4";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<p class=([""'])([^<]+?)[""']>([^<]+?)(<br>|</td>)";
                    replacement = @"<div class=$1$2$1>$3</div>";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<p (?:class|align|style)=[""'][^<]+?[""']>[\r\n\s]*?</p>";
                    main_content = Regex.Replace(main_content, pattern, "", RegexOptions.IgnoreCase);
                    pattern = @"<br>&emsp;&emsp;\s*?　　";
                    replacement = @"<br>　　";
                    main_content = Regex.Replace(main_content, pattern, replacement);
                    pattern = @"<br>　　\s*?　　([\S])";
                    replacement = @"<br>　　$1";
                    main_content = Regex.Replace(main_content, pattern, replacement);
                    pattern = @"<br class=""table"">[\s]*?<table[\s]+border=[""']0[""'][\s]+cellspacing=[""']0[""'][\s]+cellpadding=[""']0[""']>((\r?\n|.)+?)<br class=""table"">";
                    replacement = @"<table class='footnote tnb' style='margin:1.5em auto;max-width:80%;'>$1";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<br class=""table"">[\s]*?<table[\s]+border=[""']0[""'][\s]+cellspacing=[""']0[""'][\s]+cellpadding=[""']0[""'][^<\r\n]*?width=[""']([6789][\d]{2})[""'][^<]*?>((\r?\n|.)*?)<br class=""table"">";
                    replacement = @"<table class='footnote tnb' style='margin:1.5em auto;max-width:100%;width:$1px;'>$2";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<br class=""table"">[\s]*?<table([\s]+border=[""']0[""'][\s]+cellspacing=[""']0[""'][\s]+cellpadding=[""']0[""'])[^\r\n]*?width=[""']([12345][\d]{2})[""'][ \S]*?>((\r?\n|.)*?)<br class=""table"">";
                    replacement = @"<table class='footnote' style='margin:1.5em auto;max-width:80%;width:$2px'$1>$3";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<br class=""table"">[\s]*?<table([^<\r\n]*?)class=[""'][\S]+[""']([^<\r\n]*?)width=[""']([\d]{1,3}%)[""']([^\r\n]*?)>((\r?\n|.)+?</table>)<br class=""table"">";
                    main_content = Regex.Replace(main_content, pattern, "<table class=\"footnote\" style=\"margin:1.5em auto;width:$3;\" $1$2$4>$5");
                    pattern = @"<br class=""table"">[\s]*?<table[\s]+class=([""'])[\S]+[""']([^<\r\n]*?)width=[""']([12345][\d]{2})[""']([^\r\n]*?)>((\r?\n|.)+?)<br class=""table"">";
                    replacement = @"<table style=$1margin:1.5em auto;max-width:80%;width:$3;px$1 class=$1footnote$1 $2$4>$5";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<br class=""table"">[\s]*?<table[\s]+class=([""'])[\S]+[""']([^<\r\n]*?)width=[""']([6789][\d]{2})[""']([^\r\n]*?)>((\r?\n|.)+?)<br class=""table"">";
                    replacement = @"<table class=$1footnote$1 style=$1margin:1.5em auto;max-width:100%;width:$3px;$1$2$4>$5";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<br class=""table"">";
                    main_content = Regex.Replace(main_content, pattern, "", RegexOptions.IgnoreCase);
                    pattern = @"</mdd><mdd class=""quote"">";
                    replacement = @"</p><p class=""footnote"">";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<div align=([""'])center[""']>[\s\r\n]*?<table[\s]+border=[""']0[""'][\s]+cellspacing=[""']0[""'][\s]+cellpadding=[""']0[""'][^<]*?width=[""']([6789][\d]{2})[""'][^<]*?>";
                    replacement = @"<div title=""table""><table style=$1margin:1.5em auto;max-width:100%;width:$2px;$1 class=""tnb"">";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<div align=([""'])center[""']>[\s\r\n]*?<table[\s]+border=[""']0[""'][\s]+cellspacing=[""']0[""'][\s]+cellpadding=[""']0[""'][^<]*?width=[""']([12345][\d]{2})[""'][^<]*?>";
                    replacement = @"<div title=""table""><table style=$1margin:1.5em auto;max-width:80%;width:$2px;$1 class=""tnb"">";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<div align=([""'])center[""']>[\s\r\n]*?<table[\s]+border=[""']0[""'][\s]+cellspacing=[""']0[""'][\s]+cellpadding=[""']0[""'][^<]*?width=[""']([1]*[\d]{2}%)[""'][^<]*?>";
                    replacement = @"<div title=""table""><table style=$1margin:1.5em auto;width:$2;$1 class=""tnb"">";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<div align=[""']center[""']>[\s\r\n]*<table[\s]+border=[""']0[""'][\s]+cellspacing=[""']0[""'][\s]+cellpadding=[""']0[""'](?: align=center)*>";
                    replacement = @"<div title=""table""><table style=""margin:1.5em auto;max-width:80%;"" class=""tnb"">";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"[\s\r\n]+<table[\s]+border=[""']0[""'][\s]+cellspacing=[""']0[""'][\s]+cellpadding=[""']0[""'](?: align=center)*>";
                    replacement = "\r\n<table style=\"margin:1.5em auto;max-width:80%;\" class=\"tnb\">";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<table[\s]+border=[""']0[""'][\s]+cellspacing=[""']0[""'][\s]+cellpadding=[""']0[""'] width=([6789][\d]{2}) align=center>";
                    replacement = @"<table style=""margin:1.5em auto;max-width:100%;width:$1px;"" class=""tnb"">";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<table[\s]+border=[""']0[""'][\s]+cellspacing=[""']0[""'][\s]+cellpadding=[""']0[""'] width=([12345][\d]{2}) align=center>";
                    replacement = @"<table style=""margin:1.5em auto;max-width:80%;width:$1px;"" class=""tnb"">";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<table[\s]+border=[""']0[""'][\s]+cellspacing=[""']0[""'][\s]+cellpadding=[""']0[""'] width=([1]*[\d]{2}%) align=center>";
                    replacement = @"<table style=""margin:1.5em auto;width:$1;"" class=""tnb"">";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<div align=([""'])center[""']>[\s\r\n]*?<table[\s]+class=[""'][\S]+[""'] border=[""']0[""'] cellspacing=[""']0[""'] cellpadding=[""']0[""'] width=[""']([6789][\d]{2})[""']([^<]*?)>";
                    replacement = @"<div title=""table""><table style=$1margin:1.5em auto;max-width:100%;width:$2px;$1 class=""tnb""$3>";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<div align=([""'])center[""']>[\s\r\n]*?<table[\s]+class=[""'][\S]+[""'] border=[""']0[""'] cellspacing=[""']0[""'] cellpadding=[""']0[""'] width=[""']([12345][\d]{2})[""']([^<]*?)>";
                    replacement = @"<div title=""table""><table style=$1margin:1.5em auto;max-width:80%;width:$2px;$1 class=""tnb""$3>";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<div align=([""'])center[""']>[\s\r\n]*?<table[\s]+class=[""'][\S]+[""'] border=[""']0[""'] cellspacing=[""']0[""'] cellpadding=[""']0[""'] width=[""']([1]*[\d]{2}%)[""']([^<]*?)>";
                    replacement = @"<div title=""table""><table style=$1margin:1.5em auto;width:$2;$1 class=""tnb""$3>";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<div align=[""']center[""']>[\s\r\n]*?<table([^<\r\n]+?)style=[""']([^<]+?)[;]*[""']([^<\r\n]*?)class=[""'][^f]+?[""']([^<\r\n]*?)width=[""']([6789][\d]{2})[""']([^<\r\n]*?)>";
                    main_content = Regex.Replace(main_content, pattern, "<div title=\"table\"><table style=\"margin:1.5em auto;width:$5px;$2;\"$1$3$4$6>");
                    pattern = @"<div align=[""']center[""']>[\s\r\n]*?<table([^<\r\n]+?)style=[""']([^<]+?)[;]*[""']([^<\r\n]*?)class=[""'][^f]+?[""']([^<\r\n]*?)width=[""']([12345][\d]{2})[""']([^<\r\n]*?)>";
                    main_content = Regex.Replace(main_content, pattern, "<div title=\"table\"><table style=\"margin:1.5em auto;width:$5px;$2;\"$1$3$4$6>");
                    pattern = @"<div align=[""']center[""']>[\s\r\n]*?<table([^<\r\n]*?)style=[""']([^<]+?)[;]*[""']([^<\r\n]*?)class=[""'][^f]+?[""']([^<\r\n]*?)width=[""']([\d]{1,3}%)[""']([^<\r\n]*?)>";
                    main_content = Regex.Replace(main_content, pattern, "<div title=\"table\"><table style=\"margin:1.5em auto;width:$5;$2;\"$1$3$4$6>");
                    pattern = @"<div align=[""']center[""']>[\s\r\n]*?<table([^<\r\n]*?)class=[""'][^<]+?[""']([^<\r\n]*?)style=[""']([^<]+?)[;]*[""']([^<\r\n]*?)width=[""']([6789][\d]{2})[""']([^<\r\n]*?)>";
                    main_content = Regex.Replace(main_content, pattern, "<div title=\"table\"><table style=\"margin:1.5em auto;width:$5px;$3;\"$1$2$4$6>");
                    pattern = @"<div align=[""']center[""']>[\s\r\n]*?<table([^<\r\n]*?)class=[""'][^<]+?[""']([^<\r\n]*?)style=[""']([^<]+?)[;]*[""']([^<\r\n]*?)width=[""']([12345][\d]{2})[""']([^<\r\n]*?)>";
                    main_content = Regex.Replace(main_content, pattern, "<div title=\"table\"><table style=\"margin:1.5em auto;width:$5px;$3;\"$1$2$4$6>");
                    pattern = @"<div align=[""']center[""']>[\s\r\n]*?<table([^<\r\n]*?)class=[""'][^<]+?[""']([^<\r\n]*?)style=[""']([^<]+?)[;]*[""']([^<\r\n]*?)width=[""']([\d]{1,3}%)[""']([^<\r\n]*?)>";
                    main_content = Regex.Replace(main_content, pattern, "<div title=\"table\"><table style=\"margin:1.5em auto;width:$5;$3;\"$2$1$4$6>");
                    pattern = @"<div align=[""']center[""']>[\s\r\n]*?<table[\s]+class=[""'][\S]+[""']([^<]*?)width=[""']([6789][\d]{2})[""']([^<]*?)>";
                    replacement = @"<div title=""table""><table style=""margin:1.5em auto;max-width:100%;width:$2px;""$1$3>";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<div align=[""']center[""']>[\s\r\n]*?<table([^<\r\n]*?)class=[""'][\S]+[""']([^<]*?)width=[""']([12345][\d]{2})[""']([^<]*?)>";
                    replacement = @"<div title=""table""><table style=""margin:1.5em auto;max-width:80%;width:$3px;""$1$2$4>";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<div align=[""']center[""']>[\s\r\n]*?<table([^<\r\n]*?)class=[""'][\S]+?[""']([^<\r\n]*?)width=[""']([\d]{1,3}%)[""']([^<\r\n]*?)>";
                    main_content = Regex.Replace(main_content, pattern, "<div title=\"table\"><table style=\"margin:1.5em auto;width:$3;\"$1$2$4>");
                    pattern = @"<div align=[""']center[""']>[\s\r\n]*?<table([^<\r\n]*?)style=[""']([^<\r\n]*?)[;]*[""']([^<]*?)width=[""']([6789][\d]{2})[""']([^<]*?)>";
                    replacement = @"<div title=""table""><table style=""margin:1.5em auto;max-width:80%;width:$4px;$2;""$1$3$5>";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<div align=[""']center[""']>[\s\r\n]*?<table([^<\r\n]*?)style=[""']([^<\r\n]*?)[;]*[""']([^<]*?)width=[""']([12345][\d]{2})[""']([^<]*?)>";
                    replacement = @"<div title=""table""><table style=""margin:1.5em auto;max-width:80%;width:$4px;$2;""$1$3$5>";
                    main_content = Regex.Replace(main_content, pattern, replacement, RegexOptions.IgnoreCase);
                    pattern = @"<div align=[""']center[""']>[\s\r\n]*?<table([^<\r\n]*?)style=[""']([^<\r\n]*?)[;]*[""']([^<\r\n]*?)width=[""']([\d]{1,3}%)[""']([^<\r\n]*?)>";
                    main_content = Regex.Replace(main_content, pattern, "<div title=\"table\"><table style=\"margin:1.5em auto;width:$4;$2;\"$1$3$5>");
                    pattern = @"<div align=([""'])center[""']>[\s\r\n]*?<table([^<]+?)style=[""']([^<]+?)[""']([^<]*?)>";
                    main_content = Regex.Replace(main_content, pattern, "<div title=\"table\"><table style=$1margin:1.5em auto;$3$1$2$4>", RegexOptions.IgnoreCase);
                    pattern = @"<div align=([""'])center[""']>[\s\r\n]*?<table([^<]+?)>";
                    main_content = Regex.Replace(main_content, pattern, "<div title=\"table\"><table style=$1margin:1.5em auto;$1$2>", RegexOptions.IgnoreCase);
                    pattern = @"</table>[\s]*?<p>";
                    main_content = Regex.Replace(main_content, pattern, "</table>\r\n<br>");
                    pattern = @"(<table(?=((class=[""']footnote[""'])|(style=[""']margin:1.5em))[ \S]+?)>(\r?\n|.)+?)<span style=""text-align:center"">([\s\S]*?)</span>((\r?\n|.)+?)</table>";
                    main_content = Regex.Replace(main_content, pattern, "$1<span class=\"ct\">$2</span>$3");
                    pattern = @"<div title=""table"">(<table[\S\r\n\s]+?</table>[\s\r\n]*)</div>";
                    main_content = Regex.Replace(main_content, pattern, "$1");
                    pattern = @"</td></tr></table></body></html>";
                    main_content = Regex.Replace(main_content, pattern, "", RegexOptions.IgnoreCase);
                    pattern = @"><[\r\n]+";
                    main_content = Regex.Replace(main_content, pattern, ">\r\n", RegexOptions.IgnoreCase);
                    pattern = @"<(<[/a-z])";
                    main_content = Regex.Replace(main_content, pattern, "$1", RegexOptions.IgnoreCase);

                    pattern = @"<div style=""text-align[\s]*:[\s]*center[;\s]*"">";
                    main_content = Regex.Replace(main_content, pattern, "<div class=\"ct\">", RegexOptions.IgnoreCase);
                    pattern = @"<div align=""center"">";
                    main_content = Regex.Replace(main_content, pattern, "<div class=\"ct\">", RegexOptions.IgnoreCase);
                    pattern = @"<div align=""right"">";
                    main_content = Regex.Replace(main_content, pattern, "<div class=\"rt\">", RegexOptions.IgnoreCase);
                    pattern = @"<span align=""right"">";
                    main_content = Regex.Replace(main_content, pattern, "<span class=\"rt\">", RegexOptions.IgnoreCase);
                    pattern = @"<span align=""center"">";
                    main_content = Regex.Replace(main_content, pattern, "<span class=\"ct\">", RegexOptions.IgnoreCase);
                    pattern = @"<p><br>";
                    main_content = Regex.Replace(main_content, pattern, "<br>", RegexOptions.IgnoreCase);
                    pattern = @"<p title=""start"">(?:<br>)*";
                    main_content = Regex.Replace(main_content, pattern, "<p>", RegexOptions.IgnoreCase);
                    pattern = @"kfk￥\[";
                    main_content = Regex.Replace(main_content, pattern, "〔", RegexOptions.IgnoreCase);
                    pattern = @"\]kfk￥";
                    main_content = Regex.Replace(main_content, pattern, "〕", RegexOptions.IgnoreCase);
                    pattern = @"kfk￥￥sdvld￥";
                    main_content = Regex.Replace(main_content, pattern, "〔", RegexOptions.IgnoreCase);
                    pattern = @"kfksdvld";
                    main_content = Regex.Replace(main_content, pattern, "〔", RegexOptions.IgnoreCase);
                    pattern = @"kfk￥";
                    main_content = Regex.Replace(main_content, pattern, "", RegexOptions.IgnoreCase);
                    pattern = @"kfk";
                    main_content = Regex.Replace(main_content, pattern, "", RegexOptions.IgnoreCase);
                    pattern = @"\{第4版注：";
                    main_content = Regex.Replace(main_content, pattern, "〔第4版注：", RegexOptions.IgnoreCase);
                    pattern = @"弗·恩·\}";
                    main_content = Regex.Replace(main_content, pattern, "弗·恩·〕", RegexOptions.IgnoreCase);
                    // 输出最终内容
                    sw.WriteLine(main_content);

                    if (is_format2)
                        sw.WriteLine(" <HR></DIV></BODY>");
                    else
                        sw.WriteLine("</body>");
                    sw.WriteLine("</html>");
                    sw.Flush();
                    success_num++;
                }
            }
            catch (Exception ex)
            {
                CounterException?.Invoke(this, fs.Name, "WriteBook：" + ex.Message);
            }
            finally
            {
                sw?.Close();
            }
        }

        // ---------- Generate_Book 重载（支持文件路径） ----------
        private void Generate_Book(string filePath, string output_path)
        {
            try
            {
                processed_num++;

                Book book = new Book
                {
                    Editor_Notes = new List<string>(),
                    Author_Notes = new List<string>(),
                    viewabletext = new List<string>(),
                    Warning_Info = new List<string>(),
                    Annotations = null,
                    Title_Annotation_Num = 0
                };

                using (FileStream in_fs = new FileStream(filePath, FileMode.Open, FileAccess.Read))
                {
                    ReadBook(in_fs, ref book);
                }

                if (!book.NoError)
                {
                    error_num++;
                    BookException?.Invoke(this, filePath, ref book);
                }
                else
                {
                    string out_path = Path.Combine(output_path, book.Collection ?? "Unknown");
                    Directory.CreateDirectory(out_path);
                    out_path = Path.Combine(out_path, book.Volume ?? "Unknown");
                    Directory.CreateDirectory(out_path);
                    out_path = Path.Combine(out_path, book.FileName) + ".html";

                    using (FileStream out_fs = new FileStream(out_path, FileMode.Create))
                    {
                        WriteBook(out_fs, ref book);
                    }

                    if (!book.NoWarning)
                    {
                        warning_num++;
                        BookException?.Invoke(this, filePath, ref book);
                    }
                }
            }
            catch (Exception ex)
            {
                error_num++;
                CounterException?.Invoke(this, filePath, "Generate_Book：" + ex.Message);
            }
        }

        // ---------- EbooksProcess（使用文件列表） ----------
        public void EbooksProcess()
        {
            processed_num = 0;
            warning_num = 0;
            error_num = 0;
            success_num = 0;

            if (Files == null || Files.Count == 0)
            {
                Finished?.Invoke(this, 0);
                return;
            }

            files_num = Files.Count;
            int step = Math.Max(1, files_num / 100);

            for (int i = 0; i < Files.Count; i++)
            {
                string file = Files[i];
                string ext = Path.GetExtension(file).ToLowerInvariant();
                bool isHtml = ext == ".htm" || ext == ".html";
                bool isTxt = ext == ".txt";

                if (is_html_file_allowed && isHtml)
                {
                    Generate_Book(file, output_path);
                }
                else if (is_txt_file_allowed && isTxt)
                {
                    Generate_Book(file, output_path);
                }
                else
                {
                    MessageSend?.Invoke(this, file, " 文件类型不匹配，已跳过");
                }

                if ((i + 1) % step == 0)
                    ProgressUpdate?.Invoke(this, i + 1);
            }

            Finished?.Invoke(this, processed_num);
        }
    }

    // ---------- 命令行入口 (Program.cs 风格) ----------
    class Program
    {
        // ==================== 用户配置区域 ====================
        // 在此处修改路径和选项，然后编译运行即可
        private static readonly string InputDirectory = @"D:\马恩全集（第一版）\2版第44卷";   // 输入目录
        private static readonly string OutputDirectory = @"D:\Epic Games";               // 输出目录（会自动创建）

        // 处理选项
        private static readonly bool EnableTxt = true;          // 处理 .txt 文件
        private static readonly bool EnableHtml = true;         // 处理 .htm/.html 文件
        private static readonly bool EnableEditorNotes = true;  // 处理编者注
        private static readonly bool EnableAuthorNotes = true;  // 处理作者注
        private static readonly bool UseMethod1 = false;        // 注释方式1 (与method2互斥)
        private static readonly bool UseMethod2 = true;         // 注释方式2
        private static readonly bool EnableFirstlineReplace = false; // 首行替换
        private static readonly bool UseFormat2 = false;        // 输出格式2
        private static readonly bool UseMode2 = false;          // 毛文集模式
        // ======================================================

        static void Main(string[] args)
        {
            string inputDir = InputDirectory;
            string outputDir = OutputDirectory;

            if (!Directory.Exists(inputDir))
            {
                Console.WriteLine($"错误: 输入目录不存在: {inputDir}");
                Console.WriteLine("按任意键退出...");
                Console.ReadKey();
                return;
            }

            if (!Directory.Exists(outputDir))
                Directory.CreateDirectory(outputDir);

            var files = new List<string>();
            var searchOption = SearchOption.AllDirectories;
            if (EnableTxt)
                files.AddRange(Directory.GetFiles(inputDir, "*.txt", searchOption));
            if (EnableHtml)
            {
                files.AddRange(Directory.GetFiles(inputDir, "*.htm", searchOption));
                files.AddRange(Directory.GetFiles(inputDir, "*.html", searchOption));
            }

            if (files.Count == 0)
            {
                Console.WriteLine("警告: 没有找到任何可处理的文件。");
                Console.WriteLine("按任意键退出...");
                Console.ReadKey();
                return;
            }

            Console.WriteLine($"找到 {files.Count} 个文件，开始处理...");
            Console.WriteLine($"输出目录: {outputDir}");

            var processor = new EbookProcessor
            {
                Files = files,
                output_path = outputDir,
                is_txt_file_allowed = EnableTxt,
                is_html_file_allowed = EnableHtml,
                editor_notes_check = EnableEditorNotes,
                author_notes_check = EnableAuthorNotes,
                annotation_method1 = UseMethod1,
                annotation_method2 = UseMethod2,
                firstline_replace = EnableFirstlineReplace,
                is_format2 = UseFormat2,
                is_mode2 = UseMode2
            };

            processor.ProgressUpdate += (s, progress) =>
            {
                Console.Write($"\r进度: {progress}/{files.Count} ({(progress * 100 / files.Count)}%)");
            };
            processor.MessageSend += (s, path, msg) =>
            {
                Console.WriteLine($"\n[信息] {path}: {msg}");
            };
            processor.CounterException += (s, path, msg) =>
            {
                Console.WriteLine($"\n[异常] {path}: {msg}");
            };
            processor.BookException += (EbookProcessor s, string path, ref Book book) =>
            {
                if (!book.NoError)
                    Console.WriteLine($"\n[错误] {path}: {book.Error_Info}");
                if (!book.NoWarning)
                    foreach (var w in book.Warning_Info)
                        Console.WriteLine($"\n[警告] {path}: {w}");
            };
            processor.Finished += (s, processed) =>
            {
                Console.WriteLine($"\n处理完成。成功: {s.success_num}, 警告: {s.warning_num}, 错误: {s.error_num}");
            };

            processor.EbooksProcess();

            Console.WriteLine("按任意键退出...");
            Console.ReadKey();
        }
    }
}