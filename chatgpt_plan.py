"""ChatGPT plan sign-in for a single-user, locally run agent.

Uses OpenAI's documented public-client OAuth flow; credentials live in the
user profile, outside this project. This file never asks for a password.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import tempfile
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import jwt

ISSUER = "https://auth.openai.com"
RESOURCE = "https://api.openai.com/v1"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
STORE = Path(os.getenv("LOCALAPPDATA") or (Path.home() / ".config")) / "match4-agent-local" / "chatgpt-connection.json"


def _load():
    if not STORE.exists():
        return {}
    return json.loads(STORE.read_text(encoding="utf-8"))


def _save(record):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix="connection-", suffix=".tmp", dir=STORE.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(record, stream)
        os.chmod(name, 0o600)
        os.replace(name, STORE)
    finally:
        Path(name).unlink(missing_ok=True)


def _discovery():
    response = httpx.get(f"{ISSUER}/.well-known/openid-configuration", timeout=15)
    response.raise_for_status()
    provider = response.json()
    if provider.get("issuer") != ISSUER:
        raise RuntimeError("Unexpected sign-in provider.")
    for key in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        if (urlsplit(provider.get(key, "")).scheme != "https"
                or urlsplit(provider.get(key, "")).netloc != "auth.openai.com"):
            raise RuntimeError("Unexpected sign-in provider endpoint.")
    return provider


def _validated_identity(id_token, client_id, nonce, provider):
    header = jwt.get_unverified_header(id_token)
    accepted = set(provider.get("id_token_signing_alg_values_supported", [])) & {
        "RS256", "PS256", "ES256",
    }
    if header.get("alg") not in accepted or not isinstance(header.get("kid"), str):
        raise RuntimeError("Unsupported identity-token header.")

    # Fetch signing keys through the same TLS-verified HTTP client used for
    # OpenAI discovery and token exchange. PyJWKClient uses urllib instead,
    # which may use a different certificate store on Windows.
    response = httpx.get(provider["jwks_uri"], timeout=15)
    response.raise_for_status()
    keys = jwt.PyJWKSet.from_dict(response.json()).keys
    matching = [
        key for key in keys
        if key.key_id == header["kid"] and key.public_key_use in (None, "sig")
    ]
    if len(matching) != 1:
        raise RuntimeError("No unique OpenAI signing key matched the identity token.")
    identity = jwt.decode(
        id_token,
        matching[0].key,
        algorithms=[header["alg"]],
        issuer=provider["issuer"],
        audience=client_id,
        options={"require": ["sub", "exp", "iat", "iss", "aud"]},
        leeway=5,
    )
    if not hmac.compare_digest(str(identity.get("nonce", "")), nonce):
        raise RuntimeError("Sign-in nonce did not match.")
    if not isinstance(identity.get("sub"), str) or not identity["sub"]:
        raise RuntimeError("Sign-in did not provide a verified account ID.")
    return identity


def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def sign_in():
    record = _load()
    record.setdefault("ext_agent_host_id", f"urn:uuid:{uuid.uuid4()}")
    _save(record)
    provider = _discovery()
    state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    callback = {}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path != "/auth/callback":
                self.send_error(404)
                return
            callback.update({key: values[0] for key, values in parse_qs(parsed.query).items()})
            body = b"Sign-in received. Return to the terminal to see whether it succeeded."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass  # Callback query contains an authorization code.

    with HTTPServer(("127.0.0.1", 0), CallbackHandler) as listener:
        listener.timeout = 2
        redirect_uri = f"http://127.0.0.1:{listener.server_port}/auth/callback"
        existing = record.get("client_id")
        params = {
            "client_id": existing or "dynamic_agent_client",
            "ext_agent_host_id": record["ext_agent_host_id"],
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": SCOPES,
            "resource": RESOURCE,
            "state": state,
            "nonce": nonce,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
        }
        if not existing:
            params["agent_name_hint"] = "Match4 Local Agent"
        elif record.get("id_token"):
            params["id_token_hint"] = record["id_token"]
        url = provider["authorization_endpoint"] + "?" + urlencode(params)
        print("Opening your browser. Select your personal Plus account and approve plan use.")
        if not webbrowser.open(url):
            raise RuntimeError("Could not open the system browser for sign-in.")
        deadline = time.monotonic() + 180
        while not callback and time.monotonic() < deadline:
            listener.handle_request()

    if not callback:
        raise TimeoutError("Sign-in timed out. Run 'python local_agent.py login' again.")
    if not hmac.compare_digest(callback.get("state", ""), state):
        raise RuntimeError("Sign-in state did not match.")
    if callback.get("error"):
        raise RuntimeError("Sign-in was declined or unavailable for this account.")
    code = callback.get("code")
    client_id = existing or callback.get("client_id")
    if not code or not client_id or (existing and callback.get("client_id", existing) != existing):
        raise RuntimeError("Sign-in callback was incomplete or used another account.")
    token_response = httpx.post(
        provider["token_endpoint"],
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
            "resource": RESOURCE,
        },
        timeout=20,
    )
    token_response.raise_for_status()
    tokens = token_response.json()
    identity = _validated_identity(tokens["id_token"], client_id, nonce, provider)
    scopes = tokens.get("scope", "").split()
    if "chatgpt.tokens.use.direct" not in scopes:
        raise RuntimeError("ChatGPT plan use was not approved for this connection.")
    if existing and record.get("subject") and record["subject"] != identity["sub"]:
        raise RuntimeError("Sign-in returned a different account.")
    if (not tokens.get("access_token") or not tokens.get("refresh_token")
            or tokens.get("token_type", "").lower() != "bearer"):
        raise RuntimeError("ChatGPT plan credentials were not issued.")
    record.update({
        "client_id": client_id,
        "subject": identity["sub"],
        "email": identity.get("email", ""),
        "id_token": tokens["id_token"],
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "scopes": scopes,
        "expires_at": time.time() + int(tokens["expires_in"]),
    })
    _save(record)
    print("Connected:", record["email"] or "ChatGPT account")


_access_token_lock = Lock()


def _access_token_unlocked():
    record = _load()
    if "chatgpt.tokens.use.direct" not in record.get("scopes", []):
        raise RuntimeError("Run 'python local_agent.py login' first.")
    if time.time() < record.get("expires_at", 0) - 120:
        return record["access_token"]
    if not record.get("refresh_token"):
        raise RuntimeError("Session expired. Run 'python local_agent.py login' again.")
    response = httpx.post(
        _discovery()["token_endpoint"],
        data={
            "grant_type": "refresh_token",
            "client_id": record["client_id"],
            "refresh_token": record["refresh_token"],
            "resource": RESOURCE,
        },
        timeout=20,
    )
    if response.is_error:
        raise RuntimeError("Session could not be refreshed; run 'python local_agent.py login' again.")
    tokens = response.json()
    if not tokens.get("access_token") or not tokens.get("refresh_token"):
        raise RuntimeError("Refresh did not provide new credentials.")
    if tokens.get("scope") and "chatgpt.tokens.use.direct" not in tokens["scope"].split():
        raise RuntimeError("ChatGPT plan permission was withdrawn.")
    record.update({
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "expires_at": time.time() + int(tokens["expires_in"]),
    })
    if tokens.get("scope"):
        record["scopes"] = tokens["scope"].split()
    _save(record)
    return record["access_token"]


def access_token():
    # A refresh rotates credentials. Only one worker may refresh at a time.
    with _access_token_lock:
        return _access_token_unlocked()


def available_models():
    response = httpx.get(
        f"{RESOURCE}/models",
        headers={"Authorization": f"Bearer {access_token()}"},
        timeout=20,
    )
    response.raise_for_status()
    return [
        {"slug": item["slug"], "display_name": item.get("display_name", item["slug"])}
        for item in response.json()["models"]
        if item.get("visibility") == "list" and isinstance(item.get("slug"), str)
    ]



