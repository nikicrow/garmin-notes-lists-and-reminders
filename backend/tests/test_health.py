import asyncio

from httpx import ASGITransport, AsyncClient

from tuck_api.main import app


def test_health_reports_service_is_live() -> None:
    async def get_health() -> tuple[int, object]:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health")
        return response.status_code, response.json()

    status_code, body = asyncio.run(get_health())

    assert status_code == 200
    assert body == {"status": "ok"}
