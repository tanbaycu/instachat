from datetime import datetime
import os
import random
import sqlite3
import threading
from typing import Any, Dict, List, Optional

from config.config_manager import get_data_dir
from memory.nlp import NLP, sanitize_filename


class SQLiteMemoryStore:
    """Kho lưu trữ ký ức bền vững bằng SQLite, cô lập hoàn toàn theo từng user_id."""

    def __init__(self, db_path: Optional[str] = None):
        memories_dir = get_data_dir("memories")
        self.db_path = db_path or os.path.join(memories_dir, "memory.db")
        os.makedirs(os.path.dirname(self.db_path) or memories_dir, exist_ok=True)
        self._lock = threading.RLock()
        self.nlp = NLP()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS short_context (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_short_user ON short_context (user_id, id)"
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS long_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    content TEXT NOT NULL,
                    keywords TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    access_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_long_user ON long_memories (user_id, id)"
            )
            self._conn.commit()

    def save_turn(
        self,
        user_id: str,
        user_message: str,
        bot_response: str,
        short_limit: int = 12,
        save_long_term: bool = True,
    ) -> None:
        """Lưu một lượt hỏi-đáp vào ngữ cảnh ngắn hạn và trích xuất ký ức dài hạn."""
        user_msg = " ".join((user_message or "").split())
        bot_msg = " ".join((bot_response or "").split())
        if not user_msg and not bot_msg:
            return

        now = datetime.now().isoformat()
        with self._lock:
            cur = self._conn.cursor()
            if user_msg:
                cur.execute(
                    "INSERT INTO short_context (user_id, role, message, created_at) VALUES (?, ?, ?, ?)",
                    (user_id, "user", user_msg, now),
                )
            if bot_msg:
                cur.execute(
                    "INSERT INTO short_context (user_id, role, message, created_at) VALUES (?, ?, ?, ?)",
                    (user_id, "bot", bot_msg, now),
                )

            # Giữ tối đa short_limit * 2 bản ghi gần nhất cho mỗi user
            max_rows = max(2, int(short_limit) * 2)
            cur.execute(
                """
                DELETE FROM short_context
                WHERE user_id = ? AND id NOT IN (
                    SELECT id FROM short_context
                    WHERE user_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                )
                """,
                (user_id, user_id, max_rows),
            )

            if save_long_term and user_msg:
                keywords = " ".join(self.nlp.tokenize_meaningful(user_msg)[:12])
                topic = keywords[:60] if keywords else user_msg[:60]
                content = f"user: {user_msg} | bot: {bot_msg}" if bot_msg else f"user: {user_msg}"
                cur.execute(
                    """
                    INSERT INTO long_memories (user_id, topic, content, keywords, created_at, access_count)
                    VALUES (?, ?, ?, ?, ?, 0)
                    """,
                    (user_id, topic, content, keywords, now),
                )

            self._conn.commit()

    def get_short_context(self, user_id: str, limit: int = 12) -> List[Dict[str, str]]:
        """Lấy lịch sử hội thoại gần đây của riêng user_id theo đúng thứ tự thời gian."""
        max_rows = max(1, int(limit))
        with self._lock:
            cur = self._conn.cursor()
            rows = cur.execute(
                """
                SELECT role, message, created_at
                FROM short_context
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, max_rows),
            ).fetchall()

        return [
            {"role": row["role"], "message": row["message"], "created_at": row["created_at"]}
            for row in reversed(rows)
        ]

    def get_short_context_lines(self, user_id: str, limit: int = 12) -> List[str]:
        return [f"{item['role']}: {item['message']}" for item in self.get_short_context(user_id, limit)]

    def save_long_memory(self, user_id: str, topic: str, content: str, keywords: str = "") -> None:
        now = datetime.now().isoformat()
        kw = keywords or " ".join(self.nlp.tokenize_meaningful(f"{topic} {content}")[:15])
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO long_memories (user_id, topic, content, keywords, created_at, access_count)
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                (user_id, topic, content, kw, now),
            )
            self._conn.commit()

    def search_memories(
        self, user_id: str, query: str, limit: int = 5, min_score: float = 0.15
    ) -> List[str]:
        """Truy xuất ký ức liên quan nhất của user_id dựa trên keyword overlap + độ tương đồng."""
        if not query or not query.strip():
            return []

        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, topic, content, keywords
                FROM long_memories
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT 250
                """,
                (user_id,),
            ).fetchall()

        if not rows:
            return []

        scored: List[tuple[float, int, str]] = []
        for row in rows:
            candidate_text = f"{row['topic']} {row['keywords']} {row['content']}"
            score = self.nlp.similarity(query, candidate_text)
            if score >= min_score:
                scored.append((score, row["id"], row["content"]))

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        top_items = scored[:limit]

        if top_items:
            ids = [(item[1],) for item in top_items]
            with self._lock:
                self._conn.executemany(
                    "UPDATE long_memories SET access_count = access_count + 1 WHERE id = ?",
                    ids,
                )
                self._conn.commit()

        return [item[2] for item in top_items]

    def clear_short_context(self, user_id: Optional[str] = None) -> None:
        with self._lock:
            if user_id is None:
                self._conn.execute("DELETE FROM short_context")
            else:
                self._conn.execute("DELETE FROM short_context WHERE user_id = ?", (user_id,))
            self._conn.commit()

    def get_stats(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            if user_id:
                short_cnt = self._conn.execute(
                    "SELECT COUNT(*) FROM short_context WHERE user_id = ?", (user_id,)
                ).fetchone()[0]
                long_cnt = self._conn.execute(
                    "SELECT COUNT(*) FROM long_memories WHERE user_id = ?", (user_id,)
                ).fetchone()[0]
            else:
                short_cnt = self._conn.execute("SELECT COUNT(*) FROM short_context").fetchone()[0]
                long_cnt = self._conn.execute("SELECT COUNT(*) FROM long_memories").fetchone()[0]

            return {
                "short_context_count": int(short_cnt),
                "long_memories_count": int(long_cnt),
                "db_path": self.db_path,
            }

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()


# ==============================================================================
# Các lớp file-based tương thích ngược (đã sửa lỗi IndexError, negative slice & path safety)
# ==============================================================================


class ActivateLocalMemories:
    """Đọc file ký ức tương đồng nhất trong thư mục memories (tương thích ngược)."""

    def __init__(self, limit_mem_storage: int = 4, MEMORIES_DIR: Optional[str] = None):
        self.limit_mem_storage = max(1, int(limit_mem_storage))
        self.MEMORIES_DIR = MEMORIES_DIR or get_data_dir("memories")
        os.makedirs(self.MEMORIES_DIR, exist_ok=True)
        self.nlp = NLP()

    def activate_localMemories(self, inp: str) -> Optional[List[str]]:
        if not inp or not os.path.exists(self.MEMORIES_DIR):
            return None

        list_mem_name = [
            f[:-4] for f in os.listdir(self.MEMORIES_DIR) if f.endswith(".txt")
        ]
        if not list_mem_name:
            return None

        best_score = 0.0
        best_name = ""
        for mem_name in list_mem_name:
            score = self.nlp.similarity(inp, mem_name.replace("_", " "))
            if score > best_score:
                best_score = score
                best_name = mem_name

        if not best_name:
            return None

        file_path = os.path.join(self.MEMORIES_DIR, f"{best_name}.txt")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = [line for line in f.read().splitlines() if line.strip()]

            if not lines:
                return None

            if len(lines) > self.limit_mem_storage:
                # Giới hạn start index >= 0 để không bao giờ tạo slice âm gây trả về rỗng
                max_start = max(0, len(lines) - self.limit_mem_storage)
                start = random.randint(0, max_start)
                lines = lines[start : start + self.limit_mem_storage]

            return lines or None
        except Exception as exc:
            print(f"[MEMORY] ⚠️ Lỗi đọc file {file_path}: {exc}")
            return None


class ShortContextManager:
    """Quản lý ngữ cảnh ngắn hạn với backup ra file (tương thích ngược)."""

    def __init__(
        self,
        s: str,
        t: str,
        max_limit_short_mem_contxt: int = 4,
        TEMP_MEM_BACKUP_DIR: Optional[str] = None,
    ):
        self.max_limit_short_mem_contxt = max(2, int(max_limit_short_mem_contxt))
        self.s = s
        self.t = t
        self.context: List[str] = []
        self.TEMP_MEM_BACKUP_DIR = TEMP_MEM_BACKUP_DIR or os.path.join(
            get_data_dir("memories"), "backup"
        )
        os.makedirs(self.TEMP_MEM_BACKUP_DIR, exist_ok=True)
        self.read_backup()

    def _backup_file(self) -> str:
        return os.path.join(self.TEMP_MEM_BACKUP_DIR, "short_context_backup.txt")

    def read_backup(self) -> None:
        path = self._backup_file()
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                self.context = [line for line in f.read().strip().splitlines() if line.strip()]

    def backup_short_context_writer(self) -> None:
        os.makedirs(self.TEMP_MEM_BACKUP_DIR, exist_ok=True)
        with open(self._backup_file(), "w", encoding="utf-8") as f:
            f.write("\n".join(self.context))

    def save_to_shortContextMem(self, inp: str, ans: str) -> None:
        inp_clean, ans_clean = " ".join(inp.split()), " ".join(ans.split())
        self.context.append(self.s + inp_clean)
        self.context.append(self.t + ans_clean)

        if len(self.context) > self.max_limit_short_mem_contxt:
            self.context = self.context[-self.max_limit_short_mem_contxt :]

        self.backup_short_context_writer()

    def activate_short_context(self) -> Optional[List[str]]:
        return self.context if self.context else None

    def activate_shortContetxMem(self) -> Optional[List[str]]:
        return self.activate_short_context()


class WriteNewLocalMemories:
    """Ghi bộ nhớ dài hạn ra file .txt an toàn (đã sửa triệt để IndexError và filename)."""

    def __init__(
        self,
        max_mem_context_towrite: int = 10,
        s: str = "s object: ",
        t: str = "t object: ",
        MEMORIES_DIR: Optional[str] = None,
        TEMP_MEM_BACKUP_DIR: Optional[str] = None,
    ):
        self.max_mem_context_towrite = max(2, int(max_mem_context_towrite))
        self.s = s
        self.t = t
        self.CONTEXT: List[str] = []
        self.MEMORIES_DIR = MEMORIES_DIR or get_data_dir("memories")
        self.TEMP_MEM_BACKUP_DIR = TEMP_MEM_BACKUP_DIR or os.path.join(
            get_data_dir("memories"), "backup"
        )
        os.makedirs(self.MEMORIES_DIR, exist_ok=True)
        os.makedirs(self.TEMP_MEM_BACKUP_DIR, exist_ok=True)
        self.nlp = NLP()
        self.read_context_backup()

    def _backup_file(self) -> str:
        return os.path.join(self.TEMP_MEM_BACKUP_DIR, "backup_contxt_writer.txt")

    def read_context_backup(self) -> None:
        path = self._backup_file()
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                self.CONTEXT = [line for line in f.read().splitlines() if line.strip()]

    def backup_contxt_writer(self) -> None:
        os.makedirs(self.TEMP_MEM_BACKUP_DIR, exist_ok=True)
        with open(self._backup_file(), "w", encoding="utf-8") as f:
            f.write("\n".join(self.CONTEXT))

    def w(self, inp: str, ans: str, filename: str) -> None:
        inp_clean, ans_clean = " ".join(inp.split()), " ".join(ans.split())
        list_mem_name = [
            f[:-4] for f in os.listdir(self.MEMORIES_DIR) if f.endswith(".txt")
        ]

        most_mem_n = 0.0
        most_mem = ""
        query_head = " ".join(inp_clean.split()[:10])
        for mem_name in list_mem_name:
            score = self.nlp.similarity(query_head, mem_name.replace("_", " "))
            if score > most_mem_n:
                most_mem_n = score
                most_mem = mem_name

        safe_target = most_mem if (most_mem_n > 0.5 and most_mem) else sanitize_filename(filename)
        target_path = os.path.join(self.MEMORIES_DIR, f"{safe_target}.txt")
        with open(target_path, "a", encoding="utf-8") as f:
            f.write(f"{inp_clean}\n{ans_clean}\n")

    def write_newLocalMem(self, inp: str, ans: str) -> None:
        inp_clean, ans_clean = " ".join(inp.split()), " ".join(ans.split())
        self.CONTEXT.append(self.s + inp_clean)
        self.CONTEXT.append(self.t + ans_clean)

        if len(self.CONTEXT) >= self.max_mem_context_towrite:
            seed_text = self.CONTEXT[0].replace(self.s, "").replace(self.t, "")
            filename = sanitize_filename(" ".join(self.nlp.remove_punctuation(seed_text).split()[:10]))

            # Duyệt theo từng cặp (user, bot) hoàn chỉnh để không bao giờ vượt giới hạn chỉ số.
            for idx in range(0, len(self.CONTEXT) - 1, 2):
                self.w(self.CONTEXT[idx], self.CONTEXT[idx + 1], filename)

            keep = min(len(self.CONTEXT), max(2, self.max_mem_context_towrite // 2))
            self.CONTEXT = self.CONTEXT[-keep:]

        self.backup_contxt_writer()
