"""Write validated case outputs to the output directory."""
from __future__ import annotations

import json
from pathlib import Path

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"


def write_case_output(output: dict, output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> Path:
    """Write one case result as <case_id>.json and return the path."""
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{output['case_id']}.json"
    with path.open("w", encoding="utf-8") as target:
        json.dump(output, target, ensure_ascii=False, indent=2)
        target.write("\n")
    return path
