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
    assert "ci.disabled = true" in html
    assert "sendBtn.disabled = true" in html


def test_step2_removes_manual_source_inputs_but_sets_manual_interview_source():
    html = _read_frontend("step2.html")

    assert "editSrcStg" not in html
    assert "editSrcFwk" not in html
    assert "editSrcInt" not in html
    assert "用户手动添加" in html
    assert "sources: { interview: '用户手动添加' }" in html


def test_step2_shows_formula_backed_priority_judgment():
    html = _read_frontend("step2.html")

    assert "renderPriorityJudgment" in html
    assert "优先级判断" in html
    assert "战略相关性35%" in html
    assert "priorityJudgmentForLabel" in html


def test_step5_uses_framework_layout_without_weight_language():
    html = _read_frontend("step5.html")

    assert "framework-viz" in html
    assert "dim-side left" in html
    assert "dim-side right" in html
    assert "模型维度框架图" in html
    assert "权重" not in html
    assert "5/5" not in html
    assert "优先级总览" not in html
