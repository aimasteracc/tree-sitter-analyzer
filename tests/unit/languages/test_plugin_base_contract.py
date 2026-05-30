"""Parametrized contract tests for all 21 LanguagePlugin implementations.

Covers every non-abstract method of LanguagePlugin (10 contracts × 21 plugins = 210 cases).
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.languages.bash_plugin import BashPlugin
from tree_sitter_analyzer.languages.c_plugin import CPlugin
from tree_sitter_analyzer.languages.cpp_plugin import CppPlugin
from tree_sitter_analyzer.languages.csharp_plugin import CSharpPlugin
from tree_sitter_analyzer.languages.css_plugin import CssPlugin
from tree_sitter_analyzer.languages.go_plugin import GoPlugin
from tree_sitter_analyzer.languages.html_plugin import HtmlPlugin
from tree_sitter_analyzer.languages.java_plugin import JavaPlugin
from tree_sitter_analyzer.languages.javascript_plugin import JavaScriptPlugin
from tree_sitter_analyzer.languages.json_plugin import JSONPlugin
from tree_sitter_analyzer.languages.kotlin_plugin import KotlinPlugin
from tree_sitter_analyzer.languages.markdown_plugin import MarkdownPlugin
from tree_sitter_analyzer.languages.php_plugin import PHPPlugin
from tree_sitter_analyzer.languages.python_plugin import PythonPlugin
from tree_sitter_analyzer.languages.ruby_plugin import RubyPlugin
from tree_sitter_analyzer.languages.rust_plugin import RustPlugin
from tree_sitter_analyzer.languages.scala_plugin import ScalaPlugin
from tree_sitter_analyzer.languages.sql_plugin import SQLPlugin
from tree_sitter_analyzer.languages.swift_plugin import SwiftPlugin
from tree_sitter_analyzer.languages.typescript_plugin import TypeScriptPlugin
from tree_sitter_analyzer.languages.yaml_plugin import YAMLPlugin
from tree_sitter_analyzer.plugins.base import ElementExtractor, LanguagePlugin

ALL_PLUGINS: list[LanguagePlugin] = [
    BashPlugin(),
    CPlugin(),
    CppPlugin(),
    CSharpPlugin(),
    CssPlugin(),
    GoPlugin(),
    HtmlPlugin(),
    JavaPlugin(),
    JavaScriptPlugin(),
    JSONPlugin(),
    KotlinPlugin(),
    MarkdownPlugin(),
    PHPPlugin(),
    PythonPlugin(),
    RubyPlugin(),
    RustPlugin(),
    ScalaPlugin(),
    SQLPlugin(),
    SwiftPlugin(),
    TypeScriptPlugin(),
    YAMLPlugin(),
]

_PLUGIN_IDS = [type(p).__name__ for p in ALL_PLUGINS]


@pytest.mark.parametrize("plugin", ALL_PLUGINS, ids=_PLUGIN_IDS)
class TestBasePluginContract:
    """Every LanguagePlugin must satisfy these 10 invariants."""

    def test_get_language_name_returns_nonempty_string(
        self, plugin: LanguagePlugin
    ) -> None:
        name = plugin.get_language_name()
        assert isinstance(name, str)
        assert name.strip(), (
            f"{type(plugin).__name__}.get_language_name() must not be blank"
        )

    def test_get_file_extensions_returns_nonempty_list(
        self, plugin: LanguagePlugin
    ) -> None:
        exts = plugin.get_file_extensions()
        assert isinstance(exts, list)
        assert exts, f"{type(plugin).__name__}.get_file_extensions() must not be empty"
        for ext in exts:
            assert isinstance(ext, str)
            assert ext.startswith("."), f"Extension {ext!r} must start with '.'"

    def test_create_extractor_returns_element_extractor(
        self, plugin: LanguagePlugin
    ) -> None:
        extractor = plugin.create_extractor()
        assert isinstance(extractor, ElementExtractor)

    def test_get_supported_element_types_returns_list_of_strings(
        self, plugin: LanguagePlugin
    ) -> None:
        types = plugin.get_supported_element_types()
        assert isinstance(types, list)
        for t in types:
            assert isinstance(t, str)

    def test_get_queries_returns_string_dict(self, plugin: LanguagePlugin) -> None:
        queries = plugin.get_queries()
        assert isinstance(queries, dict)
        for k, v in queries.items():
            assert isinstance(k, str), f"Query key {k!r} must be str"
            assert isinstance(v, str), f"Query value for {k!r} must be str"

    def test_get_formatter_map_returns_string_dict(
        self, plugin: LanguagePlugin
    ) -> None:
        fm = plugin.get_formatter_map()
        assert isinstance(fm, dict)
        for k, v in fm.items():
            assert isinstance(k, str)
            assert isinstance(v, str)

    def test_get_element_categories_returns_dict_of_lists(
        self, plugin: LanguagePlugin
    ) -> None:
        cats = plugin.get_element_categories()
        assert isinstance(cats, dict)
        for k, v in cats.items():
            assert isinstance(k, str)
            assert isinstance(v, list)

    def test_is_applicable_true_for_own_extensions(
        self, plugin: LanguagePlugin
    ) -> None:
        for ext in plugin.get_file_extensions():
            assert plugin.is_applicable(f"example{ext}"), (
                f"{type(plugin).__name__}.is_applicable('example{ext}') must be True"
            )

    def test_is_applicable_false_for_unknown_extension(
        self, plugin: LanguagePlugin
    ) -> None:
        assert not plugin.is_applicable("example.XYZZY_UNKNOWN_EXT")

    def test_get_plugin_info_has_required_keys(self, plugin: LanguagePlugin) -> None:
        info = plugin.get_plugin_info()
        assert isinstance(info, dict)
        required = {"language", "extensions", "class_name", "module"}
        missing = required - info.keys()
        assert not missing, (
            f"{type(plugin).__name__}.get_plugin_info() missing keys: {missing}"
        )
        assert info["language"] == plugin.get_language_name()
        assert info["extensions"] == plugin.get_file_extensions()
        assert info["class_name"] == type(plugin).__name__
