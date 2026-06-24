from __future__ import annotations

import uuid


def short_id(length: int = 12) -> str:
    return uuid.uuid4().hex[:length]


def hex_id() -> str:
    return uuid.uuid4().hex
