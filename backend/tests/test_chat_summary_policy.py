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


def test_chat_summary_prompt_requires_company_name_and_management_level(monkeypatch):
    """Step1 摘要应包含给最终标题使用的公司名称和短管理层级字段。"""
    captured = {}

    def fake_call(system, user, max_tokens=1000, use_reasoner=False):
        captured["user"] = user
        return "ok"

    monkeypatch.setattr("backend.ai_service._call_deepseek", fake_call)

    from backend.ai_service import chat

    chat([{"role": "user", "content": "我们是杭州测试科技，做企业级SaaS，中层管理者需要建模。"}], force_summary=True)

    assert "公司名称" in captured["user"]
    assert "管理层级" in captured["user"]
    assert "建模对象说明" in captured["user"]
    assert "管理幅度" in captured["user"]
