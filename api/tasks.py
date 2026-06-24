from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api.image_inputs import parse_image_edit_request, read_image_sources
from api.support import require_identity, resolve_image_base_url
from services.content_filter import check_request
from services.task_service import task_service


class ImageTurnRequest(BaseModel):
    conversation_id: str = ""
    prompt: str = Field(..., min_length=1)
    model: str = "gpt-image-2"
    size: str = ""
    quality: str = "auto"
    count: int = Field(default=1, ge=1, le=10)
    ratio: str = "1:1"
    tier: str = "1k"


class EditableTaskRequest(BaseModel):
    prompt: str = ""
    base64_images: list[str] = Field(default_factory=list)


class RenameRequest(BaseModel):
    title: str = Field(..., min_length=1)


class ResumePollRequest(BaseModel):
    extra_timeout_secs: float = Field(default=30.0, ge=5.0, le=120.0)


def _task_ids(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def create_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/conversations")
    async def list_conversations(kind: str = Query(default="image"), authorization: str | None = Header(default=None)):
        identity = require_identity(authorization)
        return {"items": await run_in_threadpool(task_service.list_conversations, identity, kind)}

    @router.get("/api/conversations/{conversation_id}")
    async def get_conversation(conversation_id: str, authorization: str | None = Header(default=None)):
        identity = require_identity(authorization)
        try:
            return await run_in_threadpool(task_service.get_conversation, identity, conversation_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail={"error": str(exc)}) from exc

    @router.post("/api/conversations/{conversation_id}/rename")
    async def rename_conversation(conversation_id: str, body: RenameRequest, authorization: str | None = Header(default=None)):
        identity = require_identity(authorization)
        try:
            return await run_in_threadpool(task_service.rename_conversation, identity, conversation_id, body.title)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail={"error": str(exc)}) from exc

    @router.delete("/api/conversations/{conversation_id}")
    async def delete_conversation(conversation_id: str, authorization: str | None = Header(default=None)):
        identity = require_identity(authorization)
        return await run_in_threadpool(task_service.delete_conversation, identity, conversation_id)

    @router.delete("/api/conversations")
    async def clear_conversations(kind: str = Query(default="image"), authorization: str | None = Header(default=None)):
        identity = require_identity(authorization)
        return await run_in_threadpool(task_service.clear_conversations, identity, kind)

    @router.delete("/api/conversations/{conversation_id}/turns/{turn_id}/{part}")
    async def delete_turn_part(conversation_id: str, turn_id: str, part: str, authorization: str | None = Header(default=None)):
        if part not in {"prompt", "results"}:
            raise HTTPException(status_code=400, detail={"error": "part must be prompt or results"})
        identity = require_identity(authorization)
        try:
            return await run_in_threadpool(task_service.delete_turn_part, identity, conversation_id, turn_id, part)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail={"error": str(exc)}) from exc

    @router.get("/api/tasks")
    async def list_tasks(
        ids: str = Query(default=""),
        kind: str = Query(default=""),
        authorization: str | None = Header(default=None),
    ):
        identity = require_identity(authorization)
        return await run_in_threadpool(task_service.list_tasks, identity, _task_ids(ids), kind)

    @router.post("/api/image-turns/generations")
    async def create_image_generation_turn(body: ImageTurnRequest, request: Request, authorization: str | None = Header(default=None)):
        identity = require_identity(authorization)
        await run_in_threadpool(check_request, body.prompt)
        return await run_in_threadpool(
            task_service.submit_image_turn,
            identity,
            conversation_id=body.conversation_id,
            mode="generate",
            prompt=body.prompt,
            model=body.model,
            size=body.size,
            quality=body.quality,
            count=body.count,
            ratio=body.ratio,
            tier=body.tier,
            base_url=resolve_image_base_url(request),
        )

    @router.post("/api/image-turns/edits")
    async def create_image_edit_turn(request: Request, authorization: str | None = Header(default=None)):
        identity = require_identity(authorization)
        payload, image_sources, _ = await parse_image_edit_request(request)
        prompt = str(payload["prompt"])
        await run_in_threadpool(check_request, prompt)
        images = await read_image_sources(image_sources)
        return await run_in_threadpool(
            task_service.submit_image_turn,
            identity,
            conversation_id=str(payload.get("conversation_id") or ""),
            mode="edit",
            prompt=prompt,
            model=str(payload["model"]),
            size=str(payload.get("size") or ""),
            quality=str(payload.get("quality") or "auto"),
            count=int(payload.get("count") or 1),
            ratio=str(payload.get("ratio") or "1:1"),
            tier=str(payload.get("tier") or "1k"),
            base_url=resolve_image_base_url(request),
            images=images,
        )

    @router.post("/api/{kind}/tasks")
    async def create_editable_task(kind: str, body: EditableTaskRequest, request: Request, authorization: str | None = Header(default=None)):
        if kind not in {"ppt", "psd"}:
            raise HTTPException(status_code=404, detail={"error": "task kind not found"})
        identity = require_identity(authorization)
        await run_in_threadpool(check_request, body.prompt)
        return await run_in_threadpool(
            task_service.submit_file_task,
            identity,
            kind=kind,
            prompt=body.prompt,
            base64_images=body.base64_images,
            base_url=resolve_image_base_url(request),
        )

    @router.post("/api/tasks/{task_id}/resume-poll")
    async def resume_image_poll(task_id: str, body: ResumePollRequest, authorization: str | None = Header(default=None)):
        identity = require_identity(authorization)
        try:
            return await run_in_threadpool(task_service.resume_image_poll, identity, task_id, body.extra_timeout_secs)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc

    @router.get("/files/{file_path:path}")
    async def download_editable_file(file_path: str):
        try:
            path = await run_in_threadpool(task_service.public_file_path, file_path)
        except Exception as exc:
            raise HTTPException(status_code=404, detail={"error": "file not found"}) from exc
        return FileResponse(path, filename=path.name)

    return router
