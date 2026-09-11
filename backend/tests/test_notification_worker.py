import asyncio
import logging
import subprocess
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pytest import LogCaptureFixture, MonkeyPatch
from sqlalchemy import select

from tuck_api.db import create_engine, create_session_factory, session_scope
from tuck_api.models import (
    Base,
    NotificationDelivery,
    PushSubscription,
    Reminder,
    ReminderRecipient,
    User,
)
from tuck_api.notification_deliveries import claim_due_deliveries, materialize_due_deliveries
from tuck_api.notification_worker import (
    WorkerPassResult,
    create_gateway,
    run_worker_loop,
    run_worker_once,
)
from tuck_api.notification_worker import logger as worker_logger
from tuck_api.security import hash_password
from tuck_api.settings import Settings
from tuck_api.web_push import NotificationPayload, PushResult, PushSubscriptionData


class RecordingGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[PushSubscriptionData, NotificationPayload]] = []

    def send(self, subscription: PushSubscriptionData, payload: NotificationPayload) -> PushResult:
        self.calls.append((subscription, payload))
        return PushResult.success()


def test_worker_cli_exposes_single_pass_and_health_check() -> None:
    result = subprocess.run(
        ["uv", "run", "tuck-reminder-worker", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "--once" in result.stdout
    assert "--health-check" in result.stdout


def test_worker_readiness_rejects_empty_vapid_keys() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://tuck:password@localhost/tuck",
        vapid_public_key="",
        vapid_private_key="",
        vapid_subject="mailto:admin@example.com",
        _env_file=None,
    )

    with pytest.raises(RuntimeError, match="complete VAPID"):
        create_gateway(settings)


def test_single_pass_mode_runs_once_and_logs_only_delivery_counts(
    caplog: LogCaptureFixture,
    monkeypatch: MonkeyPatch,
) -> None:
    calls = 0

    async def run_pass() -> WorkerPassResult:
        nonlocal calls
        calls += 1
        return WorkerPassResult(materialized=1, claimed=1, sent=1, retryable=0, failed=0)

    monkeypatch.setattr(worker_logger, "disabled", False)
    with caplog.at_level(logging.INFO, logger="tuck_api.notification_worker"):
        asyncio.run(
            run_worker_loop(
                run_pass,
                poll_seconds=0.01,
                single_pass=True,
                stop_event=asyncio.Event(),
            )
        )

    assert calls == 1
    assert "worker_pass_complete" in caplog.text
    assert "materialized=1 claimed=1 sent=1 retryable=0 failed=0" in caplog.text
    assert "endpoint" not in caplog.text


def test_worker_loop_shuts_down_cleanly_after_stop_request(
    caplog: LogCaptureFixture, monkeypatch: MonkeyPatch
) -> None:
    calls = 0
    stop_event = asyncio.Event()

    async def run_pass() -> WorkerPassResult:
        nonlocal calls
        calls += 1
        if calls == 2:
            stop_event.set()
        return WorkerPassResult(materialized=0, claimed=0, sent=0, retryable=0, failed=0)

    monkeypatch.setattr(worker_logger, "disabled", False)
    with caplog.at_level(logging.INFO, logger="tuck_api.notification_worker"):
        asyncio.run(
            run_worker_loop(
                run_pass,
                poll_seconds=0.001,
                single_pass=False,
                stop_event=stop_event,
            )
        )

    assert calls == 2
    assert "worker_stopped" in caplog.text


def test_single_pass_recovers_expired_claim_without_duplicate_success(
    isolated_database_url: str,
) -> None:
    claimed_at = datetime.now(UTC)
    recovered_at = claimed_at + timedelta(minutes=6)
    gateway = RecordingGateway()

    async def exercise() -> tuple[str, int, int]:
        engine = create_engine(isolated_database_url)
        factory = create_session_factory(engine)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            async with session_scope(factory) as database:
                user = User(id=uuid4(), username="niki", password_hash=hash_password("password"))
                database.add(user)
                await database.flush()
                reminder = Reminder(
                    creator_user_id=user.id,
                    title="Private appointment",
                    detail="Private details",
                    due_at_utc=claimed_at - timedelta(minutes=1),
                    source_timezone="Australia/Brisbane",
                    is_urgent=False,
                )
                reminder.recipient_links = [ReminderRecipient(user_id=user.id)]
                database.add(reminder)
                database.add(
                    PushSubscription(
                        user_id=user.id,
                        endpoint="https://push.example.test/subscription",
                        p256dh="public-key",
                        auth="auth-secret",
                    )
                )
                await database.flush()
                assert await materialize_due_deliveries(database, now=claimed_at) == 1
            async with session_scope(factory) as database:
                claimed = await claim_due_deliveries(
                    database,
                    worker_id="crashed-worker",
                    now=claimed_at,
                    lease_duration=timedelta(minutes=5),
                    limit=10,
                )
                assert len(claimed) == 1

            first = await run_worker_once(
                factory,
                gateway=gateway,
                worker_id="replacement-worker",
                now=recovered_at,
                lease_duration=timedelta(minutes=5),
                batch_size=10,
                max_attempts=5,
            )
            second = await run_worker_once(
                factory,
                gateway=gateway,
                worker_id="replacement-worker",
                now=recovered_at,
                lease_duration=timedelta(minutes=5),
                batch_size=10,
                max_attempts=5,
            )
            async with factory() as database:
                delivery = await database.scalar(select(NotificationDelivery))
                assert delivery is not None
                return delivery.status, first.sent, second.claimed
        finally:
            await engine.dispose()

    status, first_sent, second_claimed = asyncio.run(exercise())

    assert status == "sent"
    assert first_sent == 1
    assert second_claimed == 0
    assert len(gateway.calls) == 1
    assert "Private" not in str(gateway.calls[0][1])
