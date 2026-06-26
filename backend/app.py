"""
Flask App — 领导力建模智能体
静态文件服务 + DeepSeek API 代理 + DOCX导出 + 用户认证
"""
import json
import os
import sys
import uuid
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, Response, request, jsonify, send_from_directory
from flask_cors import CORS
from backend.config import MAX_UPLOAD_SIZE, ALLOWED_EXTENSIONS, load_settings
from backend.document_parser import DocumentParseError, extract_document_text
from backend.ai_service import (
    chat,
    analyze_document,
    generate_dimensions,
    generate_descriptions,
    generate_anchors,
    build_rule_based_anchors,
    regenerate_item,
    generate_with_audit,
    check_critical_incidents,
    LLMError,
    STEP2_GUIDANCE,
    STEP3_GUIDANCE,
    STEP4_GUIDANCE,
)
from backend.auth_db import create_model_record, init_auth_db, list_model_records
from backend.auth_service import (
    AuthError,
    ensure_default_teacher,
    get_recovery_question,
    login_user,
    register_user,
    reset_password_with_recovery,
)
from backend.auth_middleware import (
    clear_session_cookie,
    current_user,
    load_current_user,
    logout_session,
    require_auth,
    set_session_cookie,
)

app = Flask(__name__, static_folder=None)
CORS(app)

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")

# 初始化认证数据库
init_auth_db()
ensure_default_teacher()

# before_request: 加载用户
app.before_request(load_current_user)


# ── Static Files ──────────────────────────────────────────────

@app.route("/")
def root():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:filename>")
def serve_frontend(filename):
    path = os.path.join(FRONTEND_DIR, filename)
    if os.path.exists(path) and not os.path.isdir(path):
        return send_from_directory(FRONTEND_DIR, filename)
    return jsonify({"error": "Not found"}), 404


# ── Health ────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    settings = load_settings()
    return jsonify({
        "status": "ok",
        "llm_mode": settings.get("llm_mode", "live"),
        "model": settings.get("openai_chat_model", ""),
        "key_configured": bool(settings.get("openai_api_key")),
    })


# ── Auth Routes（借鉴 demo2 blueprints/auth.py） ──────────────

@app.route("/api/auth/register", methods=["POST"])
def api_register():
    data = request.get_json() or {}
    try:
        user, token = register_user(
            data.get("email", ""),
            data.get("display_name", ""),
            data.get("password", ""),
            company_name=data.get("company_name", ""),
            job_title=data.get("job_title", ""),
            recovery_question=data.get("recovery_question", ""),
            recovery_answer=data.get("recovery_answer", ""),
        )
        resp = jsonify({"user": user})
        return set_session_cookie(resp, token)
    except AuthError as e:
        return jsonify({"error": e.code, "message": e.message}), e.status_code


