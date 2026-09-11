import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TypedDict
from uuid import UUID

from pydantic import SecretStr
from pywebpush import WebPushException, webpush  # type: ignore[import-untyped]
from requests import RequestException


class NotificationData(TypedDict):
    reminderId: str
    url: str
    urgency: str


class NotificationPayload(TypedDict):
    title: str
    body: str
    data: NotificationData


class PushSubscriptionData(TypedDict):
    endpoint: str
    keys: dict[str, str]


class PushOutcome(StrEnum):
    SUCCESS = "success"
    EXPIRED = "expired"
    TRANSIENT = "transient"
    TERMINAL = "terminal"


@dataclass(frozen=True)
class PushResult:
    outcome: PushOutcome
    error_code: str | None = None

    @classmethod
    def success(cls) -> "PushResult":
        return cls(PushOutcome.SUCCESS)


@dataclass(repr=False)
class PyWebPushGateway:
    vapid_private_key: SecretStr
    vapid_subject: str
    sender: Callable[..., object] = webpush

    def send(self, subscription: PushSubscriptionData, payload: NotificationPayload) -> PushResult:
        try:
            self.sender(
                subscription_info=subscription,
                data=json.dumps(payload, separators=(",", ":")),
                vapid_private_key=self.vapid_private_key.get_secret_value(),
                vapid_claims={"sub": self.vapid_subject},
                headers={"Urgency": payload["data"]["urgency"]},
            )
        except WebPushException as error:
            outcome = classify_push_failure(status_code=error.status_code)
            error_code = f"http_{error.status_code}" if error.status_code else "network_error"
            return PushResult(outcome, error_code)
        except (RequestException, OSError):
            return PushResult(PushOutcome.TRANSIENT, "network_error")
        return PushResult.success()


def classify_push_failure(*, status_code: int | None) -> PushOutcome:
    if status_code in {404, 410}:
        return PushOutcome.EXPIRED
    if status_code is None or status_code == 429 or status_code >= 500:
        return PushOutcome.TRANSIENT
    return PushOutcome.TERMINAL


def build_notification_payload(*, reminder_id: UUID, urgent: bool) -> NotificationPayload:
    return {
        "title": "Tuck reminder",
        "body": "You have a reminder.",
        "data": {
            "reminderId": str(reminder_id),
            "url": "/reminders",
            "urgency": "high" if urgent else "normal",
        },
    }
