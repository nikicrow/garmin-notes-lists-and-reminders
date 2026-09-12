import asyncio
import base64
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient, Response
from pytest import MonkeyPatch
from sqlalchemy import select

from tuck_api.db import create_engine, create_session_factory, get_session_factory, session_scope
from tuck_api.main import app, get_settings
from tuck_api.models import PushSubscription, User
from tuck_api.security import hash_password

BACKEND_ROOT = Path(__file__).parents[1]
P256_PUBLIC_KEY = bytes.fromhex(
    "04"
    "6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296"
    "4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5"
)
ROTATED_P256_PUBLIC_KEY = bytes.fromhex(
    "04"
    "7cf27b188d034f7e8a52380304b51ac3c08969e277f21b35a60b48fc47669978"
    "07775510db8ed040293d9ac69f7430dbba7dade63ce982299e04b79d227873d1"
)


def configure_app(monkeypatch: MonkeyPatch, isolated_database_url: str) -> None:
    monkeypatch.setenv("TUCK_DATABASE_URL", isolated_database_url)
    monkeypatch.setenv("TUCK_ENVIRONMENT", "test")
    get_settings.cache_clear()
    get_session_factory.cache_clear()
    command.upgrade(Config(BACKEND_ROOT / "alembic.ini"), "head")


async def create_accounts(isolated_database_url: str) -> None:
    engine = create_engine(isolated_database_url)
    factory = create_session_factory(engine)
    try:
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


def subscription_payload(
    endpoint: str = "https://push.example.test/subscriptions/browser-1",
) -> dict[str, Any]:
    return {
        "endpoint": endpoint,
        "expirationTime": None,
        "keys": {
            "p256dh": base64.urlsafe_b64encode(P256_PUBLIC_KEY).rstrip(b"=").decode(),
            "auth": base64.urlsafe_b64encode(bytes(range(16))).rstrip(b"=").decode(),
        },
    }


def test_authenticated_user_can_get_vapid_public_key(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    monkeypatch.setenv("TUCK_VAPID_PUBLIC_KEY", "server-public-key")
    monkeypatch.setenv("TUCK_VAPID_PRIVATE_KEY", "server-private-key")
    monkeypatch.setenv("TUCK_VAPID_SUBJECT", "mailto:admin@example.com")
    get_settings.cache_clear()
    asyncio.run(create_accounts(isolated_database_url))

    async def get_public_key() -> Response:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            return await client.get("/api/v1/push-subscriptions/vapid-public-key")

    try:
        response = asyncio.run(get_public_key())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert response.status_code == 200
    assert response.json() == {"public_key": "server-public-key"}


def test_authenticated_user_can_register_push_subscription(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))

    async def register() -> Response:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            return await client.post("/api/v1/push-subscriptions", json=subscription_payload())

    try:
        response = asyncio.run(register())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "expirationTime"}
    assert "push.example.test" not in response.text
    assert subscription_payload()["keys"]["p256dh"] not in response.text
    assert subscription_payload()["keys"]["auth"] not in response.text
    assert body["expirationTime"] is None


def test_user_can_revoke_own_push_subscription(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))

    async def register_then_revoke() -> tuple[Response, Response]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            registered = await client.post(
                "/api/v1/push-subscriptions", json=subscription_payload()
            )
            revoked = await client.delete(f"/api/v1/push-subscriptions/{registered.json()['id']}")
            return registered, revoked

    try:
        registered, revoked = asyncio.run(register_then_revoke())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert registered.status_code == 201
    assert revoked.status_code == 204
    assert revoked.content == b""


def test_registration_retry_and_key_rotation_are_idempotent(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))

    rotated_p256dh = base64.urlsafe_b64encode(ROTATED_P256_PUBLIC_KEY).rstrip(b"=").decode()

    async def register_repeatedly() -> tuple[Response, Response, Response, list[PushSubscription]]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            payload = subscription_payload()
            first = await client.post("/api/v1/push-subscriptions", json=payload)
            duplicate = await client.post("/api/v1/push-subscriptions", json=payload)
            payload["keys"] = {**payload["keys"], "p256dh": rotated_p256dh}
            rotated = await client.post("/api/v1/push-subscriptions", json=payload)

        engine = create_engine(isolated_database_url)
        factory = create_session_factory(engine)
        try:
            async with session_scope(factory) as database:
                subscriptions = list(await database.scalars(select(PushSubscription)))
        finally:
            await engine.dispose()
        return first, duplicate, rotated, subscriptions

    try:
        first, duplicate, rotated, subscriptions = asyncio.run(register_repeatedly())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert [response.status_code for response in (first, duplicate, rotated)] == [201, 201, 201]
    assert first.json()["id"] == duplicate.json()["id"] == rotated.json()["id"]
    assert len(subscriptions) == 1
    assert subscriptions[0].p256dh == rotated_p256dh


