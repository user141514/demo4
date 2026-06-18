"""
导出服务 — M05 最终模型文档结构（DOCX / PDF / Markdown）
"""
import html
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


PRIORITY_FORMULA = "score = 战略相关性*0.35 + 证据强度*0.25 + 层级关键性*0.25 + 发展杠杆*0.15"
PRIORITY_COMPONENT_LABELS = {
    "strategic_relevance": "战略相关性",
    "evidence_strength": "证据强度",
    "role_criticality": "层级关键性",
    "development_leverage": "发展杠杆",
}
PRIORITY_COMPONENT_WEIGHTS = {
    "strategic_relevance": 0.35,
    "evidence_strength": 0.25,
    "role_criticality": 0.25,
    "development_leverage": 0.15,
}
PRIORITY_FALLBACK_COMPONENTS = {
    "core": {
        "strategic_relevance": 5,
        "evidence_strength": 4,
        "role_criticality": 5,
        "development_leverage": 4,
    },
    "important": {
        "strategic_relevance": 4,
        "evidence_strength": 3,
        "role_criticality": 4,
        "development_leverage": 3,
    },
    "supplementary": {
        "strategic_relevance": 2,
        "evidence_strength": 2,
        "role_criticality": 3,
        "development_leverage": 2,
    },
}
PRIORITY_LABELS = {"core": "核心", "important": "重要", "supplementary": "补充"}


# ── Context normalization ─────────────────────────────────


def _norm(ctx):
    """标准化 context：兼容中英文key"""
    if not ctx:
        return {}
    c = dict(ctx)
    mapping = {
        "行业/业务": "industry", "规模/阶段": "scale",
        "战略重点": "strategy", "管理痛点": "pains",
        "建模层级": "target_group", "优秀画像": "profile",
    }
    for cn, en in mapping.items():
        if cn in c:
            c[en] = c[cn]
    return c


def _g(ctx, key, default=""):
    """安全获取，自动查中英文key"""
    if key in ctx:
        return str(ctx[key] or default)
    # Try Chinese alias
    alias = {
        "company_name": "行业/业务", "industry": "行业/业务",
        "target_group": "建模层级", "strategy": "战略重点",
        "pains": "管理痛点", "profile": "优秀画像",
        "scale": "规模/阶段",
    }
    cn = alias.get(key)
    if cn and cn in ctx:
        return str(ctx[cn] or default)
    return default


# ── Public API ────────────────────────────────────────────


def build_docx_bytes(model):
    """生成 DOCX 文件（M05结构，纯OOXML生成真实表格）"""
    blocks = build_export_outline(model)
    document_xml = _document_xml(blocks)
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _content_types_xml())
        zf.writestr("_rels/.rels", _rels_xml())
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/styles.xml", _styles_xml())
    return buffer.getvalue()


def build_pdf_bytes(model):
    """生成 PDF 文件（与 DOCX 共享 M05 内容结构）"""
    _register_pdf_fonts()
    blocks = build_export_outline(model)
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )
    styles = _pdf_styles()
    story = []

    for block in blocks:
        kind = block["type"]
        if kind == "table":
            story.append(_pdf_table(block["rows"], styles))
            story.append(Spacer(1, 4 * mm))
            continue
        pdf_style = styles.get(kind, styles["body"])
        story.append(Paragraph(_pdf_escape(str(block.get("text", ""))), pdf_style))
        story.append(Spacer(1, 4 * mm if kind == "title" else 2.5 * mm))

    doc.build(story)
    return buffer.getvalue()


def _key(d):
    """兼容 id / dimension_id 两种字段名"""
    return d.get("id") or d.get("dimension_id") or ""


