import re
from dataclasses import dataclass
import signal
import threading
from concurrent.futures import CancelledError,ThreadPoolExecutor
from pathlib import Path
import httpx
try:
    from blessed import Terminal
except ImportError as exc:
    raise SystemExit("缺少跨平台终端库 blessed，请先运行：python -m pip install blessed") from exc
from unpackpdf import ImageCache
import MEWbrief
import uuid
import time
import random
import argparse
import sys
import replace_html_quotes

terminal=Terminal()


def input_with_initial(prompt, initial):
    """Read an editable line with *initial* already present on a terminal."""
    initial=str(initial)
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        value=input(f"{prompt}（当前：{initial}；直接回车保留）：")
        return initial if value=="" else value
    text=list(initial)
    cursor=len(text)

    def redraw():
        value="".join(text)
        print("\r\x1b[2K"+prompt+value,end="",flush=True)
        tail=len(text)-cursor
        if tail:
            print(f"\x1b[{tail}D",end="",flush=True)

    redraw()
    with terminal.cbreak():
        while True:
            key=terminal.inkey()
            char=str(key)
            if key.name=="KEY_ENTER" or char in ("\r","\n"):
                print()
                return "".join(text)
            if char=="\x03":
                print()
                raise KeyboardInterrupt
            if key.name=="KEY_ESCAPE" or char=="\x1b":
                print()
                return None
            if key.name=="KEY_LEFT" and cursor>0: cursor-=1
            elif key.name=="KEY_RIGHT" and cursor<len(text): cursor+=1
            elif key.name=="KEY_HOME" or char=="\x01": cursor=0
            elif key.name=="KEY_END" or char=="\x05": cursor=len(text)
            elif key.name=="KEY_DELETE" and cursor<len(text): del text[cursor]
            elif (key.name=="KEY_BACKSPACE" or char in ("\b","\x7f")) and cursor>0:
                cursor-=1
                del text[cursor]
            elif char=="\x15":
                text.clear()
                cursor=0
            elif not key.name and char.isprintable():
                text.insert(cursor,char)
                cursor+=1
            else:
                continue
            redraw()


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
    SUPPORT_CACHE = ["https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions","https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions"]
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

def page_group(volume: int):
    page_map={}
    for group in MEWbrief.page_group[volume] or []:
        for page in group or []: page_map[page]=group
    return page_map

def parse_pages(text):
    pages=[]
    for part in text.replace("，", ",").split(","):
        part=part.strip()
        if not part:
            continue
        if "-" in part:
            start,end=(int(x.strip()) for x in part.split("-",1))
            if start>end:
                start,end=end,start
            pages.extend(range(start,end+1))
        else:
            pages.append(int(part))
    return list(dict.fromkeys(pages))

def response_text(data):
    content=data["choices"][0]["message"]["content"]
    if isinstance(content,list):
        content="".join(x.get("text","") for x in content if isinstance(x,dict))
    content=re.sub(r"^[\s\S]*```html\s*", "", str(content), flags=re.I)
    content,_,_=replace_html_quotes.fix_html(content)
    return re.sub(r"\s*```\s*$", "", content).strip()

def image_type(b64):
    if b64.startswith("iVBORw0K"): return "png"
    if b64.startswith("/9j/"): return "jpeg"
    if b64.startswith(("R0lGODdh","R0lGODlh")): return "gif"
    if b64.startswith("UklGR"): return "webp"
    if b64.startswith("Qk"): return "bmp"
    if b64.startswith(("SUkqAA","TU0AKA")): return "tiff"
    return "png"

