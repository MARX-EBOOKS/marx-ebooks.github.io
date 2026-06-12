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
import MEWbrief1 as MEWbrief
import argparse
import uuid
import usepic

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
            "User-Agent":    "RooCode/3.51.0",
            #"User-Agent":    "claude-code/2.1.87",
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
                if isinstance(result, list) and "google" in self.cfg.API_URL:
                    messages.append({
            "role": "tool",
            "tool_call_id": tc.get("id", ""),
            "content": f"[已返回 {len(result)-1} 张页面图像，见下方]"
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
            "name": "get_page_images",
            "description": "获取指定 PDF 页面的原始图片，由你直接查看。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pages": {"type": "array", "items": {"type": "integer"},
                              "description": "要查看的页码列表，不要超过 30 个页面！分批读取时务必按批次分析版面！"}
                },
                "required": ["pages"]
            }
        }},


        {"type": "function", "function": {
            "name": "add_notice",
            "description": "记录检查过程中发现的问题。",
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
            "name": "open_pic",
            "description": "按用户要求打开特定页面图片",
            "parameters": {
            "type": "object", 
                "properties": {
                    "pages": {"type": "array", "items": {"type": "integer"},
                              "description": "要打开的页面图片列表，不要超过 30 个页面！"}
                },
                "required": ["pages"]

        }
        }},
    ]

    def __init__(self, cache: ImageCache,cfg: Config,
                 use_tools: Optional[list] = None):
        self.cache       = cache
        self.cfg         =cfg
        self.tools       = use_tools if use_tools is not None else self.ALL_TOOLS
        self.pg=MEWbrief.page_group[cfg.VOL]
        self._dispatch = {
            "get_page_images": self._get_page_images,
            "add_notice":     self._add_notice,
            "page_group":self._page_group,
            "open_pic":self._open_pic,
        }
        self.FORMAT_REQUIREMENTS = Path("./prompts/convert.md").read_text(encoding="utf-8")
    def _open_pic(self, pages: list[int]=None):
        if pages:
            pic_opened=""
            for i,p in enumerate(pages):
                pic_opened+=usepic.read_pic_simp(self.cfg.VOL,p)+"\n"
                if i==30:
                    pic_opened+="一次只打开 30 个，目前仅打开前 30 个！"
                    break
            return pic_opened
        else:
            return "请确认页码"


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
    
    def _resolve_html_path(self, html_path: str="", pages: list[int]=None,merge_html:bool=False) -> Path:
        if html_path:
            if not Path(html_path).parent.exists() and not merge_html:
                Path(html_path).parent.mkdir(parents=True, exist_ok=True)
            return Path(html_path)
        prefix=f"ME{self.cfg.VOL:02d}-"
        if self.cfg.VOL in range(261,264):
            prefix = f"ME26-{self.cfg.VOL-260}"
        if merge_html:
            Path(self.cfg.HTML_MERGE_DIR).mkdir(parents=True, exist_ok=True)
            return Path(self.cfg.HTML_MERGE_DIR) / f"{prefix}{pages[0]:03d}.html"
        return Path(self.cfg.OUTPUT_DIR) / f"{prefix}{pages[0]:03d}.html"
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
            return ( "合并、重排时请注意：\n\n"
  "- 务必保证脚注链接样式符合转换格式要求，脚注id编号统一计数、连续、上下文一致。作者注与编者注的计数、编号体系相互独立，如果作者注（M1、L1、E1等）与编者注（F1等）未分栏则应分到两个aside内输出，保证作者注栏放在上，编者注栏在下。\n"
  "- 合并各页 HTML 的跨页段落<p>标签时，务必删去多余连字符或加回空格使原段落完整。合并段落时可根据上下文即语句是否完成判断，如无法判断务必参考图片，一次调用图片不要超过两个。\n"
  "- 务必同时根据语义和页面图像修正标题标签的层级，特别是前期各页 HTML 分页转换时误将标题识别为普通 p 标签的文本，应修复为正确的标题标签、标题层级。\n"
  "- 应注意检查其他文本内容、样式、排版的问题，如有严重错误影响可读性时，则应向用户反馈，由用户决定是否修改、重新转换。\n"
  "- 对 Marx 的手稿，应留意手稿页码格式是否正确，如发现手稿页码被[]包裹，不要将其误认为书末注释编号！可根据图像修正格式。\n\n"""
            f"待合并 HTML:\n{HTML}"
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
            f"当前 HTML:\n{html}"
            )
        return (
            "请按要求处理转换后的HTML！\n"
            f"当前 HTML:\n{html}"         
        )

    def _get_page_images(self, pages: list[int]) -> list:
        image_need=[] 
        text_4=""
        for pnum,p in enumerate(pages):
            image_need.append( {"type": "image_url","image_url": {"url": f"data:image/png;base64,{self.cache.get_image_b64(p)}"}})
            if pnum==8:
                text_4="（一次请求的页数不要超过8页！目前返回前8页！查看后续页码请另行调用本函数！）"
                break

        image_need.append({"type":"text","text":f"""请按用户要求，记录每页正文开头部分（页眉下方）的十个单词，或查找图片中除单词连字符外标点符号出现在页面最底部的语句（形如 The sentence has finished[,.?":!“]|页面正文最底端边缘），同时也记录作者注释（短横线下各条目）或编者注释（长横线下各条目）跨页的情况。最后将跨页注释和句子在页尾结束的段落所在页面以及其后一页返回为 python 数组，并向用户反馈具体上下文。{text_4}"""})
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



    def _add_notice(self, note: str) -> str:
        with self.cfg.NOTICE_FILE.open("a", encoding="utf-8") as f:
            f.write(f"- {note}\n")
        return f"已记录：{note}"

