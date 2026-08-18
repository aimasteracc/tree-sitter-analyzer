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
        "oracle_baseline_reason": "dispatch-returns-none",
        "verification_argv": ["uv", "run", "pytest", "tests/", "-q"],
        "expected_terminal": {"verdict": "PASS", "reason_code": None},
        "defect": {"file": "src/dispatch.py", "line": 12, "kind": "missing-else"},
    }


def test_record_from_dict_accepts_valid_payload() -> None:
    record = record_from_dict(_valid_payload())
    assert record.id == "no1-010b/0001-bugfix-dispatch-null"
    assert record.task_class == "bugfix"
    assert record.repo_commit == "0" * 40
    assert record.allowed_paths == ("src/dispatch.py", "tests/")
    assert record.verification_argv == ("uv", "run", "pytest", "tests/", "-q")
    assert record.oracle_baseline_reason == "dispatch-returns-none"
    assert record.expected_terminal.verdict == "PASS"
    assert record.expected_terminal.reason_code is None


def test_record_from_dict_rejects_unknown_fields() -> None:
    payload = _valid_payload()
    payload["sneaky"] = True
    with pytest.raises(BenchmarkRecordError, match="unknown record fields"):
        record_from_dict(payload)


def test_record_from_dict_rejects_invalid_enums() -> None:
    for field, bad in (
        ("task_class", "bugfiix"),
        ("operation", "understnd"),
    ):
        payload = _valid_payload()
        payload[field] = bad
        with pytest.raises(BenchmarkRecordError, match="invalid"):
            record_from_dict(payload)


def test_record_from_dict_rejects_empty_task() -> None:
    payload = _valid_payload()
    payload["task"] = "  "
    with pytest.raises(BenchmarkRecordError, match="task must not be empty"):
        record_from_dict(payload)


def test_record_from_dict_rejects_short_commit() -> None:
    payload = _valid_payload()
    payload["repo_commit"] = "abc"
    with pytest.raises(BenchmarkRecordError, match="hex git sha"):
        record_from_dict(payload)


def test_record_accepts_double_dot_prefix_inside_legitimate_segment() -> None:
    payload = _valid_payload()
    payload["allowed_paths"] = ["src/..generated/config.py"]
    record = record_from_dict(payload)

    assert record.allowed_paths == ("src/..generated/config.py",)
    assert path_allowed("src/..generated/config.py", record.allowed_paths) is True


def test_record_accepts_allowed_path_with_space() -> None:
    payload = _valid_payload()
    payload["allowed_paths"] = ["src/my file.py"]

    assert record_from_dict(payload).allowed_paths == ("src/my file.py",)


def test_path_allowed_is_segment_aware() -> None:
    allowed = ("src/dispatch.py", "tests/")
    assert path_allowed("src/dispatch.py", allowed) is True
    assert path_allowed("tests/test_dispatch.py", allowed) is True
    assert path_allowed("tests-escape/file.py", allowed) is False
    assert path_allowed("src/routes.py", allowed) is False
    assert path_allowed("tests", allowed) is False  # the dir itself is not a descendant


def test_record_rejects_non_object_payload() -> None:
    with pytest.raises(BenchmarkRecordError, match="JSON object"):
        record_from_dict([])  # type: ignore[arg-type]


def test_record_rejects_missing_fields() -> None:
    payload = _valid_payload()
    del payload["operation"]
    with pytest.raises(BenchmarkRecordError, match="missing record fields"):
        record_from_dict(payload)


@pytest.mark.parametrize("field", ["id", "repo", "oracle", "oracle_baseline_reason"])
def test_record_rejects_blank_scalar_fields(field: str) -> None:
    payload = _valid_payload()
    payload[field] = "  "
    with pytest.raises(BenchmarkRecordError, match=f"{field} must be a non-empty"):
        record_from_dict(payload)


def test_record_rejects_blank_verification_command_hint() -> None:
    payload = _valid_payload()
    payload["verification_command"] = "  "
    with pytest.raises(BenchmarkRecordError, match="verification_command"):
        record_from_dict(payload)


@pytest.mark.parametrize(
    "bad_reason",
    ["Returns None", "has space", "UPPER", "trailing-", "-leading", "double--dash"],
)
def test_record_rejects_non_kebab_reason_tokens(bad_reason: str) -> None:
    payload = _valid_payload()
    payload["oracle_baseline_reason"] = bad_reason
    with pytest.raises(BenchmarkRecordError, match="lowercase-kebab token"):
        record_from_dict(payload)


