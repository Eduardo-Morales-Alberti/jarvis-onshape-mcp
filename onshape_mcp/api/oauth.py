"""Onshape OAuth 2.0 authorization code flow.

Run `onshape-mcp --auth` once to authenticate. Tokens are stored at
~/.config/onshape-mcp/oauth_tokens.json and refreshed automatically.
"""

import json
import os
import sys
import time
import secrets
import threading
import urllib.parse
import webbrowser
from dataclasses import dataclass, asdict
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional

import httpx

ONSHAPE_AUTH_URL = "https://oauth.onshape.com/oauth/authorize"
ONSHAPE_TOKEN_URL = "https://oauth.onshape.com/oauth/token"
ONSHAPE_SCOPES = "OAuth2Read OAuth2Write"
AUTH_TIMEOUT = 120  # seconds to wait for browser callback
# Fixed callback port — must match the Redirect URL registered in your Onshape OAuth app.
# Override with ONSHAPE_OAUTH_PORT env var if you used a different port.
DEFAULT_CALLBACK_PORT = 8765


def _token_file() -> str:
    config_dir = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return os.path.join(config_dir, "onshape-mcp", "oauth_tokens.json")


@dataclass
class OAuthTokens:
    access_token: str
    refresh_token: str
    expires_at: float  # Unix timestamp
    client_id: str = ""
    client_secret: str = ""


def load_tokens() -> Optional[OAuthTokens]:
    path = _token_file()
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        # Accept files that predate client_id/client_secret fields.
        data.setdefault("client_id", "")
        data.setdefault("client_secret", "")
        return OAuthTokens(**data)
    except Exception:
        return None


def save_tokens(tokens: OAuthTokens) -> None:
    path = _token_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(asdict(tokens), f, indent=2)
    os.chmod(path, 0o600)



class _CallbackHandler(BaseHTTPRequestHandler):
    """One-shot HTTP handler that captures the OAuth redirect."""

    # Class-level dict shared across instances; populated by the first callback.
    result: dict = {}
    # Expected CSRF state, set by run_auth_flow before the server starts.
    expected_state: str = ""

    def do_GET(self):
        if not self.path.startswith("/callback"):
            self.send_response(404)
            self.end_headers()
            return

        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        # Reject callbacks whose state doesn't match — guards against CSRF
        # and stray requests hitting the local callback port.
        returned_state = params.get("state", [""])[0]
        if returned_state != _CallbackHandler.expected_state:
            _CallbackHandler.result["error"] = "state_mismatch"
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Authentication failed: state mismatch</h2></body></html>"
            )
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return

        if "code" in params:
            _CallbackHandler.result["code"] = params["code"][0]
            body = (
                b"<html><body><h2>Authentication successful!</h2>"
                b"<p>You can close this window and return to the terminal.</p></body></html>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)
        elif "error" in params:
            err = params.get("error", ["unknown"])[0]
            _CallbackHandler.result["error"] = err
            body = (
                f"<html><body><h2>Authentication failed: {err}</h2>"
                f"<p>You can close this window.</p></body></html>"
            ).encode()
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)

        # Shut down the server from a background thread so this handler can return first.
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def log_message(self, format, *args):  # noqa: A002
        pass  # suppress access-log noise


def _exchange_code(
    client_id: str, client_secret: str, code: str, redirect_uri: str
) -> OAuthTokens:
    resp = httpx.post(
        ONSHAPE_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()
    return OAuthTokens(
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        expires_at=time.time() + data.get("expires_in", 3600),
        client_id=client_id,
        client_secret=client_secret,
    )


def refresh_access_token(
    client_id: str, client_secret: str, refresh_token: str
) -> OAuthTokens:
    """Exchange a refresh token for a new access token (synchronous)."""
    resp = httpx.post(
        ONSHAPE_TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()
    return OAuthTokens(
        access_token=data["access_token"],
        # Onshape may or may not rotate the refresh token; keep old one if absent.
        refresh_token=data.get("refresh_token", refresh_token),
        expires_at=time.time() + data.get("expires_in", 3600),
        client_id=client_id,
        client_secret=client_secret,
    )


def run_auth_flow(client_id: str, client_secret: str) -> OAuthTokens:
    """Run the interactive OAuth authorization code flow.

    Opens the user's browser, starts a local callback server, waits for
    Onshape to redirect back, exchanges the code for tokens, and saves them.

    The redirect URI sent to Onshape is ``http://localhost:{port}/callback`` where
    ``port`` defaults to DEFAULT_CALLBACK_PORT (8765). This must match exactly the
    Redirect URL registered in your Onshape OAuth app.
    """
    port = int(os.environ.get("ONSHAPE_OAUTH_PORT", DEFAULT_CALLBACK_PORT))
    redirect_uri = f"http://localhost:{port}/callback"
    state = secrets.token_urlsafe(16)

    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": ONSHAPE_SCOPES,
            "state": state,
        }
    )
    auth_url = f"{ONSHAPE_AUTH_URL}?{query}"

    _CallbackHandler.result = {}
    _CallbackHandler.expected_state = state
    server = HTTPServer(("localhost", port), _CallbackHandler)

    print("\nOpening Onshape authorization page in your browser...", file=sys.stderr)
    print(
        f"If the browser does not open automatically, visit:\n  {auth_url}\n",
        file=sys.stderr,
    )
    webbrowser.open(auth_url)
    print(f"Waiting for authorization ({AUTH_TIMEOUT}s timeout)...", file=sys.stderr)

    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()

    deadline = time.time() + AUTH_TIMEOUT
    while time.time() < deadline:
        time.sleep(0.3)
        if _CallbackHandler.result:
            break
    else:
        server.shutdown()
        raise TimeoutError(f"OAuth authorization timed out after {AUTH_TIMEOUT} seconds.")

    if "error" in _CallbackHandler.result:
        raise RuntimeError(f"OAuth authorization failed: {_CallbackHandler.result['error']}")

    tokens = _exchange_code(client_id, client_secret, _CallbackHandler.result["code"], redirect_uri)
    save_tokens(tokens)
    print("Authentication successful! Tokens saved.", file=sys.stderr)
    return tokens
