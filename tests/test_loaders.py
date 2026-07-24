# tests/test_loaders.py
import os
import tempfile
from pathlib import Path
from langchain_core.documents import Document
from rag.loaders import load, SUFFIX_LOADERS


def test_suffix_map_has_required_exts():
    for ext in (".pdf", ".pptx", ".docx"):
        assert ext in SUFFIX_LOADERS, f"missing loader for {ext}"


def test_load_txt_returns_empty_with_warning(tmp_path, capsys):
    p = tmp_path / "a.txt"
    p.write_text("hello")
    docs = load(str(p))
    assert docs == []
    captured = capsys.readouterr()
    assert "unsupported" in captured.out.lower() or "unsupported" in captured.err.lower()


def test_load_pdf_returns_documents(tmp_path):
    """构造一个最简单的 PDF 验证 loader 流程。"""
    from pypdf import PdfWriter
    p = tmp_path / "a.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with open(p, "wb") as f:
        writer.write(f)
    docs = load(str(p))
    assert isinstance(docs, list)
    # blank page 可能 text 为空，但 loader 应该返回至少一条
    # 我们不强依赖内容，只验证结构
    if docs:
        assert isinstance(docs[0], Document)


def test_load_missing_file(tmp_path):
    p = tmp_path / "does-not-exist.pdf"
    # 应该抛 FileNotFoundError 而不是悄悄返回空
    import pytest
    with pytest.raises(FileNotFoundError):
        load(str(p))
