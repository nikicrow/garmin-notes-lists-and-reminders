from __future__ import annotations

from datetime import UTC, datetime
from time import monotonic
from typing import Annotated, Any, Literal, TypedDict
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query, Response, status
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from tuck_api.auth import CurrentUser, Database
from tuck_api.command_interpreter import AuthorisedContext, CommandInterpreter, RuleBasedInterpreter
from tuck_api.command_schemas import (
    AddListItems,
    CommandPlanV1,
    CreateList,
    CreateNote,
    CreateReminder,
)
from tuck_api.db import get_session_factory, session_scope
from tuck_api.lists import (
    add_list_item,
    create_list,
    get_list,
    share_list,
)
from tuck_api.models import (
    AgentActionExecution,
    AgentExecution,
    Capture,
    List,
    ResourceMembership,
    User,
)
from tuck_api.notes import create_note
from tuck_api.reminders import ReminderCreate, create_reminder

captures_router = APIRouter(prefix="/api/v1/captures", tags=["captures"])

CaptureStatus = Literal[
    "received", "interpreting", "needs_review", "executing", "completed", "failed"
]


class TextCaptureCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_text: str = Field(min_length=1, max_length=10_000)
    source_request_id: str = Field(min_length=1, max_length=255)
    occurred_at: datetime
    client_timezone: str = Field(min_length=1, max_length=100)

    @field_validator("occurred_at")
    @classmethod
    def require_offset(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a UTC offset")
        return value

    @field_validator("client_timezone")
    @classmethod
    def require_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("client_timezone must be an IANA timezone") from error
        return value


class CaptureResponse(BaseModel):
    id: UUID
    source: str
    source_request_id: str
    raw_text: str
    occurred_at: datetime
    reference_timezone: str
    status: CaptureStatus
    receipt: str | None
    proposed_plan: dict[str, Any] | None
    validation_issues: list[dict[str, Any]]
    resulting_resources: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime


class WorkflowState(TypedDict, total=False):
    database: AsyncSession
    actor: User
    capture: Capture
    execution: AgentExecution
    context: AuthorisedContext
    supplied_plan: CommandPlanV1 | None
    plan: CommandPlanV1
    issues: list[dict[str, Any]]
    executable: bool
    results: list[dict[str, Any]]


class CommandWorkflow:
    graph_version = "1"

    def __init__(self, interpreter: CommandInterpreter | None = None) -> None:
        self.interpreter = interpreter or RuleBasedInterpreter()
        graph = StateGraph(WorkflowState)
        graph.add_node("load_context", self._load_context)
        graph.add_node("interpret", self._interpret)
        graph.add_node("policy", self._policy)
        graph.add_node("execute", self._execute)
        graph.add_node("review", self._review)
        graph.add_node("receipt", self._receipt)
        graph.add_edge(START, "load_context")
        graph.add_edge("load_context", "interpret")
        graph.add_edge("interpret", "policy")
        graph.add_conditional_edges(
            "policy",
            lambda state: "execute" if state["executable"] else "review",
            {"execute": "execute", "review": "review"},
        )
        graph.add_edge("execute", "receipt")
        graph.add_edge("review", "receipt")
        graph.add_edge("receipt", END)
        self.graph = graph.compile()

    async def run(
        self,
        database: AsyncSession,
        actor: User,
        capture: Capture,
        supplied_plan: CommandPlanV1 | None = None,
    ) -> Capture:
        started = monotonic()
        attempt = (
            await database.scalar(
                select(func.max(AgentExecution.attempt_number)).where(
                    AgentExecution.capture_id == capture.id
                )
            )
            or 0
        ) + 1
        execution = AgentExecution(
            capture_id=capture.id,
            attempt_number=attempt,
            graph_version=self.graph_version,
            command_schema_version="1",
            prompt_version=self.interpreter.prompt_version,
            model_provider=self.interpreter.provider,
            model_name=self.interpreter.model,
            status="interpreting",
            validation_issues_json=[],
            started_at=datetime.now(UTC),
        )
        database.add(execution)
        await database.flush()
        capture.active_execution_id = execution.id
        capture.status = "interpreting"
        await database.flush()

        await self.graph.ainvoke(
            {
                "database": database,
                "actor": actor,
                "capture": capture,
                "execution": execution,
                "supplied_plan": supplied_plan,
                "issues": [],
                "results": [],
            }
        )
        execution.completed_at = datetime.now(UTC)
        execution.latency_ms = round((monotonic() - started) * 1_000)
        await database.flush()
        return capture

    async def _load_context(self, state: WorkflowState) -> dict[str, Any]:
        database, actor, capture = state["database"], state["actor"], state["capture"]
        people = {
            user.username.casefold(): user.id
            for user in await database.scalars(select(User).order_by(User.username))
        }
        accessible_lists = await database.scalars(
            select(List)
            .outerjoin(ResourceMembership, ResourceMembership.list_id == List.id)
            .where(
                or_(List.owner_user_id == actor.id, ResourceMembership.user_id == actor.id),
                List.archived_at.is_(None),
            )
        )
        lists_by_name: dict[str, UUID] = {}
        duplicate_names: set[str] = set()
        for resource in accessible_lists.unique():
            name = resource.title.casefold()
            if name in lists_by_name:
                duplicate_names.add(name)
            else:
                lists_by_name[name] = resource.id
        for duplicate_name in duplicate_names:
            lists_by_name.pop(duplicate_name, None)
        return {
            "context": AuthorisedContext(
                actor_id=actor.id,
                actor_name=actor.username,
                people=people,
                lists=lists_by_name,
                reference_time=capture.occurred_at,
                timezone=capture.reference_timezone,
            )
        }

    async def _interpret(self, state: WorkflowState) -> dict[str, Any]:
        supplied_plan = state.get("supplied_plan")
        plan = supplied_plan or self.interpreter.interpret(
            state["capture"].raw_text, state["context"]
        )
        state["execution"].structured_plan_json = plan.model_dump(mode="json")
        await state["database"].flush()
        return {"plan": plan}

    async def _policy(self, state: WorkflowState) -> dict[str, Any]:
        database, actor, plan = state["database"], state["actor"], state["plan"]
        issues = [ambiguity.model_dump(mode="json") for ambiguity in plan.ambiguities]
        known_users = set(await database.scalars(select(User.id)))
        now = datetime.now(UTC)

        for index, action in enumerate(plan.actions):
            if isinstance(action, CreateNote) and action.share_with_user_ids:
                issues.append(
                    self._issue("unsupported_sharing", "Shared notes are not supported.", index)
                )
            elif isinstance(action, CreateList):
                if not set(action.share_with_user_ids) <= known_users:
                    issues.append(
                        self._issue("unknown_recipient", "A list recipient is unknown.", index)
                    )
            elif isinstance(action, AddListItems):
                if action.list_id is None:
                    issues.append(
                        self._issue("list_not_found", "The target list is ambiguous.", index)
                    )
                else:
                    try:
                        await get_list(database, actor, action.list_id)
                    except HTTPException:
                        issues.append(
                            self._issue(
                                "list_not_authorised", "The target list is unavailable.", index
                            )
                        )
            elif isinstance(action, CreateReminder):
                if action.due_local is None:
                    issues.append(self._issue("missing_due_time", "A due time is required.", index))
                else:
                    due = action.due_local
                    if due.tzinfo is None:
                        due = due.replace(tzinfo=ZoneInfo(action.timezone))
                    if due.astimezone(UTC) <= now:
                        issues.append(
                            self._issue("past_due_time", "The due time must be future.", index)
                        )
                if not set(action.recipient_user_ids) <= known_users:
                    issues.append(
                        self._issue("unknown_recipient", "A reminder recipient is unknown.", index)
                    )

        executable = bool(plan.actions) and not issues
        execution = state["execution"]
        execution.validation_issues_json = issues
        execution.policy_decision_json = {
            "decision": "execute" if executable else "needs_review",
            "schema_version": plan.schema_version,
        }
        await database.flush()
        return {"issues": issues, "executable": executable}

    async def _execute(self, state: WorkflowState) -> dict[str, Any]:
        database, actor = state["database"], state["actor"]
        capture, execution = state["capture"], state["execution"]
        capture.status = execution.status = "executing"
        await database.flush()
        results: list[dict[str, Any]] = []

        for index, action in enumerate(state["plan"].actions):
            idempotency_key = f"{capture.id}:1:{index}"
            prior = await database.scalar(
                select(AgentActionExecution).where(
                    AgentActionExecution.idempotency_key == idempotency_key
                )
            )
            if prior is not None and prior.result_summary_json is not None:
                results.append(prior.result_summary_json)
                continue
            action_execution = AgentActionExecution(
                agent_execution_id=execution.id,
                action_index=index,
                action_type=action.type,
                idempotency_key=idempotency_key,
                validated_command_json=action.model_dump(mode="json"),
                status="executing",
            )
            database.add(action_execution)
            await database.flush()
            result = await self._execute_action(database, actor, action)
            action_execution.status = "completed"
            action_execution.result_entity_type = result["type"]
            action_execution.result_entity_id = UUID(result["id"])
            action_execution.result_summary_json = result
            results.append(result)

        capture.resulting_resource_summary = results
        capture.status = execution.status = "completed"
        return {"results": results}

    async def _execute_action(
        self,
        database: AsyncSession,
        actor: User,
        action: CreateNote | CreateList | AddListItems | CreateReminder,
    ) -> dict[str, Any]:
        if isinstance(action, CreateNote):
            note = await create_note(database, actor, action.body)
            return {"type": "note", "id": str(note.id), "body": note.body}
        if isinstance(action, CreateList):
            created_list = await create_list(database, actor, action.title)
            for item in action.items:
                await add_list_item(database, actor, created_list.id, item)
            for user_id in action.share_with_user_ids:
                if user_id != actor.id:
                    await share_list(database, actor, created_list.id, user_id)
            return {
                "type": "list",
                "id": str(created_list.id),
                "title": created_list.title,
                "item_count": len(action.items),
            }
        if isinstance(action, AddListItems):
            if action.list_id is None:
                raise RuntimeError("policy allowed an unresolved list")
            target_list = await get_list(database, actor, action.list_id)
            for item in action.items:
                await add_list_item(database, actor, target_list.id, item)
            return {
                "type": "list",
                "id": str(target_list.id),
                "title": target_list.title,
                "items": action.items,
            }
        if action.due_local is None:
            raise RuntimeError("policy allowed a reminder without a due time")
        due = action.due_local
        if due.tzinfo is None:
            due = due.replace(tzinfo=ZoneInfo(action.timezone))
        reminder = await create_reminder(
            database,
            actor,
            ReminderCreate(
                title=action.title,
                detail=action.detail,
                due_at_utc=due.astimezone(UTC),
                source_timezone=action.timezone,
                is_urgent=action.is_urgent,
                recipient_user_ids=action.recipient_user_ids,
            ),
        )
        return {"type": "reminder", "id": str(reminder.id), "title": reminder.title}

    async def _review(self, state: WorkflowState) -> dict[str, Any]:
        capture, execution = state["capture"], state["execution"]
        capture.status = execution.status = "needs_review"
        return {}

    async def _receipt(self, state: WorkflowState) -> dict[str, Any]:
        capture = state["capture"]
        if capture.status == "needs_review":
            message = state["issues"][0]["message"] if state["issues"] else "Review required."
            capture.receipt = f"Needs review: {message}"
        else:
            summaries: list[str] = []
            for result in state["results"]:
                if result["type"] == "note":
                    summaries.append(f"Saved note: {result['body']}.")
                elif result["type"] == "list" and "items" in result:
                    summaries.append(f"Added {', '.join(result['items'])} to {result['title']}.")
                elif result["type"] == "list":
                    summaries.append(f"Created list: {result['title']}.")
                else:
                    summaries.append(f"Created reminder: {result['title']}.")
            capture.receipt = " ".join(summaries)
        await state["database"].flush()
        return {}

    @staticmethod
    def _issue(code: str, message: str, action_index: int) -> dict[str, Any]:
        return {"code": code, "message": message, "action_index": action_index}


workflow = CommandWorkflow()


async def _execution_for(database: AsyncSession, capture: Capture) -> AgentExecution | None:
    if capture.active_execution_id is None:
        return None
    return await database.get(AgentExecution, capture.active_execution_id)


async def to_response(database: AsyncSession, capture: Capture) -> CaptureResponse:
    # Workflow updates expire server-managed columns such as ``updated_at``.
    # Refresh explicitly so response serialization never triggers implicit async I/O.
    await database.refresh(capture)
    execution = await _execution_for(database, capture)
    return CaptureResponse(
        id=capture.id,
        source=capture.source,
        source_request_id=capture.source_request_id,
        raw_text=capture.raw_text,
        occurred_at=capture.occurred_at,
        reference_timezone=capture.reference_timezone,
        status=capture.status,
        receipt=capture.receipt,
        proposed_plan=execution.structured_plan_json if execution is not None else None,
        validation_issues=execution.validation_issues_json if execution is not None else [],
        resulting_resources=capture.resulting_resource_summary or [],
        created_at=capture.created_at,
        updated_at=capture.updated_at,
    )


async def owned_capture(database: AsyncSession, actor: User, capture_id: UUID) -> Capture:
    capture = await database.scalar(
        select(Capture).where(Capture.id == capture_id, Capture.user_id == actor.id)
    )
    if capture is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Capture not found")
    return capture


async def persist_text_capture(payload: TextCaptureCreate, user_id: UUID) -> tuple[UUID, bool]:
    """Commit raw intake independently before running interpretation."""
    async with session_scope(get_session_factory()) as intake_database:
        created_id = await intake_database.scalar(
            insert(Capture)
            .values(
                user_id=user_id,
                source="pwa_text",
                source_request_id=payload.source_request_id,
                raw_text=payload.raw_text.strip(),
                occurred_at=payload.occurred_at,
                reference_timezone=payload.client_timezone,
                status="received",
            )
            .on_conflict_do_nothing(index_elements=["source", "user_id", "source_request_id"])
            .returning(Capture.id)
        )
        if created_id is not None:
            return created_id, True

        existing_id = await intake_database.scalar(
            select(Capture.id).where(
                Capture.source == "pwa_text",
                Capture.user_id == user_id,
                Capture.source_request_id == payload.source_request_id,
            )
        )
        if existing_id is None:
            raise RuntimeError("capture idempotency conflict did not return an existing row")
        return existing_id, False


@captures_router.post("/text", response_model=CaptureResponse, status_code=status.HTTP_201_CREATED)
async def create_text_capture(
    payload: TextCaptureCreate,
    response: Response,
    database: Database,
    user: CurrentUser,
) -> CaptureResponse:
    capture_id, created = await persist_text_capture(payload, user.id)
    capture = await database.get(Capture, capture_id)
    if capture is None:
        raise RuntimeError("persisted capture could not be loaded")
    if not created:
        response.status_code = status.HTTP_200_OK
        return await to_response(database, capture)

    await workflow.run(database, user, capture)
    return await to_response(database, capture)


@captures_router.get("", response_model=list[CaptureResponse])
async def list_captures(
    database: Database,
    user: CurrentUser,
    capture_status: Annotated[CaptureStatus | None, Query(alias="status")] = None,
) -> list[CaptureResponse]:
    query = select(Capture).where(Capture.user_id == user.id)
    if capture_status is not None:
        query = query.where(Capture.status == capture_status)
    captures = await database.scalars(query.order_by(Capture.created_at.desc(), Capture.id.desc()))
    return [await to_response(database, capture) for capture in captures]


@captures_router.get("/{capture_id}", response_model=CaptureResponse)
async def get_capture(capture_id: UUID, database: Database, user: CurrentUser) -> CaptureResponse:
    return await to_response(database, await owned_capture(database, user, capture_id))


@captures_router.post("/{capture_id}/confirm", response_model=CaptureResponse)
async def confirm_capture(
    capture_id: UUID,
    plan: CommandPlanV1,
    database: Database,
    user: CurrentUser,
) -> CaptureResponse:
    capture = await owned_capture(database, user, capture_id)
    if capture.status != "needs_review":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Capture is not in review")
    await workflow.run(database, user, capture, supplied_plan=plan)
    return await to_response(database, capture)


@captures_router.post("/{capture_id}/retry", response_model=CaptureResponse)
async def retry_capture(capture_id: UUID, database: Database, user: CurrentUser) -> CaptureResponse:
    capture = await owned_capture(database, user, capture_id)
    if capture.status not in {"needs_review", "failed"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Capture cannot be retried"
        )
    await workflow.run(database, user, capture)
    return await to_response(database, capture)


@captures_router.post("/{capture_id}/reject", response_model=CaptureResponse)
async def reject_capture(
    capture_id: UUID, database: Database, user: CurrentUser
) -> CaptureResponse:
    capture = await owned_capture(database, user, capture_id)
    if capture.status != "needs_review":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Capture is not in review")
    capture.status = "failed"
    capture.safe_error_code = "rejected_by_user"
    capture.receipt = "Capture rejected."
    capture.updated_at = datetime.now(UTC)
    await database.flush()
    return await to_response(database, capture)
