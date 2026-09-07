"""Issue #1376：Gin qualification 行为组，保留测试逻辑，文本 I/O 显式使用 UTF-8。"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from benchmarks.codegraph_compare import gin_smoke
from benchmarks.codegraph_compare.adapters import IndexStats


class TestGinSmokeQualification:
    def _bundle(self, tmp_path: Path) -> Path:
        bundle = tmp_path / "bundle"
        gin_smoke.create_bundle(
            bundle,
            benchmark_git_sha="a" * 40,
            repository_path="/fixture/repository",
            repository_commit="b" * 40,
            repository_fingerprint="c" * 64,
            question="Where is the Gin router assembled?",
            model="fixture-model",
            timeout_seconds=60,
        )
        return bundle

    def _validate(self, bundle: Path, git_sha: str = "a" * 40):
        digest = hashlib.sha256((bundle / "checksums.json").read_bytes()).hexdigest()
        return gin_smoke.validate_bundle(
            bundle,
            expected_git_sha=git_sha,
            expected_bundle_digest=digest,
        )

    def test_fixture_bundle_is_e0_only(self, tmp_path: Path):
        bundle = self._bundle(tmp_path)

        result = self._validate(bundle)

        assert result["evidence_level"] == "E0"
        assert result["publishable"] is False
        assert result["dominance_allowed"] is False
        assert result["winner"] is None

    def test_replay_is_byte_identical(self, tmp_path: Path):
        bundle = self._bundle(tmp_path)
        replay = tmp_path / "replay"

        gin_smoke.replay_bundle(
            bundle,
            replay,
            expected_git_sha="a" * 40,
            expected_bundle_digest=hashlib.sha256(
                (bundle / "checksums.json").read_bytes()
            ).hexdigest(),
        )

        source_bytes = {
            path.relative_to(bundle): path.read_bytes()
            for path in bundle.rglob("*")
            if path.is_file()
        }
        replay_bytes = {
            path.relative_to(replay): path.read_bytes()
            for path in replay.rglob("*")
            if path.is_file()
        }
        assert replay_bytes == source_bytes

    @pytest.mark.parametrize(
        ("path", "field", "value", "message"),
        [
            (
                "cells/native.json",
                "repository_path",
                "/wrong/repository",
                "wrong repository",
            ),
            (
                "cells/native.json",
                "input_fingerprint",
                "wrong",
                "mixed or invalid cell",
            ),
            (
                "cells/native.json",
                "index_namespace",
                "index/tree_sitter_analyzer",
                "mixed or invalid cell",
            ),
            (
                "cells/native.json",
                "repository_commit",
                "d" * 40,
                "wrong repository provenance",
            ),
        ],
    )
    def test_tampered_cell_is_rejected(
        self,
        tmp_path: Path,
        path: str,
        field: str,
        value: str,
        message: str,
    ):
        bundle = self._bundle(tmp_path)
        target = bundle / path
        payload = json.loads(target.read_text(encoding="utf-8"))
        payload[field] = value
        target.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        checksums = json.loads((bundle / "checksums.json").read_text(encoding="utf-8"))
        checksums["sha256"][path] = hashlib.sha256(target.read_bytes()).hexdigest()
        (bundle / "checksums.json").write_text(
            json.dumps(checksums, sort_keys=True) + "\n", encoding="utf-8"
        )

        with pytest.raises(gin_smoke.QualificationError, match=message):
            self._validate(bundle)

    def test_cross_arm_tool_leakage_is_rejected(self, tmp_path: Path):
        bundle = self._bundle(tmp_path)
        path = "policies/native.json"
        target = bundle / path
        policy = json.loads(target.read_text(encoding="utf-8"))
        policy["allowed_tools"].append("codegraph")
        target.write_text(json.dumps(policy, sort_keys=True) + "\n", encoding="utf-8")
        checksums = json.loads((bundle / "checksums.json").read_text(encoding="utf-8"))
        checksums["sha256"][path] = hashlib.sha256(target.read_bytes()).hexdigest()
        (bundle / "checksums.json").write_text(
            json.dumps(checksums, sort_keys=True) + "\n", encoding="utf-8"
        )

        with pytest.raises(gin_smoke.QualificationError, match="invalid cell"):
            self._validate(bundle)

    @pytest.mark.parametrize("mutation", ["missing_namespace", "extra_result"])
    def test_cell_schema_is_exact(self, tmp_path: Path, mutation: str):
        bundle = self._bundle(tmp_path)
        path = "cells/native.json"
        target = bundle / path
        cell = json.loads(target.read_text(encoding="utf-8"))
        if mutation == "missing_namespace":
            del cell["index_namespace"]
        else:
            cell["model_output"] = "undeclared result"
        target.write_text(json.dumps(cell, sort_keys=True) + "\n", encoding="utf-8")
        checksums = json.loads((bundle / "checksums.json").read_text(encoding="utf-8"))
        checksums["sha256"][path] = hashlib.sha256(target.read_bytes()).hexdigest()
        (bundle / "checksums.json").write_text(
            json.dumps(checksums, sort_keys=True) + "\n", encoding="utf-8"
        )

        with pytest.raises(gin_smoke.QualificationError, match="invalid cell"):
            self._validate(bundle)

    def test_recomputed_config_fingerprint_rejects_tampering(self, tmp_path: Path):
        bundle = self._bundle(tmp_path)
        path = "manifest.json"
        target = bundle / path
        manifest = json.loads(target.read_text(encoding="utf-8"))
        manifest["model"] = "different-model"
        target.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
        checksums = json.loads((bundle / "checksums.json").read_text(encoding="utf-8"))
        checksums["sha256"][path] = hashlib.sha256(target.read_bytes()).hexdigest()
        (bundle / "checksums.json").write_text(
            json.dumps(checksums, sort_keys=True) + "\n", encoding="utf-8"
        )

        with pytest.raises(
            gin_smoke.QualificationError, match="config fingerprint mismatch"
        ):
            self._validate(bundle)

    def test_external_bundle_digest_rejects_recomputed_checksums(self, tmp_path: Path):
        bundle = self._bundle(tmp_path)
        original_digest = hashlib.sha256(
            (bundle / "checksums.json").read_bytes()
        ).hexdigest()
        manifest_path = bundle / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["question_sha256"] = "b" * 64
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
        )
        checksums = json.loads((bundle / "checksums.json").read_text(encoding="utf-8"))
        checksums["sha256"]["manifest.json"] = hashlib.sha256(
            manifest_path.read_bytes()
        ).hexdigest()
        (bundle / "checksums.json").write_text(
            json.dumps(checksums, sort_keys=True) + "\n", encoding="utf-8"
        )

        with pytest.raises(
            gin_smoke.QualificationError, match="external bundle digest mismatch"
        ):
            gin_smoke.validate_bundle(
                bundle,
                expected_git_sha="a" * 40,
                expected_bundle_digest=original_digest,
            )

    def test_recomputed_enabled_network_is_rejected(self, tmp_path: Path):
        bundle = self._bundle(tmp_path)
        manifest_path = bundle / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["network"] = "enabled"
        shared = {
            key: manifest[key]
            for key in (
                "question_sha256",
                "model",
                "timeout_seconds",
                "network",
                "allowed_native_tools",
            )
        }
        manifest["config_fingerprint"] = gin_smoke._sha256(shared)
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
        )
        for arm in gin_smoke.EXPECTED_ARMS:
            cell_path = bundle / "cells" / f"{arm}.json"
            cell = json.loads(cell_path.read_text(encoding="utf-8"))
            cell["config_fingerprint"] = manifest["config_fingerprint"]
            cell_path.write_text(
                json.dumps(cell, sort_keys=True) + "\n", encoding="utf-8"
            )
        checksums = {
            name: hashlib.sha256((bundle / name).read_bytes()).hexdigest()
            for name in gin_smoke.FILES
        }
        (bundle / "checksums.json").write_text(
            json.dumps({"sha256": checksums}, sort_keys=True) + "\n", encoding="utf-8"
        )

        with pytest.raises(gin_smoke.QualificationError, match="invalid manifest"):
            self._validate(bundle)

    def test_transcript_semantic_tampering_is_rejected(self, tmp_path: Path):
        bundle = self._bundle(tmp_path)
        path = "transcripts/native.jsonl"
        target = bundle / path
        transcript = json.loads(target.read_text(encoding="utf-8"))
        transcript["model_executed"] = True
        target.write_text(
            json.dumps(transcript, sort_keys=True) + "\n", encoding="utf-8"
        )
        checksums = json.loads((bundle / "checksums.json").read_text(encoding="utf-8"))
        checksums["sha256"][path] = hashlib.sha256(target.read_bytes()).hexdigest()
        (bundle / "checksums.json").write_text(
            json.dumps(checksums, sort_keys=True) + "\n", encoding="utf-8"
        )

        with pytest.raises(
            gin_smoke.QualificationError, match="invalid qualification transcript"
        ):
            self._validate(bundle)

    def test_non_object_json_is_rejected_cleanly(self, tmp_path: Path):
        bundle = self._bundle(tmp_path)
        path = "manifest.json"
        target = bundle / path
        target.write_text("[]\n", encoding="utf-8")
        checksums = json.loads((bundle / "checksums.json").read_text(encoding="utf-8"))
        checksums["sha256"][path] = hashlib.sha256(target.read_bytes()).hexdigest()
        (bundle / "checksums.json").write_text(
            json.dumps(checksums, sort_keys=True) + "\n", encoding="utf-8"
        )

        with pytest.raises(gin_smoke.QualificationError, match="JSON object required"):
            self._validate(bundle)

    def test_embedded_oracle_field_is_rejected(self, tmp_path: Path):
        bundle = self._bundle(tmp_path)
        path = "manifest.json"
        target = bundle / path
        manifest = json.loads(target.read_text(encoding="utf-8"))
        manifest["expected_answer"] = "secret"
        target.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
        checksums = json.loads((bundle / "checksums.json").read_text(encoding="utf-8"))
        checksums["sha256"][path] = hashlib.sha256(target.read_bytes()).hexdigest()
        (bundle / "checksums.json").write_text(
            json.dumps(checksums, sort_keys=True) + "\n", encoding="utf-8"
        )

        with pytest.raises(
            gin_smoke.QualificationError, match="oracle material is forbidden"
        ):
            self._validate(bundle)

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("ground_truth", "secret"),
            ("expected_arms", None),
            ("question_sha256", ""),
        ],
    )
    def test_manifest_schema_is_exact(self, tmp_path: Path, field: str, value: object):
        bundle = self._bundle(tmp_path)
        path = "manifest.json"
        target = bundle / path
        manifest = json.loads(target.read_text(encoding="utf-8"))
        manifest[field] = value
        target.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
        checksums = json.loads((bundle / "checksums.json").read_text(encoding="utf-8"))
        checksums["sha256"][path] = hashlib.sha256(target.read_bytes()).hexdigest()
        (bundle / "checksums.json").write_text(
            json.dumps(checksums, sort_keys=True) + "\n", encoding="utf-8"
        )

        with pytest.raises(gin_smoke.QualificationError, match="invalid manifest"):
            self._validate(bundle)

    def test_external_git_anchor_is_required(self, tmp_path: Path):
        bundle = self._bundle(tmp_path)

        with pytest.raises(
            gin_smoke.QualificationError, match="wrong benchmark Git SHA"
        ):
            self._validate(bundle, git_sha="b" * 40)

    def test_mutable_benchmark_ref_is_rejected(self, tmp_path: Path):
        with pytest.raises(gin_smoke.QualificationError, match="identity fields"):
            gin_smoke.create_bundle(
                tmp_path / "bundle",
                benchmark_git_sha="main",
                repository_path="/fixture/repository",
                repository_commit="b" * 40,
                repository_fingerprint="c" * 64,
                question="Where is the Gin router assembled?",
                model="fixture-model",
                timeout_seconds=60,
            )

    def test_missing_cell_is_rejected(self, tmp_path: Path):
        bundle = self._bundle(tmp_path)
        (bundle / "cells" / "codegraph.json").unlink()

        with pytest.raises(
            gin_smoke.QualificationError,
            match="missing, duplicate, or unexpected",
        ):
            self._validate(bundle)


class TestGinSmokeIndexEvidence:
    def test_go_eligibility_excludes_generated_files(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_evidence import classify_go_paths

        (tmp_path / "gin.go").write_text("package gin\n", encoding="utf-8")
        generated = tmp_path / "test.pb.go"
        generated.write_text(
            "// Code generated by protoc-gen-go. DO NOT EDIT.\npackage gin\n",
            encoding="utf-8",
        )

        eligible, excluded = classify_go_paths(tmp_path, ("gin.go", "test.pb.go"))

        assert eligible == ("gin.go",)
        assert excluded == ("test.pb.go",)

    def test_masked_paths_restore_exclusions_after_failure(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_evidence import masked_paths

        generated = tmp_path / "testdata" / "test.pb.go"
        generated.parent.mkdir()
        generated.write_text("generated", encoding="utf-8")

        with pytest.raises(RuntimeError, match="index failed"):
            with masked_paths(tmp_path, ("testdata/test.pb.go",)):
                assert not generated.exists()
                raise RuntimeError("index failed")

        assert generated.read_text(encoding="utf-8") == "generated"

    def test_index_stats_reject_paths_outside_frozen_eligibility(
        self, monkeypatch, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.smoke_evidence import _build_stats

        cache = tmp_path / ".ast-cache"
        cache.mkdir()
        connection = sqlite3.connect(cache / "index.db")
        connection.execute("CREATE TABLE ast_index (file_path TEXT, symbols_json TEXT)")
        connection.executemany(
            "INSERT INTO ast_index VALUES (?, ?)",
            (("gin.go", "ServeHTTP"), ("unexpected.go", "{}")),
        )
        connection.commit()
        connection.close()
        monkeypatch.setattr(
            "benchmarks.codegraph_compare.smoke_evidence.TSAAdapter.prepare_index",
            lambda self, repo_path, cold: IndexStats(1.0, 10, 2),
        )

        with pytest.raises(
            ValueError,
            match=r"unexpected=\('unexpected.go',\)",
        ):
            _build_stats(
                repo_path=tmp_path,
                arm="tsa-warm",
                eligible_paths=("gin.go",),
                generated_paths=(),
                repo_fingerprint="repo",
                tool_fingerprint="tool",
            )
