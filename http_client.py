"""OAuth transport for the existing public media HTTP contract."""
import json
from pathlib import Path
from urllib.parse import quote
import requests
from requests_toolbelt.multipart.encoder import MultipartEncoder
from .adapter import AdapterError, token, rectangle, share_url
from .auth import BASE, REGION, access_token


class OAuthClient:
    def __init__(self, language="en"):
        self.language = language

    def request(self, method, suffix, *, params=None, path=None, media_type=None):
        headers = {"Authorization": "Bearer " + access_token()}
        def send(data=None, as_json=False):
            try:
                with requests.request(method, f"{BASE}/media-api/{REGION}/v1{suffix}",
                        headers=headers, json=data if as_json else None, data=None if as_json else data,
                        timeout=(10, 180 if path else 60), allow_redirects=False, stream=True) as response:
                    if response.status_code != 200 or not response.headers.get("Content-Type", "").lower().startswith("application/json"):
                        raise AdapterError("response", self.language)
                    chunks, size = [], 0
                    for chunk in response.iter_content(65536):
                        size += len(chunk)
                        if size > 2 * 1024 * 1024:
                            raise AdapterError("response", self.language)
                        chunks.append(chunk)
                    value = json.loads(b"".join(chunks))
                    if not isinstance(value, dict) or type(value.get("code")) is not int:
                        raise AdapterError("response", self.language)
                    return value
            except requests.RequestException:
                raise AdapterError("network", self.language) from None
            except (ValueError, UnicodeError) as exc:
                if isinstance(exc, AdapterError):
                    raise
                raise AdapterError("response", self.language) from None
        if path is None:
            return send(params, as_json=method == "POST")
        source = Path(path)
        types = {".png":"image/png", ".jpg":"image/jpeg", ".jpeg":"image/jpeg", ".webp":"image/webp"} if media_type == "image" else {".mp4":"video/mp4", ".mov":"video/quicktime"}
        try:
            if source.suffix.lower() not in types or not source.is_file() or not 0 < source.stat().st_size <= (50 if media_type == "image" else 1024) * 1024 * 1024:
                raise AdapterError("invalid", self.language)
            with source.open("rb") as stream:
                form = MultipartEncoder(fields={**{k:str(v) for k,v in params.items()},
                    "file":("media" + source.suffix.lower(), stream, types[source.suffix.lower()])})
                headers["Content-Type"] = form.content_type
                return send(form)
        except OSError:
            raise AdapterError("invalid", self.language) from None

    def execute(self, action, file_path=None, operation_id=None, idempotency_key=None, rect=None,
                share_text=None, task_id=None, confirm_charge=False):
        if action in {"image", "video", "share"} and confirm_charge is not True:
            raise AdapterError("invalid", self.language)
        if action in {"image", "video"}:
            params = {"mediaType": action, "operationId": token(operation_id if action == "image" else idempotency_key, 64)}
            coords = rectangle(rect)
            if coords and action == "video":
                params["area"] = ",".join(map(str, coords))
            return self.request("POST", "/media", params=params, path=file_path, media_type=action)
        if action == "share":
            return self.request("POST", "/media", params={"mediaType":"share", "operationId":token(operation_id, 64), "sourceUrl":share_url(share_text)})
        if action in {"image_query", "video_query"}:
            task = token(task_id)
            kind = "image" if action == "image_query" else "video"
            return self.request("GET", f"/tasks/{kind}/{quote(task, safe='')}")
        raise AdapterError("invalid", self.language)
