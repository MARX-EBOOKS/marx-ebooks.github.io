Convert this scanned page to a semantic HTML fragment.

[[context_block]]
[[header_hint]]
CONVERSION RULES:

1. RUNNING HEADERS AND FOOTERS — STRIP COMPLETELY
   Running headers (Kolumnentitel) are the repeated navigation lines at the very top of each page
   (author/editor name, book title, article or chapter title, volume number, etc.).
   Running footers are similar lines at the bottom.
   Do NOT include any running header or footer text in the output.

2. PAGE NUMBER EXTRACTION
   Locate the typeset arabic page number. It usually appears in the top or bottom margin,
   at the outer corner of a running header/footer line, or in the margin column.
   Emit it ONCE as:  <span class="page-num" data-page="N">N</span>
   Place this at the very start of the output fragment.
   If no arabic page number is visible, omit this span entirely.

3. INLINE FORMATTING
   Italic text → <em>…</em>
   Bold text   → <strong>…</strong>

4. FOOTNOTES vs. ENDNOTE REFERENCES
   Footnotes have matching note text at the BOTTOM of THIS page, below a horizontal rule.
     In text:   <sup><a href="#fn[[page_num]]-N">N</a></sup>
     Note body: <aside id="fn[[page_num]]-N" class="footnote">…note text…</aside>

   Endnote references point to an "Anmerkungen" section at the back of the book —
   there is NO matching text at the bottom of this page.
     Replace with an invisible silent anchor only — NO visible number:
     <a id="Z[[page_num]]-N" class="endnote-ref"></a>

5. DOCUMENT STRUCTURE
   Headings  → <h1> / <h2> / <h3> by visual hierarchy
   Body text → <p>
   If the first paragraph continues a sentence broken at the end of the previous page,
   open that paragraph with <!-- continued -->

6. META COMMENT — place at the very end of the output
   <!-- META {"continues_next": BOOL, "new_article": BOOL, "page_type": "TYPE", "extracted_page_num": N_OR_NULL} -->

   continues_next     true  if the last sentence on this page is cut mid-sentence
   new_article        true  if this page begins a clearly new article, chapter, or section
   page_type          one of:
                        "body"       — normal body text (default)
                        "title_page" — Titelblatt / formal title page
                        "copyright"  — Impressum / publication data
                        "toc"        — Inhaltsverzeichnis at the FRONT of the book
                        "preface"    — Vorwort / Einleitung / editorial introduction
                        "endnotes"   — Anmerkungen section at the back
                        "index"      — Register / Sachregister / Namenregister
                        "blank"      — blank or near-blank page
                        "half_title" — Schmutztitel / Zwischentitel
   extracted_page_num integer arabic page number extracted from this page, or null

Output ONLY the HTML fragment. No DOCTYPE, no <html>/<body> wrapper,
no Markdown code fences, no commentary outside the HTML.
