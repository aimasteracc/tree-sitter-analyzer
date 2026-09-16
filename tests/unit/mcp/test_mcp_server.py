"""
Tests for tree_sitter_analyzer.mcp.server module.

Basic test suite for the MCP server functionality.
"""

import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from tree_sitter_analyzer.mcp.server import (
    MCP_AVAILABLE,
    TreeSitterAnalyzerMCPServer,
    main,
)
from tree_sitter_analyzer.mcp.tools import hyphae_subscribe_tool as hst
from tree_sitter_analyzer.registry.singleton_registry import (
    get_subscription_registry,
    reset_subscription_registry,
)


@pytest.fixture
def _clean_reactive_state():
    """隔离 canonical 生命周期测试的 registry 与传输映射。"""
    reset_subscription_registry()
    hst._SESSION_LOOPS.clear()
    hst._SESSION_MIN_INTERVALS.clear()
    hst._SESSION_SESSIONS.clear()
    yield
    reset_subscription_registry()
    hst._SESSION_LOOPS.clear()
    hst._SESSION_MIN_INTERVALS.clear()
    hst._SESSION_SESSIONS.clear()


def _result(call_result):
    """解析真实 SDK tools/call 的 JSON 文本结果。"""
    return json.loads(call_result.content[0].text)


def _watch_ticket(manager, project_root, selector):
    """取得 canonical watcher 可调度的有效 ticket。"""
    token = manager.issue_watch_token(project_root)
    return next(t for t in manager.snapshot_for_watch(token) if t.selector == selector)


class TestMCPServerBasic:
    """Basic tests for MCP server."""

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True)
    @patch("tree_sitter_analyzer.mcp.server.get_analysis_engine")
    @patch("tree_sitter_analyzer.mcp.server.setup_logger")
    def test_server_initialization(self, mock_logger, mock_engine):
        """Test server initialization."""
        mock_engine.return_value = Mock()
        mock_logger.return_value = Mock()

        server = TreeSitterAnalyzerMCPServer()

        assert server.server is None
        assert server.analysis_engine is not None
        from tree_sitter_analyzer.mcp import MCP_INFO

        assert server.name == "tree-sitter-analyzer-mcp"
        assert server.version.startswith(MCP_INFO["version"])

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", False)
    def test_create_server_mcp_unavailable(self):
        """Test server creation when MCP is unavailable."""
        with (
            patch("tree_sitter_analyzer.mcp.server.get_analysis_engine"),
            patch("tree_sitter_analyzer.mcp.server.setup_logger"),
        ):
            server = TreeSitterAnalyzerMCPServer()

            with pytest.raises(RuntimeError, match="MCP library not available"):
                server.create_server()

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", False)
    def test_run_mcp_unavailable(self):
        """Test run when MCP is unavailable."""
        with (
            patch("tree_sitter_analyzer.mcp.server.get_analysis_engine"),
            patch("tree_sitter_analyzer.mcp.server.setup_logger"),
        ):
            server = TreeSitterAnalyzerMCPServer()

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                with pytest.raises(RuntimeError, match="MCP library not available"):
                    loop.run_until_complete(server.run())
            finally:
                loop.close()


