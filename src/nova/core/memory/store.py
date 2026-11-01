"""SQLite-backed conversation and local vector memory storage.

Vectors are generated locally with deterministic feature hashing. This keeps
memory retrieval private, dependency-light, and usable without a GPU or a
separate embedding service. It is a lightweight semantic approximation; a
dedicated local embedding model can replace the encoder in a future milestone.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

_VECTOR_SIZE = 256
_WORDS = re.compile(r"[a-z0-9][a-z0-9_'-]{1,}", re.IGNORECASE)
_STOPWORDS = {
    "about", "after", "again", "also", "and", "are", "because", "been",
    "being", "but", "can", "could", "did", "does", "for", "from", "had",
    "has", "have", "how", "into", "its", "just", "like", "more", "most",
    "not", "our", "out", "please", "should", "some", "than", "that", "the",
    "their", "them", "then", "there", "these", "they", "this", "those",
    "through", "too", "was", "were", "what", "when", "where", "which",
    "who", "will", "with", "would", "you", "your",
}
_NEVER_STORE = re.compile(
    r"\b(password|passcode|secret key|api key|access token|credit card|"
    r"bank account|social security|social insurance|sin number|"
    r"driver'?s license|passport number)\b",
    re.IGNORECASE,
)
_REQUIRES_APPROVAL = re.compile(
    r"\b(medical diagnosis|home address|street address|phone number|"
    r"medical condition|health condition)\b",
    re.IGNORECASE,
)
_EXPLICIT = re.compile(r"\bremember(?: that)?\s+(.+)", re.IGNORECASE)
_AUTO_PATTERNS = [
    re.compile(r"\b(?:i prefer|i like|i love|i dislike|i hate|i'm interested in|i am interested in)\s+(.+)", re.IGNORECASE),
    re.compile(r"\b(?:i study|i'm studying|i am studying|i work on|i'm building|i am building|my project is)\s+(.+)", re.IGNORECASE),
]
_IMPORTANT = re.compile(r"\b(my goal is|my long[- ]term goal is|my plan is|i always|i never)\b", re.IGNORECASE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _vector(text: str) -> list[float]:
    """Create a normalized 256-dimensional local feature-hash vector."""
    words = [w.lower() for w in _WORDS.findall(text) if w.lower() not in _STOPWORDS]
    features = words + [f"{a}_{b}" for a, b in zip(words, words[1:])]
    values = [0.0] * _VECTOR_SIZE
    for feature in features:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        number = int.from_bytes(digest, "little")
        index = number % _VECTOR_SIZE
        sign = 1.0 if (number >> 8) & 1 else -1.0
        values[index] += sign
    norm = math.sqrt(sum(value * value for value in values))
    if norm:
        values = [value / norm for value in values]
    return values


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


class MemoryStore:
    """Small SQLite repository; each operation owns its connection."""

    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_messages_conversation
                    ON messages(conversation_id, created_at);
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    category TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('approved', 'pending')),
                    source TEXT NOT NULL,
                    vector TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_accessed_at TEXT,
                    access_count INTEGER NOT NULL DEFAULT 0,
                    pinned INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_memories_status
                    ON memories(status, updated_at);
                """
            )
            # Additive migrations preserve existing local memory databases.
            conversation_columns = {row["name"] for row in db.execute("PRAGMA table_info(conversations)")}
            if "pinned" not in conversation_columns:
                db.execute("ALTER TABLE conversations ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0")
            columns = {row["name"] for row in db.execute("PRAGMA table_info(memories)")}
            if "last_accessed_at" not in columns:
                db.execute("ALTER TABLE memories ADD COLUMN last_accessed_at TEXT")
            if "access_count" not in columns:
                db.execute("ALTER TABLE memories ADD COLUMN access_count INTEGER NOT NULL DEFAULT 0")
            if "pinned" not in columns:
                db.execute("ALTER TABLE memories ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0")

    def record_turn(self, conversation_id: str, user_text: str, assistant_text: str) -> None:
        now = _now()
        with self._connect() as db:
            row = db.execute("SELECT id FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
            if row is None:
                db.execute(
                    "INSERT INTO conversations(id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (conversation_id, user_text.strip().replace("\n", " ")[:72] or "New conversation", now, now),
                )
            else:
                db.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id))
            db.executemany(
                "INSERT INTO messages(id, conversation_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
                [
                    (str(uuid4()), conversation_id, "user", user_text, now),
                    (str(uuid4()), conversation_id, "assistant", assistant_text, now),
                ],
            )

    def retrieve(self, query: str, limit: int = 4) -> list[dict[str, Any]]:
        """Retrieve approved memories using local semantic and lexical ranking."""
        if not query.strip() or limit < 1:
            return []
        query_vector = _vector(query)
        query_terms = set(w.lower() for w in _WORDS.findall(query) if w.lower() not in _STOPWORDS)
        with self._connect() as db:
            rows = db.execute(
                "SELECT id, content, category, vector, pinned FROM memories WHERE status = 'approved'"
            ).fetchall()
        ranked = []
        for row in rows:
            try:
                candidate = json.loads(row["vector"])
            except (TypeError, json.JSONDecodeError):
                continue
            semantic = _cosine(query_vector, candidate)
            terms = set(w.lower() for w in _WORDS.findall(row["content"]) if w.lower() not in _STOPWORDS)
            lexical = len(query_terms & terms) / max(1, len(query_terms))
            score = semantic * 0.8 + lexical * 0.2
            if score > 0.08:
                ranked.append({"id": row["id"], "content": row["content"], "category": row["category"],
                               "score": round(score, 4), "pinned": bool(row["pinned"])})
        results = sorted(ranked, key=lambda item: (item["pinned"], item["score"]), reverse=True)[:limit]
        if results:
            now = _now()
            with self._connect() as db:
                db.executemany(
                    "UPDATE memories SET access_count = access_count + 1, last_accessed_at = ? WHERE id = ?",
                    [(now, item["id"]) for item in results],
                )
        return results

    def capture_from_text(self, text: str) -> dict[str, Any] | None:
        """Capture safe facts; queue high-impact facts for explicit approval."""
        if _NEVER_STORE.search(text):
            return None

        requires_approval = bool(_REQUIRES_APPROVAL.search(text))
        explicit = _EXPLICIT.search(text)
        if explicit:
            content = explicit.group(1).strip().rstrip(".!?")
            status, source, category = "approved", "explicit", "user-provided"
        else:
            match = next((pattern.search(text) for pattern in _AUTO_PATTERNS if pattern.search(text)), None)
            if not match:
                important = _IMPORTANT.search(text)
                if important:
                    content = text.strip()
                    status, source, category = "pending", "automatic-review", "important"
                elif requires_approval:
                    content = text.strip()
                    status, source, category = "pending", "sensitive-review", "sensitive"
                else:
                    return None
            else:
                content = text.strip()
                status, source = "approved", "automatic"
                category = "preference" if match.re is _AUTO_PATTERNS[0] else "project-or-interest"

        if requires_approval:
            status, source, category = "pending", "sensitive-review", "sensitive"
        content = content[:1000]
        if len(content) < 8:
            return None
        now = _now()
        vector = json.dumps(_vector(content), separators=(",", ":"))
        with self._connect() as db:
            existing = db.execute(
                "SELECT id, status FROM memories WHERE lower(trim(content)) = lower(trim(?))", (content,)
            ).fetchone()
            if existing:
                db.execute("UPDATE memories SET updated_at = ? WHERE id = ?", (now, existing["id"]))
                return {"id": existing["id"], "status": existing["status"], "content": content, "duplicate": True}
            for candidate in db.execute(
                "SELECT id, status, vector FROM memories WHERE status = ? AND category = ?",
                (status, category),
            ).fetchall():
                try:
                    similarity = _cosine(_vector(content), json.loads(candidate["vector"]))
                except (TypeError, json.JSONDecodeError):
                    continue
                if similarity >= 0.96:
                    db.execute("UPDATE memories SET updated_at = ? WHERE id = ?", (now, candidate["id"]))
                    return {"id": candidate["id"], "status": candidate["status"], "content": content, "duplicate": True}
            memory_id = str(uuid4())
            db.execute(
                """INSERT INTO memories(id, content, category, status, source, vector, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (memory_id, content, category, status, source, vector, now, now),
            )
        return {"id": memory_id, "content": content, "status": status, "category": category}

    def list_memories(self, status: str | None = None, category: str | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[str] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if category:
            clauses.append("category = ?")
            params.append(category)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as db:
            rows = db.execute(
                "SELECT id, content, category, status, source, created_at, updated_at, "
                "last_accessed_at, access_count, pinned FROM memories" + where +
                " ORDER BY pinned DESC, updated_at DESC", params,
            ).fetchall()
        return [dict(row) for row in rows]

    def memory_stats(self) -> dict[str, Any]:
        with self._connect() as db:
            totals = db.execute("SELECT status, COUNT(*) AS count FROM memories GROUP BY status").fetchall()
            categories = db.execute("SELECT category, COUNT(*) AS count FROM memories GROUP BY category ORDER BY count DESC").fetchall()
            row = db.execute("SELECT COUNT(*) AS total, SUM(pinned) AS pinned, SUM(access_count) AS retrievals FROM memories").fetchone()
        return {
            "total": row["total"] or 0, "pinned": row["pinned"] or 0,
            "retrievals": row["retrievals"] or 0,
            "by_status": {item["status"]: item["count"] for item in totals},
            "by_category": {item["category"]: item["count"] for item in categories},
        }

    def pin_memory(self, memory_id: str, pinned: bool = True) -> bool:
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE memories SET pinned = ?, updated_at = ? WHERE id = ?",
                (1 if pinned else 0, _now(), memory_id),
            )
            return cursor.rowcount > 0

    def approve_memory(self, memory_id: str) -> bool:
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE memories SET status = 'approved', updated_at = ? WHERE id = ?",
                (_now(), memory_id),
            )
            return cursor.rowcount > 0

    def update_memory(self, memory_id: str, content: str) -> bool:
        """Edit a memory and re-apply the storage and approval safety policy."""
        normalized = content.strip()[:1000]
        if _NEVER_STORE.search(normalized):
            raise ValueError("NOVA will not store passwords, credentials, financial secrets, or government identifiers.")
        if len(normalized) < 8:
            raise ValueError("Memory content must contain at least 8 non-whitespace characters.")

        now = _now()
        vector = json.dumps(_vector(normalized), separators=(",", ":"))
        with self._connect() as db:
            if _REQUIRES_APPROVAL.search(normalized):
                cursor = db.execute(
                    """UPDATE memories
                       SET content = ?, category = 'sensitive', status = 'pending',
                           source = 'sensitive-review', vector = ?, updated_at = ?
                       WHERE id = ?""",
                    (normalized, vector, now, memory_id),
                )
            else:
                cursor = db.execute(
                    "UPDATE memories SET content = ?, vector = ?, updated_at = ? WHERE id = ?",
                    (normalized, vector, now, memory_id),
                )
            return cursor.rowcount > 0

    def delete_memory(self, memory_id: str) -> bool:
        with self._connect() as db:
            cursor = db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            return cursor.rowcount > 0

    def list_conversations(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id, title, created_at, updated_at, pinned FROM conversations "
                "ORDER BY pinned DESC, updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def search_conversations(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        """Search conversation titles and message text, returning newest matches."""
        term = query.strip()
        if not term:
            return self.list_conversations(limit)
        pattern = f"%{term}%"
        with self._connect() as db:
            rows = db.execute(
                """SELECT DISTINCT c.id, c.title, c.created_at, c.updated_at, c.pinned
                   FROM conversations c
                   LEFT JOIN messages m ON m.conversation_id = c.id
                   WHERE c.title LIKE ? ESCAPE '\\' OR m.content LIKE ? ESCAPE '\\'
                   ORDER BY c.pinned DESC, c.updated_at DESC LIMIT ?""",
                (pattern, pattern, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def rename_conversation(self, conversation_id: str, title: str) -> bool:
        normalized = " ".join(title.split())[:100]
        if len(normalized) < 1:
            raise ValueError("Conversation title cannot be empty.")
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (normalized, _now(), conversation_id),
            )
            return cursor.rowcount > 0

    def pin_conversation(self, conversation_id: str, pinned: bool = True) -> bool:
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE conversations SET pinned = ? WHERE id = ?",
                (1 if pinned else 0, conversation_id),
            )
            return cursor.rowcount > 0

    def get_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY rowid",
                (conversation_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_conversation(self, conversation_id: str) -> bool:
        with self._connect() as db:
            cursor = db.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
            return cursor.rowcount > 0
