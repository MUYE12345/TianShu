"""
对话记忆 — SQLite + FTS5全文搜索
参考: Hermes hermes_state.py (SQLite FTS5)
"""
import sqlite3
import json
from datetime import datetime
from typing import List, Optional

from backend.config import DATA_DIR


class ConversationMemory:
    """对话记忆提供者"""

    def __init__(self, db_path: str = str(DATA_DIR / "housekeeper.db")):
        self.db_path = db_path

    def initialize(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversation_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_cm_session
            ON conversation_memories(session_id)
        """)
        try:
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS conversation_fts
                USING fts5(session_id, content, content=conversation_memories, content_rowid=id)
            """)
        except sqlite3.OperationalError:
            pass  # FTS5可能不可用, 降级为LIKE搜索
        conn.commit()
        conn.close()

    def save(self, session_id: str, user_msg: str, asst_msg: str, metadata: dict = None):
        """保存一轮对话"""
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO conversation_memories (session_id, role, content, metadata) VALUES (?, 'user', ?, ?)",
            (session_id, user_msg, meta_json)
        )
        conn.execute(
            "INSERT INTO conversation_memories (session_id, role, content, metadata) VALUES (?, 'assistant', ?, ?)",
            (session_id, asst_msg, meta_json)
        )
        conn.commit()
        conn.close()

    def get_history(self, session_id: str, limit: int = 20) -> list:
        """获取会话历史"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT role, content, created_at FROM conversation_memories "
            "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit)
        )
        rows = cursor.fetchall()
        conn.close()
        return [{"role": r[0], "content": r[1], "time": r[2]} for r in reversed(rows)]

    def search(self, query: str, limit: int = 10) -> list:
        """全文搜索对话(FTS5优先, LIKE降级, 时效加权)"""
        import time
        conn = sqlite3.connect(self.db_path)
        rows = []
        used_fts5 = False

        # 尝试FTS5
        try:
            cursor = conn.execute(
                "SELECT cm.session_id, cm.content, cm.created_at "
                "FROM conversation_fts fts "
                "JOIN conversation_memories cm ON fts.rowid = cm.id "
                "WHERE conversation_fts MATCH ? "
                "ORDER BY rank LIMIT ?",
                (query, limit * 2)
            )
            rows = cursor.fetchall()
            used_fts5 = bool(rows)
        except (sqlite3.OperationalError, AttributeError):
            pass

        # 降级LIKE
        if not used_fts5:
            cursor = conn.execute(
                "SELECT session_id, content, created_at FROM conversation_memories "
                "WHERE content LIKE ? LIMIT ?",
                (f"%{query}%", limit * 2)
            )
            rows = cursor.fetchall()

        now = time.time()
        results = []
        for i, r in enumerate(rows):
            sid = r[0]
            content = r[1] or ""
            created_at = r[2] or ""

            rank_score = 1.0 / (i + 1)
            try:
                ts = datetime.fromisoformat(created_at).timestamp()
                age_days = (now - ts) / 86400
                time_w = 1.0 if age_days < 3 else max(0.4, 1.0 - (age_days - 3) / 20)
            except (ValueError, TypeError):
                time_w = 0.5

            final_score = rank_score * 0.7 + time_w * 0.3
            results.append({
                "session_id": sid,
                "content": content[:300],
                "score": round(final_score, 4),
                "time": str(created_at)[:19],
            })
            if len(results) >= limit:
                break

        results.sort(key=lambda x: x["score"], reverse=True)
        conn.close()
        return results[:limit]

    def evict_old(self, max_age_days: int = 90) -> int:
        """删除超过指定天数的对话记忆, 返回删除条数"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "DELETE FROM conversation_memories WHERE created_at < datetime('now', ?)",
            (f'-{max_age_days} days',)
        )
        deleted = cursor.rowcount
        # 重建FTS索引以反映删除
        try:
            conn.execute("INSERT INTO conversation_fts(conversation_fts) VALUES('rebuild')")
        except sqlite3.OperationalError:
            pass
        conn.commit()
        conn.close()
        return deleted
