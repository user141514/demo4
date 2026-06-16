"""
Tests for uploaded document text extraction.
"""
from types import SimpleNamespace

from backend import document_parser


def test_extract_document_text_reads_plain_text():
    """TXT/Markdown 文件应直接解码文本"""
    text = document_parser.extract_document_text("战略目标\n人才标准".encode("utf-8"), "demo.txt")
    assert "战略目标" in text
    assert "人才标准" in text


def test_extract_document_text_reads_pdf_via_pypdf(monkeypatch):
    """PDF 文件应通过 pypdf 提取正文"""
    class FakePage:
        def extract_text(self):
            return "战略澄清"

    class FakeReader:
        def __init__(self, stream):
            self.pages = [FakePage()]

    monkeypatch.setattr(document_parser, "PdfReader", FakeReader)
    text = document_parser.extract_document_text(b"%PDF-1.4", "demo.pdf")
    assert text == "战略澄清"


def test_extract_document_text_reads_docx_via_python_docx(monkeypatch):
    """DOCX 文件应通过 python-docx 提取段落文本"""
    fake_doc = SimpleNamespace(paragraphs=[
        SimpleNamespace(text="组织要求"),
        SimpleNamespace(text=""),
        SimpleNamespace(text="领导力标准"),
    ])

    monkeypatch.setattr(document_parser, "Document", lambda stream: fake_doc)
    text = document_parser.extract_document_text(b"PK\x03\x04", "demo.docx")
    assert text == "组织要求\n领导力标准"


def test_extract_document_text_rejects_legacy_doc():
    """老式 .doc 文件应明确提示转成 .docx"""
    try:
        document_parser.extract_document_text(b"fake-doc", "demo.doc")
    except document_parser.DocumentParseError as exc:
        assert ".docx" in str(exc)
    else:
        raise AssertionError("expected DocumentParseError for .doc files")
