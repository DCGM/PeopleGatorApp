from fastapi import (
    HTTPException,
)
from typing import (
    NoReturn,
)


def raise_api_error(status_code: int, code: str, message: str) -> NoReturn:
    raise HTTPException(status_code=status_code, detail={"code": code, "message": message})
