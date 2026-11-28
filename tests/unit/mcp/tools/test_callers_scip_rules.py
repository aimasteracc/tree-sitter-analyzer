"""Fail-closed rules of the SCIP layer, on hand-built indexes (no indexer, no TSA index).

* trust classes: only the trusted "different symbol" classes drop a site;
* the occurrence count on a line must match the text, one symbol per position;
* an enclosing definition TSA and SCIP disagree on gives no promotion;
* SCIP never removes a TSA caller; a SCIP reference TSA lists nowhere is
  ``SCIP_UNLISTED_REFERENCE``;
* the optional ``scip_agreement`` check is required only when enabled.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.mcp.tools import scip_builder as b
from tree_sitter_analyzer.call_graph import FunctionRef
from tree_sitter_analyzer.mcp.tools import callers_scip as layer_mod
from tree_sitter_analyzer.mcp.tools.callers_checks import (
    REQUIRED_CHECKS,
    Ledger,
    prove,
)
from tree_sitter_analyzer.mcp.tools.callers_outcomes import Checked, checked
from tree_sitter_analyzer.mcp.tools.callers_scip import (
    OPEN,
    PROVEN_OTHER,
    PROVEN_TARGET,
    UNCHECKED_REASON,
    UNLISTED_REASON,
    ScipLayer,
    restrict_open_sites,
    scip_check,
    unlisted_step,
)
from tree_sitter_analyzer.mcp.tools.callers_scip_index import (
    ROLE_DEFINITION,
    ROLE_IMPORT,
    parse_index,
)
from tree_sitter_analyzer.mcp.tools.callers_scip_source import (
    STALE,
    USED,
    ScipSource,
    map_target,
)
from tree_sitter_analyzer.mcp.tools.callers_scip_trust import (
    TypeGraph,
    classify,
    nominal,
    target_context,
)

S = b.global_symbol
TARGET = S("src/`a.ts`/Target#run().")
TARGET_CLS = S("src/`a.ts`/Target#")
NOMINAL = S("src/`a.ts`/Nominal#")
NOMINAL_RUN = S("src/`a.ts`/Nominal#run().")
LOOSE = S("src/`a.ts`/Loose#")
LOOSE_RUN = S("src/`a.ts`/Loose#run().")
SUB = S("src/`a.ts`/Sub#")
SUB_RUN = S("src/`a.ts`/Sub#run().")
IFACE = S("src/`a.ts`/Runner#")
IFACE_RUN = S("src/`a.ts`/Runner#run().")
FUNC_RUN = S("src/`b.ts`/run().")
VAR_RUN = S("src/`b.ts`/run.")
AMBIENT_RUN = S("src/`c.d.ts`/run().")
CORE_TRIM = "scip-typescript npm typescript 5.0.0 lib/`lib.es5.d.ts`/String#trim()."
DOM_RUN = "scip-typescript npm typescript 5.0.0 lib/`lib.dom.d.ts`/Worker#run()."
EXT_RUN = "scip-typescript npm other 1.0.0 dist/Ext#run()."

A_TS = [
    "export class Target {",  # 0
    "  run() { return 1 }",  # 1
    "}",  # 2
    "export class Nominal {",  # 3
    "  private x = 1",  # 4
    "  run() { return 2 }",  # 5
    "}",  # 6
    "export class Loose { run() { return 3 } }",  # 7
    "export class Sub extends Target { run() { return 4 } }",  # 8
    "export interface Runner { run(): number }",  # 9
]
USE_TS = [
    "export function viaTarget(t: Target) {",  # 0
    "  return t.run()",  # 1
    "}",  # 2
    "export function viaNominal(n: Nominal) { return n.run() }",  # 3
    "export function viaLoose(l: Loose) { return l.run() }",  # 4
    "export function viaSub(s: Sub) { return s.run() }",  # 5
    "export function viaIface(r: Runner) { return r.run() }",  # 6
    "export function twice(t: Target) { return t.run() } // run",  # 7
    "export function both(t: Target, n: Nominal) { return t.run() + n.run() }",  # 8
    "const f = t.run",  # 9: a reference TSA lists nowhere
    "import { run } from './b'",  # 10: imports never count
    "export function ambiguous(t: Target) { return t.run() }",  # 11
]


def _occ(line: int, col: int, end: int, symbol: str, roles: int = 0, enc=None):
    return b.occurrence(line, col, end, symbol, roles, enclosing=enc)


def _fixture(tmp_path: Path) -> ScipSource:
    for name, lines in (("src/a.ts", A_TS), ("src/use.ts", USE_TS)):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    a_doc = b.document(
        "src/a.ts",
        [
            _occ(0, 13, 19, TARGET_CLS, ROLE_DEFINITION, (0, 0, 2, 1)),
            _occ(1, 2, 5, TARGET, ROLE_DEFINITION, (1, 2, 1, 20)),
            _occ(3, 13, 20, NOMINAL, ROLE_DEFINITION, (3, 0, 6, 1)),
            _occ(4, 10, 11, S("src/`a.ts`/Nominal#x."), ROLE_DEFINITION),
            _occ(5, 2, 5, NOMINAL_RUN, ROLE_DEFINITION),
            _occ(7, 13, 18, LOOSE, ROLE_DEFINITION),
            _occ(7, 21, 24, LOOSE_RUN, ROLE_DEFINITION),
            _occ(8, 13, 16, SUB, ROLE_DEFINITION),
            _occ(8, 35, 38, SUB_RUN, ROLE_DEFINITION),
            _occ(9, 17, 23, IFACE, ROLE_DEFINITION),
            _occ(9, 26, 29, IFACE_RUN, ROLE_DEFINITION),
        ],
        [
            b.symbol_info(TARGET_CLS, 7),
            b.symbol_info(NOMINAL, 7),
            b.symbol_info(LOOSE, 7),
            b.symbol_info(
                SUB, 7, rels=[b.relationship(TARGET_CLS, implementation=True)]
            ),
            b.symbol_info(IFACE, 21),
        ],
    )
    use_doc = b.document(
        "src/use.ts",
        [
            _occ(
                0, 16, 25, S("src/`use.ts`/viaTarget()."), ROLE_DEFINITION, (0, 0, 2, 1)
            ),
            _occ(1, 11, 14, TARGET),
            _occ(3, 50, 53, NOMINAL_RUN),
            _occ(4, 46, 49, LOOSE_RUN),
            _occ(5, 42, 45, SUB_RUN),
            _occ(6, 47, 50, IFACE_RUN),
            _occ(7, 45, 48, TARGET),
            _occ(8, 57, 60, TARGET),
            _occ(8, 69, 72, NOMINAL_RUN),
            _occ(9, 12, 15, TARGET),
            _occ(10, 9, 12, FUNC_RUN, ROLE_IMPORT),
            # Two projects resolved the same token differently: ambiguous.
            _occ(11, 50, 53, TARGET),
            _occ(11, 50, 53, LOOSE_RUN),
        ],
    )
    index = parse_index(b.index([a_doc, use_doc]))
    graph = TypeGraph(index)
    targets = frozenset({TARGET})
    return ScipSource(
        USED,
        tmp_path,
        index=index,
        graph=graph,
        targets=targets,
        context=target_context(graph, targets),
    )


def _verdict(layer: ScipLayer, line0: int) -> str:
    return layer.classify_site("src/use.ts", line0 + 1, None).outcome


def test_site_outcomes_follow_the_trust_classes(tmp_path: Path) -> None:
    layer = ScipLayer(_fixture(tmp_path), "run")
    assert _verdict(layer, 1) == PROVEN_TARGET
    assert _verdict(layer, 3) == PROVEN_OTHER  # nominal class
    assert _verdict(layer, 5) == PROVEN_OTHER  # subclass override
    assert _verdict(layer, 4) == OPEN  # structural class
    assert _verdict(layer, 6) == OPEN  # interface
    assert _verdict(layer, 8) == PROVEN_TARGET  # target + trusted other


def test_occurrence_count_mismatch_and_ambiguity_stay_open(tmp_path: Path) -> None:
    layer = ScipLayer(_fixture(tmp_path), "run")
    assert layer.classify_site("src/use.ts", 8, None).why == "occurrence_count_mismatch"
    assert layer.classify_site("src/use.ts", 12, None).why == "ambiguous_occurrence"
    assert layer.classify_site("src/use.ts", 3, None).why == "no_occurrence"
    assert layer.classify_site("src/none.ts", 1, None).why == "file_not_indexed"
    # Memoized per (file, line, callee).
    assert layer.classify_site("src/use.ts", 2, None) is layer.classify_site(
        "src/use.ts", 2, None
    )


def test_trust_classes(tmp_path: Path) -> None:
    src = _fixture(tmp_path)
    graph, ctx = src.graph, src.context
    assert graph is not None and ctx is not None

    def cls(symbol: str) -> str:
        return classify(graph, symbol, ctx, src.lines)

    assert cls(TARGET) == "target"
    assert cls("local 4") == "local"
    assert cls(NOMINAL_RUN) == "other_class_nominal"
    assert cls(LOOSE_RUN) == "other_class"
    assert cls(SUB_RUN) == "subclass_override"
    assert cls(IFACE_RUN) == "structural"
    assert cls(CORE_TRIM) == "external_core"
    assert cls(DOM_RUN) == "external_iface"
    assert cls(EXT_RUN) == "external_iface"
    assert cls(S("src/`b.ts`/helper().")) == "external_function"
    assert cls(S("src/`a.ts`/Target#other().")) == "same_class_other"
    assert nominal(graph, NOMINAL, src.lines) and not nominal(graph, LOOSE, src.lines)


def test_ambient_dispatch_and_function_classes(tmp_path: Path) -> None:
    base_run = S("src/`a.ts`/Base#run().")
    doc = b.document(
        "src/b.ts",
        [
            _occ(0, 0, 3, FUNC_RUN, ROLE_DEFINITION),
            _occ(1, 0, 3, VAR_RUN, ROLE_DEFINITION),
        ],
    )
    ambient = b.document("src/c.d.ts", [_occ(0, 0, 3, AMBIENT_RUN, ROLE_DEFINITION)])
    target_doc = b.document(
        "src/a.ts",
        [_occ(1, 2, 5, TARGET, ROLE_DEFINITION)],
        [
            b.symbol_info(
                TARGET, 26, rels=[b.relationship(base_run, implementation=True)]
            )
        ],
    )
    index = parse_index(b.index([doc, ambient, target_doc]))
    graph = TypeGraph(index)
    ctx = target_context(graph, frozenset({TARGET}))
    lines = lambda _p: []  # noqa: E731
    assert classify(graph, FUNC_RUN, ctx, lines) == "other_function"
    assert classify(graph, VAR_RUN, ctx, lines) == "via_variable"
    assert classify(graph, AMBIENT_RUN, ctx, lines) == "ambient_decl"
    assert classify(graph, base_run, ctx, lines) == "dispatch_super"


class _Graph:
    def __init__(self, refs: list[FunctionRef]) -> None:
        self.refs = refs

    def function_refs_in_file(self, file: str) -> list[FunctionRef]:
        return [r for r in self.refs if r.file_path == file]


def _ref(name: str, start: int, end: int, file: str = "src/use.ts") -> FunctionRef:
    return FunctionRef(file, name, start, "typescript", end_line=end)


def test_apply_promotes_drops_and_never_removes_a_listed_caller(tmp_path: Path) -> None:
    layer = ScipLayer(_fixture(tmp_path), "run")
    graph = _Graph([_ref("viaTarget", 1, 3), _ref("viaNominal", 4, 4)])
    listed = [{"file": "src/use.ts", "name": "kept", "line": 50, "end_line": 51}]
    unresolved = [
        {"file": "src/use.ts", "line": 2, "callee": "t.run", "caller": "viaTarget"},
        {"file": "src/use.ts", "line": 4, "callee": "n.run", "caller": "viaNominal"},
        {"file": "src/use.ts", "line": 5, "callee": "l.run", "caller": "viaLoose"},
    ]
    declaring = [{"file": "src/use.ts", "line": 4, "callee": "n.run"}]
    applied = layer.apply(
        graph,
        declaring=declaring,
        excluded=[],
        unresolved=unresolved,
        possible=[],
        call_lines=None,
        listed=listed,
        target_file="src/a.ts",
    )
    assert [c["name"] for c in applied.callers] == ["viaTarget"]
    assert applied.callers[0]["resolution_kind"] == "scip"
    assert [s["line"] for s in applied.unresolved or []] == [5]
    assert [s["reason_code"] for s in applied.unresolved_excluded] == [
        "SCIP_RESOLVED_OTHER"
    ]
    assert applied.declaring == []
    assert (
        applied.excluded and applied.excluded[0]["reason_code"] == "SCIP_RESOLVED_OTHER"
    )
    # The inputs are untouched and the listed caller is not in the output to drop.
    assert len(unresolved) == 3 and listed[0]["name"] == "kept"
    problems = layer.agreement(listed + applied.callers, [applied.unresolved], [])
    assert problems == (UNLISTED_REASON,)
    kinds = {d["kind"] for d in layer.disagreements}
    assert "listed_caller_without_scip_reference" in kinds
    assert any(r["line"] == 10 for r in layer.unlisted)
    report = layer.report()
    assert report["added_callers"] == 1 and report["unlisted_references_total"] >= 1


def test_attribution_must_agree_between_tsa_and_scip(tmp_path: Path) -> None:
    layer = ScipLayer(_fixture(tmp_path), "run")
    # TSA's innermost definition has another name than SCIP's enclosing one.
    assert (
        layer.attribute(_Graph([_ref("wrapper", 1, 3)]), "src/use.ts", 2, None) is None
    )
    # The edge names another caller than the innermost definition.
    graph = _Graph([_ref("viaTarget", 1, 3)])
    assert layer.attribute(graph, "src/use.ts", 2, "other") is None
    assert layer.attribute(graph, "src/use.ts", 2, "viaTarget")["name"] == "viaTarget"
    # Two equally small definitions: ambiguous.
    tied = _Graph([_ref("viaTarget", 1, 3), _ref("viaTarget", 1, 3, "src/use.ts")])
    tied.refs[1] = FunctionRef("src/use.ts", "twin", 1, "typescript", end_line=3)
    assert layer.attribute(tied, "src/use.ts", 2, None) is None
    # Module level: no TSA definition and no SCIP enclosing definition.
    module = layer.attribute(_Graph([]), "src/use.ts", 10, "<module>")
    assert module is not None and module["name"] == "<module>"
    assert layer.attribute(_Graph([]), "src/use.ts", 10, "named") is None


class _Broken:
    def function_refs_in_file(self, file: str) -> list[FunctionRef]:
        raise RuntimeError("graph unreadable")


def test_unreadable_graph_gives_no_promotion(tmp_path: Path) -> None:
    layer = ScipLayer(_fixture(tmp_path), "run")
    assert layer.attribute(_Broken(), "src/use.ts", 2, None) is None


def test_name_only_callers(tmp_path: Path) -> None:
    layer = ScipLayer(_fixture(tmp_path), "run")
    graph = _Graph(
        [_ref("viaTarget", 1, 3), _ref("viaNominal", 4, 4), _ref("viaLoose", 5, 5)]
    )
    possible = [
        {"file": "src/use.ts", "name": "viaTarget", "line": 1, "end_line": 3},
        {"file": "src/use.ts", "name": "viaNominal", "line": 4, "end_line": 4},
        {"file": "src/use.ts", "name": "viaLoose", "line": 5, "end_line": 5},
        {"file": "src/use.ts", "name": "noLines", "line": 40, "end_line": 41},
    ]
    lines = {"src/use.ts": frozenset({2, 4, 5})}
    applied = layer.apply(
        graph,
        declaring=None,
        excluded=None,
        unresolved=None,
        possible=possible,
        call_lines=lines,
        listed=[],
        target_file="src/a.ts",
    )
    assert [c["name"] for c in applied.callers] == ["viaTarget"]
    assert [c["name"] for c in applied.possible] == ["viaLoose", "noLines"]
    assert applied.declaring is None and applied.excluded is None
    assert layer.counts == {PROVEN_TARGET: 1, PROVEN_OTHER: 1, OPEN: 2}


def test_map_target(tmp_path: Path) -> None:
    index = _fixture(tmp_path).index
    assert index is not None
    assert map_target(index, "src/a.ts", "Target.run", True) == (
        frozenset({TARGET}),
        None,
    )
    assert map_target(index, "src/a.ts", "run", False)[0] >= {TARGET, NOMINAL_RUN}
    assert map_target(index, "src/a.ts", "Nope.run", True) == (frozenset(), "not_found")
    assert map_target(index, "src/zz.ts", "run", False)[1] == "file_not_indexed"
    assert map_target(index, "src/a.ts", "", False)[1] == "not_found"
    twin = b.document(
        "src/t.ts",
        [
            _occ(0, 0, 1, S("src/`t.ts`/A#run()."), ROLE_DEFINITION),
            _occ(1, 0, 1, S("src/`t.ts`/A#run(+1)."), ROLE_DEFINITION),
        ],
    )
    assert map_target(parse_index(b.index([twin])), "src/t.ts", "A.run", True)[1] == (
        "ambiguous"
    )


def test_scip_check_records_or_skips(tmp_path: Path) -> None:
    scope = ("Target.run", "src/a.ts")
    layer = ScipLayer(_fixture(tmp_path), "run")
    ledger = scip_check(
        layer, Ledger(scope), scope, callers=[], open_lists=[], excluded=[]
    )
    assert ledger.outcomes["scip_agreement"] == Checked(scope, (UNLISTED_REASON,))
    stale = ScipLayer(ScipSource(STALE, tmp_path), "run")
    skipped = scip_check(
        stale, Ledger(scope), scope, callers=[], open_lists=[], excluded=[]
    )
    assert skipped.not_applicable == {"scip_agreement": "stale"}
    assert "scip_agreement" not in skipped.enabled


def test_scip_check_fails_closed_on_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scope = ("Target.run", "src/a.ts")
    layer = ScipLayer(_fixture(tmp_path), "run")

    def boom(*_a: object, **_k: object) -> tuple[str, ...]:
        raise ValueError("bad")

    monkeypatch.setattr(layer, "agreement", boom)
    ledger = scip_check(
        layer, Ledger(scope), scope, callers=[], open_lists=[], excluded=[]
    )
    passing = ledger.record_all((s.name, checked(scope)) for s in REQUIRED_CHECKS)
    proof = prove(passing, 1)
    assert proof.completeness == "incomplete"
    assert proof.reasons == (UNCHECKED_REASON,)


def test_optional_check_is_required_only_when_enabled() -> None:
    scope = ("f", "a.ts")
    passing = Ledger(scope).record_all(
        (s.name, checked(scope)) for s in REQUIRED_CHECKS
    )
    assert prove(passing, 0).checks == {"required": 13, "checked": 13}
    enabled = passing.enable("scip_agreement")
    assert prove(enabled, 0).completeness == "unknown"
    done = enabled.record("scip_agreement", checked(scope))
    assert prove(done, 0).checks == {"required": 14, "checked": 14}
    blocked = enabled.record("scip_agreement", checked(scope, UNLISTED_REASON))
    assert prove(blocked, 2).reasons == (UNLISTED_REASON,)
    skipped = passing.skip("scip_agreement", "absent")
    assert prove(skipped, 0).checks["not_applicable"] == {"scip_agreement": "absent"}
    with pytest.raises(ValueError):
        passing.record("scip_agreement", checked(scope))
    with pytest.raises(ValueError):
        passing.enable("nope")
    with pytest.raises(ValueError):
        enabled.skip("scip_agreement", "x")


def test_open_sites_and_step(tmp_path: Path) -> None:
    layer = ScipLayer(_fixture(tmp_path), "run")
    bound = {"total": 1, "enumerated": True, "fields": ["name_only_sites"]}
    assert restrict_open_sites(bound, None) is bound
    assert restrict_open_sites(bound, layer) is bound
    assert unlisted_step("run", layer) is None
    layer.agreement([], [], [])
    assert restrict_open_sites(bound, layer) == {
        "enumerated": False,
        "reason": UNLISTED_REASON,
    }
    for line in range(5):
        layer.unlisted.append({"file": "x.ts", "line": line, "text": ""})
    assert "and " in (unlisted_step("run", layer) or "")


def test_report_of_an_inactive_layer(tmp_path: Path) -> None:
    report = ScipLayer(
        ScipSource(STALE, tmp_path, detail="git tree differs"), "f"
    ).report()
    assert report == {"status": "stale", "detail": "git tree differs"}
    assert layer_mod.LIST_CAP == 20
