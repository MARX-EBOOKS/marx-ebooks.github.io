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
        self.HTML_MERGE_DIR   =PDF_CONFI.HTML_MERGE_DIR
        self.DPI            =PDF_CONFI.DPI
        self.RASTER_WORKERS =PDF_CONFI.RASTER_WORKERS
        self.MAX_CONCURRENT = MAX_CONCURRENT
        # ── 缓存相关 ──────────────────────────────────────────
        self.ENABLE_EXPLICIT_CACHE =ENABLE_EXPLICIT_CACHE
        self.LONG_SHORT =PDF_CONFI.LONG_SHORT
        self.TIMEOUT = httpx.Timeout(connect=10.0, read=900.0, write=120.0, pool=10.0)
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
            "thinking_level":     "high" if ENABLE_THINK else "off",
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
    HTML_MERGE_DIR=""
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

    def __init__(self, cfg: Config, interrupt: threading.Event):
        self.cfg        = cfg
        self._interrupt = interrupt
        self._sem       = threading.Semaphore(cfg.MAX_CONCURRENT)
        self._cancel    =threading.Event()
        self._headers   = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {cfg.API_KEY}",
            #"User-Agent":    "RooCode/3.51.0",
            #"User-Agent":    "claude-code/2.1.87",
            "User-Agent":    "opencode/1.14.31",
        }
        self.prompt_usage = 0
        self._usage_lock  = threading.Lock()

    def _build_payload(self, messages: list, tools: Optional[list] = None,
                       enable_cache: bool = True, enable_think: bool = False) -> dict:
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
            if self.cfg.THINK_TYPE == "enable_thinking":
                payload["top_k"] = 20

        # 🔥 新增：历史记录缓存 - 对最后一个消息添加 cache_control
        
        return payload
        """if enable_cache and self.cfg.ENABLE_EXPLICIT_CACHE and self.cfg.API_URL in self.cfg.SUPPORT_CACHE and len(messages)>4:
            last_msg = messages[-1]
            content = last_msg.get("content")
            # 情况1: content 是纯字符串
            if isinstance(content, str) and len(content) >= self.cfg.CACHE_MIN_TOKENS:
                last_msg["content"] = [{
                    "type": "text",
                    "text": content,
                    "cache_control": {"type": "ephemeral"}
                }]
            # 情况2: content 是列表（多模态），找最后一个 text 项
            elif isinstance(content, list):
                for item in reversed(content):
                    if item.get("type") == "text" and len(item.get("text", "")) >= self.cfg.CACHE_MIN_TOKENS:
                        item["cache_control"] = {"type": "ephemeral"}
                        break"""
    
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
            m = re.search(r"<(?:think|thought)>(.*?)</(?:think|thought)>", content, re.DOTALL)
            if m:
                thinking       = m.group(1).strip()
                msg["content"] = re.sub(r"<(?:think|thought)>.*?</(?:think|thought)>\s*", "", content,
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
        content = [{"type": "text", "text": prompt}]
        content.append({"type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"}}
                   for b64 in images_b64)
        return [{"role": "user", "content": content}]

    def _request_with_retry(self, payload: dict, validate_fn=None) -> httpx.Response:
        attempt = 0
        last_error = None
        
        while True:
            try:
                resp = self._do_request(payload)
                
                # 1. 优先检查 HTTP 状态码
                if resp.status_code >= 400:
                    error_msg = f"[HTTP {resp.status_code}] {resp.text[:300]}"
                    print(error_msg)
                    last_error = RuntimeError(error_msg)
                    # 可重试的状态码
                    if resp.status_code in self._RETRY_STATUS and attempt < self.cfg.MAX_RETRIES - 1:
                        wait = random.uniform(self.cfg.RETRY_WAIT, self.cfg.RETRY_WAIT + attempt)
                        print(f"  └─ 等待 {wait:.1f}s 后重试 ({attempt+1}/{self.cfg.MAX_RETRIES})")
                        self._sleep_interruptible(wait)
                        attempt += 1
                        continue
                    # 不可重试的错误（如 401/403）
                    raise last_error
                
                # 2. 执行自定义验证函数
                if validate_fn is not None:
                    try:
                        if not validate_fn(resp):
                            raise RuntimeError("响应验证未通过（内容/格式不符合预期）")
                    except json.JSONDecodeError as e:
                        # JSON 解析失败也视为可重试错误
                        last_error = e
                        if attempt < self.cfg.MAX_RETRIES - 1:
                            wait = random.uniform(self.cfg.RETRY_WAIT, self.cfg.RETRY_WAIT + attempt)
                            print(f"  └─ JSON解析失败，等待 {wait:.1f}s 重试 ({attempt+1}/{self.cfg.MAX_RETRIES})")
                            self._sleep_interruptible(wait)
                            attempt += 1
                            continue
                        raise
                
                # 3. 验证通过，返回响应
                return resp
                
            except httpx.RequestError as e:
                # 网络层错误（超时、连接失败等）
                last_error = e
                print(f"[网络错误] {type(e).__name__}: {e}")
                if attempt < self.cfg.MAX_RETRIES - 1:
                    wait = random.uniform(self.cfg.RETRY_WAIT, self.cfg.RETRY_WAIT + attempt)
                    print(f"  └─ 等待 {wait:.1f}s 后重试 ({attempt+1}/{self.cfg.MAX_RETRIES})")
                    self._sleep_interruptible(wait)
                    attempt += 1
                    continue
                raise
            except KeyboardInterrupt:
                # 用户中断，立即退出
                raise
            except Exception as e:
                # 其他未知错误
                last_error = e
                print(f"[未知错误] {type(e).__name__}: {e}")
                if attempt < self.cfg.MAX_RETRIES - 1:
                    wait = random.uniform(self.cfg.RETRY_WAIT, self.cfg.RETRY_WAIT + attempt)
                    self._sleep_interruptible(wait)
                    attempt += 1
                    continue
                raise
        
        # 理论上不会执行到这里
        raise last_error or RuntimeError("请求失败且重试耗尽")
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
             enable_cache: bool = True, enable_think: bool = False) -> dict:
        """
        发送聊天请求并解析响应（带健壮的错误处理）
        """
        payload = self._build_payload(messages, tools, enable_cache, enable_think)
        
        # 安全的验证函数：捕获所有可能的解析异常
        def safe_validate(r: httpx.Response) -> bool:
            try:
                # 1. 检查响应是否为空
                if not r.content:
                    print(f"[验证失败] 响应内容为空，状态码: {r.status_code}")
                    return False
                # 2. 尝试解析 JSON
                data = r.json()
                # 3. 检查关键字段
                if not data or not isinstance(data, dict):
                    print(f"[验证失败] 响应不是有效的对象: {r.text[:200]}")
                    return False
                # 4. 检查 choices 字段
                choices = data.get("choices")
                if not choices:
                    print(f"[验证失败] 响应缺少 'choices' 字段: {data.keys()}")
                    return False
                return True
            except json.JSONDecodeError as e:
                # 记录原始响应内容便于调试
                content_type = r.headers.get("content-type", "unknown")
                print(f"[JSON解析失败] 状态码: {r.status_code}, Content-Type: {content_type}")
                print(f"[原始响应预览] {r.text[:500]}")
                return False
            except Exception as e:
                print(f"[验证函数异常] {type(e).__name__}: {e}")
                return False
        
        # 执行带重试的请求
        resp = self._request_with_retry(payload, validate_fn=safe_validate)
        
        # 解析并返回结果（此处已确认是有效 JSON）
        return self._parse_response(resp.json(), tools)

    def chat_loop(self, messages: list, tools: list, tool_handler=None,
                  max_rounds: int = 300, show_tools: bool = False,
                  enable_think: bool = False, enable_cache: bool = True) -> dict:
        empty_retry = 0
        for _ in range(max_rounds):
            msg        = self.chat(messages, tools=tools or None, enable_cache=enable_cache,enable_think=enable_think)
            tool_calls = msg.get("tool_calls") or []

            if msg.get("_thinking"):
                text = msg["_thinking"][:25000]+"..." if len(msg["_thinking"])>25000 else msg["_thinking"]
                print(f"\n  ┌─[思考]{'─'*50}")
                for line in text.splitlines():
                    print(f"  │ {line}")
                print(f"  └{'─'*52}")

            if not tool_calls and not msg.get("content"):
                empty_retry += 1
                if empty_retry <= self.cfg.MAX_RETRIES:
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
                if isinstance(result, list) and "google" in self.cfg.API_URL:
                    messages.append({
            "role": "tool",
            "tool_call_id": tc.get("id", ""),
            "content": "Successfully retrieved and upload requested images. See in following user's message."
        })
                    messages.append({
            "role": "user",
            "content": result   # 含 image_url 的 list 放到 user 消息
        })
                else:
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
# ==================== 工具处理器 ====================
class ToolHandler:

    ALL_TOOLS = [
        {"type": "function", "function": {
            "name": "check_read_html",
            "description": (
                "读取已生成的 HTML 文件文本，由你直接审阅。"
                "适合纯文本层面校对：拼写、标签闭合、脚注编号、双向链接、跨页合并、标题层级等。"
                "如发现错误请告知用户，经同意后调用 save_html 保存修改结果。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "html_path": {"type": "string", "description": "HTML 文件路径，为空则按 pages[0] 自动推断",
                                  "default": ""},
                    "pages": {"type": "array", "items": {"type": "integer"},
                              "description": "对应的原始页码列表，用于自动推断路径"},
                    "check": {"type": "boolean", "description": "是否进行检查，默认不检查即False。","default":False},
                    "merge_html":{"type": "boolean", "description": "同时阅读多个 HTML 开关，默认False。","default":False}
                },
                "required": ["pages"]
            }
        }},
        {"type": "function", "function": {
            "name": "get_page_images",
            "description": "获取指定 PDF 页面的原始图片，由你直接查看。用于直接转换PDF页面，也可配合 check_read_html 对照校对。如果你是MiniMax、Stepfun等LLM，不要用这个函数！",
            "parameters": {
                "type": "object",
                "properties": {
                    "pages": {"type": "array", "items": {"type": "integer"},
                              "description": "要查看的页码列表，不要超过 8 个页面！分批读取时务必按批次分析版面！"}
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
            "name":"save_html_by_page_num",
            "description": "按首页页码保存 HTML 文件（用于保存转换结果）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pages": {"type": "array", "items": {"type": "integer"},
                              "description": "要保存的页码列表"},
                    "content":   {"type": "string", "description": "待保存的 HTML 内容"},
                    "temp":{"type": "boolean", "description": "是否将文件保存到临时目录以待之后合并，默认 False 即不保存临时文件。","default":False}
                },
                "required": ["pages", "content"]
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
        }}
        ,
        {"type": "function", "function": {
            "name": "get_requirements",
            "description": "在用户反馈异常时查看重新对照转换要求",
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
                                "pattern":     {"type": "string", "description": "Python 中有效的正则表达式，如有捕获组应写作\1、\2等"},
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
                "调用目录表数组，字符串为应转换的标题文本及层级标签，整数为对应页码。"
            ),
            "parameters": {
            "type": "object", 
            "properties": {}
            }
        }
        }
    ]

    def __init__(self, cache: ImageCache,cfg: Config,
                 use_tools: Optional[list] = None):
        self.cache       = cache
        self.cfg         =cfg
        self.tools       = use_tools if use_tools is not None else self.ALL_TOOLS
        self.pg=MEWbrief.page_group[cfg.VOL]
        self._dispatch = {
            "check_read_html":self._check_read_html,
            "get_page_images": self._get_page_images,
            "save_html":      self._save_html,
            "save_html_by_page_num":      self._save_html_by_page_num,
            "add_notice":     self._add_notice,
            "page_group":self._page_group,
            "get_requirements":self._get_requirements,
            "regex_edit_html": self._regex_edit_html,
            "str_replace_html": self._str_replace_html,
            "grep_files":self._grep_files,
            "table_content":self._table_content,
        }
        self.FORMAT_REQUIREMENTS = self.get_format_requirements(cfg.VOL)
        self._page_to_group_start: dict[int, int] = {
    pg: group[0]
    for group in self.pg
    if isinstance(group, (list, tuple))
    for pg in group
}
    def _table_content(self):
        vol=self.cfg.VOL
        return "请按用户要求与指示核对标题！字符串为应转换的标题文本及层级标签，整数为对应页码。\n目录表："+str(MEWbrief.inhalt[vol]) if MEWbrief.inhalt[vol] else "目录为空，请用户检查目录！"
    def get_format_requirements(self,vol):
        FORMAT_REQUIREMENTS=Path("./prompts/convert2.md").read_text(encoding="utf-8")
        if vol in range(23,26):
            FORMAT_REQUIREMENTS=Path("./prompts/convert23.md").read_text(encoding="utf-8")
        return FORMAT_REQUIREMENTS
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

    def _read_html_text(self, html_path: str, pages: list[int], merge_html: bool) -> tuple[Path, str]:
        """共用 helper：解析路径并读取 HTML 文本。"""
        path = self._resolve_html_path(html_path, pages, merge_html=merge_html)
        try:
            return path, path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return path, None
    def _get_requirements(self) -> str:
        FORMAT_REQUIREMENTS=self.FORMAT_REQUIREMENTS
        if self.cfg.MODEL.lower() not in ["qwen3.5-plus"]:
            FORMAT_REQUIREMENTS2=self.FORMAT_REQUIREMENTS+"""
## 合并或重排 HTML 注意事项

在上述转换要求的基础上，还应注意以下细节：
  - 合并或重排时，务必保证脚注链接样式符合转换格式要求，脚注id编号统一计数、连续、上下文一致。作者注与编者注的计数、编号体系相互独立，如果作者注（M1、L1、E1等）与编者注（F1等）未分栏则应分到两个aside内输出，保证作者注栏放在上，编者注栏在下。
  - 合并各页 HTML 的跨页段落<p>标签时，务必删去多余连字符或加回空格使原段落完整。合并跨页段落时首先根据上下文判断，如页尾有连字符或语句未完成时则明显应合并，如页尾段落后有空格则不应合并。仅在句子刚好在页尾完成且段末无空格时调用 get_page_images 参考图片判断是否合并，因此一次调用图片不要超过两个。
  - 合并或重排时，务必同时根据语义和页面图像修正标题标签的层级，特别是前期各页 HTML 分页转换时误将标题识别为普通 p 标签的文本，应修复为正确的标题标签、标题层级。
  - 合并或重排的过程中还应注意检查其他文本内容、样式、排版的问题，如有严重错误影响可读性时，则应向用户反馈，由用户决定是否修改、重新转换。
  - 对 Marx 的手稿，应留意手稿页码格式是否正确，如发现手稿页码被[]包裹，不要将其误认为书末注释编号！可根据图像修正格式。"""
        return "按以下要求转换有关 PDF 页面或检查有关 HTML 的质量\n"+FORMAT_REQUIREMENTS


    def _check_read_html(self, html_path: str = "", pages: list[int] = None,check:bool=False,merge_html:bool=False) -> str:
        """仅读取 HTML 文本，返回给聊天模型自己校对。"""
        _, html = self._read_html_text(html_path, pages,merge_html)
        if html is None:
            return f"文件不存在：{self._resolve_html_path(html_path, pages,merge_html)}"
        if merge_html:
            HTML=""
            for p in pages:
                _, htmlp = self._read_html_text("",[p],merge_html)
                HTML+=f"\n\n<!-- Page {p} -->\n\n"+htmlp
            return ( "请按要求批量处理 HTML\n\n"

            f"各 HTML:\n{HTML}"
            )


        if check:
            return ("请检查 HTML 转换结果是否有以下问题：\n"
                "1. 拼写错误\n"   
                "2. 跨页段落转换错误，尤其是本应都是引用blockquote中的内容却被分到不同段落，或在语义连续却突然分段的情况，乃至完整单词出现连字符后突然换段\n"
                "3. 脚注上标编号与内容不对应，脚注未按条目分段\n"
                "4. 双向链接 id/href 不正确，存在方括号[]包裹的书末注释编号\n"
                "5. 斜体、粗体、居中、靠右等格式在语义上不正确，标题层级错误，部分标题被当做p（居中标签）识别\n"
                "6. HTML 代码格式错误，如标签未闭合、嵌套错误等\n"
            
            "如有错误请反馈给用户，在用户明确指出修改后请调用 get_page_images 查对页面图像修复拼写、标题层级、方括号书末注释编号、段落错误划分等问题，一次调用不超过两个图片。\n\n"
            f"当前文件 HTML:\n{html}"
            )
        return (
            "请按要求处理转换后的HTML！\n"
            f"当前文件 {self._resolve_html_path(html_path, pages,merge_html)}:\n{html}"         
        )

    def _get_page_images(self, pages: list[int]) -> list:
        image_need=[] 
        text_4=""
        for pnum,p in enumerate(pages):
            image_need.append( {"type": "image_url","image_url": {"url": f"data:image/png;base64,{self.cache.get_image_b64(p)}"}})
            if pnum==8:
                text_4="一次请求的页数不要超过8页！目前返回前8页！查看后续页码请另行调用本函数！"
                break
        image_need.append({"type":"text","text":f"请按要求转换该组页面，转换后务必自动调用 _save_html_by_page_num 保存，如忘记转换要求务必调用 _check_read_html 和 _get_requirements 重新对照要求检查！{text_4}"})
        return image_need
    def _save_html_by_page_num(self,pages: list[int], content: str = "",temp:bool=False) -> str:
        corrected = re.sub(r'^.*?```html\s*', '', content, flags=re.IGNORECASE | re.DOTALL)
        corrected = re.sub(r'\s*```.*?$', '', corrected, flags=re.DOTALL)
        html_path=self._resolve_html_path("",pages,temp)
        Path(html_path).write_text(corrected, encoding="utf-8")
        return f"已保存：{html_path}"
    def _save_html(self, html_path: str = "", content: str = "") -> str:
        corrected = re.sub(r'^.*?```html\s*', '', content, flags=re.IGNORECASE | re.DOTALL)
        corrected = re.sub(r'\s*```.*?$', '', corrected, flags=re.DOTALL)
        if not Path(html_path).parent.exists():
            Path(html_path).parent.mkdir(parents=True, exist_ok=True)
        Path(html_path).write_text(corrected, encoding="utf-8")
        return f"已保存：{html_path}"
    def _page_group(self)  -> str:
        return f"篇目页码组：{self.pg}"
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
                header = "["+str(html_file)+" "+title + f" {len(file_hits)}处]"
                hits.append(header + "\n" + "\n···\n".join(file_hits))

        if not hits:
            scope = (f"「{', '.join(Path(h).name for h in html_paths)}」" if html_paths
                     else f"页码{pages}" if pages
                     else f"全卷({Path(self.cfg.OUTPUT_DIR).name})")
            return f"{scope}未找到「{keyword}」，请调整关键词。"

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
        path, html = self._read_html_text(html_path, pages, merge_html)
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
        path, html = self._read_html_text(html_path, pages, merge_html)
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

    def _add_notice(self, note: str) -> str:
        with self.cfg.NOTICE_FILE.open("a", encoding="utf-8") as f:
            f.write(f"- {note}\n")
        return f"已记录：{note}"

