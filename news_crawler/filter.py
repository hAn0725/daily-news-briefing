"""本地排除过滤：娱乐八卦/社会猎奇/软文广告/标题党"""
EXCLUDE_DEFAULT = [
    "八卦", "绯闻", "恋情", "出轨", "塌房", "离婚", "灵异", "奇闻", "猎奇",
    "秒杀", "促销", "优惠券", "抽奖", "爆款", "种草", "安利", "明星同款",
    "限时抢购", "免费领取",
]


def is_excluded(item, extra_words=None) -> bool:
    text = f"{item.title} {item.summary}".lower()
    words = list(EXCLUDE_DEFAULT)
    if extra_words:
        words += [w for w in extra_words if w]
    for w in words:
        if w and w.lower() in text:
            return True
    return False


def filter_items(items, config):
    extra = config.profile.get("exclude_keywords", []) or []
    return [it for it in items if not is_excluded(it, extra)]
