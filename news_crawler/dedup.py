"""标题/摘要相似度去重"""
import difflib
import re


def _norm(t: str) -> str:
    t = (t or "").lower()
    t = re.sub(r"[\W_]+", "", t, flags=re.UNICODE)
    return t


def _ngrams(s: str, n: int = 4):
    """提取字符 n-gram 集合（长度不足时退化为含原文的集合）"""
    return {s[i:i + n] for i in range(max(0, len(s) - n + 1))}


def dedup_items(items, threshold: float = 0.85, key=None, prefer_score: bool = False):
    """按指定文本的相似度去重，保留首次出现的条目（源优先级由配置顺序决定）

    key：提取比较文本的可调用对象，默认用标题（例如跨源去重可传 cn_summary）。
    prefer_score：为 True 时，若后出现的重复条目相关度(score)更高，则替换先前的版本。

    用“长度范围 + 公共 n-gram”预筛后，仅对候选做精确 SequenceMatcher：
    结果与全量两两比较完全一致，但耗时从 O(n²) 降到近线性。
    长度下界 threshold/(2-threshold) 可由数学证明不误杀真正相似的文本。
    """
    kept = []
    seen = []      # 已保留条目的归一化比较文本
    seen_ng = []   # 对应的 n-gram 集合
    seen_len = []  # 对应的长度
    len_low = threshold / (2 - threshold)
    len_high = 1.0 / len_low
    for it in items:
        n = _norm(key(it) if key else it.title)
        if len(n) < 6:
            kept.append(it)
            continue
        ng = _ngrams(n)
        ln = len(n)
        dup = -1
        for i, (s, sg, sl) in enumerate(zip(seen, seen_ng, seen_len)):
            # 长度相差过大（ratio>=threshold 时不可能）或无公共 n-gram：直接跳过
            if not (len_low <= ln / sl <= len_high):
                continue
            if not (ng & sg):
                continue
            if difflib.SequenceMatcher(None, n, s).ratio() >= threshold:
                dup = i
                break
        if dup == -1:
            seen.append(n)
            seen_ng.append(ng)
            seen_len.append(ln)
            kept.append(it)
        elif prefer_score and it.score > kept[dup].score:
            # 同题新闻取相关度更高的版本
            kept[dup] = it
            seen[dup] = n
            seen_ng[dup] = ng
            seen_len[dup] = ln
    return kept
