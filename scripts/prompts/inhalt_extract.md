Look at this scanned page. Does it contain a section headed "Inhalt",
"Inhaltsverzeichnis", "Содержание", "Contents", or a similar table-of-contents heading?

In MEW (Marx-Engels-Werke) volumes, the Inhalt appears at the VERY END of the book
and lists each article, letter, or document with its typeset arabic page number.
A typical entry looks like:
  Marx an Engels, 14. Januar 1858  .  .  .  .  .  7
  Engels an Marx, 22. Januar 1858  .  .  .  .  .  9

If this page belongs to such an Inhalt, extract every entry visible on this page.

Return JSON only — no other text:
{
  "has_inhalt": true,
  "entries": [
    {"title": "Marx an Engels, 14. Januar 1858", "page": 7},
    {"title": "Engels an Marx, 22. Januar 1858", "page": 9}
  ]
}

If there is no Inhalt on this page:
{"has_inhalt": false, "entries": []}

Rules:
  • "page" must be the arabic typeset page number from the Inhalt listing (integer).
  • Include EVERY entry visible on this page; do not summarise or truncate.
  • If a title is cut at the page edge, include the visible portion.
  • Section headings within the Inhalt (e.g. "Briefe", "Dokumente") are NOT entries —
    skip them or incorporate them into the following entry's title only if clearly part of it.
