"""Tests for tree_sitter_analyzer.mcp.utils.__init__ module."""

import importlib

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
    def test_fallback_get_cache_manager_returns_none(self):
        """Test that fallback returns None when core services unavailable."""
        import sys

        # Remove the cache_service module from sys.modules so the import
        # machinery actually calls find_spec (where we block it).
        blocked = "tree_sitter_analyzer.core.cache_service"
        saved = sys.modules.pop(blocked, None)

        block_list = {blocked}

        class BlockFinder:
            def find_spec(self, fullname, path, target=None):
                if fullname in block_list:
                    raise ImportError(f"Blocked import of {fullname}")
                return None

        finder = BlockFinder()
        sys.meta_path.insert(0, finder)

        # Remove cached mcp.utils modules to force fresh import
        for mod in list(sys.modules):
            if mod.startswith("tree_sitter_analyzer.mcp.utils"):
                del sys.modules[mod]

        try:
            mod = importlib.import_module("tree_sitter_analyzer.mcp.utils")
            result = mod.get_cache_manager()
            assert result is None
        finally:
            sys.meta_path.remove(finder)
            if saved is not None:
                sys.modules[blocked] = saved
            for mod in list(sys.modules):
                if mod.startswith("tree_sitter_analyzer.mcp.utils"):
                    del sys.modules[mod]
            importlib.import_module("tree_sitter_analyzer.mcp.utils")

    def test_fallback_get_performance_monitor_returns_none(self):
        """Test that fallback performance monitor returns None."""
        import sys

        blocked = "tree_sitter_analyzer.core.cache_service"
        saved = sys.modules.pop(blocked, None)

        block_list = {blocked}

        class BlockFinder:
            def find_spec(self, fullname, path, target=None):
                if fullname in block_list:
                    raise ImportError(f"Blocked import of {fullname}")
                return None

        finder = BlockFinder()
        sys.meta_path.insert(0, finder)

        for mod in list(sys.modules):
            if mod.startswith("tree_sitter_analyzer.mcp.utils"):
                del sys.modules[mod]

        try:
            mod = importlib.import_module("tree_sitter_analyzer.mcp.utils")
            result = mod.get_performance_monitor()
            assert result is None
        finally:
            sys.meta_path.remove(finder)
            if saved is not None:
                sys.modules[blocked] = saved
            for mod in list(sys.modules):
                if mod.startswith("tree_sitter_analyzer.mcp.utils"):
                    del sys.modules[mod]
            importlib.import_module("tree_sitter_analyzer.mcp.utils")
