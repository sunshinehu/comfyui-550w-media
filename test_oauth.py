import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse, urlencode
from urllib.request import urlopen
from urllib.error import HTTPError

name = "fiftyw_test_comfy"
if name not in sys.modules:
    root = Path(__file__).parent
    spec = importlib.util.spec_from_file_location(name, root / "__init__.py", submodule_search_locations=[str(root)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
from fiftyw_test_comfy import auth, oauth_cli
from fiftyw_test_comfy.http_client import OAuthClient


class OAuthTests(unittest.TestCase):
    def test_old_default_and_explicit_selection(self):
        with patch.dict("os.environ", {"FIFTYW_API_KEY":"test-key", "FIFTYW_USER_NO":"test-user"}):
            self.assertIsInstance(auth.client("en"), auth.Client)
            self.assertIsInstance(auth.client("en", "oauth"), OAuthClient)
            with self.assertRaises(ValueError):
                auth.client("en", "automatic")

    def test_confirmation_precedes_token_access(self):
        with patch("fiftyw_test_comfy.http_client.access_token") as access:
            with self.assertRaises(ValueError):
                OAuthClient().execute("video", idempotency_key="stable-id")
            access.assert_not_called()

    def test_http_area_and_full_frame_contract(self):
        with patch.object(OAuthClient, "request", return_value={"code":200}) as call:
            OAuthClient().execute("video", file_path="test.mp4", idempotency_key="stable-id", rect="[1,2,30,40]", confirm_charge=True)
            self.assertEqual(call.call_args.kwargs["params"]["area"], "1,2,30,40")
            OAuthClient().execute("video", file_path="test.mp4", idempotency_key="stable-id", confirm_charge=True)
            self.assertNotIn("area", call.call_args.kwargs["params"])

    def test_region_bound_storage_and_refresh_once(self):
        store = MagicMock()
        value = dict(region=auth.REGION, client_id="client", access_token="access", refresh_token="refresh", expires_at=0)
        store.get_password.return_value = json.dumps(value)
        with patch.object(auth,"vault",return_value=store), patch.object(auth,"oauth_post",return_value=dict(access_token="new-access",refresh_token="new-refresh",expires_in=300)) as request:
            self.assertEqual(auth.access_token(), "new-access")
            self.assertEqual(request.call_args.args[1]["resource"], auth.RESOURCE)
            saved = json.loads(store.set_password.call_args.args[2])
            self.assertEqual(saved["refresh_token"], "new-refresh")
            value["region"] = "cn" if auth.REGION == "global" else "global"
            store.get_password.return_value = json.dumps(value)
            with self.assertRaises(ValueError):
                auth.load()

    def test_rejected_request_never_replayed(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status_code = 401
        with patch("fiftyw_test_comfy.http_client.access_token",return_value="fake-access"), patch("fiftyw_test_comfy.http_client.requests.request", return_value=response) as request:
            with self.assertRaises(ValueError):
                OAuthClient().execute("share",share_text="https://example.com/share",operation_id="stable-id",confirm_charge=True)
            self.assertEqual(request.call_count,1)
            self.assertFalse(request.call_args.kwargs["allow_redirects"])
            self.assertNotIn("apiKey", request.call_args.kwargs["json"])

    def test_loopback_pkce_and_wrong_state_rejected(self):
        import base64
        import hashlib
        calls = []
        def post(path, params):
            calls.append((path,params))
            return {"client_id":"test-client"} if path.endswith("register") else dict(access_token="fake-access",refresh_token="fake-refresh",expires_in=300)
        def browser(url):
            import threading
            params = parse_qs(urlparse(url).query)
            self.assertEqual(params["code_challenge_method"],["S256"])
            self.assertEqual(params["resource"],[auth.RESOURCE])
            callback = params["redirect_uri"][0]
            self.assertEqual(urlparse(callback).hostname,"127.0.0.1")
            def send():
                try:
                    urlopen(callback + "?" + urlencode(dict(state="wrong",code="bad"))).close()
                except HTTPError as error:
                    self.assertEqual(error.code,400)
                urlopen(callback + "?" + urlencode(dict(state=params["state"][0],code="test-code"))).close()
            thread = threading.Thread(target=send)
            thread.start()
            return True
        with patch.object(oauth_cli,"vault"),patch.object(oauth_cli,"oauth_post",side_effect=post),patch.object(oauth_cli,"save") as save,patch.object(oauth_cli.webbrowser,"open",side_effect=browser),patch("sys.stdout",new_callable=io.StringIO):
            oauth_cli.connect()
            self.assertEqual(calls[1][1]["code"],"test-code")
            self.assertGreaterEqual(len(calls[1][1]["code_verifier"]),43)
            save.assert_called_once()

    def test_plaintext_store_rejected(self):
        import keyring
        class Plaintext:
            pass
        with patch.object(keyring,"get_keyring",return_value=Plaintext()):
            with self.assertRaises(ValueError):
                auth.vault()

    def test_multipart_stream_uses_http_contract_without_open_credentials(self):
        from tempfile import TemporaryDirectory
        response = MagicMock()
        response.__enter__.return_value = response
        response.status_code = 200
        response.headers = {"Content-Type":"application/json"}
        response.iter_content.return_value = [b'{"code":200,"taskId":"test-task"}']
        with TemporaryDirectory() as directory:
            image = Path(directory) / "image.png"
            image.write_bytes(b"test-image")
            with patch("fiftyw_test_comfy.http_client.access_token",return_value="fake-access"),patch("fiftyw_test_comfy.http_client.requests.request",return_value=response) as request:
                result = OAuthClient().execute("image",file_path=str(image),operation_id="stable-id",confirm_charge=True)
                self.assertEqual(result["code"],200)
                call = request.call_args
                self.assertEqual(call.args[1],f"{auth.BASE}/media-api/{auth.REGION}/v1/media")
                fields = call.kwargs["data"].fields
                self.assertEqual(fields["mediaType"],"image")
                self.assertNotIn("apiKey",fields)
                self.assertNotIn("sync",fields)
                self.assertEqual(call.kwargs["headers"]["Authorization"],"Bearer fake-access")
                self.assertTrue(fields["file"][1].closed)

    def test_revocation_failure_preserves_connection(self):
        store=MagicMock()
        with patch.object(oauth_cli,"load",return_value=dict(client_id="client",refresh_token="fake-refresh")),patch.object(oauth_cli,"vault",return_value=store),patch.object(oauth_cli,"oauth_post",side_effect=ValueError("revocation failed")),patch("sys.argv",["oauth_cli","disconnect"]),patch("sys.stderr",new_callable=io.StringIO):
            with self.assertRaises(SystemExit):
                oauth_cli.main()
            store.delete_password.assert_not_called()


if __name__ == "__main__":
    unittest.main()
