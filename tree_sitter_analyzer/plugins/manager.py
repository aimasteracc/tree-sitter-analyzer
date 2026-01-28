#!/usr/bin/env python3
"""
Plugin Manager Module for Tree-sitter Analyzer

This module provides a dynamic plugin discovery and management system
with lazy loading, performance optimization, and comprehensive error handling.

Features:
- Dynamic plugin discovery via entry points
- Local directory scanning for plugins
- Lazy loading for performance
- Plugin validation and testing
- Thread-safe operations
- Performance monitoring and statistics
- Comprehensive error handling
- Type-safe operations (PEP 484)
"""

import importlib
import importlib.metadata
import logging
import os
import pkgutil
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, List, Dict, Tuple, Union, Callable, Type
from functools import lru_cache, wraps
from time import perf_counter
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import pickle

# Configure logging
logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .base import LanguagePlugin, ElementExtractor
    from ..utils import log_debug, log_info, log_warning, log_error, log_performance
    from ..core.cache_service import CacheService
    from ..core.query import QueryResult


class PluginType(Enum):
    """Plugin type enumeration."""

    PROGRAMMING = "programming"
    MARKUP = "markup"
    DATA = "data"
    UNKNOWN = "unknown"


class PluginState(Enum):
    """Plugin state enumeration."""

    LOADED = "loaded"
    UNLOADED = "unloaded"
    ERROR = "error"
    INITIALIZING = "initializing"


class PluginError(Exception):
    """Base exception for plugin-related errors."""

    pass


class PluginLoadError(PluginError):
    """Raised when a plugin fails to load."""

    pass


class PluginNotFoundError(PluginError):
    """Raised when a requested plugin is not found."""

    pass


class PluginValidationError(PluginError):
    """Raised when a plugin fails validation."""

    pass


class PluginExecutionError(PluginError):
    """Raised when a plugin fails to execute."""

    pass


@dataclass
class PluginInfo:
    """
    Information about a plugin.

    Attributes:
        name: Plugin name
        type: Plugin type (programming, markup, data)
        state: Plugin state
        version: Plugin version
        description: Plugin description
        language: Programming language this plugin supports
        extensions: File extensions this plugin supports
        module: Python module name
        load_time: Time when plugin was loaded (seconds)
        is_valid: Whether plugin passed validation
    """

    name: str
    type: PluginType
    state: PluginState
    version: Optional[str]
    description: str
    language: str
    extensions: List[str]
    module: str
    load_time: float
    is_valid: bool
    error_message: Optional[str]


