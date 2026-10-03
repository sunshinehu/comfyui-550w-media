"""Native IMAGE output from completed 550W image tasks, without account headers."""
import io
import json
import warnings
from urllib.parse import urlparse
import requests


def completed_image_url(result_json):
    try:
        result = json.loads(result_json)
        data = result.get("data") if isinstance(result.get("data"), dict) else result
        if result.get("code") != 200 or data.get("status") != "success":
            raise ValueError()
        url = data.get("resultUrl")
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "i.550wai.cn" or parsed.port not in (None, 443) or parsed.username or parsed.password:
            raise ValueError()
        return url
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Supply JSON from a completed 550W image task; pending tasks are not image results") from None


class ImageResult:
    CATEGORY = "550W"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"result_json": ("STRING", {"multiline": True, "forceInput": True})}}

    def run(self, result_json):
        url = completed_image_url(result_json)
        try:
            with requests.get(url, timeout=(10, 60), allow_redirects=False, stream=True) as response:
                if response.status_code != 200:
                    raise ValueError("Image download failed; query the existing task or use its result URL")
                content = bytearray()
                for chunk in response.iter_content(65536):
                    content.extend(chunk)
                    if len(content) > 50 * 1024 * 1024:
                        raise ValueError("Image result exceeds 50 MiB")
            from PIL import Image, ImageOps
            import numpy as np
            import torch
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(content)) as image:
                    if image.width * image.height > 40_000_000:
                        raise ValueError("Image result exceeds pixel limit")
                    pixels = np.array(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.float32) / 255.0
            return (torch.from_numpy(pixels).unsqueeze(0),)
        except requests.RequestException:
            raise ValueError("Image download failed; use the result URL without resubmitting a paid task") from None
