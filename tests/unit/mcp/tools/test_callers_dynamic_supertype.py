"""#1882: a JS/TS member under an ``extends`` clause the index cannot follow is never ``complete``.

``class V1 extends mix(Proc)`` gets no inheritance edge, so ``this.getQuery()`` in
``Proc.run`` never offers ``V1.getQuery`` as a target: before the fix the override
answered ``complete`` with 0 callers.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools import callers_supertypes
from tree_sitter_analyzer.mcp.tools.callers_open_sites import open_sites
from tree_sitter_analyzer.mcp.tools.callers_outcomes import Checked, NotChecked
from tree_sitter_analyzer.mcp.tools.callers_reasons import COMPLETENESS_REASONS
from tree_sitter_analyzer.mcp.tools.callers_supertypes import (
    DYNAMIC_SUPERTYPE_REASON,
    dynamic_supertype,
    dynamic_supertype_hint,
    supertype_outcome,
)
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool
from tree_sitter_analyzer.mcp.tools.callers_ts_source import clear_parsed

_PROC = (
    "export class Proc {\n"
    "  static create() { return new this().run() }\n"
    "  static make() { return this.build() }\n"
    "  static build() { return 1 }\n"
    "  run() { return this.getQuery() }\n"
    "  getQuery() { return '' }\n"
    "}\n"
)
#: The issue's repro, plus the plain-``extends`` and no-``extends`` negatives.
_MIXIN = (
    "import { Proc } from './a'\n"
    "const mix = <T>(B: T) => B\n"
    "export class V1 extends mix(Proc) {\n"
    "  getQuery() { return 'v1' }\n"
    "  static build() { return 2 }\n"
    "  uniqueM() { return 7 }\n"
    "  useUnique() { return this.uniqueM() }\n"
    "  constructor() { super() }\n"
    "}\n"
    "export class Plain extends Proc {\n"
    "  plainOnly() { return 3 }\n"
    "}\n"
    "export class Root {\n"
    "  rootOnly() { return 4 }\n"
    "  static rootStatic() { return 5 }\n"
    "}\n"
)
#: The grandparent's clause is the dynamic one.
_CHAIN = {
    "a.ts": _PROC,
    "mid.ts": (
        "import { Proc } from './a'\n"
        "const mix = <T>(B: T) => B\n"
        "export class Mid extends mix(Proc) {}\n"
    ),
    "leaf.ts": (
        "import { Mid } from './mid'\n"
        "export class Leaf extends Mid {\n"
        "  leafOnly() { return 1 }\n"
        "}\n"
    ),
}
#: Package and platform bases stop the walk: no new block.
_EXTERNAL = {
    "ext.ts": (
        "import { EventEmitter } from 'events'\n"
        "import * as stream from 'stream'\n"
        "export class Bus extends EventEmitter {\n"
        "  busOnly() { return 1 }\n"
        "}\n"
        "export class Pipe extends stream.Readable {\n"
        "  pipeOnly() { return 1 }\n"
        "}\n"
        "export function use() { return helper() }\n"
        "function helper() { return 1 }\n"
        "export class Oops extends Error {\n"
        "  oopsOnly() { return 1 }\n"
        "}\n"
    ),
}


async def _index(root, files: dict[str, str]) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    for rel_path, text in files.items():
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 20}
    )
    assert indexed["published"] is True
    return str(root)


async def _callers(root: str, name: str) -> dict:
    return await CodeGraphCallersTool(root).execute(
        {"function_name": name, "include_bodies": False}
    )


def _write(root, files: dict[str, str]) -> str:
    clear_parsed()
    for rel_path, text in files.items():
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return str(root)


def _line_of(text: str, needle: str) -> int:
    return next(i for i, line in enumerate(text.split("\n"), 1) if needle in line)


def _finding(tmp_path, files: dict[str, str], rel: str, needle: str, bare: str):
    root = _write(tmp_path, files)
    line = _line_of(files[rel], needle)
    return dynamic_supertype(root, [(rel, line, "typescript")], bare)


# --- end to end ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_mixin_override_is_not_complete(tmp_path) -> None:
    root = await _index(tmp_path, {"a.ts": _PROC, "b.ts": _MIXIN})

    result = await _callers(root, "V1.getQuery")

    assert (result["caller_count"], result["completeness"]) == (0, "unknown")
    assert result["completeness_reasons"] == [DYNAMIC_SUPERTYPE_REASON]
    assert "`mix(Proc)`" in result["next_step"]
    assert "not_checked" not in result["completeness_checks"]


@pytest.mark.asyncio
async def test_mixin_static_override_is_not_complete(tmp_path) -> None:
    # ``Proc.make`` calls ``this.build()``: ``V1.make()`` dispatches to V1's static build.
    root = await _index(tmp_path, {"a.ts": _PROC, "b.ts": _MIXIN})

    result = await _callers(root, "V1.build")

    assert result["completeness"] == "unknown"
    assert result["completeness_reasons"] == [DYNAMIC_SUPERTYPE_REASON]


@pytest.mark.asyncio
async def test_listed_callers_under_a_mixin_are_incomplete(tmp_path) -> None:
    root = await _index(tmp_path, {"a.ts": _PROC, "b.ts": _MIXIN})

    result = await _callers(root, "V1.uniqueM")

    assert (result["caller_count"], result["completeness"]) == (1, "incomplete")
    assert result["completeness_reasons"] == [DYNAMIC_SUPERTYPE_REASON]


@pytest.mark.asyncio
async def test_dynamic_grandparent_blocks_the_leaf(tmp_path) -> None:
    root = await _index(tmp_path, _CHAIN)

    result = await _callers(root, "Leaf.leafOnly")

    assert result["completeness"] == "unknown"
    assert result["completeness_reasons"] == [DYNAMIC_SUPERTYPE_REASON]
    assert "class `Mid` (mid.ts:3) extends `mix(Proc)`" in result["next_step"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name", ["Plain.plainOnly", "Root.rootOnly", "Root.rootStatic"]
)
async def test_followable_chains_keep_their_answer(tmp_path, name: str) -> None:
    root = await _index(tmp_path, {"a.ts": _PROC, "b.ts": _MIXIN})

    result = await _callers(root, name)

    assert (result["completeness"], result["completeness_reasons"]) == ("complete", [])
    assert result["completeness_checks"] == {"required": 13, "checked": 13}


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["Bus.busOnly", "Pipe.pipeOnly", "Oops.oopsOnly"])
async def test_external_bases_keep_complete(tmp_path, name: str) -> None:
    root = await _index(tmp_path, _EXTERNAL)

    result = await _callers(root, name)

    assert (result["completeness"], result["completeness_reasons"]) == ("complete", [])


def test_reason_is_in_the_closed_set() -> None:
    assert DYNAMIC_SUPERTYPE_REASON in COMPLETENESS_REASONS


# --- the walk -------------------------------------------------------------


@pytest.mark.parametrize(
    ("clause", "why"),
    [
        ("mix(Base)", "a call"),
        ("(flag ? Base : Other)", "a conditional"),
        ("(Base as any)", "a cast"),
        ("Missing", "not declared or imported"),
        ("Value", "a value"),
        ("Gone", "does not resolve to one project file"),
        ("local.Base", "member of a local value"),
        ("deep.a.Base", "member path"),
        ("named.Base", "member of an imported value"),
        ("unknownNs.Base", "identifier not declared or imported"),
        ("Twice", "bound more than once"),
        ("Def", "default or module import"),
        ("Rel", "a value"),
        ("Shadow", "bound more than once"),
    ],
)
def test_unfollowable_clauses_are_named(tmp_path, clause: str, why: str) -> None:
    files = {
        "base.ts": "export class Base {}\nexport class Other {}\nexport const named = {}\n",
        "def.ts": "export default class Def {}\n",
        "c.ts": (
            "import { Base, Other, named } from './base'\n"
            "import { Gone } from './nowhere'\n"
            "import Def from './def'\n"
            "import * as deep from './base'\n"
            "const mix = (b: any) => b\n"
            "const flag = true\n"
            "const Value = mix(Base)\n"
            "const local = { Base }\n"
            "if (flag) { class Twice {} }\n"
            "class Twice {}\n"
            "const Rel = require('./base')\n"
            "class Shadow {}\n"
            "export const f = (Shadow: any) => Shadow\n"
            f"export class K extends {clause} {{\n"
            "  m() { return 1 }\n"
            "}\n"
        ),
    }

    found = _finding(tmp_path, files, "c.ts", "  m() {", "m")

    assert found is not None and not found.unchecked
    assert found.clause == clause
    assert (found.file, found.class_name) == ("c.ts", "K")
    assert why in found.why
    assert f"extends `{clause}`" in dynamic_supertype_hint("K.m", found)


@pytest.mark.parametrize(
    "clause",
    [
        "Base",
        "ns.Base",
        "Barrel",
        "Star",
        "Aliased",
        "Error",
        "pkg.Thing",
        "Pkg",
        "null",
        "Req",
        "Des",
        "Mem",
    ],
)
def test_followable_clauses_pass(tmp_path, clause: str) -> None:
    files = {
        "base.ts": "export class Base {}\n",
        "barrel.ts": "export { Base as Barrel } from './base'\n",
        "star.ts": "export * from './starred'\n",
        "starred.ts": "class Star {}\nexport { Star }\n",
        "alias.ts": "export { Base as Aliased } from './base.js'\n",
        "c.ts": (
            "import { Base } from './base'\n"
            "import * as ns from './base'\n"
            "import { Barrel } from './barrel'\n"
            "import { Star } from './star'\n"
            "import { Aliased } from './alias'\n"
            "import * as pkg from 'some-pkg'\n"
            "import Pkg from 'some-pkg'\n"
            "const Req = require('events')\n"
            "const { Des } = require('pkg')\n"
            "const Mem = require('pkg').Mem\n"
            f"export class K extends {clause} {{\n"
            "  m() { return 1 }\n"
            "}\n"
        ),
    }

    assert _finding(tmp_path, files, "c.ts", "  m() {", "m") is None


def test_dynamic_clause_behind_a_barrel_is_found(tmp_path) -> None:
    files = {
        "core.ts": "const mix = (b: any) => b\nclass P {}\nexport class Core extends mix(P) {}\n",
        "index.ts": "export * from './core'\n",
        "c.ts": "import { Core } from './index'\nexport class K extends Core {\n  m() {}\n}\n",
    }

    found = _finding(tmp_path, files, "c.ts", "  m() {}", "m")

    assert found is not None
    assert (found.file, found.class_name, found.clause) == ("core.ts", "Core", "mix(P)")


@pytest.mark.parametrize(
    ("body", "needle", "bare"),
    [
        ("  constructor() { super() }\n", "constructor", "constructor"),
        ("  m() { return 1 }\n", "  m() {", "other"),
        ("  #secret() { return 1 }\n", "#secret", "#secret"),
        ("  #secret() { return 1 }\n", "#secret", "secret"),
    ],
)
def test_constructors_and_other_names_pass(tmp_path, body, needle, bare) -> None:
    files = {
        "c.ts": (
            "const mix = (b: any) => b\nclass B {}\n"
            f"export class K extends mix(B) {{\n{body}}}\n"
        ),
    }

    assert _finding(tmp_path, files, "c.ts", needle, bare) is None


@pytest.mark.parametrize(
    ("member", "bare"),
    [
        ("  get value() { return 1 }\n", "value"),
        ("  handler = () => 1\n", "handler"),
        ("  static build() { return 1 }\n", "build"),
        ("  'quoted'() { return 1 }\n", "quoted"),
    ],
)
def test_every_overridable_member_kind_is_gated(tmp_path, member, bare) -> None:
    files = {
        "c.ts": (
            "const mix = (b: any) => b\nclass B {}\n"
            f"export class K extends mix(B) {{\n{member}}}\n"
        ),
    }

    found = _finding(tmp_path, files, "c.ts", member.strip()[:6], bare)

    assert found is not None and found.clause == "mix(B)"


def test_object_literal_methods_and_functions_pass(tmp_path) -> None:
    files = {
        "c.ts": (
            "const mix = (b: any) => b\n"
            "export const o = { m() { return 1 } }\n"
            "export function m() { return 2 }\n"
        ),
    }
    root = _write(tmp_path, files)

    assert dynamic_supertype(root, [("c.ts", 2, "typescript")], "m") is None
    assert dynamic_supertype(root, [("c.ts", 3, "typescript")], "m") is None


def test_other_language_declarations_pass(tmp_path) -> None:
    # Python rows are walked since #1883 (test_callers_python_dynamic_bases.py).
    root = _write(tmp_path, {"m.rb": "class K < mix(B)\n  def m; end\nend\n"})

    assert dynamic_supertype(root, [("m.rb", 2, "ruby")], "m") is None


def test_javascript_heritage_and_class_expressions(tmp_path) -> None:
    files = {
        "c.js": (
            "const mix = (b) => b\nclass B {}\n"
            "export const K = class extends mix(B) {\n  m() { return 1 }\n}\n"
        ),
    }

    found = _finding(tmp_path, files, "c.js", "  m() {", "m")

    assert found is not None
    assert (found.class_name, found.clause) == ("<anonymous>", "mix(B)")


def test_implements_only_passes(tmp_path) -> None:
    files = {
        "c.ts": "interface I { m(): number }\nexport class K implements I {\n  m() { return 1 }\n}\n"
    }

    assert _finding(tmp_path, files, "c.ts", "  m() {", "m") is None


def test_a_cycle_is_a_finding(tmp_path) -> None:
    files = {"c.ts": "class A extends B {}\nclass B extends A {\n  m() {}\n}\n"}

    found = _finding(tmp_path, files, "c.ts", "  m() {}", "m")

    assert found is not None and "cycle" in found.why


def test_a_long_chain_is_a_finding(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(callers_supertypes, "_CHAIN_MAX", 2)
    files = {
        "c.ts": "class A {}\nclass B extends A {}\nclass C extends B {}\nclass D extends C {\n  m() {}\n}\n"
    }

    found = _finding(tmp_path, files, "c.ts", "  m() {}", "m")

    assert found is not None and "too long" in found.why


def test_unreadable_and_broken_files_are_unchecked(tmp_path) -> None:
    root = _write(tmp_path, {"bad.ts": "export class K extends {\n  m( {\n"})

    missing = dynamic_supertype(root, [("gone.ts", 1, "typescript")], "m")
    broken = dynamic_supertype(root, [("bad.ts", 2, "typescript")], "zz")

    assert missing is not None and missing.unchecked
    assert broken is not None and broken.unchecked
    assert "could not be read" in dynamic_supertype_hint("K.m", missing)


def test_import_of_a_broken_module_is_a_finding(tmp_path) -> None:
    files = {
        "base.ts": "export class Base {\n  m( {\n",
        "c.ts": "import { Base } from './base'\nexport class K extends Base {\n  m() {}\n}\n",
    }

    found = _finding(tmp_path, files, "c.ts", "  m() {}", "m")

    assert found is not None and "could not be parsed" in found.why


def test_outcome_records_the_check(tmp_path, monkeypatch) -> None:
    scope = ("K.m", None)
    files = {
        "c.ts": "const mix = (b: any) => b\nclass B {}\nclass K extends mix(B) {\n  m() {}\n}\n"
    }
    root = _write(tmp_path, files)

    found, finding = supertype_outcome(scope, root, [("c.ts", 4, "typescript")], "m")
    clean, none = supertype_outcome(scope, root, [("c.ts", 2, "typescript")], "B")
    unread, _ = supertype_outcome(scope, root, [("gone.ts", 1, "typescript")], "m")

    def boom(*_args):
        raise RuntimeError("boom")

    monkeypatch.setattr(callers_supertypes, "dynamic_supertype", boom)
    failed, why = supertype_outcome(scope, root, [("c.ts", 4, "typescript")], "m")

    assert found == Checked(scope, (DYNAMIC_SUPERTYPE_REASON,)) and finding is not None
    assert (clean, none) == (Checked(scope), None)
    assert unread == NotChecked(DYNAMIC_SUPERTYPE_REASON)
    assert failed == NotChecked(DYNAMIC_SUPERTYPE_REASON)
    assert why is not None and "RuntimeError" in why.why


def test_a_dynamic_supertype_blocks_open_sites_enumeration() -> None:
    from tree_sitter_analyzer.mcp.tools.callers_absence import AbsenceVerdict
    from tree_sitter_analyzer.mcp.tools.callers_checks import REQUIRED_CHECKS, REVIEW

    scope = ("f", "a.ts")
    checks = tuple(
        (spec.name, Checked(scope)) for spec in REQUIRED_CHECKS if spec.layer == REVIEW
    )
    blocked = AbsenceVerdict(
        "unknown",
        checks=(
            *checks[:-1],
            ("supertype_dispatch", Checked(scope, (DYNAMIC_SUPERTYPE_REASON,))),
        ),
    )
    result = {
        "name_only_sites": [{"file": "u.ts", "line": 2}],
        "name_only_sites_total": 1,
    }

    bound, _ = open_sites(
        result, ["NAME_ONLY_INBOUND"], name_only_exact=True, review=lambda: blocked
    )

    assert bound["enumerated"] is False
