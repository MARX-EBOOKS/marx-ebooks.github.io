import json
import re
import random
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Optional
import httpx
from unpackpdf import ImageCache
import MEWbrief
import argparse
import uuid
from bs4 import BeautifulSoup  

# ==================== 配置类 ====================
class Config:
    """
    同时承担两种职责：
      1. 模型配置  MODEL / API_URL / API_KEY / ENABLE_THINK / THINK_TYPE
      2. 通用配置  VOL / DPI / OUTPUT_DIR / …
    main() 中创建两个实例（page_cfg / chat_cfg），各自填写模型字段；
    通用字段只需在其中一个上设置，组件统一从 chat_cfg 读取。
    """

    # ── 通用默认值（类级别，实例可覆盖）──────────────────────
    MAX_RETRIES      = 5
    RETRY_WAIT       = 2
    CACHE_MIN_TOKENS = 64
    CACHE_MARK_LIMIT = 32
    MAX_ROUNDS       = 300
    SUPPORT_CACHE = ["https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"]
    def __init__(self,USE_API:API_SERVERICE,PDF_CONFI:PDF_CONVERT_Config,ENABLE_EXPLICIT_CACHE:bool,MAX_CONCURRENT:int,THINK_TYPE:str):
        # ── 模型配置字段（两个实例各自填写）──────────────────
        self.MODEL        =""
        self.API_URL      =USE_API.API_URL
        self.API_KEY      =USE_API.API_KEY
        self.THINK_TYPE   =THINK_TYPE
        # 支持: chat_template_kwargs / extra_body / reasoning_content / think / reasoning_effort
        self.VOL            =PDF_CONFI.VOL
        self.CACHE_DIR      =PDF_CONFI.CACHE_DIR
        self.OUTPUT_DIR     =PDF_CONFI.OUTPUT_DIR
        self.NOTICE_FILE    =PDF_CONFI.NOTICE_FILE
        self.DPI            =PDF_CONFI.DPI
        self.RASTER_WORKERS =PDF_CONFI.RASTER_WORKERS
        self.MAX_CONCURRENT = MAX_CONCURRENT
        # ── 缓存相关 ──────────────────────────────────────────
        self.ENABLE_EXPLICIT_CACHE =ENABLE_EXPLICIT_CACHE
        self.LONG_SHORT =PDF_CONFI.LONG_SHORT
        self.TIMEOUT= httpx.Timeout(connect=10.0, read=360.0, write=120.0, pool=10.0)
        self.MAX_TOKENS = 65336
        self.TEMPERATURE= 0.6
        self.TOP_P= 0.9
    def get_think_payload(self,ENABLE_THINK) -> dict | None:
        """返回当前配置对应的思考参数，供 _build_payload 插入 payload。"""
        mapping = {
            "extra_body":           {"enable_thinking":ENABLE_THINK, "top_k": 20},
            "reasoning_content":ENABLE_THINK,
            "think":                {"type": "think"},
            "thinking":                {"type": "enabled" if ENABLE_THINK else "disabled"},
            "reasoning_effort":     "high",
            "chat_template_kwargs": {"enable_thinking":ENABLE_THINK},
            "enable_thinking":ENABLE_THINK
        }
        if not ENABLE_THINK and self.THINK_TYPE in ["think","reasoning_effort"]:
            return None
        return mapping.get(self.THINK_TYPE)
class API_SERVERICE:
    def __init__(self,API_URL:str, API_KEY:str):
        self.API_URL=API_URL
        self.API_KEY=API_KEY
@dataclass
class PDF_CONVERT_Config:
    VOL            = 0
    CACHE_DIR      = "cache_images"
    OUTPUT_DIR     = "output"
    NOTICE_FILE    = None
    DPI            = 225
    RASTER_WORKERS = 1
    LONG_SHORT=1
    LONG_THINK=True
    SHORT_THINK=False
    DEFAULT_CHAT_THINK=True
# ==================== 信号与结果定义 ====================
class AgentSignal(Enum):
    ANSWER   = auto()
    NEW_CONV = auto()
    PAUSE    = auto()

@dataclass
class AgentResult:
    signal:  AgentSignal
    answer:  Optional[str] = None
    history: list = field(default_factory=list)

