#!/usr/bin/env python3
"""
Plugin Manager

Dynamic plugin discovery and management system.
Handles loading plugins from entry points and local directories.
"""

import importlib
import importlib.metadata
import logging
import os
import pkgutil
import sys
from pathlib import Path
from typing import Any

from ..utils import log_debug, log_error, log_info, log_warning
from ._manager_helpers import (
    PluginLoggers,
    build_plugin_info,
    default_aliases,
    discover_entry_points,
    discover_local_plugin_modules,
    find_loaded_plugin_case_insensitive,
    find_plugin_classes,
    lazy_load_entry_point_plugin,
    lazy_load_local_plugin,
    load_plugins_from_entry_points,
    load_plugins_from_local_directory,
    plugin_module_for_language,
    validate_plugin_instance,
)
from .base import LanguagePlugin

logger = logging.getLogger(__name__)


def _is_source_checkout() -> bool:
    """Heuristic to detect running from a source checkout (tests/dev)."""
    try:
        here = Path(__file__).resolve()
        return any((p / ".git").exists() for p in here.parents)
    except Exception:
        return False


def _should_load_entry_points() -> bool:
    """Decide whether to scan setuptools entry points for plugins."""
    if os.environ.get("TREE_SITTER_ANALYZER_SKIP_ENTRYPOINTS", "").strip() == "1":
        return False
    # Default: always scan. (Unit tests expect _load_from_entry_points to be called.)
    return True


def _is_running_under_pytest() -> bool:
    """Best-effort detection for pytest to allow test-only pre-warming."""
    return "pytest" in sys.modules


def _prewarm_local_language_modules_for_tests() -> None:
    """Import local language plugin modules during test collection.

    Hypothesis deadline-based tests measure runtime of the test body, and Windows
    cold-start imports can be slow and flaky. Pre-warming moves import cost to
    collection time and stabilizes per-example execution time.
    """

    def _safe_import(module_name: str) -> None:
        """Best-effort import helper (never raises)."""
        try:
            importlib.import_module(module_name)
        except (ImportError, ModuleNotFoundError):
            return
        except Exception as e:
            log_debug(f"Skipping plugin prewarm for {module_name}: {e}")

    try:
        languages_package = "tree_sitter_analyzer.languages"
        languages_module = importlib.import_module(languages_package)
    except (ImportError, ModuleNotFoundError):
        return
    except Exception as e:
        log_debug(f"Failed to prewarm languages package: {e}")
        return

    for _finder, name, ispkg in pkgutil.iter_modules(
        languages_module.__path__, languages_module.__name__ + "."
    ):
        if not ispkg:
            _safe_import(name)