def build_markdown(model):
    """生成 Markdown 文本（M05结构）"""
    blocks = build_export_outline(model)
    lines = []
    for block in blocks:
        kind = block["type"]
        text = block.get("text", "")
        if kind == "title":
            lines.append(f"# {text}")
        elif kind == "heading":
            lines.append(f"## {text}")
        elif kind == "subheading":
            lines.append(f"### {text}")
        elif kind == "table":
            lines.append("| 水平分级 | 行为描述 |")
            lines.append("|---|---|")
            for row in block["rows"][1:]:
                lines.append(f"| {row[0]} | {row[1]} |")
        elif text:
            lines.append(text)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def build_export_outline(model):
    """构建 M05 输出大纲，供 DOCX / PDF / Markdown 复用。"""
    model = _normalize_model(model)
    ctx = _norm(model.get("context") or {})
    dims = model.get("dimensions") or []
    descs = {_key(d): d for d in (model.get("descriptions") or [])}
    anchors = {_key(a): a for a in (model.get("anchors") or [])}

    company_label = _g(ctx, 'company_name') or _g(ctx, 'industry', '企业')
    target = _g(ctx, "target_group", "管理者")
    blocks = [
        {"type": "title", "text": f"《{company_label} {target} 领导力模型》"},
        {"type": "body", "text": f"版本：V1.0  |  构建日期：{model.get('date', '')}"},
        {"type": "body", "text": f"适用对象：{target}"},
        {"type": "heading", "text": "目录"},
        {"type": "body", "text": "第一章  模型概述"},
        {"type": "body", "text": f"第二章  维度详解（{len(dims)}个维度）"},
    ]

    for i, dim in enumerate(dims, 1):
        blocks.append({"type": "body", "text": f"2.{i}  {dim.get('name', '未命名')}"})

    blocks.extend([
        {"type": "body", "text": "附录A  建模方法说明"},
        {"type": "body", "text": "附录B  参照标准库说明"},
        {"type": "heading", "text": "第一章  模型概述"},
        {"type": "subheading", "text": "1.1 建模背景"},
        {"type": "body", "text": _bg_text(ctx)},
        {"type": "body", "text": f"本模型聚焦{target}，旨在支撑管理者把战略要求转化为可观察、可发展、可评估的领导力行为。"},
        {"type": "subheading", "text": "1.2 模型框架图"},
        {"type": "body", "text": " / ".join(dim.get("name", "未命名") for dim in dims) or "暂无维度"},
        {"type": "heading", "text": "第二章  维度详解"},
    ])

    for i, dim in enumerate(dims, 1):
        dim_id = dim.get("id")
        desc = descs.get(dim_id, {})
        anc = anchors.get(dim_id, {})
        dim_name = dim.get("name", "未命名")
        blocks.append({"type": "subheading", "text": f"2.{i}  {dim_name}"})
        blocks.append({"type": "body", "text": "维度定义：" + (dim.get("definition") or "--")})
        blocks.append({"type": "body", "text": f"{target}定位要求：" + (desc.get("description") or "--")})
        blocks.append({"type": "body", "text": _priority_text(dim)})
        blocks.append({"type": "body", "text": "行为锚定对照表："})

        anc_data = anc.get("anchors", {})
        rows = [["水平分级", "行为描述"]]
        for level_key, label in [
            ("excellent", "优秀"),
            ("standard", "达标"),
            ("below", "不达标"),
        ]:
            texts = _anchor_texts(anc_data, level_key)
            if not texts:
                rows.append([label, "--"])
                continue
            rows.append([label, "\n".join(texts)])
        blocks.append({"type": "table", "rows": rows})

    blocks.append({"type": "heading", "text": "附录A  建模方法说明"})
    blocks.append({
        "type": "body",
        "text": "本模型采用AI辅助建模方式，融合企业背景摘要、用户访谈、文档分析、标准领导力知识库与行为锚定方法形成。各维度均经过确认后进入描述和行为锚定阶段。",
    })
    blocks.append({"type": "heading", "text": "附录B  参照标准库说明"})
    source_lines = _source_lines(dims)
    blocks.append({
        "type": "body",
        "text": "\n".join(source_lines) if source_lines else "本次建模未记录外部标准库来源，维度主要来自对话归纳与AI综合生成。",
    })
    return blocks


# ── Internal ──────────────────────────────────────────────


def _build_paragraphs(model):
    return [(b["type"], b.get("text", "")) for b in build_export_outline(model) if b["type"] != "table"]


def _bg_text(ctx):
    return (
        f"本模型聚焦{_g(ctx, 'target_group', '目标管理群体')}，"
        f"围绕{_g(ctx, 'strategy', '未提供战略')}等战略重点，"
        f"针对{_g(ctx, 'pains', '未提供痛点')}等管理挑战建立。"
        f"行业背景：{_g(ctx, 'industry', '未提供')}，规模：{_g(ctx, 'scale', '未提供')}。"
    )


def _anchor_texts(anchor_data, level):
    items = anchor_data.get(level) or []
    if not items:
        return None
    return [item.get("text") if isinstance(item, dict) else str(item) for item in items]


