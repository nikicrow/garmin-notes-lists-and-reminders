from functools import lru_cache
from typing import Literal

from pydantic import (
    Field,
    PositiveFloat,
    PositiveInt,
    PostgresDsn,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env",
        env_prefix="TUCK_",
        extra="ignore",
    )

    database_url: PostgresDsn = Field(repr=False)
    environment: Literal["development", "test", "production"] = "development"
    vapid_public_key: str | None = None
    vapid_private_key: SecretStr | None = Field(default=None, repr=False)
    vapid_subject: str | None = None
    notification_worker_poll_seconds: PositiveFloat = 5.0
    notification_worker_batch_size: PositiveInt = 100
    notification_worker_max_attempts: PositiveInt = 5

    @field_validator("database_url")
    @classmethod
    def require_asyncpg_driver(cls, value: PostgresDsn) -> PostgresDsn:
        if value.scheme != "postgresql+asyncpg":
            raise ValueError("database URL must use the postgresql+asyncpg scheme")
        return value

    @field_validator("vapid_subject")
    @classmethod
    def require_vapid_contact_uri(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith(("mailto:", "https://")):
            raise ValueError("VAPID subject must start with mailto: or https://")
        return value

    @model_validator(mode="after")
    def require_complete_vapid_configuration(self) -> "Settings":
        vapid_values = (self.vapid_public_key, self.vapid_private_key, self.vapid_subject)
        if any(value is not None for value in vapid_values) and not all(
            value is not None for value in vapid_values
        ):
            raise ValueError("VAPID settings must be provided together")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