@pytest.mark.parametrize(
    "bad_argv", ["uv run pytest", [], [""], ["uv", 42], ["uv", " "]]
)
def test_record_rejects_invalid_verification_argv(bad_argv: object) -> None:
    payload = _valid_payload()
    payload["verification_argv"] = bad_argv
    with pytest.raises(BenchmarkRecordError, match="verification_argv"):
        record_from_dict(payload)


def test_record_rejects_malformed_defect() -> None:
    payload = _valid_payload()
    payload["defect"] = "not-an-object"
    with pytest.raises(BenchmarkRecordError, match="defect must be an object"):
        record_from_dict(payload)


def test_record_rejects_malformed_patch() -> None:
    payload = _valid_payload()
    payload["patch"] = 42
    with pytest.raises(BenchmarkRecordError, match="patch must be a string"):
        record_from_dict(payload)


@pytest.mark.parametrize(
    "patch",
    [
        "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n\\ No newline at end of file\n+new\n",
        "--- /dev/null\n+++ b/x.py\n@@ -0,0 +1 @@\n+new\n",
    ],
)
def test_record_accepts_unified_diff_patch(patch: str) -> None:
    payload = _valid_payload()
    payload["patch"] = patch
    assert record_from_dict(payload).patch == patch


def test_record_rejects_reference_patch_with_unpaired_surrogate() -> None:
    payload = _valid_payload()
    payload["patch"] = (
        "--- a/src/dispatch.py\n+++ b/src/dispatch.py\n@@ -1 +1 @@\n-old\n+\ud800\n"
    )

    with pytest.raises(BenchmarkRecordError, match="valid UTF-8"):
        record_from_dict(payload)


@pytest.mark.parametrize(
    "patch",
    [
        "",
        "--- a/x.py\n+++ b/x.py\n@@ malformed @@\n",
        "+stray",
        "--- a/x.py\n+++ b/x.py\n",
        "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n",
        "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n context\n@@ -0,0 +1 @@\n context\n",
        "--- a/x.py\n+++ b/x.py\n@@ -0,0 +1 @@\n-old\n",
        "--- a/x.py\n+++ b/x.py\n@@ -1 +0,0 @@\n+new\n",
        "--- a/x.py\n+++ b/x.py\ndiff --git a/y.py b/y.py\n@@ -1 +1 @@\n-old\n+new\n",
        "--- a/x.py\n+++ b/x.py\n@@ -1,12345678 +1,12345678 @@\n-old\n+new\n",
    ],
)
def test_record_rejects_empty_or_non_diff_patch(patch: str) -> None:
    payload = _valid_payload()
    payload["patch"] = patch
    with pytest.raises(BenchmarkRecordError, match="non-empty unified diff"):
        record_from_dict(payload)


@pytest.mark.parametrize("bad_selected", ["tests/x.py", ["tests/x.py", 42]])
def test_record_rejects_malformed_selected_tests(bad_selected: object) -> None:
    payload = _valid_payload()
    payload["selected_tests"] = bad_selected
    with pytest.raises(BenchmarkRecordError, match="list of strings"):
        record_from_dict(payload)


def test_record_rejects_duplicate_allowed_paths() -> None:
    payload = _valid_payload()
    payload["allowed_paths"] = ["tests/", "tests/"]
    with pytest.raises(BenchmarkRecordError, match="duplicates"):
        record_from_dict(payload)


def test_record_rejects_duplicate_selected_tests() -> None:
    payload = _valid_payload()
    payload["selected_tests"] = ["tests/test_app.py", "tests/test_app.py"]
    with pytest.raises(BenchmarkRecordError, match="selected_tests.*duplicates"):
        record_from_dict(payload)


def test_record_rejects_empty_allowed_paths() -> None:
    payload = _valid_payload()
    payload["allowed_paths"] = []
    with pytest.raises(BenchmarkRecordError, match="non-empty list"):
        record_from_dict(payload)


@pytest.mark.parametrize("field", ["task_class", "operation"])
def test_record_rejects_non_string_enum_values(field: str) -> None:
    payload = _valid_payload()
    payload[field] = ["bugfix"]
    with pytest.raises(BenchmarkRecordError, match="invalid"):
        record_from_dict(payload)


def test_record_rejects_non_object_expected_terminal() -> None:
    payload = _valid_payload()
    payload["expected_terminal"] = "PASS"
    with pytest.raises(BenchmarkRecordError, match="must be an object"):
        record_from_dict(payload)


