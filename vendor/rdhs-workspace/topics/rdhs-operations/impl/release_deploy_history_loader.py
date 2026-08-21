from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def load_monthly_summaries(csv_path: Path, months: list[str]) -> list[dict[str, Any]]:
    if not csv_path.exists():
        return []

    rows: list[dict[str, Any]] = []
    with csv_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            if not months or row.get("month") in months:
                rows.append(dict(row))
    return rows


def load_release_plan_history(
    jsonl_path: Path, month_start: str, month_end: str
) -> list[dict[str, Any]]:
    if not jsonl_path.exists():
        return []

    rows: list[dict[str, Any]] = []
    with jsonl_path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                row = json.loads(line)
                month = row.get("month", "")
                if month_start <= month < month_end:
                    rows.append(row)
    return rows


def load_deploy_task_history(
    jsonl_path: Path, month_start: str, month_end: str
) -> list[dict[str, Any]]:
    if not jsonl_path.exists():
        return []

    rows: list[dict[str, Any]] = []
    with jsonl_path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                row = json.loads(line)
                month = row.get("month", "")
                if month_start <= month < month_end:
                    rows.append(row)
    return rows
