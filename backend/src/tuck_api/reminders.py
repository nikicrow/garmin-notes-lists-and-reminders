from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, status
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from tuck_api.auth import CurrentUser, Database
from tuck_api.models import Reminder, ReminderRecipient, User

reminders_router = APIRouter(prefix="/api/v1/reminders", tags=["reminders"])


def valid_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as error:
        raise ValueError("source_timezone must be an IANA timezone") from error
    return value


Timezone = Annotated[str, AfterValidator(valid_timezone)]


def nonblank_title(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("title must not be blank")
    return value


Title = Annotated[str, Field(min_length=1, max_length=200), AfterValidator(nonblank_title)]


class DueTime(BaseModel):
    model_config = ConfigDict(extra="forbid")

    due_at_utc: datetime

    @model_validator(mode="after")
    def validate_due_time(self) -> "DueTime":
        if self.due_at_utc.tzinfo is None or self.due_at_utc.utcoffset() is None:
            raise ValueError("due_at_utc must include a UTC offset")
        self.due_at_utc = self.due_at_utc.astimezone(UTC)
        if self.due_at_utc <= datetime.now(UTC):
            raise ValueError("due_at_utc must be in the future")
        return self


class ReminderCreate(DueTime):
    title: Title
    detail: str | None = None
    source_timezone: Timezone
    is_urgent: bool = False
    recipient_user_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=2)

    @field_validator("recipient_user_ids")
    @classmethod
    def validate_unique_recipients(cls, value: list[UUID] | None) -> list[UUID] | None:
        if value is not None and len(set(value)) != len(value):
            raise ValueError("recipient_user_ids must be unique")
        return value


class ReminderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title | None = None
    detail: str | None = None
    is_urgent: bool | None = None

    @model_validator(mode="after")
    def validate_update(self) -> "ReminderUpdate":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("title must not be null")
        if "is_urgent" in self.model_fields_set and self.is_urgent is None:
            raise ValueError("is_urgent must not be null")
        return self


class ReminderReschedule(DueTime):
    source_timezone: Timezone


class ReminderSnooze(DueTime):
    pass


class ReminderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    detail: str | None
    due_at_utc: datetime
    source_timezone: str
    is_urgent: bool
    status: Literal["pending", "completed", "cancelled"]
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    cancelled_at: datetime | None
    recipient_user_ids: list[UUID]


async def create_reminder(database: AsyncSession, actor: User, payload: ReminderCreate) -> Reminder:
    recipient_user_ids = payload.recipient_user_ids or [actor.id]
    existing_recipient_ids = set(
        await database.scalars(select(User.id).where(User.id.in_(recipient_user_ids)))
    )
    if existing_recipient_ids != set(recipient_user_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Unknown reminder recipient",
        )

    reminder = Reminder(
        creator_user_id=actor.id,
        **payload.model_dump(exclude={"recipient_user_ids"}),
    )
    reminder.recipient_links = [
        ReminderRecipient(user_id=recipient_user_id) for recipient_user_id in recipient_user_ids
    ]
    database.add(reminder)
    await database.flush()
    await database.refresh(reminder)
    return reminder


async def list_reminders(database: AsyncSession, actor: User) -> list[Reminder]:
    result = await database.scalars(
        select(Reminder)
        .where(reminder_is_readable_by(actor))
        .order_by(Reminder.due_at_utc, Reminder.id)
    )
    return list(result)


def reminder_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found")


def reminder_is_readable_by(actor: User) -> ColumnElement[bool]:
    return or_(
        Reminder.creator_user_id == actor.id,
        exists(
            select(ReminderRecipient.id).where(
                ReminderRecipient.reminder_id == Reminder.id,
                ReminderRecipient.user_id == actor.id,
            )
        ),
    )


async def get_reminder(database: AsyncSession, actor: User, reminder_id: UUID) -> Reminder:
    reminder = await database.scalar(
        select(Reminder).where(
            Reminder.id == reminder_id,
            reminder_is_readable_by(actor),
        )
    )
    if reminder is None:
        raise reminder_not_found()
    return reminder


