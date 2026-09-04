from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from tuck_api.auth import CurrentUser, Database
from tuck_api.models import List, ResourceMembership, User

lists_router = APIRouter(prefix="/api/v1/lists", tags=["lists"])


class ListCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)


class ListUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)


class ListResponse(BaseModel):
    id: UUID
    owner_user_id: UUID
    title: str
    shared_user_ids: list[UUID]
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


async def create_list(database: AsyncSession, actor: User, title: str) -> List:
    resource = List(owner_user_id=actor.id, title=title)
    database.add(resource)
    await database.flush()
    await database.refresh(resource)
    return resource


async def list_lists(database: AsyncSession, actor: User) -> list[List]:
    result = await database.scalars(
        select(List)
        .outerjoin(ResourceMembership, ResourceMembership.list_id == List.id)
        .where(
            or_(List.owner_user_id == actor.id, ResourceMembership.user_id == actor.id),
            List.archived_at.is_(None),
        )
        .order_by(List.created_at.desc(), List.id.desc())
    )
    return list(result.unique())


def list_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List not found")


async def get_list(database: AsyncSession, actor: User, list_id: UUID) -> List:
    resource = await database.scalar(
        select(List)
        .outerjoin(ResourceMembership, ResourceMembership.list_id == List.id)
        .where(
            List.id == list_id,
            or_(List.owner_user_id == actor.id, ResourceMembership.user_id == actor.id),
        )
    )
    if resource is None:
        raise list_not_found()
    return resource


async def get_owned_list(database: AsyncSession, actor: User, list_id: UUID) -> List:
    resource = await database.scalar(
        select(List).where(List.id == list_id, List.owner_user_id == actor.id)
    )
    if resource is None:
        raise list_not_found()
    return resource


async def rename_list(database: AsyncSession, actor: User, list_id: UUID, title: str) -> List:
    resource = await get_owned_list(database, actor, list_id)
    resource.title = title
    resource.updated_at = datetime.now(UTC)
    await database.flush()
    return resource


async def archive_list(database: AsyncSession, actor: User, list_id: UUID) -> List:
    resource = await get_owned_list(database, actor, list_id)
    now = datetime.now(UTC)
    resource.archived_at = now
    resource.updated_at = now
    await database.flush()
    return resource


async def share_list(
    database: AsyncSession, actor: User, list_id: UUID, member_user_id: UUID
) -> List:
    resource = await get_owned_list(database, actor, list_id)
    member = await database.get(User, member_user_id)
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if member.id == actor.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="List owner cannot be added as a member",
        )
    await database.execute(
        insert(ResourceMembership)
        .values(list_id=list_id, user_id=member_user_id)
        .on_conflict_do_nothing(index_elements=["list_id", "user_id"])
    )
    resource.updated_at = datetime.now(UTC)
    await database.flush()
    return resource


async def unshare_list(
    database: AsyncSession, actor: User, list_id: UUID, member_user_id: UUID
) -> List:
    resource = await get_owned_list(database, actor, list_id)
    membership = await database.scalar(
        select(ResourceMembership).where(
            ResourceMembership.list_id == list_id,
            ResourceMembership.user_id == member_user_id,
        )
    )
    if membership is not None:
        await database.delete(membership)
        resource.updated_at = datetime.now(UTC)
        await database.flush()
    return resource


async def to_response(database: AsyncSession, resource: List) -> ListResponse:
    shared_user_ids = list(
        await database.scalars(
            select(ResourceMembership.user_id)
            .where(ResourceMembership.list_id == resource.id)
            .order_by(ResourceMembership.created_at, ResourceMembership.id)
        )
    )
    return ListResponse(
        id=resource.id,
        owner_user_id=resource.owner_user_id,
        title=resource.title,
        shared_user_ids=shared_user_ids,
        created_at=resource.created_at,
        updated_at=resource.updated_at,
        archived_at=resource.archived_at,
    )


@lists_router.post("", response_model=ListResponse, status_code=status.HTTP_201_CREATED)
async def create_list_route(
    payload: ListCreate, database: Database, user: CurrentUser
) -> ListResponse:
    return await to_response(database, await create_list(database, user, payload.title))


@lists_router.get("", response_model=list[ListResponse])
async def list_lists_route(database: Database, user: CurrentUser) -> list[ListResponse]:
    return [await to_response(database, resource) for resource in await list_lists(database, user)]


@lists_router.get("/{list_id}", response_model=ListResponse)
async def get_list_route(list_id: UUID, database: Database, user: CurrentUser) -> ListResponse:
    return await to_response(database, await get_list(database, user, list_id))


@lists_router.patch("/{list_id}", response_model=ListResponse)
async def rename_list_route(
    list_id: UUID, payload: ListUpdate, database: Database, user: CurrentUser
) -> ListResponse:
    return await to_response(database, await rename_list(database, user, list_id, payload.title))


@lists_router.delete("/{list_id}", response_model=ListResponse)
async def archive_list_route(list_id: UUID, database: Database, user: CurrentUser) -> ListResponse:
    return await to_response(database, await archive_list(database, user, list_id))


@lists_router.put("/{list_id}/members/{member_user_id}", response_model=ListResponse)
async def share_list_route(
    list_id: UUID, member_user_id: UUID, database: Database, user: CurrentUser
) -> ListResponse:
    return await to_response(database, await share_list(database, user, list_id, member_user_id))


@lists_router.delete("/{list_id}/members/{member_user_id}", response_model=ListResponse)
async def unshare_list_route(
    list_id: UUID, member_user_id: UUID, database: Database, user: CurrentUser
) -> ListResponse:
    return await to_response(database, await unshare_list(database, user, list_id, member_user_id))
