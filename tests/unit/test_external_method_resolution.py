"""RFC-0005 RED-first: external library method names classify as external, not unknown.

The cascade's new ``_try_external_method`` tier (placed after ``_try_stdlib_method``)
classifies bare method names dominated by test-framework calls (pytest, hypothesis,
unittest.mock) as ``external`` — but ONLY when the project defines no compatible-
language method of that name.

Guards:
  - shadowing: a project method of the same name wins → ``project``, not ``external``
  - ambiguous project name stays ``unknown``, not ``external``
  - cross-language JS symbol of the same name does NOT suppress classification
  - the public lazy ResolverContext(project_root=, cache=) must populate
    external_methods (the _ensure_loaded copy-back — Codex P2 bug pattern)
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


def test_mock_method_classifies_as_external(tmp_path: Path) -> None:
    """``obj.assert_called_once_with(...)`` with no project def → not unknown.

    Uses a function argument (``mock_arg``) as the receiver so the AST extractor
    cannot type-infer its class — the qualifier stays as the variable name rather
    than being rewritten to ``MagicMock``, which would trigger ``_try_stdlib``
    (since ``MagicMock`` is imported from stdlib ``unittest.mock``).

    With no type inference, only ``_try_external_method`` (RFC-0005) can classify
    ``assert_called_once_with`` as something other than ``unknown``.
    """
    _index(
        tmp_path,
        {
            "test_a.py": (
                "def test_something(mock_arg):\n"
                "    mock_arg.assert_called_once_with('x')\n"
            )
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")

    res = _resolution_for(db, "assert_called_once_with")
    assert res, "expected an assert_called_once_with() edge"
    assert "external" in res, (
        "assert_called_once_with must classify as external (RFC-0005 final tier); "
        f"got {res}"
    )
    assert "unknown" not in res, (
        f"assert_called_once_with must not be unknown after RFC-0005; got {res}"
    )


def test_pytest_raises_classifies_as_external(tmp_path: Path) -> None:
    """``pytest.raises(...)`` bare name → external, not unknown."""
    _index(
        tmp_path,
        {
            "test_b.py": (
                "import pytest\n\n"
                "def test_err():\n"
                "    with pytest.raises(ValueError):\n"
                "        raise ValueError\n"
            )
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")
    res = _resolution_for(db, "raises")
    assert res, "expected a raises() edge"
    assert "external" in res, f"raises must classify as external (pytest); got {res}"


def test_project_method_shadows_external_name(tmp_path: Path) -> None:
    """A project class defining ``assert_called_once`` wins over the external table.

    The project-ownership gate must prevent mis-labeling a project method as
    ``external`` just because the name appears in the external table.
    """
    _index(
        tmp_path,
        {
            "verifier.py": (
                "class CallVerifier:\n"
                "    def assert_called_once(self):\n"
                "        return True\n\n"
                "def check(v):\n"
                "    v.assert_called_once()\n"
            )
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")
    res = _resolution_for(db, "assert_called_once")
    assert res, "expected an assert_called_once() edge"
    assert "external" not in res, (
        f"project-defined assert_called_once must NOT be classified external; got {res}"
    )


def test_ambiguous_project_method_stays_unknown_not_external(tmp_path: Path) -> None:
    """Two project classes define a name that also appears in the external table.

    The project owns the name (ambiguously) — the cascade must NOT jump to
    ``external`` even though the name is in the table.
    """
    _index(
        tmp_path,
        {
            "m.py": (
                "class A:\n"
                "    def assert_called_once(self):\n"
                "        return True\n\n"
                "class B:\n"
                "    def assert_called_once(self):\n"
                "        return True\n\n"
                "def caller(obj):\n"
                "    obj.assert_called_once()\n"
            )
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")
    res = _resolution_for(db, "assert_called_once")
    assert res, "expected an assert_called_once() edge"
    # Project owns name ambiguously — must stay unknown, not be claimed external.
    assert "external" not in res, (
        f"ambiguous project assert_called_once must stay unknown, not external; got {res}"
    )


def test_cross_language_js_symbol_does_not_suppress_external(tmp_path: Path) -> None:
    """A JS file defining ``readouterr`` must NOT make a Python pytest-capfd call
    resolve to unknown — external classification stands.

    Language-aware gate: only a compatible-language project symbol suppresses.
    ``readouterr`` is a pytest capsys/capfd fixture method — purely third-party.
    The Python file has no stdlib import that would trigger ``_try_stdlib``, so
    the only classification path is ``_try_external_method``.
    """
    _index(
        tmp_path,
        {
            "test_cap.py": (
                "def test_output(capsys):\n"
                "    print('hello')\n"
                "    captured = capsys.readouterr()\n"
                "    assert captured.out == 'hello\\n'\n"
            ),
            "utils.js": ("function readouterr() { return {out: '', err: ''}; }\n"),
        },
    )
    db = str(tmp_path / ".ast-cache" / "index.db")
    res = _resolution_for(db, "readouterr")
    # The Python call must be external despite the JS symbol of the same name.
    assert "external" in res, (
        f"cross-language JS readouterr must not suppress Python external; got {res}"
    )


def test_lazy_context_construction_populates_external_methods(tmp_path: Path) -> None:
    """The public lazy ResolverContext(project_root=, cache=) must populate
    external_methods via _ensure_loaded copy-back.

    This guards against the Codex P2 bug pattern from RFC-0004 where the lazy
    public API path silently returned {} for the methods table.
    """
    _index(
        tmp_path,
        {
            "test_a.py": (
                "from unittest.mock import MagicMock\n\n"
                "def test_x():\n"
                "    m = MagicMock()\n"
                "    m.assert_called_once_with('x')\n"
            )
        },
    )

    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.synapse_resolver import ResolverContext

    cache = ASTCache(str(tmp_path))
    try:
        ctx = ResolverContext(project_root=str(tmp_path), cache=cache)
        # Touching the property triggers the lazy load; it must carry the table.
        ext = ctx.external_methods.get("python", frozenset())
        assert "assert_called_once_with" in ext, (
            "lazy ResolverContext must populate external_methods via _ensure_loaded "
            "(Codex P2 copy-back pattern)"
        )
        assert "raises" in ext, "raises (pytest) must be in the external_methods table"
    finally:
        cache.close()
