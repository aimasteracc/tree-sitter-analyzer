#!/usr/bin/env python3
"""Tests for PluginRegistry — metadata, metrics, hot-reload."""

import pytest

from tree_sitter_analyzer.plugins.registry import (
    PluginMetadata,
    PluginRegistry,
    RegistryStats,
)


@pytest.fixture
def registry() -> PluginRegistry:
    return PluginRegistry()


class TestRegistryStats:
    def test_to_dict(self) -> None:
        stats = RegistryStats(
            total_discovered=5, total_loaded=3, total_load_time_s=1.2345
        )
        d = stats.to_dict()
        assert d["total_discovered"] == 5
        assert d["total_loaded"] == 3
        assert d["total_load_time_s"] == 1.2345

    def test_default_values(self) -> None:
        stats = RegistryStats()
        assert stats.total_discovered == 0
        assert stats.total_loaded == 0


class TestPluginMetadata:
    def test_frozen(self) -> None:
        meta = PluginMetadata(
            language="python", module_name="m", extensions=(".py",), source="local"
        )
        with pytest.raises(AttributeError):
            meta.language = "java"  # type: ignore[misc]

    def test_defaults(self) -> None:
        meta = PluginMetadata(
            language="java", module_name="m", extensions=(), source="local"
        )
        assert meta.load_time_s == 0.0
        assert not meta.loaded


class TestPluginRegistry:
    def test_discover_finds_languages(self, registry: PluginRegistry) -> None:
        langs = registry.discover()
        assert len(langs) > 0
        assert "python" in langs

    def test_load_single_plugin(self, registry: PluginRegistry) -> None:
        registry.discover()
        plugin = registry.load("python")
        assert plugin is not None
        assert plugin.get_language_name() == "python"

    def test_load_unknown_returns_none(self, registry: PluginRegistry) -> None:
        registry.discover()
        assert registry.load("nonexistent_lang_xyz") is None

    def test_load_family(self, registry: PluginRegistry) -> None:
        registry.discover()
        result = registry.load_family(["python", "java"])
        assert "python" in result
        assert "java" in result

    def test_load_all(self, registry: PluginRegistry) -> None:
        registry.discover()
        all_plugins = registry.load_all()
        assert len(all_plugins) > 0

    def test_metadata_tracks_loaded(self, registry: PluginRegistry) -> None:
        registry.discover()
        registry.load("python")
        meta = registry.metadata["python"]
        assert meta.loaded
        assert ".py" in meta.extensions

    def test_stats_update_on_load(self, registry: PluginRegistry) -> None:
        registry.discover()
        registry.load("python")
        assert registry.stats.total_loaded >= 1

    def test_measure_load(self, registry: PluginRegistry) -> None:
        registry.discover()
        metrics = registry.measure_load(["python"])
        assert "python" in metrics
        assert metrics["python"]["time_s"] >= 0
        assert metrics["python"]["loaded"]

    def test_measure_load_multiple(self, registry: PluginRegistry) -> None:
        registry.discover()
        metrics = registry.measure_load(["python", "java", "go"])
        assert len(metrics) == 3
        for _lang, data in metrics.items():
            assert "time_s" in data
            assert "memory_bytes" in data

    def test_get_registry_info(self, registry: PluginRegistry) -> None:
        registry.discover()
        info = registry.get_registry_info()
        assert "stats" in info
        assert "plugins" in info
        assert "python" in info["plugins"]


class TestHotReload:
    def test_hot_reload_python(self, registry: PluginRegistry) -> None:
        registry.discover()
        registry.load("python")

        reloaded = registry.hot_reload("python")
        assert reloaded is not None
        assert reloaded.get_language_name() == "python"

    def test_hot_reload_unknown_fails(self, registry: PluginRegistry) -> None:
        registry.discover()
        assert registry.hot_reload("nonexistent_lang_xyz") is None

    def test_hot_reload_updates_metadata(self, registry: PluginRegistry) -> None:
        registry.discover()
        registry.load("python")

        registry.hot_reload("python")
        meta = registry.metadata["python"]
        assert meta.loaded


class TestRegistryWithCustomManager:
    def test_inject_custom_manager(self) -> None:
        from tree_sitter_analyzer.plugins.manager import PluginManager

        mgr = PluginManager()
        reg = PluginRegistry(manager=mgr)
        assert reg._manager is mgr
