
from shared.constants import (
    ACTION_EXPLAIN_VALID_SPLIT_PAYMENT,
    ISSUE_VALID_SPLIT_PAYMENT,
    MAX_EVIDENCE_IDS,
    ROOT_CAUSE_MULTIPLE_PAYMENTS_RECONCILED,
)
from shared.evidence import policy_evidence_id


def evaluate_rule_5_valid_split_payment(payment: dict) -> dict | None:
    """Rule 5 only. Call this after canceled/unavailable/late-delivery rules."""
    handoff = payment
    if not handoff.get("valid_split_payment"):
        return None

    evidence_ids = list(handoff.get("evidence_ids", []))
    evidence_ids.append(policy_evidence_id(ROOT_CAUSE_MULTIPLE_PAYMENTS_RECONCILED))

    return {
        "primary_issue": ISSUE_VALID_SPLIT_PAYMENT,
        "case_status": "no_action",
        "confidence": 0.9,
        "responsible_parties": [],
        "ranked_causes": [{"cause_code": ROOT_CAUSE_MULTIPLE_PAYMENTS_RECONCILED, "rank": 1}],
        "evidence_ids": evidence_ids[:MAX_EVIDENCE_IDS],
        "recommended_refund_brl": 0.0,
        "resolution_actions": [ACTION_EXPLAIN_VALID_SPLIT_PAYMENT],
    }
