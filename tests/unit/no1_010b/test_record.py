"""Contract tests for the NO1-010B strict benchmark-record model (RFC-0026 §1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tree_sitter_analyzer.no1_010b.record import (
    BenchmarkRecordError,
    load_corpus_records,
    path_allowed,
    per_class_counts,
    record_from_dict,
)

CORPUS = Path(__file__).resolve().parents[3] / "benchmarks" / "no1_010b" / "corpus"


def _valid_payload() -> dict:
    return {
        "id": "no1-010b/0001-bugfix-dispatch-null",
        "task_class": "bugfix",
        "repo": "fixtures/dispatch_app",
        "repo_commit": "0" * 40,
        "operation": "plan_change",
        "task": "dispatch returns None for an unknown route",
        "allowed_paths": ["src/dispatch.py", "tests/"],
        "oracle": "oracles/0001.py",
        "oracle_baseline_reason": "returns None, no 404 branch",
        "verification_command": "uv run pytest tests/ -q",
        "expected_outcome": "PASS",
        "defect": {"file": "src/dispatch.py", "line": 12, "kind": "missing-else"},
    }


def test_record_from_dict_accepts_valid_payload() -> None:
    record = record_from_dict(_valid_payload())
    assert record.id == "no1-010b/0001-bugfix-dispatch-null"
    assert record.task_class == "bugfix"
    assert record.repo_commit == "0" * 40
    assert record.allowed_paths == ("src/dispatch.py", "tests/")


def test_record_from_dict_rejects_unknown_fields() -> None:
    payload = _valid_payload()
    payload["sneaky"] = True
    with pytest.raises(BenchmarkRecordError, match="unknown record fields"):
        record_from_dict(payload)


def test_record_from_dict_rejects_invalid_enums() -> None:
    for field, bad in (
        ("task_class", "bugfiix"),
        ("operation", "understnd"),
        ("expected_outcome", "MAYBE"),
    ):
        payload = _valid_payload()
        payload[field] = bad
        with pytest.raises(BenchmarkRecordError, match="invalid"):
            record_from_dict(payload)


def test_record_from_dict_rejects_empty_task_and_short_commit() -> None:
    payload = _valid_payload()
    payload["task"] = "  "
    with pytest.raises(BenchmarkRecordError, match="task must not be empty"):
        record_from_dict(payload)
    payload = _valid_payload()
    payload["repo_commit"] = "abc"
    with pytest.raises(BenchmarkRecordError, match="40-char git sha"):
        record_from_dict(payload)


def test_record_from_dict_rejects_non_canonical_paths() -> None:
    for bad in ("/abs/path.py", "./rel.py", "a/../b.py", "dir//x.py"):
        payload = _valid_payload()
        payload["allowed_paths"] = [bad]
        with pytest.raises(BenchmarkRecordError, match="path"):
            record_from_dict(payload)


def test_path_allowed_is_segment_aware() -> None:
    allowed = ("src/dispatch.py", "tests/")
    assert path_allowed("src/dispatch.py", allowed) is True
    assert path_allowed("tests/test_dispatch.py", allowed) is True
    assert path_allowed("tests-escape/file.py", allowed) is False
    assert path_allowed("src/routes.py", allowed) is False
    assert path_allowed("tests", allowed) is False  # the dir itself is not a descendant


def test_to_task_request_projection() -> None:
    record = record_from_dict(_valid_payload())
    operation, request = record.to_task_request()
    assert operation == "plan_change"
    assert request == {"task": "dispatch returns None for an unknown route"}
    # The projection never leaks benchmark-only fields into the task request.
    assert "allowed_paths" not in request


def test_seed_corpus_loads_with_exact_class_counts() -> None:
    records = load_corpus_records(str(CORPUS / "no1_010b_v1.jsonl"))
    assert len(records) == 10
    assert per_class_counts(records) == {
        "bugfix": 4,
        "refactor": 2,
        "migration": 2,
        "test_selection": 2,
    }
    assert sum(1 for r in records if r.expected_outcome == "PASS") == 9
    assert sum(1 for r in records if r.expected_outcome == "FAIL") == 1
    ids = [record.id for record in records]
    assert len(set(ids)) == 10  # no duplicates


def test_seed_corpus_duplicate_id_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    import io
    import sys

    line = json.dumps(_valid_payload())
    monkeypatch.setattr(sys, "stdin", io.StringIO(line + "\n" + line + "\n"))
    with pytest.raises(BenchmarkRecordError, match="duplicate id"):
        load_corpus_records("-")
