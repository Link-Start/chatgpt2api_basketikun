from __future__ import annotations

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Condition, Lock
from typing import Any

from services.config import DATA_DIR, config
from services.log_service import (
    LOG_TYPE_ACCOUNT,
    log_service,
)
from utils.date_utils import parse_time, utc_now_text
from utils.helper import anonymize_token


class AccountService:
    """账号池服务，使用 token -> account 的 dict 保存账号。"""

    _ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 24 * 60 * 60  # access_token 剩余不足 24 小时时提前刷新
    _REFRESH_TOKEN_KEEPALIVE_SECONDS = 3 * 24 * 60 * 60  # refresh_token 每 3 天保活一次
    _REFRESH_TOKEN_KEEPALIVE_ERROR_BACKOFF_SECONDS = 6 * 60 * 60  # 保活失败后 6 小时内不重试
    _REFRESH_TOKEN_KEEPALIVE_BATCH_SIZE = 3  # watcher 每轮最多保活的 refresh_token 数
    _ACCOUNT_REFRESH_BATCH_SIZE = 1  # watcher 每轮每类状态最多刷新 1 个账号
    _TOKEN_REFRESH_ERROR_BACKOFF_SECONDS = 5 * 60  # access_token 刷新失败后 5 分钟内不重试
    _OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"  # OpenAI OAuth token endpoint
    _OAUTH_CLIENT_ID = "app_2SKx67EdpoN0G6j64rFvigXD"  # ChatGPT Web OAuth client id
    _OAUTH_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/145.0.0.0 Safari/537.36"
    )

    def __init__(self, accounts_file: Path | None = None):
        """初始化账号存储、索引和运行时并发状态。"""
        self.accounts_file = accounts_file or DATA_DIR / "accounts.json"
        self.accounts_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._token_refresh_lock = Lock()
        self._image_slot_condition = Condition(self._lock)
        self._index = 0
        self._accounts = self._load_accounts()
        self._image_inflight: dict[str, int] = {}
        self._token_aliases: dict[str, str] = {}
        self._refreshing_tokens: set[str] = set()

    @staticmethod
    def _decode_jwt_payload(token: str) -> dict:
        """解码 JWT payload，失败时返回空字典。"""
        try:
            payload = str(token or "").split(".")[1]
            payload += "=" * ((4 - len(payload) % 4) % 4)
            import base64
            import json
            data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _load_accounts(self) -> dict[str, dict]:
        """从账号文件加载并按 access_token 建索引。"""
        if not self.accounts_file.exists():
            accounts = []
        else:
            try:
                raw = json.loads(self.accounts_file.read_text(encoding="utf-8"))
                accounts = raw if isinstance(raw, list) else []
            except Exception:
                accounts = []
        return {
            normalized["access_token"]: normalized
            for item in accounts
            if (normalized := self._normalize_account(item)) is not None
        }

    def _save_accounts(self) -> None:
        """把账号索引写回账号文件。"""
        self.accounts_file.write_text(
            json.dumps(list(self._accounts.values()), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _is_image_account_available(account: dict) -> bool:
        """判断账号是否可参与图片任务调度。"""
        if not isinstance(account, dict):
            return False
        if account.get("status") in {"禁用", "限流", "异常"}:
            return False
        if bool(account.get("image_quota_unknown")):
            return True
        return int(account.get("quota") or 0) > 0

    @classmethod
    def _account_matches_plan_type(cls, account: dict, plan_type: str | None = None) -> bool:
        """判断账号套餐类型是否匹配指定套餐。"""
        if not plan_type:
            return True
        normalized_plan = cls._normalize_account_type(plan_type)
        normalized_account = cls._normalize_account_type(account.get("type"))
        if not normalized_plan or not normalized_account:
            return False
        return normalized_plan.lower() == normalized_account.lower()

    @classmethod
    def _account_matches_source_type(cls, account: dict, source_type: str | None = None) -> bool:
        """判断账号来源是否匹配指定来源。"""
        if not source_type:
            return True
        return cls._normalize_source_type(account.get("source_type")) == cls._normalize_source_type(source_type)

    @classmethod
    def _account_matches_any_plan_type(cls, account: dict,
                                       plan_types: set[str] | tuple[str, ...] | None = None) -> bool:
        """判断账号套餐是否命中任一目标套餐。"""
        if not plan_types:
            return True
        normalized_account = cls._normalize_account_type(account.get("type"))
        normalized_plans = {
            normalized
            for plan_type in plan_types
            if (normalized := cls._normalize_account_type(plan_type))
        }
        return bool(normalized_account and normalized_account in normalized_plans)

    @staticmethod
    def _normalize_source_type(value: object) -> str:
        """标准化账号来源字段。"""
        return str(value or "web").strip().lower() or "web"

    @staticmethod
    def _normalize_account_type(value: object) -> str | None:
        """标准化账号套餐名称。"""
        raw = str(value or "").strip()
        if not raw:
            return None
        key = raw.lower().replace("-", "_").replace(" ", "_")
        compact = key.replace("_", "")
        aliases = {
            "free": "free",
            "plus": "Plus",
            "pro": "Pro",
            "prolite": "ProLite",
            "team": "Team",
            "business": "Team",
            "enterprise": "Enterprise",
        }
        return aliases.get(compact) or aliases.get(key) or raw

    def _normalize_account(self, item: dict) -> dict | None:
        """把输入账号数据整理成内部统一结构。"""
        if not isinstance(item, dict):
            return None
        access_token = item.get("access_token") or item.get("accessToken") or ""
        if not access_token:
            return None
        normalized = dict(item)
        normalized.pop("accessToken", None)
        normalized["access_token"] = access_token
        if str(normalized.get("type") or "").strip().lower() == "codex":
            normalized["export_type"] = "codex"
            normalized.pop("type", None)
        normalized["type"] = normalized.get("type") or "free"
        normalized["status"] = normalized.get("status") or "正常"
        normalized["quota"] = max(0, int(normalized.get("quota") if normalized.get("quota") is not None else 0))
        normalized["image_quota_unknown"] = bool(normalized.get("image_quota_unknown"))
        normalized["email"] = normalized.get("email") or None
        normalized["user_id"] = normalized.get("user_id") or None
        normalized["proxy"] = str(normalized.get("proxy") or "").strip()
        source_type = normalized.get("source_type")
        if not source_type and str(normalized.get("export_type") or "").strip().lower() == "codex":
            source_type = "codex"
        normalized["source_type"] = self._normalize_source_type(source_type)
        limits_progress = normalized.get("limits_progress")
        normalized["limits_progress"] = limits_progress if isinstance(limits_progress, list) else []
        normalized["default_model_slug"] = normalized.get("default_model_slug") or None
        normalized["restore_at"] = normalized.get("restore_at") or None
        normalized["success"] = int(normalized.get("success") or 0)
        normalized["fail"] = int(normalized.get("fail") or 0)
        normalized.pop("invalid_count", None)
        normalized["last_used_at"] = normalized.get("last_used_at")
        normalized.pop("last_invalid_at", None)
        normalized["last_refresh_error"] = normalized.get("last_refresh_error") or None
        normalized["last_refresh_error_at"] = normalized.get("last_refresh_error_at") or None
        normalized["last_refreshed_at"] = normalized.get("last_refreshed_at") or None
        normalized["last_token_refresh_at"] = normalized.get("last_token_refresh_at") or None
        normalized["last_token_refresh_error"] = normalized.get("last_token_refresh_error") or None
        normalized["last_token_refresh_error_at"] = normalized.get("last_token_refresh_error_at") or None
        normalized["created_at"] = normalized.get("created_at") or utc_now_text()
        return normalized

    @staticmethod
    def _jwt_exp(access_token: str) -> int:
        """读取 access_token 的过期时间戳。"""
        try:
            return int(AccountService._decode_jwt_payload(access_token).get("exp") or 0)
        except (TypeError, ValueError):
            return 0

    @classmethod
    def _token_expires_in(cls, access_token: str) -> int | None:
        """返回 access_token 距离过期的秒数。"""
        exp = cls._jwt_exp(access_token)
        if exp <= 0:
            return None
        return exp - int(time.time())

    @classmethod
    def _token_needs_refresh(cls, access_token: str, *, force: bool = False) -> bool:
        """判断 access_token 是否需要刷新。"""
        if force:
            return True
        remaining = cls._token_expires_in(access_token)
        return remaining is not None and remaining <= cls._ACCESS_TOKEN_REFRESH_SKEW_SECONDS

    @classmethod
    def _token_issued_at(cls, access_token: str) -> datetime | None:
        """读取 access_token 的签发时间。"""
        try:
            iat = int(cls._decode_jwt_payload(access_token).get("iat") or 0)
        except (TypeError, ValueError):
            return None
        if iat <= 0:
            return None
        return datetime.fromtimestamp(iat, tz=timezone.utc)

    @staticmethod
    def _safe_response_text(response: object, limit: int = 300) -> str:
        """截取上游响应文本用于错误信息。"""
        try:
            return str(getattr(response, "text", "") or "")[:limit]
        except Exception:
            return ""

    def _resolve_access_token_locked(self, access_token: str) -> str:
        """在持锁状态下解析 token 轮换后的当前 token。"""
        token = str(access_token or "").strip()
        seen: set[str] = set()
        while token and token not in self._accounts and token in self._token_aliases and token not in seen:
            seen.add(token)
            token = self._token_aliases.get(token, token)
        return token

    def resolve_access_token(self, access_token: str) -> str:
        """解析 token 轮换后的当前 token。"""
        if not access_token:
            return ""
        with self._lock:
            return self._resolve_access_token_locked(access_token)

    def _get_account_for_token(self, access_token: str) -> tuple[str, dict | None]:
        """按 token 获取当前账号副本。"""
        with self._lock:
            resolved = self._resolve_access_token_locked(access_token)
            account = self._accounts.get(resolved)
            return resolved, dict(account) if account else None

    def _record_token_refresh_error(self, access_token: str, event: str, error: str) -> None:
        """记录 refresh_token 刷新 access_token 的错误。"""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            resolved = self._resolve_access_token_locked(access_token)
            current = self._accounts.get(resolved)
            if current is None:
                return
            next_item = dict(current)
            next_item["last_token_refresh_error"] = str(error or "refresh token failed")
            next_item["last_token_refresh_error_at"] = now
            account = self._normalize_account(next_item)
            if account is not None:
                self._accounts[resolved] = account
                self._save_accounts()
        log_service.add(
            LOG_TYPE_ACCOUNT,
            "refresh_token 刷新 access_token 失败",
            {"source": event, "token": anonymize_token(access_token), "error": str(error or "")},
        )

    def _recent_token_refresh_error(self, account: dict) -> bool:
        """判断账号最近是否发生过 access_token 刷新错误。"""
        last_error_at = parse_time(account.get("last_token_refresh_error_at"))
        if last_error_at is None:
            return False
        return (datetime.now(timezone.utc) - last_error_at).total_seconds() < self._TOKEN_REFRESH_ERROR_BACKOFF_SECONDS

    def _recent_refresh_token_keepalive_error(self, account: dict, now: datetime) -> bool:
        """判断 refresh_token keepalive 是否处于错误退避期。"""
        last_error_at = parse_time(account.get("last_token_refresh_error_at"))
        if last_error_at is None:
            return False
        return (now - last_error_at).total_seconds() < self._REFRESH_TOKEN_KEEPALIVE_ERROR_BACKOFF_SECONDS

    def _refresh_token_keepalive_anchor(self, account: dict) -> datetime | None:
        """计算 refresh_token keepalive 的起始参考时间。"""
        return (
                parse_time(account.get("last_token_refresh_at"))
                or self._token_issued_at(str(account.get("access_token") or ""))
                or parse_time(account.get("created_at"))
        )

    def _refresh_token_keepalive_due_at(self, account: dict, now: datetime) -> datetime | None:
        """返回账号 refresh_token keepalive 到期时间。"""
        if not str(account.get("refresh_token") or "").strip():
            return None
        if account.get("status") == "禁用":
            return None
        if self._recent_refresh_token_keepalive_error(account, now):
            return None
        anchor = self._refresh_token_keepalive_anchor(account)
        if anchor is None:
            return now
        due_at = anchor + timedelta(seconds=self._REFRESH_TOKEN_KEEPALIVE_SECONDS)
        return due_at if due_at <= now else None

    def _account_refresh_due_at(self, account: dict, now: datetime) -> datetime:
        """返回账号信息刷新到期时间。"""
        interval_seconds = config.refresh_account_interval_seconds
        last_refreshed_at = parse_time(account.get("last_refreshed_at"))
        if last_refreshed_at is not None:
            return last_refreshed_at + timedelta(seconds=interval_seconds)

        token = str(account.get("access_token") or "")
        digest = hashlib.sha1(token.encode("utf-8")).hexdigest()
        offset_seconds = int(digest[:8], 16) % interval_seconds
        created_at = parse_time(account.get("created_at")) or now
        return created_at + timedelta(seconds=offset_seconds)

    def _request_access_token_refresh(self, refresh_token: str, account: dict | None = None) -> dict[str, str]:
        """调用 OAuth 接口用 refresh_token 换取新 token。"""
        import httpx
        from services.proxy_service import proxy_settings

        kwargs = proxy_settings.build_client_kwargs(account=account, verify=True)
        session = httpx.Client(**kwargs)
        try:
            response = session.post(
                self._OAUTH_TOKEN_URL,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": self._OAUTH_USER_AGENT,
                },
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": self._OAUTH_CLIENT_ID,
                },
                timeout=60,
            )
            data = response.json() if response.text else {}
            if response.status_code != 200 or not isinstance(data, dict) or not data.get("access_token"):
                detail = ""
                if isinstance(data, dict):
                    detail = str(data.get("error_description") or data.get("error") or data.get("message") or "")
                detail = detail or self._safe_response_text(response)
                raise RuntimeError(f"oauth_refresh_http_{response.status_code}{': ' + detail if detail else ''}")
            return {
                "access_token": str(data.get("access_token") or "").strip(),
                "refresh_token": str(data.get("refresh_token") or refresh_token).strip(),
                "id_token": str(data.get("id_token") or "").strip(),
            }
        finally:
            session.close()

    def _apply_refreshed_tokens(self, old_access_token: str, token_data: dict, event: str) -> str:
        """把刷新得到的新 token 写回账号池。"""
        now = datetime.now(timezone.utc).isoformat()
        with self._image_slot_condition:
            old_token = self._resolve_access_token_locked(old_access_token)
            current = self._accounts.get(old_token)
            if current is None:
                return old_token
            new_token = str(token_data.get("access_token") or old_token).strip()
            if not new_token:
                return old_token

            next_item = dict(current)
            next_item["access_token"] = new_token
            if token_data.get("refresh_token"):
                next_item["refresh_token"] = str(token_data.get("refresh_token") or "").strip()
            if token_data.get("id_token"):
                next_item["id_token"] = str(token_data.get("id_token") or "").strip()
            next_item["last_token_refresh_at"] = now
            next_item["last_token_refresh_error"] = None
            next_item["last_token_refresh_error_at"] = None
            next_item["last_refresh_error"] = None
            next_item["last_refresh_error_at"] = None

            account = self._normalize_account(next_item)
            if account is None:
                return old_token

            rotated = new_token != old_token
            if rotated:
                self._accounts.pop(old_token, None)
                self._token_aliases[old_token] = new_token
                old_inflight = int(self._image_inflight.pop(old_token, 0))
                if old_inflight:
                    self._image_inflight[new_token] = int(self._image_inflight.get(new_token, 0)) + old_inflight
            self._accounts[new_token] = account
            self._save_accounts()
            self._image_slot_condition.notify_all()

        log_service.add(
            LOG_TYPE_ACCOUNT,
            "refresh_token 已刷新 access_token",
            {"source": event, "token": anonymize_token(new_token), "rotated": rotated},
        )
        return new_token

    def refresh_access_token(self, access_token: str, *, force: bool = False,
                             event: str = "refresh_access_token") -> str:
        """按需刷新 access_token 并返回当前可用 token。"""
        if not access_token:
            return ""
        with self._token_refresh_lock:
            resolved_token, account = self._get_account_for_token(access_token)
            if not account:
                return access_token
            active_token = str(account.get("access_token") or resolved_token or access_token)
            if not self._token_needs_refresh(active_token, force=force):
                return active_token
            refresh_token = str(account.get("refresh_token") or "").strip()
            if not refresh_token:
                return active_token
            if not force and self._recent_token_refresh_error(account):
                return active_token
            try:
                token_data = self._request_access_token_refresh(refresh_token, account)
            except Exception as exc:
                self._record_token_refresh_error(active_token, event, str(exc or ""))
                return active_token
            return self._apply_refreshed_tokens(active_token, token_data, event)

    def list_expiring_access_tokens(self) -> list[str]:
        """列出即将过期且可用 refresh_token 续期的 access_token。"""
        with self._lock:
            return [
                token
                for account in self._accounts.values()
                if str(account.get("refresh_token") or "").strip()
                   and (token := str(account.get("access_token") or "").strip())
                   and self._token_needs_refresh(token)
            ]

    def list_refresh_token_keepalive_tokens(self) -> list[str]:
        """列出需要执行 refresh_token keepalive 的账号 token。"""
        now = datetime.now(timezone.utc)
        due_items: list[tuple[datetime, str]] = []
        with self._lock:
            for account in self._accounts.values():
                due_at = self._refresh_token_keepalive_due_at(account, now)
                token = str(account.get("access_token") or "").strip()
                if due_at is not None and token:
                    due_items.append((due_at, token))
        due_items.sort(key=lambda item: item[0])
        return [token for _, token in due_items[: self._REFRESH_TOKEN_KEEPALIVE_BATCH_SIZE]]

    def keepalive_refresh_tokens(self, access_tokens: list[str]) -> dict[str, Any]:
        """批量执行 refresh_token keepalive。"""
        access_tokens = list(dict.fromkeys(token for token in access_tokens if token))
        if not access_tokens:
            return {"refreshed": 0, "errors": [], "items": self.list_accounts()}

        refreshed = 0
        errors = []
        for access_token in access_tokens:
            before = self.resolve_access_token(access_token)
            after = self.refresh_access_token(before, force=True, event="refresh_token_keepalive")
            account = self.get_account(after)
            if account and str(account.get("last_token_refresh_error") or "").strip():
                errors.append({
                    "token": anonymize_token(before),
                    "error": str(account.get("last_token_refresh_error") or "refresh token failed"),
                })
                continue
            if account:
                refreshed += 1

        return {
            "refreshed": refreshed,
            "errors": errors,
            "items": self.list_accounts(),
        }

    def list_tokens(self) -> list[str]:
        """列出当前所有 access_token。"""
        with self._lock:
            return list(self._accounts)

    def _list_ready_candidate_tokens(
            self,
            excluded_tokens: set[str] | None = None,
            plan_type: str | None = None,
            source_type: str | None = None,
            plan_types: set[str] | tuple[str, ...] | None = None,
    ) -> list[str]:
        """列出状态和筛选条件满足图片调度的候选 token。"""
        excluded = set(excluded_tokens or set())
        return [
            token
            for item in self._accounts.values()
            if self._is_image_account_available(item)
               and self._account_matches_plan_type(item, plan_type)
               and self._account_matches_any_plan_type(item, plan_types)
               and self._account_matches_source_type(item, source_type)
               and (token := item.get("access_token") or "")
               and token not in excluded
        ]

    def _list_available_candidate_tokens(
            self,
            excluded_tokens: set[str] | None = None,
            plan_type: str | None = None,
            source_type: str | None = None,
            plan_types: set[str] | tuple[str, ...] | None = None,
    ) -> list[str]:
        """列出当前图片并发槽未满的候选 token。"""
        max_concurrency = max(1, int(config.image_account_concurrency or 1))
        return [
            token
            for token in self._list_ready_candidate_tokens(excluded_tokens, plan_type, source_type, plan_types)
            if int(self._image_inflight.get(token, 0)) < max_concurrency
        ]

    def _acquire_next_candidate_token(
            self,
            excluded_tokens: set[str] | None = None,
            plan_type: str | None = None,
            source_type: str | None = None,
            plan_types: set[str] | tuple[str, ...] | None = None,
    ) -> str:
        """占用一个图片并发槽并返回对应 token。"""
        with self._image_slot_condition:
            while True:
                if not self._list_ready_candidate_tokens(excluded_tokens, plan_type, source_type, plan_types):
                    raise RuntimeError(
                        f"no available {plan_type or source_type or ''} image quota".replace("  ", " ").strip()
                        if plan_type or source_type else "no available image quota"
                    )
                tokens = self._list_available_candidate_tokens(excluded_tokens, plan_type, source_type, plan_types)
                if tokens:
                    access_token = tokens[self._index % len(tokens)]
                    self._index += 1
                    self._image_inflight[access_token] = int(self._image_inflight.get(access_token, 0)) + 1
                    return access_token
                self._image_slot_condition.wait(timeout=1.0)

    def release_image_slot(self, access_token: str) -> None:
        """释放账号图片并发槽。"""
        if not access_token:
            return
        with self._image_slot_condition:
            access_token = self._resolve_access_token_locked(access_token)
            current_inflight = int(self._image_inflight.get(access_token, 0))
            if current_inflight <= 1:
                self._image_inflight.pop(access_token, None)
            else:
                self._image_inflight[access_token] = current_inflight - 1
            self._image_slot_condition.notify_all()

    def get_available_access_token(
            self,
            plan_type: str | None = None,
            source_type: str | None = None,
            plan_types: set[str] | tuple[str, ...] | None = None,
    ) -> str:
        """从候选池中获取一个可用的图片生图 token。

        基于本地缓存做初筛，然后通过 fetch_remote_info 做远程验证（token 有效性、配额等）。
        限制最大尝试次数防止 token rotation 导致无限循环。
        """
        max_attempts = 20  # 防止无限循环
        attempted_tokens: set[str] = set()
        for _attempt in range(max_attempts):
            access_token = self._acquire_next_candidate_token(
                excluded_tokens=attempted_tokens,
                plan_type=plan_type,
                source_type=source_type,
                plan_types=plan_types,
            )
            attempted_tokens.add(access_token)
            try:
                account = self.fetch_remote_info(access_token, "get_available_access_token")
            except Exception:
                self.release_image_slot(access_token)
                continue
            # fetch_remote_info 内部可能因 token rotation 导致 access_token 变化，
            # 把新 token 也加入排除列表，防止重复尝试
            resolved = str((account or {}).get("access_token") or "")
            if resolved and resolved != access_token:
                attempted_tokens.add(resolved)
            if (
                    self._is_image_account_available(account or {})
                    and self._account_matches_plan_type(account or {}, plan_type)
                    and self._account_matches_any_plan_type(account or {}, plan_types)
                    and self._account_matches_source_type(account or {}, source_type)
            ):
                return str((account or {}).get("access_token") or access_token)
            self.release_image_slot(access_token)
        raise RuntimeError(
            f"no available {plan_type or source_type or ''} image quota (tried {len(attempted_tokens)} tokens)".replace(
                "  ", " ").strip()
            if plan_type or source_type else f"no available image quota (tried {len(attempted_tokens)} tokens)"
        )

    def get_text_access_token(self, excluded_tokens: set[str] | None = None) -> str:
        """获取一个可用于文本请求的 token。"""
        excluded = set(excluded_tokens or set())
        with self._lock:
            candidates = [
                token
                for account in self._accounts.values()
                if account.get("status") not in {"禁用", "异常"}
                   and (token := account.get("access_token") or "")
                   and token not in excluded
            ]
            if not candidates:
                return ""
            access_token = candidates[self._index % len(candidates)]
            self._index += 1
        return self.refresh_access_token(access_token, event="get_text_access_token") or access_token

    def mark_text_used(self, access_token: str) -> None:
        """记录文本请求最近使用时间。"""
        if not access_token:
            return
        with self._lock:
            access_token = self._resolve_access_token_locked(access_token)
            current = self._accounts.get(access_token)
            if current is None:
                return
            next_item = dict(current)
            next_item["last_used_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            account = self._normalize_account(next_item)
            if account is None:
                return
            self._accounts[access_token] = account
            self._save_accounts()

    def remove_invalid_token(self, access_token: str, event: str, error: str = "", quiet: bool = False) -> bool:
        """按配置移除或标记异常 token。"""
        if not config.auto_remove_invalid_accounts:
            self.update_account(
                access_token,
                {
                    "status": "异常",
                    "quota": 0,
                    "last_refresh_error": str(error or "invalid access token"),
                    "last_refresh_error_at": datetime.now(timezone.utc).isoformat(),
                },
                quiet=quiet,
            )
            return False
        removed = self.get_account(access_token) is not None
        self.delete_accounts([access_token])
        if removed:
            log_service.add(
                LOG_TYPE_ACCOUNT,
                "自动移除异常账号",
                {"source": event, "token": anonymize_token(access_token), "error": str(error or "")},
            )
        return removed

    def get_account(self, access_token: str) -> dict | None:
        """获取单个账号副本。"""
        if not access_token:
            return None
        with self._lock:
            access_token = self._resolve_access_token_locked(access_token)
            account = self._accounts.get(access_token)
            return dict(account) if account else None

    def list_accounts(self) -> list[dict]:
        """返回所有账号的副本，并为每个账号附加当前图片在途数 image_inflight。

        image_inflight 为内存态并发计数(账号正在生成、尚未结束的图片数)。号池空闲时
        若某账号该值持续 > 0，说明其并发槽位泄漏、已被静默排除出调度，可借此在 UI 上诊断。
        """
        with self._lock:
            result = []
            for item in self._accounts.values():
                account = dict(item)
                token = account.get("access_token") or ""
                account["image_inflight"] = int(self._image_inflight.get(token, 0))
                result.append(account)
            return result

    def list_due_refresh_tokens(self, status: str) -> list[str]:
        """按账号独立刷新时间列出到期 token。"""
        now = datetime.now(timezone.utc)
        due_items: list[tuple[datetime, str]] = []
        with self._lock:
            for account in self._accounts.values():
                token = str(account.get("access_token") or "").strip()
                if account.get("status") != status or not token:
                    continue
                if token in self._refreshing_tokens:
                    continue
                due_at = self._account_refresh_due_at(account, now)
                if due_at <= now:
                    due_items.append((due_at, token))
        due_items.sort(key=lambda item: item[0])
        return [token for _, token in due_items[: self._ACCOUNT_REFRESH_BATCH_SIZE]]

    @staticmethod
    def _account_payload_token(item: dict) -> str:
        """从账号导入 payload 中提取 access_token。"""
        return str(item.get("access_token") or item.get("accessToken") or "").strip()

    @staticmethod
    def _prepare_account_payload(item: dict) -> dict | None:
        """整理账号导入 payload 并补充 JWT 中的基础信息。"""
        if not isinstance(item, dict):
            return None
        access_token = AccountService._account_payload_token(item)
        if not access_token:
            return None
        payload = dict(item)
        payload.pop("accessToken", None)
        payload["access_token"] = access_token
        # CPA/Codex 导出文件里的 `type=codex` 是导出格式，不是号池套餐类型。
        if str(payload.get("type") or "").strip().lower() == "codex":
            payload["export_type"] = "codex"
            payload["source_type"] = "codex"
            payload.pop("type", None)
        if str(payload.get("export_type") or "").strip().lower() == "codex":
            payload["source_type"] = "codex"
        if payload.get("plan_type") and not payload.get("type"):
            payload["type"] = str(payload.get("plan_type") or "").strip()
        token_payload = AccountService._decode_jwt_payload(access_token)
        profile_claim = token_payload.get("https://api.openai.com/profile")
        profile_claim = profile_claim if isinstance(profile_claim, dict) else {}
        auth_claim = token_payload.get("https://api.openai.com/auth")
        auth_claim = auth_claim if isinstance(auth_claim, dict) else {}
        if not payload.get("email"):
            payload["email"] = str(profile_claim.get("email") or "").strip() or None
        if not payload.get("user_id"):
            payload["user_id"] = str(auth_claim.get("user_id") or "").strip() or None
        if not payload.get("type"):
            payload["type"] = AccountService._normalize_account_type(auth_claim.get("chatgpt_plan_type")) or "free"
        return payload

    def add_account_items(self, items: list[dict]) -> dict:
        """导入结构化账号 payload。"""
        payloads = [
            payload
            for item in items
            if (payload := self._prepare_account_payload(item)) is not None
        ]
        return self._add_account_payloads(payloads)

    def add_accounts(self, tokens: list[str], source_type: str = "web") -> dict:
        """按 access_token 列表导入账号。"""
        tokens = list(dict.fromkeys(token for token in tokens if token))
        if not tokens:
            return {"added": 0, "skipped": 0, "items": self.list_accounts()}
        return self._add_account_payloads([
            {"access_token": token, "source_type": self._normalize_source_type(source_type)}
            for token in tokens
        ])

    def _add_account_payloads(self, payloads: list[dict]) -> dict:
        """写入去重后的账号 payload 并返回账号列表。"""
        deduped: dict[str, dict] = {}
        for payload in payloads:
            if not isinstance(payload, dict):
                continue
            access_token = self._account_payload_token(payload)
            if not access_token:
                continue
            current = deduped.get(access_token, {})
            deduped[access_token] = {**current, **payload, "access_token": access_token}

        if not deduped:
            return {"added": 0, "skipped": 0, "items": self.list_accounts()}

        with self._lock:
            added = 0
            skipped = 0
            for access_token, payload in deduped.items():
                current = self._accounts.get(access_token)
                if current is None:
                    added += 1
                    current = {"created_at": utc_now_text()}
                else:
                    skipped += 1
                incoming = dict(payload)
                if not incoming.get("created_at"):
                    incoming.pop("created_at", None)
                account = self._normalize_account(
                    {
                        **current,
                        **incoming,
                        "access_token": access_token,
                        "type": str(incoming.get("type") or current.get("type") or "free"),
                    }
                )
                if account is not None:
                    self._accounts[access_token] = account
            self._save_accounts()
            items = [dict(item) for item in self._accounts.values()]
            log_service.add(LOG_TYPE_ACCOUNT, f"新增 {added} 个账号，跳过 {skipped} 个",
                            {"added": added, "skipped": skipped})
        return {"added": added, "skipped": skipped, "items": items}

    def delete_accounts(self, tokens: list[str]) -> None:
        """删除指定 token 对应的账号和运行时状态。"""
        target_set = set(token for token in tokens if token)
        if not target_set:
            return
        with self._lock:
            target_set = {self._resolve_access_token_locked(token) for token in target_set if token}
            for token in target_set:
                self._accounts.pop(token, None)
                self._image_inflight.pop(token, None)
            self._token_aliases = {
                old: new
                for old, new in self._token_aliases.items()
                if old not in target_set and new not in target_set
            }
            if self._accounts:
                self._index %= len(self._accounts)
            else:
                self._index = 0
            self._save_accounts()
            log_service.add(LOG_TYPE_ACCOUNT, "删除账号", {})

    def update_account(self, access_token: str, updates: dict, quiet: bool = False) -> dict | None:
        """合并更新单个账号并返回最新账号信息。"""
        if not access_token:
            return None
        with self._lock:
            access_token = self._resolve_access_token_locked(access_token)
            current = self._accounts.get(access_token)
            if current is None:
                return None
            account = self._normalize_account({**current, **updates, "access_token": access_token})
            if account is None:
                return None
            if account.get("status") == "限流" and config.auto_remove_rate_limited_accounts:
                self._accounts.pop(access_token, None)
                self._save_accounts()
                log_service.add(LOG_TYPE_ACCOUNT, "自动移除限流账号", {"token": anonymize_token(access_token)})
                return None
            self._accounts[access_token] = account
            self._save_accounts()
            if not quiet:
                log_service.add(LOG_TYPE_ACCOUNT, "更新账号",
                                {"token": anonymize_token(access_token), "status": account.get("status")})
            return dict(account)
        return None

    def _record_refresh_success(self, access_token: str) -> None:
        """记录账号刷新成功并清理失败状态。"""
        with self._lock:
            access_token = self._resolve_access_token_locked(access_token)
            current = self._accounts.get(access_token)
            if current is None:
                return
            next_item = dict(current)
            next_item["last_refresh_error"] = None
            next_item["last_refresh_error_at"] = None
            account = self._normalize_account(next_item)
            if account is not None:
                self._accounts[access_token] = account

    def mark_image_result(self, access_token: str, success: bool) -> dict | None:
        """记录图片任务结果并更新账号额度状态。"""
        if not access_token:
            return None
        self.release_image_slot(access_token)
        with self._lock:
            access_token = self._resolve_access_token_locked(access_token)
            current = self._accounts.get(access_token)
            if current is None:
                return None
            next_item = dict(current)
            next_item["last_used_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            image_quota_unknown = bool(next_item.get("image_quota_unknown"))
            if success:
                next_item["success"] = int(next_item.get("success") or 0) + 1
                if not image_quota_unknown:
                    next_item["quota"] = max(0, int(next_item.get("quota") or 0) - 1)
                if not image_quota_unknown and next_item["quota"] == 0:
                    next_item["status"] = "限流"
                    next_item["restore_at"] = next_item.get("restore_at") or None
                elif next_item.get("status") == "限流":
                    next_item["status"] = "正常"
            else:
                next_item["fail"] = int(next_item.get("fail") or 0) + 1
            account = self._normalize_account(next_item)
            if account is None:
                return None
            if account.get("status") == "限流" and config.auto_remove_rate_limited_accounts:
                self._accounts.pop(access_token, None)
                self._save_accounts()
                log_service.add(LOG_TYPE_ACCOUNT, "自动移除限流账号", {"token": anonymize_token(access_token)})
                return None
            self._accounts[access_token] = account
            self._save_accounts()
            return dict(account)
        return None

    def fetch_remote_info(self, access_token: str, event: str = "fetch_remote_info") -> dict[str, Any] | None:
        """拉取远端账号信息并同步到本地账号。"""
        if not access_token:
            raise ValueError("access_token is required")

        active_token = self.refresh_access_token(access_token, event=f"{event}:preflight") or access_token
        try:
            from services.protocol.openai_backend_api import InvalidAccessTokenError, OpenAIBackendAPI
            account = self.get_account(active_token) or {"access_token": active_token}
            result = OpenAIBackendAPI(account=account).get_user_info()
        except InvalidAccessTokenError as exc:
            refreshed_token = self.refresh_access_token(active_token, force=True, event=f"{event}:invalid_access_token")
            if refreshed_token and refreshed_token != active_token:
                try:
                    account = self.get_account(refreshed_token) or {"access_token": refreshed_token}
                    result = OpenAIBackendAPI(account=account).get_user_info()
                except InvalidAccessTokenError as retry_exc:
                    self.remove_invalid_token(refreshed_token, event, str(retry_exc))
                    raise
                active_token = refreshed_token
            else:
                self.remove_invalid_token(active_token, event, str(exc))
                raise
        self._record_refresh_success(active_token)
        return self.update_account(active_token, result)

    def _claim_refresh_tokens(self, access_tokens: list[str]) -> list[str]:
        """占用可刷新的 token，避免并发重复刷新。"""
        claimed: list[str] = []
        with self._lock:
            for token in access_tokens:
                resolved = self._resolve_access_token_locked(token)
                account = self._accounts.get(resolved)
                if not account:
                    continue
                if resolved in self._refreshing_tokens:
                    continue
                self._refreshing_tokens.add(resolved)
                claimed.append(resolved)
        return claimed

    def _release_refresh_token(self, access_token: str, refreshed: bool) -> None:
        """释放刷新占用，并在成功时记录刷新时间。"""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            resolved = self._resolve_access_token_locked(access_token)
            self._refreshing_tokens.discard(access_token)
            self._refreshing_tokens.discard(resolved)
            current = self._accounts.get(resolved)
            if current is None or not refreshed:
                return
            next_item = dict(current)
            next_item["last_refreshed_at"] = now
            account = self._normalize_account(next_item)
            if account is not None:
                self._accounts[resolved] = account
                self._save_accounts()

    def refresh_accounts(self, access_tokens: list[str]) -> dict[str, Any]:
        """批量刷新账号信息并返回刷新结果统计。"""
        access_tokens = list(dict.fromkeys(token for token in access_tokens if token))
        if not access_tokens:
            return {"refreshed": 0, "failed": 0}

        refreshed = 0
        failed = 0
        refresh_tokens = self._claim_refresh_tokens(access_tokens)
        if not refresh_tokens:
            return {"refreshed": 0, "failed": 0}
        max_workers = min(10, len(refresh_tokens))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.fetch_remote_info, token, "refresh_accounts"): token
                for token in refresh_tokens
            }
            for future in as_completed(futures):
                token = futures[future]
                account = None
                try:
                    account = future.result()
                except Exception as exc:
                    failed += 1
                    print(f"[account-refresh] {anonymize_token(token)} failed: {exc}")
                else:
                    if account is not None:
                        refreshed += 1
                    else:
                        failed += 1
                finally:
                    self._release_refresh_token(token, account is not None)

        return {"refreshed": refreshed, "failed": failed}

    def get_stats(self) -> dict:
        """统计账号数量、状态、额度和调用结果。"""
        with self._lock:
            items = list(self._accounts.values())
        total = len(items)
        active = sum(1 for a in items if a.get("status") == "正常")
        limited = sum(1 for a in items if a.get("status") == "限流")
        abnormal = sum(1 for a in items if a.get("status") == "异常")
        disabled = sum(1 for a in items if a.get("status") == "禁用")
        total_quota = sum(max(0, int(a.get("quota") or 0)) for a in items if a.get("status") == "正常")
        unlimited = sum(1 for a in items if a.get("status") == "正常" and bool(a.get("image_quota_unknown")))
        total_success = sum(int(a.get("success") or 0) for a in items)
        total_fail = sum(int(a.get("fail") or 0) for a in items)
        by_type = {}
        for a in items:
            t = a.get("type", "unknown")
            by_type[t] = by_type.get(t, 0) + 1
        return {
            "total": total,
            "active": active,
            "limited": limited,
            "abnormal": abnormal,
            "disabled": disabled,
            "total_quota": total_quota,
            "unlimited_quota_count": unlimited,
            "total_success": total_success,
            "total_fail": total_fail,
            "by_type": by_type,
        }


account_service = AccountService()
