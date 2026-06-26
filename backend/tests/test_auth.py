"""
TDD tests for auth system (auth_db + auth_service + auth_middleware)
"""
import os
import sys
import tempfile
import pytest

# Ensure backend package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend import auth_db
from backend import auth_service
from backend.auth_service import register_user, login_user, hash_token, AuthError
from backend.auth_middleware import load_current_user, require_auth


# ── Fixtures ───────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_db():
    """每个测试使用独立临时数据库"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    old_path = auth_db.DB_PATH
    auth_db.DB_PATH = path  # type: ignore
    auth_db.init_auth_db()
    yield
    auth_db.DB_PATH = old_path  # type: ignore
    try:
        os.unlink(path)
    except OSError:
        pass


# ═════════════════════════════════════════════════════════════
# RED: auth_db — 用户 CRUD
# ═════════════════════════════════════════════════════════════

def test_create_user_stores_email_and_name():
    """创建用户后能通过邮箱查回"""
    auth_db.create_user("u1", "a@b.com", "张三", "hash123", "2026-01-01T00:00:00Z")
    user = auth_db.get_user_by_email("a@b.com")
    assert user is not None
    assert user["email"] == "a@b.com"
    assert user["display_name"] == "张三"


def test_create_user_stores_profile_and_student_role_by_default():
    """用户资料字段和默认学生角色会被保存"""
    auth_db.create_user(
        "u1",
        "profile@b.com",
        "张三",
        "hash123",
        "2026-01-01T00:00:00Z",
        company_name="杭州测试科技",
        job_title="产品经理",
    )

    user = auth_db.get_user_by_email("profile@b.com")

    assert user["role"] == "student"
    assert user["company_name"] == "杭州测试科技"
    assert user["job_title"] == "产品经理"


def test_get_user_by_email_nonexistent_returns_none():
    """查询不存在的邮箱返回 None"""
    assert auth_db.get_user_by_email("no@exist.com") is None


def test_create_duplicate_email_raises():
    """重复邮箱抛出异常"""
    auth_db.create_user("u1", "dup@b.com", "A", "h1", "2026-01-01T00:00:00Z")
    with pytest.raises(ValueError):
        auth_db.create_user("u2", "dup@b.com", "B", "h2", "2026-01-01T00:00:00Z")


def test_get_user_by_id():
    """通过 user_id 查询"""
    auth_db.create_user("uid1", "x@y.com", "Name", "hash", "2026-01-01T00:00:00Z")
    user = auth_db.get_user_by_id("uid1")
    assert user is not None
    assert user["email"] == "x@y.com"


def test_get_user_by_id_missing_returns_none():
    """查询不存在的 user_id 返回 None"""
    assert auth_db.get_user_by_id("no-such-id") is None


def test_count_users():
    """统计用户数"""
    assert auth_db.count_users() == 0
    auth_db.create_user("u1", "a@b.com", "A", "h", "2026-01-01T00:00:00Z")
    assert auth_db.count_users() == 1
    auth_db.create_user("u2", "b@b.com", "B", "h", "2026-01-01T00:00:00Z")
    assert auth_db.count_users() == 2


# ═════════════════════════════════════════════════════════════
# RED: auth_db — Session CRUD
# ═════════════════════════════════════════════════════════════

def test_create_and_get_active_session():
    """创建 session 后能通过 token_hash 查回"""
    auth_db.create_user("u1", "s@test.com", "Test", "hash", "2026-01-01T00:00:00Z")
    auth_db.create_session("sid1", "u1", "th_abc", "2026-01-01T00:00:00Z", "2099-01-01T00:00:00Z")

    session = auth_db.get_active_session("th_abc", "2026-06-01T00:00:00Z")
    assert session is not None
    assert session["user_id"] == "u1"
    assert session["user"]["email"] == "s@test.com"


def test_expired_session_returns_none():
    """过期的 session 返回 None"""
    auth_db.create_user("u1", "ex@test.com", "Test", "hash", "2026-01-01T00:00:00Z")
    auth_db.create_session("sid1", "u1", "th_exp", "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z")

    session = auth_db.get_active_session("th_exp", "2026-06-01T00:00:00Z")  # now > expires
    assert session is None


def test_revoked_session_returns_none():
    """被撤销的 session 返回 None"""
    auth_db.create_user("u1", "rv@test.com", "Test", "hash", "2026-01-01T00:00:00Z")
    auth_db.create_session("sid1", "u1", "th_rev", "2026-01-01T00:00:00Z", "2099-01-01T00:00:00Z")

    auth_db.revoke_session("th_rev", "2026-06-01T00:00:00Z")
    session = auth_db.get_active_session("th_rev", "2026-06-01T00:00:00Z")
    assert session is None


# ═════════════════════════════════════════════════════════════
# RED: auth_service — 注册
# ═════════════════════════════════════════════════════════════

def test_register_returns_user_and_token():
    """注册成功返回用户信息和 token"""
    user, token = register_user(
        "new@test.com",
        "New User",
        "123456",
        company_name="New Co",
        job_title="Manager",
        recovery_question="项目名？",
        recovery_answer="Alpha",
    )
    assert user["email"] == "new@test.com"
    assert user["display_name"] == "New User"
    assert user["role"] == "student"
    assert user["company_name"] == "New Co"
    assert user["job_title"] == "Manager"
    assert len(token) > 20  # token 足够长


def test_register_persists_user():
    """注册后能从数据库查到用户"""
    register_user("keep@test.com", "Keep", "password")
    db_user = auth_db.get_user_by_email("keep@test.com")
    assert db_user is not None
    assert db_user["display_name"] == "Keep"


def test_register_creates_valid_session():
    """注册后自动创建可用的 session"""
    from datetime import datetime, timezone
    _, token = register_user("sess@test.com", "Session", "123456")
    now = datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None).isoformat() + "Z"
    session = auth_db.get_active_session(hash_token(token), now)
    assert session is not None
    assert session["user"]["email"] == "sess@test.com"


def test_register_rejects_invalid_email():
    """拒绝无效邮箱"""
    with pytest.raises(AuthError) as exc:
        register_user("notanemail", "Name", "123456")
    assert exc.value.code == "invalid_email"


def test_register_rejects_short_name():
    """拒绝过短的姓名"""
    with pytest.raises(AuthError) as exc:
        register_user("a@b.com", "A", "123456")
    assert exc.value.code == "invalid_name"


def test_register_rejects_short_password():
    """拒绝过短的密码"""
    with pytest.raises(AuthError) as exc:
        register_user("a@b.com", "Name", "12345")
    assert exc.value.code == "invalid_password"


def test_register_rejects_duplicate_email():
    """拒绝重复邮箱"""
    register_user("dup@test.com", "First", "123456")
    with pytest.raises(AuthError) as exc:
        register_user("dup@test.com", "Second", "123456")
    assert exc.value.code == "email_exists"


# ═════════════════════════════════════════════════════════════
# RED: auth_service — 登录
# ═════════════════════════════════════════════════════════════

def test_login_returns_user_and_token():
    """登录成功返回用户信息和 token"""
    register_user("login@test.com", "Login User", "mypassword")
    user, token = login_user("login@test.com", "mypassword", role="student")
    assert user["email"] == "login@test.com"
    assert user["role"] == "student"
    assert len(token) > 20


def test_login_rejects_student_when_instructor_role_requested():
    """学生账号不能用讲师角色登录"""
    register_user("student@test.com", "Student", "mypassword")

    with pytest.raises(AuthError) as exc:
        login_user("student@test.com", "mypassword", role="instructor")

    assert exc.value.code == "invalid_credentials"


def test_default_teacher_account_can_login_as_instructor_only():
    """内置讲师账号只允许按讲师角色登录"""
    auth_service.ensure_default_teacher()

    teacher, token = login_user("teacher", "meitai123456", role="instructor")

    assert teacher["role"] == "instructor"
    assert teacher["display_name"] == "讲师"
    assert len(token) > 20

    with pytest.raises(AuthError):
        login_user("teacher", "meitai123456", role="student")


def test_recovery_question_and_reset_password_flow():
    """安全问题找回密码可以重置学生账号密码"""
    register_user(
        "recover@test.com",
        "Recover User",
        "oldpass",
        recovery_question="第一个项目？",
        recovery_answer="Alpha 项目",
    )

    question = auth_service.get_recovery_question("recover@test.com")
    assert question == "第一个项目？"

    with pytest.raises(AuthError) as exc:
        auth_service.reset_password_with_recovery("recover@test.com", "Wrong", "newpass1")
    assert exc.value.code == "invalid_recovery_answer"

    auth_service.reset_password_with_recovery("recover@test.com", "alpha 项目", "newpass1")
    user, token = login_user("recover@test.com", "newpass1")
    assert user["email"] == "recover@test.com"
    assert len(token) > 20


def test_login_creates_new_session():
    """登录创建新的可用 session"""
    from datetime import datetime, timezone
    register_user("login2@test.com", "User2", "abcdef")
    _, token = login_user("login2@test.com", "abcdef")
    now = datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None).isoformat() + "Z"
    session = auth_db.get_active_session(hash_token(token), now)
    assert session is not None


def test_login_rejects_wrong_password():
    """拒绝错误密码"""
    register_user("wp@test.com", "WP", "correct")
    with pytest.raises(AuthError) as exc:
        login_user("wp@test.com", "wrong")
    assert exc.value.code == "invalid_credentials"


def test_login_rejects_nonexistent_email():
    """拒绝不存在的邮箱"""
    with pytest.raises(AuthError) as exc:
        login_user("no@exist.com", "whatever")
    assert exc.value.code == "invalid_credentials"


def test_login_rejects_empty_credentials():
    """拒绝空邮箱或空密码"""
    with pytest.raises(AuthError) as exc:
        login_user("", "password")
    assert exc.value.code == "invalid_credentials"

    with pytest.raises(AuthError) as exc2:
        login_user("a@b.com", "")
    assert exc2.value.code == "invalid_credentials"


# ═════════════════════════════════════════════════════════════
# RED: auth_service — hash_token
# ═════════════════════════════════════════════════════════════

def test_hash_token_is_deterministic():
    """相同输入产生相同哈希"""
    assert hash_token("abc") == hash_token("abc")


def test_hash_token_differs_for_different_inputs():
    """不同输入产生不同哈希"""
    assert hash_token("abc") != hash_token("def")
