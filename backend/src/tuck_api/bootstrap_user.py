import asyncio
import getpass
import os
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from tuck_api.db import get_session_factory, session_scope
from tuck_api.models import User, UserSession
from tuck_api.security import hash_password


async def bootstrap_user(
    database: AsyncSession,
    username: str,
    password: str,
) -> bool:
    normalized_username = username.strip().casefold()
    if not normalized_username:
        raise ValueError("username must not be empty")
    if len(password) < 12:
        raise ValueError("password must contain at least 12 characters")

    user = await database.scalar(select(User).where(User.username == normalized_username))
    password_hash = hash_password(password)
    if user is None:
        database.add(User(username=normalized_username, password_hash=password_hash))
        return True
    user.password_hash = password_hash
    await database.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    return False


def _read_credentials() -> tuple[str, str]:
    username = os.getenv("TUCK_BOOTSTRAP_USERNAME") or input("Username: ")
    password = os.getenv("TUCK_BOOTSTRAP_PASSWORD") or getpass.getpass("Password: ")
    return username, password


async def _run() -> bool:
    username, password = _read_credentials()
    async with session_scope(get_session_factory()) as database:
        return await bootstrap_user(database, username, password)


def main() -> None:
    created = asyncio.run(_run())
    print("Account created." if created else "Account password updated.")


if __name__ == "__main__":
    main()
