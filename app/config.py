"""Application configuration settings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_name: str = "A/B Testing API"
    database_url: str = "postgresql://abtest:abtest123@db:5432/ab_testing"

    class Config:
        env_file = ".env"


settings = Settings()
