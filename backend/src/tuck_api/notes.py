from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tuck_api.auth import CurrentUser, Database
from tuck_api.models import Note, User

notes_router = APIRouter(prefix="/api/v1/notes", tags=["notes"])


class NoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1)


class NoteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1)


class NoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    body: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


async def create_note(database: AsyncSession, actor: User, body: str) -> Note:
    note = Note(owner_user_id=actor.id, body=body)
    database.add(note)
    await database.flush()
    await database.refresh(note)
    return note


async def list_notes(database: AsyncSession, actor: User) -> list[Note]:
    result = await database.scalars(
        select(Note)
        .where(Note.owner_user_id == actor.id, Note.archived_at.is_(None))
        .order_by(Note.created_at.desc(), Note.id.desc())
    )
    return list(result)


def note_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")


async def get_note(database: AsyncSession, actor: User, note_id: UUID) -> Note:
    note = await database.scalar(
        select(Note).where(Note.id == note_id, Note.owner_user_id == actor.id)
    )
    if note is None:
        raise note_not_found()
    return note


async def edit_note(database: AsyncSession, actor: User, note_id: UUID, body: str) -> Note:
    note = await get_note(database, actor, note_id)
    note.body = body
    note.updated_at = datetime.now(UTC)
    await database.flush()
    return note


async def archive_note(database: AsyncSession, actor: User, note_id: UUID) -> Note:
    note = await get_note(database, actor, note_id)
    now = datetime.now(UTC)
    note.archived_at = now
    note.updated_at = now
    await database.flush()
    return note


@notes_router.post("", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
async def create_note_route(payload: NoteCreate, database: Database, user: CurrentUser) -> Note:
    return await create_note(database, user, payload.body)


@notes_router.get("", response_model=list[NoteResponse])
async def list_notes_route(database: Database, user: CurrentUser) -> list[Note]:
    return await list_notes(database, user)


@notes_router.get("/{note_id}", response_model=NoteResponse)
async def get_note_route(note_id: UUID, database: Database, user: CurrentUser) -> Note:
    return await get_note(database, user, note_id)


@notes_router.patch("/{note_id}", response_model=NoteResponse)
async def edit_note_route(
    note_id: UUID, payload: NoteUpdate, database: Database, user: CurrentUser
) -> Note:
    return await edit_note(database, user, note_id, payload.body)


@notes_router.delete("/{note_id}", response_model=NoteResponse)
async def archive_note_route(note_id: UUID, database: Database, user: CurrentUser) -> Note:
    return await archive_note(database, user, note_id)
