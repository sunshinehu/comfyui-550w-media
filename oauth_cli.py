"""Run with ComfyUI's Python: python -m PACKAGE.oauth_cli connect|status|disconnect."""
import argparse
import base64
import hashlib
from http.server import HTTPServer, BaseHTTPRequestHandler
import secrets
import time
from urllib.parse import parse_qs, urlencode, urlparse
import webbrowser
from .auth import BASE, REGION, RESOURCE, SCOPE, SERVICE, vault, oauth_post, save, load


def connect():
    vault()  # Fail before authorization if safe storage is unavailable.
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    received = {}
    class Callback(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)
        def log_message(self, *_args):
            pass  # Never log authorization codes or callback URLs.
        def do_GET(self):
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            valid = parsed.path == "/callback" and params.get("state") == [state]
            if valid and len(params.get("code", [])) == 1 and 0 < len(params["code"][0]) <= 2048:
                received["code"] = params["code"][0]
            elif valid and params.get("error"):
                received["error"] = True
            self.send_response(200 if received else 400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"Return to ComfyUI's terminal." if received else b"Invalid callback.")
    with HTTPServer(("127.0.0.1", 0), Callback) as server:
        callback = f"http://127.0.0.1:{server.server_port}/callback"
        registration = oauth_post("/oauth2/register", dict(client_name=f"550W ComfyUI {REGION}",
            redirect_uris=[callback], token_endpoint_auth_method="none", grant_types=["authorization_code", "refresh_token"],
            response_types=["code"], scope=SCOPE, resource=RESOURCE))
        client_id = registration.get("client_id")
        if not isinstance(client_id, str) or not 1 <= len(client_id) <= 128:
            raise ValueError("Invalid registered client")
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        url = BASE + "/oauth2/authorize?" + urlencode(dict(client_id=client_id, redirect_uri=callback,
            response_type="code", scope=SCOPE, resource=RESOURCE, state=state,
            code_challenge=challenge, code_challenge_method="S256"))
        print("Authorize in the browser on this ComfyUI host. No media is submitted.")
        if not webbrowser.open(url):
            raise ValueError("Cannot open the host browser; use API Key on headless/remote hosts")
        deadline = time.monotonic() + 300
        server.timeout = 1
        while not received and time.monotonic() < deadline:
            server.handle_request()
        if "code" not in received:
            raise ValueError("Authorization cancelled or timed out; no credentials changed")
        result = oauth_post("/oauth2/token", dict(grant_type="authorization_code", client_id=client_id,
            redirect_uri=callback, code=received["code"], code_verifier=verifier, resource=RESOURCE))
        save(result, client_id)
        print(f"Connected {REGION}; select oauth on 550W nodes.")


def main():
    parser = argparse.ArgumentParser(description="550W ComfyUI account connection")
    parser.add_argument("command", choices=("connect", "status", "disconnect"))
    command = parser.parse_args().command
    try:
        if command == "connect":
            connect()
        elif command == "status":
            value = load()
            print(f"{REGION}: saved connection; access token " + ("valid" if value["expires_at"] > time.time() else "needs refresh"))
        else:
            value = load()
            oauth_post("/oauth2/revoke", dict(client_id=value["client_id"], token=value["refresh_token"], token_type_hint="refresh_token"))
            vault().delete_password(SERVICE, REGION)
            print(f"Disconnected {REGION}")
    except ValueError as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
