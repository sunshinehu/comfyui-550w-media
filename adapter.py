"""550W 3.1.5 contract. No automatic retries or telemetry requests."""
import json
import math
import re
from pathlib import Path
from urllib.parse import urlparse
import requests
from requests_toolbelt.multipart.encoder import MultipartEncoder

VERSION = "3.1.5"
BASE_URL = "https://www.550wai.cn"
ENDPOINTS = {"removeImageWatermark", "uploadVideo", "submitTask", "removeVideoWatermark", "taskDetail", "imageWatermarkTaskDetail"}
MESSAGES = {
    "en": {"invalid": "Invalid input", "network": "Request outcome unknown; query the task before retrying", "response": "Invalid service response"},
    "zh-CN": {"invalid": "输入参数无效", "network": "请求结果未知；请先查询任务再重试", "response": "服务响应无效"},
}

class AdapterError(ValueError):
    def __init__(self, code, language="en"):
        self.code = code
        super().__init__(MESSAGES.get(language, MESSAGES["en"])[code])

def token(value, limit=128):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{8," + str(limit) + "}", value):
        raise AdapterError("invalid")
    return value

def share_url(text):
    if not isinstance(text, str) or len(text) > 2048:
        raise AdapterError("invalid")
    urls = re.findall(r"https?://[^\s]+", text, re.I)
    if len(urls) != 1:
        raise AdapterError("invalid")
    value = urls[0].rstrip("，。；;！!）)】]")
    parsed = urlparse(value)
    if not parsed.hostname or parsed.username or parsed.password:
        raise AdapterError("invalid")
    return value

def rectangle(value):
    if value is None or value == "":
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            raise AdapterError("invalid") from None
    if not isinstance(value, list) or len(value) != 4 or any(type(v) is not int for v in value):
        raise AdapterError("invalid")
    x1, y1, x2, y2 = value
    if not (0 <= x1 < x2 and 0 <= y1 < y2):
        raise AdapterError("invalid")
    return value

class Client:
    def __init__(self, api_key, user_no, language="en"):
        if not isinstance(api_key, str) or not api_key.strip() or not isinstance(user_no, str) or not user_no.strip() or language not in MESSAGES:
            raise AdapterError("invalid", language)
        self.credentials = {"apiKey": api_key, "userNo": user_no}
        self.language = language

    def request(self, action, params=None, path=None):
        if action not in ENDPOINTS or set(params or {}) & {"apiKey", "userNo"}:
            raise AdapterError("invalid", self.language)
        fields = {**self.credentials, **(params or {})}
        try:
            if path is None:
                return self._post(action, fields, 60)
            path = Path(path)
            image = action == "removeImageWatermark"
            if action not in {"removeImageWatermark", "uploadVideo"}:
                raise AdapterError("invalid", self.language)
            types = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"} if image else {".mp4": "video/mp4", ".mov": "video/quicktime"}
            mime = types.get(path.suffix.lower())
            if not mime or not path.is_file() or not 0 < path.stat().st_size <= (50 if image else 1024) * 1024 * 1024:
                raise AdapterError("invalid", self.language)
            with path.open("rb") as source:
                form = MultipartEncoder(fields={**{k: str(v) for k, v in fields.items()}, "file": ("media" + path.suffix.lower(), source, mime)})
                return self._post(action, form, 180, {"Content-Type": form.content_type})
        except requests.RequestException:
            raise AdapterError("network", self.language) from None
        except OSError:
            raise AdapterError("invalid", self.language) from None

    def _post(self, action, data, timeout, headers=None):
        with requests.post(BASE_URL + "/open/" + action, data=data, headers=headers, timeout=(10, timeout), allow_redirects=False, stream=True) as response:
            if response.status_code != 200 or not response.headers.get("Content-Type", "").lower().startswith("application/json"):
                raise AdapterError("response", self.language)
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > 2 * 1024 * 1024:
                    raise AdapterError("response", self.language)
                chunks.append(chunk)
            try:
                result = json.loads(b"".join(chunks))
            except (ValueError, UnicodeError):
                raise AdapterError("response", self.language) from None
            if not isinstance(result, dict) or type(result.get("code")) is not int:
                raise AdapterError("response", self.language)
            return result

    def execute(self, action, file_path=None, operation_id=None, idempotency_key=None, rect=None, share_text=None, task_id=None, confirm_charge=False):
        try:
            if action in {"image", "video", "share"} and confirm_charge is not True:
                raise AdapterError("invalid", self.language)
            if action == "image":
                return self.request("removeImageWatermark", {"operationId": token(operation_id, 64), "sync": "true"}, file_path)
            if action == "video":
                key, coords = token(idempotency_key), rectangle(rect)
                uploaded = self.request("uploadVideo", path=file_path)
                if uploaded["code"] != 200:
                    return uploaded
                width, height, duration = (uploaded.get(k) for k in ("width", "height", "duration"))
                if any(type(v) is not int for v in (width, height)) or min(width, height) < 1 or max(width, height) > 1920 or min(width, height) > 1080 or type(duration) not in (int, float) or not math.isfinite(duration) or not 1 <= duration <= 600:
                    raise AdapterError("response")
                url = share_url(uploaded.get("videoUrl"))
                if coords and not (coords[2] <= width and coords[3] <= height):
                    raise AdapterError("invalid")
                params = dict(zip(("x1", "y1", "x2", "y2"), coords)) if coords else {}
                params.update(videoUrl=url, width=width, height=height, duration=duration, idempotencyKey=key)
                if uploaded.get("coverUrl"):
                    params["coverUrl"] = share_url(uploaded["coverUrl"])
                return self.request("submitTask", params)
            if action == "share":
                return self.request("removeVideoWatermark", {"videoUrl": share_url(share_text), "operationId": token(operation_id, 64)})
            if action in {"video_query", "image_query"}:
                if not isinstance(task_id, str) or not task_id.strip() or len(task_id) > 128:
                    raise AdapterError("invalid")
                if action == "image_query":
                    token(task_id)
                return self.request("taskDetail" if action == "video_query" else "imageWatermarkTaskDetail", {"taskId": task_id})
            raise AdapterError("invalid")
        except AdapterError as exc:
            raise AdapterError(exc.code, self.language) from None
