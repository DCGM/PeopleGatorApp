from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BatchSettings(BaseSettings):
    """Maximum request sizes for batch API operations."""

    model_config = SettingsConfigDict(
        env_prefix="PEOPLE_GATOR_API__BATCH__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    max_entity_batch_size: int = Field(default=10_000, gt=0)
    max_face_batch_size: int = Field(default=10_000, gt=0)
    max_text_mention_batch_size: int = Field(default=10_000, gt=0)
    max_media_batch_size: int = Field(default=10_000, gt=0)


batch_settings = BatchSettings()


__all__ = ["BatchSettings", "batch_settings"]
