"""
Tests for Step1 summary gating policy.
"""


def test_chat_force_summary_instructs_model_to_stop_asking(monkeypatch):
    """达到最大轮次时，后端 prompt 应要求输出摘要而不是继续追问"""
    captured = {}

    def fake_call(system, user, max_tokens=1000, use_reasoner=False):
        captured["user"] = user
        return "ok"

    monkeypatch.setattr("backend.ai_service._call_deepseek", fake_call)

    from backend.ai_service import chat

    messages = []
    for idx in range(6):
        messages.append({"role": "user", "content": f"回答{idx}"})

    chat(messages, force_summary=True)

    assert "已达到信息采集上限" in captured["user"]
    assert "必须输出【摘要】" in captured["user"]
    assert "不要继续追问" in captured["user"]
