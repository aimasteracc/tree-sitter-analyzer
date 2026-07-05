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


def test_nested_namespace_name() -> None:
    """``namespace A.B { }`` carries a nested_identifier name."""
    extractor = TypeScriptElementExtractor()
    lang = tree_sitter.Language(language_typescript())
    parser = tree_sitter.Parser(lang)
    src = "namespace A.B { export const x = 1; }\n"
    classes = extractor.extract_classes(parser.parse(src.encode()), src)
    names = {c.name: c.class_type for c in classes}
    assert names.get("A.B") == "namespace"


def test_ambient_string_module_name() -> None:
    """``declare module "pkg" { }`` carries a string name — quotes stripped."""
    extractor = TypeScriptElementExtractor()
    lang = tree_sitter.Language(language_typescript())
    parser = tree_sitter.Parser(lang)
    src = 'declare module "my-pkg" { export function f(): void; }\n'
    classes = extractor.extract_classes(parser.parse(src.encode()), src)
    names = {c.name: c.class_type for c in classes}
    assert names.get("my-pkg") == "namespace"


def test_nameless_namespace_node_returns_none() -> None:
    """A namespace node with no name child must be skipped, not crash."""
    from unittest.mock import Mock

    from tree_sitter_analyzer.languages.typescript_plugin._class import (
        extract_namespace,
    )

    node = Mock()
    node.start_point = (0, 0)
    node.end_point = (0, 10)
    node.children = []
    assert (
        extract_namespace(node, lambda n: "", lambda line: None, lambda n: False, "")
        is None
    )


def test_namespace_extractor_exception_returns_none() -> None:
    """An exploding node must be caught and yield None (error path)."""
    from unittest.mock import Mock

    from tree_sitter_analyzer.languages.typescript_plugin._class import (
        extract_namespace,
    )

    node = Mock()
    node.start_point = (0, 0)
    node.end_point = (0, 10)
    type(node).children = property(
        lambda self: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    assert (
        extract_namespace(node, lambda n: "", lambda line: None, lambda n: False, "")
        is None
    )
