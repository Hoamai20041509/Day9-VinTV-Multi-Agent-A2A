"""Typed A2A envelopes and the common agent port used by the coordinator."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol, cast, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import to_jsonable_python


class AgentName(str, Enum):
    COORDINATOR = "coordinator"
    ORDER_SELLER = "order_seller"
    PAYMENT = "payment"
    DELIVERY = "delivery"
    POLICY = "policy"
    VERIFIER = "verifier"


class MessageType(str, Enum):
    ORDER_SELLER_REQUEST = "order_seller.request"
    ORDER_SELLER_RESULT = "order_seller.result"
    PAYMENT_REQUEST = "payment.request"
    PAYMENT_RESULT = "payment.result"
    DELIVERY_REQUEST = "delivery.request"
    DELIVERY_RESULT = "delivery.result"
    POLICY_REQUEST = "policy.request"
    POLICY_RESULT = "policy.result"
    VERIFIER_REQUEST = "verifier.request"
    VERIFIER_RESULT = "verifier.result"


class MessageStatus(str, Enum):
    REQUESTED = "requested"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AgentError(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    retryable: bool = False


class A2AMessage(BaseModel):
    """Serializable envelope for every request and response handoff."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message_id: str = Field(default_factory=lambda: uuid4().hex)
    correlation_id: str = Field(min_length=1)
    causation_id: str | None = None
    case_id: str = Field(pattern=r"^EC_\d{3}$")
    sender: AgentName
    recipient: AgentName
    message_type: MessageType
    status: MessageStatus
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = Field(default_factory=dict)
    error: AgentError | None = None

    @field_validator("created_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_status_and_error(self) -> "A2AMessage":
        if self.status == MessageStatus.FAILED and self.error is None:
            raise ValueError("failed messages require error details")
        if self.status != MessageStatus.FAILED and self.error is not None:
            raise ValueError("only failed messages may include error details")
        return self

    @classmethod
    def request(
        cls,
        *,
        correlation_id: str,
        case_id: str,
        recipient: AgentName,
        message_type: MessageType,
        payload: BaseModel | dict[str, Any],
        causation_id: str | None = None,
    ) -> "A2AMessage":
        return cls(
            correlation_id=correlation_id,
            causation_id=causation_id,
            case_id=case_id,
            sender=AgentName.COORDINATOR,
            recipient=recipient,
            message_type=message_type,
            status=MessageStatus.REQUESTED,
            payload=_payload_dict(payload),
        )

    @classmethod
    def success_response(
        cls,
        *,
        request: "A2AMessage",
        sender: AgentName,
        message_type: MessageType,
        payload: BaseModel | dict[str, Any],
    ) -> "A2AMessage":
        return cls(
            correlation_id=request.correlation_id,
            causation_id=request.message_id,
            case_id=request.case_id,
            sender=sender,
            recipient=AgentName.COORDINATOR,
            message_type=message_type,
            status=MessageStatus.SUCCEEDED,
            payload=_payload_dict(payload),
        )

    @classmethod
    def failure_response(
        cls,
        *,
        request: "A2AMessage",
        sender: AgentName,
        message_type: MessageType,
        code: str,
        message: str,
        retryable: bool = False,
    ) -> "A2AMessage":
        return cls(
            correlation_id=request.correlation_id,
            causation_id=request.message_id,
            case_id=request.case_id,
            sender=sender,
            recipient=AgentName.COORDINATOR,
            message_type=message_type,
            status=MessageStatus.FAILED,
            error=AgentError(code=code, message=message, retryable=retryable),
        )


def _payload_dict(payload: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, BaseModel):
        return payload.model_dump(mode="json")
    return cast(dict[str, Any], to_jsonable_python(payload))


@runtime_checkable
class AgentPort(Protocol):
    """The only invocation interface the coordinator needs from domain agents."""

    name: AgentName

    def handle(self, message: A2AMessage) -> A2AMessage:
        """Process one request and return one correlated response."""


@runtime_checkable
class OutputWriterPort(Protocol):
    def write(self, output: Any) -> Any:
        """Persist one verified case output."""
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentHandoff:
    case_id: str
    order_id: str
    source_agent: str
    payload: dict[str, Any]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "order_id": self.order_id,
            "source_agent": self.source_agent,
            "payload": self.payload,
            "warnings": self.warnings,
        }
