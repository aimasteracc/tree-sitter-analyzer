"""Strict benchmark-record model for the NO1-010B corpus (RFC-0026 §1)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal, cast

TaskClass = Literal["bugfix", "refactor", "migration", "test_selection"]
Operation = Literal["understand", "plan_change", "assess_change"]
ExpectedVerdict = Literal["PASS", "FAIL", "UNKNOWN"]
ProductReasonCode = Literal[
    "PATH_VIOLATION",
    "ORACLE_FAILED",
    "VERIFICATION_FAILED",
    "STALE_ROWS",
    "UNSUPPORTED_RELATIONSHIP",
    "TEST_SELECTION_FAILED",
]
UnknownReasonCode = Literal[
    "PATCH_NOT_APPLICABLE",
    "PATCH_OVER_BOUND",
    "PROVENANCE_MISSING",
    "AGENT_OUTPUT_ERROR",
    "ORACLE_LOAD_ERROR",
    "ORACLE_EXECUTION_ERROR",
    "ORACLE_PROTOCOL_ERROR",
    "ORACLE_TIMEOUT",
    "VERIFICATION_EXECUTION_ERROR",
    "VERIFICATION_TIMEOUT",
    "INDEX_REFRESH_ERROR",
    "INDEX_QUERY_ERROR",
    "EVIDENCE_CHECK_ERROR",
    "SANDBOX_FAILURE",
    "REGISTRY_FAILURE",
]
TerminalReasonCode = ProductReasonCode | UnknownReasonCode

_TASK_CLASSES = frozenset({"bugfix", "refactor", "migration", "test_selection"})
_OPERATIONS = frozenset({"understand", "plan_change", "assess_change"})
_EXPECTED_VERDICTS = frozenset({"PASS", "FAIL", "UNKNOWN"})
_PRODUCT_REASON_CODES = frozenset(
    {
        "PATH_VIOLATION",
        "ORACLE_FAILED",
        "VERIFICATION_FAILED",
        "STALE_ROWS",
        "UNSUPPORTED_RELATIONSHIP",
        "TEST_SELECTION_FAILED",
    }
)
_UNKNOWN_REASON_CODES = frozenset(
    {
        "PATCH_NOT_APPLICABLE",
        "PATCH_OVER_BOUND",
        "PROVENANCE_MISSING",
        "AGENT_OUTPUT_ERROR",
        "ORACLE_LOAD_ERROR",
        "ORACLE_EXECUTION_ERROR",
        "ORACLE_PROTOCOL_ERROR",
        "ORACLE_TIMEOUT",
        "VERIFICATION_EXECUTION_ERROR",
        "VERIFICATION_TIMEOUT",
        "INDEX_REFRESH_ERROR",
        "INDEX_QUERY_ERROR",
        "EVIDENCE_CHECK_ERROR",
        "SANDBOX_FAILURE",
        "REGISTRY_FAILURE",
    }
)
_EXPECTED_TERMINAL_FIELDS = frozenset({"verdict", "reason_code"})
_MAX_CORPUS_BYTES = 8 * 1024 * 1024  # mirrors task_harness's input bound

_REASON_TOKEN_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_PATCH_HUNK_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@(?: .*)?$")
_PATCH_COUNT_MAX_DIGITS = 7

_REQUIRED_FIELDS = frozenset(
    {
        "id",
        "task_class",
        "repo",
        "repo_commit",
        "operation",
        "task",
        "allowed_paths",
        "oracle",
        "oracle_baseline_reason",
        "verification_argv",
        "expected_terminal",
    }
)
_OPTIONAL_FIELDS = frozenset(
    {"defect", "patch", "selected_tests", "verification_command"}
)


class BenchmarkRecordError(ValueError):
    """One malformed corpus record; the exact message names the offending field."""


@dataclass(frozen=True)
class ExpectedTerminal:
    """The exact pre-registered verdict/reason pair for one reference attempt."""

    verdict: ExpectedVerdict
    reason_code: TerminalReasonCode | None


@dataclass(frozen=True)
class BenchmarkRecord:
    """One task with pinned provenance and an exact expected terminal state."""

    id: str
    task_class: TaskClass
    repo: str
    repo_commit: str
    operation: Operation
    task: str
    allowed_paths: tuple[str, ...]
    oracle: str
    oracle_baseline_reason: str
    verification_argv: tuple[str, ...]
    expected_terminal: ExpectedTerminal
    verification_command: str | None = None
    defect: dict[str, Any] | None = None
    patch: str | None = None
    selected_tests: tuple[str, ...] = ()

    def to_task_request(self) -> tuple[str, dict[str, Any]]:
        """Project only the task-layer fields (RFC-0026 §1)."""
        if self.operation == "understand":
            return "understand", {"task": self.task}
        if self.operation == "plan_change":
            return "plan_change", {"task": self.task}
        return "assess_change", {"diff": {"source": "workspace"}}


def _canonical_rel_path(raw: Any, field: str) -> str:
    """Accept only paths representable by the runner's unquoted Git grammar."""
    if not isinstance(raw, str) or not raw:
        raise BenchmarkRecordError(f"{field}: path must be a non-empty string")
    if "\\" in raw:
        raise BenchmarkRecordError(f"{field}: backslashes are not allowed")
    if not raw.isascii():
        raise BenchmarkRecordError(f"{field}: path must contain only ASCII")
    value = raw
    if value.startswith("/") or value.startswith("./"):
        raise BenchmarkRecordError(f"{field}: path must be repository-relative")
    if len(value) >= 2 and value[1] == ":" and value[0].isalpha():
        raise BenchmarkRecordError(f"{field}: drive-qualified paths are not allowed")
    if "//" in value:
        raise BenchmarkRecordError(f"{field}: empty path segments are not allowed")
    segments = value[:-1].split("/") if value.endswith("/") else value.split("/")
    if any(segment in {".", ".."} for segment in segments):
        raise BenchmarkRecordError(f"{field}: '.' and '..' segments are not allowed")
    return value


