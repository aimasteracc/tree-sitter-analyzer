"""Issue #1376：test_benchmark_harness_gin_bundle 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.unit._benchmark_harness_smoke_helpers import (
    TestGinSmokeBundle as _TestGinSmokeBundle,
)


class TestGinSmokeBundle(_TestGinSmokeBundle):
    def test_bundle_recomputes_invalid_claim_bounded_verdict(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_bundle import (
            create_smoke_bundle,
            validate_smoke_bundle,
        )

        plan, experiment, registry = self._bundle_inputs(tmp_path)
        bundle = tmp_path / "bundle"
        digest = create_smoke_bundle(
            bundle,
            plan_dir=plan,
            experiment_dir=experiment,
            registry_path=registry,
        )

        verdict = validate_smoke_bundle(bundle, external_digest=digest)

        assert verdict["claim_level"] == "INVALID"
        assert verdict["dominance_allowed"] is False
        assert verdict["winner"] is None

    def test_bundle_rejects_orphan_runtime_evidence(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_bundle import create_smoke_bundle

        plan, experiment, registry = self._bundle_inputs(tmp_path)
        (experiment / "runtime_index_unknown-run.json").write_text(
            "{}\n", encoding="utf-8"
        )

        # Issue #1219: 每份留存的运行时审计都必须绑定精确的运行实例。
        with pytest.raises(ValueError, match="runtime evidence inventory mismatch"):
            create_smoke_bundle(
                tmp_path / "bundle",
                plan_dir=plan,
                experiment_dir=experiment,
                registry_path=registry,
            )

    def test_bundle_accepts_bound_legacy_terminal_exception(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_bundle import create_smoke_bundle

        plan, experiment, registry = self._bundle_inputs(tmp_path)
        runs_path = experiment / "runs.jsonl"
        runs = [
            json.loads(line)
            for line in runs_path.read_text(encoding="utf-8").splitlines()
        ]
        run = runs[0]
        violations = [
            "EXECUTION_EXCEPTION:ValueError",
            "TRANSCRIPT_MISSING",
        ]
        run["status"] = "INVALID"
        run["answer"] = "ERROR"
        run["transcript_path"] = ""
        run["blocker_reason"] = "POLICY_AUDIT:" + ",".join(violations)
        runs_path.write_text(
            "".join(json.dumps(item) + "\n" for item in runs),
            encoding="utf-8",
        )
        policy_path = experiment / f"policy_{run['run_id']}.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["transcript_path"] = ""
        policy["observed_mcp_servers"] = []
        policy["observed_mcp_tools"] = []
        policy["violations"] = violations
        policy_path.write_text(json.dumps(policy) + "\n", encoding="utf-8")
        # Issue #1201: 不可变的 INVALID 证据早于 transcript 留存机制。
        digest = create_smoke_bundle(
            tmp_path / "bundle",
            plan_dir=plan,
            experiment_dir=experiment,
            registry_path=registry,
        )

        assert len(digest) == 64

    def test_bundle_accepts_evidence_fallback_after_runtime_failure(
        self, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.smoke_bundle import create_smoke_bundle

        plan, experiment, registry = self._bundle_inputs(tmp_path)
        runs_path = experiment / "runs.jsonl"
        runs = [
            json.loads(line)
            for line in runs_path.read_text(encoding="utf-8").splitlines()
        ]
        run = runs[0]
        violations = ["EVIDENCE_EXCEPTION:ValueError", "TRANSCRIPT_MISSING"]
        run["status"] = "INVALID"
        run["answer"] = "ERROR"
        run["transcript_path"] = ""
        run["blocker_reason"] = "POLICY_AUDIT:" + ",".join(violations)
        runs_path.write_text(
            "".join(json.dumps(item) + "\n" for item in runs), encoding="utf-8"
        )
        policy_path = experiment / f"policy_{run['run_id']}.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy.update(
            transcript_path="",
            observed_mcp_servers=[],
            observed_mcp_tools=[],
            violations=violations,
        )
        policy_path.write_text(json.dumps(policy) + "\n", encoding="utf-8")
        manifest = json.loads(
            (plan / "experiment-manifest.json").read_text(encoding="utf-8")
        )
        expected_hash = dict(manifest["index_content_hashes"])[run["arm"]]
        expected_paths = run["index_stats"]["indexed_paths"]
        (experiment / f"runtime_index_{run['run_id']}.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "experiment_id": run["experiment_id"],
                    "manifest_hash": manifest["manifest_hash"],
                    "session_id": run["session_id"],
                    "run_id": run["run_id"],
                    "repo": run["repo"],
                    "arm": run["arm"],
                    "repeat": run["repeat"],
                    "expected_hash": expected_hash,
                    "expected_paths": expected_paths,
                    "failure_codes": ["RUNTIME_SEMANTIC_DRIFT"],
                    "materialized": True,
                    "runtime_hash_before": expected_hash,
                    "runtime_hash_after": expected_hash,
                    "runtime_mutated": False,
                    "semantic_digest_before": "before-digest",
                    "semantic_digest_after": "after-digest",
                    "post_paths": expected_paths,
                    "frozen_hash_after": expected_hash,
                    "cleanup_status": "SUCCESS",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        # Issue #1219: 证据回退会替换先前的运行时策略审计。
        digest = create_smoke_bundle(
            tmp_path / "bundle",
            plan_dir=plan,
            experiment_dir=experiment,
            registry_path=registry,
        )

        assert len(digest) == 64

        runtime_path = experiment / f"runtime_index_{run['run_id']}.json"
        valid_runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        for name, mutation, message in (
            ("wrong-paths", {"expected_paths": ["unrelated.go"]}, "path mismatch"),
            (
                "wrong-baseline",
                {"runtime_hash_before": "wrong"},
                "measurement mismatch",
            ),
            ("wrong-mutated", {"runtime_mutated": True}, "measurement mismatch"),
        ):
            runtime_path.write_text(
                json.dumps({**valid_runtime, **mutation}) + "\n", encoding="utf-8"
            )
            with pytest.raises(ValueError, match=message):
                create_smoke_bundle(
                    tmp_path / f"bundle-{name}",
                    plan_dir=plan,
                    experiment_dir=experiment,
                    registry_path=registry,
                )

    def test_bundle_accepts_runtime_marker_with_product_failure(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_bundle import create_smoke_bundle

        plan, experiment, registry = self._bundle_inputs(tmp_path)
        runs_path = experiment / "runs.jsonl"
        runs = [
            json.loads(line)
            for line in runs_path.read_text(encoding="utf-8").splitlines()
        ]
        run = runs[0]
        policy_path = experiment / f"policy_{run['run_id']}.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        marker = "RUNTIME_CLEANUP_FAILED:OSError"
        policy["violations"] = [marker, *policy["violations"]]
        policy_path.write_text(json.dumps(policy) + "\n", encoding="utf-8")
        run["status"] = "INVALID"
        run["blocker_reason"] = (
            "POLICY_AUDIT:"
            + ",".join(policy["violations"])
            + ";PRODUCT_FAILURE:backend unavailable"
        )
        runs_path.write_text(
            "".join(json.dumps(item) + "\n" for item in runs), encoding="utf-8"
        )
        manifest = json.loads(
            (plan / "experiment-manifest.json").read_text(encoding="utf-8")
        )
        expected_hash = dict(manifest["index_content_hashes"])[run["arm"]]
        expected_paths = run["index_stats"]["indexed_paths"]
        (experiment / f"runtime_index_{run['run_id']}.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "experiment_id": run["experiment_id"],
                    "manifest_hash": manifest["manifest_hash"],
                    "session_id": run["session_id"],
                    "run_id": run["run_id"],
                    "repo": run["repo"],
                    "arm": run["arm"],
                    "repeat": run["repeat"],
                    "expected_hash": expected_hash,
                    "expected_paths": expected_paths,
                    "failure_codes": [marker],
                    "materialized": True,
                    "runtime_hash_before": expected_hash,
                    "runtime_hash_after": expected_hash,
                    "runtime_mutated": False,
                    "semantic_digest_before": "same-digest",
                    "semantic_digest_after": "same-digest",
                    "post_paths": expected_paths,
                    "frozen_hash_after": expected_hash,
                    "cleanup_status": "FAILED",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        # Issue #1219: 产品失败仍须绑定运行时策略证据。
        digest = create_smoke_bundle(
            tmp_path / "bundle",
            plan_dir=plan,
            experiment_dir=experiment,
            registry_path=registry,
        )

        assert len(digest) == 64

    def test_bundle_rejects_runtime_marker_contradicting_audit(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_bundle import create_smoke_bundle

        plan, experiment, registry = self._bundle_inputs(tmp_path)
        runs_path = experiment / "runs.jsonl"
        runs = [
            json.loads(line)
            for line in runs_path.read_text(encoding="utf-8").splitlines()
        ]
        run = runs[0]
        policy_path = experiment / f"policy_{run['run_id']}.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        marker = "RUNTIME_POST_AUDIT_FAILED:ValueError"
        policy["violations"] = [marker, *policy["violations"]]
        policy_path.write_text(json.dumps(policy) + "\n", encoding="utf-8")
        run["status"] = "INVALID"
        run["blocker_reason"] = "POLICY_AUDIT:" + ",".join(policy["violations"])
        runs_path.write_text(
            "".join(json.dumps(item) + "\n" for item in runs), encoding="utf-8"
        )
        manifest = json.loads(
            (plan / "experiment-manifest.json").read_text(encoding="utf-8")
        )
        expected_hash = dict(manifest["index_content_hashes"])[run["arm"]]
        expected_paths = run["index_stats"]["indexed_paths"]
        (experiment / f"runtime_index_{run['run_id']}.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "experiment_id": run["experiment_id"],
                    "manifest_hash": manifest["manifest_hash"],
                    "session_id": run["session_id"],
                    "run_id": run["run_id"],
                    "repo": run["repo"],
                    "arm": run["arm"],
                    "repeat": run["repeat"],
                    "expected_hash": expected_hash,
                    "expected_paths": expected_paths,
                    "failure_codes": [marker],
                    "materialized": True,
                    "runtime_hash_before": expected_hash,
                    "runtime_hash_after": expected_hash,
                    "runtime_mutated": False,
                    "semantic_digest_before": "original-digest",
                    "semantic_digest_after": "unexpected-digest",
                    "post_paths": expected_paths,
                    "frozen_hash_after": expected_hash,
                    "cleanup_status": "SUCCESS",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        # Issue #1219: 策略标记不能自行授权运行时证据。
        with pytest.raises(ValueError, match="runtime evidence measurement mismatch"):
            create_smoke_bundle(
                tmp_path / "bundle",
                plan_dir=plan,
                experiment_dir=experiment,
                registry_path=registry,
            )

    def test_bundle_accepts_bound_runtime_post_audit_failure(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_bundle import create_smoke_bundle

        plan, experiment, registry = self._bundle_inputs(tmp_path)
        runs_path = experiment / "runs.jsonl"
        runs = [
            json.loads(line)
            for line in runs_path.read_text(encoding="utf-8").splitlines()
        ]
        run = runs[0]
        policy_path = experiment / f"policy_{run['run_id']}.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        violations = ["RUNTIME_POST_AUDIT_FAILED:ValueError", "TRANSCRIPT_MISSING"]
        run["status"] = "INVALID"
        run["answer"] = "retained backend answer"
        run["transcript_path"] = ""
        run["blocker_reason"] = "POLICY_AUDIT:" + ",".join(violations)
        runs_path.write_text(
            "".join(json.dumps(item) + "\n" for item in runs),
            encoding="utf-8",
        )
        policy.update(
            transcript_path="",
            observed_mcp_servers=[],
            observed_mcp_tools=[],
            violations=violations,
        )
        policy_path.write_text(json.dumps(policy) + "\n", encoding="utf-8")
        manifest = json.loads(
            (plan / "experiment-manifest.json").read_text(encoding="utf-8")
        )
        expected_hash = dict(manifest["index_content_hashes"])[run["arm"]]
        expected_paths = run["index_stats"]["indexed_paths"]
        (experiment / f"runtime_index_{run['run_id']}.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "experiment_id": run["experiment_id"],
                    "manifest_hash": manifest["manifest_hash"],
                    "session_id": run["session_id"],
                    "run_id": run["run_id"],
                    "repo": run["repo"],
                    "arm": run["arm"],
                    "repeat": run["repeat"],
                    "expected_hash": expected_hash,
                    "expected_paths": expected_paths,
                    "failure_codes": [violations[0]],
                    "materialized": True,
                    "runtime_hash_before": expected_hash,
                    "runtime_hash_after": expected_hash,
                    "runtime_mutated": False,
                    "semantic_digest_before": "original-digest",
                    "semantic_digest_after": None,
                    "post_paths": None,
                    "frozen_hash_after": expected_hash,
                    "cleanup_status": "SUCCESS",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        # Issue #1219: 运行时终态证据必须仍可打包。
        digest = create_smoke_bundle(
            tmp_path / "bundle",
            plan_dir=plan,
            experiment_dir=experiment,
            registry_path=registry,
        )

        assert len(digest) == 64

    def test_bundle_replay_is_byte_identical(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_bundle import (
            create_smoke_bundle,
            replay_smoke_bundle,
        )

        plan, experiment, registry = self._bundle_inputs(tmp_path)
        bundle = tmp_path / "bundle"
        digest = create_smoke_bundle(
            bundle,
            plan_dir=plan,
            experiment_dir=experiment,
            registry_path=registry,
        )

        replay_smoke_bundle(bundle, tmp_path / "replay", external_digest=digest)

        assert {
            path.relative_to(bundle): path.read_bytes()
            for path in bundle.rglob("*")
            if path.is_file()
        } == {
            path.relative_to(tmp_path / "replay"): path.read_bytes()
            for path in (tmp_path / "replay").rglob("*")
            if path.is_file()
        }

    def test_bundle_rejects_tampering_against_external_digest(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_bundle import (
            create_smoke_bundle,
            validate_smoke_bundle,
        )

        plan, experiment, registry = self._bundle_inputs(tmp_path)
        bundle = tmp_path / "bundle"
        digest = create_smoke_bundle(
            bundle,
            plan_dir=plan,
            experiment_dir=experiment,
            registry_path=registry,
        )
        (bundle / "evidence" / "runs.jsonl").write_text("tampered\n", encoding="utf-8")

        with pytest.raises(ValueError, match="bundle checksum mismatch"):
            validate_smoke_bundle(bundle, external_digest=digest)

    def test_bundle_reaudits_transcript_instead_of_trusting_policy_file(
        self, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.smoke_bundle import (
            create_smoke_bundle,
        )

        plan, experiment, registry = self._bundle_inputs(tmp_path)
        transcript = next((plan / "artifacts").rglob("*.jsonl"))
        transcript.write_text(
            json.dumps(
                {
                    "item": {
                        "type": "command_execution",
                        "command": "curl https://example.com",
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="policy audit mismatch"):
            create_smoke_bundle(
                tmp_path / "bundle",
                plan_dir=plan,
                experiment_dir=experiment,
                registry_path=registry,
            )
