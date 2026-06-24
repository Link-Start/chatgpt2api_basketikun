from __future__ import annotations

import copy
import os
import random
import time
from pathlib import Path

from dotenv import load_dotenv
import yaml

BASE_DIR = Path(__file__).resolve().parents[1]

load_dotenv(BASE_DIR / ".env", override=False)

DATA_DIR = BASE_DIR / "data"
CONFIG_FILE = BASE_DIR / "config.yaml"
VERSION_FILE = BASE_DIR / "VERSION"

DEFAULT_PROXY_RUNTIME_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/145.0.0.0 Safari/537.36"
)

CODEX_SYSTEM_CHANNEL_ID = "system"
CODEX_SYSTEM_TYPE = "system"
CODEX_TOOL_CALL_TYPE = "tool_call"
CODEX_SYSTEM_MODEL = "gpt-image-2"
CODEX_SYSTEM_MODELS = [
    CODEX_SYSTEM_MODEL,
    "codex-gpt-image-2",
    "plus-codex-gpt-image-2",
    "team-codex-gpt-image-2",
    "pro-codex-gpt-image-2",
]

DEFAULT_CONFIG = {
    "refresh_account_interval_seconds": 300,
    "image_retention_days": 30,
    "image_poll_timeout_secs": 120,
    "image_poll_interval_secs": 10.0,
    "image_poll_initial_wait_secs": 10.0,
    "image_account_concurrency": 3,
    "image_parallel_generation": True,
    "image_settle_enabled": True,
    "image_check_before_hit_enabled": True,
    "image_settle_secs": 2.0,
    "image_timeout_retry_secs": 30,
    "auto_remove_invalid_accounts": False,
    "auto_remove_rate_limited_accounts": False,
    "log_levels": [],
    "proxy": "",
    "base_url": "",
    "global_system_prompt": "",
    "ai_review": {
        "enabled": False,
        "base_url": "",
        "api_key": "",
        "model": "",
        "prompt": "",
    },
    "image_storage": {
        "enabled": False,
        "mode": "local",
        "webdav_url": "",
        "webdav_username": "",
        "webdav_password": "",
        "webdav_root_path": "chatgpt2api/images",
        "public_base_url": "",
    },
    "chat_completion_cache": {
        "enabled": True,
        "ttl_seconds": 60,
        "max_entries": 256,
        "dedupe_inflight": True,
        "stream_cache": True,
        "normalize_messages": True,
        "drop_adjacent_duplicates": True,
        "drop_assistant_history": False,
    },
    "proxy_runtime": {
        "enabled": False,
        "egress_mode": "direct",
        "proxy_url": "",
        "resource_proxy_url": "",
        "skip_ssl_verify": False,
        "reset_session_status_codes": [403],
        "clearance": {
            "enabled": False,
            "mode": "none",
            "cf_cookies": "",
            "cf_clearance": "",
            "user_agent": DEFAULT_PROXY_RUNTIME_USER_AGENT,
            "browser": "chrome",
            "flaresolverr_url": "",
            "timeout_sec": 60,
            "refresh_interval": 3600,
            "warm_up_on_start": False,
        },
    },
    "infinite_canvas": {
        "enabled": False,
        "url": "https://canvas.best",
    },
    "codex_channels": {
        "channels": [
            {
                "id": CODEX_SYSTEM_CHANNEL_ID,
                "type": CODEX_SYSTEM_TYPE,
                "enabled": True,
                "name": "系统渠道",
                "weight": 1,
            },
        ],
    },
}