# ==================== VLM 客户端 ====================
class VLMClient:
    """同步 LLM/VLM 客户端。cfg 同时提供模型参数和通用参数。"""

    _RETRY_STATUS = {429, 500, 502, 503}

    def __init__(self, cfg: Config, interrupt: threading.Event,cancel:threading.Event):
        self.cfg        = cfg
        self._interrupt = interrupt
        self._sem       = threading.Semaphore(cfg.MAX_CONCURRENT)
        self._cancel    =cancel
        self._headers   = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {cfg.API_KEY}",
            "User-Agent":    "opencode/1.14.31",
        }
        self.prompt_usage = 0
        self._usage_lock  = threading.Lock()

    def _build_payload(self, messages: list, tools: Optional[list] = None,
                       enable_cache: bool = True,enable_think:bool=False) -> dict:
        if enable_cache and self.cfg.ENABLE_EXPLICIT_CACHE \
                and self.cfg.API_URL in self.cfg.SUPPORT_CACHE:
            mark_count = 0
            for msg in messages:
                if mark_count >= self.cfg.CACHE_MARK_LIMIT:
                    break
                if msg["role"] == "system" and isinstance(msg["content"], str):
                    if len(msg["content"]) >= self.cfg.CACHE_MIN_TOKENS:
                        msg["content"] = [{"type": "text", "text": msg["content"],
                                           "cache_control": {"type": "ephemeral"}}]
                        mark_count += 1
                elif msg["role"] == "user" and isinstance(msg["content"], list):
                    for item in reversed(msg["content"]):
                        if item.get("type") == "text" \
                                and len(item.get("text", "")) >= self.cfg.CACHE_MIN_TOKENS:
                            item["cache_control"] = {"type": "ephemeral"}
                            mark_count += 1
                            break

        payload = {
            "model":       self.cfg.MODEL,
            "messages":    messages,
            "temperature": self.cfg.TEMPERATURE,
            "top_p":       self.cfg.TOP_P,
            "max_tokens":  self.cfg.MAX_TOKENS,
            "stream":      False,
        }
        if tools:
            payload["tools"] = tools

        think_val = self.cfg.get_think_payload(enable_think)
        if think_val is not None:
            payload[self.cfg.THINK_TYPE] = think_val
            if self.cfg.THINK_TYPE=="enable_thinking":
                payload["top_k"]=20
            if "deepseek" in self.cfg.API_URL and enable_think:
                payload["reasoning_effort"] = "max"
        return payload

    def _parse_response(self, data: dict, tools: Optional[list] = None) -> dict:
        if not data or "choices" not in data or not data["choices"]:
            raise RuntimeError(f"响应格式异常：{data}")

        usage = data.get("usage")
        if usage:
            print(f"\nToken 使用：输入={usage['prompt_tokens']}，"
                  f"输出={usage['completion_tokens']}，"
                  f"总计={usage['total_tokens']}\n")
            details = usage.get("prompt_tokens_details", {})
            if details:
                cached  = details.get("cached_tokens", 0)
                created = details.get("cache_creation_input_tokens", 0)
                if cached > 0:
                    print(f"🎯 缓存命中：{cached} tokens"
                          f" (节省约 {cached/usage['prompt_tokens']*100:.1f}%)")
                elif created > 0:
                    print(f"💾 缓存创建：{created} tokens (下次请求可命中)")
                else:
                    print("❌ 缓存未命中 (可能原因：内容变化/超时/长度不足)")
            with self._usage_lock:
                self.prompt_usage = usage["prompt_tokens"]

        msg      = data["choices"][0]["message"]
        thinking = (msg.get("reasoning_content") or "").strip()
        content  = msg.get("content") or ""

        if not thinking and content:
            m = re.search(r"<think>(.*?)</think>", content, re.DOTALL)
            if m:
                thinking       = m.group(1).strip()
                msg["content"] = re.sub(r"<think>.*?</think>\s*", "", content,
                                        flags=re.DOTALL).strip()

        if msg.get("content") is None:
            msg["content"] = ""
        if thinking:
            msg["_thinking"] = thinking

        if not msg.get("tool_calls"):
            extracted = self._extract_tool_calls_from_thinking(thinking, tools)
            if extracted:
                msg["tool_calls"] = extracted
        return msg

    @staticmethod
    def _extract_tool_calls_from_thinking(thinking: str,
                                          tools: Optional[list] = None) -> list:
        sig_map = []
        if tools:
            for t in tools:
                fn  = t["function"]
                req = frozenset(fn["parameters"].get("required", []))
                if req:
                    sig_map.append((req, fn["name"]))

        tool_calls = []
        for i, m in enumerate(re.finditer(r'\{.*?\}', thinking, re.DOTALL)):
            raw = m.group(0).strip()
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict) or not obj:
                continue

            name = obj.get("name") or obj.get("function") or obj.get("tool")
            args = obj.get("arguments") or obj.get("parameters")
            if name and args is not None:
                args_str = json.dumps(args, ensure_ascii=False) \
                    if isinstance(args, dict) else str(args)
                tool_calls.append({
                    "id": f"think_tc_{i}", "type": "function",
                    "function": {"name": name, "arguments": args_str},
                })
                continue

            if sig_map:
                key_set = frozenset(obj.keys())
                for req_keys, tool_name in sig_map:
                    if req_keys.issubset(key_set):
                        tool_calls.append({
                            "id": f"think_tc_{i}", "type": "function",
                            "function": {"name": tool_name,
                                         "arguments": json.dumps(obj, ensure_ascii=False)},
                        })
                        break
        return tool_calls

    @staticmethod
    def build_multimodal_messages(prompt: str, images_b64: list[str]) -> list[dict]:
        content = [{"type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"}}
                   for b64 in images_b64]
        content.append({"type": "text", "text": prompt})
        return [{"role": "user", "content": content}]

    def _request_with_retry(self, payload: dict, validate_fn=None) -> httpx.Response:
        attempt = 0
        MAX_RETRIES=self.cfg.MAX_RETRIES
        while True:
            resp = self._do_request(payload)
            if resp.status_code < 400:
                if validate_fn is None or validate_fn(resp):
                    return resp          
            if attempt < MAX_RETRIES - 1:
                if resp.status_code == 200:
                    wait= random.uniform(60,120)
                    self._sleep_interruptible(wait)
                else:
                    wait = random.uniform(self.cfg.RETRY_WAIT, self.cfg.RETRY_WAIT + attempt)
                    self._sleep_interruptible(wait)
                if resp.status_code == 504:
                    attempt=0
                attempt += 1
            else:
                print(f"[API error {resp.status_code}: {resp.text[:300]}, failed after {attempt+1} attempt(s)]")
                self._pause_on_error()
                attempt = 0
    def _do_request(self, payload: dict) -> httpx.Response:
        result, error = [None], [None]
        client_ref = [None]
        self._sem.acquire()
        try:
            def _worker():
                try:
                    with httpx.Client(timeout=self.cfg.TIMEOUT) as client:
                        client_ref[0] = client
                        headers_act = {**self._headers, "x-request-id": str(uuid.uuid4())}
                        result[0] = client.post(self.cfg.API_URL,
                                                json=payload, headers=headers_act)
                except Exception as exc:
                    error[0] = exc
            t = threading.Thread(target=_worker, daemon=True)
            t.start()
            while t.is_alive():
                t.join(timeout=0.1)
                if self._interrupt.is_set() or self._cancel.is_set():
                    self._cancel.clear()
                    self._interrupt.clear()
                    c = client_ref[0]
                    if c:
                        c.close()
                    raise KeyboardInterrupt
            if error[0]:
                raise error[0]
            return result[0]
        finally:
            self._sem.release()

    def _sleep_interruptible(self, seconds: float):
        for _ in range(int(seconds * 10)):
            time.sleep(random.uniform(0.08, 0.15))
            if self._interrupt.is_set():
                self._cancel.clear()
                self._interrupt.clear()
                raise KeyboardInterrupt

    def chat(self, messages: list, tools: Optional[list] = None,
             enable_cache: bool = True,enable_think:bool=False) -> dict:
        payload = self._build_payload(messages, tools, enable_cache,enable_think=enable_think)
        resp = self._request_with_retry(
            payload, validate_fn=lambda r: bool((r.json() or {}).get("choices")))
        return self._parse_response(resp.json(), tools)

    def chat_loop(self, messages: list, tools: list, tool_handler=None,
                  max_rounds: int = 300, show_tools: bool = False,
                  enable_think: bool = False, enable_cache: bool = True) -> dict:
        empty_retry = 0
        for _ in range(max_rounds):
            msg        = self.chat(messages, tools=tools or None, enable_cache=enable_cache,enable_think=enable_think)
            tool_calls = msg.get("tool_calls") or []

            if msg.get("_thinking"):
                text = msg["_thinking"][:60000]+"..." if len(msg["_thinking"])>60000 else msg["_thinking"]
                print(f"\n  ┌─[思考]{'─'*50}")
                for line in text.splitlines():
                    print(f"  │ {line}")
                print(f"  └{'─'*52}")

            if not tool_calls and not msg.get("content"):
                empty_retry += 1
                if empty_retry <= 5:
                    wait = random.uniform(self.cfg.RETRY_WAIT, self.cfg.RETRY_WAIT+empty_retry)
                    self._sleep_interruptible(wait)
                    continue
                raise RuntimeError("模型多次返回空响应")
            empty_retry = 0

            if not tool_calls or not tool_handler:
                messages.append({k: v for k, v in msg.items() if k != "_thinking"})
                return msg

            messages.append({k: v for k, v in msg.items()
                             if k not in ("_thinking", "tool_calls")})
            messages[-1]["tool_calls"] = tool_calls

            def _exec_one(tc):
                fn_name = tc["function"]["name"]
                fn_args = json.loads(tc["function"].get("arguments", "{}"))
                if show_tools:
                    print(f"\n[工具] {fn_name}({fn_args})")
                result = tool_handler.call(fn_name, fn_args)
                if show_tools:
                    preview = (result if isinstance(result, str)
                               else f"[multimodal, {len(result)} blocks]")
                    print(f"  [结果] {str(preview)[:200]}"
                          f"{'…' if isinstance(result, str) and len(result) > 200 else ''}")
                return tc, result
            if len(tool_calls) == 1:
                results = [_exec_one(tool_calls[0])]
            else:
                results = [None] * len(tool_calls)
                with ThreadPoolExecutor(
                        max_workers=min(len(tool_calls), self.cfg.MAX_CONCURRENT)) as ex:
                    futures = {ex.submit(_exec_one, tc): i
                               for i, tc in enumerate(tool_calls)}
                    for future in as_completed(futures):
                        results[futures[future]] = future.result()

            for tc, result in results:
                messages.append({"role": "tool",
                                  "tool_call_id": tc.get("id", ""),
                                  "content": result})

        raise RuntimeError(f"超出最大工具调用轮次 {max_rounds}")
    def _pause_on_error(self):
        print("\n" + "─"*50 + "\n[程序已暂停]\n" + "─"*50)
        try:
            if input("按任意键重试 / q 暂停：").strip().lower() == "q":
                self._cancel.clear()      # 新增：清除取消标志
                self._interrupt.clear()   # 新增：清除中断标志
                raise KeyboardInterrupt
        except (EOFError, KeyboardInterrupt):
            self._cancel.clear()      # 新增：清除取消标志
            self._interrupt.clear()   # 新增：清除中断标志
            raise KeyboardInterrupt

