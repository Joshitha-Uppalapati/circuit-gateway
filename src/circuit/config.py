from pydantic_settings import BaseSettings
from typing import List

DAILY_USD_LIMIT = 10.0

class Settings(BaseSettings):
    # Comma-separated API keys
    PROVIDER: str = "MOCK"
    CIRCUIT_API_KEYS: str

    # Debug flag
    CIRCUIT_LOG_PAYLOADS: bool = False

    # SQLite database path
    CIRCUIT_DB_PATH: str = "./circuit.db"

    # Default quota limits
    CIRCUIT_REQUESTS_PER_MIN: int = 60
    CIRCUIT_DAILY_USD_LIMIT: float = 10.0
    CIRCUIT_MAX_OUTPUT_TOKENS: int = 4096

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def api_keys(self) -> List[str]:
        return [key.strip() for key in self.CIRCUIT_API_KEYS.split(",") if key.strip()]


settings = Settings()