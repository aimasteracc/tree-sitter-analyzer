"""Issue #791: JS prototype-assignment methods silently dropped.

``Animal.prototype.speak = function speak() {...}`` and
``Animal.prototype.walk = function() {...}`` must be extracted as methods
of class 'Animal', not silently discarded.

RED-first: this test MUST fail before the fix and pass after it.
"""

from __future__ import annotations

import pytest
import tree_sitter_javascript as tsjs
from tree_sitter import Language, Parser

from tree_sitter_analyzer.languages.javascript_plugin.extractor import (
    JavaScriptElementExtractor,
)


@pytest.fixture(scope="module")
def js_parser() -> Parser:
    return Parser(Language(tsjs.language()))


@pytest.fixture(scope="module")
def prototype_fixture() -> str:
    return (
        "\n"
        "function Animal(name) { this.name = name; }\n"
        "Animal.prototype.speak = function speak() { return this.name; };\n"
        "Animal.prototype.walk = function() { return 'walking'; };\n"
    )


@pytest.fixture(scope="module")
def extracted(js_parser: Parser, prototype_fixture: str):
    tree = js_parser.parse(bytes(prototype_fixture, "utf-8"))
    ext = JavaScriptElementExtractor()
    ext.current_file = "animal.js"
    ext._file_encoding = "utf-8"
    functions = ext.extract_functions(tree, prototype_fixture)
    classes = ext.extract_classes(tree, prototype_fixture)
    return {"functions": functions, "classes": classes}


# ---------------------------------------------------------------------------
# Core correctness assertions
# ---------------------------------------------------------------------------


def test_method_count(extracted):
    """Exactly 3 functions: Animal constructor + speak + walk."""
    assert len(extracted["functions"]) == 3


def test_class_count(extracted):
    """Animal is synthesised as a class via prototype aggregation."""
    assert len(extracted["classes"]) == 1


def test_class_name(extracted):
    assert extracted["classes"][0].name == "Animal"


def test_speak_present(extracted):
    names = [f.name for f in extracted["functions"]]
    assert "speak" in names


def test_walk_present(extracted):
    names = [f.name for f in extracted["functions"]]
    assert "walk" in names


def test_speak_is_method(extracted):
    speak = next(f for f in extracted["functions"] if f.name == "speak")
    assert speak.is_method is True


def test_walk_is_method(extracted):
    walk = next(f for f in extracted["functions"] if f.name == "walk")
    assert walk.is_method is True


def test_speak_parent_class(extracted):
    speak = next(f for f in extracted["functions"] if f.name == "speak")
    assert speak.parent_class == "Animal"


def test_walk_parent_class(extracted):
    walk = next(f for f in extracted["functions"] if f.name == "walk")
    assert walk.parent_class == "Animal"


def test_constructor_not_lost(extracted):
    """The Animal constructor function must still be extracted."""
    names = [f.name for f in extracted["functions"]]
    assert "Animal" in names


def test_no_duplicate_names(extracted):
    """No function name should appear more than once."""
    names = [f.name for f in extracted["functions"]]
    assert len(names) == len(set(names))
