"""加载配置与环境变量"""
import logging
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .sources import Source

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
log = logging.getLogger("news")


class Config:
    def __init__(self, path: str = ""):
        self.base_dir = BASE_DIR
        cfg_path = Path(path) if path else BASE_DIR / "config.yaml"
        with open(cfg_path, encoding="utf-8") as f:
            self.data = yaml.safe_load(f) or {}
        self.api_key = self._load_api_key()

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

        self.report = self.data.get("report", {}) or {}
        self.network = self.data.get("network", {}) or {}
        self.ai_cfg = self.data.get("ai", {}) or {}
        self.profile = self.data.get("user_profile", {}) or {}

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
