"""Issue #1376：test_benchmark_harness_setup_diagnostics 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from benchmarks.codegraph_compare import run as compare_run
from tests.unit._benchmark_harness_matrix_helpers import (
    TestCodeGraphCompareSetupGate as _TestCodeGraphCompareSetupGate,
)
from tests.unit._benchmark_harness_matrix_helpers import _v1_manifest


class TestCodeGraphCompareSetupGate(_TestCodeGraphCompareSetupGate):
    """模型驱动的矩阵执行必须受 setup 验证保护，失败时保持关闭。"""

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
