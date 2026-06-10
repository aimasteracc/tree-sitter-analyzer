"""Theme-I regression: Java ``record`` and ``@interface`` (annotation type)
declarations must appear in extraction output.

2026-06-10 quality-audit finding: the extractor registration map and
``_CLASS_TYPE_MAP`` only listed ``class_declaration`` / ``interface_declaration``
/ ``enum_declaration``, so ``record_declaration`` and
``annotation_type_declaration`` nodes (both top-level and nested) were silently
dropped from outlines — an agent asking for the structure of a modern Java
file never saw its records or annotation types.
"""

from __future__ import annotations

import tree_sitter
import tree_sitter_java

from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor

JAVA_SRC = """\
package demo;

public class Container {
    public record Point(int x, int y) {
        public double dist() { return Math.sqrt(x * x + y * y); }
    }

    public @interface Audited {
        String value() default "";
    }

    public enum Color { RED, GREEN }

    void use() {}
}

record TopLevelRecord(String name, int age) {}

@interface TopLevelAnno { int level(); }
"""


def _extract_classes() -> dict[str, str]:
    lang = tree_sitter.Language(tree_sitter_java.language())
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(JAVA_SRC.encode())
    extractor = JavaElementExtractor()
    classes = extractor.extract_classes(tree, JAVA_SRC)
    return {c.name: c.class_type for c in classes}


def test_record_declarations_extracted() -> None:
    found = _extract_classes()
    assert "Point" in found, f"nested record missing; got {sorted(found)}"
    assert "TopLevelRecord" in found, f"top-level record missing; got {sorted(found)}"
    assert found["Point"] == "record"
    assert found["TopLevelRecord"] == "record"


def test_annotation_type_declarations_extracted() -> None:
    found = _extract_classes()
    assert "Audited" in found, f"nested @interface missing; got {sorted(found)}"
    assert "TopLevelAnno" in found, f"top-level @interface missing; got {sorted(found)}"
    assert found["Audited"] == "annotation"
    assert found["TopLevelAnno"] == "annotation"


def test_existing_kinds_unchanged() -> None:
    """The graduation must not disturb class/enum extraction."""
    found = _extract_classes()
    assert found.get("Container") == "class"
    assert found.get("Color") == "enum"


def test_record_method_still_extracted() -> None:
    """Methods inside a record body must be visible as functions."""
    lang = tree_sitter.Language(tree_sitter_java.language())
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(JAVA_SRC.encode())
    extractor = JavaElementExtractor()
    functions = extractor.extract_functions(tree, JAVA_SRC)
    names = {f.name for f in functions}
    assert "dist" in names, f"record method missing; got {sorted(names)}"
