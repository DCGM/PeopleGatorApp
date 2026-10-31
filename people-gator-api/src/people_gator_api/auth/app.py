"""Independently runnable issuer; no resource routes or database lifecycle."""
from typing import Annotated
from fastapi import Depends, FastAPI, Response
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from people_gator_api.auth import accounts, keys
from people_gator_api.auth.settings import settings


class RefreshRequest(BaseModel):
    refresh_token: str


def get_app() -> FastAPI:
    app = FastAPI(title="PeopleGator authorization")
    app.add_middleware(CORSMiddleware, allow_origins=settings.allow_origins,
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    @app.middleware("http")
    async def no_store(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/auth/health")
    async def health():
        accounts.accounts()
        await keys.get_key_set()
        return {"status": "ok"}

    @app.get("/.well-known/jwks.json")
    async def jwks():
        return (await keys.get_key_set()).as_dict(private=False)

    @app.get("/.well-known/openid-configuration")
    async def discovery():
        return {"issuer": settings.issuer, "jwks_uri": settings.issuer + "/.well-known/jwks.json",
                "token_endpoint": settings.issuer + "/token/login",
                "grant_types_supported": ["password", "refresh_token"]}

    @app.post("/token/login", response_model=accounts.TokenResponse)
    async def login(form: Annotated[OAuth2PasswordRequestForm, Depends()]):
        return await accounts.login(form.username, form.password, form.scopes)

    @app.post("/token/refresh", response_model=accounts.TokenResponse)
    async def refresh(body: RefreshRequest):
        return await accounts.refresh(body.refresh_token)

    @app.post("/token/logout", status_code=204)
    async def logout(body: RefreshRequest):
        await accounts.logout(body.refresh_token)
        return Response(status_code=204)

    return app


app = get_app()


def server():
    import uvicorn
    uvicorn.run("people_gator_api.auth.app:app", host=settings.host, port=settings.port)