@pytest.mark.parametrize(
    "terminal",
    [
        {"verdict": "PASS"},
        {"verdict": "PASS", "reason_code": None, "extra": True},
    ],
)
def test_record_rejects_non_exact_expected_terminal_shape(terminal: dict) -> None:
    payload = _valid_payload()
    payload["expected_terminal"] = terminal
    with pytest.raises(BenchmarkRecordError, match="contain exactly"):
        record_from_dict(payload)


@pytest.mark.parametrize("verdict", ["MAYBE", ["PASS"]])
def test_record_rejects_invalid_expected_terminal_verdict(verdict: object) -> None:
    payload = _valid_payload()
    payload["expected_terminal"] = {"verdict": verdict, "reason_code": None}
    with pytest.raises(BenchmarkRecordError, match="invalid expected_terminal verdict"):
        record_from_dict(payload)


@pytest.mark.parametrize(
    "terminal",
    [
        {"verdict": "PASS", "reason_code": "ORACLE_FAILED"},
        {"verdict": "FAIL", "reason_code": None},
        {"verdict": "FAIL", "reason_code": "ORACLE_TIMEOUT"},
        {"verdict": "UNKNOWN", "reason_code": None},
        {"verdict": "UNKNOWN", "reason_code": "ORACLE_FAILED"},
        {"verdict": "FAIL", "reason_code": "TEST_SELECTION_FAILED"},
    ],
)
def test_record_rejects_mismatched_expected_terminal_reason(terminal: dict) -> None:
    payload = _valid_payload()
    payload["expected_terminal"] = terminal
    with pytest.raises(
        BenchmarkRecordError, match="reason_code|unknown_reason|task_class"
    ):
        record_from_dict(payload)


@pytest.mark.parametrize(
    ("terminal", "verdict", "reason_code"),
    [
        (
            {"verdict": "FAIL", "reason_code": "TEST_SELECTION_FAILED"},
            "FAIL",
            "TEST_SELECTION_FAILED",
        ),
        (
            {"verdict": "UNKNOWN", "reason_code": "PATCH_NOT_APPLICABLE"},
            "UNKNOWN",
            "PATCH_NOT_APPLICABLE",
        ),
    ],
)
def test_record_accepts_non_pass_expected_terminal(
    terminal: dict, verdict: str, reason_code: str
) -> None:
    payload = _valid_payload()
    payload["expected_terminal"] = terminal
    if reason_code == "TEST_SELECTION_FAILED":
        payload["task_class"] = "test_selection"
    result = record_from_dict(payload).expected_terminal
    assert result.verdict == verdict
    assert result.reason_code == reason_code


def test_record_rejects_non_hex_repo_commit() -> None:
    payload = _valid_payload()
    payload["repo_commit"] = "g" * 40
    with pytest.raises(BenchmarkRecordError, match="hex git sha"):
        record_from_dict(payload)


def test_record_rejects_nul_in_verification_argv() -> None:
    payload = _valid_payload()
    payload["verification_argv"] = ["python", "bad\x00arg"]
    with pytest.raises(BenchmarkRecordError, match="must not contain NUL"):
        record_from_dict(payload)


def test_path_canonicalization_rejects_all_bad_forms() -> None:
    for bad in (
        None,
        "",
        "/abs/path.py",
        "./rel.py",
        "..",
        "../x.py",
        "a/../b.py",
        "a/./b.py",
        "a//b.py",
        "a\\b.py",
        "src/é.py",
        "C:/outside/file.py",
        "C:\\outside\\file.py",
    ):
        payload = _valid_payload()
        payload["allowed_paths"] = [bad]
        with pytest.raises(BenchmarkRecordError, match="path"):
            record_from_dict(payload)


def test_record_rejects_selected_tests_for_non_selection_task() -> None:
    payload = _valid_payload()
    payload["selected_tests"] = ["tests/test_app.py"]
    with pytest.raises(BenchmarkRecordError, match="task_class test_selection"):
        record_from_dict(payload)


def test_to_task_request_understand_operation() -> None:
    understand = record_from_dict({**_valid_payload(), "operation": "understand"})
    op, req = understand.to_task_request()
    assert op == "understand" and req == {"task": understand.task}


def test_to_task_request_assess_change_operation() -> None:
    assess = record_from_dict({**_valid_payload(), "operation": "assess_change"})
    op, req = assess.to_task_request()
    assert op == "assess_change" and req == {"diff": {"source": "workspace"}}


