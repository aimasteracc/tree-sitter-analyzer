"""Swift per-language callee resolver + extraction activation (RFC-0010 wave 3).

Includes the poetic moat case: the exact Python-sorted()->Swift-func-sorted
mis-wire that CodeGraph produces must NOT happen here, in either direction.
"""

from __future__ import annotations

import os
import shutil
import tempfile

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.function_extraction import _CALL_NODE_TYPES, _FUNC_DEF_TYPES
from tree_sitter_analyzer.synapse_resolver._registry import (
    get_language_resolver,
    registered_languages,
)
from tree_sitter_analyzer.synapse_resolver.languages.swift import (
    SwiftResolverContext,
    resolve_swift_callee,
)


def _ctx(file_symbols=None, file_languages=None, global_name_table=None):
    return SwiftResolverContext(
        file_symbols=file_symbols or {},
        file_languages=file_languages or {},
        global_name_table=global_name_table or {},
    )


def test_swift_registered_and_wired() -> None:
    assert "swift" in registered_languages()
    assert get_language_resolver("swift") is not None
    assert _CALL_NODE_TYPES.get("swift") == {"call_expression"}
    assert "function_declaration" in _FUNC_DEF_TYPES["swift"]


def test_bare_local_call_resolves() -> None:
    ctx = _ctx(file_symbols={"a.swift": [("greet", "function", 7)]})
    assert resolve_swift_callee("greet", "greet", "a.swift", ctx) == (
        7,
        "local",
        "a.swift",
    )


def test_self_method_unique_binds_ambiguous_unknown() -> None:
    ctx = _ctx(file_symbols={"a.swift": [("m", "method", 3)]})
    assert resolve_swift_callee("m", "self.m", "a.swift", ctx) == (
        3,
        "local",
        "a.swift",
    )
    # two same-named methods -> ambiguous -> unknown
    ctx2 = _ctx(file_symbols={"a.swift": [("m", "method", 3), ("m", "method", 9)]})
    assert resolve_swift_callee("m", "self.m", "a.swift", ctx2) == (None, "unknown", "")
    # self.X where X is only a free function -> not a member -> unknown
    ctx3 = _ctx(file_symbols={"a.swift": [("m", "function", 3)]})
    assert resolve_swift_callee("m", "self.m", "a.swift", ctx3) == (None, "unknown", "")


def test_stdlib_global_classified_but_shadow_wins() -> None:
    assert resolve_swift_callee("print", "print", "a.swift", _ctx()) == (
        None,
        "stdlib",
        "",
    )
    # a project Swift `print` suppresses the stdlib tier
    ctx = _ctx(
        global_name_table={"print": [("b.swift", 5)]},
        file_languages={"b.swift": "swift"},
    )
    assert resolve_swift_callee("print", "print", "a.swift", ctx) == (
        None,
        "unknown",
        "",
    )


def test_moat_python_owner_never_suppresses_or_binds() -> None:
    # a Python `print` must NOT count as a Swift owner (stdlib stays classified)
    ctx = _ctx(
        global_name_table={"print": [("p.py", 5)]},
        file_languages={"p.py": "python"},
    )
    assert resolve_swift_callee("print", "print", "a.swift", ctx) == (
        None,
        "stdlib",
        "",
    )


def test_poetic_moat_end_to_end() -> None:
    """Index a Swift file defining `sorted` + a Python file calling sorted();
    neither binds across the language boundary (the CodeGraph failure)."""
    d = tempfile.mkdtemp()
    try:
        with open(os.path.join(d, "s.swift"), "w") as f:
            f.write(
                "func sorted(_ a: [Int]) -> [Int] { return a }\n"
                "func run() { let x = sorted([3,1]); print(x) }\n"
            )
        with open(os.path.join(d, "p.py"), "w") as f:
            f.write("def use():\n    return sorted([3,1])\n")
        cache = ASTCache(d)
        cache.index_project()
        conn = cache.get_conn()
        rows = conn.execute(
            "SELECT language, callee_name, callee_resolved_file "
            "FROM edges WHERE kind='calls' AND callee_name='sorted'"
        ).fetchall()
        assert rows, "no sorted() edges"
        for r in rows:
            # a swift caller must not resolve into a .py file and vice-versa
            if r["language"] == "swift":
                assert not str(r["callee_resolved_file"]).endswith(".py")
            if r["language"] == "python":
                assert not str(r["callee_resolved_file"]).endswith(".swift")
        # Discriminating: Swift print() must classify 'stdlib' via resolve_swift_callee.
        # The Python cascade would instead call it 'builtin' (print is in BUILTINS_PY),
        # so this assertion fails if the Swift resolver is not actually invoked.
        prints = conn.execute(
            "SELECT callee_resolution FROM edges "
            "WHERE kind='calls' AND language='swift' AND callee_name='print'"
        ).fetchall()
        assert prints, "no swift print() edge"
        assert all(r["callee_resolution"] == "stdlib" for r in prints)
        cache.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)
