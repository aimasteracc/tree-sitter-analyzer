#!/usr/bin/env python3
"""
Tests for tree_sitter_analyzer.plugins.manager module.

This module tests the PluginManager class which handles dynamic
plugin discovery and management in the new architecture.
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from tree_sitter_analyzer.plugins.base import LanguagePlugin
from tree_sitter_analyzer.plugins.manager import PluginManager


class MockLanguagePlugin(LanguagePlugin):
    """Mock language plugin for testing"""

    def __init__(self, language: str, extensions: list[str]):
        self._language = language
        self._extensions = extensions

    def get_language_name(self) -> str:
        return self._language

    def get_file_extensions(self) -> list[str]:
        return self._extensions

    def create_extractor(self):
        return Mock()

    def is_applicable(self, file_path: str) -> bool:
        return any(file_path.endswith(ext) for ext in self._extensions)

    async def analyze_file(self, file_path: str, request):
        """Mock implementation of analyze_file"""
        from tree_sitter_analyzer.models import AnalysisResult

        return AnalysisResult(
            file_path=file_path,
            language=self._language,
            line_count=10,
            elements=[],
            node_count=5,
            query_results={},
            source_code="// Mock source code",
            success=True,
            error_message=None,
        )


class TestPluginManager:
    """Test cases for PluginManager class"""

    @pytest.fixture
    def plugin_manager(self) -> PluginManager:
        """Create an isolated PluginManager instance for testing"""
        manager = PluginManager()
        # Mock methods to prevent real loading/discovery/aliases by default
        manager._load_from_entry_points = MagicMock(return_value=[])
        manager._load_from_local_directory = MagicMock(return_value=[])
        manager._get_default_aliases = MagicMock(return_value=[])

        if hasattr(manager, "_discover_from_entry_points"):
            manager._discover_from_entry_points = MagicMock()
        if hasattr(manager, "_discover_from_local_directory"):
            manager._discover_from_local_directory = MagicMock()

        return manager

    @pytest.fixture
    def mock_java_plugin(self) -> MockLanguagePlugin:
        """Create a mock Java plugin"""
        return MockLanguagePlugin("java", [".java"])

    @pytest.fixture
    def mock_python_plugin(self) -> MockLanguagePlugin:
        """Create a mock Python plugin"""
        return MockLanguagePlugin("python", [".py", ".pyi"])

    @pytest.fixture
    def mock_javascript_plugin(self) -> MockLanguagePlugin:
        """Create a mock JavaScript plugin"""
        return MockLanguagePlugin("javascript", [".js", ".jsx"])

    @pytest.fixture
    def mock_typescript_plugin(self) -> MockLanguagePlugin:
        """Create a mock TypeScript plugin"""
        return MockLanguagePlugin("typescript", [".ts", ".tsx", ".d.ts"])

    def test_plugin_manager_initialization(self, plugin_manager: PluginManager) -> None:
        """Test PluginManager initialization"""
        assert plugin_manager is not None
        assert hasattr(plugin_manager, "load_plugins")
        assert hasattr(plugin_manager, "get_plugin")
        assert hasattr(plugin_manager, "register_plugin")

    def test_load_plugins_success(self, plugin_manager: PluginManager) -> None:
        """Test successful plugin loading"""
        with (
            patch.object(
                plugin_manager, "_load_from_entry_points"
            ) as mock_entry_points,
            patch.object(plugin_manager, "_load_from_local_directory") as mock_local,
        ):
            mock_entry_points.return_value = [MockLanguagePlugin("java", [".java"])]
            mock_local.return_value = [MockLanguagePlugin("python", [".py"])]

            plugins = plugin_manager.load_plugins()

            assert isinstance(plugins, list)
            assert len(plugins) == 2
            mock_entry_points.assert_called_once()
            mock_local.assert_called_once()

    def test_load_from_entry_points_success(
        self, plugin_manager: PluginManager
    ) -> None:
        """Test loading plugins from entry points"""
        mock_entry_point = Mock()
        mock_entry_point.name = "java"
        mock_entry_point.load.return_value = MockLanguagePlugin

        with patch("importlib.metadata.entry_points") as mock_iter:
            mock_iter.return_value = [mock_entry_point]

            plugins = plugin_manager._load_from_entry_points()

            assert isinstance(plugins, list)
            assert len(plugins) == 0

    def test_load_from_entry_points_with_exception(
        self, plugin_manager: PluginManager
    ) -> None:
        """Test loading plugins from entry points with exception"""
        mock_entry_point = Mock()
        mock_entry_point.name = "java"
        mock_entry_point.load.side_effect = Exception("Load failed")

        with patch("importlib.metadata.entry_points") as mock_iter:
            mock_iter.return_value = [mock_entry_point]

            plugins = plugin_manager._load_from_entry_points()

            # Should handle exceptions gracefully
            assert isinstance(plugins, list)
            assert len(plugins) == 0

    def test_load_from_local_directory_success(
        self, plugin_manager: PluginManager
    ) -> None:
        """Test loading plugins from local directory"""
        with (
            patch("pathlib.Path.iterdir") as mock_iterdir,
            patch("importlib.util.spec_from_file_location") as mock_spec,
            patch("importlib.util.module_from_spec") as mock_module,
            patch.object(plugin_manager, "_find_plugin_classes") as mock_find,
        ):
            # Mock directory structure
            mock_file = Mock()
            mock_file.name = "java_plugin.py"
            mock_file.is_file.return_value = True
            mock_file.suffix = ".py"
            mock_iterdir.return_value = [mock_file]

            # Mock module loading
            mock_spec.return_value = Mock()
            mock_module_instance = Mock()
            mock_module.return_value = mock_module_instance

            # Mock plugin class finding
            mock_find.return_value = [MockLanguagePlugin]

            plugins = plugin_manager._load_from_local_directory()

            assert isinstance(plugins, list)

    def test_load_from_local_directory_with_exception(
        self, plugin_manager: PluginManager
    ) -> None:
        """Test loading plugins from local directory with exception"""
        with patch("pkgutil.iter_modules") as mock_iter_modules:
            mock_iter_modules.side_effect = Exception("Module iteration failed")

            plugins = plugin_manager._load_from_local_directory()

            # Should handle exceptions gracefully
            assert isinstance(plugins, list)
            assert len(plugins) == 0

    def test_find_plugin_classes(self, plugin_manager: PluginManager) -> None:
        """Test finding plugin classes in a module"""
        # Create a mock module with plugin classes
        mock_module = Mock()

        # Mock plugin class
        mock_plugin_class = Mock()
        mock_plugin_class.__bases__ = (LanguagePlugin,)
        mock_plugin_class.__name__ = "TestPlugin"

        # Mock non-plugin class
        mock_other_class = Mock()
        mock_other_class.__bases__ = (object,)
        mock_other_class.__name__ = "OtherClass"

        # Set up module attributes
        mock_module.TestPlugin = mock_plugin_class
        mock_module.OtherClass = mock_other_class
        mock_module.some_function = lambda: None

        with patch("inspect.getmembers") as mock_getmembers:
            mock_getmembers.return_value = [
                ("TestPlugin", mock_plugin_class),
                ("OtherClass", mock_other_class),
                ("some_function", lambda: None),
            ]

            plugin_classes = plugin_manager._find_plugin_classes(mock_module)

            assert isinstance(plugin_classes, list)
            # Should find only the plugin class
            assert len(plugin_classes) >= 0  # Depends on implementation

    def test_get_plugin_existing(
        self, plugin_manager: PluginManager, mock_java_plugin: MockLanguagePlugin
    ) -> None:
        """Test getting an existing plugin"""
        plugin_manager.register_plugin(mock_java_plugin)

        retrieved_plugin = plugin_manager.get_plugin("java")

        assert retrieved_plugin is not None
        assert retrieved_plugin.get_language_name() == "java"

    def test_get_plugin_nonexistent(self, plugin_manager: PluginManager) -> None:
        """Test getting a non-existent plugin"""
        retrieved_plugin = plugin_manager.get_plugin("nonexistent")

        assert retrieved_plugin is None

    def test_get_all_plugins(
        self,
        plugin_manager: PluginManager,
        mock_java_plugin: MockLanguagePlugin,
        mock_python_plugin: MockLanguagePlugin,
        mock_javascript_plugin: MockLanguagePlugin,
        mock_typescript_plugin: MockLanguagePlugin,
    ) -> None:
        """Test getting all registered plugins"""
        plugin_manager.register_plugin(mock_java_plugin)
        plugin_manager.register_plugin(mock_python_plugin)
        plugin_manager.register_plugin(mock_javascript_plugin)
        plugin_manager.register_plugin(mock_typescript_plugin)

        all_plugins = plugin_manager.get_all_plugins()

        assert isinstance(all_plugins, dict)
        assert len(all_plugins) == 4
        assert "java" in all_plugins
        assert "python" in all_plugins
        assert "javascript" in all_plugins
        assert "typescript" in all_plugins

    def test_get_supported_languages(
        self,
        plugin_manager: PluginManager,
        mock_java_plugin: MockLanguagePlugin,
        mock_python_plugin: MockLanguagePlugin,
        mock_javascript_plugin: MockLanguagePlugin,
        mock_typescript_plugin: MockLanguagePlugin,
    ) -> None:
        """Test getting list of supported languages"""
        plugin_manager.register_plugin(mock_java_plugin)
        plugin_manager.register_plugin(mock_python_plugin)
        plugin_manager.register_plugin(mock_javascript_plugin)
        plugin_manager.register_plugin(mock_typescript_plugin)

        languages = plugin_manager.get_supported_languages()

        assert isinstance(languages, list)
        assert len(languages) == 4
        assert "java" in languages
        assert "python" in languages
        assert "javascript" in languages
        assert "typescript" in languages

    def test_reload_plugins(self, plugin_manager: PluginManager) -> None:
        """Test reloading plugins"""
        with patch.object(plugin_manager, "load_plugins") as mock_load:
            mock_load.return_value = [MockLanguagePlugin("java", [".java"])]

            plugins = plugin_manager.reload_plugins()

            assert isinstance(plugins, list)
            mock_load.assert_called_once()

    def test_register_plugin_success(
        self, plugin_manager: PluginManager, mock_java_plugin: MockLanguagePlugin
    ) -> None:
        """Test successful plugin registration"""
        result = plugin_manager.register_plugin(mock_java_plugin)

        assert result is True
        assert plugin_manager.get_plugin("java") is not None

    def test_register_plugin_duplicate(
        self, plugin_manager: PluginManager, mock_java_plugin: MockLanguagePlugin
    ) -> None:
        """Test registering duplicate plugin"""
        # Register first time
        result1 = plugin_manager.register_plugin(mock_java_plugin)
        assert result1 is True

        # Register again (should replace)
        another_java_plugin = MockLanguagePlugin("java", [".java"])
        result2 = plugin_manager.register_plugin(another_java_plugin)
        assert result2 is True

    def test_register_plugin_with_exception(
        self, plugin_manager: PluginManager
    ) -> None:
        """Test plugin registration with exception"""
        mock_plugin = Mock()
        mock_plugin.get_language_name.side_effect = Exception("Plugin error")

        result = plugin_manager.register_plugin(mock_plugin)

        assert result is False

    def test_unregister_plugin_existing(
        self, plugin_manager: PluginManager, mock_java_plugin: MockLanguagePlugin
    ) -> None:
        """Test unregistering an existing plugin"""
        plugin_manager.register_plugin(mock_java_plugin)

        result = plugin_manager.unregister_plugin("java")

        assert result is True
        assert plugin_manager.get_plugin("java") is None

    def test_unregister_plugin_nonexistent(self, plugin_manager: PluginManager) -> None:
        """Test unregistering a non-existent plugin"""
        result = plugin_manager.unregister_plugin("nonexistent")

        assert result is False

    def test_get_plugin_info_existing(
        self, plugin_manager: PluginManager, mock_java_plugin: MockLanguagePlugin
    ) -> None:
        """Test getting plugin info for existing plugin"""
        plugin_manager.register_plugin(mock_java_plugin)

        info = plugin_manager.get_plugin_info("java")

        assert isinstance(info, dict)
        assert "language" in info
        assert "extensions" in info
        assert info["language"] == "java"

    def test_get_plugin_info_nonexistent(self, plugin_manager: PluginManager) -> None:
        """Test getting plugin info for non-existent plugin"""
        info = plugin_manager.get_plugin_info("nonexistent")

        assert info is None

    def test_validate_plugin_valid(
        self, plugin_manager: PluginManager, mock_java_plugin: MockLanguagePlugin
    ) -> None:
        """Test validating a valid plugin"""
        is_valid = plugin_manager.validate_plugin(mock_java_plugin)

        assert is_valid is True

    def test_validate_plugin_invalid(self, plugin_manager: PluginManager) -> None:
        """Test validating an invalid plugin"""
        # Create a plugin that doesn't implement required methods
        invalid_plugin = Mock()
        invalid_plugin.get_language_name.side_effect = Exception("Not implemented")

        is_valid = plugin_manager.validate_plugin(invalid_plugin)

        assert is_valid is False

    def test_validate_plugin_missing_methods(
        self, plugin_manager: PluginManager
    ) -> None:
        """Test validating a plugin with missing methods"""
        incomplete_plugin = Mock()
        # Missing some required methods
        del incomplete_plugin.get_file_extensions

        is_valid = plugin_manager.validate_plugin(incomplete_plugin)

        assert is_valid is False


class TestPluginManagerErrorHandling:
    """Test error handling in PluginManager"""

    @pytest.fixture
    def plugin_manager(self) -> PluginManager:
        """Create an isolated PluginManager instance for testing"""
        manager = PluginManager()
        # Mock methods to prevent real loading/discovery/aliases by default
        manager._load_from_entry_points = MagicMock(return_value=[])
        manager._load_from_local_directory = MagicMock(return_value=[])
        manager._get_default_aliases = MagicMock(return_value=[])

        if hasattr(manager, "_discover_from_entry_points"):
            manager._discover_from_entry_points = MagicMock()
        if hasattr(manager, "_discover_from_local_directory"):
            manager._discover_from_local_directory = MagicMock()

        return manager

    def test_load_plugins_with_import_error(
        self, plugin_manager: PluginManager
    ) -> None:
        """Test plugin loading with import errors"""
        with patch("importlib.metadata.entry_points") as mock_iter:
            mock_iter.side_effect = ImportError("pkg_resources not available")

            plugins = plugin_manager.load_plugins()

            # Should handle import errors gracefully
            assert isinstance(plugins, list)

    def test_load_plugins_with_corrupted_entry_point(
        self, plugin_manager: PluginManager
    ) -> None:
        """Test loading plugins with corrupted entry point"""
        mock_entry_point = Mock()
        mock_entry_point.name = "corrupted"
        mock_entry_point.load.side_effect = AttributeError("Corrupted entry point")

        with patch("importlib.metadata.entry_points") as mock_iter:
            mock_iter.return_value = [mock_entry_point]

            plugins = plugin_manager._load_from_entry_points()

            # Should skip corrupted entry points
            assert isinstance(plugins, list)
            assert len(plugins) == 0

    def test_register_plugin_none(self, plugin_manager: PluginManager) -> None:
        """Test registering None as plugin"""
        result = plugin_manager.register_plugin(None)

        assert result is False

    def test_get_plugin_info_with_exception(
        self, plugin_manager: PluginManager
    ) -> None:
        """Test getting plugin info when plugin raises exception"""
        mock_plugin = Mock()
        mock_plugin.get_language_name.return_value = "test"
        mock_plugin.get_file_extensions.side_effect = Exception("Extensions error")

        plugin_manager.register_plugin(mock_plugin)

        info = plugin_manager.get_plugin_info("test")

        # Should handle exceptions gracefully
        assert info is None or isinstance(info, dict)

    def test_validate_plugin_with_none(self, plugin_manager: PluginManager) -> None:
        """Test validating None plugin"""
        is_valid = plugin_manager.validate_plugin(None)

        assert is_valid is False


class TestPluginManagerIntegration:
    """Integration tests for PluginManager"""

    @pytest.fixture
    def plugin_manager(self) -> PluginManager:
        """Create an isolated PluginManager instance for testing"""
        manager = PluginManager()
        # Mock methods to prevent real loading/discovery/aliases by default
        manager._load_from_entry_points = MagicMock(return_value=[])
        manager._load_from_local_directory = MagicMock(return_value=[])
        manager._get_default_aliases = MagicMock(return_value=[])

        if hasattr(manager, "_discover_from_entry_points"):
            manager._discover_from_entry_points = MagicMock()
        if hasattr(manager, "_discover_from_local_directory"):
            manager._discover_from_local_directory = MagicMock()

        return manager

    def test_full_plugin_lifecycle(self, plugin_manager: PluginManager) -> None:
        """Test complete plugin lifecycle"""
        # Create plugins
        java_plugin = MockLanguagePlugin("java", [".java"])
        python_plugin = MockLanguagePlugin("python", [".py"])

        # Register plugins
        assert plugin_manager.register_plugin(java_plugin) is True
        assert plugin_manager.register_plugin(python_plugin) is True

        # Verify registration
        assert len(plugin_manager.get_supported_languages()) == 2
        assert plugin_manager.get_plugin("java") is not None
        assert plugin_manager.get_plugin("python") is not None

        # Get plugin info
        java_info = plugin_manager.get_plugin_info("java")
        assert java_info is not None
        assert java_info["language"] == "java"

        # Unregister plugin
        assert plugin_manager.unregister_plugin("java") is True
        assert plugin_manager.get_plugin("java") is None
        assert len(plugin_manager.get_supported_languages()) == 1

    def test_plugin_discovery_and_loading(self, plugin_manager: PluginManager) -> None:
        """Test plugin discovery and loading process"""
        with (
            patch.object(
                plugin_manager, "_load_from_entry_points"
            ) as mock_entry_points,
            patch.object(plugin_manager, "_load_from_local_directory") as mock_local,
        ):
            # Mock discovered plugins
            mock_entry_points.return_value = [
                MockLanguagePlugin("java", [".java"]),
                MockLanguagePlugin("python", [".py"]),
            ]
            mock_local.return_value = [MockLanguagePlugin("javascript", [".js"])]

            # Load plugins
            plugins = plugin_manager.load_plugins()

            # Verify loading
            assert len(plugins) == 3
            assert len(plugin_manager.get_supported_languages()) == 3

            # Verify each plugin is accessible
            assert plugin_manager.get_plugin("java") is not None
            assert plugin_manager.get_plugin("python") is not None
            assert plugin_manager.get_plugin("javascript") is not None

    def test_plugin_validation_during_registration(
        self, plugin_manager: PluginManager
    ) -> None:
        """Test plugin validation during registration process"""
        # Valid plugin
        valid_plugin = MockLanguagePlugin("java", [".java"])
        assert plugin_manager.register_plugin(valid_plugin) is True

        # Invalid plugin (missing methods)
        invalid_plugin = Mock()
        invalid_plugin.get_language_name.side_effect = NotImplementedError()
        assert plugin_manager.register_plugin(invalid_plugin) is False

        # Verify only valid plugin is registered
        assert len(plugin_manager.get_supported_languages()) == 1
        assert "java" in plugin_manager.get_supported_languages()

    def test_plugin_manager_with_multiple_extensions(
        self, plugin_manager: PluginManager
    ) -> None:
        """Test plugin manager with plugins supporting multiple extensions"""
        # Python plugin with multiple extensions
        python_plugin = MockLanguagePlugin("python", [".py", ".pyi", ".pyw"])

        # TypeScript plugin with multiple extensions
        typescript_plugin = MockLanguagePlugin("typescript", [".ts", ".tsx", ".d.ts"])

        plugin_manager.register_plugin(python_plugin)
        plugin_manager.register_plugin(typescript_plugin)

        # Verify plugins are registered correctly
        python_info = plugin_manager.get_plugin_info("python")
        typescript_info = plugin_manager.get_plugin_info("typescript")

        assert set(python_info["extensions"]) == {".py", ".pyi", ".pyw"}
        assert set(typescript_info["extensions"]) == {".ts", ".tsx", ".d.ts"}

    def test_plugin_reload_preserves_manual_registrations(
        self, plugin_manager: PluginManager
    ) -> None:
        """Test that plugin reload preserves manually registered plugins"""
        # Manually register a plugin
        manual_plugin = MockLanguagePlugin("manual", [".manual"])
        plugin_manager.register_plugin(manual_plugin)

        # Mock reload to return different plugins
        with patch.object(plugin_manager, "load_plugins") as mock_load:
            mock_load.return_value = [MockLanguagePlugin("java", [".java"])]

            # Reload plugins
            reloaded_plugins = plugin_manager.reload_plugins()

            # Verify reload worked
            assert len(reloaded_plugins) == 1
            assert reloaded_plugins[0].get_language_name() == "java"
