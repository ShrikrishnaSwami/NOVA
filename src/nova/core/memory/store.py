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
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memories_status
                    ON memories(status, updated_at);
                """
            )

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
        query_vector = _vector(query)
        with self._connect() as db:
            rows = db.execute(
                "SELECT id, content, category, vector FROM memories WHERE status = 'approved'"
            ).fetchall()
        ranked = []
        for row in rows:
            try:
                candidate = json.loads(row["vector"])
            except (TypeError, json.JSONDecodeError):
                continue
            score = _cosine(query_vector, candidate)
            if score > 0.08:
                ranked.append({"id": row["id"], "content": row["content"], "category": row["category"], "score": round(score, 4)})
        return sorted(ranked, key=lambda item: item["score"], reverse=True)[:limit]

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
                "SELECT id, status FROM memories WHERE lower(content) = lower(?)", (content,)
            ).fetchone()
            if existing:
                return {"id": existing["id"], "status": existing["status"], "content": content, "duplicate": True}
            memory_id = str(uuid4())
            db.execute(
                """INSERT INTO memories(id, content, category, status, source, vector, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (memory_id, content, category, status, source, vector, now, now),
            )
        return {"id": memory_id, "content": content, "status": status, "category": category}

    def list_memories(self, status: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as db:
            if status:
                rows = db.execute(
                    "SELECT id, content, category, status, source, created_at, updated_at FROM memories WHERE status = ? ORDER BY updated_at DESC",
                    (status,),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT id, content, category, status, source, created_at, updated_at FROM memories ORDER BY updated_at DESC"
                ).fetchall()
        return [dict(row) for row in rows]

    def approve_memory(self, memory_id: str) -> bool:
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE memories SET status = 'approved', updated_at = ? WHERE id = ?",
                (_now(), memory_id),
            )
            return cursor.rowcount > 0

    def update_memory(self, memory_id: str, content: str) -> bool:
        if _NEVER_STORE.search(content):
            raise ValueError("NOVA will not store passwords, credentials, financial secrets, or government identifiers.")
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE memories SET content = ?, vector = ?, updated_at = ? WHERE id = ?",
                (content[:1000], json.dumps(_vector(content[:1000]), separators=(",", ":")), _now(), memory_id),
            )
            return cursor.rowcount > 0

    def delete_memory(self, memory_id: str) -> bool:
        with self._connect() as db:
            cursor = db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            return cursor.rowcount > 0

    def list_conversations(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

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
