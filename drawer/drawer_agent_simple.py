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
# ChatClient — independent LLM wrapper
# ══════════════════════════════════════════════════════════════════════════════
class ChatClient:
    """
    Self-contained LLM client with retry logic and Ctrl+C interruptibility.
    No knowledge of tools, agents, or domain logic.
    """
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

    # ── internals ─────────────────────────────────────────────────────────
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

    # ── public ─────────────────────────────────────────────────────────────
    def grep_files(
        self, keyword: str = "", subdir: str = "",
        max_hits: int = None, is_regex: bool = False,
        CONTEXT_CHARS: int = 100, full_text: bool = False,
    ) -> str:
        if max_hits is None:
            max_hits = self._cfg.MAX_HITS
        ok, err = self._check_lang(keyword, subdir)
        if not ok:
            return err
        if CONTEXT_CHARS > 250:
            return "上下文字符数长于 250，请缩小范围，或直接用 full_text=True 阅读某个文件。"
        file_iter, single_file, err_str = self._resolve_iter(subdir)
        if err_str:
            return err_str
        # full_text with no keyword → return whole file body
        if full_text and not keyword:
            for html_file in file_iter:
                try:
                    soup = BeautifulSoup(
                        html_file.read_text(encoding="utf-8-sig", errors="ignore"),
                        "html.parser",
                    )
                    return f"[阅读后请将此处文本压缩至{self._cfg.MAX_TOOL_RESULT_CHARS}字符以下，阅读时如发现关键语句务必及时调用add_quote记录！]"+"\n"+str(soup.body)+"\n"+f"[阅读后请将此处文本压缩至{self._cfg.MAX_TOOL_RESULT_CHARS}字符以下，如有关键语句务必调用add_quote记录！]" if soup.body else str(soup)
                except Exception as exc:
                    return f"读取失败：{exc}"
            return "文件不存在。"
        try:
            pattern = re.compile(
                keyword if is_regex else re.escape(keyword), re.IGNORECASE
            )
        except re.error as exc:
            return (f"正则语法错误：{exc}\n"
                    "常用：(?:A|B)（或）、(?=.*A)(?=.*B)（同段同时含）")
        effective_max = float("inf") if (subdir and not single_file) else max_hits
        hits, collected = [], 0
        for html_file in file_iter:
            if collected >= effective_max:
                break
            try:
                raw  = html_file.read_text(encoding="utf-8-sig", errors="ignore")
                soup = BeautifulSoup(raw, "html.parser")               
                    # full_text=True with keyword: return tagged body of matching files
                text = soup.get_text(separator="\n")
                if full_text and pattern.search(text):
                    full_text=False
                    collected+=1
                    continue
            except Exception:
                continue
            for m in pattern.finditer(text):
                if len(hits) >= effective_max:
                    break
                start   = max(0, m.start() - CONTEXT_CHARS // 2)
                end     = min(len(text), m.end() + CONTEXT_CHARS // 2)
                snippet = text[start:end].strip()
                title   = self._extract_title(html_file)
                rel     = str(html_file.relative_to(self._root))
                hits.append(
                    f"[文件：{rel}" + (f" | 标题：{title}" if title else "") + "]\n"
                    + snippet
                )
                collected += 1
        if not hits:
            scope = f"「{subdir}」内" if subdir else "全库"
            return f"{scope}未找到包含「{keyword}」的内容。"
        return "\n---\n".join(hits)

    def book_index(self, subdir: str) -> str:
        if subdir in self._cfg.SPECIAL_DIRS:
            attr, fname = self._cfg.SPECIAL_DIRS[subdir]
            return (self._cfg.prefix_for(attr)
                    + f"[DIRECTORY: {subdir}]\n[Discard after locating target files, keep only needed paths in your reply.]\n"
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
            return (f"[Contents: {subdir}  Total: {len(lines)}]\n"+"[Discard after locating target files, keep only needed paths in your reply.]\n"
                    + "\n".join(lines)+"\n[Discard after locating target files, keep only needed paths in your reply.]") if lines else soup.get_text(separator="\n")[:3000]+"\n[Discard after locating target files, keep only needed paths in your reply.]"
        except Exception as exc:
            return f"读取失败：{exc}"

    # ── private ─────────────────────────────────────────────────────────────
    def _resolve_iter(self, subdir: str):
        """Returns (file_iter, is_single_file, error_str)."""
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
        if not subdir or not keyword:
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
# ToolHandler — TOOLS schema, dispatch table, session quotes
# ══════════════════════════════════════════════════════════════════════════════
class ToolHandler:
    """
    Owns the TOOLS list sent to the LLM and the function dispatch table.
    Keeps session quotes.  Delegates real work to SearchTools.
    """
    TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "grep_files",
                "description": (
                    "Full-text keyword search across the library. Returns context snippets "
                    "around each match and the source file. Always search in the original "
                    "language; Chinese is forbidden unless the user permits it. May be called "
                    "multiple times with different languages or directories."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": (
                                "Search keyword; leave empty to retrieve the full text of a file. "
                                "For German/English/Russian files use the corresponding language. "
                                "For Marx/Engels prefer German then English/French; for Lenin prefer "
                                "Russian then German/English/French. Chinese is forbidden unless the "
                                "user permits it.\n"
                                "For multiple terms always construct a valid regex and set is_regex=True.\n"
                                "Regex: (?:A|B)=A or B; (?=.*A)(?=.*B)=both in paragraph; "
                                "A.{0,50}B=within 50 chars."
                            ),
                            "default": "",
                        },
                        "subdir": {
                            "type": "string",
                            "description": (
                                "Search scope (relative to the library root): "
                                "a subdirectory path, a single HTML file, "
                                "or leave empty for a full-library search."
                            ),
                            "default": "",
                        },
                        "max_hits": {
                            "type": "integer",
                            "description": "Maximum number of snippets to return.",
                            "default": 8,
                        },
                        "is_regex": {
                            "type": "boolean",
                            "description": "Enable regex mode.",
                            "default": False,
                        },
                        "CONTEXT_CHARS": {
                            "type": "integer",
                            "description": (
                                "Context characters around each match. "
                                "German/Russian/English > 100; Chinese < 50. Max 250. Default 150."
                            ),
                            "default": 150,
                        },
                        "full_text": {
                            "type": "boolean",
                            "description": (
                                "When true, returns the complete file content including HTML tags. "
                                "Leave keyword empty to retrieve the whole file unconditionally."
                            ),
                            "default": False,
                        },
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
                            "description": (
                                "Directory or index file path relative to library root, "
                                "e.g. 'docs/MEW-ZENO/23/', 'ME-index.html', "
                                "'en/MECW/MECW6-index.html'."
                            ),
                        },
                    },
                    "required": ["subdir"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "add_quote",
                "description": (
                    "Records a key original-text sentence into the session excerpt list. "
                    "Call immediately when grep_files returns a sentence directly relevant "
                    "to the user's question especially when the file only has only a few sentences user needed."
                    "Also call immediately to preserve important search results when they are too long. "
                    "Preserve source language — do not translate."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text":   {"type": "string",
                                   "description": "The original sentence (source language)."},
                        "source": {"type": "string",
                                   "description": "Relative file path of the source."},
                        "note":   {"type": "string",
                                   "description": "Optional note on relevance.",
                                   "default": ""},
                    },
                    "required": ["text", "source"],
                },
            },
        },
    ]

    def __init__(self, search: SearchTools):
        self.session_quotes: list[dict] = []
        self._dispatch = {
            "grep_files": search.grep_files,
            "book_index": search.book_index,
            "add_quote":  self._add_quote,
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
        self._cfg       = cfg
        self._client    = chat_client
        self._tools     = tool_handler
        self._interrupt = chat_client._interrupt

    def run(self, user_input: str, history: list,
            show_tools: bool, show_think: bool, deep_read: bool) -> AgentResult:
        # ── build system prompt ────────────────────────────────────────────
        system = self._cfg.system_prompt_simp.replace("{LIBRARY_MAP}", self._cfg.library_map)
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
            # ── LLM call ──────────────────────────────────────────────────
            try:
                msg = self._client.chat(messages, self._tools.TOOLS, think=show_think)
            except KeyboardInterrupt:
                self._interrupt.clear()
                result = self._wait_for_followup(messages, pre_query_history)
                if result is not None:
                    return result
                continue
            self._print_thinking(msg, show_think)
            messages.append({k: v for k, v in msg.items() if k != "_thinking"})
            # ── no tool calls → final answer ──────────────────────────────
            if not msg.get("tool_calls"):
                answer      = msg.get("content", "").strip()
                new_history = [m for m in messages if m.get("role") != "system"]
                return AgentResult(AgentSignal.ANSWER, answer=answer, history=new_history)
            # ── tool dispatch ─────────────────────────────────────────────
            interrupted = False
            for tc in msg["tool_calls"]:
                fn_name = tc["function"]["name"]
                fn_args = json.loads(tc["function"]["arguments"])
                if show_tools:
                    print(f"\n[工具] {fn_name}({fn_args})")
                try:
                    result_str = self._tools.call(fn_name, fn_args)
                except KeyboardInterrupt:
                    self._interrupt.clear()
                    idx = msg["tool_calls"].index(tc)
                    for rtc in msg["tool_calls"][idx:]:
                        messages.append({
                            "role": "tool", "tool_call_id": rtc["id"],
                            "content": "[STOPPED ABRUPTLY]",
                        })
                    interrupted = True
                    break
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

    # ── pause menu ──────────────────────────────────────────────────────────

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

    def _wait_for_followup(self, messages: list,
                           pre_query_history: list) -> Optional[AgentResult]:
        while True:
            reply       = self._pause_menu("[已中断]")
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
            if not reply:
                print("  [请输入补充问题，或输入 p 暂停返回主菜单]")
                try:
                    supplement = input("  补充 > ").strip()
                except (EOFError, KeyboardInterrupt):
                    self._interrupt.clear()
                    return AgentResult(AgentSignal.PAUSE, history=new_history)
                if supplement.lower() == "p":
                    self._interrupt.clear()
                    return AgentResult(AgentSignal.PAUSE, history=new_history)
                if supplement:
                    messages.append({"role": "user", "content": supplement})
                    print("  [继续处理补充问题…]")
                    return None
                continue


            # 其他输入 → 精简上下文单次作答
            #self._single_trimmed_request(messages, reply)

    # ── tool result cap ─────────────────────────────────────────────────────

    def _cap_tool_result(self, text: str) -> str:
        limit = self._cfg.MAX_TOOL_RESULT_CHARS
        if len(text) > limit:
            return (text
                    + f"\n[Search result too long, already exceed {limit} chars, "
                    "please sort out the results needed for answering user's question! "
                    "And also using add_quote to record if you find key contexts!]")
        return text

    # ── context management ──────────────────────────────────────────────────

    @staticmethod
    def _total_chars(messages: list) -> int:
        return sum(len(str(m.get("content", ""))) for m in messages)

    def _trim_messages(self, messages: list, char_limit: int) -> list:
        """Return system + as many recent non-system messages as fit in char_limit.
        Orphaned tool_calls / tool results (whose pair was trimmed away) are collapsed to '未匹配'."""
        system     = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]
        kept, chars = [], 0
        for m in reversed(non_system):
            c = len(str(m.get("content", "")))
            if chars + c > char_limit:
                break
            kept.append(m)
            chars += c
        kept = list(reversed(kept))

        # 收集 assistant 侧发出的所有 tool_call_id
        issued_ids = {
            tc["id"]
            for m in kept if m.get("role") == "assistant"
            for tc in m.get("tool_calls", [])
        }
        # 收集 tool 侧已回复的所有 id
        answered_ids = {
            m["tool_call_id"]
            for m in kept if m.get("role") == "tool" and "tool_call_id" in m
        }
        for m in kept:
            if m.get("role") == "tool" and m.get("tool_call_id") not in issued_ids:
                m["content"] = "未匹配"
            if m.get("role") == "assistant" and m.get("tool_calls"):
                m["tool_calls"] = [
                    {**tc, "function": {**tc["function"], "arguments": '"未匹配"'}}
                    if tc["id"] not in answered_ids else tc
                    for tc in m["tool_calls"]
                ]
        return system + kept

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

    # ── display ─────────────────────────────────────────────────────────────

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
# save_history — module-level helper (used only by main)
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
# AppController — owns all CLI state and the interactive loop
# ══════════════════════════════════════════════════════════════════════════════
class AppController:
    """
    Holds all mutable runtime state (history, display flags) and drives the
    CLI loop.  Constructs nothing — receives every dependency via __init__.
    main() is reduced to wiring + AppController(...).run().
    """
    def __init__(self, cfg: Config, interrupt: threading.Event,
                 tool_handler: ToolHandler, agent: Agent):
        self._cfg          = cfg
        self._interrupt    = interrupt
        self._tool_handler = tool_handler
        self._agent        = agent
        self.show_tools = cfg.DISPLAY_TOOLS
        self.show_think = cfg.ENABLE_THINKING
        self.history:   list = []

    # ── entry point ────────────────────────────────────────────────────────
    def run(self):
        self._register_sigint()
        
        try:
            while True:
                self._print_banner()
                user_input = self._read_input()
                if user_input is None:          # EOF / confirmed exit
                    break
                if user_input.lower() == "q":
                    break
                if not self._dispatch_cmd(user_input):
                    self._run_agent(user_input)
        finally:
            self._autosave()

    # ── SIGINT ─────────────────────────────────────────────────────────────
    def _register_sigint(self):
        def _handler(sig, frame):
            if self._interrupt.is_set():
                self._interrupt.clear()  # 清除标志，避免重复触发
                raise KeyboardInterrupt
            self._interrupt.set()
        signal.signal(signal.SIGINT, _handler)

    # ── input ──────────────────────────────────────────────────────────────
    def _read_input(self) -> Optional[str]:
        """Returns the stripped input string, or None to signal exit."""
        try:
            return input("请输入问题：").strip()
        except EOFError:
            return None
        except KeyboardInterrupt:
            self._interrupt.clear()  # 清除标志
            print()
            try:
                confirm = input("确认退出？(y/Enter=退出，其他键继续)：").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return None
            return None if confirm in ("", "y", "yes") else ""

    # ── command dispatch ───────────────────────────────────────────────────
    def _dispatch_cmd(self, user_input: str) -> bool:
        """Handle single-char commands.  Returns True if consumed."""
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
        return False

    # ── agent runner ───────────────────────────────────────────────────────
    def _run_agent(self, user_input: str):
        result = self._agent.run(
            user_input, self.history,
            show_tools=self.show_tools,
            show_think=self.show_think,
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

    # ── status ─────────────────────────────────────────────────────────────
    def _status(self) -> str:
        flags = [n for n, v in [("工具显示", self.show_tools),
                                ("思考模式", self.show_think)] if v]
        return "、".join(flags) if flags else "全关"

    # ── commands ───────────────────────────────────────────────────────────
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

    # ── autosave on exit ───────────────────────────────────────────────────
    def _autosave(self):
        if self.history:
            try:
                p = save_history(self.history, self._tool_handler.session_quotes,
                                 self.show_tools, self._cfg.HISTORY_OUTPUT_PATH)
                print(f"\n[退出前已自动保存至 {p}]")
            except Exception as exc:
                print(f"\n[自动保存失败：{exc}]")
        print("[再见]")

    # ── banner ─────────────────────────────────────────────────────────────
    def _print_banner(self):
        print(f"文献查询系统已就绪  文件夹：{self._cfg.HTML_FOLDER}")
        print("  t 工具显示  d 思考模式  n 新对话  s 保存 + 新对话  e 撤销  q 退出")
        print("  Ctrl+C 中止当前查询（再按一次强制退出）\n")

# ══════════════════════════════════════════════════════════════════════════════
# main — wires dependencies, hands off to AppController
# ══════════════════════════════════════════════════════════════════════════════
def main():
    cfg          = Config()
    interrupt    = threading.Event()
    chat_client  = ChatClient(cfg, interrupt)
    search       = SearchTools(cfg)
    tool_handler = ToolHandler(search)
    agent        = Agent(cfg, chat_client, tool_handler)
    AppController(cfg, interrupt, tool_handler, agent).run()

if __name__ == "__main__":
    main()