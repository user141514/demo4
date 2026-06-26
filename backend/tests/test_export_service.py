"""
Tests for export service data normalization and M05 output structure.
"""
from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from backend.export_service import build_docx_bytes, build_export_outline, build_markdown, build_pdf_bytes


W_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def _sample_model():
    return {
        "context": {
            "company_name": "测试科技",
            "industry": "科技服务",
            "scale": "500人左右，快速扩张期",
            "strategy": "高速扩张；客户体验升级",
            "pains": "跨部门协作摩擦；项目质量不稳定",
            "target_group": "中层管理者",
            "profile": "能拆解目标，带团队完成复杂项目交付",
        },
        "dimensions": [
            {
                "id": "LN-023",
                "nm": "跨部门协作",
                "df": "建立跨团队协同机制，协调关键资源，推动项目目标一致。",
                "priority_judgment": {
                    "score": 4.35,
                    "label": "core",
                    "formula": "score = 战略相关性*0.35 + 证据强度*0.25 + 层级关键性*0.25 + 发展杠杆*0.15",
                    "components": {
                        "strategic_relevance": 5,
                        "evidence_strength": 4,
                        "role_criticality": 4,
                        "development_leverage": 5,
                    },
                    "rationale": "战略扩张和访谈痛点均集中指向跨部门协同。",
                },
                "sources": {
                    "strategy": "高速扩张",
                    "framework": "横向领导力 Lateral Leadership",
                    "interview": "跨部门协作摩擦大",
                },
            },
            {
                "id": "U_manual",
                "nm": "项目质量",
                "df": "明确交付标准，跟踪过程偏差，推动问题闭环。",
                "sources": {"interview": "用户手动添加"},
                "manual": True,
            },
        ],
        "descriptions": [
            {
                "id": "LN-023",
                "desc": "中层管理者需要建立跨部门协同节奏，提前识别依赖关系，并用清晰规则推动多方达成一致。",
                "qc": {"ok": True, "issues": []},
            },
            {
                "id": "U_manual",
                "desc": "中层管理者需要把项目质量标准拆到关键节点，并通过复盘和纠偏减少返工。",
                "qc": {"ok": True, "issues": []},
            },
        ],
        "anchors": [
            {
                "id": "LN-023",
                "ex": ["提前识别跨部门依赖冲突，组织关键方确定资源承诺并按周复盘。"],
                "st": ["在项目启动时对齐各方目标、边界和交付节奏。"],
                "bl": ["只转发本部门诉求，未澄清其他团队约束。"],
            },
            {
                "id": "U_manual",
                "ex": ["建立质量预警清单，推动关键缺陷在交付前关闭。"],
                "st": ["按节点检查交付物质量，记录偏差并跟进责任人。"],
                "bl": ["临近交付才发现问题，导致反复返工。"],
            },
        ],
        "date": "2026-06-18",
    }


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


def test_build_markdown_uses_m05_document_structure():
    """Markdown 导出应按 M05 最终模型文档结构组织内容"""
    md = build_markdown(_sample_model())

    for text in [
        "目录",
        "第一章  模型概述",
        "第二章  维度详解",
        "附录A  建模方法说明",
        "附录B  参照标准库说明",
        "BARS 五级行为描述",
        "水平分级",
        "行为锚点描述",
        "横向领导力 Lateral Leadership",
        "用户手动添加",
    ]:
        assert text in md


def test_build_docx_contains_m05_sections_and_real_anchor_tables():
    """DOCX 导出应包含 M05 章节，并为每个维度生成真实 Word 表格"""
    content = build_docx_bytes(_sample_model())

    with ZipFile(BytesIO(content)) as zf:
        assert "word/document.xml" in zf.namelist()
        root = ET.fromstring(zf.read("word/document.xml"))

    paragraphs = []
    for para in root.findall(".//w:p", W_NS):
        text = "".join(t.text or "" for t in para.findall(".//w:t", W_NS))
        if text:
            paragraphs.append(text)
    full_text = "\n".join(paragraphs)

    for text in [
        "目录",
        "第一章  模型概述",
        "第二章  维度详解",
        "附录A  建模方法说明",
        "附录B  参照标准库说明",
        "《测试科技 中层管理者 领导力模型》",
        "BARS 五级行为描述",
    ]:
        assert text in full_text

    tables = root.findall(".//w:tbl", W_NS)
    assert len(tables) >= 2
    table_text = "\n".join(
        t.text or ""
        for table in tables
        for t in table.findall(".//w:t", W_NS)
    )
    assert "水平分级" in table_text
    assert "行为锚点描述" in table_text
    assert "5分" in table_text
    assert "3分" in table_text
    assert "1分" in table_text
    assert "提前识别跨部门依赖冲突" in table_text


def test_build_pdf_contains_m05_sections():
    """PDF 导出应复用同一套 M05 内容大纲，并返回有效 PDF 二进制"""
    outline = build_export_outline(_sample_model())
    text = "\n".join(block["text"] for block in outline if block.get("text"))
    for expected in [
        "目录",
        "第一章",
        "模型概述",
        "第二章",
        "维度详解",
        "附录A",
        "附录B",
        "BARS 五级行为描述",
    ]:
        assert expected in text

    content = build_pdf_bytes(_sample_model())
    assert content.startswith(b"%PDF")


