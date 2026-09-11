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


async def create_accounts(isolated_database_url: str) -> dict[str, str]:
    engine = create_engine(isolated_database_url)
    factory = create_session_factory(engine)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_scope(factory) as database:
            users = [
                User(username="niki", password_hash=hash_password("niki password")),
                User(username="ben", password_hash=hash_password("ben password")),
                User(username="visitor", password_hash=hash_password("visitor password")),
            ]
            database.add_all(users)
            await database.flush()
            return {user.username: str(user.id) for user in users}
    finally:
        await engine.dispose()


async def login(client: AsyncClient, username: str) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": f"{username} password"},
    )
    assert response.status_code == 200


def test_owner_creates_and_lists_a_private_list_with_server_metadata(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))

    async def exercise_lists() -> tuple[int, dict[str, object], int, object]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            created = await client.post("/api/v1/lists", json={"title": "Shopping"})
            listed = await client.get("/api/v1/lists")
        return created.status_code, created.json(), listed.status_code, listed.json()

    try:
        create_status, created, list_status, listed = asyncio.run(exercise_lists())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert create_status == 201
    assert created["title"] == "Shopping"
    assert created["shared_user_ids"] == []
    assert created["archived_at"] is None
    assert isinstance(created["id"], str)
    assert isinstance(created["owner_user_id"], str)
    assert isinstance(created["created_at"], str)
    assert isinstance(created["updated_at"], str)
    assert list_status == 200
    assert listed == [created]


def test_list_creation_rejects_server_owned_fields(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    user_ids = asyncio.run(create_accounts(isolated_database_url))

    async def create_with_server_fields() -> Response:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            return await client.post(
                "/api/v1/lists",
                json={
                    "title": "Forged",
                    "owner_user_id": user_ids["ben"],
                    "created_at": "2000-01-01T00:00:00Z",
                },
            )

    try:
        response = asyncio.run(create_with_server_fields())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert response.status_code == 422


def test_owner_gets_renames_and_archives_a_list(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))

    async def exercise_list() -> tuple[Response, Response, Response, Response]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            created = await client.post("/api/v1/lists", json={"title": "Draft"})
            list_id = created.json()["id"]
            fetched = await client.get(f"/api/v1/lists/{list_id}")
            renamed = await client.patch(f"/api/v1/lists/{list_id}", json={"title": "Shopping"})
            archived = await client.delete(f"/api/v1/lists/{list_id}")
            listed = await client.get("/api/v1/lists")
        return fetched, renamed, archived, listed

    try:
        fetched, renamed, archived, listed = asyncio.run(exercise_list())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert fetched.status_code == 200
    assert fetched.json()["title"] == "Draft"
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Shopping"
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    assert listed.json() == []


def test_sharing_grants_access_and_unsharing_removes_it(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    user_ids = asyncio.run(create_accounts(isolated_database_url))

    async def exercise_sharing() -> tuple[
        Response, Response, Response, Response, Response, Response, Response
    ]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            created = await client.post("/api/v1/lists", json={"title": "Shopping"})
            list_id = created.json()["id"]
            shared = await client.put(f"/api/v1/lists/{list_id}/members/{user_ids['ben']}")
            await login(client, "ben")
            member_listed = await client.get("/api/v1/lists")
            member_fetched = await client.get(f"/api/v1/lists/{list_id}")
            member_rename = await client.patch(
                f"/api/v1/lists/{list_id}", json={"title": "Hijacked"}
            )
            await login(client, "visitor")
            unrelated_fetch = await client.get(f"/api/v1/lists/{list_id}")
            await login(client, "niki")
            unshared = await client.delete(f"/api/v1/lists/{list_id}/members/{user_ids['ben']}")
            await login(client, "ben")
            removed_fetch = await client.get(f"/api/v1/lists/{list_id}")
        return (
            shared,
            member_listed,
            member_fetched,
            member_rename,
            unrelated_fetch,
            unshared,
            removed_fetch,
        )

    try:
        shared, member_listed, member_fetched, member_rename, unrelated, unshared, removed = (
            asyncio.run(exercise_sharing())
        )
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert shared.status_code == 200
    assert shared.json()["shared_user_ids"] == [user_ids["ben"]]
    assert member_listed.json() == [shared.json()]
    assert member_fetched.status_code == 200
    assert (member_rename.status_code, member_rename.json()) == (404, {"detail": "List not found"})
    assert (unrelated.status_code, unrelated.json()) == (404, {"detail": "List not found"})
    assert unshared.status_code == 200
    assert unshared.json()["shared_user_ids"] == []
    assert (removed.status_code, removed.json()) == (404, {"detail": "List not found"})


def test_concurrent_sharing_is_idempotent(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    user_ids = asyncio.run(create_accounts(isolated_database_url))

    async def share_concurrently() -> list[Response]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            created = await client.post("/api/v1/lists", json={"title": "Shopping"})
            path = f"/api/v1/lists/{created.json()['id']}/members/{user_ids['ben']}"
            return await asyncio.gather(*(client.put(path) for _ in range(8)))

    try:
        responses = asyncio.run(share_concurrently())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert [response.status_code for response in responses] == [200] * 8
    assert all(response.json()["shared_user_ids"] == [user_ids["ben"]] for response in responses)
