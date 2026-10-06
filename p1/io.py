"""Reading and writing the JSON Lines files the tools use (one JSON object per line)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator


def read_jsonl(path: str | Path) -> Iterator[dict]:
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                raise SystemExit(f"{path}, line {n}: not valid JSON ({e})") from None


def write_jsonl(path: str | Path, rows: Iterable[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def labels_by_id(path: str | Path) -> dict[str, list]:
    """Read a labels file: lines of {"id": ..., "output": {...}}. Several lines for one id are kept in file order,
    one per call of the step. Other keys (e.g., "input", "call") are ignored."""
    out: dict[str, list] = {}
    for row in read_jsonl(path):
        if "id" not in row or "output" not in row:
            raise SystemExit(f"{path}: every line needs \"id\" and \"output\"; got keys {sorted(row)}")
        out.setdefault(row["id"], []).append(row["output"])
    return out
