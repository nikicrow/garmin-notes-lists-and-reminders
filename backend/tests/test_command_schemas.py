from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from tuck_api.command_schemas import (
    AddListItems,
    CommandPlanV1,
    CreateNote,
    CreateReminder,
)


def test_command_plan_is_a_bounded_versioned_discriminated_union() -> None:
    plan = CommandPlanV1(
        schema_version="1",
        actions=[{"type": "create_note", "body": "Book the dentist"}],
    )

    assert plan.actions == [CreateNote(body="Book the dentist")]

    with pytest.raises(ValidationError):
        CommandPlanV1(
            schema_version="1",
            actions=[{"type": "create_note", "body": str(index)} for index in range(6)],
        )


def test_commands_reject_unbounded_or_incomplete_payloads() -> None:
    with pytest.raises(ValidationError):
        AddListItems(list_name_as_spoken="Shopping", items=[])

    with pytest.raises(ValidationError):
        CreateNote(body="x" * 10_001)

    reminder = CreateReminder(
        title="Call Mum",
        due_local=datetime(2027, 1, 2, 9, 30),
        timezone="Australia/Sydney",
        recipient_user_ids=[uuid4()],
    )
    assert reminder.type == "create_reminder"
