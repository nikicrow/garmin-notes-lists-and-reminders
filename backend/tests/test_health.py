import asyncio

from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch

from tuck_api.main import app, get_settings


def test_health_reports_service_is_live() -> None:
    async def get_health() -> tuple[int, object]:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health")
        return response.status_code, response.json()

    status_code, body = asyncio.run(get_health())

    assert status_code == 200
    assert body == {"status": "ok"}


def test_readiness_reports_configured_service_is_ready(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv(
        "TUCK_DATABASE_URL",
        "postgresql+asyncpg://test_user:test_password@localhost:5432/tuck_test",
    )

    async def get_readiness() -> tuple[int, object]:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/ready")
        return response.status_code, response.json()

    get_settings.cache_clear()
    try:
        status_code, body = asyncio.run(get_readiness())
    finally:
        get_settings.cache_clear()

    assert status_code == 200
    assert body == {"status": "ready"}


def test_readiness_reports_unavailable_for_invalid_configuration(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("TUCK_DATABASE_URL", "not-a-database-url")

    async def get_readiness() -> tuple[int, str]:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/ready")
        return response.status_code, response.text

    get_settings.cache_clear()
    try:
        status_code, body = asyncio.run(get_readiness())
    finally:
        get_settings.cache_clear()

    assert status_code == 503
    assert body == '{"detail":"Application configuration is invalid"}'
