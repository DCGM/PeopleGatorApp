from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix='PEOPLE_GATOR_API__',
        env_nested_delimiter='__',
    )
    app_name: str = "People Gator API"
    debug: bool = True
    reload: bool = True
    port: int = Field(default=8000, le=65535, ge=1)
    host: str = "0.0.0.0"

settings = Settings()
