"""Delivery Agent - specialist agent #3 of the dispute-resolution mesh.

Owner: member 4 (Delivery Agent). Files owned: this module and
``services/delivery_analysis.py``.

Scope
-----
The agent answers exactly one question of the investigation: **was the parcel
delivered late, and if so whose deadline was missed?** It compares
``order_delivered_customer_date`` against ``order_estimated_delivery_date``,
then combines that verdict with the Order & Seller handoff
(``seller_id`` + ``shipping_limit_date`` per item row) to distinguish:

* ``late_delivery_seller``      - late arrival *and* carrier pickup after ``shipping_limit_date``
* ``late_delivery_logistics``   - late arrival but the seller handed off in time
* ``unsupported_late_claim``    - delivered no later than the estimate

Root-cause candidates returned: ``SELLER_HANDOFF_AFTER_LIMIT``,
``CARRIER_DELIVERED_AFTER_ESTIMATE``, ``DELIVERY_WITHIN_ESTIMATE``.

Contracts
---------
The agent is runnable standalone (``python -m agents.delivery_agent --selftest``
or piping a JSON task on stdin), publishes an Agent Card via
:meth:`DeliveryAgent.agent_card`, accepts **structured input** and always returns
the agreed **structured output** envelope::

    {"agent_name": "delivery_agent", "status": "completed",
     "result": {...}, "summary": "...", "error": null}

Boundaries kept on purpose: no CSV/file access, no timezone conversion, no
refund maths and no payment logic. Money and final issue selection belong to the
Payment and Policy agents; this agent only supplies a verified delivery verdict.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from services.delivery_analysis import (
    CAUSE_CARRIER_DELIVERED_AFTER_ESTIMATE,
    CAUSE_DELIVERY_WITHIN_ESTIMATE,
    CAUSE_SELLER_HANDOFF_AFTER_LIMIT,
    DeliveryFinding,
    DeliveryTimeline,
    ISSUE_LATE_DELIVERY_LOGISTICS,
    ISSUE_LATE_DELIVERY_SELLER,
    ISSUE_UNSUPPORTED_LATE_CLAIM,
    analyze_delivery,
    as_mapping,
)

AGENT_NAME = "delivery_agent"
AGENT_VERSION = "1.0.0"
SKILL_ANALYZE_DELIVERY = "analyze_delivery_timeline"

STATUS_COMPLETED = "completed"
STATUS_PARTIAL = "partial"
STATUS_FAILED = "failed"

# Declared per lab rule 4 (<= 10B parameters). This agent is a deterministic
# rule evaluator over timestamps, so no model is invoked at inference time; the
# name is recorded so metadata.json and the source agree.
MODEL_NAME = "qwen2.5-7b-instruct"
MODEL_PARAMETER_SIZE = "7B"
REASONING_MODE = "deterministic-rules"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


# --------------------------------------------------------------------------- #
# A2A envelope
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class AgentResponse:
    """The team-wide structured output contract."""

    agent_name: str
    status: str
    result: dict[str, Any]
    summary: str
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in (STATUS_COMPLETED, STATUS_PARTIAL)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "status": self.status,
            "result": self.result,
            "summary": self.summary,
            "error": self.error,
        }

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(
            self.to_dict(), ensure_ascii=False, indent=indent, default=str
        )


class DeliveryAgentError(ValueError):
    """Raised for malformed task envelopes; converted into a failed response."""


# --------------------------------------------------------------------------- #
# Agent
# --------------------------------------------------------------------------- #


class DeliveryAgent:
    """Stateless delivery-timeline specialist.

    ``tracer`` is optional so the agent runs standalone. When the Coordinator
    passes a tracer exposing ``log``/``handoff`` (see ``shared.trace``), every
    task and handoff edge is recorded; when it is absent the agent stays silent.
    """

    name = AGENT_NAME
    version = AGENT_VERSION

    def __init__(self, tracer: Any | None = None) -> None:
        self._tracer = tracer

    # ----------------------------------------------------------- agent card
    @classmethod
    def agent_card(cls) -> dict[str, Any]:
        """Machine-readable capability descriptor for agent discovery."""
        return {
            "name": AGENT_NAME,
            "version": AGENT_VERSION,
            "description": (
                "Xac dinh don giao tre hay dung han bang cach so sanh "
                "order_delivered_customer_date voi order_estimated_delivery_date, "
                "va phan biet trach nhiem seller vs logistics_provider dua tren "
                "shipping_limit_date."
            ),
            "owner_role": "specialist_agent_3_delivery",
            "model": {
                "name": MODEL_NAME,
                "parameter_size": MODEL_PARAMETER_SIZE,
                "reasoning_mode": REASONING_MODE,
            },
            "data_access": {
                "reads_csv_directly": False,
                "receives_from": ["coordinator_agent", "order_seller_agent"],
                "hands_off_to": ["policy_agent", "verifier_agent"],
                "required_fields": [
                    "order.order_delivered_customer_date",
                    "order.order_estimated_delivery_date",
                ],
                "optional_fields": [
                    "order.order_delivered_carrier_date",
                    "order.order_status",
                    "items[].seller_id",
                    "items[].shipping_limit_date",
                    "items[].order_item_id",
                ],
            },
            "skills": [
                {
                    "id": SKILL_ANALYZE_DELIVERY,
                    "name": "Analyze delivery timeline",
                    "input_schema": {
                        "type": "object",
                        "required": ["order"],
                        "properties": {
                            "case_id": {"type": "string"},
                            "order": {"type": "object"},
                            "items": {"type": "array", "items": {"type": "object"}},
                        },
                    },
                    "output_schema": {
                        "type": "object",
                        "required": [
                            "agent_name",
                            "status",
                            "result",
                            "summary",
                            "error",
                        ],
                        "properties": {
                            "result": {
                                "type": "object",
                                "required": [
                                    "delivery_verdict",
                                    "late_vs_estimate",
                                    "seller_handoff_late",
                                    "cause_candidates",
                                    "issue_candidate",
                                ],
                            }
                        },
                    },
                }
            ],
            "emits_cause_codes": [
                CAUSE_SELLER_HANDOFF_AFTER_LIMIT,
                CAUSE_CARRIER_DELIVERED_AFTER_ESTIMATE,
                CAUSE_DELIVERY_WITHIN_ESTIMATE,
            ],
            "emits_issue_candidates": [
                ISSUE_LATE_DELIVERY_SELLER,
                ISSUE_LATE_DELIVERY_LOGISTICS,
                ISSUE_UNSUPPORTED_LATE_CLAIM,
            ],
            "guarantees": [
                "khong chuyen doi mui gio: timestamp so sanh dung gia tri trong CSV",
                "thieu timestamp khong bao gio duoc coi la giao dung han",
                "khong tu tao su kien tracking khong co trong du lieu",
                "luon tra ve envelope co status/result/summary/error",
            ],
            "status_values": [STATUS_COMPLETED, STATUS_PARTIAL, STATUS_FAILED],
        }

    # --------------------------------------------------------------- tracing
    def _trace(self, event: str, case_id: str | None, payload: dict[str, Any]) -> None:
        tracer = self._tracer
        if tracer is None:
            return
        log = getattr(tracer, "log", None)
        if callable(log):
            try:
                log(event, case_id=case_id, agent=AGENT_NAME, payload=payload)
            except TypeError:
                log(event)

    def _trace_handoff(self, case_id: str | None, payload: dict[str, Any]) -> None:
        tracer = self._tracer
        if tracer is None:
            return
        handoff = getattr(tracer, "handoff", None)
        if callable(handoff):
            try:
                handoff(AGENT_NAME, "policy_agent", case_id or "", payload)
            except TypeError:
                pass

    # ------------------------------------------------------------ execution
    def analyze(
        self,
        order: Mapping[str, Any] | DeliveryTimeline | Any | None,
        items: Sequence[Any] | None = None,
    ) -> DeliveryFinding:
        """Direct in-process entry point used by the Coordinator."""
        return analyze_delivery(order, items)

    def handle(self, task: Mapping[str, Any] | None) -> AgentResponse:
        """Execute one structured task and return the structured envelope.

        Accepted task shapes (all tolerated so upstream agents can hand off
        either their own payload or a raw CSV-shaped record)::

            {"case_id": "EC_001", "order": {...}, "items": [{...}]}
            {"case_id": "EC_001", "payload": {"order": {...}, "items": [...]}}
            {"case_id": "EC_001", "result": {"order": {...}, "items": [...]}}

        Never raises: a malformed or empty task produces a ``failed`` /
        ``partial`` envelope with ``error`` set, so the Coordinator can continue.
        """
        try:
            case_id, order, items = self._parse_task(task)
        except DeliveryAgentError as exc:
            response = AgentResponse(
                agent_name=AGENT_NAME,
                status=STATUS_FAILED,
                result={},
                summary="Khong xu ly duoc task: input khong dung contract.",
                error=str(exc),
            )
            self._trace(
                "agent_error",
                None,
                {"task": SKILL_ANALYZE_DELIVERY, "error": str(exc)},
            )
            return response

        started = datetime.now(timezone.utc)
        try:
            finding = analyze_delivery(order, items)
        except Exception as exc:  # defensive: keep the mesh alive
            error = f"{type(exc).__name__}: {exc}"
            self._trace(
                "agent_error",
                case_id,
                {"task": SKILL_ANALYZE_DELIVERY, "error": error},
            )
            return AgentResponse(
                agent_name=AGENT_NAME,
                status=STATUS_FAILED,
                result={},
                summary="Loi khi phan tich moc giao hang.",
                error=error,
            )

        duration_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000.0
        result = finding.to_dict()
        result.update(
            {
                "case_id": case_id,
                "agent_version": AGENT_VERSION,
                "evaluated_at": _now_iso(),
            }
        )

        if not finding.has_usable_timeline:
            status = STATUS_PARTIAL
            error = "; ".join(finding.warnings) or (
                "thieu timestamp giao hang: khong ket luan duoc late/on-time"
            )
        else:
            status = STATUS_COMPLETED
            error = None

        response = AgentResponse(
            agent_name=AGENT_NAME,
            status=status,
            result=result,
            summary=finding.summary(),
            error=error,
        )

        trace_payload = {
            "task": SKILL_ANALYZE_DELIVERY,
            "received_from": "order_seller_agent",
            "duration_ms": round(duration_ms, 3),
            "delivery_verdict": finding.delivery_verdict,
            "late_vs_estimate": finding.late_vs_estimate,
            "delay_days": finding.delay_days,
            "seller_handoff_late": finding.seller_handoff_late,
            "late_seller_ids": list(finding.late_seller_ids),
            "cause_candidates": list(finding.cause_candidates),
            "issue_candidate": finding.issue_candidate,
            "status": status,
            "warnings": list(finding.warnings),
        }
        self._trace("agent_task", case_id, trace_payload)
        self._trace_handoff(case_id, trace_payload)
        return response

    # ------------------------------------------------------------- parsing
    @staticmethod
    def _parse_task(
        task: Mapping[str, Any] | Any | None,
    ) -> tuple[str, Mapping[str, Any] | None, Sequence[Mapping[str, Any]]]:
        if task is None:
            raise DeliveryAgentError("task rong: can mot object JSON co khoa 'order'")
        original_type = type(task).__name__
        task = as_mapping(task)
        if task is None:
            raise DeliveryAgentError(f"task phai la object, nhan duoc {original_type}")

        body: Mapping[str, Any] = task
        for nested_key in ("payload", "result", "input"):
            nested = as_mapping(task.get(nested_key))
            if nested is not None and ("order" in nested or "items" in nested):
                body = nested
                break

        case_id = str(task.get("case_id") or body.get("case_id") or "").strip()

        order = as_mapping(body.get("order"))
        if order is None and body.get("order") is not None:
            raise DeliveryAgentError("khoa 'order' phai la object")
        if order is None:
            # Tolerate a flat record that already carries the timeline columns.
            flat = {
                key: value
                for key, value in body.items()
                if key.startswith("order_") or key in ("claimed_order_id", "status")
            }
            order = flat or None

        raw_items = body.get("items")
        if raw_items is None:
            raw_items = body.get("order_items")
        if raw_items is None:
            raw_items = []
        single = as_mapping(raw_items)
        if single is not None:
            raw_items = [single]
        if isinstance(raw_items, (str, bytes)):
            raise DeliveryAgentError("khoa 'items' phai la mang object")
        try:
            candidate_rows = list(raw_items)
        except TypeError as exc:
            raise DeliveryAgentError("khoa 'items' phai la mang object") from exc
        items = [row for row in (as_mapping(entry) for entry in candidate_rows) if row]

        return case_id, order, items


# --------------------------------------------------------------------------- #
# Standalone runner + acceptance tests
# --------------------------------------------------------------------------- #

# Fixtures cover: seller fault, logistics fault, on-time claim, missing data,
# a multi-seller order and the no-timezone-conversion rule. Timestamps mirror
# real rows from the Olist CSVs.
SELFTEST_CASES: list[dict[str, Any]] = [
    {
        "name": "late_seller_handoff_after_limit",
        "task": {
            "case_id": "T1_EC_009",
            "order": {
                "order_id": "3aaee056441dcae251f360b1c71a7279",
                "order_status": "delivered",
                "order_delivered_carrier_date": "2018-02-20 17:45:15",
                "order_delivered_customer_date": "2018-03-21 13:43:25",
                "order_estimated_delivery_date": "2018-03-09 00:00:00",
            },
            "items": [
                {
                    "order_id": "3aaee056441dcae251f360b1c71a7279",
                    "order_item_id": "1",
                    "seller_id": "SELLER_A",
                    "shipping_limit_date": "2018-02-19 23:15:35",
                }
            ],
        },
        "expect": {
            "status": STATUS_COMPLETED,
            "delivery_verdict": "late",
            "late_vs_estimate": True,
            "seller_handoff_late": True,
            "issue_candidate": ISSUE_LATE_DELIVERY_SELLER,
            "cause_candidates": [
                CAUSE_SELLER_HANDOFF_AFTER_LIMIT,
                CAUSE_CARRIER_DELIVERED_AFTER_ESTIMATE,
            ],
            "late_seller_ids": ["SELLER_A"],
        },
    },
    {
        "name": "late_but_seller_handed_off_in_time",
        "task": {
            "case_id": "T2_EC_012",
            "order": {
                "order_id": "103de323ece563a1012b4b6adf5a81b2",
                "order_status": "delivered",
                "order_delivered_carrier_date": "2018-08-23 14:43:00",
                "order_delivered_customer_date": "2018-09-03 19:06:55",
                "order_estimated_delivery_date": "2018-08-23 00:00:00",
            },
            "items": [
                {
                    "order_id": "103de323ece563a1012b4b6adf5a81b2",
                    "order_item_id": "1",
                    "seller_id": "SELLER_B",
                    "shipping_limit_date": "2018-08-24 03:30:00",
                }
            ],
        },
        "expect": {
            "status": STATUS_COMPLETED,
            "delivery_verdict": "late",
            "late_vs_estimate": True,
            "seller_handoff_late": False,
            "issue_candidate": ISSUE_LATE_DELIVERY_LOGISTICS,
            "cause_candidates": [CAUSE_CARRIER_DELIVERED_AFTER_ESTIMATE],
            "late_seller_ids": [],
        },
    },
    {
        "name": "on_time_delivery_rejects_late_claim",
        "task": {
            "case_id": "T3_EC_002",
            "order": {
                "order_id": "8067c5e4834f3c0a3c8a4e921d65c5b1",
                "order_status": "delivered",
                "order_delivered_carrier_date": "2018-01-29 17:58:40",
                "order_delivered_customer_date": "2018-01-31 21:34:47",
                "order_estimated_delivery_date": "2018-02-09 00:00:00",
            },
            "items": [
                {
                    "order_id": "8067c5e4834f3c0a3c8a4e921d65c5b1",
                    "order_item_id": "1",
                    "seller_id": "SELLER_C",
                    "shipping_limit_date": "2018-01-31 16:39:42",
                }
            ],
        },
        "expect": {
            "status": STATUS_COMPLETED,
            "delivery_verdict": "on_time",
            "late_vs_estimate": False,
            "seller_handoff_late": False,
            "issue_candidate": ISSUE_UNSUPPORTED_LATE_CLAIM,
            "cause_candidates": [CAUSE_DELIVERY_WITHIN_ESTIMATE],
            "late_seller_ids": [],
        },
    },
    {
        "name": "canceled_order_without_delivery_timestamp",
        "task": {
            "case_id": "T4_EC_003",
            "order": {
                "order_id": "71303d7e93b399f5bcd537d124c0bcfa",
                "order_status": "canceled",
                "order_delivered_carrier_date": "",
                "order_delivered_customer_date": "nan",
                "order_estimated_delivery_date": "2016-10-25 00:00:00",
            },
            "items": [
                {
                    "order_id": "71303d7e93b399f5bcd537d124c0bcfa",
                    "order_item_id": "1",
                    "seller_id": "SELLER_D",
                    "shipping_limit_date": "2016-10-21 16:19:54",
                }
            ],
        },
        "expect": {
            "status": STATUS_PARTIAL,
            "delivery_verdict": "not_delivered",
            "late_vs_estimate": False,
            "seller_handoff_late": False,
            "issue_candidate": None,
            "cause_candidates": [],
            "late_seller_ids": [],
        },
    },
    {
        "name": "multi_seller_only_offending_seller_blamed",
        "task": {
            "case_id": "T5_MULTI",
            "order": {
                "order_id": "MULTI_ORDER",
                "order_status": "delivered",
                "order_delivered_carrier_date": "2018-05-10 08:00:00",
                "order_delivered_customer_date": "2018-05-30 09:00:00",
                "order_estimated_delivery_date": "2018-05-25 00:00:00",
            },
            "items": [
                {
                    "order_id": "MULTI_ORDER",
                    "order_item_id": "1",
                    "seller_id": "SELLER_ON_TIME",
                    "shipping_limit_date": "2018-05-12 00:00:00",
                },
                {
                    "order_id": "MULTI_ORDER",
                    "order_item_id": "2",
                    "seller_id": "SELLER_LATE",
                    "shipping_limit_date": "2018-05-08 00:00:00",
                },
            ],
        },
        "expect": {
            "status": STATUS_COMPLETED,
            "delivery_verdict": "late",
            "late_vs_estimate": True,
            "seller_handoff_late": True,
            "issue_candidate": ISSUE_LATE_DELIVERY_SELLER,
            "cause_candidates": [
                CAUSE_SELLER_HANDOFF_AFTER_LIMIT,
                CAUSE_CARRIER_DELIVERED_AFTER_ESTIMATE,
            ],
            "late_seller_ids": ["SELLER_LATE"],
        },
    },
    {
        "name": "empty_task_returns_failed_envelope",
        "task": None,
        "expect": {"status": STATUS_FAILED, "error_present": True},
    },
    {
        "name": "missing_order_returns_partial_envelope",
        "task": {"case_id": "T7_EMPTY", "order": {}, "items": []},
        "expect": {
            "status": STATUS_PARTIAL,
            "delivery_verdict": "unknown",
            "late_vs_estimate": False,
            "issue_candidate": None,
            "cause_candidates": [],
            "error_present": True,
        },
    },
    {
        "name": "timezone_offset_is_not_converted",
        "task": {
            "case_id": "T8_TZ",
            "order": {
                "order_id": "TZ_ORDER",
                "order_status": "delivered",
                "order_delivered_carrier_date": "2018-10-10T00:00:00-03:00",
                "order_delivered_customer_date": "2018-10-18T00:00:00-03:00",
                "order_estimated_delivery_date": "2018-10-18T00:00:00-03:00",
            },
            "items": [],
        },
        # Same wall-clock value on both sides: no shift, therefore not late.
        "expect": {
            "status": STATUS_COMPLETED,
            "delivery_verdict": "on_time",
            "late_vs_estimate": False,
            "issue_candidate": ISSUE_UNSUPPORTED_LATE_CLAIM,
            "cause_candidates": [CAUSE_DELIVERY_WITHIN_ESTIMATE],
        },
    },
]


def run_selftest(verbose: bool = True) -> int:
    """Run the built-in acceptance cases; return the number of failures."""
    agent = DeliveryAgent()
    failures = 0
    for case in SELFTEST_CASES:
        response = agent.handle(case["task"])
        payload = response.to_dict()
        expect = case["expect"]
        problems: list[str] = []

        if payload["agent_name"] != AGENT_NAME:
            problems.append(f"agent_name={payload['agent_name']}")
        if payload["status"] != expect["status"]:
            problems.append(f"status={payload['status']} (expected {expect['status']})")
        if expect.get("error_present") and not payload["error"]:
            problems.append("error missing")
        if not payload["summary"]:
            problems.append("summary empty")

        result = payload["result"]
        for key in (
            "delivery_verdict",
            "late_vs_estimate",
            "seller_handoff_late",
            "issue_candidate",
            "cause_candidates",
            "late_seller_ids",
        ):
            if key not in expect:
                continue
            actual = result.get(key)
            if actual != expect[key]:
                problems.append(f"{key}={actual!r} (expected {expect[key]!r})")

        if problems:
            failures += 1
            if verbose:
                print(f"[FAIL] {case['name']}: " + "; ".join(problems))
        elif verbose:
            print(f"[PASS] {case['name']}: {payload['summary']}")

    if verbose:
        total = len(SELFTEST_CASES)
        print(f"\n{total - failures}/{total} delivery agent cases passed")
    return failures


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Delivery Agent (standalone runner)")
    parser.add_argument(
        "--selftest", action="store_true", help="run the built-in acceptance cases"
    )
    parser.add_argument(
        "--agent-card", action="store_true", help="print the Agent Card as JSON"
    )
    parser.add_argument("--task", help="path to a JSON task file ('-' reads stdin)")
    args = parser.parse_args(argv)

    if args.agent_card:
        print(json.dumps(DeliveryAgent.agent_card(), ensure_ascii=False, indent=2))
        return 0
    if args.selftest:
        return 1 if run_selftest() else 0

    agent = DeliveryAgent()
    if args.task:
        raw = (
            sys.stdin.read()
            if args.task == "-"
            else open(args.task, encoding="utf-8").read()
        )
    elif not sys.stdin.isatty():
        raw = sys.stdin.read()
    else:
        parser.print_help()
        return 2

    try:
        task = json.loads(raw) if raw.strip() else None
    except json.JSONDecodeError as exc:
        response = AgentResponse(
            agent_name=AGENT_NAME,
            status=STATUS_FAILED,
            result={},
            summary="Task khong phai JSON hop le.",
            error=f"JSONDecodeError: {exc}",
        )
        print(response.to_json())
        return 1

    response = agent.handle(task)
    print(response.to_json())
    return 0 if response.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())