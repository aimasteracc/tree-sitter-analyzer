"""RED-first tests for the Mis-Wire Audit (the run-on-your-repo correctness demo).

The audit models what a name-only resolver WOULD mis-wire (bind a call to a
same-named definition in another language) and contrasts it with what TSA
actually resolves. The cross-language MOAT means TSA's count must stay ~0.
"""

from __future__ import annotations

import os
import shutil
import tempfile

from tree_sitter_analyzer.miswire_audit import audit, render_card, render_terminal


def _planted_polyglot() -> str:
    """A tiny repo with a same-name collision: a Python `sorted()` caller and a
    Swift `func sorted` — the exact CodeGraph flagship mis-wire."""
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "app.py"), "w") as f:
        f.write("def use():\n    return sorted([3, 1, 2])\n")
    with open(os.path.join(d, "lib.swift"), "w") as f:
        f.write("func sorted(_ a: [Int]) -> [Int] { return a }\n")
    return d


def test_audit_flags_name_only_miswire_but_tsa_does_not() -> None:
    d = _planted_polyglot()
    try:
        r = audit(d, reindex=True)
        # a name-only resolver would wire Python sorted() -> the Swift func sorted
        assert r.naive_miswires >= 1, r
        assert any(
            o.callee_name == "sorted" and o.callee_lang == "swift"
            for o in r.naive_offenders
        ), r.naive_offenders
        # TSA refuses that cross-language bind — Python sorted() stays builtin
        assert r.tsa_miswires == 0, r
        # the headline multiplier is meaningful
        assert r.multiplier >= 1
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_audit_clean_repo_reports_zero_for_both() -> None:
    """A single-language repo with no cross-language collisions -> 0 and 0."""
    d = tempfile.mkdtemp()
    try:
        with open(os.path.join(d, "a.py"), "w") as f:
            f.write("def helper():\n    return 1\ndef run():\n    return helper()\n")
        r = audit(d, reindex=True)
        assert r.tsa_miswires == 0
        # helper() resolves locally; no foreign same-name def exists
        assert r.naive_miswires == 0
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_render_terminal_and_card_are_honest() -> None:
    """The output must NOT claim the name-only number is CodeGraph's exact count
    (it is the worst-case for the name-only design); it must point to the live
    head-to-head for the CodeGraph-specific figure."""
    d = _planted_polyglot()
    try:
        r = audit(d, reindex=True)
        term = render_terminal(r)
        card = render_card(r)
        assert "NAME-ONLY resolver" in term
        assert "REPORT-v1.21.0.md" in term  # honest pointer to the live comparison
        assert "name-only resolver" in card.lower()
        # never label the modeled number as CodeGraph's measured count
        assert "CodeGraph would mis-wire" not in term
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_symbols_json_fallback_when_no_ast_symbol_rows() -> None:
    """Codex #369 L74: on no-FTS5 builds ast_symbol_rows is absent; the audit
    must fall back to ast_index.symbols_json and still find the collision."""
    from tree_sitter_analyzer.miswire_audit import _iter_symbol_defs

    d = _planted_polyglot()
    try:
        from tree_sitter_analyzer.ast_cache import ASTCache

        cache = ASTCache(d)
        cache.index_project()
        conn = cache.get_conn()
        # simulate a no-FTS5 build: drop the table the primary path uses
        conn.execute("DROP TABLE IF EXISTS ast_symbol_rows")
        defs = _iter_symbol_defs(conn)
        names = {n for n, _f, _l in defs}
        # the Swift `sorted` def must still be discoverable via symbols_json
        assert "sorted" in names, names
        assert any(lang == "swift" for _n, _f, lang in defs)
        cache.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_no_fts5_renders_clear_unavailable_message_not_misleading_zero() -> None:
    """Codex #369 L158: on no-FTS5 builds TSA writes no call edges; the audit must
    say so plainly, NOT print a misleading '0 mis-wires / 0× cleaner' verdict."""
    from tree_sitter_analyzer.miswire_audit import AuditResult, render_terminal

    r = AuditResult(project_root=".", call_edges_available=False)
    out = render_terminal(r)
    assert "FTS5" in out
    assert "cleaner" not in out  # no misleading verdict when there is no data


def test_genuine_collisions_exclude_builtins() -> None:
    """RFC-0011 open Q1 (skeptic-resistance): the GENUINE count excludes the
    caller language's own builtins. A Python `compute()` (not a builtin) bound to
    a Swift `compute` IS genuine; a Python `sorted()` (a builtin) is worst-case
    only — a skeptic can't dismiss the genuine examples as 'obviously a builtin'."""
    import os
    import shutil
    import tempfile

    from tree_sitter_analyzer.miswire_audit import audit, render_terminal

    d = tempfile.mkdtemp()
    try:
        with open(os.path.join(d, "app.py"), "w") as f:
            # `compute` is NOT a Python builtin (genuine); `sorted` IS (worst-case only)
            f.write("def use():\n    compute()\n    return sorted([1])\n")
        with open(os.path.join(d, "lib.swift"), "w") as f:
            f.write(
                "func compute() -> Int { return 1 }\n"
                "func sorted(_ a: [Int]) -> [Int] { return a }\n"
            )
        r = audit(d, reindex=True)
        assert r.naive_genuine_miswires >= 1
        assert any(o.callee_name == "compute" for o in r.genuine_offenders)
        # `sorted` is a Python builtin -> never a GENUINE offender
        assert not any(o.callee_name == "sorted" for o in r.genuine_offenders)
        # but it still counts in the worst-case total
        assert r.naive_miswires > r.naive_genuine_miswires
        out = render_terminal(r)
        assert "GENUINE" in out
        assert r.tsa_miswires == 0
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_js_builtins_excluded_from_genuine() -> None:
    """Codex #377 P2: a language WITHOUT a builtin set would count its own
    builtins (JS Map/Promise) as genuine. All 15 languages now have a set, so a
    JS `Map()` is excluded while a genuine name (`tokenize`) is kept."""
    from tree_sitter_analyzer.miswire_audit import _CALLER_BUILTINS

    for lang in ("javascript", "typescript", "java", "go", "kotlin", "csharp",
                 "swift", "c", "cpp", "python", "ruby", "php", "rust"):
        assert _CALLER_BUILTINS.get(lang), f"{lang} has no builtin set"
    assert "Map" in _CALLER_BUILTINS["javascript"]
    assert "Promise" in _CALLER_BUILTINS["javascript"]
    assert "tokenize" not in _CALLER_BUILTINS["javascript"]
