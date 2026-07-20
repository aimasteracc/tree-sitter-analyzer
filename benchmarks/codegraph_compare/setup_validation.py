"""Fail-closed, model-free setup validation for benchmark matrices.

This module intentionally validates only the runner's basic index-readiness
boundary. Manifest provenance, exact source partitions, and known-answer query
checks are separate RFC-0021 slices and can extend this boundary without
changing the rule that every selected indexed cell is checked first.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast


@dataclass(frozen=True)
class SetupFailure:
    """One repository/arm setup failure that blocks model-backed work."""

    repo_id: str
    arm_id: str
    index_mode: str
    code: str
    message: str
    question_id: str | None = None


@dataclass(frozen=True)
class SetupValidationResult:
    """Collected setup outcome plus prepared adapters for later execution."""

    failures: tuple[SetupFailure, ...]
    prepared_adapters: dict[tuple[str, str], Any]
    prepared_run_configs: dict[tuple[str, str, str], Any]

    @property
    def ok(self) -> bool:
        return not self.failures


@dataclass(frozen=True)
class _PreparedCell:
    repo_id: str
    arm_id: str
    index_mode: str
    repo_path: Path
    adapter: Any


def validate_matrix_setup(
    repo_entries: Sequence[dict],
    arm_entries: Sequence[dict],
    *,
    questions_by_repo: Mapping[str, Sequence[dict]],
    repo_path_resolver: Callable[[dict], Path],
    adapter_factory: Callable[[str], Any],
    backend_validator: Callable[[str], None] | None = None,
) -> SetupValidationResult:
    """Prepare every indexed repo/arm cell and collect all basic failures.

    Native/no-index arms skip index preparation but still validate their run
    configuration. Indexed arms must return a positive source-file count.
    """

    failures: list[SetupFailure] = []
    prepared_adapters: dict[tuple[str, str], Any] = {}
    prepared_run_configs: dict[tuple[str, str, str], Any] = {}

    for repo_entry in repo_entries:
        for arm_entry in arm_entries:
            cell, failure = _prepare_cell(
                repo_entry,
                arm_entry,
                repo_path_resolver=repo_path_resolver,
                adapter_factory=adapter_factory,
                backend_validator=backend_validator,
            )
            if failure is not None:
                failures.append(failure)
                continue
            cell = cast(_PreparedCell, cell)

            configs, config_failures = _build_run_configs(
                cell, questions_by_repo.get(cell.repo_id, ())
            )
            prepared_run_configs.update(configs)
            failures.extend(config_failures)
            if not config_failures:
                prepared_adapters[(cell.repo_id, cell.arm_id)] = cell.adapter

    return SetupValidationResult(
        tuple(failures), prepared_adapters, prepared_run_configs
    )


def _prepare_cell(
    repo_entry: dict,
    arm_entry: dict,
    *,
    repo_path_resolver: Callable[[dict], Path],
    adapter_factory: Callable[[str], Any],
    backend_validator: Callable[[str], None] | None,
) -> tuple[_PreparedCell | None, SetupFailure | None]:
    repo_id = str(repo_entry["id"])
    arm_id = str(arm_entry["id"])
    index_mode = str(arm_entry.get("index_mode", "warm"))
    if index_mode not in {"none", "warm", "cold"}:
        return None, _failure(
            repo_id, arm_id, index_mode, "INVALID_INDEX_MODE",
            f"unsupported index_mode: {index_mode}",
        )

    if backend_validator is not None:
        try:
            backend_validator(arm_id)
        except Exception as exc:  # noqa: BLE001 - persist unsupported combinations
            return None, _failure(
                repo_id,
                arm_id,
                index_mode,
                "BACKEND_UNSUPPORTED",
                str(exc),
            )

    try:
        repo_path = repo_path_resolver(repo_entry)
        adapter = adapter_factory(arm_id)
        stats = (
            adapter.prepare_index(repo_path, cold=index_mode == "cold")
            if index_mode != "none"
            else None
        )
    except Exception as exc:  # noqa: BLE001 - evidence must capture every arm
        return None, _failure(
            repo_id, arm_id, index_mode, "PREPARE_EXCEPTION", str(exc)
        )

    stats_failure = _validate_index_stats(repo_id, arm_id, index_mode, stats)
    if stats_failure is not None:
        return None, stats_failure
    return _PreparedCell(repo_id, arm_id, index_mode, repo_path, adapter), None


def _validate_index_stats(
    repo_id: str, arm_id: str, index_mode: str, stats: Any
) -> SetupFailure | None:
    if index_mode == "none":
        return None
    file_count = getattr(stats, "file_count", None)
    if isinstance(file_count, bool) or not isinstance(file_count, int):
        return _failure(
            repo_id,
            arm_id,
            index_mode,
            "INVALID_INDEX_STATS",
            "index preparation returned invalid file_count",
        )
    if file_count <= 0:
        return _failure(
            repo_id,
            arm_id,
            index_mode,
            "EMPTY_INDEX",
            "index preparation returned zero indexed files",
        )
    return None


def _build_run_configs(
    cell: _PreparedCell, question_entries: Sequence[dict]
) -> tuple[dict[tuple[str, str, str], Any], tuple[SetupFailure, ...]]:
    configs: dict[tuple[str, str, str], Any] = {}
    failures: list[SetupFailure] = []
    for question_entry in question_entries:
        question_id = str(question_entry["id"])
        try:
            config = cell.adapter.build_run_config(
                cell.repo_path, str(question_entry["prompt"])
            )
        except Exception as exc:  # noqa: BLE001 - collect later cells too
            failures.append(
                _failure(
                    cell.repo_id,
                    cell.arm_id,
                    cell.index_mode,
                    "RUN_CONFIG_EXCEPTION",
                    str(exc),
                    question_id=question_id,
                )
            )
            continue
        configs[(cell.repo_id, cell.arm_id, question_id)] = config
    return configs, tuple(failures)


def _failure(
    repo_id: str,
    arm_id: str,
    index_mode: str,
    code: str,
    message: str,
    *,
    question_id: str | None = None,
) -> SetupFailure:
    return SetupFailure(
        repo_id=repo_id,
        arm_id=arm_id,
        index_mode=index_mode,
        code=code,
        message=message,
        question_id=question_id,
    )


def write_setup_failure_evidence(
    results_dir: Path,
    *,
    session_id: str,
    result: SetupValidationResult,
) -> Path:
    """Persist session-scoped failure evidence without overwriting history."""

    if result.ok:
        raise ValueError("setup failure evidence requires at least one failure")

    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / f"setup_failures_{session_id}.json"
    payload = {
        "schema_version": 1,
        "session_id": session_id,
        "status": "setup_failed",
        "model_calls_started": 0,
        "failures": [
            {key: value for key, value in asdict(failure).items() if value is not None}
            for failure in result.failures
        ],
    }
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return path
