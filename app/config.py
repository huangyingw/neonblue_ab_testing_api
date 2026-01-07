"""Application configuration settings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_name: str = "A/B Testing API"
    database_url: str = "sqlite:///./ab_testing.db"

    # Valid API tokens for authentication
    api_tokens: list[str] = [
        "test-token-123",
        "test-token-456",
    ]

    class Config:
        env_file = ".env"


settings = Settings()
