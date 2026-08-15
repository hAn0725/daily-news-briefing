"""DeepSeek AI 处理：批量摘要/翻译/分类/过滤 + 今日综述，失败自动回退"""
import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from . import nlp_local
from .classify import classify_item

log = logging.getLogger("news")

CATS = ("finance", "tech", "world")


class AIProcessor:
    def __init__(self, config):
        self.base = (config.ai_cfg.get("base_url", "https://api.deepseek.com")
                     .rstrip("/"))
        self.model = config.ai_cfg.get("model", "deepseek-v4-flash")
        self.key = config.api_key
        self.timeout = int(config.ai_cfg.get("timeout", 120))
        self.retries = int(config.ai_cfg.get("max_retries", 3))
        self.batch = int(config.ai_cfg.get("batch_size", 15))
        self.concurrent = max(1, int(config.ai_cfg.get("concurrency", 4)))
        self.thinking = (config.ai_cfg.get("thinking") or "").strip()
        self.profile = config.profile
        self.pricing = config.ai_cfg.get("pricing", {}) or {}
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0,
                      "total_tokens": 0}
        self._usage_lock = threading.Lock()
        self.headers = {
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }

    # ---------------- 底层调用 ----------------
    def _chat(self, system: str, user: str) -> dict:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.3,
            "max_tokens": 8192,  # 预留充足输出空间，避免大批量响应被截断
            "response_format": {"type": "json_object"},
        }
        if self.thinking:
            payload["thinking"] = {"type": self.thinking}
        last = None
        for _ in range(self.retries):
            try:
                r = requests.post(f"{self.base}/chat/completions",
                                  headers=self.headers, json=payload,
                                  timeout=self.timeout)
                r.raise_for_status()
                data = r.json()
                content = data["choices"][0]["message"]["content"]
                u = data.get("usage") or {}
                with self._usage_lock:
                    self.usage["prompt_tokens"] += int(u.get("prompt_tokens", 0))
                    self.usage["completion_tokens"] += int(
                        u.get("completion_tokens", 0))
                    self.usage["total_tokens"] += int(u.get("total_tokens", 0))
                return self._parse_json(content)
            except Exception as e:  # noqa: BLE001
                last = e
                time.sleep(2)  # 重试前短暂退避，缓解瞬时限流
        raise RuntimeError(f"AI 调用失败: {last}")

    def get_usage(self) -> dict:
        """返回累计 token 用量（输入/输出/总计）"""
        return dict(self.usage)

    def estimate_cost(self) -> float:
        """按配置单价估算本次费用（元）"""
        in_price = float(self.pricing.get("input_per_million", 1.0))
        out_price = float(self.pricing.get("output_per_million", 2.0))
        cost = (self.usage["prompt_tokens"] / 1_000_000 * in_price +
                self.usage["completion_tokens"] / 1_000_000 * out_price)
        return round(cost, 4)

    @staticmethod
    def _parse_json(content: str) -> dict:
        content = content.strip()
        m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", content, re.S)
        if m:
            content = m.group(1)
        s, e = content.find("{"), content.rfind("}")
        if s == -1 or e == -1:
            raise ValueError("AI 响应不是 JSON")
        return json.loads(content[s:e + 1])

    # ---------------- Prompt 构建 ----------------
    def _system_prompt(self) -> str:
        bg = self.profile.get("background", "")
        focus = "、".join(self.profile.get("focus_areas", []) or [])
        prio = "、".join(self.profile.get("priorities", []) or [])
        style = self.profile.get("summary_style", "客观简报")
        lv = self.profile.get("language_level", "通俗易懂")
        summary_chars = int(self.profile.get("item_summary_chars", 170))
        return (
            "你是一名专业的新闻编辑助手，为一位用户制作每日新闻简报。\n"
            f"用户背景：{bg}\n"
            f"重点关注领域：{focus}\n"
            f"优先级：{prio}\n"
            "处理要求：\n"
            "1. 剔除娱乐八卦、明星绯闻、社会猎奇、软文广告、标题党、低质量或与用户需求无关的内容。\n"
            "2. 优先保留与用户关注领域相关、或具有重要性的新闻。\n"
            f"3. 每条用中文写 6-8 句、约 {summary_chars} 字的摘要，信息充分时不要低于 150 字（信息充实，尽量保留具体数字/人名/时间/机构等细节；原文信息有限时写到信息允许的程度即可，切勿编造原文没有的事实），风格：{style}，语言{lv}。\n"
            "4. 若原新闻为英文，须提供中文译名 cn_title；中文新闻 cn_title 留空。\n"
            "5. 分类：finance=财经与股市, tech=科技前沿, world=国际大事, other=其他。\n"
            "6. 相关度评分 score 用 1-5 的整数，5 为最相关/最重要。\n"
            '只输出 JSON，格式：{"items":[{"index":0,"keep":true,"cn_title":"...","cn_summary":"...","category":"finance","score":4}]}'
        )

    # ---------------- 批量处理 ----------------
    def process_items(self, items):
        """逐批处理，返回处理后的条目（keep=False 的条目仍在列表中，但被标记剔除）"""
        # 本地预分类（作为 AI 未返回分类时的兜底）
        for it in items:
            classify_item(it, self.profile)

        batches = [items[i:i + self.batch] for i in range(0, len(items), self.batch)]
        results = {}
        lock = threading.Lock()

        def _run_batch(bi, batch):
            """处理单批；各批独立并发，失败仅该批回退本地，不影响整体质量"""
            local = []
            payload = [
                {
                    "index": i,
                    "title": it.title,
                    "summary": (it.summary or "")[:600],
                    "full_text": (it.full_text or "")[:400],
                    "source": it.source,
                    "language": it.language,
                }
                for i, it in enumerate(batch)
            ]
            try:
                data = self._chat(self._system_prompt(),
                                  json.dumps(payload, ensure_ascii=False))
                res_map = {int(r.get("index", -1)): r
                           for r in data.get("items", [])}
                for i, it in enumerate(batch):
                    r = res_map.get(i, {})
                    if r.get("keep", True) is False:
                        it.keep = False
                        continue
                    it.keep = True
                    cn_title = (r.get("cn_title") or "").strip()
                    if it.language == "en":
                        it.cn_title = cn_title or it.title
                    else:
                        it.cn_title = cn_title
                    it.cn_summary = (r.get("cn_summary") or "").strip() or \
                        nlp_local.summarize(it.summary or it.full_text)
                    cat = (r.get("category") or "").strip().lower()
                    it.category = cat if cat in CATS else "other"
                    try:
                        it.score = min(5, max(0, int(r.get("score") or 0)))
                    except (TypeError, ValueError):
                        it.score = 0
                    local.append(it)
            except Exception as e:  # noqa: BLE001
                log.warning("第 %d 批 AI 处理失败，本地兜底: %s", bi + 1, e)
                for it in batch:
                    it.keep = True
                    it.category = it.category or "other"
                    it.cn_summary = it.cn_summary or \
                        nlp_local.summarize(it.summary or it.full_text)
                    local.append(it)
            with lock:
                results[bi] = local

        # 并发处理各批（DeepSeek 支持并发请求；结果按批次顺序合并，内容与串行完全一致）
        with ThreadPoolExecutor(max_workers=self.concurrent) as ex:
            list(ex.map(lambda t: _run_batch(t[0], t[1]), enumerate(batches)))

        processed = []
        for bi in range(len(batches)):
            processed.extend(results[bi])
        log.info("AI 处理完成，保留 %d / %d", len(processed), len(items))
        return processed

    # ---------------- 跨源去重 ----------------
    def find_duplicates(self, items):
        """用 AI 识别“报道同一事件/主题”的重复条目，返回分组（每组为 items 下标列表）"""
        if len(items) < 2:
            return []
        brief = [
            {"index": i, "title": it.cn_title or it.title,
             "summary": (it.cn_summary or "")[:200]}
            for i, it in enumerate(items)
        ]
        system = (
            "你是新闻去重助手。给定一批新闻（含标题与中文摘要），找出“报道同一事件/主题”的条目并分成组。\n"
            "判定为重复的典型情况（不同媒体/角度/措辞都算）：\n"
            "- 同一家公司/机构发布的同一件事：同一份财报、同一产品发布会、同一笔并购/融资、同一次上市，即使角度不同（如一篇讲财报数据、一篇讲战略、一篇讲股价反应）也算重复，应合并为一组\n"
            "- 同一场事件：同一次袭击、同一条政策、同一个选举结果、同一次事故、同一条地缘冲突\n"
            "不算重复：同一主题但对象/事件不同（如两家不同公司的各自财报、两次不同地区的袭击）。\n"
            "只输出 JSON：{\"groups\":[[0,5],[1,3,7]]}，index 为输入中的序号；无重复则输出 {\"groups\":[]}。"
        )
        try:
            data = self._chat(system, json.dumps(brief, ensure_ascii=False))
        except Exception as e:  # noqa: BLE001
            log.warning("AI 去重调用失败（跳过去重）: %s", e)
            return []
        groups = []
        for g in data.get("groups") or []:
            ids = []
            for x in g:
                try:
                    ix = int(x)
                except (TypeError, ValueError):
                    continue
                if 0 <= ix < len(items):
                    ids.append(ix)
            if len(ids) >= 2:
                groups.append(ids)
        return groups

    # ---------------- 今日综述 ----------------
    def generate_summary(self, items) -> str:
        if not items:
            return "今日暂无重大新闻。"
        brief = []
        for it in items[:25]:
            t = it.cn_title or it.title
            brief.append(f"- [{t}] {it.cn_summary or ''}".strip())
        system = (
            f"你是一名新闻编辑。请根据下面的新闻，用中文写一段约 "
            f"{self.profile.get('summary_length', 200)} 字的"
            "“今日要闻综述”，客观简报风格，只陈述事实、不发表评论，"
            "按重要性组织内容。\n只输出 JSON：{\"summary\":\"...\"}"
        )
        try:
            data = self._chat(system, "\n".join(brief))
            return (data.get("summary") or "").strip()
        except Exception as e:  # noqa: BLE001
            log.warning("综述生成失败: %s", e)
            return "今日新闻较多，详见各分类。"
