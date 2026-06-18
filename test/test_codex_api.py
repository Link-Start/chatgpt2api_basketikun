from __future__ import annotations

import base64
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.codex_api import CODEX_RESPONSES_MODEL, CodexAPI


BASE_URL = "xxx"
ACCESS_TOKEN = "sk-xxx"
MODEL = CODEX_RESPONSES_MODEL
PROMPT = "生成一张简洁的未来城市夜景插画，霓虹灯，16:9。"
SIZE = "1024x1024"
QUALITY = "auto"
OUTPUT_DIR = Path("data/files/codex-test")


def extract_images(value: Any) -> list[str]:
    if isinstance(value, dict):
        if value.get("type") == "image_generation_call" and isinstance(value.get("result"), str):
            result = value["result"].strip()
            if result:
                return [result.split(",", 1)[1] if result.startswith("data:image/") else result]
        images: list[str] = []
        for item in value.values():
            images.extend(extract_images(item))
        return images
    if isinstance(value, list):
        images: list[str] = []
        for item in value:
            images.extend(extract_images(item))
        return images
    return []


def save_images(images: list[str], output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    paths: list[Path] = []
    for index, image in enumerate(images, 1):
        path = output_dir / f"codex-api-{stamp}-{index}.png"
        path.write_bytes(base64.b64decode(image))
        paths.append(path)
    return paths


def main() -> None:
    if not ACCESS_TOKEN.strip():
        raise ValueError("ACCESS_TOKEN is required")

    api = CodexAPI(
        base_url=BASE_URL,
        access_token=ACCESS_TOKEN,
        model=MODEL,
    )
    events = list(api.iter_image_response_events(
        prompt=PROMPT,
        size=SIZE,
        quality=QUALITY,
    ))
    images = extract_images(events)
    if not images:
        raise RuntimeError("No image result found in response")

    paths = save_images(images, OUTPUT_DIR)
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
