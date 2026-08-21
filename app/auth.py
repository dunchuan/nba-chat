"""SQLite-backed users and server-side login sessions."""

import hashlib
import hmac
import os
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("SQLITE_PATH", str(BASE_DIR / "data" / "nba_chat.sqlite3")))
DEMO_ACCOUNTS = (
    ("nbachat", "nbachat"),
    ("tester_hlx", "tester_hlx"),
    ("tester_wk", "tester_wk"),
    ("tester_lyk", "tester_lyk"),
)
LEGACY_ACCOUNT_NAMES = {
    "demo1": "tester_hlx",
    "demo2": "tester_wk",
    "demo3": "tester_lyk",
}
_init_lock = threading.Lock()
_initialized_path: Path | None = None


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_auth_db() -> None:
    global _initialized_path
    current_path = DB_PATH.resolve()
    if _initialized_path == current_path:
        return

    with _init_lock:
        if _initialized_path == current_path:
            return
        with _connection() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    expires_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
                CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    thread_id TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_conversations_user_updated
                    ON conversations(user_id, updated_at DESC);
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_messages_conversation_id
                    ON messages(conversation_id, id ASC);
                """
            )
            # Migrate the previous demo names once, preserving their user IDs.
            for old_name, new_name in LEGACY_ACCOUNT_NAMES.items():
                old_row = db.execute("SELECT id FROM users WHERE username = ?", (old_name,)).fetchone()
                new_row = db.execute("SELECT id FROM users WHERE username = ?", (new_name,)).fetchone()
                if old_row and not new_row:
                    db.execute(
                        "UPDATE users SET username = ?, password_hash = ? WHERE username = ?",
                        (new_name, _hash_password(new_name), old_name),
                    )
            for username, password in DEMO_ACCOUNTS:
                exists = db.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
                if not exists:
                    db.execute(
                        "INSERT INTO users(username, password_hash, created_at) VALUES (?, ?, ?)",
                        (username, _hash_password(password), int(time.time())),
                    )
        _initialized_path = current_path


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240_000)
    return f"pbkdf2_sha256$240000${salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, rounds, salt_hex, digest_hex = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def normalize_username(username: str) -> str:
    return username.strip().lower()


def create_user(username: str, password: str) -> int:
    init_auth_db()
    username = normalize_username(username)
    with _connection() as db:
        cursor = db.execute(
            "INSERT INTO users(username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, _hash_password(password), int(time.time())),
        )
        return int(cursor.lastrowid)


def authenticate(username: str, password: str) -> int | None:
    init_auth_db()
    username = normalize_username(username)
    with _connection() as db:
        row = db.execute("SELECT id, password_hash FROM users WHERE username = ?", (username,)).fetchone()
    if row and _verify_password(password, row["password_hash"]):
        return int(row["id"])
    return None


def create_session(user_id: int, ttl_seconds: int = 7 * 24 * 3600) -> str:
    init_auth_db()
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    with _connection() as db:
        db.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
        db.execute("INSERT INTO sessions(token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)", (token, user_id, now + ttl_seconds, now))
    return token


def username_for_user_id(user_id: int) -> str | None:
    init_auth_db()
    with _connection() as db:
        row = db.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
    return str(row["username"]) if row else None


def user_from_session(token: str | None) -> dict[str, object] | None:
    if not token:
        return None
    init_auth_db()
    with _connection() as db:
        row = db.execute(
            "SELECT users.id, users.username FROM sessions JOIN users ON users.id = sessions.user_id WHERE sessions.token = ? AND sessions.expires_at > ?",
            (token, int(time.time())),
        ).fetchone()
    return dict(row) if row else None


def delete_session(token: str | None) -> None:
    if token:
        init_auth_db()
        with _connection() as db:
            db.execute("DELETE FROM sessions WHERE token = ?", (token,))


def _conversation_title(message: str) -> str:
    """Create a compact default title from the first user message."""
    title = " ".join(message.split())
    return (title[:80] or "新对话")


def ensure_conversation(user_id: int, thread_id: str, first_message: str) -> dict[str, object]:
    """Create a user-owned conversation once, or return its existing record."""
    init_auth_db()
    now = int(time.time())
    with _connection() as db:
        row = db.execute(
            "SELECT id, user_id, thread_id, title, created_at, updated_at FROM conversations WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
        if row:
            if int(row["user_id"]) != user_id:
                raise PermissionError("conversation does not belong to the current user")
            return dict(row)
        cursor = db.execute(
            "INSERT INTO conversations(user_id, thread_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, thread_id, _conversation_title(first_message), now, now),
        )
        return {
            "id": int(cursor.lastrowid), "user_id": user_id, "thread_id": thread_id,
            "title": _conversation_title(first_message), "created_at": now, "updated_at": now,
        }


def append_message(user_id: int, thread_id: str, role: str, content: str) -> None:
    """Append a visible chat message and update the owning conversation timestamp."""
    if role not in {"user", "assistant"}:
        raise ValueError("unsupported message role")
    conversation = ensure_conversation(user_id, thread_id, content)
    now = int(time.time())
    with _connection() as db:
        db.execute(
            "INSERT INTO messages(conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (conversation["id"], role, content, now),
        )
        db.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation["id"]))


def list_conversations(user_id: int) -> list[dict[str, object]]:
    init_auth_db()
    with _connection() as db:
        rows = db.execute(
            "SELECT thread_id, title, created_at, updated_at FROM conversations WHERE user_id = ? ORDER BY updated_at DESC, id DESC",
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_conversation_messages(user_id: int, thread_id: str) -> list[dict[str, object]]:
    init_auth_db()
    with _connection() as db:
        conversation = db.execute(
            "SELECT id FROM conversations WHERE user_id = ? AND thread_id = ?", (user_id, thread_id)
        ).fetchone()
        if not conversation:
            raise LookupError("conversation not found")
        rows = db.execute(
            "SELECT role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY id ASC",
            (conversation["id"],),
        ).fetchall()
    return [dict(row) for row in rows]


def rename_conversation(user_id: int, thread_id: str, title: str) -> None:
    init_auth_db()
    cleaned = " ".join(title.split())[:120]
    if not cleaned:
        raise ValueError("conversation title cannot be empty")
    with _connection() as db:
        cursor = db.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE user_id = ? AND thread_id = ?",
            (cleaned, int(time.time()), user_id, thread_id),
        )
        if cursor.rowcount == 0:
            raise LookupError("conversation not found")


def delete_conversation(user_id: int, thread_id: str) -> bool:
    init_auth_db()
    with _connection() as db:
        cursor = db.execute(
            "DELETE FROM conversations WHERE user_id = ? AND thread_id = ?", (user_id, thread_id)
        )
    return cursor.rowcount > 0


def delete_all_conversations(user_id: int) -> int:
    init_auth_db()
    with _connection() as db:
        cursor = db.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
    return cursor.rowcount
