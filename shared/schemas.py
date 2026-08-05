"""Schema helpers for final case results."""

from __future__ import annotations

from typing import Any, TypedDict


class CaseInput(TypedDict):
    case_id: str
    opened_at: str
    customer_request: dict[str, str]
    policy_version: str


class CaseOutput(TypedDict):
    case_id: str
    assessment: dict[str, Any]
    affected_entities: dict[str, list[str]]
    root_cause_analysis: dict[str, list[dict[str, Any]]]
    evidence_ids: list[str]
    financial_resolution: dict[str, Any]
    resolution_actions: list[str]
