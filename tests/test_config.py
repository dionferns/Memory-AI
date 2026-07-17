import pytest
from pydantic import ValidationError

from memory_ai.config import Settings


def test_settings_load_from_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pw@localhost:5432/memory_ai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("JWT_SECRET", "test-secret")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.database_url == "postgresql+psycopg://user:pw@localhost:5432/memory_ai"
    assert settings.anthropic_api_key == "sk-ant-test"
    assert settings.jwt_secret == "test-secret"
    assert settings.environment == "development"


def test_settings_missing_required_vars_raises_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)  # type: ignore[call-arg]

    missing_fields = {error["loc"][0] for error in exc_info.value.errors()}
    assert missing_fields == {"database_url", "anthropic_api_key", "jwt_secret"}
