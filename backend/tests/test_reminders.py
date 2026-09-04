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


async def create_reminder(client: AsyncClient, title: str = "Appointment") -> Response:
    return await client.post(
        "/api/v1/reminders",
        json={
            "title": title,
            "detail": "Bring paperwork",
            "due_at_utc": "2026-10-01T04:30:00Z",
            "source_timezone": "Australia/Brisbane",
            "is_urgent": True,
        },
    )


def test_owner_can_use_the_one_time_reminder_lifecycle(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))

    async def exercise_reminders() -> tuple[Response, ...]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            created = await create_reminder(client)
            reminder_id = created.json()["id"]
            listed = await client.get("/api/v1/reminders")
            fetched = await client.get(f"/api/v1/reminders/{reminder_id}")
            edited = await client.patch(
                f"/api/v1/reminders/{reminder_id}",
                json={"title": "Dentist", "detail": None, "is_urgent": False},
            )
            rescheduled = await client.post(
                f"/api/v1/reminders/{reminder_id}/reschedule",
                json={
                    "due_at_utc": "2026-10-02T05:00:00+00:00",
                    "source_timezone": "Australia/Sydney",
                },
            )
            snoozed = await client.post(
                f"/api/v1/reminders/{reminder_id}/snooze",
                json={"due_at_utc": "2026-10-02T05:15:00Z"},
            )
            completed_reminder = await create_reminder(client, "Complete me")
            completed = await client.post(
                f"/api/v1/reminders/{completed_reminder.json()['id']}/complete"
            )
            cancelled_reminder = await create_reminder(client, "Cancel me")
            cancelled = await client.post(
                f"/api/v1/reminders/{cancelled_reminder.json()['id']}/cancel"
            )
        return created, listed, fetched, edited, rescheduled, snoozed, completed, cancelled

    try:
        responses = asyncio.run(exercise_reminders())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    created, listed, fetched, edited, rescheduled, snoozed, completed, cancelled = responses
    assert created.status_code == 201
    reminder = created.json()
    assert reminder["title"] == "Appointment"
    assert reminder["detail"] == "Bring paperwork"
    assert reminder["due_at_utc"] == "2026-10-01T04:30:00Z"
    assert reminder["source_timezone"] == "Australia/Brisbane"
    assert reminder["is_urgent"] is True
    assert reminder["status"] == "pending"
    assert reminder["completed_at"] is None
    assert reminder["cancelled_at"] is None
    assert isinstance(reminder["id"], str)
    assert isinstance(reminder["created_at"], str)
    assert isinstance(reminder["updated_at"], str)
    assert listed.status_code == 200
    assert listed.json() == [reminder]
    assert fetched.json() == reminder
    assert edited.status_code == 200
    assert edited.json()["title"] == "Dentist"
    assert edited.json()["detail"] is None
    assert edited.json()["is_urgent"] is False
    assert rescheduled.status_code == 200
    assert rescheduled.json()["due_at_utc"] == "2026-10-02T05:00:00Z"
    assert rescheduled.json()["source_timezone"] == "Australia/Sydney"
    assert snoozed.status_code == 200
    assert snoozed.json()["due_at_utc"] == "2026-10-02T05:15:00Z"
    assert snoozed.json()["source_timezone"] == "Australia/Sydney"
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["completed_at"] is not None
    assert completed.json()["cancelled_at"] is None
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["cancelled_at"] is not None
    assert cancelled.json()["completed_at"] is None


def test_reminder_creation_validates_due_time_timezone_and_owned_fields(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))

    invalid_payloads: list[dict[str, object]] = [
        {
            "title": "   ",
            "due_at_utc": "2026-10-01T04:30:00Z",
            "source_timezone": "Australia/Brisbane",
        },
        {
            "title": "Bad timezone",
            "due_at_utc": "2026-10-01T04:30:00Z",
            "source_timezone": "Moon/Tranquility",
        },
        {
            "title": "Naive time",
            "due_at_utc": "2026-10-01T04:30:00",
            "source_timezone": "Australia/Brisbane",
        },
        {
            "title": "Past time",
            "due_at_utc": "2000-01-01T00:00:00Z",
            "source_timezone": "Australia/Brisbane",
        },
        {
            "title": "Forged metadata",
            "due_at_utc": "2026-10-01T04:30:00Z",
            "source_timezone": "Australia/Brisbane",
            "status": "completed",
            "creator_user_id": "00000000-0000-0000-0000-000000000000",
            "created_at": "2000-01-01T00:00:00Z",
        },
    ]

    async def attempt_invalid_creates() -> list[Response]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            return [
                await client.post("/api/v1/reminders", json=payload) for payload in invalid_payloads
            ]

    try:
        responses = asyncio.run(attempt_invalid_creates())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert [response.status_code for response in responses] == [422, 422, 422, 422, 422]


