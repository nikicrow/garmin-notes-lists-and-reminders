import asyncio

from httpx import ASGITransport, AsyncClient, Response
from pytest import MonkeyPatch

from tuck_api.db import create_engine, create_session_factory, get_session_factory, session_scope
from tuck_api.main import app, get_settings
from tuck_api.models import Base, User
from tuck_api.security import hash_password


def configure_app(monkeypatch: MonkeyPatch, isolated_database_url: str) -> None:
    monkeypatch.setenv("TUCK_DATABASE_URL", isolated_database_url)
    monkeypatch.setenv("TUCK_ENVIRONMENT", "test")
    get_settings.cache_clear()
    get_session_factory.cache_clear()


async def create_accounts(isolated_database_url: str) -> None:
    engine = create_engine(isolated_database_url)
    factory = create_session_factory(engine)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_scope(factory) as database:
            database.add_all(
                [
                    User(username="niki", password_hash=hash_password("niki password")),
                    User(username="ben", password_hash=hash_password("ben password")),
                ]
            )
    finally:
        await engine.dispose()


async def login(client: AsyncClient, username: str) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": f"{username} password"},
    )
    assert response.status_code == 200


def test_owner_can_create_and_list_notes_with_server_generated_metadata(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))

    async def exercise_notes() -> tuple[int, dict[str, object], int, object]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            created = await client.post("/api/v1/notes", json={"body": "Buy milk"})
            listed = await client.get("/api/v1/notes")
        return created.status_code, created.json(), listed.status_code, listed.json()

    try:
        create_status, note, list_status, notes = asyncio.run(exercise_notes())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert create_status == 201
    assert note["body"] == "Buy milk"
    assert note["archived_at"] is None
    assert isinstance(note["id"], str)
    assert isinstance(note["created_at"], str)
    assert isinstance(note["updated_at"], str)
    assert list_status == 200
    assert notes == [note]


def test_owner_can_get_edit_and_archive_a_note(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))

    async def exercise_note() -> tuple[Response, Response, Response, Response]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            created = await client.post("/api/v1/notes", json={"body": "Draft"})
            note_id = created.json()["id"]
            fetched = await client.get(f"/api/v1/notes/{note_id}")
            edited = await client.patch(f"/api/v1/notes/{note_id}", json={"body": "Finished"})
            archived = await client.delete(f"/api/v1/notes/{note_id}")
            listed = await client.get("/api/v1/notes")
        return fetched, edited, archived, listed

    try:
        fetched, edited, archived, listed = asyncio.run(exercise_note())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert fetched.status_code == 200
    assert fetched.json()["body"] == "Draft"
    assert edited.status_code == 200
    assert edited.json()["body"] == "Finished"
    assert edited.json()["updated_at"] >= edited.json()["created_at"]
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    assert listed.status_code == 200
    assert listed.json() == []


def test_user_cannot_access_another_users_note(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))

    async def attempt_cross_user_access() -> tuple[Response, Response, Response, Response]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            created = await client.post("/api/v1/notes", json={"body": "Niki only"})
            note_id = created.json()["id"]
            await login(client, "ben")
            listed = await client.get("/api/v1/notes")
            fetched = await client.get(f"/api/v1/notes/{note_id}")
            edited = await client.patch(f"/api/v1/notes/{note_id}", json={"body": "Intrusion"})
            archived = await client.delete(f"/api/v1/notes/{note_id}")
        return listed, fetched, edited, archived

    try:
        listed, fetched, edited, archived = asyncio.run(attempt_cross_user_access())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert listed.status_code == 200
    assert listed.json() == []
    assert (fetched.status_code, fetched.json()) == (404, {"detail": "Note not found"})
    assert (edited.status_code, edited.json()) == (404, {"detail": "Note not found"})
    assert (archived.status_code, archived.json()) == (404, {"detail": "Note not found"})


def test_note_creation_rejects_server_owned_fields(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))

    async def create_with_server_fields() -> Response:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            return await client.post(
                "/api/v1/notes",
                json={
                    "body": "Forged metadata",
                    "created_at": "2000-01-01T00:00:00Z",
                    "owner_user_id": "00000000-0000-0000-0000-000000000000",
                },
            )

    try:
        response = asyncio.run(create_with_server_fields())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert response.status_code == 422
