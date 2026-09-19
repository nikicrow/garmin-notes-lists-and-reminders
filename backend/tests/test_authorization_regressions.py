import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from tuck_api.db import create_engine, create_session_factory, session_scope
from tuck_api.lists import get_list, share_list
from tuck_api.models import Base, List, PushSubscription, Reminder, ReminderRecipient, User
from tuck_api.push_subscriptions import revoke_push_subscription
from tuck_api.reminders import ReminderUpdate, edit_reminder, transition_reminder
from tuck_api.security import hash_password


async def seed_users(database_url: str) -> tuple[UUID, UUID]:
    engine = create_engine(database_url)
    factory = create_session_factory(engine)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_scope(factory) as database:
            owner = User(username="owner", password_hash=hash_password("owner password"))
            intruder = User(username="intruder", password_hash=hash_password("intruder password"))
            database.add_all([owner, intruder])
            await database.flush()
            return owner.id, intruder.id
    finally:
        await engine.dispose()


def assert_concealed_not_found(error: HTTPException, resource: str) -> None:
    assert error.status_code == 404
    assert error.detail == f"{resource} not found"


def test_list_domain_service_conceals_existing_and_unknown_unowned_ids(
    isolated_database_url: str,
) -> None:
    owner_id, intruder_id = asyncio.run(seed_users(isolated_database_url))

    async def exercise() -> tuple[HTTPException, HTTPException, HTTPException]:
        engine = create_engine(isolated_database_url)
        factory = create_session_factory(engine)
        try:
            async with session_scope(factory) as database:
                owner = await database.get(User, owner_id)
                intruder = await database.get(User, intruder_id)
                assert owner is not None and intruder is not None
                resource = List(owner_user_id=owner.id, title="Private")
                database.add(resource)
                await database.flush()

                errors: list[HTTPException] = []
                for operation in (
                    get_list(database, intruder, resource.id),
                    get_list(database, intruder, uuid4()),
                    share_list(database, intruder, resource.id, owner.id),
                ):
                    with pytest.raises(HTTPException) as caught:
                        await operation
                    errors.append(caught.value)
                return errors[0], errors[1], errors[2]
        finally:
            await engine.dispose()

    existing, unknown, share = asyncio.run(exercise())

    assert_concealed_not_found(existing, "List")
    assert_concealed_not_found(unknown, "List")
    assert_concealed_not_found(share, "List")


def test_reminder_domain_service_rejects_recipient_mutation(
    isolated_database_url: str,
) -> None:
    owner_id, recipient_id = asyncio.run(seed_users(isolated_database_url))

    async def exercise() -> list[HTTPException]:
        engine = create_engine(isolated_database_url)
        factory = create_session_factory(engine)
        try:
            async with session_scope(factory) as database:
                owner = await database.get(User, owner_id)
                recipient = await database.get(User, recipient_id)
                assert owner is not None and recipient is not None
                reminder = Reminder(
                    creator_user_id=owner.id,
                    title="Private",
                    detail=None,
                    due_at_utc=datetime.now(UTC) + timedelta(hours=1),
                    source_timezone="UTC",
                    is_urgent=False,
                )
                reminder.recipient_links = [ReminderRecipient(user_id=recipient.id)]
                database.add(reminder)
                await database.flush()

                errors: list[HTTPException] = []
                operations = (
                    edit_reminder(
                        database,
                        recipient,
                        reminder.id,
                        ReminderUpdate(title="Forged edit"),
                    ),
                    transition_reminder(database, recipient, reminder.id, "completed"),
                )
                for operation in operations:
                    with pytest.raises(HTTPException) as caught:
                        await operation
                    errors.append(caught.value)
                return errors
        finally:
            await engine.dispose()

    errors = asyncio.run(exercise())

    assert len(errors) == 2
    for error in errors:
        assert_concealed_not_found(error, "Reminder")


def test_push_subscription_domain_service_rejects_cross_user_revocation(
    isolated_database_url: str,
) -> None:
    owner_id, intruder_id = asyncio.run(seed_users(isolated_database_url))

    async def exercise() -> HTTPException:
        engine = create_engine(isolated_database_url)
        factory = create_session_factory(engine)
        try:
            async with session_scope(factory) as database:
                intruder = await database.get(User, intruder_id)
                assert intruder is not None
                subscription = PushSubscription(
                    user_id=owner_id,
                    endpoint="https://push.example.test/private-endpoint",
                    p256dh="private-public-key",
                    auth="private-auth-key",
                )
                database.add(subscription)
                await database.flush()
                with pytest.raises(HTTPException) as caught:
                    await revoke_push_subscription(database, intruder, subscription.id)
                return caught.value
        finally:
            await engine.dispose()

    error = asyncio.run(exercise())

    assert_concealed_not_found(error, "Push subscription")
