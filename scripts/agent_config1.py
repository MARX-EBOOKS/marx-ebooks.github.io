from pathlib import Path
import httpx
# 配置
class Config:
    SKILLS_DIR = Path("./skills") #skills文件存放位置，可自行编辑
    # ── API ────────────────────────────────────────────────────────────────
    API_KEY          = r"sk-xxxxxxxx/xxxxxxxxxx/nvapi-xxxxxxxx" #api密钥，自行填写，如本地部署一般可忽略
   #API_URL        = r"https://api.openai.com/v1/responses" #openai Chat-GPT
   #API_URL        = r"https://openrouter.ai/api/v1/chat/completions"#openrouters
   #API_URL        = r"https://api.deepseek.com/chat/completions" #deepseek
   #API_URL        =r"https://integrate.api.nvidia.com/v1/chat/completions" #NVIDIA NIM免费API
    API_URL        = r"http://localhost:17117/v1/chat/completions", #本地部署模型的端口、链接，此处端口号为17117
    MODELS            = ["glm-4.7-flash","glm-4-flash","glm-5","deepseek-reasoner","deepseek-v3.2","qwen3.5-plus","qwen3-max","kimi-k2.5","minimax-m2.5","kimi-k2-thinking","gpt-5.4","nvidia/nemotron-3-nano-30b-a3b","nvidia/nemotron-3-super-120b-a12b"] #可自行编辑，根据api支持的模型名称填写
    MODEL=MODELS[0] #最终选择的模型，根据以上数组的编号选择对应模型
    MAX_TOKENS       = 64000 #最大输出token
    COMPRESS_HISTORY = True #是否压缩对话历史
    ENABLE_THINKING_default = True #思考模式默认状态
    MODEL_THINK_TYPE="enable_thinking" #思考模式配置方式
    #MODEL_THINK_TYPE="thinking"
    #MODEL_THINK_TYPE="reasoning_effort"
    #MODEL_THINK_TYPE="chat_template_kwargs"
    TEMPERATURE      = 1 #控制模型输出随机性
    TOP_P            = 0.9 #控制模型关联token输出
    MAX_RETRIES      = 2 #模型请求连接失败时重试数
    RETRY_WAIT       = 300 #请求失败时等待时间
    MAX_CONCURRENT   = 1 #最大并发数
    TIMEOUT          = httpx.Timeout(connect=10.0,read=3600.0,write=3600.0,pool=10.0) #超时时间设置，单位秒
    # ── Search ─────────────────────────────────────────────────────────────
    MAX_HITS              = 20 #最大匹配数
    TRANS_CHUNK_CHARS     = 6000 #翻译分段大小
    MAX_TOOL_RESULT_CHARS = 1000 #各工具结果最大字符数
    MODEL_MAX_CONTEXT_TOKEN     = 202000 #模型最大上下文窗口token，根据技术文档填写
    COMPRESS_THRESHOLD =MODEL_MAX_CONTEXT_TOKEN-MAX_TOKENS #压缩阈值，最大上下文-最大输出token
    # ── Paths ──────────────────────────────────────────────────────────────
    HTML_FOLDER         =".." #文件目录，自行配置，此处为仓库主目录（即agent的上一级文件夹）
    HISTORY_OUTPUT_PATH = r"./aioutput" #ai记录保存目录，可自行设置
    # ── Runtime defaults ───────────────────────────────────────────────────
    DISPLAY_TOOLS   = True #工具显示默认状态
    DEEP_READ       = True #深度阅读默认状态
    LANG_NAMES = {
        "zh": "Chinese", "de": "German",
        "en": "English", "ru": "Russian", "fr": "French",
    }
    #请确保以下目录均在同一主文件夹内
    ZH_DIRS = ["docs/MEW-ZH", "docs/MEA", "docs/LENIN"]
    DE_DIRS = [
        "docs/MEW-ZENO", "MEW",
        *[f"docs/HEGEL/{v}" for v in (1, 2, 3, 4, 5, 7, 10, 11, 12, 13, 16, 18)],
    ]
    EN_DIRS = ["en/MECW"]
    RU_DIRS = ["ru/VIL-FB2", "ru/VIL-UAIO"]
    SPECIAL_DIRS: dict[str, tuple[str, str]] = {
        "MEW/":      ("important_works_me", "MEW.md"),
        "docs/MEW-ZENO/": ("",                   "MEW_ZENO.md"),
        "en/MECW/":       ("important_works_me", "MECW.md"),
        "docs/MEW-ZH/":   ("",                   "MEW_ZH.md"),
        "docs/MEA/":      ("",                   "MEA.md"),
        "ru/VIL-FB2/":    ("important_works_vl", "VIL_FB2.md"),
        "ru/VIL-UAIO/":   ("important_works_vl", "VIL_UAIO.md"),
    }
    RAG_DB_PATH    = "./mydb_lance"
    EMBED_BASE_URL = "https://integrate.api.nvidia.com/v1"
    #EMBED_BASE_URL = "http://localhost:17117/v1"
    EMBED_API_KEY  = "nvapi-xxxxxx"
    EMBED_MODEL    = "nvidia/llama-nemotron-embed-1b-v2"
    EMBED_TIMEOUT  = 120

    def __init__(self):
        self.library_map        = self._load("LIB_MAP.md")
        self.important_works_me = self._load("IMPORTANT_WORK_ME.md")
        self.important_works_vl = self._load("IMPORTANT_WORK_VL.md")
        self.system_prompt      = self._load("SYSTEM.md").replace("{LIBRARY_MAP}", self.library_map).replace("{SYS_MAX_TOOL_RESULT_CHARS}", f"{self.MAX_TOOL_RESULT_CHARS}")
        self.system_prompt_simp  = self._load("SYS_SIMP.md").replace("{LIBRARY_MAP}", self.library_map).replace("{SYS_MAX_TOOL_RESULT_CHARS}", f"{self.MAX_TOOL_RESULT_CHARS}")
        self.mode_deep_read     = self._load("READ.md")
        self.trans_prompt_html  = self._load("TRANS.md")
        self.trans_prompt_text  = self._load("TRANS_TEXT.md")
        self._dir_texts: dict[str, str] = {
            fname: self._load(fname)
            for _, fname in self.SPECIAL_DIRS.values()
        }
        self.ENABLE_THINKING=self.ENABLE_THINKING_default

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
        return mapping.get(self.MODEL_THINK_TYPE)

    def _load(self, filename: str) -> str:
        p = self.SKILLS_DIR / filename
        return p.read_text(encoding="utf-8-sig").strip() if p.exists() else ""

    def dir_text(self, filename: str) -> str:
        return self._dir_texts.get(filename, "")

    def prefix_for(self, attr: str) -> str:
        return getattr(self, attr, "") if attr else ""