class AppController:
    def __init__(self,cfg: Config,API_OPTIONS,PAGES,variable_prompt):
        self.cfg=cfg
        self.API_OPTIONS=API_OPTIONS
        self.api_name=next((name for name,item in API_OPTIONS if item.API_URL==cfg.API_URL and item.API_KEY==cfg.API_KEY),"自定义")
        self.cache=None
        self.pages=list(PAGES)
        self.page_text=f"{PAGES[0]}-{PAGES[-1]}" if PAGES else "未设置"
        self.semaphore=threading.Semaphore(self.cfg.MAX_CONCURRENT)
        self.stop_new=threading.Event()
        self.force_cancel=threading.Event()
        self.request_lock=threading.Lock()
        self.active_clients=set()
        self.pending_futures=[]
        self.variable_prompt=variable_prompt
        self.DEFAULT_PROMPTS=variable_prompt
        self.NOTICE=""
        self.control_stop=threading.Event()

    def _selected_groups(self):
        page_group_map=page_group(self.cfg.VOL)
        groups=[]
        seen=set()
        missing=[]
        for page in self.pages:
            group=page_group_map.get(page)
            if not group:
                missing.append(page)
                continue
            key=tuple(group)
            if key not in seen:
                seen.add(key)
                groups.append(list(group))
        if missing:
            print(f"[跳过] 未登记页面组：{missing}")
        return sorted(groups,key=lambda group:group[0])

    def _wait_to_start(self):
        while not self.stop_new.is_set():
            if self.semaphore.acquire(timeout=0.2):
                if not self.stop_new.is_set():
                    return True
                self.semaphore.release()
        return False

    def _request_menu_return(self,force=False):
        with self.request_lock:
            force=force or self.stop_new.is_set()
            self.stop_new.set()
            clients=[]
            if force and not self.force_cancel.is_set():
                self.force_cancel.set()
                clients=list(self.active_clients)
            futures=list(self.pending_futures)
        for future in futures:
            future.cancel()
        if force:
            print("\n[强制中断] 正在关闭所有在途请求并返回主菜单。")
            for client in clients:
                try:
                    client.close()
                except Exception:
                    pass
        else:
            print("\n[停止发送] 不再发起新请求；在途请求结束后返回主菜单。再次按 p/Ctrl+C 或按 q 可强制中断。")

    def _begin_request(self,client):
        with self.request_lock:
            if self.stop_new.is_set():
                return False
            self.active_clients.add(client)
            return True

    def _end_request(self,client):
        with self.request_lock:
            self.active_clients.discard(client)
        try:
            client.close()
        except Exception:
            pass

    def _paths(self):
        if self.cfg.VOL in (261,262,263):
            PDF_PATH=Path(f"马恩全集德文/mew_band26_{self.cfg.VOL-260}.pdf")
        else:
            PDF_PATH=Path(f"马恩全集德文/mew_band{self.cfg.VOL:02d}.pdf")
        CACHE_DIR=Path(f"cache_images{self.cfg.VOL}")
        CACHE_DIR.mkdir(exist_ok=True)
        notice_file=Path(f"cache_images{self.cfg.VOL}/NOTICE.md")
        if not notice_file.exists():
            notice_file.write_text("", encoding="utf-8")
        else:
            self.NOTICE=notice_file.read_text(encoding="utf-8")
        return PDF_PATH,CACHE_DIR

    def _messages(self,group):
        prompt="convert23.md" if self.cfg.VOL in range(23,26) else "convert2.md"
        rules=Path("prompts",prompt).read_text(encoding="utf-8")
        capital=f"。\n当前为《资本论》第 {self.cfg.VOL-22} 卷" if self.cfg.VOL in range(23,26) else ""
        system_text="你是专业电子出版物编辑，请按页面图像高质量录入网页"+capital+f"。严格遵守以下格式要求：\n{rules}"
        if self.NOTICE:
            system_text+=f"\n\n还应注意：\n{self.NOTICE}"
        system={"role":"system","content":system_text}
        cache_ok=self.cfg.ENABLE_EXPLICIT_CACHE and self.cfg.API_URL in self.cfg.SUPPORT_CACHE
        if cache_ok and len(system_text)>=self.cfg.CACHE_MIN_TOKENS:
            system["content"]=[{"type":"text","text":system_text,"cache_control":{"type":"ephemeral"}}]
        items=[]
        for page in group:
            b64=self.cache.get_image_b64(page)
            items.append({"type":"image_url","image_url":{
                "url":f"data:image/{image_type(b64)};base64,{b64}"}})
        text_item={"type":"text","text":self.variable_prompt}
        if cache_ok and len(self.variable_prompt)>=self.cfg.CACHE_MIN_TOKENS: text_item["cache_control"]={"type":"ephemeral"}
        items.append(text_item)
        return [system,{"role":"user","content":items}]

    def _convert(self,group):
        retry_status={400,408,409,429,500,502,503,504}
        last_error=None
        for attempt in range(self.cfg.MAX_RETRIES+1):
            acquired=False
            try:
                payload={"model":self.cfg.MODEL,"messages":self._messages(group),"max_tokens":self.cfg.MAX_TOKENS,
                     "temperature":self.cfg.TEMPERATURE,"top_p":self.cfg.TOP_P,"stream":False}
                thinking=self.cfg.get_think_payload(self.cfg.ENABLE_THINK)
                if thinking is not None:
                    payload[self.cfg.THINK_TYPE]=thinking
                headers={"Authorization":f"Bearer {self.cfg.API_KEY}",
                             "Accept":"application/json","x-request-id":str(uuid.uuid4()),
                             "User-Agent":"opencode/1.18.26"}
                if not self._wait_to_start():
                    return f"[已取消] ME{self.cfg.VOL:02d}-{group[0]:03d}"
                acquired=True
                attempt_text=f"（重试 {attempt}/{self.cfg.MAX_RETRIES}）" if attempt else ""
                print(f"正在转换 [ME{self.cfg.VOL:02d}-{group[0]:03d}]{attempt_text}")
                client=httpx.Client(timeout=self.cfg.TIMEOUT)
                if not self._begin_request(client):
                    self._end_request(client)
                    return f"[已停止] ME{self.cfg.VOL:02d}-{group[0]:03d}"
                try:
                    response=client.post(self.cfg.API_URL,json=payload,headers=headers)
                    response.raise_for_status()
                    data=response.json()
                finally:
                    self._end_request(client)
                if self.force_cancel.is_set():
                    return f"[已强制中断] ME{self.cfg.VOL:02d}-{group[0]:03d}"
                html=response_text(data)
                if not html:
                    raise ValueError("响应正文为空")
                usage = data.get("usage")
                details=(usage or {}).get("prompt_tokens_details") or {}
                cached,created=details.get("cached_tokens",0),details.get("cache_creation_input_tokens",0)
                usage_info=""
                if usage:
                    usage_info=f"Token 使用：输入={usage['prompt_tokens']}，输出={usage['completion_tokens']}，总计={usage['total_tokens']}"
                    if cached:
                        usage_info=f"[缓存命中] {cached} tokens，"+usage_info
                    elif created:
                        usage_info=f"[缓存创建] {created} tokens，"+usage_info
                output=self.cfg.OUTPUT_DIR / str(self.cfg.VOL) / f"ME{self.cfg.VOL:02d}-{group[0]:03d}.html"
                output.parent.mkdir(parents=True,exist_ok=True)
                temp=output.with_suffix(".html.tmp")
                temp.write_text(html,encoding="utf-8")
                temp.replace(output)
                time.sleep(random.uniform(0.15,0.25))
                return f"完成 -> {output}。"+usage_info
            except httpx.HTTPStatusError as exc:
                last_error=exc
                if exc.response.status_code not in retry_status:
                    raise ValueError(f"[失败] ME{self.cfg.VOL:02d}-{group[0]:03d}：{exc}")
                    return f"[失败] ME{self.cfg.VOL:02d}-{group[0]:03d}：{exc}"
            except Exception as exc:
                last_error=exc
            finally:
                if acquired:
                    self.semaphore.release()
            if self.stop_new.is_set():
                status="已强制中断" if self.force_cancel.is_set() else "已停止"
                return f"[{status}] ME{self.cfg.VOL:02d}-{group[0]:03d}"
            if attempt==self.cfg.MAX_RETRIES:
                raise ValueError(f"[失败] ME{self.cfg.VOL:02d}-{group[0]:03d}：已重试 {self.cfg.MAX_RETRIES} 次；{last_error}")
                return f"[失败] ME{self.cfg.VOL:02d}-{group[0]:03d}：已重试 {self.cfg.MAX_RETRIES} 次；{last_error}"
            delay=random.uniform(0.5,1.5)*min(2**(attempt+1),8)
            print(f"[自动重试 ME{self.cfg.VOL:02d}-{group[0]:03d} {attempt+1}/{self.cfg.MAX_RETRIES}] {last_error}；{delay:.1f} 秒后重试")
            if self.stop_new.wait(delay):
                status="已强制中断" if self.force_cancel.is_set() else "已停止"
                return f"[{status}] ME{self.cfg.VOL:02d}-{group[0]:03d}"

    def _controls(self):
        if not sys.stdin.isatty():
            self.control_stop.wait()
            return
        with terminal.cbreak():
            while not self.control_stop.is_set():
                command=str(terminal.inkey(timeout=0.1)).lower()
                if command=="p": self._request_menu_return()
                elif command=="q": self._request_menu_return(force=True)
    def request_starter(self,groups):
        previous_sigint=signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT,lambda *_: self._request_menu_return())
        self.control_stop.clear()
        control_thread=threading.Thread(target=self._controls,daemon=True); control_thread.start()
        print(f"共 {len(groups)} 组，最大并发 {self.cfg.MAX_CONCURRENT}。按一次 p/Ctrl+C 停止发送并在在途请求结束后返回；再按一次或按 q 强制中断。"+"当前指令："+self.variable_prompt)
        workers=min(len(groups),self.cfg.MAX_CONCURRENT)
        error_pages=[]
        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures=[pool.submit(self._convert,group) for group in groups]
                with self.request_lock:
                    self.pending_futures=futures
                    should_cancel=self.stop_new.is_set()
                if should_cancel:
                    for future in futures: future.cancel()
                for future in futures:
                    try:
                        print(future.result())
                    except ValueError as exc:
                        print(exc)
                        error_pages.append(str(exc))
                    except CancelledError:
                        pass
        finally:
            self.control_stop.set()
            control_thread.join()
            signal.signal(signal.SIGINT,previous_sigint)
            if error_pages:
                print("\n以下页面组转换失败或被取消：")
                for error_page in error_pages:
                    print(error_page)
            with self.request_lock:
                self.pending_futures.clear()
    def run(self):
        self.stop_new.clear()
        self.force_cancel.clear()
        with self.request_lock:
            self.active_clients.clear()
            self.pending_futures.clear()
        while True:
            try: 
                CACHE_OPEN=""
                if self.cfg.API_URL in self.cfg.SUPPORT_CACHE and self.cfg.ENABLE_EXPLICIT_CACHE:
                    CACHE_OPEN="（启用显式缓存）"
                choice=input(f"\n卷号：{self.cfg.VOL}，共 {MEWbrief.page_group[self.cfg.VOL][-1][-1]} 页；页码：{self.page_text}；API：{self.api_name}{CACHE_OPEN}；并发：{self.cfg.MAX_CONCURRENT}；模型：{self.cfg.MODEL}\n[1] 卷号  [2] 页码  [3] API  [4] 并发数  [5] 模型名  [6/ENTER] 开始  [a] 额外指令  [q] 退出  [t] 调整思考模式\n请选择：").strip().lower()
            except (EOFError,KeyboardInterrupt): return
            try:
                if choice=="1":
                    volume_text=input("卷号（q 返回）：").strip()
                    if volume_text.lower()=="q": continue
                    volume=int(volume_text)
                    if volume<0 or volume>=len(MEWbrief.page_group) or not MEWbrief.page_group[volume]: raise ValueError("该卷没有页面组")
                    self.cfg.VOL=volume
                elif choice=="2":
                    new_text=input("页码（如 101-300 或 101,105-108；q 返回）：").strip()
                    if new_text.lower()=="q": continue
                    new_pages=parse_pages(new_text)
                    if not new_pages: raise ValueError("页码不能为空")
                    self.page_text,self.pages=new_text,new_pages
                elif choice=="3":
                    print("\n".join(f"[{index}] {name}" for index,(name,_) in enumerate(self.API_OPTIONS)))
                    api_text=input("API 厂商 index（q 返回）：").strip().lower()
                    if api_text=="q": continue
                    api_index=int(api_text)
                    if api_index<0 or api_index>=len(self.API_OPTIONS): raise ValueError("没有这个 API index")
                    self.api_name,api=self.API_OPTIONS[api_index]
                    self.cfg.API_URL,self.cfg.API_KEY=api.API_URL,api.API_KEY
                elif choice=="4":
                    concurrent_text=input("最大并发数（q 返回）：").strip()
                    if concurrent_text.lower()=="q": continue
                    new_concurrent=int(concurrent_text)
                    if new_concurrent<1: raise ValueError("并发数必须大于 0")
                    self.cfg.MAX_CONCURRENT=new_concurrent
                    self.semaphore=threading.Semaphore(self.cfg.MAX_CONCURRENT)
                elif choice=="5":
                    model_text=input_with_initial("模型名（Esc 返回）：",self.cfg.MODEL)
                    if model_text is None: continue
                    model_text=model_text.strip()
                    if model_text.lower()=="q": continue
                    if not model_text: raise ValueError("模型名不能为空")
                    self.cfg.MODEL=model_text
                elif choice=="a":
                    print("当前指令："+self.variable_prompt)
                    instructions=input("额外指令（q 返回）：").strip()
                    self.variable_prompt=instructions if instructions else self.DEFAULT_PROMPTS
                    if instructions.lower()=="q" or not instructions: continue
                elif choice=="t":
                    self.cfg.ENABLE_THINK=not self.cfg.ENABLE_THINK
                    print(f"思考模式：{self.cfg.ENABLE_THINK}，模型思考模式字段（q返回）：{self.cfg.THINK_TYPE}")
                    THINK_TYPE=input_with_initial("模型思考模式字段（q返回）：",self.cfg.THINK_TYPE)
                    if THINK_TYPE.lower()=="q" or not THINK_TYPE: continue
                    self.cfg.THINK_TYPE=THINK_TYPE
                elif choice=="6" or choice=="": break
                elif choice=="q": return
                else: print("请输入 1、2、3、4、5、6、A 或 q。")
            except ValueError as exc: print(f"[输入无效] {exc}")
        groups=self._selected_groups()
        if not groups:
            print("没有可转换的页面组。"); return
        pdf_path,cache_dir=self._paths()
        if not pdf_path.is_file():
            print(f"PDF 文件不存在：{pdf_path}"); return
        max_edge=None;trim_white=False
        #if self.cfg.API_URL=="https://api-inference.modelscope.cn/v1/chat/completions":
            #max_edge=2048
            #trim_white=True
        self.cache=ImageCache(pdf_path=pdf_path,cache_dir=cache_dir,dpi=self.cfg.DPI,max_edge=max_edge,trim_white=trim_white)
        if not self.variable_prompt:
            self.variable_prompt=self.DEFAULT_PROMPTS
        self.request_starter(groups)
        return True
        

