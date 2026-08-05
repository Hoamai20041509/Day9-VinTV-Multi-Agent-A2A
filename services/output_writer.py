"""Stable JSON output writing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_output(result: dict[str, Any], output_dir: str | Path) -> Path:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f'{result["case_id"]}.json'
    temporary = destination.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temporary.replace(destination)
    return destination
