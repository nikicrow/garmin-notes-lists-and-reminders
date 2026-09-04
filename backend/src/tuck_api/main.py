from functools import lru_cache

from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from tuck_api.settings import Settings

app = FastAPI(title="Tuck API")


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


@app.get("/api/v1/ready")
def readiness() -> dict[str, str]:
    try:
        get_settings()
    except ValidationError as error:
        raise HTTPException(
            status_code=503,
            detail="Application configuration is invalid",
        ) from error
    return {"status": "ready"}
