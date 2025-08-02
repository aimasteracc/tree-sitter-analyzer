#!/usr/bin/env python3
"""
Tests for tree_sitter_analyzer.plugins.registry module.

This module tests the LanguageRegistry class which handles language
and plugin mapping in the new architecture.
"""

from pathlib import Path
from unittest.mock import Mock

import pytest

from tree_sitter_analyzer.plugins.base import LanguagePlugin
from tree_sitter_analyzer.plugins.registry import LanguageRegistry


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


class TestLanguageRegistry:
    """Test cases for LanguageRegistry class"""

    @pytest.fixture
    def registry(self) -> LanguageRegistry:
        """Create a LanguageRegistry instance for testing"""
        return LanguageRegistry()

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

    def test_registry_initialization(self, registry: LanguageRegistry) -> None:
        """Test LanguageRegistry initialization"""
        assert registry is not None
        assert hasattr(registry, "register_plugin")
        assert hasattr(registry, "get_plugin")
        assert hasattr(registry, "detect_language_from_file")

    def test_register_plugin_success(
        self, registry: LanguageRegistry, mock_java_plugin: MockLanguagePlugin
    ) -> None:
        """Test successful plugin registration"""
        result = registry.register_plugin(mock_java_plugin)

        assert result is True
        assert registry.get_plugin("java") is not None

    def test_register_plugin_duplicate(
        self, registry: LanguageRegistry, mock_java_plugin: MockLanguagePlugin
    ) -> None:
        """Test registering duplicate plugin"""
        # Register first time
        result1 = registry.register_plugin(mock_java_plugin)
        assert result1 is True

        # Register again (should replace)
        another_java_plugin = MockLanguagePlugin("java", [".java"])
        result2 = registry.register_plugin(another_java_plugin)
        assert result2 is True

    def test_register_plugin_with_exception(self, registry: LanguageRegistry) -> None:
        """Test plugin registration with exception"""
        mock_plugin = Mock()
        mock_plugin.get_language_name.side_effect = Exception("Plugin error")

        result = registry.register_plugin(mock_plugin)

        assert result is False

    def test_get_plugin_existing(
        self, registry: LanguageRegistry, mock_java_plugin: MockLanguagePlugin
    ) -> None:
        """Test getting an existing plugin"""
        registry.register_plugin(mock_java_plugin)

        retrieved_plugin = registry.get_plugin("java")

        assert retrieved_plugin is not None
        assert retrieved_plugin.get_language_name() == "java"

    def test_get_plugin_nonexistent(self, registry: LanguageRegistry) -> None:
        """Test getting a non-existent plugin"""
        retrieved_plugin = registry.get_plugin("nonexistent")

        assert retrieved_plugin is None

    def test_get_plugin_with_alias(
        self, registry: LanguageRegistry, mock_java_plugin: MockLanguagePlugin
    ) -> None:
        """Test getting plugin with language alias"""
        registry.register_plugin(mock_java_plugin)

        # Test with normalized language name
        retrieved_plugin = registry.get_plugin("JAVA")  # Case insensitive

        assert retrieved_plugin is not None
        assert retrieved_plugin.get_language_name() == "java"

    def test_detect_language_from_file_java(
        self, registry: LanguageRegistry, mock_java_plugin: MockLanguagePlugin
    ) -> None:
        """Test language detection from Java file"""
        registry.register_plugin(mock_java_plugin)

        java_file = Path("test.java")
        detected_language = registry.detect_language_from_file(java_file)

        assert detected_language == "java"

    def test_detect_language_from_file_python(
        self, registry: LanguageRegistry, mock_python_plugin: MockLanguagePlugin
    ) -> None:
        """Test language detection from Python file"""
        registry.register_plugin(mock_python_plugin)

        python_file = Path("test.py")
        detected_language = registry.detect_language_from_file(python_file)

        assert detected_language == "python"

    def test_detect_language_from_file_unknown(
        self, registry: LanguageRegistry
    ) -> None:
        """Test language detection from unknown file"""
        unknown_file = Path("test.xyz")
        detected_language = registry.detect_language_from_file(unknown_file)

        assert detected_language is None

    def test_get_supported_languages(
        self,
        registry: LanguageRegistry,
        mock_java_plugin: MockLanguagePlugin,
        mock_python_plugin: MockLanguagePlugin,
    ) -> None:
        """Test getting list of supported languages"""
        registry.register_plugin(mock_java_plugin)
        registry.register_plugin(mock_python_plugin)

        languages = registry.get_supported_languages()

        assert isinstance(languages, list)
        assert len(languages) == 2
        assert "java" in languages
        assert "python" in languages

    def test_get_supported_extensions(
        self,
        registry: LanguageRegistry,
        mock_java_plugin: MockLanguagePlugin,
        mock_python_plugin: MockLanguagePlugin,
    ) -> None:
        """Test getting list of supported extensions"""
        registry.register_plugin(mock_java_plugin)
        registry.register_plugin(mock_python_plugin)

        extensions = registry.get_supported_extensions()

        assert isinstance(extensions, list)
        assert ".java" in extensions
        assert ".py" in extensions
        assert ".pyi" in extensions

    def test_get_extensions_for_language(
        self, registry: LanguageRegistry, mock_python_plugin: MockLanguagePlugin
    ) -> None:
        """Test getting extensions for specific language"""
        registry.register_plugin(mock_python_plugin)

        extensions = registry.get_extensions_for_language("python")

        assert isinstance(extensions, list)
        assert ".py" in extensions
        assert ".pyi" in extensions

    def test_get_extensions_for_unknown_language(
        self, registry: LanguageRegistry
    ) -> None:
        """Test getting extensions for unknown language"""
        extensions = registry.get_extensions_for_language("unknown")

        assert isinstance(extensions, list)
        assert len(extensions) == 0

    def test_get_language_for_extension(
        self, registry: LanguageRegistry, mock_java_plugin: MockLanguagePlugin
    ) -> None:
        """Test getting language for specific extension"""
        registry.register_plugin(mock_java_plugin)

        language = registry.get_language_for_extension(".java")

        assert language == "java"

    def test_get_language_for_unknown_extension(
        self, registry: LanguageRegistry
    ) -> None:
        """Test getting language for unknown extension"""
        language = registry.get_language_for_extension(".xyz")

        assert language is None

    def test_is_language_supported(
        self, registry: LanguageRegistry, mock_java_plugin: MockLanguagePlugin
    ) -> None:
        """Test checking if language is supported"""
        registry.register_plugin(mock_java_plugin)

        assert registry.is_language_supported("java") is True
        assert registry.is_language_supported("unknown") is False

    def test_is_extension_supported(
        self, registry: LanguageRegistry, mock_java_plugin: MockLanguagePlugin
    ) -> None:
        """Test checking if extension is supported"""
        registry.register_plugin(mock_java_plugin)

        assert registry.is_extension_supported(".java") is True
        assert registry.is_extension_supported(".xyz") is False

    def test_add_language_alias(
        self, registry: LanguageRegistry, mock_java_plugin: MockLanguagePlugin
    ) -> None:
        """Test adding language alias"""
        registry.register_plugin(mock_java_plugin)

        result = registry.add_language_alias("jvm", "java")

        assert result is True

        # Test that alias works
        retrieved_plugin = registry.get_plugin("jvm")
        assert retrieved_plugin is not None
        assert retrieved_plugin.get_language_name() == "java"

    def test_add_language_alias_for_unknown_language(
        self, registry: LanguageRegistry
    ) -> None:
        """Test adding alias for unknown language"""
        result = registry.add_language_alias("alias", "unknown")

        assert result is False

    def test_get_registry_info(
        self,
        registry: LanguageRegistry,
        mock_java_plugin: MockLanguagePlugin,
        mock_python_plugin: MockLanguagePlugin,
    ) -> None:
        """Test getting registry information"""
        registry.register_plugin(mock_java_plugin)
        registry.register_plugin(mock_python_plugin)

        info = registry.get_registry_info()

        assert isinstance(info, dict)
        assert "languages" in info
        assert "extensions" in info
        assert "plugin_count" in info
        assert info["plugin_count"] == 2

    def test_find_plugins_for_file(
        self,
        registry: LanguageRegistry,
        mock_java_plugin: MockLanguagePlugin,
        mock_python_plugin: MockLanguagePlugin,
    ) -> None:
        """Test finding plugins for specific file"""
        registry.register_plugin(mock_java_plugin)
        registry.register_plugin(mock_python_plugin)

        java_file = Path("test.java")
        plugins = registry.find_plugins_for_file(java_file)

        assert isinstance(plugins, list)
        assert len(plugins) == 1
        assert plugins[0].get_language_name() == "java"

    def test_find_plugins_for_file_no_match(
        self, registry: LanguageRegistry, mock_java_plugin: MockLanguagePlugin
    ) -> None:
        """Test finding plugins for file with no matching plugins"""
        registry.register_plugin(mock_java_plugin)

        unknown_file = Path("test.xyz")
        plugins = registry.find_plugins_for_file(unknown_file)

        assert isinstance(plugins, list)
        assert len(plugins) == 0

    def test_clear_registry(
        self, registry: LanguageRegistry, mock_java_plugin: MockLanguagePlugin
    ) -> None:
        """Test clearing the registry"""
        registry.register_plugin(mock_java_plugin)

        # Verify plugin is registered
        assert registry.get_plugin("java") is not None

        # Clear registry
        registry.clear()

        # Verify plugin is removed
        assert registry.get_plugin("java") is None
        assert len(registry.get_supported_languages()) == 0

    def test_unregister_plugin_existing(
        self, registry: LanguageRegistry, mock_java_plugin: MockLanguagePlugin
    ) -> None:
        """Test unregistering an existing plugin"""
        registry.register_plugin(mock_java_plugin)

        result = registry.unregister_plugin("java")

        assert result is True
        assert registry.get_plugin("java") is None

    def test_unregister_plugin_nonexistent(self, registry: LanguageRegistry) -> None:
        """Test unregistering a non-existent plugin"""
        result = registry.unregister_plugin("nonexistent")

        assert result is False


