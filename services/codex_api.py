from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Iterator
from urllib.parse import urlparse

from utils.helper import UpstreamHTTPError
from utils.log import logger


CODEX_RESPONSES_MODEL = "gpt-5.5"
CODEX_RESPONSES_INSTRUCTIONS = (
    "Use the image_generation tool to create exactly one image for the user's request. "
    "Return the generated image result."
)


class CodexAPI:
    def __init__(self, base_url: str, access_token: str, model: str) -> None:
        self.base_url = str(base_url or "https://chatgpt.com").rstrip("/")
        self.access_token = str(access_token or "").strip()
        self.model = str(model or CODEX_RESPONSES_MODEL).strip()

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _responses_path(self) -> str:
        parsed = urlparse(self.base_url)
        host = parsed.netloc.lower()
        if host == "chatgpt.com" or host.endswith(".chatgpt.com"):
            return "/backend-api/codex/responses"
        if parsed.path.rstrip("/").endswith("/v1"):
            return "/responses"
        return "/v1/responses"

    @staticmethod
    def _image_input(prompt: str, images: list[str]) -> list[Dict[str, Any]]:
        content: list[Dict[str, Any]] = [{"type": "input_text", "text": prompt}]
        for image in images:
            payload = image if image.startswith("data:image/") else f"data:image/png;base64,{image}"
            content.append({"type": "input_image", "image_url": payload})
        return [{"role": "user", "content": content}]

    @staticmethod
    def _body_preview(body: Any, limit: int = 4000) -> str:
        if isinstance(body, (dict, list)):
            try:
                text = json.dumps(body, ensure_ascii=False)
            except Exception:
                text = repr(body)
        else:
            text = str(body or "")
        return text if len(text) <= limit else text[:limit] + "...[truncated]"

    @staticmethod
    def _event_image_result_lengths(value: Any) -> list[int]:
        if isinstance(value, dict):
            lengths: list[int] = []
            if value.get("type") == "image_generation_call" and isinstance(value.get("result"), str):
                lengths.append(len(value["result"]))
            for item in value.values():
                lengths.extend(CodexAPI._event_image_result_lengths(item))
            return lengths
        if isinstance(value, list):
            lengths: list[int] = []
            for item in value:
                lengths.extend(CodexAPI._event_image_result_lengths(item))
            return lengths
        return []

    @staticmethod
    def _event_summary(event: Dict[str, Any]) -> Dict[str, Any]:
        summary: Dict[str, Any] = {
            "type": str(event.get("type") or ""),
            "keys": list(event.keys())[:30],
        }
        for key in ("id", "status", "sequence_number", "response_id", "item_id", "output_index", "content_index"):
            value = event.get(key)
            if isinstance(value, (str, int, float, bool)) or value is None:
                summary[key] = value
        for key in ("response", "item", "output"):
            value = event.get(key)
            if isinstance(value, dict):
                summary[f"{key}_type"] = value.get("type")
                summary[f"{key}_status"] = value.get("status")
                summary[f"{key}_keys"] = list(value.keys())[:30]
            elif isinstance(value, list):
                summary[f"{key}_len"] = len(value)
                summary[f"{key}_types"] = [
                    item.get("type") for item in value[:10] if isinstance(item, dict)
                ]
        error = event.get("error")
        if isinstance(error, dict):
            summary["error"] = {
                key: error.get(key)
                for key in ("type", "code", "message")
                if error.get(key) is not None
            }
        delta = event.get("delta")
        if isinstance(delta, str):
            summary["delta_len"] = len(delta)
            summary["delta_preview"] = delta[:200]
        result_lengths = CodexAPI._event_image_result_lengths(event)
        if result_lengths:
            summary["image_result_lengths"] = result_lengths[:10]
        return summary

    def _log_response_failure(
            self,
            path: str,
            status_code: int,
            headers: Any,
            payload: Dict[str, Any],
            body: Any,
    ) -> None:
        request_headers = self._headers()
        safe_request_headers = {
            key: value for key, value in request_headers.items() if key.lower() != "authorization"
        }
        response_headers = dict(headers.items()) if hasattr(headers, "items") else dict(headers or {})
        tool = ((payload.get("tools") or [{}])[0]) if isinstance(payload.get("tools"), list) else {}
        logger.warning({
            "event": "codex_responses_http_error",
            "path": path,
            "status_code": status_code,
            "request": {
                "model": payload.get("model"),
                "tool_model": tool.get("model"),
                "tool_action": tool.get("action"),
                "size": tool.get("size"),
                "quality": tool.get("quality"),
                "image_input_count": max(len((payload.get("input") or [{}])[0].get("content") or []) - 1, 0),
                "prompt_preview": self._body_preview(
                    (((payload.get("input") or [{}])[0].get("content") or [{}])[0].get("text") or ""),
                    500,
                ),
                "headers": safe_request_headers,
            },
            "response": {
                "headers": response_headers,
                "body_preview": self._body_preview(body),
            },
        })

    @staticmethod
    def _iter_response_events(raw: Any) -> Iterator[Dict[str, Any]]:
        content_type = str(raw.headers.get("content-type") or "").lower()
        text = raw.read().decode("utf-8", "replace")
        status_code = getattr(raw, "status", None)
        parse_errors: list[str] = []
        events: list[Dict[str, Any]] = []
        if "application/json" in content_type:
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    events.append(data)
            except Exception as exc:
                parse_errors.append(str(exc))
        else:
            lines: list[str] = []
            for line in text.splitlines() + [""]:
                if not line:
                    if lines:
                        payload_text = "\n".join(lines).strip()
                        if payload_text and payload_text != "[DONE]":
                            try:
                                data = json.loads(payload_text)
                            except Exception as exc:
                                parse_errors.append(str(exc))
                                data = None
                            if isinstance(data, dict):
                                events.append(data)
                        lines = []
                elif line.startswith("data:"):
                    lines.append(line[5:].lstrip())

        event_types: Dict[str, int] = {}
        image_result_lengths: list[int] = []
        for event in events:
            event_type = str(event.get("type") or "<missing>")
            event_types[event_type] = event_types.get(event_type, 0) + 1
            image_result_lengths.extend(CodexAPI._event_image_result_lengths(event))
        logger.info({
            "event": "codex_responses_response_debug",
            "status_code": status_code,
            "content_type": content_type,
            "response_text_len": len(text),
            "event_count": len(events),
            "event_types": event_types,
            "image_result_lengths": image_result_lengths[:10],
            "parse_error_count": len(parse_errors),
            "parse_errors": parse_errors[:5],
            "event_summaries": [CodexAPI._event_summary(event) for event in events[:30]],
            "event_previews": [
                CodexAPI._body_preview(event, 1500)
                for event in events[:10]
            ] if not image_result_lengths else [],
            "body_preview": text[:1000] if not events else "",
        })
        for event in events:
            yield event

    def iter_image_response_events(
            self,
            prompt: str,
            images: list[str] | None = None,
            size: str | None = None,
            quality: str = "auto",
    ) -> Iterator[Dict[str, Any]]:
        if not self.access_token:
            raise RuntimeError("access_token is required for codex image endpoints")
        path = self._responses_path()
        payload = {
            "model": self.model,
            "instructions": CODEX_RESPONSES_INSTRUCTIONS,
            "store": False,
            "input": self._image_input(prompt, images or []),
            "tools": [{
                "type": "image_generation",
                "model": "gpt-image-2",
                "action": "edit" if images else "generate",
                "size": str(size or "1024x1024"),
                "quality": str(quality or "auto"),
                "output_format": "png",
            }],
            "tool_choice": {"type": "image_generation"},
            "stream": True,
        }
        request = urllib.request.Request(
            self.base_url + path,
            json.dumps(payload).encode(),
            self._headers(),
            method="POST",
        )
        tool = payload["tools"][0]
        logger.info({
            "event": "codex_responses_request_debug",
            "url": self.base_url + path,
            "transport": "urllib.request",
            "timeout_secs": 1200,
            "request": {
                "model": payload.get("model"),
                "tool_model": tool.get("model"),
                "tool_action": tool.get("action"),
                "size": tool.get("size"),
                "quality": tool.get("quality"),
                "output_format": tool.get("output_format"),
                "stream": payload.get("stream"),
                "image_input_count": max(len((payload.get("input") or [{}])[0].get("content") or []) - 1, 0),
                "prompt_preview": self._body_preview(
                    (((payload.get("input") or [{}])[0].get("content") or [{}])[0].get("text") or ""),
                    500,
                ),
            },
            "headers": {
                key: value for key, value in self._headers().items()
                if key.lower() != "authorization"
            },
        })
        try:
            with urllib.request.urlopen(request, timeout=1200) as raw:
                yield from self._iter_response_events(raw)
        except urllib.error.HTTPError as error:
            body_text = error.read().decode("utf-8", "replace")
            body: Any = body_text
            try:
                body = json.loads(body_text)
            except Exception:
                pass
            self._log_response_failure(path, error.code, error.headers, payload, body)
            retry_after_header = error.headers.get("Retry-After") if error.headers else None
            retry_after = int(retry_after_header) if str(retry_after_header or "").isdigit() else None
            raise UpstreamHTTPError(path, error.code, body, retry_after=retry_after) from error
