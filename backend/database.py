"""
Database Abstraction Layer for AI Agent Chat (MCP 2026-02)

Supports SQLite (default) and PostgreSQL.
Stores conversation metadata, session roots, prompt roots, and message history.
Canonical log files remain on disk for cryptographic verification.

Setup:
- SQLite: No extra setup needed (default, stored at backend/agent_chat.db).
- PostgreSQL: Set DATABASE_URL in .env, e.g.:
      DATABASE_URL=postgresql://user:pass@localhost:5432/agent_db
      pip install psycopg2-binary
"""

import os
import sqlite3
from typing import Optional

# Try to import PostgreSQL driver
try:
    import psycopg2
    import psycopg2.extras
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False

import structlog

logger = structlog.get_logger(__name__)


class DatabaseBackend:
    """Abstract base for database operations."""

    def initialize(self):
        raise NotImplementedError

    def save_conversation(self, data: dict):
        raise NotImplementedError

    def save_message(self, conversation_id: str, role: str, content: str, timestamp: str, prompt_index: int = 0):
        raise NotImplementedError

    def save_prompt_root(self, conversation_id: str, prompt_data: dict):
        raise NotImplementedError

    def get_conversation(self, conversation_id: str) -> Optional[dict]:
        raise NotImplementedError

    def list_conversations(self) -> list[dict]:
        raise NotImplementedError

    def save_integrity(self, conversation_id: str, integrity_data: dict):
        raise NotImplementedError

    def get_messages(self, conversation_id: str) -> list[dict]:
        raise NotImplementedError

    def delete_conversation(self, conversation_id: str) -> bool:
        raise NotImplementedError

    def close(self):
        raise NotImplementedError


