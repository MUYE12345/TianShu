"""
嵌入适配层 — 统一"文本 → 向量"入口，支持三种 provider 可切换。

provider:
  - dashscope : 阿里云 DashScope text-embedding API（OpenAI 兼容 /embeddings）
  - local     : 本地 sentence-transformers MiniLM（离线，需模型已下载）
  - auto      : 默认。先试 DashScope，失败自动降级本地；两者皆无则返回 None，
                由调用方降级为"仅 BM25 关键词检索"

使用：
    from backend.core.embedding_adapter import embedding_adapter
    vecs = embedding_adapter.encode(["文本一", "文本二"])   # list[list[float]]
    vec  = embedding_adapter.encode_one("查询")             # list[float] | None
"""
import hashlib
import json
import logging
import time

import httpx

from backend.config import settings
from backend.core.cache import request_cache

logger = logging.getLogger(__name__)


class EmbeddingAdapter:
    """可切换的嵌入提供者。线程不要求严格安全（单进程个人项目）。"""

    def __init__(self):
        self._provider = (settings.EMBEDDING_PROVIDER or "auto").lower()
        self._local_model = None       # 惰性加载的 sentence-transformers 模型
        self._fallback_state = None    # None | "dashscope" | "local" | "none"，auto 模式动态切换
        self._last_health_check = 0.0
        self._health_interval = 60.0   # 60s 内不重复健康检查
        self._resolved_dim = 0         # 探测出的实际向量维度

    # ── 配置 ──
    def _api_key(self) -> str:
        return settings.EMBEDDING_API_KEY or settings.MAIN_MODEL_API_KEY or ""

    def active_provider(self) -> str:
        """返回当前实际生效的 provider（auto 经健康检查后解析出的）。"""
        self._ensure_resolved()
        return self._fallback_state or self._provider

    # ── 健康检查：决定 auto 模式走哪条路 ──
    def _ensure_resolved(self):
        if self._provider != "auto":
            return
        now = time.time()
        if self._fallback_state is not None and now - self._last_health_check < self._health_interval:
            return
        # DashScope 可用性：轻量探测一次（空 input 也能返回，仅测连通）
        ok = self._dashscope_probe()
        self._fallback_state = "dashscope" if ok else ("local" if self._local_available() else "none")
        self._last_health_check = now
        logger.info("[Embedding] provider=auto 解析为 %s", self._fallback_state)

    def _dashscope_probe(self) -> bool:
        try:
            key = self._api_key()
            if not key:
                return False
            with httpx.Client(timeout=10) as client:
                resp = client.post(
                    f"{settings.EMBEDDING_API_BASE}/embeddings",
                    headers={"Authorization": f"Bearer {key}",
                             "Content-Type": "application/json"},
                    json={"model": settings.EMBEDDING_MODEL, "input": ["ping"]},
                )
                return resp.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    def _local_available(self) -> bool:
        try:
            import sentence_transformers  # noqa: F401
            return True
        except ImportError:
            return False

    # ── 本地模型 ──
    def _get_local_model(self):
        if self._local_model is not None:
            return self._local_model
        try:
            from sentence_transformers import SentenceTransformer
            self._local_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
            logger.info("[Embedding] 本地 MiniLM 模型加载完成")
        except Exception as e:  # noqa: BLE001
            logger.warning("[Embedding] 本地 MiniLM 不可用: %s", e)
            self._local_model = None
        return self._local_model

    def _local_encode(self, texts: list) -> list | None:
        model = self._get_local_model()
        if model is None:
            return None
        try:
            vecs = model.encode(texts)
            return [v.tolist() for v in vecs]
        except Exception as e:  # noqa: BLE001
            logger.warning("[Embedding] 本地编码失败: %s", e)
            return None

    # ── DashScope 批量编码 ──
    def _dashscope_encode(self, texts: list) -> list | None:
        key = self._api_key()
        if not key:
            return None
        out: list = []
        batch = max(1, int(settings.EMBEDDING_BATCH or 25))
        try:
            with httpx.Client(timeout=settings.EMBEDDING_TIMEOUT) as client:
                for i in range(0, len(texts), batch):
                    chunk = texts[i:i + batch]
                    payload = {"model": settings.EMBEDDING_MODEL, "input": chunk}
                    if self.dim:
                        payload["dimensions"] = self.dim
                    resp = client.post(
                        f"{settings.EMBEDDING_API_BASE}/embeddings",
                        headers={"Authorization": f"Bearer {key}",
                                 "Content-Type": "application/json"},
                        json=payload,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    for item in data["data"]:
                        out.append(item["embedding"])
            return out
        except Exception as e:  # noqa: BLE001
            logger.warning("[Embedding] DashScope 编码失败: %s", e)
            return None

    # ── 对外接口 ──
    def encode(self, texts: list, use_cache: bool = False) -> list | None:
        """
        批量编码。返回 list[list[float]]；不可用返回 None（调用方降级 BM25）。
        use_cache=True 时对输入做哈希缓存（适合 query，避免重复 API 调用）。
        """
        if not texts:
            return []
        texts = [t if isinstance(t, str) else str(t) for t in texts]

        if use_cache and len(texts) == 1:
            key = f"emb:{hashlib.md5(texts[0].encode('utf-8')).hexdigest()}"
            cached = request_cache.get(key)
            if cached is not None:
                return cached

        self._ensure_resolved()
        provider = self._fallback_state if self._provider == "auto" else self._provider

        if provider == "dashscope":
            vecs = self._dashscope_encode(texts)
            if vecs is None and self._provider == "auto":
                logger.info("[Embedding] auto 降级到本地 MiniLM")
                self._fallback_state = "local"
                vecs = self._local_encode(texts)
        elif provider == "local":
            vecs = self._local_encode(texts)
            if vecs is None and self._provider == "auto":
                self._fallback_state = "dashscope"
                vecs = self._dashscope_encode(texts)
        else:
            vecs = self._dashscope_encode(texts)
            if vecs is None:
                vecs = self._local_encode(texts)
            if vecs is None:
                self._fallback_state = "none"

        if vecs is not None and use_cache and len(texts) == 1:
            request_cache.set(key, vecs, ttl=3600)
        return vecs

    def encode_one(self, text: str, use_cache: bool = True) -> list | None:
        """单条编码（查询/单文本）。失败返回 None。"""
        vecs = self.encode([text], use_cache=use_cache)
        if not vecs:
            return None
        return vecs[0]

    @property
    def dim(self) -> int:
        return int(settings.EMBEDDING_DIM or 1024)

    def resolve_dim(self) -> int:
        """实际向量维度(探测一次并缓存)。失败回退配置值。"""
        if self._resolved_dim:
            return self._resolved_dim
        v = self.encode_one("维度探测", use_cache=False)
        self._resolved_dim = len(v) if v else self.dim
        return self._resolved_dim

    def health(self) -> dict:
        """供 /api 健康检查或调试。"""
        return {
            "configured_provider": self._provider,
            "active_provider": self.active_provider(),
            "dim": self.dim,
            "api_base": settings.EMBEDDING_API_BASE,
            "model": settings.EMBEDDING_MODEL,
        }


embedding_adapter = EmbeddingAdapter()


if __name__ == "__main__":
    # 手动验证: python -m backend.core.embedding_adapter
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    h = embedding_adapter.health()
    print("health:", h)
    v = embedding_adapter.encode_one("大语言模型的检索增强生成")
    if v:
        print("向量维度:", len(v), "前5:", v[:5])
    else:
        print("嵌入不可用，将降级为纯 BM25 检索")