# ==================== 页面处理器 ====================
class PageProcessor:

    def __init__(self, cache: ImageCache, vlm: VLMClient):
        self.cache       = cache
        self.vlm         =vlm
        self.cfg         =vlm.cfg
        self._fixed_messages    = []
        self._cache_initialized = False
        self.FORMAT_REQUIREMENTS = self.get_format_requirements(self.cfg.VOL)
    def get_format_requirements(self,vol):
        FORMAT_REQUIREMENTS=Path("./prompts/convert2.md").read_text(encoding="utf-8")
        if vol in range(23,26):
            FORMAT_REQUIREMENTS=Path("./prompts/convert23.md").read_text(encoding="utf-8")
        return FORMAT_REQUIREMENTS


    def convert_and_merge(self, page_list: list[int], user_instruction: str = "",enable_think:bool=False) -> str:
        capital=""
        if self.cfg.VOL in range(23,26):
            capital=f"，正在处理资本论第 {self.cfg.VOL-22} 卷内容。"
        self._fixed_messages = [{"role": "system", "content":
                f"你是一个专业的 PDF 转 HTML 助手{capital}。\n"
                f"请严格按照以下格式要求转换：\n{self.FORMAT_REQUIREMENTS}\n"}]
        if not self._cache_initialized and self.vlm.cfg.ENABLE_EXPLICIT_CACHE and self.vlm.cfg.API_URL in self.vlm.cfg.SUPPORT_CACHE:
            self._cache_initialized = True

        images_b64 = [self.cache.get_image_b64(p) for p in page_list]
        notice = (self.cfg.NOTICE_FILE.read_text(encoding="utf-8")
                  if self.cfg.NOTICE_FILE.exists() else "")
        variable_prompt = (f"{user_instruction + notice if user_instruction else '请输出！'}\n")

        messages = self._fixed_messages.copy()
        messages.append({"role": "user", "content": [
                *[{"type": "image_url",
                   "image_url": {"url": f"data:image/png;base64,{b64}"}}
                  for b64 in images_b64],
                {"type": "text", "text": variable_prompt}
            ]})

        msg = self.vlm.chat_loop(messages, tools=[], tool_handler=None,
                                 show_tools=True, enable_think=enable_think,
                                 enable_cache=self._cache_initialized)
        if not msg.get("content"):
            return ""

        merged = re.sub(r'^.*?```html\s*', '', msg["content"], flags=re.IGNORECASE)
        merged = re.sub(r'\s*```.*?$', '', merged)
        if not re.search(r'<title>', merged, re.IGNORECASE):
            merged = (f"<title>MEW Band{self.cfg.VOL} "
                      f"S.{page_list[0]}-{page_list[-1]}</title>\n{merged}")
        if not re.search(r'<body>', merged, re.IGNORECASE):
            merged = f"<body>\n{merged}\n</body>"
        if not self.cfg.VOL in range(261,264):
            output_path = Path(self.cfg.OUTPUT_DIR) / f"ME{self.cfg.VOL:02d}-{page_list[0]:03d}.html"
        elif self.cfg.VOL==261:
            output_path = Path(self.cfg.OUTPUT_DIR) / f"ME26-1{page_list[0]:03d}.html"
        elif self.cfg.VOL==262:
            output_path = Path(self.cfg.OUTPUT_DIR) / f"ME26-2{page_list[0]:03d}.html"
        elif self.cfg.VOL==263:
            output_path = Path(self.cfg.OUTPUT_DIR) / f"ME26-3{page_list[0]:03d}.html"
        output_path.write_text(merged, encoding="utf-8")
        return str(output_path)

