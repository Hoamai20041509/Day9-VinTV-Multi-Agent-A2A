
import csv
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"


def read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    csv_path = Path(path)
    if not csv_path.is_absolute():
        csv_path = DATA_DIR / csv_path

    with csv_path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def filter_rows(rows: Iterable[dict[str, str]], key: str, value: str) -> list[dict[str, str]]:
    return [row for row in rows if row.get(key) == value]
