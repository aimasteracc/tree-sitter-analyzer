"""Bounded JSONL loading and corpus summaries for NO1-010B records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .record import BenchmarkRecord, BenchmarkRecordError, record_from_dict

_MAX_CORPUS_BYTES = 8 * 1024 * 1024  # mirrors task_harness's input bound


def _strict_json_loads(text: str) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> Any:
        raise ValueError(f"non-standard JSON constant {value!r}")

    return json.loads(
        text,
        object_pairs_hook=reject_duplicates,
        parse_constant=reject_constant,
    )


def load_corpus_records(path: str) -> list[BenchmarkRecord]:
    import sys

    if path == "-":
        binary_stdin = getattr(sys.stdin, "buffer", None)
        if binary_stdin is not None:
            raw_bytes = binary_stdin.read(_MAX_CORPUS_BYTES + 1)
        else:
            try:
                raw_bytes = sys.stdin.read(_MAX_CORPUS_BYTES + 1).encode("utf-8")
            except UnicodeEncodeError as exc:
                raise BenchmarkRecordError("corpus must be valid UTF-8") from exc
    else:
        with Path(path).open("rb") as handle:
            raw_bytes = handle.read(_MAX_CORPUS_BYTES + 1)

    if len(raw_bytes) > _MAX_CORPUS_BYTES:
        raise BenchmarkRecordError("corpus exceeds the 8 MiB input bound")
    try:
        raw = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BenchmarkRecordError("corpus must be valid UTF-8") from exc

    lines = [line.removesuffix("\r") for line in raw.split("\n")]
    records: list[BenchmarkRecord] = []
    seen_ids: set[str] = set()
    for index, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            payload = _strict_json_loads(line)
        except (RecursionError, ValueError) as exc:
            raise BenchmarkRecordError(
                f"corpus line {index}: invalid JSON: {exc}"
            ) from exc
        record = record_from_dict(payload)
        if record.id in seen_ids:
            raise BenchmarkRecordError(
                f"corpus line {index}: duplicate id {record.id!r}"
            )
        seen_ids.add(record.id)
        records.append(record)
    if not records:
        raise BenchmarkRecordError("corpus is empty")
    return records


def per_class_counts(records: list[BenchmarkRecord]) -> dict[str, int]:
    return {
        task_class: sum(1 for record in records if record.task_class == task_class)
        for task_class in ("bugfix", "refactor", "migration", "test_selection")
    }
