from pydantic import BaseModel
from typing import Literal

from people_gator_api.utils.version_info import get_version_info

# ---------------------------------------------------------------------------
# Just a simple root response for the API
# ---------------------------------------------------------------------------


class RootResponse(BaseModel):
    message: str
    version: str = get_version_info().full_version
    package_name: str = "people-gator-api"


class HealthResponse(BaseModel):
    status: Literal["ok"]


__all__ = [
    "RootResponse",
    "HealthResponse",
]

