from pydantic import BaseModel, Field


class SseTopicStatsResponse(BaseModel):
    """Response model for SSE topic statistics."""
    topic: tuple[str, ...]
    subscriber_count: int = Field(ge=0)


class SseStatsResponse(BaseModel):
    """Active SSE subscriber counts for each concrete topic in this process."""
    topics: list[SseTopicStatsResponse]
    total_subscribers: int
