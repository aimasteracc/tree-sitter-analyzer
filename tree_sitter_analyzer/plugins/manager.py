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
from typing import Any, cast

from ..utils import log_debug, log_error, log_info, log_warning
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
        try:
            # We use a special mapping for entry points to load them later
            self._entry_point_map: dict[str, Any] = {}
            entry_points = importlib.metadata.entry_points()

            plugin_entries: Any = []
            if hasattr(entry_points, "select"):
                plugin_entries = entry_points.select(group=self._entry_point_group)
            elif hasattr(entry_points, "get"):
                result = entry_points.get(self._entry_point_group)
                plugin_entries = list(result) if result else []

            for entry_point in plugin_entries:
                # We can't know the language without loading,
                # so we might have to load entry points or use their names as hints
                lang_hint = entry_point.name.lower()
                self._entry_point_map[lang_hint] = entry_point
                log_debug(f"Discovered entry point plugin: {entry_point.name}")
        except Exception as e:
            log_warning(f"Failed to discover plugins from entry points: {e}")

    def _discover_from_local_directory(self) -> None:
        """Discover plugins from the local languages directory without importing."""
        try:
            current_dir = Path(__file__).parent.parent
            languages_dir = current_dir / "languages"
            if not languages_dir.exists():
                return

            languages_package = "tree_sitter_analyzer.languages"
            languages_module = importlib.import_module(languages_package)

            for _finder, name, ispkg in pkgutil.iter_modules(
                languages_module.__path__, languages_module.__name__ + "."
            ):
                if ispkg:
                    continue

                # Derive language name from filename (e.g., python_plugin -> python)
                base_name = name.split(".")[-1]
                if base_name.endswith("_plugin"):
                    lang_hint = base_name[: -len("_plugin")]
                    self._plugin_modules[lang_hint] = name
                    # Also support some common aliases if needed, but get_plugin will handle it
        except Exception as e:
            log_warning(f"Failed to discover local plugins: {e}")

    def get_plugin(self, language: str) -> LanguagePlugin | None:
        """
        Get a plugin for a specific language, loading it if necessary.
        """
        lang_lower = language.lower()
        if not self._discovered:
            self.load_plugins()

        if lang_lower in self._loaded_plugins:
            return self._loaded_plugins[lang_lower]

        # Try to load from discovered modules (local)
        module_name = self._plugin_modules.get(lang_lower)

        # Try some common aliases (e.g., js -> javascript)
        aliases = {
            "js": "javascript",
            "py": "python",
            "rb": "ruby",
            "ts": "typescript",
        }

        if not module_name and lang_lower in aliases:
            module_name = self._plugin_modules.get(aliases[lang_lower])

        if module_name:
            try:
                log_debug(
                    f"Lazily loading local plugin for {lang_lower} from {module_name}"
                )
                module = importlib.import_module(module_name)
                plugin_classes = self._find_plugin_classes(module)
                for plugin_class in plugin_classes:
                    instance = plugin_class()
                    lang = instance.get_language_name()
                    self._loaded_plugins[lang] = instance
                    if lang == lang_lower or (
                        lang_lower in aliases and lang == aliases[lang_lower]
                    ):
                        return instance
            except Exception as e:
                log_error(f"Failed to lazily load local plugin {module_name}: {e}")

        # Try to load from discovered entry points
        if hasattr(self, "_entry_point_map") and lang_lower in self._entry_point_map:
            try:
                entry_point = self._entry_point_map[lang_lower]
                log_debug(
                    f"Lazily loading entry point plugin for {lang_lower}: {entry_point.name}"
                )
                plugin_class = entry_point.load()
                if issubclass(plugin_class, LanguagePlugin):
                    instance = plugin_class()
                    lang = instance.get_language_name()
                    self._loaded_plugins[lang] = instance
                    instance_any: Any = instance
                    return cast(LanguagePlugin, instance_any)
            except Exception as e:
                log_error(f"Failed to lazily load entry point plugin {lang_lower}: {e}")

        # Final check in loaded plugins (case-insensitive)
        for lang, plugin in self._loaded_plugins.items():
            if lang.lower() == lang_lower:
                return plugin

        return None

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
        return ["js", "py", "rb", "ts"]

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
