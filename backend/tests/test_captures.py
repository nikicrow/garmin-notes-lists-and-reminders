import asyncio
from uuid import uuid4

from httpx import ASGITransport, AsyncClient, Response
from pytest import MonkeyPatch
from sqlalchemy import func, select

from tuck_api.db import create_engine, create_session_factory, get_session_factory, session_scope
from tuck_api.main import app, get_settings
from tuck_api.models import AgentActionExecution, Base, Capture, Note, User
from tuck_api.security import hash_password


def configure_app(monkeypatch: MonkeyPatch, isolated_database_url: str) -> None:
    monkeypatch.setenv("TUCK_DATABASE_URL", isolated_database_url)
    monkeypatch.setenv("TUCK_ENVIRONMENT", "test")
    get_settings.cache_clear()
    get_session_factory.cache_clear()


async def create_account(isolated_database_url: str) -> None:
    engine = create_engine(isolated_database_url)
    factory = create_session_factory(engine)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_scope(factory) as database:
            database.add(User(username="niki", password_hash=hash_password("niki password")))
    finally:
        await engine.dispose()


async def login(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "niki", "password": "niki password"},
    )
    assert response.status_code == 200


def test_text_capture_executes_and_retries_idempotently(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_account(isolated_database_url))
    request_id = str(uuid4())

    async def exercise() -> tuple[Response, Response, int, int, int]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client)
            payload = {
                "raw_text": "Note: book the dentist",
                "source_request_id": request_id,
                "occurred_at": "2026-09-20T10:00:00+10:00",
                "client_timezone": "Australia/Sydney",
            }
            first = await client.post("/api/v1/captures/text", json=payload)
            repeated = await client.post("/api/v1/captures/text", json=payload)

        factory = get_session_factory()
        async with session_scope(factory) as database:
            return (
                first,
                repeated,
                int(await database.scalar(select(func.count()).select_from(Capture)) or 0),
                int(await database.scalar(select(func.count()).select_from(Note)) or 0),
                int(
                    await database.scalar(select(func.count()).select_from(AgentActionExecution))
                    or 0
                ),
            )

    try:
        first, repeated, captures, notes, actions = asyncio.run(exercise())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert first.status_code == 201
    assert first.json()["status"] == "completed"
    assert first.json()["receipt"] == "Saved note: book the dentist."
    assert repeated.status_code == 200
    assert repeated.json() == first.json()
    assert (captures, notes, actions) == (1, 1, 1)


def test_ambiguous_capture_enters_review_and_can_be_corrected(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_account(isolated_database_url))

    async def exercise() -> tuple[Response, Response, Response]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client)
            created = await client.post(
                "/api/v1/captures/text",
                json={
                    "raw_text": "Maybe deal with that thing later",
                    "source_request_id": str(uuid4()),
                    "occurred_at": "2026-09-20T10:00:00+10:00",
                    "client_timezone": "Australia/Sydney",
                },
            )
            inbox = await client.get("/api/v1/captures?status=needs_review")
            corrected = await client.post(
                f"/api/v1/captures/{created.json()['id']}/confirm",
                json={
                    "schema_version": "1",
                    "actions": [{"type": "create_note", "body": "Deal with that thing"}],
                    "ambiguities": [],
                },
            )
        return created, inbox, corrected

    try:
        created, inbox, corrected = asyncio.run(exercise())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert created.status_code == 201
    assert created.json()["status"] == "needs_review"
    assert inbox.json() == [created.json()]
    assert corrected.status_code == 200
    assert corrected.json()["status"] == "completed"
    assert corrected.json()["receipt"] == "Saved note: Deal with that thing."
