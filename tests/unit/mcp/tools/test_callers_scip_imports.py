"""#1892: a SCIP reference inside a (multi-line) import statement is not unlisted.

``scip_agreement`` skips import specifiers and export-list entries: they name
the target without calling it. Only positions inside a statement tree-sitter
parsed as an import / export list are skipped; a call after the statement on
its closing line, code in template literals or comments that look like
imports, dynamic ``import()`` and broken statements all still count.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.mcp.tools import scip_builder as b
from tree_sitter_analyzer.mcp.tools import callers_scip_imports as imports
from tree_sitter_analyzer.mcp.tools.callers_scip import UNLISTED_REASON, ScipLayer
from tree_sitter_analyzer.mcp.tools.callers_scip_index import (
    ROLE_DEFINITION,
    parse_index,
)
from tree_sitter_analyzer.mcp.tools.callers_scip_source import USED, ScipSource
from tree_sitter_analyzer.mcp.tools.callers_scip_trust import (
    TypeGraph,
    target_context,
)

TARGET = b.global_symbol("src/`a.ts`/run().")

#: ``(line, marker)``: the target reference is the ``run`` after ``marker``.
SKIPPED = "skipped"
COUNTED = "counted"
USE_TS = [
    ("import {", None),  # 0
    ("  alpha,", None),  # 1
    ("  run,", SKIPPED),  # 2: multi-line named import
    ('} from "./a"', None),  # 3
    ("import type {", None),  # 4
    ("  run as R,", SKIPPED),  # 5: multi-line type import
    ('} from "./a"', None),  # 6
    ("export {", None),  # 7
    ("  run,", SKIPPED),  # 8: multi-line re-export
    ('} from "./a"', None),  # 9
    ("import Def, {", None),  # 10
    ("  // } is not the end", None),  # 11
    ("  run as r2, /* { */", SKIPPED),  # 12: default + named, comments inside
    ('} from "./a"; run()', COUNTED),  # 13: a call after the statement
    ("const s = `import {", None),  # 14
    ("  ${run()}", COUNTED),  # 15: a template literal is not an import
    ('} from "./a"`', None),  # 16
    ("/* import {", None),  # 17
    ("  run,", COUNTED),  # 18: a comment is not an import
    ('} from "./a" */', None),  # 19
    ('import("./a").then((m) => m.run())', COUNTED),  # 20: dynamic import
    ('import { run as one } from "./a"', SKIPPED),  # 21: single line, unchanged
    ("export { run as two }", SKIPPED),  # 22: export list, unchanged
    ('export * as ns from "./a"; run()', COUNTED),  # 23
    ("export const v = run()", COUNTED),  # 24: an exported value is a use
    ("run()", COUNTED),  # 25
]


def _write(root: Path, rel: str, lines: list[str]) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _refs(lines: list[str], expected: list[tuple[int, str]]) -> list[bytes]:
    out = []
    for line, _kind in expected:
        col = lines[line].rindex("run")
        out.append(b.occurrence(line, col, col + 3, TARGET))
    return out


def _layer(root: Path, rel: str, lines: list[str], marked: list[tuple[int, str]]):
    _write(root, "src/a.ts", ["export function run() { return 1 }"])
    _write(root, rel, lines)
    target_doc = b.document(
        "src/a.ts", [b.occurrence(0, 16, 19, TARGET, ROLE_DEFINITION, (0, 0, 0, 35))]
    )
    index = parse_index(b.index([target_doc, b.document(rel, _refs(lines, marked))]))
    graph = TypeGraph(index)
    targets = frozenset({TARGET})
    source = ScipSource(
        USED,
        root,
        index=index,
        graph=graph,
        targets=targets,
        context=target_context(graph, targets),
    )
    return ScipLayer(source, "run")


def _unlisted(layer: ScipLayer) -> list[int]:
    problems = layer.agreement([], [], [])
    lines = sorted(r["line"] - 1 for r in layer.unlisted)
    assert problems == ((UNLISTED_REASON,) if lines else ())
    return lines


def test_only_positions_inside_import_statements_are_skipped(tmp_path: Path) -> None:
    lines = [text for text, _ in USE_TS]
    marked = [(i, kind) for i, (_, kind) in enumerate(USE_TS) if kind]
    layer = _layer(tmp_path, "src/use.ts", lines, marked)
    assert _unlisted(layer) == [i for i, kind in marked if kind == COUNTED]


@pytest.mark.parametrize("rel", ["src/use.js", "src/use.mjs", "src/use.tsx"])
def test_multi_line_import_in_other_dialects(tmp_path: Path, rel: str) -> None:
    lines = ["import {", "  alpha,", "  run,", '} from "./a"', "run()"]
    layer = _layer(tmp_path, rel, lines, [(2, SKIPPED), (4, COUNTED)])
    assert _unlisted(layer) == [4]


def test_a_broken_import_gives_no_span(tmp_path: Path) -> None:
    lines = ["import {", "  run,", '  from "./a"', "const x = 1"]
    layer = _layer(tmp_path, "src/use.ts", lines, [(1, COUNTED)])
    assert _unlisted(layer) == [1]


def test_an_unsupported_file_gives_no_span(tmp_path: Path) -> None:
    lines = ["import {", "  run,", '} from "./a"']
    layer = _layer(tmp_path, "src/use.vue", lines, [(1, COUNTED)])
    assert _unlisted(layer) == [1]


def test_spans_are_cached_per_file(tmp_path: Path) -> None:
    lines = ["import {", "  run,", '} from "./a"', "run()"]
    layer = _layer(tmp_path, "src/use.ts", lines, [(1, SKIPPED), (3, COUNTED)])
    assert _unlisted(layer) == [3]
    assert list(layer._import_spans) == ["src/use.ts"]


def test_import_spans_and_columns() -> None:
    assert imports.grammar_for("A/B.CTS") == "typescript"
    assert imports.grammar_for("a.py") is None
    assert imports.import_spans("a.ts", []) == ()
    (span,) = imports.import_spans(
        "a.ts", ["import {", "  run,", '} from "./a"; run()']
    )
    assert (span.start_line, span.end_line, span.end_col) == (0, 2, 13)
    assert imports.covers((span,), 1, 2, 1, 5)
    assert not imports.covers((span,), 2, 14, 2, 17)


def test_columns_hold_under_utf16_and_code_points() -> None:
    # An astral character is one code point and two UTF-16 units: the span
    # start takes the larger count, the end the smaller.
    line = '"\U0001f600"; import { run } from "./a"'
    (span,) = imports.import_spans("a.ts", [line])
    assert span.start_col == line.index("import") + 1
    assert span.end_col == len(line)


def test_parse_failure_gives_no_span(monkeypatch: pytest.MonkeyPatch) -> None:
    from tree_sitter_analyzer import language_loader

    monkeypatch.setattr(language_loader, "load_language", lambda _g: None)
    assert imports.import_spans("a.ts", ["import {", "  run,", '} from "./a"']) == ()

    def boom(_g: str) -> None:
        raise RuntimeError("no grammar")

    monkeypatch.setattr(language_loader, "load_language", boom)
    assert imports.import_spans("a.ts", ["import { run } from './a'"]) == ()
