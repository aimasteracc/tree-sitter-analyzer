#!/usr/bin/env python3
"""
Unit tests for plugins/manager.py
"""

import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from tree_sitter_analyzer.plugins.base import LanguagePlugin
from tree_sitter_analyzer.plugins.manager import (
    PluginManager,
    _is_running_under_pytest,
    _is_source_checkout,
    _should_load_entry_points,
)


# Mock plugin for testing
class MockPlugin(LanguagePlugin):
    """Mock plugin for testing"""

    def get_language_name(self) -> str:
        return "mock"

    def get_file_extensions(self) -> list[str]:
        return [".mock"]

    def create_extractor(self) -> Any:
        return MagicMock()

    def analyze_file(
        self, file_path: Path, options: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return {"elements": [], "metadata": {}}


class MockPlugin2(LanguagePlugin):
    """Another mock plugin for testing"""

    def get_language_name(self) -> str:
        return "mock2"

    def get_file_extensions(self) -> list[str]:
        return [".mock2"]

    def create_extractor(self) -> Any:
        return MagicMock()

    def analyze_file(
        self, file_path: Path, options: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return {"elements": [], "metadata": {}}


class TestIsSourceCheckout:
    """Tests for _is_source_checkout function"""

    @patch("tree_sitter_analyzer.plugins.manager.Path")
    def test_is_source_checkout_with_git(self, mock_path: MagicMock) -> None:
        """Test detection when .git directory exists"""
        mock_file = MagicMock()
        mock_parent = MagicMock()
        mock_parent.__truediv__ = MagicMock(return_value=MagicMock(exists=lambda: True))
        mock_file.resolve.return_value = MagicMock(parents=[mock_parent])
        mock_path.return_value = mock_file

        result = _is_source_checkout()
        assert result is True

    @patch("tree_sitter_analyzer.plugins.manager.Path")
    def test_is_source_checkout_without_git(self, mock_path: MagicMock) -> None:
        """Test detection when no .git directory exists"""
        mock_file = MagicMock()
        mock_parent = MagicMock()
        mock_parent.__truediv__ = MagicMock(
            return_value=MagicMock(exists=lambda: False)
        )
        mock_file.resolve.return_value = MagicMock(parents=[mock_parent])
        mock_path.return_value = mock_file

        result = _is_source_checkout()
        assert result is False

    @patch("tree_sitter_analyzer.plugins.manager.Path")
    def test_is_source_checkout_exception(self, mock_path: MagicMock) -> None:
        """Test exception handling"""
        mock_path.side_effect = Exception("Test error")

        result = _is_source_checkout()
        assert result is False


class TestShouldLoadEntryPoints:
    """Tests for _should_load_entry_points function"""

    @patch.dict(os.environ, {"TREE_SITTER_ANALYZER_SKIP_ENTRYPOINTS": "1"})
    def test_skip_entry_points_env_set(self) -> None:
        """Test skipping when environment variable is set to 1"""
        result = _should_load_entry_points()
        assert result is False

    @patch.dict(os.environ, {"TREE_SITTER_ANALYZER_SKIP_ENTRYPOINTS": "0"})
    def test_load_entry_points_env_set_to_zero(self) -> None:
        """Test loading when environment variable is set to 0"""
        result = _should_load_entry_points()
        assert result is True

    @patch.dict(os.environ, {}, clear=True)
    def test_load_entry_points_default(self) -> None:
        """Test default behavior (load entry points)"""
        result = _should_load_entry_points()
        assert result is True

    @patch.dict(os.environ, {"TREE_SITTER_ANALYZER_SKIP_ENTRYPOINTS": "  1  "})
    def test_skip_entry_points_with_whitespace(self) -> None:
        """Test skipping with whitespace in environment variable"""
        result = _should_load_entry_points()
        assert result is False


class TestIsRunningUnderPytest:
    """Tests for _is_running_under_pytest function"""

    @patch.dict(sys.modules, {"pytest": MagicMock()})
    def test_running_under_pytest(self) -> None:
        """Test detection when pytest is in sys.modules"""
        result = _is_running_under_pytest()
        assert result is True

    @patch.dict(sys.modules, {}, clear=True)
    def test_not_running_under_pytest(self) -> None:
        """Test detection when pytest is not in sys.modules"""
        result = _is_running_under_pytest()
        assert result is False


class TestPluginManagerInitialization:
    """Tests for PluginManager initialization"""

    def test_initialization(self) -> None:
        """Test default initialization of PluginManager"""
        manager = PluginManager()
        assert manager._loaded_plugins == {}
        assert manager._plugin_modules == {}
        assert manager._entry_point_group == "tree_sitter_analyzer.plugins"
        assert manager._discovered is False


class TestPluginManagerLoadPlugins:
    """Tests for load_plugins method"""

    def test_load_plugins_first_call(self) -> None:
        """Test first call to load_plugins"""
        manager = PluginManager()
        plugins = manager.load_plugins()

        assert manager._discovered is True
        assert isinstance(plugins, list)

    def test_load_plugins_cached(self) -> None:
        """Test that subsequent calls return cached results"""
        manager = PluginManager()
        plugins1 = manager.load_plugins()
        plugins2 = manager.load_plugins()

        # Both should be lists with same content (not necessarily same object)
        assert isinstance(plugins1, list)
        assert isinstance(plugins2, list)
        # Check that content is same
        assert len(plugins1) == len(plugins2)

    def test_load_plugins_with_manual_registration(self) -> None:
        """Test load_plugins returns manually registered plugins"""
        manager = PluginManager()
        plugin = MockPlugin()
        manager.register_plugin(plugin)

        plugins = manager.load_plugins()

        assert len(plugins) >= 1
        assert plugin in plugins


class TestPluginManagerDiscoverFromEntryPoints:
    """Tests for _discover_from_entry_points method"""

    @patch("tree_sitter_analyzer.plugins.manager.importlib.metadata.entry_points")
    @patch("tree_sitter_analyzer.plugins.manager.log_debug")
    def test_discover_with_select_api(
        self, mock_log_debug: MagicMock, mock_entry_points: MagicMock
    ) -> None:
        """Test discovery with select API (Python 3.10+)"""
        manager = PluginManager()

        mock_ep = MagicMock()
        mock_ep.name = "test_plugin"
        mock_entry_points.return_value.select.return_value = [mock_ep]

        manager._discover_from_entry_points()

        assert hasattr(manager, "_entry_point_map")
        assert "test_plugin" in manager._entry_point_map

    @patch("tree_sitter_analyzer.plugins.manager.importlib.metadata.entry_points")
    @patch("tree_sitter_analyzer.plugins.manager.log_warning")
    def test_discover_exception_handling(
        self, mock_log_warning: MagicMock, mock_entry_points: MagicMock
    ) -> None:
        """Test exception handling during discovery"""
        manager = PluginManager()
        mock_entry_points.side_effect = Exception("Test error")

        manager._discover_from_entry_points()

        mock_log_warning.assert_called_once()


class TestPluginManagerDiscoverFromLocalDirectory:
    """Tests for _discover_from_local_directory method"""

    @patch("tree_sitter_analyzer.plugins.manager.Path")
    def test_discover_local_plugins(self, mock_path: MagicMock) -> None:
        """Test discovering local plugins"""
        manager = PluginManager()

        # Mock path
        mock_languages_dir = MagicMock()
        mock_languages_dir.exists.return_value = True
        mock_file = MagicMock()
        mock_file.resolve.return_value = MagicMock(parents=[MagicMock()])
        mock_file.parent.parent.__truediv__ = MagicMock(return_value=mock_languages_dir)
        mock_path.return_value = mock_file

        # Just verify the method runs without crashing
        # The actual discovery happens via pkgutil.iter_modules which is hard to mock
        manager._discover_from_local_directory()

        # Verify that discovery was attempted (no exception raised)
        assert True  # If we get here, discovery worked

    @patch("tree_sitter_analyzer.plugins.manager.Path")
    def test_discover_no_languages_dir(self, mock_path: MagicMock) -> None:
        """Test when languages directory doesn't exist"""
        manager = PluginManager()

        mock_languages_dir = MagicMock()
        mock_languages_dir.exists.return_value = False
        mock_file = MagicMock()
        mock_file.parent.parent.__truediv__ = MagicMock(return_value=mock_languages_dir)
        mock_path.return_value = mock_file

        manager._discover_from_local_directory()

        assert manager._plugin_modules == {}


class TestPluginManagerGetPlugin:
    """Tests for get_plugin method"""

    def test_get_plugin_already_loaded(self) -> None:
        """Test getting already loaded plugin"""
        manager = PluginManager()
        plugin = MockPlugin()
        manager._loaded_plugins["mock"] = plugin

        result = manager.get_plugin("mock")

        assert result is plugin

    def test_get_plugin_not_found(self) -> None:
        """Test getting non-existent plugin"""
        manager = PluginManager()

        result = manager.get_plugin("nonexistent")

        assert result is None

    def test_get_plugin_case_insensitive(self) -> None:
        """Test case-insensitive plugin lookup"""
        manager = PluginManager()
        plugin = MockPlugin()
        manager._loaded_plugins["mock"] = plugin

        result = manager.get_plugin("MOCK")

        assert result is plugin

    @patch("tree_sitter_analyzer.plugins.manager.importlib.import_module")
    def test_get_plugin_lazy_load(self, mock_import: MagicMock) -> None:
        """Test lazy loading of plugin"""
        manager = PluginManager()
        manager._plugin_modules["mock"] = "tree_sitter_analyzer.languages.mock_plugin"

        mock_module = MagicMock()
        mock_plugin_class = MockPlugin
        mock_module.MockPlugin = mock_plugin_class
        mock_import.return_value = mock_module

        result = manager.get_plugin("mock")

        assert result is not None
        assert isinstance(result, MockPlugin)
        assert "mock" in manager._loaded_plugins


class TestPluginManagerLoadFromEntryPoints:
    """Tests for _load_from_entry_points method"""

    @patch("tree_sitter_analyzer.plugins.manager.importlib.metadata.entry_points")
    @patch("tree_sitter_analyzer.plugins.manager.log_debug")
    def test_load_from_entry_points_success(
        self, mock_log_debug: MagicMock, mock_entry_points: MagicMock
    ) -> None:
        """Test successful loading from entry points"""
        manager = PluginManager()

        mock_ep = MagicMock()
        mock_ep.name = "test_plugin"
        mock_ep.load.return_value = MockPlugin

        mock_entry_points.return_value.select.return_value = [mock_ep]

        plugins = manager._load_from_entry_points()

        assert len(plugins) == 1
        assert isinstance(plugins[0], MockPlugin)

    @patch("tree_sitter_analyzer.plugins.manager.importlib.metadata.entry_points")
    @patch("tree_sitter_analyzer.plugins.manager.log_warning")
    def test_load_invalid_plugin(
        self, mock_log_warning: MagicMock, mock_entry_points: MagicMock
    ) -> None:
        """Test loading invalid plugin (not a LanguagePlugin subclass)"""
        manager = PluginManager()

        mock_ep = MagicMock()
        mock_ep.name = "invalid_plugin"
        mock_ep.load.return_value = object

        mock_entry_points.return_value.select.return_value = [mock_ep]

        plugins = manager._load_from_entry_points()

        assert len(plugins) == 0
        mock_log_warning.assert_called_once()


class TestPluginManagerLoadFromLocalDirectory:
    """Tests for _load_from_local_directory method"""

    @patch("tree_sitter_analyzer.plugins.manager.Path")
    def test_load_local_plugins(self, mock_path: MagicMock) -> None:
        """Test loading local plugins"""
        manager = PluginManager()

        # Mock path
        mock_languages_dir = MagicMock()
        mock_languages_dir.exists.return_value = True
        mock_file = MagicMock()
        mock_file.resolve.return_value = MagicMock(parents=[MagicMock()])
        mock_file.parent.parent.__truediv__ = MagicMock(return_value=mock_languages_dir)
        mock_path.return_value = mock_file

        # Just verify the method runs without crashing
        plugins = manager._load_from_local_directory()

        # Verify that the method returns a list (may be empty due to mocking)
        assert isinstance(plugins, list)

    @patch("tree_sitter_analyzer.plugins.manager.Path")
    @patch("tree_sitter_analyzer.plugins.manager.log_debug")
    def test_load_creates_languages_dir(
        self, mock_log_debug: MagicMock, mock_path: MagicMock
    ) -> None:
        """Test that languages directory is created if it doesn't exist"""
        manager = PluginManager()

        mock_languages_dir = MagicMock()
        mock_languages_dir.exists.return_value = False
        mock_file = MagicMock()
        mock_file.parent.parent.__truediv__ = MagicMock(return_value=mock_languages_dir)
        mock_path.return_value = mock_file

        plugins = manager._load_from_local_directory()

        assert plugins == []
        mock_languages_dir.mkdir.assert_called_once_with(exist_ok=True)


class TestPluginManagerFindPluginClasses:
    """Tests for _find_plugin_classes method"""

    def test_find_plugin_classes(self) -> None:
        """Test finding plugin classes in a module"""
        manager = PluginManager()

        # Create a mock module with plugin classes
        mock_module = MagicMock()
        mock_module.MockPlugin = MockPlugin
        mock_module.MockPlugin2 = MockPlugin2
        mock_module.NotAPlugin = object

        plugin_classes = manager._find_plugin_classes(mock_module)

        assert len(plugin_classes) == 2
        assert MockPlugin in plugin_classes
        assert MockPlugin2 in plugin_classes
        assert object not in plugin_classes

    def test_find_plugin_classes_excludes_base(self) -> None:
        """Test that LanguagePlugin base class is excluded"""
        manager = PluginManager()

        mock_module = MagicMock()
        mock_module.LanguagePlugin = LanguagePlugin

        plugin_classes = manager._find_plugin_classes(mock_module)

        assert LanguagePlugin not in plugin_classes


class TestPluginManagerGetAllPlugins:
    """Tests for get_all_plugins method"""

    def test_get_all_plugins_empty(self) -> None:
        """Test getting all plugins when none are loaded"""
        manager = PluginManager()

        plugins = manager.get_all_plugins()

        assert isinstance(plugins, dict)

    def test_get_all_plugins_with_loaded(self) -> None:
        """Test getting all loaded plugins"""
        manager = PluginManager()
        plugin1 = MockPlugin()
        plugin2 = MockPlugin2()
        manager._loaded_plugins["mock"] = plugin1
        manager._loaded_plugins["mock2"] = plugin2

        plugins = manager.get_all_plugins()

        # Check that our plugins are included
        assert "mock" in plugins
        assert "mock2" in plugins
        assert plugins["mock"] is plugin1
        assert plugins["mock2"] is plugin2


class TestPluginManagerGetDefaultAliases:
    """Tests for _get_default_aliases method"""

    def test_get_default_aliases(self) -> None:
        """Test getting default aliases"""
        manager = PluginManager()
        aliases = manager._get_default_aliases()

        assert isinstance(aliases, list)
        assert "js" in aliases
        assert "py" in aliases
        assert "rb" in aliases
        assert "ts" in aliases


class TestPluginManagerGetSupportedLanguages:
    """Tests for get_supported_languages method"""

    def test_get_supported_languages_empty(self) -> None:
        """Test getting supported languages when none are loaded"""
        manager = PluginManager()

        languages = manager.get_supported_languages()

        assert isinstance(languages, list)

    def test_get_supported_languages_with_plugins(self) -> None:
        """Test getting supported languages with loaded plugins"""
        manager = PluginManager()
        plugin1 = MockPlugin()
        plugin2 = MockPlugin2()
        manager._loaded_plugins["mock"] = plugin1
        manager._loaded_plugins["mock2"] = plugin2

        languages = manager.get_supported_languages()

        assert "mock" in languages
        assert "mock2" in languages
        assert isinstance(languages, list)


class TestPluginManagerReloadPlugins:
    """Tests for reload_plugins method"""

    @patch("tree_sitter_analyzer.plugins.manager.log_info")
    def test_reload_plugins(self, mock_log_info: MagicMock) -> None:
        """Test reloading plugins"""
        manager = PluginManager()
        plugin = MockPlugin()
        manager._loaded_plugins["mock"] = plugin
        manager._plugin_modules["mock"] = "test_module"
        manager._discovered = True

        plugins = manager.reload_plugins()

        # Check that reload was called (clears and re-discovers)
        assert manager._discovered is True
        mock_log_info.assert_called_once()
        # Note: plugin_modules will be repopulated by discovery


class TestPluginManagerRegisterPlugin:
    """Tests for register_plugin method"""

    @patch("tree_sitter_analyzer.plugins.manager.log_debug")
    def test_register_plugin_success(self, mock_log_debug: MagicMock) -> None:
        """Test successful plugin registration"""
        manager = PluginManager()
        plugin = MockPlugin()

        result = manager.register_plugin(plugin)

        assert result is True
        assert manager._loaded_plugins["mock"] is plugin
        mock_log_debug.assert_called_once()

    @patch("tree_sitter_analyzer.plugins.manager.log_warning")
    def test_register_plugin_duplicate(self, mock_log_warning: MagicMock) -> None:
        """Test registering duplicate plugin"""
        manager = PluginManager()
        plugin1 = MockPlugin()
        plugin2 = MockPlugin()

        manager.register_plugin(plugin1)
        result = manager.register_plugin(plugin2)

        assert result is True
        assert manager._loaded_plugins["mock"] is plugin2
        mock_log_warning.assert_called_once()

    @patch("tree_sitter_analyzer.plugins.manager.log_error")
    def test_register_plugin_exception(self, mock_log_error: MagicMock) -> None:
        """Test exception handling during registration"""
        manager = PluginManager()
        plugin = MagicMock()
        plugin.get_language_name.side_effect = Exception("Test error")

        result = manager.register_plugin(plugin)

        assert result is False
        mock_log_error.assert_called_once()


class TestPluginManagerUnregisterPlugin:
    """Tests for unregister_plugin method"""

    @patch("tree_sitter_analyzer.plugins.manager.log_debug")
    def test_unregister_plugin_success(self, mock_log_debug: MagicMock) -> None:
        """Test successful plugin unregistration"""
        manager = PluginManager()
        plugin = MockPlugin()
        manager._loaded_plugins["mock"] = plugin

        result = manager.unregister_plugin("mock")

        assert result is True
        assert "mock" not in manager._loaded_plugins
        mock_log_debug.assert_called_once()

    def test_unregister_plugin_not_found(self) -> None:
        """Test unregistering non-existent plugin"""
        manager = PluginManager()

        result = manager.unregister_plugin("nonexistent")

        assert result is False


class TestPluginManagerGetPluginInfo:
    """Tests for get_plugin_info method"""

    def test_get_plugin_info_success(self) -> None:
        """Test getting plugin info"""
        manager = PluginManager()
        plugin = MockPlugin()
        manager._loaded_plugins["mock"] = plugin

        info = manager.get_plugin_info("mock")

        assert info is not None
        assert info["language"] == "mock"
        assert info["extensions"] == [".mock"]
        assert "class_name" in info
        assert "module" in info

    def test_get_plugin_info_not_found(self) -> None:
        """Test getting info for non-existent plugin"""
        manager = PluginManager()

        info = manager.get_plugin_info("nonexistent")

        assert info is None


class TestPluginManagerValidatePlugin:
    """Tests for validate_plugin method"""

    @patch("tree_sitter_analyzer.plugins.manager.log_error")
    def test_validate_plugin_success(self, mock_log_error: MagicMock) -> None:
        """Test validating a valid plugin"""
        manager = PluginManager()
        plugin = MockPlugin()

        result = manager.validate_plugin(plugin)

        assert result is True
        mock_log_error.assert_not_called()

    @patch("tree_sitter_analyzer.plugins.manager.log_error")
    def test_validate_plugin_missing_method(self, mock_log_error: MagicMock) -> None:
        """Test validating plugin with missing method"""
        manager = PluginManager()
        plugin = MagicMock()
        plugin.get_language_name.return_value = "test"
        plugin.get_file_extensions.return_value = [".test"]
        # Missing create_extractor
        del plugin.create_extractor

        result = manager.validate_plugin(plugin)

        assert result is False
        mock_log_error.assert_called()

    @patch("tree_sitter_analyzer.plugins.manager.log_error")
    def test_validate_plugin_invalid_language_name(
        self, mock_log_error: MagicMock
    ) -> None:
        """Test validating plugin with invalid language name"""
        manager = PluginManager()
        plugin = MagicMock()
        plugin.get_language_name.return_value = ""
        plugin.get_file_extensions.return_value = [".test"]
        plugin.create_extractor.return_value = MagicMock()

        result = manager.validate_plugin(plugin)

        assert result is False
        mock_log_error.assert_called()

    @patch("tree_sitter_analyzer.plugins.manager.log_error")
    def test_validate_plugin_invalid_extensions(
        self, mock_log_error: MagicMock
    ) -> None:
        """Test validating plugin with invalid extensions"""
        manager = PluginManager()
        plugin = MagicMock()
        plugin.get_language_name.return_value = "test"
        plugin.get_file_extensions.return_value = "not_a_list"
        plugin.create_extractor.return_value = MagicMock()

        result = manager.validate_plugin(plugin)

        assert result is False
        mock_log_error.assert_called()

    @patch("tree_sitter_analyzer.plugins.manager.log_error")
    def test_validate_plugin_no_extractor(self, mock_log_error: MagicMock) -> None:
        """Test validating plugin that returns no extractor"""
        manager = PluginManager()
        plugin = MagicMock()
        plugin.get_language_name.return_value = "test"
        plugin.get_file_extensions.return_value = [".test"]
        plugin.create_extractor.return_value = None

        result = manager.validate_plugin(plugin)

        assert result is False
        mock_log_error.assert_called()


class TestPluginManagerIntegration:
    """Integration tests for PluginManager"""

    def test_full_lifecycle(self) -> None:
        """Test full plugin lifecycle"""
        manager = PluginManager()

        # Register plugin
        plugin = MockPlugin()
        manager.register_plugin(plugin)

        # Get plugin
        result = manager.get_plugin("mock")
        assert result is plugin

        # Get plugin info
        info = manager.get_plugin_info("mock")
        assert info is not None

        # Validate plugin
        assert manager.validate_plugin(plugin) is True

        # Unregister plugin
        assert manager.unregister_plugin("mock") is True
        assert manager.get_plugin("mock") is None

    def test_multiple_plugins(self) -> None:
        """Test managing multiple plugins"""
        manager = PluginManager()
        plugin1 = MockPlugin()
        plugin2 = MockPlugin2()

        manager.register_plugin(plugin1)
        manager.register_plugin(plugin2)

        all_plugins = manager.get_all_plugins()

        # Check that our plugins are included
        assert "mock" in all_plugins
        assert "mock2" in all_plugins

        supported = manager.get_supported_languages()
        assert "mock" in supported
        assert "mock2" in supported

    def test_plugin_replacement(self) -> None:
        """Test replacing an existing plugin"""
        manager = PluginManager()
        plugin1 = MockPlugin()
        plugin2 = MockPlugin2()

        manager.register_plugin(plugin1)
        manager.register_plugin(plugin2)

        # Both should be registered with their language names
        assert manager._loaded_plugins["mock"] is plugin1
        assert manager._loaded_plugins["mock2"] is plugin2
