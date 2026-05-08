In your reasoning, please follow the order of analyzing page layout → writing HTML code → checking the code against the original PDF page, step by step. After confirming there are no errors, output the final result.

# Analyzing Layout and Writing Code

- 1. When identifying layout information, you may rely on semantic connections. If there is an obvious mismatch between layout and semantics, promptly re-check the image and adjust according to what you see.
- 2. Discard headers (those with a horizontal line underneath, centered text, and page numbers). Do **not** treat headers as headings! Also, identify paragraphs that are split across adjacent pages and merge them into a single `<p>` tag.
- 3. Delete unnecessary hyphens (line-break hyphens). Restore correct spaces between words. Decide whether to keep a hyphen or add a space based on word completeness. If a hyphen is followed by a space (e.g., "aa- und bb-"), keep the hyphen.
- 4. Superscripts identified as endnotes (i.e., superscripts with brackets, like [123]) should be output only as anchors in the format: `<a id="Axx"></a>`. Do **not** output any visible text for them. Also, discard any navigation labels at the very bottom of the footer that point to endnotes (such as index information).
- 5. Convert footnote markers in the body (both author's notes and editor's notes) and the corresponding numbers before each footnote at the page footer into mutually clickable two‑way links. Ensure that clicking the superscript in the body jumps to the corresponding footnote, and clicking the footnote number in the footer returns to the original position. Follow these rules:
   - (1) For the author's own notes (i.e., notes by Marx, Engels, or Lenin), use the numbering and ids assigned during recognition. The link text must be enclosed in parentheses. Format for Marx/Engels notes: `<sup><a id="ZMxx" href="#Mxx">(xx)</a></sup>`.
   - (2) For editor's footnotes in the body (superscripts recognized as plain numbers), output as: `<sup><a id="ZFxx" href="#Fxx">xx</a></sup>`. If different pages have footnotes with the same number (e.g., page 101 and page 102 both have a footnote numbered 1 but with different content), assign the correct sequential ids based on the recognition phase.
   - (3) If there are multiple superscripts in the body pointing to the same footnote, output each superscript with its own id based on recognition: `<sup><a id="ZFxx-序号" href="#Fxx">xx</a></sup>`. The corresponding link in the footer only needs to return to the **first** superscript occurrence.
   - (4) All footer footnote content should be placed at the end of the `<body>`, wrapped in `<aside>`. Author's notes and editor's notes must be in separate `<aside>` elements: first the `<aside>` for author's notes, then the `<aside>` for editor's notes. Each footnote should be on its own line, formatted as: `<p><a id="Fxx/Mxx" href="#ZFxx/ZMxx">xx</a> 注释内容</p>`. Also, if an author's note contains editor's note numbers inside its text, those editor's note numbers must be converted into superscript links as well.
- 6. Correctly convert italics, right‑alignment, centering, blockquotes, full‑line indentation, and other formatting. Follow these requirements:
   - Output only `<body>` and `<title>`, nothing extra.
   - The `<title>` defaults to the header content **without** the page number. Apart from the discarded headers, all other styles (bold, italic, right‑aligned, centered, blockquotes, tables, etc.) must be correctly output.
   - Centered text: `<p align="center">`; right‑aligned: `<p align="right">`; author blockquotes: `<blockquote>`.
   - Italics: `<i>`; bold: `<b>`.
   - Table headers: use `</td> only; preserve the original table layout. Note that footnotes may also contain tables.
   - For headings of various levels, **do not** add centering style or `align`. Use `<br>` for line breaks. Multi‑line headings should be contained in a single tag. For letter headings in particular, output them in a single `<h1>` tag.
   - For images: leave an empty tag (add an `alt` attribute if a description is available). If an image occupies an entire page and separates a complete paragraph, place the image tag at the end of the nearest paragraph.
   - Other layout styles on the page must also be encoded with inline styles or tags to ensure correct rendering on both mobile and desktop. For example, use appropriate `margin` to reproduce indentation effects; use tables for multi‑column layouts; use appropriate styles for formulas. **Do not** write any CSS/styles inside `<head>`!
- 7. Before finishing the conversion or reasoning, re‑check the output. Proofread for any conversion errors or omissions (e.g., missing italics, incorrect footnote markup, wrong formatting). Only output after verification.

# Output Template

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
...
<p><a id="Mxx" href="#ZMxx">(xx)</a> xxxx.....</p>
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

# Guidelines for Identifying Different Types of Notes

Identify notes in the following order and by their characteristics:

   - (1) First, identify the author's own notes (Marx, Engels):
     - The author's note section is separated from the main text at the footer by a short horizontal line (left‑aligned), and the font size is similar to the main text.
     - Author's note markers are usually plain numbers (e.g., 101), numbers with letters (e.g., 202a), or superscripts/markers with letters inside square brackets (e.g., 6[a]).
   - (2) Second, identify editor's notes:
     - The editor's note section is separated from the main text and author's notes by a long horizontal line spanning the page. Use this feature to distinguish author's notes from editor's notes.
     - Editor's note markers are usually numbers with an asterisk (e.g., 1*).
     - Also note cases where the same superscript appears multiple times on the same page.
     - When recognizing editor's note entries, correctly identify multiple note contents and numbers separated by en‑dashes (`–`), spaces, etc., within the footer.
   - (3) Also identify content index information at the very bottom of the footer, such as isolated numbers (e.g., 5), isolated numbers with asterisks (e.g., 11*), or items like "3 MEW Band 3 S.221", "5 Karl Marx Kapital I", etc. These are navigation labels for endnotes and should be discarded.
   - (4) Superscripts with numbers inside square brackets (e.g., [123]) are endnote numbers. They belong to a numbering system independent from footnotes. Besides identifying them by the square brackets, you can also judge endnotes by the order in which they appear: for example, if a note number like 2 or 5 (greater than 1) appears near the beginning of a chapter, it is very likely an endnote. In such cases, re‑check the image to distinguish endnotes from footnotes.
   - (5) After identifying author's notes and editor's notes (excluding author's notes in *Das Kapital*), renumber them to ensure uniqueness and continuity within each group.
   - (6) After determining the numbers, generate ids for each note:
      - Prefix for Marx/Engels notes: `M`; prefix for editor's notes: `F`. Do **not** renumber author's notes.
      - For the corresponding superscripts, add `Z` before `M`/`F` (e.g., `ZM`, `ZF`). If the same note number appears multiple times on the same page, add a `-sequence` suffix to each superscript id after the first one (e.g., `ZFxx-1`, `ZFxx-2`).
   - (7) In the footer's author's note or editor's note section, paragraphs without a preceding number, or text immediately under the separator line without indentation, are continuations of the previous footnote (i.e., footnotes that span multiple pages). Such footnotes may be distributed across several pages; be sure to merge them.
   - (8) If a footnote entry has multiple paragraphs, identify and preserve all of them accurately.
