import asyncio
from datetime import UTC, datetime, timedelta

from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch
from sqlalchemy import select

from tuck_api.auth import hash_session_token
from tuck_api.bootstrap_user import bootstrap_user
from tuck_api.db import (
    create_engine,
    create_session_factory,
    get_session_factory,
    session_scope,
)
from tuck_api.main import app, get_settings
from tuck_api.models import Base, User, UserSession
from tuck_api.security import hash_password, verify_password


async def create_account(isolated_database_url: str, username: str = "niki") -> User:
    engine = create_engine(isolated_database_url)
    factory = create_session_factory(engine)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        user = User(username=username, password_hash=hash_password("valid password"))
        async with session_scope(factory) as database:
            database.add(user)
        return user
    finally:
        await engine.dispose()


def configure_app(monkeypatch: MonkeyPatch, isolated_database_url: str) -> None:
    monkeypatch.setenv("TUCK_DATABASE_URL", isolated_database_url)
    monkeypatch.setenv("TUCK_ENVIRONMENT", "test")
    get_settings.cache_clear()
    get_session_factory.cache_clear()


def test_passwords_are_stored_as_salted_hashes() -> None:
    first_hash = hash_password("correct horse battery staple")
    second_hash = hash_password("correct horse battery staple")

    assert first_hash != "correct horse battery staple"
    assert first_hash != second_hash
    assert verify_password("correct horse battery staple", first_hash)
    assert not verify_password("wrong password", first_hash)


def test_user_and_session_are_persisted(isolated_database_url: str) -> None:
    async def persist_account() -> tuple[str, datetime]:
        engine = create_engine(isolated_database_url)
        factory = create_session_factory(engine)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            user = User(username="niki", password_hash=hash_password("secret password"))
            async with session_scope(factory) as database:
                database.add(user)
                await database.flush()
                database.add(
                    UserSession(
                        user_id=user.id,
                        token_hash="hashed-token",
                        expires_at=datetime.now(UTC) + timedelta(hours=1),
                    )
                )

            async with factory() as database:
                stored = await database.scalar(select(User).where(User.username == "niki"))
                assert stored is not None
                session = await database.scalar(
                    select(UserSession).where(UserSession.user_id == stored.id)
                )
                assert session is not None
                return stored.username, session.expires_at
        finally:
            await engine.dispose()

    username, expires_at = asyncio.run(persist_account())

    assert username == "niki"
    assert expires_at.tzinfo is not None


def test_login_sets_secure_cookie_and_identifies_current_user(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setenv("TUCK_DATABASE_URL", isolated_database_url)
    monkeypatch.setenv("TUCK_ENVIRONMENT", "test")
    get_settings.cache_clear()
    get_session_factory.cache_clear()

    async def exercise_login() -> tuple[int, object, str, int, object]:
        engine = create_engine(isolated_database_url)
        factory = create_session_factory(engine)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            async with session_scope(factory) as database:
                database.add(User(username="niki", password_hash=hash_password("valid password")))

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="https://test") as client:
                login = await client.post(
                    "/api/v1/auth/login",
                    json={"username": "niki", "password": "valid password"},
                )
                current_user = await client.get("/api/v1/auth/me")
            return (
                login.status_code,
                login.json(),
                login.headers["set-cookie"],
                current_user.status_code,
                current_user.json(),
            )
        finally:
            await engine.dispose()

    try:
        login_status, login_body, cookie, me_status, me_body = asyncio.run(exercise_login())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert login_status == 200
    assert login_body == {"username": "niki"}
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=strict" in cookie
    assert me_status == 200
    assert me_body == {"username": "niki"}


