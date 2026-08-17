"""Strict benchmark-record model for the NO1-010B corpus (RFC-0026 §1).

The corpus is a pre-registered set of agent change tasks. Every record is
validated by a strict allowlist model: unknown fields, wrong types, invalid
enums, empty tasks, and non-canonical paths are rejected before a record can
reach the task layer. Only the `understand` / `plan_change` / `assess_change`
projection is forwarded to `task_harness.request_from_dict`, preserving the
`task/` import boundary.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

TaskClass = Literal["bugfix", "refactor", "migration", "test_selection"]
Operation = Literal["understand", "plan_change", "assess_change"]
ExpectedOutcome = Literal["PASS", "FAIL"]

_TASK_CLASSES = frozenset({"bugfix", "refactor", "migration", "test_selection"})
_OPERATIONS = frozenset({"understand", "plan_change", "assess_change"})
_EXPECTED_OUTCOMES = frozenset({"PASS", "FAIL"})
_MAX_CORPUS_BYTES = 8 * 1024 * 1024  # mirrors task_harness's input bound

# Canonical kebab-case token for the oracle baseline reason (RFC-0026 C43):
# the oracle's NO1_010B_ORACLE_REASON line must equal it exactly.
_REASON_TOKEN_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

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
        "expected_outcome",
    }
)
_OPTIONAL_FIELDS = frozenset(
    {"defect", "patch", "selected_tests", "verification_command"}
)


class BenchmarkRecordError(ValueError):
    """One malformed corpus record; the exact message names the offending field."""


@dataclass(frozen=True)
class BenchmarkRecord:
    """One pre-registered agent change task (RFC-0026 §1).

    ``allowed_paths`` are canonical, repository-relative POSIX paths: a
    directory entry ends with ``/`` and matches its descendants on
    path-segment boundaries; a file entry matches exactly. ``repo_commit``
    pins the fixture revision (RFC-0026 C15); ``expected_outcome`` is the
    pre-registered PASS/FAIL for the reference patch (RFC-0026 §5, non-vacuous
    B1 gate). ``verification_argv`` is the typed execution spec (no shell
    parsing, RFC-0026 C43); ``verification_command`` is a display-only hint.
    ``oracle_baseline_reason`` is a canonical kebab-case token the oracle's
    ``NO1_010B_ORACLE_REASON`` line must equal exactly (RFC-0026 C42/C43).
    ``patch`` and ``selected_tests`` exist only on fixture records.
    """

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
    expected_outcome: ExpectedOutcome
    verification_command: str | None = None
    defect: dict[str, Any] | None = None
    patch: str | None = None
    selected_tests: tuple[str, ...] = ()

    def to_task_request(self) -> tuple[str, dict[str, Any]]:
        """Project only the task-layer fields (RFC-0026 §1).

        ``assess_change`` needs a real diff at run time; the runner supplies
        it (the record carries no diff).
        """
        if self.operation == "understand":
            return "understand", {"task": self.task}
        if self.operation == "plan_change":
            return "plan_change", {"task": self.task}
        return "assess_change", {"diff": {"source": "workspace"}}


def _canonical_rel_path(raw: Any, field: str) -> str:
    """Normalize one allowed-path entry or reject it.

    Accepts repository-relative POSIX paths only: no leading ``/``, no
    ``./`` prefix, no ``..`` segments, no backslashes. Directory entries must
    end with ``/``.
    """
    if not isinstance(raw, str) or not raw:
        raise BenchmarkRecordError(f"{field}: path must be a non-empty string")
    value = raw.replace("\\", "/")
    if value.startswith("/") or value.startswith("./"):
        raise BenchmarkRecordError(f"{field}: path must be repository-relative")
    if value == ".." or value.startswith("../"):
        raise BenchmarkRecordError(f"{field}: '..' segments are not allowed")
    if "//" in value:
        raise BenchmarkRecordError(f"{field}: empty path segments are not allowed")
    if "/.." in value or value.endswith("/.."):
        raise BenchmarkRecordError(f"{field}: '..' segments are not allowed")
    return value


def path_allowed(rel_path: str, allowed_paths: tuple[str, ...]) -> bool:
    """Segment-aware allowlist check (RFC-0026 C6).

    A directory entry (``tests/``) matches its exact descendants on
    path-segment boundaries (``tests/test_dispatch.py`` yes,
    ``tests-escape/file.py`` no); a file entry matches exactly.
    """
    value = _canonical_rel_path(rel_path, "rel_path")
    for entry in allowed_paths:
        if entry.endswith("/"):
            prefix = entry
            if value.startswith(prefix) and len(value) > len(prefix):
                return True
        elif value == entry:
            return True
    return False


def record_from_dict(payload: dict[str, Any]) -> BenchmarkRecord:
    """Build one strict record, rejecting unknown fields and bad values.

    Mirrors ``task_harness._strict_json_loads``'s rejection discipline at the
    record level: schema typos fail loudly instead of silently passing.
    """
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

    task_class = payload["task_class"]
    if task_class not in _TASK_CLASSES:
        raise BenchmarkRecordError(f"invalid task_class: {task_class!r}")

    repo = payload["repo"]
    repo_commit = payload["repo_commit"]
    if not isinstance(repo, str) or not repo.strip():
        raise BenchmarkRecordError("repo must be a non-empty string")
    if not isinstance(repo_commit, str) or len(repo_commit) != 40:
        raise BenchmarkRecordError("repo_commit must be a 40-char git sha")

    operation = payload["operation"]
    if operation not in _OPERATIONS:
        raise BenchmarkRecordError(f"invalid operation: {operation!r}")

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
    verification_argv = tuple(raw_argv)

    verification_hint = payload.get("verification_command")
    if verification_hint is not None and (
        not isinstance(verification_hint, str) or not verification_hint.strip()
    ):
        raise BenchmarkRecordError(
            "verification_command must be a non-empty string when present"
        )

    expected = payload["expected_outcome"]
    if expected not in _EXPECTED_OUTCOMES:
        raise BenchmarkRecordError(f"invalid expected_outcome: {expected!r}")

    defect = payload.get("defect")
    if defect is not None and not isinstance(defect, dict):
        raise BenchmarkRecordError("defect must be an object")

    patch = payload.get("patch")
    if patch is not None and not isinstance(patch, str):
        raise BenchmarkRecordError("patch must be a string")

    raw_selected = payload.get("selected_tests", [])
    if not isinstance(raw_selected, list) or not all(
        isinstance(item, str) for item in raw_selected
    ):
        raise BenchmarkRecordError("selected_tests must be a list of strings")
    selected_tests = tuple(
        _canonical_rel_path(item, "selected_tests") for item in raw_selected
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
        expected_outcome=expected,
        verification_command=verification_hint,
        defect=defect,
        patch=patch,
        selected_tests=selected_tests,
    )


def load_corpus_records(path: str) -> list[BenchmarkRecord]:
    """Load a strict JSONL corpus (one record per line, bounded input).

    ``path == "-"`` reads stdin, mirroring ``task_harness.load_corpus``; the
    same 8 MiB input bound and strict-JSON discipline apply.
    """
    import sys

    if path == "-":
        raw = sys.stdin.read(_MAX_CORPUS_BYTES + 1)
        if len(raw) > _MAX_CORPUS_BYTES:
            raise BenchmarkRecordError("corpus exceeds the 8 MiB input bound")
        lines = raw.splitlines()
    else:
        from pathlib import Path

        size = Path(path).stat().st_size
        if size > _MAX_CORPUS_BYTES:
            raise BenchmarkRecordError("corpus exceeds the 8 MiB input bound")
        lines = Path(path).read_text(encoding="utf-8").splitlines()

    records: list[BenchmarkRecord] = []
    for index, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BenchmarkRecordError(
                f"corpus line {index}: invalid JSON: {exc}"
            ) from exc
        record = record_from_dict(payload)
        if record.id in {existing.id for existing in records}:
            raise BenchmarkRecordError(
                f"corpus line {index}: duplicate id {record.id!r}"
            )
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
