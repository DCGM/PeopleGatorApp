from pydantic import BaseModel


class ErrorResponse(BaseModel):
    code: str
    message: str


class IdResponse(BaseModel):
    id: str
