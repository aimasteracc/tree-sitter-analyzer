#!/usr/bin/env python3
"""
Plugin Registry — metadata tracking, load metrics, and hot reload.

Wraps PluginManager with a structured registry that tracks plugin metadata,
measures load performance, and supports runtime hot-reload of individual plugins.
"""

import importlib
import time
import tracemalloc
from dataclasses import dataclass
from typing import Any

from ..utils import log_error, log_info, log_warning
from .base import LanguagePlugin
from .manager import PluginManager


@dataclass(frozen=True)
class PluginMetadata:
    """Static metadata about a discovered (but possibly unloaded) plugin."""

    language: str
    module_name: str
    extensions: tuple[str, ...]
    source: str  # "local" or "entry_point"
    load_time_s: float = 0.0
    memory_bytes: int = 0
    loaded: bool = False


@dataclass
class RegistryStats:
    """Aggregate registry statistics."""

    total_discovered: int = 0
    total_loaded: int = 0
    total_load_time_s: float = 0.0
    total_memory_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_discovered": self.total_discovered,
            "total_loaded": self.total_loaded,
            "total_load_time_s": round(self.total_load_time_s, 4),
            "total_memory_bytes": self.total_memory_bytes,
        }


class PluginRegistry:
    """
    Structured plugin registry with metadata, metrics, and hot-reload.

    Usage:
        registry = PluginRegistry()
        registry.discover()
        plugin = registry.load("python")
        stats = registry.measure_load(["python", "java", "go"])
    """

    def __init__(self, manager: PluginManager | None = None) -> None:
        self._manager = manager or PluginManager()
        self._metadata: dict[str, PluginMetadata] = {}
        self._stats = RegistryStats()

    @property
    def stats(self) -> RegistryStats:
        return self._stats

    @property
    def metadata(self) -> dict[str, PluginMetadata]:
        return dict(self._metadata)

    def discover(self) -> list[str]:
        """Discover all available plugins (metadata-only scan)."""
        self._manager.load_plugins()
        supported = self._manager.get_supported_languages()
        for lang in supported:
            if lang not in self._metadata:
                self._metadata[lang] = PluginMetadata(
                    language=lang,
                    module_name=self._manager._plugin_modules.get(lang, ""),
                    extensions=(),
                    source="local",
                )
        self._stats.total_discovered = len(self._metadata)
        return supported

    def load(self, language: str) -> LanguagePlugin | None:
        """Load a single plugin by language, recording metrics."""
        plugin = self._manager.get_plugin(language)
        if plugin is None:
            return None

        meta = self._metadata.get(language)
        if meta and not meta.loaded:
            self._metadata[language] = PluginMetadata(
                language=language,
                module_name=meta.module_name,
                extensions=tuple(plugin.get_file_extensions()),
                source=meta.source,
                loaded=True,
            )
            self._stats.total_loaded = sum(
                1 for m in self._metadata.values() if m.loaded
            )

        return plugin

    def load_family(self, languages: list[str]) -> dict[str, LanguagePlugin]:
        """Load multiple plugins, returning the successfully loaded ones."""
        result: dict[str, LanguagePlugin] = {}
        for lang in languages:
            plugin = self.load(lang)
            if plugin:
                result[lang] = plugin
        return result

    def load_all(self) -> dict[str, LanguagePlugin]:
        """Load all discovered plugins."""
        return self.load_family(list(self._metadata.keys()))

    def measure_load(self, languages: list[str]) -> dict[str, dict[str, Any]]:
        """
        Measure load time and memory for specified languages.

        Returns dict mapping language -> {"time_s": float, "memory_bytes": int}.
        """
        results: dict[str, dict[str, Any]] = {}

        for lang in languages:
            tracemalloc.start()
            t0 = time.perf_counter()

            try:
                plugin = self.load(lang)
                elapsed = time.perf_counter() - t0
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()

                results[lang] = {
                    "time_s": round(elapsed, 4),
                    "memory_bytes": peak,
                    "loaded": plugin is not None,
                }

                meta = self._metadata.get(lang)
                if meta:
                    self._metadata[lang] = PluginMetadata(
                        language=lang,
                        module_name=meta.module_name,
                        extensions=meta.extensions,
                        source=meta.source,
                        load_time_s=elapsed,
                        memory_bytes=peak,
                        loaded=meta.loaded,
                    )
                    self._stats.total_load_time_s += elapsed
                    self._stats.total_memory_bytes += peak

            except Exception as exc:
                tracemalloc.stop()
                log_error(f"Failed to measure load for {lang}: {exc}")
                results[lang] = {"time_s": 0.0, "memory_bytes": 0, "loaded": False}

        return results

    def hot_reload(self, language: str) -> LanguagePlugin | None:
        """
        Hot-reload a single plugin by re-importing its module.

        Returns the reloaded plugin or None on failure.
        """
        meta = self._metadata.get(language)
        if not meta or not meta.module_name:
            log_warning(f"Cannot hot-reload {language}: not discovered")
            return None

        module_name = meta.module_name

        # Unregister existing
        self._manager.unregister_plugin(language)

        # Reimport module
        try:
            module = importlib.import_module(module_name)
            importlib.reload(module)
        except Exception as exc:
            log_error(f"Failed to reload module {module_name}: {exc}")
            return None

        # Find and register new instance
        plugin_classes = self._manager._find_plugin_classes(module)
        if not plugin_classes:
            log_error(f"No LanguagePlugin class found in {module_name}")
            return None

        instance = plugin_classes[0]()
        self._manager.register_plugin(instance)

        # Update metadata
        self._metadata[language] = PluginMetadata(
            language=language,
            module_name=module_name,
            extensions=tuple(instance.get_file_extensions()),
            source=meta.source,
            loaded=True,
        )

        log_info(f"Hot-reloaded plugin for {language}")
        return instance

    def get_registry_info(self) -> dict[str, Any]:
        """Get full registry state as a dict."""
        return {
            "stats": self._stats.to_dict(),
            "plugins": {
                lang: {
                    "loaded": m.loaded,
                    "module": m.module_name,
                    "extensions": list(m.extensions),
                    "load_time_s": m.load_time_s,
                    "memory_bytes": m.memory_bytes,
                }
                for lang, m in self._metadata.items()
            },
        }
