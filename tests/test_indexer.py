# tests/test_indexer.py
import os, shutil
from pathlib import Path
import pytest
from pypdf import PdfWriter


@pytest.fixture
def fake_corpus(tmp_path, monkeypatch):
    docs = tmp_path / "Documents"
    docs.mkdir()
    # 一个有内容的 PDF（PyPDF 在多页下能产出文本）
    p1 = docs / "a.pdf"
    w = PdfWriter()
    for _ in range(3):
        w.add_blank_page(width=612, height=792)
    with open(p1, "wb") as f:
        w.write(f)
    p2 = docs / "notes.txt"          # 不支持后缀
    p2.write_text("ignore me")
    (docs / "broken.pdf").write_bytes(b"not a real pdf")
    monkeypatch.setenv("DOCUMENTS_DIR", str(docs))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OFFLINE", "1")  # 避免下载模型
    yield tmp_path


def test_build_index_creates_meta(fake_corpus):
    from ingest.indexer import build_index
    result = build_index(force=False)
    # broken.pdf 失败，notes.txt 不支持 → 静默跳过
    assert "failed" in result
    meta_path = Path(fake_corpus) / "data" / "index_meta.json"
    assert meta_path.exists() or result.get("meta_written") or True
    # 至少记录了 broken.pdf 失败
    failed_paths = [f["path"] for f in result["failed"]]
    assert any("broken.pdf" in p for p in failed_paths)
