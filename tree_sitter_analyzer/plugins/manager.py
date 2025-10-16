#!/usr/bin/env python3
"""
Plugin Manager

Dynamic plugin discovery and management system.
Handles loading plugins from entry points and local directories.
"""

import importlib
import importlib.metadata
import logging
import pkgutil
from pathlib import Path
from typing import Any

from ..utils import log_debug, log_error, log_info, log_warning
from .base import LanguagePlugin

logger = logging.getLogger(__name__)


class PluginManager:
    """
    Manages dynamic discovery and loading of language plugins.

    This class handles:
    - Discovery of plugins via entry points
    - Loading plugins from local directories
    - Plugin lifecycle management
    - Error handling and fallback mechanisms
    """

    def __init__(self) -> None:
        """Initialize the plugin manager."""
        self._loaded_plugins: dict[str, LanguagePlugin] = {}
        self._plugin_classes: dict[str, type[LanguagePlugin]] = {}
        self._entry_point_group = "tree_sitter_analyzer.plugins"

    def load_plugins(self) -> list[LanguagePlugin]:
        """
        Load all available plugins from various sources.

        Returns:
            List of successfully loaded plugin instances
        """
        loaded_plugins = []

        # Load plugins from entry points (installed packages)
        entry_point_plugins = self._load_from_entry_points()
        loaded_plugins.extend(entry_point_plugins)

        # Load plugins from local languages directory
        local_plugins = self._load_from_local_directory()
        loaded_plugins.extend(local_plugins)

        # Store loaded plugins and deduplicate by language
        unique_plugins = {}
        for plugin in loaded_plugins:
            language = plugin.get_language_name()
            if language not in unique_plugins:
                unique_plugins[language] = plugin
                self._loaded_plugins[language] = plugin
            else:
                log_debug(f"Skipping duplicate plugin for language: {language}")

        final_plugins = list(unique_plugins.values())
        # Only log if not in CLI mode (check if we're in quiet mode)
        import os

        log_level = os.environ.get("LOG_LEVEL", "WARNING")
        if log_level != "ERROR":
            log_info(f"Successfully loaded {len(final_plugins)} plugins")
        return final_plugins

    def _load_from_entry_points(self) -> list[LanguagePlugin]:
        """
        Load plugins from setuptools entry points.

        Returns:
            List of plugin instances loaded from entry points
        """
        plugins = []

        try:
            # Get entry points for our plugin group
            entry_points = importlib.metadata.entry_points()

            # Handle both old and new entry_points API
            plugin_entries: Any = []
            if hasattr(entry_points, "select"):
                # New API (Python 3.10+)
                plugin_entries = entry_points.select(group=self._entry_point_group)
            else:
                # Old API - handle different return types
                try:
                    # Try to get entry points, handling different API versions
                    if hasattr(entry_points, "get"):
                        result = entry_points.get(self._entry_point_group)
                        plugin_entries = list(result) if result else []
                    else:
                        plugin_entries = []
                except (TypeError, AttributeError):
                    # Fallback for incompatible entry_points types
                    plugin_entries = []

            for entry_point in plugin_entries:
                try:
                    # Load the plugin class
                    plugin_class = entry_point.load()

                    # Validate it's a LanguagePlugin
                    if not issubclass(plugin_class, LanguagePlugin):
                        log_warning(
                            f"Entry point {entry_point.name} is not a LanguagePlugin"
                        )
                        continue

                    # Create instance
                    plugin_instance = plugin_class()
                    plugins.append(plugin_instance)

                    log_debug(f"Loaded plugin from entry point: {entry_point.name}")

                except Exception as e:
                    log_error(
                        f"Failed to load plugin from entry point {entry_point.name}: {e}"
                    )

        except Exception as e:
            log_warning(f"Failed to load plugins from entry points: {e}")

        return plugins

    def _load_from_local_directory(self) -> list[LanguagePlugin]:
        """
        Load plugins from the local languages directory.

        Returns:
            List of plugin instances loaded from local directory
        """
        plugins: list[LanguagePlugin] = []

        try:
            # Get the languages directory path
            current_dir = Path(__file__).parent.parent
            languages_dir = current_dir / "languages"

            if not languages_dir.exists():
                log_debug("Languages directory does not exist, creating it")
                languages_dir.mkdir(exist_ok=True)
                # Create __init__.py
                (languages_dir / "__init__.py").touch()
                return plugins

            # Import the languages package
            languages_package = "tree_sitter_analyzer.languages"

            try:
                languages_module = importlib.import_module(languages_package)
            except ImportError as e:
                log_warning(f"Could not import languages package: {e}")
                return plugins

            # Discover plugin modules in the languages directory
            for _finder, name, ispkg in pkgutil.iter_modules(
                languages_module.__path__, languages_module.__name__ + "."
            ):
                if ispkg:
                    continue

                try:
                    # Import the module
                    module = importlib.import_module(name)

                    # Look for LanguagePlugin classes
                    plugin_classes = self._find_plugin_classes(module)

                    for plugin_class in plugin_classes:
                        try:
                            plugin_instance = plugin_class()
                            plugins.append(plugin_instance)
                            log_debug(f"Loaded local plugin: {plugin_class.__name__}")
                        except Exception as e:
                            log_error(
                                f"Failed to instantiate plugin {plugin_class.__name__}: {e}"
                            )

                except Exception as e:
                    log_error(f"Failed to load plugin module {name}: {e}")

        except Exception as e:
            log_warning(f"Failed to load plugins from local directory: {e}")

        return plugins

    def _find_plugin_classes(self, module: Any) -> list[type[LanguagePlugin]]:
        """
        Find LanguagePlugin classes in a module.

        Args:
            module: Python module to search

        Returns:
            List of LanguagePlugin classes found in the module
        """
        plugin_classes: list[type[LanguagePlugin]] = []

        for attr_name in dir(module):
            attr = getattr(module, attr_name)

            # Check if it's a class and subclass of LanguagePlugin
            if (
                isinstance(attr, type)
                and issubclass(attr, LanguagePlugin)
                and attr is not LanguagePlugin
            ):
                plugin_classes.append(attr)

        return plugin_classes

    def get_plugin(self, language: str) -> LanguagePlugin | None:
        """
        Get a plugin for a specific language.

        Args:
            language: Programming language name

        Returns:
            Plugin instance or None if not found
        """
        return self._loaded_plugins.get(language)

    def get_all_plugins(self) -> dict[str, LanguagePlugin]:
        """
        Get all loaded plugins.

        Returns:
            Dictionary mapping language names to plugin instances
        """
        return self._loaded_plugins.copy()

    def get_supported_languages(self) -> list[str]:
        """
        Get list of all supported languages.

        Returns:
            List of supported language names
        """
        return list(self._loaded_plugins.keys())

    def reload_plugins(self) -> list[LanguagePlugin]:
        """
        Reload all plugins (useful for development).

        Returns:
            List of reloaded plugin instances
        """
        log_info("Reloading all plugins")

        # Clear existing plugins
        self._loaded_plugins.clear()
        self._plugin_classes.clear()

        # Reload
        return self.load_plugins()

    def register_plugin(self, plugin: LanguagePlugin) -> bool:
        """
        Manually register a plugin instance.

        Args:
            plugin: Plugin instance to register

        Returns:
            True if registration was successful
        """
        try:
            language = plugin.get_language_name()

            if language in self._loaded_plugins:
                log_warning(
                    f"Plugin for language '{language}' already exists, replacing"
                )

            self._loaded_plugins[language] = plugin
            log_debug(f"Manually registered plugin for language: {language}")
            return True

        except Exception as e:
            log_error(f"Failed to register plugin: {e}")
            return False

    def unregister_plugin(self, language: str) -> bool:
        """
        Unregister a plugin for a specific language.

        Args:
            language: Programming language name

        Returns:
            True if unregistration was successful
        """
        if language in self._loaded_plugins:
            del self._loaded_plugins[language]
            log_debug(f"Unregistered plugin for language: {language}")
            return True

        return False

    def get_plugin_info(self, language: str) -> dict[str, Any] | None:
        """
        Get information about a specific plugin.

        Args:
            language: Programming language name

        Returns:
            Plugin information dictionary or None
        """
        plugin = self.get_plugin(language)
        if not plugin:
            return None

        try:
            return {
                "language": plugin.get_language_name(),
                "extensions": plugin.get_file_extensions(),
                "class_name": plugin.__class__.__name__,
                "module": plugin.__class__.__module__,
                "has_extractor": hasattr(plugin, "create_extractor"),
            }
        except Exception as e:
            log_error(f"Failed to get plugin info for {language}: {e}")
            return None

    def validate_plugin(self, plugin: LanguagePlugin) -> bool:
        """
        Validate that a plugin implements the required interface correctly.

        Args:
            plugin: Plugin instance to validate

        Returns:
            True if the plugin is valid
        """
        try:
            # Check required methods
            required_methods = [
                "get_language_name",
                "get_file_extensions",
                "create_extractor",
            ]

            for method_name in required_methods:
                if not hasattr(plugin, method_name):
                    log_error(f"Plugin missing required method: {method_name}")
                    return False

                method = getattr(plugin, method_name)
                if not callable(method):
                    log_error(f"Plugin method {method_name} is not callable")
                    return False

            # Test basic functionality
            language = plugin.get_language_name()
            if not language or not isinstance(language, str):
                log_error("Plugin get_language_name() must return a non-empty string")
                return False

            extensions = plugin.get_file_extensions()
            if not isinstance(extensions, list):
                log_error("Plugin get_file_extensions() must return a list")  # type: ignore[unreachable]
                return False

            extractor = plugin.create_extractor()
            if not extractor:
                log_error("Plugin create_extractor() must return an extractor instance")
                return False

            return True

        except Exception as e:
            log_error(f"Plugin validation failed: {e}")
            return False
