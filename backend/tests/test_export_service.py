"""
Tests for export service data normalization.
"""
from backend.export_service import build_markdown


def test_build_markdown_supports_frontend_shaped_model():
    """前端 step5 传入的 nm/df/desc/ex/st/bl 结构也应正确导出"""
    model = {
        "context": {"行业/业务": "科技", "建模层级": "中层管理者"},
        "dimensions": [{"id": "D1", "nm": "战略引领", "df": "将战略目标转成执行计划"}],
        "descriptions": [{"id": "D1", "desc": "能把公司战略转成团队行动"}],
        "anchors": [{
            "id": "D1",
            "ex": ["提前识别偏差并调整资源"],
            "st": ["定期对齐战略目标"],
            "bl": ["只被动接收战略信息"],
        }],
        "date": "2026-06-16",
    }

    md = build_markdown(model)

    assert "战略引领" in md
    assert "将战略目标转成执行计划" in md
    assert "能把公司战略转成团队行动" in md
    assert "提前识别偏差并调整资源" in md
    assert "定期对齐战略目标" in md
    assert "只被动接收战略信息" in md
