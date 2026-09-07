"""本地关键词分类（AI 不可用时的兜底 + 预分类）"""

FIN = ["A股", "港股", "美股", "大盘", "上证", "深证", "创业板", "涨停", "跌停",
       "央行", "降息", "加息", "美联储", "GDP", "CPI", "通胀", "通缩", "财政",
       "货币政策", "汇率", "关税", "贸易战", "北向资金", "外资", "股价", "市值",
       "财报", "业绩", "分红", "回购", "基金", "券商", "行情", "IPO", "国债",
       "债券", "黄金", "原油", "大宗商品", "人民币", "美元", "指数", "A股市场"]

TECH = ["半导体", "芯片", "AI", "人工智能", "大模型", "智能体", "机器人", "光电",
        "激光", "显示", "OLED", "面板", "光子", "算力", "GPU", "CPU", "消费电子",
        "光刻", "制程", "纳米", "华为", "苹果", "英伟达", "特斯拉", "自动驾驶",
        "新能源车", "云计算", "数据中心", "开源", "GPT", "DeepSeek", "机器学习",
        "算法", "传感器", "摄像头", "VR", "AR", "5G", "6G", "通信", "操作系统",
        "晶圆", "刻蚀", "光刻机", "量子", "卫星", "航天"]

WORLD = ["美国", "白宫", "俄罗斯", "乌克兰", "欧盟", "北约", "英国", "法国",
         "德国", "日本", "韩国", "印度", "以色列", "伊朗", "巴勒斯坦", "中东",
         "特朗普", "拜登", "普京", "习近平", "外交", "制裁", "冲突", "战争",
         "峰会", "G7", "G20", "联合国", "地缘", "停火", "选举", "国会", "贸易",
         "世贸", "WTO", "北约峰会"]

SCIENCE = ["研究", "论文", "科学家", "实验", "发现", "观测", "临床试验", "基因",
           "生物", "医学", "物理", "化学", "材料", "天文", "气候", "能源研究",
           "Nature", "Science", "NASA", "JPL", "大学", "研究所", "科研",
           "research", "scientist", "experiment", "physics", "biology",
           "climate", "astronomy", "materials"]

FOCUS = ["半导体", "芯片", "AI", "算力", "新能源", "锂电", "军工", "光电",
         "显示", "光学", "高端制造", "大模型", "机器人"]


def _score(text: str, words) -> int:
    if not text:
        return 0
    normalized = text.casefold()
    return sum(normalized.count(str(w).casefold()) for w in words)


def classify_item(item, profile=None) -> str:
    """本地分类并计算相关度得分。"""
    text = f"{item.title} {item.summary}"
    fin = _score(text, FIN)
    tech = _score(text, TECH)
    science = _score(text, SCIENCE)
    world = _score(text, WORLD)
    if fin == tech == science == world == 0:
        item.category = "other"
    else:
        item.category = max(
            (("finance", fin), ("tech", tech), ("science", science),
             ("world", world)),
            key=lambda x: x[1],
        )[0]
    # 相关度（1-5）：命中关注领域关键词即加分
    item.score = min(5, 1 + sum(text.count(w) for w in FOCUS))
    return item.category
