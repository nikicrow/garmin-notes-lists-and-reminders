import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict
from uuid import uuid4

import pytest

from tuck_api.command_interpreter import AuthorisedContext, RuleBasedInterpreter


class EvaluationCase(TypedDict, total=False):
    name: str
    input: str
    expected_action: str
    expected_issue: str


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "command_evaluations.json"
CASES: list[EvaluationCase] = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=lambda case: str(case["name"]))
def test_representative_command_evaluations(case: EvaluationCase) -> None:
    actor_id = uuid4()
    context = AuthorisedContext(
        actor_id=actor_id,
        actor_name="niki",
        people={"niki": actor_id},
        lists={"shopping": uuid4()},
        reference_time=datetime(2026, 9, 20, 10, tzinfo=UTC),
        timezone="Australia/Sydney",
    )

    plan = RuleBasedInterpreter().interpret(case["input"], context)

    if expected_action := case.get("expected_action"):
        assert [action.type for action in plan.actions] == [expected_action]
        assert plan.ambiguities == []
    else:
        assert [issue.code for issue in plan.ambiguities] == [case["expected_issue"]]
