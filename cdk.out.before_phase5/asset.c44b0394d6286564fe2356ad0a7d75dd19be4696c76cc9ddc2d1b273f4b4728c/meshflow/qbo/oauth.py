from __future__ import annotations

import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from intuitlib.client import AuthClient
from intuitlib.enums import Scopes
from intuitlib.exceptions import AuthClientError

from meshflow.config import QBOSettings
from meshflow.qbo.token_store import QBOTokens, save_tokens


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    auth_code: str | None = None
    realm_id: str | None = None
    error: str | None = None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path != "/callback":
            self.send_error(404)
            return

        if "error" in params:
            _OAuthCallbackHandler.error = params["error"][0]
        else:
            _OAuthCallbackHandler.auth_code = params.get("code", [None])[0]
            _OAuthCallbackHandler.realm_id = params.get("realmId", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if _OAuthCallbackHandler.error:
            body = f"<h1>QuickBooks connection failed</h1><p>{_OAuthCallbackHandler.error}</p>"
        else:
            body = "<h1>QuickBooks connected</h1><p>You can close this tab and return to the terminal.</p>"
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, format: str, *args) -> None:
        return


def _build_auth_client(settings: QBOSettings) -> AuthClient:
    return AuthClient(
        settings.client_id,
        settings.client_secret,
        settings.redirect_uri,
        settings.environment,
    )


def _oauth_server_address(redirect_uri: str) -> tuple[str, int]:
    """Return a local bind address for the temporary OAuth callback server."""
    parsed = urlparse(redirect_uri)
    port = parsed.port or 8080
    hostname = (parsed.hostname or "localhost").lower()

    if hostname in {"localhost", "127.0.0.1", "::1"}:
        # Windows can fail binding to "localhost" when it resolves to IPv6.
        return "127.0.0.1", port

    raise ValueError(
        f"QBO_REDIRECT_URI {redirect_uri!r} is not a local callback URL. "
        "For scripts/qbo_auth.py use http://localhost:8080/callback "
        "(or http://127.0.0.1:8080/callback) in Secrets Manager and your Intuit app."
    )


def connect_quickbooks(settings: QBOSettings, *, open_browser: bool = True) -> QBOTokens:
    """Run the OAuth authorization-code flow and persist tokens locally."""
    auth_client = _build_auth_client(settings)
    auth_url = auth_client.get_authorization_url([Scopes.ACCOUNTING])

    host, port = _oauth_server_address(settings.redirect_uri)

    server = HTTPServer((host, port), _OAuthCallbackHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    print(f"Open this URL if your browser does not launch automatically:\n{auth_url}\n")
    if open_browser:
        webbrowser.open(auth_url)

    thread.join(timeout=300)
    server.server_close()

    if _OAuthCallbackHandler.error:
        raise RuntimeError(f"QuickBooks OAuth failed: {_OAuthCallbackHandler.error}")
    if not _OAuthCallbackHandler.auth_code or not _OAuthCallbackHandler.realm_id:
        raise RuntimeError("Timed out waiting for QuickBooks OAuth callback on /callback")

    try:
        auth_client.get_bearer_token(
            _OAuthCallbackHandler.auth_code,
            realm_id=_OAuthCallbackHandler.realm_id,
        )
    except AuthClientError as exc:
        raise RuntimeError(f"Token exchange failed: {exc}") from exc

    tokens = QBOTokens(
        access_token=auth_client.access_token,
        refresh_token=auth_client.refresh_token,
        realm_id=auth_client.realm_id,
        token_type=getattr(auth_client, "token_type", "bearer") or "bearer",
        expires_in=getattr(auth_client, "expires_in", None),
    )
    save_tokens(settings.token_path, tokens)
    return tokens


def refresh_access_token(settings: QBOSettings, tokens: QBOTokens) -> QBOTokens:
    auth_client = _build_auth_client(settings)
    auth_client.refresh(refresh_token=tokens.refresh_token)

    refreshed = QBOTokens(
        access_token=auth_client.access_token,
        refresh_token=auth_client.refresh_token,
        realm_id=tokens.realm_id,
        token_type=getattr(auth_client, "token_type", "bearer") or "bearer",
        expires_in=getattr(auth_client, "expires_in", None),
    )
    save_tokens(settings.token_path, refreshed)
    return refreshed
