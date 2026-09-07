"""Issue #1376：Gin bundle 行为组，保留测试逻辑，文本 I/O 显式使用 UTF-8。"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from tests.unit._benchmark_harness_matrix_helpers import _v1_manifest, _v1_run


class TestGinSmokeBundle:
    @staticmethod
    def _bundle_inputs(tmp_path: Path):
        from dataclasses import asdict

        from benchmarks.codegraph_compare.integrity import RegistryEvent
        from benchmarks.codegraph_compare.smoke_policy import PolicyAudit

        manifest = _v1_manifest(
            index_content_hashes={
                "codegraph-warm": "codegraph-index-hash",
                "tsa-warm": "tsa-index-hash",
            },
        )
        plan = tmp_path / "plan-source"
        plan.mkdir()
        (plan / "experiment-manifest.json").write_text(
            json.dumps(asdict(manifest)), encoding="utf-8"
        )
        from benchmarks.codegraph_compare.smoke_preflight import SENTINEL

        (plan / "model-preflight.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "PASSED",
                    "provider": "OpenAI",
                    "account_surface": "ChatGPT",
                    "model": manifest.model,
                    "checked_at": "2026-07-31T00:00:00+00:00",
                    "agent_cli": {},
                    "agent_cli_fingerprint": manifest.agent_cli_fingerprint,
                    "sentinel_sha256": hashlib.sha256(SENTINEL.encode()).hexdigest(),
                }
            ),
            encoding="utf-8",
        )
        (plan / "arm-tool-preflight.json").write_text(
            json.dumps(
                {
                    arm: {
                        "server": server,
                        "enabled": True,
                        "command": sys.executable,
                        "args": ["serve", "--mcp"],
                    }
                    for arm, server in {
                        "tsa-warm": "tree-sitter-analyzer",
                        "codegraph-warm": "codegraph",
                    }.items()
                }
            ),
            encoding="utf-8",
        )
        for name in (
            "eligibility.json",
            "index-evidence.json",
            "workspace-evidence.json",
        ):
            (plan / name).write_text("{}\n", encoding="utf-8")
        experiment = tmp_path / "experiment"
        experiment.mkdir()
        runs = []
        servers = {
            "codegraph-warm": "codegraph",
            "tsa-warm": "tree-sitter-analyzer",
        }
        for cell in manifest.expected_cells:
            transcript_path = f"/original/{cell.run_id}.jsonl"
            transcript = (
                plan / "artifacts" / cell.arm / "raw" / Path(transcript_path).name
            )
            transcript.parent.mkdir(parents=True)
            transcript.write_text(
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "mcp_tool_call",
                            "server": servers[cell.arm],
                            "tool": "query",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            run = _v1_run(manifest, cell.run_id, transcript_path=transcript_path)
            runs.append(run)
            (experiment / f"policy_{cell.run_id}.json").write_text(
                json.dumps(
                    asdict(
                        PolicyAudit(
                            cell.arm,
                            transcript_path,
                            (servers[cell.arm],),
                            ("query",),
                            (),
                        )
                    )
                )
                + "\n",
                encoding="utf-8",
            )
        (experiment / "runs.jsonl").write_text(
            "".join(json.dumps(asdict(run)) + "\n" for run in runs),
            encoding="utf-8",
        )
        registry = tmp_path / "registry.jsonl"
        events = (
            RegistryEvent(
                manifest.experiment_id,
                manifest.manifest_hash,
                "RUNNING",
                "smoke_started",
            ),
            RegistryEvent(
                manifest.experiment_id,
                manifest.manifest_hash,
                "INVALID",
                "smoke_invalid",
            ),
        )
        registry.write_text(
            "".join(json.dumps(asdict(event)) + "\n" for event in events),
            encoding="utf-8",
        )
        return plan, experiment, registry

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

        # Issue #1219: every retained runtime audit must bind to an exact run.
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
        # Issue #1201: immutable INVALID evidence predates transcript retention.
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

        # Issue #1219: evidence fallback replaces the earlier runtime policy audit.
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

        # Issue #1219: product failures remain bound to runtime policy evidence.
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

        # Issue #1219: a policy marker cannot self-authorize runtime evidence.
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

        # Issue #1219: runtime terminal evidence must remain bundleable.
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
