"""Host-owned credentials: explicit OAuth selection, never silent fallback."""
import json
import os
import threading
import time
from .adapter import Client
from .region import LANGUAGE

BASE = "https://www.550wai.cn"
REGION = "cn" if LANGUAGE == "zh-CN" else "global"
RESOURCE = f"{BASE}/media-api/{REGION}"
SCOPE = "credits:read tasks:read tasks:submit media:upload"
SERVICE = "550w-comfyui-oauth"
LOCK = threading.RLock()


def vault():
    import keyring
    backend = keyring.get_keyring()
    if type(backend).__module__ == "keyring.backends.chainer":
        backend = next((item for item in backend.backends if type(item).__module__.startswith(
            ("keyring.backends.macOS", "keyring.backends.Windows", "keyring.backends.SecretService"))), backend)
    # Reject plaintext/third-party fallback stores; unattended hosts must use API Key.
    if not type(backend).__module__.startswith(("keyring.backends.macOS", "keyring.backends.Windows", "keyring.backends.SecretService")):
        raise ValueError("Configure an OS credential store, or use API Key; plaintext OAuth storage is disabled")
    return backend


def load():
    with LOCK:
        raw = vault().get_password(SERVICE, REGION)
        if not raw:
            raise ValueError("Connect this regional node package using python -m <package>.oauth_cli connect")
        try:
            value = json.loads(raw)
            if value["region"] != REGION or not isinstance(value["expires_at"], (int, float)):
                raise ValueError()
            for key in ("client_id", "access_token", "refresh_token"):
                if not isinstance(value[key], str) or not value[key] or any(c in value[key] for c in "\r\n"):
                    raise ValueError()
            return value
        except (ValueError, KeyError, TypeError):
            raise ValueError("Invalid saved OAuth connection; reconnect") from None


def save(result, client_id, previous_refresh=None):
    expires = result.get("expires_in")
    access = result.get("access_token")
    refresh = result.get("refresh_token") or previous_refresh
    if type(expires) not in (int, float) or not 0 < expires <= 86400 or not all(isinstance(x, str) and x and not any(c in x for c in "\r\n") for x in (access, refresh, client_id)):
        raise ValueError("Invalid OAuth token response")
    value = dict(region=REGION, client_id=client_id, access_token=access,
                 refresh_token=refresh, expires_at=time.time() + expires)
    with LOCK:
        vault().set_password(SERVICE, REGION, json.dumps(value))
    return value


def oauth_post(path, params):
    import requests
    try:
        with requests.post(BASE + path, json=params if path.endswith("register") else None,
                           data=None if path.endswith("register") else params,
                           timeout=(10, 30), allow_redirects=False, stream=True) as response:
            if path == "/oauth2/revoke" and response.status_code == 200:
                return {}
            if response.status_code not in (200, 201) or not response.headers.get("Content-Type", "").startswith("application/json"):
                raise ValueError("OAuth request rejected; reconnect")
            chunks, size = [], 0
            for chunk in response.iter_content(8192):
                size += len(chunk)
                if size > 65536:
                    raise ValueError("OAuth response exceeds size limit")
                chunks.append(chunk)
            value = json.loads(b"".join(chunks))
            if not isinstance(value, dict) or value.get("error"):
                raise ValueError("OAuth request failed; reconnect")
            return value
    except (requests.RequestException, json.JSONDecodeError, UnicodeError):
        raise ValueError("OAuth connection failed; no automatic retry") from None


def access_token():
    with LOCK:
        value = load()
        if value["expires_at"] <= time.time() + 60:
            result = oauth_post("/oauth2/token", dict(grant_type="refresh_token", client_id=value["client_id"],
                                refresh_token=value["refresh_token"], resource=RESOURCE))
            value = save(result, value["client_id"], value["refresh_token"])
        return value["access_token"]


def client(language, auth_mode="api_key"):
    if auth_mode == "api_key":
        return Client(os.environ.get("FIFTYW_API_KEY"), os.environ.get("FIFTYW_USER_NO"), language)
    if auth_mode == "oauth":
        from .http_client import OAuthClient
        return OAuthClient(language)
    raise ValueError("Select api_key or oauth")
