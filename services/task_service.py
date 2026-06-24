from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from services.account.account_service import account_service
from services.config import DATA_DIR, config
from services.content_filter import request_text
from services.image_storage_service import image_storage_service
from services.log_service import LOG_TYPE_CALL, log_service
from services.protocol.openai_backend_api import EDITABLE_FILE_MODEL, OpenAIBackendAPI
from services.protocol import openai_v1_image_edit, openai_v1_image_generations
from utils.helper import new_uuid

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"
UNFINISHED_STATUSES = {STATUS_QUEUED, STATUS_RUNNING}

CONVERSATIONS_PATH = DATA_DIR / "conversations.json"
TASKS_PATH = DATA_DIR / "tasks.json"
EDITABLE_FILE_ROOT = DATA_DIR / "files"
EDITABLE_FILE_PLAN_TYPES = ("Plus", "Team", "Pro", "Enterprise")


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _clean(value: object, default: str = "") -> str:
    return str(value or default).strip()


def _owner_id(identity: dict[str, object]) -> str:
    return _clean(identity.get("id")) or "anonymous"


def _task_key(owner_id: str, task_id: str) -> str:
    return f"{owner_id}:{task_id}"


def _editable_access_token() -> str:
    accounts = [
        item for item in account_service.list_accounts()
        if _clean(item.get("access_token"))
        and item.get("status") not in {"禁用", "异常"}
        and account_service._account_matches_any_plan_type(item, EDITABLE_FILE_PLAN_TYPES)
    ]
    if not accounts:
        raise RuntimeError("no available plus/team/pro account")
    accounts.sort(key=lambda item: _clean(item.get("last_used_at")))
    token = _clean(accounts[0].get("access_token"))
    return account_service.refresh_access_token(token, event="editable_file_task") or token


def _file_url(path: Path, base_url: str) -> str:
    rel = path.resolve().relative_to(EDITABLE_FILE_ROOT.resolve()).as_posix()
    prefix = str(base_url or "").strip().rstrip("/")
    return f"{prefix}/files/{quote(rel, safe='/')}" if prefix else f"/files/{quote(rel, safe='/')}"


def _title(prompt: str, fallback: str) -> str:
    text = " ".join(_clean(prompt).split())
    return text[:24] or fallback


