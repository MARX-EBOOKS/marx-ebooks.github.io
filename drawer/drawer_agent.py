from __future__ import annotations
import json
import re
import signal
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Optional
import httpx
from bs4 import BeautifulSoup
from agent_config import Config
"""
确保httpx、bs4均已安装
命令示例
pip install bs4
pip install httpx
"""
# ══════════════════════════════════════════════════════════════════════════════
# ChatClient — independent LLM wrapper (httpx)
# ══════════════════════════════════════════════════════════════════════════════
class ChatClient:
    def __init__(self, cfg: Config, interrupt_flag: threading.Event):
        self._cfg       = cfg
        self._interrupt = interrupt_flag
        self._sem       = threading.Semaphore(cfg.MAX_CONCURRENT)
        self._timeout   = cfg.TIMEOUT
        self._headers   = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {cfg.API_KEY}",
        }

    def chat(self, messages: list, tools: Optional[list] = None,
             think: bool = True) -> dict:
        payload = {
            "model":              self._cfg.MODEL,
            "messages":           messages,
            "temperature":        self._cfg.TEMPERATURE,
            "top_p":              self._cfg.TOP_P,
            "max_tokens":         self._cfg.MAX_TOKENS,
            "stream":             False,
            "repetition_penalty": 1.0,
            "presence_penalty":   1.5,
            "extra_body": {"TOP_K": 20, "enable_thinking": think},
        }
        if tools:
            payload["tools"] = tools
        resp = self._request_with_retry(payload)
        resp.raise_for_status()
        data  = resp.json()
        usage = data.get("usage")
        if usage:
            print(f"Token 使用：输入={usage['prompt_tokens']}，"
                  f"输出={usage['completion_tokens']}，"
                  f"总计={usage['total_tokens']}")
        msg     = data["choices"][0]["message"]
        thinking = msg.get("reasoning_content", "").strip()
        if not thinking and msg.get("content"):
            m = re.search(r"<think>(.*?)</think>", msg["content"], re.DOTALL)
            if m:
                thinking = m.group(1).strip()
                msg["content"] = re.sub(
                    r"<think>.*?</think>\s*", "", msg["content"], flags=re.DOTALL
                ).strip()
        if thinking:
            msg["_thinking"] = thinking
        return msg

    def _request_with_retry(self, payload: dict):
        attempt = 0
        while True:
            resp = self._do_request(payload)
            if resp.status_code < 400:
                return resp
            if attempt < self._cfg.MAX_RETRIES - 1:
                wait = self._cfg.RETRY_WAIT
                print(f"\n[API {resp.status_code}: {resp.text[:300]}, "
                      f"retry {attempt+1}, wait {wait}s…]")
                self._sleep_interruptible(wait)
                attempt += 1
            else:
                print(f"[API error {resp.status_code}: {resp.text[:300]}, "
                      f"failed after {attempt+1} attempt(s)]")
                self._pause_on_error()
                attempt = 0

    def _do_request(self, payload: dict):
        result: list = [None]
        error:  list = [None]
        self._sem.acquire()
        try:
            def _worker():
                try:
                    # 使用 httpx.Client + with 语句管理连接和超时
                    with httpx.Client(timeout=self._timeout) as client:
                        result[0] = client.post(
                            self._cfg.API_URL,
                            json=payload,
                            headers=self._headers,
                        )
                except Exception as exc:
                    error[0] = exc

            t = threading.Thread(target=_worker, daemon=True)
            t.start()
            while t.is_alive():
                t.join(timeout=0.1)
                if self._interrupt.is_set():
                    self._interrupt.clear()
                    raise KeyboardInterrupt
            if error[0]:
                raise error[0]
            return result[0]
        finally:
            self._sem.release()

    def _sleep_interruptible(self, seconds: float):
        for _ in range(int(seconds * 10)):
            time.sleep(0.1)
            if self._interrupt.is_set():
                self._interrupt.clear()
                raise KeyboardInterrupt

    def _pause_on_error(self):
        print("\n" + "─"*50 + "\n[程序已暂停]\n" + "─"*50)
        try:
            if input("按任意键重试 / q 退出：").strip().lower() == "q":
                raise KeyboardInterrupt
        except (EOFError, KeyboardInterrupt):
            raise KeyboardInterrupt
# ══════════════════════════════════════════════════════════════════════════════
# Control-flow signals  (replaces bare-string sentinels)
# ══════════════════════════════════════════════════════════════════════════════
class AgentSignal(Enum):
    ANSWER   = auto()   # normal answer produced
    NEW_CONV = auto()   # discard history, start fresh
    PAUSE    = auto()   # user typed "p" after interrupt

@dataclass
class AgentResult:
    signal:  AgentSignal
    answer:  Optional[str] = None
    history: list          = field(default_factory=list)