def test_bootstrap_user_safely_creates_and_updates_an_account(
    isolated_database_url: str,
) -> None:
    async def bootstrap_account() -> tuple[bool, bool, str, datetime | None]:
        engine = create_engine(isolated_database_url)
        factory = create_session_factory(engine)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            async with session_scope(factory) as database:
                created = await bootstrap_user(database, "Ben", "first password")
            async with session_scope(factory) as database:
                user = await database.scalar(select(User).where(User.username == "ben"))
                assert user is not None
                database.add(
                    UserSession(
                        user_id=user.id,
                        token_hash=hash_session_token("existing session"),
                        expires_at=datetime.now(UTC) + timedelta(hours=1),
                    )
                )
            async with session_scope(factory) as database:
                created_again = await bootstrap_user(database, "Ben", "replacement password")
            async with factory() as database:
                user = await database.scalar(select(User).where(User.username == "ben"))
                assert user is not None
                existing_session = await database.scalar(
                    select(UserSession).where(UserSession.user_id == user.id)
                )
                assert existing_session is not None
                return created, created_again, user.password_hash, existing_session.revoked_at
        finally:
            await engine.dispose()

    created, created_again, stored_hash, revoked_at = asyncio.run(bootstrap_account())

    assert created
    assert not created_again
    assert verify_password("replacement password", stored_hash)
    assert not verify_password("first password", stored_hash)
    assert revoked_at is not None


def test_login_rejects_bad_credentials_without_revealing_the_username(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_account(isolated_database_url))

    async def attempt_logins() -> tuple[tuple[int, object], tuple[int, object]]:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="https://test") as client:
            wrong_password = await client.post(
                "/api/v1/auth/login",
                json={"username": "niki", "password": "wrong password"},
            )
            unknown_user = await client.post(
                "/api/v1/auth/login",
                json={"username": "unknown", "password": "wrong password"},
            )
        return (
            (wrong_password.status_code, wrong_password.json()),
            (unknown_user.status_code, unknown_user.json()),
        )

    try:
        wrong_password, unknown_user = asyncio.run(attempt_logins())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert wrong_password == (401, {"detail": "Invalid username or password"})
    assert unknown_user == wrong_password


def test_authentication_is_enforced_by_default(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_account(isolated_database_url))

    async def request_private_path() -> tuple[int, object]:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="https://test") as client:
            response = await client.get("/api/v1/private-placeholder")
        return response.status_code, response.json()

    try:
        result = asyncio.run(request_private_path())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert result == (401, {"detail": "Authentication required"})


def test_expired_and_revoked_sessions_are_rejected(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    user = asyncio.run(create_account(isolated_database_url))

    async def add_invalid_sessions() -> None:
        engine = create_engine(isolated_database_url)
        factory = create_session_factory(engine)
        try:
            async with session_scope(factory) as database:
                database.add_all(
                    [
                        UserSession(
                            user_id=user.id,
                            token_hash=hash_session_token("expired"),
                            expires_at=datetime.now(UTC) - timedelta(seconds=1),
                        ),
                        UserSession(
                            user_id=user.id,
                            token_hash=hash_session_token("revoked"),
                            expires_at=datetime.now(UTC) + timedelta(hours=1),
                            revoked_at=datetime.now(UTC),
                        ),
                    ]
                )
        finally:
            await engine.dispose()

    async def request_with_tokens() -> tuple[int, int]:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="https://test") as client:
            client.cookies.set("tuck_session", "expired")
            expired = await client.get("/api/v1/auth/me")
            client.cookies.set("tuck_session", "revoked")
            revoked = await client.get("/api/v1/auth/me")
        return expired.status_code, revoked.status_code

    asyncio.run(add_invalid_sessions())
    try:
        expired_status, revoked_status = asyncio.run(request_with_tokens())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert expired_status == 401
    assert revoked_status == 401


def test_logout_revokes_the_server_session(
    isolated_database_url: str, monkeypatch: MonkeyPatch
) -> None:
    configure_app(monkeypatch, isolated_database_url)
    asyncio.run(create_account(isolated_database_url))

    async def login_logout_and_replay() -> tuple[int, int]:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="https://test") as client:
            await client.post(
                "/api/v1/auth/login",
                json={"username": "niki", "password": "valid password"},
            )
            token = client.cookies["tuck_session"]
            logout = await client.post("/api/v1/auth/logout")
            client.cookies.set("tuck_session", token)
            replay = await client.get("/api/v1/auth/me")
        return logout.status_code, replay.status_code

    try:
        logout_status, replay_status = asyncio.run(login_logout_and_replay())
    finally:
        get_settings.cache_clear()
        get_session_factory.cache_clear()

    assert logout_status == 204
    assert replay_status == 401