def _load_array(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


def _save_array(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _elapsed(task: dict[str, Any]) -> int:
    start = float(task.get("started_ts") or task.get("created_ts") or 0)
    end = float(task.get("ended_ts") or time.time())
    return max(0, int(end - start)) if start else 0


def _public_task(task: dict[str, Any]) -> dict[str, Any]:
    item = {
        "id": task.get("id"),
        "taskId": task.get("id"),
        "owner_id": task.get("owner_id"),
        "kind": task.get("kind"),
        "mode": task.get("mode"),
        "status": task.get("status"),
        "progress": task.get("progress"),
        "model": task.get("model"),
        "created_at": task.get("created_at"),
        "updated_at": task.get("updated_at"),
        "elapsed_seconds": _elapsed(task),
        "duration_ms": task.get("duration_ms"),
    }
    if task.get("conversation_id"):
        item["conversation_id"] = task.get("conversation_id")
    if task.get("turn_id"):
        item["turn_id"] = task.get("turn_id")
    if task.get("request"):
        item["request"] = task.get("request")
        item["prompt_preview"] = request_text(task.get("request", {}).get("prompt"))
    if task.get("result"):
        item["result"] = task.get("result")
        items = task.get("result", {}).get("items")
        if isinstance(items, list):
            item["data"] = [
                {
                    "url": result.get("url"),
                    "revised_prompt": result.get("revised_prompt"),
                }
                for result in items
                if isinstance(result, dict) and result.get("type") == "image"
            ]
    if task.get("error"):
        item["error"] = task.get("error")
    return item


def _turn_status(tasks: list[dict[str, Any]]) -> str:
    statuses = [task.get("status") for task in tasks]
    if any(status == STATUS_RUNNING for status in statuses):
        return "generating"
    if any(status == STATUS_QUEUED for status in statuses):
        return "queued"
    if any(status == STATUS_ERROR for status in statuses):
        return "error"
    return "success"


class TaskService:
    def __init__(self, conversations_path: Path = CONVERSATIONS_PATH, tasks_path: Path = TASKS_PATH) -> None:
        self.conversations_path = conversations_path
        self.tasks_path = tasks_path
        self._lock = threading.RLock()
        with self._lock:
            self._conversations = _load_array(self.conversations_path)
            self._tasks = {
                _task_key(_clean(item.get("owner_id")), _clean(item.get("id"))): item
                for item in _load_array(self.tasks_path)
                if _clean(item.get("owner_id")) and _clean(item.get("id"))
            }
            if self._recover_unfinished_locked():
                self._save_tasks_locked()

    def list_conversations(self, identity: dict[str, object], kind: str) -> list[dict[str, Any]]:
        owner = _owner_id(identity)
        with self._lock:
            items = [
                self._public_conversation(item)
                for item in self._conversations
                if item.get("owner_id") == owner and item.get("kind") == kind
            ]
        return sorted(items, key=lambda item: str(item.get("updated_at") or ""), reverse=True)

    def get_conversation(self, identity: dict[str, object], conversation_id: str) -> dict[str, Any]:
        owner = _owner_id(identity)
        with self._lock:
            for item in self._conversations:
                if item.get("owner_id") == owner and item.get("id") == conversation_id:
                    return self._public_conversation(item)
        raise ValueError("conversation not found")

    def rename_conversation(self, identity: dict[str, object], conversation_id: str, title: str) -> dict[str, Any]:
        owner = _owner_id(identity)
        with self._lock:
            item = self._find_conversation_locked(owner, conversation_id)
            item["title"] = _clean(title, item.get("title") or "未命名")
            item["updated_at"] = _now()
            self._save_conversations_locked()
            return self._public_conversation(item)

    def delete_conversation(self, identity: dict[str, object], conversation_id: str) -> dict[str, int]:
        owner = _owner_id(identity)
        with self._lock:
            before = len(self._conversations)
            self._conversations = [
                item for item in self._conversations
                if not (item.get("owner_id") == owner and item.get("id") == conversation_id)
            ]
            self._save_conversations_locked()
            return {"removed": before - len(self._conversations)}

    def clear_conversations(self, identity: dict[str, object], kind: str) -> dict[str, int]:
        owner = _owner_id(identity)
        with self._lock:
            before = len(self._conversations)
            self._conversations = [
                item for item in self._conversations
                if not (item.get("owner_id") == owner and item.get("kind") == kind)
            ]
            self._save_conversations_locked()
            return {"removed": before - len(self._conversations)}

    def delete_turn_part(self, identity: dict[str, object], conversation_id: str, turn_id: str, part: str) -> dict[str, Any]:
        owner = _owner_id(identity)
        with self._lock:
            conversation = self._find_conversation_locked(owner, conversation_id)
            turns = []
            for turn in conversation.get("turns") or []:
                if turn.get("id") != turn_id:
                    turns.append(turn)
                    continue
                next_turn = dict(turn)
                if part == "prompt":
                    next_turn["prompt"] = ""
                if part == "results":
                    next_turn["task_ids"] = []
                if next_turn.get("prompt") or next_turn.get("task_ids"):
                    turns.append(next_turn)
            if turns:
                conversation["turns"] = turns
                conversation["updated_at"] = _now()
            else:
                self._conversations.remove(conversation)
            self._save_conversations_locked()
            return self._public_conversation(conversation) if turns else {"removed": 1}

    def list_tasks(self, identity: dict[str, object], task_ids: list[str], kind: str = "") -> dict[str, Any]:
        owner = _owner_id(identity)
        ids = [_clean(item) for item in task_ids if _clean(item)]
        with self._lock:
            if ids:
                items = [
                    _public_task(task)
                    for task_id in ids
                    if (task := self._tasks.get(_task_key(owner, task_id)))
                ]
                found = {item["id"] for item in items}
                return {"items": items, "missing_ids": [task_id for task_id in ids if task_id not in found]}
            items = [
                _public_task(task)
                for task in self._tasks.values()
                if task.get("owner_id") == owner and (not kind or task.get("kind") == kind)
            ]
        items.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        return {"items": items, "missing_ids": []}

    def submit_image_turn(
        self,
        identity: dict[str, object],
        *,
        conversation_id: str = "",
        mode: str,
        prompt: str,
        model: str,
        size: str,
        quality: str,
        count: int,
        ratio: str,
        tier: str,
        base_url: str,
        images: list[tuple[bytes, str, str]] | None = None,
    ) -> dict[str, Any]:
        owner = _owner_id(identity)
        now = _now()
        turn_id = new_uuid()
        conversation_id = _clean(conversation_id) or new_uuid()
        reference_images = self._save_reference_images(images or [], base_url)
        task_ids = [new_uuid() for _ in range(max(1, count))]
        turn = {
            "id": turn_id,
            "mode": "edit" if mode == "edit" else "generate",
            "prompt": prompt,
            "model": _clean(model, "gpt-image-2"),
            "size": size,
            "quality": _clean(quality, "auto"),
            "ratio": _clean(ratio, "1:1"),
            "tier": _clean(tier, "1k"),
            "count": len(task_ids),
            "reference_images": reference_images,
            "task_ids": task_ids,
            "created_at": now,
        }
        with self._lock:
            conversation = self._get_or_create_conversation_locked(owner, conversation_id, "image", _title(prompt, "图片对话"), now)
            conversation["turns"] = [*(conversation.get("turns") or []), turn]
            conversation["updated_at"] = now
            for task_id in task_ids:
                self._tasks[_task_key(owner, task_id)] = {
                    "id": task_id,
                    "owner_id": owner,
                    "conversation_id": conversation_id,
                    "turn_id": turn_id,
                    "kind": "image",
                    "mode": turn["mode"],
                    "status": STATUS_QUEUED,
                    "model": turn["model"],
                    "progress": "",
                    "request": {
                        "prompt": prompt,
                        "size": size,
                        "quality": turn["quality"],
                        "input_urls": [item["url"] for item in reference_images],
                    },
                    "result": {"items": []},
                    "error": "",
                    "created_at": now,
                    "updated_at": now,
                    "created_ts": time.time(),
                }
            self._save_conversations_locked()
            self._save_tasks_locked()
            public = self._public_conversation(conversation)

        for task_id in task_ids:
            payload = {
                "prompt": prompt,
                "model": turn["model"],
                "n": 1,
                "size": size,
                "quality": turn["quality"],
                "response_format": "url",
                "base_url": base_url,
            }
            if turn["mode"] == "edit":
                payload["images"] = images or []
            threading.Thread(
                target=self._run_image_task,
                args=(_task_key(owner, task_id), payload, dict(identity)),
                daemon=True,
                name=f"image-task-{task_id[:16]}",
            ).start()
        return public

    def submit_file_task(
        self,
        identity: dict[str, object],
        *,
        kind: str,
        prompt: str,
        base64_images: list[str],
        base_url: str,
    ) -> dict[str, Any]:
        owner = _owner_id(identity)
        now = _now()
        conversation_id = new_uuid()
        turn_id = new_uuid()
        task_id = new_uuid()
        with self._lock:
            conversation = {
                "id": conversation_id,
                "owner_id": owner,
                "kind": kind,
                "title": _title(prompt, f"{kind.upper()} 任务"),
                "created_at": now,
                "updated_at": now,
                "turns": [
                    {
                        "id": turn_id,
                        "mode": "generate",
                        "prompt": prompt,
                        "model": EDITABLE_FILE_MODEL,
                        "reference_images": [],
                        "task_ids": [task_id],
                        "created_at": now,
                    }
                ],
            }
            self._conversations.append(conversation)
            self._tasks[_task_key(owner, task_id)] = {
                "id": task_id,
                "owner_id": owner,
                "conversation_id": conversation_id,
                "turn_id": turn_id,
                "kind": kind,
                "mode": "generate",
                "status": STATUS_QUEUED,
                "progress": "",
                "model": EDITABLE_FILE_MODEL,
                "request": {
                    "prompt": prompt,
                    "input_urls": [],
                },
                "result": {"items": []},
                "error": "",
                "created_at": now,
                "updated_at": now,
                "created_ts": time.time(),
            }
            self._save_conversations_locked()
            self._save_tasks_locked()
            task = _public_task(self._tasks[_task_key(owner, task_id)])
        threading.Thread(
            target=self._run_file_task,
            args=(_task_key(owner, task_id), kind, prompt, base64_images, dict(identity), base_url),
            daemon=True,
            name=f"{kind}-task-{task_id[:16]}",
        ).start()
        return task

    def resume_image_poll(self, identity: dict[str, object], task_id: str, extra_timeout_secs: float) -> dict[str, Any]:
        owner = _owner_id(identity)
        key = _task_key(owner, task_id)
        with self._lock:
            task = self._tasks.get(key)
            if not task:
                raise ValueError("task not found")
            task["status"] = STATUS_RUNNING
            task["error"] = ""
            task["updated_at"] = _now()
            self._save_tasks_locked()
            return _public_task(task)

    def _run_image_task(self, key: str, payload: dict[str, Any], identity: dict[str, object]) -> None:
        started = time.time()

        def progress(step: str) -> None:
            updates: dict[str, Any] = {"progress": step}
            if step == "image_stream_resolve_start":
                updates["started_ts"] = time.time()
            self._update_task(key, **updates)

        self._update_task(key, status=STATUS_RUNNING, error="", started_ts=started)
        try:
            with self._lock:
                task = self._tasks[key]
                mode = task.get("mode")
                model = task.get("model")
            handler = openai_v1_image_edit.handle if mode == "edit" else openai_v1_image_generations.handle
            result = handler({**payload, "progress_callback": progress})
            data = result.get("data") if isinstance(result, dict) else None
            if not isinstance(data, list) or not data:
                raise RuntimeError(_clean(result.get("message") if isinstance(result, dict) else "") or "图片生成失败")
            items = [
                {
                    "type": "image",
                    "url": item.get("url"),
                    "revised_prompt": item.get("revised_prompt") or "",
                }
                for item in data
                if isinstance(item, dict) and item.get("url")
            ]
            self._update_task(
                key,
                status=STATUS_SUCCESS,
                result={
                    "items": items,
                    "usage": result.get("usage") if isinstance(result, dict) else {},
                },
                error="",
                ended_ts=time.time(),
                duration_ms=int((time.time() - started) * 1000),
            )
            self._log_call(identity, "image", model, started, "图片生成完成", result={"items": items})
        except Exception as exc:
            self._update_task(
                key,
                status=STATUS_ERROR,
                error=str(exc) or "图片生成失败",
                ended_ts=time.time(),
                duration_ms=int((time.time() - started) * 1000),
            )
            self._log_call(identity, "image", payload.get("model"), started, "图片生成失败", status="failed", error=str(exc))

    def _run_file_task(self, key: str, kind: str, prompt: str, base64_images: list[str], identity: dict[str, object], base_url: str) -> None:
        started = time.time()
        self._update_task(key, status=STATUS_RUNNING, error="", started_ts=started)
        try:
            if kind == "psd" and not base64_images:
                raise ValueError("base64_images is empty")
            token = _editable_access_token()
            backend = OpenAIBackendAPI(account={"access_token": token})
            task_id = key.rsplit(":", 1)[-1]
            output_dir = EDITABLE_FILE_ROOT / kind / task_id
            result = backend.export_psd_zip(base64_images, prompt, output_dir) if kind == "psd" else backend.export_ppt_zip(base64_images, prompt, output_dir)
            account_service.mark_text_used(token)
            item = {
                "type": "file",
                "primary_url": _file_url(result.primary_path, base_url),
                "zip_url": _file_url(result.zip_path, base_url),
                "conversation_id": result.conversation_id,
            }
            self._update_task(
                key,
                status=STATUS_SUCCESS,
                result={"items": [item], **item},
                error="",
                ended_ts=time.time(),
                duration_ms=int((time.time() - started) * 1000),
            )
            self._log_call(identity, kind, EDITABLE_FILE_MODEL, started, f"{kind.upper()}生成完成", result=item)
        except Exception as exc:
            self._update_task(
                key,
                status=STATUS_ERROR,
                error=str(exc) or f"{kind}生成失败",
                ended_ts=time.time(),
                duration_ms=int((time.time() - started) * 1000),
            )
            self._log_call(identity, kind, EDITABLE_FILE_MODEL, started, f"{kind.upper()}生成失败", status="failed", error=str(exc))

    def _save_reference_images(self, images: list[tuple[bytes, str, str]], base_url: str) -> list[dict[str, str]]:
        refs = []
        for payload, filename, mime_type in images:
            stored = image_storage_service.save(payload, base_url=base_url)
            refs.append({
                "url": stored.url,
                "name": filename or "reference.png",
                "mime_type": mime_type or "image/png",
            })
        return refs

    def _public_conversation(self, conversation: dict[str, Any]) -> dict[str, Any]:
        turns = []
        for turn in conversation.get("turns") or []:
            tasks = [
                self._tasks[_task_key(conversation["owner_id"], task_id)]
                for task_id in turn.get("task_ids") or []
                if _task_key(conversation["owner_id"], task_id) in self._tasks
            ]
            public_tasks = [_public_task(task) for task in tasks]
            turns.append({
                **turn,
                "status": _turn_status(tasks),
                "tasks": public_tasks,
            })
        return {
            **conversation,
            "turns": turns,
        }

    def _find_conversation_locked(self, owner: str, conversation_id: str) -> dict[str, Any]:
        for item in self._conversations:
            if item.get("owner_id") == owner and item.get("id") == conversation_id:
                return item
        raise ValueError("conversation not found")

    def _get_or_create_conversation_locked(self, owner: str, conversation_id: str, kind: str, title: str, now: str) -> dict[str, Any]:
        for item in self._conversations:
            if item.get("owner_id") == owner and item.get("id") == conversation_id:
                return item
        item = {
            "id": conversation_id,
            "owner_id": owner,
            "kind": kind,
            "title": title,
            "created_at": now,
            "updated_at": now,
            "turns": [],
        }
        self._conversations.append(item)
        return item

    def _update_task(self, key: str, **updates: Any) -> None:
        with self._lock:
            task = self._tasks.get(key)
            if not task:
                return
            task.update(updates)
            task["updated_at"] = _now()
            task["updated_ts"] = time.time()
            self._save_tasks_locked()

    def _save_conversations_locked(self) -> None:
        self._conversations.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        _save_array(self.conversations_path, self._conversations)

    def _save_tasks_locked(self) -> None:
        items = sorted(self._tasks.values(), key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        _save_array(self.tasks_path, items)

    def _recover_unfinished_locked(self) -> bool:
        changed = False
        for task in self._tasks.values():
            if task.get("status") in UNFINISHED_STATUSES:
                task["status"] = STATUS_ERROR
                task["error"] = "服务已重启，未完成的任务已中断"
                task["updated_at"] = _now()
                task["ended_ts"] = time.time()
                changed = True
        return changed

    def _log_call(
        self,
        identity: dict[str, object],
        kind: str,
        model: object,
        started: float,
        summary: str,
        *,
        status: str = "success",
        error: str = "",
        result: dict[str, Any] | None = None,
    ) -> None:
        detail = {
            "key_id": identity.get("id"),
            "key_name": identity.get("name"),
            "role": identity.get("role"),
            "model": model,
            "started_at": datetime.fromtimestamp(started).strftime("%Y-%m-%d %H:%M:%S"),
            "ended_at": _now(),
            "duration_ms": int((time.time() - started) * 1000),
            "status": status,
            "kind": kind,
        }
        if error:
            detail["error"] = error
        if result:
            detail["result"] = result
        try:
            log_service.add(LOG_TYPE_CALL, summary, detail)
        except Exception:
            pass

    def public_file_path(self, relative_path: str) -> Path:
        raw = str(relative_path or "").replace("\\", "/").lstrip("/")
        path = (EDITABLE_FILE_ROOT / raw).resolve()
        path.relative_to(EDITABLE_FILE_ROOT.resolve())
        if not path.is_file():
            raise FileNotFoundError(raw)
        return path


task_service = TaskService()
