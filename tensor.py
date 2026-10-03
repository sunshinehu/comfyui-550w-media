"""Native ComfyUI IMAGE input; only one explicitly selected image per submission."""
from pathlib import Path
from tempfile import TemporaryDirectory
from .adapter import Client, AdapterError
from .region import LANGUAGE
from .auth import client as account_client
import os
import json

class ImageTensor:
    CATEGORY = "550W"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("result_json",)
    FUNCTION = "run"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image": ("IMAGE",), "operation_id": ("STRING", {"default": ""}),
            "confirm_charge": ("BOOLEAN", {"default": False}),
            "language": (["en", "zh-CN"], {"default": os.environ.get("FIFTYW_LANGUAGE", LANGUAGE)})},
            "optional": {"auth_mode": (["api_key", "oauth"], {"default": "api_key"})}}

    def run(self, image, operation_id, confirm_charge, language, auth_mode="api_key"):
        if confirm_charge is not True:
            raise AdapterError("invalid", language)
        shape = image.shape
        if len(shape) != 4 or shape[0] != 1 or shape[3] not in (3, 4) or min(shape[1:3]) < 1 or shape[1]*shape[2] > 40_000_000:
            raise AdapterError("invalid", language)
        # Pillow, numpy and torch belong to the host ComfyUI runtime; no second torch installation.
        import numpy as np
        from PIL import Image
        array = image[0].detach().cpu().numpy()
        if not np.isfinite(array).all():
            raise AdapterError("invalid", language)
        pixels = np.clip(array * 255, 0, 255).astype(np.uint8)
        client = account_client(language, auth_mode)
        with TemporaryDirectory(prefix="550w-comfyui-") as directory:
            path = Path(directory) / "image.png"
            Image.fromarray(pixels).save(path)
            result = client.execute("image", file_path=str(path), operation_id=operation_id, confirm_charge=True)
        return (json.dumps(result, ensure_ascii=False),)
