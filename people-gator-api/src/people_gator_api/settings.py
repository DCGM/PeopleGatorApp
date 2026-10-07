from pathlib import Path
from typing import Literal, Self

from pydantic import (
    BaseModel,
    Field,
    model_validator,
)
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)
from people_gator_api.schemas.enums import Language

# --------------------------------------------------------------------------------------
# Persistence backend settings
# --------------------------------------------------------------------------------------

class PersistenceBaseSetting(BaseModel):
    """Shared configuration for a persistence backend."""


class PostgresSettings(PersistenceBaseSetting):
    """PostgreSQL database connection settings."""

    host: str
    port: int = Field(le=65535, ge=1)
    user: str
    password: str
    database: str
    schema_mode: Literal["bootstrap", "validate"] = "bootstrap"
    startup_timeout_seconds: float = Field(default=60.0, gt=0)
    startup_retry_interval_seconds: float = Field(default=2.0, gt=0)


class WeaviateSettings(PersistenceBaseSetting):
    http_host: str
    http_port: int = Field(le=65535, ge=1)
    http_secure: bool
    grpc_host: str
    grpc_port: int = Field(le=65535, ge=1)
    grpc_secure: bool
    api_key: str | None = None
    startup_timeout_seconds: float = Field(default=300.0, gt=0)
    startup_retry_interval_seconds: float = Field(default=2.0, gt=0)


class PersistenceSettings(BaseModel):
    """Configure exactly one enabled persistence backend."""

    postgres: PostgresSettings | None = None
    weaviate: WeaviateSettings | None = None

    @model_validator(mode="after")
    def validate_backend(self) -> Self:
        enabled_count = sum(
            config is not None for config in (self.postgres, self.weaviate)
        )
        if enabled_count != 1:
            raise ValueError("Exactly one persistence backend must be set")
        return self

    @property
    def backend(self) -> Literal["postgres", "weaviate"]:
        """Backend selected by the validated enabled flags."""
        return (
            "postgres"
            if self.postgres is not None
            else "weaviate"
        )

# --------------------------------------------------------------------------------------
# Filesystem backend settings
# --------------------------------------------------------------------------------------

class FilesystemBaseSetting(BaseModel):
    """Shared configuration for a filesystem backend."""


class S3Settings(FilesystemBaseSetting):
    """S3 storage settings."""

    access_key_id: str
    secret_access_key: str
    bucket_name: str
    region: str
    endpoint_url: str | None = None
    timeout_seconds: float = Field(default=30.0, gt=0)


class LocalStorageSettings(FilesystemBaseSetting):
    """Root directory for local object storage."""
    root: Path = Path("./storage")


class StorageSettings(BaseModel):
    model_config = {"extra": "forbid"}
    s3: S3Settings | None = None
    local: LocalStorageSettings | None = None

    @model_validator(mode="after")
    def validate_backend(self) -> Self:
        enabled_count = sum(
            config is not None for config in (self.s3, self.local)
        )
        if enabled_count != 1:
            raise ValueError("Exactly one filesystem backend must be set")
        return self


    @property
    def backend(self) -> Literal["s3", "local"]:
        """Backend selected by the validated enabled flags."""
        return "local" if self.local is not None else "s3"

# --------------------------------------------------------------------------------------
# Image and page storage settings
# --------------------------------------------------------------------------------------

class ImageContentSettings(BaseModel):
    """S3 storage settings for original image content."""

    key_prefix: str = "images"


class PageImageSettings(BaseModel):
    """S3 storage settings for original page scans."""

    key_prefix: str = "images/ndk"


class PageImageCacheSettings(BaseModel):
    """Filesystem-backed cache for resized page images (JPEG only)."""

    enabled: bool = True
    key_prefix: str = "cache/page-images"
    quality: int = Field(default=85, ge=1, le=100)
    # Widths (in pixels) pre-generated and accepted as ``size`` query values.
    widths: list[int] = Field(default_factory=lambda: [256, 1024, 2048])


class PageLayoutSettings(BaseModel):
    """S3 storage settings for page-layout JSON documents."""

    key_prefix: str = "page-layouts"


