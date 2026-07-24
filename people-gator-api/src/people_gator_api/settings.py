from enum import StrEnum

from pydantic import BaseModel, Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from people_gator_api.schemas.enums import AnnotationType
from people_gator_api.services.vector_service.schema import (
    DEFAULT_FACE_VECTOR,
    DEFAULT_FULLTEXT_VECTOR,
    DEFAULT_NAME_VECTOR,
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


class StorageSettings(BaseModel):
    s3: S3Settings


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


class SearchModalitySettings(BaseModel):
    annotation_type: AnnotationType
    weight: float = Field(default=1.0, gt=0)
    vector_name: str
    aggregation: SearchEntityAggregationMode = (
        SearchEntityAggregationMode.best_annotation
    )
    min_confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class SearchProfileSettings(BaseModel):
    entity_candidate_multiplier: int = Field(default=5, ge=1, le=50)
    annotation_candidate_multiplier: int = Field(default=3, ge=1, le=50)
    modalities: list[SearchModalitySettings] = Field(
        default_factory=lambda: [
            SearchModalitySettings(
                annotation_type=AnnotationType.face,
                weight=0.6,
                vector_name=DEFAULT_FACE_VECTOR,
                aggregation=SearchEntityAggregationMode.best_annotation,
                min_confidence=0.6,
            ),
            SearchModalitySettings(
                annotation_type=AnnotationType.entity_name,
                weight=0.25,
                vector_name=DEFAULT_NAME_VECTOR,
                aggregation=SearchEntityAggregationMode.best_annotation,
            ),
            SearchModalitySettings(
                annotation_type=AnnotationType.document_mention,
                weight=0.1,
                vector_name=DEFAULT_NAME_VECTOR,
                aggregation=SearchEntityAggregationMode.best_annotation,
            ),
            SearchModalitySettings(
                annotation_type=AnnotationType.description,
                weight=0.05,
                vector_name=DEFAULT_FULLTEXT_VECTOR,
                aggregation=SearchEntityAggregationMode.best_annotation,
            ),
            SearchModalitySettings(
                annotation_type=AnnotationType.entity,
                weight=0.1,
                vector_name=DEFAULT_FULLTEXT_VECTOR,
                aggregation=SearchEntityAggregationMode.best_annotation,
            ),
        ]
    )


class SearchSettings(BaseModel):
    profile: SearchProfileSettings = SearchProfileSettings()


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
    keycloak: KeycloakSettings
    weaviate: WeaviateSettings
    embedding_service: EmbeddingServiceSettings = EmbeddingServiceSettings()
    search: SearchSettings = SearchSettings()


settings = Settings()  # pyright: ignore[reportCallIssue] - BaseSettings values come from env sources.
