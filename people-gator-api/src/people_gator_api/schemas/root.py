from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Just a simple root response for the API
# ---------------------------------------------------------------------------

class RootResponse(BaseModel):
    message: str
    version: str = "0.1.0"
    package_name: str = "people-gator-api"
