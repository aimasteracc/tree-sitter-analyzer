#!/usr/bin/env python3
"""
Language Registry

Manages mapping between languages, file extensions, and plugins.
Provides language detection and plugin resolution services.
"""

import logging
from pathlib import Path

from ..utils import log_debug, log_error, log_warning
from .base import LanguagePlugin

logger = logging.getLogger(__name__)


class LanguageRegistry:
    """
    Registry for managing language-to-plugin mappings.

    This class handles:
    - Mapping languages to plugins
    - Mapping file extensions to languages
    - Language detection from file paths
    - Plugin resolution for languages
    """

    def __init__(self):
        """Initialize the language registry."""
        self._plugins: dict[str, LanguagePlugin] = {}
        self._extension_map: dict[str, str] = {}  # extension -> language
        self._language_aliases: dict[str, str] = {}  # alias -> canonical_language

        # Initialize common language aliases
        self._init_language_aliases()

    def _init_language_aliases(self):
        """Initialize common language aliases."""
        self._language_aliases.update(
            {
                "js": "javascript",
                "ts": "typescript",
                "py": "python",
                "rb": "ruby",
                "cpp": "c++",
                "cxx": "c++",
                "cc": "c++",
                "c++": "cpp",  # Normalize c++ to cpp
            }
        )

    def register_plugin(self, plugin: LanguagePlugin) -> bool:
        """
        Register a language plugin.

        Args:
            plugin: Plugin instance to register

        Returns:
            True if registration was successful
        """
        try:
            language = plugin.get_language_name().lower()
            extensions = plugin.get_file_extensions()

            # Check for conflicts
            if language in self._plugins:
                existing_plugin = self._plugins[language]
                log_warning(
                    f"Language '{language}' already registered by {existing_plugin.__class__.__name__}, "
                    f"replacing with {plugin.__class__.__name__}"
                )

            # Register the plugin
            self._plugins[language] = plugin

            # Register file extensions
            for ext in extensions:
                ext = ext.lower()
                if not ext.startswith("."):
                    ext = "." + ext

                if ext in self._extension_map:
                    existing_lang = self._extension_map[ext]
                    log_debug(
                        f"Extension '{ext}' already mapped to '{existing_lang}', overriding with '{language}'"
                    )

                self._extension_map[ext] = language

            log_debug(
                f"Registered plugin for language '{language}' with extensions: {extensions}"
            )
            return True

        except Exception as e:
            log_error(f"Failed to register plugin: {e}")
            return False

    def get_plugin(self, language: str) -> LanguagePlugin | None:
        """
        Get plugin for a specific language.

        Args:
            language: Programming language name

        Returns:
            Plugin instance or None if not found
        """
        # Normalize language name
        language = self._normalize_language(language)
        return self._plugins.get(language)

    def detect_language_from_file(self, file_path: Path) -> str | None:
        """
        Detect programming language from file path.

        Args:
            file_path: Path to the file

        Returns:
            Detected language name or None
        """
        if file_path is None:
            return None

        if isinstance(file_path, str):
            file_path = Path(file_path)

        # Get file extension
        extension = file_path.suffix.lower()

        # Look up in extension map
        language = self._extension_map.get(extension)
        if language:
            return language

        # Try compound extensions (e.g., .test.js, .spec.ts)
        if len(file_path.suffixes) > 1:
            # Try the last extension
            last_ext = file_path.suffixes[-1].lower()
            language = self._extension_map.get(last_ext)
            if language:
                return language

        # Special cases based on filename patterns
        filename = file_path.name.lower()

        # Common configuration files
        config_patterns = {
            "makefile": "make",
            "dockerfile": "dockerfile",
            "vagrantfile": "ruby",
            "rakefile": "ruby",
            "gemfile": "ruby",
            "podfile": "ruby",
        }

        for pattern, lang in config_patterns.items():
            if filename == pattern or filename.startswith(pattern):
                if lang in self._plugins:
                    return lang

        log_debug(f"Could not detect language for file: {file_path}")
        return None

    def get_supported_languages(self) -> list[str]:
        """
        Get list of all supported languages.

        Returns:
            List of supported language names
        """
        return list(self._plugins.keys())

    def get_supported_extensions(self) -> list[str]:
        """
        Get list of all supported file extensions.

        Returns:
            List of supported file extensions
        """
        return list(self._extension_map.keys())

    def get_extensions_for_language(self, language: str) -> list[str]:
        """
        Get file extensions for a specific language.

        Args:
            language: Programming language name

        Returns:
            List of file extensions for the language
        """
        language = self._normalize_language(language)
        plugin = self._plugins.get(language)

        if plugin:
            return plugin.get_file_extensions()

        return []

    def get_language_for_extension(self, extension: str) -> str | None:
        """
        Get language for a specific file extension.

        Args:
            extension: File extension (with or without leading dot)

        Returns:
            Language name or None if not found
        """
        if not extension.startswith("."):
            extension = "." + extension

        return self._extension_map.get(extension.lower())

    def is_language_supported(self, language: str) -> bool:
        """
        Check if a language is supported.

        Args:
            language: Programming language name

        Returns:
            True if the language is supported
        """
        language = self._normalize_language(language)
        return language in self._plugins

    def is_extension_supported(self, extension: str) -> bool:
        """
        Check if a file extension is supported.

        Args:
            extension: File extension (with or without leading dot)

        Returns:
            True if the extension is supported
        """
        if not extension.startswith("."):
            extension = "." + extension

        return extension.lower() in self._extension_map

    def _normalize_language(self, language: str) -> str:
        """
        Normalize language name using aliases.

        Args:
            language: Language name to normalize

        Returns:
            Normalized language name
        """
        if language is None:
            return ""
        language = language.lower().strip()
        return self._language_aliases.get(language, language)

    def add_language_alias(self, alias: str, canonical_language: str) -> bool:
        """
        Add a language alias.

        Args:
            alias: Alias name
            canonical_language: Canonical language name

        Returns:
            True if alias was added successfully
        """
        try:
            alias = alias.lower().strip()
            canonical_language = canonical_language.lower().strip()

            if canonical_language not in self._plugins:
                log_warning(
                    f"Cannot add alias '{alias}' for unsupported language '{canonical_language}'"
                )
                return False

            self._language_aliases[alias] = canonical_language
            log_debug(f"Added language alias: '{alias}' -> '{canonical_language}'")
            return True

        except Exception as e:
            log_error(f"Failed to add language alias: {e}")
            return False

    def get_registry_info(self) -> dict[str, any]:
        """
        Get comprehensive information about the registry.

            "plugin_count": len(self._plugins),
        Returns:
            Dictionary containing registry information
        """
        return {
            "plugin_count": len(self._plugins),
            "supported_languages": len(self._plugins),
            "supported_extensions": len(self._extension_map),
            "language_aliases": len(self._language_aliases),
            "languages": list(self._plugins.keys()),
            "extensions": list(self._extension_map.keys()),
            "aliases": dict(self._language_aliases),
            "extension_mapping": dict(self._extension_map),
        }

    def find_plugins_for_file(self, file_path: Path) -> list[LanguagePlugin]:
        """
        Find all possible plugins for a file (useful for ambiguous cases).

        Args:
            file_path: Path to the file

        Returns:
            List of possible plugins
        """
        plugins = []

        # Primary detection
        language = self.detect_language_from_file(file_path)
        if language:
            plugin = self.get_plugin(language)
            if plugin:
                plugins.append(plugin)

        # Check if any plugins explicitly support this file
        for plugin in self._plugins.values():
            if hasattr(plugin, "is_applicable") and plugin.is_applicable(
                str(file_path)
            ):
                if plugin not in plugins:
                    plugins.append(plugin)

        return plugins

    def clear(self):
        """Clear all registered plugins and mappings."""
        self._plugins.clear()
        self._extension_map.clear()
        # Keep language aliases as they're static
        log_debug("Cleared language registry")

    def unregister_plugin(self, language: str) -> bool:
        """
        Unregister a plugin for a specific language.

        Args:
            language: Programming language name

        Returns:
            True if unregistration was successful
        """
        language = self._normalize_language(language)

        if language not in self._plugins:
            return False

        # Remove the plugin
        self._plugins.pop(language)

        # Remove associated extensions
        extensions_to_remove = []
        for ext, lang in self._extension_map.items():
            if lang == language:
                extensions_to_remove.append(ext)

        for ext in extensions_to_remove:
            del self._extension_map[ext]

        log_debug(f"Unregistered plugin for language '{language}'")
        return True