def test_concurrent_registration_retries_are_idempotent(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))

    async def register_concurrently() -> list[Response]:
        async with (
            AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as first,
            AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as second,
        ):
            await asyncio.gather(login(first, "niki"), login(second, "niki"))
            return list(
                await asyncio.gather(
                    first.post("/api/v1/push-subscriptions", json=subscription_payload()),
                    second.post("/api/v1/push-subscriptions", json=subscription_payload()),
                )
            )

    try:
        responses = asyncio.run(register_concurrently())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert [response.status_code for response in responses] == [201, 201]
    assert responses[0].json()["id"] == responses[1].json()["id"]


def test_registration_rejects_expiration_time_outside_datetime_range(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))

    async def register() -> Response:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            payload = subscription_payload()
            payload["expirationTime"] = 253_402_300_800_000
            return await client.post("/api/v1/push-subscriptions", json=payload)

    try:
        response = asyncio.run(register())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert response.status_code == 422


def test_user_cannot_take_over_another_users_endpoint(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))
    takeover_auth = base64.urlsafe_b64encode(bytes(range(16, 32))).rstrip(b"=").decode()

    async def attempt_takeover() -> tuple[Response, Response]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            registered = await client.post(
                "/api/v1/push-subscriptions", json=subscription_payload()
            )
            await login(client, "ben")
            takeover_payload = subscription_payload()
            takeover_payload["keys"] = {
                **takeover_payload["keys"],
                "auth": takeover_auth,
            }
            takeover = await client.post("/api/v1/push-subscriptions", json=takeover_payload)
            return registered, takeover

    try:
        registered, takeover = asyncio.run(attempt_takeover())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert registered.status_code == 201
    assert takeover.status_code == 409
    assert subscription_payload()["endpoint"] not in takeover.text
    assert takeover_auth not in takeover.text


def test_user_cannot_revoke_another_users_subscription(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))

    async def attempt_revoke() -> tuple[Response, Response]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            registered = await client.post(
                "/api/v1/push-subscriptions", json=subscription_payload()
            )
            await login(client, "ben")
            revoked = await client.delete(f"/api/v1/push-subscriptions/{registered.json()['id']}")
            return registered, revoked

    try:
        registered, revoked = asyncio.run(attempt_revoke())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert registered.status_code == 201
    assert (revoked.status_code, revoked.json()) == (
        404,
        {"detail": "Push subscription not found"},
    )
    assert subscription_payload()["endpoint"] not in revoked.text


def test_registration_rejects_malformed_endpoint_port(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))

    async def register() -> Response:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            return await client.post(
                "/api/v1/push-subscriptions",
                json=subscription_payload("https://push.example.test:not-a-port/subscription"),
            )

    try:
        response = asyncio.run(register())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert response.status_code == 422


def test_registration_refreshes_expired_revoked_record(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))

    async def refresh_subscription() -> tuple[Response, Response, Response, PushSubscription]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            expired_payload = subscription_payload()
            expired_payload["expirationTime"] = 1
            registered = await client.post("/api/v1/push-subscriptions", json=expired_payload)
            revoked = await client.delete(f"/api/v1/push-subscriptions/{registered.json()['id']}")
            refreshed_payload = subscription_payload()
            refreshed_payload["expirationTime"] = 4_102_444_800_000
            refreshed = await client.post("/api/v1/push-subscriptions", json=refreshed_payload)

        engine = create_engine(isolated_database_url)
        factory = create_session_factory(engine)
        try:
            async with session_scope(factory) as database:
                subscription = (await database.scalars(select(PushSubscription))).one()
        finally:
            await engine.dispose()
        return registered, revoked, refreshed, subscription

    try:
        registered, revoked, refreshed, subscription = asyncio.run(refresh_subscription())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert registered.status_code == 201
    assert revoked.status_code == 204
    assert refreshed.status_code == 201
    assert refreshed.json()["id"] == registered.json()["id"]
    assert refreshed.json()["expirationTime"] == "2100-01-01T00:00:00Z"
    assert subscription.disabled_at is None
    assert subscription.expires_at is not None
    assert subscription.expires_at.year == 2100


def test_endpoint_rotation_keeps_new_endpoint_active_when_old_is_revoked(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))

    async def rotate_endpoint() -> tuple[Response, Response, Response, list[PushSubscription]]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            old = await client.post("/api/v1/push-subscriptions", json=subscription_payload())
            new = await client.post(
                "/api/v1/push-subscriptions",
                json=subscription_payload("https://push.example.test/subscriptions/browser-2"),
            )
            revoked = await client.delete(f"/api/v1/push-subscriptions/{old.json()['id']}")

        engine = create_engine(isolated_database_url)
        factory = create_session_factory(engine)
        try:
            async with session_scope(factory) as database:
                subscriptions = list(
                    await database.scalars(
                        select(PushSubscription).order_by(PushSubscription.endpoint)
                    )
                )
        finally:
            await engine.dispose()
        return old, new, revoked, subscriptions

    try:
        old, new, revoked, subscriptions = asyncio.run(rotate_endpoint())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert old.status_code == new.status_code == 201
    assert old.json()["id"] != new.json()["id"]
    assert revoked.status_code == 204
    assert subscriptions[0].disabled_at is not None
    assert subscriptions[1].disabled_at is None


