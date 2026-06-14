"""Tests for Kotlin property/field extraction correctness (issue #758).

Verifies that property_declaration nodes yield:
  - the real property name (not "unknown")
  - the declared type annotation (not "Inferred") when present
  - "Inferred" only when no type annotation exists (e.g. `val version = "1.0"`)
  - correct is_static / is_readonly flags for `const val`
"""

import pytest

pytest.importorskip("tree_sitter_kotlin")

import tree_sitter  # noqa: E402
import tree_sitter_kotlin  # noqa: E402

from tree_sitter_analyzer.languages.kotlin_plugin import (
    KotlinElementExtractor,  # noqa: E402
)


@pytest.fixture(scope="module")
def kotlin_parser():
    """Build a tree-sitter Kotlin parser (module-scoped for speed)."""
    lang = tree_sitter_kotlin.language()
    if not (hasattr(lang, "__class__") and "Language" in str(type(lang))):
        lang = tree_sitter.Language(lang)
    parser = tree_sitter.Parser()
    if hasattr(parser, "set_language"):
        parser.set_language(lang)
    elif hasattr(parser, "language"):
        parser.language = lang
    else:
        parser = tree_sitter.Parser(lang)
    return parser


@pytest.fixture
def extractor():
    return KotlinElementExtractor()


class TestKotlinPropertyNameExtraction:
    """Issue #758: property names must not be 'unknown'."""

    def test_val_with_type_annotation_name(self, extractor, kotlin_parser):
        """val name: String — name must be 'name', not 'unknown'."""
        code = 'val name: String = "Alice"\n'
        tree = kotlin_parser.parse(code.encode("utf-8"))
        variables = extractor.extract_variables(tree, code)

        assert len(variables) == 1
        assert variables[0].name == "name"

    def test_var_with_type_annotation_name(self, extractor, kotlin_parser):
        """var total: Int — name must be 'total'."""
        code = "var total: Int = 0\n"
        tree = kotlin_parser.parse(code.encode("utf-8"))
        variables = extractor.extract_variables(tree, code)

        assert len(variables) == 1
        assert variables[0].name == "total"

    def test_const_val_name(self, extractor, kotlin_parser):
        """const val MAX_USERS: Int — name must be 'MAX_USERS'."""
        code = "const val MAX_USERS: Int = 100\n"
        tree = kotlin_parser.parse(code.encode("utf-8"))
        variables = extractor.extract_variables(tree, code)

        assert len(variables) == 1
        assert variables[0].name == "MAX_USERS"

    def test_val_without_type_annotation_name(self, extractor, kotlin_parser):
        """val version = "1.0" — name must be 'version', not 'unknown'."""
        code = 'val version = "1.0"\n'
        tree = kotlin_parser.parse(code.encode("utf-8"))
        variables = extractor.extract_variables(tree, code)

        assert len(variables) == 1
        assert variables[0].name == "version"

    def test_class_property_names(self, extractor, kotlin_parser):
        """Properties inside a class body must carry real names."""
        code = """\
class Config {
    val host: String = "localhost"
    var port: Int = 8080
    val debug = false
}
"""
        tree = kotlin_parser.parse(code.encode("utf-8"))
        variables = extractor.extract_variables(tree, code)

        assert len(variables) == 3
        names = [v.name for v in variables]
        assert names == ["host", "port", "debug"]


class TestKotlinPropertyTypeExtraction:
    """Issue #758: declared types must be extracted, not hardcoded 'Inferred'."""

    def test_val_with_string_type(self, extractor, kotlin_parser):
        """val name: String — type must be 'String'."""
        code = 'val name: String = "Alice"\n'
        tree = kotlin_parser.parse(code.encode("utf-8"))
        variables = extractor.extract_variables(tree, code)

        assert len(variables) == 1
        assert variables[0].variable_type == "String"

    def test_var_with_int_type(self, extractor, kotlin_parser):
        """var total: Int — type must be 'Int'."""
        code = "var total: Int = 0\n"
        tree = kotlin_parser.parse(code.encode("utf-8"))
        variables = extractor.extract_variables(tree, code)

        assert len(variables) == 1
        assert variables[0].variable_type == "Int"

    def test_const_val_with_type(self, extractor, kotlin_parser):
        """const val MAX_USERS: Int — type must be 'Int'."""
        code = "const val MAX_USERS: Int = 100\n"
        tree = kotlin_parser.parse(code.encode("utf-8"))
        variables = extractor.extract_variables(tree, code)

        assert len(variables) == 1
        assert variables[0].variable_type == "Int"

    def test_val_without_type_stays_inferred(self, extractor, kotlin_parser):
        """val version = "1.0" — no annotation, so type must be 'Inferred'."""
        code = 'val version = "1.0"\n'
        tree = kotlin_parser.parse(code.encode("utf-8"))
        variables = extractor.extract_variables(tree, code)

        assert len(variables) == 1
        assert variables[0].variable_type == "Inferred"


class TestKotlinConstValFlags:
    """Issue #758: const val must set is_static=True and is_readonly=True."""

    def test_const_val_is_static_and_readonly(self, extractor, kotlin_parser):
        """const val MAX_USERS: Int = 100 — must be static and readonly."""
        code = "const val MAX_USERS: Int = 100\n"
        tree = kotlin_parser.parse(code.encode("utf-8"))
        variables = extractor.extract_variables(tree, code)

        assert len(variables) == 1
        v = variables[0]
        assert v.is_static is True
        assert v.is_readonly is True

    def test_plain_val_is_not_static(self, extractor, kotlin_parser):
        """Plain val must NOT be marked static."""
        code = 'val name: String = "Alice"\n'
        tree = kotlin_parser.parse(code.encode("utf-8"))
        variables = extractor.extract_variables(tree, code)

        assert len(variables) == 1
        assert variables[0].is_static is False

    def test_var_is_not_readonly(self, extractor, kotlin_parser):
        """var must NOT be marked readonly."""
        code = "var total: Int = 0\n"
        tree = kotlin_parser.parse(code.encode("utf-8"))
        variables = extractor.extract_variables(tree, code)

        assert len(variables) == 1
        assert variables[0].is_readonly is False
