# tests/test_fingerprint.py
import os, json, time
from ingest.fingerprint import hash_file, should_skip, IndexMeta


def test_hash_changes_with_content(tmp_path):
    a = tmp_path / "a.txt"
    a.write_text("hello")
    h1 = hash_file(str(a))
    a.write_text("world")
    h2 = hash_file(str(a))
    assert h1 != h2


def test_should_skip_unchanged(tmp_path):
    a = tmp_path / "a.txt"
    a.write_text("hi")
    h = hash_file(str(a))
    stat = a.stat()
    meta_entry = {"hash": h, "mtime": stat.st_mtime}
    assert should_skip(meta_entry, str(a)) is True


def test_should_skip_changed_content(tmp_path):
    a = tmp_path / "a.txt"
    a.write_text("v1")
    h_old = hash_file(str(a))
    time.sleep(0.01)
    a.write_text("v2-different")
    stat = a.stat()
    meta_entry = {"hash": h_old, "mtime": stat.st_mtime - 100}
    assert should_skip(meta_entry, str(a)) is False


def test_index_meta_roundtrip(tmp_path):
    p = tmp_path / "meta.json"
    meta = IndexMeta(path=str(p))
    meta.set("/a.pdf", {"hash": "abc", "mtime": 1.0, "chunks": 3})
    meta.set_failed("/b.docx", "parse error")
    meta2 = IndexMeta(path=str(p))
    assert meta2.get("/a.pdf")["chunks"] == 3
    assert any(f["path"] == "/b.docx" for f in meta2.failed())