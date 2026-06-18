"""
Tests for behavioral-anchor quality guards.
"""


def test_find_similar_anchor_texts_flags_template_like_cross_dimension_behavior():
    """不同维度若只是替换维度名，其余行为高度相似，应被识别"""
    from backend.ai_service import find_similar_anchor_texts

    anchors = [
        {
            "dimension_id": "D1",
            "dimension_name": "战略引领",
            "anchors": {
                "excellent": [{"text": "建立战略引领检查清单，每周跟踪关键任务进展并推动问题闭环。"}],
                "standard": [],
                "below": [],
            },
        },
        {
            "dimension_id": "D2",
            "dimension_name": "团队赋能",
            "anchors": {
                "excellent": [{"text": "建立团队赋能检查清单，每周跟踪关键任务进展并推动问题闭环。"}],
                "standard": [],
                "below": [],
            },
        },
    ]

    issues = find_similar_anchor_texts(anchors, threshold=0.82)

    assert issues
    assert issues[0]["level"] == "excellent"
    assert set(issues[0]["dimension_names"]) == {"战略引领", "团队赋能"}


def test_find_similar_anchor_texts_allows_specific_dimension_behavior():
    """场景、对象、结果均不同的行为不应被误判为模板化"""
    from backend.ai_service import find_similar_anchor_texts

    anchors = [
        {
            "dimension_id": "D1",
            "dimension_name": "战略引领",
            "anchors": {
                "excellent": [{"text": "拆解年度战略目标，识别关键里程碑并协调资源完成阶段复盘。"}],
                "standard": [],
                "below": [],
            },
        },
        {
            "dimension_id": "D2",
            "dimension_name": "团队赋能",
            "anchors": {
                "excellent": [{"text": "设计成员成长任务，结合项目复盘提供反馈并调整授权边界。"}],
                "standard": [],
                "below": [],
            },
        },
    ]

    assert find_similar_anchor_texts(anchors, threshold=0.82) == []
