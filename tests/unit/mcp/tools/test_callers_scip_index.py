"""SCIP reader (stdlib protobuf decoding) and the SCIP symbol grammar."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.mcp.tools import scip_builder as b
from tree_sitter_analyzer.mcp.tools import callers_scip_symbols as sym
from tree_sitter_analyzer.mcp.tools.callers_scip_index import (
    ROLE_DEFINITION,
    ScipFormatError,
    parse_index,
)

FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "scip_ts"
TARGET_RUN = "scip-typescript npm scip-fixture 1.0.0 src/`shapes.ts`/Target#run()."


def test_fixture_index_decodes() -> None:
    index = parse_index((FIXTURE / "index.scip").read_bytes())
    assert (index.tool_name, index.tool_version) == ("scip-typescript", "0.6.1")
    assert {"src/shapes.ts", "src/use.ts", "src/store.ts", "src/app.ts"} <= set(
        index.documents
    )
    assert index.defined_in[TARGET_RUN] == ("src/shapes.ts",)
    refs = index.references[TARGET_RUN]
    assert {(f, o.line + 1) for f, o in refs} >= {("src/use.ts", 4)}
    assert any(o.symbol == TARGET_RUN for o in index.on_line("src/use.ts", 3))
    assert index.on_line("src/use.ts", 9999) == ()


def test_ranges_enclosing_and_relationships() -> None:
    base = b.global_symbol("src/`a.ts`/Base#")
    sub = b.global_symbol("src/`a.ts`/Sub#")
    data = b.index(
        [
            b.document(
                "src\\a.ts",
                [
                    b.occurrence(2, 4, 9, sub, ROLE_DEFINITION, enclosing=(2, 0, 9, 1)),
                    b.field_bytes(1, b"") + b.text(2, "ignored-no-range"),
                ],
                [
                    b.symbol_info(
                        sub, 7, "doc", [b.relationship(base, implementation=True)]
                    )
                ],
            ),
            # The same file in a second tsconfig project: occurrences merge.
            b.document(
                "src/a.ts",
                [b.occurrence(5, 1, 4, base)],
                [
                    b.symbol_info(
                        sub, 0, "", [b.relationship(base, implementation=True)]
                    )
                ],
            ),
        ],
        external=[b.symbol_info(base, 7)],
    )
    index = parse_index(data)
    occs = index.documents["src/a.ts"]
    assert [(o.line, o.col, o.end_line, o.end_col) for o in occs] == [
        (2, 4, 2, 9),
        (5, 1, 5, 4),
    ]
    assert occs[0].enclosing == (2, 0, 9, 1)
    assert occs[0].is_definition and not occs[1].is_definition
    info = index.symbols[sub]
    assert info.kind == 7 and info.documentation == "doc"
    assert [r.symbol for r in info.relationships] == [base]
    assert info.relationships[0].is_implementation
    assert index.symbols[base].kind == 7
    assert index.references[base][0][0] == "src/a.ts"


@pytest.mark.parametrize(
    "data",
    [
        b"\x12",  # length missing
        b"\x12\x05ab",  # length overruns
        b"\x80",  # truncated varint
        b"\x0b",  # wire type 3 (groups) is unsupported
        b.index([b.document("", [])]),  # document without a path
        b.field_bytes(2, b.text(1, "") + b"\x0a\x02\xff\xfe"),  # invalid UTF-8 path
    ],
)
def test_malformed_input_raises(data: bytes) -> None:
    with pytest.raises(ScipFormatError):
        parse_index(data)


def test_fixed_width_fields_are_skipped() -> None:
    skipped = b.varint(9 << 3 | 1) + b"\0" * 8 + b.varint(10 << 3 | 5) + b"\0" * 4
    index = parse_index(skipped + b.index([b.document("x.ts", [])]))
    assert "x.ts" in index.documents


def test_symbol_grammar() -> None:
    method = "scip-typescript npm hono 4.0.0 src/`hono-base.ts`/Hono#`#addRoute`()."
    assert sym.last_name(method) == "#addRoute"
    assert sym.last_kind(method) == "method"
    assert (
        sym.owner(method) == "scip-typescript npm hono 4.0.0 src/`hono-base.ts`/Hono#"
    )
    assert sym.qual_names(method) == ["Hono", "#addRoute"]
    assert sym.package(method) == "hono"
    nested = "scip-typescript npm p 1 src/`a.ts`/outer().inner()."
    assert sym.owner(nested) is None
    assert sym.qual_names(nested) == ["outer", "inner"]
    param = "scip-typescript npm p 1 src/`a.ts`/f().(x)"
    assert sym.last_name(param) is None and sym.last_kind(param) == "param"
    tparam = "scip-typescript npm p 1 src/`a.ts`/f().[T]"
    assert sym.last_kind(tparam) == "typeparam"
    assert sym.last_kind("scip-typescript npm p 1 src/`a.ts`/x.") == "term"
    assert sym.last_kind("scip-typescript npm p 1 m:") == "meta"
    assert sym.last_kind("scip-typescript npm p 1 m!") == "macro"
    assert sym.last_name("scip-typescript npm p 1 src/`a``b.ts`/f().") == "f"
    assert sym.parse("scip-typescript npm p 1 src/`a``b.ts`/")[1][-1][1] == "a`b.ts"
    assert sym.package("scip-typescript npm my  pkg 1 x.") == "my pkg"
    assert sym.last_kind("scip-typescript npm p 1 trailing") == "?"
    assert sym.owner("scip-typescript npm p 1 f().") is None


@pytest.mark.parametrize(
    "symbol",
    ["", "local 3", "scip-typescript npm p 1 f(unterminated"],
)
def test_local_and_unparseable_symbols(symbol: str) -> None:
    assert sym.parse(symbol) is None
    assert sym.last_name(symbol) is None
    assert sym.last_kind(symbol) is None
    assert sym.owner(symbol) is None
    assert sym.qual_names(symbol) is None
    assert sym.package(symbol) is None
