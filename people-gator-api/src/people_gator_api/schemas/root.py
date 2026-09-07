from pydantic import BaseModel
from typing import Literal

# ---------------------------------------------------------------------------
# Just a simple root response for the API
# ---------------------------------------------------------------------------


class RootResponse(BaseModel):
    message: str
    version: str = "0.1.0"
    package_name: str = "people-gator-api"


class HealthResponse(BaseModel):
    status: Literal["ok"]
