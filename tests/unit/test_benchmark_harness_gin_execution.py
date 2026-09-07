"""Issue #1376：test_benchmark_harness_gin_execution 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.unit._benchmark_harness_matrix_helpers import _v1_manifest, _v1_run
from tests.unit._benchmark_harness_smoke_helpers import (
    TestGinSmokeManifestExecution as _TestGinSmokeManifestExecution,
)


class TestGinSmokeManifestExecution(_TestGinSmokeManifestExecution):
    def test_v1_attempt_is_manifest_bound_and_append_only(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_execution import (
            PolicyAudit,
            append_v1_attempt,
            build_v1_attempt,
        )

        manifest = _v1_manifest()
        cell = manifest.expected_cells[0]
        legacy = self._legacy_record(manifest, cell.run_id, tmp_path / "raw.jsonl")
        stats = _v1_run(manifest, cell.run_id).index_stats
        audit = PolicyAudit(
            cell.arm,
            legacy["transcript_path"],
            ("codegraph",),
            ("codegraph_search",),
            (),
        )

        attempt = build_v1_attempt(
            manifest,
            cell,
            legacy,
            index_stats=stats,
            policy_audit=audit,
        )
        path = append_v1_attempt(tmp_path, manifest, attempt, audit)

        persisted = json.loads(path.read_text(encoding="utf-8"))
        assert persisted["experiment_id"] == manifest.experiment_id
        assert persisted["session_id"] == manifest.primary_session_id
        assert persisted["run_id"] == cell.run_id
        assert persisted["status"] == "SUCCESS"
        path.unlink()
        recovered = append_v1_attempt(tmp_path, manifest, attempt, audit)
        assert (
            json.loads(recovered.read_text(encoding="utf-8"))["run_id"] == cell.run_id
        )
        with pytest.raises(ValueError, match="Duplicate physical attempt"):
            append_v1_attempt(tmp_path, manifest, attempt, audit)

    def test_failed_manifest_smoke_records_supported_invalid_registry_status(
        self, monkeypatch, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.smoke_execution import (
            execute_bound_manifest,
        )

        manifest = _v1_manifest()
        events: list[tuple[str, str]] = []
        monkeypatch.setattr(
            "benchmarks.codegraph_compare.smoke_execution.run_manifest_setup_gate",
            lambda **kwargs: 0,
        )
        monkeypatch.setattr(
            "benchmarks.codegraph_compare.smoke_execution.run_manifest_smoke",
            lambda **kwargs: 1,
        )

        result = execute_bound_manifest(
            manifest=manifest,
            args=SimpleNamespace(),
            supplied_index_stats={},
            workspace=None,
            repo_entries=[],
            arm_entries=[],
            question_entries_by_repo={},
            repeats=1,
            session_id=manifest.primary_session_id,
            results_dir=tmp_path,
            repo_path_resolver=lambda repo: tmp_path,
            append_event=lambda _, status, outcome: events.append((status, outcome)),
            adapter_factory=lambda arm: None,
            run_one=lambda **kwargs: None,
        )

        assert result == 1
        assert events == [
            ("RUNNING", "smoke_started"),
            ("INVALID", "smoke_invalid"),
        ]

    def test_manifest_smoke_retains_exception_and_continues_schedule(
        self, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.adapters import RunConfig
        from benchmarks.codegraph_compare.smoke_execution import (
            run_manifest_smoke,
        )

        manifest = _v1_manifest()
        calls = 0

        class Adapter:
            def __init__(self, arm: str) -> None:
                self.arm = arm

            def build_run_config(self, repo_path: Path, prompt: str) -> RunConfig:
                return RunConfig(self.arm, repo_path, "system")

        def run_one(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("backend crashed")
            cell = manifest.expected_cells[1]
            transcript = tmp_path / "second.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "mcp_tool_call",
                            "server": "tree-sitter-analyzer",
                            "tool": "nav",
                        },
                    }
                ),
                encoding="utf-8",
            )
            return self._legacy_record(manifest, cell.run_id, transcript)

        stats = {
            ("gin", cell.arm): _v1_run(manifest, cell.run_id).index_stats
            for cell in manifest.expected_cells
        }
        result = run_manifest_smoke(
            manifest=manifest,
            repo_entries=[{"id": "gin", "local_path": str(tmp_path)}],
            arm_entries=[
                {"id": "codegraph-warm"},
                {"id": "tsa-warm"},
            ],
            questions_by_repo={"gin": [{"id": "q1", "prompt": "Where is it?"}]},
            supplied_index_stats=stats,
            results_dir=tmp_path / "results",
            workspace=None,
            repo_path_resolver=lambda repo: Path(repo["local_path"]),
            adapter_factory=Adapter,
            run_one=run_one,
        )

        records = [
            json.loads(line)
            for line in (
                tmp_path
                / "results"
                / "experiments"
                / manifest.manifest_hash
                / "runs.jsonl"
            )
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        assert result == 1
        assert calls == 2
        assert [record["status"] for record in records] == [
            "INVALID",
            "SUCCESS",
        ]
        assert json.loads(
            (
                tmp_path
                / "results"
                / "experiments"
                / manifest.manifest_hash
                / f"policy_{manifest.expected_cells[0].run_id}.json"
            ).read_text(encoding="utf-8")
        )["violations"] == [
            "EXECUTION_EXCEPTION:RuntimeError",
            "TRANSCRIPT_MISSING",
        ]

    def test_manifest_smoke_preserves_completed_evidence_after_index_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from dataclasses import replace

        from benchmarks.codegraph_compare.adapters import RunConfig
        from benchmarks.codegraph_compare.smoke_execution import (
            run_manifest_smoke,
        )
        from benchmarks.codegraph_compare.smoke_workspace import (
            IndexContentDriftError,
        )

        manifest = replace(
            _v1_manifest(),
            index_content_hashes=(
                ("codegraph-warm", "codegraph-index-hash"),
                ("tsa-warm", "tsa-index-hash"),
            ),
        )
        cells = iter(manifest.expected_cells)

        class Adapter:
            def __init__(self, arm: str) -> None:
                self.arm = arm

            def build_run_config(self, repo_path: Path, prompt: str) -> RunConfig:
                return RunConfig(self.arm, repo_path, "system")

        def run_one(**kwargs):
            cell = next(cells)
            transcript = tmp_path / f"{cell.run_id}.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "mcp_tool_call",
                            "server": (
                                "codegraph"
                                if cell.arm == "codegraph-warm"
                                else "tree-sitter-analyzer"
                            ),
                            "tool": "query",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            record = self._legacy_record(manifest, cell.run_id, transcript)
            record["answer"] = f"completed answer for {cell.arm}"
            record["input_tokens"] = 101
            record["output_tokens"] = 23
            record["total_tokens"] = 124
            record["tool_calls"] = 7
            record["file_reads"] = 3
            record["search_calls"] = 2
            record["index_queries"] = 1
            record["cached_input_tokens"] = 41
            record["reasoning_output_tokens"] = 11
            record["cache_read_tokens"] = 37
            record["cache_creation_tokens"] = 4
            record["total_cost_usd"] = 0.125
            record["estimated_cost_usd"] = 0.25
            record["citations"] = ["gin.go", "tree.go"]
            record["started_at"] = "2026-07-31T01:02:03Z"
            record["ended_at"] = "2026-07-31T01:02:08Z"
            record["elapsed_seconds"] = 5.0
            if cell.arm == "codegraph-warm":
                record["error"] = "provider returned a partial failure"
            return record

        validation_calls = 0

        def validate(*args):
            nonlocal validation_calls
            validation_calls += 1
            if validation_calls == 1:
                raise IndexContentDriftError("index changed after completed model call")
            raise OSError("index digest could not be read")

        workspace_cells = {}
        for arm, index_name in (
            ("codegraph-warm", ".codegraph"),
            ("tsa-warm", ".ast-cache"),
        ):
            checkout_path = tmp_path / "checkouts" / arm
            artifact_path = tmp_path / "artifacts" / arm
            index_path = tmp_path / "frozen-indexes" / arm / index_name
            checkout_path.mkdir(parents=True)
            artifact_path.mkdir(parents=True)
            index_path.mkdir(parents=True)
            workspace_cells[arm] = SimpleNamespace(
                checkout_path=checkout_path,
                artifact_path=artifact_path,
                index_path=index_path,
            )
        workspace = SimpleNamespace(cell=workspace_cells.__getitem__)
        expected_hashes = dict(manifest.index_content_hashes)
        monkeypatch.setattr(
            "benchmarks.codegraph_compare.smoke_execution.index_content_hash",
            lambda path: expected_hashes[
                next(arm for arm in manifest.indexed_arms if arm in path.parts)
            ],
        )
        monkeypatch.setattr(
            "benchmarks.codegraph_compare.smoke_execution.canonical_semantic_digest",
            lambda path: "semantic-digest",
        )

        def materialize(index_path, checkout_path, arm, expected_hash, expected_paths):
            runtime_path = checkout_path / index_path.name
            runtime_path.mkdir()
            return runtime_path

        monkeypatch.setattr(
            "benchmarks.codegraph_compare.smoke_execution.materialize_runtime_index",
            materialize,
        )
        monkeypatch.setattr(
            "benchmarks.codegraph_compare.smoke_execution.audit_runtime_index",
            lambda runtime_path, audit_path, arm, expected_paths: (
                "semantic-digest",
                expected_paths,
            ),
        )
        monkeypatch.setattr(
            "benchmarks.codegraph_compare.smoke_execution.validate_index_content_v1",
            validate,
        )
        stats = {
            ("gin", cell.arm): _v1_run(manifest, cell.run_id).index_stats
            for cell in manifest.expected_cells
        }

        result = run_manifest_smoke(
            manifest=manifest,
            repo_entries=[{"id": "gin", "local_path": str(tmp_path)}],
            arm_entries=[
                {"id": "codegraph-warm"},
                {"id": "tsa-warm"},
            ],
            questions_by_repo={"gin": [{"id": "q1", "prompt": "Where is it?"}]},
            supplied_index_stats=stats,
            results_dir=tmp_path / "results",
            workspace=workspace,
            repo_path_resolver=lambda repo: Path(repo["local_path"]),
            adapter_factory=Adapter,
            run_one=run_one,
        )

        experiment = tmp_path / "results" / "experiments" / manifest.manifest_hash
        first = json.loads(
            (experiment / "runs.jsonl").read_text(encoding="utf-8").splitlines()[0]
        )
        second = json.loads(
            (experiment / "runs.jsonl").read_text(encoding="utf-8").splitlines()[1]
        )
        policy = json.loads(
            (experiment / f"policy_{manifest.expected_cells[0].run_id}.json").read_text(
                encoding="utf-8"
            )
        )
        # Issue #1201: 运行后的索引验证不能抹去模型证据。
        assert result == 1
        assert first["answer"] == "completed answer for codegraph-warm"
        assert first["transcript_path"].endswith(
            f"{manifest.expected_cells[0].run_id}.jsonl"
        )
        assert first["input_tokens"] == 101
        assert first["output_tokens"] == 23
        assert first["total_tokens"] == 124
        assert first["tool_calls"] == 7
        assert first["file_reads"] == 3
        assert first["search_calls"] == 2
        assert first["index_queries"] == 1
        assert first["cached_input_tokens"] == 41
        assert first["reasoning_output_tokens"] == 11
        assert first["cache_read_tokens"] == 37
        assert first["cache_creation_tokens"] == 4
        assert first["total_cost_usd"] == 0.125
        assert first["estimated_cost_usd"] == 0.25
        assert first["citations"] == ["gin.go", "tree.go"]
        assert first["started_at"] == "2026-07-31T01:02:03Z"
        assert first["ended_at"] == "2026-07-31T01:02:08Z"
        assert first["elapsed_seconds"] == 5.0
        assert first["status"] == "INVALID"
        assert first["blocker_reason"] == (
            "POLICY_AUDIT:INDEX_CONTENT_DRIFT;"
            "PRODUCT_FAILURE:provider returned a partial failure"
        )
        assert policy["violations"] == ["INDEX_CONTENT_DRIFT"]
        assert second["status"] == "INVALID"
        assert second["blocker_reason"] == "POLICY_AUDIT:EXECUTION_EXCEPTION:OSError"