# ══════════════════════════════════════════════════════════════════════════════
# SearchTools — grep_files, book_index
# ══════════════════════════════════════════════════════════════════════════════
class SearchTools:
    def __init__(self, cfg: Config):
        self._cfg  = cfg
        self._root = Path(cfg.HTML_FOLDER)

    def grep_files(
        self, keyword: str, subdir: str = "",
        max_hits: int = None, is_regex: bool = False,
        count_only: bool = False, page: int = 0, page_size: int = 600,
        CONTEXT_CHARS_COARSE: int = 100,
    ) -> str:
        if max_hits is None:
            max_hits = self._cfg.MAX_HITS
        ok, err = self._check_lang(keyword, subdir)
        if not ok:
            return err
        if CONTEXT_CHARS_COARSE > 250:
            return "上下文字符数长于 250，请缩小范围。"
        file_iter, single_file, err_str = self._resolve_iter(subdir)
        if err_str:
            return err_str
        try:
            pattern = re.compile(
                keyword if is_regex else re.escape(keyword), re.IGNORECASE
            )
        except re.error as exc:
            return (f"正则语法错误：{exc}\n"
                    "常用：(?:A|B)（或）、(?=.*A)(?=.*B)（同段同时含）")
        effective_max = float("inf") if (subdir and not single_file) else max_hits
        all_hits = self._collect(file_iter, pattern, effective_max,
                                 count_only, CONTEXT_CHARS_COARSE)
        total = len(all_hits)
        scope = f"（范围：{subdir}）" if subdir else ""
        if total == 0:
            return f"{'「'+subdir+'」内' if subdir else '全库'}未找到「{keyword}」。"
        if count_only:
            lines = [
                f"命中 {total} 个文件{scope}，关键词「{keyword}」",
                f"（按页取结果：page_size={page_size}，共 {-(-total//page_size)} 页）",
                "",
            ]
            lines += [f"  {r}" + (f"  | {t}" if t else "") for r, t, _ in all_hits]
            return "\n".join(lines)
        page_size   = max(1, page_size)
        total_pages = -(-total // page_size)
        page        = max(0, min(page, total_pages - 1))
        sliced      = all_hits[page*page_size:(page+1)*page_size]
        header      = (f"共 {total} 处命中{scope}，"
                       f"第 {page+1}/{total_pages} 页，每页 {page_size} 条\n")
        parts = [
            f"[文件：{r}" + (f" | 标题：{t}" if t else "") + "]\n" + s
            for r, t, s in sliced
        ]
        return header + "\n---\n".join(parts)

    def book_index(self, subdir: str) -> str:
        if subdir in self._cfg.SPECIAL_DIRS:
            attr, fname = self._cfg.SPECIAL_DIRS[subdir]
            return (self._cfg.prefix_for(attr)
                    + f"[DIRECTORY: {subdir}]\n[Discard after locating target files, keep only needed paths in your reply.]\n]"
                    + self._cfg.dir_text(fname)+"\n[Discard after locating target files, keep only needed paths in your reply.]")
        norm = subdir.replace("\\", "/").strip("/")
        if (norm.startswith("en/MECW/")
                and not norm.endswith(".html")
                and norm != "en/MECW"):
            return ("DIRECTORY ERROR: No sub-folders in en/MECW/. "
                    "Open en/MECW/MECWxx-index.html directly.")
        html_file = self._find_index(norm)
        if html_file is None:
            return f"No index page found in {subdir}."
        try:
            soup  = BeautifulSoup(
                html_file.read_text(encoding="utf-8-sig", errors="ignore"),
                "html.parser",
            )
            lines = [
                f"{a['href']}  {a.get_text(strip=True)}"
                for a in soup.find_all("a", href=True)
                if a.get_text(strip=True)
                and not a["href"].startswith(("http://", "https://", "mailto:"))
            ]
            return (f"[Contents: {subdir}  Total: {len(lines)}]"+"\n[Discard after locating target files, keep only needed paths in your reply.]\n"
                    + "\n".join(lines)+"\n[Discard after locating target files, keep only needed paths in your reply.]") if lines else soup.get_text(separator="\n")[:3000]+"\n[Discard after locating target files, keep only needed paths in your reply.]"
        except Exception as exc:
            return f"读取失败：{exc}"

    def _resolve_iter(self, subdir: str):
        if not subdir:
            return self._root.rglob("*.html"), False, ""
        norm = subdir.replace("\\", "/").strip("/")
        p    = self._root / Path(norm)
        if norm.endswith(".html") and p.is_file():
            return [p], True, ""
        if norm.startswith("en/MECW/") and not norm.endswith(".html") and norm != "en/MECW":
            return None, False, "路径错误：en/MECW/ 下无子目录，subdir 只能填 en/MECW/。"
        if not p.exists():
            return None, False, f"路径不存在：{subdir}"
        return p.rglob("*.html"), False, ""

    def _collect(self, file_iter, pattern, effective_max,
                 count_only: bool, ctx: int) -> list:
        hits, collected = [], 0
        for html_file in file_iter:
            if collected >= effective_max:
                break
            try:
                text = BeautifulSoup(
                    html_file.read_text(encoding="utf-8-sig", errors="ignore"),
                    "html.parser",
                ).get_text(separator="\n")
            except Exception:
                continue
            m = pattern.search(text)
            if not m:
                continue
            title = self._extract_title(html_file)
            rel   = str(html_file.relative_to(self._root))
            if count_only:
                hits.append((rel, title, None))
            else:
                start = max(0, m.start() - ctx // 2)
                end   = min(len(text), m.end() + ctx // 2)
                hits.append((rel, title, text[start:end].strip()))
            collected += 1
        return hits

    def _find_index(self, norm: str) -> Optional[Path]:
        base = self._root / Path(norm)
        vol  = base.name
        candidates = (
            [f"MECW{vol}-index.html", "index.html", "nav.html"]
            if (vol.isdigit() or vol.startswith("MECW"))
            else ["index.html", "nav.html"]
        )
        for name in candidates:
            p = base / name
            if p.exists():
                return p
        direct = self._root / Path(norm)
        return direct if direct.is_file() else None

    @staticmethod
    def _extract_title(html_path: Path) -> str:
        try:
            soup = BeautifulSoup(
                html_path.read_text(encoding="utf-8-sig"), "html.parser"
            )
            for attr in [("name", "title"), ("property", "og:title")]:
                tag = soup.find("meta", attrs={attr[0]: attr[1]})
                if tag and tag.get("content", "").strip():
                    return tag["content"].strip()
            if soup.title and soup.title.string:
                return soup.title.string.strip()
            for sel in ["h1", "h2"]:
                tag = soup.find(sel)
                if tag and tag.get_text(strip=True):
                    return tag.get_text(strip=True)
        except Exception:
            pass
        return ""

    @staticmethod
    def _detect_script(text: str) -> dict:
        r = {"zh": False, "latin": False, "cyrillic": False}
        for c in text:
            if '\u4e00' <= c <= '\u9fff':
                r["zh"] = True
            elif c.isascii() and c.isalpha():
                r["latin"] = True
            elif '\u0400' <= c <= '\u052F':
                r["cyrillic"] = True
        return r

    def _check_lang(self, keyword: str, subdir: str) -> tuple[bool, str]:
        if not subdir:
            return True, ""
        norm = subdir.replace("\\", "/").strip("/")
        d    = self._detect_script(keyword)
        cfg  = self._cfg
        if any(norm.startswith(x) for x in cfg.ZH_DIRS):
            if d["latin"] or d["cyrillic"]:
                return False, (f"语言不匹配：目录「{subdir}」是中文文献，"
                               f"但关键词「{keyword}」包含外文。请用中文关键词。")
        if any(norm.startswith(x) for x in cfg.DE_DIRS):
            if d["zh"]:
                return False, (f"语言不匹配：目录「{subdir}」是德文文献，"
                               f"但关键词「{keyword}」包含中文。请用德文关键词。")
        if any(norm.startswith(x) for x in cfg.EN_DIRS):
            if d["zh"]:
                return False, (f"语言不匹配：目录「{subdir}」是英文文献，"
                               f"但关键词「{keyword}」包含中文。请用英文关键词。")
        if any(norm.startswith(x) for x in cfg.RU_DIRS):
            if d["zh"]:
                return False, (f"语言不匹配：目录「{subdir}」是俄文文献，"
                               f"但关键词「{keyword}」包含中文。请用俄文关键词。")
        return True, ""

# ══════════════════════════════════════════════════════════════════════════════
# ReadingTools — read_file_html, read_file_links, read_file_raw
# ══════════════════════════════════════════════════════════════════════════════
class ReadingTools:
    def __init__(self, cfg: Config):
        self._root = Path(cfg.HTML_FOLDER)
        self.MAX_TOOL_RESULT_CHARS=cfg.MAX_TOOL_RESULT_CHARS

    def read_file_html(self, rel_path: str,
                       max_chars: int = 30000, offset: int = 0) -> str:
        p = self._resolve(rel_path)
        if p is None:
            return f"文件不存在：{rel_path}"
        try:
            soup = BeautifulSoup(
                p.read_text(encoding="utf-8-sig", errors="ignore"), "html.parser"
            )
            for tag in soup(["script", "style", "nav", "header", "footer"]):
                tag.decompose()
            body      = soup.find("body") or soup
            html_text = re.sub(r"\n{3,}", "\n", str(body)).strip()
        except Exception as exc:
            return f"读取失败：{exc}"
        total     = len(html_text)
        chunk     = html_text[offset:offset + max_chars]
        remaining = max(0, total - offset - max_chars)
        title     = SearchTools._extract_title(p)
        header    = (f"[文件：{rel_path}" + (f" | 标题：{title}" if title else "") + "]\n"
                     f"[字符 {offset}~{offset+len(chunk)} / 共 {total}")
        if remaining > 0:
            header += f"，剩余 {remaining} 字符，读后续部分请将offset设为{offset+max_chars}"+" 阅读时如发现关键语句务必及时调用add_quote记录，"+f"阅读后请将此处文本压缩至{self.MAX_TOOL_RESULT_CHARS}字符以下"
        return header + "]\n" + chunk+"\n"+f"[阅读后请将此处文本压缩至{self.MAX_TOOL_RESULT_CHARS}字符以下，如有关键语句务必调用add_quote记录]"

    def read_file_links(self, rel_path: str, anchors_only: bool = False) -> str:
        p = self._resolve(rel_path)
        if p is None:
            return f"文件不存在：{rel_path}"
        try:
            soup = BeautifulSoup(
                p.read_text(encoding="utf-8-sig", errors="ignore"), "html.parser"
            )
        except Exception as exc:
            return f"读取失败：{exc}"
        anchors, local_links, seen = [], [], set()
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            text = a.get_text(strip=True)
            if not href or href in seen:
                continue
            seen.add(href)
            if href.startswith("#"):
                anchors.append(f"{href}  {text}")
            elif not href.startswith(("http://", "https://", "mailto:", "javascript:")):
                if href.endswith((".html", ".htm")) or "/" in href:
                    local_links.append(f"{href}  {text}")
        heading_anchors = []
        for tag in soup.find_all(["h1","h2","h3","h4","h5","h6"], id=True):
            aid = "#" + tag["id"]
            if aid not in seen:
                heading_anchors.append(
                    f"{aid}  [{tag.name}] {tag.get_text(strip=True)}"
                )
        lines = [f"[链接结构：{rel_path}]"]
        if anchors or heading_anchors:
            lines.append(f"\n── 页内锚点（{len(anchors)+len(heading_anchors)} 个）──")
            lines.extend(anchors)
            if heading_anchors:
                lines.append("  # 带 id 的标题")
                lines.extend(heading_anchors)
        if not anchors_only and local_links:
            lines.append(f"\n── 本地文件链接（{len(local_links)} 个）──")
            lines.extend(local_links)
        return "\n".join(lines) if len(lines) > 1 else f"{rel_path} 中未找到链接。"

    def read_file_raw(self, rel_path: str) -> str:
        p = self._resolve(rel_path)
        if p is None:
            return f"文件不存在：{rel_path}"
        return p.read_text(encoding="utf-8-sig", errors="ignore")

    def _resolve(self, rel_path: str) -> Optional[Path]:
        p = self._root / Path(rel_path.replace("\\", "/"))
        return p if p.is_file() else None

# ══════════════════════════════════════════════════════════════════════════════
# TranslationTools — translate_file, translate_snippet
# ══════════════════════════════════════════════════════════════════════════════
class TranslationTools:
    def __init__(self, cfg: Config, chat_client: ChatClient,
                 reading: ReadingTools):
        self._cfg     = cfg
        self._client  = chat_client
        self._reading = reading

    def translate_file(self, rel_path: str, source_lang: str,
                       target_lang: str = "zh", keep_html: bool = True) -> str:
        html = self._reading.read_file_raw(rel_path)
        if html.startswith("文件不存在"):
            return html
        chunks = self._split_chunks(html) if keep_html else [html]
        print(f"\n[翻译] {rel_path}  共 {len(chunks)} 块  {source_lang}→{target_lang}")
        results = []
        for i, chunk in enumerate(chunks, 1):
            print(f"  [翻译] 第 {i}/{len(chunks)} 块 ({len(chunk)} 字符)…")
            results.append(self._translate(chunk, source_lang, target_lang, keep_html))
        return "\n".join(results)

    def translate_snippet(self, content: str, source_lang: str,
                          target_lang: str = "zh", keep_html: bool = False) -> str:
        print(f"\n[翻译片段] {len(content)} 字符  {source_lang}→{target_lang}")
        return self._translate(content, source_lang, target_lang, keep_html)

    def _translate(self, content: str, source_lang: str,
                   target_lang: str, keep_html: bool) -> str:
        src  = self._cfg.LANG_NAMES.get(source_lang, source_lang)
        tgt  = self._cfg.LANG_NAMES.get(target_lang, target_lang)
        tmpl = self._cfg.trans_prompt_html if keep_html else self._cfg.trans_prompt_text
        msg  = self._client.chat(
            [{"role": "user",
              "content": tmpl.format(
                  source_lang=src, target_lang=tgt, content=content)}],
            tools=None, think=False,
        )
        return msg.get("content", "").strip()

    def _split_chunks(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        body = soup.find("body") or soup
        chunks, current, current_len = [], [], 0
        for child in body.children:
            s = str(child)
            if current_len + len(s) > self._cfg.TRANS_CHUNK_CHARS and current:
                chunks.append("".join(current))
                current, current_len = [], 0
            current.append(s)
            current_len += len(s)
        if current:
            chunks.append("".join(current))
        return chunks or [html]

# ══════════════════════════════════════════════════════════════════════════════
# ToolHandler — TOOLS schema, dispatch table, session quotes
# ══════════════════════════════════════════════════════════════════════════════
class ToolHandler:
    TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "grep_files",
                "description": (
                    "Broad keyword search across the whole library or a subdirectory. "
                    "Returns the first matching context snippet from each hit file.\n"
                    "【Two-step workflow to prevent oversized results】\n"
                    "1. Call with count_only=true → get hit count + file list.\n"
                    "2a. Hits ≤ page_size → call normally (count_only=false).\n"
                    "2b. Hits > page_size → page through (page=0,1,…) or pick key files "
                    "    and read them with read_file_html.\n"
                    "When subdir points to a directory the full directory is scanned "
                    "(max_hits cap is ignored)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": (
                                "Search keyword; language must match the files in subdir. "
                                "German/English/Russian for those corpora; Chinese is forbidden "
                                "unless the user explicitly permits it.\n"
                                "For multiple terms use a regex and set is_regex=true.\n"
                                "Regex: (?:A|B)=A or B; (?=.*A)(?=.*B)=both in paragraph; "
                                "A.{0,50}B=within 50 chars."
                            ),
                        },
                        "subdir":               {"type": "string",  "default": ""},
                        "max_hits":             {"type": "integer", "default": 20},
                        "is_regex":             {"type": "boolean", "default": False},
                        "count_only":           {"type": "boolean", "default": False},
                        "page":                 {"type": "integer", "default": 0},
                        "page_size":            {"type": "integer", "default": 600},
                        "CONTEXT_CHARS_COARSE": {"type": "integer", "default": 150},
                    },
                    "required": ["keyword"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "book_index",
                "description": (
                    "Reads a table-of-contents page and returns the chapter list with file names. "
                    "Use when you know the work or volume but not the specific chapter."
                    "Discard after locating target files, keep only needed paths in your reply."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "subdir": {
                            "type": "string",
                            "description": "Directory or index file path relative to library root.",
                        },
                    },
                    "required": ["subdir"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_file_html",
                "description": (
                "Reads the tagged body of an HTML file for close reading and excerpting.\n"
                "Semantic tags preserved: blockquote = quotation, table = table, "
                "sup = footnote reference, li = list item, h1–h6 = heading levels.\n"
                "Noise tags stripped: script, style, nav, header, footer.\n"
                "Once you have located a file, prefer this tool over further grep searches for details.\n"
                "Use the offset parameter to read long files in chunks."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "rel_path":  {"type": "string","description":"Relative file path (as returned by grep_files or book_index)."},
                        "max_chars": {"type": "integer","description":"Maximum characters to read per chunk. Default is 30 000. Increase for denser files, decrease to read by shorter context.", "default": 30000},
                        "offset":    {"type": "integer","description": "Starting character position. Use 0 for the first chunk. To read the next page, set offset = previous_offset + max_chars. Increment repeatedly to page through the entire file.","default": 0},
                    },
                    "required": ["rel_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_file_links",
                "description": ( "Reads the links in a file: in-page anchors (#id, for navigating within the page) "
                "and local file links (navigation to related articles)." ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "rel_path":     {"type": "string","description": "Relative file path."},
                        "anchors_only": {"type": "boolean","description": "When true, returns only in-page anchors. When false (default), returns both anchor types.", "default": False},
                    },
                    "required": ["rel_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "add_quote",
                "description": (
                    "Records a key original-text sentence into the session excerpt list. "
                    "Call immediately when read_file_html returns a sentence directly relevant "
                    "to the user's question especially when the file only has only a few sentences user needed. "
                    "Also call immediately to preserve important search results when they are too long. "
                    "Preserve source language — do not translate."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text":   {"type": "string","description": "The original sentence or results (preserved in its source language).",},
                        "source": {"type": "string","description": "Relative file path of the source.",},
                        "note":   {"type": "string","description": "Optional note explaining how this sentence relates to the user's question.", "default": ""},
                    },
                    "required": ["text", "source"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "translate_file",
                "description": (
                    "Translates a specified HTML file in the library. "
                    "Obtain rel_path via grep_files or book_index first."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "rel_path":    {"type": "string"},
                        "source_lang": {"type": "string",
                                        "description": "de / en / ru / fr / zh"},
                        "target_lang": {"type": "string", "default": "zh"},
                        "keep_html":   {"type": "boolean", "default": True},
                    },
                    "required": ["rel_path", "source_lang"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "translate_snippet",
                "description": (
                    "Translates a snippet of HTML or plain text. "
                    "Suitable for context snippets from grep_files or user-pasted passages."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content":     {"type": "string"},
                        "source_lang": {"type": "string"},
                        "target_lang": {"type": "string", "default": "zh"},
                        "keep_html":   {"type": "boolean", "default": False},
                    },
                    "required": ["content", "source_lang"],
                },
            },
        },
    ]

    def __init__(self, search: SearchTools, reading: ReadingTools,
                 translation: TranslationTools):
        self.session_quotes: list[dict] = []
        self._dispatch = {
            "grep_files":        search.grep_files,
            "book_index":        search.book_index,
            "read_file_html":    reading.read_file_html,
            "read_file_links":   reading.read_file_links,
            "add_quote":         self._add_quote,
            "translate_file":    translation.translate_file,
            "translate_snippet": translation.translate_snippet,
        }

    def call(self, fn_name: str, fn_args: dict) -> str:
        fn = self._dispatch.get(fn_name)
        return str(fn(**fn_args)) if fn else f"未知工具：{fn_name}"

    def clear_quotes(self):
        self.session_quotes.clear()

    def _add_quote(self, text: str, source: str, note: str = "") -> str:
        self.session_quotes.append({"text": text, "source": source, "note": note})
        idx     = len(self.session_quotes)
        preview = text[:120] + ("…" if len(text) > 120 else "")
        return f"[摘录 #{idx} 已记录]\n来源：{source}\n内容：{preview}"

# ══════════════════════════════════════════════════════════════════════════════
# Agent — agentic loop
# ══════════════════════════════════════════════════════════════════════════════
class Agent:
    def __init__(self, cfg: Config, chat_client: ChatClient,
                 tool_handler: ToolHandler):
        self._cfg    = cfg
        self._client = chat_client
        self._tools  = tool_handler
        self._interrupt = chat_client._interrupt  # 获取 interrupt 引用

    def run(self, user_input: str, history: list,
            show_tools: bool, show_think: bool, deep_read: bool) -> AgentResult:
        system = self._cfg.system_prompt
        if deep_read:
            system += "\n" + self._cfg.mode_deep_read
        if not history:
            system += ("\n## 重要著作速查\n"
                       + self._cfg.important_works_me + "\n"
                       + self._cfg.important_works_vl)
        pre_query_history = list(history)
        messages = [
            {"role": "system", "content": system},
            *history,
            {"role": "user",   "content": user_input},
        ]
        while True:

            try:
                msg = self._client.chat(messages, self._tools.TOOLS, think=show_think)
            except KeyboardInterrupt:
                self._interrupt.clear()  # 清除标志，避免重复触发
                result = self._wait_for_followup(messages, pre_query_history)
                if result is not None:
                    return result
                continue
            self._print_thinking(msg, show_think)
            messages.append({k: v for k, v in msg.items() if k != "_thinking"})
            if not msg.get("tool_calls"):
                answer      = msg.get("content", "").strip()
                new_history = [m for m in messages if m.get("role") != "system"]
                return AgentResult(AgentSignal.ANSWER, answer=answer, history=new_history)
            interrupted = False
            for tc in msg["tool_calls"]:
                fn_name = tc["function"]["name"]
                fn_args = json.loads(tc["function"]["arguments"])
                if show_tools:
                    print(f"\n[工具] {fn_name}({fn_args})")
                try:
                    result_str = self._tools.call(fn_name, fn_args)
                except KeyboardInterrupt:
                    self._interrupt.clear()  # 清除标志
                    idx = msg["tool_calls"].index(tc)
                    for rtc in msg["tool_calls"][idx:]:
                        messages.append({
                            "role": "tool", "tool_call_id": rtc["id"],
                            "content": "[STOPPED ABRUPTLY]",
                        })
                    interrupted = True
                    break
                if fn_name not in [r"translate_file",r"translate_snippet"]:
                    result_str = self._cap_tool_result(result_str)
                if show_tools:
                    print(f"  [结果] {result_str[:300]}"
                          f"{'…' if len(result_str) > 300 else ''}")
                messages.append({
                    "role": "tool", "tool_call_id": tc["id"],
                    "content": result_str,
                })
            if interrupted:
                self._interrupt.clear() 
                result = self._wait_for_followup(messages, pre_query_history)
                if result is not None:
                    return result
                continue



    @staticmethod
    def _pause_menu(context_note: str = "") -> str:
        if context_note:
            print(context_note)
        print(
            "  选项：\n"
            "    <问题>  精简上下文单次作答（不使用工具）\n"
            "    c       继续/重新发送当前请求\n"
            "    回车    输入补充问题后继续\n"
            "    p       保留记录返回主菜单\n"
            "    r       撤销本次输入，返回主菜单\n"
            "    n       清空记录，开始新对话"
        )
        try:
            return input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            return "p"
    def _single_trimmed_request(self, messages: list, question: str):
        """Send one tool-free question with a half-size trimmed context."""
        trimmed = self._trim_messages(messages, self._cfg.MAX_CONTEXT_CHARS // 2)
        trimmed.append({"role": "user", "content": question})
        print(f"  [精简上下文：{self._total_chars(trimmed)} 字符，无工具，发送中…]")
        try:
            single = self._client.chat(trimmed, tools=None, think=False)
            print(f"\n{single.get('content', '').strip()}\n")
        except Exception as exc:
            print(f"  [单次请求失败：{exc}]")

    def _wait_for_followup(self, messages: list,
                           pre_query_history: list) -> Optional[AgentResult]:
        while True:
            reply = self._pause_menu("[已中断]")
            new_history = [m for m in messages if m.get("role") != "system"]
            if reply.lower() == "c":
                return None

            if reply.lower() == "p":
                self._interrupt.clear()
                return AgentResult(AgentSignal.PAUSE, history=new_history)

            if reply.lower() == "n":
                print("[原记录已清空，新对话开始]\n")
                return AgentResult(AgentSignal.NEW_CONV)

            if reply.lower() == "r":
                last_user = next(
                    (i for i in range(len(messages) - 1, -1, -1)
                     if messages[i].get("role") == "user"),
                    None,
                )
                if last_user is None:
                    print("  [无可撤销的输入]\n")
                    continue
                revoked       = messages[last_user].get("content", "")[:40]
                clean_history = [m for m in messages[:last_user]
                                 if m.get("role") != "system"]
                print(f"  [已撤销本次输入：{revoked}…  请重新输入]\n")
                return AgentResult(AgentSignal.PAUSE, history=clean_history)
            if reply:
                messages.append({"role": "user", "content": reply})
                print("  [继续处理补充问题…]")
                return None
            # 直接回车时提示输入补充问题
            if not reply:
                print("  [请输入补充问题，或输入 p 暂停返回主菜单]")
                try:
                    supplement = input("  补充 > ").strip()
                    if supplement.lower() == "p":
                        self._interrupt.clear()
                        return AgentResult(AgentSignal.PAUSE, history=new_history)
                    if supplement:
                        messages.append({"role": "user", "content": supplement})
                        print("  [继续处理补充问题…]")
                        return None   
                except (EOFError, KeyboardInterrupt):
                    self._interrupt.clear()
                    return AgentResult(AgentSignal.PAUSE, history=new_history)
                continue         

    def _cap_tool_result(self, text: str) -> str:
        limit =self._cfg.MAX_TOOL_RESULT_CHARS
        if len(text) > limit:
            return (text
                    + f"\n[Search result too long, already exceed {limit} chars, "
                    "please sort out the results needed for answering user's question! And also using add_quote to record if you find key contexts!]")
        return text

    @staticmethod
    def _total_chars(messages: list) -> int:
        return sum(len(str(m.get("content", ""))) for m in messages)

    def _trim_messages(self, messages: list, char_limit: int) -> list:
        system     = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]
        kept, chars = [], 0
        for m in reversed(non_system):
            c = len(str(m.get("content", "")))
            if chars + c > char_limit:
                break
            kept.append(m)
            chars += c
        return system + list(reversed(kept))

    @staticmethod
    def _print_thinking(msg: dict, show_think: bool):
        if not show_think or not msg.get("_thinking"):
            return
        text = msg["_thinking"]
        if len(text) > 1500:
            text = text[:1500] + f"\n… （共 {len(msg['_thinking'])} 字符，已截断）"
        print(f"\n  ┌─[思考]{'─'*50}")
        for line in text.splitlines():
            print(f"  │ {line}")
        print(f"  └{'─'*52}")

# ══════════════════════════════════════════════════════════════════════════════
# save_history
# ══════════════════════════════════════════════════════════════════════════════
def save_history(history: list, quotes: list,
                 show_tools: bool, output_dir: str) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    lines = []
    for m in history:
        role    = m.get("role")
        content = m.get("content", "").strip()
        if role == "user" and content:
            lines.append(f"## 问\n{content}\n")
        elif role == "assistant":
            if m.get("_thinking"):
                lines.append(f"### 思考\n```\n{m['_thinking'].strip()}\n```\n")
            if m.get("tool_calls") and show_tools:
                lines.append("### 工具调用\n")
                for tc in m["tool_calls"]:
                    fn   = tc.get("function", {})
                    args = json.dumps(
                        json.loads(fn.get("arguments", "{}")),
                        ensure_ascii=False, indent=2,
                    )
                    lines.append(f"**{fn.get('name','?')}**:\n```json\n{args}\n```\n")
            if content:
                lines.append(f"## 答\n{content}\n")
        elif role == "tool" and show_tools:
            tid     = m.get("tool_call_id", "")
            snippet = content[:2000] + ("\n…（已截断）" if len(content) > 2000 else "")
            lines.append(f"### 工具结果 `{tid}`\n```\n{snippet}\n```\n")
    if quotes:
        lines.append("\n---\n## 本轮摘录\n")
        for i, q in enumerate(quotes, 1):
            note = f"（{q['note']}）" if q.get("note") else ""
            lines.append(f"**#{i}** 来源：`{q['source']}`{note}\n> {q['text']}\n")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path

# ══════════════════════════════════════════════════════════════════════════════
# AppController
# ══════════════════════════════════════════════════════════════════════════════
class AppController:
    def __init__(self, cfg: Config, interrupt: threading.Event,
                 tool_handler: ToolHandler, agent: Agent):
        self._cfg          = cfg
        self._interrupt    = interrupt
        self._tool_handler = tool_handler
        self._agent        = agent
        self.show_tools = cfg.DISPLAY_TOOLS
        self.show_think = cfg.ENABLE_THINKING
        self.deep_read  = cfg.DEEP_READ
        self.history:   list = []

    def run(self):
        self._register_sigint()
        
        try:
            while True:
                self._print_banner()
                user_input = self._read_input()
                if user_input is None:
                    break
                if user_input.lower() == "q":
                    break
                if not self._dispatch_cmd(user_input):
                    self._run_agent(user_input)
        finally:
            self._autosave()

    def _register_sigint(self):
        def _handler(sig, frame):
            if self._interrupt.is_set():
                self._interrupt.clear()  # 清除标志，避免重复触发
                raise KeyboardInterrupt
            self._interrupt.set()
        signal.signal(signal.SIGINT, _handler)

    def _read_input(self) -> Optional[str]:
        try:
            return input("请输入问题：").strip()
        except EOFError:
            return None
        except KeyboardInterrupt:
            self._interrupt.clear()
            print()
            try:
                confirm = input("确认退出？(y/Enter=退出，其他键继续)：").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return None
            return None if confirm in ("", "y", "yes") else ""

    def _dispatch_cmd(self, user_input: str) -> bool:
        if not user_input:
            return True
        cmd = user_input.lower()
        handlers = {
            "s": self._cmd_save,
            "n": self._cmd_new,
            "e": self._cmd_undo,
        }
        if cmd in handlers:
            handlers[cmd]()
            return True
        if cmd == "t":
            self.show_tools = not self.show_tools
            print(f"[当前模式：{self._status()}]\n")
            return True
        if cmd == "d":
            self.show_think = not self.show_think
            print(f"[当前模式：{self._status()}（需模型支持）]\n")
            return True
        if cmd == "r":
            self.deep_read = not self.deep_read
            print(f"[当前模式：{self._status()}]\n")
            return True
        return False
    

    def _run_agent(self, user_input: str):
        result = self._agent.run(
            user_input, self.history,
            show_tools=self.show_tools,
            show_think=self.show_think,
            deep_read=self.deep_read,
        )
        if result.signal == AgentSignal.NEW_CONV:
            self._tool_handler.clear_quotes()
            self.history = []
            return
        # Both PAUSE (revoke) and ANSWER update history
        self.history = result.history
        if result.signal == AgentSignal.PAUSE:
            print("[已暂停，待重新发送指令]\n")
            return                          # 返回主菜单，history 已恢复
        # ANSWER
        if result.answer:
            print(result.answer)
        if self._tool_handler.session_quotes:
            print(f"\n[本轮摘录 {len(self._tool_handler.session_quotes)} 条，"
                  f"输入 s 保存并开始新对话]")
        print("\n" + "─"*55 + "\n")

    def _status(self) -> str:
        flags = [n for n, v in [("工具显示", self.show_tools),
                                ("思考模式", self.show_think),
                                ("深度阅读", self.deep_read)] if v]
        return "、".join(flags) if flags else "全关"

    def _cmd_save(self):
        if self.history:
            p = save_history(self.history, self._tool_handler.session_quotes,
                             self.show_tools, self._cfg.HISTORY_OUTPUT_PATH)
            print(f"[已保存至 {p}]")
            self._tool_handler.clear_quotes()
            self.history = []
            print("[原记录已清空，新对话开始]\n")

    def _cmd_new(self):
        self._tool_handler.clear_quotes()
        self.history = []
        print("[原记录已清空，新对话开始]\n")

    def _cmd_undo(self):
        last_user = next(
            (i for i in range(len(self.history)-1, -1, -1)
             if self.history[i].get("role") == "user"),
            None,
        )
        if last_user is None:
            print("[记录为空，无可撤销的内容]\n")
        else:
            q_text       = self.history[last_user].get("content", "")[:60]
            self.history = self.history[:last_user]
            print(f"[已撤销最后一轮问答：{q_text}…]\n请重新输入：")

    def _autosave(self):
        if self.history:
            try:
                p = save_history(self.history, self._tool_handler.session_quotes,
                                 self.show_tools, self._cfg.HISTORY_OUTPUT_PATH)
                print(f"\n[退出前已自动保存至 {p}]")
            except Exception as exc:
                print(f"\n[自动保存失败：{exc}]")
        print("[再见]")

    def _print_banner(self):
        print(f"文献查询系统已就绪  文件夹：{self._cfg.HTML_FOLDER}")
        print("  t 工具显示  d 思考模式  r 深度阅读  n 新对话  s 保存 + 新对话  e 撤销  q 退出")
        print("  Ctrl+C 中止当前查询（再按一次强制退出）\n")

# ══════════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════════
def main():
    cfg          = Config()
    interrupt    = threading.Event()
    chat_client  = ChatClient(cfg, interrupt)
    search       = SearchTools(cfg)
    reading      = ReadingTools(cfg)
    translation  = TranslationTools(cfg, chat_client, reading)
    tool_handler = ToolHandler(search, reading, translation)
    agent        = Agent(cfg, chat_client, tool_handler)
    AppController(cfg, interrupt, tool_handler, agent).run()

if __name__ == "__main__":
    main()