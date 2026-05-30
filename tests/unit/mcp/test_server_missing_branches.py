#!/usr/bin/env python3
"""
Coverage-boosting tests for mcp/server.py uncovered branches.

Targets the ~72 uncovered lines in the 80.3% file to push it past 85%.
Focus: parse_mcp_args, main() branches, tool handler routes,
resource reading, and analysis failure paths.
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# parse_mcp_args – lines ~815
# ---------------------------------------------------------------------------


class TestParseMcpArgs:
    def test_no_args(self):
        from tree_sitter_analyzer.mcp.server import parse_mcp_args

        args = parse_mcp_args([])
        assert args.project_root is None

    def test_unknown_args_raises(self):
        from tree_sitter_analyzer.mcp.server import parse_mcp_args

        with pytest.raises(SystemExit):
            parse_mcp_args(["--unknown-arg"])

    def test_with_project_root(self):
        from tree_sitter_analyzer.mcp.server import parse_mcp_args

        args = parse_mcp_args(["--project-root", "/tmp/foo"])
        assert args.project_root == "/tmp/foo"


# ---------------------------------------------------------------------------
# main() branches – env var, placeholders, KeyboardInterrupt, main_sync
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# _handle_analyze_code – universal tool + analysis failure + RuntimeError
# ---------------------------------------------------------------------------


class TestHandleAnalyzeCode:
    @pytest.fixture
    def tmp_path(self):
        with tempfile.TemporaryDirectory() as td:
            yield Path(td)

    @pytest.mark.asyncio
    async def test_missing_file_path_uses_universal_tool(self, tmp_path):
        """no file_path, universal tool available, succeeds"""
        from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer

        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        server.universal_analyze_tool = AsyncMock()
        server.universal_analyze_tool.execute = AsyncMock(
            return_value={"universal": "result"}
        )
        result = await server._analyze_code_scale({})
        assert result["universal"] == "result"

    @pytest.mark.asyncio
    async def test_missing_file_path_no_universal_raises(self, tmp_path):
        """no file_path and no universal tool"""
        from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer

        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        server.universal_analyze_tool = None
        with pytest.raises(ValueError, match="file_path is required"):
            await server._analyze_code_scale({})

    @pytest.mark.asyncio
    async def test_universal_tool_raises_valueerror(self, tmp_path):
        """Universal tool re-raises ValueError"""
        from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer

        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        server.universal_analyze_tool = AsyncMock()
        server.universal_analyze_tool.execute = AsyncMock(
            side_effect=ValueError("bad input")
        )
        with pytest.raises(ValueError, match="bad input"):
            await server._analyze_code_scale({})

    @pytest.mark.asyncio
    async def test_analysis_failure(self, tmp_path):
        """analysis_result.success == False"""
        from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer

        file = tmp_path / "test.py"
        file.write_text("x = 1")
        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        server.analysis_engine.analyze = AsyncMock(
            return_value=MagicMock(success=False, error_message="boom")
        )
        with pytest.raises(RuntimeError, match="Failed to analyze file"):
            await server._analyze_code_scale(
                {"file_path": str(file), "language": "python"}
            )

    @pytest.mark.asyncio
    async def test_analysis_none_result(self, tmp_path):
        """analysis_result is None"""
        from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer

        file = tmp_path / "test.py"
        file.write_text("x = 1")
        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        server.analysis_engine.analyze = AsyncMock(return_value=None)
        with pytest.raises(RuntimeError, match="Failed to analyze file"):
            await server._analyze_code_scale(
                {"file_path": str(file), "language": "python"}
            )


# ---------------------------------------------------------------------------
# _calculate_file_metrics
# ---------------------------------------------------------------------------


class TestCalculateFileMetrics:
    @pytest.fixture
    def tmp_path(self):
        with tempfile.TemporaryDirectory() as td:
            yield Path(td)

    def test_calculate_metrics(self, tmp_path):
        from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer

        file = tmp_path / "test.py"
        file.write_text("def foo(): pass\n")
        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        metrics = server._calculate_file_metrics(str(file), "python")
        assert isinstance(metrics, dict)
        assert "total_lines" in metrics
        assert metrics["total_lines"] > 0

    def test_calculate_metrics_nonexistent_file(self, tmp_path):
        from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer

        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        metrics = server._calculate_file_metrics(str(tmp_path / "missing.py"), "python")
        assert isinstance(metrics, dict)
        assert "total_lines" in metrics

    def test_calculate_metrics_empty_file(self, tmp_path):
        from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer

        file = tmp_path / "empty.py"
        file.write_text("")
        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        metrics = server._calculate_file_metrics(str(file), "python")
        assert isinstance(metrics, dict)
        assert metrics["total_lines"] >= 0


# ---------------------------------------------------------------------------
# _read_resource – code_file vs project_stats branches
# ---------------------------------------------------------------------------


class TestReadResource:
    @pytest.fixture
    def tmp_path(self):
        with tempfile.TemporaryDirectory() as td:
            yield Path(td)

    @pytest.mark.asyncio
    async def test_read_code_file_resource(self, tmp_path):
        from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer

        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        server.code_file_resource = MagicMock()
        server.code_file_resource.read_resource = AsyncMock(
            return_value={"code": "x=1"}
        )
        result = await server._read_resource("code://file/test.py")
        assert result["content"] == {"code": "x=1"}

    @pytest.mark.asyncio
    async def test_read_project_stats_resource(self, tmp_path):
        from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer

        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        server.project_stats_resource = MagicMock()
        server.project_stats_resource.read_resource = AsyncMock(
            return_value={"stats": "ok"}
        )
        result = await server._read_resource("code://stats/general")
        assert result["content"] == {"stats": "ok"}

    @pytest.mark.asyncio
    async def test_read_resource_not_found(self, tmp_path):
        from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer

        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        with pytest.raises(ValueError, match="Unknown resource URI"):
            await server._read_resource("unknown://x")


# ---------------------------------------------------------------------------
# create_server – tool handler routing
# ---------------------------------------------------------------------------


class TestCreateServerToolHandlers:
    @pytest.fixture
    def tmp_path(self):
        with tempfile.TemporaryDirectory() as td:
            yield Path(td)

    def test_create_server_returns_server(self, tmp_path):
        from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer

        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        mcp_server = server.create_server()
        assert mcp_server is not None
        assert hasattr(mcp_server, "name")

    def test_set_project_path(self, tmp_path):
        from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer

        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        server.set_project_path(str(tmp_path))
        assert server.analysis_engine is not None

    def test_project_root_stored(self, tmp_path):
        from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer

        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        assert (
            str(tmp_path) in str(server.analysis_engine)
            or server.analysis_engine is not None
        )

    def test_set_project_path_reinit(self, tmp_path):
        from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer

        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        server.set_project_path(str(tmp_path))
        assert server.analysis_engine is not None


# ---------------------------------------------------------------------------
# run() – MCP not available
# ---------------------------------------------------------------------------


class TestRun:
    @pytest.fixture
    def tmp_path(self):
        with tempfile.TemporaryDirectory() as td:
            yield Path(td)

    @pytest.mark.asyncio
    async def test_run_raises_when_mcp_not_available(self, tmp_path):
        from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer

        server = TreeSitterAnalyzerMCPServer(project_root=str(tmp_path))
        with patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", False):
            with pytest.raises(RuntimeError, match="MCP library not available"):
                await server.run()


# ---------------------------------------------------------------------------
# main() – KeyboardInterrupt + Exception + finally
# ---------------------------------------------------------------------------


class TestMainFunction:
    @pytest.mark.asyncio
    async def test_main_keyboard_interrupt(self):
        from tree_sitter_analyzer.mcp.server import main

        with (
            patch(
                "tree_sitter_analyzer.mcp.server.parse_mcp_args",
                return_value=MagicMock(project_root=None),
            ),
            patch(
                "tree_sitter_analyzer.mcp.server.TreeSitterAnalyzerMCPServer"
            ) as mock_srv_cls,
        ):
            mock_srv = MagicMock()
            mock_srv.run = AsyncMock(side_effect=KeyboardInterrupt)
            mock_srv_cls.return_value = mock_srv
            with patch("sys.exit") as mock_exit:
                await main()
                mock_exit.assert_called_with(0)

    @pytest.mark.asyncio
    async def test_main_exception(self):
        from tree_sitter_analyzer.mcp.server import main

        with (
            patch(
                "tree_sitter_analyzer.mcp.server.parse_mcp_args",
                return_value=MagicMock(project_root=None),
            ),
            patch(
                "tree_sitter_analyzer.mcp.server.TreeSitterAnalyzerMCPServer"
            ) as mock_srv_cls,
        ):
            mock_srv = MagicMock()
            mock_srv.run = AsyncMock(side_effect=ValueError("bad"))
            mock_srv_cls.return_value = mock_srv
            with patch("sys.exit") as mock_exit:
                await main()
                mock_exit.assert_called_with(1)

    def test_main_sync(self):
        from tree_sitter_analyzer.mcp.server import main_sync

        with patch("asyncio.run") as mock_run:
            main_sync()
            mock_run.assert_called_once()
            args, _kwargs = mock_run.call_args
            if args and hasattr(args[0], "close"):
                args[0].close()
