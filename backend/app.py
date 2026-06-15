"""
Flask App — 领导力建模智能体
静态文件服务 + DeepSeek API 代理 + DOCX/PDF 导出
"""
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from backend.config import MAX_UPLOAD_SIZE, ALLOWED_EXTENSIONS, load_settings
from backend.ai_service import (
    chat,
    analyze_document,
    generate_dimensions,
    generate_descriptions,
    generate_anchors,
    regenerate_item,
    LLMError,
)

app = Flask(__name__, static_folder=None)
CORS(app)

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")


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


# ── Step1: Chat + Documents ───────────────────────────────────

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json()
    if not data or "messages" not in data:
        return jsonify({"error": "messages required"}), 400
    try:
        reply = chat(data["messages"], data.get("context", ""))
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/analyze-doc", methods=["POST"])
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

        if ext in ("txt", "md"):
            text = content.decode("utf-8", errors="replace")
        elif ext == "pdf":
            text = f"[PDF: {file.filename}] 需安装 pypdf 库进行文本提取"
        elif ext in ("docx", "doc"):
            text = f"[DOCX: {file.filename}] 需安装 python-docx 库进行文本提取"
        else:
            text = content.decode("utf-8", errors="replace")

        result = analyze_document(text, file.filename)
        return jsonify({"result": result, "filename": file.filename})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Step2: Dimensions ─────────────────────────────────────────

@app.route("/api/generate-dimensions", methods=["POST"])
def api_generate_dimensions():
    data = request.get_json()
    if not data or "company_info" not in data:
        return jsonify({"error": "company_info required"}), 400
    try:
        result = generate_dimensions(data["company_info"], data.get("level", "中层管理者"))
        return jsonify({"result": result})
    except LLMError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": f"AI调用失败: {e}"}), 500


# ── Step3: Descriptions ───────────────────────────────────────

@app.route("/api/generate-descriptions", methods=["POST"])
def api_generate_descriptions():
    data = request.get_json()
    if not data or "dimensions" not in data:
        return jsonify({"error": "dimensions required"}), 400
    try:
        result = generate_descriptions(
            data["dimensions"],
            data.get("company_info", ""),
            data.get("level", "中层管理者"),
        )
        return jsonify({"result": result})
    except LLMError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": f"AI调用失败: {e}"}), 500


# ── Step4: Anchors ────────────────────────────────────────────

@app.route("/api/generate-anchors", methods=["POST"])
def api_generate_anchors():
    data = request.get_json()
    if not data or "dimensions" not in data:
        return jsonify({"error": "dimensions required"}), 400
    try:
        result = generate_anchors(
            data["dimensions"],
            data.get("company_info", ""),
            data.get("level", "中层管理者"),
        )
        return jsonify({"result": result})
    except LLMError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": f"AI调用失败: {e}"}), 500


# ── Regenerate ────────────────────────────────────────────────

@app.route("/api/regenerate", methods=["POST"])
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
            content = build_docx_bytes(model)
            return content, 200, {
                "Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "Content-Disposition": "attachment; filename=领导力模型.docx",
            }
        elif export_format == "markdown":
            from backend.export_service import build_markdown
            md = build_markdown(model)
            return jsonify({"content": md, "filename": f"领导力模型_{model.get('date', '')}.md"})
        else:
            return jsonify({"error": f"不支持的导出格式: {export_format}"}), 400
    except Exception as e:
        return jsonify({"error": f"导出失败: {e}"}), 500


# ── Main ──────────────────────────────────────────────────────

if __name__ == "__main__":
    settings = load_settings()
    print(f"Frontend: {FRONTEND_DIR}")
    print(f"LLM Mode: {settings.get('llm_mode')}")
    print(f"Model: {settings.get('openai_chat_model')}")
    print(f"Key configured: {bool(settings.get('openai_api_key'))}")
    print("Server: http://localhost:8000")
    app.run(host="0.0.0.0", port=8000, debug=True)