class TestMCPServerWithMCP:
    """Tests for MCP server when MCP is available."""

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True)
    @patch("tree_sitter_analyzer.mcp.server.Server")
    @patch("tree_sitter_analyzer.mcp.server.get_analysis_engine")
    @patch("tree_sitter_analyzer.mcp.server.setup_logger")
    def test_create_server_success(self, mock_logger, mock_engine, mock_server_class):
        """Test successful server creation."""
        mock_engine.return_value = Mock()
        mock_logger.return_value = Mock()
        mock_server = Mock()
        mock_server_class.return_value = mock_server

        server = TreeSitterAnalyzerMCPServer()
        result = server.create_server()

        assert result == mock_server
        assert server.server == mock_server
        mock_server_class.assert_called_once()
        call = mock_server_class.call_args
        assert call.args == ("tree-sitter-analyzer-mcp",)
        assert call.kwargs["version"] == server.version
        assert call.kwargs["lifespan"] == server.subscription_lifecycle.lifespan
        assert callable(call.kwargs["lifespan"])

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True)
    @patch("tree_sitter_analyzer.mcp.server.stdio_server")
    @patch("tree_sitter_analyzer.mcp.server.InitializationOptions")
    @patch("tree_sitter_analyzer.mcp.server.Server")
    @patch("tree_sitter_analyzer.mcp.server.get_analysis_engine")
    @patch("tree_sitter_analyzer.mcp.server.setup_logger")
    def test_run_server_basic(
        self,
        mock_logger,
        mock_engine,
        mock_server_class,
        mock_init_options,
        mock_stdio_server,
    ):
        """Test basic server running."""
        mock_engine.return_value = Mock()
        mock_logger.return_value = Mock()

        mock_server = Mock()
        mock_server.run = AsyncMock()
        mock_server_class.return_value = mock_server

        mock_streams = (AsyncMock(), AsyncMock())
        mock_stdio_server.return_value.__aenter__ = AsyncMock(return_value=mock_streams)
        mock_stdio_server.return_value.__aexit__ = AsyncMock(return_value=None)

        async def quick_run(*args, **kwargs):
            await asyncio.sleep(0.01)

        mock_server.run.side_effect = quick_run

        server = TreeSitterAnalyzerMCPServer()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(server.run())
        finally:
            loop.close()

        mock_init_options.assert_called_once()
        mock_server.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_2026_09_14_empty_run_does_not_materialize_tool_registry(
        self, tmp_path
    ):
        """真实 SDK initialize/disconnect 清理不能物化延迟 registry。"""
        server = TreeSitterAnalyzerMCPServer(str(tmp_path))
        async with create_connected_server_and_client_session(server.create_server()):
            pass

        assert server._registry_built is False

    @pytest.mark.asyncio
    async def test_2026_09_14_last_connection_exit_keeps_application_watcher(
        self, tmp_path
    ):
        """最后一个低层连接退出时仍保留 application watcher。"""
        server = TreeSitterAnalyzerMCPServer(str(tmp_path))
        cache_tool = server.tools["index"].action_map["cache"]
        await cache_tool.execute({"mode": "watch_start"})
        try:
            async with create_connected_server_and_client_session(
                server.create_server()
            ):
                pass
            assert cache_tool._watcher.is_running() is True
        finally:
            await cache_tool.execute({"mode": "watch_stop"})

    @pytest.mark.asyncio
    async def test_2026_09_14_app_run_finally_stops_only_its_built_watcher(
        self, tmp_path, monkeypatch
    ):
        """canonical 应用 run finally 只停止本应用已构建的 watcher。"""
        server = TreeSitterAnalyzerMCPServer(str(tmp_path))
        other = TreeSitterAnalyzerMCPServer(str(tmp_path))
        cache_tool = server.tools["index"].action_map["cache"]
        other_cache_tool = other.tools["index"].action_map["cache"]
        await cache_tool.execute({"mode": "watch_start"})
        await other_cache_tool.execute({"mode": "watch_start"})
        monkeypatch.setattr(server, "create_server", lambda: object())

        async def finish(_server, _options):
            return None

        monkeypatch.setattr(server, "_run_server_loop", finish)
        try:
            await server.run()
            assert cache_tool._watcher.is_running() is False
            assert other_cache_tool._watcher.is_running() is True
        finally:
            if cache_tool._watcher.is_running():
                cache_tool._watcher.stop()
            other_cache_tool._watcher.stop()

    @pytest.mark.asyncio
    async def test_2026_09_14_shutdown_failure_does_not_mask_run_failure(
        self, tmp_path, monkeypatch
    ):
        """watcher shutdown 失败时仍传播原始 run 异常对象。"""
        server = TreeSitterAnalyzerMCPServer(str(tmp_path))
        cache_tool = server.tools["index"].action_map["cache"]
        primary = RuntimeError("run failed")
        monkeypatch.setattr(server, "create_server", lambda: object())

        async def fail_run(_server, _options):
            raise primary

        def fail_shutdown():
            raise TimeoutError("shutdown failed")

        monkeypatch.setattr(server, "_run_server_loop", fail_run)
        monkeypatch.setattr(cache_tool, "shutdown_application_watcher", fail_shutdown)

        with pytest.raises(RuntimeError, match="run failed") as caught:
            await server.run()

        assert caught.value is primary

    @pytest.mark.asyncio
    async def test_2026_09_14_setup_failure_still_stops_built_watcher(
        self, tmp_path, monkeypatch
    ):
        """create_server 失败仍传播原异常并停止已构建 watcher。"""
        server = TreeSitterAnalyzerMCPServer(str(tmp_path))
        cache_tool = server.tools["index"].action_map["cache"]
        await cache_tool.execute({"mode": "watch_start"})
        primary = RuntimeError("setup failed")
        monkeypatch.setattr(server, "create_server", Mock(side_effect=primary))

        with pytest.raises(RuntimeError, match="setup failed") as caught:
            await server.run()

        assert caught.value is primary
        assert cache_tool._watcher.is_running() is False


