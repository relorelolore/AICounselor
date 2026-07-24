from __future__ import annotations

import os

from langchain_core.documents import Document


def to_citations(docs: list[Document], *, snippet_len: int = 200) -> list[dict]:
    out: list[dict] = []
    for i, document in enumerate(docs, start=1):
        metadata = document.metadata or {}
        source = metadata.get("source") or metadata.get("file_path") or ""
        filename = os.path.basename(source) if source else "(unknown)"
        page = int(metadata.get("page") or 0)
        snippet = (document.page_content or "")[:snippet_len].replace("\n", " ").strip()
        out.append(
            {
                "index": i,
                "filename": filename,
                "page": page,
                "snippet": snippet,
            }
        )
    return out