async def get_reminder_for_update(
    database: AsyncSession, actor: User, reminder_id: UUID
) -> Reminder:
    reminder = await database.scalar(
        select(Reminder)
        .where(
            Reminder.id == reminder_id,
            Reminder.creator_user_id == actor.id,
        )
        .with_for_update()
    )
    if reminder is None:
        raise reminder_not_found()
    return reminder


def require_pending(reminder: Reminder) -> None:
    if reminder.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reminder is no longer pending",
        )


async def edit_reminder(
    database: AsyncSession,
    actor: User,
    reminder_id: UUID,
    payload: ReminderUpdate,
) -> Reminder:
    reminder = await get_reminder_for_update(database, actor, reminder_id)
    require_pending(reminder)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(reminder, field, value)
    reminder.updated_at = datetime.now(UTC)
    await database.flush()
    return reminder


async def reschedule_reminder(
    database: AsyncSession,
    actor: User,
    reminder_id: UUID,
    due_at_utc: datetime,
    source_timezone: str | None = None,
) -> Reminder:
    reminder = await get_reminder_for_update(database, actor, reminder_id)
    require_pending(reminder)
    reminder.due_at_utc = due_at_utc
    if source_timezone is not None:
        reminder.source_timezone = source_timezone
    reminder.updated_at = datetime.now(UTC)
    await database.flush()
    return reminder


async def transition_reminder(
    database: AsyncSession,
    actor: User,
    reminder_id: UUID,
    new_status: Literal["completed", "cancelled"],
) -> Reminder:
    reminder = await get_reminder_for_update(database, actor, reminder_id)
    require_pending(reminder)
    now = datetime.now(UTC)
    reminder.status = new_status
    if new_status == "completed":
        reminder.completed_at = now
    else:
        reminder.cancelled_at = now
    reminder.updated_at = now
    await database.flush()
    return reminder


@reminders_router.post("", response_model=ReminderResponse, status_code=status.HTTP_201_CREATED)
async def create_reminder_route(
    payload: ReminderCreate, database: Database, user: CurrentUser
) -> Reminder:
    return await create_reminder(database, user, payload)


@reminders_router.get("", response_model=list[ReminderResponse])
async def list_reminders_route(database: Database, user: CurrentUser) -> list[Reminder]:
    return await list_reminders(database, user)


@reminders_router.get("/{reminder_id}", response_model=ReminderResponse)
async def get_reminder_route(reminder_id: UUID, database: Database, user: CurrentUser) -> Reminder:
    return await get_reminder(database, user, reminder_id)


@reminders_router.patch("/{reminder_id}", response_model=ReminderResponse)
async def edit_reminder_route(
    reminder_id: UUID, payload: ReminderUpdate, database: Database, user: CurrentUser
) -> Reminder:
    return await edit_reminder(database, user, reminder_id, payload)


@reminders_router.post("/{reminder_id}/complete", response_model=ReminderResponse)
async def complete_reminder_route(
    reminder_id: UUID, database: Database, user: CurrentUser
) -> Reminder:
    return await transition_reminder(database, user, reminder_id, "completed")


@reminders_router.post("/{reminder_id}/cancel", response_model=ReminderResponse)
async def cancel_reminder_route(
    reminder_id: UUID, database: Database, user: CurrentUser
) -> Reminder:
    return await transition_reminder(database, user, reminder_id, "cancelled")


@reminders_router.post("/{reminder_id}/snooze", response_model=ReminderResponse)
async def snooze_reminder_route(
    reminder_id: UUID, payload: ReminderSnooze, database: Database, user: CurrentUser
) -> Reminder:
    return await reschedule_reminder(database, user, reminder_id, payload.due_at_utc)


@reminders_router.post("/{reminder_id}/reschedule", response_model=ReminderResponse)
async def reschedule_reminder_route(
    reminder_id: UUID, payload: ReminderReschedule, database: Database, user: CurrentUser
) -> Reminder:
    return await reschedule_reminder(
        database,
        user,
        reminder_id,
        payload.due_at_utc,
        payload.source_timezone,
    )
