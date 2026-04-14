from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator
from typing import List


class Settings(BaseSettings):
    PROVIDER: str = "MOCK"
    CIRCUIT_API_KEYS: str

    CIRCUIT_LOG_PAYLOADS: bool = False

    CIRCUIT_REQUESTS_PER_MIN: int = 60
    CIRCUIT_DAILY_USD_LIMIT: float = 10.0
    CIRCUIT_MAX_OUTPUT_TOKENS: int = 4096

    OPENAI_API_KEY: str | None = None
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    OTEL_SERVICE_NAME: str = "circuit-gateway"
    OTEL_SERVICE_VERSION: str = "0.1.0"
    APP_ENV: str = "dev"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4318"
    OTEL_EXPORTER_OTLP_TRACES_ENDPOINT: str | None = None

    GLOBAL_REQUEST_TIMEOUT_SEC: float = 15.0
    DATABASE_URL: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_provider_config(self):
        if self.PROVIDER.upper() == "OPENAI" and not self.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is required when PROVIDER=OPENAI")
        return self

    @property
    def api_keys(self) -> List[str]:
        return [k.strip() for k in self.CIRCUIT_API_KEYS.split(",") if k.strip()]


settings = Settings()