from typing import Literal

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env",
        env_prefix="TUCK_",
        extra="ignore",
    )

    database_url: PostgresDsn = Field(repr=False)
    environment: Literal["development", "test", "production"] = "development"

    @field_validator("database_url")
    @classmethod
    def require_asyncpg_driver(cls, value: PostgresDsn) -> PostgresDsn:
        if value.scheme != "postgresql+asyncpg":
            raise ValueError("database URL must use the postgresql+asyncpg scheme")
        return value
