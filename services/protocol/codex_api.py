from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

import httpx

from services.proxy_service import proxy_settings
from utils.log import logger

default_model = "gpt-5.5"
instructions = "Use the image_generation tool to create exactly one image for the user's request.Return the generated image result."


class CodexAPI:
    """
    本文件是 codex 反代 2api 使用，利用 image_gen 工具调用来生图（需要 Free 层级及以上才可以使用）。
    方式一：有 Free 层级以上的账号的 Codex 登录 access_token 即可。
      老版本中，codex 使用 https://chatgpt.com/backend-api/codex/responses 生图，可流式调用，
      注意：之前可出 1k 2k 4k，目前已无法指定尺寸，对应 version=v1。
      新版本中，codex 使用 https://chatgpt.com/backend-api/codex/images/generations 以及
      https://chatgpt.com/backend-api/codex/images/edits 生图/编辑图，对应 version=v2。
      注意：这个现在也没办法指定尺寸了。
    方式二：利用中转站的工具调用 image_gen 工具来生图，走 responses 即可，原理就是上面的工具调用
           如果中非流一般会被中转站的Cloudflare 120s 限制，这边使用流式调用。
    """

    def __init__(self, base_url: str, access_token: str, model: str = default_model, version: str = "v1") -> None:
        """初始化 Codex 上游地址、鉴权 token、模型和接口版本。"""
        self.base_url = str(base_url or "https://chatgpt.com").strip().rstrip("/")
        self.access_token = access_token
        self.model = model
        self.version = version

    def generate_image(self, options: dict[str, Any]) -> str:
        """
        根据图片生成参数生成图片，返回图片 base64 内容。
        options 参数：
          prompt: 图片生成提示词。
          images: 可选参考图列表，支持 data URL 或纯 base64。
          size: 可选图片尺寸。
          quality: 可选图片质量，默认 auto。
        """
        url = self._request_path(options)
        body = self._request_body(options)
        data = self._post(url, body)
        image = self._image_from_response(data)
        if not image:
            raise RuntimeError("No image result found in response")
        return image

    def _request_path(self, options: dict[str, Any]) -> str:
        """按当前上游、版本和是否有参考图获取完整请求地址。"""
        images = options.get("images") or []
        if self._is_chatgpt() and self.version == "v2":
            path = "/backend-api/codex/images/edits" if images else "/backend-api/codex/images/generations"
            return self.base_url + path
        if self._is_chatgpt():
            return self.base_url + "/backend-api/codex/responses"
        path = "/responses" if urlparse(self.base_url).path.rstrip("/").endswith("/v1") else "/v1/responses"
        return self.base_url + path

    def _request_body(self, options: dict[str, Any]) -> dict[str, Any]:
        """按当前上游和版本组装请求体。"""
        prompt = str(options.get("prompt") or "")
        images = options.get("images") or []
        size = options.get("size")
        quality = options.get("quality") or "auto"
        if self._is_chatgpt() and self.version == "v2":
            body = {
                "prompt": prompt,
                "model": "gpt-image-2",
                "size": size or "auto",
                "quality": quality or "auto",
                "output_format": "png",
            }
            image_urls = self._image_urls(images)
            if image_urls:
                body["image"] = image_urls
            return body

        content = [
                      {
                          "type": "input_text",
                          "text": prompt,
                      }
                  ] + [
                      {
                          "type": "input_image",
                          "image_url": item,
                      }
                      for item in self._image_urls(images)
                  ]
        return {
            "model": self.model,
            "instructions": instructions,
            "store": False,
            "input": [
                {
                    "role": "user",
                    "content": content,
                }
            ],
            "tools": [
                {
                    "type": "image_generation",
                    "model": "gpt-image-2",
                    "action": "edit" if images else "generate",
                    "size": size or "3840x2160",
                    "quality": quality or "auto",
                    "output_format": "png",
                }
            ],
            "tool_choice": {
                "type": "image_generation",
            },
            "stream": True,
        }

    def _post(self, url: str, body: dict[str, Any]) -> Any:
        """向上游发送流式 JSON 请求，并返回解析后的响应事件。"""
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        proxy_url = proxy_settings.get_profile(upstream=True).proxy_url
        kwargs: dict[str, Any] = {
            "json": body,
            "headers": headers,
            "timeout": 1200,
        }
        if proxy_url:
            kwargs["proxy"] = proxy_url
        events = []
        with httpx.stream("POST", url, **kwargs) as response:
            if response.status_code >= 400:
                body = response.read().decode("utf-8", "replace")
                raise RuntimeError(f"HTTP {response.status_code}: {body[:1000]}")
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                return response.json()
            try:
                for line in response.iter_lines():
                    logger.debug(line)
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    event = json.loads(data)
                    events.append(event)
                    if self._image_from_response(event):
                        return events
            except httpx.RemoteProtocolError:
                if self._image_from_response(events):
                    return events
                raise RuntimeError("Upstream stream closed before image result")
        return events

    def _is_chatgpt(self) -> bool:
        """判断当前 base_url 是否为 ChatGPT 官方域名。"""
        host = urlparse(self.base_url).netloc.lower()
        return host == "chatgpt.com" or host.endswith(".chatgpt.com")

    def _image_urls(self, images: list[str]) -> list[str]:
        """将传入图片统一转换成接口可接受的 data URL 格式。"""
        return [
            item if item.startswith("data:image/") else f"data:image/png;base64,{item}"
            for item in images
        ]

    def _image_from_response(self, data: Any) -> str:
        """从不同接口形态的响应中提取图片 base64 内容。"""
        image = ""
        if isinstance(data, dict):
            if data.get("data"):
                item = data["data"][0]
                image = (
                        item.get("b64_json") or
                        item.get("base64") or
                        item.get("image") or
                        ""
                )
            if not image and data.get("type") == "image_generation_call":
                image = data.get("result") or ""
            if not image and data.get("item"):
                image = self._image_from_response(data.get("item"))
            if not image:
                outputs = data.get("output", [])
                for output in outputs:
                    image = self._image_from_response(output)
                    if image:
                        break
            if not image:
                image = data.get("result") or data.get("image") or ""
        if not image and isinstance(data, list):
            for item in data:
                image = self._image_from_response(item)
                if image:
                    break
        if isinstance(image, str) and image.startswith("data:image/"):
            return image.split(",", 1)[1]
        return str(image or "").strip()
