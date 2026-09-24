"""Swappable interpretation boundary used by the command graph.

The initial provider is deliberately deterministic: it gives the PWA and evaluation
suite a safe vertical slice while the model/provider privacy decision remains open.
An LLM adapter can replace this class without changing command or persistence APIs.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

from tuck_api.command_schemas import (
    AddListItems,
    Ambiguity,
    CommandPlanV1,
    CreateList,
    CreateNote,
    CreateReminder,
)


@dataclass(frozen=True)
class AuthorisedContext:
    actor_id: UUID
    actor_name: str
    people: dict[str, UUID]
    lists: dict[str, UUID]
    reference_time: datetime
    timezone: str


class CommandInterpreter(Protocol):
    provider: str
    model: str
    prompt_version: str

    def interpret(self, raw_text: str, context: AuthorisedContext) -> CommandPlanV1: ...


class RuleBasedInterpreter:
    provider = "deterministic"
    model = "tuck-rules-v1"
    prompt_version = "rules-v1"

    _add_items = re.compile(
        r"^add\s+(?P<items>.+?)\s+to\s+(?:the\s+)?(?P<list>.+?)(?:\s+list)?[.!]?$",
        re.IGNORECASE,
    )
    _create_list = re.compile(
        r"^(?:create|make)\s+(?:a\s+)?list(?:\s+called|\s+named)?\s+(?P<title>.+?)[.!]?$",
        re.IGNORECASE,
    )
    _reminder = re.compile(
        r"^remind\s+(?:me|(?P<person>[\w-]+))\s+to\s+(?P<title>.+?)\s+"
        r"(?P<day>today|tomorrow)\s+at\s+(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?"
        r"\s*(?P<ampm>am|pm)?[.!]?$",
        re.IGNORECASE,
    )

    def interpret(self, raw_text: str, context: AuthorisedContext) -> CommandPlanV1:
        text = raw_text.strip()
        if note_match := re.match(r"^(?:note|remember)\s*:\s*(.+)$", text, re.IGNORECASE):
            return CommandPlanV1(actions=[CreateNote(body=note_match.group(1))])

        if match := self._add_items.match(text):
            spoken_name = match.group("list").strip().casefold()
            items = [
                item.strip()
                for item in re.split(r"\s*(?:,|\band\b)\s*", match.group("items"))
                if item.strip()
            ]
            list_id = context.lists.get(spoken_name)
            ambiguities = []
            if list_id is None:
                ambiguities.append(
                    Ambiguity(
                        code="list_not_found",
                        message=f'No accessible list exactly matches "{spoken_name}".',
                    )
                )
            return CommandPlanV1(
                actions=[
                    AddListItems(
                        list_id=list_id,
                        list_name_as_spoken=spoken_name,
                        items=items,
                    )
                ],
                ambiguities=ambiguities,
            )

        if match := self._create_list.match(text):
            return CommandPlanV1(actions=[CreateList(title=match.group("title"))])

        if match := self._reminder.match(text):
            person_name = (match.group("person") or context.actor_name).casefold()
            recipient_id = context.people.get(person_name)
            if recipient_id is None:
                return CommandPlanV1(
                    ambiguities=[
                        Ambiguity(
                            code="unknown_recipient",
                            message=f'No household member exactly matches "{person_name}".',
                        )
                    ]
                )
            hour = int(match.group("hour"))
            minute = int(match.group("minute") or 0)
            ampm = match.group("ampm")
            if ampm is not None:
                hour = hour % 12 + (12 if ampm.casefold() == "pm" else 0)
            local_reference = context.reference_time.astimezone(ZoneInfo(context.timezone))
            due_date = local_reference.date() + timedelta(
                days=1 if match.group("day").casefold() == "tomorrow" else 0
            )
            return CommandPlanV1(
                actions=[
                    CreateReminder(
                        title=match.group("title").strip(),
                        due_local=datetime.combine(due_date, datetime.min.time()).replace(
                            hour=hour, minute=minute
                        ),
                        timezone=context.timezone,
                        recipient_user_ids=[recipient_id],
                    )
                ]
            )

        return CommandPlanV1(
            ambiguities=[
                Ambiguity(
                    code="unsupported_or_ambiguous",
                    message="Tuck could not safely identify a supported creation command.",
                )
            ]
        )
