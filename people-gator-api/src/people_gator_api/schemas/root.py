from pydantic import BaseModel


class RootResponse(BaseModel):
    message: str
    version: str = "0.1.0"
    package_name: str = "people-gator-api"
