#!/usr/bin/env python3
"""
YAML Plugin Unit Tests

Tests for the YAML language plugin functionality.
"""

import pytest

from tree_sitter_analyzer.languages.yaml_plugin import (
    YAML_AVAILABLE,
    YAMLElement,
    YAMLElementExtractor,
    YAMLPlugin,
)


class TestYAMLPlugin:
    """Tests for YAMLPlugin class."""

    def test_get_language_name(self) -> None:
        """Test that plugin returns correct language name."""
        plugin = YAMLPlugin()
        assert plugin.get_language_name() == "yaml"

    def test_get_file_extensions(self) -> None:
        """Test that plugin returns correct file extensions."""
        plugin = YAMLPlugin()
        extensions = plugin.get_file_extensions()
        assert ".yaml" in extensions
        assert ".yml" in extensions

    def test_get_supported_element_types(self) -> None:
        """Test that plugin returns supported element types."""
        plugin = YAMLPlugin()
        types = plugin.get_supported_element_types()
        assert "mapping" in types
        assert "sequence" in types
        assert "scalar" in types
        assert "anchor" in types
        assert "alias" in types
        assert "comment" in types
        assert "document" in types

    def test_create_extractor(self) -> None:
        """Test that plugin creates correct extractor."""
        plugin = YAMLPlugin()
        extractor = plugin.create_extractor()
        assert isinstance(extractor, YAMLElementExtractor)

    def test_get_queries(self) -> None:
        """Test that plugin returns queries."""
        plugin = YAMLPlugin()
        queries = plugin.get_queries()
        assert isinstance(queries, dict)
        assert len(queries) > 0
        assert "document" in queries
        assert "block_mapping" in queries


class TestYAMLElement:
    """Tests for YAMLElement class."""

    def test_create_yaml_element(self) -> None:
        """Test creating a YAMLElement."""
        element = YAMLElement(
            name="test_key",
            start_line=1,
            end_line=1,
            raw_text="test_key: value",
            element_type="mapping",
            key="test_key",
            value="value",
            value_type="string",
        )
        assert element.name == "test_key"
        assert element.element_type == "mapping"
        assert element.key == "test_key"
        assert element.value == "value"
        assert element.value_type == "string"

    def test_yaml_element_defaults(self) -> None:
        """Test YAMLElement default values."""
        element = YAMLElement(
            name="test",
            start_line=1,
            end_line=1,
            raw_text="test",
        )
        assert element.language == "yaml"
        assert element.element_type == "yaml"
        assert element.nesting_level == 0
        assert element.document_index == 0
        assert element.anchor_name is None
        assert element.alias_target is None


@pytest.mark.skipif(not YAML_AVAILABLE, reason="tree-sitter-yaml not installed")
class TestYAMLElementExtractor:
    """Tests for YAMLElementExtractor class."""

    def test_extract_empty_functions(self) -> None:
        """Test that extract_functions returns empty list."""
        extractor = YAMLElementExtractor()
        # YAML doesn't have functions
        result = extractor.extract_functions(None, "")  # type: ignore
        assert result == []

    def test_extract_empty_classes(self) -> None:
        """Test that extract_classes returns empty list."""
        extractor = YAMLElementExtractor()
        # YAML doesn't have classes
        result = extractor.extract_classes(None, "")  # type: ignore
        assert result == []


@pytest.mark.skipif(not YAML_AVAILABLE, reason="tree-sitter-yaml not installed")
@pytest.mark.asyncio
class TestYAMLPluginAnalysis:
    """Integration tests for YAML plugin analysis."""

    async def test_analyze_simple_yaml(self, tmp_path) -> None:
        """Test analyzing a simple YAML file."""
        from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest

        # Create test file
        yaml_content = """
name: test
version: 1.0
enabled: true
"""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml_content)

        plugin = YAMLPlugin()
        request = AnalysisRequest(file_path=str(yaml_file))
        result = await plugin.analyze_file(str(yaml_file), request)

        assert result.success
        assert result.language == "yaml"
        assert len(result.elements) > 0

    async def test_analyze_yaml_with_anchors(self, tmp_path) -> None:
        """Test analyzing YAML with anchors and aliases."""
        from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest

        yaml_content = """
defaults: &defaults
  timeout: 30
  retries: 3

production:
  <<: *defaults
  debug: false
"""
        yaml_file = tmp_path / "anchors.yaml"
        yaml_file.write_text(yaml_content)

        plugin = YAMLPlugin()
        request = AnalysisRequest(file_path=str(yaml_file))
        result = await plugin.analyze_file(str(yaml_file), request)

        assert result.success
        # Check for anchor elements
        anchors = [
            e for e in result.elements if getattr(e, "element_type", "") == "anchor"
        ]
        assert len(anchors) >= 1

    async def test_analyze_multi_document_yaml(self, tmp_path) -> None:
        """Test analyzing multi-document YAML."""
        from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest

        yaml_content = """---
doc1: value1
---
doc2: value2
"""
        yaml_file = tmp_path / "multi.yaml"
        yaml_file.write_text(yaml_content)

        plugin = YAMLPlugin()
        request = AnalysisRequest(file_path=str(yaml_file))
        result = await plugin.analyze_file(str(yaml_file), request)

        assert result.success
        # Check for multiple documents
        documents = [
            e for e in result.elements if getattr(e, "element_type", "") == "document"
        ]
        assert len(documents) >= 2

    async def test_analyze_yaml_with_sequences(self, tmp_path) -> None:
        """Test analyzing YAML with sequences."""
        from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest

        yaml_content = """
items:
  - item1
  - item2
  - item3
"""
        yaml_file = tmp_path / "sequence.yaml"
        yaml_file.write_text(yaml_content)

        plugin = YAMLPlugin()
        request = AnalysisRequest(file_path=str(yaml_file))
        result = await plugin.analyze_file(str(yaml_file), request)

        assert result.success
        # Check for sequence elements
        sequences = [
            e for e in result.elements if getattr(e, "element_type", "") == "sequence"
        ]
        assert len(sequences) >= 1