@app.route("/api/auth/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    try:
        user, token = login_user(
            data.get("email", ""),
            data.get("password", ""),
            role=data.get("role", "student"),
        )
        resp = jsonify({"user": user})
        return set_session_cookie(resp, token)
    except AuthError as e:
        return jsonify({"error": e.code, "message": e.message}), e.status_code


@app.route("/api/auth/recover/question", methods=["POST"])
def api_recover_question():
    data = request.get_json() or {}
    try:
        question = get_recovery_question(data.get("email", ""))
        return jsonify({"recovery_question": question})
    except AuthError as e:
        return jsonify({"error": e.code, "message": e.message}), e.status_code


@app.route("/api/auth/recover/reset", methods=["POST"])
def api_recover_reset():
    data = request.get_json() or {}
    try:
        reset_password_with_recovery(
            data.get("email", ""),
            data.get("recovery_answer", ""),
            data.get("new_password", ""),
        )
        return jsonify({"ok": True})
    except AuthError as e:
        return jsonify({"error": e.code, "message": e.message}), e.status_code


@app.route("/api/auth/logout", methods=["POST"])
def api_logout():
    logout_session()
    resp = jsonify({"ok": True})
    return clear_session_cookie(resp)


@app.route("/api/auth/me", methods=["GET"])
def api_me():
    user = current_user()
    if user is None:
        return jsonify({"user": None})
    return jsonify({"user": user})


# ── Step1: Chat + Documents ───────────────────────────────────

@app.route("/api/chat", methods=["POST"])
@require_auth
def api_chat():
    data = request.get_json()
    if not data or "messages" not in data:
        return jsonify({"error": "messages required"}), 400
    try:
        reply = chat(data["messages"], data.get("context", ""), bool(data.get("force_summary", False)))
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/analyze-doc", methods=["POST"])
@require_auth
def api_analyze_doc():
    if "file" not in request.files:
        return jsonify({"error": "file required"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "no file selected"}), 400

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": f"不支持的文件类型: .{ext}"}), 400

    try:
        content = file.read()
        if len(content) > MAX_UPLOAD_SIZE:
            return jsonify({"error": "文件超过10MB限制"}), 400

        text = extract_document_text(content, file.filename)
        result = analyze_document(text, file.filename)
        return jsonify({"result": result, "filename": file.filename})
    except DocumentParseError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Step2: Dimensions ─────────────────────────────────────────

@app.route("/api/generate-dimensions", methods=["POST"])
@require_auth
def api_generate_dimensions():
    data = request.get_json()
    if not data or "company_info" not in data:
        return jsonify({"error": "company_info required"}), 400
    try:
        result, report = generate_with_audit(
            generate_dimensions, "dimension",
            data["company_info"], data.get("level", "中层管理者"),
            max_total_retries=2,
        )
        return jsonify({"result": result, "audit": report, "step_guidance": STEP2_GUIDANCE})
    except Exception as e:
        from backend.ai_service import build_rule_based_dimensions
        result = build_rule_based_dimensions(data["company_info"], data.get("level", "中层管理者"))
        return jsonify({"result": result, "audit": {"total": 0, "passed": 0, "fixed": 0, "failed": 0, "details": []}, "step_guidance": STEP2_GUIDANCE, "fallback_reason": str(e)})


# ── Step3: Descriptions ───────────────────────────────────────

@app.route("/api/generate-descriptions", methods=["POST"])
@require_auth
def api_generate_descriptions():
    data = request.get_json()
    if not data or "dimensions" not in data:
        return jsonify({"error": "dimensions required"}), 400
    try:
        result, report = generate_with_audit(
            generate_descriptions, "description",
            data["dimensions"],
            data.get("company_info", ""),
            data.get("level", "中层管理者"),
            enterprise_terms=data.get("enterprise_terms", ""),
            max_total_retries=2,
        )
        return jsonify({"result": result, "audit": report, "step_guidance": STEP3_GUIDANCE})
    except LLMError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": f"AI调用失败: {e}"}), 500


# ── Step4: Anchors ────────────────────────────────────────────

@app.route("/api/check-incidents", methods=["POST"])
@require_auth
def api_check_incidents():
    data = request.get_json() or {}
    result = check_critical_incidents(
        data.get("critical_incidents", ""),
        data.get("dimensions", []),
        data.get("company_info", ""),
        data.get("level", "中层管理者"),
    )
    return jsonify({"result": result})


@app.route("/api/generate-anchors", methods=["POST"])
@require_auth
def api_generate_anchors():
    data = request.get_json()
    if not data or "dimensions" not in data:
        return jsonify({"error": "dimensions required"}), 400
    try:
        result, report = generate_with_audit(
            generate_anchors, "anchor",
            data["dimensions"],
            data.get("company_info", ""),
            data.get("level", "中层管理者"),
            critical_incidents=data.get("critical_incidents", ""),
            max_total_retries=2,
        )
        if not result:
            raise LLMError("empty anchor result")
        return jsonify({"result": result, "audit": report, "step_guidance": STEP4_GUIDANCE})
    except LLMError as e:
        result = build_rule_based_anchors(data["dimensions"], data.get("critical_incidents", ""))
        return jsonify({"result": result, "audit": {"total": len(result), "passed": len(result), "fixed": 0, "failed": 0, "details": []}, "step_guidance": STEP4_GUIDANCE, "fallback_reason": str(e)})
    except Exception as e:
        result = build_rule_based_anchors(data["dimensions"], data.get("critical_incidents", ""))
        return jsonify({"result": result, "audit": {"total": len(result), "passed": len(result), "fixed": 0, "failed": 0, "details": []}, "step_guidance": STEP4_GUIDANCE, "fallback_reason": str(e)})


# ── Regenerate ────────────────────────────────────────────────

@app.route("/api/regenerate", methods=["POST"])
@require_auth
def api_regenerate():
    data = request.get_json()
    if not data:
        return jsonify({"error": "request body required"}), 400
    try:
        result = regenerate_item(
            data.get("original", ""),
            data.get("direction", "优化表述"),
            data.get("item_type", "定位描述"),
        )
        return jsonify({"result": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Export ────────────────────────────────────────────────────

@app.route("/api/export", methods=["POST"])
@require_auth
def api_export():
    """导出领导力模型为 DOCX 或 Markdown"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "request body required"}), 400

    export_format = data.get("format", "docx")
    model = data.get("model", {})

    try:
        if export_format == "docx":
            from backend.export_service import build_docx_bytes
            from urllib.parse import quote
            content = build_docx_bytes(model)
            filename = quote("领导力模型.docx")
            return Response(
                content,
                mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
            )
        elif export_format == "pdf":
            from backend.export_service import build_pdf_bytes
            from urllib.parse import quote
            content = build_pdf_bytes(model)
            filename = quote("领导力模型.pdf")
            return Response(
                content,
                mimetype="application/pdf",
                headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
            )
        elif export_format == "markdown":
            from backend.export_service import build_markdown
            md = build_markdown(model)
            return jsonify({"content": md, "filename": f"领导力模型_{model.get('date', '')}.md"})
        else:
            return jsonify({"error": f"不支持的导出格式: {export_format}"}), 400
    except Exception as e:
        return jsonify({"error": f"导出失败: {e}"}), 500


# ── Model Records / Instructor Dashboard ─────────────────────

@app.route("/api/model-records", methods=["POST"])
@require_auth
def api_create_model_record():
    user = current_user()
    if user.get("role") != "student":
        return jsonify({"error": "forbidden", "message": "讲师账号不能提交学生建模记录"}), 403

    data = request.get_json() or {}
    summary = data.get("summary")
    dimensions = data.get("dimensions")
    if not isinstance(summary, dict) or not isinstance(dimensions, list):
        return jsonify({"error": "invalid_record", "message": "summary 必须为对象，dimensions 必须为数组"}), 400

    record_id = uuid.uuid4().hex
    created_at = _now_str()
    create_model_record(
        record_id,
        user["user_id"],
        json.dumps(summary, ensure_ascii=False),
        json.dumps(dimensions, ensure_ascii=False),
        created_at,
    )
    return jsonify({"record": {
        "record_id": record_id,
        "created_at": created_at,
        "summary": summary,
        "dimensions": dimensions,
    }})


@app.route("/api/instructor/model-records", methods=["GET"])
@require_auth
def api_instructor_model_records():
    user = current_user()
    if user.get("role") != "instructor":
        return jsonify({"error": "forbidden", "message": "当前账号无权访问讲师看板"}), 403

    records = []
    for row in list_model_records():
        records.append({
            "record_id": row["record_id"],
            "created_at": row["created_at"],
            "summary": json.loads(row["summary_json"]),
            "dimensions": json.loads(row["dimensions_json"]),
            "user": {
                "user_id": row["user_id"],
                "email": row["email"],
                "display_name": row["display_name"],
                "company_name": row["company_name"],
                "job_title": row["job_title"],
            },
        })
    return jsonify({"records": records})


def _now_str():
    return datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None).isoformat() + "Z"


# ── Main ──────────────────────────────────────────────────────

if __name__ == "__main__":
    settings = load_settings()
    print(f"Frontend: {FRONTEND_DIR}")
    print(f"LLM Mode: {settings.get('llm_mode')}")
    print(f"Model: {settings.get('openai_chat_model')}")
    print(f"Key configured: {bool(settings.get('openai_api_key'))}")
    print("Server: http://localhost:8000")
    app.run(host="0.0.0.0", port=8000, debug=True)
