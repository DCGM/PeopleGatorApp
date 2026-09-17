import uuid

from pydantic import BaseModel, Field

from people_gator_api.schemas.enums import EntityType


class TextLineModel(BaseModel):
    id: str
    baseline: list[list[float]]
    polygon: list[list[float]]
    heights: list[float]
    transcription: str = ""
    transcription_confidence: float | None = None
    index: int | None = None


class RegionLayoutModel(BaseModel):
    id: str
    polygon: list[list[float]]
    region_type: str | None = None
    transcription: str = ""
    lines: list[TextLineModel]


class PageLayoutModel(BaseModel):
    id: str
    page_size: tuple[int, int]
    regions: list[RegionLayoutModel]
    reading_order: dict[str, int]


class EntitySpanModel(BaseModel):
    """An entity occurrence located in one or more OCR text lines.

    Character offsets are zero-based within their respective lines and
    ``end_character`` is exclusive.
    """

    entity_id: uuid.UUID
    entity_type: EntityType | None
    start_line_id: str
    end_line_id: str
    start_character: int = Field(ge=0)
    end_character: int = Field(ge=0)


__all__ = [
    "TextLineModel",
    "RegionLayoutModel",
    "PageLayoutModel",
    "EntitySpanModel",
]
