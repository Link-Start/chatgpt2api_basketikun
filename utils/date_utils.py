from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """返回当前 UTC datetime。"""
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """返回当前 UTC ISO 时间字符串。"""
    return utc_now().isoformat()


def utc_now_text() -> str:
    """返回当前 UTC 时间字符串。"""
    return utc_now().strftime("%Y-%m-%d %H:%M:%S")


def local_now_text() -> str:
    """返回当前本地时间字符串。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def local_timestamp_text(timestamp: float) -> str:
    """把本地时间戳格式化为字符串。"""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def local_timestamp_date(timestamp: float) -> str:
    """把本地时间戳格式化为日期字符串。"""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")


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
