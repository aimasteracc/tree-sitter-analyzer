"""Issue #1376：test_benchmark_harness_setup_manifest 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.codegraph_compare import run as compare_run
from tests.unit._benchmark_harness_matrix_helpers import (
    TestCodeGraphCompareSetupGate as _TestCodeGraphCompareSetupGate,
)
from tests.unit._benchmark_harness_matrix_helpers import _v1_manifest, _v1_run


class TestCodeGraphCompareSetupGate(_TestCodeGraphCompareSetupGate):
    """模型驱动的矩阵执行必须受 setup 验证保护，失败时保持关闭。"""

    def test_manifest_bound_setup_only_writes_success_evidence_without_model_calls(
        self, monkeypatch, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.adapters import RunConfig

        manifest = self._v1_setup_manifest()
        manifest_path = self._write_v1_manifest(tmp_path, manifest)
        evidence_input = self._write_v1_index_evidence(tmp_path, manifest)
        model_calls = 0

        class Adapter:
            def __init__(self, arm_id: str) -> None:
                self.arm_id = arm_id

            def prepare_index(self, repo_path: Path, cold: bool):
                record = _v1_run(
                    manifest,
                    f"q1__{self.arm_id}__{manifest.agent_backend}__00",
                )
                assert record.index_stats is not None
                return record.index_stats

            def build_run_config(self, repo_path: Path, prompt: str) -> RunConfig:
                return RunConfig(self.arm_id, repo_path, "system")

        def run_one(**kwargs):
            nonlocal model_calls
            model_calls += 1
            raise AssertionError("setup-only must not call the model")

        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        self._install_runner_modules(monkeypatch, Adapter, run_one)
        args = self._matrix_args()
        args.agent_backend = manifest.agent_backend
        args.manifest = str(manifest_path)
        args.setup_only = True
        args.index_evidence = evidence_input

        assert compare_run.cmd_run_matrix(args) == 0
        assert model_calls == 0
        evidence_path = next(
            (tmp_path / "results" / "experiments" / manifest.manifest_hash).glob(
                "setup_*.json"
            )
        )
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert evidence["schema_version"] == 1
        assert evidence["experiment_id"] == manifest.experiment_id
        assert evidence["manifest_hash"] == manifest.manifest_hash
        assert evidence["status"] == "setup_passed"
        assert evidence["validation_level"] == "manifest-bound-v1-consumer"
        assert evidence["publishable"] is False
        assert evidence["model_calls_started"] == 0
        assert [(cell["repo_id"], cell["arm_id"]) for cell in evidence["cells"]] == [
            ("gin", "codegraph-warm"),
            ("gin", "tsa-warm"),
        ]
        registry_events = [
            json.loads(line)
            for line in (tmp_path / "results" / "experiment_registry.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        assert registry_events == [
            {
                "experiment_id": manifest.experiment_id,
                "manifest_hash": manifest.manifest_hash,
                "outcome": "setup_started",
                "status": "PLANNED",
            },
            {
                "experiment_id": manifest.experiment_id,
                "manifest_hash": manifest.manifest_hash,
                "outcome": "setup_passed",
                "status": "PLANNED",
            },
        ]

    def test_matrix_manifest_mismatch_fails_before_adapter_creation(
        self, monkeypatch, tmp_path: Path
    ):
        manifest = self._v1_setup_manifest()
        manifest_path = self._write_v1_manifest(tmp_path, manifest)
        adapter_calls = 0
        model_calls = 0

        def get_adapter(arm_id: str):
            nonlocal adapter_calls
            adapter_calls += 1
            raise AssertionError("mismatched matrix must not create an adapter")

        def run_one(**kwargs):
            nonlocal model_calls
            model_calls += 1
            raise AssertionError("mismatched matrix must not call the model")

        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        self._install_runner_modules(monkeypatch, get_adapter, run_one)
        args = self._matrix_args()
        args.agent_backend = manifest.agent_backend
        args.arms = "tsa-warm"
        args.manifest = str(manifest_path)
        args.setup_only = True
        args.index_evidence = self._write_v1_index_evidence(tmp_path, manifest)

        assert compare_run.cmd_run_matrix(args) == 1
        assert adapter_calls == 0
        assert model_calls == 0
        evidence_path = next(
            (tmp_path / "results" / "experiments" / manifest.manifest_hash).glob(
                "setup_*.json"
            )
        )
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert [failure["code"] for failure in evidence["failures"]] == [
            "MATRIX_MANIFEST_MISMATCH"
        ]

    def test_setup_only_rejects_timeout_that_differs_from_manifest(
        self, monkeypatch, tmp_path: Path
    ):
        manifest = self._v1_setup_manifest()
        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        args = self._matrix_args()
        args.agent_backend = manifest.agent_backend
        args.timeout_seconds = manifest.timeout_seconds + 1
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
            "MATRIX_TIMEOUT_MISMATCH"
        ]

    def test_setup_only_rejects_unsupported_backend_arm_pairs(
        self, monkeypatch, tmp_path: Path
    ):
        manifest = self._v1_setup_manifest(agent_backend="unsupported")
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
            "BACKEND_UNSUPPORTED",
            "BACKEND_UNSUPPORTED",
        ]

    def test_setup_only_rejects_changed_arm_configuration(
        self, monkeypatch, tmp_path: Path
    ):
        manifest = self._v1_setup_manifest()
        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        original_load = compare_run._load_yaml
        changed_arms = [
            {**arm, "adapter": "changed-adapter"}
            for arm in original_load(compare_run.ARMS_YAML)
        ]
        monkeypatch.setattr(
            compare_run,
            "_load_yaml",
            lambda path: (
                changed_arms if path == compare_run.ARMS_YAML else original_load(path)
            ),
        )
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
            "MATRIX_CONFIG_HASH_MISMATCH"
        ]

    def test_setup_only_rejects_changed_question_configuration(
        self, monkeypatch, tmp_path: Path
    ):
        manifest = self._v1_setup_manifest()
        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        original_load = compare_run._load_yaml
        changed_questions = [
            {**question, "prompt": "Changed after manifest creation"}
            for question in original_load(compare_run.QUESTIONS_YAML)
        ]
        monkeypatch.setattr(
            compare_run,
            "_load_yaml",
            lambda path: (
                changed_questions
                if path == compare_run.QUESTIONS_YAML
                else original_load(path)
            ),
        )
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
            "MATRIX_QUESTION_HASH_MISMATCH"
        ]

    def test_setup_only_rejects_indexed_arm_omission(self, monkeypatch, tmp_path: Path):
        manifest = self._v1_setup_manifest(
            indexed_arms=(),
            required_readiness_oracles={},
        )
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
            "MATRIX_INDEXED_ARMS_MISMATCH"
        ]

    def test_setup_only_rejects_conflicting_repo_commit(
        self, monkeypatch, tmp_path: Path
    ):
        manifest = self._v1_setup_manifest(repo_commits={"gin": "conflicting-revision"})
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
            "MATRIX_REPO_COMMIT_MISMATCH"
        ]

    def test_matrix_manifest_rejects_selected_repo_without_questions(
        self,
        tmp_path: Path,
    ):
        from benchmarks.codegraph_compare.setup_validation import (
            validate_matrix_setup,
        )

        manifest = _v1_manifest(
            expected_run_ids=("q1__native-only__codex__00",),
            required_arms=("native-only",),
            tool_fingerprints={"native-only": "native"},
        )

        result = validate_matrix_setup(
            [
                {"id": "gin"},
                {"id": "empty"},
            ],
            [{"id": "native-only", "index_mode": "none"}],
            questions_by_repo={
                "gin": [{"id": "q1"}],
                "empty": [],
            },
            repo_path_resolver=lambda repo: tmp_path / str(repo["id"]),
            adapter_factory=lambda arm_id: pytest.fail(
                f"manifest validation created adapter {arm_id}"
            ),
            manifest=manifest,
            repeats=1,
            agent_backend="codex",
            model="gpt-5",
            supplied_index_stats={},
        )

        assert tuple(failure.code for failure in result.failures) == (
            "MATRIX_MANIFEST_MISMATCH",
        )

    def test_readiness_oracle_mismatch_fails_closed_without_model_calls(
        self, monkeypatch, tmp_path: Path
    ):
        manifest = self._v1_setup_manifest()
        manifest_path = self._write_v1_manifest(tmp_path, manifest)
        evidence_input = self._write_v1_index_evidence(
            tmp_path, manifest, readiness=False
        )
        model_calls = 0

        def run_one(**kwargs):
            nonlocal model_calls
            model_calls += 1
            raise AssertionError("failed readiness must not call the model")

        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        self._install_runner_modules(
            monkeypatch,
            lambda arm_id: (_ for _ in ()).throw(
                AssertionError("evidence consumer must not create adapters")
            ),
            run_one,
        )
        args = self._matrix_args()
        args.agent_backend = manifest.agent_backend
        args.manifest = str(manifest_path)
        args.setup_only = True
        args.index_evidence = evidence_input

        assert compare_run.cmd_run_matrix(args) == 1
        assert model_calls == 0
        evidence_path = next(
            (tmp_path / "results" / "experiments" / manifest.manifest_hash).glob(
                "setup_*.json"
            )
        )
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert [failure["code"] for failure in evidence["failures"]] == [
            "READINESS_ORACLE_MISMATCH"
        ]

    def test_setup_evidence_uses_exclusive_create(self, monkeypatch, tmp_path: Path):
        from benchmarks.codegraph_compare.adapters import RunConfig

        manifest = self._v1_setup_manifest()
        manifest_path = self._write_v1_manifest(tmp_path, manifest)
        evidence_input = self._write_v1_index_evidence(tmp_path, manifest)
        session_id = "20260721T010203000000Z"
        experiment_dir = tmp_path / "results" / "experiments" / manifest.manifest_hash
        experiment_dir.mkdir(parents=True)
        evidence_path = experiment_dir / f"setup_{session_id}.json"
        evidence_path.write_text("sentinel\n", encoding="utf-8")

        class Adapter:
            def __init__(self, arm_id: str) -> None:
                self.arm_id = arm_id

            def prepare_index(self, repo_path: Path, cold: bool):
                record = _v1_run(
                    manifest,
                    f"q1__{self.arm_id}__{manifest.agent_backend}__00",
                )
                assert record.index_stats is not None
                return record.index_stats

            def build_run_config(self, repo_path: Path, prompt: str) -> RunConfig:
                return RunConfig(self.arm_id, repo_path, "system")

        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        self._install_runner_modules(
            monkeypatch,
            Adapter,
            lambda **kwargs: (_ for _ in ()).throw(
                AssertionError("setup-only must not call the model")
            ),
        )
        monkeypatch.setattr(
            compare_run,
            "datetime",
            SimpleNamespace(
                now=lambda timezone: SimpleNamespace(
                    strftime=lambda pattern: session_id
                )
            ),
        )
        args = self._matrix_args()
        args.agent_backend = manifest.agent_backend
        args.manifest = str(manifest_path)
        args.setup_only = True
        args.index_evidence = evidence_input

        with pytest.raises(FileExistsError):
            compare_run.cmd_run_matrix(args)

        assert evidence_path.read_text(encoding="utf-8") == "sentinel\n"
        registry_events = [
            json.loads(line)
            for line in (tmp_path / "results" / "experiment_registry.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        assert registry_events == [
            {
                "experiment_id": manifest.experiment_id,
                "manifest_hash": manifest.manifest_hash,
                "outcome": "setup_started",
                "status": "PLANNED",
            },
            {
                "experiment_id": manifest.experiment_id,
                "manifest_hash": manifest.manifest_hash,
                "outcome": "setup_internal_failed",
                "status": "BLOCKED",
            },
        ]
