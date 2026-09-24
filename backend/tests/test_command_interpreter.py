from datetime import UTC, datetime
from uuid import uuid4

from tuck_api.command_interpreter import AuthorisedContext, RuleBasedInterpreter
from tuck_api.command_schemas import AddListItems, CreateNote, CreateReminder


def test_interprets_representative_creation_commands() -> None:
    niki_id = uuid4()
    interpreter = RuleBasedInterpreter()
    context = AuthorisedContext(
        actor_id=niki_id,
        actor_name="niki",
        people={"niki": niki_id},
        lists={"shopping": uuid4()},
        reference_time=datetime(2026, 9, 20, 10, tzinfo=UTC),
        timezone="Australia/Sydney",
    )

    note = interpreter.interpret("Note: book a dentist appointment", context)
    items = interpreter.interpret("Add milk and bananas to the shopping list", context)
    reminder = interpreter.interpret("Remind me to call Mum tomorrow at 9am", context)

    assert note.actions == [CreateNote(body="book a dentist appointment")]
    assert items.actions == [
        AddListItems(
            list_id=context.lists["shopping"],
            list_name_as_spoken="shopping",
            items=["milk", "bananas"],
        )
    ]
    assert reminder.actions == [
        CreateReminder(
            title="call Mum",
            due_local=datetime(2026, 9, 21, 9),
            timezone="Australia/Sydney",
            recipient_user_ids=[niki_id],
        )
    ]


def test_routes_ambiguous_text_to_review() -> None:
    interpreter = RuleBasedInterpreter()
    context = AuthorisedContext(
        actor_id=uuid4(),
        actor_name="niki",
        people={},
        lists={},
        reference_time=datetime(2026, 9, 20, 10, tzinfo=UTC),
        timezone="Australia/Sydney",
    )

    plan = interpreter.interpret("Maybe deal with that thing later", context)

    assert plan.actions == []
    assert plan.ambiguities[0].code == "unsupported_or_ambiguous"
