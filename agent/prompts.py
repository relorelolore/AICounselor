from __future__ import annotations

import os

from langchain_core.documents import Document


COUNSELOR_SYSTEM_PROMPT = """你是学校的 AI 学业辅导员，叫"小辅"。你的职责是回答学生关于培养方案、课程、毕业要求等问题。

行为准则：
- 像人一样说话。不要重复使用"未在培养方案中查到相关说法，建议咨询学院教务"这种固定模板——只在确实毫无信息时简短说明。
- 必要时调用 search_documents 工具检索资料；如果只是打招呼、问心情、问自己之前说过什么、闲聊，根本不需要查资料——直接回应即可。
- 答完要点的事。如果学生问得模糊，可以简短反问澄清，而不是堆一大段空话。
- 用与学生相同的语言回答。
- 不知道的事坦然承认，别编。
- 回答尽量精炼：能一句话说完的不要五句。"""


def format_docs_as_text(docs: list[Document], *, snippet_chars: int = 300) -> str:
    """Format a list of Documents as the tool return string.

    Each entry is rendered as::

        [i] 来源：《文件名》 第 N 页
            内容：snippet[:snippet_chars]

    Empty list returns ``""`` so the tool caller can decide what to do.
    """
    lines: list[str] = []
    for i, document in enumerate(docs, start=1):
        metadata = document.metadata or {}
        source = metadata.get("source") or metadata.get("file_path") or ""
        filename = os.path.basename(source) if source else "(unknown)"
        page = int(metadata.get("page") or 0)
        snippet = (document.page_content or "")[:snippet_chars].replace("\n", " ").strip()
        lines.append(f"[{i}] 来源：《{filename}》 第 {page} 页\n    内容：{snippet}")
    return "\n\n".join(lines)


__all__ = ["COUNSELOR_SYSTEM_PROMPT", "format_docs_as_text"]