import importlib

from langchain_core.documents import Document


def test_embeddings_lazy_init(monkeypatch):
    """get_embeddings exposes the configured embedding object without encoding."""
    import rag.embeddings as embeddings

    class FakeHuggingFaceEmbeddings:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    embeddings.get_embeddings.cache_clear()
    monkeypatch.setattr(
        embeddings, "HuggingFaceEmbeddings", FakeHuggingFaceEmbeddings
    )
    emb = embeddings.get_embeddings()
    assert emb.kwargs["model_name"] == embeddings.DEFAULT_EMBED_MODEL


def test_retriever_uses_chroma_persist_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import rag.retriever as r

    importlib.reload(r)

    class FakeChroma:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def as_retriever(self, *, search_type, search_kwargs):
            from types import SimpleNamespace

            return SimpleNamespace(
                search_type=search_type,
                search_kwargs=search_kwargs,
            )

    r.get_chroma.cache_clear()
    monkeypatch.setattr(r, "Chroma", FakeChroma)
    monkeypatch.setattr(r, "get_embeddings", lambda: object())
    rc = r.get_retriever(k=4)
    assert rc.search_kwargs["k"] == 4
    assert r.get_chroma().kwargs["persist_directory"] == str(tmp_path / "chroma")


def test_chroma_roundtrip_with_ephemeral():
    """使用 LangChain 提供的 ephemeral chroma 验证 add/query 流程。"""
    from langchain_chroma import Chroma
    from rag.embeddings import get_embeddings

    emb = get_embeddings()
    docs = [
        Document(
            page_content="培养方案要求实践学分不少于 16 分",
            metadata={"source": "x.pdf", "page": 1},
        ),
        Document(
            page_content="通识选修课包括人文与社会两大模块",
            metadata={"source": "x.pdf", "page": 2},
        ),
    ]
    db = Chroma.from_documents(
        documents=docs,
        embedding=emb,
        collection_name="t",
        persist_directory=None,
    )
    out = db.similarity_search("实践学分要求", k=1)
    assert out and "实践学分" in out[0].page_content
