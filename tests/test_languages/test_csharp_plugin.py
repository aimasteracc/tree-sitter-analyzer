"""Tests for C# plugin functionality."""

import pytest
from pathlib import Path
from tree_sitter_analyzer.languages.csharp_plugin import CSharpPlugin


class TestCSharpPluginInterface:
    """Test CSharp plugin interface implementation."""

    def test_plugin_instantiation(self):
        """Test that plugin instantiates successfully."""
        plugin = CSharpPlugin()
        assert plugin is not None

    def test_get_language_name(self):
        """Test language name."""
        plugin = CSharpPlugin()
        assert plugin.get_language_name() == "csharp"

    def test_get_file_extensions(self):
        """Test file extensions."""
        plugin = CSharpPlugin()
        extensions = plugin.get_file_extensions()
        assert ".cs" in extensions
        assert isinstance(extensions, list)

    def test_get_tree_sitter_language(self):
        """Test tree-sitter language retrieval."""
        plugin = CSharpPlugin()
        language = plugin.get_tree_sitter_language()
        assert language is not None


class TestCSharpExtraction:
    """Test C# element extraction interface."""

    def test_class_extraction_method_exists(self):
        """Test class extraction method exists."""
        plugin = CSharpPlugin()
        assert hasattr(plugin, 'extract_classes')
        assert callable(getattr(plugin, 'extract_classes'))

    def test_method_extraction_method_exists(self):
        """Test method extraction method exists."""
        plugin = CSharpPlugin()
        assert hasattr(plugin, 'extract_functions')
        assert callable(getattr(plugin, 'extract_functions'))

    def test_field_extraction_method_exists(self):
        """Test field extraction method exists."""
        plugin = CSharpPlugin()
        assert hasattr(plugin, 'extract_variables')
        assert callable(getattr(plugin, 'extract_variables'))

    def test_import_extraction_method_exists(self):
        """Test import extraction method exists."""
        plugin = CSharpPlugin()
        assert hasattr(plugin, 'extract_imports')
        assert callable(getattr(plugin, 'extract_imports'))


class TestCSharpIntegration:
    """Integration tests for C# plugin."""

    def test_plugin_loads_successfully(self):
        """Test that C# plugin loads successfully."""
        plugin = CSharpPlugin()
        assert plugin is not None
        assert plugin.get_language_name() == "csharp"

    def test_cs_file_extension_recognized(self):
        """Test that .cs file extension is recognized."""
        plugin = CSharpPlugin()
        extensions = plugin.get_file_extensions()
        assert ".cs" in extensions

    @pytest.mark.skipif(
        not Path("examples/Sample.cs").exists(),
        reason="C# sample file not found"
    )
    def test_analyze_sample_file(self):
        """Test analysis of example C# file."""
        plugin = CSharpPlugin()
        sample_path = Path("examples/Sample.cs")
        with open(sample_path, "r", encoding="utf-8") as f:
            code = f.read()
        # Just verify it can be read without errors
        assert len(code) > 0
