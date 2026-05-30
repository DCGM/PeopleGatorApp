from pydantic import Field, BaseModel, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

class OpenTelemetrySettings(BaseModel):
    enabled: bool = True
    http_endpoint: str = "http://lgtm:4318"
    grpc_endpoint: str = "http://lgtm:4317"
    traces_path: str = "/v1/traces"
    logs_path: str = "/v1/logs"
    metrics_path: str = "/v1/metrics"
    profiles_path: str = "/v1/profiles"


class PostgresSettings(BaseModel):
    host: str
    port: int = Field(le=65535, ge=1)
    user: str
    password: str
    database: str

class S3Settings(BaseModel):
    access_key_id: str
    secret_access_key: str
    bucket_name: str
    region: str
    endpoint_url: str | None = None

class StorageSettings(BaseModel):
    s3: S3Settings

class WeaviateSettings(BaseModel):
    http_host: str = "weaviate"
    http_port: int = Field(default=8080, le=65535, ge=1)
    http_secure: bool = False
    grpc_host: str = "weaviate"
    grpc_port: int = Field(default=50051, le=65535, ge=1)
    grpc_secure: bool = False
    api_key: str | None = None


class KeycloakSettings(BaseModel):
    url: str = "https://auth.dev.people-gator.capturemyhand.com"
    realm: str = "people-gator"

    @computed_field
    @property
    def issuer(self) -> str:
        return f"{self.url}/realms/{self.realm}"

    @computed_field
    @property
    def jwks_uri(self) -> str:
        return f"{self.url}/realms/{self.realm}/protocol/openid-connect/certs"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix='PEOPLE_GATOR_API__',
        env_nested_delimiter='__',
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    app_name: str = "People Gator API"
    debug: bool = True
    reload: bool = True
    port: int = Field(default=8000, le=65535, ge=1)
    host: str = "0.0.0.0"
    log_level: str = "INFO"
    otel: OpenTelemetrySettings = OpenTelemetrySettings()
    postgres: PostgresSettings
    storage: StorageSettings
    keycloak: KeycloakSettings = KeycloakSettings()
    weaviate: WeaviateSettings = WeaviateSettings()

settings = Settings() # type: ignore