def test_registration_rejects_endpoint_control_characters(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))

    async def register() -> Response:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            return await client.post(
                "/api/v1/push-subscriptions",
                json=subscription_payload("https://push.example.test/subscription\nsecret"),
            )

    try:
        response = asyncio.run(register())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert response.status_code == 422


def test_registration_rejects_off_curve_p256_key(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))

    async def register() -> Response:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            payload = subscription_payload()
            payload["keys"] = {
                **payload["keys"],
                "p256dh": base64.urlsafe_b64encode(b"\x04" + bytes(64)).rstrip(b"=").decode(),
            }
            return await client.post("/api/v1/push-subscriptions", json=payload)

    try:
        response = asyncio.run(register())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert response.status_code == 422


def test_registration_rejects_endpoint_whitespace(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))

    async def register() -> Response:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            return await client.post(
                "/api/v1/push-subscriptions",
                json=subscription_payload("https://push.example.test/subscription path"),
            )

    try:
        response = asyncio.run(register())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert response.status_code == 422


def test_registration_rejects_structurally_invalid_endpoints(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))
    endpoints = [
        "https://push.example.test/subscription\x00suffix",
        "https://push.example.test/subscription\x85suffix",
        "https://invalid_host.example/subscription",
        "https://push.example.test/subscription%GG",
        "https://push.example.test/subscription%00",
        "https://push.example.test:0/subscription",
        "https://push.example.test:/subscription",
        "https://１２７.０.０.１/subscription",
        "https://127.1/subscription",
        "https://2130706433/subscription",
        "https://0177.0.0.1/subscription",
        "https://0x7f000001/subscription",
    ]

    async def register_all() -> list[Response]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            return [
                await client.post("/api/v1/push-subscriptions", json=subscription_payload(endpoint))
                for endpoint in endpoints
            ]

    try:
        responses = asyncio.run(register_all())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert [response.status_code for response in responses] == [422] * len(endpoints)


def test_registration_rejects_private_network_endpoint(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))

    async def register() -> Response:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            return await client.post(
                "/api/v1/push-subscriptions",
                json=subscription_payload("https://169.254.169.254/latest/meta-data"),
            )

    try:
        response = asyncio.run(register())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert response.status_code == 422


def test_registration_rejects_malformed_payloads(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))

    valid_keys = subscription_payload()["keys"]
    assert isinstance(valid_keys, dict)
    invalid_payloads = [
        subscription_payload("http://push.example.test/subscription"),
        subscription_payload("https://" + "a" * 2049),
        {**subscription_payload(), "unexpected": "field"},
        {**subscription_payload(), "expirationTime": True},
        {
            **subscription_payload(),
            "keys": {"p256dh": "AA", "auth": "AAECAwQFBgcICQoLDA0ODw"},
        },
        {
            **subscription_payload(),
            "keys": {"p256dh": valid_keys["p256dh"], "auth": "AA"},
        },
    ]

    async def register_all() -> list[Response]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            return [
                await client.post("/api/v1/push-subscriptions", json=payload)
                for payload in invalid_payloads
            ]

    try:
        responses = asyncio.run(register_all())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert [response.status_code for response in responses] == [422] * len(invalid_payloads)


def test_validation_error_does_not_echo_auth_secret(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))
    auth_secret = "sensitive-auth-secret"

    async def register() -> Response:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            payload = subscription_payload()
            payload["keys"] = {**payload["keys"], "auth": auth_secret}
            return await client.post("/api/v1/push-subscriptions", json=payload)

    try:
        response = asyncio.run(register())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert response.status_code == 422
    assert auth_secret not in response.text


def test_nested_validation_error_does_not_echo_auth_secret(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_accounts(isolated_database_url))
    auth_secret = subscription_payload()["keys"]["auth"]

    async def register() -> Response:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            await login(client, "niki")
            payload = subscription_payload()
            payload["keys"] = {**payload["keys"], "unexpected": "field"}
            return await client.post("/api/v1/push-subscriptions", json=payload)

    try:
        response = asyncio.run(register())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert response.status_code == 422
    assert auth_secret not in response.text


def test_push_subscription_endpoints_require_authentication(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)

    async def request_without_login() -> tuple[Response, Response]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            registered = await client.post(
                "/api/v1/push-subscriptions", json=subscription_payload()
            )
            revoked = await client.delete(
                "/api/v1/push-subscriptions/00000000-0000-0000-0000-000000000000"
            )
            return registered, revoked

    try:
        registered, revoked = asyncio.run(request_without_login())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert registered.status_code == 401
    assert revoked.status_code == 401
