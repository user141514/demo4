"""
导出服务 — DOCX（纯XML生成） + Markdown
借鉴 demo2 leadership_export.py 的 DOCX 生成方式
"""
import html
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile


def build_docx_bytes(model):
    """生成 DOCX 文件（纯 XML，不依赖 python-docx）"""
    paragraphs = _build_paragraphs(model)
    document_xml = _document_xml(paragraphs)
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _content_types_xml())
        zf.writestr("_rels/.rels", _rels_xml())
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/styles.xml", _styles_xml())
    return buffer.getvalue()


def build_markdown(model):
    """生成 Markdown 文本"""
    context = model.get("context") or {}
    dims = model.get("dimensions") or []
    descs = {d.get("id"): d for d in (model.get("descriptions") or [])}
    anchors = {a.get("dimension_id") or a.get("id"): a for a in (model.get("anchors") or [])}

    lines = [
        f"# {context.get('company_name', '企业')} {context.get('target_group', '管理者')} 领导力模型",
        "",
        f"> 生成时间：{model.get('date', '')}",
        "",
        "## 模型概览",
        "",
        f"- 维度数量：{len(dims)}",
        f"- 行业：{context.get('industry', '未提供')}",
        f"- 建模层级：{context.get('target_group', '未指定')}",
        "",
        "---",
        "",
    ]

    for i, dim in enumerate(dims, 1):
        dim_id = dim.get("id")
        desc = descs.get(dim_id, {})
        anc = anchors.get(dim_id, {})

        lines.append(f"## {i}. {dim.get('name', '未命名')}")
        lines.append("")
        if dim.get("definition"):
            lines.append(f"**定义**：{dim['definition']}")
            lines.append("")
        if desc.get("description"):
            lines.append(f"**定位描述**：{desc['description']}")
            lines.append("")

        anc_data = anc.get("anchors", {})
        excellent = _anchor_texts(anc_data, "excellent")
        standard = _anchor_texts(anc_data, "standard")
        below = _anchor_texts(anc_data, "below")

        if excellent:
            lines.append("### ⭐ 优秀水平")
            lines.append("")
            for t in excellent:
                lines.append(f"- {t}")
            lines.append("")
        if standard:
            lines.append("### ✅ 达标水平")
            lines.append("")
            for t in standard:
                lines.append(f"- {t}")
            lines.append("")
        if below:
            lines.append("### ⚠️ 不达标")
            lines.append("")
            for t in below:
                lines.append(f"- {t}")
            lines.append("")

    return "\n".join(lines)


def _build_paragraphs(model):
    context = model.get("context") or {}
    dims = model.get("dimensions") or []
    descs = {d.get("id"): d for d in (model.get("descriptions") or [])}
    anchors = {a.get("dimension_id") or a.get("id"): a for a in (model.get("anchors") or [])}

    title = f"《{context.get('company_name', '企业')} {context.get('target_group', '管理者')} 领导力模型》"
    paragraphs = [
        ("title", title),
        ("body", f"版本：V1.0"),
        ("body", f"适用对象：{context.get('target_group', '--')}"),
        ("heading", "第一章 模型概述"),
        ("body", _background_text(context)),
        ("heading", "第二章 维度详解"),
    ]

    for dim in dims:
        dim_id = dim.get("id")
        desc = descs.get(dim_id, {})
        anc = anchors.get(dim_id, {})
        anc_data = anc.get("anchors", {})

        paragraphs.append(("heading", f"{dim_id} {dim.get('name', '未命名')}"))
        paragraphs.append(("body", f"维度定义：{dim.get('definition', '--')}"))
        paragraphs.append(("body", f"定位描述：{desc.get('description', '--')}"))
        paragraphs.append(("body", "优秀行为：" + "；".join(_anchor_texts(anc_data, "excellent") or ["--"])))
        paragraphs.append(("body", "达标行为：" + "；".join(_anchor_texts(anc_data, "standard") or ["--"])))
        paragraphs.append(("body", "不达标表现：" + "；".join(_anchor_texts(anc_data, "below") or ["--"])))

    paragraphs.append(("heading", "附录A 建模方法说明"))
    paragraphs.append(("body", "本模型采用 AI 辅助建模方式，融合企业背景、用户访谈、上传文档与标准库参照形成。"))

    return paragraphs


def _background_text(context):
    text = (
        f"{context.get('company_name', '企业')}属于{context.get('industry', '未提供行业')}，"
        f"聚焦{context.get('target_group', '目标管理群体')}。"
    )
    return text


def _anchor_texts(anchor_data, level):
    items = anchor_data.get(level) or []
    if not items:
        return None
    return [item.get("text") if isinstance(item, dict) else str(item) for item in items]


# ── DOCX XML Templates ────────────────────────────────────────

def _document_xml(paragraphs):
    body = "".join(_para_xml(style, text) for style, text in paragraphs)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}"
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/>'
        "</w:sectPr></w:body></w:document>"
    )


def _para_xml(style, text):
    style_id = {"title": "Title", "heading": "Heading1"}.get(style)
    ppr = f'<w:pPr><w:pStyle w:val="{style_id}"/></w:pPr>' if style_id else ""
    return f"<w:p>{ppr}<w:r><w:t>{html.escape(str(text))}</w:t></w:r></w:p>"


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
        "</w:styles>"
    )
