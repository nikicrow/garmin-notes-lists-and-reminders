import hashlib
import secrets
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

from tuck_api.db import get_session_factory, session_scope
from tuck_api.models import User, UserSession
from tuck_api.security import hash_password, verify_password

SESSION_COOKIE_NAME = "tuck_session"
SESSION_TTL = timedelta(days=30)
PUBLIC_PATHS = {"/api/v1/health", "/api/v1/ready", "/api/v1/auth/login"}
_DUMMY_PASSWORD_HASH = hash_password("not-a-real-password")

auth_router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


class UserResponse(BaseModel):
    username: str


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
    )


async def get_database() -> AsyncIterator[AsyncSession]:
    async with session_scope(get_session_factory()) as database:
        yield database


async def require_authenticated_request(request: Request) -> None:
    if request.url.path in PUBLIC_PATHS:
        return

    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token is None:
        raise unauthorized()

    now = datetime.now(UTC)
    async with session_scope(get_session_factory()) as database:
        user = await database.scalar(
            select(User)
            .join(UserSession, UserSession.user_id == User.id)
            .where(
                UserSession.token_hash == hash_session_token(token),
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
            )
        )
    if user is None:
        raise unauthorized()
    request.state.current_user = user


class AuthenticationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            await require_authenticated_request(request)
        except HTTPException as error:
            return JSONResponse(status_code=error.status_code, content={"detail": error.detail})
        return await call_next(request)


def get_current_user(request: Request) -> User:
    return cast(User, request.state.current_user)


Database = Annotated[AsyncSession, Depends(get_database)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@auth_router.post("/login", response_model=UserResponse)
async def login(credentials: LoginRequest, response: Response, database: Database) -> User:
    username = credentials.username.strip().casefold()
    user = await database.scalar(select(User).where(User.username == username))
    password_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    if not verify_password(credentials.password, password_hash) or user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = secrets.token_urlsafe(32)
    database.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_session_token(token),
            expires_at=datetime.now(UTC) + SESSION_TTL,
        )
    )
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=int(SESSION_TTL.total_seconds()),
        secure=True,
        httponly=True,
        samesite="strict",
        path="/",
    )
    return user


@auth_router.get("/me", response_model=UserResponse)
async def current_user(user: CurrentUser) -> User:
    return user


@auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, database: Database) -> None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token is not None:
        session = await database.scalar(
            select(UserSession).where(UserSession.token_hash == hash_session_token(token))
        )
        if session is not None:
            session.revoked_at = datetime.now(UTC)
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        secure=True,
        httponly=True,
        samesite="strict",
    )
