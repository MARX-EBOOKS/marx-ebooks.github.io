Look carefully at this scanned page. Identify the running header (Kolumnentitel) at the top
and any running footer at the bottom. These are the repeated navigation lines, NOT the body text.

Typical patterns in scholarly German books (MEW volumes):
  Left page header:  author/editor name in italics
  Right page header: article or chapter title in italics
  Page number:       outer top corner, sometimes bottom center

Return JSON only — no other text:
{
  "header_desc":  "short description, e.g. 'left: author name italic; right: article title italic'",
  "footer_desc":  "short description, or empty string if no footer",
  "page_num_loc": "location of the arabic page number, e.g. 'top-right corner', 'bottom-center'"
}

If there is no visible running header, set header_desc to "".
