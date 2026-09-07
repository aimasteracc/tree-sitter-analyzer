"""Issue #1376：setup_failures 行为组，原测试 AST 保持不变。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from benchmarks.codegraph_compare import run as compare_run
from benchmarks.codegraph_compare.adapters import IndexStats
from tests.unit._benchmark_harness_matrix_helpers import (
    TestCodeGraphCompareSetupGate as _TestCodeGraphCompareSetupGate,
)
from tests.unit._benchmark_harness_matrix_helpers import _v1_manifest


class TestCodeGraphCompareSetupGate(_TestCodeGraphCompareSetupGate):
    """Model-backed matrix work must be fail-closed behind setup validation."""

    def test_invalid_index_evidence_records_started_and_blocked(
        self, monkeypatch, tmp_path: Path
    ):
        manifest = _v1_manifest()
        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        args = self._matrix_args()
        args.manifest = self._write_v1_manifest(tmp_path, manifest)
        args.setup_only = True
        args.index_evidence = tmp_path / "invalid.json"
        args.index_evidence.write_text("{not-json", encoding="utf-8")

        with pytest.raises(SystemExit) as exc_info:
            compare_run.cmd_run_matrix(args)

        assert exc_info.value.code == 1
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
        assert [event["status"] for event in registry_events] == [
            "PLANNED",
            "BLOCKED",
        ]

    def test_oversized_index_duration_records_started_and_blocked(
        self, monkeypatch, tmp_path: Path
    ):
        manifest = _v1_manifest()
        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        evidence_path = self._write_v1_index_evidence(tmp_path, manifest)
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        evidence["cells"][0]["index_stats"]["build_seconds"] = 10**400
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        args = self._matrix_args()
        args.manifest = self._write_v1_manifest(tmp_path, manifest)
        args.setup_only = True
        args.index_evidence = evidence_path

        with pytest.raises(SystemExit) as exc_info:
            compare_run.cmd_run_matrix(args)

        assert exc_info.value.code == 1
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

    def test_non_object_manifest_uses_cli_diagnostic(
        self, monkeypatch, tmp_path: Path, capsys
    ):
        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text("[]", encoding="utf-8")
        args = self._matrix_args()
        args.manifest = manifest_path
        args.setup_only = True
        args.index_evidence = tmp_path / "unused-index-evidence.json"

        with pytest.raises(SystemExit) as exc_info:
            compare_run.cmd_run_matrix(args)

        assert exc_info.value.code == 1
        assert (
            f"Invalid experiment manifest {manifest_path}: "
            "Experiment manifest must be an object" in capsys.readouterr().err
        )

    def test_duplicate_manifest_member_uses_cli_diagnostic(
        self, tmp_path: Path, capsys
    ):
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(
            '{"benchmark_version":1,"benchmark_version":1}',
            encoding="utf-8",
        )
        args = self._matrix_args()
        args.manifest = manifest_path
        args.setup_only = True
        args.index_evidence = tmp_path / "unused-index-evidence.json"

        with pytest.raises(SystemExit) as exc_info:
            compare_run.cmd_run_matrix(args)

        assert exc_info.value.code == 1
        assert (
            f"Invalid experiment manifest {manifest_path}: "
            "Duplicate JSON member: benchmark_version" in capsys.readouterr().err
        )

    def test_duplicate_index_evidence_member_records_input_failure(
        self, monkeypatch, tmp_path: Path, capsys
    ):
        manifest = self._v1_setup_manifest()
        evidence_path = tmp_path / "index-evidence.json"
        evidence_path.write_text(
            '{"schema_version":1,"schema_version":1,"cells":[]}',
            encoding="utf-8",
        )
        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        args = self._matrix_args()
        args.agent_backend = manifest.agent_backend
        args.manifest = self._write_v1_manifest(tmp_path, manifest)
        args.setup_only = True
        args.index_evidence = evidence_path

        with pytest.raises(SystemExit) as exc_info:
            compare_run.cmd_run_matrix(args)

        assert exc_info.value.code == 1
        assert "Duplicate JSON member: schema_version" in capsys.readouterr().err
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

    def test_malformed_nested_manifest_uses_cli_diagnostic(
        self, monkeypatch, tmp_path: Path, capsys
    ):
        from dataclasses import asdict

        manifest = self._v1_setup_manifest()
        payload = json.loads(json.dumps(asdict(manifest)))
        payload["eligible_paths"] = [[]]
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        args = self._matrix_args()
        args.manifest = manifest_path
        args.setup_only = True
        args.index_evidence = tmp_path / "unused-index-evidence.json"

        with pytest.raises(SystemExit) as exc_info:
            compare_run.cmd_run_matrix(args)

        assert exc_info.value.code == 1
        assert (
            f"Invalid experiment manifest {manifest_path}: "
            "Manifest nested fields do not match the V1 schema"
            in capsys.readouterr().err
        )

    def test_setup_only_direct_script_preserves_package_imports(self, tmp_path: Path):
        script = Path(compare_run.__file__).resolve()
        missing_manifest = tmp_path / "missing-manifest.json"
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                str(script),
                "run-matrix",
                "--manifest",
                str(missing_manifest),
                "--index-evidence",
                str(tmp_path / "unused-index-evidence.json"),
                "--setup-only",
            ],
            cwd=tmp_path,
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1
        assert f"Invalid experiment manifest {missing_manifest}" in result.stderr
        assert "ModuleNotFoundError" not in result.stderr

    def test_invalid_matrix_yaml_shape_records_started_and_blocked(
        self, monkeypatch, tmp_path: Path
    ):
        manifest = _v1_manifest()
        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        original_load = compare_run._load_yaml
        monkeypatch.setattr(
            compare_run,
            "_load_yaml",
            lambda path: (
                [{"local_path": str(tmp_path)}]
                if path == compare_run.REPOS_YAML
                else original_load(path)
            ),
        )
        args = self._matrix_args()
        args.manifest = self._write_v1_manifest(tmp_path, manifest)
        args.setup_only = True
        args.index_evidence = self._write_v1_index_evidence(tmp_path, manifest)

        with pytest.raises(SystemExit) as exc_info:
            compare_run.cmd_run_matrix(args)

        assert exc_info.value.code == 1
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

    def test_setup_only_rejects_dry_run_before_adapter_creation(
        self, monkeypatch, tmp_path: Path, capsys
    ):
        manifest = _v1_manifest()
        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        self._install_runner_modules(
            monkeypatch,
            lambda arm_id: (_ for _ in ()).throw(
                AssertionError("invalid setup flags must not create adapters")
            ),
            lambda **kwargs: (_ for _ in ()).throw(
                AssertionError("invalid setup flags must not call the model")
            ),
        )
        args = self._matrix_args()
        args.manifest = self._write_v1_manifest(tmp_path, manifest)
        args.setup_only = True
        args.index_evidence = self._write_v1_index_evidence(tmp_path, manifest)
        args.dry_run = True

        with pytest.raises(SystemExit) as exc_info:
            compare_run.cmd_run_matrix(args)

        assert exc_info.value.code == 1
        assert "cannot be combined with --dry-run" in capsys.readouterr().err

    def test_duplicate_matrix_entry_is_rejected_before_adapter_creation(
        self, monkeypatch, tmp_path: Path
    ):
        manifest = _v1_manifest()
        self._patch_v1_matrix_inputs(monkeypatch, tmp_path)
        original_load = compare_run._load_yaml
        monkeypatch.setattr(
            compare_run,
            "_load_yaml",
            lambda path: (
                original_load(path) + [original_load(path)[0]]
                if path == compare_run.ARMS_YAML
                else original_load(path)
            ),
        )
        self._install_runner_modules(
            monkeypatch,
            lambda arm_id: (_ for _ in ()).throw(
                AssertionError("duplicate matrix must not create adapters")
            ),
            lambda **kwargs: (_ for _ in ()).throw(
                AssertionError("duplicate matrix must not call the model")
            ),
        )
        args = self._matrix_args()
        args.manifest = self._write_v1_manifest(tmp_path, manifest)
        args.setup_only = True
        args.index_evidence = self._write_v1_index_evidence(tmp_path, manifest)

        assert compare_run.cmd_run_matrix(args) == 1

    def test_setup_failure_checks_all_indexed_arms_and_blocks_model_calls(
        self, monkeypatch, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.adapters import RunConfig

        events: list[str] = []

        class Adapter:
            def __init__(self, arm_id: str) -> None:
                self.arm_id = arm_id

            def prepare_index(self, repo_path: Path, cold: bool) -> IndexStats:
                events.append(f"prepare:{self.arm_id}")
                if self.arm_id == "codegraph-warm":
                    raise RuntimeError("codegraph executable missing")
                if self.arm_id == "tsa-warm":
                    return IndexStats(0.1, 0, 0)
                return IndexStats(0.1, 100, 2)

            def build_run_config(self, repo_path: Path, prompt: str) -> RunConfig:
                return RunConfig(self.arm_id, repo_path, "system")

        def run_one(**kwargs):
            events.append(f"model:{kwargs['arm_id']}")
            raise AssertionError("model call must remain unreachable")

        self._patch_matrix_inputs(monkeypatch, tmp_path)
        self._install_runner_modules(monkeypatch, Adapter, run_one)

        exit_code = compare_run.cmd_run_matrix(self._matrix_args())

        assert exit_code == 1
        assert events == ["prepare:codegraph-warm", "prepare:tsa-warm"]
        evidence_files = list((tmp_path / "results").glob("setup_failures_*.json"))
        assert len(evidence_files) == 1
        evidence = json.loads(evidence_files[0].read_text(encoding="utf-8"))
        assert evidence["status"] == "setup_failed"
        assert evidence["model_calls_started"] == 0
        assert evidence["failures"] == [
            {
                "arm_id": "codegraph-warm",
                "code": "PREPARE_EXCEPTION",
                "index_mode": "warm",
                "message": "codegraph executable missing",
                "repo_id": "demo",
            },
            {
                "arm_id": "tsa-warm",
                "code": "EMPTY_INDEX",
                "index_mode": "warm",
                "message": "index preparation returned zero indexed files",
                "repo_id": "demo",
            },
        ]

    def test_all_indexed_setup_finishes_before_first_model_call(
        self, monkeypatch, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.adapters import RunConfig

        events: list[str] = []

        class Adapter:
            def __init__(self, arm_id: str) -> None:
                self.arm_id = arm_id

            def prepare_index(self, repo_path: Path, cold: bool) -> IndexStats:
                events.append(f"prepare:{self.arm_id}")
                return IndexStats(0.1, 100, 2)

            def build_run_config(self, repo_path: Path, prompt: str) -> RunConfig:
                events.append(f"config:{self.arm_id}")
                return RunConfig(self.arm_id, repo_path, "system")

        def run_one(**kwargs):
            events.append(f"model:{kwargs['arm_id']}")
            return {
                "answer": "ok",
                "elapsed_seconds": 0.1,
            }

        self._patch_matrix_inputs(monkeypatch, tmp_path)
        self._install_runner_modules(monkeypatch, Adapter, run_one)

        exit_code = compare_run.cmd_run_matrix(self._matrix_args())

        assert exit_code == 0
        first_model = next(
            i for i, event in enumerate(events) if event.startswith("model:")
        )
        assert events[:first_model] == [
            "config:native-only",
            "prepare:codegraph-warm",
            "config:codegraph-warm",
            "prepare:tsa-warm",
            "config:tsa-warm",
        ]
        assert events.count("prepare:codegraph-warm") == 1
        assert events.count("prepare:tsa-warm") == 1

    def test_dry_run_preserves_stub_execution_without_index_setup(
        self, monkeypatch, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.adapters import RunConfig

        dry_run_calls: list[bool] = []

        class Adapter:
            def __init__(self, arm_id: str) -> None:
                self.arm_id = arm_id

            def prepare_index(self, repo_path: Path, cold: bool) -> IndexStats:
                raise AssertionError("dry-run must not prepare indexes")

            def build_run_config(self, repo_path: Path, prompt: str) -> RunConfig:
                return RunConfig(self.arm_id, repo_path, "system")

        def run_one(**kwargs):
            dry_run_calls.append(kwargs["dry_run"])
            return {"answer": "DRY_RUN", "elapsed_seconds": 0.0}

        self._patch_matrix_inputs(monkeypatch, tmp_path)
        self._install_runner_modules(monkeypatch, Adapter, run_one)
        args = self._matrix_args()
        args.dry_run = True

        exit_code = compare_run.cmd_run_matrix(args)

        assert exit_code == 0
        assert dry_run_calls == [True, True, True]
        assert not list((tmp_path / "results").glob("setup_failures_*.json"))

    def test_run_config_failure_is_collected_before_model_execution(
        self, monkeypatch, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.adapters import RunConfig

        model_calls = 0

        class Adapter:
            def __init__(self, arm_id: str) -> None:
                self.arm_id = arm_id

            def prepare_index(self, repo_path: Path, cold: bool) -> IndexStats:
                return IndexStats(0.1, 100, 2)

            def build_run_config(self, repo_path: Path, prompt: str) -> RunConfig:
                if self.arm_id == "tsa-warm":
                    raise RuntimeError("prompt unavailable")
                return RunConfig(self.arm_id, repo_path, "system")

        def run_one(**kwargs):
            nonlocal model_calls
            model_calls += 1
            raise AssertionError("model call must remain unreachable")

        self._patch_matrix_inputs(monkeypatch, tmp_path)
        self._install_runner_modules(monkeypatch, Adapter, run_one)

        assert compare_run.cmd_run_matrix(self._matrix_args()) == 1
        assert model_calls == 0
        evidence_path = next((tmp_path / "results").glob("setup_failures_*.json"))
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert evidence["failures"] == [
            {
                "arm_id": "tsa-warm",
                "code": "RUN_CONFIG_EXCEPTION",
                "index_mode": "warm",
                "message": "prompt unavailable",
                "question_id": "demo-q1",
                "repo_id": "demo",
            }
        ]

    def test_invalid_mode_and_malformed_stats_fail_closed(self, tmp_path: Path):
        from benchmarks.codegraph_compare.setup_validation import (
            validate_matrix_setup,
        )

        class InvalidStatsAdapter:
            def prepare_index(self, repo_path: Path, cold: bool):
                return None

        result = validate_matrix_setup(
            [{"id": "demo", "local_path": str(tmp_path)}],
            [
                {"id": "bad-mode", "index_mode": "typo"},
                {"id": "bad-stats", "index_mode": "warm"},
            ],
            questions_by_repo={"demo": []},
            repo_path_resolver=lambda repo: Path(repo["local_path"]),
            adapter_factory=lambda arm_id: InvalidStatsAdapter(),
        )

        assert result.ok is False
        assert [failure.code for failure in result.failures] == [
            "INVALID_INDEX_MODE",
            "INVALID_INDEX_STATS",
        ]

    def test_unsupported_backend_arms_block_native_model_before_index_setup(
        self, monkeypatch, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.adapters import RunConfig

        events: list[str] = []

        class Adapter:
            def __init__(self, arm_id: str) -> None:
                self.arm_id = arm_id

            def prepare_index(self, repo_path: Path, cold: bool) -> IndexStats:
                events.append(f"prepare:{self.arm_id}")
                return IndexStats(0.1, 100, 2)

            def build_run_config(self, repo_path: Path, prompt: str) -> RunConfig:
                return RunConfig(self.arm_id, repo_path, "system")

        def validate_backend(agent_backend: str, arm_id: str) -> None:
            events.append(f"validate:{agent_backend}:{arm_id}")
            if agent_backend == "codex" and arm_id != "native-only":
                raise NotImplementedError(f"codex does not support {arm_id}")

        def run_one(**kwargs):
            events.append(f"model:{kwargs['arm_id']}")
            raise AssertionError("model call must remain unreachable")

        self._patch_matrix_inputs(monkeypatch, tmp_path)
        self._install_runner_modules(
            monkeypatch, Adapter, run_one, validate_backend=validate_backend
        )

        assert compare_run.cmd_run_matrix(self._matrix_args()) == 1
        assert events == [
            "validate:codex:native-only",
            "validate:codex:codegraph-warm",
            "validate:codex:tsa-warm",
        ]
        evidence_path = next((tmp_path / "results").glob("setup_failures_*.json"))
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert [item["code"] for item in evidence["failures"]] == [
            "BACKEND_UNSUPPORTED",
            "BACKEND_UNSUPPORTED",
        ]
