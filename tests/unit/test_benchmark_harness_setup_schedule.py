"""Issue #1376：test_benchmark_harness_setup_schedule 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.codegraph_compare import run as compare_run
from tests.unit._benchmark_harness_matrix_helpers import (
    TestCodeGraphCompareSetupGate as _TestCodeGraphCompareSetupGate,
)


class TestCodeGraphCompareSetupGate(_TestCodeGraphCompareSetupGate):
    """模型驱动的矩阵执行必须受 setup 验证保护，失败时保持关闭。"""

    def test_manifest_bound_execution_persists_v1_attempts_in_frozen_order(
        self, monkeypatch, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.adapters import RunConfig

        manifest = self._v1_setup_manifest(agent_backend="codex")
        manifest_path = self._write_v1_manifest(tmp_path, manifest)
        evidence_input = self._write_v1_index_evidence(tmp_path, manifest)
        observed: list[str] = []

        class Adapter:
            def __init__(self, arm_id: str) -> None:
                self.arm_id = arm_id

            def build_run_config(self, repo_path: Path, prompt: str) -> RunConfig:
                return RunConfig(self.arm_id, repo_path, "system")

        def run_one(**kwargs):
            run_id = (
                f"{kwargs['question_id']}__{kwargs['arm_id']}__"
                f"{kwargs['agent_backend']}__{kwargs['repeat']:02d}"
            )
            observed.append(run_id)
            transcript = tmp_path / f"{run_id}.jsonl"
            server = (
                "codegraph"
                if kwargs["arm_id"] == "codegraph-warm"
                else "tree-sitter-analyzer"
            )
            transcript.write_text(
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "mcp_tool_call",
                            "server": server,
                            "tool": "search",
                        },
                    }
                ),
                encoding="utf-8",
            )
            return {
                "run_id": run_id,
                "session_id": kwargs["session_id"],
                "repo": "gin",
                "question_id": kwargs["question_id"],
                "arm": kwargs["arm_id"],
                "repeat": kwargs["repeat"],
                "agent_backend": kwargs["agent_backend"],
                "model": kwargs["model"],
                "started_at": "2026-07-31T00:00:00Z",
                "ended_at": "2026-07-31T00:00:01Z",
                "elapsed_seconds": 1.0,
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
                "estimated_cost_usd": 0.0,
                "total_cost_usd": 0.0,
                "tool_calls": 1,
                "file_reads": 0,
                "search_calls": 0,
                "index_queries": 1,
                "answer": "answer",
                "citations": ["gin.go"],
                "transcript_path": str(transcript),
                "error": None,
            }

        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        self._install_runner_modules(monkeypatch, Adapter, run_one)
        args = self._matrix_args()
        args.agent_backend = manifest.agent_backend
        args.manifest = str(manifest_path)
        args.index_evidence = evidence_input

        assert compare_run.cmd_run_matrix(args) == 0
        assert observed == [cell.run_id for cell in manifest.expected_cells]
        attempts_path = (
            tmp_path / "results" / "experiments" / manifest.manifest_hash / "runs.jsonl"
        )
        attempts = [
            json.loads(line)
            for line in attempts_path.read_text(encoding="utf-8").splitlines()
        ]
        assert [attempt["run_id"] for attempt in attempts] == observed
        assert [attempt["status"] for attempt in attempts] == [
            "SUCCESS",
            "SUCCESS",
        ]

    def test_matrix_rejects_zero_repeats_instead_of_defaulting_to_one(
        self, monkeypatch, tmp_path: Path, capsys
    ):
        manifest = self._v1_setup_manifest()
        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        args = self._matrix_args()
        args.agent_backend = manifest.agent_backend
        args.repeats = 0
        args.manifest = self._write_v1_manifest(tmp_path, manifest)
        args.setup_only = True
        args.index_evidence = self._write_v1_index_evidence(tmp_path, manifest)

        with pytest.raises(SystemExit) as exc_info:
            compare_run.cmd_run_matrix(args)

        assert exc_info.value.code == 1
        assert "--repeats must be greater than zero" in capsys.readouterr().err
        registry_events = [
            json.loads(line)
            for line in (tmp_path / "results" / "experiment_registry.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        assert [event["outcome"] for event in registry_events] == [
            "setup_started",
            "setup_input_failed",
        ]

    def test_setup_only_accepts_pre_registered_interleaved_schedule(
        self, monkeypatch, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.setup_validation import (
            selected_schedule_hash,
        )

        repos, arms, questions = self._v1_matrix_configs(Path("/runtime-path"))
        backend = "claude"
        interleaved_arms = list(reversed(arms))
        manifest = self._v1_setup_manifest(
            expected_run_ids=tuple(
                f"q1__{arm['id']}__{backend}__00" for arm in interleaved_arms
            ),
            schedule_hash=selected_schedule_hash(
                repos,
                interleaved_arms,
                {"gin": questions},
                repeats=1,
                agent_backend=backend,
            ),
        )
        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        args = self._matrix_args()
        args.agent_backend = manifest.agent_backend
        args.manifest = self._write_v1_manifest(tmp_path, manifest)
        args.setup_only = True
        args.index_evidence = self._write_v1_index_evidence(tmp_path, manifest)

        assert compare_run.cmd_run_matrix(args) == 0

    def test_setup_only_rejects_schedule_hash_not_bound_to_manifest_cells(
        self, monkeypatch, tmp_path: Path
    ):
        manifest = self._v1_setup_manifest(schedule_hash="wrong-schedule")
        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        args = self._matrix_args()
        args.agent_backend = manifest.agent_backend
        args.manifest = self._write_v1_manifest(tmp_path, manifest)
        args.setup_only = True
        args.index_evidence = self._write_v1_index_evidence(tmp_path, manifest)

        assert compare_run.cmd_run_matrix(args) == 1

        evidence_path = next(
            (tmp_path / "results" / "experiments" / manifest.manifest_hash).glob(
                "setup_*.json"
            )
        )
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert [failure["code"] for failure in evidence["failures"]] == [
            "MATRIX_SCHEDULE_HASH_MISMATCH"
        ]
