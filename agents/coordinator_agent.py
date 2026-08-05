"""Coordinator for the evidence-driven e-commerce dispute pipeline."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, TypeVar
from uuid import uuid4

from pydantic import BaseModel

from shared.a2a_messages import (
    A2AMessage,
    AgentName,
    AgentPort,
    MessageStatus,
    MessageType,
    OutputWriterPort,
)
from shared.schemas import (
    CaseInput,
    CaseOutput,
    DeliveryResult,
    OrderSellerResult,
    PaymentResult,
    PolicyResult,
    VerificationResult,
)
from shared.trace import TraceWriter


ResultModel = TypeVar("ResultModel", bound=BaseModel)


class CaseProcessingError(RuntimeError):
    def __init__(self, case_id: str, stage: str, message: str) -> None:
        super().__init__(f"{case_id} failed at {stage}: {message}")
        self.case_id = case_id
        self.stage = stage
        self.detail = message


@dataclass(slots=True)
class BatchRunResult:
    run_id: str
    outputs: list[CaseOutput] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def succeeded(self) -> int:
        return len(self.outputs)

    @property
    def failed(self) -> int:
        return len(self.errors)


class CoordinatorAgent:
    """Orchestrate domain agents without implementing their domain logic."""

    def __init__(
        self,
        *,
        order_seller_agent: AgentPort,
        payment_agent: AgentPort,
        delivery_agent: AgentPort,
        policy_agent: AgentPort,
        verifier_agent: AgentPort,
        trace_writer: TraceWriter,
        output_writer: OutputWriterPort | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 1,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")

        self._agents = {
            AgentName.ORDER_SELLER: order_seller_agent,
            AgentName.PAYMENT: payment_agent,
            AgentName.DELIVERY: delivery_agent,
            AgentName.POLICY: policy_agent,
            AgentName.VERIFIER: verifier_agent,
        }
        for expected_name, agent in self._agents.items():
            if getattr(agent, "name", None) != expected_name:
                raise ValueError(f"agent registered for {expected_name.value} has wrong name")
            if not callable(getattr(agent, "handle", None)):
                raise TypeError(f"{expected_name.value} agent must implement handle(message)")

        self._trace = trace_writer
        self._output_writer = output_writer
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="agent")

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def __enter__(self) -> "CoordinatorAgent":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def run(
        self,
        cases: list[CaseInput],
        *,
        continue_on_error: bool = True,
    ) -> BatchRunResult:
        self._validate_case_batch(cases)
        run_id = uuid4().hex
        result = BatchRunResult(run_id=run_id)
        self._trace.start_run(run_id, case_count=len(cases))

        for case in cases:
            try:
                output = self.process_case(case)
                if self._output_writer is not None:
                    self._output_writer.write(output)
                result.outputs.append(output)
                self._trace.record(
                    event_type="case_finished",
                    status="succeeded",
                    case_id=case.case_id,
                    details={"order_id": case.order_id, "output_written": self._output_writer is not None},
                )
            except Exception as exc:
                result.errors[case.case_id] = str(exc)
                self._trace.record(
                    event_type="case_finished",
                    status="failed",
                    case_id=case.case_id,
                    details={"order_id": case.order_id, "error": str(exc)},
                )
                if not continue_on_error:
                    self._trace.finish_run(succeeded=result.succeeded, failed=result.failed)
                    raise

        self._trace.finish_run(succeeded=result.succeeded, failed=result.failed)
        return result

    def process_case(self, case: CaseInput) -> CaseOutput:
        correlation_id = uuid4().hex
        self._trace.record(
            event_type="case_started",
            status="started",
            case_id=case.case_id,
            correlation_id=correlation_id,
            details={"order_id": case.order_id, "policy_version": case.policy_version},
        )

        order_result = self._request_result(
            case=case,
            correlation_id=correlation_id,
            recipient=AgentName.ORDER_SELLER,
            request_type=MessageType.ORDER_SELLER_REQUEST,
            response_type=MessageType.ORDER_SELLER_RESULT,
            payload={"case_id": case.case_id, "order_id": case.order_id},
            result_model=OrderSellerResult,
            stage="order_seller",
        )
        self._validate_domain_identity(case, order_result.case_id, order_result.order_id, "order_seller")

        payment_result = self._request_result(
            case=case,
            correlation_id=correlation_id,
            recipient=AgentName.PAYMENT,
            request_type=MessageType.PAYMENT_REQUEST,
            response_type=MessageType.PAYMENT_RESULT,
            payload={
                "case_id": case.case_id,
                "order_id": case.order_id,
                "item_total_brl": order_result.item_total_brl,
                "freight_total_brl": order_result.freight_total_brl,
            },
            result_model=PaymentResult,
            stage="payment",
        )
        self._validate_domain_identity(case, payment_result.case_id, payment_result.order_id, "payment")

        delivery_result = self._request_result(
            case=case,
            correlation_id=correlation_id,
            recipient=AgentName.DELIVERY,
            request_type=MessageType.DELIVERY_REQUEST,
            response_type=MessageType.DELIVERY_RESULT,
            payload={
                "case_id": case.case_id,
                "order_id": case.order_id,
                "order_delivered_carrier_date": order_result.order_delivered_carrier_date,
                "order_delivered_customer_date": order_result.order_delivered_customer_date,
                "order_estimated_delivery_date": order_result.order_estimated_delivery_date,
                "late_handoffs": order_result.late_handoffs,
            },
            result_model=DeliveryResult,
            stage="delivery",
        )
        self._validate_domain_identity(case, delivery_result.case_id, delivery_result.order_id, "delivery")

        policy_result = self._request_result(
            case=case,
            correlation_id=correlation_id,
            recipient=AgentName.POLICY,
            request_type=MessageType.POLICY_REQUEST,
            response_type=MessageType.POLICY_RESULT,
            payload={
                "case": case,
                "order_seller_result": order_result,
                "payment_result": payment_result,
                "delivery_result": delivery_result,
            },
            result_model=PolicyResult,
            stage="policy",
        )
        if policy_result.case_id != case.case_id:
            raise CaseProcessingError(case.case_id, "policy", "response case_id mismatch")
        if policy_result.draft_output.case_id != case.case_id:
            raise CaseProcessingError(case.case_id, "policy", "draft output case_id mismatch")

        verification = self._request_result(
            case=case,
            correlation_id=correlation_id,
            recipient=AgentName.VERIFIER,
            request_type=MessageType.VERIFIER_REQUEST,
            response_type=MessageType.VERIFIER_RESULT,
            payload={"case": case, "draft_output": policy_result.draft_output},
            result_model=VerificationResult,
            stage="verifier",
        )
        if verification.case_id != case.case_id:
            raise CaseProcessingError(case.case_id, "verifier", "response case_id mismatch")
        if not verification.is_valid or verification.verified_output is None:
            errors = "; ".join(verification.errors) or "output rejected"
            raise CaseProcessingError(case.case_id, "verifier", errors)
        if verification.verified_output.case_id != case.case_id:
            raise CaseProcessingError(case.case_id, "verifier", "verified output case_id mismatch")

        return verification.verified_output

    def _request_result(
        self,
        *,
        case: CaseInput,
        correlation_id: str,
        recipient: AgentName,
        request_type: MessageType,
        response_type: MessageType,
        payload: dict[str, Any],
        result_model: type[ResultModel],
        stage: str,
    ) -> ResultModel:
        request = A2AMessage.request(
            correlation_id=correlation_id,
            case_id=case.case_id,
            recipient=recipient,
            message_type=request_type,
            payload=payload,
        )
        response = self._dispatch(request, response_type=response_type, stage=stage)
        try:
            return result_model.model_validate(response.payload)
        except Exception as exc:
            raise CaseProcessingError(case.case_id, stage, f"invalid response payload: {exc}") from exc

    def _dispatch(
        self,
        request: A2AMessage,
        *,
        response_type: MessageType,
        stage: str,
    ) -> A2AMessage:
        agent = self._agents[request.recipient]
        last_error = "unknown agent error"

        for attempt in range(1, self._max_retries + 2):
            self._trace.record_message("sent", request)
            started = perf_counter()
            future = self._executor.submit(agent.handle, request)
            try:
                raw_response = future.result(timeout=self._timeout_seconds)
                elapsed_ms = (perf_counter() - started) * 1000
                response = A2AMessage.model_validate(raw_response)
                self._validate_response(request, response, response_type)
                self._trace.record_message("received", response, duration_ms=elapsed_ms)

                if response.status == MessageStatus.SUCCEEDED:
                    return response

                last_error = response.error.message if response.error else "agent returned failure"
                retryable = bool(response.error and response.error.retryable)
                if not retryable or attempt > self._max_retries:
                    break
            except FutureTimeoutError:
                future.cancel()
                last_error = f"timed out after {self._timeout_seconds:g}s"
                self._trace.record(
                    event_type="handoff_timeout",
                    status="failed",
                    case_id=request.case_id,
                    correlation_id=request.correlation_id,
                    actor="coordinator",
                    message_id=request.message_id,
                    duration_ms=(perf_counter() - started) * 1000,
                    details={"stage": stage, "attempt": attempt},
                )
            except Exception as exc:
                last_error = str(exc)
                self._trace.record(
                    event_type="handoff_error",
                    status="failed",
                    case_id=request.case_id,
                    correlation_id=request.correlation_id,
                    actor="coordinator",
                    message_id=request.message_id,
                    duration_ms=(perf_counter() - started) * 1000,
                    details={"stage": stage, "attempt": attempt, "error": str(exc)},
                )

        raise CaseProcessingError(request.case_id, stage, last_error)

    @staticmethod
    def _validate_response(
        request: A2AMessage,
        response: A2AMessage,
        expected_type: MessageType,
    ) -> None:
        if response.correlation_id != request.correlation_id:
            raise ValueError("response correlation_id mismatch")
        if response.causation_id != request.message_id:
            raise ValueError("response causation_id mismatch")
        if response.case_id != request.case_id:
            raise ValueError("response case_id mismatch")
        if response.sender != request.recipient:
            raise ValueError("response sender mismatch")
        if response.recipient != AgentName.COORDINATOR:
            raise ValueError("response recipient must be coordinator")
        if response.message_type != expected_type:
            raise ValueError("unexpected response message_type")

    @staticmethod
    def _validate_domain_identity(
        case: CaseInput,
        result_case_id: str,
        result_order_id: str,
        stage: str,
    ) -> None:
        if result_case_id != case.case_id:
            raise CaseProcessingError(case.case_id, stage, "response case_id mismatch")
        if result_order_id != case.order_id:
            raise CaseProcessingError(case.case_id, stage, "response order_id mismatch")

    @staticmethod
    def _validate_case_batch(cases: list[CaseInput]) -> None:
        if not cases:
            raise ValueError("at least one case is required")
        case_ids = [case.case_id for case in cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("case batch contains duplicate case_id values")
