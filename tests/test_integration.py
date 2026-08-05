"""Integration coverage for the coordinator's official 50-case batch."""

from __future__ import annotations

import json

from agents.coordinator_agent import CoordinatorAgent
from run_all import load_cases
from shared.trace import TraceWriter
from tests.fakes import MemoryOutputWriter, build_fake_agents


def test_all_official_inputs_complete_the_orchestration_flow(tmp_path) -> None:
    order, payment, delivery, policy, verifier = build_fake_agents()
    writer = MemoryOutputWriter()
    coordinator = CoordinatorAgent(
        order_seller_agent=order,
        payment_agent=payment,
        delivery_agent=delivery,
        policy_agent=policy,
        verifier_agent=verifier,
        trace_writer=TraceWriter(tmp_path / "trace.jsonl"),
        output_writer=writer,
        timeout_seconds=1,
        max_retries=0,
    )
    try:
        result = coordinator.run(load_cases("input"))
    finally:
        coordinator.close()

    assert result.succeeded == 50
    assert result.failed == 0
    assert len(writer.outputs) == 50
    assert [output.case_id for output in writer.outputs] == [
        f"EC_{index:03d}" for index in range(1, 51)
    ]

    events = [
        json.loads(line)
        for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert events[0]["event_type"] == "run_started"
    assert events[-1]["event_type"] == "run_finished"
    assert events[-1]["details"] == {"succeeded": 50, "failed": 0}
