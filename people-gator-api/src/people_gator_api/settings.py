from pydantic import Field, BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

class OpenTelemetrySettings(BaseModel):
    enabled: bool = True
    http_endpoint: str = "http://lgtm:4318"
    grpc_endpoint: str = "http://lgtm:4317"
    traces_path: str = "/v1/traces"
    logs_path: str = "/v1/logs"
    metrics_path: str = "/v1/metrics"
    profiles_path: str = "/v1/profiles"


class PostgresSettings(BaseModel):
    host: str = "dev-peoplegator-postgres"
    port: int = Field(default=5432, le=65535, ge=1)
    user: str = "postgres"
    password: str = "password"
    database: str = "people_gator"


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
    log_level: str = "INFO"
    otel: OpenTelemetrySettings = OpenTelemetrySettings()
    postgres: PostgresSettings = PostgresSettings()

settings = Settings()
