"""PostgreSQL-backed users, sessions, conversations, and chat messages."""

import hashlib
import hmac
import os
import secrets
import time
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.getenv("DATABASE_URL") or (
    "postgresql://{user}:{password}@{host}:{port}/{database}".format(
        user=os.environ["POSTGRES_USER"], password=os.environ["POSTGRES_PASSWORD"],
        host=os.getenv("POSTGRES_HOST", "nba-chat-db"), port=os.getenv("POSTGRES_PORT", "5432"),
        database=os.environ["POSTGRES_DB"],
    )
)
@contextmanager
def _connection() -> Iterator[psycopg.Connection]:
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
        yield connection


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240_000)
    return f"pbkdf2_sha256$240000${salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, rounds, salt_hex, digest_hex = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256": return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError): return False


def normalize_username(username: str) -> str: return username.strip().lower()


def create_user(username: str, password: str) -> int:
    with _connection() as db:
        row = db.execute("INSERT INTO users(username, password_hash, created_at) VALUES (%s, %s, %s) RETURNING id", (normalize_username(username), _hash_password(password), int(time.time()))).fetchone()
    return int(row["id"])


def authenticate(username: str, password: str) -> int | None:
    with _connection() as db:
        row = db.execute("SELECT id, password_hash FROM users WHERE username = %s", (normalize_username(username),)).fetchone()
    return int(row["id"]) if row and _verify_password(password, row["password_hash"]) else None


def create_session(user_id: int, ttl_seconds: int = 7 * 24 * 3600) -> str:
    token, now = secrets.token_urlsafe(32), int(time.time())
    with _connection() as db:
        db.execute("DELETE FROM sessions WHERE expires_at <= %s", (now,))
        db.execute("INSERT INTO sessions(token, user_id, expires_at, created_at) VALUES (%s, %s, %s, %s)", (token, user_id, now + ttl_seconds, now))
    return token


def username_for_user_id(user_id: int) -> str | None:
    with _connection() as db: row = db.execute("SELECT username FROM users WHERE id = %s", (user_id,)).fetchone()
    return str(row["username"]) if row else None


def user_from_session(token: str | None) -> dict[str, object] | None:
    if not token: return None
    with _connection() as db:
        row = db.execute("SELECT users.id, users.username FROM sessions JOIN users ON users.id = sessions.user_id WHERE sessions.token = %s AND sessions.expires_at > %s", (token, int(time.time()))).fetchone()
    return dict(row) if row else None


def delete_session(token: str | None) -> None:
    if token:
        with _connection() as db: db.execute("DELETE FROM sessions WHERE token = %s", (token,))


def _conversation_title(message: str) -> str: return (" ".join(message.split())[:80] or "新对话")


def ensure_conversation(user_id: int, thread_id: str, first_message: str) -> dict[str, object]:
    now, title = int(time.time()), _conversation_title(first_message)
    with _connection() as db:
        row = db.execute("SELECT id, user_id, thread_id, title, created_at, updated_at FROM conversations WHERE thread_id = %s", (thread_id,)).fetchone()
        if row:
            if int(row["user_id"]) != user_id: raise PermissionError("conversation does not belong to the current user")
            return dict(row)
        row = db.execute("INSERT INTO conversations(user_id, thread_id, title, created_at, updated_at) VALUES (%s, %s, %s, %s, %s) RETURNING id, user_id, thread_id, title, created_at, updated_at", (user_id, thread_id, title, now, now)).fetchone()
    return dict(row)


def append_message(user_id: int, thread_id: str, role: str, content: str) -> None:
    if role not in {"user", "assistant"}: raise ValueError("unsupported message role")
    conversation = ensure_conversation(user_id, thread_id, content); now = int(time.time())
    with _connection() as db:
        db.execute("INSERT INTO messages(conversation_id, role, content, created_at) VALUES (%s, %s, %s, %s)", (conversation["id"], role, content, now))
        db.execute("UPDATE conversations SET updated_at = %s WHERE id = %s", (now, conversation["id"]))


def list_conversations(user_id: int) -> list[dict[str, object]]:
    with _connection() as db: rows = db.execute("SELECT thread_id, title, created_at, updated_at FROM conversations WHERE user_id = %s ORDER BY updated_at DESC, id DESC", (user_id,)).fetchall()
    return [dict(row) for row in rows]


def get_conversation_messages(user_id: int, thread_id: str) -> list[dict[str, object]]:
    with _connection() as db:
        conversation = db.execute("SELECT id FROM conversations WHERE user_id = %s AND thread_id = %s", (user_id, thread_id)).fetchone()
        if not conversation: raise LookupError("conversation not found")
        rows = db.execute("SELECT role, content, created_at FROM messages WHERE conversation_id = %s ORDER BY id ASC", (conversation["id"],)).fetchall()
    return [dict(row) for row in rows]


def rename_conversation(user_id: int, thread_id: str, title: str) -> None:
    cleaned = " ".join(title.split())[:120]
    if not cleaned: raise ValueError("conversation title cannot be empty")
    with _connection() as db:
        result = db.execute("UPDATE conversations SET title = %s, updated_at = %s WHERE user_id = %s AND thread_id = %s", (cleaned, int(time.time()), user_id, thread_id))
        if result.rowcount == 0: raise LookupError("conversation not found")


def delete_conversation(user_id: int, thread_id: str) -> bool:
    with _connection() as db: result = db.execute("DELETE FROM conversations WHERE user_id = %s AND thread_id = %s", (user_id, thread_id))
    return result.rowcount > 0


def delete_all_conversations(user_id: int) -> int:
    with _connection() as db: result = db.execute("DELETE FROM conversations WHERE user_id = %s", (user_id,))
    return result.rowcount
