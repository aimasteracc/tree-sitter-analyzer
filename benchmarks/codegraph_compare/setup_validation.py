"""Fail-closed, model-free setup validation for benchmark matrices.

Legacy runs keep the basic index-readiness boundary. Manifest-bound setup-only
runs consume externally produced ``IndexStatsV1`` evidence and validate its
provenance, source partition, and declared readiness-oracle results. Producing
that evidence and executing known-answer queries remain a separate stage; this
module does not treat oracle names as proof by itself.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, cast

from benchmarks.codegraph_compare.integrity import (
    ExperimentManifestV1,
    _sha256,
    validate_setup_index_stats,
)
from benchmarks.codegraph_compare.schemas import IndexStatsV1


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
    prepared_index_stats: dict[tuple[str, str], IndexStatsV1]

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


def selected_matrix_config_hash(
    repo_entries: Sequence[dict],
    arm_entries: Sequence[dict],
) -> str:
    """Hash the selected, machine-independent repo and arm configuration."""

    repos = [
        {key: value for key, value in entry.items() if key != "local_path"}
        for entry in repo_entries
    ]
    return _sha256(
        {
            "repos": sorted(repos, key=lambda entry: str(entry.get("id", ""))),
            "arms": sorted(
                (dict(entry) for entry in arm_entries),
                key=lambda entry: str(entry.get("id", "")),
            ),
        }
    )


def selected_questions_hash(
    questions_by_repo: Mapping[str, Sequence[dict]],
) -> str:
    """Hash every selected question and its repository binding."""

    questions = [
        {"repo_id": repo_id, "question": dict(question)}
        for repo_id, entries in questions_by_repo.items()
        for question in entries
    ]
    return _sha256(
        sorted(
            questions,
            key=lambda item: (
                str(item["repo_id"]),
                str(item["question"].get("id", "")),
            ),
        )
    )


def validate_matrix_setup(
    repo_entries: Sequence[dict],
    arm_entries: Sequence[dict],
    *,
    questions_by_repo: Mapping[str, Sequence[dict]],
    repo_path_resolver: Callable[[dict], Path],
    adapter_factory: Callable[[str], Any],
    backend_validator: Callable[[str], None] | None = None,
    manifest: ExperimentManifestV1 | None = None,
    repeats: int = 1,
    agent_backend: str = "",
    model: str | None = None,
    supplied_index_stats: Mapping[tuple[str, str], IndexStatsV1] | None = None,
) -> SetupValidationResult:
    """Prepare every indexed repo/arm cell and collect all basic failures.

    Native/no-index arms skip index preparation but still validate their run
    configuration. Indexed arms must return a positive source-file count.
    """

    failures: list[SetupFailure] = []
    prepared_adapters: dict[tuple[str, str], Any] = {}
    prepared_run_configs: dict[tuple[str, str, str], Any] = {}

    if manifest is not None:
        mismatch = _validate_manifest_matrix(
            repo_entries,
            arm_entries,
            questions_by_repo,
            repeats=repeats,
            agent_backend=agent_backend,
            model=model,
            manifest=manifest,
        )
        if mismatch is not None:
            return SetupValidationResult((mismatch,), {}, {}, {})
        backend_failures = _validate_manifest_backend_arms(
            arm_entries,
            backend_validator=backend_validator,
        )
        if backend_failures:
            return SetupValidationResult(backend_failures, {}, {}, {})
        config_failure = _validate_manifest_config_hashes(
            repo_entries,
            arm_entries,
            questions_by_repo,
            manifest=manifest,
        )
        if config_failure is not None:
            return SetupValidationResult((config_failure,), {}, {}, {})
        return _validate_supplied_index_stats(
            repo_entries,
            arm_entries,
            manifest=manifest,
            supplied_index_stats=supplied_index_stats,
        )

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
        tuple(failures),
        prepared_adapters,
        prepared_run_configs,
        {},
    )


def _validate_manifest_backend_arms(
    arm_entries: Sequence[dict],
    *,
    backend_validator: Callable[[str], None] | None,
) -> tuple[SetupFailure, ...]:
    if backend_validator is None:
        return ()
    failures: list[SetupFailure] = []
    for arm in arm_entries:
        arm_id = str(arm["id"])
        try:
            backend_validator(arm_id)
        except Exception as exc:  # noqa: BLE001 - persist every unsupported arm
            failures.append(
                _failure(
                    "*",
                    arm_id,
                    str(arm.get("index_mode", "none")),
                    "BACKEND_UNSUPPORTED",
                    str(exc),
                )
            )
    return tuple(failures)


def _validate_manifest_config_hashes(
    repo_entries: Sequence[dict],
    arm_entries: Sequence[dict],
    questions_by_repo: Mapping[str, Sequence[dict]],
    *,
    manifest: ExperimentManifestV1,
) -> SetupFailure | None:
    if selected_matrix_config_hash(repo_entries, arm_entries) != manifest.config_hash:
        return _failure(
            "*",
            "*",
            "none",
            "MATRIX_CONFIG_HASH_MISMATCH",
            "selected repository or arm configuration does not match config_hash",
        )
    if selected_questions_hash(questions_by_repo) != manifest.question_hash:
        return _failure(
            "*",
            "*",
            "none",
            "MATRIX_QUESTION_HASH_MISMATCH",
            "selected question configuration does not match question_hash",
        )
    return None


def _validate_manifest_matrix(
    repo_entries: Sequence[dict],
    arm_entries: Sequence[dict],
    questions_by_repo: Mapping[str, Sequence[dict]],
    *,
    repeats: int,
    agent_backend: str,
    model: str | None,
    manifest: ExperimentManifestV1,
) -> SetupFailure | None:
    actual_cells = [
        (
            str(repo["id"]),
            str(question["id"]),
            str(arm["id"]),
            repeat,
            agent_backend,
            f"{question['id']}__{arm['id']}__{agent_backend}__{repeat:02d}",
        )
        for repo in repo_entries
        for arm in arm_entries
        for question in questions_by_repo.get(str(repo["id"]), ())
        for repeat in range(repeats)
    ]
    expected_cells = [
        (
            cell.repo,
            cell.question_id,
            cell.arm,
            cell.repeat,
            cell.agent_backend,
            cell.run_id,
        )
        for cell in manifest.expected_cells
    ]
    selected_repo_ids = [str(repo["id"]) for repo in repo_entries]
    selected_arm_ids = [str(arm["id"]) for arm in arm_entries]
    expected_repo_ids = {cell.repo for cell in manifest.expected_cells}
    expected_arm_ids = set(manifest.required_arms)
    selections_match = (
        len(selected_repo_ids) == len(set(selected_repo_ids))
        and set(selected_repo_ids) == expected_repo_ids
        and len(selected_arm_ids) == len(set(selected_arm_ids))
        and set(selected_arm_ids) == expected_arm_ids
    )
    model_matches = model == manifest.model
    if (
        selections_match
        and Counter(actual_cells) == Counter(expected_cells)
        and model_matches
    ):
        return None
    return _failure(
        "*",
        "*",
        "none",
        "MATRIX_MANIFEST_MISMATCH",
        "selected repos, arms, questions, repeats, backend, or model "
        "do not exactly match the experiment manifest",
    )


def _validate_supplied_index_stats(
    repo_entries: Sequence[dict],
    arm_entries: Sequence[dict],
    *,
    manifest: ExperimentManifestV1,
    supplied_index_stats: Mapping[tuple[str, str], IndexStatsV1] | None,
) -> SetupValidationResult:
    expected = {
        (str(repo["id"]), str(arm["id"]))
        for repo in repo_entries
        for arm in arm_entries
        if str(arm["id"]) in manifest.indexed_arms
    }
    if supplied_index_stats is None or set(supplied_index_stats) != expected:
        failure = _failure(
            "*",
            "*",
            "none",
            "INDEX_EVIDENCE_SET_MISMATCH",
            "V1 index evidence must exactly cover every selected indexed repo/arm cell",
        )
        return SetupValidationResult((failure,), {}, {}, {})

    failures: list[SetupFailure] = []
    prepared: dict[tuple[str, str], IndexStatsV1] = {}
    for (repo_id, arm_id), stats in sorted(supplied_index_stats.items()):
        code = validate_setup_index_stats(stats, manifest, repo_id, arm_id)
        if code is None:
            prepared[(repo_id, arm_id)] = stats
        else:
            failures.append(
                _failure(
                    repo_id,
                    arm_id,
                    "evidence",
                    code,
                    "strict index evidence does not satisfy the experiment manifest",
                )
            )
    return SetupValidationResult(tuple(failures), {}, {}, prepared)


def parse_index_evidence_v1(raw: object) -> dict[tuple[str, str], IndexStatsV1]:
    """Parse a strict, duplicate-free V1 index-evidence document."""

    if not isinstance(raw, dict) or set(raw) != {"schema_version", "cells"}:
        raise ValueError("Index evidence must contain only schema_version and cells")
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise ValueError("Index evidence schema_version must be the integer 1")
    if not isinstance(raw["cells"], list):
        raise ValueError("Index evidence cells must be a list")
    stats_fields = {field.name for field in fields(IndexStatsV1)}
    tuple_fields = {
        "indexed_paths",
        "excluded_paths",
        "parse_error_paths",
        "readiness_oracles",
    }
    integer_fields = {
        "eligible_source_files",
        "indexed_source_files",
        "excluded_source_files",
        "parse_error_files",
        "index_size_bytes",
    }
    string_fields = {
        "eligible_paths_hash",
        "indexed_paths_hash",
        "excluded_paths_hash",
        "parse_error_paths_hash",
        "repo_fingerprint",
        "tool_fingerprint",
    }
    parsed: dict[tuple[str, str], IndexStatsV1] = {}
    for cell in raw["cells"]:
        if not isinstance(cell, dict) or set(cell) != {
            "repo_id",
            "arm_id",
            "index_stats",
        }:
            raise ValueError(
                "Each evidence cell must contain repo_id, arm_id, index_stats"
            )
        stats_raw = cell["index_stats"]
        if not isinstance(stats_raw, dict) or set(stats_raw) != stats_fields:
            raise ValueError("Index evidence fields do not match IndexStatsV1")
        if any(type(stats_raw[field]) is not int for field in integer_fields):
            raise ValueError("Index evidence count and size fields must be integers")
        build_seconds = stats_raw["build_seconds"]
        if type(build_seconds) not in {int, float}:
            raise ValueError("Index evidence build_seconds must be a finite number")
        try:
            build_seconds_is_finite = math.isfinite(build_seconds)
        except OverflowError:
            build_seconds_is_finite = False
        if not build_seconds_is_finite:
            raise ValueError("Index evidence build_seconds must be a finite number")
        if any(not isinstance(stats_raw[field], str) for field in string_fields):
            raise ValueError("Index evidence provenance fields must be strings")
        if any(
            not isinstance(stats_raw[field], list)
            or any(not isinstance(item, str) for item in stats_raw[field])
            for field in tuple_fields
        ):
            raise ValueError(
                "Index evidence path and oracle fields must be string lists"
            )
        repo_id = cell["repo_id"]
        arm_id = cell["arm_id"]
        if (
            not isinstance(repo_id, str)
            or not repo_id
            or not isinstance(arm_id, str)
            or not arm_id
        ):
            raise ValueError("Index evidence repo_id and arm_id must be strings")
        normalized = {
            key: tuple(value) if key in tuple_fields else value
            for key, value in stats_raw.items()
        }
        key = (repo_id, arm_id)
        if key in parsed:
            raise ValueError(f"Duplicate index evidence cell: {key[0]}/{key[1]}")
        parsed[key] = IndexStatsV1(**cast(Any, normalized))
    return parsed


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
            repo_id,
            arm_id,
            index_mode,
            "INVALID_INDEX_MODE",
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


def write_manifest_setup_evidence(
    results_dir: Path,
    *,
    session_id: str,
    manifest: ExperimentManifestV1,
    result: SetupValidationResult,
) -> Path:
    """Persist immutable, experiment-scoped strict setup evidence."""

    experiment_dir = results_dir / "experiments" / manifest.manifest_hash
    experiment_dir.mkdir(parents=True, exist_ok=True)
    path = experiment_dir / f"setup_{session_id}.json"
    cells = [
        {
            "repo_id": repo_id,
            "arm_id": arm_id,
            "index_stats": asdict(stats),
        }
        for (repo_id, arm_id), stats in sorted(result.prepared_index_stats.items())
    ]
    payload = {
        "schema_version": 1,
        "experiment_id": manifest.experiment_id,
        "manifest_hash": manifest.manifest_hash,
        "session_id": session_id,
        "status": "setup_passed" if result.ok else "setup_failed",
        "validation_level": "manifest-bound-v1-consumer",
        "publishable": False,
        "model_calls_started": 0,
        "cells": cells,
        "failures": [
            {key: value for key, value in asdict(failure).items() if value is not None}
            for failure in result.failures
        ],
    }
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return path
