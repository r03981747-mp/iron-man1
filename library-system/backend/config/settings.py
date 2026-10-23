from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # General
    PROJECT_NAME: str = "Libra — Library OS"
    API_V1_STR: str = "/api/v1"
    APP_BASE_URL: str = "http://localhost:8000"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Security
    SECRET_KEY: str = "change-me-in-production-use-a-long-random-string"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Database (SQLite by default for instant local start; set DATABASE_URL for PostgreSQL)
    DATABASE_URL: str = "sqlite:///./library.db"

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

    # Payments (Stripe)
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    DEFAULT_CURRENCY: str = "USD"

    # Membership pricing (per month)
    PRICE_BASIC: float = 0.0
    PRICE_STUDENT: float = 4.99
    PRICE_PREMIUM: float = 9.99
    PRICE_FAMILY: float = 14.99

    # Loan policy
    DEFAULT_LOAN_DAYS: int = 14
    MAX_RENEWALS: int = 2
    FINE_PER_DAY: float = 0.25
    MAX_ACTIVE_LOANS: int = 10

    # Email (optional)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAILS_FROM_EMAIL: str = "noreply@librarysystem.com"
    EMAILS_FROM_NAME: str = "Libra — Library OS"

    # Uploads
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024

    @property
    def is_postgres(self) -> bool:
        return self.DATABASE_URL.startswith("postgresql")

    @property
    def stripe_enabled(self) -> bool:
        return bool(self.STRIPE_SECRET_KEY)

    @property
    def membership_prices(self) -> dict:
        return {
            "basic": self.PRICE_BASIC,
            "student": self.PRICE_STUDENT,
            "premium": self.PRICE_PREMIUM,
            "family": self.PRICE_FAMILY,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
