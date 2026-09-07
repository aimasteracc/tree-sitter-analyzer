"""Issue #1376：_benchmark_harness_smoke_helpers 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from tests.unit._benchmark_harness_matrix_helpers import _v1_manifest, _v1_run


class TestGinSmokeManifestExecution:
    @staticmethod
    def _tsa_canary_item(call_id: str = "call-001") -> dict:
        payload = {
            "symbol": "Engine.ServeHTTP",
            "definition": {
                "definitions": [
                    {
                        "file": "gin.go",
                        "name": "Engine.ServeHTTP",
                        "kind": "method",
                    }
                ]
            },
        }
        return {
            "id": call_id,
            "type": "mcp_tool_call",
            "status": "completed",
            "server": "tree-sitter-analyzer",
            "tool": "nav",
            "arguments": {
                "action": "navigate",
                "symbol": "Engine.ServeHTTP",
                "file_path": "gin.go",
                "output_format": "json",
            },
            "result": {
                "content": [{"type": "text", "text": json.dumps(payload)}],
                "structured_content": {"untrusted": "not receipt evidence"},
            },
        }

    @staticmethod
    def _legacy_record(manifest, run_id: str, transcript_path: Path) -> dict:
        cell = next(cell for cell in manifest.expected_cells if cell.run_id == run_id)
        return {
            "run_id": cell.run_id,
            "session_id": manifest.primary_session_id,
            "repo": cell.repo,
            "question_id": cell.question_id,
            "arm": cell.arm,
            "repeat": cell.repeat,
            "agent_backend": cell.agent_backend,
            "model": manifest.model,
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
            "transcript_path": str(transcript_path),
            "error": None,
        }


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
