import asyncio
from typing import cast

import pytest
from httpx import ASGITransport, AsyncClient
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


def test_authorized_user_adds_and_lists_items_in_stable_order(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))

    async def exercise_items() -> tuple[
        dict[str, object], dict[str, object], list[dict[str, object]]
    ]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            resource = await client.post("/api/v1/lists", json={"title": "Shopping"})
            path = f"/api/v1/lists/{resource.json()['id']}/items"
            first = await client.post(path, json={"body": "Milk"})
            second = await client.post(path, json={"body": "Bread"})
            listed = await client.get(path)
        assert first.status_code == 201
        assert second.status_code == 201
        assert listed.status_code == 200
        return first.json(), second.json(), listed.json()

    try:
        first, second, listed = asyncio.run(exercise_items())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert first["body"] == "Milk"
    assert first["position"] == 0
    assert first["completed_at"] is None
    assert first["completed_by_user_id"] is None
    assert isinstance(first["id"], str)
    assert isinstance(first["list_id"], str)
    assert isinstance(first["created_by_user_id"], str)
    assert isinstance(first["created_at"], str)
    assert isinstance(first["updated_at"], str)
    assert second["position"] == 1
    assert listed == [first, second]


def test_concurrent_adds_receive_unique_contiguous_positions(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))

    async def add_concurrently() -> tuple[list[int], list[dict[str, object]]]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            resource = await client.post("/api/v1/lists", json={"title": "Shopping"})
            path = f"/api/v1/lists/{resource.json()['id']}/items"
            responses = await asyncio.gather(
                *(client.post(path, json={"body": f"Item {index}"}) for index in range(8))
            )
            listed = await client.get(path)
        return [response.status_code for response in responses], listed.json()

    try:
        statuses, listed = asyncio.run(add_concurrently())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert statuses == [201] * 8
    assert [item["position"] for item in listed] == list(range(8))
    assert {item["body"] for item in listed} == {f"Item {index}" for index in range(8)}


def test_item_creation_rejects_server_owned_fields(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    user_ids = asyncio.run(create_accounts(isolated_database_url))

    async def create_with_server_fields() -> int:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            resource = await client.post("/api/v1/lists", json={"title": "Shopping"})
            response = await client.post(
                f"/api/v1/lists/{resource.json()['id']}/items",
                json={
                    "body": "Forged",
                    "position": 99,
                    "created_by_user_id": user_ids["ben"],
                    "created_at": "2000-01-01T00:00:00Z",
                },
            )
        return response.status_code

    try:
        response_status = asyncio.run(create_with_server_fields())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert response_status == 422


def test_authorized_user_edits_checks_unchecks_and_deletes_an_item(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))

    async def exercise_items() -> tuple[
        dict[str, object], dict[str, object], list[dict[str, object]]
    ]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            resource = await client.post("/api/v1/lists", json={"title": "Shopping"})
            path = f"/api/v1/lists/{resource.json()['id']}/items"
            first = await client.post(path, json={"body": "Milk"})
            second = await client.post(path, json={"body": "Bred"})
            await client.post(path, json={"body": "Eggs"})
            edited = await client.patch(
                f"{path}/{second.json()['id']}", json={"body": "Bread", "is_checked": True}
            )
            unchecked = await client.patch(
                f"{path}/{second.json()['id']}", json={"is_checked": False}
            )
            deleted = await client.delete(f"{path}/{first.json()['id']}")
            listed = await client.get(path)
        assert edited.status_code == 200
        assert unchecked.status_code == 200
        assert deleted.status_code == 204
        assert listed.status_code == 200
        return edited.json(), unchecked.json(), listed.json()

    try:
        edited, unchecked, listed = asyncio.run(exercise_items())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert edited["body"] == "Bread"
    assert isinstance(edited["completed_at"], str)
    assert edited["completed_by_user_id"] == edited["created_by_user_id"]
    assert unchecked["completed_at"] is None
    assert unchecked["completed_by_user_id"] is None
    assert [(item["body"], item["position"]) for item in listed] == [
        ("Bread", 0),
        ("Eggs", 1),
    ]