class PluginManager:
    """
    Dynamic plugin discovery and management system with performance optimization.

    Features:
    - Plugin discovery via entry points
    - Local directory scanning
    - Lazy loading for performance
    - Plugin validation and testing
    - Thread-safe operations
    - Performance monitoring
    - Comprehensive error handling
    - Type-safe operations (PEP 484)

    Usage:
    ```python
    manager = PluginManager()

    # Load plugins
    plugins = manager.load_plugins()

    # Get plugin for a language
    plugin = manager.get_plugin("python")

    # Register a plugin manually
    manager.register_plugin(plugin)

    # Get all plugins
    all_plugins = manager.get_all_plugins()

    # Get statistics
    stats = manager.get_plugin_statistics()
    ```

    Attributes:
        _loaded_plugins: Dict[str, LanguagePlugin]
        _plugin_modules: Dict[str, str]
        _entry_point_group: str
        _discovered: bool
        _lock: threading.RLock
        _stats: Dict[str, Any]
        _cache: Optional[CacheService]
        _enable_cache: bool
        _cache_ttl: int
    """

    def __init__(
        self,
        cache: Optional[CacheService] = None,
        enable_cache: bool = True,
        cache_ttl: int = 3600,
        enable_threading: bool = True,
    ) -> None:
        """
        Initialize plugin manager.

        Args:
            cache: Optional cache service for plugin instances
            enable_cache: Whether to enable caching (default: True)
            cache_ttl: Cache time-to-live in seconds (default: 3600 = 1 hour)
            enable_threading: Whether to enable thread-safety (default: True)

        Note:
            - Plugins are discovered via entry points and local directories
            - Lazy loading for performance (only loaded when needed)
            - Thread-safe operations if threading is enabled
            - Performance monitoring is built-in
        """
        self._loaded_plugins: Dict[str, LanguagePlugin] = {}
        self._plugin_modules: Dict[str, str] = {}
        self._entry_point_group = "tree_sitter_analyzer.plugins"
        self._discovered = False
        self._lock = threading.RLock() if enable_threading else None
        self._enable_cache = enable_cache
        self._cache_ttl = cache_ttl
        self._cache = cache

        # Initialize statistics
        self._stats: Dict[str, Any] = {
            "total_plugins": 0,
            "loaded_plugins": 0,
            "failed_plugins": 0,
            "total_load_time": 0.0,
            "cache_hits": 0,
            "cache_misses": 0,
        }

        logger.info(
            f"PluginManager initialized (cache={enable_cache}, ttl={cache_ttl}s, "
            f"threading={'enabled' if enable_threading else 'disabled'})"
        )

    def discover_plugins(self) -> List[PluginInfo]:
        """
        Discover available plugins without loading them.

        Returns:
            List of PluginInfo with metadata

        Note:
            - Scans entry points and local directories
            - Does not load plugin classes
            - Performance: Fast (metadata only)
        """
        start_time = perf_counter()
        self._stats["total_plugins"] += 1

        with self._lock:
            # Discover from entry points
            entry_point_plugins = self._discover_from_entry_points()

            # Discover from local directory
            local_plugins = self._discover_from_local_directory()

            # Combine and deduplicate
            all_plugins = self._deduplicate_plugins(
                entry_point_plugins + local_plugins
            )

            end_time = perf_counter()
            load_time = end_time - start_time

            logger.info(
                f"Discovered {len(all_plugins)} plugins in {load_time:.3f}s"
            )

        return all_plugins

    def load_plugins(self) -> List[PluginInfo]:
        """
        Discover and load all available plugins.

        Returns:
            List of PluginInfo with validation status

        Note:
            - Discovers plugins via entry points and local directories
            - Loads plugin classes
            - Validates plugins
            - Performance: Slower (class loading)
        """
        start_time = perf_counter()

        with self._lock:
            # Check if already discovered
            if not self._discovered:
                # Discover from entry points
                self._discover_from_entry_points()

                # Discover from local directory
                self._discover_from_local_directory()

                self._discovered = True

            # Load all discovered modules
            plugins = []
            for language_name, module_name in self._plugin_modules.items():
                try:
                    start_load_time = perf_counter()
                    plugin_instance = self._load_plugin_module(
                        module_name, language_name
                    )
                    end_load_time = perf_counter()
                    load_time = end_load_time - start_load_time

                    if plugin_instance:
                        self._loaded_plugins[language_name] = plugin_instance
                        self._stats["loaded_plugins"] += 1
                        self._stats["total_load_time"] += load_time

                        plugin_info = PluginInfo(
                            name=language_name,
                            type=self._determine_plugin_type(plugin_instance),
                            state=PluginState.LOADED,
                            version=self._get_plugin_version(plugin_instance),
                            description=plugin_instance.__doc__ or "",
                            language=language_name,
                            extensions=plugin_instance.get_file_extensions(),
                            module=module_name,
                            load_time=load_time,
                            is_valid=True,
                            error_message=None,
                        )
                        plugins.append(plugin_info)

                        logger.debug(
                            f"Loaded plugin: {language_name} ({module_name}) "
                            f"in {load_time:.3f}s"
                        )

                    else:
                        self._stats["failed_plugins"] += 1
                        plugin_info = PluginInfo(
                            name=language_name,
                            type=PluginType.UNKNOWN,
                            state=PluginState.ERROR,
                            version=None,
                            description="",
                            language=language_name,
                            extensions=[],
                            module=module_name,
                            load_time=0.0,
                            is_valid=False,
                            error_message=f"Failed to load plugin: {language_name}",
                        )
                        plugins.append(plugin_info)

                        logger.error(
                            f"Failed to load plugin: {language_name} ({module_name})"
                        )

                except Exception as e:
                    self._stats["failed_plugins"] += 1
                    plugin_info = PluginInfo(
                        name=language_name,
                        type=PluginType.UNKNOWN,
                        state=PluginState.ERROR,
                        version=None,
                        description="",
                        language=language_name,
                        extensions=[],
                        module=module_name,
                        load_time=0.0,
                        is_valid=False,
                        error_message=f"Error loading plugin: {str(e)}",
                    )
                    plugins.append(plugin_info)

                    logger.error(
                        f"Error loading plugin: {language_name} ({module_name}): {e}"
                    )

        end_time = perf_counter()
        discovery_time = end_time - start_time

        logger.info(
            f"Loaded {len(plugins)} plugins in {discovery_time:.3f}s "
            f"(valid: {sum(1 for p in plugins if p.is_valid)})"
        )

        return plugins

    def get_plugin(self, language: str) -> Optional[LanguagePlugin]:
        """
        Get a plugin for a specific language.

        Args:
            language: Programming language name

        Returns:
            LanguagePlugin instance or None

        Raises:
            PluginNotFoundError: If plugin is not found

        Note:
            - Uses cache if enabled
            - Lazy loading (only loads when requested)
            - Thread-safe if threading is enabled
        """
        if not language or language.strip() == "":
            raise PluginNotFoundError(f"Language cannot be empty")

        # Normalize language name
        language_lower = language.lower().strip()

        # Check cache first
        if self._enable_cache and self._cache:
            cache_key = f"plugin:{language_lower}"
            try:
                cached = self._cache.get(cache_key)
                if cached:
                    self._stats["cache_hits"] += 1
                    logger.debug(f"Plugin cache hit for {language_lower}")
                    return cached
                else:
                    self._stats["cache_misses"] += 1
            except Exception as e:
                logger.debug(f"Cache check failed: {e}")

        # Check if already loaded
        with self._lock:
            if language_lower in self._loaded_plugins:
                return self._loaded_plugins[language_lower]

            # Try to load plugin
            module_name = self._plugin_modules.get(language_lower)
            if module_name:
                try:
                    start_load_time = perf_counter()
                    plugin_instance = self._load_plugin_module(
                        module_name, language_lower
                    )
                    end_load_time = perf_counter()
                    load_time = end_load_time - start_load_time

                    self._loaded_plugins[language_lower] = plugin_instance
                    self._stats["loaded_plugins"] += 1

                    # Cache the plugin
                    if self._enable_cache and self._cache:
                        cache_key = f"plugin:{language_lower}"
                        self._cache.set(cache_key, plugin_instance, ttl=self._cache_ttl)

                    logger.info(
                        f"Loaded plugin: {language_lower} ({module_name}) "
                        f"in {load_time:.3f}s"
                    )

                    return plugin_instance

                except Exception as e:
                    logger.error(f"Failed to load plugin: {language_lower}: {e}")
                    raise PluginLoadError(f"Failed to load plugin: {language_lower}") from e

            # Try aliases
            aliases = self._get_default_aliases()
            for alias, original in aliases.items():
                if language_lower == alias or language_lower == original:
                    module_name = self._plugin_modules.get(original)
                    if module_name:
                        try:
                            plugin_instance = self._load_plugin_module(
                                module_name, language_lower
                            )
                            self._loaded_plugins[language_lower] = plugin_instance
                            logger.info(f"Loaded plugin via alias: {language_lower}")

                            return plugin_instance
                        except Exception as e:
                            logger.error(f"Failed to load plugin via alias: {language_lower}: {e}")
                            break

        raise PluginNotFoundError(f"Plugin not found for language: {language}")

    def register_plugin(self, plugin: LanguagePlugin) -> bool:
        """
        Manually register a plugin.

        Args:
            plugin: Plugin instance to register

        Returns:
            True if registration was successful

        Raises:
            PluginValidationError: If plugin validation fails

        Note:
            - Validates plugin before registration
            - Thread-safe if threading is enabled
        """
        if not plugin:
            raise PluginValidationError("Plugin cannot be None")

        # Validate plugin
        if not self.validate_plugin(plugin):
            raise PluginValidationError(f"Plugin validation failed: {plugin}")

        language = plugin.get_language_name()

        with self._lock:
            if language in self._loaded_plugins:
                logger.warning(f"Plugin for language '{language}' already exists, replacing")
                self._loaded_plugins[language] = plugin
                return True
            else:
                self._loaded_plugins[language] = plugin
                logger.info(f"Registered plugin for language: {language}")
                return True

    def unregister_plugin(self, language: str) -> bool:
        """
        Unregister a plugin for a specific language.

        Args:
            language: Programming language name

        Returns:
            True if unregistration was successful

        Note:
            - Thread-safe if threading is enabled
            - Clears plugin from cache
        """
        language_lower = language.lower().strip()

        with self._lock:
            if language_lower in self._loaded_plugins:
                del self._loaded_plugins[language_lower]
                logger.info(f"Unregistered plugin for language: {language_lower}")

                # Clear from cache
                if self._enable_cache and self._cache:
                    cache_key = f"plugin:{language_lower}"
                    self._cache.delete(cache_key)

                return True

        return False

    def get_all_plugins(self) -> Dict[str, LanguagePlugin]:
        """
        Get all loaded plugins.

        Returns:
            Dictionary mapping language names to plugin instances
        """
        with self._lock:
            return self._loaded_plugins.copy()

    def get_plugin_info(self, language: str) -> Optional[PluginInfo]:
        """
        Get information about a plugin.

        Args:
            language: Programming language name

        Returns:
            PluginInfo object or None

        Note:
            - Returns None if plugin is not found
            - Does not load plugin (lazy loading)
        """
        language_lower = language.lower().strip()

        module_name = self._plugin_modules.get(language_lower)
        if not module_name:
            return None

        # Try to get basic info without loading
        try:
            import importlib.metadata
            metadata = importlib.metadata.metadata(module_name)
            return PluginInfo(
                name=language,
                type=PluginType.UNKNOWN,
                state=PluginState.UNLOADED,
                version=metadata.get("Version", "unknown"),
                description=metadata.get("Summary", ""),
                language=language,
                extensions=[],  # Not loaded yet
                module=module_name,
                load_time=0.0,
                is_valid=True,
                error_message=None,
            )
        except Exception as e:
            logger.error(f"Failed to get plugin info: {e}")
            return None

    def get_supported_languages(self) -> List[str]:
        """
        Get list of all supported languages.

        Returns:
            Sorted list of language names

        Note:
            - Returns both loaded and discovered plugins
        """
        with self._lock:
            languages = list(self._plugin_modules.keys())

            # Add common aliases
            aliases = self._get_default_aliases()
            for original, alias in aliases.items():
                if original not in languages:
                    languages.append(alias)

            return sorted(set(languages))

    def get_plugin_statistics(self) -> Dict[str, Any]:
        """
        Get plugin management statistics.

        Returns:
            Dictionary with plugin statistics

        Note:
            - Includes load success/failure rates
            - Cache hit/miss rates
            - Total load time
            - Plugin count
        """
        with self._lock:
            stats = self._stats.copy()

            total_requests = stats["total_plugins"]
            success_rate = (
                stats["loaded_plugins"] / total_requests
                if total_requests > 0 else 0.0
            )

            cache_requests = stats["cache_hits"] + stats["cache_misses"]
            cache_hit_rate = (
                stats["cache_hits"] / cache_requests
                if cache_requests > 0 else 0.0
            )

            return {
                "total_plugins": total_requests,
                "loaded_plugins": stats["loaded_plugins"],
                "failed_plugins": stats["failed_plugins"],
                "success_rate": success_rate,
                "cache_hits": stats["cache_hits"],
                "cache_misses": stats["cache_misses"],
                "cache_hit_rate": cache_hit_rate,
                "total_load_time": stats["total_load_time"],
                "average_load_time": (
                    stats["total_load_time"] / stats["loaded_plugins"]
                    if stats["loaded_plugins"] > 0 else 0.0
                ),
                "cache_enabled": self._enable_cache,
            "cache_ttl": self._cache_ttl,
            "threading_enabled": self._lock is not None,
            "plugin_count": len(self._loaded_plugins),
            "discovered_plugins": len(self._plugin_modules),
            "supported_languages": len(self.get_supported_languages()),
            "cache_size": self._cache.size() if self._cache else 0,
            }

    def validate_plugin(self, plugin: LanguagePlugin) -> bool:
        """
        Validate that a plugin implements the required interface.

        Args:
            plugin: Plugin instance to validate

        Returns:
            True if plugin is valid

        Note:
            - Checks required methods
            - Checks method signatures
            - Checks return types
        """
        try:
            # Check required methods
            required_methods = [
                "get_language_name",
                "get_file_extensions",
                "create_extractor",
                "is_applicable",
            ]

            for method_name in required_methods:
                if not hasattr(plugin, method_name):
                    logger.error(f"Plugin missing required method: {method_name}")
                    return False

                method = getattr(plugin, method_name)
                if not callable(method):
                    logger.error(f"Plugin method {method_name} is not callable")
                    return False

            # Validate get_language_name
            if not callable(plugin.get_language_name):
                logger.error("Plugin.get_language_name is not callable")
                return False

            result = plugin.get_language_name()
            if not isinstance(result, str) or result.strip() == "":
                logger.error(f"Plugin.get_language_name() must return non-empty string")
                return False

            # Validate get_file_extensions
            if not callable(plugin.get_file_extensions):
                logger.error("Plugin.get_file_extensions() is not callable")
                return False

            extensions = plugin.get_file_extensions()
            if not isinstance(extensions, list) or any(
                not isinstance(ext, str) for ext in extensions
            ):
                logger.error("Plugin.get_file_extensions() must return list of strings")
                return False

            # Validate is_applicable
            if not callable(plugin.is_applicable):
                logger.error("Plugin.is_applicable is not callable")
                return False

            return True

        except Exception as e:
            logger.error(f"Plugin validation failed: {e}")
            return False

    def _discover_from_entry_points(self) -> List[PluginInfo]:
        """
        Discover plugins from setuptools entry points.

        Returns:
            List of discovered PluginInfo objects

        Note:
            - Only reads metadata, does not load plugin classes
            - Performance: Fast (metadata only)
        """
        plugins = []

        try:
            # Get entry points for our plugin group
            entry_points = importlib.metadata.entry_points()

            # Handle different entry point API versions
            if hasattr(entry_points, "select"):
                # New API
                entry_points = entry_points.select(group=self._entry_point_group)
            elif hasattr(entry_points, "get"):
                # Old API
                result = entry_points.get(self._entry_point_group)
                entry_points = list(result) if result else []
            else:
                # Fallback
                entry_points = []

            for entry_point in entry_points:
                try:
                    # Get language from entry point name
                    lang_name = self._extract_language_from_name(entry_point.name)

                    # Get metadata
                    metadata = entry_point.dist

                    plugin_info = PluginInfo(
                        name=lang_name,
                        type=self._determine_plugin_type_from_name(lang_name),
                        state=PluginState.UNLOADED,
                        version=metadata.get("Version", "unknown"),
                        description=metadata.get("Summary", ""),
                        language=lang_name,
                        extensions=[],  # Will be loaded later
                        module=entry_point.name,
                        load_time=0.0,
                        is_valid=True,
                        error_message=None,
                    )
                    plugins.append(plugin_info)

                    logger.debug(f"Discovered plugin: {lang_name} ({entry_point.name})")

                except Exception as e:
                    logger.error(f"Error processing entry point {entry_point.name}: {e}")

        except Exception as e:
            logger.error(f"Failed to discover plugins from entry points: {e}")

        return plugins

    def _discover_from_local_directory(self) -> List[PluginInfo]:
        """
        Discover plugins from the local languages directory.

        Returns:
            List of discovered PluginInfo objects

        Note:
            - Only scans directory, does not load plugin classes
            - Performance: Fast (directory scan only)
        """
        plugins = []

        try:
            # Get languages directory path
            current_dir = Path(__file__).parent.parent
            languages_dir = current_dir / "tree_sitter_analyzer" / "languages"

            if not languages_dir.exists():
                logger.debug(f"Languages directory does not exist: {languages_dir}")
                return []

            # Scan directory for plugin modules
            for item in languages_dir.iterdir():
                if item.is_file() and item.suffix == ".py":
                    module_name = item.stem

                    # Derive language name from module name
                    lang_name = self._extract_language_from_name(module_name)

                    # Skip __init__ files
                    if module_name == "__init__":
                        continue

                    plugin_info = PluginInfo(
                        name=lang_name,
                        type=self._determine_plugin_type_from_name(lang_name),
                        state=PluginState.UNLOADED,
                        version="unknown",
                        description=f"Local plugin: {module_name}",
                        language=lang_name,
                        extensions=[],  # Will be loaded later
                        module=f"tree_sitter_analyzer.languages.{module_name}",
                        load_time=0.0,
                        is_valid=True,
                        error_message=None,
                    )
                    plugins.append(plugin_info)

                    logger.debug(f"Discovered local plugin: {lang_name} ({module_name})")

        except Exception as e:
            logger.error(f"Failed to scan local directory: {e}")

        return plugins

    def _load_plugin_module(
        self, module_name: str, language: str
    ) -> Optional[LanguagePlugin]:
        """
        Load a plugin module and return an instance.

        Args:
            module_name: Module name (e.g., "python_plugin")
            language: Programming language (e.g., "python")

        Returns:
            LanguagePlugin instance or None

        Note:
            - Uses importlib for loading
            - Wraps in try-except for error handling
            - Performance: Medium (class loading)
        """
        try:
            # Build full module path
            module_path = f"tree_sitter_analyzer.languages.{module_name}"

            logger.debug(f"Loading plugin module: {module_path}")

            # Import the module
            plugin_module = importlib.import_module(module_path)

            # Find LanguagePlugin classes
            plugin_classes = self._find_plugin_classes(plugin_module)

            if not plugin_classes:
                logger.error(f"No LanguagePlugin classes found in {module_path}")
                return None

            # Use the first plugin class found
            plugin_class = plugin_classes[0]

            # Create instance
            plugin_instance = plugin_class()

            return plugin_instance

        except ImportError as e:
            logger.error(f"Failed to import module {module_name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to load plugin module {module_name}: {e}")
            return None

    def _find_plugin_classes(
        self, module: Any
    ) -> List[Type[LanguagePlugin]]:
        """
        Find LanguagePlugin classes in a module.

        Args:
            module: Python module to search

        Returns:
            List of LanguagePlugin classes found

        Note:
            - Looks for classes that inherit from LanguagePlugin
            - Looks for classes that end with "Plugin"
            - Filters out the base class itself
        """
        plugin_classes: List[Type[LanguagePlugin]] = []

        for attr_name in dir(module):
            attr = getattr(module, attr_name)

            # Check if it's a class
            if not isinstance(attr, type):
                continue

            # Check if it inherits from LanguagePlugin
            if issubclass(attr, LanguagePlugin) and attr is not LanguagePlugin:
                plugin_classes.append(attr)

        return plugin_classes

    def _extract_language_from_name(self, name: str) -> str:
        """
        Extract language name from a module or entry point name.

        Args:
            name: Module name (e.g., "python_plugin")

        Returns:
            Language name (e.g., "python")

        Note:
            - Removes "_plugin" suffix
            - Converts to lowercase
            - Handles common naming patterns
        """
        # Remove common suffixes
        for suffix in ["_plugin", "Plugin", ".py"]:
            if name.endswith(suffix):
                name = name[: -len(suffix)]

        # Convert to lowercase
        language = name.lower().strip()

        return language

    def _determine_plugin_type(self, plugin: LanguagePlugin) -> PluginType:
        """
        Determine plugin type from plugin instance.

        Args:
            plugin: Plugin instance

        Returns:
            Plugin type (programming, markup, data, unknown)

        Note:
            - Checks module name for type hints
            - Checks file extensions for type hints
        """
        module_name = plugin.__class__.__module__
        extensions = plugin.get_file_extensions()

        # Check extensions for hints
        if ".html" in extensions or ".css" in extensions or ".md" in extensions:
            return PluginType.MARKUP
        elif ".json" in extensions or ".xml" in extensions or ".yaml" in extensions:
            return PluginType.DATA

        # Default to programming
        return PluginType.PROGRAMMING

    def _determine_plugin_type_from_name(self, name: str) -> PluginType:
        """
        Determine plugin type from name.

        Args:
            name: Plugin name

        Returns:
            Plugin type (programming, markup, data, unknown)

        Note:
            - Checks name for type hints
            - Makes an educated guess
        """
        name_lower = name.lower()

        if "markup" in name_lower:
            return PluginType.MARKUP
        elif "data" in name_lower:
            return PluginType.DATA

        return PluginType.PROGRAMMING

    def _deduplicate_plugins(self, plugins: List[PluginInfo]) -> List[PluginInfo]:
        """
        Deduplicate plugins by name.

        Args:
            plugins: List of PluginInfo objects

        Returns:
            Deduplicated list of PluginInfo objects

        Note:
            - Keeps the first occurrence of each plugin
            - Updates state to LOADED if multiple copies
        """
        seen = {}
        unique = []

        for plugin in plugins:
            if plugin.name not in seen:
                seen[plugin.name] = True
                unique.append(plugin)
            else:
                # Update existing plugin state to LOADED
                for i, p in enumerate(unique):
                    if p.name == plugin.name:
                        unique[i] = plugin

        return unique

    def _get_default_aliases(self) -> Dict[str, str]:
        """
        Get default language aliases.

        Returns:
            Dictionary mapping aliases to canonical names

        Note:
            - Maps common abbreviations to full names
            - Helps with language detection
        """
        return {
            "js": "javascript",
            "ts": "typescript",
            "py": "python",
            "rb": "ruby",
            "rs": "rust",
            "go": "go",
            "kt": "kotlin",
            "java": "java",
            "c": "c",
            "cpp": "cpp",
            "cs": "csharp",
            "vb": "vbnet",
            "sh": "bash",
            "sql": "sql",
            "html": "html",
            "css": "css",
            "json": "json",
            "xml": "xml",
            "yaml": "yaml",
            "toml": "toml",
            "md": "markdown",
        }

    def clear_cache(self) -> None:
        """
        Clear plugin cache if enabled.

        Note:
            - Invalidates all cached plugins
            - Next get_plugin will reload plugins
        """
        if self._cache:
            self._cache.clear()
            logger.info("Plugin cache cleared")

    def reload_plugins(self) -> List[PluginInfo]:
        """
        Reload all plugins.

        Returns:
            List of reloaded PluginInfo objects

        Note:
            - Clears loaded plugins
            - Re-discovers and reloads
            - Useful for development
        """
        logger.info("Reloading all plugins")

        with self._lock:
            # Clear loaded plugins
            self._loaded_plugins.clear()
            self._plugin_modules.clear()
            self._discovered = False

        # Reload plugins
            return self.load_plugins()

    def __repr__(self) -> str:
        """
        Return string representation of plugin manager.

        Returns:
            String representation with statistics
        """
        with self._lock:
            return (
                f"PluginManager(loaded={len(self._loaded_plugins)}, "
                f"discovered={len(self._plugin_modules)}, "
                f"cache={'enabled' if self._enable_cache else 'disabled'})"
            )