class SQLiteBackend(DatabaseBackend):
    """SQLite database backend (default, zero extra dependencies)."""

    def __init__(self, db_path: str = "backend/agent_chat.db"):
        self.db_path = db_path
        self.conn = None

    def initialize(self):
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                session_id TEXT,
                created_at TEXT,
                finalized_at TEXT,
                is_finalized INTEGER DEFAULT 0,
                conversation_root TEXT,
                canonical_log_hash TEXT,
                workflow_dir TEXT,
                message_count INTEGER DEFAULT 0,
                prompt_count INTEGER DEFAULT 0
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT,
                role TEXT,
                content TEXT,
                timestamp TEXT,
                prompt_index INTEGER DEFAULT 0,
                FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS prompt_roots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT,
                prompt_index INTEGER,
                prompt_session_id TEXT,
                prompt_root TEXT,
                event_accumulator_root TEXT,
                event_count INTEGER DEFAULT 0,
                timestamp TEXT,
                FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
            )
        """)
        self.conn.commit()
        logger.info("sqlite_initialized", db_path=self.db_path)

    def save_conversation(self, data: dict):
        self.conn.execute("""
            INSERT OR REPLACE INTO conversations 
            (conversation_id, session_id, created_at, finalized_at, is_finalized,
             conversation_root, canonical_log_hash, workflow_dir, message_count, prompt_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("conversation_id"),
            data.get("session_id"),
            data.get("created_at"),
            data.get("finalized_at"),
            1 if data.get("is_finalized") else 0,
            data.get("conversation_root"),
            data.get("canonical_log_hash"),
            data.get("workflow_dir"),
            data.get("message_count", 0),
            data.get("prompt_count", 0),
        ))
        self.conn.commit()

    def save_message(self, conversation_id: str, role: str, content: str, timestamp: str, prompt_index: int = 0):
        self.conn.execute("""
            INSERT INTO messages (conversation_id, role, content, timestamp, prompt_index)
            VALUES (?, ?, ?, ?, ?)
        """, (conversation_id, role, content, timestamp, prompt_index))
        self.conn.commit()

    def save_prompt_root(self, conversation_id: str, prompt_data: dict):
        self.conn.execute("""
            INSERT INTO prompt_roots 
            (conversation_id, prompt_index, prompt_session_id, prompt_root, 
             event_accumulator_root, event_count, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            conversation_id,
            prompt_data.get("prompt_index", 0),
            prompt_data.get("prompt_session_id", ""),
            prompt_data.get("prompt_root", ""),
            prompt_data.get("event_accumulator_root", ""),
            prompt_data.get("event_count", 0),
            prompt_data.get("timestamp", ""),
        ))
        self.conn.commit()

    def get_conversation(self, conversation_id: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM conversations WHERE conversation_id = ?", (conversation_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_conversations(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM conversations ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]

    def save_integrity(self, conversation_id: str, integrity_data: dict):
        self.conn.execute("""
            UPDATE conversations 
            SET conversation_root = ?, canonical_log_hash = ?, workflow_dir = ?,
                finalized_at = ?, is_finalized = 1, 
                message_count = ?, prompt_count = ?
            WHERE conversation_id = ?
        """, (
            integrity_data.get("conversation_root"),
            integrity_data.get("canonical_log_hash"),
            integrity_data.get("workflow_dir"),
            integrity_data.get("finalized_at"),
            integrity_data.get("message_count", 0),
            integrity_data.get("prompt_count", 0),
            conversation_id,
        ))
        self.conn.commit()

    def get_messages(self, conversation_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT role, content, timestamp, prompt_index FROM messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation and all related records (messages, prompt_roots)."""
        try:
            self.conn.execute("DELETE FROM prompt_roots WHERE conversation_id = ?", (conversation_id,))
            self.conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            self.conn.execute("DELETE FROM conversations WHERE conversation_id = ?", (conversation_id,))
            self.conn.commit()
            logger.info("sqlite_conversation_deleted", conversation_id=conversation_id)
            return True
        except Exception as e:
            logger.error("sqlite_delete_failed", conversation_id=conversation_id, error=str(e))
            return False

    def close(self):
        if self.conn:
            self.conn.close()
            logger.info("sqlite_closed")


class PostgreSQLBackend(DatabaseBackend):
    """PostgreSQL database backend (requires psycopg2 and a running PostgreSQL server)."""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self.conn = None

    def initialize(self):
        if not HAS_POSTGRES:
            raise ImportError(
                "psycopg2 is required for PostgreSQL. Install with: pip install psycopg2-binary"
            )
        self.conn = psycopg2.connect(self.database_url)
        with self.conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    conversation_id TEXT PRIMARY KEY,
                    session_id TEXT,
                    created_at TEXT,
                    finalized_at TEXT,
                    is_finalized BOOLEAN DEFAULT FALSE,
                    conversation_root TEXT,
                    canonical_log_hash TEXT,
                    workflow_dir TEXT,
                    message_count INTEGER DEFAULT 0,
                    prompt_count INTEGER DEFAULT 0
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id SERIAL PRIMARY KEY,
                    conversation_id TEXT REFERENCES conversations(conversation_id),
                    role TEXT,
                    content TEXT,
                    timestamp TEXT,
                    prompt_index INTEGER DEFAULT 0
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS prompt_roots (
                    id SERIAL PRIMARY KEY,
                    conversation_id TEXT REFERENCES conversations(conversation_id),
                    prompt_index INTEGER,
                    prompt_session_id TEXT,
                    prompt_root TEXT,
                    event_accumulator_root TEXT,
                    event_count INTEGER DEFAULT 0,
                    timestamp TEXT
                )
            """)
        self.conn.commit()
        logger.info("postgresql_initialized", url=self.database_url.split("@")[-1] if "@" in self.database_url else "***")

    def save_conversation(self, data: dict):
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO conversations 
                (conversation_id, session_id, created_at, finalized_at, is_finalized,
                 conversation_root, canonical_log_hash, workflow_dir, message_count, prompt_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (conversation_id) DO UPDATE SET
                    session_id = EXCLUDED.session_id,
                    finalized_at = EXCLUDED.finalized_at,
                    is_finalized = EXCLUDED.is_finalized,
                    conversation_root = EXCLUDED.conversation_root,
                    canonical_log_hash = EXCLUDED.canonical_log_hash,
                    workflow_dir = EXCLUDED.workflow_dir,
                    message_count = EXCLUDED.message_count,
                    prompt_count = EXCLUDED.prompt_count
            """, (
                data.get("conversation_id"),
                data.get("session_id"),
                data.get("created_at"),
                data.get("finalized_at"),
                data.get("is_finalized", False),
                data.get("conversation_root"),
                data.get("canonical_log_hash"),
                data.get("workflow_dir"),
                data.get("message_count", 0),
                data.get("prompt_count", 0),
            ))
        self.conn.commit()

    def save_message(self, conversation_id: str, role: str, content: str, timestamp: str, prompt_index: int = 0):
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO messages (conversation_id, role, content, timestamp, prompt_index)
                VALUES (%s, %s, %s, %s, %s)
            """, (conversation_id, role, content, timestamp, prompt_index))
        self.conn.commit()

    def save_prompt_root(self, conversation_id: str, prompt_data: dict):
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO prompt_roots 
                (conversation_id, prompt_index, prompt_session_id, prompt_root,
                 event_accumulator_root, event_count, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                conversation_id,
                prompt_data.get("prompt_index", 0),
                prompt_data.get("prompt_session_id", ""),
                prompt_data.get("prompt_root", ""),
                prompt_data.get("event_accumulator_root", ""),
                prompt_data.get("event_count", 0),
                prompt_data.get("timestamp", ""),
            ))
        self.conn.commit()

    def get_conversation(self, conversation_id: str) -> Optional[dict]:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM conversations WHERE conversation_id = %s", (conversation_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def list_conversations(self) -> list[dict]:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM conversations ORDER BY created_at DESC")
            return [dict(row) for row in cur.fetchall()]

    def save_integrity(self, conversation_id: str, integrity_data: dict):
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE conversations 
                SET conversation_root = %s, canonical_log_hash = %s, workflow_dir = %s,
                    finalized_at = %s, is_finalized = TRUE,
                    message_count = %s, prompt_count = %s
                WHERE conversation_id = %s
            """, (
                integrity_data.get("conversation_root"),
                integrity_data.get("canonical_log_hash"),
                integrity_data.get("workflow_dir"),
                integrity_data.get("finalized_at"),
                integrity_data.get("message_count", 0),
                integrity_data.get("prompt_count", 0),
                conversation_id,
            ))
        self.conn.commit()

    def get_messages(self, conversation_id: str) -> list[dict]:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT role, content, timestamp, prompt_index FROM messages WHERE conversation_id = %s ORDER BY id",
                (conversation_id,)
            )
            return [dict(row) for row in cur.fetchall()]

    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation and all related records (messages, prompt_roots)."""
        try:
            with self.conn.cursor() as cur:
                cur.execute("DELETE FROM prompt_roots WHERE conversation_id = %s", (conversation_id,))
                cur.execute("DELETE FROM messages WHERE conversation_id = %s", (conversation_id,))
                cur.execute("DELETE FROM conversations WHERE conversation_id = %s", (conversation_id,))
            self.conn.commit()
            logger.info("postgres_conversation_deleted", conversation_id=conversation_id)
            return True
        except Exception as e:
            logger.error("postgres_delete_failed", conversation_id=conversation_id, error=str(e))
            return False

    def close(self):
        if self.conn:
            self.conn.close()
            logger.info("postgresql_closed")


def create_database() -> DatabaseBackend:
    """
    Factory function to create the appropriate database backend.
    Uses DATABASE_URL env var for PostgreSQL, otherwise defaults to SQLite.
    """
    database_url = os.getenv("DATABASE_URL")

    if database_url and database_url.startswith("postgresql"):
        safe_url = database_url.split("@")[-1] if "@" in database_url else database_url
        print(f"[DB] Using PostgreSQL: {safe_url}")
        db = PostgreSQLBackend(database_url)
    else:
        db_path = os.getenv("SQLITE_PATH", "backend/agent_chat.db")
        print(f"[DB] Using SQLite: {db_path}")
        db = SQLiteBackend(db_path)

    db.initialize()
    return db