class AlignedFaceCropSettings(BaseModel):
    """Rendering settings for ArcFace-aligned face crops.

    The reference keypoint template is defined for a ``reference_width`` x
    ``reference_height`` canvas, but the actual output keeps the original
    image scale: only rotation and translation are applied, so the output
    canvas is scaled up/down from the reference size to match the detected
    face's native resolution.
    """

    reference_width: int = Field(default=112, gt=0)
    reference_height: int = Field(default=112, gt=0)
    jpeg_quality: int = Field(default=92, ge=1, le=100)
    max_output_width: int = Field(default=4096, gt=0)
    cache_enabled: bool = True
    cache_key_prefix: str = "cache/aligned-face-crops"

# --------------------------------------------------------------------------------------
# Inference services settings
# --------------------------------------------------------------------------------------

class EmbeddingServiceSettings(BaseModel):
    detect_and_embed_image_url: str = "http://localhost:8001/v1/faces/detect"
    embed_image_url: str = "http://localhost:8001/v1/embeddings/image"
    embed_text_url: str = "http://localhost:8001/v1/embeddings/text"
    request_timeout_seconds: float = Field(default=30.0, gt=0)


class OpenRouterSettings(BaseModel):
    """Fixed configuration for the OpenRouter-backed translation endpoint."""

    api_key: str = "sk-..."
    model: str = "deepseek/deepseek-v4-flash"
    base_url: str = "https://openrouter.ai/api/v1"
    request_timeout_seconds: float = Field(default=30.0, gt=0)
    allowed_languages: list[Language] = Field(default_factory=lambda: list(Language))

# --------------------------------------------------------------------------------------
# Logging and telemetry settings
# --------------------------------------------------------------------------------------

class OpenTelemetrySettings(BaseModel):
    """OpenTelemetry configuration settings."""

    enabled: bool = False
    http_endpoint: str = "http://lgtm:4318"
    grpc_endpoint: str = "http://lgtm:4317"
    traces_path: str = "/v1/traces"
    logs_path: str = "/v1/logs"
    metrics_path: str = "/v1/metrics"
    profiles_path: str = "/v1/profiles"


# --------------------------------------------------------------------------------------
# Batch and CORS settings
# --------------------------------------------------------------------------------------

class BatchSettings(BaseModel):
    """Maximum request sizes for batch API operations."""

    max_entity_batch_size: int = Field(default=10_000, gt=0)
    max_face_batch_size: int = Field(default=10_000, gt=0)
    max_text_mention_batch_size: int = Field(default=10_000, gt=0)
    max_media_batch_size: int = Field(default=10_000, gt=0)


class CorsSettings(BaseModel):
    """CORS (Cross-Origin Resource Sharing) configuration settings."""

    allow_origin_regex: str = r"^https?://(?:localhost|127\.0\.0\.1|\[::1\])(?::\d+)?$"


class JwkSettings(BaseModel):
    key_path: str = "peoplegator_api/jwks.json"
    users_path: str = Field(default="peoplegator_api/users.json", min_length=1)
    key_cache_ttl_seconds: int = Field(default=3600, gt=0)
    issuer: str = "https://preview.peoplegator.dev"
    audience: str = "preview.peoplegator.dev"
    

# --------------------------------------------------------------------------------------
# Full application settings
# --------------------------------------------------------------------------------------

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PEOPLE_GATOR_API__",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "People Gator API"
    debug: bool = False
    reload: bool = False
    port: int = Field(default=8000, le=65535, ge=1)
    host: str = "0.0.0.0"
    log_level: str = "INFO"
    batch: BatchSettings = Field(default_factory=BatchSettings)
    cors: CorsSettings = Field(default_factory=CorsSettings)
    otel: OpenTelemetrySettings = Field(default_factory=OpenTelemetrySettings)
    persistence: PersistenceSettings = Field(default_factory=PersistenceSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    jwk: JwkSettings = Field(default_factory=JwkSettings)
    embedding_service: EmbeddingServiceSettings | None = None
    openrouter: OpenRouterSettings | None = None
    image_content: ImageContentSettings = Field(default_factory=ImageContentSettings)
    page_image: PageImageSettings = Field(default_factory=PageImageSettings)
    page_image_cache: PageImageCacheSettings = Field(default_factory=PageImageCacheSettings)
    page_layout: PageLayoutSettings = Field(default_factory=PageLayoutSettings)
    aligned_face_crop: AlignedFaceCropSettings = Field(default_factory=AlignedFaceCropSettings)


settings = Settings()
