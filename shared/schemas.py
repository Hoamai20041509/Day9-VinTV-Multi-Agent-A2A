"""Validated contracts shared by every agent in the pipeline."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CASE_ID_PATTERN = r"^EC_\d{3}$"
ENTITY_ID_PATTERN = r"^[^:]+:\d+$"
EVIDENCE_ID_PATTERN = re.compile(
    r"^(?:order:[^:]+|item:[^:]+:\d+|payment:[^:]+:\d+|"
    r"seller:[^:]+|policy:[A-Z_]+)$"
)

Money = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class StrictModel(BaseModel):
    """Base contract that rejects misspelled or unexpected fields."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PrimaryIssue(str, Enum):
    CANCELED_ORDER_PAID = "canceled_order_paid"
    UNAVAILABLE_ORDER_PAID = "unavailable_order_paid"
    LATE_DELIVERY_SELLER = "late_delivery_seller"
    LATE_DELIVERY_LOGISTICS = "late_delivery_logistics"
    VALID_SPLIT_PAYMENT = "valid_split_payment"
    UNSUPPORTED_LATE_CLAIM = "unsupported_late_claim"


class CaseStatus(str, Enum):
    ACTION_REQUIRED = "action_required"
    NO_ACTION = "no_action"


class RootCauseCode(str, Enum):
    SELLER_HANDOFF_AFTER_LIMIT = "SELLER_HANDOFF_AFTER_LIMIT"
    CARRIER_DELIVERED_AFTER_ESTIMATE = "CARRIER_DELIVERED_AFTER_ESTIMATE"
    ORDER_CANCELED_AFTER_PAYMENT = "ORDER_CANCELED_AFTER_PAYMENT"
    ORDER_UNAVAILABLE_AFTER_PAYMENT = "ORDER_UNAVAILABLE_AFTER_PAYMENT"
    MULTIPLE_PAYMENTS_RECONCILED = "MULTIPLE_PAYMENTS_RECONCILED"
    DELIVERY_WITHIN_ESTIMATE = "DELIVERY_WITHIN_ESTIMATE"


class PartyType(str, Enum):
    PLATFORM = "platform"
    SELLER = "seller"
    LOGISTICS_PROVIDER = "logistics_provider"


class ResolutionAction(str, Enum):
    ISSUE_FULL_REFUND = "issue_full_refund"
    REFUND_FREIGHT = "refund_freight"
    EXPLAIN_VALID_SPLIT_PAYMENT = "explain_valid_split_payment"
    REJECT_LATE_REFUND = "reject_late_refund"