class TestLanguageRegistryErrorHandling:
    """Test error handling in LanguageRegistry"""

    @pytest.fixture
    def registry(self) -> LanguageRegistry:
        """Create a LanguageRegistry instance for testing"""
        return LanguageRegistry()

    def test_register_plugin_none(self, registry: LanguageRegistry) -> None:
        """Test registering None as plugin"""
        result = registry.register_plugin(None)

        assert result is False

    def test_detect_language_from_file_none(self, registry: LanguageRegistry) -> None:
        """Test language detection with None file"""
        detected_language = registry.detect_language_from_file(None)

        assert detected_language is None

    def test_get_plugin_none_language(self, registry: LanguageRegistry) -> None:
        """Test getting plugin with None language"""
        retrieved_plugin = registry.get_plugin(None)

        assert retrieved_plugin is None

    def test_get_plugin_empty_language(self, registry: LanguageRegistry) -> None:
        """Test getting plugin with empty language"""
        retrieved_plugin = registry.get_plugin("")

        assert retrieved_plugin is None

    def test_add_language_alias_none_values(self, registry: LanguageRegistry) -> None:
        """Test adding language alias with None values"""
        result1 = registry.add_language_alias(None, "java")
        result2 = registry.add_language_alias("alias", None)

        assert result1 is False
        assert result2 is False

    def test_plugin_with_invalid_extensions(self, registry: LanguageRegistry) -> None:
        """Test plugin with invalid extensions"""
        mock_plugin = Mock()
        mock_plugin.get_language_name.return_value = "test"
        mock_plugin.get_file_extensions.side_effect = Exception("Extensions error")

        result = registry.register_plugin(mock_plugin)

        # Should handle gracefully
        assert result is False


