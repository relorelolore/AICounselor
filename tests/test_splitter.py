# tests/test_splitter.py
from langchain_core.documents import Document
from rag.splitter import split, DEFAULT_SEPARATORS


def test_default_separators_chinese_aware():
    assert "。" in DEFAULT_SEPARATORS
    assert "\n\n" in DEFAULT_SEPARATORS


def test_short_doc_not_split():
    docs = [Document(page_content="短文本", metadata={"source": "x.pdf"})]
    out = split(docs, chunk_size=500, chunk_overlap=80)
    assert len(out) == 1
    assert out[0].page_content == "短文本"


def test_long_doc_is_split():
    text = "\n\n".join([f"段落{i}：" + "汉字" * 50 for i in range(20)])
    docs = [Document(page_content=text, metadata={"source": "x.pdf", "page": 1})]
    out = split(docs, chunk_size=200, chunk_overlap=30)
    assert len(out) > 1
    # 切分后的 chunk 不应超过 chunk_size ± 重叠
    for d in out:
        assert len(d.page_content) <= 200 + 30


def test_overlap_present():
    text = "ABCDEFGH" * 100   # 800 字符
    docs = [Document(page_content=text, metadata={"source": "x.pdf"})]
    out = split(docs, chunk_size=100, chunk_overlap=20)
    assert len(out) >= 2
    # 相邻 chunk 应有重叠字符
    s1 = out[0].page_content
    s2 = out[1].page_content
    assert s1[-20:] in s2


def test_metadata_preserved():
    docs = [Document(page_content="a" * 600, metadata={"source": "s.pdf", "page": 7})]
    out = split(docs, chunk_size=200, chunk_overlap=20)
    for d in out:
        assert d.metadata.get("source") == "s.pdf"
        assert d.metadata.get("page") == 7
