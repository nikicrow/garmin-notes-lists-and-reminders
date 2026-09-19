import json
import secrets
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from pydantic import SecretStr
from pywebpush import WebPushException  # type: ignore[import-untyped]

from tuck_api.web_push import (
    PushOutcome,
    PushResult,
    PyWebPushGateway,
    build_notification_payload,
    classify_push_failure,
)


def test_notification_payload_is_minimal_and_safe() -> None:
    reminder_id = UUID("00000000-0000-0000-0000-000000000123")

    payload = build_notification_payload(reminder_id=reminder_id, urgent=True)

    assert payload == {
        "title": "Tuck reminder",
        "body": "You have a reminder.",
        "data": {
            "reminderId": str(reminder_id),
            "url": "/reminders",
            "urgency": "high",
        },
    }


@pytest.mark.parametrize("status_code", [404, 410])
def test_expired_provider_responses_are_permanent(status_code: int) -> None:
    assert classify_push_failure(status_code=status_code) == PushOutcome.EXPIRED


@pytest.mark.parametrize("status_code", [None, 429, 500, 503])
def test_rate_limit_server_and_network_failures_are_transient(
    status_code: int | None,
) -> None:
    assert classify_push_failure(status_code=status_code) == PushOutcome.TRANSIENT


def test_web_push_gateway_sends_json_with_vapid_and_urgency() -> None:
    call: dict[str, Any] = {}

    def sender(**kwargs: Any) -> object:
        call.update(kwargs)
        return object()

    private_key = SecretStr(secrets.token_urlsafe(32))
    gateway = PyWebPushGateway(
        vapid_private_key=private_key,
        vapid_subject="mailto:admin@example.com",
        sender=sender,
    )
    payload = build_notification_payload(
        reminder_id=UUID("00000000-0000-0000-0000-000000000123"), urgent=True
    )

    result = gateway.send(
        {
            "endpoint": "https://push.example.test/subscription",
            "keys": {"p256dh": "public-key", "auth": "auth-secret"},
        },
        payload,
    )

    assert result.outcome == PushOutcome.SUCCESS
    assert json.loads(call["data"]) == payload
    assert call["headers"] == {"Urgency": "high"}
    assert call["timeout"] == 10
    assert call["vapid_claims"] == {"sub": "mailto:admin@example.com"}
    assert private_key.get_secret_value() not in repr(gateway)


@pytest.mark.parametrize("status_code", [404, 410])
def test_gateway_classifies_expired_provider_responses(status_code: int) -> None:
    def sender(**kwargs: Any) -> object:
        del kwargs
        raise WebPushException(
            "provider rejected subscription",
            response=SimpleNamespace(status_code=status_code, text="expired"),
        )

    gateway = PyWebPushGateway(
        vapid_private_key=SecretStr(secrets.token_urlsafe(32)),
        vapid_subject="mailto:admin@example.com",
        sender=sender,
    )

    result = gateway.send(
        {"endpoint": "https://push.example.test", "keys": {}},
        build_notification_payload(
            reminder_id=UUID("00000000-0000-0000-0000-000000000123"), urgent=False
        ),
    )

    assert result == PushResult(PushOutcome.EXPIRED, f"http_{status_code}")


def test_gateway_classifies_network_failure_as_transient() -> None:
    def sender(**kwargs: Any) -> object:
        del kwargs
        raise OSError("connection unavailable")

    gateway = PyWebPushGateway(
        vapid_private_key=SecretStr(secrets.token_urlsafe(32)),
        vapid_subject="mailto:admin@example.com",
        sender=sender,
    )

    result = gateway.send(
        {"endpoint": "https://push.example.test", "keys": {}},
        build_notification_payload(
            reminder_id=UUID("00000000-0000-0000-0000-000000000123"), urgent=False
        ),
    )

    assert result == PushResult(PushOutcome.TRANSIENT, "network_error")