def _source_lines(dims):
    lines = []
    seen = set()
    for dim in dims:
        sources = dim.get("sources") or {}
        for label, key in [("战略映射", "strategy"), ("标准库参照", "framework"), ("访谈归纳", "interview")]:
            value = str(sources.get(key) or "").strip()
            if not value:
                continue
            entry = f"{label}：{value}"
            if entry not in seen:
                seen.add(entry)
                lines.append(entry)
    return lines


def _clamp_component(value, default=3):
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        number = default
    return max(1, min(5, number))


def _priority_label(score):
    if score >= 4.2:
        return "core"
    if score >= 3.0:
        return "important"
    return "supplementary"


def _priority_score(components):
    return round(sum(
        _clamp_component(components.get(key)) * PRIORITY_COMPONENT_WEIGHTS[key]
        for key in PRIORITY_COMPONENT_WEIGHTS
    ), 2)


def _priority_payload(dim):
    raw = dim.get("priority_judgment") or dim.get("pj") or {}
    if isinstance(raw, dict):
        components = raw.get("components") if isinstance(raw.get("components"), dict) else {}
        if components:
            components = {
                key: _clamp_component(components.get(key))
                for key in PRIORITY_COMPONENT_WEIGHTS
            }
            score = raw.get("score")
            try:
                score = round(float(score), 2)
            except (TypeError, ValueError):
                score = _priority_score(components)
            return {
                "score": score,
                "label": raw.get("label") or _priority_label(score),
                "formula": raw.get("formula") or PRIORITY_FORMULA,
                "components": components,
                "rationale": raw.get("rationale") or dim.get("rationale") or "基于现有信息按公式化评分生成。",
            }

    label = dim.get("priority") or dim.get("pri") or "important"
    components = dict(PRIORITY_FALLBACK_COMPONENTS.get(label, PRIORITY_FALLBACK_COMPONENTS["important"]))
    score = _priority_score(components)
    return {
        "score": score,
        "label": _priority_label(score),
        "formula": PRIORITY_FORMULA,
        "components": components,
        "rationale": dim.get("rationale") or "未记录 LLM 分项时，系统按优先级标签采用兜底分项评分。",
    }


def _priority_text(dim):
    payload = _priority_payload(dim)
    score_text = f"{payload['score']:g}/5"
    label_text = PRIORITY_LABELS.get(payload["label"], payload["label"])
    component_text = "，".join(
        f"{PRIORITY_COMPONENT_LABELS[key]}{payload['components'][key]}"
        for key in PRIORITY_COMPONENT_LABELS
    )
    return (
        f"优先级判断：{label_text}（{score_text}）。"
        f"公式：{payload['formula']}。"
        f"分项：{component_text}。"
        f"理由：{payload['rationale']}"
    )


def _normalize_model(model):
    """兼容前端 step5 的简写字段与导出层标准字段"""
    ctx = _norm(model.get("context") or {})
    dims = []
    for dim in (model.get("dimensions") or []):
        dims.append({
            **dim,
            "id": dim.get("id") or dim.get("dimension_id") or "",
            "name": dim.get("name") or dim.get("nm") or "",
            "definition": dim.get("definition") or dim.get("df") or "",
            "priority": dim.get("priority") or dim.get("pri") or "important",
            "priority_judgment": dim.get("priority_judgment") or dim.get("pj"),
        })

    descs = []
    for desc in (model.get("descriptions") or []):
        descs.append({
            **desc,
            "id": desc.get("id") or desc.get("dimension_id") or "",
            "description": desc.get("description") or desc.get("desc") or "",
        })

    anchors = []
    for anc in (model.get("anchors") or []):
        anchor_payload = anc.get("anchors")
        if not anchor_payload:
            anchor_payload = {
                "excellent": anc.get("excellent") or anc.get("ex") or [],
                "standard": anc.get("standard") or anc.get("st") or [],
                "below": anc.get("below") or anc.get("bl") or [],
            }
        anchors.append({
            **anc,
            "id": anc.get("id") or anc.get("dimension_id") or "",
            "anchors": anchor_payload,
        })

    return {
        **model,
        "context": ctx,
        "dimensions": dims,
        "descriptions": descs,
        "anchors": anchors,
    }


