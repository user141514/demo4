"""
TDD tests for Flask app routes
"""
import io
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Override DB path BEFORE importing app
import backend.auth_db as auth_db
fd, db_path = tempfile.mkstemp(suffix=".db")
os.close(fd)
auth_db.DB_PATH = db_path  # type: ignore
auth_db.init_auth_db()

from backend.app import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def clean_db():
    """每个测试后清空数据"""
    yield
    conn = auth_db.get_conn()
    try:
        conn.execute("DELETE FROM user_sessions")
        conn.execute("DELETE FROM users")
        conn.commit()
    finally:
        conn.close()


# ═════════════════════════════════════════════════════════════
# RED: Health & Pages
# ═════════════════════════════════════════════════════════════

def test_health_returns_ok(client):
    """GET /api/health 返回 200 + status ok"""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert "model" in data


def test_index_serves_html(client):
    """GET / 返回 HTML 首页"""
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"html" in resp.data.lower() or b"<!DOCTYPE" in resp.data


def test_login_page_served(client):
    """GET /login.html 返回登录页"""
    resp = client.get("/login.html")
    assert resp.status_code == 200


def test_404_for_nonexistent_page(client):
    """不存在的页面返回 404"""
    resp = client.get("/nonexistent-page-xyz")
    assert resp.status_code == 404


# ═════════════════════════════════════════════════════════════
# RED: Auth Routes — Register
# ═════════════════════════════════════════════════════════════

