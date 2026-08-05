"""JSONL trace logging for real pipeline runs.

Each run opens the trace file in write mode (no append) so the file always
holds exactly one run, as required by the submission checklist.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

DEFAULT_TRACE_PATH = Path(__file__).resolve().parents[1] / "logging" / "trace.jsonl"


class TraceLogger:
    """Append structured events for one pipeline run to a JSONL file."""

    def __init__(self, path: str | Path = DEFAULT_TRACE_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle: TextIO | None = None

    def __enter__(self) -> "TraceLogger":
        self._handle = self.path.open("w", encoding="utf-8")
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    def log(self, event: str, **fields: Any) -> None:
        if self._handle is None:
            raise RuntimeError("TraceLogger must be used as a context manager")
        record = {"ts": datetime.now().isoformat(timespec="seconds"), "event": event}
        record.update(fields)
        self._handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._handle.flush()

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None
