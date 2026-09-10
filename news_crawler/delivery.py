"""Idempotency state for report delivery."""
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path


def report_fingerprint(grouped, summary: str, market) -> str:
    """Hash logical report content, excluding volatile PDF metadata and time."""
    payload = {
        "summary": summary or "",
        "market": market or [],
        "categories": {
            category: [
                {
                    "title": item.display_title,
                    "original_title": item.title,
                    "summary": item.cn_summary,
                    "url": item.url,
                    "source": item.source,
                    "published": item.published.isoformat()
                    if item.published else None,
                    "score": item.score,
                }
                for item in items
            ]
            for category, items in grouped.items()
        },
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _read_state(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def already_sent(state_path: Path, date_str: str, fingerprint: str) -> bool:
    """True only when the same date and logical content were sent."""
    entry = _read_state(state_path).get(date_str) or {}
    return entry.get("content_sha256") == fingerprint


def delivered_on(state_path: Path, date_str: str) -> bool:
    """True 表示该日期已有成功发送记录（含 tools/resend.py 的手动补发）。"""
    return bool(_read_state(state_path).get(date_str))


def _write_state(state_path: Path, data: dict):
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = state_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    os.replace(tmp_path, state_path)


def mark_sent(state_path: Path, date_str: str, fingerprint: str):
    """Atomically record a successful delivery after SMTP confirms acceptance."""
    data = _read_state(state_path)
    data[date_str] = {
        "content_sha256": fingerprint,
        "sent_at": datetime.now().isoformat(timespec="seconds"),
    }
    _write_state(state_path, data)


def record_delivery(state_path: Path, date_str: str, note: str = ""):
    """记录一次"已送达"，用于没有内容指纹的场景（如手动补发）。

    看门狗与定时幂等判断只看该日期是否有记录，因此补发成功后不应再告警。
    """
    data = _read_state(state_path)
    entry = {
        "content_sha256": "manual-resend",
        "sent_at": datetime.now().isoformat(timespec="seconds"),
    }
    if note:
        entry["note"] = note
    data[date_str] = entry
    _write_state(state_path, data)
