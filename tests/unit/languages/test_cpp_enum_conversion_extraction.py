"""Theme-I regression: C++ ``enum`` / ``enum class`` and conversion operators.

2026-06-10 quality-audit finding, CLI-verified: ``enum_specifier`` was not
registered in the class extractor map, so plain enums AND scoped
``enum class`` declarations were completely invisible in outlines. Conversion
operators (``operator double() const``) parse as ``function_definition >
operator_cast`` (no ``function_declarator``), which the signature parser
couldn't name, so they vanished from the function list while ``operator+``
(a normal declarator) survived.
"""

from __future__ import annotations

import tree_sitter
import tree_sitter_cpp

from tree_sitter_analyzer.languages.cpp_plugin import CppElementExtractor

CPP_SRC = """\
enum Color { RED, GREEN };

enum class Status : int { OK = 0, FAIL = 1 };

class Meters {
public:
    explicit Meters(double v) : value(v) {}
    operator double() const { return value; }
    Meters operator+(const Meters& o) const { return Meters(value + o.value); }
    double get() const { return value; }
private:
    double value;
};
"""


def _extract():
    lang = tree_sitter.Language(tree_sitter_cpp.language())
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(CPP_SRC.encode())
    extractor = CppElementExtractor()
    classes = {c.name: c.class_type for c in extractor.extract_classes(tree, CPP_SRC)}
    functions = {f.name for f in extractor.extract_functions(tree, CPP_SRC)}
    return classes, functions


def test_plain_enum_extracted() -> None:
    classes, _ = _extract()
    assert classes.get("Color") == "enum", f"got {sorted(classes)}"


def test_enum_class_extracted() -> None:
    classes, _ = _extract()
    assert classes.get("Status") == "enum_class", f"got {sorted(classes)}"


def test_conversion_operator_extracted() -> None:
    _, functions = _extract()
    assert "operator double" in functions, f"got {sorted(functions)}"


def test_existing_extraction_unchanged() -> None:
    classes, functions = _extract()
    assert classes.get("Meters") == "class"
    assert "operator+" in functions
    assert "get" in functions


def test_enum_extractor_exception_returns_none() -> None:
    """An exploding node must be caught and yield None (error path).

    The inner class extractor is stubbed to return a truthy result so the
    explosion happens in the scoped-check loop and the enum extractor's OWN
    except branch is the one exercised (not the inner extractor's catch).
    """
    from unittest.mock import Mock

    extractor = CppElementExtractor()
    extractor._extract_class_optimized = lambda n: Mock()  # type: ignore[method-assign]
    node = Mock()
    type(node).children = property(
        lambda self: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    assert extractor._extract_enum_optimized(node) is None


def test_operator_cast_without_type_child_yields_no_name() -> None:
    """operator_cast with no recognizable type child -> parser returns None."""
    from unittest.mock import Mock

    from tree_sitter_analyzer.languages._cpp_signature import (
        parse_function_signature,
    )

    cast = Mock()
    cast.type = "operator_cast"
    cast.children = []  # no _TYPE_NODES_CPP child
    node = Mock()
    node.children = [cast]
    assert parse_function_signature(node, lambda n: "", lambda n: []) is None
