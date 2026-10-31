from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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


settings = AuthSettings()
