"""Load and validate case input JSON files."""

from __future__ import annotations

import json
from pathlib import Path

from shared.constants import POLICY_VERSION
from shared.schemas import CaseInput


def load_case(path: str | Path) -> CaseInput:
    source = Path(path)
    with source.open(encoding="utf-8") as handle:
        case = json.load(handle)
    if case.get("case_id") != source.stem:
        raise ValueError(f"Case ID does not match filename: {source}")
    if case.get("policy_version") != POLICY_VERSION:
        raise ValueError(f"Unsupported policy version in {source}")
    if not case.get("customer_request", {}).get("claimed_order_id"):
        raise ValueError(f"Missing claimed_order_id in {source}")
    return case


def load_cases(directory: str | Path) -> list[CaseInput]:
    return [load_case(path) for path in sorted(Path(directory).glob("EC_*.json"))]