def _pdf_styles():
    styles = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "PdfTitle",
            parent=styles["Title"],
            fontName="STSong-Light",
            fontSize=18,
            leading=24,
            spaceAfter=6,
        ),
        "heading": ParagraphStyle(
            "PdfHeading",
            parent=styles["Heading2"],
            fontName="STSong-Light",
            fontSize=13,
            leading=18,
            spaceBefore=4,
            spaceAfter=2,
        ),
        "subheading": ParagraphStyle(
            "PdfSubHeading",
            parent=styles["Heading3"],
            fontName="STSong-Light",
            fontSize=11.5,
            leading=16,
            spaceBefore=3,
            spaceAfter=2,
        ),
        "body": ParagraphStyle(
            "PdfBody",
            parent=styles["BodyText"],
            fontName="STSong-Light",
            fontSize=10.5,
            leading=15,
            spaceAfter=2,
        ),
    }


def _pdf_escape(text):
    escaped = html.escape(text)
    return escaped.replace("\n", "<br/>")


def _register_pdf_fonts():
    if "STSong-Light" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))


def _pdf_table(rows, styles):
    data = [
        [Paragraph(_pdf_escape(str(cell)), styles["body"]) for cell in row]
        for row in rows
    ]
    table = Table(data, colWidths=[26 * mm, 130 * mm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F4ECF4")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#4A1550")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D0C0D3")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


# ── DOCX XML Templates ────────────────────────────────────


def _document_xml(blocks):
    body_parts = []
    for block in blocks:
        if block["type"] == "table":
            body_parts.append(_table_xml(block["rows"]))
        else:
            body_parts.append(_para_xml(block["type"], block.get("text", "")))
    body = "".join(body_parts)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}"
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/>'
        "</w:sectPr></w:body></w:document>"
    )


def _para_xml(style, text):
    style_id = {"title": "Title", "heading": "Heading1", "subheading": "Heading2"}.get(style)
    ppr = f'<w:pPr><w:pStyle w:val="{style_id}"/></w:pPr>' if style_id else ""
    return f"<w:p>{ppr}<w:r>{_text_xml(text)}</w:r></w:p>"


def _text_xml(text):
    parts = []
    for i, line in enumerate(str(text).splitlines() or [""]):
        if i:
            parts.append("<w:br/>")
        parts.append(f"<w:t>{html.escape(line)}</w:t>")
    return "".join(parts)


def _table_xml(rows):
    row_xml = "".join(_tr_xml(row) for row in rows)
    return (
        "<w:tbl>"
        '<w:tblPr><w:tblW w:w="9360" w:type="dxa"/>'
        "<w:tblBorders>"
        '<w:top w:val="single" w:sz="6" w:space="0" w:color="D0C0D3"/>'
        '<w:left w:val="single" w:sz="6" w:space="0" w:color="D0C0D3"/>'
        '<w:bottom w:val="single" w:sz="6" w:space="0" w:color="D0C0D3"/>'
        '<w:right w:val="single" w:sz="6" w:space="0" w:color="D0C0D3"/>'
        '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="EAE0EC"/>'
        '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="EAE0EC"/>'
        "</w:tblBorders>"
        '<w:tblCellMar><w:top w:w="120" w:type="dxa"/><w:left w:w="120" w:type="dxa"/><w:bottom w:w="120" w:type="dxa"/><w:right w:w="120" w:type="dxa"/></w:tblCellMar>'
        "</w:tblPr>"
        '<w:tblGrid><w:gridCol w:w="1600"/><w:gridCol w:w="7760"/></w:tblGrid>'
        f"{row_xml}</w:tbl>"
    )


def _tr_xml(row):
    return "<w:tr>" + "".join(_tc_xml(cell, idx) for idx, cell in enumerate(row)) + "</w:tr>"


def _tc_xml(text, idx):
    width = "1600" if idx == 0 else "7760"
    return (
        f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/></w:tcPr>'
        f"<w:p><w:r>{_text_xml(text)}</w:r></w:p></w:tc>"
    )


def _content_types_xml():
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        "</Types>"
    )


def _rels_xml():
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        "</Relationships>"
    )


def _styles_xml():
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:rPr><w:b/><w:sz w:val="40"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:rPr><w:b/><w:sz w:val="30"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:rPr><w:b/><w:sz w:val="24"/></w:rPr></w:style>'
        "</w:styles>"
    )
