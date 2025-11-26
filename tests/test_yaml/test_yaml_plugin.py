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
