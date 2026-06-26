"""
Static regression checks for feedback-driven frontend changes.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read_frontend(name: str) -> str:
    return (ROOT / "frontend" / name).read_text(encoding="utf-8")


def test_step1_requires_explicit_summary_confirmation_and_locks_after_confirm():
    html = _read_frontend("step1.html")

    assert "collectionState" in html
    assert "summary_ready" in html
    assert "confirmed" in html
    assert "confirmSummary()" in html
    assert "summaryConfirmed = true" not in html.split("function parseSummary", 1)[1].split("function renderSummary", 1)[0]
    assert "requestSummary" in html
    assert "可继续补充" in html


def test_step2_removes_manual_source_inputs_but_sets_manual_interview_source():
    html = _read_frontend("step2.html")

    assert "editSrcStg" not in html
    assert "editSrcFwk" not in html
    assert "editSrcInt" not in html
    assert "用户手动添加" in html
    assert "sources:{type:'对话归纳', detail:'用户手动添加'}" in html
    assert "MIN_SELECTED = 6" in html
    assert "source_type" in html


def test_step2_does_not_show_priority_judgment():
    html = _read_frontend("step2.html")

    assert "renderPriorityJudgment" not in html
    assert "priorityJudgmentForLabel" not in html
    assert "战略文档关键词" in html
    assert "标准库映射" in html


def test_step2_standard_mapping_uses_model_name_dimension_display():
    html = _read_frontend("step2.html")

    assert "compactModelName" in html
    assert "join('-')" in html
    assert "连接成熟模型" not in html
    assert "kbId" not in html


def test_step4_marks_sample_as_single_dimension_only():
    html = _read_frontend("step4.html")

    assert "填入单维度示例" in html
    assert "可以只填写某一个领导力维度" in html
    assert "不是所有维度的通用" in html
    assert "这个事件主要对应哪个领导力维度" in html
    assert "lm_incident_dimension" in html
    assert "criticalIncidentPayloadText" in html
    assert "【事件对应领导力维度】" in html
    assert "关键事件来源" not in html


def test_step5_uses_framework_layout_without_weight_language():
    html = _read_frontend("step5.html")

    assert "framework-viz" in html
    assert "dim-side left" in html
    assert "dim-side right" in html
    assert "模型维度框架图" in html
    assert "BARS 五级行为描述" in html
    assert "正负向行为对照" in html
    assert "权重" not in html
    assert "5/5" not in html
    assert "优先级总览" not in html


def test_login_page_does_not_offer_guest_entry():
    html = _read_frontend("login.html")

    assert "跳过登录" not in html
    assert "不登录也可直接建模" not in html
    assert "请登录后使用" in html
    assert "登录（可选）" not in html


def test_login_page_uses_mahdi_style_auth_tabs():
    html = _read_frontend("login.html")

    assert "auth-tabs" in html
    assert "用户登录" in html
    assert "用户注册" in html
    assert "讲师登录" in html
    assert "找回密码" in html
    assert "company_name" in html
    assert "job_title" in html
    assert "recovery_question" in html
    assert "recovery_answer" in html
    assert "role: 'instructor'" in html


def test_login_page_hides_default_teacher_credentials():
    html = _read_frontend("login.html")

    assert "默认讲师账号" not in html
    assert "teacher / meitai123456" not in html
    assert "讲师端只读展示摘要信息和最终维度" in html


def test_index_page_does_not_offer_guest_mode_entry():
    html = _read_frontend("index.html")

    assert "访客模式" not in html
    assert "登录（可选）" not in html
    assert "直接开始建模" not in html
    assert "无需注册登录" not in html
    assert "请登录后使用" in html
    assert "teacher.html" in html


def test_step2_submits_confirmed_summary_and_dimensions_record():
    html = _read_frontend("step2.html")

    assert "/api/model-records" in html
    assert "lm_company_info" in html
    assert "dimensions: confirmed" in html
    assert "await fetch" in html


def test_teacher_dashboard_lists_summary_and_final_dimensions():
    html = _read_frontend("teacher.html")

    assert "/api/instructor/model-records" in html
    assert "讲师看板" in html
    assert "摘要信息" in html
    assert "最终维度" in html
    assert "renderRecords" in html