def test_export_outline_uses_company_name_and_short_management_level_in_title():
    """标题应使用公司名称和短管理层级，而不是行业/业务和长建模对象说明。"""
    model = _sample_model()
    model["context"] = {
        "公司名称": "杭州测试科技",
        "行业/业务": "企业级SaaS，服务制造业客户，产品覆盖生产协同、设备数据采集、质量追溯等",
        "规模/阶段": "约800人，总部杭州，三地办公；正从项目交付型向平台订阅型业务转型",
        "战略重点": "订阅收入占比提升；平台化复用减少定制；客户价值指标统一；数据驱动决策",
        "管理痛点": "跨部门协作慢、责任不清；中层对经营指标拆解不足；客户价值理解不一致",
        "管理层级": "中层管理者",
        "建模层级": "中层管理者（产品负责人、研发小组负责人、交付经理、客户成功经理、售前方案经理、区域业务负责人），管理6-20人",
        "优秀画像": "能用数据判断优先级，推动共性需求标准化",
        "标准库参照": "美世领导力模型 + DDI成功者画像",
    }

    outline = build_export_outline(model)

    assert outline[0] == {"type": "title", "text": "《杭州测试科技 中层管理者 领导力模型》"}


def test_export_outline_structures_modeling_background_as_tables_and_bullets():
    """建模背景应拆成稳定字段表格和战略挑战列表，避免输出一个混杂长段落。"""
    model = _sample_model()
    model["context"] = {
        "公司名称": "杭州测试科技",
        "行业/业务": "企业级SaaS，服务制造业客户",
        "规模/阶段": "约800人，总部杭州，三地办公；正从项目交付型向平台订阅型业务转型",
        "战略重点": "1. 订阅收入占比提升；2. 平台化复用减少定制；3. 客户价值指标统一；4. 数据驱动决策",
        "管理痛点": "1. 跨部门协作慢、责任不清；2. 中层对经营指标拆解不足；3. 客户价值理解不一致；4. 人才培养依赖个人带教；5. 问题复盘不深入",
        "管理层级": "中层管理者",
        "建模层级": "中层管理者（产品负责人、研发小组负责人、交付经理、客户成功经理、售前方案经理、区域业务负责人），管理6-20人",
        "管理幅度": "6-20人",
        "建模对象说明": "产品负责人、研发小组负责人、交付经理、客户成功经理、售前方案经理、区域业务负责人",
        "层级定位": "承接战略、拆解经营指标、推动跨部门协作与团队交付",
    }

    outline = build_export_outline(model)
    bg_index = next(i for i, block in enumerate(outline) if block == {"type": "subheading", "text": "1.1 建模背景"})
    bg_blocks = outline[bg_index + 1:bg_index + 9]

    assert {"type": "body", "text": "基础信息"} in bg_blocks
    assert {
        "type": "table",
        "rows": [
            ["项目", "内容"],
            ["公司名称", "杭州测试科技"],
            ["行业/业务", "企业级SaaS，服务制造业客户"],
            ["规模/阶段", "约800人，总部杭州，三地办公；正从项目交付型向平台订阅型业务转型"],
            ["管理层级", "中层管理者"],
        ],
    } in bg_blocks
    assert {"type": "body", "text": "建模对象"} in bg_blocks
    assert {
        "type": "table",
        "rows": [
            ["项目", "内容"],
            ["适用对象", "产品负责人、研发小组负责人、交付经理、客户成功经理、售前方案经理、区域业务负责人"],
            ["管理幅度", "6-20人"],
            ["层级定位", "承接战略、拆解经营指标、推动跨部门协作与团队交付"],
        ],
    } in bg_blocks
    assert {"type": "body", "text": "战略与挑战"} in bg_blocks
    assert {"type": "body", "text": "战略重点：订阅收入占比提升；平台化复用减少定制；客户价值指标统一；数据驱动决策"} in bg_blocks
    assert {"type": "body", "text": "管理痛点：跨部门协作慢、责任不清；中层对经营指标拆解不足；客户价值理解不一致；人才培养依赖个人带教；问题复盘不深入"} in bg_blocks


def test_standard_library_source_text_keeps_only_label_and_reference_model():
    """标准库映射来源只展示来源标签和引用模型，避免暴露内部编号或映射维度。"""
    model = _sample_model()
    model["dimensions"] = [{
        "id": "LN-001",
        "name": "战略拆解与落地",
        "definition": "将战略要求拆解为团队目标和行动计划。",
        "source_type": "标准库映射",
        "source_detail": "LN-001",
        "framework_dimension": "战略拆解与落地",
        "framework_name": "Hay Group 领导力素质模型",
    }]
    model["descriptions"] = [{
        "id": "LN-001",
        "description": "能够把战略要求拆成可执行目标。",
    }]
    model["anchors"] = [{"id": "LN-001", "bars5": []}]

    outline = build_export_outline(model)
    source_block = next(block for block in outline if block.get("text", "").startswith("来源标签："))

    assert source_block["text"] == "来源标签：标准库映射；引用模型：Hay Group 领导力素质模型"
    assert "来源说明" not in source_block["text"]
    assert "映射维度" not in source_block["text"]
    assert "LN-001" not in source_block["text"]
