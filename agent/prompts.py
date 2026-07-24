from __future__ import annotations


SYSTEM_PROMPT = (
    "你是学校学业辅导员。请仅基于【参考资料】回答学生关于培养方案、课程、毕业要求等问题。"
    "如果参考资料不能回答，请礼貌告知「未在培养方案中查到相关说法，建议咨询学院教务」。"
    "回答结尾用 [1] [2] ... 标注引用，对应参考资料中的段落。"
    "回答使用与学生提问相同的语言。"
)


GRADE_PROMPT = """参考资料：
{docs}

学生问题：{question}

请判断参考资料是否包含回答该问题所需的关键信息。仅输出 JSON，不要其它文字：
{{"relevant": true|false, "reason": "..."}}"""


GENERATE_PROMPT = """参考资料：
{docs}

历史对话：
{history}

学生问题：{question}

请使用与学生提问相同的语言生成回答（含引用编号）。引用编号必须出现在句末。"""


def format_docs_full(docs, snippets: list[str]) -> str:
    """[i] 来源：《文件名》 第 N 页\\n内容：snippet"""
    lines = []
    for i, (d, s) in enumerate(zip(docs, snippets), start=1):
        from os.path import basename
        source = (d.metadata or {}).get("source", "")
        page = (d.metadata or {}).get("page", 0)
        lines.append(f"[{i}] 来源：《{basename(source)}》 第 {page} 页\n    内容：{s}")
    return "\n\n".join(lines)


def format_docs_compact(docs) -> str:
    """仅含 filename + page + page_content[:150]，长度可控。"""
    from os.path import basename
    lines = []
    for i, d in enumerate(docs, start=1):
        source = (d.metadata or {}).get("source", "")
        page = (d.metadata or {}).get("page", 0)
        snippet = (d.page_content or "")[:150].replace("\n", " ").strip()
        lines.append(f"[{i}] 《{basename(source)}》 p{page}：{snippet}")
    return "\n".join(lines)
