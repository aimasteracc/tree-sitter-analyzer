"""Tests for tree_sitter_analyzer.cli.commands.codegraph_index_commands.

Covers payload builders, helpers, and dispatcher error paths via mocking.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from tree_sitter_analyzer.cli.commands.codegraph_index_commands import (
    _autoindex_payload,
    _exit_code_for,
    _full_index_payload,
    _incremental_sync_payload,
    _knowledge_graph_index_payload,
    _metrics_payload,
    _print,
    _project_root,
    run_autoindex,
    run_codegraph_metrics,
    run_full_index,
    run_incremental_sync,
    run_knowledge_graph_index,
)


def _args(**kwargs: object) -> SimpleNamespace:
    return SimpleNamespace(**kwargs)


# ---------------------------------------------------------------------------
# _project_root
# ---------------------------------------------------------------------------


class TestProjectRoot:
    def test_returns_project_root_attr(self):
        args = _args(project_root="/srv/myproject")
        assert _project_root(args) == "/srv/myproject"

    def test_falls_back_to_cwd_when_none(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        args = _args(project_root=None)
        result = _project_root(args)
        assert result  # truthy, some cwd

    def test_falls_back_to_cwd_when_missing(self, monkeypatch):
        args = _args()
        result = _project_root(args)
        assert result  # truthy


# ---------------------------------------------------------------------------
# _exit_code_for
# ---------------------------------------------------------------------------


class TestExitCodeFor:
    def test_returns_0_on_success(self):
        assert _exit_code_for({"success": True}) == 0

    def test_returns_1_on_failure(self):
        assert _exit_code_for({"success": False}) == 1

    def test_returns_1_when_key_missing(self):
        assert _exit_code_for({}) == 1


# ---------------------------------------------------------------------------
# _print
# ---------------------------------------------------------------------------


class TestPrint:
    def test_toon_format_prints_toon_content(self, capsys):
        _print({"toon_content": "## Result\nsome content"}, "toon")
        out = capsys.readouterr().out
        assert "## Result" in out

    def test_json_format_prints_json(self, capsys):
        _print({"key": "value", "success": True}, "json")
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["key"] == "value"

    def test_toon_format_missing_key_prints_empty(self, capsys):
        _print({}, "toon")
        out = capsys.readouterr().out
        assert out.strip() == ""


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------


class TestAutoindexPayload:
    def test_default_values(self):
        args = _args()
        payload = _autoindex_payload(args, "json")
        assert payload["mode"] == "status"
        assert payload["max_files"] == 20_000
        assert payload["output_format"] == "json"

    def test_custom_mode(self):
        args = _args(autoindex_mode="check")
        payload = _autoindex_payload(args, "toon")
        assert payload["mode"] == "check"
        assert payload["output_format"] == "toon"

    def test_empty_mode_falls_back_to_status(self):
        args = _args(autoindex_mode="")
        payload = _autoindex_payload(args, "json")
        assert payload["mode"] == "status"


class TestFullIndexPayload:
    def test_default_values(self):
        args = _args()
        payload = _full_index_payload(args, "json")
        assert payload["mode"] == "incremental"
        assert payload["max_files"] == 20_000
        assert payload["include_activation"] is False
        assert payload["output_format"] == "json"

    def test_include_activation_true(self):
        args = _args(full_index_include_activation=True)
        payload = _full_index_payload(args, "json")
        assert payload["include_activation"] is True


class TestIncrementalSyncPayload:
    def test_default_values(self):
        args = _args()
        payload = _incremental_sync_payload(args, "json")
        assert payload["mode"] == "sync"
        assert payload["max_files"] == 20_000

    def test_custom_mode(self):
        args = _args(incremental_sync_mode="check")
        payload = _incremental_sync_payload(args, "toon")
        assert payload["mode"] == "check"


class TestKnowledgeGraphIndexPayload:
    def test_default_values(self):
        args = _args()
        payload = _knowledge_graph_index_payload(args, "json")
        assert payload["mode"] == "update"
        assert payload["backend"] == "json"
        assert payload["max_files"] == 1_000_000
        assert payload["max_nodes"] == 100_000
        assert payload["max_edges"] == 500_000
        assert payload["include_docs"] is True
        assert payload["output_format"] == "json"

    def test_custom_values(self):
        args = _args(
            knowledge_graph_index_mode="build",
            knowledge_graph_backend="hybrid",
            knowledge_graph_max_files=123,
            knowledge_graph_max_nodes=456,
            knowledge_graph_max_edges=789,
            knowledge_graph_no_docs=True,
        )
        payload = _knowledge_graph_index_payload(args, "toon")
        assert payload["mode"] == "build"
        assert payload["backend"] == "hybrid"
        assert payload["max_files"] == 123
        assert payload["max_nodes"] == 456
        assert payload["max_edges"] == 789
        assert payload["include_docs"] is False
        assert payload["output_format"] == "toon"


class TestMetricsPayload:
    def test_no_sections(self):
        args = _args()
        payload = _metrics_payload(args, "json")
        assert "sections" not in payload
        assert payload["output_format"] == "json"

    def test_with_sections(self):
        args = _args(codegraph_metrics_sections=["summary", "files"])
        payload = _metrics_payload(args, "json")
        assert payload["sections"] == ["summary", "files"]


# ---------------------------------------------------------------------------
# Dispatcher run_autoindex — error paths
# ---------------------------------------------------------------------------


_AUTOINDEX_CLS = "tree_sitter_analyzer.mcp.tools.auto_index_tool.CodeGraphAutoIndexTool"
_FULLINDEX_CLS = "tree_sitter_analyzer.mcp.tools.full_index_tool.CodeGraphFullIndexTool"
_INCSYNC_CLS = (
    "tree_sitter_analyzer.mcp.tools.incremental_sync_tool.CodeGraphIncrementalSyncTool"
)
_METRICS_CLS = (
    "tree_sitter_analyzer.mcp.tools.codegraph_metrics_tool.CodeGraphMetricsTool"
)
_KNOWLEDGE_INDEX_CLS = (
    "tree_sitter_analyzer.mcp.tools.knowledge_graph_tool.CodeGraphKnowledgeIndexTool"
)
_OUTPUT_FMT = (
    "tree_sitter_analyzer.cli.commands.codegraph_index_commands._output_format"
)


class TestRunAutoindex:
    def test_import_error_returns_1(self, tmp_path):
        """Module absent from sys.modules → import failure → return 1."""
        args = _args(project_root=str(tmp_path))
        errors: list[str] = []
        with patch.dict(
            "sys.modules",
            {"tree_sitter_analyzer.mcp.tools.auto_index_tool": None},
        ):
            code = run_autoindex(args, errors.append)
        assert code == 1
        assert any("import" in e.lower() or "failed" in e.lower() for e in errors)

    def test_execute_failure_returns_1(self, tmp_path):
        args = _args(
            project_root=str(tmp_path), autoindex_mode="status", autoindex_max_files=10
        )
        errors: list[str] = []

        mock_tool = MagicMock()
        mock_tool.execute = AsyncMock(side_effect=RuntimeError("tool boom"))

        with patch(_AUTOINDEX_CLS, return_value=mock_tool):
            code = run_autoindex(args, errors.append)
        assert code == 1
        assert any("failed" in e for e in errors)

    def test_success_returns_0(self, tmp_path, capsys):
        args = _args(
            project_root=str(tmp_path), autoindex_mode="status", autoindex_max_files=10
        )
        mock_tool = MagicMock()
        mock_tool.execute = AsyncMock(
            return_value={"success": True, "toon_content": "ok"}
        )

        with patch(_AUTOINDEX_CLS, return_value=mock_tool):
            with patch(_OUTPUT_FMT, return_value="toon"):
                code = run_autoindex(args, lambda e: None)
        assert code == 0


# ---------------------------------------------------------------------------
# run_full_index
# ---------------------------------------------------------------------------


class TestRunFullIndex:
    def test_execute_failure_returns_1(self, tmp_path):
        args = _args(project_root=str(tmp_path))
        mock_tool = MagicMock()
        mock_tool.execute = AsyncMock(side_effect=RuntimeError("full fail"))

        errors: list[str] = []
        with patch(_FULLINDEX_CLS, return_value=mock_tool):
            code = run_full_index(args, errors.append)
        assert code == 1

    def test_success_returns_0(self, tmp_path, capsys):
        args = _args(project_root=str(tmp_path))
        mock_tool = MagicMock()
        mock_tool.execute = AsyncMock(
            return_value={"success": True, "toon_content": "ok"}
        )

        with patch(_FULLINDEX_CLS, return_value=mock_tool):
            with patch(_OUTPUT_FMT, return_value="toon"):
                code = run_full_index(args, lambda e: None)
        assert code == 0


# ---------------------------------------------------------------------------
# run_incremental_sync
# ---------------------------------------------------------------------------


class TestRunIncrementalSync:
    def test_execute_failure_returns_1(self, tmp_path):
        args = _args(project_root=str(tmp_path))
        mock_tool = MagicMock()
        mock_tool.execute = AsyncMock(side_effect=RuntimeError("sync fail"))

        errors: list[str] = []
        with patch(_INCSYNC_CLS, return_value=mock_tool):
            code = run_incremental_sync(args, errors.append)
        assert code == 1

    def test_success_returns_0(self, tmp_path):
        args = _args(project_root=str(tmp_path))
        mock_tool = MagicMock()
        mock_tool.execute = AsyncMock(
            return_value={"success": True, "toon_content": "ok"}
        )

        with patch(_INCSYNC_CLS, return_value=mock_tool):
            with patch(_OUTPUT_FMT, return_value="toon"):
                code = run_incremental_sync(args, lambda e: None)
        assert code == 0


# ---------------------------------------------------------------------------
# run_knowledge_graph_index
# ---------------------------------------------------------------------------


class TestRunKnowledgeGraphIndex:
    def test_execute_failure_returns_1(self, tmp_path):
        args = _args(project_root=str(tmp_path))
        mock_tool = MagicMock()
        mock_tool.execute = AsyncMock(side_effect=RuntimeError("kg fail"))

        errors: list[str] = []
        with patch(_KNOWLEDGE_INDEX_CLS, return_value=mock_tool):
            code = run_knowledge_graph_index(args, errors.append)
        assert code == 1
        assert errors == ["--knowledge-graph-index failed: kg fail"]

    def test_success_returns_0(self, tmp_path, capsys):
        args = _args(project_root=str(tmp_path), knowledge_graph_backend="json")
        mock_tool = MagicMock()
        mock_tool.execute = AsyncMock(
            return_value={"success": True, "toon_content": "kg ok"}
        )

        with patch(_KNOWLEDGE_INDEX_CLS, return_value=mock_tool):
            with patch(_OUTPUT_FMT, return_value="toon"):
                code = run_knowledge_graph_index(args, lambda e: None)
        out = capsys.readouterr().out
        assert code == 0
        assert "kg ok" in out


# ---------------------------------------------------------------------------
# run_codegraph_metrics
# ---------------------------------------------------------------------------


class TestRunCodegraphMetrics:
    def test_execute_failure_returns_1(self, tmp_path):
        args = _args(project_root=str(tmp_path))
        mock_tool = MagicMock()
        mock_tool.execute = AsyncMock(side_effect=RuntimeError("metrics fail"))

        errors: list[str] = []
        with patch(_METRICS_CLS, return_value=mock_tool):
            code = run_codegraph_metrics(args, errors.append)
        assert code == 1

    def test_success_with_sections(self, tmp_path, capsys):
        args = _args(project_root=str(tmp_path), codegraph_metrics_sections=["summary"])
        mock_tool = MagicMock()
        mock_tool.execute = AsyncMock(
            return_value={"success": True, "toon_content": "metrics ok"}
        )

        with patch(_METRICS_CLS, return_value=mock_tool):
            with patch(_OUTPUT_FMT, return_value="toon"):
                code = run_codegraph_metrics(args, lambda e: None)
        out = capsys.readouterr().out
        assert code == 0
        assert "metrics ok" in out