def path_allowed(rel_path: str, allowed_paths: tuple[str, ...]) -> bool:
    """Apply the segment-aware allowed-path contract (RFC-0026 C6)."""
    value = _canonical_rel_path(rel_path, "rel_path")
    for entry in allowed_paths:
        if entry.endswith("/"):
            prefix = entry
            if value.startswith(prefix) and len(value) > len(prefix):
                return True
        elif value == entry:
            return True
    return False


def patch_has_changed_hunk(lines: list[str]) -> bool:
    """Validate counted hunks and require at least one real changed line."""
    file_header_seen = False
    in_hunk = False
    remaining_old = 0
    remaining_new = 0
    hunk_changed = False
    completed_change = False
    for index, line in enumerate(lines):
        if in_hunk:
            if line == r"\ No newline at end of file":
                continue
            if line.startswith(" "):
                if remaining_old == 0 or remaining_new == 0:
                    return False
                remaining_old -= 1
                remaining_new -= 1
            elif line.startswith("-"):
                if remaining_old == 0:
                    return False
                remaining_old -= 1
                hunk_changed = True
            elif line.startswith("+"):
                if remaining_new == 0:
                    return False
                remaining_new -= 1
                hunk_changed = True
            else:
                return False
            if remaining_old == 0 and remaining_new == 0:
                completed_change = completed_change or hunk_changed
                in_hunk = False
            continue
        if line.startswith("diff --git "):
            file_header_seen = False
            continue
        if (
            line.startswith("--- ")
            and index + 1 < len(lines)
            and lines[index + 1].startswith("+++ ")
        ):
            file_header_seen = True
            continue
        if (
            line.startswith("+++ ")
            and index > 0
            and lines[index - 1].startswith("--- ")
        ):
            continue
        if not line.startswith("@@"):
            if line.startswith(("+", "-")):
                return False
            continue
        if not file_header_seen:
            return False
        match = _PATCH_HUNK_RE.fullmatch(line)
        if match is None:
            return False
        old_count, new_count = match.groups()
        if any(
            count is not None and len(count) > _PATCH_COUNT_MAX_DIGITS
            for count in (old_count, new_count)
        ):
            return False
        remaining_old = int(old_count) if old_count is not None else 1
        remaining_new = int(new_count) if new_count is not None else 1
        hunk_changed = False
        in_hunk = remaining_old != 0 or remaining_new != 0
    return completed_change and not in_hunk


