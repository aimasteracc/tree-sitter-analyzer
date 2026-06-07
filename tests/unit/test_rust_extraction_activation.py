"""RFC-0010 activation: Rust call-edge extraction wired into function_extraction.

The Rust per-language resolver (languages/rust.py, #349) was dormant — no Rust
call edges were extracted, so it never ran. This wires Rust into
``_CALL_NODE_TYPES`` / ``_FUNC_DEF_TYPES`` so the resolver activates. The moat
(no cross-language binding) must hold on the now-extracted edges.
"""

from __future__ import annotations

import os
import shutil
import tempfile

from tree_sitter import Parser

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.function_extraction import (
    _CALL_NODE_TYPES,
    _FUNC_DEF_TYPES,
    walk_tree,
)
from tree_sitter_analyzer.language_loader import load_language

_RUST_SRC = """
fn helper() -> i32 { 42 }

fn run() -> String {
    let x = helper();
    let s = "hi".to_string();
    println!("{}", x);
    format!("{}", s)
}
"""


def test_rust_is_wired_into_call_and_def_extraction() -> None:
    assert "call_expression" in _CALL_NODE_TYPES["rust"]
    assert "macro_invocation" in _CALL_NODE_TYPES["rust"]
    assert "function_item" in _FUNC_DEF_TYPES["rust"]


def test_walk_tree_extracts_rust_calls_and_defs() -> None:
    lang = load_language("rust")
    parser = Parser(lang)
    tree = parser.parse(_RUST_SRC.encode())
    defs, calls = walk_tree(tree.root_node, _RUST_SRC, "rust")
    def_names = {d.get("name") for d in defs}
    call_names = {c.get("name") for c in calls}
    assert {"helper", "run"} <= def_names
    # function call, method call (receiver), and a macro must all be captured
    assert "helper" in call_names
    assert "to_string" in call_names  # method call via field_expression
    assert "println" in call_names or "format" in call_names  # macro_invocation


def test_rust_local_call_resolves_and_moat_holds() -> None:
    """A real index: the same-file `helper()` call resolves local; a Rust call
    whose name also exists in a Python file is NEVER bound to the .py file."""
    d = tempfile.mkdtemp()
    try:
        with open(os.path.join(d, "m.rs"), "w") as f:
            f.write(_RUST_SRC)
        # Python shadow defining the same names the Rust file calls.
        with open(os.path.join(d, "shadow.py"), "w") as f:
            f.write("def helper():\n    return 0\ndef to_string():\n    return ''\n")
        cache = ASTCache(d)
        cache.index_project()
        conn = cache.get_conn()
        rows = conn.execute(
            "SELECT callee_name, callee_resolution, callee_resolved_file "
            "FROM edges WHERE kind='calls' AND language='rust'"
        ).fetchall()
        assert rows, "no Rust call edges were extracted"
        # MOAT: no Rust edge may resolve into a Python file.
        cross = [r for r in rows if str(r["callee_resolved_file"]).endswith(".py")]
        assert not cross, f"cross-language mis-wire: {cross}"
        # The same-file helper() call must resolve local (not unknown).
        helper_edges = [r for r in rows if r["callee_name"] == "helper"]
        assert any(r["callee_resolution"] == "local" for r in helper_edges)
        cache.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)
