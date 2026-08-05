"""Thread-safe JSONL trace writer for the latest coordinator run."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from shared.a2a_messages import A2AMessage


class TraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    run_id: str
    event_type: str
    status: str
    case_id: str | None = None
    correlation_id: str | None = None
    actor: str = "coordinator"
    message_id: str | None = None
    duration_ms: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class TraceWriter:
    """Write one complete run, replacing any trace from an earlier run."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = Lock()
        self._run_id: str | None = None

    @property
    def run_id(self) -> str:
        if self._run_id is None:
            raise RuntimeError("trace run has not been started")
        return self._run_id

    def start_run(self, run_id: str, *, case_count: int) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self.path.write_text("", encoding="utf-8")
            self._run_id = run_id
        self.record(
            event_type="run_started",
            status="started",
            details={"case_count": case_count},
        )

    def finish_run(self, *, succeeded: int, failed: int) -> None:
        self.record(
            event_type="run_finished",
            status="succeeded" if failed == 0 else "completed_with_errors",
            details={"succeeded": succeeded, "failed": failed},
        )

    def record(
        self,
        *,
        event_type: str,
        status: str,
        case_id: str | None = None,
        correlation_id: str | None = None,
        actor: str = "coordinator",
        message_id: str | None = None,
        duration_ms: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        event = TraceEvent(
            run_id=self.run_id,
            event_type=event_type,
            status=status,
            case_id=case_id,
            correlation_id=correlation_id,
            actor=actor,
            message_id=message_id,
            duration_ms=round(duration_ms, 3) if duration_ms is not None else None,
            details=details or {},
        )
        line = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
        with self._lock:
            with self.path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(line + "\n")

    def record_message(
        self,
        direction: str,
        message: A2AMessage,
        *,
        duration_ms: float | None = None,
    ) -> None:
        self.record(
            event_type=f"handoff_{direction}",
            status=message.status.value,
            case_id=message.case_id,
            correlation_id=message.correlation_id,
            actor=message.sender.value,
            message_id=message.message_id,
            duration_ms=duration_ms,
            details={
                "recipient": message.recipient.value,
                "message_type": message.message_type.value,
                "causation_id": message.causation_id,
                "payload": message.payload,
                "error": (
                    message.error.model_dump(mode="json") if message.error else None
                ),
            },
        )
