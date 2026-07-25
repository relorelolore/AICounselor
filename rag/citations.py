from __future__ import annotations

import os
from typing import Any

from langchain_core.documents import Document


def to_citations(docs: list[Any], *, snippet_len: int = 200) -> list[dict]:
    """Build citations from the ``ToolMessage.artifact`` payload.

    ``artifact`` may be a list of :class:`langchain_core.documents.Document`
    (in-memory) or a list of plain ``dict`` (after the SQLite checkpointer
    round-trips the artifact, the Document pydantic model comes back as a
    ``{id, metadata, page_content, type: 'Document'}`` mapping). We accept
    either shape so callers don't need to know how the state was loaded.
    """
    out: list[dict] = []
    for i, document in enumerate(docs, start=1):
        if isinstance(document, Document):
            metadata = document.metadata or {}
            page_content = document.page_content or ""
        elif isinstance(document, dict):
            metadata = document.get("metadata") or {}
            page_content = document.get("page_content") or ""
        else:
            # Unexpected shape — degrade gracefully.
            metadata = getattr(document, "metadata", None) or {}
            page_content = getattr(document, "page_content", "") or ""

        source = metadata.get("source") or metadata.get("file_path") or ""
        filename = os.path.basename(source) if source else "(unknown)"
        page = int(metadata.get("page") or 0)
        snippet = (page_content or "")[:snippet_len].replace("\n", " ").strip()
        out.append(
            {
                "index": i,
                "filename": filename,
                "page": page,
                "snippet": snippet,
            }
        )
    return out
