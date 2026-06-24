from __future__ import annotations

from typing import Any

from services.account.account_service import account_service
from services.config import CODEX_SYSTEM_TYPE, config
from services.protocol.openai_backend_api import OpenAIBackendAPI
from utils.helper import CODEX_IMAGE_MODEL


def _model_item(model: str, owned_by: str = "chatgpt2api") -> dict[str, Any]:
    return {
        "id": model,
        "object": "model",
        "created": 0,
        "owned_by": owned_by,
        "permission": [],
        "root": model,
        "parent": None,
    }


def _dynamic_image_models() -> list[str]:
    dynamic_models: set[str] = set()
    accounts = account_service.list_accounts()
    channels = config.list_enabled_codex_channels()
    system_models = {
        str(model or "").strip()
        for channel in channels
        if channel.get("type") == CODEX_SYSTEM_TYPE
        for model in channel.get("mapped_models", [])
        if str(model or "").strip()
    }
    web_image_accounts = [
        account
        for account in accounts
        if isinstance(account, dict)
           and account.get("source_type") != "codex"
    ]
    codex_types = {
        normalized
        for account in accounts
        if isinstance(account, dict)
           and account.get("source_type") == "codex"
           and (normalized := account_service._normalize_account_type(account.get("type")))
    }

    if web_image_accounts and "gpt-image-2" in system_models:
        dynamic_models.add("gpt-image-2")
    if codex_types & {"Plus", "Team", "Pro"} and CODEX_IMAGE_MODEL in system_models:
        dynamic_models.add(CODEX_IMAGE_MODEL)
    if "Plus" in codex_types and f"plus-{CODEX_IMAGE_MODEL}" in system_models:
        dynamic_models.add(f"plus-{CODEX_IMAGE_MODEL}")
    if "Team" in codex_types and f"team-{CODEX_IMAGE_MODEL}" in system_models:
        dynamic_models.add(f"team-{CODEX_IMAGE_MODEL}")
    if "Pro" in codex_types and f"pro-{CODEX_IMAGE_MODEL}" in system_models:
        dynamic_models.add(f"pro-{CODEX_IMAGE_MODEL}")
    for channel in channels:
        if channel.get("type") == CODEX_SYSTEM_TYPE:
            continue
        for model in channel.get("mapped_models", []):
            mapped_model = str(model or "").strip()
            if mapped_model:
                dynamic_models.add(mapped_model)
    return sorted(dynamic_models)


def list_image_models() -> dict[str, Any]:
    data = [_model_item(model) for model in _dynamic_image_models()]
    if not data:
        data = [_model_item("gpt-image-2")]
    return {"object": "list", "data": data}


def list_models() -> dict[str, Any]:
    result = OpenAIBackendAPI().list_models()
    data = result.get("data")
    if not isinstance(data, list):
        return result
    seen = {str(item.get("id") or "").strip() for item in data if isinstance(item, dict)}
    for model in _dynamic_image_models():
        if model not in seen:
            data.append(_model_item(model))
    return result