def _unique(values: list[Any], field_name: str) -> list[Any]:
    comparable = [str(value) for value in values]
    if len(comparable) != len(set(comparable)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return values


def _money(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("money values cannot be booleans")
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("invalid money value") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("money values must be finite and non-negative")
    return float(amount)


class CustomerRequest(StrictModel):
    language: str = Field(min_length=1)
    message: str = Field(min_length=1)
    claimed_order_id: str = Field(min_length=1)


class CaseInput(StrictModel):
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    opened_at: datetime
    customer_request: CustomerRequest
    policy_version: str = Field(pattern=r"^EC_POLICY_V1$")

    @property
    def order_id(self) -> str:
        return self.customer_request.claimed_order_id


class Assessment(StrictModel):
    primary_issue: PrimaryIssue
    case_status: CaseStatus
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)


class AffectedEntities(StrictModel):
    order_ids: list[str] = Field(default_factory=list, max_length=5)
    item_ids: list[str] = Field(default_factory=list, max_length=5)
    seller_ids: list[str] = Field(default_factory=list, max_length=5)
    payment_ids: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("item_ids", "payment_ids")
    @classmethod
    def validate_composite_ids(cls, values: list[str]) -> list[str]:
        if any(re.fullmatch(ENTITY_ID_PATTERN, value) is None for value in values):
            raise ValueError("item and payment IDs must use <order_id>:<sequence>")
        return values

    @field_validator("order_ids", "item_ids", "seller_ids", "payment_ids")
    @classmethod
    def validate_unique_ids(cls, values: list[str], info: Any) -> list[str]:
        if any(not value for value in values):
            raise ValueError(f"{info.field_name} must not contain empty IDs")
        return _unique(values, info.field_name)


class RankedCause(StrictModel):
    cause_code: RootCauseCode
    rank: int = Field(ge=1, le=3)


class ResponsibleParty(StrictModel):
    party_type: PartyType
    party_id: str = Field(min_length=1)


class RootCauseAnalysis(StrictModel):
    ranked_causes: list[RankedCause] = Field(default_factory=list, max_length=3)
    responsible_parties: list[ResponsibleParty] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def validate_unique_entries(self) -> "RootCauseAnalysis":
        _unique([cause.rank for cause in self.ranked_causes], "ranked_causes ranks")
        _unique(
            [(party.party_type, party.party_id) for party in self.responsible_parties],
            "responsible_parties",
        )
        return self


class FinancialResolution(StrictModel):
    currency: str = Field(pattern=r"^BRL$")
    item_total_brl: Money
    freight_total_brl: Money
    payment_total_brl: Money
    recommended_refund_brl: Money

    @field_validator(
        "item_total_brl",
        "freight_total_brl",
        "payment_total_brl",
        "recommended_refund_brl",
        mode="before",
    )
    @classmethod
    def round_money(cls, value: Any) -> float:
        return _money(value)


class CaseOutput(StrictModel):
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    assessment: Assessment
    affected_entities: AffectedEntities
    root_cause_analysis: RootCauseAnalysis
    evidence_ids: list[str] = Field(default_factory=list, max_length=10)
    financial_resolution: FinancialResolution
    resolution_actions: list[ResolutionAction] = Field(default_factory=list, max_length=5)

    @field_validator("evidence_ids")
    @classmethod
    def validate_evidence_ids(cls, values: list[str]) -> list[str]:
        if any(EVIDENCE_ID_PATTERN.fullmatch(value) is None for value in values):
            raise ValueError("invalid evidence ID format")
        return _unique(values, "evidence_ids")

    @field_validator("resolution_actions")
    @classmethod
    def validate_unique_actions(
        cls, values: list[ResolutionAction]
    ) -> list[ResolutionAction]:
        return _unique(values, "resolution_actions")

    @model_validator(mode="after")
    def validate_status_matches_refund(self) -> "CaseOutput":
        refund = self.financial_resolution.recommended_refund_brl
        expected = CaseStatus.ACTION_REQUIRED if refund > 0 else CaseStatus.NO_ACTION
        if self.assessment.case_status != expected:
            raise ValueError("case_status must agree with recommended_refund_brl")
        return self


class OrderItemResult(StrictModel):
    item_id: str = Field(pattern=ENTITY_ID_PATTERN)
    order_item_id: int = Field(ge=1)
    seller_id: str = Field(min_length=1)
    price_brl: Money
    freight_brl: Money
    shipping_limit_date: datetime | None = None

    @field_validator("price_brl", "freight_brl", mode="before")
    @classmethod
    def round_item_money(cls, value: Any) -> float:
        return _money(value)


class SellerHandoffViolation(StrictModel):
    item_id: str = Field(pattern=ENTITY_ID_PATTERN)
    seller_id: str = Field(min_length=1)
    shipping_limit_date: datetime
    order_delivered_carrier_date: datetime


class OrderSellerResult(StrictModel):
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    order_id: str = Field(min_length=1)
    order_exists: bool
    order_status: str | None = None
    order_delivered_carrier_date: datetime | None = None
    order_delivered_customer_date: datetime | None = None
    order_estimated_delivery_date: datetime | None = None
    items: list[OrderItemResult] = Field(default_factory=list)
    seller_ids: list[str] = Field(default_factory=list)
    late_handoffs: list[SellerHandoffViolation] = Field(default_factory=list)
    item_total_brl: Money = 0.0
    freight_total_brl: Money = 0.0
    evidence_ids: list[str] = Field(default_factory=list)

    @field_validator("item_total_brl", "freight_total_brl", mode="before")
    @classmethod
    def round_totals(cls, value: Any) -> float:
        return _money(value)


class PaymentRowResult(StrictModel):
    payment_id: str = Field(pattern=ENTITY_ID_PATTERN)
    payment_sequential: int = Field(ge=1)
    payment_type: str = Field(min_length=1)
    payment_installments: int = Field(ge=0)
    payment_value_brl: Money

    @field_validator("payment_value_brl", mode="before")
    @classmethod
    def round_payment_value(cls, value: Any) -> float:
        return _money(value)


class PaymentResult(StrictModel):
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    order_id: str = Field(min_length=1)
    payments: list[PaymentRowResult] = Field(default_factory=list)
    payment_total_brl: Money = 0.0
    payment_row_count: int = Field(ge=0)
    is_split_payment: bool
    is_reconciled: bool
    reconciliation_difference_brl: Money = 0.0
    evidence_ids: list[str] = Field(default_factory=list)

    @field_validator("payment_total_brl", "reconciliation_difference_brl", mode="before")
    @classmethod
    def round_payment_money(cls, value: Any) -> float:
        return _money(value)

    @model_validator(mode="after")
    def validate_payment_count(self) -> "PaymentResult":
        if self.payment_row_count != len(self.payments):
            raise ValueError("payment_row_count must equal the number of payment rows")
        if self.is_split_payment != (self.payment_row_count >= 2):
            raise ValueError("is_split_payment must agree with payment_row_count")
        return self


class DeliveryResult(StrictModel):
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    order_id: str = Field(min_length=1)
    delivered_customer_date: datetime | None = None
    estimated_delivery_date: datetime | None = None
    is_late: bool | None = None
    cause_candidate: RootCauseCode | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class PolicyResult(StrictModel):
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    draft_output: CaseOutput


class VerificationResult(StrictModel):
    case_id: str = Field(pattern=CASE_ID_PATTERN)
    is_valid: bool
    verified_output: CaseOutput | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_verification_state(self) -> "VerificationResult":
        if self.is_valid and self.verified_output is None:
            raise ValueError("valid verification requires verified_output")
        if not self.is_valid and not self.errors:
            raise ValueError("invalid verification requires at least one error")
        return self
