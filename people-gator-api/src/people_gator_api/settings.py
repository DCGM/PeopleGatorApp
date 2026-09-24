from pydantic import (
    BaseModel,
    Field,
    computed_field,
)
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)
from people_gator_api.schemas.enums import Language


class OpenTelemetrySettings(BaseModel):
    """OpenTelemetry configuration settings."""

    enabled: bool = True
    http_endpoint: str = "http://lgtm:4318"
    grpc_endpoint: str = "http://lgtm:4317"
    traces_path: str = "/v1/traces"
    logs_path: str = "/v1/logs"
    metrics_path: str = "/v1/metrics"
    profiles_path: str = "/v1/profiles"


class BatchSettings(BaseModel):
    """Maximum request sizes for batch API operations."""

    max_entity_batch_size: int = Field(default=10_000, gt=0)
    max_face_batch_size: int = Field(default=10_000, gt=0)
    max_text_mention_batch_size: int = Field(default=10_000, gt=0)
    max_media_batch_size: int = Field(default=10_000, gt=0)


class CorsSettings(BaseModel):
    """CORS (Cross-Origin Resource Sharing) configuration settings."""

    allow_origin_regex: str = r"^https?://(?:localhost|127\.0\.0\.1|\[::1\])(?::\d+)?$"


class PostgresSettings(BaseModel):
    """PostgreSQL database connection settings."""

    host: str
    port: int = Field(le=65535, ge=1)
    user: str
    password: str
    database: str


class S3Settings(BaseModel):
    """S3 storage settings."""

    access_key_id: str
    secret_access_key: str
    bucket_name: str
    region: str
    endpoint_url: str | None = None
    timeout_seconds: float = Field(default=30.0, gt=0)


class StorageSettings(BaseModel):
    s3: S3Settings


class ImageContentSettings(BaseModel):
    """S3 storage settings for original image content."""

    key_prefix: str = "images"


class PageImageSettings(BaseModel):
    """S3 storage settings for original page scans."""

    key_prefix: str = "images/ndk"


class PageImageCacheSettings(BaseModel):
    """S3-backed cache for resized page images (JPEG only)."""

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
    startup_timeout_seconds: float = Field(default=300.0, gt=0)
    startup_retry_interval_seconds: float = Field(default=2.0, gt=0)


class PersistenceSettings(BaseModel):
    postgres: PostgresSettings
    weaviate: WeaviateSettings


class EmbeddingServiceSettings(BaseModel):
    detect_and_embed_image_url: str = "http://localhost:8001/v1/faces/detect"
    embed_image_url: str = "http://localhost:8001/v1/embeddings/image"
    embed_text_url: str = "http://localhost:8001/v1/embeddings/text"
    request_timeout_seconds: float = Field(default=30.0, gt=0)


class OpenRouterSettings(BaseModel):
    """Fixed configuration for the OpenRouter-backed translation endpoint."""

    api_key: str
    model: str = "deepseek/deepseek-v4-flash"
    base_url: str = "https://openrouter.ai/api/v1"
    request_timeout_seconds: float = Field(default=30.0, gt=0)
    allowed_languages: list[Language] = Field(default_factory=lambda: list(Language))


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
    batch: BatchSettings = Field(default_factory=BatchSettings)
    cors: CorsSettings = CorsSettings()
    otel: OpenTelemetrySettings = OpenTelemetrySettings()
    persistence: PersistenceSettings
    storage: StorageSettings
    jwk: JwkSettings = JwkSettings()
    keycloak: KeycloakSettings
    embedding_service: EmbeddingServiceSettings = EmbeddingServiceSettings()
    openrouter: OpenRouterSettings
    image_content: ImageContentSettings = ImageContentSettings()
    page_image: PageImageSettings = PageImageSettings()
    page_image_cache: PageImageCacheSettings = PageImageCacheSettings()
    page_layout: PageLayoutSettings = PageLayoutSettings()
    aligned_face_crop: AlignedFaceCropSettings = AlignedFaceCropSettings()


settings = Settings()  # type: ignore
