import os
for proxy_key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'):
    os.environ.pop(proxy_key, None)
from types import SimpleNamespace
from unittest.mock import patch
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from decision import ChatGPTPlanModel
from retrieval import fetch_page

calls = []
class FakeStream:
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def __iter__(self):
        yield SimpleNamespace(type="response.output_text.delta", delta='{"ok": true}')
        yield SimpleNamespace(type="response.completed")
class FakeClient:
    def __init__(self, **kwargs):
        assert kwargs["base_url"] == "https://api.openai.com/v1"
        assert kwargs["api_key"] == "test-token"
        self.responses = self
    def create(self, **kwargs):
        calls.append(kwargs)
        return FakeStream()
with patch("decision.access_token", return_value="test-token"), patch("decision.OpenAI", FakeClient):
    reply = ChatGPTPlanModel("test-model").generate([
        {"role": "system", "content": "Reply in JSON"},
        {"role": "user", "content": '{"question":"sample"}'},
    ])
assert reply == '{"ok": true}'
assert calls[0]["store"] is False and calls[0]["stream"] is True
assert calls[0]["instructions"] == "Reply in JSON"
assert calls[0]["input"] == [{"role": "user", "content": '{"question":"sample"}'}]
print("Model request contract: PASS")

server = ThreadingHTTPServer(("127.0.0.1", 0),
    partial(SimpleHTTPRequestHandler, directory=str(Path("test_site").resolve())))
Thread(target=server.serve_forever, daemon=True).start()
try:
    page = fetch_page(f"http://127.0.0.1:{server.server_port}/checkpoint4-admission-table.html")
    assert "Adult" in page["text"] and "12 EUR" in page["text"]
    print("Local HTML + table retrieval: PASS")
finally:
    server.shutdown()
    server.server_close()



# Exercise loopback OAuth handling without contacting OpenAI or saving real tokens.
import json
import tempfile
import urllib.request
from urllib.parse import parse_qs, urlencode, urlsplit
from unittest.mock import patch
import chatgpt_plan

with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
    simulated_store = Path(temp_dir) / "credentials.json"
    provider = {
        "issuer": "https://auth.openai.com",
        "authorization_endpoint": "https://auth.openai.com/api/accounts/authorize",
        "token_endpoint": "https://auth.openai.com/api/accounts/oauth/token",
        "jwks_uri": "https://auth.openai.com/.well-known/jwks.json",
    }
    def fake_browser(url):
        params = parse_qs(urlsplit(url).query)
        assert params["client_id"] == ["dynamic_agent_client"]
        assert "chatgpt.tokens.use.direct" in params["scope"][0]
        def callback():
            args = urlencode({"code": "mock-code", "state": params["state"][0],
                              "client_id": "oaiapp_mock"})
            urllib.request.urlopen(params["redirect_uri"][0] + "?" + args, timeout=5).read()
        Thread(target=callback, daemon=True).start()
        return True
    def fake_exchange(url, data, timeout):
        assert data["grant_type"] == "authorization_code"
        assert data["client_id"] == "oaiapp_mock"
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"id_token": "mock-id", "access_token": "mock-access",
                          "refresh_token": "mock-refresh", "token_type": "Bearer",
                          "scope": "chatgpt.tokens.use.direct offline_access",
                          "expires_in": 3600},
        )
    with patch.object(chatgpt_plan, "STORE", simulated_store), \
            patch.object(chatgpt_plan, "_discovery", return_value=provider), \
            patch.object(chatgpt_plan, "_validated_identity",
                         return_value={"sub": "mock-sub", "email": "mock@example.test"}), \
            patch.object(chatgpt_plan.webbrowser, "open", side_effect=fake_browser), \
            patch.object(chatgpt_plan.httpx, "post", side_effect=fake_exchange):
        chatgpt_plan.sign_in()
        saved = json.loads(simulated_store.read_text())
        assert saved["client_id"] == "oaiapp_mock"
        assert saved["ext_agent_host_id"].startswith("urn:uuid:")
        assert chatgpt_plan.access_token() == "mock-access"
print("Loopback sign-in and credential save: PASS")




# Verify JWT signature/audience/nonce checks with a locally signed token.
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
from jwt import encode
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
identity_provider = {
    "issuer": "https://auth.openai.com",
    "jwks_uri": "https://auth.openai.com/.well-known/jwks.json",
    "id_token_signing_alg_values_supported": ["RS256"],
}
claims = {
    "sub": "mock-sub",
    "iss": identity_provider["issuer"],
    "aud": "oaiapp_mock",
    "nonce": "nonce-123",
    "iat": int(__import__("time").time()),
    "exp": int(__import__("time").time()) + 300,
}
token = encode(claims, key, algorithm="RS256", headers={"kid": "mock-kid"})
public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
public_jwk.update({"kid": "mock-kid", "use": "sig"})
jwks_response = SimpleNamespace(
    raise_for_status=lambda: None,
    json=lambda: {"keys": [public_jwk]},
)
with patch.object(chatgpt_plan.httpx, "get", return_value=jwks_response) as fetch:
    assert chatgpt_plan._validated_identity(
        token, "oaiapp_mock", "nonce-123", identity_provider
    )["sub"] == "mock-sub"
    assert fetch.call_args.args[0] == identity_provider["jwks_uri"]
    try:
        chatgpt_plan._validated_identity(
            token, "oaiapp_mock", "wrong-nonce", identity_provider
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("Wrong nonce was accepted")
    wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forgery = encode(claims, wrong_key, algorithm="RS256", headers={"kid": "mock-kid"})
    try:
        chatgpt_plan._validated_identity(
            forgery, "oaiapp_mock", "nonce-123", identity_provider
        )
    except jwt.InvalidSignatureError:
        pass
    else:
        raise AssertionError("Wrong signing key was accepted")
print("Verified JWKS fetch and signature checks: PASS")




