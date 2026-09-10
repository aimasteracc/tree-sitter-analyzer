#!/usr/bin/env python3
"""Legacy table formatter boost2 — full signatures, shorten, visibility, doc summary."""

import tree_sitter_analyzer.formatters  # noqa: F401
from tree_sitter_analyzer.legacy_table_formatter import LegacyTableFormatter

# ============================================================================
# _create_full_signature (lines 815-845)
# ============================================================================


class TestCreateFullSignature:
    """Tests for _create_full_signature with all parameter types."""

    def test_string_parameter(self) -> None:
        """Lines 825-827: string parameter (not dict)."""
        formatter = LegacyTableFormatter()
        method = {
            "parameters": ["int x", "String y"],
            "return_type": "void",
        }
        sig = formatter._create_full_signature(method)
        assert "int x" in sig
        assert "String y" in sig

    def test_fallback_parameter(self) -> None:
        """Lines 828-830: fallback for non-dict non-string params."""
        formatter = LegacyTableFormatter()
        method = {
            "parameters": [123],
            "return_type": "void",
        }
        sig = formatter._create_full_signature(method)
        assert "123" in sig

    def test_static_method(self) -> None:
        """Lines 836-837, 842-843: static method modifier."""
        formatter = LegacyTableFormatter()
        method = {
            "parameters": [],
            "return_type": "MyClass",
            "is_static": True,
        }
        sig = formatter._create_full_signature(method)
        assert "[static]" in sig

    def test_non_static_method(self) -> None:
        """Line 842: modifier_str empty -> no modifier."""
        formatter = LegacyTableFormatter()
        method = {
            "parameters": [],
            "return_type": "void",
            "is_static": False,
        }
        sig = formatter._create_full_signature(method)
        assert "[static]" not in sig

    def test_mixed_parameter_types(self) -> None:
        """Mix of dict, string, and other parameters."""
        formatter = LegacyTableFormatter()
        method = {
            "parameters": [
                {"type": "String", "name": "a"},
                "int b",
                42,
            ],
            "return_type": "boolean",
        }
        sig = formatter._create_full_signature(method)
        assert "a:String" in sig
        assert "int b" in sig
        assert "42" in sig


# ============================================================================
# _shorten_type (lines 847-890)
# ============================================================================


class TestShortenType:
    """Tests for _shorten_type with all branches."""

    def test_none_type(self) -> None:
        """Lines 849-850: type_name is None -> 'O'."""
        formatter = LegacyTableFormatter()
        assert formatter._shorten_type(None) == "O"

    def test_non_string_type(self) -> None:
        """Lines 853-854: non-string type_name."""
        formatter = LegacyTableFormatter()
        assert formatter._shorten_type(123) == "123"

    def test_map_generic(self) -> None:
        """Lines 871-876: Map<String,Object> -> M<S,O>."""
        formatter = LegacyTableFormatter()
        result = formatter._shorten_type("Map<String,Object>")
        assert "M<" in result

    def test_list_generic(self) -> None:
        """Lines 879-880: List<String> -> L<S>."""
        formatter = LegacyTableFormatter()
        result = formatter._shorten_type("List<String>")
        assert "L<" in result

    def test_array_known_type(self) -> None:
        """Lines 883-886: String[] -> S[]."""
        formatter = LegacyTableFormatter()
        assert formatter._shorten_type("String[]") == "S[]"

    def test_array_unknown_type(self) -> None:
        formatter = LegacyTableFormatter()
        result = formatter._shorten_type("custom[]")
        assert result == "C[]"

    def test_empty_array(self) -> None:
        """Lines 887-888: '[]' with empty base -> 'O[]'."""
        formatter = LegacyTableFormatter()
        assert formatter._shorten_type("[]") == "O[]"

    def test_all_known_mappings(self) -> None:
        formatter = LegacyTableFormatter()
        assert formatter._shorten_type("String") == "S"
        assert formatter._shorten_type("int") == "i"
        assert formatter._shorten_type("long") == "l"
        assert formatter._shorten_type("double") == "d"
        assert formatter._shorten_type("boolean") == "b"
        assert formatter._shorten_type("void") == "void"
        assert formatter._shorten_type("Object") == "O"
        assert formatter._shorten_type("Exception") == "E"
        assert formatter._shorten_type("SQLException") == "SE"
        assert formatter._shorten_type("IllegalArgumentException") == "IAE"
        assert formatter._shorten_type("RuntimeException") == "RE"

    def test_unknown_type(self) -> None:
        formatter = LegacyTableFormatter()
        assert formatter._shorten_type("CustomType") == "CustomType"


# ============================================================================
# _convert_visibility (lines 892-895)
# ============================================================================


class TestConvertVisibility:
    """Tests for _convert_visibility."""

    def test_all_values(self) -> None:
        formatter = LegacyTableFormatter()
        assert formatter._convert_visibility("public") == "+"
        assert formatter._convert_visibility("private") == "-"
        assert formatter._convert_visibility("protected") == "#"
        assert formatter._convert_visibility("package") == "~"
        assert formatter._convert_visibility("custom") == "custom"


# ============================================================================
# _extract_doc_summary (lines 897-913)
# ============================================================================


class TestExtractDocSummary:
    """Tests for _extract_doc_summary."""

    def test_empty_javadoc(self) -> None:
        """Lines 899-900: empty javadoc -> '-'."""
        formatter = LegacyTableFormatter()
        assert formatter._extract_doc_summary("") == "-"

    def test_none_javadoc(self) -> None:
        formatter = LegacyTableFormatter()
        assert formatter._extract_doc_summary(None) == "-"

    def test_single_sentence(self) -> None:
        """Lines 908-911: javadoc with a single sentence."""
        formatter = LegacyTableFormatter()
        doc = "/** Returns the value. More details here. */"
        result = formatter._extract_doc_summary(doc)
        assert result == "Returns the value"

    def test_no_period(self) -> None:
        """Lines 908-913: javadoc without period."""
        formatter = LegacyTableFormatter()
        doc = "/** Get the name */"
        result = formatter._extract_doc_summary(doc)
        assert result == "Get the name"

    def test_multiline(self) -> None:
        formatter = LegacyTableFormatter()
        doc = "/**\n * Sets the value.\n * @param x the value\n */"
        result = formatter._extract_doc_summary(doc)
        assert result == "Sets the value"

    def test_with_return_tag(self) -> None:
        formatter = LegacyTableFormatter()
        doc = "/**\n * Get the user.\n * @return User\n */"
        result = formatter._extract_doc_summary(doc)
        assert "Get the user" in result


