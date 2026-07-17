from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from the environment (or a .env file).

    Required keys have no defaults, so instantiating ``Settings`` with any of
    them missing raises a ``pydantic.ValidationError`` immediately rather than
    failing silently later.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str
    anthropic_api_key: str
    jwt_secret: str
    environment: str = "development"


@lru_cache
def get_settings() -> Settings:
    """Return a cached, process-wide ``Settings`` instance."""
    return Settings()  # type: ignore[call-arg]
