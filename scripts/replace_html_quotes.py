#!/usr/bin/env python3
"""批量修正 HTML 文本中的低位开引号 + ASCII 闭引号。"""

import re
import shutil
from pathlib import Path


# 只需修改这里：可以填一个 .html 文件，也可以填网页目录。
HTML_PATH = Path(r"./MEW_BRIEF/32")
FILE_PATTERN = "*.html"
RECURSIVE = True
MAKE_BACKUP = True


# 整段跳过脚本、样式、代码等内容；普通标签只作为分隔符保留原文。
SKIP_RE = re.compile(
    r"<!--[\s\S]*?-->|<!\[CDATA\[[\s\S]*?\]\]>|"
    r"<(script|style|pre|code|textarea)\b[^>]*>[\s\S]*?</\1\s*>|"
    r"<[^>]*>",
    re.IGNORECASE,
)
BLOCK_RE = re.compile(
    r"^</?(?:address|article|aside|blockquote|br|dd|div|dl|dt|fieldset|figcaption|"
    r"figure|footer|form|h[1-6]|header|hr|li|main|nav|ol|p|section|table|tbody|"
    r"td|tfoot|th|thead|tr|ul)\b",
    re.IGNORECASE,
)


def fix_html(source):
    """返回 (修正后的 HTML, 双引号数, 单引号数)。"""
    output, counts = [], [0, 0]
    double_open = single_open = False
    last_text_char = ""
    cursor = 0

    # 末尾哨兵让最后一个文本片段也走同一套逻辑。
    for match in list(SKIP_RE.finditer(source)) + [None]:
        end = len(source) if match is None else match.start()
        text = source[cursor:end]
        chars = list(text)

        for i, char in enumerate(chars):
            previous = chars[i - 1] if i else last_text_char
            following = chars[i + 1] if i + 1 < len(chars) else ""

            if char == "„":
                if double_open:
                    chars[i] = "‚"
                    counts[1] += 1
                    single_open = True
                else:
                    double_open = True
            elif char == "“":
                if single_open:
                    chars[i] = "‘"
                    counts[1] += 1
                    single_open = False
                else:
                    double_open = False
            elif char == '"' and double_open:
                chars[i] = "“"
                double_open = False
                counts[0] += 1
            elif (
                char == ","
                and double_open
                and not single_open
                and following.isalnum()
                and (
                    not previous
                    or previous.isspace()
                    or previous in "„([{—–-:"
                )
            ):
                # OCR 可能把低位单开引号 ‚ 识别成逗号。
                chars[i] = "‚"
                single_open = True
                counts[1] += 1
            elif char == "‚":
                single_open = True
            elif char == "‘":
                single_open = False
            elif char == "'" and single_open:
                # 字母/数字之间的是撇号（如 don't），不把它当闭引号。
                if not (previous.isalnum() and following.isalnum()):
                    chars[i] = "‘"
                    single_open = False
                    counts[1] += 1

        if chars:
            last_text_char = chars[-1]
        output.append("".join(chars))

        if match is not None:
            token = match.group(0)
            output.append(token)
            if BLOCK_RE.match(token):
                double_open = single_open = False
                last_text_char = ""
            cursor = match.end()

    return "".join(output), counts[0], counts[1]


def process_files(paths):
    """处理文件，并返回 (扫描数, 变更文件数, 双引号数, 单引号数)。"""
    totals = [0, 0, 0, 0]
    for path in paths:
        raw = path.read_bytes()
        bom = raw.startswith(b"\xef\xbb\xbf")
        try:
            source, encoding = raw.decode("utf-8-sig"), "utf-8"
        except UnicodeDecodeError:
            source, encoding = raw.decode("gb18030"), "gb18030"

        fixed, double_count, single_count = fix_html(source)
        totals[0] += 1
        totals[2] += double_count
        totals[3] += single_count
        if fixed == source:
            continue

        totals[1] += 1
        print(f"{path}: 修正双引号 {double_count} 处，单引号 {single_count} 处")
        if MAKE_BACKUP:
            shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        data = fixed.encode(encoding)
        if encoding == "utf-8" and bom:
            data = b"\xef\xbb\xbf" + data
        path.write_bytes(data)
    return tuple(totals)


def main():
    if HTML_PATH.is_file():
        paths = [HTML_PATH]
    elif HTML_PATH.is_dir():
        paths = sorted(
            HTML_PATH.rglob(FILE_PATTERN) if RECURSIVE else HTML_PATH.glob(FILE_PATTERN)
        )
    else:
        raise FileNotFoundError(f"路径不存在，请修改脚本顶部的 HTML_PATH：{HTML_PATH}")

    scanned, changed, doubles, singles = process_files(paths)
    print(f"完成：扫描 {scanned} 个文件，修改 {changed} 个；双引号 {doubles} 处，单引号 {singles} 处。")


if __name__ == "__main__":
    main()
