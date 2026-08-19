from enum import StrEnum

from pydantic import (
    BaseModel,
    Field,
    computed_field,
)
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class SearchEntityAggregationMode(StrEnum):
    best_annotation = "best_annotation"
    average_annotation = "average_annotation"


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
    timeout_seconds: float = Field(default=30.0, gt=0)


class StorageSettings(BaseModel):
    s3: S3Settings


class JwkSettings(BaseModel):
    key_path: str = "peoplegator_api/jwks.json"
    cache_ttl_seconds: int = Field(default=3600, gt=0)


class WeaviateSettings(BaseModel):
    http_host: str
    http_port: int = Field(le=65535, ge=1)
    http_secure: bool
    grpc_host: str
    grpc_port: int = Field(le=65535, ge=1)
    grpc_secure: bool
    api_key: str | None = None


class EmbeddingServiceSettings(BaseModel):
    detect_and_embed_image_url: str = "http://localhost:8001/v1/faces/detect"
    embed_image_url: str = "http://localhost:8001/v1/embeddings/image"
    embed_text_url: str = "http://localhost:8001/v1/embeddings/text"
    request_timeout_seconds: float = Field(default=30.0, gt=0)


class KeycloakSettings(BaseModel):
    url: str
    realm: str
    audience: str

    @computed_field
    @property
    def issuer(self) -> str:
        return f"{self.url}/realms/{self.realm}"

    @computed_field
    @property
    def jwks_uri(self) -> str:
        return f"{self.url}/realms/{self.realm}/protocol/openid-connect/certs"

    @computed_field
    @property
    def openid_configuration(self) -> str:
        return f"{self.url}/realms/{self.realm}/.well-known/openid-configuration"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PEOPLE_GATOR_API__",
        env_nested_delimiter="__",
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
    jwk: JwkSettings = JwkSettings()
    keycloak: KeycloakSettings
    weaviate: WeaviateSettings
    embedding_service: EmbeddingServiceSettings = EmbeddingServiceSettings()


settings = Settings() # type: ignore
