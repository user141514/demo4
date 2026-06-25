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
