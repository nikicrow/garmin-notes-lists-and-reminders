import base64
import binascii
import re
import socket
from datetime import UTC, datetime
from ipaddress import ip_address
from typing import Annotated
from unicodedata import category
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from tuck_api.auth import CurrentUser, Database
from tuck_api.models import PushSubscription, User
from tuck_api.settings import get_settings

push_subscriptions_router = APIRouter(
    prefix="/api/v1/push-subscriptions", tags=["push subscriptions"]
)

Base64UrlKey = Annotated[str, Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9_-]+$")]
P256_FIELD_PRIME = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
P256_B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B


def decode_base64url(value: str) -> bytes:
    try:
        return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("must be unpadded base64url") from error


class PushKeys(BaseModel):
    model_config = ConfigDict(extra="forbid")

    p256dh: Base64UrlKey
    auth: SecretStr

    @field_validator("p256dh")
    @classmethod
    def validate_p256dh(cls, value: str) -> str:
        decoded = decode_base64url(value)
        if len(decoded) != 65 or decoded[0] != 4:
            raise ValueError("must be a 65-byte uncompressed P-256 public key")
        x_coordinate = int.from_bytes(decoded[1:33], "big")
        y_coordinate = int.from_bytes(decoded[33:], "big")
        if (
            x_coordinate >= P256_FIELD_PRIME
            or y_coordinate >= P256_FIELD_PRIME
            or pow(y_coordinate, 2, P256_FIELD_PRIME)
            != (pow(x_coordinate, 3, P256_FIELD_PRIME) - 3 * x_coordinate + P256_B)
            % P256_FIELD_PRIME
        ):
            raise ValueError("must be a valid P-256 public key")
        return value

    @field_validator("auth")
    @classmethod
    def validate_auth(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if len(secret) > 255 or re.fullmatch(r"[A-Za-z0-9_-]+", secret) is None:
            raise ValueError("must be bounded unpadded base64url")
        if len(decode_base64url(secret)) != 16:
            raise ValueError("must be a 16-byte authentication secret")
        return value


class PushSubscriptionUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoint: str = Field(min_length=1, max_length=2048)
    expiration_time: int | None = Field(
        default=None,
        alias="expirationTime",
        ge=0,
        le=253_402_300_799_999,
        strict=True,
    )
    keys: PushKeys

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        if any(category(character) == "Cc" or character.isspace() for character in value):
            raise ValueError("must not contain whitespace or control characters")
        if re.search(r"%(?![0-9A-Fa-f]{2})", value) is not None:
            raise ValueError("must contain only valid percent escapes")
        if any(
            int(encoded_octet, 16) < 32 or 127 <= int(encoded_octet, 16) <= 159
            for encoded_octet in re.findall(r"%([0-9A-Fa-f]{2})", value)
        ):
            raise ValueError("must not contain encoded control characters")
        parsed = urlsplit(value)
        try:
            endpoint_port = parsed.port
        except ValueError as error:
            raise ValueError("must have a valid port") from error
        if (
            parsed.scheme != "https"
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise ValueError("must be an HTTPS URL without credentials or a fragment")
        if endpoint_port == 0 or parsed.netloc.endswith(":"):
            raise ValueError("must have a valid port")
        try:
            endpoint_ip = ip_address(parsed.hostname)
        except ValueError:
            endpoint_ip = None
        if endpoint_ip is not None and not endpoint_ip.is_global:
            raise ValueError("must not target a private or reserved network address")
        if endpoint_ip is None:
            try:
                ascii_hostname = parsed.hostname.encode("idna").decode("ascii")
            except UnicodeError as error:
                raise ValueError("must have a valid hostname") from error
            try:
                socket.inet_aton(ascii_hostname)
            except OSError:
                pass
            else:
                raise ValueError("must not use a legacy numeric network address")
            labels = ascii_hostname.split(".")
            if (
                len(ascii_hostname) > 253
                or any(
                    not label
                    or len(label) > 63
                    or re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label) is None
                    for label in labels
                )
                or ascii_hostname.lower() == "localhost"
                or ascii_hostname.lower().endswith(".localhost")
            ):
                raise ValueError("must have a valid public hostname")
        return value


class PushSubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    expiration_time: datetime | None = Field(
        validation_alias="expires_at", serialization_alias="expirationTime"
    )


class VapidPublicKeyResponse(BaseModel):
    public_key: str


def expiration_datetime(expiration_time: int | None) -> datetime | None:
    if expiration_time is None:
        return None
    return datetime.fromtimestamp(expiration_time / 1000, tz=UTC)


async def register_push_subscription(
    database: AsyncSession, actor: User, payload: PushSubscriptionUpsert
) -> PushSubscription:
    values = {
        "user_id": actor.id,
        "endpoint": payload.endpoint,
        "p256dh": payload.keys.p256dh,
        "auth": payload.keys.auth.get_secret_value(),
        "expires_at": expiration_datetime(payload.expiration_time),
        "disabled_at": None,
    }
    statement = (
        insert(PushSubscription)
        .values(**values)
        .on_conflict_do_update(
            index_elements=[PushSubscription.endpoint],
            set_={
                "p256dh": payload.keys.p256dh,
                "auth": payload.keys.auth.get_secret_value(),
                "expires_at": expiration_datetime(payload.expiration_time),
                "disabled_at": None,
            },
            where=PushSubscription.user_id == actor.id,
        )
        .returning(PushSubscription)
    )
    subscription = await database.scalar(statement)
    if subscription is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Push subscription endpoint is already registered",
        )
    return subscription


async def revoke_push_subscription(
    database: AsyncSession, actor: User, subscription_id: UUID
) -> None:
    subscription = await database.scalar(
        select(PushSubscription).where(
            PushSubscription.id == subscription_id,
            PushSubscription.user_id == actor.id,
            PushSubscription.disabled_at.is_(None),
        )
    )
    if subscription is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Push subscription not found",
        )
    subscription.disabled_at = datetime.now(UTC)
    await database.flush()


@push_subscriptions_router.post(
    "", response_model=PushSubscriptionResponse, status_code=status.HTTP_201_CREATED
)
async def register_push_subscription_route(
    payload: PushSubscriptionUpsert, database: Database, user: CurrentUser
) -> PushSubscription:
    return await register_push_subscription(database, user, payload)


@push_subscriptions_router.get("/vapid-public-key", response_model=VapidPublicKeyResponse)
async def get_vapid_public_key(_user: CurrentUser) -> VapidPublicKeyResponse:
    public_key = get_settings().vapid_public_key
    if not public_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Push notifications are not configured",
        )
    return VapidPublicKeyResponse(public_key=public_key)


@push_subscriptions_router.delete("/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_push_subscription_route(
    subscription_id: UUID, database: Database, user: CurrentUser
) -> None:
    await revoke_push_subscription(database, user, subscription_id)