def test_register_creates_user_and_sets_cookie(client):
    """POST /api/auth/register 创建用户并设置 cookie"""
    resp = client.post("/api/auth/register", json={
        "email": "test@example.com",
        "display_name": "Test User",
        "password": "password123",
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["user"]["email"] == "test@example.com"
    assert data["user"]["display_name"] == "Test User"
    # Cookie must be set
    assert "lm_session" in resp.headers.get("Set-Cookie", "")


def test_register_rejects_invalid_email(client):
    """无效邮箱返回 400"""
    resp = client.post("/api/auth/register", json={
        "email": "notemail",
        "display_name": "Name",
        "password": "123456",
    })
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_email"


def test_register_rejects_short_password(client):
    """短密码返回 400"""
    resp = client.post("/api/auth/register", json={
        "email": "a@b.com",
        "display_name": "Name",
        "password": "12345",
    })
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_password"


# ═════════════════════════════════════════════════════════════
# RED: Auth Routes — Login / Me / Logout
# ═════════════════════════════════════════════════════════════

def test_login_with_correct_credentials(client):
    """正确凭据登录成功"""
    # 先注册
    client.post("/api/auth/register", json={
        "email": "login@test.com",
        "display_name": "Login",
        "password": "secret123",
    })
    # 登出
    client.post("/api/auth/logout")

    # 登录
    resp = client.post("/api/auth/login", json={
        "email": "login@test.com",
        "password": "secret123",
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["user"]["email"] == "login@test.com"


def test_login_rejects_wrong_password(client):
    """错误密码返回 401"""
    client.post("/api/auth/register", json={
        "email": "wp@test.com",
        "display_name": "WP",
        "password": "correct",
    })
    client.post("/api/auth/logout")

    resp = client.post("/api/auth/login", json={
        "email": "wp@test.com",
        "password": "wrong",
    })
    assert resp.status_code == 401


def test_me_returns_user_after_login(client):
    """登录后 /me 返回用户信息"""
    # 注册（自动登录）
    client.post("/api/auth/register", json={
        "email": "me@test.com",
        "display_name": "Me",
        "password": "123456",
    })
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["user"] is not None
    assert data["user"]["email"] == "me@test.com"


def test_me_returns_null_without_login(client):
    """未登录时 /me 返回 null"""
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.get_json()["user"] is None


def test_logout_clears_session(client):
    """登出后 /me 返回 null"""
    client.post("/api/auth/register", json={
        "email": "out@test.com",
        "display_name": "Out",
        "password": "123456",
    })
    # 确认已登录
    resp = client.get("/api/auth/me")
    assert resp.get_json()["user"] is not None

    # 登出
    client.post("/api/auth/logout")
    resp2 = client.get("/api/auth/me")
    assert resp2.get_json()["user"] is None


# ═════════════════════════════════════════════════════════════
# RED: AI Routes — require valid JSON body
# ═════════════════════════════════════════════════════════════

def test_chat_requires_messages(client):
    """POST /api/chat 缺少 messages 返回 400"""
    resp = client.post("/api/chat", json={})
    assert resp.status_code == 400


def test_generate_dimensions_requires_company_info(client):
    """POST /api/generate-dimensions 缺少 company_info 返回 400"""
    resp = client.post("/api/generate-dimensions", json={})
    assert resp.status_code == 400


def test_generate_descriptions_requires_dimensions(client):
    """POST /api/generate-descriptions 缺少 dimensions 返回 400"""
    resp = client.post("/api/generate-descriptions", json={})
    assert resp.status_code == 400


def test_generate_anchors_requires_dimensions(client):
    """POST /api/generate-anchors 缺少 dimensions 返回 400"""
    resp = client.post("/api/generate-anchors", json={})
    assert resp.status_code == 400


def test_analyze_doc_requires_file(client):
    """POST /api/analyze-doc 没有文件返回 400"""
    resp = client.post("/api/analyze-doc")
    assert resp.status_code == 400


def test_analyze_doc_uses_extracted_document_text(client, monkeypatch):
    """PDF 上传时应使用真实提取文本，而不是占位提示"""
    captured = {}

    def fake_extract(content, filename):
        captured["filename"] = filename
        captured["content"] = content
        return "真实文档内容"

    def fake_analyze(text, filename):
        captured["analyze_text"] = text
        captured["analyze_filename"] = filename
        return f"分析完成: {text}"

    monkeypatch.setattr("backend.app.extract_document_text", fake_extract)
    monkeypatch.setattr("backend.app.analyze_document", fake_analyze)

    resp = client.post(
        "/api/analyze-doc",
        data={"file": (io.BytesIO(b"%PDF-1.4 fake"), "demo.pdf")},
        content_type="multipart/form-data",
    )

    assert resp.status_code == 200
    assert captured["filename"] == "demo.pdf"
    assert captured["analyze_text"] == "真实文档内容"
    assert "需安装" not in resp.get_json()["result"]


def test_analyze_doc_rejects_legacy_doc_file(client):
    """老式 .doc 上传应返回明确错误，而不是伪成功"""
    resp = client.post(
        "/api/analyze-doc",
        data={"file": (io.BytesIO(b"fake-doc"), "legacy.doc")},
        content_type="multipart/form-data",
    )

    assert resp.status_code == 400
    assert ".docx" in resp.get_json()["error"]


# ═════════════════════════════════════════════════════════════
# RED: Export Route
# ═════════════════════════════════════════════════════════════

def test_export_markdown_returns_content(client):
    """POST /api/export format=markdown 返回内容"""
    model = {
        "context": {"company_name": "Test Co", "industry": "Tech", "target_group": "中层"},
        "dimensions": [{"id": "D1", "name": "战略", "definition": "test"}],
        "descriptions": [{"id": "D1", "description": "测试描述"}],
        "anchors": [],
        "date": "2026-06-15",
    }
    resp = client.post("/api/export", json={"format": "markdown", "model": model})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "content" in data
    assert "Test Co" in data["content"]


def test_export_docx_returns_binary(client):
    """POST /api/export format=docx 返回 DOCX 二进制"""
    model = {
        "context": {"company_name": "Test"},
        "dimensions": [],
        "descriptions": [],
        "anchors": [],
    }
    resp = client.post("/api/export", json={"format": "docx", "model": model})
    assert resp.status_code == 200
    assert "vnd.openxmlformats" in resp.content_type


def test_export_pdf_returns_binary(client):
    """POST /api/export format=pdf 返回 PDF 二进制"""
    model = {
        "context": {"company_name": "Test"},
        "dimensions": [],
        "descriptions": [],
        "anchors": [],
    }
    resp = client.post("/api/export", json={"format": "pdf", "model": model})
    assert resp.status_code == 200
    assert resp.content_type == "application/pdf"
    assert resp.data.startswith(b"%PDF")


def test_export_rejects_invalid_format(client):
    """不支持的格式返回 400"""
    resp = client.post("/api/export", json={"format": "exe", "model": {}})
    assert resp.status_code == 400
