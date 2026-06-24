from __future__ import annotations

from datetime import datetime, timezone


def utc_now_text() -> str:
    """返回当前 UTC 时间字符串。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def parse_time(value: object) -> datetime | None:
    """解析常见时间字符串为 UTC datetime。"""
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        try:
            parsed = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
