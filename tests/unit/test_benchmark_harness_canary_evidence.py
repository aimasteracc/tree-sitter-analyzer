"""Issue #1376：canary evidence 行为组，保留测试逻辑，文本 I/O 显式使用 UTF-8。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tests.unit._benchmark_harness_smoke_helpers import TestGinSmokeManifestExecution


class TestCanaryEvidence:
    @staticmethod
    def _manifest():
        from benchmarks.codegraph_compare.canary_evidence import create_canary_manifest

        return create_canary_manifest(
            benchmark_git_sha="benchmark-sha",
            benchmark_version="NO1-002C-E0-v1",
            model="gpt-fixture",
            agent_cli_fingerprint="codex-cli-fixture",
            gin_commit="gin-commit",
            gin_source_fingerprint="a" * 64,
            canary_prompt_sha256="b" * 64,
            launch_config_hashes={"tsa-warm": "c" * 64, "codegraph-warm": "d" * 64},
            timeout_seconds=300,
            seed=1195,
        )

    @staticmethod
    def _evidence(manifest, tmp_path):
        from benchmarks.codegraph_compare.canary_evidence import (
            CanaryArtifactV1,
            CanaryAttemptV1,
            CanaryRegistryEventV1,
        )

        attempts = []
        artifacts = []
        for index, cell in enumerate(manifest.cells):
            call_id = f"call-{index}"
            if cell.arm == "tsa-warm":
                item = TestGinSmokeManifestExecution._tsa_canary_item(call_id)
            else:
                item = {
                    "id": call_id,
                    "type": "mcp_tool_call",
                    "status": "completed",
                    "server": "codegraph",
                    "tool": "codegraph_search",
                    "arguments": {
                        "query": "Engine.ServeHTTP",
                        "kind": "method",
                        "limit": 10,
                    },
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": "**ServeHTTP** (method)\n"
                                "func (engine *Engine) ServeHTTP(w http.ResponseWriter, req *http.Request)\n"
                                "gin.go:42",
                            }
                        ]
                    },
                }
            transcript_payload = (
                json.dumps({"type": "item.completed", "item": item}) + "\n"
            ).encode()
            source_inventory = [["gin.go", "a" * 64]]
            audit = {
                "checkout_root": str((tmp_path / f"checkout-{index}").resolve()),
                "head_commit": "e" * 40,
                "tracked_paths": ["gin.go"],
                "repository_fingerprint": "f" * 64,
                "source_before": source_inventory,
                "source_after": source_inventory,
                "runtime_namespace": (
                    ".ast-cache" if cell.arm == "tsa-warm" else ".codegraph"
                ),
                "runtime_before": [],
                "runtime_after": [["index.db", "b" * 64]],
            }
            workspace = hashlib.sha256(
                json.dumps(audit, separators=(",", ":"), sort_keys=True).encode()
            ).hexdigest()
            payloads = {
                "receipt": json.dumps(
                    {"call_id": call_id}, separators=(",", ":"), sort_keys=True
                ).encode(),
                "transcript": transcript_payload,
                "workspace_audit": json.dumps(
                    {
                        "schema_version": 1,
                        "manifest_hash": manifest.manifest_hash,
                        "session_id": "session-001",
                        "run_id": cell.cell_id,
                        "cell_id": cell.cell_id,
                        "arm": cell.arm,
                        "audit_sha256": workspace,
                        "audit": audit,
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode(),
            }
            runtime = hashlib.sha256(f"runtime-{index}".encode()).hexdigest()
            payloads["runtime"] = runtime.encode()
            transcript = hashlib.sha256(payloads["transcript"]).hexdigest()
            attempt = CanaryAttemptV1(
                1,
                manifest.manifest_hash,
                "session-001",
                cell.cell_id,
                cell.cell_id,
                cell.arm,
                1,
                call_id,
                transcript,
                workspace,
                runtime,
                "SUCCESS",
            )
            attempts.append(attempt)
            for kind, payload in payloads.items():
                path = (tmp_path / f"{cell.cell_id}.{kind}").resolve()
                path.write_bytes(payload)
                artifacts.append(
                    CanaryArtifactV1(
                        1,
                        manifest.manifest_hash,
                        "session-001",
                        cell.cell_id,
                        cell.cell_id,
                        cell.arm,
                        kind,
                        hashlib.sha256(payload).hexdigest(),
                        str(path),
                        call_id if kind == "receipt" else None,
                    )
                )
        registry = (
            CanaryRegistryEventV1(
                1,
                manifest.manifest_hash,
                "session-001",
                "COMPLETE",
                "canary_accepted",
                ("tsa-warm-canary", "codegraph-warm-canary"),
            ),
        )
        return tuple(attempts), tuple(artifacts), registry

    def test_manifest_freezes_exact_two_cell_e0_protocol(self):
        from benchmarks.codegraph_compare.canary_evidence import (
            canonical_sha256,
            validate_canary_manifest,
        )

        manifest = self._manifest()
        validate_canary_manifest(manifest)

        assert tuple(
            (
                cell.cell_id,
                cell.arm,
                cell.attempt_count,
                cell.schedule_order,
                cell.phase,
                cell.native_allowed,
            )
            for cell in manifest.cells
        ) == (
            ("tsa-warm-canary", "tsa-warm", 1, 0, "E0", False),
            ("codegraph-warm-canary", "codegraph-warm", 1, 1, "E0", False),
        )
        assert manifest.oracle == ("gin.go", "Engine.ServeHTTP", "method")
        assert manifest.oracle_hash == canonical_sha256(list(manifest.oracle))
        assert manifest.budget_ceiling_usd == 3.0
        assert (manifest.winner, manifest.dominance_allowed, manifest.publishable) == (
            None,
            False,
            False,
        )

    def test_canonical_sha256_is_key_order_independent_and_exact(self):
        from benchmarks.codegraph_compare.canary_evidence import canonical_sha256

        left = canonical_sha256({"b": 2, "a": [1, "x"]})
        right = canonical_sha256({"a": [1, "x"], "b": 2})

        assert (
            left
            == "8cbd548a32262b76a6536efe4e7ba86a0e811fcd0475d83a43e10acd0615aa37"  # pragma: allowlist secret
        )
        assert right == left

    def test_complete_two_cell_evidence_requires_production_trust_anchor(
        self, tmp_path
    ):
        from benchmarks.codegraph_compare.canary_evidence import (
            validate_canary_evidence,
        )

        manifest = self._manifest()
        verdict = validate_canary_evidence(
            manifest, *self._evidence(manifest, tmp_path)
        )

        assert verdict.status == "NOT_EVALUATED"
        assert verdict.violations == ("PRODUCTION_TRUST_ANCHOR_UNAVAILABLE",)
        assert (verdict.accepted_cells, verdict.required_cells) == (2, 2)
        assert (verdict.winner, verdict.dominance_allowed, verdict.publishable) == (
            None,
            False,
            False,
        )

    def test_absent_evidence_is_not_evaluated(self):
        from benchmarks.codegraph_compare.canary_evidence import (
            validate_canary_evidence,
        )

        verdict = validate_canary_evidence(self._manifest(), (), (), ())

        assert verdict.status == "NOT_EVALUATED"
        assert verdict.violations == ()
        assert (verdict.accepted_cells, verdict.required_cells) == (0, 2)
        assert verdict.publishable is False

    def test_tampered_protected_claim_flag_is_invalid_without_evidence(self):
        from dataclasses import replace

        from benchmarks.codegraph_compare.canary_evidence import (
            validate_canary_evidence,
        )

        manifest = replace(self._manifest(), dominance_allowed=True)

        verdict = validate_canary_evidence(manifest, (), (), ())

        assert verdict.status == "INVALID"
        assert verdict.violations == (
            "MANIFEST_INVALID:protected claim flags must remain false/null",
        )
        assert (verdict.winner, verdict.dominance_allowed, verdict.publishable) == (
            None,
            False,
            False,
        )

    def test_malformed_manifest_type_returns_invalid_instead_of_raising(self):
        from benchmarks.codegraph_compare.canary_evidence import (
            validate_canary_evidence,
        )

        verdict = validate_canary_evidence({}, (), (), ())

        assert verdict.status == "INVALID"
        assert verdict.violations == (
            "MANIFEST_INVALID:manifest must be CanaryManifestV1",
        )
        assert (verdict.accepted_cells, verdict.required_cells) == (0, 2)

    @pytest.mark.parametrize("mutation", ("duplicate", "cross-arm"))
    def test_artifact_nonbijection_fails_closed(self, tmp_path, mutation: str):
        from dataclasses import replace

        from benchmarks.codegraph_compare.canary_evidence import (
            validate_canary_evidence,
        )

        manifest = self._manifest()
        attempts, artifacts, registry = self._evidence(manifest, tmp_path)
        mutated = list(artifacts)
        if mutation == "duplicate":
            mutated.append(artifacts[0])
        else:
            mutated[4] = replace(
                mutated[4],
                cell_id="tsa-warm-canary",
                arm="tsa-warm",
                run_id="tsa-warm-canary",
            )

        verdict = validate_canary_evidence(manifest, attempts, mutated, registry)

        assert verdict.status == "INVALID"
        assert "ARTIFACT_BIJECTION:tsa-warm-canary" in verdict.violations
        assert verdict.publishable is False

    def test_attempt_receipt_binding_mismatch_is_invalid(self, tmp_path):
        from dataclasses import replace

        from benchmarks.codegraph_compare.canary_evidence import (
            validate_canary_evidence,
        )

        manifest = self._manifest()
        attempts, artifacts, registry = self._evidence(manifest, tmp_path)
        attempts = (replace(attempts[0], receipt_call_id="call-tampered"), attempts[1])

        verdict = validate_canary_evidence(manifest, attempts, artifacts, registry)

        assert verdict.status == "INVALID"
        assert verdict.violations == ("ARTIFACT_BINDING:tsa-warm-canary",)
        assert verdict.publishable is False

    def test_artifact_digest_cannot_self_attest_tampered_bytes(self, tmp_path):
        from benchmarks.codegraph_compare.canary_evidence import (
            validate_canary_evidence,
        )

        manifest = self._manifest()
        attempts, artifacts, registry = self._evidence(manifest, tmp_path)
        Path(artifacts[0].evidence_path).write_bytes(b"tampered")

        verdict = validate_canary_evidence(manifest, attempts, artifacts, registry)

        assert verdict.status == "INVALID"
        assert verdict.violations == ("ARTIFACT_BINDING:tsa-warm-canary",)

    @pytest.mark.parametrize("mutation", ("no-receipt", "wrong-receiver"))
    def test_transcript_hash_cannot_replace_semantic_replay(
        self, tmp_path, mutation: str
    ):
        from dataclasses import replace

        from benchmarks.codegraph_compare.canary_evidence import (
            validate_canary_evidence,
        )

        manifest = self._manifest()
        attempts, artifacts, registry = self._evidence(manifest, tmp_path)
        transcript = artifacts[1]
        if mutation == "no-receipt":
            payload = b'{"type":"turn.completed"}\n'
        else:
            item = TestGinSmokeManifestExecution._tsa_canary_item("call-0")
            body = json.loads(item["result"]["content"][0]["text"])
            body["symbol"] = "Other.ServeHTTP"
            item["result"]["content"][0]["text"] = json.dumps(body)
            payload = (
                json.dumps({"type": "item.completed", "item": item}) + "\n"
            ).encode()
        Path(transcript.evidence_path).write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        attempts = (replace(attempts[0], transcript_sha256=digest), attempts[1])
        artifacts = tuple(
            replace(artifact, sha256=digest) if artifact is transcript else artifact
            for artifact in artifacts
        )

        verdict = validate_canary_evidence(manifest, attempts, artifacts, registry)

        assert verdict.status == "INVALID"
        assert verdict.violations == ("ARTIFACT_BINDING:tsa-warm-canary",)

    def test_workspace_hash_cannot_replace_schema_binding(self, tmp_path):
        from dataclasses import replace

        from benchmarks.codegraph_compare.canary_evidence import (
            validate_canary_evidence,
        )

        manifest = self._manifest()
        attempts, artifacts, registry = self._evidence(manifest, tmp_path)
        workspace = artifacts[2]
        payload = b'{"audit_sha256":"arbitrary"}'
        Path(workspace.evidence_path).write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        artifacts = tuple(
            replace(artifact, sha256=digest) if artifact is workspace else artifact
            for artifact in artifacts
        )

        verdict = validate_canary_evidence(manifest, attempts, artifacts, registry)

        assert verdict.status == "INVALID"
        assert verdict.violations == ("ARTIFACT_BINDING:tsa-warm-canary",)

    def test_workspace_arbitrary_self_hash_cannot_replace_raw_audit(self, tmp_path):
        from dataclasses import replace

        from benchmarks.codegraph_compare.canary_evidence import (
            validate_canary_evidence,
        )

        manifest = self._manifest()
        attempts, artifacts, registry = self._evidence(manifest, tmp_path)
        workspace = artifacts[2]
        envelope = json.loads(Path(workspace.evidence_path).read_text(encoding="utf-8"))
        envelope["audit_sha256"] = "f" * 64
        payload = json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode()
        Path(workspace.evidence_path).write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        attempts = (replace(attempts[0], workspace_audit_sha256="f" * 64), attempts[1])
        artifacts = tuple(
            replace(artifact, sha256=digest) if artifact is workspace else artifact
            for artifact in artifacts
        )

        verdict = validate_canary_evidence(manifest, attempts, artifacts, registry)

        assert verdict.status == "INVALID"
        assert verdict.violations == ("ARTIFACT_BINDING:tsa-warm-canary",)

    def test_synchronized_raw_audit_rehash_never_unlocks_accept(self, tmp_path):
        from dataclasses import replace

        from benchmarks.codegraph_compare.canary_evidence import (
            validate_canary_evidence,
        )

        manifest = self._manifest()
        attempts, artifacts, registry = self._evidence(manifest, tmp_path)
        workspace = artifacts[2]
        envelope = json.loads(Path(workspace.evidence_path).read_text(encoding="utf-8"))
        envelope["audit"]["head_commit"] = "d" * 40
        audit_hash = hashlib.sha256(
            json.dumps(
                envelope["audit"], separators=(",", ":"), sort_keys=True
            ).encode()
        ).hexdigest()
        envelope["audit_sha256"] = audit_hash
        payload = json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode()
        Path(workspace.evidence_path).write_bytes(payload)
        artifact_hash = hashlib.sha256(payload).hexdigest()
        attempts = (
            replace(attempts[0], workspace_audit_sha256=audit_hash),
            attempts[1],
        )
        artifacts = tuple(
            (
                replace(artifact, sha256=artifact_hash)
                if artifact is workspace
                else artifact
            )
            for artifact in artifacts
        )

        verdict = validate_canary_evidence(manifest, attempts, artifacts, registry)

        assert verdict.status == "NOT_EVALUATED"
        assert verdict.violations == ("PRODUCTION_TRUST_ANCHOR_UNAVAILABLE",)
        assert verdict.publishable is False

    @pytest.mark.parametrize("launches", (None, [], "not-a-tuple"))
    def test_malformed_manifest_launch_config_type_is_invalid(self, launches):
        from dataclasses import replace

        from benchmarks.codegraph_compare.canary_evidence import (
            validate_canary_evidence,
        )

        verdict = validate_canary_evidence(
            replace(self._manifest(), launch_config_hashes=launches), (), (), ()
        )

        assert verdict.status == "INVALID"
        assert verdict.violations == (
            "MANIFEST_INVALID:launch_config_hashes must be a tuple",
        )

    @pytest.mark.parametrize(
        ("field", "value", "message"),
        (
            ("schema_version", True, "unsupported canary manifest schema"),
            ("timeout_seconds", True, "timeout_seconds must be a positive integer"),
            ("seed", False, "seed must be a non-negative integer"),
            ("budget_ceiling_usd", 3, "budget ceiling mismatch"),
            ("dominance_allowed", 0, "protected claim flags must remain false/null"),
            ("publishable", 0, "protected claim flags must remain false/null"),
        ),
    )
    def test_manifest_rejects_bool_integer_type_confusion(self, field, value, message):
        from dataclasses import replace

        from benchmarks.codegraph_compare.canary_evidence import (
            validate_canary_evidence,
        )

        verdict = validate_canary_evidence(
            replace(self._manifest(), **{field: value}), (), (), ()
        )

        assert verdict.status == "INVALID"
        assert verdict.violations == (f"MANIFEST_INVALID:{message}",)

    @pytest.mark.parametrize("invalid_artifact", (object(), {"kind": "receipt"}))
    def test_invalid_artifact_schema_fails_closed(
        self, tmp_path, invalid_artifact: object
    ):
        from benchmarks.codegraph_compare.canary_evidence import (
            validate_canary_evidence,
        )

        manifest = self._manifest()
        attempts, artifacts, registry = self._evidence(manifest, tmp_path)

        verdict = validate_canary_evidence(
            manifest, attempts, (*artifacts, invalid_artifact), registry
        )

        assert verdict.status == "INVALID"
        assert verdict.violations == ("ARTIFACT_SCHEMA_INVALID",)
        assert verdict.publishable is False

    def test_extra_registry_event_is_invalid(self, tmp_path):
        from dataclasses import replace

        from benchmarks.codegraph_compare.canary_evidence import (
            validate_canary_evidence,
        )

        manifest = self._manifest()
        attempts, artifacts, registry = self._evidence(manifest, tmp_path)
        registry = (*registry, replace(registry[0], outcome="late_event"))

        verdict = validate_canary_evidence(manifest, attempts, artifacts, registry)

        assert verdict.status == "INVALID"
        assert verdict.violations == ("REGISTRY_TERMINAL_INVALID",)
        assert verdict.publishable is False