class TestAnalyzeCodeScale:
    """Test analyze code scale functionality."""

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True)
    @patch("tree_sitter_analyzer.mcp.server.get_analysis_engine")
    @patch("tree_sitter_analyzer.mcp.server.setup_logger")
    def test_analyze_code_scale_method(self, mock_logger, mock_engine):
        """Test _analyze_code_scale method."""
        mock_engine.return_value = Mock()
        mock_logger.return_value = Mock()

        server = TreeSitterAnalyzerMCPServer()

        mock_result = Mock()
        mock_class = Mock()
        mock_class.element_type = "class"
        mock_class.name = "TestClass"

        mock_function = Mock()
        mock_function.element_type = "function"
        mock_function.name = "test_method"
        mock_function.complexity_score = 1  # Add complexity_score

        mock_result.elements = [mock_class, mock_function]
        mock_result.success = True
        mock_result.to_dict.return_value = {
            "elements": [
                {"element_type": "class", "name": "TestClass"},
                {"element_type": "function", "name": "test_method"},
            ],
            "line_count": 50,
        }
        server.analysis_engine.analyze = AsyncMock(return_value=mock_result)

        with (
            patch("tree_sitter_analyzer.mcp.server.PathClass") as mock_path,
            patch(
                "tree_sitter_analyzer.language_detector.detect_language_from_file"
            ) as mock_detect_lang,
        ):
            mock_path_instance = Mock()
            mock_path_instance.exists.return_value = True
            mock_path.return_value = mock_path_instance
            mock_detect_lang.return_value = "python"

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    server._analyze_code_scale({"file_path": "test.py"})
                )
                assert "metrics" in result
                assert "elements" in result["metrics"]
                assert result["metrics"]["elements"]["classes"] == 1
                assert result["metrics"]["elements"]["methods"] == 1
            finally:
                loop.close()


class TestMainFunction:
    """Test main function."""

    @patch("tree_sitter_analyzer.mcp.server.TreeSitterAnalyzerMCPServer")
    @patch("tree_sitter_analyzer.mcp.server.logger")
    def test_main_keyboard_interrupt(self, mock_logger, mock_server_class):
        """Test main function handles KeyboardInterrupt."""
        mock_server = Mock()
        mock_server.run = AsyncMock(side_effect=KeyboardInterrupt())
        mock_server_class.return_value = mock_server

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            with pytest.raises(SystemExit) as exc_info:
                loop.run_until_complete(main())
            assert exc_info.value.code == 0
        finally:
            loop.close()

        mock_server_class.assert_called_once()
        mock_logger.info.assert_any_call("Server stopped by user")
        mock_logger.info.assert_called_with("MCP server shutdown complete")

    @patch("tree_sitter_analyzer.mcp.server.TreeSitterAnalyzerMCPServer")
    @patch("tree_sitter_analyzer.mcp.server.logger")
    def test_main_exception_handling(self, mock_logger, mock_server_class):
        """Test main function handles exceptions."""
        mock_server_class.side_effect = Exception("Test error")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            with pytest.raises(SystemExit):
                loop.run_until_complete(main())
        finally:
            loop.close()

        mock_logger.error.assert_called()


