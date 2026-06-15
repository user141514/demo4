"""
认证服务 — 注册/登录/登出
借鉴 demo2 services/auth_service.py
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from backend.auth_db import (
    count_users,
    create_session,
    create_user,
    get_user_by_email,
)


class AuthError(Exception):
    def __init__(self, code, message, status_code=400):
        self.code = code
        self.message = message
        self.status_code = status_code


SESSION_DAYS = 7


def register_user(email, display_name, password):
    email = (email or "").strip().lower()
    display_name = (display_name or "").strip()
    password = password or ""

    if "@" not in email or "." not in email.split("@")[-1]:
        raise AuthError("invalid_email", "请输入有效邮箱", 400)
    if len(display_name) < 2:
        raise AuthError("invalid_name", "姓名至少需要2个字符", 400)
    if len(password) < 6:
        raise AuthError("invalid_password", "密码至少需要6位", 400)
    if get_user_by_email(email):
        raise AuthError("email_exists", "该邮箱已注册", 409)

    now = _utcnow_str()
    user_id = uuid.uuid4().hex
    create_user(user_id, email, display_name, generate_password_hash(password), now)
    token = _create_login_session(user_id)
    return {
        "user_id": user_id,
        "email": email,
        "display_name": display_name,
    }, token


def login_user(email, password):
    email = (email or "").strip().lower()
    password = password or ""
    if not email or not password:
        raise AuthError("invalid_credentials", "邮箱或密码错误", 401)

    user = get_user_by_email(email)
    if not user or not check_password_hash(user["password_hash"], password):
        raise AuthError("invalid_credentials", "邮箱或密码错误", 401)

    token = _create_login_session(user["user_id"])
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "display_name": user["display_name"],
    }, token


def _create_login_session(user_id):
    token = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    expires = now + timedelta(days=SESSION_DAYS)
    create_session(
        uuid.uuid4().hex,
        user_id,
        hash_token(token),
        _fmt(now),
        _fmt(expires),
    )
    return token


def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _utcnow_str():
    return _fmt(datetime.utcnow())


def _fmt(dt):
    return dt.replace(microsecond=0).isoformat() + "Z"
