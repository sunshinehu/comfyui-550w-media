# 550W Watermark & Text Eraser

Native ComfyUI nodes for image watermark/text erasure, full-frame video
subtitle/watermark erasure, and supported TikTok/X share-link resolution.
Copy a link using the original app or website's Share action.

## Installation and account

Place the node directory under ComfyUI/custom_nodes, install requirements.txt
using ComfyUI's Python interpreter, and restart ComfyUI. Python 3.11+ is required.
ComfyUI provides torch, numpy and Pillow; this package does not install a second
torch runtime. A GPU is not required by these remote-service nodes.

Configure FIFTYW_API_KEY and FIFTYW_USER_NO in the ComfyUI process environment.
Credentials are not stored in workflow widgets. API Key management:
https://eraser.550wai.com/api/ . Credits: https://eraser.550wai.com/purchase/ .
Both API Key and OAuth are supported. Existing workflows default to api_key;
select oauth explicitly on processing/query nodes. OAuth never silently falls
back to a different API Key account. The interface language does not change region.

For OAuth, install with ComfyUI's Python, then from custom_nodes run:
`python -m 550w-media.oauth_cli connect` (replace the package name with
the actual installed node directory name). A browser on the ComfyUI host opens
the regional authorization page. A temporary 127.0.0.1 callback closes after
five minutes. The callback must run on the same machine as the browser; remote
and headless deployments should use API Key unless configured with a supported
desktop credential store and browser. Do not expose this callback externally.

OAuth uses dynamic public-client registration, S256 PKCE and state verification.
Credentials are stored in macOS Keychain, Windows Credential Manager or Linux
Secret Service, never in workflow JSON or plaintext fallback files. Run the
same command with `status` to inspect connection presence or `disconnect` to
revoke the refresh token and remove the regional connection. Failed revocation
keeps the local connection so you can retry. Expired access tokens refresh
before the request; rejected/unknown media submissions are never automatically
replayed. Use one ComfyUI process per regional OAuth connection. This is a
host-account connection, not per-browser-user isolation: do not expose an
authorized ComfyUI instance to untrusted users.

## Workflow

- Connect a single IMAGE to Native Image Erase, or select an uploaded image.
- For video, place an MP4/MOV in ComfyUI's input directory and select it.
  Default erasure is full-frame. Optional rect is [x1,y1,x2,y2] in pixels.
- Charged submissions require confirm_charge=true and a stable operation ID
  (8-64 characters for image/share; retain the same ID when recovering a request).
- Submission outputs are service JSON. Query the returned task ID before
  considering an asynchronous task completed. Connect completed image JSON to
  Image Result and then to Preview Image or Save Image. Image Result accepts
  only successful image results on the 550W image host and sends no account
  credentials when downloading. Video/share outputs retain their result URLs;
  video tensor decoding is not claimed. This is not yet a released Registry package.
- Do not automatically resubmit an unknown timeout outcome. If share resolution
  succeeds but the media cannot be downloaded, retain the resolved video URL
  for downloading in a browser rather than returning the original share link.

Uploaded images are limited to 50 MiB and videos to 1 GiB. The existing video
API Key pipeline validates returned metadata (1-600 seconds, supported resolution);
OAuth uploads delegate preparation and validation to the existing server pipeline.
Only process media you own or have permission to edit. Remote processing may
consume account credits; installing the node itself does not charge credits.

## Privacy

Selected media, supplied share links, and required account credentials are sent
to the fixed HTTPS 550W service. IMAGE conversion uses a temporary PNG which is
removed after the attempt. No additional telemetry requests or automatic paid
retries are made. Task/payment facts remain owned by the existing server.
Privacy: https://eraser.550wai.com/privacy/ . Support: support@550wai.com .

## China distribution

The separately built Chinese package uses Chinese labels and introduction,
https://qzm.550wai.cn/api-keys for API Key management and
https://qzm.550wai.cn/purchase?tab=speed for credits. It is a self-distribution
package with independent node ID node-550w-media-cn; the international node ID
is node-550w-media. Registry publication is verified separately. Region is not changed
by choosing an interface language. Both packages use the same processing service.
