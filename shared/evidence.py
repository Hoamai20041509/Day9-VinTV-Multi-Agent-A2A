"""Construct only evidence identifiers allowed by the assignment."""

from __future__ import annotations

from collections.abc import Iterable

from shared.constants import MAX_EVIDENCE_IDS


def build_evidence_ids(
    order_id: str,
    item_ids: Iterable[str],
    payment_ids: Iterable[str],
    seller_ids: Iterable[str],
    cause_code: str,
) -> list[str]:
    evidence = [f"order:{order_id}"]
    evidence.extend(f"item:{item_id}" for item_id in item_ids)
    evidence.extend(f"payment:{payment_id}" for payment_id in payment_ids)
    evidence.extend(f"seller:{seller_id}" for seller_id in seller_ids)
    policy_evidence = f"policy:{cause_code}"
    evidence = list(dict.fromkeys(evidence))
    # Preserve the policy row even for unusually large orders.
    return evidence[: MAX_EVIDENCE_IDS - 1] + [policy_evidence]
