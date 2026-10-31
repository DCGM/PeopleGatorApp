"""Real HTTP JWKS retrieval, rotation, outages and alternate provider mapping."""
import asyncio
import json
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from threading import Thread
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from fastapi import HTTPException
from joserfc.jwk import ECKey, KeySet, OctKey, RSAKey
from joserfc.jwt import encode
from people_gator_api.services import jwk_service as validator
from people_gator_api.settings import TokenValidationSettings, settings

pytestmark = pytest.mark.asyncio


@contextmanager
def public_server():
    state = {"keys": KeySet([ECKey.generate_key("P-256", auto_kid=True)]), "calls": 0, "fail": False}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state["calls"] += 1
            self.send_response(503 if state["fail"] else 200)
            self.end_headers()
            self.wfile.write(json.dumps(state.get("body", state["keys"].as_dict(private=False))).encode())
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state, f"http://127.0.0.1:{server.server_port}/jwks"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


@pytest.fixture
def consumer(monkeypatch):
    monkeypatch.setattr(validator, "_keyset", None)
    monkeypatch.setattr(validator, "_last_fetch_time", float("-inf"))
    monkeypatch.setattr(validator, "_last_attempt", float("-inf"))
    monkeypatch.setattr(validator, "_keyset_lock", asyncio.Lock())
    with public_server() as (state, url):
        monkeypatch.setattr(settings, "auth", TokenValidationSettings(jwks_url=url))
        yield state


def token(keys, **claims):
    now = int(time.time())
    return encode({"alg": "ES256"}, {"iss": settings.auth.issuer, "aud": settings.auth.audience,
        "sub": "alice", "uid": str(uuid.uuid4()), "iat": now, "exp": now+60,
        "scopes": "people-gator:browse", **claims}, keys)


async def test_cache_concurrency_outage_expiry_and_negative_throttle(consumer, monkeypatch):
    signed = token(consumer["keys"])
    await asyncio.gather(*(validator.verify_access_token(signed) for _ in range(10)))
    assert consumer["calls"] == 1
    consumer["fail"] = True
    assert (await validator.verify_access_token(signed))["sub"] == "alice"
    assert consumer["calls"] == 1
    monkeypatch.setattr(validator, "_last_fetch_time", float("-inf"))
    monkeypatch.setattr(validator, "_last_attempt", float("-inf"))
    for _ in range(10):
        with pytest.raises(HTTPException) as error:
            await validator.verify_access_token(signed)
        assert error.value.status_code == 503
    assert consumer["calls"] == 2


async def test_rotation_and_bounded_unknown_kid(consumer, monkeypatch):
    await validator.verify_access_token(token(consumer["keys"]))
    consumer["keys"] = KeySet([ECKey.generate_key("P-256", auto_kid=True)])
    monkeypatch.setattr(validator, "_last_attempt", float("-inf"))
    await validator.verify_access_token(token(consumer["keys"]))
    assert consumer["calls"] == 2
    for _ in range(8):
        with pytest.raises(HTTPException) as error:
            await validator.verify_access_token(token(KeySet([ECKey.generate_key("P-256", auto_kid=True)])))
        assert error.value.status_code == 401
    assert consumer["calls"] == 2


async def test_alternate_provider_and_claim_mapping(consumer, monkeypatch):
    monkeypatch.setattr(settings.auth, "issuer", "https://second-provider.test")
    monkeypatch.setattr(settings.auth, "audience", "other-resource")
    monkeypatch.setattr(settings.auth, "actor_claim", "actor_id")
    monkeypatch.setattr(settings.auth, "scopes_claim", "scope")
    actor = uuid.uuid4()
    signed = token(consumer["keys"], uid=None, scopes=None, actor_id=str(actor), scope="people-gator:browse")
    assert (await validator.verify_access_token(signed))["uid"] == actor


async def test_issuer_import_is_independent():
    result = subprocess.run([sys.executable, "-c", "import sys; import people_gator_api.auth.app; "
        "assert 'people_gator_api.settings' not in sys.modules; "
        "assert 'people_gator_api.services.database_service' not in sys.modules; "
        "assert 'people_gator_api.app' not in sys.modules"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


async def test_resource_import_does_not_load_issuer_or_expose_token_routes():
    result = subprocess.run([sys.executable, "-c", "import sys; import people_gator_api.schemas; "
        "from people_gator_api.app import app; "
        "assert not any(name.startswith('people_gator_api.auth.') for name in sys.modules); "
        "assert not any(route.path.startswith(('/token/', '/.well-known/')) for route in app.routes); "
        "from people_gator_api.settings import settings; assert not hasattr(settings, 'jwk')"],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("kind", ["private", "symmetric", "malformed"])
async def test_nonpublic_or_malformed_jwks_is_unavailable(consumer, kind):
    consumer["body"] = consumer["keys"].as_dict(private=True) if kind == "private" else (
        {"keys": [{"kty": "oct", "k": "c2VjcmV0"}]} if kind == "symmetric" else {"keys": [42]})
    with pytest.raises(HTTPException) as error:
        await validator.verify_access_token(token(consumer["keys"]))
    assert error.value.status_code == 503


async def test_unsupported_algorithm_is_rejected(consumer):
    signed = encode({"alg": "HS256"}, {"iss": settings.auth.issuer}, OctKey.generate_key(256))
    with pytest.raises(HTTPException) as error:
        await validator.verify_access_token(signed)
    assert error.value.status_code == 401


async def test_rsa_provider_and_jti_are_supported_with_configuration(consumer, monkeypatch):
    consumer["keys"] = KeySet([RSAKey.generate_key(2048, auto_kid=True)])
    monkeypatch.setattr(settings.auth, "algorithms", ["RS256"])
    now = int(time.time())
    signed = encode({"alg": "RS256"}, {"iss": settings.auth.issuer, "aud": settings.auth.audience,
        "sub": "external", "uid": str(uuid.uuid4()), "iat": now, "exp": now+60,
        "scopes": "people-gator:browse", "jti": "external-access-id"}, consumer["keys"])
    assert (await validator.verify_access_token(signed))["sub"] == "external"
