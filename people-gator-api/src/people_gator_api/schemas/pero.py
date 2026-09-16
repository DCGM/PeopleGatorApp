from pydantic import BaseModel


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


__all__ = [
	"TextLineModel",
	"RegionLayoutModel",
	"PageLayoutModel",
]

