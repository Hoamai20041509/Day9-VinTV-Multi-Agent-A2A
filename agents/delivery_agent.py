"""Delivery-domain agent entry point."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from shared.a2a_messages import A2AMessage, AgentName, MessageType
from shared.schemas import DeliveryResult, RootCauseCode


def _timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


class DeliveryAgent:
    """Classify delivery timeliness from order timestamps and seller handoff."""

    name = AgentName.DELIVERY

    def __init__(self, data_dir: str | Path | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else None

    def analyze(
        self,
        *,
        case_id: str,
        order_id: str,
        order_delivered_customer_date: Any,
        order_estimated_delivery_date: Any,
        late_handoffs: list[dict[str, Any]] | None = None,
    ) -> DeliveryResult:
        delivered = _timestamp(order_delivered_customer_date)
        estimated = _timestamp(order_estimated_delivery_date)
        is_late = delivered > estimated if delivered is not None and estimated is not None else None
        cause = None
        if is_late is True:
            cause = (
                RootCauseCode.SELLER_HANDOFF_AFTER_LIMIT
                if late_handoffs
                else RootCauseCode.CARRIER_DELIVERED_AFTER_ESTIMATE
            )
        elif is_late is False:
            cause = RootCauseCode.DELIVERY_WITHIN_ESTIMATE

        return DeliveryResult(
            case_id=case_id,
            order_id=order_id,
            delivered_customer_date=delivered,
            estimated_delivery_date=estimated,
            is_late=is_late,
            cause_candidate=cause,
            evidence_ids=[f"order:{order_id}"] if cause is not None else [],
        )

    def handle(self, message: A2AMessage) -> A2AMessage:
        if message.message_type != MessageType.DELIVERY_REQUEST:
            return A2AMessage.failure_response(
                request=message,
                sender=self.name,
                message_type=MessageType.DELIVERY_RESULT,
                code="unexpected_message",
                message=f"unsupported message type: {message.message_type}",
            )
        try:
            result = self.analyze(
                case_id=message.payload["case_id"],
                order_id=message.payload["order_id"],
                order_delivered_customer_date=message.payload.get("order_delivered_customer_date"),
                order_estimated_delivery_date=message.payload.get("order_estimated_delivery_date"),
                late_handoffs=message.payload.get("late_handoffs") or [],
            )
        except Exception as exc:
            return A2AMessage.failure_response(
                request=message,
                sender=self.name,
                message_type=MessageType.DELIVERY_RESULT,
                code="delivery_error",
                message=str(exc),
            )
        return A2AMessage.success_response(
            request=message,
            sender=self.name,
            message_type=MessageType.DELIVERY_RESULT,
            payload=result,
        )
