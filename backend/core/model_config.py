"""
三层模型配置管理（主体模型 / 审查模型 / OCR 模型）
支持多 LLM 提供商（openai、anthropic 等），通过适配器模式解耦。
"""
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from backend.config import settings

from .adapters import AnthropicAdapter, BaseLLMAdapter, OpenAIAdapter


# ---------------------------------------------------------------------------
# 配置数据类
# ---------------------------------------------------------------------------

@dataclass
class LLMConfig:
    """单个 LLM 实例的配置参数。"""
    provider: str = "openai"
    api_base: str = ""
    api_key: str = ""
    model_name: str = ""
    temperature: float = 0.7
    max_tokens: int = 8192
    thinking_mode: bool = False
    thinking_budget: int = 4000
    extra_kwargs: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 适配器注册与模型管理器
# ---------------------------------------------------------------------------

class ModelManager:
    """全局模型管理器（单例）。

    职责：
    - 维护  ``{provider -> adapter}``  的映射表。
    - 根据 ``LLMConfig`` 中的 provider 自动选取适配器。
    - 对外提供 ``get_main_llm()`` / ``get_review_llm()`` 快捷方法。
    """

    _instance = None
    _adapters: Dict[str, BaseLLMAdapter] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # ---------- 注册内置适配器 ----------
        if "openai" not in self._adapters:
            self.register_adapter("openai", OpenAIAdapter())
        if "anthropic" not in self._adapters:
            self.register_adapter("anthropic", AnthropicAdapter())

        # ---------- 主体模型配置 ----------
        self.main_config = LLMConfig(
            provider=settings.MAIN_MODEL_PROVIDER,
            api_base=settings.MAIN_MODEL_API_BASE,
            api_key=settings.MAIN_MODEL_API_KEY,
            model_name=settings.MAIN_MODEL_NAME,
            temperature=settings.MAIN_MODEL_TEMPERATURE,
            max_tokens=settings.MAIN_MODEL_MAX_TOKENS,
            thinking_mode=settings.MAIN_MODEL_THINKING_MODE,
            thinking_budget=settings.MAIN_MODEL_THINKING_BUDGET,
        )
        # ---------- 审查模型配置 ----------
        self.review_config = LLMConfig(
            provider=settings.REVIEW_MODEL_PROVIDER,
            api_base=settings.REVIEW_MODEL_API_BASE,
            api_key=settings.REVIEW_MODEL_API_KEY,
            model_name=settings.REVIEW_MODEL_NAME,
            temperature=settings.REVIEW_MODEL_TEMPERATURE,
            max_tokens=4096,
            thinking_mode=settings.REVIEW_MODEL_THINKING_MODE,
        )

        # 内部缓存，避免每次调用都构造适配器
        self._main_adapter: Optional[BaseLLMAdapter] = None
        self._review_adapter: Optional[BaseLLMAdapter] = None

        # ---------- 从 settings 读取的 extra kwargs ----------
        self._main_extra: Dict[str, Any] = {}
        self._review_extra: Dict[str, Any] = {}

    # ---- 适配器注册 ----

    @classmethod
    def register_adapter(cls, provider: str, adapter: BaseLLMAdapter) -> None:
        """注册（或覆盖）某个 provider 对应的适配器。"""
        cls._adapters[provider] = adapter

    @classmethod
    def get_adapter(cls, provider: str) -> BaseLLMAdapter:
        """根据 provider 名称获取适配器，不存在则抛出 KeyError。"""
        if provider not in cls._adapters:
            raise KeyError(f"未注册的 LLM provider: {provider}。"
                           f" 已注册: {list(cls._adapters)}")
        return cls._adapters[provider]

    # ---- 构建适配器实例（含 config） ----

    def _build_adapter(self, config: LLMConfig) -> BaseLLMAdapter:
        """根据 LLMConfig 构造已注入 api_base / api_key / model 的适配器。"""
        adapter_cls = self.get_adapter(config.provider)
        # 用 config 中的 api_base / api_key 覆盖适配器默认值
        adapter_cls.api_base = config.api_base or adapter_cls.api_base
        adapter_cls.api_key = config.api_key or adapter_cls.api_key
        adapter_cls.default_model = config.model_name
        return adapter_cls

    # ---- 对外接口 ----

    def get_main_llm(self) -> BaseLLMAdapter:
        """获取主体模型适配器（已注入端点与密钥）。"""
        if self._main_adapter is None:
            self._main_adapter = self._build_adapter(self.main_config)
        return self._main_adapter

    def get_review_llm(self) -> BaseLLMAdapter:
        """获取审查模型适配器（已注入端点与密钥）。"""
        if self._review_adapter is None:
            self._review_adapter = self._build_adapter(self.review_config)
        return self._review_adapter

    def get_vision_model(self) -> str:
        """返回可用的视觉模型名（供截图翻译/图片OCR使用）。

        优先取 DB 里 vision_support=1 且启用的模型；否则回退 qwen3.6-flash。
        """
        try:
            from backend.models.model_provider import ModelProvider
            from backend.database import SessionLocal
            db = SessionLocal()
            try:
                m = db.query(ModelProvider).filter(
                    ModelProvider.vision_support == True,  # noqa: E712
                    ModelProvider.is_active == True,  # noqa: E712
                ).first()
                if m and m.model_name:
                    return m.model_name
            finally:
                db.close()
        except Exception:
            pass
        return "qwen3.6-flash"

    # ---- thinking kwargs ----

    def get_thinking_kwargs(self, config: LLMConfig, runtime_enabled: bool = None) -> dict:
        """构建 thinking 相关参数，用于传递给适配器。

        Args:
            config: LLM 配置
            runtime_enabled: 运行时覆盖（None 表示使用配置值）
        """
        enabled = runtime_enabled if runtime_enabled is not None else config.thinking_mode
        if not enabled:
            return {}

        provider = config.provider
        if provider == "anthropic":
            return {
                "thinking": {
                    "type": "enabled",
                    "budget_tokens": config.thinking_budget,
                }
            }
        elif provider == "openai":
            # OpenAI 兼容 API: DeepSeek-reasoner 不需要额外参数（模型自带思考）
            # 通义千问 enable_thinking, OpenAI o-series reasoning_effort
            model_lower = config.model_name.lower()
            if "deepseek-reasoner" in model_lower or "deepseek-r1" in model_lower:
                return {}  # DeepSeek reasoner 自带思考，不需要额外参数
            if "qwen" in model_lower or "qwq" in model_lower:
                return {"enable_thinking": True}
            if any(m in model_lower for m in ("o1", "o3", "o4")):
                return {"reasoning_effort": "medium"}
            # 通用 OpenAI 兼容 API：尝试 enable_thinking
            return {"enable_thinking": True}
        return {}

    # ---- 运行时更新 ----

    def reload_from_db(self, db_session=None):
        """从数据库模型表重新加载配置。

        如果有数据库记录则用数据库值覆盖 .env 配置。
        """
        if db_session is None:
            return
        try:
            from backend.models.model_provider import ModelProvider
            models = db_session.query(ModelProvider).filter(ModelProvider.is_active).all()

            # LLM 模型：按 is_default 排序
            llm_models = [m for m in models if m.model_type == "llm"]
            chat = None
            review = None
            multimodal = None
            embedding = None

            # 默认对话模型
            chat = next((m for m in llm_models if m.is_default), None)
            if not chat and llm_models:
                chat = llm_models[0]

            # 审查模型：非默认的 LLM，或同个模型的第二个配置
            if chat and len(llm_models) > 1:
                review = next((m for m in llm_models if m.id != chat.id), None)

            if chat:
                self.main_config.provider = chat.provider
                self.main_config.api_base = chat.api_base
                self.main_config.api_key = chat.api_key
                self.main_config.model_name = chat.model_name
                self.main_config.temperature = float(chat.temperature) if chat.temperature else 0.7
                self.main_config.max_tokens = chat.max_tokens
                self.main_config.thinking_mode = bool(chat.thinking_mode)
                self.main_config.thinking_budget = chat.thinking_budget
                self._main_adapter = None

            if review:
                self.review_config.provider = review.provider
                self.review_config.api_base = review.api_base
                self.review_config.api_key = review.api_key
                self.review_config.model_name = review.model_name
                self.review_config.temperature = float(review.temperature) if review.temperature else 0.3
                self.review_config.max_tokens = review.max_tokens
                self.review_config.thinking_mode = bool(review.thinking_mode)
                self._review_adapter = None
            else:
                # 只有一个 LLM 时，审查模型与主体模型保持同步，避免调用失效模型
                self.review_config.provider = self.main_config.provider
                self.review_config.api_base = self.main_config.api_base
                self.review_config.api_key = self.main_config.api_key
                self.review_config.model_name = self.main_config.model_name
                self.review_config.temperature = 0.3
                self.review_config.max_tokens = self.main_config.max_tokens
                self._review_adapter = None
        except Exception:
            pass  # 静默失败，使用 .env 兜底

    def update_config(self, main: dict = None, review: dict = None):
        """动态更新模型配置并清空对应缓存。"""
        if main:
            self.main_config = LLMConfig(**{**self.main_config.__dict__, **main})
            self._main_adapter = None
        if review:
            self.review_config = LLMConfig(**{**self.review_config.__dict__, **review})
            self._review_adapter = None


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

model_manager = ModelManager()