def test_user_cannot_access_another_users_reminder(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))

    async def attempt_cross_user_access() -> tuple[Response, ...]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            created = await create_reminder(client, "Niki only")
            reminder_id = created.json()["id"]
            await login(client, "ben")
            listed = await client.get("/api/v1/reminders")
            fetched = await client.get(f"/api/v1/reminders/{reminder_id}")
            edited = await client.patch(
                f"/api/v1/reminders/{reminder_id}", json={"title": "Intrusion"}
            )
            completed = await client.post(f"/api/v1/reminders/{reminder_id}/complete")
            cancelled = await client.post(f"/api/v1/reminders/{reminder_id}/cancel")
            snoozed = await client.post(
                f"/api/v1/reminders/{reminder_id}/snooze",
                json={"due_at_utc": "2026-10-02T05:15:00Z"},
            )
            rescheduled = await client.post(
                f"/api/v1/reminders/{reminder_id}/reschedule",
                json={
                    "due_at_utc": "2026-10-02T05:15:00Z",
                    "source_timezone": "Australia/Brisbane",
                },
            )
        return listed, fetched, edited, completed, cancelled, snoozed, rescheduled

    try:
        responses = asyncio.run(attempt_cross_user_access())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    listed, *resource_responses = responses
    assert listed.status_code == 200
    assert listed.json() == []
    assert [(response.status_code, response.json()) for response in resource_responses] == [
        (404, {"detail": "Reminder not found"})
    ] * 6


def test_completed_reminder_rejects_further_changes(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))

    async def attempt_changes() -> tuple[Response, ...]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            created = await create_reminder(client)
            reminder_id = created.json()["id"]
            await client.post(f"/api/v1/reminders/{reminder_id}/complete")
            edited = await client.patch(
                f"/api/v1/reminders/{reminder_id}", json={"title": "Too late"}
            )
            cancelled = await client.post(f"/api/v1/reminders/{reminder_id}/cancel")
            snoozed = await client.post(
                f"/api/v1/reminders/{reminder_id}/snooze",
                json={"due_at_utc": "2026-10-02T05:15:00Z"},
            )
        return edited, cancelled, snoozed

    try:
        responses = asyncio.run(attempt_changes())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert [(response.status_code, response.json()) for response in responses] == [
        (409, {"detail": "Reminder is no longer pending"})
    ] * 3


def test_reminder_edit_rejects_empty_or_null_required_fields(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))

    async def attempt_invalid_edits() -> list[Response]:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="https://test",
        ) as client:
            await login(client, "niki")
            created = await create_reminder(client)
            reminder_url = f"/api/v1/reminders/{created.json()['id']}"
            return [
                await client.patch(reminder_url, json={}),
                await client.patch(reminder_url, json={"title": None}),
                await client.patch(reminder_url, json={"is_urgent": None}),
            ]

    try:
        responses = asyncio.run(attempt_invalid_edits())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert [response.status_code for response in responses] == [422, 422, 422]


def test_terminal_reminder_transitions_are_atomic(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))

    async def race_transitions() -> tuple[tuple[Response, Response], Response]:
        async with (
            AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as creator,
            AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as completer,
            AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as canceller,
        ):
            await asyncio.gather(
                login(creator, "niki"), login(completer, "niki"), login(canceller, "niki")
            )
            created = await create_reminder(creator)
            reminder_url = f"/api/v1/reminders/{created.json()['id']}"
            responses = await asyncio.gather(
                completer.post(f"{reminder_url}/complete"),
                canceller.post(f"{reminder_url}/cancel"),
            )
            fetched = await creator.get(reminder_url)
        return responses, fetched

    try:
        responses, fetched = asyncio.run(race_transitions())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert sorted(response.status_code for response in responses) == [200, 409]
    reminder = fetched.json()
    assert (reminder["completed_at"] is None) != (reminder["cancelled_at"] is None)
