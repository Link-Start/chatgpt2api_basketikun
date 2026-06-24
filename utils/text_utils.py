from __future__ import annotations


def clean_text(value: object, default: str = "") -> str:
    return str(value or default).strip()
