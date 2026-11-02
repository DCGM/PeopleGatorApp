"""Standalone OIDC issuer. No resource routes, settings or database lifecycle."""
import html
import re
import secrets
import time
from urllib.parse import urlencode, urlsplit

import argon2
from authlib.oauth2.rfc6749.errors import OAuth2Error, InvalidRequestError
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from joserfc.jwt import decode
from starlette.concurrency import run_in_threadpool

from people_gator_auth import accounts, keys
from people_gator_auth.protocol import Principal, ProtocolRequest, Server, request_pairs
from people_gator_auth.settings import settings
from people_gator_auth.store import Store, digest

SESSION_COOKIE = "pg_auth_session"
INTERACTION_COOKIE = "pg_auth_interaction"


def cookie(response, name, value, max_age):
    response.set_cookie(name, value, httponly=True, secure=settings.issuer.startswith("https://"),
                        samesite="lax", path="/token", max_age=max_age)


def login_page(interaction, *, username=None, error=""):
    preview = re.fullmatch(r"pr-\d+\.preview\.peoplegator\.dev", urlsplit(settings.issuer).hostname or "")
    username = username if username is not None else ("test" if preview else "")
    password = "test" if preview and not error else ""
    escape = html.escape
    message = f'<p role="alert">{escape(error)}</p>' if error else ""
    # The issuer owns this form; it has no app bundle or resource dependencies.
    return HTMLResponse(f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sign in — PeopleGator</title><style>
:root{{color-scheme:light dark;font:16px system-ui,sans-serif;background:#faf9f6;color:#202625}}
body{{margin:0;padding:64px 24px}}main{{max-width:384px;margin:auto}}.brand{{color:#687374;margin:0 0 24px}}
h1{{font-size:24px;margin:0 0 24px}}form{{display:flex;flex-direction:column;gap:12px}}
input,button{{font:inherit;box-sizing:border-box;width:100%;min-width:0;border-radius:6px;padding:10px 12px}}
input{{border:1px solid #c6cbca;background:transparent;color:inherit}}button{{border:0;background:#202a2d;color:white;cursor:pointer;margin-top:8px}}
input:focus-visible,button:focus-visible{{outline:2px solid #668c98;outline-offset:3px}}
[role=alert]{{margin:4px 0}}@media(prefers-color-scheme:dark){{:root{{background:#181c1d;color:#eee}}input{{border-color:#687374}}button{{background:#eee;color:#202a2d}}}}
</style></head><body><main><p class="brand">PeopleGator</p><h1>Sign in</h1>
<form method="post" action="/token/login">
<input type="hidden" name="interaction" value="{escape(interaction)}">
<label for="username">Username</label><input id="username" name="username" autocomplete="username" required value="{escape(username, quote=True)}">
<label for="password">Password</label><input id="password" name="password" type="password" autocomplete="current-password" required value="{password}">
{message}<button type="submit">Sign in</button></form></main></body></html>''', headers={
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
    })


def get_app() -> FastAPI:
    app = FastAPI(title="PeopleGator authorization", docs_url=None, redoc_url=None)
    origins = set(settings.allow_origins)
    for client in settings.browser_clients():
        for uri in client.redirect_uris:
            parsed = urlsplit(uri)
            origins.add(f"{parsed.scheme}://{parsed.netloc}")
    app.add_middleware(CORSMiddleware, allow_origins=sorted(origins),
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    @app.middleware("http")
    async def no_store(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def state():
        return Store(settings.state_dir)

    @app.get("/auth/health")
    async def health():
        accounts.accounts()
        await keys.get_key_set()
        with state().transaction(): pass
        return {"status": "ok"}

    @app.get("/.well-known/jwks.json")
    async def jwks():
        return (await keys.get_key_set()).as_dict(private=False)

    @app.get("/.well-known/openid-configuration")
    async def discovery():
        issuer = settings.issuer.rstrip("/")
        return {"issuer": issuer, "authorization_endpoint": issuer + "/token/authorize",
                "token_endpoint": issuer + "/token/oidc", "jwks_uri": issuer + "/.well-known/jwks.json",
                "end_session_endpoint": issuer + "/token/logout", "revocation_endpoint": issuer + "/token/revoke",
                "response_types_supported": ["code"], "response_modes_supported": ["query"],
                "grant_types_supported": ["authorization_code", "refresh_token"],
                "token_endpoint_auth_methods_supported": ["none"], "revocation_endpoint_auth_methods_supported": ["none"],
                "code_challenge_methods_supported": ["S256"], "subject_types_supported": ["public"],
                "id_token_signing_alg_values_supported": ["ES256"],
                "scopes_supported": ["openid", "profile", "offline_access"] + settings.api_scopes}

    def principal(records, sid):
        saved = records.get("session", sid) if sid else None
        user = Principal(saved["username"], digest(sid), saved["auth_time"]) if saved else None
        return user if user and user.account else None

    @app.get("/token/authorize")
    async def authorize(request: Request):
        if len(request.url.query) > 8192:
            return JSONResponse({"error": "invalid_request"}, status_code=400)
        key_set = await keys.get_key_set()
        def response():
            with state().transaction() as records:
                server = Server(records, key_set)
                try:
                    pairs = request_pairs(request.url.query.encode())
                    protocol = ProtocolRequest("GET", "/token/authorize", pairs)
                    user = principal(records, request.cookies.get(SESSION_COOKIE))
                    grant = server.get_consent_grant(protocol, end_user=user)
                    prompt = protocol.payload.data.get("prompt", "")
                    if prompt not in {"", "none", "login", "select_account"}:
                        raise InvalidRequestError("Unsupported prompt")
                    if user and prompt not in {"login", "select_account"}:
                        return server.create_authorization_response(protocol, grant_user=user, grant=grant)
                    handle = secrets.token_urlsafe(32)
                    records.put("interaction", handle, {"pairs": pairs}, 600)
                    page = login_page(handle)
                    cookie(page, INTERACTION_COOKIE, handle, 600)
                    return page
                except OAuth2Error as error:
                    return server.handle_error_response(locals().get("protocol"), error)
                except ValueError:
                    return JSONResponse({"error": "invalid_request"}, status_code=400)
        return await run_in_threadpool(response)

    @app.post("/token/login")
    async def login(request: Request):
        body = await request.body()
        if len(body) > 16384:
            return JSONResponse({"error": "invalid_request"}, status_code=400)
        key_set = await keys.get_key_set()
        def response():
            with state().transaction() as records:
                server = Server(records, key_set)
                try:
                    form = dict(request_pairs(body))
                    handle = form.get("interaction", "")
                    saved = records.get("interaction", handle)
                    if not saved or not secrets.compare_digest(handle, request.cookies.get(INTERACTION_COOKIE, "")):
                        return JSONResponse({"error": "invalid_request", "error_description": "Login expired. Start sign-in again."}, status_code=400)
                    username = form.get("username", "")
                    account = accounts.accounts().get(username)
                    valid = False
                    try:
                        valid = account is not None and argon2.PasswordHasher().verify(account.hash, form.get("password", ""))
                    except argon2.exceptions.VerificationError:
                        pass
                    if not valid or not account.is_active:
                        return login_page(handle, username=username, error="Check your username and password.")
                    sid = secrets.token_urlsafe(32)
                    user = Principal(username, digest(sid), int(time.time()))
                    protocol = ProtocolRequest("GET", "/token/authorize", saved["pairs"])
                    grant = server.get_authorization_grant(protocol)
                    result = server.create_authorization_response(protocol, grant_user=user, grant=grant)
                    if result.status_code == 302:
                        records.put("session", sid, {"username": username, "auth_time": user.auth_time}, settings.session_lifetime_seconds)
                        records.delete("interaction", handle)
                        cookie(result, SESSION_COOKIE, sid, settings.session_lifetime_seconds)
                        result.delete_cookie(INTERACTION_COOKIE, path="/token")
                    return result
                except (OAuth2Error, ValueError) as error:
                    if isinstance(error, OAuth2Error): return server.handle_error_response(None, error)
                    return JSONResponse({"error": "invalid_request"}, status_code=400)
        return await run_in_threadpool(response)

    @app.post("/token/oidc")
    async def token(request: Request):
        body = await request.body()
        if len(body) > 16384 or request.headers.get("content-type", "").split(";")[0] != "application/x-www-form-urlencoded":
            return JSONResponse({"error": "invalid_request"}, status_code=400)
        key_set = await keys.get_key_set()
        def response():
            with state().transaction() as records:
                server = Server(records, key_set)
                try:
                    protocol = ProtocolRequest("POST", "/token/oidc", request_pairs(body), dict(request.headers))
                    return server.create_token_response(protocol)
                except (OAuth2Error, ValueError) as error:
                    if isinstance(error, OAuth2Error): return server.handle_error_response(None, error)
                    return JSONResponse({"error": "invalid_request"}, status_code=400)
        return await run_in_threadpool(response)

    @app.post("/token/revoke")
    async def revoke(request: Request):
        try:
            form = dict(request_pairs(await request.body()))
            with state().transaction() as records:
                server = Server(records, None)
                if not server.query_client(form.get("client_id")):
                    return JSONResponse({"error": "invalid_client"}, status_code=400)
                secret = form.get("token", "")
                saved = records.get("refresh", secret)
                if saved and saved["client_id"] == form["client_id"]:
                    records.delete("refresh", secret)
            return JSONResponse({})
        except (OAuth2Error, ValueError):
            return JSONResponse({"error": "invalid_request"}, status_code=400)

    @app.get("/token/logout")
    async def logout(request: Request):
        key_set = await keys.get_key_set()
        def response():
            try:
                form = dict(request_pairs(request.url.query.encode()))
                hint = decode(form.get("id_token_hint", ""), key_set, algorithms=["ES256"]).claims
                # Expired hints are permitted, but signatures, issuer, token kind
                # and registered client/redirect must still be validated.
                if hint.get("iss") != settings.issuer or hint.get("token_use") != "id":
                    raise ValueError("Invalid hint")
                client = Server(None, key_set).query_client(hint.get("aud"))
                target = form.get("post_logout_redirect_uri")
                if not client or target not in client.registration.post_logout_redirect_uris:
                    raise ValueError("Invalid redirect")
                if state_value := form.get("state"):
                    target += ("&" if "?" in target else "?") + urlencode({"state": state_value})
                with state().transaction() as records:
                    sid = request.cookies.get(SESSION_COOKIE, "")
                    saved = records.get("session", sid) if sid else None
                    if saved and saved["username"] != hint.get("sub"):
                        raise ValueError("Session mismatch")
                    if saved: records.revoke_session(sid)
                    if isinstance(hint.get("sid"), str):
                        records.revoke_session_hash(hint["sid"])
                result = RedirectResponse(target, status_code=302)
                result.delete_cookie(SESSION_COOKIE, path="/token")
                return result
            except Exception:
                return JSONResponse({"error": "invalid_request"}, status_code=400)
        return await run_in_threadpool(response)

    return app


app = get_app()


def server():
    import uvicorn
    uvicorn.run("people_gator_auth.app:app", host=settings.host, port=settings.port)
