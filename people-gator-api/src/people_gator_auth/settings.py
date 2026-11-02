from pathlib import Path
from pydantic import Field, BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator
from urllib.parse import urlsplit


class BrowserClient(BaseModel):
    client_id: str = Field(min_length=1)
    redirect_uris: list[str] = Field(min_length=1)
    post_logout_redirect_uris: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_redirects(self):
        for uri in self.redirect_uris + self.post_logout_redirect_uris:
            parsed = urlsplit(uri)
            if parsed.fragment or parsed.username or parsed.password or "*" in uri or not parsed.netloc:
                raise ValueError("Client redirects must be exact absolute URLs without fragments")
            if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}):
                raise ValueError("Client redirects require HTTPS except loopback development")
        return self


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PEOPLE_GATOR_AUTH__", env_file=".env", extra="ignore")
    state_dir: Path = Path("./auth-state")
    issuer: str = "https://preview.peoplegator.dev"
    audience: str = "preview.peoplegator.dev"
    host: str = "0.0.0.0"
    port: int = Field(default=8002, ge=1, le=65535)
    key_cache_ttl_seconds: int = Field(default=3600, gt=0)
    access_token_lifetime_seconds: int = Field(default=7200, gt=0)
    allow_origins: list[str] = Field(default_factory=list)
    clients: list[BrowserClient] = Field(default_factory=list)
    authorization_code_lifetime_seconds: int = Field(default=60, gt=0, le=600)
    session_lifetime_seconds: int = Field(default=28800, gt=0)
    refresh_token_lifetime_seconds: int = Field(default=86400, gt=0)
    api_scopes: list[str] = Field(default_factory=lambda: [
        "people-gator:browse", "people-gator:annotate", "people-gator:ingest", "people-gator:admin",
    ])

    @model_validator(mode="after")
    def validate_issuer(self):
        self.issuer = self.issuer.rstrip("/")
        parsed = urlsplit(self.issuer)
        if not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path:
            raise ValueError("Built-in issuer must be a public origin without path/query/fragment")
        if len({client.client_id for client in self.clients}) != len(self.clients):
            raise ValueError("Client IDs must be unique")
        return self

    def browser_clients(self) -> list[BrowserClient]:
        if self.clients:
            return self.clients
        # Exact same-origin registration keeps the existing reviewed controller
        # recipe compatible. Additional origins must be registered explicitly.
        return [BrowserClient(client_id="people-gator-browser",
                              redirect_uris=[self.issuer.rstrip("/") + "/auth-callback.html", self.issuer.rstrip("/") + "/docs"],
                              post_logout_redirect_uris=[self.issuer.rstrip("/") + "/login.html"])]


settings = AuthSettings()
