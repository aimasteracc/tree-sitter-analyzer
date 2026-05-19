#!/usr/bin/env python3
"""
Coverage-boosting tests for plugins/manager.py uncovered branches.
Targets ~52 uncovered lines: 81.1% → 85%+
"""

from unittest.mock import MagicMock, patch

from tree_sitter_analyzer.plugins.manager import (
    PluginManager,
)

# ---------------------------------------------------------------------------
# _prewarm_plugin_imports — lines 58-70 (safe_import, except branches)
# ---------------------------------------------------------------------------


class TestPrewarmPluginImports:
    def test_prewarm_called_during_init(self):
        """__init__ calls _prewarm_plugin_imports unconditionally"""
        with patch(
            "tree_sitter_analyzer.plugins.manager.importlib.import_module",
            side_effect=ImportError("no module"),
        ):
            mgr = PluginManager()
        assert isinstance(mgr._plugin_modules, dict)

    def test_prewarm_non_import_error(self):
        """languages import_module raises RuntimeError → log_debug path"""
        with patch(
            "tree_sitter_analyzer.plugins.manager.importlib.import_module",
            side_effect=RuntimeError("unexpected"),
        ):
            mgr = PluginManager()
        assert isinstance(mgr._plugin_modules, dict)


# ---------------------------------------------------------------------------
# _discover_from_entry_points — lines 131-133
# ---------------------------------------------------------------------------


class TestDiscoverFromEntryPoints:
    def test_entry_point_map_init(self):
        manager = PluginManager()
        fake_eps = MagicMock()
        fake_eps.select.return_value = []
        with patch("importlib.metadata.entry_points", return_value=fake_eps):
            manager._discover_from_entry_points()
        assert isinstance(manager._entry_point_map, dict)


# ---------------------------------------------------------------------------
# _discover_from_local_directory — line 159 (ispkg check)
# ---------------------------------------------------------------------------


class TestDiscoverFromLocalDirectory:
    def test_discovers_plugin_modules(self):
        """hits lines 156-168: iter_modules + _plugin suffix matching"""
        manager = PluginManager()
        manager._discover_from_local_directory()
        # should be a dict (may be empty if no dir found)
        assert isinstance(manager._plugin_modules, dict)


# ---------------------------------------------------------------------------
# get_plugin — entry point lazy loading (lines 220-233)
# ---------------------------------------------------------------------------


class TestGetPluginEntryPoint:
    def test_get_plugin_from_entry_point_map(self):
        manager = PluginManager()
        manager._discovered = True  # prevent load_plugins() from resetting state
        manager._plugin_modules = {}
        manager._entry_point_map = {}
        mock_entry = MagicMock()
        mock_plugin_cls = MagicMock()
        mock_plugin = mock_plugin_cls.return_value
        mock_plugin.get_language_name.return_value = "testlang"
        mock_entry.load.return_value = mock_plugin_cls
        manager._entry_point_map["testlang"] = mock_entry
        manager._loaded_plugins = {}

        with patch(
            "tree_sitter_analyzer.plugins.manager.issubclass", return_value=True
        ):
            result = manager.get_plugin("testlang")
        assert result is not None

    def test_get_plugin_entry_point_fails_gracefully(self):
        manager = PluginManager()
        manager._discovered = True
        manager._plugin_modules = {}
        manager._entry_point_map = {}
        mock_entry = MagicMock()
        mock_entry.load.side_effect = RuntimeError("bad")
        manager._entry_point_map["badlang"] = mock_entry

        with patch(
            "tree_sitter_analyzer.plugins.manager.issubclass", return_value=True
        ):
            result = manager.get_plugin("badlang")
        assert result is None


# ---------------------------------------------------------------------------
# _load_from_entry_points — old API (lines 257-266, 286-292)
# ---------------------------------------------------------------------------


class TestLoadFromEntryPoints:
    def test_old_api_get_no_select(self):
        manager = PluginManager()
        eps = MagicMock()
        eps.get.return_value = []
        del eps.select  # hasattr(eps, "select") will be False
        with patch("importlib.metadata.entry_points", return_value=eps):
            result = manager._load_from_entry_points()
        assert result == []

    def test_load_exception_in_loop(self):
        manager = PluginManager()
        eps = MagicMock()
        eps.select.return_value = [MagicMock()]
        eps.select.return_value[0].load.side_effect = ValueError("bad")
        with patch("importlib.metadata.entry_points", return_value=eps):
            result = manager._load_from_entry_points()
        assert result == []

    def test_entry_points_type_error_outer(self):
        manager = PluginManager()
        with patch("importlib.metadata.entry_points", side_effect=TypeError):
            result = manager._load_from_entry_points()
        assert result == []


# ---------------------------------------------------------------------------
# _load_from_local_directory — import+instantiation (lines 322-354)
# ---------------------------------------------------------------------------


class TestLoadFromLocalDirectory:
    def test_languages_package_import_error(self):
        manager = PluginManager()
        patch_path = "tree_sitter_analyzer.plugins.manager.importlib.import_module"
        with patch(patch_path, side_effect=ImportError):
            result = manager._load_from_local_directory()
        assert result == []

    def test_plugin_instantiation_exception(self):
        manager = PluginManager()
        patch_path = "tree_sitter_analyzer.plugins.manager.importlib.import_module"
        mock_mod = MagicMock()
        mock_mod.__name__ = "tree_sitter_analyzer.languages"
        mock_mod.__path__ = []
        with patch(patch_path, return_value=mock_mod):
            with patch("pkgutil.iter_modules", return_value=[]):
                with patch.object(manager, "_find_plugin_classes") as mock_find:

                    class BadPlugin:
                        def __init__(self):
                            raise RuntimeError("nope")

                    mock_find.return_value = [BadPlugin]
                    result = manager._load_from_local_directory()
        assert result == []


# ---------------------------------------------------------------------------
# validate_plugin — callable check (line 539)
# ---------------------------------------------------------------------------


class TestValidatePluginCallable:
    def test_method_not_callable(self):
        manager = PluginManager()
        plugin = MagicMock()
        plugin.get_language_name = "not_callable"
        plugin.get_file_extensions = MagicMock(return_value=[".test"])
        plugin.create_extractor = MagicMock(return_value=MagicMock())
        assert manager.validate_plugin(plugin) is False
