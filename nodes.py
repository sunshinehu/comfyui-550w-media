import json
import os
from pathlib import Path
from .adapter import Client, AdapterError
from .tensor import ImageTensor
from .results import ImageResult
from .region import LANGUAGE
from .auth import client as account_client

class MediaNode:
    CATEGORY = "550W"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("result_json",)
    FUNCTION = "run"
    OUTPUT_NODE = True
    action = ""
    fields = {}
    @classmethod
    def INPUT_TYPES(cls):
        required = {"language": (["zh-CN", "en"], {"default": os.environ.get("FIFTYW_LANGUAGE", LANGUAGE)}), **cls.fields}
        if cls.action in {"image", "video", "share"}:
            required["confirm_charge"] = ("BOOLEAN", {"default": False})
        return {"required": required, "optional": {"auth_mode": (["api_key", "oauth"], {"default": "api_key"})}}
    def run(self, language, auth_mode="api_key", **kwargs):
        # Credentials intentionally stay out of saved workflow widgets.
        client = account_client(language, auth_mode)
        if "file" in kwargs:
            import folder_paths
            selected = kwargs.pop("file")
            root = Path(folder_paths.get_input_directory()).resolve()
            path = Path(folder_paths.get_annotated_filepath(selected)).resolve()
            if not path.is_relative_to(root):
                raise AdapterError("invalid", language)
            kwargs["file_path"] = str(path)
        return (json.dumps(client.execute(self.action, **kwargs), ensure_ascii=False),)

def uploaded_files(suffixes):
    import folder_paths
    root = Path(folder_paths.get_input_directory())
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and p.suffix.lower() in suffixes)

class ImageUpload(MediaNode):
    action = "image"
    @classmethod
    def INPUT_TYPES(cls):
        cls.fields = {"file": (uploaded_files({".png", ".jpg", ".jpeg", ".webp"}), {"image_upload": True}),
                      "operation_id": ("STRING", {"default": ""})}
        return super().INPUT_TYPES()

class VideoUpload(MediaNode):
    action = "video"
    @classmethod
    def INPUT_TYPES(cls):
        cls.fields = {"file": (uploaded_files({".mp4", ".mov"}), {}),
                      "idempotency_key": ("STRING", {"default": ""}),
                      "rect": ("STRING", {"default": "", "multiline": False})}
        return super().INPUT_TYPES()

class ShareResolve(MediaNode):
    action = "share"
    fields = {"share_text": ("STRING", {"multiline": True}),
              "operation_id": ("STRING", {"default": ""})}

class VideoQuery(MediaNode):
    action = "video_query"
    fields = {"task_id": ("STRING", {"default": ""})}
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

class ImageQuery(VideoQuery):
    action = "image_query"

NODE_CLASS_MAPPINGS = {
    "FiftyWImageTensor": ImageTensor,
    "FiftyWImageUpload": ImageUpload, "FiftyWVideoUpload": VideoUpload,
    "FiftyWShareResolve": ShareResolve, "FiftyWVideoQuery": VideoQuery,
    "FiftyWImageQuery": ImageQuery,
    "FiftyWImageResult": ImageResult,
}
_zh = os.environ.get("FIFTYW_LANGUAGE", LANGUAGE) == "zh-CN"
NODE_DISPLAY_NAME_MAPPINGS = dict(zip(NODE_CLASS_MAPPINGS,
    ["550W 原生图片擦除", "550W 图片去水印", "550W 视频上传与提交", "550W 分享链接解析", "550W 视频任务查询", "550W 图片任务查询", "550W 图片结果"]
    if _zh else ["550W Native Image Erase", "550W Remove Image Watermark", "550W Upload and Submit Video", "550W Resolve Share Link", "550W Video Task Query", "550W Image Task Query", "550W Image Result"]))
