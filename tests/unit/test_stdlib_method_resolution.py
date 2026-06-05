"""RFC-0004 RED-first: stdlib/builtin method names classify as stdlib, not unknown.

The cascade's final tier classifies a bare method name that survives every
project-binding rule (write_text, strip, items, …) as ``stdlib`` — but ONLY when
the project defines no method of that name (shadowing preserved; ambiguous
project names stay ``unknown``).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from tree_sitter_analyzer.ast_cache import ASTCache


def _index(tmp_path: Path, files: dict[str, str]) -> Path:
    proj = tmp_path / "pkg"
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "__init__.py").write_text("# pkg\n")
    for name, body in files.items():
        (proj / name).write_text(body)
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project()
    finally:
        cache.close()
    return tmp_path


def _resolution_for(db_path: str, callee_name: str) -> list[str]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT callee_resolution FROM edges "
            "WHERE kind = 'calls' AND callee_name = ?",
            (callee_name,),
        ).fetchall()
        return [r["callee_resolution"] for r in rows]
    finally:
        conn.close()


def test_stdlib_method_name_classifies_as_stdlib(tmp_path: Path) -> None:
    """``p.write_text(...)`` with no project ``write_text`` → stdlib, not unknown."""
    _index(
        tmp_path,
        {
            "a.py": (
                "from pathlib import Path\n\n"
                "def caller(p):\n"
                "    p.write_text('x')\n"
                "    'hello'.strip()\n"
            )
        },
    )
    db = str(tmp_path / "pkg" / ".ast-cache" / "index.db")
    # ASTCache stores its db under project_root/.ast-cache
    db = str(tmp_path / ".ast-cache" / "index.db")

    assert "stdlib" in _resolution_for(db, "write_text"), (
        "write_text must classify as stdlib (RFC-0004 final tier)"
    )
    assert "unknown" not in _resolution_for(db, "write_text")
    assert "stdlib" in _resolution_for(db, "strip")


def test_project_method_shadows_stdlib_name(tmp_path: Path) -> None:
    """A project class defining ``split`` → ``split()`` resolves to project,
    never stdlib (shadowing preserved)."""
    _index(
        tmp_path,
        {
            "svc.py": (
                "class Splitter:\n"
                "    def split(self):\n"
                "        return 1\n\n"
                "def caller():\n"
                "    s = Splitter()\n"
                "    s.split()\n"
            )
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")
    res = _resolution_for(db, "split")
    assert res, "expected a split() edge"
    assert "stdlib" not in res, (
        f"project-defined split must NOT be classified stdlib; got {res}"
    )


def test_ambiguous_project_method_stays_unknown(tmp_path: Path) -> None:
    """Two classes define ``get`` → an unqualifiable ``get()`` stays unknown,
    never falsely claimed stdlib."""
    _index(
        tmp_path,
        {
            "m.py": (
                "class A:\n"
                "    def get(self):\n"
                "        return 1\n\n"
                "class B:\n"
                "    def get(self):\n"
                "        return 2\n\n"
                "def caller(obj):\n"
                "    obj.get()\n"
            )
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")
    res = _resolution_for(db, "get")
    assert res, "expected a get() edge"
    # The project owns the name (ambiguously) — must not be mislabeled stdlib.
    assert "stdlib" not in res, (
        f"ambiguous project method get must stay unknown, not stdlib; got {res}"
    )


def test_cross_language_symbol_does_not_suppress_stdlib(tmp_path: Path) -> None:
    """Codex P2 #319: a JS file defining ``split`` must NOT make a Python
    ``'x'.split()`` resolve to unknown — Python stdlib classification stands."""
    _index(
        tmp_path,
        {
            "py_caller.py": ("def caller():\n    'hello'.split(',')\n"),
            "js_owner.js": ("function split() { return 1; }\n"),
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")
    res = _resolution_for(db, "split")
    # The Python call must be stdlib despite the JS symbol of the same name.
    assert "stdlib" in res, (
        f"cross-language JS split must not suppress Python stdlib; got {res}"
    )


def test_lazy_context_construction_fires_stdlib_method(tmp_path: Path) -> None:
    """Codex P2 #319: the public lazy form ResolverContext(project_root=, cache=)
    must populate stdlib_methods (not the constructor default {}), so RFC-0004
    classification works for direct API users, not only the hot index path."""
    _index(tmp_path, {"a.py": ("def caller(p):\n    p.write_text('x')\n")})

    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.synapse_resolver import ResolverContext

    cache = ASTCache(str(tmp_path))
    try:
        ctx = ResolverContext(project_root=str(tmp_path), cache=cache)
        # Touching the property triggers the lazy load; it must carry the table.
        assert "write_text" in ctx.stdlib_methods.get("python", frozenset()), (
            "lazy ResolverContext must populate stdlib_methods (Codex P2 #319)"
        )
    finally:
        cache.close()


def test_genuinely_unknown_name_stays_unknown(tmp_path: Path) -> None:
    """A name that is neither project nor stdlib stays unknown."""
    _index(
        tmp_path,
        {"u.py": ("def caller(x):\n    x.frobnicate_xyz()\n")},
    )
    db = str(tmp_path / ".ast-cache" / "index.db")
    res = _resolution_for(db, "frobnicate_xyz")
    assert res, "expected a frobnicate_xyz() edge"
    assert set(res) == {"unknown"}, f"expected unknown, got {res}"
