"""
认证数据库操作 — 用户/会话 CRUD（SQLite）
借鉴 demo2 repository.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "app.db"


def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_auth_db():
    conn = get_conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS user_sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON user_sessions(user_id);
        """)
        conn.commit()
    finally:
        conn.close()


# ── User CRUD ────────────────────────────────────────────

def create_user(user_id, email, display_name, password_hash, created_at):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO users (user_id, email, display_name, password_hash, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (user_id, email, display_name, password_hash, created_at, created_at),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise ValueError("该邮箱已注册")
    finally:
        conn.close()


def get_user_by_email(email):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_id(user_id):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def count_users():
    conn = get_conn()
    try:
        row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
        return row["n"] if row else 0
    finally:
        conn.close()


# ── Session CRUD ─────────────────────────────────────────

def create_session(session_id, user_id, token_hash, created_at, expires_at):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO user_sessions (session_id, user_id, token_hash, created_at, expires_at) VALUES (?,?,?,?,?)",
            (session_id, user_id, token_hash, created_at, expires_at),
        )
        conn.commit()
    finally:
        conn.close()


def get_active_session(token_hash, now_str):
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT s.*, u.email, u.display_name, u.created_at as user_created_at
               FROM user_sessions s JOIN users u ON u.user_id = s.user_id
               WHERE s.token_hash = ? AND s.revoked_at IS NULL AND s.expires_at > ?""",
            (token_hash, now_str),
        ).fetchone()
        if not row:
            return None
        r = dict(row)
        return {
            "session_id": r["session_id"],
            "user_id": r["user_id"],
            "user": {
                "user_id": r["user_id"],
                "email": r["email"],
                "display_name": r["display_name"],
                "created_at": r["user_created_at"],
            },
        }
    finally:
        conn.close()


def revoke_session(token_hash, now_str):
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE user_sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
            (now_str, token_hash),
        )
        conn.commit()
    finally:
        conn.close()
