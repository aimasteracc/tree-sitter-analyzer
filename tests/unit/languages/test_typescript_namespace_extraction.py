"""Theme-I regression: TypeScript ``namespace`` / ``module`` extraction.

2026-06-10 quality-audit finding (worse than the pilot reported): a
``namespace X { ... }`` block parses as ``expression_statement >
internal_module`` and ``module Y { ... }`` as a ``module`` node — none of
which were in the traversal container whitelist or the extractor map. So the
namespace itself was invisible AND every symbol inside it (classes,
functions, interfaces) was silently lost from outlines.
"""

from __future__ import annotations

import tree_sitter
from tree_sitter_typescript import language_typescript

from tree_sitter_analyzer.languages.typescript_plugin.extractor import (
    TypeScriptElementExtractor,
)

TS_SRC = """\
namespace Geometry {
    export interface Point { x: number; y: number; }
    export function dist(p: Point): number { return Math.sqrt(p.x*p.x + p.y*p.y); }
    export class Circle {
        constructor(public r: number) {}
        area(): number { return Math.PI * this.r * this.r; }
    }
}

module Legacy {
    export const VERSION = "1.0";
}

enum Color { Red, Green }

class Standalone {
    run(): void {}
}
"""


def _parse():
    lang = tree_sitter.Language(language_typescript())
    parser = tree_sitter.Parser(lang)
    return parser.parse(TS_SRC.encode())


def _extract_classes() -> dict[str, str]:
    extractor = TypeScriptElementExtractor()
    classes = extractor.extract_classes(_parse(), TS_SRC)
    return {c.name: c.class_type for c in classes}


def _extract_function_names() -> set[str]:
    extractor = TypeScriptElementExtractor()
    return {f.name for f in extractor.extract_functions(_parse(), TS_SRC)}


def test_namespace_itself_extracted() -> None:
    found = _extract_classes()
    assert found.get("Geometry") == "namespace", f"got {sorted(found)}"


def test_module_itself_extracted() -> None:
    found = _extract_classes()
    assert found.get("Legacy") == "namespace", f"got {sorted(found)}"


def test_symbols_inside_namespace_extracted() -> None:
    """The critical bug: everything inside a namespace was silently lost."""
    found = _extract_classes()
    assert found.get("Circle") == "class", f"got {sorted(found)}"
    assert found.get("Point") == "interface", f"got {sorted(found)}"
    names = _extract_function_names()
    assert "dist" in names, f"namespace function missing; got {sorted(names)}"


def test_top_level_kinds_unchanged() -> None:
    found = _extract_classes()
    assert found.get("Color") == "enum"
    assert found.get("Standalone") == "class"
    names = _extract_function_names()
    assert "run" in names
