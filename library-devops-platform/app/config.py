"""All settings come from environment variables (twelve-factor style)."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    database_url: str
    api_key: str
    loan_days: int = 14
    version: str = "dev"
    # Test-only switch used to demonstrate automatic canary rollback.
    fault_rate: float = 0.0

    @classmethod
    def from_env(cls) -> "Config":
        api_key = os.environ.get("API_KEY", "")
        if len(api_key) < 16:
            raise RuntimeError("API_KEY must be set and at least 16 characters long")
        return cls(
            database_url=os.environ["DATABASE_URL"],
            api_key=api_key,
            loan_days=int(os.environ.get("LOAN_DAYS", "14")),
            version=os.environ.get("APP_VERSION", "dev"),
            fault_rate=float(os.environ.get("FAULT_RATE", "0")),
        )
