import argparse
import asyncio
import logging
import os
import signal
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tuck_api.db import create_engine, create_session_factory, session_scope
from tuck_api.models import NotificationDelivery
from tuck_api.notification_deliveries import (
    DeliveryStatus,
    PushGateway,
    claim_due_deliveries,
    materialize_due_deliveries,
    send_claimed_delivery,
)
from tuck_api.settings import Settings, get_settings
from tuck_api.web_push import PyWebPushGateway

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkerPassResult:
    materialized: int
    claimed: int
    sent: int
    retryable: int
    failed: int


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Tuck's durable reminder delivery worker")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="process one due-delivery batch and exit")
    mode.add_argument(
        "--health-check",
        action="store_true",
        help="verify worker configuration and database readiness, then exit",
    )
    return parser.parse_args(argv)


def create_gateway(settings: Settings) -> PyWebPushGateway:
    if (
        not settings.vapid_public_key
        or settings.vapid_private_key is None
        or not settings.vapid_private_key.get_secret_value()
        or not settings.vapid_subject
    ):
        raise RuntimeError("reminder worker requires complete VAPID configuration")
    return PyWebPushGateway(
        vapid_private_key=settings.vapid_private_key,
        vapid_subject=settings.vapid_subject,
    )


async def check_worker_readiness(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    create_gateway(settings)
    async with session_scope(session_factory) as database:
        await database.execute(text("SELECT 1"))


async def run_worker_loop(
    run_pass: Callable[[], Awaitable[WorkerPassResult]],
    *,
    poll_seconds: float,
    single_pass: bool,
    stop_event: asyncio.Event,
) -> None:
    """Run passes until requested to stop, with an interruptible polling wait."""

    try:
        while not stop_event.is_set():
            result = await run_pass()
            logger.info(
                "worker_pass_complete materialized=%d claimed=%d sent=%d retryable=%d failed=%d",
                result.materialized,
                result.claimed,
                result.sent,
                result.retryable,
                result.failed,
            )
            if single_pass or stop_event.is_set():
                return
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
            except TimeoutError:
                pass
    finally:
        logger.info("worker_stopped")


async def run_worker_once(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    gateway: PushGateway,
    worker_id: str,
    now: datetime,
    lease_duration: timedelta,
    batch_size: int,
    max_attempts: int,
) -> WorkerPassResult:
    """Materialize, claim, and send one database-backed batch."""

    async with session_scope(session_factory) as database:
        materialized = await materialize_due_deliveries(database, now=now)

    async with session_scope(session_factory) as database:
        claimed = await claim_due_deliveries(
            database,
            worker_id=worker_id,
            now=now,
            lease_duration=lease_duration,
            limit=batch_size,
        )
        delivery_ids: list[UUID] = [delivery.id for delivery in claimed]

    outcomes = {status: 0 for status in DeliveryStatus}
    for delivery_id in delivery_ids:
        async with session_scope(session_factory) as database:
            delivery = await database.get(NotificationDelivery, delivery_id)
            if (
                delivery is None
                or delivery.status != DeliveryStatus.CLAIMED
                or delivery.claimed_by != worker_id
            ):
                continue
            await send_claimed_delivery(
                database,
                delivery,
                gateway=gateway,
                now=now,
                max_attempts=max_attempts,
            )
            outcomes[DeliveryStatus(delivery.status)] += 1

    return WorkerPassResult(
        materialized=materialized,
        claimed=len(delivery_ids),
        sent=outcomes[DeliveryStatus.SENT],
        retryable=outcomes[DeliveryStatus.RETRYABLE],
        failed=outcomes[DeliveryStatus.FAILED],
    )


async def run_from_settings(*, single_pass: bool, health_check: bool) -> None:
    settings = get_settings()
    engine = create_engine(str(settings.database_url))
    session_factory = create_session_factory(engine)
    try:
        if health_check:
            await check_worker_readiness(session_factory, settings)
            logger.info("worker_ready")
            return

        gateway = create_gateway(settings)
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for handled_signal in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(handled_signal, stop_event.set)
        worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid4()}"

        async def run_pass() -> WorkerPassResult:
            return await run_worker_once(
                session_factory,
                gateway=gateway,
                worker_id=worker_id,
                now=datetime.now(UTC),
                lease_duration=timedelta(seconds=settings.notification_worker_lease_seconds),
                batch_size=settings.notification_worker_batch_size,
                max_attempts=settings.notification_worker_max_attempts,
            )

        await run_worker_loop(
            run_pass,
            poll_seconds=settings.notification_worker_poll_seconds,
            single_pass=single_pass,
            stop_event=stop_event,
        )
    finally:
        await engine.dispose()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s level=%(levelname)s logger=%(name)s message=%(message)s",
    )
    args = parse_args()
    asyncio.run(run_from_settings(single_pass=args.once, health_check=args.health_check))