def _merge_config(default: dict[str, object], data: dict[str, object]) -> dict[str, object]:
    merged = copy.deepcopy(default)
    for key, value in data.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_config(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_yaml_object(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _write_yaml_object(path: Path, data: dict[str, object]) -> None:
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _auth_key(value: object) -> str:
    return str(value or "").strip()


def _validate_image_storage_settings(settings: dict[str, object]) -> None:
    if not settings["enabled"]:
        return
    if not str(settings["webdav_url"]).strip():
        raise ValueError("启用 WebDAV 图片存储后必须填写 WebDAV URL")
    if not str(settings["webdav_password"]).strip():
        raise ValueError("启用 WebDAV 图片存储后必须填写 WebDAV 密码")


class ConfigStore:
    def __init__(self, path: Path):
        self.path = path
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.data = self._load()
        if not self.auth_key:
            raise ValueError(
                "❌ auth-key 未设置！\n"
                "请在环境变量 CHATGPT2API_AUTH_KEY 中设置管理员密钥。"
            )

    def _load(self) -> dict[str, object]:
        return _merge_config(DEFAULT_CONFIG, _read_yaml_object(self.path))

    def _save(self) -> None:
        _write_yaml_object(self.path, self.data)

    @property
    def auth_key(self) -> str:
        return _auth_key(os.getenv("CHATGPT2API_AUTH_KEY"))

    @property
    def accounts_file(self) -> Path:
        return DATA_DIR / "accounts.json"

    @property
    def refresh_account_interval_seconds(self) -> int:
        return int(self.data["refresh_account_interval_seconds"])

    @property
    def image_retention_days(self) -> int:
        return int(self.data["image_retention_days"])

    @property
    def image_poll_timeout_secs(self) -> int:
        return int(self.data["image_poll_timeout_secs"])

    @property
    def image_poll_interval_secs(self) -> float:
        return float(self.data["image_poll_interval_secs"])

    @property
    def image_poll_initial_wait_secs(self) -> float:
        return float(self.data["image_poll_initial_wait_secs"])

    @property
    def image_account_concurrency(self) -> int:
        return int(self.data["image_account_concurrency"])

    @property
    def image_parallel_generation(self) -> bool:
        return bool(self.data["image_parallel_generation"])

    @property
    def image_settle_enabled(self) -> bool:
        return bool(self.data["image_settle_enabled"])

    @property
    def image_check_before_hit_enabled(self) -> bool:
        return bool(self.data["image_check_before_hit_enabled"])

    @property
    def image_settle_secs(self) -> float:
        return float(self.data["image_settle_secs"])

    @property
    def auto_remove_invalid_accounts(self) -> bool:
        return bool(self.data["auto_remove_invalid_accounts"])

    @property
    def auto_remove_rate_limited_accounts(self) -> bool:
        return bool(self.data["auto_remove_rate_limited_accounts"])

    @property
    def log_levels(self) -> list[str]:
        return self.data["log_levels"]

    @property
    def ai_review(self) -> dict[str, object]:
        return self.data["ai_review"]

    @property
    def global_system_prompt(self) -> str:
        return str(self.data["global_system_prompt"]).strip()

    @property
    def images_dir(self) -> Path:
        path = DATA_DIR / "images"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def cleanup_old_images(self) -> int:
        cutoff = time.time() - self.image_retention_days * 86400
        removed = 0
        for path in self.images_dir.rglob("*"):
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        for path in sorted((p for p in self.images_dir.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
            try:
                path.rmdir()
            except OSError:
                pass
        return removed

    @property
    def base_url(self) -> str:
        return str(self.data["base_url"]).strip().rstrip("/")

    @property
    def app_version(self) -> str:
        return VERSION_FILE.read_text(encoding="utf-8").strip()

    def get(self) -> dict[str, object]:
        data = copy.deepcopy(self.data)
        data["proxy_runtime"] = self.get_public_proxy_runtime_settings()
        return data

    def get_proxy_settings(self) -> str:
        return str(self.data["proxy"]).strip()

    @property
    def proxy_url(self) -> str:
        return self.get_proxy_settings()

    def get_proxy_runtime_settings(self) -> dict[str, object]:
        return self.data["proxy_runtime"]

    def get_public_proxy_runtime_settings(self) -> dict[str, object]:
        runtime = copy.deepcopy(self.get_proxy_runtime_settings())
        clearance = runtime["clearance"]
        cf_cookies = str(clearance["cf_cookies"]).strip()
        cf_clearance = str(clearance["cf_clearance"]).strip()
        clearance["cf_cookies"] = ""
        clearance["cf_clearance"] = ""
        clearance["has_cf_cookies"] = bool(cf_cookies)
        clearance["has_cf_clearance"] = bool(cf_clearance)
        return runtime

    def get_infinite_canvas_settings(self) -> dict[str, object]:
        return self.data["infinite_canvas"]

    def get_codex_channels_settings(self) -> dict[str, object]:
        return self.data["codex_channels"]

    def list_enabled_codex_channels(self) -> list[dict[str, object]]:
        channels = self.data["codex_channels"]["channels"]
        result = []
        for channel in channels:
            item = dict(channel)
            item["type"] = item.get("type") or (
                CODEX_SYSTEM_TYPE
                if item.get("id") == CODEX_SYSTEM_CHANNEL_ID
                else CODEX_TOOL_CALL_TYPE
            )
            if item["type"] == CODEX_SYSTEM_TYPE:
                item["mapped_models"] = CODEX_SYSTEM_MODELS
            is_system = item["type"] == CODEX_SYSTEM_TYPE
            has_base_url = str(item.get("base_url") or "").strip()
            has_api_key = str(item.get("api_key") or "").strip()
            has_upstream = has_base_url and has_api_key
            if (
                item.get("enabled")
                and int(item.get("weight") or 0) > 0
                and item.get("mapped_models")
                and (is_system or has_upstream)
            ):
                result.append(item)
        return result

    def list_codex_channels_for_model(self, model: object) -> list[dict[str, object]]:
        normalized = str(model or "").strip().lower()
        return [
            channel
            for channel in self.list_enabled_codex_channels()
            if normalized in {str(item or "").strip().lower() for item in channel["mapped_models"]}
        ]

    def get_codex_channel_for_model(self, model: object) -> dict[str, object] | None:
        channels = self.list_codex_channels_for_model(model)
        if not channels:
            return None
        return random.choices(channels, weights=[int(channel["weight"]) for channel in channels], k=1)[0]

    def update(self, data: dict[str, object]) -> dict[str, object]:
        next_data = _merge_config(self.data, data)
        if "proxy_runtime" in data:
            self._preserve_clearance_secrets(next_data["proxy_runtime"])
        _validate_image_storage_settings(next_data["image_storage"])
        self.data = _merge_config(DEFAULT_CONFIG, next_data)
        self._save()
        return self.get()

    def _preserve_clearance_secrets(self, runtime: dict[str, object]) -> None:
        clearance = runtime["clearance"]
        previous_clearance = self.get_proxy_runtime_settings()["clearance"]
        if not str(clearance["cf_cookies"]).strip() and clearance.pop("has_cf_cookies", False):
            clearance["cf_cookies"] = previous_clearance["cf_cookies"]
        if not str(clearance["cf_clearance"]).strip() and clearance.pop("has_cf_clearance", False):
            clearance["cf_clearance"] = previous_clearance["cf_clearance"]

    def get_image_storage_settings(self) -> dict[str, object]:
        return self.data["image_storage"]

    def get_chat_completion_cache_settings(self) -> dict[str, object]:
        return self.data["chat_completion_cache"]


config = ConfigStore(CONFIG_FILE)
