"""Database security and migration regression tests (SQLite backend)."""

import sqlite3

from backend.database import SQLiteBackend


def test_sqlite_parameterized_queries_resist_injection_payload(tmp_path) -> None:
    db_path = tmp_path / "db_injection.sqlite3"
    db = SQLiteBackend(str(db_path))
    db.initialize()

    malicious_id = "conv-1'; DROP TABLE conversations; --"
    db.save_conversation(
        {
            "conversation_id": malicious_id,
            "session_id": "s-1",
            "created_at": "2026-03-24T10:00:00Z",
            "is_finalized": False,
            "message_count": 0,
            "prompt_count": 0,
        }
    )

    # If SQL injection were possible, this query would fail because the table would be dropped.
    row = db.get_conversation(malicious_id)
    assert row is not None
    assert row["conversation_id"] == malicious_id

    # Ensure core table still exists.
    exists = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='conversations'"
    ).fetchone()
    assert exists is not None

    db.close()


def test_sqlite_owner_token_migration_is_idempotent(tmp_path) -> None:
    db_path = tmp_path / "db_migration.sqlite3"
    db = SQLiteBackend(str(db_path))

    # Run initialize twice to simulate repeated startup migrations.
    db.initialize()
    db.initialize()

    cols = db.conn.execute("PRAGMA table_info(conversations)").fetchall()
    col_names = [c[1] for c in cols]  # sqlite pragma tuple index 1 == column name
    assert "owner_token" in col_names

    # Ensure we can still write/read after repeated migration path.
    db.save_conversation(
        {
            "conversation_id": "conv-2",
            "session_id": "s-2",
            "created_at": "2026-03-24T10:05:00Z",
            "owner_token": "token-abc",
            "is_finalized": False,
        }
    )
    row = db.get_conversation("conv-2")
    assert row is not None
    assert row["owner_token"] == "token-abc"

    db.close()


def test_sqlite_rejects_nonexistent_table_drop_via_message_content(tmp_path) -> None:
    db_path = tmp_path / "db_message.sqlite3"
    db = SQLiteBackend(str(db_path))
    db.initialize()

    db.save_conversation(
        {
            "conversation_id": "conv-msg",
            "session_id": "s-msg",
            "created_at": "2026-03-24T10:10:00Z",
            "is_finalized": False,
        }
    )

    payload = "'; DROP TABLE messages; --"
    db.save_message("conv-msg", "user", payload, "2026-03-24T10:11:00Z")

    rows = db.get_messages("conv-msg")
    assert len(rows) == 1
    assert rows[0]["content"] == payload

    exists = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='messages'"
    ).fetchone()
    assert exists is not None

    db.close()