def _expected_terminal_from_dict(raw: Any) -> ExpectedTerminal:
    if not isinstance(raw, dict):
        raise BenchmarkRecordError("expected_terminal must be an object")
    unknown = set(raw) - _EXPECTED_TERMINAL_FIELDS
    missing = _EXPECTED_TERMINAL_FIELDS - set(raw)
    if unknown or missing:
        raise BenchmarkRecordError(
            "expected_terminal must contain exactly verdict and reason_code"
        )

    verdict_raw = raw["verdict"]
    if not isinstance(verdict_raw, str) or verdict_raw not in _EXPECTED_VERDICTS:
        raise BenchmarkRecordError(
            f"invalid expected_terminal verdict: {verdict_raw!r}"
        )
    verdict = cast(ExpectedVerdict, verdict_raw)
    reason_raw = raw["reason_code"]
    if verdict == "PASS":
        if reason_raw is not None:
            raise BenchmarkRecordError(
                "PASS expected_terminal reason_code must be null"
            )
        return ExpectedTerminal(verdict, None)
    if not isinstance(reason_raw, str):
        raise BenchmarkRecordError(
            f"{verdict} expected_terminal reason_code must be a string"
        )
    if verdict == "FAIL":
        if reason_raw not in _PRODUCT_REASON_CODES:
            raise BenchmarkRecordError(
                "FAIL expected_terminal requires a product reason_code"
            )
    elif reason_raw not in _UNKNOWN_REASON_CODES:
        raise BenchmarkRecordError(
            "UNKNOWN expected_terminal requires an unknown_reason code"
        )
    return ExpectedTerminal(verdict, cast(TerminalReasonCode, reason_raw))


