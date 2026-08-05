"""Coordinator behavior tests independent of domain implementations."""

from __future__ import annotations

import json
import time

from agents.coordinator_agent import CoordinatorAgent
from run_all import load_cases
from shared.a2a_messages import AgentName
from shared.trace import TraceWriter
from tests.fakes import FakeAgent, MemoryOutputWriter, build_fake_agents


def make_coordinator(tmp_path, *, order_agent=None, timeout=1.0):
    order, payment, delivery, policy, verifier = build_fake_agents()
    writer = MemoryOutputWriter()
    coordinator = CoordinatorAgent(
        order_seller_agent=order_agent or order,
        payment_agent=payment,
        delivery_agent=delivery,
        policy_agent=policy,
        verifier_agent=verifier,
        trace_writer=TraceWriter(tmp_path / "trace.jsonl"),
        output_writer=writer,
        timeout_seconds=timeout,
        max_retries=0,
    )
    return coordinator, writer


def test_one_case_runs_all_handoffs_and_writes_verified_output(tmp_path) -> None:
    coordinator, writer = make_coordinator(tmp_path)
    try:
        result = coordinator.run(load_cases("input", "EC_001"))
    finally:
        coordinator.close()

    assert result.succeeded == 1
    assert result.failed == 0
    assert len(writer.outputs) == 1

    events = [
        json.loads(line)
        for line in (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    received = [event for event in events if event["event_type"] == "handoff_received"]
    assert len(received) == 5
    assert len({event["correlation_id"] for event in received}) == 1


def test_timeout_fails_case_without_writing_output(tmp_path) -> None:
    order, *_ = build_fake_agents()

    def slow_response(message):
        time.sleep(0.05)
        return order._responder(message)

    slow_order = FakeAgent(AgentName.ORDER_SELLER, slow_response)
    coordinator, writer = make_coordinator(tmp_path, order_agent=slow_order, timeout=0.001)
    try:
        result = coordinator.run(load_cases("input", "EC_001"))
    finally:
        coordinator.close()

    assert result.succeeded == 0
    assert result.failed == 1
    assert writer.outputs == []
    assert "timed out" in result.errors["EC_001"]
