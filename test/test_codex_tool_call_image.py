import unittest

from services.config import config
from services.protocol.codex_api import CodexAPI
from test.utils import save_image

channel = next((
    c for c in config.list_enabled_codex_channels()
    if str(c.get("type") or "") != "system" and c.get("base_url") and c.get("api_key")
), None)
api_v1 = CodexAPI(
    str(channel.get("base_url") or ""),
    str(channel.get("api_key") or ""),
    str(channel.get("upstream_model") or "gpt-5.5"),
    version="v1",
) if channel else None
api_v2 = CodexAPI(
    str(channel.get("base_url") or ""),
    str(channel.get("api_key") or ""),
    str(channel.get("upstream_model") or "gpt-5.5"),
    version="v2",
) if channel else None

PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAIAAAAlC+aJAAAAWElEQVR4nO3PQQ3AIADAQMDN4JNK"
    "cBcWSPedrU2HGfC9ZwPg1wJYAcwAZgAzgBnADGAGMAOYAcwAZgAzgBnADGAGMAOYAcwAZgAzgBnA"
    "DGAGMAOYAcwA5gUbAULdrIhVAAAAAElFTkSuQmCC"
)


class ToolCallImageTests(unittest.TestCase):
    def test_v1_tool_call_image_1k(self) -> None:
        print("v1 tool_call image 1k start")
        image = api_v1.generate_image({
            "prompt": "Generate a clean detailed 1K image, no text.",
            "size": "1024x1024",
        })
        print("v1 tool_call image 1k results: 1")
        print(f"v1 tool_call image 1k saved: {save_image(image, 'v1_tool_call_image_1k')}")

    def test_v1_tool_call_image_2k(self) -> None:
        print("v1 tool_call image 2k start")
        image = api_v1.generate_image({
            "prompt": "Generate a clean detailed 2K image, no text.",
            "size": "2048x2048",
        })
        print("v1 tool_call image 2k results: 1")
        print(f"v1 tool_call image 2k saved: {save_image(image, 'v1_tool_call_image_2k')}")

    def test_v1_tool_call_image_4k(self) -> None:
        print("v1 tool_call image 4k start")
        image = api_v1.generate_image({
            "prompt": "Generate a clean detailed 4K UHD image, no text.",
            "size": "3840x2160",
        })
        print("v1 tool_call image 4k results: 1")
        print(f"v1 tool_call image 4k saved: {save_image(image, 'v1_tool_call_image_4k')}")

    def test_v1_edit_image(self):
        print("v1 edit image start")
        image = api_v1.generate_image({
            "prompt": "Edit this image into a clean blue app icon with no text.",
            "images": [PNG_DATA_URL],
            "size": "1024x1024",
        })
        print("v1 edit image results: 1")
        print(f"v1 edit image saved: {save_image(image, 'v1_tool_call_edit_image')}")

    def test_v2_tool_call_image_1k(self) -> None:
        print("v2 tool_call image 1k start")
        image = api_v2.generate_image({
            "prompt": "Generate a clean detailed 1K image, no text.",
            "size": "1024x1024",
        })
        print("v2 tool_call image 1k results: 1")
        print(f"v2 tool_call image 1k saved: {save_image(image, 'v2_tool_call_image_1k')}")

    def test_v2_tool_call_image_2k(self) -> None:
        print("v2 tool_call image 2k start")
        image = api_v2.generate_image({
            "prompt": "Generate a clean detailed 2K image, no text.",
            "size": "2048x2048",
        })
        print("v2 tool_call image 2k results: 1")
        print(f"v2 tool_call image 2k saved: {save_image(image, 'v2_tool_call_image_2k')}")

    def test_v2_tool_call_image_4k(self) -> None:
        print("v2 tool_call image 4k start")
        image = api_v2.generate_image({
            "prompt": "Generate a clean detailed 4K UHD image, no text.",
            "size": "3840x2160",
        })
        print("v2 tool_call image 4k results: 1")
        print(f"v2 tool_call image 4k saved: {save_image(image, 'v2_tool_call_image_4k')}")

    def test_v2_edit_image(self):
        print("v2 edit image start")
        image = api_v2.generate_image({
            "prompt": "Edit this image into a clean green app icon with no text.",
            "images": [PNG_DATA_URL],
            "size": "1024x1024",
        })
        print("v2 edit image results: 1")
        print(f"v2 edit image saved: {save_image(image, 'v2_tool_call_edit_image')}")


if __name__ == "__main__":
    unittest.main()
