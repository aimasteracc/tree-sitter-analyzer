"""RFC-0007 RED-first: qualified builtin calls (monkeypatch.setattr, obj.getattr, …)
classify as ``builtin``, not ``unknown``.

The cascade's new ``_try_builtin_method`` tier (placed AFTER ``_try_external_method``)
classifies bare Python builtin names that appear with a qualifier as ``builtin``
— but ONLY when the project defines no compatible-language method of that name.

Guards tested:
  1. monkeypatch.setattr(...)  → builtin  (the primary 688-edge gap)
  2. Project method named setattr → project (shadowing preserved)
  3. Ambiguous project method setattr (two classes) → unknown, not builtin
  4. Cross-language JS symbol of same name does NOT suppress classification
  5. Public lazy ResolverContext(project_root=, cache=) populates builtin_methods
     (the _ensure_loaded copy-back — Codex P2 bug pattern)
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


def test_monkeypatch_setattr_classifies_as_builtin(tmp_path: Path) -> None:
    """``monkeypatch.setattr(obj, 'attr', val)`` with no project def → builtin.

    This is the primary 688-edge gap: ``setattr`` is in BUILTINS_PY but
    ``_try_builtin`` requires no qualifier. With a qualifier, it falls through
    to ``unknown``. ``_try_builtin_method`` (RFC-0007) must catch it as builtin.

    RED before RFC-0007: this resolves to ``unknown``.
    """
    _index(
        tmp_path,
        {
            "test_patch.py": (
                "def test_something(monkeypatch):\n"
                "    monkeypatch.setattr(object, 'attr', 42)\n"
            )
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")

    res = _resolution_for(db, "setattr")
    assert res, "expected a setattr() edge"
    assert "builtin" in res, (
        f"monkeypatch.setattr must classify as builtin (RFC-0007 final tier); got {res}"
    )
    assert "unknown" not in res, (
        f"monkeypatch.setattr must not be unknown after RFC-0007; got {res}"
    )


def test_getattr_with_qualifier_classifies_as_builtin(tmp_path: Path) -> None:
    """``obj.getattr(...)`` with no project def → builtin.

    getattr, hasattr, delattr all belong in BUILTIN_QUALIFIED_PY.
    """
    _index(
        tmp_path,
        {
            "accessor.py": (
                "def get_value(obj, name):\n    return obj.getattr(name, None)\n"
            )
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")

    res = _resolution_for(db, "getattr")
    assert res, "expected a getattr() edge"
    assert "builtin" in res, (
        f"obj.getattr must classify as builtin (RFC-0007); got {res}"
    )


def test_project_method_named_setattr_shadows_builtin(tmp_path: Path) -> None:
    """A project class defining ``setattr`` wins over the builtin_method table.

    The project-ownership gate must prevent mis-labeling a project method as
    ``builtin`` just because ``setattr`` appears in BUILTIN_QUALIFIED_PY.
    """
    _index(
        tmp_path,
        {
            "patcher.py": (
                "class Patcher:\n"
                "    def setattr(self, obj, attr, val):\n"
                "        pass\n\n"
                "def patch(p):\n"
                "    p.setattr(object, 'x', 1)\n"
            )
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")

    res = _resolution_for(db, "setattr")
    assert res, "expected setattr() edges"
    # The qualified call p.setattr(...) must NOT be classified builtin;
    # the project class owns that name.
    assert "builtin" not in res, (
        f"project-defined setattr must NOT be classified builtin; got {res}"
    )


def test_ambiguous_project_setattr_stays_unknown_not_builtin(tmp_path: Path) -> None:
    """Two project classes define ``setattr`` — ambiguous; stays unknown, not builtin.

    The project-ownership gate fires on any compatible-language match, so an
    ambiguous project name must stay ``unknown`` rather than be claimed ``builtin``.
    """
    _index(
        tmp_path,
        {
            "m.py": (
                "class A:\n"
                "    def setattr(self, obj, name, val):\n"
                "        pass\n\n"
                "class B:\n"
                "    def setattr(self, obj, name, val):\n"
                "        pass\n\n"
                "def caller(obj):\n"
                "    obj.setattr(object, 'x', 1)\n"
            )
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")

    res = _resolution_for(db, "setattr")
    assert res, "expected setattr() edges"
    # Project owns name ambiguously — must NOT be claimed builtin.
    assert "builtin" not in res, (
        f"ambiguous project setattr must stay unknown, not builtin; got {res}"
    )


def test_cross_language_js_symbol_does_not_suppress_builtin_method(
    tmp_path: Path,
) -> None:
    """A JS file defining ``setattr`` must NOT make a Python monkeypatch.setattr
    call resolve to unknown — builtin classification stands.

    Language-aware gate: only a compatible-language project symbol suppresses.
    ``setattr`` is a Python builtin; a JS function of the same name is irrelevant
    to the Python resolution.
    """
    _index(
        tmp_path,
        {
            "test_p.py": (
                "def test_something(monkeypatch):\n"
                "    monkeypatch.setattr(object, 'x', 1)\n"
            ),
            "utils.js": ("function setattr(obj, name, val) { obj[name] = val; }\n"),
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")

    res = _resolution_for(db, "setattr")
    # The Python qualified call must be builtin despite the JS symbol of the same name.
    assert "builtin" in res, (
        f"cross-language JS setattr must not suppress Python builtin; got {res}"
    )


def test_lazy_context_construction_populates_builtin_methods(tmp_path: Path) -> None:
    """The public lazy ResolverContext(project_root=, cache=) must populate
    builtin_methods via _ensure_loaded copy-back.

    Guards against the Codex P2 bug pattern from RFC-0004/0005 where the lazy
    public API path silently returned {} for the methods table, making the
    classification tier a no-op for direct API users.
    """
    _index(
        tmp_path,
        {
            "test_a.py": (
                "def test_something(monkeypatch):\n"
                "    monkeypatch.setattr(object, 'attr', 42)\n"
            )
        },
    )

    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.synapse_resolver import ResolverContext

    cache = ASTCache(str(tmp_path))
    try:
        ctx = ResolverContext(project_root=str(tmp_path), cache=cache)
        # Touching the property triggers the lazy load; it must carry the table.
        bm = ctx.builtin_methods.get("python", frozenset())
        assert "setattr" in bm, (
            "lazy ResolverContext must populate builtin_methods via _ensure_loaded "
            "(Codex P2 copy-back pattern)"
        )
        assert "getattr" in bm, "getattr must be in the builtin_methods table"
        assert "hasattr" in bm, "hasattr must be in the builtin_methods table"
        assert "delattr" in bm, "delattr must be in the builtin_methods table"
    finally:
        cache.close()
