from pydantic import BaseModel
import uuid


class ErrorResponse(BaseModel):
    code: str
    message: str


class GenericListResponse[T: BaseModel](BaseModel):
    items: list[T]
    total_count: int
    limit: int
    after_id: uuid.UUID | None = None
