"""Issue #1376：test_benchmark_harness_gin_codegraph_receipts 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.unit._benchmark_harness_smoke_helpers import (
    TestGinSmokeManifestExecution as _TestGinSmokeManifestExecution,
)


class TestGinSmokeManifestExecution(_TestGinSmokeManifestExecution):
    def test_canary_transcript_binds_codegraph_markdown_receipt(self, tmp_path: Path):
        from benchmarks.codegraph_compare.canary_policy import audit_canary_transcript

        markdown = (
            "**ServeHTTP** (method)\n"
            "func (engine *Engine) ServeHTTP(w http.ResponseWriter, req *http.Request)\n"
            "gin.go:688"
        )
        transcript = tmp_path / "wrong-symbol.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "call-001",
                        "type": "mcp_tool_call",
                        "status": "completed",
                        "server": "codegraph",
                        "tool": "codegraph_search",
                        "arguments": {
                            "query": "Engine.ServeHTTP",
                            "kind": "method",
                            "limit": 10,
                        },
                        "result": {"content": [{"type": "text", "text": markdown}]},
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )

        audit = audit_canary_transcript(
            transcript,
            "codegraph-warm",
            expected_tool="codegraph_search",
            expected_path="gin.go",
            expected_symbol="Engine.ServeHTTP",
            expected_kind="method",
        )

        assert audit.violations == ()
        assert audit.receipt is not None
        assert audit.receipt.server == "codegraph"
        assert audit.receipt.repository_relative_path == "gin.go"

    @pytest.mark.parametrize(
        "markdown",
        (
            "**ServeHTTP** (method)\ngin.go:688",
            "**ServeHTTP** (method)\nfunc ServeHTTP(w http.ResponseWriter)\ngin.go:688",
            "**ServeHTTP** (method)\nfunc (server *Server) ServeHTTP(w http.ResponseWriter)\ngin.go:688",
            "**ServeHTTP** (method)\nfunc (engine *Engine) ServeHTTP(w http.ResponseWriter)\ngin.go:688\n"
            "**ServeHTTP** (method)\nfunc (server *Server) ServeHTTP(w http.ResponseWriter)\nother.go:42",
        ),
    )
    def test_canary_transcript_rejects_codegraph_receiver_counterexamples(
        self, tmp_path: Path, markdown: str
    ):
        from benchmarks.codegraph_compare.canary_policy import audit_canary_transcript

        item = {
            "id": "call-001",
            "type": "mcp_tool_call",
            "status": "completed",
            "server": "codegraph",
            "tool": "codegraph_search",
            "arguments": {
                "query": "Engine.ServeHTTP",
                "kind": "method",
                "limit": 10,
            },
            "result": {"content": [{"type": "text", "text": markdown}]},
        }
        transcript = tmp_path / "receiver-counterexample.jsonl"
        transcript.write_text(
            json.dumps({"type": "item.completed", "item": item}) + "\n",
            encoding="utf-8",
        )

        audit = audit_canary_transcript(
            transcript,
            "codegraph-warm",
            expected_tool="codegraph_search",
            expected_path="gin.go",
            expected_symbol="Engine.ServeHTTP",
            expected_kind="method",
        )

        assert audit.violations == (
            "CANARY_RECEIPT_INVALID:1",
            "CANARY_RECEIPT_MISSING",
        )
        assert audit.receipt is None

    @pytest.mark.parametrize(
        ("arguments", "markdown", "violation"),
        (
            (
                {"query": "ServeHTTP", "kind": "method", "limit": 10},
                "**ServeHTTP** (method)\ngin.go:42",
                "CANARY_ARGUMENTS_MISMATCH:1",
            ),
            (
                {"query": "Engine.ServeHTTP", "kind": "method", "limit": 10},
                "**ServeHTTP** (method)\ngin.go:42\n**ServeHTTP** (method)\ngin.go:688",
                "CANARY_RECEIPT_INVALID:1",
            ),
            (
                {"query": "Engine.ServeHTTP", "kind": "method", "limit": 10},
                "**ServeHTTP** (method)\ngin.go:0",
                "CANARY_RECEIPT_INVALID:1",
            ),
        ),
    )
    def test_canary_transcript_rejects_codegraph_receipt_ambiguity(
        self, tmp_path: Path, arguments: dict, markdown: str, violation: str
    ):
        from benchmarks.codegraph_compare.canary_policy import audit_canary_transcript

        item = {
            "id": "call-001",
            "type": "mcp_tool_call",
            "status": "completed",
            "server": "codegraph",
            "tool": "codegraph_search",
            "arguments": arguments,
            "result": {"content": [{"type": "text", "text": markdown}]},
        }
        transcript = tmp_path / "bad-codegraph-receipt.jsonl"
        transcript.write_text(
            json.dumps({"type": "item.completed", "item": item}) + "\n",
            encoding="utf-8",
        )

        audit = audit_canary_transcript(
            transcript,
            "codegraph-warm",
            expected_tool="codegraph_search",
            expected_path="gin.go",
            expected_symbol="Engine.ServeHTTP",
            expected_kind="method",
        )

        assert audit.violations == (
            violation,
            "CANARY_RECEIPT_MISSING",
        )
        assert audit.receipt is None
