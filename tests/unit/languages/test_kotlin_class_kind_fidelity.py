"""Theme-I regression: Kotlin class-kind fidelity.

2026-06-10 quality-audit finding: ``extract_kotlin_class_or_object`` only
distinguished class/interface/object, so ``annotation class`` / ``data class``
/ ``enum class`` / ``sealed class`` all surfaced as ``class_type="class"`` —
an agent could not tell a DTO from an enum from an annotation in outlines
(Java reports enum/annotation/record kinds correctly; Kotlin lagged).

Known UPSTREAM limitation (documented, not fixed here): tree-sitter-kotlin
1.1.0 mis-parses an *annotated* ``annotation class`` (e.g. ``@Target(...)
annotation class X``) as an ``annotated_expression`` instead of a
``class_declaration``, so such declarations cannot be extracted at all until
the grammar is fixed. Plain ``annotation class X`` parses fine and is covered
here.
"""

from __future__ import annotations

import tree_sitter
import tree_sitter_kotlin

from tree_sitter_analyzer.languages.kotlin_plugin import KotlinElementExtractor

KOTLIN_SRC = """\
package demo

annotation class Audited(val value: String = "")

class Container {
    annotation class Nested

    data class Point(val x: Int, val y: Int)

    enum class Color { RED, GREEN }

    sealed class State

    object Singleton

    fun use() {}
}

interface Shape { fun area(): Double }
"""


def _extract_classes() -> dict[str, str]:
    lang = tree_sitter.Language(tree_sitter_kotlin.language())
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(KOTLIN_SRC.encode())
    extractor = KotlinElementExtractor()
    classes = extractor.extract_classes(tree, KOTLIN_SRC)
    return {c.name: c.class_type for c in classes}


def test_annotation_class_kind() -> None:
    found = _extract_classes()
    assert found.get("Audited") == "annotation", f"got {found.get('Audited')!r}"
    assert found.get("Nested") == "annotation", f"got {found.get('Nested')!r}"


def test_data_class_kind() -> None:
    found = _extract_classes()
    assert found.get("Point") == "data", f"got {found.get('Point')!r}"


def test_enum_class_kind() -> None:
    found = _extract_classes()
    assert found.get("Color") == "enum", f"got {found.get('Color')!r}"


def test_sealed_class_kind() -> None:
    found = _extract_classes()
    assert found.get("State") == "sealed", f"got {found.get('State')!r}"


def test_plain_kinds_unchanged() -> None:
    found = _extract_classes()
    assert found.get("Container") == "class"
    assert found.get("Shape") == "interface"
    assert found.get("Singleton") == "object"
