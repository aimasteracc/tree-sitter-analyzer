"""Issue #1376：_smoke_helpers 行为组，原测试 AST 保持不变。"""

from __future__ import annotations

import json
from pathlib import Path


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