# ==================== 系统提示 ====================
def get_system_prompt(vol: int,Model:str) -> str:
    FORMAT_REQUIREMENTS = Path("./prompts/convert2.md").read_text(encoding="utf-8")
    if "gemma" in Model.lower():
        FORMAT_REQUIREMENTS = Path("./prompts/convert2en.md").read_text(encoding="utf-8")
    if vol in range(23,26):
        FORMAT_REQUIREMENTS =Path("./prompts/convert23.md").read_text(encoding="utf-8")
        if "gemma" in Model.lower():
            FORMAT_REQUIREMENTS = Path("./prompts/convert23en.md").read_text(encoding="utf-8")
    
    pageg=MEWbrief.page_group[vol]
    vol26=""
    #checkh=""
    checkh="""- 用户也可要求批量更正标题层级，此时应首先调用 table_content 查看目录表及正确标题层级，然后调用 grep_file 检索需修改的标题，检索后调用有关替换工具对内容进行替换。被错误转换的标题，可能在 <h[1-6] 中，也可能在 <p align="center"> 内，还可能分成多行在多个块级标签中，搜索时应注意随情况调整，未查到时阅读全文。更正时，如标题保留脚注、锚点等标签，保留换行，保留方括号，都不要删去，仅修改标题标签！"""
    if "gemma" in Model.lower():
        checkh="""- User can also ask you to revise headings in converted files. You should first call tool table_content to check the table of contents to see the correct heading levels on relevant pages, then use grep_file to check the specific context and code in the related converted files. The headings that need revision may be in <h[1-6] tags with the wrong level, or in ordinary <p align="center"> tags, or even in multiple mixed tags. Therefore, you should adjust the keyword to patch the headings correctly. Read the whole file only after you are unable to find what you need through search. When you find anchors and footnotes links in the needed revise headings, please perserve them. And do not change line breaks in the converted headings while revising only the level of a whole heading."""
    check=""
    #if vol in range(261,264):
    #    vol26="注意页码组页码的重叠，如有重叠请按要求仅输出对应的内容。"

    if Model.lower() not in ["qwen3.5-plus"]:
        check="""- 用户也可要求将多页已转换的 HTML 合并为一个 HTML 或重排某几个 HTML，此时也应参考转换要求合并。默认按照页码组合并。合并后的文件调用 save_html_by_page_num 即按合并页码组的首页页码保存。与前后组有页码重叠的组同样仅转换页码组中完整出现的一节，即本组页面中第一个出现的标题到本组最后一个标题前的内容。
- 用户如有明确待合并文件的目录，则应在 check_read_html 中填入对应路径，而非只填页码。"""

        FORMAT_REQUIREMENTS2="""
## 合并或重排 HTML 注意事项

在上述转换要求的基础上，还应注意以下细节：
  - 务必保证脚注链接样式符合转换格式要求，脚注id编号统一计数、连续、上下文一致。作者注与编者注的计数、编号体系相互独立，如果作者注（M1、L1、E1等）与编者注（F1等）未分栏则应分到两个aside内输出，保证作者注栏放在上，编者注栏在下。
  - 合并各页 HTML 的跨页段落<p>标签时，务必删去多余连字符或加回空格使原段落完整。合并跨页段落时首先根据上下文判断，如页尾有连字符或语句未完成时则明显应合并，如页尾段落后有空格则不应合并。仅在句子刚好在页尾完成且段末无空格时调用 get_page_images 参考图片判断是否合并，因此一次调用图片不要超过两个。
  - 务必同时根据语义和页面图像修正标题标签的层级，特别是前期各页 HTML 分页转换时误将标题识别为普通 p 标签的文本，应修复为正确的标题标签、标题层级。
  - 合并或重排的过程中还应注意检查其他文本内容、样式、排版的问题，如有严重错误影响可读性时，则应向用户反馈，由用户决定是否修改、重新转换。
  - 对 Marx 的手稿，应留意手稿页码格式是否正确，如发现手稿页码被[]包裹，不要将其误认为书末注释编号！可根据图像修正格式。
  - 用户也可要求你在查看每页图片后，给多页组按组转换后的文件加入页码锚点，格式为<a id="S页码"></a>，位置在文本中对应的 每页第一段段前或每页第一个完整单词后，在相应文本内容中添加页码，从第二个页码开始。
用户也可以要求你帮忙确认某组内或某页码范围内哪些页面有跨页段落，此时你仅需调用 get_page_images 对图片分批探查即可，仅需将跨页段落的所在页码输出为数组即可，格式为 [跨页段落开始页码,跨页段落结束页码]。如一个段落跨3个及以上页面，则输出该段落的所在的所有页码。特别留意语句在某一页最末尾处结束（行末与页边无留白）、即后一页首行无缩进的段落（行首与页边无留白）的跨页段落，不要误判！如需确认的页面超12个以上，可分批输出页码。"""
    if "gemma" not in Model.lower():
        return f"""你是专业的互联网出版编辑，可以通过熟练运用HTML语法，协助用户还原 PDF 页面的排版布局。

# 🛠️ 可用工具：
- add_notice: 记录转换过程中的问题
- check_read_html：获取转换后的 HTML 文本
- get_page_images：查看特定页码的原始PDF页面以供对照或检查
- save_html：保存修改后的HTML
- save_html_by_page_num：按页码保存修改后的HTML
- page_group：查看PDF各篇目的页码组
- get_requirements：用户反馈异常时重新查看转换要求

# 📌 使用策略：
- 用户说"把第 2 到 5 页转成 HTML"，则调用 get_page_images(pages=[2,3,4,5])。
- 用户输入多个页码或页码范围，务必严格对照下述篇目的页码组检查，如用户输入页码与分组不符时应询问用户，确认是否跳过部分页面，如用户同意则跳过。
- 发现用户要求的页码组与其他组有重叠时，除明确询问确认用户有其他要求外，仅可转换页码组中完整出现的一节：第一个页码与前一组最后一个页码重叠时，就从页码重叠组的第一个出现的标题开始转换；最后一个页码与后一组第一个页码重叠时，则在最后一个标题前结束，不要多余，不要缺漏。检查相应文件时也应注意文件内容范围是否正确，如有超出或缺失请修改。
- 在确定用户要求的页码范围的篇目划分后，务必调用 get_page_images 按组查看各篇目的相应页面，不确定页码组的时候应调用函数page_group。
- 用户要求从某页的某个标题开始到其他页某个标题结束，则应严格按照用户要求，仅识别并转换某个标题开始至另个标题结束前的内容，不可缺漏，不可多余。
- 检查注释时可通过以下几个特征判断异常：
  - 各类注释编号不连续，如 A/F/M/E 为前缀的 id 数字在同一文件中出现一个异常大的编号数字插在小编号之前
  - F 后数字 2 位数以上，A 后数字 4 位数以上
  - aside 栏中脚注内容在语义上不完整，如仅以单词结尾或逗号结尾等
  有异常时务必查对原图。

- 转换后调用 save_html_by_page_num 保存结果。
- get_page_images 读图一次不超过 8 个页面！
{checkh}

# 转换要求：
{FORMAT_REQUIREMENTS}

# 各篇目页码组：
{pageg}
除用户要求按标题层级输出或用户同意跳过部分页面外，严格按照页码组划分转换！{vol26}
"""
    else:
        return f"""You are a professional internet publishing editor. You can assist users in restoring the layout of PDF pages by skillfully using HTML syntax.

# 🛠️ Available Tools:
- add_notice: Record issues encountered during the conversion process
- check_read_html: Retrieve the converted HTML text
- get_page_images: View the original PDF pages of specific page numbers for reference or inspection
- save_html: Save the modified HTML
- save_html_by_page_num: Save the modified HTML by page number
- page_group: View the page groups for each section of the PDF
- get_requirements: Re-check the conversion requirements when user reports an anomaly

# 📌 Usage Strategy:
- If the user says "convert pages 2 to 5 into HTML", call get_page_images(pages=[2,3,4,5]).
- When the user inputs multiple page numbers or page ranges, strictly cross-check against the page groups of the sections listed below. If the user's input does not match the grouping, ask the user for confirmation. If the user agrees, skip those pages.
- If you find that the page group requested by the user overlaps with other groups, unless explicitly confirmed by the user for other requirements, only convert the section that appears completely within the page group: if the first page overlaps with the last page of the previous group, start from the first heading that appears in the overlapping group; if the last page overlaps with the first page of the next group, end before the last heading. Do not include excess or miss any content. When checking the corresponding files, also ensure the content range is correct; if there is overflow or omission, please correct it.
- After determining the section division for the page range requested by the user, be sure to call get_page_images to view the pages of each section by group. If unsure about the page groups, call the function page_group.
- If the user requests starting from a specific heading on a certain page and ending at a specific heading on another page, strictly follow the user's request: only recognize and convert the content from that starting heading to just before the ending heading, without omission or excess.
- After conversion, call save_html_by_page_num to save the result.
- Do not read more than 8 pages at a time with get_page_images!
- You can judge the abnormal notes (number) by:
  - Discontinutiy of notes' ids number, like extra large numbers after A/M/E/F's prefix lies before the small numbers.
  - F with 2-digit id number, A with 4-digit id number
  - Incompleteness of sentences inside the aside column which might end with letters or commas.
  You should check pictures if you find these mistakes.
{checkh}

# Conversion Requirements:
{FORMAT_REQUIREMENTS}

# Page Groups for Each Section:
{pageg}
Unless the user requests output by heading level or agrees to skip certain pages, strictly follow the page groups for conversion! 
"""