def test_to_task_request_projection() -> None:
    record = record_from_dict(_valid_payload())
    operation, request = record.to_task_request()
    assert operation == "plan_change"
    assert request == {"task": "dispatch returns None for an unknown route"}
    assert "allowed_paths" not in request


def test_loader_rejects_invalid_json_line(tmp_path: Path) -> None:
    corpus = tmp_path / "bad.jsonl"
    corpus.write_text("not-json\n", encoding="utf-8")
    with pytest.raises(BenchmarkRecordError, match="invalid JSON"):
        load_corpus_records(str(corpus))


def test_loader_rejects_oversized_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    import io
    import sys

    monkeypatch.setattr(sys, "stdin", io.StringIO("x" * (8 * 1024 * 1024 + 1)))
    with pytest.raises(BenchmarkRecordError, match="8 MiB"):
        load_corpus_records("-")


def test_loader_reads_binary_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    import io
    import sys
    from types import SimpleNamespace

    raw = (json.dumps(_valid_payload()) + "\n").encode()
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(raw)))

    assert load_corpus_records("-")[0].id == _valid_payload()["id"]


def test_loader_rejects_empty_corpus(tmp_path: Path) -> None:
    corpus = tmp_path / "empty.jsonl"
    corpus.write_text("\n\n", encoding="utf-8")
    with pytest.raises(BenchmarkRecordError, match="corpus is empty"):
        load_corpus_records(str(corpus))


def test_loader_rejects_oversized_file(tmp_path: Path) -> None:
    corpus = tmp_path / "big.jsonl"
    corpus.write_text("x" * (8 * 1024 * 1024 + 1), encoding="utf-8")
    with pytest.raises(BenchmarkRecordError, match="8 MiB"):
        load_corpus_records(str(corpus))


def test_loader_enforces_file_limit_in_bytes(tmp_path: Path) -> None:
    corpus = tmp_path / "multi-byte.jsonl"
    corpus.write_bytes("界".encode() * ((8 * 1024 * 1024) // 3 + 1))
    with pytest.raises(BenchmarkRecordError, match="8 MiB"):
        load_corpus_records(str(corpus))


def test_loader_rejects_non_utf8_bytes(tmp_path: Path) -> None:
    corpus = tmp_path / "binary.jsonl"
    corpus.write_bytes(b"\xff\n")
    with pytest.raises(BenchmarkRecordError, match="valid UTF-8"):
        load_corpus_records(str(corpus))


def test_loader_preserves_unicode_line_separator_inside_json(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["task"] = "first\u2028second"
    corpus = tmp_path / "unicode-separator.jsonl"
    corpus.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    records = load_corpus_records(str(corpus))
    assert records[0].task == "first\u2028second"


def test_loader_rejects_duplicate_keys(tmp_path: Path) -> None:
    corpus = tmp_path / "dup.jsonl"
    corpus.write_text('{"id": "a", "id": "b"}\n', encoding="utf-8")
    with pytest.raises(BenchmarkRecordError, match="duplicate key"):
        load_corpus_records(str(corpus))


def test_loader_rejects_nan_constant(tmp_path: Path) -> None:
    corpus = tmp_path / "nan.jsonl"
    corpus.write_text('{"id": "a", "task": NaN}\n', encoding="utf-8")
    with pytest.raises(BenchmarkRecordError, match="non-standard JSON constant"):
        load_corpus_records(str(corpus))


def test_per_class_counts_is_exact_for_all_classes() -> None:
    records = [
        record_from_dict(
            {**_valid_payload(), "id": f"task-{index}", "task_class": task_class}
        )
        for index, task_class in enumerate(
            ("bugfix", "refactor", "migration", "test_selection"), start=1
        )
    ]

    assert per_class_counts(records) == {
        "bugfix": 1,
        "refactor": 1,
        "migration": 1,
        "test_selection": 1,
    }


def test_per_class_counts_is_zero_for_empty_input() -> None:
    assert per_class_counts([]) == {
        "bugfix": 0,
        "refactor": 0,
        "migration": 0,
        "test_selection": 0,
    }


def test_loader_rejects_duplicate_record_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    import io
    import sys

    line = json.dumps(_valid_payload())
    monkeypatch.setattr(sys, "stdin", io.StringIO(line + "\n" + line + "\n"))
    with pytest.raises(BenchmarkRecordError, match="duplicate id"):
        load_corpus_records("-")
