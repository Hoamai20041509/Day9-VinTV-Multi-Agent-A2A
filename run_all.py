"""CLI entry point for validating or processing one/all dispute cases."""

from __future__ import annotations

import argparse
import json
import re
import sys
from importlib import import_module
from pathlib import Path
from typing import Any, Sequence

from pydantic import ValidationError

from agents.coordinator_agent import CoordinatorAgent
from shared.schemas import CaseInput
from shared.trace import TraceWriter


PROJECT_ROOT = Path(__file__).resolve().parent
OFFICIAL_CASE_NAMES = tuple(f"EC_{index:03d}.json" for index in range(1, 51))


class CompositionError(RuntimeError):
    """Raised when a teammate-owned runtime component is unavailable."""


def load_cases(input_dir: str | Path, case_id: str | None = None) -> list[CaseInput]:
    directory = Path(input_dir)
    if not directory.is_dir():
        raise FileNotFoundError(f"input directory does not exist: {directory}")

    if case_id is not None:
        if re.fullmatch(r"EC_\d{3}", case_id) is None:
            raise ValueError("--case must use the EC_001 format")
        paths = [directory / f"{case_id}.json"]
        if not paths[0].is_file():
            raise FileNotFoundError(f"case input does not exist: {paths[0]}")
    else:
        paths = sorted(directory.glob("EC_*.json"))
        actual_names = tuple(path.name for path in paths)
        if actual_names != OFFICIAL_CASE_NAMES:
            missing = sorted(set(OFFICIAL_CASE_NAMES) - set(actual_names))
            unexpected = sorted(set(actual_names) - set(OFFICIAL_CASE_NAMES))
            raise ValueError(
                "official run requires exactly EC_001.json through EC_050.json; "
                f"missing={missing}, unexpected={unexpected}"
            )

    cases: list[CaseInput] = []
    for path in paths:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            case = CaseInput.model_validate(raw)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(f"invalid case input {path}: {exc}") from exc
        if path.stem != case.case_id:
            raise ValueError(f"filename {path.name} does not match case_id {case.case_id}")
        cases.append(case)

    return cases


def _component(module_name: str, class_name: str) -> type[Any]:
    module = import_module(module_name)
    component = getattr(module, class_name, None)
    if component is None:
        raise CompositionError(
            f"{module_name}.{class_name} is not implemented; "
            "the owning team member must provide the agreed A2A contract"
        )
    return component


def build_default_coordinator(args: argparse.Namespace) -> CoordinatorAgent:
    """Compose teammate-owned agents using their agreed constructor contract."""

    order_seller_cls = _component("agents.order_seller_agent", "OrderSellerAgent")
    payment_cls = _component("agents.payment_agent", "PaymentAgent")
    delivery_cls = _component("agents.delivery_agent", "DeliveryAgent")
    policy_cls = _component("agents.policy_agent", "PolicyAgent")
    verifier_cls = _component("agents.verifier_agent", "VerifierAgent")
    output_writer_cls = _component("services.output_writer", "OutputWriter")

    return CoordinatorAgent(
        order_seller_agent=order_seller_cls(data_dir=args.data_dir),
        payment_agent=payment_cls(data_dir=args.data_dir),
        delivery_agent=delivery_cls(data_dir=args.data_dir),
        policy_agent=policy_cls(),
        verifier_agent=verifier_cls(data_dir=args.data_dir),
        trace_writer=TraceWriter(args.trace_file),
        output_writer=output_writer_cls(output_dir=args.output_dir),
        timeout_seconds=args.timeout,
        max_retries=args.retries,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Olist dispute pipeline")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--case", help="run one case, for example EC_001")
    selection.add_argument("--all", action="store_true", help="run all 50 official cases")
    parser.add_argument("--validate-only", action="store_true", help="validate inputs without calling agents")
    parser.add_argument("--input-dir", type=Path, default=PROJECT_ROOT / "input")
    parser.add_argument("--data-dir", type=Path, default=PROJECT_ROOT / "data")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "output")
    parser.add_argument("--trace-file", type=Path, default=PROJECT_ROOT / "trace.jsonl")
    parser.add_argument("--timeout", type=float, default=30.0, help="seconds allowed per agent call")
    parser.add_argument("--retries", type=int, default=1, help="retries after a failed agent call")
    parser.add_argument("--fail-fast", action="store_true", help="stop after the first failed case")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        cases = load_cases(args.input_dir, args.case)
        if args.validate_only:
            print(f"Validated {len(cases)} input case(s).")
            return 0

        coordinator = build_default_coordinator(args)
        try:
            result = coordinator.run(cases, continue_on_error=not args.fail_fast)
        finally:
            coordinator.close()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(
        f"Run {result.run_id}: {result.succeeded} succeeded, "
        f"{result.failed} failed. Trace: {args.trace_file}"
    )
    for case_id, error in sorted(result.errors.items()):
        print(f"  {case_id}: {error}", file=sys.stderr)
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