# ==================== 系统提示 ====================
def get_system_prompt(vol: int,Model:str) -> str:
    pageg=MEWbrief.page_group[vol]
    requireback=f"""按用户要求分析一个 PDF 文件版面、探查特定格式的内容。PDF 文件已经按页码拆分成各个图像，同时也有现成的页码组。当用户下达“查找某个页码范围”或“查找某几组”的指令时，你就首先按照篇目页码组用 get_page_images 调用对应页面图片查找图片中正文句号、感叹号、括号、引号、冒号等出现在页面最底部的语句（形如 The sentence has finished[.?":!“]|页面正文最底端边缘），同时也记录作者注释（短横线下各条目）或编者注释（长横线下各条目）跨页的情况。最后将跨页注释和句子在页尾结束的段落所在页面以及其后一页返回为 python 数组，同时帮用户打开图片，向用户反馈具体上下文。"""
    return f"""按用户要求完成对 PDF 电子书页面的分析任务。

# 默认状态：
- 用户下达搜索某几个页面或页面组的指令后，直接按页码组或页码打开页面图片，直接查看页面底部。
- 如页面正文最底部的边缘处出现：
  - 标点符号而非空格或字母或单词未完成时的连字符；
  - 页脚注释区注释内容不完整、延续到后页注释区的注释，
  那么就记录相关页面的页码，最后将有关页码的本页和后一页返回为 PYTHON 数组，并帮用户打开图片。
- 用户下达打开某几个页面或某几组页面或按组打开页面的指令后，则直接帮用户打开页面图片，其余什么都不用做。
- 用户也可以要求查看某几页正文开头部分的文本。此时应调用 get_page_images 查看图片，同时为用户打开对应图片，仅返回每页正文开头部分（页眉正下方）的 10 个单词（包括十个单词之间的标点，各注释上标视为一个单词），如果正文开头（页眉正下方）是某个标题则返回标题内容即可。其余什么都不用做！用户用 “check fl...” 下达指令时照此办理。

# 可用工具：

- add_notice: 记录用户反馈的与分组有关的问题，也可以直接记录页码组等信息
- get_page_images：查看特定页码的原始PDF页面以供对照或检查
- page_group：查看PDF各篇目的页码组

# 各篇目页码组：

{pageg}
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
    MS=API_SERVERICE("https://api-inference.modelscope.cn/v1/chat/completions","ms-...")
    NIM=API_SERVERICE("https://integrate.api.nvidia.com/v1/chat/completions","nvapi-...")
    BL=API_SERVERICE("https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions","sk-...")
    CT=API_SERVERICE("https://wishub-x6.ctyun.cn/v1/chat/completions","...")
    MM=API_SERVERICE("https://api.minimaxi.com/v1/text/chatcompletion_v2","sk-cp-...")
    GOG=API_SERVERICE("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions","...")
    CFG=API_SERVERICE("https://gateway.ai.cloudflare.com/v1/.../private/google-ai-studio/v1beta/openai/chat/completions","...")
    cfg.DEFAULT_CHAT_THINK=True
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
    #chat_cfg.MODEL= "qwen/qwen3.5-397b-a17b"
    #chat_cfg.MODEL= "qwen/qwen3.5-122b-a10b"
    chat_cfg.MODEL= "qwen/qwen3.5-35b-a3b"
    #chat_cfg.MODEL="qwen3.5-plus"
    #chat_cfg.MODEL="qwen3.6-plus"
    #chat_cfg.MODEL="google/gemma-4-31b-it"
    #chat_cfg.MODEL="gemma-4-31b-it"
    #chat_cfg.MODEL="gemini-3.1-flash-lite-preview"
    #chat_cfg.MODEL="google/gemini-3.1-flash-lite-preview"
    #chat_cfg.MODEL="Kimi-K2.5"
    if chat_cfg.MODEL.lower() in ["kimi-k2.5","qwen3.5-plus","qwen3.6-plus"]:
        chat_cfg.TIMEOUT=httpx.Timeout(connect=10.0, read=3600.0, write=120.0, pool=10.0)
    #chat_cfg.MODEL="kimi-code/kimi-for-coding"
    #chat_cfg.MODEL= "Qwen3.5-397B-A17B"
    #chat_cfg.THINK_TYPE= "chat_template_kwargs"
    #chat_cfg.MODEL= "mistralai/mistral-small-4-119b-2603"
    #chat_cfg.MODEL="stepfun-ai/step-3.5-flash"
    #chat_cfg.MODEL="nvidia/nemotron-3-super-120b-a12b"
    #chat_cfg.MODEL="MiniMax-M2.7"
    #chat_cfg.THINK_TYPE= "thinking"
    chat_cfg.TEMPERATURE=1
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