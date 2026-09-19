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


def test_settings_load_typed_notification_configuration(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv(
        "TUCK_DATABASE_URL",
        "postgresql+asyncpg://test_user:test_password@localhost:5432/tuck_test",
    )
    monkeypatch.setenv("TUCK_VAPID_PUBLIC_KEY", "public-key")
    monkeypatch.setenv("TUCK_VAPID_PRIVATE_KEY", "private-key")
    monkeypatch.setenv("TUCK_VAPID_SUBJECT", "mailto:admin@example.com")
    monkeypatch.setenv("TUCK_NOTIFICATION_WORKER_POLL_SECONDS", "2.5")
    monkeypatch.setenv("TUCK_NOTIFICATION_WORKER_LEASE_SECONDS", "120")
    monkeypatch.setenv("TUCK_NOTIFICATION_WORKER_BATCH_SIZE", "25")
    monkeypatch.setenv("TUCK_NOTIFICATION_WORKER_MAX_ATTEMPTS", "4")

    settings = Settings(_env_file=None)

    assert settings.vapid_public_key == "public-key"
    assert settings.vapid_private_key is not None
    assert settings.vapid_private_key.get_secret_value() == "private-key"
    assert settings.vapid_subject == "mailto:admin@example.com"
    assert settings.notification_worker_poll_seconds == 2.5
    assert settings.notification_worker_lease_seconds == 120
    assert settings.notification_worker_batch_size == 25
    assert settings.notification_worker_max_attempts == 4
    assert "private-key" not in repr(settings)


def test_settings_reject_incomplete_vapid_configuration(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv(
        "TUCK_DATABASE_URL",
        "postgresql+asyncpg://test_user:test_password@localhost:5432/tuck_test",
    )
    monkeypatch.setenv("TUCK_VAPID_PUBLIC_KEY", "public-key")

    with pytest.raises(ValidationError, match="VAPID settings must be provided together"):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    ("environment_name", "invalid_value"),
    [
        ("TUCK_NOTIFICATION_WORKER_POLL_SECONDS", "0"),
        ("TUCK_NOTIFICATION_WORKER_LEASE_SECONDS", "0"),
        ("TUCK_NOTIFICATION_WORKER_BATCH_SIZE", "0"),
        ("TUCK_NOTIFICATION_WORKER_MAX_ATTEMPTS", "0"),
    ],
)
def test_settings_require_positive_worker_limits(
    monkeypatch: MonkeyPatch, environment_name: str, invalid_value: str
) -> None:
    monkeypatch.setenv(
        "TUCK_DATABASE_URL",
        "postgresql+asyncpg://test_user:test_password@localhost:5432/tuck_test",
    )
    monkeypatch.setenv(environment_name, invalid_value)

    with pytest.raises(ValidationError, match="greater than 0"):
        Settings(_env_file=None)


def test_settings_require_vapid_contact_uri(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv(
        "TUCK_DATABASE_URL",
        "postgresql+asyncpg://test_user:test_password@localhost:5432/tuck_test",
    )
    monkeypatch.setenv("TUCK_VAPID_PUBLIC_KEY", "public-key")
    monkeypatch.setenv("TUCK_VAPID_PRIVATE_KEY", "private-key")
    monkeypatch.setenv("TUCK_VAPID_SUBJECT", "admin@example.com")

    with pytest.raises(ValidationError, match="mailto: or https://"):
        Settings(_env_file=None)
