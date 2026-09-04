from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tuck_api.auth import CurrentUser, Database
from tuck_api.models import List, ListItem, ResourceMembership, User

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


class ListItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=2000)


class ListItemResponse(BaseModel):
    id: UUID
    list_id: UUID
    body: str
    position: int
    created_by_user_id: UUID
    completed_at: datetime | None
    completed_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime


class ListItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str | None = Field(default=None, min_length=1, max_length=2000)
    is_checked: bool | None = None


class ListItemPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: UUID
    position: int = Field(ge=0)


class ListItemsReorder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    positions: list[ListItemPosition]


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


async def add_list_item(database: AsyncSession, actor: User, list_id: UUID, body: str) -> ListItem:
    for _ in range(2):
        resource = await database.scalar(
            select(List)
            .where(
                List.id == list_id,
                or_(
                    List.owner_user_id == actor.id,
                    List.id.in_(
                        select(ResourceMembership.list_id).where(
                            ResourceMembership.user_id == actor.id
                        )
                    ),
                ),
            )
            .with_for_update()
        )
        if resource is None:
            raise list_not_found()
        last_position = await database.scalar(
            select(func.max(ListItem.position)).where(ListItem.list_id == list_id)
        )
        item = ListItem(
            list_id=list_id,
            body=body,
            position=0 if last_position is None else last_position + 1,
            created_by_user_id=actor.id,
        )
        database.add(item)
        try:
            await database.flush()
            await database.refresh(item)
            return item
        except IntegrityError:
            await database.rollback()
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Could not assign position after retry",
    )


async def list_list_items(database: AsyncSession, actor: User, list_id: UUID) -> list[ListItem]:
    await get_list(database, actor, list_id)
    return list(
        await database.scalars(
            select(ListItem)
            .where(ListItem.list_id == list_id)
            .order_by(ListItem.position, ListItem.id)
        )
    )


async def get_list_item(
    database: AsyncSession, actor: User, list_id: UUID, item_id: UUID
) -> ListItem:
    await get_list(database, actor, list_id)
    item = await database.scalar(
        select(ListItem).where(ListItem.id == item_id, ListItem.list_id == list_id)
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List item not found")
    return item


async def edit_list_item(
    database: AsyncSession,
    actor: User,
    list_id: UUID,
    item_id: UUID,
    body: str | None,
    is_checked: bool | None,
) -> ListItem:
    item = await get_list_item(database, actor, list_id, item_id)
    if body is not None:
        item.body = body
    if is_checked is not None:
        item.completed_at = datetime.now(UTC) if is_checked else None
        item.completed_by_user_id = actor.id if is_checked else None
    item.updated_at = datetime.now(UTC)
    await database.flush()
    return item


async def delete_list_item(
    database: AsyncSession, actor: User, list_id: UUID, item_id: UUID
) -> None:
    resource = await database.scalar(
        select(List)
        .where(
            List.id == list_id,
            or_(
                List.owner_user_id == actor.id,
                List.id.in_(
                    select(ResourceMembership.list_id).where(ResourceMembership.user_id == actor.id)
                ),
            ),
        )
        .with_for_update()
    )
    if resource is None:
        raise list_not_found()
    item = await database.scalar(
        select(ListItem).where(ListItem.id == item_id, ListItem.list_id == list_id)
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List item not found")
    removed_position = item.position
    await database.delete(item)
    await database.flush()
    await database.execute(
        update(ListItem)
        .where(ListItem.list_id == list_id, ListItem.position > removed_position)
        .values(position=ListItem.position - 1, updated_at=datetime.now(UTC))
    )


async def reorder_list_items(
    database: AsyncSession,
    actor: User,
    list_id: UUID,
    positions: list[ListItemPosition],
) -> list[ListItem]:
    await get_list(database, actor, list_id)
    await database.scalar(select(List.id).where(List.id == list_id).with_for_update())
    items = list(await database.scalars(select(ListItem).where(ListItem.list_id == list_id)))
    item_ids = {item.id for item in items}
    requested_ids = [entry.item_id for entry in positions]
    requested_positions = [entry.position for entry in positions]
    if (
        len(requested_ids) != len(item_ids)
        or set(requested_ids) != item_ids
        or len(set(requested_ids)) != len(requested_ids)
        or set(requested_positions) != set(range(len(items)))
        or len(set(requested_positions)) != len(requested_positions)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reorder must assign every item exactly once to contiguous positions",
        )
    positions_by_id = {entry.item_id: entry.position for entry in positions}
    now = datetime.now(UTC)
    for item in items:
        item.position = positions_by_id[item.id]
        item.updated_at = now
    await database.flush()
    return sorted(items, key=lambda item: (item.position, item.id))


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


@lists_router.post(
    "/{list_id}/items", response_model=ListItemResponse, status_code=status.HTTP_201_CREATED
)
async def add_list_item_route(
    list_id: UUID, payload: ListItemCreate, database: Database, user: CurrentUser
) -> ListItem:
    return await add_list_item(database, user, list_id, payload.body)


@lists_router.get("/{list_id}/items", response_model=list[ListItemResponse])
async def list_list_items_route(
    list_id: UUID, database: Database, user: CurrentUser
) -> list[ListItem]:
    return await list_list_items(database, user, list_id)


@lists_router.patch("/{list_id}/items/{item_id}", response_model=ListItemResponse)
async def edit_list_item_route(
    list_id: UUID,
    item_id: UUID,
    payload: ListItemUpdate,
    database: Database,
    user: CurrentUser,
) -> ListItem:
    return await edit_list_item(database, user, list_id, item_id, payload.body, payload.is_checked)


@lists_router.delete("/{list_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_list_item_route(
    list_id: UUID, item_id: UUID, database: Database, user: CurrentUser
) -> None:
    await delete_list_item(database, user, list_id, item_id)


@lists_router.put("/{list_id}/items/reorder", response_model=list[ListItemResponse])
async def reorder_list_items_route(
    list_id: UUID,
    payload: ListItemsReorder,
    database: Database,
    user: CurrentUser,
) -> list[ListItem]:
    return await reorder_list_items(database, user, list_id, payload.positions)
