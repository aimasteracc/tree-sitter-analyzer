"""Issue #1376：gin_tool_policy 行为组，原测试 AST 保持不变。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.unit._benchmark_harness_smoke_helpers import (
    TestGinSmokeManifestExecution as _TestGinSmokeManifestExecution,
)


class TestGinSmokeManifestExecution(_TestGinSmokeManifestExecution):
    @pytest.mark.parametrize("command", ("rg -n ServeHTTP .", "cat gin.go"))
    def test_canary_transcript_keeps_source_locked_after_unknown_mcp(
        self, tmp_path: Path, command: str
    ):
        from benchmarks.codegraph_compare.canary_policy import audit_canary_transcript

        transcript = tmp_path / "unknown-before-source.jsonl"
        transcript.write_text(
            "\n".join(
                (
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {
                                "id": "call-unknown",
                                "type": "mcp_tool_call",
                                "status": "completed",
                                "server": "tree-sitter-analyzer",
                                "tool": "unknown",
                                "result": {},
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {
                                "type": "command_execution",
                                "command": command,
                            },
                        }
                    ),
                )
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

        assert audit.violations == (
            "CANARY_TOOL_MISMATCH:1",
            "CANARY_SOURCE_DISCOVERY_BEFORE_RECEIPT:2",
            "CANARY_RECEIPT_MISSING",
        )

    @pytest.mark.parametrize(
        "result_error",
        ({"isError": True}, {"error": {"message": "query failed"}}),
    )
    def test_canary_transcript_rejects_nested_error_result_before_source(
        self, tmp_path: Path, result_error: dict
    ):
        from benchmarks.codegraph_compare.canary_policy import audit_canary_transcript

        result = {**self._tsa_canary_item()["result"], **result_error}
        transcript = tmp_path / "failed-before-source.jsonl"
        transcript.write_text(
            "\n".join(
                (
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {
                                "id": "call-failed",
                                "type": "mcp_tool_call",
                                "status": "completed",
                                "server": "tree-sitter-analyzer",
                                "tool": "nav",
                                "result": result,
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {
                                "type": "command_execution",
                                "command": "rg -n ServeHTTP .",
                            },
                        }
                    ),
                )
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

        assert audit.violations == (
            "MCP_CALL_FAILED:1",
            "SOURCE_DISCOVERY_BEFORE_INDEX:2",
            "MISSING_INDEX_QUERY",
            "CANARY_SOURCE_DISCOVERY_BEFORE_RECEIPT:2",
            "CANARY_RECEIPT_MISSING",
        )

    def test_canary_transcript_unlocks_source_after_exact_receipt(self, tmp_path: Path):
        from benchmarks.codegraph_compare.canary_policy import audit_canary_transcript

        transcript = tmp_path / "receipt-before-source.jsonl"
        transcript.write_text(
            "\n".join(
                (
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": self._tsa_canary_item(),
                        }
                    ),
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {
                                "type": "command_execution",
                                "command": "cat gin.go",
                            },
                        }
                    ),
                )
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

    @pytest.mark.parametrize(
        ("item", "violation"),
        (
            ({"type": "file_change"}, "FILE_CHANGE:1"),
            (
                {"type": "command_execution", "command": "touch marker"},
                "MUTATING_COMMAND:1",
            ),
            (
                {
                    "type": "command_execution",
                    "command": "tree_sitter_analyzer --outline",
                },
                "INDEX_COMMAND_OUTSIDE_MCP:1",
            ),
            (
                {
                    "type": "command_execution",
                    "command": "sqlite3 .ast-cache/index.db '.tables'",
                },
                "INDEX_NAMESPACE_OUTSIDE_MCP:1",
            ),
            (
                {"type": "command_execution", "command": "cat /etc/hosts"},
                "FILESYSTEM_BOUNDARY_ESCAPE:1",
            ),
            (
                {"type": "command_execution", "command": "ps aux"},
                "FILESYSTEM_BOUNDARY_ESCAPE:1",
            ),
            (
                {
                    "type": "command_execution",
                    "command": "curl https://example.com",
                },
                "NETWORK_COMMAND:1",
            ),
            (
                {"type": "command_execution", "command": "gh api repos/x/y"},
                "UNDECLARED_SHELL_COMMAND:1",
            ),
            (
                {
                    "type": "command_execution",
                    "command": "git -c credential.helper=x fetch origin",
                },
                "NETWORK_COMMAND:1",
            ),
            (
                {
                    "type": "command_execution",
                    "command": "awk 'BEGIN {system(\"curl example.com\")}'",
                },
                "UNDECLARED_SHELL_COMMAND:1",
            ),
            (
                {
                    "type": "command_execution",
                    "command": "find . -exec curl example.com ;",
                },
                "NETWORK_COMMAND:1",
            ),
        ),
    )
    def test_codex_transcript_rejects_non_readonly_events(
        self, tmp_path: Path, item: dict, violation: str
    ):
        from benchmarks.codegraph_compare.smoke_execution import (
            audit_codex_transcript,
        )

        transcript = tmp_path / "forbidden.jsonl"
        transcript.write_text(
            json.dumps({"type": "item.completed", "item": item}),
            encoding="utf-8",
        )

        audit = audit_codex_transcript(transcript, "native-only")

        assert audit.violations == (violation,)

    @pytest.mark.parametrize(
        "command",
        (
            "find . -name '*.go'",
            "rg -n ServeHTTP .",
            "sed -n '1,40p' gin.go",
            "/bin/bash -lc 'grep -n ServeHTTP gin.go'",
            "/bin/sh -lc \"sed -n '1,40p' gin.go\"",
        ),
    )
    def test_codex_transcript_accepts_declared_readonly_discovery(
        self, tmp_path: Path, command: str
    ):
        from benchmarks.codegraph_compare.smoke_execution import (
            audit_codex_transcript,
        )

        transcript = tmp_path / "readonly.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "command_execution", "command": command},
                }
            ),
            encoding="utf-8",
        )

        audit = audit_codex_transcript(transcript, "native-only")

        assert audit.violations == ()

    @pytest.mark.parametrize(
        "command",
        (
            "grep -RIn 'http.MethodGet|http.ListenAndServe' .",
            "rg -n 'python|node|curl' README.md",
            "/bin/bash -lc \"grep -n 'func ServeHTTP' gin.go\"",
        ),
    )
    def test_codex_transcript_does_not_treat_search_terms_as_network_commands(
        self, tmp_path: Path, command: str
    ):
        """Regression for the retained NO1-001C false policy failures (#1216)."""
        from benchmarks.codegraph_compare.smoke_execution import (
            audit_codex_transcript,
        )

        transcript = tmp_path / "source-search.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "command_execution", "command": command},
                }
            ),
            encoding="utf-8",
        )

        audit = audit_codex_transcript(transcript, "native-only")

        assert audit.violations == ()

    def test_codex_transcript_audits_inside_shell_launcher(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_execution import (
            audit_codex_transcript,
        )

        transcript = tmp_path / "wrapped-network.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "type": "command_execution",
                        "command": "/bin/bash -lc 'curl https://example.com'",
                    },
                }
            ),
            encoding="utf-8",
        )

        audit = audit_codex_transcript(transcript, "native-only")

        assert audit.violations == ("NETWORK_COMMAND:1",)

    def test_codex_transcript_audits_literal_newline_commands(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_execution import (
            audit_codex_transcript,
        )

        transcript = tmp_path / "multiline-network.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "type": "command_execution",
                        "command": "rg -n foo .\ncurl https://example.com",
                    },
                }
            ),
            encoding="utf-8",
        )

        audit = audit_codex_transcript(transcript, "native-only")

        assert audit.violations == ("NETWORK_COMMAND:1",)

    def test_indexed_arm_rejects_source_discovery_before_mcp(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_execution import (
            audit_codex_transcript,
        )

        transcript = tmp_path / "mcp-second.jsonl"
        transcript.write_text(
            "\n".join(
                (
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {
                                "type": "command_execution",
                                "command": "rg -n ServeHTTP .",
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {
                                "type": "mcp_tool_call",
                                "server": "tree-sitter-analyzer",
                                "tool": "search",
                            },
                        }
                    ),
                )
            ),
            encoding="utf-8",
        )

        audit = audit_codex_transcript(transcript, "tsa-warm")

        assert audit.violations == ("SOURCE_DISCOVERY_BEFORE_INDEX:1",)
