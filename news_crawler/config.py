"""加载配置与环境变量"""
import logging
import os
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlparse

import yaml
from dotenv import load_dotenv

from .sources import Source

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
log = logging.getLogger("news")


class ConfigError(ValueError):
    """Raised when configuration cannot be used safely."""


class Config:
    def __init__(self, path: str = ""):
        self.base_dir = BASE_DIR
        cfg_path = Path(path) if path else BASE_DIR / "config.yaml"
        with open(cfg_path, encoding="utf-8") as f:
            self.data = yaml.safe_load(f) or {}
        if not isinstance(self.data, Mapping):
            raise ConfigError("配置文件根节点必须是 YAML 对象")
        self.report = self.data.get("report", {}) or {}
        self.network = self.data.get("network", {}) or {}
        self.ai_cfg = self.data.get("ai", {}) or {}
        self.profile = self.data.get("user_profile", {}) or {}
        self.email = self.data.get("email", {}) or {}
        self.schedule = self.data.get("schedule", {}) or {}
        self._validate()
        self.api_key = self._load_api_key()

    def _validate(self):
        """Fail early for values that would otherwise break a scheduled run."""
        sections = {
            "report": self.report, "network": self.network,
            "ai": self.ai_cfg, "email": self.email, "schedule": self.schedule,
            "user_profile": self.profile,
        }
        for name, value in sections.items():
            if not isinstance(value, Mapping):
                raise ConfigError(f"{name} 必须是 YAML 对象")

        def non_negative(section, key, default=0):
            value = sections[section].get(key, default)
            try:
                if int(value) < 0:
                    raise ValueError
            except (TypeError, ValueError) as exc:
                raise ConfigError(f"{section}.{key} 必须是非负整数") from exc

        def positive(section, key, default=1):
            value = sections[section].get(key, default)
            try:
                if int(value) <= 0:
                    raise ValueError
            except (TypeError, ValueError) as exc:
                raise ConfigError(f"{section}.{key} 必须是正整数") from exc

        for key in ("hours_back", "keep_days", "fulltext_cap",
                    "max_items_per_source"):
            non_negative("report", key)
        positive("network", "request_timeout", 15)
        non_negative("network", "retries")
        positive("ai", "timeout", 120)
        non_negative("ai", "max_retries")
        for key in ("batch_size", "concurrency"):
            positive("ai", key)
        pdf_cfg = self.report.get("pdf", {}) or {}
        if not isinstance(pdf_cfg, Mapping):
            raise ConfigError("report.pdf 必须是 YAML 对象")
        categories = self.report.get("categories", {}) or {}
        if not isinstance(categories, Mapping):
            raise ConfigError("report.categories 必须是 YAML 对象")
        for name, category in categories.items():
            if not isinstance(category, Mapping):
                raise ConfigError(f"report.categories.{name} 必须是 YAML 对象")
            try:
                if int(category.get("max_items", 10)) < 0:
                    raise ValueError
            except (TypeError, ValueError) as exc:
                raise ConfigError(
                    f"report.categories.{name}.max_items 必须是非负整数") from exc

        sources = self.data.get("sources", []) or []
        if not isinstance(sources, list):
            raise ConfigError("sources 必须是 YAML 列表")
        for i, source in enumerate(sources, 1):
            if not isinstance(source, Mapping):
                raise ConfigError(f"sources[{i}] 必须是 YAML 对象")
            url = str(source.get("url") or "")
            if urlparse(url).scheme not in {"http", "https"}:
                raise ConfigError(f"sources[{i}].url 必须是 HTTP(S) 地址")
            if source.get("type") not in {"rss", "json"}:
                raise ConfigError(f"sources[{i}].type 仅支持 rss 或 json")

    def _load_api_key(self) -> str:
        """优先解密 .env 中的加密 Key（Windows DPAPI，绑定当前用户）；兼容旧明文"""
        import base64
        enc = os.getenv("DEEPSEEK_API_KEY_ENC", "").strip()
        if enc:
            try:
                from .secure import unprotect
                return unprotect(base64.b64decode(enc)).decode("utf-8").strip()
            except Exception as e:  # noqa: BLE001
                log.warning("解密 API Key 失败（回退明文）: %s", e)
        return os.getenv("DEEPSEEK_API_KEY", "").strip()

    @property
    def smtp_password(self) -> str:
        """QQ 邮箱 SMTP 授权码：优先解密 .env 中加密的 QQ_SMTP_AUTH_ENC；兼容旧明文"""
        import base64
        enc = os.getenv("QQ_SMTP_AUTH_ENC", "").strip()
        if enc:
            try:
                from .secure import unprotect
                return unprotect(base64.b64decode(enc)).decode("utf-8").strip()
            except Exception as e:  # noqa: BLE001
                log.warning("解密 QQ SMTP 授权码失败（回退明文）: %s", e)
        return os.getenv("QQ_SMTP_AUTH", "").strip()

    @property
    def email_from(self) -> str:
        """发件邮箱：优先 .env 的 SMTP_FROM_ADDR（避免公开仓库泄露），兼容旧 config.yaml"""
        return (os.getenv("SMTP_FROM_ADDR", "").strip()
                or str(self.email.get("from_addr") or "").strip())

    @property
    def email_to(self) -> list:
        """收件邮箱列表：优先 .env 的 SMTP_TO_ADDRS（英文逗号分隔），兼容旧 config.yaml"""
        v = os.getenv("SMTP_TO_ADDRS", "").strip()
        if v:
            return [x.strip() for x in v.split(",") if x.strip()]
        cfg = self.email.get("to_addrs") or []
        if isinstance(cfg, str):
            return [x.strip() for x in cfg.split(",") if x.strip()]
        return [str(x).strip() for x in cfg if str(x).strip()]

    @property
    def ai_enabled(self) -> bool:
        return bool(self.ai_cfg.get("enabled", True)) and bool(self.api_key)

    @property
    def sources(self):
        """解析新闻源；单个源配置有误时跳过而不是让整个程序崩溃"""
        srcs = []
        for s in self.data.get("sources", []) or []:
            if not isinstance(s, dict):
                continue
            # 只取数据模型认识的字段，避免多余/拼错字段导致报错
            s = {k: v for k, v in s.items()
                 if k in Source.__dataclass_fields__}
            try:
                srcs.append(Source(**s))
            except (TypeError, ValueError) as e:
                log.warning("跳过配置错误的新闻源 %s: %s", s.get("name"), e)
        return srcs

    @property
    def categories(self) -> dict:
        return self.report.get("categories", {}) or {}

    @property
    def proxy_dict(self):
        p = (self.network.get("proxy") or "").strip()
        if not p:
            return None
        return {"http": p, "https": p}

    def get_report(self, key, default=None):
        return self.report.get(key, default)
