from dataclasses import dataclass


@dataclass
class TimeoutConfig:
    connect_timeout: float = 0.5
    read_timeout: float = 1.0
    total_timeout: float = 1.5


DEFAULT_TIMEOUT = TimeoutConfig()