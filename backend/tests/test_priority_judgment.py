"""
Tests for formula-backed priority judgment.
"""
import pytest


def test_normalize_priority_judgment_uses_formula_and_thresholds():
    from backend.ai_service import normalize_priority_judgment

    dim = {
        "name": "战略引领",
        "priority_judgment": {
            "strategic_relevance": 5,
            "evidence_strength": 4,
            "role_criticality": 5,
            "development_leverage": 4,
            "rationale": "直接承接高速扩张战略，访谈中多次出现目标拆解问题。",
        },
    }

    judgment = normalize_priority_judgment(dim)

    assert judgment["score"] == pytest.approx(4.6)
    assert judgment["label"] == "core"
    assert "战略相关性*0.35" in judgment["formula"]
    assert judgment["components"]["strategic_relevance"] == 5
    assert judgment["rationale"].startswith("直接承接")


def test_normalize_priority_judgment_falls_back_from_existing_label():
    from backend.ai_service import normalize_priority_judgment

    judgment = normalize_priority_judgment({
        "name": "项目质量",
        "priority": "supplementary",
        "rationale": "当前仅来自单点访谈。",
    })

    assert judgment["label"] == "supplementary"
    assert judgment["score"] < 3.0
    assert judgment["source"] == "fallback"
    assert "当前仅来自单点访谈" in judgment["rationale"]


def test_generate_dimensions_normalizes_llm_priority_judgment(monkeypatch):
    from backend.ai_service import generate_dimensions

    def fake_call(system, user, max_tokens=2000, use_reasoner=False):
        return """
        {
          "recommended": [{
            "id": "D1",
            "name": "战略引领",
            "definition": "拆解战略目标，推动团队形成阶段行动方案。",
            "sources": {"strategy": "高速扩张", "interview": "目标拆解不足"},
            "priority": "important",
            "priority_judgment": {
              "strategic_relevance": 5,
              "evidence_strength": 5,
              "role_criticality": 4,
              "development_leverage": 4,
              "rationale": "战略和访谈证据均指向该维度。"
            },
            "rationale": "战略和访谈证据均指向该维度。"
          }],
          "alternatives": []
        }
        """

    monkeypatch.setattr("backend.ai_service._call_deepseek", fake_call)

    result = generate_dimensions("科技企业，高速扩张，目标拆解不足", use_kb=False)
    dim = result["recommended"][0]

    assert dim["priority"] == "core"
    assert dim["priority_judgment"]["score"] == pytest.approx(4.6)
    assert dim["priority_judgment"]["label"] == "core"
