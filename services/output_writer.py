
"""Atomic JSON output writer for verified case outputs."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from pydantic import BaseModel


class OutputWriter:
    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)

    def write(self, output: Any) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        case_id = output.case_id if hasattr(output, "case_id") else output["case_id"]
        target = self.output_dir / f"{case_id}.json"
        payload = output.model_dump(mode="json") if isinstance(output, BaseModel) else output
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=self.output_dir,
            delete=False,
            suffix=".tmp",
        ) as tmp:
            json.dump(payload, tmp, ensure_ascii=False, indent=2)
            tmp.write("\n")
            tmp_path = Path(tmp.name)
        tmp_path.replace(target)
        return target
