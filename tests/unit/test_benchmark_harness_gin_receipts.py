"""Issue #1376：test_benchmark_harness_gin_receipts 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.unit._benchmark_harness_smoke_helpers import (
    TestGinSmokeManifestExecution as _TestGinSmokeManifestExecution,
)


class TestGinSmokeManifestExecution(_TestGinSmokeManifestExecution):
    def test_codex_transcript_accepts_only_the_declared_index_server(
        self, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.smoke_execution import (
            audit_codex_transcript,
        )

        transcript = tmp_path / "tsa.jsonl"
        transcript.write_text(
            "\n".join(
                (
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
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {
                                "type": "command_execution",
                                "command": "grep -n ServeHTTP gin.go",
                            },
                        }
                    ),
                )
            ),
            encoding="utf-8",
        )

        audit = audit_codex_transcript(transcript, "tsa-warm")

        assert audit.violations == ()
        assert audit.observed_mcp_servers == ("tree-sitter-analyzer",)
        assert audit.observed_mcp_tools == ("nav",)

    @pytest.mark.parametrize(
        "failure",
        (
            {"status": "failed"},
            {"error": {"message": "server unavailable"}},
            {"isError": True},
            {"result": {"isError": True}},
            {"result": {"is_error": True}},
        ),
    )
    def test_codex_transcript_rejects_failed_index_query(
        self, tmp_path: Path, failure: dict
    ):
        from benchmarks.codegraph_compare.smoke_execution import (
            audit_codex_transcript,
        )

        transcript = tmp_path / "failed-mcp.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "type": "mcp_tool_call",
                        "server": "tree-sitter-analyzer",
                        "tool": "nav",
                        **failure,
                    },
                }
            ),
            encoding="utf-8",
        )

        audit = audit_codex_transcript(transcript, "tsa-warm")

        assert audit.violations == ("MCP_CALL_FAILED:1", "MISSING_INDEX_QUERY")

    def test_codex_transcript_does_not_accept_started_index_query(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_execution import (
            audit_codex_transcript,
        )

        transcript = tmp_path / "started-mcp.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "type": "item.started",
                    "item": {
                        "type": "mcp_tool_call",
                        "server": "tree-sitter-analyzer",
                        "tool": "nav",
                    },
                }
            ),
            encoding="utf-8",
        )

        audit = audit_codex_transcript(transcript, "tsa-warm")

        assert audit.violations == ("MISSING_INDEX_QUERY",)
        assert audit.observed_mcp_servers == ()

    def test_codex_transcript_rejects_mutating_tsa_index_tool(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_execution import (
            audit_codex_transcript,
        )

        transcript = tmp_path / "mutating-index.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "type": "mcp_tool_call",
                        "server": "tree-sitter-analyzer",
                        "tool": "index",
                    },
                }
            ),
            encoding="utf-8",
        )

        audit = audit_codex_transcript(transcript, "tsa-warm")

        assert audit.violations == (
            "MUTATING_INDEX_TOOL:1",
            "MISSING_INDEX_QUERY",
        )

    def test_codex_transcript_rejects_cross_arm_mcp(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_execution import (
            audit_codex_transcript,
        )

        transcript = tmp_path / "cross-arm.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "type": "mcp_tool_call",
                        "server": "codegraph",
                        "tool": "codegraph_search",
                    },
                }
            ),
            encoding="utf-8",
        )

        audit = audit_codex_transcript(transcript, "tsa-warm")

        assert audit.violations == ("CROSS_ARM_MCP:1", "MISSING_INDEX_QUERY")

    def test_canary_transcript_binds_exact_mcp_receipt(self, tmp_path: Path):
        from benchmarks.codegraph_compare.canary_policy import audit_canary_transcript

        transcript = tmp_path / "canary.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": self._tsa_canary_item(),
                }
            )
            + "\n",
            encoding="utf-8",
        )

        audit = audit_canary_transcript(
            transcript,
            "tsa-warm",
            expected_tool="nav",
            expected_path="gin.go",
            expected_symbol="Engine.ServeHTTP",
            expected_kind="method",
        )

        assert audit.violations == ()
        assert audit.receipt is not None
        assert audit.receipt.call_id == "call-001"
        assert audit.receipt.repository_relative_path == "gin.go"
        assert audit.receipt.symbol_identity == "Engine.ServeHTTP"
        assert audit.receipt.symbol_kind == "method"

    @pytest.mark.parametrize(
        "arguments",
        (
            {
                "action": "navigate",
                "symbol": "Engine.ServeHTTP",
                "file_path": "gin.go",
            },
            {
                "action": "navigate",
                "symbol": "Engine.ServeHTTP",
                "file_path": "gin.go",
                "output_format": "toon",
            },
            {
                "action": "resolve",
                "symbol": "Engine.ServeHTTP",
                "file_path": "gin.go",
                "output_format": "json",
            },
        ),
    )
    def test_canary_transcript_rejects_nonexact_tsa_arguments(
        self, tmp_path: Path, arguments: dict
    ):
        from benchmarks.codegraph_compare.canary_policy import audit_canary_transcript

        item = {**self._tsa_canary_item(), "arguments": arguments}
        transcript = tmp_path / "wrong-tsa-arguments.jsonl"
        transcript.write_text(
            json.dumps({"type": "item.completed", "item": item}) + "\n",
            encoding="utf-8",
        )

        audit = audit_canary_transcript(
            transcript,
            "tsa-warm",
            expected_tool="nav",
            expected_path="gin.go",
            expected_symbol="Engine.ServeHTTP",
            expected_kind="method",
        )

        assert audit.violations == (
            "CANARY_ARGUMENTS_MISMATCH:1",
            "CANARY_RECEIPT_MISSING",
        )
        assert audit.receipt is None

    @pytest.mark.parametrize(
        ("mutation", "violation"),
        (
            ({"tool": "unknown"}, "CANARY_TOOL_MISMATCH:1"),
            ({"id": ""}, "CANARY_RECEIPT_INVALID:1"),
            ({"result": {}}, "CANARY_RECEIPT_INVALID:1"),
            ({"status": "started"}, "CANARY_RECEIPT_INVALID:1"),
            ({"status": None}, "CANARY_RECEIPT_INVALID:1"),
        ),
    )
    def test_canary_transcript_rejects_ambiguous_mcp_success(
        self, tmp_path: Path, mutation: dict, violation: str
    ):
        from benchmarks.codegraph_compare.canary_policy import audit_canary_transcript

        item = {**self._tsa_canary_item(), **mutation}
        transcript = tmp_path / "ambiguous-canary.jsonl"
        transcript.write_text(
            json.dumps({"type": "item.completed", "item": item}) + "\n",
            encoding="utf-8",
        )

        audit = audit_canary_transcript(
            transcript,
            "tsa-warm",
            expected_tool="nav",
            expected_path="gin.go",
            expected_symbol="Engine.ServeHTTP",
            expected_kind="method",
        )

        assert audit.violations == (violation, "CANARY_RECEIPT_MISSING")
        assert audit.receipt is None

    def test_canary_transcript_rejects_started_item_shape(self, tmp_path: Path):
        from benchmarks.codegraph_compare.canary_policy import audit_canary_transcript

        item = {**self._tsa_canary_item(), "status": "in_progress"}
        transcript = tmp_path / "started-canary.jsonl"
        transcript.write_text(
            json.dumps({"type": "item.started", "item": item}) + "\n",
            encoding="utf-8",
        )

        audit = audit_canary_transcript(
            transcript,
            "tsa-warm",
            expected_tool="nav",
            expected_path="gin.go",
            expected_symbol="Engine.ServeHTTP",
            expected_kind="method",
        )

        assert audit.violations == ("MISSING_INDEX_QUERY", "CANARY_RECEIPT_MISSING")
        assert audit.receipt is None

    def test_canary_transcript_rejects_failed_item_status(self, tmp_path: Path):
        from benchmarks.codegraph_compare.canary_policy import audit_canary_transcript

        item = {**self._tsa_canary_item(), "status": "failed"}
        transcript = tmp_path / "failed-canary.jsonl"
        transcript.write_text(
            json.dumps({"type": "item.completed", "item": item}) + "\n",
            encoding="utf-8",
        )

        audit = audit_canary_transcript(
            transcript,
            "tsa-warm",
            expected_tool="nav",
            expected_path="gin.go",
            expected_symbol="Engine.ServeHTTP",
            expected_kind="method",
        )

        assert audit.violations == (
            "MCP_CALL_FAILED:1",
            "MISSING_INDEX_QUERY",
            "CANARY_RECEIPT_MISSING",
        )
        assert audit.receipt is None

    def test_canary_transcript_rejects_wrong_tsa_definition(self, tmp_path: Path):
        from benchmarks.codegraph_compare.canary_policy import audit_canary_transcript

        item = self._tsa_canary_item()
        payload = json.loads(item["result"]["content"][0]["text"])
        payload["definition"]["definitions"][0]["file"] = "tree.go"
        item["result"]["content"][0]["text"] = json.dumps(payload)
        transcript = tmp_path / "wrong-tsa-definition.jsonl"
        transcript.write_text(
            json.dumps({"type": "item.completed", "item": item}) + "\n",
            encoding="utf-8",
        )

        audit = audit_canary_transcript(
            transcript,
            "tsa-warm",
            expected_tool="nav",
            expected_path="gin.go",
            expected_symbol="Engine.ServeHTTP",
            expected_kind="method",
        )

        assert audit.violations == (
            "CANARY_EVIDENCE_MISMATCH:1",
            "CANARY_RECEIPT_MISSING",
        )
        assert audit.receipt is None

    def test_canary_transcript_rejects_multiple_exact_receipts(self, tmp_path: Path):
        from benchmarks.codegraph_compare.canary_policy import audit_canary_transcript

        def event(call_id: str) -> str:
            return json.dumps(
                {
                    "type": "item.completed",
                    "item": self._tsa_canary_item(call_id),
                }
            )

        transcript = tmp_path / "duplicate-receipts.jsonl"
        transcript.write_text(
            event("call-001") + "\n" + event("call-002") + "\n",
            encoding="utf-8",
        )

        audit = audit_canary_transcript(
            transcript,
            "tsa-warm",
            expected_tool="nav",
            expected_path="gin.go",
            expected_symbol="Engine.ServeHTTP",
            expected_kind="method",
        )

        assert audit.violations == ("CANARY_RECEIPT_AMBIGUOUS",)
        assert audit.receipt is None
