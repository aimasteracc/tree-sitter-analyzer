"""Unit tests for the JSON language plugin (json_plugin.py).

json_plugin had ~17% unit coverage: it has a golden-corpus test (high-level
output match) but no unit tests exercising the extractor's element-type logic.
tree-sitter-json is a core dependency, so these run on every platform.
"""

from __future__ import annotations

import tree_sitter

from tree_sitter_analyzer.languages.json_plugin import JSONPlugin


def _parse(code: str) -> tuple[tree_sitter.Tree, JSONPlugin]:
    plugin = JSONPlugin()
    parser = tree_sitter.Parser(plugin.get_tree_sitter_language())
    return parser.parse(code.encode("utf-8")), plugin


class TestJSONExtraction:
    def test_extract_elements_returns_json_elements_bucket(self) -> None:
        code = '{"name": "demo"}'
        tree, plugin = _parse(code)
        els = plugin.create_extractor().extract_elements(tree, code)
        assert "json_elements" in els
        assert len(els["json_elements"]) > 0

    def test_extracts_pairs_with_key_names(self) -> None:
        code = '{"name": "demo", "count": 42}'
        tree, plugin = _parse(code)
        elements = plugin.create_extractor().extract_json_elements(tree, code)
        pair_names = {e.name for e in elements if e.element_type == "pair"}
        assert {"name", "count"} <= pair_names

    def test_extracts_value_types(self) -> None:
        code = '{"s": "x", "n": 1, "b": true, "z": null}'
        tree, plugin = _parse(code)
        elements = plugin.create_extractor().extract_json_elements(tree, code)
        types = {e.element_type for e in elements}
        # object + pair + the scalar value node types
        assert "object" in types
        assert "pair" in types
        assert "string" in types
        assert "number" in types

    def test_nested_object_is_extracted(self) -> None:
        code = '{"outer": {"inner": 1}}'
        tree, plugin = _parse(code)
        elements = plugin.create_extractor().extract_json_elements(tree, code)
        object_count = sum(1 for e in elements if e.element_type == "object")
        assert object_count >= 2  # outer + inner
        pair_names = {e.name for e in elements if e.element_type == "pair"}
        assert {"outer", "inner"} <= pair_names

    def test_array_is_extracted(self) -> None:
        code = '{"items": [1, 2, 3]}'
        tree, plugin = _parse(code)
        elements = plugin.create_extractor().extract_json_elements(tree, code)
        types = {e.element_type for e in elements}
        assert "array" in types

    def test_empty_object_does_not_crash(self) -> None:
        code = "{}"
        tree, plugin = _parse(code)
        elements = plugin.create_extractor().extract_json_elements(tree, code)
        # one object element, no pairs
        assert all(e.element_type != "pair" for e in elements)

    def test_extract_with_none_tree_returns_empty(self) -> None:
        plugin = JSONPlugin()
        elements = plugin.create_extractor().extract_json_elements(None, "")
        assert elements == []


class TestJSONPluginMetadata:
    def test_language_name(self) -> None:
        assert JSONPlugin().get_language_name() == "json"

    def test_file_extensions(self) -> None:
        assert ".json" in JSONPlugin().get_file_extensions()

    def test_is_applicable(self) -> None:
        plugin = JSONPlugin()
        assert plugin.is_applicable("config.json") is True
        assert plugin.is_applicable("script.py") is False

    def test_create_extractor_is_fresh_instance(self) -> None:
        plugin = JSONPlugin()
        assert plugin.create_extractor() is not None