def main():
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,"reconfigure"):
            stream.reconfigure(encoding="utf-8")
    MS=API_SERVERICE("https://api-inference.modelscope.cn/v1/chat/completions","ms-...")
    NIM=API_SERVERICE("https://integrate.api.nvidia.com/v1/chat/completions","nvapi-...")
    NIM2=API_SERVERICE("https://integrate.api.nvidia.com/v1/chat/completions","nvapi-...")
    BL=API_SERVERICE("https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions","sk-...")
    CT=API_SERVERICE("https://wishub-x6.ctyun.cn/v1/chat/completions","...")
    MM=API_SERVERICE("https://api.minimaxi.com/v1/text/chatcompletion_v2","sk-cp-...")
    MIS=API_SERVERICE("https://api.mistral.ai/v1/chat/completions","...")
    GLM=API_SERVERICE("https://open.bigmodel.cn/api/paas/v4/chat/completions","...")
    MI=API_SERVERICE("https://api.xiaomimimo.com/v1/chat/completions","sk-...")
    OR=API_SERVERICE("https://openrouter.ai/api/v1/chat/completions","sk-or-v1-...")
    MON=API_SERVERICE("https://api.kimi.com/coding/v1/chat/completions","sk-kimi-...")
    DS=API_SERVERICE("https://api.deepseek.com/chat/completions","sk-...")
    QW=API_SERVERICE("https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions","sk-...")
    BLB=API_SERVERICE("https://batch.dashscope.aliyuncs.com/compatible-mode/v1/chat/completions","sk-...")
    ACTIVE_API=MS
    API_OPTIONS=[("ModelScope",MS),("NVIDIA NIM",NIM),("NVIDIA NIM 2",NIM2),
                 ("阿里云百炼",BL),("天翼云",CT),("MiniMax",MM),
                 ("Mistral",MIS),("智谱 GLM",GLM),("小米 MiMo",MI),
                 ("OpenRouter",OR),("Kimi",MON),("DeepSeek",DS),("通义千问",QW)]

    pdf_cfg=PDF_CONVERT_Config()
    pdf_cfg.VOL=27
    pdf_cfg.OUTPUT_DIR=Path("./MEW_BRIEF/")
    cfg=Config(ACTIVE_API,pdf_cfg,True,1,"enable_thinking")
    cfg.MODEL="qwen/qwen3.8-flash-next"
    cfg.ENABLE_THINK=True
    cfg.TIMEOUT=httpx.Timeout(connect=10.0,read=600.0,write=120.0,pool=10.0)
    cfg.MAX_RETRIES=30
    cfg.MAX_TOKENS=65338
    cfg.SUPPORT_CACHE=[BL.API_URL,QW.API_URL]
    variable_prompt="请转换！"

    parser = argparse.ArgumentParser(description="文献查询系统")
    parser.add_argument("-v","--vol",type=int,help="卷号")
    parser.add_argument("-c","--MAX-CONCURRENT",dest="max_concurrent",type=int,help="最大线程")
    parser.add_argument("-p","--pages",type=str,help="页码")
    parser.add_argument("-m","--model",type=str,help="模型")
    parser.add_argument("--cache",action='store_true',help="启用缓存")
    args = parser.parse_args()
    cfg.VOL=args.vol if args.vol else cfg.VOL
    cfg.MODEL=args.model if args.model else cfg.MODEL
    cfg.MAX_CONCURRENT=args.max_concurrent if args.max_concurrent is not None else cfg.MAX_CONCURRENT
    if cfg.MAX_CONCURRENT<1:
        parser.error("最大线程必须大于 0")
    cfg.ENABLE_EXPLICIT_CACHE=not cfg.ENABLE_EXPLICIT_CACHE if args.cache else cfg.ENABLE_EXPLICIT_CACHE
    controller=AppController(cfg,API_OPTIONS,parse_pages(args.pages) if args.pages else [],variable_prompt)
    while True:
        if not controller.run(): break

if __name__ == "__main__":
    main()