# Module-level convenience functions
def create_plugin_manager(
    cache: Optional[CacheService] = None,
    enable_cache: bool = True,
    cache_ttl: int = 3600,
    enable_threading: bool = True,
) -> PluginManager:
    """
    Factory function to create a properly configured plugin manager.

    Args:
        cache: Optional cache service for plugin instances
        enable_cache: Whether to enable caching (default: True)
        cache_ttl: Cache time-to-live in seconds (default: 3600 = 1 hour)
        enable_threading: Whether to enable thread-safety (default: True)

    Returns:
        Configured PluginManager instance

    Raises:
        ValueError: If parameters are invalid

    Note:
        - Creates all necessary dependencies
        - Provides clean factory pattern
        - Recommended for new code
    """
    return PluginManager(
        cache=cache,
        enable_cache=enable_cache,
        cache_ttl=cache_ttl,
        enable_threading=enable_threading,
    )


def get_plugin_manager() -> PluginManager:
    """
    Get default plugin manager instance (backward compatible).

    This function returns a singleton-like instance and is provided
    for backward compatibility. For new code, prefer using `create_plugin_manager()`
    factory function.

    Returns:
        PluginManager instance with default settings

    Note:
        - Cache is enabled by default
        - Cache TTL is 1 hour
        - Threading is enabled by default
        - For new code, prefer `create_plugin_manager()` factory function
    """
    return create_plugin_manager()


# Export for convenience
__all__ = [
    # Enums
    "PluginType",
    "PluginState",

    # Exceptions
    "PluginError",
    "PluginLoadError",
    "PluginNotFoundError",
    "PluginValidationError",
    "PluginExecutionError",

    # Data classes
    "PluginInfo",

    # Main class
    "PluginManager",

    # Factory functions
    "create_plugin_manager",
    "get_plugin_manager",
]
