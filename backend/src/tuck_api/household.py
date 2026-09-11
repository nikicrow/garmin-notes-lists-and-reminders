from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from tuck_api.auth import CurrentUser, Database
from tuck_api.models import User

household_router = APIRouter(prefix="/api/v1/household", tags=["household"])


class HouseholdUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str


@household_router.get("/users", response_model=list[HouseholdUserResponse])
async def list_household_users(database: Database, user: CurrentUser) -> list[User]:
    del user
    result = await database.scalars(select(User).order_by(User.username, User.id))
    return list(result)