@pytest.mark.skipif(not YAML_AVAILABLE, reason="tree-sitter-yaml not installed")
class TestYAMLEnhancedFeatures:
    """Tests for advanced YAML features merged from enhanced test file."""

    def _get_tree_for_code(self, code, plugin):
        """Helper to parse YAML code and return tree."""
        import tree_sitter

        language = plugin.get_tree_sitter_language()
        parser = tree_sitter.Parser()
        if hasattr(parser, "set_language"):
            parser.set_language(language)
        elif hasattr(parser, "language"):
            parser.language = language
        else:
            parser = tree_sitter.Parser(language)
        return parser.parse(code.encode("utf-8"))

    def test_extract_key_value_types(self) -> None:
        """Test extraction of different value types (string, number, boolean, null)."""
        plugin = YAMLPlugin()
        code = """name: John Doe
age: 30
salary: 50000.50
active: true
verified: false
middle_name: null
"""
        tree = self._get_tree_for_code(code, plugin)
        elements = plugin.extractor.extract_elements(tree, code)

        name_element = next((e for e in elements if e.key == "name"), None)
        if name_element:
            assert name_element.value_type == "string"
        age_element = next((e for e in elements if e.key == "age"), None)
        if age_element:
            assert age_element.value_type == "number"
        active_element = next((e for e in elements if e.key == "active"), None)
        if active_element:
            assert active_element.value_type == "boolean"

    def test_extract_list_sequences(self) -> None:
        """Test extraction of list/sequence elements."""
        plugin = YAMLPlugin()
        code = """fruits:
  - apple
  - banana
  - orange
colors: [red, green, blue]
"""
        tree = self._get_tree_for_code(code, plugin)
        elements = plugin.extractor.extract_elements(tree, code)

        sequence_elements = [e for e in elements if e.element_type == "sequence"]
        assert len(sequence_elements) >= 1

    def test_extract_deep_nesting_levels(self) -> None:
        """Test that nesting levels are correctly captured for deeply nested structures."""
        plugin = YAMLPlugin()
        code = """config:
  database:
    connection:
      host: localhost
      port: 5432
      credentials:
        username: admin
        password: secret
"""
        tree = self._get_tree_for_code(code, plugin)
        elements = plugin.extractor.extract_elements(tree, code)

        nested_elements = [e for e in elements if e.nesting_level > 0]
        assert len(nested_elements) >= 1
        assert len(elements) >= 5

    def test_extract_anchors_and_aliases(self) -> None:
        """Test extraction of YAML anchors and aliases."""
        plugin = YAMLPlugin()
        code = """defaults: &defaults
  timeout: 30
  retries: 3
production:
  <<: *defaults
  timeout: 60
"""
        tree = self._get_tree_for_code(code, plugin)
        elements = plugin.extractor.extract_elements(tree, code)

        anchor_elements = [e for e in elements if e.element_type == "anchor"]
        alias_elements = [e for e in elements if e.element_type == "alias"]
        assert len(anchor_elements) >= 1 or len(alias_elements) >= 1

    def test_extract_scalar_types_variety(self) -> None:
        """Test extraction of various scalar types (scientific, hex, timestamp)."""
        plugin = YAMLPlugin()
        code = """string_value: "Hello, World!"
integer_value: 42
float_value: 3.14159
boolean_true: true
null_value: null
scientific: 1.23e+10
hex: 0x1A
timestamp: 2001-12-15T02:59:43.1Z
"""
        tree = self._get_tree_for_code(code, plugin)
        elements = plugin.extractor.extract_elements(tree, code)

        scalar_types = {e.value_type for e in elements if e.value_type}
        assert "string" in scalar_types
        assert "number" in scalar_types
