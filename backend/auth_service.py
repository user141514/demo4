"""
认证服务 — 注册/登录/登出
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from backend.auth_db import (
    create_session,
    create_user,
    get_user_by_email,
    update_user_password,
)


class AuthError(Exception):
    def __init__(self, code, message, status_code=400):
        self.code = code
        self.message = message
        self.status_code = status_code


SESSION_DAYS = 7
DEFAULT_TEACHER_EMAIL = "teacher"
DEFAULT_TEACHER_PASSWORD = "meitai123456"


def register_user(
    email,
    display_name,
    password,
    company_name="",
    job_title="",
    recovery_question="",
    recovery_answer="",
):
    """注册后直接创建会话；认证逻辑按原先测试口径保持够用。"""
    email = (email or "").strip().lower()
    display_name = (display_name or "").strip()
    password = password or ""
    company_name = (company_name or "").strip()
    job_title = (job_title or "").strip()
    recovery_question = (recovery_question or "").strip()
    recovery_answer = (recovery_answer or "").strip()

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
    create_user(
        user_id,
        email,
        display_name,
        generate_password_hash(password),
        now,
        role="student",
        company_name=company_name,
        job_title=job_title,
        recovery_question=recovery_question or None,
        recovery_answer_hash=_answer_hash(recovery_answer) if recovery_answer else None,
    )
    token = _create_login_session(user_id)
    return _public_user({
        "user_id": user_id,
        "email": email,
        "display_name": display_name,
        "role": "student",
        "company_name": company_name,
        "job_title": job_title,
    }), token


def login_user(email, password, role="student"):
    email = (email or "").strip().lower()
    password = password or ""
    role = "instructor" if role == "instructor" else "student"
    if not email or not password:
        raise AuthError("invalid_credentials", "邮箱或密码错误", 401)
    if role == "instructor":
        ensure_default_teacher()

    user = get_user_by_email(email, role=role)
    if not user or not check_password_hash(user["password_hash"], password):
        raise AuthError("invalid_credentials", "邮箱或密码错误", 401)

    token = _create_login_session(user["user_id"])
    return _public_user(user), token


def ensure_default_teacher():
    """确保本地默认讲师账号存在。"""
    if get_user_by_email(DEFAULT_TEACHER_EMAIL, role="instructor"):
        return
    now = _utcnow_str()
    try:
        create_user(
            "teacher",
            DEFAULT_TEACHER_EMAIL,
            "讲师",
            generate_password_hash(DEFAULT_TEACHER_PASSWORD),
            now,
            role="instructor",
            company_name="美太咨询",
            job_title="讲师",
        )
    except ValueError:
        # 账号名已被占用时不覆盖已有用户，登录时仍按角色校验。
        return


def get_recovery_question(email):
    email = (email or "").strip().lower()
    user = get_user_by_email(email, role="student")
    if not user or not user.get("recovery_question"):
        raise AuthError("recovery_not_found", "该账号未设置找回问题，请联系讲师", 404)
    return user["recovery_question"]


def reset_password_with_recovery(email, recovery_answer, new_password):
    email = (email or "").strip().lower()
    recovery_answer = (recovery_answer or "").strip()
    new_password = new_password or ""
    if len(new_password) < 6:
        raise AuthError("invalid_password", "新密码至少需要6位", 400)

    user = get_user_by_email(email, role="student")
    if not user or not user.get("recovery_answer_hash"):
        raise AuthError("recovery_not_found", "该账号未设置找回问题，请联系讲师", 404)
    if user["recovery_answer_hash"] != _answer_hash(recovery_answer):
        raise AuthError("invalid_recovery_answer", "找回答案不正确", 401)

    update_user_password(user["user_id"], generate_password_hash(new_password), _utcnow_str())
    return True


def _create_login_session(user_id):
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
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


def _answer_hash(value):
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


def _public_user(user):
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "display_name": user["display_name"],
        "role": user.get("role") or "student",
        "company_name": user.get("company_name") or "",
        "job_title": user.get("job_title") or "",
    }


def _utcnow_str():
    return _fmt(datetime.now(timezone.utc).replace(tzinfo=None))


def _fmt(dt):
    return dt.replace(microsecond=0).isoformat() + "Z"
