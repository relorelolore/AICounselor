from langchain_core.documents import Document
from rag.citations import to_citations


def test_citations_basic():
    docs = [
        Document(
            page_content="培养方案要求实践学分不少于 16 分。" * 10,
            metadata={"source": "plan.pdf", "page": 3},
        ),
        Document(
            page_content="通识选修课包括人文与社会两大模块。" * 5,
            metadata={"source": "plan.pdf", "page": 5},
        ),
    ]
    out = to_citations(docs, snippet_len=80)
    assert len(out) == 2
    assert out[0]["index"] == 1
    assert out[0]["filename"] == "plan.pdf"
    assert out[0]["page"] == 3
    assert len(out[0]["snippet"]) <= 80
    assert out[1]["index"] == 2


def test_citations_filename_from_path():
    docs = [
        Document(
            page_content="x",
            metadata={"source": "/abs/path/培养方案.pdf", "page": 1},
        )
    ]
    out = to_citations(docs)
    assert out[0]["filename"] == "培养方案.pdf"


def test_citations_missing_page_defaults_to_zero():
    docs = [Document(page_content="x", metadata={"source": "a.pdf"})]
    out = to_citations(docs)
    assert out[0]["page"] == 0


def test_citations_empty():
    assert to_citations([]) == []
