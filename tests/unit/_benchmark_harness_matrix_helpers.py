"""Issue #1376：_matrix_helpers 行为组，原测试 AST 保持不变。"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.codegraph_compare import run as compare_run


def _v1_paths_hash(paths: tuple[str, ...]) -> str:
    payload = json.dumps(
        list(paths), ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _v1_manifest(**overrides):
    from benchmarks.codegraph_compare.integrity import ExpectedCellV1, create_manifest

    values = {
        "benchmark_git_sha": "abc123",
        "config_hash": "cfg123",
        "question_hash": "questions123",
        "oracle_hash": "oracles123",
        "seed": 210021,
        "timeout_seconds": 300,
        "schedule_hash": "schedule123",
        "agent_backend": "codex",
        "model": "gpt-5",
        "agent_cli_fingerprint": "codex-cli-1",
        "platform": "windows-x64",
        "environment_fingerprint": "env123",
        "primary_session_id": "PRIMARY",
        "retry_session_ids": (),
        "expected_run_ids": (
            "q1__codegraph-warm__codex__00",
            "q1__tsa-warm__codex__00",
        ),
        "required_arms": ("codegraph-warm", "tsa-warm"),
        "indexed_arms": ("codegraph-warm", "tsa-warm"),
        "tool_fingerprints": {"codegraph-warm": "cg141", "tsa-warm": "tsa130"},
        "repo_commits": {"gin": "repo123"},
        "repo_fingerprints": {"gin": "repo-fingerprint"},
        "eligible_paths": {"gin": tuple(f"src/file_{index}.py" for index in range(10))},
        "parse_error_allowlists": {"gin": ()},
        "required_readiness_oracles": {
            "codegraph-warm": ("known-symbol",),
            "tsa-warm": ("known-symbol",),
        },
    }
    values.update(overrides)
    if "eligible_paths_hashes" not in overrides:
        values["eligible_paths_hashes"] = {
            repo: _v1_paths_hash(paths)
            for repo, paths in values["eligible_paths"].items()
        }
    if "indexed_arms" not in overrides:
        values["indexed_arms"] = tuple(
            arm for arm in values["required_arms"] if arm != "native-only"
        )
    if "required_readiness_oracles" not in overrides:
        values["required_readiness_oracles"] = dict.fromkeys(
            values["indexed_arms"], ("known-symbol",)
        )
    run_ids = values.pop("expected_run_ids")
    values["expected_cells"] = tuple(
        ExpectedCellV1(
            repo="gin",
            question_id=run_id.rsplit("__", 3)[0],
            arm=run_id.rsplit("__", 3)[1],
            agent_backend=run_id.rsplit("__", 3)[2],
            repeat=int(run_id.rsplit("__", 3)[3]),
            run_id=run_id,
        )
        for run_id in run_ids
    )
    return create_manifest(**values)


def _registry_for(manifest):
    from benchmarks.codegraph_compare.integrity import RegistryEvent

    return (
        RegistryEvent(
            manifest.experiment_id,
            manifest.manifest_hash,
            "COMPLETE",
            "producer_completed",
        ),
    )


def _v1_run(manifest, run_id: str, **overrides):
    from benchmarks.codegraph_compare.schemas import (
        BenchmarkStatus,
        IndexStatsV1,
        RunRecordV1,
    )

    arm = run_id.rsplit("__", 3)[1]
    eligible_paths = dict(manifest.eligible_paths)["gin"]
    empty_paths: tuple[str, ...] = ()
    tool_fingerprint = {
        "codegraph-warm": "cg141",
        "tsa-warm": "tsa130",
        "native-only": "native1",
    }[arm]
    values = {
        "benchmark_version": 1,
        "experiment_id": manifest.experiment_id,
        "session_id": "PRIMARY",
        "run_id": run_id,
        "attempt_no": 0,
        "retry_of": None,
        "status": BenchmarkStatus.SUCCESS,
        "repo": "gin",
        "question_id": "q1",
        "arm": arm,
        "repeat": 0,
        "agent_backend": "codex",
        "model": "gpt-5",
        "config_hash": "cfg123",
        "question_hash": "questions123",
        "oracle_hash": "oracles123",
        "tool_fingerprint": tool_fingerprint,
        "repo_commit": "repo123",
        "benchmark_git_sha": "abc123",
        "agent_cli_fingerprint": "codex-cli-1",
        "platform": "windows-x64",
        "environment_fingerprint": "env123",
        "blocker_reason": None,
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
        "total_cost_usd": 0.01,
        "tool_calls": 1,
        "answer": "answer",
        "index_stats": IndexStatsV1(
            eligible_source_files=len(eligible_paths),
            indexed_source_files=len(eligible_paths),
            excluded_source_files=0,
            parse_error_files=0,
            eligible_paths_hash=_v1_paths_hash(eligible_paths),
            indexed_paths_hash=_v1_paths_hash(eligible_paths),
            excluded_paths_hash=_v1_paths_hash(empty_paths),
            parse_error_paths_hash=_v1_paths_hash(empty_paths),
            indexed_paths=eligible_paths,
            excluded_paths=empty_paths,
            parse_error_paths=empty_paths,
            build_seconds=1.0,
            index_size_bytes=100,
            repo_fingerprint="repo-fingerprint",
            tool_fingerprint=tool_fingerprint,
            readiness_oracles=("known-symbol",),
        ),
    }
    values.update(overrides)
    return RunRecordV1(**values)


def _v1_eval(run):
    from benchmarks.codegraph_compare.schemas import EvalRecordV1

    return EvalRecordV1(
        benchmark_version=1,
        experiment_id=run.experiment_id,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_no=run.attempt_no,
        correctness=5,
        completeness=5,
        citation_location_validity=1.0,
        claim_support=5,
        overall=5.0,
        evaluator_model="judge-v1",
    )


class TestCodeGraphCompareSetupGate:
    """Model-backed matrix work must be fail-closed behind setup validation."""

    @staticmethod
    def _matrix_args() -> SimpleNamespace:
        return SimpleNamespace(
            repos="all",
            arms="all",
            repeats=1,
            question_limit=None,
            dry_run=False,
            agent_backend="codex",
            model="gpt-5",
            timeout_seconds=1200,
            manifest=None,
            setup_only=False,
            index_evidence=None,
        )

    @staticmethod
    def _matrix_configs(repo_path: Path) -> tuple[list[dict], list[dict], list[dict]]:
        repos = [{"id": "demo", "local_path": str(repo_path)}]
        arms = [
            {"id": "native-only", "index_mode": "none"},
            {"id": "codegraph-warm", "index_mode": "warm"},
            {"id": "tsa-warm", "index_mode": "warm"},
        ]
        questions = [
            {
                "id": "demo-q1",
                "repo": "demo",
                "prompt": "Where is the entry point?",
            }
        ]
        return repos, arms, questions

    @staticmethod
    def _install_runner_modules(
        monkeypatch, get_adapter, run_one, validate_backend=None
    ) -> None:
        from types import ModuleType

        adapters_module = ModuleType("adapters")
        adapters_module.get_adapter = get_adapter
        runner_module = ModuleType("adapters.claude_runner")
        runner_module.run_one = run_one
        runner_module.validate_backend_arm_support = validate_backend or (
            lambda agent_backend, arm_id: None
        )
        monkeypatch.setitem(sys.modules, "adapters", adapters_module)
        monkeypatch.setitem(sys.modules, "adapters.claude_runner", runner_module)

    @staticmethod
    def _patch_matrix_inputs(monkeypatch, tmp_path: Path) -> None:
        repos, arms, questions = TestCodeGraphCompareSetupGate._matrix_configs(tmp_path)
        configs = {
            compare_run.REPOS_YAML: repos,
            compare_run.ARMS_YAML: arms,
            compare_run.QUESTIONS_YAML: questions,
        }
        monkeypatch.setattr(compare_run, "_load_yaml", configs.__getitem__)
        monkeypatch.setattr(
            compare_run, "_repo_local_path", lambda repo: Path(repo["local_path"])
        )
        monkeypatch.setattr(compare_run, "RESULTS_DIR", tmp_path / "results")

    @staticmethod
    def _patch_v1_matrix_inputs(monkeypatch, tmp_path: Path) -> None:
        repos, arms, questions = TestCodeGraphCompareSetupGate._v1_matrix_configs(
            tmp_path
        )
        configs = {
            compare_run.REPOS_YAML: repos,
            compare_run.ARMS_YAML: arms,
            compare_run.QUESTIONS_YAML: questions,
        }
        monkeypatch.setattr(compare_run, "_load_yaml", configs.__getitem__)
        monkeypatch.setattr(
            compare_run, "_repo_local_path", lambda repo: Path(repo["local_path"])
        )
        monkeypatch.setattr(compare_run, "RESULTS_DIR", tmp_path / "results")

    @staticmethod
    def _v1_matrix_configs(
        repo_path: Path,
    ) -> tuple[list[dict], list[dict], list[dict]]:
        return (
            [{"id": "gin", "local_path": str(repo_path), "commit": "repo123"}],
            [
                {"id": "codegraph-warm", "index_mode": "warm"},
                {"id": "tsa-warm", "index_mode": "warm"},
            ],
            [
                {
                    "id": "q1",
                    "repo": "gin",
                    "prompt": "Where is the entry point?",
                }
            ],
        )

    @classmethod
    def _v1_setup_manifest(cls, *, agent_backend: str = "claude", **overrides):
        from benchmarks.codegraph_compare.setup_validation import (
            selected_matrix_config_hash,
            selected_questions_hash,
            selected_schedule_hash,
        )

        repos, arms, questions = cls._v1_matrix_configs(Path("/runtime-path"))
        questions_by_repo = {"gin": questions}
        values = {
            "agent_backend": agent_backend,
            "expected_run_ids": tuple(
                f"q1__{arm['id']}__{agent_backend}__00" for arm in arms
            ),
            "config_hash": selected_matrix_config_hash(repos, arms),
            "question_hash": selected_questions_hash(questions_by_repo),
            "schedule_hash": selected_schedule_hash(
                repos,
                arms,
                questions_by_repo,
                repeats=1,
                agent_backend=agent_backend,
            ),
            "timeout_seconds": 1200,
        }
        values.update(overrides)
        return _v1_manifest(
            **values,
        )

    @staticmethod
    def _write_v1_manifest(tmp_path: Path, manifest) -> Path:
        from dataclasses import asdict

        path = tmp_path / "experiment_manifest.json"
        path.write_text(json.dumps(asdict(manifest)), encoding="utf-8")
        return path

    @staticmethod
    def _write_v1_index_evidence(tmp_path: Path, manifest, *, readiness=True) -> Path:
        from dataclasses import asdict, replace

        cells = []
        for arm_id in ("codegraph-warm", "tsa-warm"):
            record = _v1_run(
                manifest,
                f"q1__{arm_id}__{manifest.agent_backend}__00",
            )
            stats = record.index_stats
            if stats is None:
                pytest.fail(f"{arm_id} fixture must include V1 index statistics")
            if not readiness and arm_id == "tsa-warm":
                stats = replace(stats, readiness_oracles=("unexpected-symbol",))
            cells.append(
                {"repo_id": "gin", "arm_id": arm_id, "index_stats": asdict(stats)}
            )
        path = tmp_path / "index_evidence.json"
        path.write_text(
            json.dumps({"schema_version": 1, "cells": cells}), encoding="utf-8"
        )
        return path

    @staticmethod
    def _v1_index_stats_payload(manifest) -> dict:
        from dataclasses import asdict

        stats = _v1_run(
            manifest,
            "q1__codegraph-warm__codex__00",
        ).index_stats
        if stats is None:
            pytest.fail("codegraph fixture must include V1 index statistics")
        return json.loads(json.dumps(asdict(stats)))

    @classmethod
    def _parse_v1_index_evidence(
        cls,
        *,
        cell_overrides: dict | None = None,
        stats_overrides: dict | None = None,
    ):
        from benchmarks.codegraph_compare.setup_validation import (
            parse_index_evidence_v1,
        )

        stats_raw = cls._v1_index_stats_payload(_v1_manifest())
        stats_raw.update(stats_overrides or {})
        cell = {
            "repo_id": "gin",
            "arm_id": "codegraph-warm",
            "index_stats": stats_raw,
        }
        cell.update(cell_overrides or {})
        return parse_index_evidence_v1({"schema_version": 1, "cells": [cell]})
