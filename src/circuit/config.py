from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    PROVIDER: str = "MOCK"
    CIRCUIT_API_KEYS: str

    CIRCUIT_LOG_PAYLOADS: bool = False
    CIRCUIT_DB_PATH: str = "./circuit.db"

    CIRCUIT_REQUESTS_PER_MIN: int = 60
    CIRCUIT_DAILY_USD_LIMIT: float = 10.0
    CIRCUIT_MAX_OUTPUT_TOKENS: int = 4096

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def api_keys(self) -> List[str]:
        return [k.strip() for k in self.CIRCUIT_API_KEYS.split(",") if k.strip()]


settings = Settings()