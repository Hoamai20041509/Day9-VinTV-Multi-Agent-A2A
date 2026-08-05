"""Final schema, limit, money and evidence verifier."""

from __future__ import annotations

import re
from typing import Any

from shared.constants import (
    CURRENCY,
    ISSUE_RULES,
    MAX_ACTIONS,
    MAX_ENTITY_IDS,
    MAX_EVIDENCE_IDS,
    MAX_RESPONSIBLE_PARTIES,
    MAX_ROOT_CAUSES,
    PAYMENT_TOLERANCE_BRL,
)


EVIDENCE_PATTERN = re.compile(
    r"^(?:order:[0-9a-z-]+|item:[0-9a-z-]+:[0-9]+|"
    r"payment:[0-9a-z-]+:[0-9]+|seller:[0-9a-z-]+|policy:[A-Z_]+)$"
)


class VerificationError(ValueError):
    pass


class VerifierAgent:
    def verify(self, result: dict[str, Any]) -> dict[str, Any]:
        required = {
            "case_id",
            "assessment",
            "affected_entities",
            "root_cause_analysis",
            "evidence_ids",
            "financial_resolution",
            "resolution_actions",
        }
        if set(result) != required:
            raise VerificationError(f"Invalid top-level keys: {set(result) ^ required}")

        assessment = result["assessment"]
        if assessment["primary_issue"] not in ISSUE_RULES:
            raise VerificationError("Unknown primary issue")
        if assessment["case_status"] not in {"action_required", "no_action"}:
            raise VerificationError("Invalid case status")
        if not 0 <= assessment["confidence"] <= 1:
            raise VerificationError("Confidence must be in [0, 1]")

        entities = result["affected_entities"]
        if set(entities) != {"order_ids", "item_ids", "seller_ids", "payment_ids"}:
            raise VerificationError("Invalid affected entity sets")
        if any(len(values) > MAX_ENTITY_IDS for values in entities.values()):
            raise VerificationError("Affected entity limit exceeded")

        causes = result["root_cause_analysis"]["ranked_causes"]
        parties = result["root_cause_analysis"]["responsible_parties"]
        if len(causes) > MAX_ROOT_CAUSES or len(parties) > MAX_RESPONSIBLE_PARTIES:
            raise VerificationError("Root cause or responsible party limit exceeded")
        if [cause["rank"] for cause in causes] != list(range(1, len(causes) + 1)):
            raise VerificationError("Cause ranks must be contiguous from 1")
        rule = ISSUE_RULES[assessment["primary_issue"]]
        if not causes or causes[0]["cause_code"] != rule["cause"]:
            raise VerificationError("Primary issue and root cause do not match")

        evidence = result["evidence_ids"]
        if len(evidence) > MAX_EVIDENCE_IDS or len(evidence) != len(set(evidence)):
            raise VerificationError("Evidence limit exceeded or evidence duplicated")
        if not all(EVIDENCE_PATTERN.fullmatch(value) for value in evidence):
            raise VerificationError("Malformed evidence ID")
        entity_evidence = {
            f"order:{value}" for value in entities["order_ids"]
        } | {f"item:{value}" for value in entities["item_ids"]} | {
            f"payment:{value}" for value in entities["payment_ids"]
        } | {f"seller:{value}" for value in entities["seller_ids"]}
        policy_evidence = {
            f'policy:{cause["cause_code"]}' for cause in causes
        }
        if not set(evidence) <= entity_evidence | policy_evidence:
            raise VerificationError("Evidence does not reference an affected entity")
        if not policy_evidence <= set(evidence):
            raise VerificationError("Ranked cause is missing policy evidence")

        financial = result["financial_resolution"]
        if financial["currency"] != CURRENCY:
            raise VerificationError("Currency must be BRL")
        money_fields = (
            "item_total_brl",
            "freight_total_brl",
            "payment_total_brl",
            "recommended_refund_brl",
        )
        if any(financial[field] < 0 for field in money_fields):
            raise VerificationError("Financial values must not be negative")
        if assessment["case_status"] == "action_required" and financial[
            "recommended_refund_brl"
        ] <= 0:
            raise VerificationError("Action-required case must have a positive refund")
        expected_status = (
            "action_required"
            if financial["recommended_refund_brl"] > 0
            else "no_action"
        )
        if assessment["case_status"] != expected_status:
            raise VerificationError("Case status and refund do not match")

        issue = assessment["primary_issue"]
        if issue in {"canceled_order_paid", "unavailable_order_paid"}:
            expected_refund = financial["payment_total_brl"]
        elif issue in {"late_delivery_seller", "late_delivery_logistics"}:
            expected_refund = financial["freight_total_brl"]
        else:
            expected_refund = 0.0
        if round(financial["recommended_refund_brl"], 2) != round(
            expected_refund, 2
        ):
            raise VerificationError("Refund does not match the selected policy")

        if issue in {"valid_split_payment", "unsupported_late_claim"}:
            merchandise_total = round(
                financial["item_total_brl"] + financial["freight_total_brl"], 2
            )
            if (
                abs(financial["payment_total_brl"] - merchandise_total)
                > PAYMENT_TOLERANCE_BRL
            ):
                raise VerificationError("Payment is not reconciled for no-action case")

        actions = result["resolution_actions"]
        if len(actions) > MAX_ACTIONS:
            raise VerificationError("Resolution action limit exceeded")
        if actions != [rule["action"]]:
            raise VerificationError("Primary issue and resolution action do not match")
        return result

    def run(self, result: dict[str, Any]) -> dict[str, Any]:
        return self.verify(result)
