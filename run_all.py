"""Command-line entry point for running one case or all cases.

Usage:
    python run_all.py                 # all 50 cases, LLM intent on, fresh trace
    python run_all.py --case EC_004   # single case
    python run_all.py --no-llm        # deterministic pipeline only (CI/tests)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from agents.coordinator_agent import CoordinatorAgent
from services.output_writer import write_case_output
from shared.constants import (
    MODEL_FRAMEWORK,
    MODEL_NAME,
    MODEL_PARAMETER_SIZE_BILLION,
    MODEL_RUNTIME,
)
from shared.trace import DEFAULT_TRACE_PATH, TraceLogger


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", help="run a single case ID, e.g. EC_004")
    parser.add_argument("--input-dir", default=ROOT / "input", type=Path)
    parser.add_argument("--output-dir", default=ROOT / "output", type=Path)
    parser.add_argument("--trace", default=DEFAULT_TRACE_PATH, type=Path)
    parser.add_argument("--no-llm", action="store_true", help="skip LLM intent classification")
    args = parser.parse_args()

    case_files = sorted(args.input_dir.glob("EC_*.json"))
    if args.case:
        case_files = [path for path in case_files if path.stem == args.case]
    if not case_files:
        print(f"No case files found in {args.input_dir}", file=sys.stderr)
        return 1

    coordinator = CoordinatorAgent(use_llm=not args.no_llm)
    issues: Counter[str] = Counter()
    started = time.time()

    with TraceLogger(args.trace) as trace:
        trace.log(
            "run_start",
            model=MODEL_NAME,
            parameter_size_billion=MODEL_PARAMETER_SIZE_BILLION,
            framework=MODEL_FRAMEWORK,
            runtime=MODEL_RUNTIME,
            llm_enabled=not args.no_llm,
            case_count=len(case_files),
        )
        for path in case_files:
            case = json.loads(path.read_text(encoding="utf-8"))
            output = coordinator.handle_case(case, trace)
            write_case_output(output, args.output_dir)
            issues[output["assessment"]["primary_issue"]] += 1
            print(
                f"{case['case_id']}: {output['assessment']['primary_issue']}"
                f" (refund {output['financial_resolution']['recommended_refund_brl']} BRL)"
            )
        trace.log(
            "run_complete",
            cases=len(case_files),
            seconds=round(time.time() - started, 1),
            primary_issue_counts=dict(issues),
        )

    print(f"\n{len(case_files)} case(s) in {time.time() - started:.1f}s -> {args.output_dir}")
    for issue, count in issues.most_common():
        print(f"  {issue}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