def record_from_dict(payload: dict[str, Any]) -> BenchmarkRecord:
    """Build one strict record, rejecting unknown fields and bad values."""
    if not isinstance(payload, dict):
        raise BenchmarkRecordError("record must be a JSON object")
    unknown = set(payload) - _REQUIRED_FIELDS - _OPTIONAL_FIELDS
    if unknown:
        raise BenchmarkRecordError(f"unknown record fields: {sorted(unknown)}")
    missing = _REQUIRED_FIELDS - set(payload)
    if missing:
        raise BenchmarkRecordError(f"missing record fields: {sorted(missing)}")

    record_id = payload["id"]
    if not isinstance(record_id, str) or not record_id.strip():
        raise BenchmarkRecordError("id must be a non-empty string")

    task_class_raw = payload["task_class"]
    if not isinstance(task_class_raw, str) or task_class_raw not in _TASK_CLASSES:
        raise BenchmarkRecordError(f"invalid task_class: {task_class_raw!r}")
    task_class: TaskClass = cast(TaskClass, task_class_raw)

    repo = payload["repo"]
    repo_commit = payload["repo_commit"]
    if not isinstance(repo, str) or not repo.strip():
        raise BenchmarkRecordError("repo must be a non-empty string")
    if not isinstance(repo_commit, str) or not re.fullmatch(
        r"[0-9a-fA-F]{40}", repo_commit
    ):
        raise BenchmarkRecordError("repo_commit must be a 40-char hex git sha")

    operation_raw = payload["operation"]
    if not isinstance(operation_raw, str) or operation_raw not in _OPERATIONS:
        raise BenchmarkRecordError(f"invalid operation: {operation_raw!r}")
    operation: Operation = cast(Operation, operation_raw)

    task = payload["task"]
    if not isinstance(task, str) or not task.strip():
        raise BenchmarkRecordError("task must not be empty")

    raw_paths = payload["allowed_paths"]
    if not isinstance(raw_paths, list) or not raw_paths:
        raise BenchmarkRecordError("allowed_paths must be a non-empty list")
    allowed_paths = tuple(_canonical_rel_path(p, "allowed_paths") for p in raw_paths)
    if len(set(allowed_paths)) != len(allowed_paths):
        raise BenchmarkRecordError("allowed_paths must not contain duplicates")

    oracle = payload["oracle"]
    oracle_reason = payload["oracle_baseline_reason"]
    for name, value in (
        ("oracle", oracle),
        ("oracle_baseline_reason", oracle_reason),
    ):
        if not isinstance(value, str) or not value.strip():
            raise BenchmarkRecordError(f"{name} must be a non-empty string")
    if not _REASON_TOKEN_RE.fullmatch(oracle_reason):
        raise BenchmarkRecordError(
            "oracle_baseline_reason must be a lowercase-kebab token"
        )

    raw_argv = payload["verification_argv"]
    if not isinstance(raw_argv, list) or not raw_argv:
        raise BenchmarkRecordError("verification_argv must be a non-empty list")
    if not all(isinstance(item, str) and item.strip() for item in raw_argv):
        raise BenchmarkRecordError(
            "verification_argv entries must be non-empty strings"
        )
    if any("\x00" in item for item in raw_argv):
        raise BenchmarkRecordError("verification_argv entries must not contain NUL")
    verification_argv = tuple(raw_argv)

    verification_hint = payload.get("verification_command")
    if verification_hint is not None and (
        not isinstance(verification_hint, str) or not verification_hint.strip()
    ):
        raise BenchmarkRecordError(
            "verification_command must be a non-empty string when present"
        )

    expected_terminal = _expected_terminal_from_dict(payload["expected_terminal"])

    defect = payload.get("defect")
    if defect is not None and not isinstance(defect, dict):
        raise BenchmarkRecordError("defect must be an object")

    patch = payload.get("patch")
    if patch is not None and not isinstance(patch, str):
        raise BenchmarkRecordError("patch must be a string")
    if isinstance(patch, str):
        try:
            patch.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise BenchmarkRecordError("patch must be valid UTF-8") from exc
        if not patch.strip():
            raise BenchmarkRecordError("patch must be a non-empty unified diff")
        lines = patch.split("\n")
        if not patch_has_changed_hunk(lines):
            raise BenchmarkRecordError("patch must be a non-empty unified diff")

    raw_selected = payload.get("selected_tests", [])
    if not isinstance(raw_selected, list) or not all(
        isinstance(item, str) for item in raw_selected
    ):
        raise BenchmarkRecordError("selected_tests must be a list of strings")
    selected_tests = tuple(
        _canonical_rel_path(item, "selected_tests") for item in raw_selected
    )
    if len(set(selected_tests)) != len(selected_tests):
        raise BenchmarkRecordError("selected_tests must not contain duplicates")
    if task_class != "test_selection" and selected_tests:
        raise BenchmarkRecordError("selected_tests require task_class test_selection")
    if (
        task_class != "test_selection"
        and expected_terminal.reason_code == "TEST_SELECTION_FAILED"
    ):
        raise BenchmarkRecordError(
            "TEST_SELECTION_FAILED requires task_class test_selection"
        )

    return BenchmarkRecord(
        id=record_id,
        task_class=task_class,
        repo=repo,
        repo_commit=repo_commit,
        operation=operation,
        task=task,
        allowed_paths=allowed_paths,
        oracle=oracle,
        oracle_baseline_reason=oracle_reason,
        verification_argv=verification_argv,
        expected_terminal=expected_terminal,
        verification_command=verification_hint,
        defect=defect,
        patch=patch,
        selected_tests=selected_tests,
    )


def _strict_json_loads(text: str) -> Any:
    """JSON decode that rejects duplicate keys and NaN/Infinity constants."""

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
    """Load a strict, bounded JSONL corpus from a file or stdin."""
    import sys

    if path == "-":
        binary_stdin = getattr(sys.stdin, "buffer", None)
        if binary_stdin is not None:
            raw_bytes = binary_stdin.read(_MAX_CORPUS_BYTES + 1)
        else:
            raw_bytes = sys.stdin.read(_MAX_CORPUS_BYTES + 1).encode("utf-8")
    else:
        from pathlib import Path

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
        except ValueError as exc:
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
    """Exact per-class counts for the report (RFC-0026 §1, C8)."""
    return {
        task_class: sum(1 for record in records if record.task_class == task_class)
        for task_class in ("bugfix", "refactor", "migration", "test_selection")
    }