# ==================== 工具处理器 ====================
class ToolHandler:

    ALL_TOOLS = [
        {"type": "function", "function": {
            "name": "merge_pages",
            "description": "将多个 PDF 页面发给 VLM 模型合并为一个 HTML 文件，注意一组一用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pages": {"type": "array", "items": {"type": "integer"},
                              "description": "要合并的页码组"},
                    "merge_instruction": {"type": "string", "description": "合并要求",
                                         "default": ""}
                },
                "required": ["pages"]
            }
        }},
        {"type": "function", "function": {
            "name": "check_read_html",
            "description": (
                "读取已生成的 HTML 文件文本，由你直接审阅。"
                "适合纯文本层面校对：拼写、标签闭合、脚注编号、双向链接、跨页合并、标题层级等。"
                "如发现错误请告知用户，如错误过多请代用户附加要求发给VLM重新转换。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "html_path": {"type": "string", "description": "HTML 文件路径，为空则按 pages[0] 自动推断",
                                  "default": ""},
                    "pages": {"type": "array", "items": {"type": "integer"},
                              "description": "对应的原始页码列表，用于自动推断路径"}
                },
                "required": ["pages"]
            }
        }},
        {"type": "function", "function": {
            "name": "get_page_images",
            "description": "获取指定 PDF 页面的原始图片，由你直接查看。可配合 check_read_html 对照校对。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pages": {"type": "array", "items": {"type": "integer"},
                              "description": "要查看的页码列表"}
                },
                "required": ["pages"]
            }
        }},
        {"type": "function", "function": {
            "name": "save_html",
            "description": "保存 HTML 文件（用于保存校对后的修正结果）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "html_path": {"type": "string", "description": "HTML 文件路径"},
                    "content":   {"type": "string", "description": "待保存的 HTML 内容"}
                },
                "required": ["html_path", "content"]
            }
        }},
        {"type": "function", "function": {
            "name": "add_notice",
            "description": "记录转换中发现的问题。",
            "parameters": {
                "type": "object",
                "properties": {
                    "note": {"type": "string", "description": "要记录的问题"}
                },
                "required": ["note"]
            }
        }},
        {"type": "function", "function": {
            "name": "page_group",
            "description": "查看PDF各篇目页码组",
            "parameters": {
            "type": "object", 
            "properties": {}
            }
        }},
        {"type": "function", "function": {
            "name": "get_requirements",
            "description": "查看用户转换要求",
            "parameters": {
            "type": "object", 
            "properties": {}
            }
        }},
                {"type": "function", "function": {
            "name": "regex_edit_html",
            "description": (
                "对指定 HTML 文件执行一次或多次正则替换，替换完成后自动保存。"
                "适合批量修正重复性错误，如错误标签、连字符、多余空格、错误编号前缀等。"
                "每条规则的 pattern 为 Python re 正则，flags 支持 'I'/'DOTALL'/'M' 等，"
                "可用 r'\\1' 风格的反向引用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "html_path": {"type": "string",
                                  "description": "HTML 文件路径，为空则按 pages[0] 自动推断",
                                  "default": ""},
                    "pages": {"type": "array", "items": {"type": "integer"},
                              "description": "对应页码（用于自动推断路径）",
                              "default": []},
                    "merge_html": {"type": "boolean",
                                   "description": "是否在 merge 目录中操作",
                                   "default": False},
                    "rules": {
                        "type": "array",
                        "description": "替换规则列表，按顺序执行",
                        "items": {
                            "type": "object",
                            "properties": {
                                "pattern":     {"type": "string", "description": "Python 正则表达式，如有捕获组应写作\1、\2等"},
                                "replacement": {"type": "string", "description": "替换字符串，可含反向引用"},
                                "flags":       {"type": "string",
                                                "description": "可选标志，逗号分隔：I, M, DOTALL, S",
                                                "default": ""}
                            },
                            "required": ["pattern", "replacement"]
                        }
                    }
                },
                "required": ["rules"]
            }
        }},
        {"type": "function", "function": {
            "name": "str_replace_html",
            "description": (
                "对 HTML 文件精准字符串替换（非正则）。"
                "先用 check_read_html 读取文件内容，找到要修改的原文，"
                "再调用本工具将 old_str 精确替换为 new_str 并保存。"
                "old_str 必须在文件中唯一出现，否则返回错误。"
                "在确定段落、标签、属性等精确定位的内容后可使用本函数。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "html_path": {"type": "string", "description": "要替换的文件路径","default": ""},
                    "pages":     {"type": "array", "items": {"type": "integer"}, "description": "要替换的页码", "default": []},
                    "merge_html":{"type": "boolean", "default": False},
                    "old_str":   {"type": "string", "description": "要替换的原始字符串，必须与文件内容完全一致"},
                    "new_str":   {"type": "string", "description": "替换后的新字符串"}
                },
                "required": ["old_str", "new_str"]
            }
        }},
        {"type": "function", "function": {
            "name": "grep_files",
            "description": (
                "内容检索工具，支持全字匹配与正则检索。可按页码搜索转换后的 HTML 文本以供修改。正则检索时 is_regex 务必设为 True。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": ("要搜索的关键词。\n"
                                        "除全字匹配外，还可设为 python 中有效的正则表达式。")
                    },
                    "pages": {
                        "type": "array", "items": {"type": "integer"},
                        "description": "要搜索的转换后文件页码列表，取需检索组每组的第一个页码即可。"
                    },
                    "html_paths": {
                        "type": "array", "items": {"type": "string"},
                        "description": "显式指定的 HTML 路径列表（优先于 pages 自动推断）",
                        "default": []
                    },
                    "max_hits": {
                        "type": "integer",
                        "description": "最大匹配数",
                        "default": 50
                    },
                    "CONTEXT_CHARS":{
                        "type": "integer",
                        "description": "单条匹配的上下文字符长度，默认100",
                        "default": 100
                    },
                    "is_regex":{
                        "type": "boolean",
                        "description": "keyword 为正则表达式时开启正则，默认False",
                        "default": False
                    },
                    "page_index":{
                        "type": "integer",
                        "description": "搜索结果分页查看，需要看那一分页就填什么数字",
                        "default": 0
                    },
                    "SEARCH_PAGE_SIZE":{
                        "type": "integer",
                        "description": "搜索结果分页的每页条数",
                        "default": 10
                    }

                },
                "required": ["keyword"]
            }
        }},
        {"type": "function", "function": {
            "name": "table_content",
            "description": (
                "调用目录表数组，查看正确的标题层级，字符串为应转换的标题文本及层级标签，整数为对应页码。"
            ),
            "parameters": {
            "type": "object", 
            "properties": {}
            }
        }
        }


    ]

    def __init__(self, cache: ImageCache,page_client_long:VLMClient,page_client_short:VLMClient,
                 pdf_cfg: PDF_CONVERT_Config,
                 use_tools: Optional[list] = None):
        self.cache       = cache
        self.pdfcfg         =pdf_cfg
        self.cfg         =self.pdfcfg 
        self.page_client_long=page_client_long
        self.page_client_short=page_client_short
        self.tools       = use_tools if use_tools is not None else self.ALL_TOOLS
        self.pg=MEWbrief.page_group[pdf_cfg.VOL]
        self._dispatch = {
            "merge_pages":    self._merge_pages,
            "check_read_html":self._check_read_html,
            "get_page_images": self._get_page_images,
            "save_html":      self._save_html,
            "add_notice":     self._add_notice,
            "page_group":self._page_group,
            "get_requirements":self._get_requirements,
            "read_html_files_for_merge":self._read_html_files_for_merge,
            "regex_edit_html": self._regex_edit_html,
            "str_replace_html": self._str_replace_html,
            "grep_files":self._grep_files,
            "table_content":self._table_content,
        }
        self.FORMAT_REQUIREMENTS = self.get_format_requirements(pdf_cfg.VOL)
        self._page_to_group_start: dict[int, int] = {
    pg: group[0]
    for group in self.pg
    if isinstance(group, (list, tuple))
    for pg in group
}
    def _table_content(self):
        vol=self.pdfcfg.VOL
        return str(MEWbrief.inhalt[vol]) if MEWbrief.inhalt[vol] else "目录为空，请用户检查目录！"
    def get_format_requirements(self,vol):
        FORMAT_REQUIREMENTS=Path("./prompts/convert2.md").read_text(encoding="utf-8")
        if vol in range(23,26):
            FORMAT_REQUIREMENTS=Path("./prompts/convert23.md").read_text(encoding="utf-8")
        return FORMAT_REQUIREMENTS
    def _get_processor(self,page_client) -> PageProcessor:
        _processor = PageProcessor(self.cache, page_client)
        return _processor

    def call(self, fn_name: str, fn_args: dict) ->str | list:
        fn = self._dispatch.get(fn_name)
        if not fn:
            return f"未知工具：{fn_name}"
        valid = {
            t["function"]["name"]: set(t["function"]["parameters"]["properties"].keys())
            for t in self.tools if t.get("type") == "function"
        }.get(fn_name)
        if valid:
            bad = {k for k in fn_args if k not in valid}
            if bad:
                print(f"  [忽略未知参数 {fn_name}: {bad}]")
                fn_args = {k: v for k, v in fn_args.items() if k in valid}
        result = fn(**fn_args)
        return result if isinstance(result, list) else str(result)
    def _resolve_page_path(self, pg: int) -> Path | None:
        """按页码推断文件路径，找不到时返回 None。"""
        p = self._resolve_html_path(pages=[pg])
        return p if p.exists() else None

    def _resolve_html_path(self, html_path: str = "", pages: list[int] = None,
                            merge_html: bool = False) -> Path:
        if html_path:
            if not Path(html_path).parent.exists() and not merge_html:
                Path(html_path).parent.mkdir(parents=True, exist_ok=True)
            return Path(html_path)

        prefix = f"ME{self.cfg.VOL:02d}-"
        if self.cfg.VOL in range(261, 264):
            prefix = f"ME26-{self.cfg.VOL - 260}"

        if merge_html:
            Path(self.cfg.HTML_MERGE_DIR).mkdir(parents=True, exist_ok=True)
            return Path(self.cfg.HTML_MERGE_DIR) / f"{prefix}{pages[0]:03d}.html"

        base_dir = Path(self.cfg.OUTPUT_DIR)
        direct   = base_dir / f"{prefix}{pages[0]:03d}.html"
        if direct.exists():
            return direct

        # ── 回退：在页码组里找包含该页码的组，取其首页 ──────────
        pg = pages[0]
        group_start = self._page_to_group_start.get(pg)
        if group_start is not None:
            fallback = base_dir / f"{prefix}{group_start:03d}.html"
            if fallback.exists():
                return fallback
        return direct

    def _read_html_text(self, html_path: str, pages: list[int]) -> tuple[Path, str]:
        """共用 helper：解析路径并读取 HTML 文本。"""
        path = self._resolve_html_path(html_path, pages)
        try:
            return path, path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return path, None
    def _read_html_files_for_merge(self, pages: list[int], html_paths: list[str] = None,
                         merge_instruction: str = "") -> str:
        paths: list[Path] = []
        if html_paths:
            paths = [Path(p) for p in html_paths]
        else:
            for p in sorted(pages):
                paths.append(self._resolve_html_path("", [p]))
        missing = [str(p) for p in paths if not p.exists()]
        if missing:
            return f"以下文件不存在，请先转换：{missing}"

        fragments = []
        for path in paths:
            text = path.read_text(encoding="utf-8")
            fragments.append(f"<!-- === SOURCE: {path.name} === -->\n{text}")

        first, last = sorted(pages)[0], sorted(pages)[-1]
        vol = self.pdfcfg.VOL
        stem = (f"ME26-1{first:03d}-{last:03d}" if vol == 261 else
                f"ME26-2{first:03d}-{last:03d}" if vol == 262 else
                f"ME26-3{first:03d}-{last:03d}" if vol == 263 else
                f"ME{vol:02d}-{first:03d}-{last:03d}")
        suggested_output = str(Path(self.pdfcfg.OUTPUT_DIR) / f"{stem}.html")

        return (
            f"以下是 {len(paths)} 个 HTML 片段，请按照 get_requirements 的要求，将这些片段拼接成一个可连续阅读的完整HTML文本后，调用 save_html 保存。\n"
            f"建议输出路径：{suggested_output}\n"
            f"用户附加要求：{merge_instruction}\n" if merge_instruction else ""
            f"拼接规则（用户无特殊要求时）：\n"
            f"1. 识别作者注和编者注的链接与内容后，分别按不同编号系统编号，而编号系统即编号开始的数字也可由用户指定。其中作者注的id为Mxx/ZMxx/Exx/ZExx，编者注的id为Fxx/ZFxx，均已按照 get_requirements 中的要求放到对应aside容器中，因此输出时应该把连续多页aside栏中的脚注内容合并，保证各栏的脚注用对应的编号系统，即保证链接id的编号唯一\n"
            f"2. 相邻片段、页面的首尾若属同一自然段落则合并，注意如 get_requirements 中所述，将段落中多余的连字符号删去，将相应的空格加回\n"
            f"3. 去除片段间重复的 <html>/<head>/<body> 标签及重复 Kolumnentitel\n"
            f"4. 如需对照原始版面或内容请调用 get_page_images\n\n"
            f"5. 根据语义和图像校订标题层级，保证层级正确，最终的title定为处理的内容中出现的第一个标题\n\n"
            f"6. 根据语义和图像，按照get_requirements 的要求，同时严格遵照用户的其他要求，校订待合并内容的其他问题，如脚注、拼写、居中靠右、缩进等\n\n"
            f"{'=' * 60}\n"
            + "\n\n".join(fragments)
        )


    def _merge_pages(self, pages: list[int], merge_instruction: str = "") -> str:
        try:
            if len(pages)>=self.pdfcfg.LONG_SHORT:
                output_path = self._get_processor(self.page_client_long).convert_and_merge(
                pages, merge_instruction,self.pdfcfg.LONG_THINK)
            else:
                output_path = self._get_processor(self.page_client_short).convert_and_merge(
                pages, merge_instruction,self.pdfcfg.SHORT_THINK)
            return f"合并完成，输出文件：{output_path}"
        except Exception as e:
            return f"合并失败：{e}"

    def _check_read_html(self, html_path: str = "", pages: list[int] = None) -> str:
        """仅读取 HTML 文本，返回给聊天模型自己校对。"""
        _, html = self._read_html_text(html_path, pages)
        if html is None:
            return f"文件不存在：{self._resolve_html_path(html_path, pages)}"
        return (
            "请检查 HTML 转换结果是否符合以下标准：\n"
            f"{self.FORMAT_REQUIREMENTS}\n\n"
            "如不符合以上标准请反馈给用户，有上述错误请代用户在_merge_pages附加要求发给VLM重新转换，部分细微错误经用户同意后可代用户进行基础性修改。\n"
            f"当前 HTML:\n{html}"
        )
    def _get_page_images(self, pages: list[int]) -> list:
        image_need=[] 
        for p in pages:
            image_need.append( {"type": "image_url","image_url": {"url": f"data:image/png;base64,{self.cache.get_image_b64(p)}"}})
        return image_need

    def _save_html(self, html_path: str = "", content: str = "") -> str:
        corrected = re.sub(r'^.*?```html\s*', '', content, flags=re.IGNORECASE | re.DOTALL)
        corrected = re.sub(r'\s*```.*?$', '', corrected, flags=re.DOTALL)
        Path(html_path).write_text(corrected, encoding="utf-8")
        return f"已保存：{html_path}"
    def _page_group(self)  -> str:
        pageinfo=f"{self.pg if self.pg else None}"
        vol=self.pdfcfg.VOL
        if not self.pg:
            pageinfo=f"{MEWbrief.search_page_group(vol)}"
        return f"篇目页码组："+pageinfo

    def _grep_files(
        self, keyword: str = "",
        pages: list[int] = None, html_paths: list[str] = None,
        max_hits: int = 50, is_regex: bool = False,
        CONTEXT_CHARS: int = 100, page_index: int = 0,SEARCH_PAGE_SIZE:int=10
    ) -> str:
        if not keyword:
            return "请提供搜索关键词。"
        if CONTEXT_CHARS > 250:
            return "上下文字符数不能超过 250。"

        # ── 文件列表解析 ──────────────────────────────────────────
        if html_paths:
            file_iter = []
            for hp in html_paths:
                p = Path(hp)
                if not p.exists():
                    return f"文件不存在：{hp}"
                file_iter.append(p)
        elif pages:
            file_iter = []
            for pg in pages:
                candidate = self._resolve_page_path(pg)
                if candidate is None:
                    return f"找不到页码 {pg} 对应的文件"
                file_iter.append(candidate)
        else:
            out = Path(self.cfg.OUTPUT_DIR)
            if not out.exists():
                return f"输出目录不存在：{out}"
            file_iter = sorted(out.glob("*.html"))

        effective_max = float("inf") if (pages or html_paths) else max_hits

        # ── 编译正则 ──────────────────────────────────────────────
        try:
            pattern = re.compile(
                keyword if is_regex else re.escape(keyword), re.IGNORECASE|re.DOTALL
            )
        except re.error as exc:
            return f"正则语法错误：{exc}"
        # ── 搜索 ──────────────────────────────────────────────────
        hits, collected = [], 0
        for html_file in file_iter:
            title="title标签：空"
            if collected >= effective_max:
                break
            try:
                text = html_file.read_text(encoding="utf-8", errors="ignore")
                soup = BeautifulSoup(text, "html.parser")
                t    = soup.find("title")
                title = "title：" + t.get_text(strip=True) if t else ""
            except Exception:
                continue

            file_hits = []
            for m in pattern.finditer(text):
                start = max(0, m.start() - CONTEXT_CHARS // 2)
                end   = min(len(text), m.end() + CONTEXT_CHARS // 2)
                file_hits.append(text[start:end].strip())
                collected += 1
                if collected >= effective_max:
                    break

            if file_hits:
                header = f"[{html_file.name} "+title + f" {len(file_hits)}处]"
                hits.append(header + "\n" + "\n···\n".join(file_hits))

        if not hits:
            scope = (f"「{', '.join(Path(h).name for h in html_paths)}」" if html_paths
                     else f"页码{pages}" if pages
                     else f"全卷({Path(self.cfg.OUTPUT_DIR).name})")
            return f"{scope}未找到「{keyword}」。"

        # ── 分页输出 ──────────────────────────────────────────────
        PAGE_SIZE   = SEARCH_PAGE_SIZE 
        total_pages = max(1, (len(hits) + PAGE_SIZE - 1) // PAGE_SIZE)
        page_index  = max(0, min(page_index, total_pages - 1))
        sliced      = hits[page_index * PAGE_SIZE : (page_index + 1) * PAGE_SIZE]

        header = f"共 {collected} 处命中 / {len(hits)} 个文件"
        if total_pages > 1:
            header += f" | 第 {page_index + 1}/{total_pages} 页（page_index={page_index}）"

        return header + "\n===\n" + "\n---\n".join(sliced)
    def _str_replace_html(self, old_str: str, new_str: str,
                          html_path: str = "", pages: list[int] = None,
                          merge_html: bool = False) -> str:
        pages = pages or []
        if not pages and not html_path:
            return "请明确要修改的页码或 HTML 文件！"
        path, html = self._read_html_text(html_path, pages)
        if html is None:
            return f"文件不存在：{path}"

        count = html.count(old_str)
        if count == 0:
            # 给模型看截断的上下文，方便它自查
            return (f"❌ 未找到 old_str，替换取消。\n"
                    f"old_str 前20字符：{old_str[:20]!r}\n"
                    f"请重新调用 check_read_html 确认原文后再试。")
        if count > 1:
            return (f"❌ old_str 在文件中出现 {count} 次，替换取消（存在歧义）。\n"
                    f"请在 old_str 中加入更多上下文使其唯一。")

        html = html.replace(old_str, new_str, 1)
        path.write_text(html, encoding="utf-8")
        return f"✅ 已替换并保存：{path}"
    def _regex_edit_html(self, rules: list,
                         html_path: str = "", pages: list[int] = None,
                         merge_html: bool = False) -> str:
        pages = pages or []
        path, html = self._read_html_text(html_path, pages)
        if html is None:
            return f"文件不存在：{path}"

        _flag_map = {
            "I": re.IGNORECASE, "IGNORECASE": re.IGNORECASE,
            "M": re.MULTILINE,  "MULTILINE":  re.MULTILINE,
            "S": re.DOTALL,     "DOTALL":     re.DOTALL,
        }

        results = []
        for i, rule in enumerate(rules):
            # ── 兜底：模型有时把 rule 序列化成 JSON 字符串 ──
            if isinstance(rule, str):
                try:
                    rule = json.loads(rule)
                except json.JSONDecodeError as e:
                    return f"规则{i+1} 无法解析为对象：{e}\n原始内容：{rule!r}"

            pattern     = rule["pattern"]
            replacement = rule["replacement"]
            raw_flags   = rule.get("flags", "") or ""
            flag_val    = 0
            for f in re.split(r"[,| ]+", raw_flags.upper()):
                flag_val |= _flag_map.get(f.strip(), 0)

            try:
                new_html, n = re.subn(pattern, replacement, html, flags=flag_val)
                html = new_html
                results.append(f"规则{i+1} /{pattern}/ → {n} 处替换")
            except re.error as e:
                return f"规则{i+1} 正则错误：{e}"

        path.write_text(html, encoding="utf-8")
        return f"已保存：{path}\n" + "\n".join(results)

    def _get_requirements(self)  -> str:
        return "# 转换要求：\n\n"+ Path("./prompts/convert2.md").read_text(encoding="utf-8")

    def _add_notice(self, note: str) -> str:
        with self.pdfcfg.NOTICE_FILE.open("a", encoding="utf-8") as f:
            f.write(f"- {note}\n")
        return f"已记录：{note}"

# ==================== 系统提示 ====================
def get_system_prompt(vol: int,model:str) -> str:
    pageg=""
    pageg=str(MEWbrief.page_group[vol])
    merged="""- 对 7 页及以上的页面，如你是多模态模型，则务必首先调用 get_page_images 根据段落特征帮助用户制订一个好的分组，让用户可以在后期用程序机械拼接转换的页面，保证跨页段落不被打断。
  - **只需且必须保证**：
    - 把跨页段落，尤其是有句子刚好在某一页页尾结束（句号、感叹号、括号、引号等在页尾正文处与页边无留白）、即后一页首行无缩进的段落（行首与页边无留白），分到同一个 merge_pages 进行转换，每一组页面在 4 个以下。
    - 如果 4 页及以下的切分无法涵盖所有跨页段落，那么优先保证上述句子完成在页尾、下页首行无缩进的跨页段落被分到一个 merge_pages中去，其余由用户自行在后期进行合并。
  - 用户也可以要求你仅返回分组方案，此时应将分组方案输出为与页码组相同的数组，制定分组时每次阅读页面不要超过4个！"""
    if model not in ["MiniMax-M2.7","deepseek-v4-flash","stepfun-ai/step-3.5-flash","nvidia/nemotron-3-super-120b-a12b","deepseek-ai/DeepSeek-V4-Flash"]:
        merged2="""- 对 7 页及以上的页面，如你是多模态模型，则务必首先调用 get_page_images 对待输入的图片进行分组，一组不超过4个，保证每个分组最后一页的正文最后一行末尾是空白即段落结束、或是字母即词组明显未完成。用户也可以要求你仅返回分组方案，此时应将分组方案输出为与页码组相同的数组"""
    requirements=Path("./prompts/convert2.md").read_text(encoding="utf-8")
    if vol in range(23,26):
        requirements=Path("./prompts/convert23.md").read_text(encoding="utf-8")
    systemp=f"""你是一个 PDF 转换助手，可以通过工具将 PDF 页面转换为高质量的 HTML。

# 🛠️ 可用工具：

- merge_pages: 将多个 PDF 页面发给其他 VLM 模型合并为一个 HTML 文件
- add_notice: 记录转换过程中的问题
- check_read_html：获取并检查转换后的 HTML 文本
- save_html：保存修改后的HTML
- page_group：查看PDF各篇目的页码组
- grep_file：搜索转换后的 HTML 文件
- table_content：通过目录表数组查看正确的标题层级及所对应页码，通过标题所在页码页码查找对应页码组及文件。

# 📌 使用策略：

- 用户说"把第 2 到 5 页转成 HTML"，则调用 merge_pages(pages=[2,3,4,5])
- 用户输入多个页码或页码范围，务必严格对照下述篇目的页码组检查，如用户输入页码与分组不符时应询问用户，确认是否跳过部分页面，如用户同意则跳过
- 在确定用户要求的页码范围的篇目划分后，务必按组转换各篇目，即将各组相应页面分入多个 merge_pages 交由其他模型排版，应先发页数较多的请求，不确定页码组的时候应调用函数page_group查对
- 用户要求从某页的某个标题开始到其他页某个标题结束，则应严格按照用户要求，仅识别并转换某个标题开始至另个标题结束前的内容，不可缺漏，不可多余
- 用户也可要求对特定内容格式批量进行修改，如更正标题层级、插入特定标签等，此时可以调用 grep_file 利用需修改的关键词与对应格式标签进行检索，检索后调用有关替换工具对内容进行替换
- 可调用 table_content 查看文件的标题层级是否正确，如不正确请代用户修改。如用户要求检查、修改已转换的文件标题层级是否正确，则首先通过关键词检索标题对应文件的上下文及标签来检查、找到应替换内容，标题不仅可能在<h[1-6]>中，也可能在<p align="center">标签中，搜索时应注意随情况调整，未查到时阅读全文。转换包含标题的页码组时也可指示 VLM 将对应标题转换为目录表中的特定样式。
- 检查注释时可通过以下几个特征判断异常：
  - 各类注释编号不连续，如 A/F/M/E 为前缀的 id 数字在同一文件中出现一个异常大的编号数字插在小编号之前
  - F 后数字 2 位数以上，A 后数字 4 位数以上
  - aside 栏中脚注内容在语义上不完整，如仅以单词结尾或逗号结尾等
  有异常时务必向用户反馈！
"""
    if model=="MiniMax-M2.7":
        systemp+="- 用户也可以要求按组转换，如自第几页开始后几组，包含某几页的某几组，或转换某组之后的几组，此时应查对下方的页码组，同样按组转换。不要擅自合并分组，严格按组进行转换！"
    systemp+="""
# 转换与合并HTML的要求
"""+requirements
    systemp+=f"""
# 各篇目页码组：

{pageg}
除用户要求按标题层级输出或用户同意跳过部分页面外，严格按照页码组转换！
"""
    return systemp

# ==================== Agent ====================
class Agent:

    def __init__(self, general_cfg: Config, chat_client: VLMClient,
                 tool_handler: ToolHandler):
        self.cfg        = general_cfg
        self.client     = chat_client
        self.tools      = tool_handler
        self._interrupt = chat_client._interrupt
        self._cancel=chat_client._cancel

    def run(self, user_input: str, history: list,
            show_tools: bool, enable_think: bool) -> AgentResult:
        system   = get_system_prompt(self.cfg.VOL,self.cfg.MODEL)
        messages = [{"role": "system", "content": system},
                    *history,
                    {"role": "user", "content": user_input}]
        try:
            msg = self.client.chat_loop(
                messages, self.tools.tools, self.tools,
                max_rounds=self.cfg.MAX_ROUNDS,
                show_tools=show_tools,enable_think=enable_think)
        except KeyboardInterrupt:
            self._interrupt.clear()
            self.client._cancel.clear()
            partial= [m for m in messages if m.get("role") != "system"]
            return AgentResult(AgentSignal.PAUSE, history=partial)
        except RuntimeError as e:
            partial= [m for m in messages if m.get("role") != "system"]
            return AgentResult(AgentSignal.ANSWER, answer=f"错误：{e}", history=partial)

        new_history = [m for m in messages if m.get("role") != "system"]
        return AgentResult(AgentSignal.ANSWER,
                           answer=msg.get("content", ""), history=new_history)

# ==================== 应用控制器 ====================
class AppController:

    def __init__(self, cfg: Config, interrupt: threading.Event, agent: Agent,DEFAULT_CHAT_THINK:bool,cancel_all:Optional[list[threading.Event]]):
        self.cfg        = cfg
        self._interrupt = interrupt
        self._agent     = agent
        self.show_tools = True
        self.enable_think =DEFAULT_CHAT_THINK
        self.history    = []
        self.cancel_all=cancel_all or []

    def run(self):
        self._register_sigint()
        try:
            while True:
                self._print_banner()
                user_input = self._read_input()
                if user_input is None or user_input.lower() == "q":
                    break
                if user_input.lower() == "n":
                    self.history = []
                    print("[新对话开始]\n")
                    continue
                if user_input.lower() == "d":
                    self.history = []
                    self.enable_think=not self.enable_think
                    print("[思考模式：开启]\n" if self.enable_think else "[思考模式：关闭]\n")
                    continue
                self._run_agent(user_input)
        finally:
            if self.cancel_all:
                for cancel in self.cancel_all:
                    cancel.set()
            print("[再见]")

    def _register_sigint(self):
        def handler(sig, frame):
            if self._interrupt.is_set():
                raise KeyboardInterrupt
            self._interrupt.set()
        signal.signal(signal.SIGINT, handler)

    def _read_input(self) -> Optional[str]:
        try:
            return input("请输入指令：").strip()
        except (EOFError, KeyboardInterrupt):
            return None

    def _run_agent(self, user_input: str):
        result = self._agent.run(user_input, self.history,
                                 self.show_tools,self.enable_think)
        self.history = result.history
        if result.answer:
            print(f"\n{result.answer}\n{'─'*55}\n")

    def _print_banner(self):
        print("PDF 转换助手（自然语言控制）")
        print("  t 工具显示  d 思考模式  n 新对话  q 退出")
        print("  Ctrl+C 中止当前操作\n")

# ==================== 入口（统一配置） ====================
def main():
    # ── 🖼️ 页面转换模型（VLM，负责看图转 HTML）────────────────
    cfg=PDF_CONVERT_Config()
    parser = argparse.ArgumentParser(description="文献查询系统")
    parser.add_argument("-v","--vol",type=int,help="卷号")
    parser.add_argument("-l","--long-short",type=int,help="长短分界")
    parser.add_argument("-c","--MAX-CONCURRENT",type=int,help="最大线程")
    args = parser.parse_args()
    cfg.VOL= args.vol if args.vol else 37
    if cfg.VOL not in range(261,264):
        cfg.CACHE_DIR= f"cache_images{cfg.VOL}"
        cfg.OUTPUT_DIR= f"./MEW_BRIEF/{cfg.VOL}"
        pdf_path = r"D:\马恩列总装\马恩全集德文\mew_band" + f"{cfg.VOL:02d}.pdf"
    if cfg.VOL==261:
        cfg.CACHE_DIR= r"cache_images26_1"
        cfg.OUTPUT_DIR= r"./MEW_BRIEF/261"
        pdf_path = r"D:\马恩列总装\马恩全集德文\mew_band26_1.pdf"
    if cfg.VOL==262:
        cfg.CACHE_DIR= r"cache_images26_2"
        cfg.OUTPUT_DIR= r"./MEW_BRIEF/262"
        pdf_path = r"D:\马恩列总装\马恩全集德文\mew_band26_2.pdf"
    if cfg.VOL==263:
        cfg.CACHE_DIR= r"cache_images26_3"
        cfg.OUTPUT_DIR= r"./MEW_BRIEF/263"
        pdf_path = r"D:\马恩列总装\马恩全集德文\mew_band26_3.pdf"
    if not Path(pdf_path).is_file():
        print(f"❌ PDF 文件不存在: {pdf_path}")
        return
    # ── 初始化路径 ─────────────────────────────────────────────
    cfg.DPI= 150
    cfg.MAX_ROUNDS= 300
    notice_file= Path(cfg.CACHE_DIR) / "NOTICE.md"
    cfg.NOTICE_FILE = notice_file
    Path(cfg.OUTPUT_DIR).mkdir(exist_ok=True)
    Path(cfg.CACHE_DIR).mkdir(exist_ok=True)
    if not notice_file.exists():
        notice_file.write_text("", encoding="utf-8")
    MAX_CONCURRENT=args.MAX_CONCURRENT if args.MAX_CONCURRENT else 2
    MS=API_SERVERICE("https://api-inference.modelscope.cn/v1/chat/completions","ms-...")
    NIM=API_SERVERICE("https://integrate.api.nvidia.com/v1/chat/completions","nvapi-...")
    BL=API_SERVERICE("https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions","sk-...")
    CT=API_SERVERICE("https://wishub-x6.ctyun.cn/v1/chat/completions","")
    MM=API_SERVERICE("https://api.minimaxi.com/v1/text/chatcompletion_v2","")
    MIS=API_SERVERICE("https://api.mistral.ai/v1/chat/completions","")
    GLM=API_SERVERICE("https://open.bigmodel.cn/api/paas/v4/chat/completions","")
    MI=API_SERVERICE("https://api.xiaomimimo.com/v1/chat/completions","sk-...")
    OR=API_SERVERICE("https://openrouter.ai/api/v1/chat/completions","sk-...")
    MON=API_SERVERICE("https://api.kimi.com/coding/v1/chat/completions","sk-...")
    DS=API_SERVERICE("https://api.deepseek.com/chat/completions","sk-...")
    cfg.LONG_SHORT=args.long_short if args.long_short else 1
    cfg.LONG_THINK=True
    cfg.SHORT_THINK=True
    cfg.DEFAULT_CHAT_THINK=True
    page_cfg=Config(BL,cfg,True,MAX_CONCURRENT,"enable_thinking")
    page_cfg.MODEL= "qwen3.5-plus"

    #page_cfg_long=Config(GLM,cfg,False,MAX_CONCURRENT,"thinking")
    #page_cfg_long=Config(NIM,cfg,True,MAX_CONCURRENT,"chat_template_kwargs")
    #page_cfg_long=Config(MIS,cfg,True,MAX_CONCURRENT,"reasoning_effort")
    #page_cfg_long=Config(MI,cfg,True,MAX_CONCURRENT,"thinking")
    #page_cfg_long.MODEL="mistral-medium-latest"
    #page_cfg_long=page_cfg
    page_cfg_long=Config(MS,cfg,True,MAX_CONCURRENT, "enable_thinking")
    #page_cfg_long=Config(MON,cfg,True,MAX_CONCURRENT,"thinking")
    #page_cfg_long=Config(NIM,cfg,True,MAX_CONCURRENT,"reasoning_effort")
    #page_cfg_long.MODEL= "qwen3.5-plus"
    #page_cfg_long.MODEL= "qwen3.6-plus"
    #page_cfg_long.MODEL= "mimo-v2.5"
    #page_cfg_long.MODEL="qwen/qwen3.6-plus-preview:free"
    #page_cfg_long.MODEL= "qwen/qwen3.5-397b-a17b"
    #page_cfg_long.MODEL= "qwen/qwen3.5-27b"
    #page_cfg_long.MODEL= "glm-4.6v-flash"
    #page_cfg_long.MODEL= "mistralai/mistral-medium-3.5-128b"
    #page_cfg_long.MODEL= "mistral-medium-2604"
    page_cfg_long.MODEL= "moonshotai/Kimi-K2.5"
    #page_cfg_long.MODEL="Shanghai_AI_Laboratory/Intern-S1-Pro"
    
    #page_cfg_long.MODEL="kimi-code/kimi-for-coding"
    #page_cfg_long.MODEL="Kimi-K2.5"
    page_cfg_long.TIMEOUT=httpx.Timeout(connect=10.0, read=900.0, write=120.0, pool=10.0)

    #page_cfg_long.MODEL= "Qwen3.5-397B-A17B"
    #page_cfg.MODEL= "qwen/qwen3-VL-235B-A22B-thinking-2507"
    #page_cfg.MODEL= "mistralai/mistral-small-4-119b-2603"
    #page_cfg_long.MODEL="moonshotai/Kimi-K2.5"
    page_cfg_long.TEMPERATURE=0.8
    #page_cfg_long.TEMPERATURE=1
    #page_cfg_long.THINK_TYPE= "chat_template_kwargs"
    #page_cfg_long.THINK_TYPE= "extra_body"

    page_cfg_short=Config(MS,cfg,True,MAX_CONCURRENT,"enable_thinking")
    #page_cfg_short=Config(CT,cfg,True,MAX_CONCURRENT,"enable_thinking")
    #page_cfg_short=Config(MON,cfg,True,MAX_CONCURRENT,"thinking")
    #page_cfg_short.MODEL="Kimi-K2.5"
    #page_cfg_short=Config(NIM,cfg,True,MAX_CONCURRENT,"chat_template_kwargs")
    #page_cfg=Config(NIM,cfg,True,MAX_CONCURRENT)
    #page_cfg_short.MODEL= "qwen3.5-plus"
    page_cfg_short.MODEL= "qwen/qwen3.5-397b-a17b"
    #page_cfg_short.MODEL= "qwen/qwen3.5-122b-a10b"
    #page_cfg_short.MODEL= "moonshotai/kimi-k2.5"
    #page_cfg_short.MODEL="fde2b0a897b140bda7909861ed734671"
    #page_cfg_short.MODEL= "qwen/qwen3-vl-235b-a22b-thinking-2507"
    #page_cfg.MODEL= "mistralai/mistral-small-4-119b-2603"
    #page_cfg_short.MODEL= "mistralai/mistral-large-3-675b-instruct-2512"
    #page_cfg_short.THINK_TYPE= "extra_body"
    #page_cfg_short.MODEL="MiniMax-M2.7"
    #page_cfg_short.THINK_TYPE= "thinking"
    if page_cfg_short.API_URL=="https://wishub-x6.ctyun.cn/v1/chat/completions":
        page_cfg_short.MAX_TOKENS=16383
    #page_cfg_short.TEMPERATURE=1
    page_cfg_short.TEMPERATURE=0.8
    #page_cfg_short.THINK_TYPE= "reasoning_effort"

    # ── 💬 聊天调度模型（负责解析用户指令、调用工具）──────────
    #chat_cfg=Config(MS,cfg,False,MAX_CONCURRENT,"enable_thinking")
    #chat_cfg=Config(MS,cfg,False,MAX_CONCURRENT,"thinking")
    #chat_cfg=Config(NIM,cfg,False,MAX_CONCURRENT,"reasoning_effort")
    #chat_cfg=Config(MM,cfg,False,MAX_CONCURRENT,"thinking")
    #chat_cfg=Config(MS,cfg,False,MAX_CONCURRENT,"enable_thinking")
    #chat_cfg=Config(MS,cfg,False,MAX_CONCURRENT,"reasoning_effort")
    chat_cfg=Config(DS,cfg,False,MAX_CONCURRENT,"thinking")
    #chat_cfg.MODEL= "qwen/qwen3.5-397b-a17b"
    #chat_cfg.MODEL= "qwen/qwen3.5-122b-a10b"
    #chat_cfg.THINK_TYPE= "chat_template_kwargs"
    #chat_cfg.MODEL= "mistralai/mistral-small-4-119b-2603"
    #chat_cfg.MODEL="stepfun-ai/step-3.5-flash"
    chat_cfg.MODEL="deepseek-v4-flash"
    #chat_cfg.MODEL="deepseek-ai/DeepSeek-V4-Flash"
    #chat_cfg.MODEL="nvidia/nemotron-3-super-120b-a12b"
    #chat_cfg.TIMEOUT=httpx.Timeout(connect=10.0, read=43200.0, write=120.0, pool=10.0)
    #chat_cfg.MODEL="MiniMax-M2.7"
    chat_cfg.TEMPERATURE=1
    LLM=True
    #chat_cfg.THINK_TYPE= "chat_template_kwargs"
    interrupt = threading.Event()
    cancell= threading.Event()
    cancels= threading.Event()
    cancelc= threading.Event()

    # ── 创建两个独立客户端，各持自己的 cfg ────────────────────
    page_client_long = VLMClient(page_cfg_long, interrupt,cancell)   # 🖼️ 页面转换
    page_client_short= VLMClient(page_cfg_short, interrupt,cancels)   # 🖼️ 页面转换
    chat_client = VLMClient(chat_cfg, interrupt,cancelc)   # 💬 聊天调度
    # ── 组件组装（通用配置统一从 chat_cfg 读）─────────────────
    image_cache  = ImageCache(pdf_path, chat_cfg.CACHE_DIR, chat_cfg.DPI)
    no_llm = {"get_page_images"} if LLM else None
    selected_tools = [
    tool for tool in ToolHandler.ALL_TOOLS
    if tool["function"]["name"] not in no_llm 
]
    tool_handler = ToolHandler(
        cache=image_cache,
        page_client_long=page_client_long,
        page_client_short=page_client_short,
        pdf_cfg=cfg,use_tools=selected_tools
    )

    agent = Agent(chat_cfg, chat_client, tool_handler)
    controller = AppController(chat_cfg, interrupt, agent,cfg.DEFAULT_CHAT_THINK,[cancell,cancels,cancelc])
    cache_clear=False

    # ── 缓存清理询问 ───────────────────────────────────────────
    if image_cache.cache_dir.exists() and any(image_cache.cache_dir.iterdir()) and cache_clear:
        if input("⚠️  缓存目录已有图片，是否删除？(y/N): ").strip().lower() == "y":
            image_cache.clear_cache()

    controller.run()

if __name__ == "__main__":
    main()