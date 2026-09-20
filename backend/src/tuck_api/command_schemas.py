"""Versioned, provider-neutral command plans for natural-language capture."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator


def _nonblank(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("value must not be blank")
    return value


def _timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as error:
        raise ValueError("timezone must be an IANA timezone") from error
    return value


ShortText = Annotated[str, Field(min_length=1, max_length=2_000), AfterValidator(_nonblank)]
LongText = Annotated[str, Field(min_length=1, max_length=10_000), AfterValidator(_nonblank)]
Timezone = Annotated[str, Field(max_length=100), AfterValidator(_timezone)]


class CommandBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateNote(CommandBase):
    type: Literal["create_note"] = "create_note"
    body: LongText
    share_with_user_ids: list[UUID] = Field(default_factory=list, max_length=2)


class CreateList(CommandBase):
    type: Literal["create_list"] = "create_list"
    title: Annotated[str, Field(min_length=1, max_length=200), AfterValidator(_nonblank)]
    items: list[ShortText] = Field(default_factory=list, max_length=100)
    share_with_user_ids: list[UUID] = Field(default_factory=list, max_length=2)


class AddListItems(CommandBase):
    type: Literal["add_list_items"] = "add_list_items"
    list_id: UUID | None = None
    list_name_as_spoken: Annotated[
        str, Field(min_length=1, max_length=200), AfterValidator(_nonblank)
    ]
    items: list[ShortText] = Field(min_length=1, max_length=100)


class CreateReminder(CommandBase):
    type: Literal["create_reminder"] = "create_reminder"
    title: Annotated[str, Field(min_length=1, max_length=200), AfterValidator(_nonblank)]
    detail: Annotated[str, Field(max_length=2_000)] | None = None
    due_local: datetime | None = None
    timezone: Timezone
    recipient_user_ids: list[UUID] = Field(min_length=1, max_length=2)
    is_urgent: bool = False


CommandAction = Annotated[
    CreateNote | CreateList | AddListItems | CreateReminder,
    Field(discriminator="type"),
]


class Ambiguity(CommandBase):
    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=500)
    action_index: int | None = Field(default=None, ge=0, le=4)


class CommandPlanV1(CommandBase):
    schema_version: Literal["1"] = "1"
    actions: list[CommandAction] = Field(default_factory=list, max_length=5)
    ambiguities: list[Ambiguity] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def require_result(self) -> "CommandPlanV1":
        if not self.actions and not self.ambiguities:
            raise ValueError("a plan must contain an action or an ambiguity")
        return self
