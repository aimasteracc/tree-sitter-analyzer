"""Tests for Swift plugin functionality."""

from __future__ import annotations

import sys
from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.languages.swift_plugin import (
    SwiftElementExtractor,
    SwiftPlugin,
)

try:
    import tree_sitter
    import tree_sitter_swift

    TREE_SITTER_SWIFT_AVAILABLE = True
except ImportError:
    TREE_SITTER_SWIFT_AVAILABLE = False


SWIFT_SAMPLE = """
import Foundation
import struct Swift.String

public struct User: Codable {
    let id: Int
    var name: String

    init(id: Int, name: String) {
        self.id = id
        self.name = name
    }

    static func makeGuest() -> User {
        return User(id: 0, name: "Guest")
    }

    func greet(message: String) -> String {
        return message + name
    }
}

final class UserService {
    func load() async throws -> User {
        fatalError()
    }
}

protocol Worker {
    var isBusy: Bool { get }
    func work()
}

enum Mode {
    case fast, slow
}
"""


def _swift_parser():
    language = tree_sitter.Language(tree_sitter_swift.language())
    parser = tree_sitter.Parser()
    parser.language = language
    return parser


@pytest.fixture
def plugin() -> SwiftPlugin:
    return SwiftPlugin()


class TestSwiftPluginBasics:
    """Swift plugin interface tests."""

    def test_plugin_metadata(self, plugin: SwiftPlugin) -> None:
        assert plugin.get_language_name() == "swift"
        assert plugin.get_file_extensions() == [".swift"]
        assert plugin.supports_file("Sources/App.swift")
        assert not plugin.supports_file("Sources/App.kt")

    def test_create_extractor(self, plugin: SwiftPlugin) -> None:
        assert isinstance(plugin.create_extractor(), SwiftElementExtractor)

    def test_tree_sitter_language_missing_package(self, plugin: SwiftPlugin) -> None:
        with patch.dict(sys.modules, {"tree_sitter_swift": None}):
            assert plugin.get_tree_sitter_language() is None

    @pytest.mark.skipif(
        not TREE_SITTER_SWIFT_AVAILABLE,
        reason="tree-sitter-swift not installed",
    )
    def test_tree_sitter_language_is_cached(self, plugin: SwiftPlugin) -> None:
        first = plugin.get_tree_sitter_language()
        second = plugin.get_tree_sitter_language()
        assert first is not None
        assert first is second


@pytest.mark.skipif(
    not TREE_SITTER_SWIFT_AVAILABLE,
    reason="tree-sitter-swift not installed",
)
class TestSwiftExtraction:
    """Swift extraction tests using the real parser."""

    @pytest.fixture
    def tree(self):
        return _swift_parser().parse(SWIFT_SAMPLE.encode("utf-8"))

    def test_extract_imports(self, plugin: SwiftPlugin, tree) -> None:
        imports = plugin.create_extractor().extract_imports(tree, SWIFT_SAMPLE)
        modules = {item.module_name for item in imports}
        assert "Foundation" in modules
        assert "Swift.String" in modules

    def test_extract_types(self, plugin: SwiftPlugin, tree) -> None:
        classes = plugin.create_extractor().extract_classes(tree, SWIFT_SAMPLE)
        type_map = {item.name: item.class_type for item in classes}
        assert type_map["User"] == "struct"
        assert type_map["UserService"] == "class"
        assert type_map["Worker"] == "protocol"
        assert type_map["Mode"] == "enum"
        assert next(item for item in classes if item.name == "User").interfaces == [
            "Codable"
        ]

    def test_extract_functions(self, plugin: SwiftPlugin, tree) -> None:
        functions = plugin.create_extractor().extract_functions(tree, SWIFT_SAMPLE)
        names = {item.name for item in functions}
        assert {"init", "makeGuest", "greet", "load", "work"} <= names

        load = next(item for item in functions if item.name == "load")
        assert load.is_async is True
        assert load.return_type == "User"

        greet = next(item for item in functions if item.name == "greet")
        assert greet.parameters == ["message"]
        assert greet.return_type == "String"

    def test_extract_variables(self, plugin: SwiftPlugin, tree) -> None:
        variables = plugin.create_extractor().extract_variables(tree, SWIFT_SAMPLE)
        by_name = {item.name: item for item in variables}
        assert by_name["id"].is_constant is True
        assert by_name["id"].variable_type == "Int"
        assert by_name["name"].is_constant is False
        assert by_name["isBusy"].variable_type == "Bool"

    def test_extract_elements(self, plugin: SwiftPlugin, tree) -> None:
        elements = plugin.extract_elements(tree, SWIFT_SAMPLE)
        assert len(elements["imports"]) == 2
        assert len(elements["classes"]) >= 4
        assert len(elements["functions"]) >= 5
        assert len(elements["variables"]) >= 3

    @pytest.mark.asyncio
    async def test_analyze_file(self, plugin: SwiftPlugin, tmp_path) -> None:
        source = tmp_path / "User.swift"
        source.write_text(SWIFT_SAMPLE, encoding="utf-8")

        result = await plugin.analyze_file(str(source), Mock())

        assert result.success is True
        assert result.language == "swift"
        assert result.node_count > 0
        assert any(element.name == "User" for element in result.elements)


class TestSwiftFailurePaths:
    """Swift plugin fallback and error handling tests."""

    def test_extract_elements_with_none_tree(self, plugin: SwiftPlugin) -> None:
        assert plugin.extract_elements(None, "") == {
            "functions": [],
            "classes": [],
            "variables": [],
            "imports": [],
        }

    @pytest.mark.asyncio
    async def test_analyze_file_without_language(
        self, plugin: SwiftPlugin, tmp_path
    ) -> None:
        source = tmp_path / "Unavailable.swift"
        source.write_text("struct Unavailable {}", encoding="utf-8")

        with patch.object(plugin, "get_tree_sitter_language", return_value=None):
            result = await plugin.analyze_file(str(source), Mock())

        assert result.success is True
        assert result.language == "swift"
        assert result.elements == []

    @pytest.mark.asyncio
    async def test_analyze_file_read_error(self, plugin: SwiftPlugin) -> None:
        result = await plugin.analyze_file("/missing/File.swift", Mock())

        assert result.success is False
        assert result.language == "swift"
        assert result.error_message