class TestToolsAndResources:
    """Test tools and resources functionality."""

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True)
    @patch("tree_sitter_analyzer.mcp.server.get_analysis_engine")
    @patch("tree_sitter_analyzer.mcp.server.setup_logger")
    def test_tools_initialization(self, mock_logger, mock_engine):
        """Test that tools are properly initialized."""
        mock_engine.return_value = Mock()
        mock_logger.return_value = Mock()

        server = TreeSitterAnalyzerMCPServer()

        assert (
            server.read_partial_tool.get_tool_definition()["name"]
            == "extract_code_section"
        )
        assert (
            server.table_format_tool.get_tool_definition()["name"]
            == "analyze_code_structure"
        )
        assert callable(server.analysis_engine.analyze_file)

    @patch("tree_sitter_analyzer.mcp.server.MCP_AVAILABLE", True)
    @patch("tree_sitter_analyzer.mcp.server.get_analysis_engine")
    @patch("tree_sitter_analyzer.mcp.server.setup_logger")
    def test_resources_initialization(self, mock_logger, mock_engine):
        """Test that resources are properly initialized."""
        mock_engine.return_value = Mock()
        mock_logger.return_value = Mock()

        server = TreeSitterAnalyzerMCPServer()

        assert server.code_file_resource.get_resource_info()["name"] == "code_file"
        assert (
            server.project_stats_resource.get_resource_info()["name"] == "project_stats"
        )


class TestMCPAvailability:
    """Test MCP availability detection."""

    def test_mcp_available_constant(self):
        """Test MCP_AVAILABLE constant is properly set."""
        assert isinstance(MCP_AVAILABLE, bool)


class TestFallbackClasses:
    """Test fallback classes when MCP is not available."""

    def test_mcp_availability_handling(self):
        """Test that MCP availability is properly handled."""
        from tree_sitter_analyzer.mcp.server import MCP_AVAILABLE

        assert isinstance(MCP_AVAILABLE, bool)


@pytest.mark.asyncio
async def test_2026_09_14_same_raw_project_rebind_invalidates_old_subscription(
    tmp_path, _clean_reactive_state
) -> None:
    """每次真实 set_project_path 赋值都推进 epoch，即使 raw root 相同。"""
    app = TreeSitterAnalyzerMCPServer(str(tmp_path))
    async with create_connected_server_and_client_session(
        app.create_server()
    ) as client:
        first = _result(
            await client.call_tool(
                "search", {"action": "subscribe", "selector": ".function"}
            )
        )
        rebound = await client.call_tool(
            "set_project_path", {"project_path": str(tmp_path)}
        )
        assert rebound.isError is not True
        assert get_subscription_registry().subscriptions_for(first["sub_id"]) == []
        assert hst.get_session_obj(first["sub_id"]) is None
        replacement = _result(
            await client.call_tool(
                "search", {"action": "subscribe", "selector": ".class"}
            )
        )
        assert get_subscription_registry().subscriptions_for(replacement["sub_id"]) == [
            ".class"
        ]


@pytest.mark.asyncio
async def test_2026_09_14_two_real_runs_close_one_keeps_the_other(
    tmp_path, _clean_reactive_state
) -> None:
    """同一 canonical 应用的两个真实 run 必须按 run owner 独立清理。"""
    app = TreeSitterAnalyzerMCPServer(str(tmp_path))
    sdk_server = app.create_server()
    async with create_connected_server_and_client_session(sdk_server) as first_client:
        first = _result(
            await first_client.call_tool(
                "search", {"action": "subscribe", "selector": ".function"}
            )
        )
        async with create_connected_server_and_client_session(
            sdk_server
        ) as second_client:
            second = _result(
                await second_client.call_tool(
                    "search", {"action": "subscribe", "selector": ".class"}
                )
            )
            assert first["sub_id"] != second["sub_id"]

        registry = get_subscription_registry()
        assert registry.subscriptions_for(second["sub_id"]) == []
        assert hst.get_session_obj(second["sub_id"]) is None
        assert registry.subscriptions_for(first["sub_id"]) == [".function"]
        live_session = hst.get_session_obj(first["sub_id"])
        continued = await first_client.call_tool(
            "search", {"action": "subscribe", "selector": ".import"}
        )
        assert continued.isError is not True
        assert registry.subscriptions_for(first["sub_id"]) == [".function", ".import"]
        sent = asyncio.Event()
        original_send = live_session.send_resource_updated

        async def observed_send(uri: object) -> None:
            await original_send(uri)
            sent.set()

        live_session.send_resource_updated = observed_send
        ticket = _watch_ticket(app.subscription_lifecycle, str(tmp_path), ".import")
        app.subscription_lifecycle.schedule_send(ticket, "tsa://hyphae/.import")
        await asyncio.wait_for(sent.wait(), timeout=1)