# ==================== Agent ====================
class Agent:

    def __init__(self, general_cfg: Config, chat_client: VLMClient,
                 tool_handler: ToolHandler):
        self.cfg        = general_cfg
        self.client     = chat_client
        self.tools      = tool_handler
        self._interrupt = chat_client._interrupt

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
            return AgentResult(AgentSignal.PAUSE, history=history)
        except RuntimeError as e:
            return AgentResult(AgentSignal.ANSWER,
                               answer=f"错误：{e}", history=history)

        new_history = [m for m in messages if m.get("role") != "system"]
        return AgentResult(AgentSignal.ANSWER,
                           answer=msg.get("content", ""), history=new_history)

# ==================== 应用控制器 ====================
class AppController:

    def __init__(self, cfg: Config, interrupt: threading.Event, agent: Agent,DEFAULT_CHAT_THINK:bool):
        self.cfg        = cfg
        self._interrupt = interrupt
        self._agent     = agent
        self.show_tools = True
        self.enable_think =DEFAULT_CHAT_THINK
        self.history    = []
        self._cancel=self._agent.client._cancel

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
            self._cancel.set()
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
        cfg.HTML_MERGE_DIR=f"./MEW_BRIEF/{cfg.VOL}_temp"
        cfg.OUTPUT_DIR= f"./MEW_BRIEF/{cfg.VOL}"
        pdf_path = r"D:\马恩列总装\马恩全集德文\mew_band" + f"{cfg.VOL:02d}.pdf"
    if cfg.VOL==261:
        cfg.CACHE_DIR= r"cache_images26_1"
        cfg.HTML_MERGE_DIR=r"./MEW_BRIEF/261"
        cfg.OUTPUT_DIR= r"./MEW_BRIEF/26"
        pdf_path = r"D:\马恩列总装\马恩全集德文\mew_band26_1.pdf"
    if cfg.VOL==262:
        cfg.CACHE_DIR= r"cache_images26_2"
        cfg.HTML_MERGE_DIR=r"./MEW_BRIEF/262"
        cfg.OUTPUT_DIR= r"./MEW_BRIEF/26"
        pdf_path = r"D:\马恩列总装\马恩全集德文\mew_band26_2.pdf"
    if cfg.VOL==263:
        cfg.CACHE_DIR= r"cache_images26_3"
        cfg.HTML_MERGE_DIR=r"./MEW_BRIEF/263"
        cfg.OUTPUT_DIR= r"./MEW_BRIEF/26"
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
    MS=API_SERVERICE("https://api-inference.modelscope.cn/v1/chat/completions","")
    NIM=API_SERVERICE("https://integrate.api.nvidia.com/v1/chat/completions","")
    NIM2=API_SERVERICE("https://integrate.api.nvidia.com/v1/chat/completions","")
    BL=API_SERVERICE("https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions","")
    CT=API_SERVERICE("https://wishub-x6.ctyun.cn/v1/chat/completions","")
    MM=API_SERVERICE("https://api.minimaxi.com/v1/text/chatcompletion_v2","")
    MIS=API_SERVERICE("https://api.mistral.ai/v1/chat/completions","")
    GLM=API_SERVERICE("https://open.bigmodel.cn/api/paas/v4/chat/completions","")
    MI=API_SERVERICE("https://api.xiaomimimo.com/v1/chat/completions","")
    OR=API_SERVERICE("https://openrouter.ai/api/v1/chat/completions","")
    MON=API_SERVERICE("https://api.kimi.com/coding/v1/chat/completions","")
    DS=API_SERVERICE("https://api.deepseek.com/chat/completions","")
    GOG=API_SERVERICE("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions","")
    CFG=API_SERVERICE("https://gateway.ai.cloudflare.com/v1/1268bbbbed53c4851d0261970259aafa/private/google-ai-studio/v1beta/openai/chat/completions","")
    page_cfg=Config(BL,cfg,True,MAX_CONCURRENT,"enable_thinking")
    page_cfg.MODEL= "qwen3.5-plus"
    # ── 💬 聊天调度模型（负责解析用户指令、调用工具）──────────
    chat_cfg=Config(MS,cfg,False,MAX_CONCURRENT,"enable_thinking")
    #chat_cfg=Config(NIM,cfg,False,MAX_CONCURRENT,"chat_template_kwargs")
    #chat_cfg=Config(MON,cfg,True,MAX_CONCURRENT,"thinking")
    #chat_cfg=Config(NIM,cfg,False,MAX_CONCURRENT,"reasoning_effort")
    #chat_cfg=Config(CT,cfg,True,MAX_CONCURRENT,"enable_thinking")
    #chat_cfg=Config(MS,cfg,True,MAX_CONCURRENT,"enable_thinking")
    #chat_cfg=Config(BL,cfg,True,MAX_CONCURRENT,"enable_thinking")
    #chat_cfg=Config(MM,cfg,False,MAX_CONCURRENT,"thinking")
    #chat_cfg=Config(GOG,cfg,False,MAX_CONCURRENT,"reasoning_effort")
    #chat_cfg=Config(CFG,cfg,False,MAX_CONCURRENT,"reasoning_effort")
    #chat_cfg=Config(OR,cfg,False,MAX_CONCURRENT,"reasoning_effort")
    #chat_cfg=Config(DS,cfg,False,MAX_CONCURRENT,"thinking")
    #chat_cfg.MODEL= "qwen/qwen3.5-397b-a17b"
    #chat_cfg.MODEL= "qwen/qwen3.5-122b-a10b"
    #chat_cfg.MODEL="qwen3.5-plus"
    #chat_cfg.MODEL="qwen3.6-plus"
    chat_cfg.MODEL="qwen/qwen3.5-27b"
    #chat_cfg.MODEL="deepseek-v4-flash"
    #chat_cfg.MODEL="google/gemma-4-31b-it"
    #chat_cfg.MODEL="gemma-4-31b-it"
    #chat_cfg.MODEL="gemini-3.1-flash-lite-preview"
    #chat_cfg.MODEL="gemini-3-flash-preview"
    #chat_cfg.MODEL="google/gemini-3.1-flash-lite-preview"
    #chat_cfg.MODEL="Kimi-K2.5"
    if chat_cfg.MODEL.lower() in ["kimi-k2.5","qwen3.5-plus","qwen3.6-plus","gemma-4-31b-it"]:
        chat_cfg.TIMEOUT=httpx.Timeout(connect=10.0, read=900.0, write=1800.0, pool=10.0)
    #chat_cfg.MODEL="kimi-code/kimi-for-coding"
    #chat_cfg.MODEL= "Qwen3.5-397B-A17B"
    #chat_cfg.THINK_TYPE= "chat_template_kwargs"
    #chat_cfg.MODEL= "mistralai/mistral-small-4-119b-2603"
    #chat_cfg.MODEL="stepfun-ai/step-3.5-flash"
    #chat_cfg.MODEL="nvidia/nemotron-3-super-120b-a12b"
    #chat_cfg.MODEL="MiniMax-M2.7"
    #chat_cfg.THINK_TYPE= "thinking"
    chat_cfg.MAX_RETRIES=20
    chat_cfg.TEMPERATURE=1
    chat_cfg.TOP_P=0.95
    interrupt = threading.Event()

    # ── 创建两个独立客户端，各持自己的 cfg ────────────────────
    chat_client = VLMClient(chat_cfg, interrupt)   # 💬 聊天调度
    if chat_cfg.API_URL.startswith("https://gateway.ai.cloudflare.com/v1/"):
        chat_client._headers["cf-aig-authorization"]="Bearer "
    # ── 组件组装（通用配置统一从 chat_cfg 读）─────────────────
    image_cache  = ImageCache(pdf_path, chat_cfg.CACHE_DIR, chat_cfg.DPI)
    tool_handler = ToolHandler(
        cache=image_cache,
        cfg=chat_cfg
    )
    agent = Agent(chat_cfg, chat_client, tool_handler)
    controller = AppController(chat_cfg, interrupt, agent,cfg.DEFAULT_CHAT_THINK)
    cache_clear=False

    # ── 缓存清理询问 ───────────────────────────────────────────
    if image_cache.cache_dir.exists() and any(image_cache.cache_dir.iterdir()) and cache_clear:
        if input("⚠️  缓存目录已有图片，是否删除？(y/N): ").strip().lower() == "y":
            image_cache.clear_cache()

    controller.run()

if __name__ == "__main__":
    main()