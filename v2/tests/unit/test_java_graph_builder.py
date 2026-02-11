"""
Unit tests for CodeGraphBuilder with Java language support.

Tests the integration of JavaParser and JavaCallExtractor with CodeGraphBuilder.
"""

import pytest

from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder

# T4.1: Create JavaParser Integration


def test_builder_accepts_java_language():
    """Test that CodeGraphBuilder accepts language='java'."""
    builder = CodeGraphBuilder(language="java")
    assert builder.language == "java"
    assert builder.parser is not None
    assert builder.call_extractor is not None


def test_builder_raises_error_for_unsupported_language():
    """Test that CodeGraphBuilder raises ValueError for unsupported language."""
    with pytest.raises(ValueError, match="Unsupported language: brainfuck"):
        CodeGraphBuilder(language="brainfuck")


def test_builder_default_language_is_python():
    """Test that CodeGraphBuilder defaults to Python."""
    builder = CodeGraphBuilder()
    assert builder.language == "python"
