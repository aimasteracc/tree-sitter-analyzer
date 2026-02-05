"""
Test Formatter Registry implementation.

Following TDD: Write tests FIRST to define the contract.
This is T3.3: Formatter Registry

The registry provides:
- Registration of formatters (TOON, Markdown)
- Retrieval by format name
- List of available formats
- Error handling for unknown formats
"""

import pytest


class TestFormatterRegistryBasics:
    """Test basic formatter registry functionality."""

    def test_registry_can_be_imported(self):
        """Test that FormatterRegistry can be imported."""
        from tree_sitter_analyzer_v2.formatters.registry import FormatterRegistry

        assert FormatterRegistry is not None

    def test_registry_initialization(self):
        """Test creating a registry instance."""
        from tree_sitter_analyzer_v2.formatters.registry import FormatterRegistry

        registry = FormatterRegistry()
        assert registry is not None


class TestFormatterRegistration:
    """Test formatter registration."""

    def test_register_toon_formatter(self):
        """Test registering TOON formatter."""
        from tree_sitter_analyzer_v2.formatters.registry import FormatterRegistry

        registry = FormatterRegistry()

        # Should have TOON formatter registered by default
        assert "toon" in registry.list_formats()

    def test_register_markdown_formatter(self):
        """Test registering Markdown formatter."""
        from tree_sitter_analyzer_v2.formatters.registry import FormatterRegistry

        registry = FormatterRegistry()

        # Should have Markdown formatter registered by default
        assert "markdown" in registry.list_formats()

    def test_list_all_formats(self):
        """Test listing all available formats."""
        from tree_sitter_analyzer_v2.formatters.registry import FormatterRegistry

        registry = FormatterRegistry()
        formats = registry.list_formats()

        # Should have toon, markdown, and summary formatters
        assert "toon" in formats
        assert "markdown" in formats
        assert "summary" in formats
        assert len(formats) == 3


class TestFormatterRetrieval:
    """Test formatter retrieval."""

    def test_get_toon_formatter(self):
        """Test retrieving TOON formatter."""
        from tree_sitter_analyzer_v2.formatters.registry import FormatterRegistry
        from tree_sitter_analyzer_v2.formatters.toon_formatter import ToonFormatter

        registry = FormatterRegistry()
        formatter = registry.get("toon")

        assert isinstance(formatter, ToonFormatter)

    def test_get_markdown_formatter(self):
        """Test retrieving Markdown formatter."""
        from tree_sitter_analyzer_v2.formatters.markdown_formatter import MarkdownFormatter
        from tree_sitter_analyzer_v2.formatters.registry import FormatterRegistry

        registry = FormatterRegistry()
        formatter = registry.get("markdown")

        assert isinstance(formatter, MarkdownFormatter)

    def test_get_formatter_case_insensitive(self):
        """Test that formatter retrieval is case-insensitive."""
        from tree_sitter_analyzer_v2.formatters.registry import FormatterRegistry

        registry = FormatterRegistry()

        # Should work with different cases
        formatter1 = registry.get("TOON")
        formatter2 = registry.get("Toon")
        formatter3 = registry.get("toon")

        assert formatter1 is not None
        assert formatter2 is not None
        assert formatter3 is not None


class TestFormatterRegistryErrors:
    """Test formatter registry error handling."""

    def test_get_unknown_formatter_raises_error(self):
        """Test that getting unknown formatter raises error."""
        from tree_sitter_analyzer_v2.formatters.registry import FormatterRegistry

        registry = FormatterRegistry()

        with pytest.raises(ValueError, match="Unknown format"):
            registry.get("unknown")

    def test_get_empty_format_raises_error(self):
        """Test that empty format name raises error."""
        from tree_sitter_analyzer_v2.formatters.registry import FormatterRegistry

        registry = FormatterRegistry()

        with pytest.raises(ValueError):
            registry.get("")


class TestFormatterUsage:
    """Test using formatters from registry."""

    def test_format_with_toon_from_registry(self):
        """Test formatting data with TOON formatter from registry."""
        from tree_sitter_analyzer_v2.formatters.registry import FormatterRegistry

        registry = FormatterRegistry()
        formatter = registry.get("toon")

        data = {"name": "example", "count": 42}
        result = formatter.format(data)

        assert "name" in result or "Name" in result
        assert "example" in result
        assert "42" in result

    def test_format_with_markdown_from_registry(self):
        """Test formatting data with Markdown formatter from registry."""
        from tree_sitter_analyzer_v2.formatters.registry import FormatterRegistry

        registry = FormatterRegistry()
        formatter = registry.get("markdown")

        data = {"name": "example", "count": 42}
        result = formatter.format(data)

        assert "Name" in result or "name" in result
        assert "example" in result
        assert "42" in result
        assert "**" in result  # Markdown bold syntax


class TestDefaultRegistry:
    """Test default registry singleton."""

    def test_default_registry_accessible(self):
        """Test that default registry is accessible."""
        from tree_sitter_analyzer_v2.formatters.registry import get_default_registry

        registry = get_default_registry()
        assert registry is not None

    def test_default_registry_has_formatters(self):
        """Test that default registry has formatters registered."""
        from tree_sitter_analyzer_v2.formatters.registry import get_default_registry

        registry = get_default_registry()
        formats = registry.list_formats()

        assert "toon" in formats
        assert "markdown" in formats

    def test_default_registry_is_singleton(self):
        """Test that default registry returns same instance."""
        from tree_sitter_analyzer_v2.formatters.registry import get_default_registry

        registry1 = get_default_registry()
        registry2 = get_default_registry()

        assert registry1 is registry2
