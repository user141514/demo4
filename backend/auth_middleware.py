"""
认证中间件 — Cookie Session + require_auth 装饰器
借鉴 demo2 core/auth_session.py
"""
from functools import wraps

from flask import g, request

from backend.auth_db import get_active_session, revoke_session
from backend.auth_service import hash_token, SESSION_DAYS


def load_current_user():
    """before_request 钩子：从 cookie 加载用户"""
    g.current_user = None
    g.current_session_token = None

    token = request.cookies.get("lm_session")
    if not token:
        return

    session = get_active_session(hash_token(token), _now_str())
    if not session:
        return

    g.current_session_token = token
    g.current_user = session["user"]


def require_auth(view_func):
    """装饰器：要求登录"""
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if g.get("current_user") is None:
            from flask import jsonify
            return jsonify({"error": "auth_required", "message": "请先登录"}), 401
        return view_func(*args, **kwargs)
    return wrapped


def current_user():
    return g.get("current_user")


def set_session_cookie(response, token):
    response.set_cookie(
        "lm_session",
        token,
        max_age=SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        samesite="Lax",
        path="/",
    )
    return response


def clear_session_cookie(response):
    response.delete_cookie("lm_session", path="/")
    return response


def logout_session():
    token = g.get("current_session_token")
    if token:
        revoke_session(hash_token(token), _now_str())


def _now_str():
    from datetime import datetime
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