if _is_running_under_pytest():
    _prewarm_local_language_modules_for_tests()


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
        self._plugin_modules: dict[str, str] = {}  # language -> module_name
        self._entry_point_group = "tree_sitter_analyzer.plugins"
        self._discovered = False

    def load_plugins(self) -> list[LanguagePlugin]:
        """
        Discover available plugins without fully loading them for performance.
        They will be lazily loaded in get_plugin().
        """
        if self._discovered:
            return list(self._loaded_plugins.values())

        # Discover plugins from entry points (only metadata scan)
        if _should_load_entry_points():
            self._discover_from_entry_points()

        # Discover local plugins (only metadata scan)
        self._discover_from_local_directory()

        self._discovered = True

        # Return already loaded plugins (if any, e.g. manually registered)
        return list(self._loaded_plugins.values())

    def _discover_from_entry_points(self) -> None:
        """Discover plugins from setuptools entry points without loading classes."""
        self._entry_point_map = discover_entry_points(
            self._entry_point_group,
            debug=log_debug,
            warning=log_warning,
        )

    def _discover_from_local_directory(self) -> None:
        """Discover plugins from the local languages directory without importing."""
        current_dir = Path(__file__).parent.parent
        self._plugin_modules.update(
            discover_local_plugin_modules(
                current_dir / "languages",
                "tree_sitter_analyzer.languages",
                warning=log_warning,
            )
        )

    def get_plugin(self, language: str) -> LanguagePlugin | None:
        """
        Get a plugin for a specific language, loading it if necessary.
        """
        lang_lower = language.lower()
        if not self._discovered:
            self.load_plugins()

        if lang_lower in self._loaded_plugins:
            return self._loaded_plugins[lang_lower]

        module_name = plugin_module_for_language(self._plugin_modules, lang_lower)
        loggers = PluginLoggers(debug=log_debug, warning=log_warning, error=log_error)
        plugin = lazy_load_local_plugin(
            lang_lower,
            module_name,
            self._loaded_plugins,
            self._find_plugin_classes,
            loggers,
        )
        if plugin is not None:
            return plugin

        plugin = lazy_load_entry_point_plugin(
            lang_lower,
            getattr(self, "_entry_point_map", None),
            self._loaded_plugins,
            issubclass,
            loggers,
        )
        if plugin is not None:
            return plugin

        return find_loaded_plugin_case_insensitive(lang_lower, self._loaded_plugins)

    def _load_from_entry_points(self) -> list[LanguagePlugin]:
        """
        Load plugins from setuptools entry points.

        Returns:
            List of plugin instances loaded from entry points
        """
        return load_plugins_from_entry_points(
            self._entry_point_group,
            issubclass,
            debug=log_debug,
            warning=log_warning,
            error=log_error,
        )

    def _load_from_local_directory(self) -> list[LanguagePlugin]:
        """
        Load plugins from the local languages directory.

        Returns:
            List of plugin instances loaded from local directory
        """
        current_dir = Path(__file__).parent.parent
        return load_plugins_from_local_directory(
            current_dir / "languages",
            "tree_sitter_analyzer.languages",
            self._find_plugin_classes,
            PluginLoggers(debug=log_debug, warning=log_warning, error=log_error),
        )

    def _find_plugin_classes(self, module: Any) -> list[type[LanguagePlugin]]:
        """
        Find LanguagePlugin classes in a module.

        Args:
            module: Python module to search

        Returns:
            List of LanguagePlugin classes found in the module
        """
        return find_plugin_classes(module)

    def get_all_plugins(self) -> dict[str, LanguagePlugin]:
        """
        Get all plugins, loading them if not already done.

        Returns:
            Dictionary mapping language names to plugin instances
        """
        if not self._discovered:
            self.load_plugins()

        # Load all discovered plugins to satisfy the "all" requirement
        for lang in list(self._plugin_modules.keys()):
            if lang not in self._loaded_plugins:
                self.get_plugin(lang)

        return self._loaded_plugins.copy()

    def _get_default_aliases(self) -> list[str]:
        """
        Get default language aliases.

        Returns:
            List of default aliases
        """
        return default_aliases()

    def get_supported_languages(self) -> list[str]:
        """
        Get list of all supported languages (discovered or loaded).

        Returns:
            List of supported language names
        """
        if not self._discovered:
            self.load_plugins()

        # Combine loaded and discovered languages
        langs = set(self._loaded_plugins.keys())
        langs.update(self._plugin_modules.keys())
        # Also add common aliases for better support in detection
        langs.update(self._get_default_aliases())

        return sorted(langs)

    def reload_plugins(self) -> list[LanguagePlugin]:
        """
        Reload all plugins (useful for development).

        Returns:
            List of reloaded plugin instances
        """
        log_info("Reloading all plugins")

        # Clear existing plugins
        self._loaded_plugins.clear()
        self._plugin_modules.clear()
        self._discovered = False

        # Reload and return the loaded plugins directly
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
        except Exception as e:
            log_error(f"Failed to register plugin: {e}")
            return False

        if language in self._loaded_plugins:
            log_warning(f"Plugin for language '{language}' already exists, replacing")

        self._loaded_plugins[language] = plugin
        log_debug(f"Manually registered plugin for language: {language}")
        return True

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

        return build_plugin_info(plugin, language=language, error=log_error)

    def validate_plugin(self, plugin: LanguagePlugin) -> bool:
        """
        Validate that a plugin implements the required interface correctly.

        Args:
            plugin: Plugin instance to validate

        Returns:
            True if the plugin is valid
        """
        return validate_plugin_instance(plugin, error=log_error)
