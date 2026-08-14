"""本地处理回退：AI 不可用或失败时使用（关键词分类 + 摘要截取）"""
import re

from .classify import classify_item


def summarize(text, limit: int = 130) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def fallback_process(items, config):
    """本地回退：分类 + 截取摘要。返回处理后的条目"""
    # 源→分类 映射：关键词分类失败时按源归类
    src_cat = {}
    for s in config.sources:
        if s.category in ("finance", "tech", "world"):
            src_cat[s.name] = s.category
    for it in items:
        classify_item(it, config.profile)
        if it.category == "other" and it.source in src_cat:
            it.category = src_cat[it.source]
        it.cn_summary = summarize(it.summary or it.full_text)
        if it.language == "en":
            it.cn_title = it.title
        it.keep = True
    return items
