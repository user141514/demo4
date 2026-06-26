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
                role TEXT NOT NULL DEFAULT 'student',
                company_name TEXT NOT NULL DEFAULT '',
                job_title TEXT NOT NULL DEFAULT '',
                recovery_question TEXT,
                recovery_answer_hash TEXT,
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
            CREATE TABLE IF NOT EXISTS model_records (
                record_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                dimensions_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON user_sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_model_records_user_id ON model_records(user_id);
            CREATE INDEX IF NOT EXISTS idx_model_records_created_at ON model_records(created_at);
        """)
        _ensure_users_columns(conn)
        conn.commit()
    finally:
        conn.close()


def _ensure_users_columns(conn):
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    migrations = {
        "role": "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'student'",
        "company_name": "ALTER TABLE users ADD COLUMN company_name TEXT NOT NULL DEFAULT ''",
        "job_title": "ALTER TABLE users ADD COLUMN job_title TEXT NOT NULL DEFAULT ''",
        "recovery_question": "ALTER TABLE users ADD COLUMN recovery_question TEXT",
        "recovery_answer_hash": "ALTER TABLE users ADD COLUMN recovery_answer_hash TEXT",
    }
    for column, sql in migrations.items():
        if column not in existing:
            conn.execute(sql)


# ── User CRUD ────────────────────────────────────────────

def create_user(
    user_id,
    email,
    display_name,
    password_hash,
    created_at,
    role="student",
    company_name="",
    job_title="",
    recovery_question=None,
    recovery_answer_hash=None,
):
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO users (
                user_id, email, display_name, password_hash, role, company_name,
                job_title, recovery_question, recovery_answer_hash, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                user_id,
                email,
                display_name,
                password_hash,
                role,
                company_name or "",
                job_title or "",
                recovery_question,
                recovery_answer_hash,
                created_at,
                created_at,
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise ValueError("该邮箱已注册")
    finally:
        conn.close()


def get_user_by_email(email, role=None):
    conn = get_conn()
    try:
        if role is None:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        else:
            row = conn.execute("SELECT * FROM users WHERE email = ? AND role = ?", (email, role)).fetchone()
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


def update_user_password(user_id, password_hash, updated_at):
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE user_id = ?",
            (password_hash, updated_at, user_id),
        )
        conn.commit()
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
            """SELECT s.*, u.email, u.display_name, u.role, u.company_name, u.job_title, u.created_at as user_created_at
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
                "role": r["role"],
                "company_name": r["company_name"],
                "job_title": r["job_title"],
                "created_at": r["user_created_at"],
            },
        }
    finally:
        conn.close()


# ── Model Record CRUD ────────────────────────────────────────

def create_model_record(record_id, user_id, summary_json, dimensions_json, created_at):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO model_records (record_id, user_id, summary_json, dimensions_json, created_at) VALUES (?,?,?,?,?)",
            (record_id, user_id, summary_json, dimensions_json, created_at),
        )
        conn.commit()
    finally:
        conn.close()


def list_model_records():
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT r.*, u.email, u.display_name, u.company_name, u.job_title
               FROM model_records r
               JOIN users u ON u.user_id = r.user_id
               ORDER BY r.created_at DESC, r.record_id DESC"""
        ).fetchall()
        return [dict(row) for row in rows]
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
