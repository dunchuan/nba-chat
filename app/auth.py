"""Small SQLite-backed authentication layer for the demo deployment."""

import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from pathlib import Path


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


def _connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_auth_db() -> None:
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
            db.execute(
                "INSERT OR IGNORE INTO users(username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, _hash_password(password), int(time.time())),
            )


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


def create_user(username: str, password: str) -> int:
    init_auth_db()
    with _connection() as db:
        cursor = db.execute(
            "INSERT INTO users(username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, _hash_password(password), int(time.time())),
        )
        return int(cursor.lastrowid)


def authenticate(username: str, password: str) -> int | None:
    init_auth_db()
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
