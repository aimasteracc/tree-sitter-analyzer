"""Tests for tree_sitter_analyzer.mcp.utils.__init__ module."""

import importlib
from unittest.mock import patch

import tree_sitter_analyzer.mcp.utils as mcp_utils_mod
from tree_sitter_analyzer.mcp.utils import (
    MCP_UTILS_CAPABILITIES,
    get_cache_manager,
    get_performance_monitor,
)


class TestMcpUtilsCapabilities:
    def test_capabilities_is_dict(self):
        assert isinstance(MCP_UTILS_CAPABILITIES, dict)

    def test_capabilities_has_version(self):
        assert "version" in MCP_UTILS_CAPABILITIES
        assert isinstance(MCP_UTILS_CAPABILITIES["version"], str)


class TestBackwardCompatibleCacheManager:
    def test_get_cache_manager_returns_object(self):
        mgr = get_cache_manager()
        assert mgr is not None

    def test_get_cache_stats_returns_dict(self):
        mgr = get_cache_manager()
        result = mgr.get_cache_stats()
        assert isinstance(result, dict)

    def test_delegation_via_getattr(self):
        mgr = get_cache_manager()
        assert hasattr(mgr, "clear")

    def test_clear_all_caches(self):
        mgr = get_cache_manager()
        mgr.clear_all_caches()


class TestGetPerformanceMonitor:
    def test_get_performance_monitor_returns_object(self):
        monitor = get_performance_monitor()
        assert monitor is not None


class TestImportErrorFallback:
    @patch.dict("sys.modules", {"tree_sitter_analyzer.core.cache_service": None})
    def test_fallback_get_cache_manager_returns_none(self):
        importlib.reload(mcp_utils_mod)
        try:
            result = mcp_utils_mod.get_cache_manager()
            assert result is None
        finally:
            importlib.reload(mcp_utils_mod)

    @patch.dict("sys.modules", {"tree_sitter_analyzer.core.cache_service": None})
    def test_fallback_get_performance_monitor_returns_none(self):
        importlib.reload(mcp_utils_mod)
        try:
            result = mcp_utils_mod.get_performance_monitor()
            assert result is None
        finally:
            importlib.reload(mcp_utils_mod)