def test_shared_member_can_mutate_items_while_unrelated_user_cannot(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    user_ids = asyncio.run(create_accounts(isolated_database_url))

    async def exercise_permissions() -> tuple[int, int, int, int, list[dict[str, object]]]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            resource = await client.post("/api/v1/lists", json={"title": "Shopping"})
            path = f"/api/v1/lists/{resource.json()['id']}/items"
            await client.put(f"/api/v1/lists/{resource.json()['id']}/members/{user_ids['ben']}")
            await login(client, "ben")
            added = await client.post(path, json={"body": "Milk"})
            edited = await client.patch(f"{path}/{added.json()['id']}", json={"is_checked": True})
            await login(client, "visitor")
            denied_list = await client.get(path)
            denied_add = await client.post(path, json={"body": "Intrusion"})
            await login(client, "niki")
            listed = await client.get(path)
        return (
            added.status_code,
            edited.status_code,
            denied_list.status_code,
            denied_add.status_code,
            listed.json(),
        )

    try:
        added, edited, denied_list, denied_add, listed = asyncio.run(exercise_permissions())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert (added, edited) == (201, 200)
    assert (denied_list, denied_add) == (404, 404)
    assert listed[0]["created_by_user_id"] == user_ids["ben"]
    assert isinstance(listed[0]["completed_at"], str)
    assert listed[0]["completed_by_user_id"] == user_ids["ben"]


def test_authorized_user_reorders_every_item_by_position(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))

    async def exercise_reorder() -> list[dict[str, object]]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            resource = await client.post("/api/v1/lists", json={"title": "Shopping"})
            path = f"/api/v1/lists/{resource.json()['id']}/items"
            first = await client.post(path, json={"body": "Milk"})
            second = await client.post(path, json={"body": "Bread"})
            third = await client.post(path, json={"body": "Eggs"})
            reordered = await client.put(
                f"{path}/reorder",
                json={
                    "positions": [
                        {"item_id": third.json()["id"], "position": 0},
                        {"item_id": first.json()["id"], "position": 1},
                        {"item_id": second.json()["id"], "position": 2},
                    ]
                },
            )
        assert reordered.status_code == 200
        return cast(list[dict[str, object]], reordered.json())

    try:
        reordered = asyncio.run(exercise_reorder())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert [(item["body"], item["position"]) for item in reordered] == [
        ("Eggs", 0),
        ("Milk", 1),
        ("Bread", 2),
    ]


@pytest.mark.parametrize("requested_positions", [[0, 0], [0, 2]])
def test_reorder_rejects_conflicting_or_noncontiguous_positions(
    requested_positions: list[int],
    isolated_database_url: str,
    monkeypatch: MonkeyPatch,
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))

    async def exercise_invalid_reorder() -> tuple[int, dict[str, object], list[dict[str, object]]]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            resource = await client.post("/api/v1/lists", json={"title": "Shopping"})
            path = f"/api/v1/lists/{resource.json()['id']}/items"
            first = await client.post(path, json={"body": "Milk"})
            second = await client.post(path, json={"body": "Bread"})
            reordered = await client.put(
                f"{path}/reorder",
                json={
                    "positions": [
                        {"item_id": first.json()["id"], "position": requested_positions[0]},
                        {"item_id": second.json()["id"], "position": requested_positions[1]},
                    ]
                },
            )
            listed = await client.get(path)
        return reordered.status_code, reordered.json(), listed.json()

    try:
        response_status, response_body, listed = asyncio.run(exercise_invalid_reorder())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert response_status == 409
    assert response_body == {
        "detail": "Reorder must assign every item exactly once to contiguous positions"
    }
    assert [(item["body"], item["position"]) for item in listed] == [
        ("Milk", 0),
        ("Bread", 1),
    ]
