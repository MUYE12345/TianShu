"""
Tianshu 全局配置
使用 Pydantic Settings 从环境变量加载
"""
from pathlib import Path
from pydantic_settings import BaseSettings

# 项目根目录与数据目录 — 固定为绝对路径，避免因启动工作目录不同而解析到不同的库/数据目录
PROJECT_ROOT = Path(__file__).resolve().parents[1]  # …/Intelligen_housekeeper/
DATA_DIR = PROJECT_ROOT / "data"


class Settings(BaseSettings):
    # 应用
    APP_NAME: str = "Tianshu"
    DEBUG: bool = True

    # 数据库（默认指向项目 data 目录下的绝对路径）
    DATABASE_URL: str = f"sqlite:///{(DATA_DIR / 'housekeeper.db').as_posix()}"
    REDIS_URL: str = ""

    # JWT
    JWT_SECRET: str = "change-this-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440  # 24小时

    # 模型 - 主体模型
    MAIN_MODEL_API_BASE: str = ""
    MAIN_MODEL_API_KEY: str = ""
    MAIN_MODEL_NAME: str = ""
    MAIN_MODEL_TEMPERATURE: float = 0.7
    MAIN_MODEL_MAX_TOKENS: int = 8192
    MAIN_MODEL_PROVIDER: str = "openai"
    MAIN_MODEL_THINKING_MODE: bool = False
    MAIN_MODEL_THINKING_BUDGET: int = 4000

    # 模型 - 审查模型
    REVIEW_MODEL_API_BASE: str = ""
    REVIEW_MODEL_API_KEY: str = ""
    REVIEW_MODEL_NAME: str = ""
    REVIEW_MODEL_TEMPERATURE: float = 0.3
    REVIEW_MODEL_PROVIDER: str = "openai"
    REVIEW_MODEL_THINKING_MODE: bool = False

    # 嵌入 - RAG 向量化（provider: dashscope | local | auto）
    # auto 优先 DashScope text-embedding API，失败降级本地 MiniLM；两者皆无则纯 BM25 检索
    EMBEDDING_PROVIDER: str = "auto"
    EMBEDDING_MODEL: str = "text-embedding-v3"
    EMBEDDING_API_BASE: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    EMBEDDING_API_KEY: str = ""            # 空则回退 MAIN_MODEL_API_KEY
    EMBEDDING_DIM: int = 1024              # text-embedding-v3 支持 384/512/768/1024
    EMBEDDING_TIMEOUT: int = 60
    EMBEDDING_BATCH: int = 10              # DashScope text-embedding-v3 批量上限为 10

    # RAG - 检索参数
    RAG_CHUNK_SIZE: int = 700
    RAG_CHUNK_OVERLAP: int = 100
    RAG_TOP_K: int = 5
    RAG_CANDIDATE_K: int = 30              # BM25/语义各自取候选数
    RAG_RETRIEVE_CACHE_TTL: int = 60
    RAG_REWRITE: bool = True               # 多轮问答是否用 LLM 改写查询

    # RAG - 语义边界检测(父子分块)
    RAG_SEMANTIC_THRESHOLD: float = 0.75   # 边界带嵌入余弦阈值(低于则切)
    RAG_SEMANTIC_OVERLAP_LOW: float = 0.3  # 相邻段词项重叠率低于此 → 直接判新段
    RAG_SEMANTIC_OVERLAP_HIGH: float = 0.6  # 高于此 → 直接判同段;之间 → 嵌入二次确认
    RAG_CHILD_SIZE: int = 250              # 子块长度(检索单元)
    RAG_PARENT_MAX_CHARS: int = 2000       # 注入 prompt 的父块截断上限

    # RAG - 轻量实体图(GraphRAG)
    GRAPH_ENABLED: bool = True
    GRAPH_ENTITY_TOP_K: int = 8            # 检索时实体候选数
    GRAPH_BOOST: float = 0.2               # 图扩展命中的块的加分
    GRAPH_BUILD_BATCH: int = 5             # 每次 LLM 提取的父块数

    # RAG - Agentic 检索循环
    RAG_AGENT_MAX_RETRIES: int = 2         # 检索不足时最多重检轮数
    RAG_GRADE_HIGH: float = 0.60           # 启发式分数高于此 → 直接过
    RAG_GRADE_LOW: float = 0.35            # 低于此 → missing;之间 → LLM 评分
    RAG_AGENT_REFLECT: bool = True         # 是否做答案完整性反思

    # 论文 - OCR/翻译/解析并发与上限
    PAPER_OCR_MAX_PAGES: int = 40          # 扫描页视觉OCR最多处理页数
    PAPER_OCR_CONCURRENCY: int = 3         # 视觉OCR并行数
    PAPER_TRANSLATE_CONCURRENCY: int = 3   # 逐页翻译并行数
    PAPER_ANALYSIS_CONCURRENCY: int = 3    # 分段解析并行数

    # 多智能体 - 并发/超时
    MULTI_AGENT_MAX_WORKERS: int = 5
    MULTI_AGENT_WORKER_TIMEOUT: int = 120
    MULTI_AGENT_MAX_WORKER_LOOPS: int = 5
    MULTI_AGENT_MAX_TOOL_ROUNDS: int = 8

    # 推送 - 飞书
    FEISHU_WEBHOOK_URL: str = ""
    FEISHU_BOT_TOKEN: str = ""
    FEISHU_APP_ID: str = ""
    FEISHU_APP_SECRET: str = ""
    # 长连接模式(免公网): 启动时用 lark-oapi ws.Client 连飞书网关,
    # 用户发消息经长连接推送本地触发 agent, 不需要公网回调 URL
    FEISHU_LONG_CONNECTION: bool = False

    # 推送 - QQ邮箱
    QQMAIL_SMTP_HOST: str = "smtp.qq.com"
    QQMAIL_SMTP_PORT: int = 465
    QQMAIL_USER: str = ""
    QQMAIL_PASS: str = ""

    # 爬虫
    CRAWLER_TIMEOUT: int = 15
    CRAWLER_MAX_RETRIES: int = 3
    CRAWLER_USER_AGENT_ROTATE: bool = True

    # 推送 - 定时任务
    WEATHER_PUSH_TIME: str = "07:00"  # 早起看天气
    NEWS_PUSH_TIME: str = "09:00"     # 上班看新闻
    NEWS_PUSH_CHANNELS: str = "feishu,qqmail"

    # 搜索 - Google
    GOOGLE_API_KEY: str = ""
    GOOGLE_SEARCH_ENGINE_ID: str = ""

    # 天气 - 华风爱科天气 (https://openapi.weathercn.com)
    WEATHER_API_KEY: str = ""

    # 文件存储
    UPLOAD_DIR: str = str(DATA_DIR)
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50MB

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173"

    # 桌面应用(划屏翻译/桌宠): 默认不随服务端启动(服务端可无桌面环境),
    # 需要时置 true 或另跑 run_desktop.py
    LAUNCH_DESKTOP_APPS: bool = False

    # env_file 使用绝对路径，保证无论从哪个目录启动都能加载到项目 .env
    model_config = {
        "env_file": str(PROJECT_ROOT / ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
