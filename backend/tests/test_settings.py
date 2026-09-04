import pytest
from pydantic import ValidationError
from pytest import MonkeyPatch

from tuck_api.settings import Settings


def test_settings_load_database_url_from_environment(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv(
        "TUCK_DATABASE_URL",
        "postgresql+asyncpg://test_user:test_password@localhost:5432/tuck_test",
    )
    monkeypatch.setenv("TUCK_ENVIRONMENT", "test")

    settings = Settings(_env_file=None)

    assert str(settings.database_url) == (
        "postgresql+asyncpg://test_user:test_password@localhost:5432/tuck_test"
    )
    assert settings.environment == "test"


def test_settings_reject_non_async_postgresql_url(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv(
        "TUCK_DATABASE_URL",
        "postgresql://test_user:test_password@localhost:5432/tuck_test",
    )

    with pytest.raises(ValidationError, match="postgresql\\+asyncpg"):
        Settings(_env_file=None)
