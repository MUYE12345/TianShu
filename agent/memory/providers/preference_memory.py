"""
偏好记忆 — SQLite持久化 + LLM自动学习

存储结构(SQLite preferences表):
  id         INTEGER PRIMARY KEY AUTOINCREMENT
  user_id    TEXT NOT NULL          -- 用户标识
  pref_key   TEXT NOT NULL          -- 偏好键名
  pref_value TEXT NOT NULL          -- 偏好值(JSON序列化)
  confidence REAL NOT NULL DEFAULT 1.0  -- 置信度 0~1
  source     TEXT NOT NULL DEFAULT 'explicit'  -- explicit/inferred/learned
  count      INTEGER NOT NULL DEFAULT 1       -- 学习次数
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  UNIQUE(user_id, pref_key)

来源类型:
- explicit: 用户在设置中直接配置
- inferred: LLM从对话中推断
- learned: 多次对话确认的习惯
"""
import json
import os
import time
import sqlite3
from typing import Any, Optional, Dict, List

from backend.config import DATA_DIR


class PreferenceMemory:
    """偏好记忆提供者 — SQLite存储 + 内存缓存"""

    ALLOWED_KEYS = {
        "theme", "language", "news_sources", "daily_push_time",
        "output_detail", "greeting_style", "preferred_model",
        "interests", "timezone", "custom_rules",
    }

    def __init__(self, db_path: str = str(DATA_DIR / "housekeeper.db")):
        self.db_path = db_path
        self._cache: Dict[str, dict] = {}

    # ── 生命周期 ──

    def initialize(self):
        """初始化SQLite表并加载缓存"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL DEFAULT 'default',
                pref_key TEXT NOT NULL,
                pref_value TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 1.0,
                source TEXT NOT NULL DEFAULT 'explicit',
                count INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, pref_key)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_pref_user_key
            ON preferences(user_id, pref_key)
        """)
        conn.commit()
        conn.close()

        self._migrate_from_json()
        self._load_cache()
        print(f"[偏好记忆] 已加载 {len(self._cache)} 项偏好 (SQLite)")

    def _migrate_from_json(self):
        """从旧版JSON文件迁移数据到SQLite(仅首次运行)"""
        store_dir = os.path.join(os.path.dirname(self.db_path), "user_data")
        old_path = os.path.join(store_dir, "preferences.json")
        if not os.path.exists(old_path):
            return
        try:
            with open(old_path, "r", encoding="utf-8") as f:
                old_data = json.load(f)
            if not old_data:
                return
            conn = sqlite3.connect(self.db_path)
            for key, entry in old_data.items():
                raw = entry.get("value")
                value_json = json.dumps(raw, ensure_ascii=False) if not isinstance(raw, str) else raw
                conn.execute(
                    """INSERT OR IGNORE INTO preferences
                       (user_id, pref_key, pref_value, confidence, source, count, updated_at)
                       VALUES ('default', ?, ?, ?, ?, ?, ?)""",
                    (key, value_json,
                     entry.get("confidence", 1.0),
                     entry.get("source", "explicit"),
                     entry.get("count", 1),
                     entry.get("timestamp", time.time()))
                )
            conn.commit()
            conn.close()
            os.rename(old_path, old_path + ".bak")
            print(f"[偏好记忆] 已从旧JSON迁移 {len(old_data)} 项偏好")
        except Exception as e:
            print(f"[偏好记忆] JSON迁移跳过: {e}")

    def _load_cache(self):
        """从SQLite加载全部偏好到内存缓存"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT pref_key, pref_value, confidence, source, count, updated_at "
            "FROM preferences WHERE user_id = 'default'"
        )
        self._cache = {}
        for r in cursor.fetchall():
            key = r[0]
            raw = r[1]
            try:
                value = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                value = raw
            self._cache[key] = {
                "value": value,
                "confidence": r[2],
                "source": r[3],
                "count": r[4],
                "timestamp": r[5] if r[5] else time.time(),
            }
        conn.close()

    def _persist(self, key: str):
        """将单个key写回SQLite(UPSERT)"""
        entry = self._cache.get(key)
        if not entry:
            return
        raw = entry["value"]
        value_json = json.dumps(raw, ensure_ascii=False) if not isinstance(raw, str) else raw
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """INSERT INTO preferences
               (user_id, pref_key, pref_value, confidence, source, count, updated_at)
               VALUES ('default', ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(user_id, pref_key) DO UPDATE SET
                   pref_value = excluded.pref_value,
                   confidence = excluded.confidence,
                   source = excluded.source,
                   count = excluded.count,
                   updated_at = CURRENT_TIMESTAMP""",
            (key, value_json,
             entry["confidence"],
             entry["source"],
             entry.get("count", 1))
        )
        conn.commit()
        conn.close()

    # ── CRUD ──

    def get(self, key: str) -> Optional[Any]:
        """获取偏好值"""
        entry = self._cache.get(key)
        return entry["value"] if entry else None

    def set(self, key: str, value: Any, source: str = "explicit", confidence: float = 1.0):
        """设置偏好(用户显式设置)"""
        self._cache[key] = {
            "value": value,
            "source": source,
            "confidence": confidence,
            "timestamp": time.time(),
            "count": 1,
        }
        self._persist(key)

    def infer(self, key: str, value: Any, confidence: float = 0.5):
        """推断偏好(LLM推测, 低置信度累加)"""
        existing = self._cache.get(key)
        if existing and existing["confidence"] >= 0.9:
            return
        if existing and existing["source"] == "explicit":
            return

        new_conf = min(0.9, confidence + (existing["confidence"] * 0.3 if existing else 0))
        self._cache[key] = {
            "value": value,
            "source": "learned",
            "confidence": new_conf,
            "timestamp": time.time(),
            "count": (existing.get("count", 0) + 1) if existing else 1,
        }
        self._persist(key)

    def delete(self, key: str):
        """删除偏好"""
        self._cache.pop(key, None)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "DELETE FROM preferences WHERE user_id = 'default' AND pref_key = ?",
            (key,)
        )
        conn.commit()
        conn.close()

    def get_all(self) -> dict:
        """获取所有偏好(仅返回值)"""
        return {k: v["value"] for k, v in self._cache.items()}

    # ── 置信度查询 ──

    def get_by_confidence(self, min_confidence: float = 0.5) -> List[dict]:
        """按置信度阈值查询偏好, 结果按置信度降序

        Args:
            min_confidence: 最小置信度阈值 (0~1)

        Returns:
            [{"key": str, "value": Any, "confidence": float, "source": str}, ...]
        """
        results = []
        for key, entry in self._cache.items():
            conf = entry.get("confidence", 0)
            if conf >= min_confidence:
                results.append({
                    "key": key,
                    "value": entry["value"],
                    "confidence": conf,
                    "source": entry.get("source", "unknown"),
                })
        return sorted(results, key=lambda x: x["confidence"], reverse=True)

    # ── 上下文注入 ──

    def get_contextual(self, min_confidence: float = 0.3) -> str:
        """生成注入Agent上下文的偏好描述

        Args:
            min_confidence: 只包含置信度不低于此值的偏好

        Returns:
            格式化的Markdown字符串, 或空字符串
        """
        items = self.get_by_confidence(min_confidence)
        if not items:
            return ""

        parts = []
        for item in items:
            key = item["key"]
            value = item["value"]
            if key == "theme":
                parts.append(f"- 界面主题偏好: {value}")
            elif key == "language":
                parts.append(f"- 语言: {value}")
            elif key == "interests":
                if isinstance(value, list):
                    parts.append(f"- 关注领域: {', '.join(value)}")
                else:
                    parts.append(f"- 关注领域: {value}")
            elif key == "output_detail":
                parts.append(f"- 回答详细程度: {value}")
            elif key == "news_sources":
                if isinstance(value, list):
                    parts.append(f"- 常用新闻源: {', '.join(value)}")
            elif key == "greeting_style":
                parts.append(f"- 问候风格: {value}")
            elif key == "timezone":
                parts.append(f"- 时区: {value}")
            elif key == "preferred_model":
                parts.append(f"- 偏好模型: {value}")

        if parts:
            return "## 用户偏好 (已学习)\n" + "\n".join(parts) + "\n\n请根据这些偏好调整回答风格和内容。"
        return ""

    # ── LLM学习 ──

    def learn_from_conversation(self, user_msg: str, asst_msg: str, llm=None) -> list:
        """
        从对话中学习用户偏好

        LLM分析对话, 提取偏好信号:
        - 用户说"我喜欢简洁的回答" -> output_detail: brief
        - 用户问天气 -> interests: weather
        - 用户说"太复杂了" -> output_detail: simple
        - 用户说"用英文回答" -> language: en
        """
        if not llm:
            return []

        prompt = f"""从以下对话中提取用户偏好, 返回JSON数组。
可识别的偏好类型: theme(light/dark), language(zh/en), interests(列表), output_detail(brief/detailed/simple), greeting_style(formal/casual/friendly)

用户: {user_msg[:200]}
助手: {asst_msg[:200]}

如果没有明显的偏好信号, 返回空数组 []。
如果有, 返回: [{{"key": "偏好名", "value": "偏好值", "confidence": 0.1-0.8}}]"""

        try:
            result = llm.invoke(prompt)
            learned = json.loads(result)
            for item in learned:
                if item["key"] in self.ALLOWED_KEYS:
                    self.infer(item["key"], item["value"], item.get("confidence", 0.5))
            return learned
        except (json.JSONDecodeError, Exception):
            return []

    # ── 统计 ──

    def get_stats(self) -> dict:
        """偏好统计"""
        if not self._cache:
            return {"total": 0}
        sources = {}
        for v in self._cache.values():
            src = v.get("source", "unknown")
            sources[src] = sources.get(src, 0) + 1
        high_conf = sum(1 for v in self._cache.values() if v.get("confidence", 0) >= 0.8)
        return {
            "total": len(self._cache),
            "sources": sources,
            "high_confidence": high_conf,
            "keys": list(self._cache.keys()),
        }