class TestLanguageRegistryIntegration:
    """Integration tests for LanguageRegistry"""

    @pytest.fixture
    def registry(self) -> LanguageRegistry:
        """Create a LanguageRegistry instance for testing"""
        return LanguageRegistry()

    def test_multiple_plugins_with_same_extension(
        self, registry: LanguageRegistry
    ) -> None:
        """Test multiple plugins supporting the same extension"""
        # Create plugins that both support .js
        js_plugin = MockLanguagePlugin("javascript", [".js"])
        ts_plugin = MockLanguagePlugin("typescript", [".js", ".ts"])

        registry.register_plugin(js_plugin)
        registry.register_plugin(ts_plugin)

        # Should find both plugins for .js files
        js_file = Path("test.js")
        plugins = registry.find_plugins_for_file(js_file)

        assert len(plugins) >= 1  # At least one plugin should match

    def test_case_insensitive_language_handling(
        self, registry: LanguageRegistry
    ) -> None:
        """Test case insensitive language handling"""
        java_plugin = MockLanguagePlugin("java", [".java"])
        registry.register_plugin(java_plugin)

        # Test various case combinations
        assert registry.get_plugin("java") is not None
        assert registry.get_plugin("JAVA") is not None
        assert registry.get_plugin("Java") is not None

        assert registry.is_language_supported("java") is True
        assert registry.is_language_supported("JAVA") is True

    def test_extension_normalization(self, registry: LanguageRegistry) -> None:
        """Test extension normalization"""
        java_plugin = MockLanguagePlugin("java", ["java", ".java"])  # Mixed formats
        registry.register_plugin(java_plugin)

        # Should handle both formats
        assert registry.is_extension_supported(".java") is True
        assert registry.get_language_for_extension(".java") == "java"

    def test_registry_with_many_plugins(self, registry: LanguageRegistry) -> None:
        """Test registry performance with many plugins"""
        plugins = []
        for i in range(50):
            plugin = MockLanguagePlugin(f"lang{i}", [f".ext{i}"])
            plugins.append(plugin)
            registry.register_plugin(plugin)

        # Verify all plugins are registered
        assert len(registry.get_supported_languages()) == 50

        # Verify specific lookups work
        assert registry.get_plugin("lang25") is not None
        assert registry.is_extension_supported(".ext25") is True

    def test_plugin_replacement_workflow(self, registry: LanguageRegistry) -> None:
        """Test plugin replacement workflow"""
        # Register initial plugin
        old_plugin = MockLanguagePlugin("java", [".java"])
        registry.register_plugin(old_plugin)

        old_retrieved = registry.get_plugin("java")
        assert old_retrieved is old_plugin

        # Replace with new plugin
        new_plugin = MockLanguagePlugin("java", [".java", ".jav"])
        registry.register_plugin(new_plugin)

        new_retrieved = registry.get_plugin("java")
        assert new_retrieved is new_plugin
        assert new_retrieved is not old_plugin

        # Verify new extensions are available
        extensions = registry.get_extensions_for_language("java")
        assert ".jav" in extensions

    def test_registry_state_consistency(self, registry: LanguageRegistry) -> None:
        """Test registry state consistency across operations"""
        # Add plugins
        java_plugin = MockLanguagePlugin("java", [".java"])
        python_plugin = MockLanguagePlugin("python", [".py"])

        registry.register_plugin(java_plugin)
        registry.register_plugin(python_plugin)

        # Verify initial state
        assert len(registry.get_supported_languages()) == 2
        assert len(registry.get_supported_extensions()) == 2

        # Remove one plugin
        registry.unregister_plugin("java")

        # Verify state consistency
        assert len(registry.get_supported_languages()) == 1
        assert len(registry.get_supported_extensions()) == 1
        assert "python" in registry.get_supported_languages()
        assert ".py" in registry.get_supported_extensions()
        assert "java" not in registry.get_supported_languages()
        assert ".java" not in registry.get_supported_extensions()
