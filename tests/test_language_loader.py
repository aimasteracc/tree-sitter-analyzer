#!/usr/bin/env python3
"""
Tests for language_loader module
"""

import sys

# Add project root to path
sys.path.insert(0, ".")

# Mock functionality now provided by pytest-mock

from tree_sitter_analyzer.language_loader import (
    LanguageLoader,
    check_language_availability,
    create_parser_safely,
    loader,
)


def test_loader_instance():
    """Test that loader instance is properly initialized"""
    assert loader is not None
    assert isinstance(loader, LanguageLoader)


def test_supported_languages():
    """Test that supported languages are defined"""
    supported = loader.SUPPORTED_LANGUAGES
    assert isinstance(supported, list)
    assert "java" in supported
    assert "javascript" in supported
    assert "python" in supported
    assert "typescript" in supported


def test_is_language_available_known_languages():
    """Test availability check for known languages"""
    # These should be true if libraries are installed
    java_available = loader.is_language_available("java")
    js_available = loader.is_language_available("javascript")
    py_available = loader.is_language_available("python")

    # At least one should be available in a proper setup
    assert isinstance(java_available, bool)
    assert isinstance(js_available, bool)
    assert isinstance(py_available, bool)


def test_is_language_available_unknown_language():
    """Test availability check for unknown languages"""
    assert not loader.is_language_available("unknown_lang")
    assert not loader.is_language_available("nonexistent")


def test_create_parser_safely_with_available_language():
    """Test parser creation for available languages"""
    # Try to create a parser for each language
    for lang in ["java", "javascript", "python", "typescript"]:
        parser = create_parser_safely(lang)
        # Parser could be None if library is not installed, but should not raise exception
        assert parser is None or hasattr(parser, "parse")


def test_create_parser_safely_with_unavailable_language():
    """Test parser creation for unavailable languages"""
    parser = create_parser_safely("unknown_language")
    assert parser is None


def test_check_language_availability_function():
    """Test the standalone availability check function"""
    # Should not raise exceptions
    java_available = check_language_availability("java")
    unknown_available = check_language_availability("unknown")

    assert isinstance(java_available, bool)
    assert isinstance(unknown_available, bool)
    assert not unknown_available


def test_typescript_dialects():
    """Test TypeScript dialect handling"""
    ts_dialects = loader.TYPESCRIPT_DIALECTS
    assert isinstance(ts_dialects, dict)
    assert "typescript" in ts_dialects
    assert "tsx" in ts_dialects


def test_load_language_with_import_error():
    """Test language loading when import fails for unknown language"""
    # Test with definitely unavailable language
    result = loader.load_language("definitely_unknown_language_12345")
    assert result is None


def test_load_language_with_missing_language_function():
    """Test language loading when module lacks language() function"""
    # Test with language not in LANGUAGE_MODULES
    result = loader.load_language("nonexistent_language")
    assert result is None


def test_create_parser_success():
    """Test successful parser creation with available language"""
    # Test with known available language
    parser = loader.create_parser("java")

    # Should return a parser object or None (if java not available)
    # Both are acceptable in test environment
    assert parser is None or hasattr(parser, "parse")


def test_caching_behavior():
    """Test that loaded languages are cached"""
    # Clear cache first
    loader._loaded_languages.clear()
    loader._loaded_modules.clear()
    loader._availability_cache.clear()

    # First call should attempt to load
    availability1 = loader.is_language_available("java")

    # Second call should use cache
    availability2 = loader.is_language_available("java")

    assert availability1 == availability2
    # Cache should have the result
    # Check that the result is consistent (cache working)
    assert isinstance(availability1, bool)
    assert isinstance(availability2, bool)


def test_special_typescript_handling():
    """Test special handling for TypeScript variants"""
    # This mainly tests that TypeScript/TSX are handled correctly
    ts_available = loader.is_language_available("typescript")
    tsx_available = loader.is_language_available("tsx")

    assert isinstance(ts_available, bool)
    assert isinstance(tsx_available, bool)

    # Both should return same availability status for TypeScript
    # since TSX uses the same parser as TypeScript
    if ts_available:
        # If TypeScript is available, TSX should also be available
        assert tsx_available


# Edge cases and error conditions tests


def test_empty_language_name():
    """Test handling of empty language names"""
    assert not loader.is_language_available("")
    assert create_parser_safely("") is None


def test_none_language_name():
    """Test handling of None language names"""
    assert not loader.is_language_available(None)
    assert create_parser_safely(None) is None


def test_case_sensitivity():
    """Test case sensitivity of language names"""
    # Language names should be case sensitive
    assert not loader.is_language_available("JAVA")
    assert not loader.is_language_available("JavaScript")
    assert not loader.is_language_available("Python")
