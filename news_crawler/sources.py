"""数据模型：新闻源与新闻条目"""
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Source:
    name: str
    category: str          # finance / tech / world / hot
    type: str              # rss / json
    url: str
    language: str = "zh"   # zh / en
    full_text: bool = False
    via_proxy: bool = False  # 强制走代理（如海外托管的国内源）


@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    summary: str = ""
    full_text: str = ""
    language: str = "zh"
    published: datetime | None = None
    hot_score: int = 0

    # ---- 处理后字段 ----
    cn_title: str = ""     # 英文新闻的中文译名（双语显示用）
    cn_summary: str = ""   # AI/本地生成的中文摘要
    category: str = ""     # finance / tech / world / other
    score: int = 0         # 相关度 1-5
    keep: bool = True

    @property
    def display_title(self) -> str:
        """报告主标题：中文新闻用原标题，英文新闻用中文译名（无译名则用原标题）"""
        return self.cn_title or self.title

    @property
    def en_original(self) -> str:
        """英文新闻的原标题（双语对照）"""
        if self.language == "en" and self.cn_title and self.cn_title != self.title:
            return self.title
        return ""
