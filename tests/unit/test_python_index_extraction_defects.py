"""Regression tests for four Python index-extraction defects.

Found by dogfooding the project index against a stdlib-``ast`` ground truth
over all 1930 Python files in this repo:

* BUG-1 ``from __future__ import X`` produced no ``import`` symbol at all
  (787 occurrences repo-wide) because tree-sitter emits a dedicated
  ``future_import_statement`` node type that ``_IMPORT_LIKE`` did not list.
* BUG-2 a function nested inside a *method* was classified ``method`` and
  attributed to the enclosing class (334 symbols, plus 226 bogus
  ``contains`` edges) because ``_find_parent_class`` walked past the
  intervening ``function_definition``.
* BUG-3 ``ast_imports.line`` was 0 for every one of the 16171 rows because
  the INSERT omitted the column even though ``ImportEntry.line`` was set.
* BUG-4 a parenthesised multi-line ``from X import (...)`` carrying a
  trailing comment lost every bound name (105 occurrences) because the
  DOTALL regex let ``split("#", 1)[0]`` truncate the body.
"""

from __future__ import annotations

import sqlite3

import pytest
import tree_sitter_python
from tree_sitter import Language, Parser

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.cache.extraction import _extract_symbols
from tree_sitter_analyzer.synapse_resolver import parse_imports

_PY_PARSER = Parser(Language(tree_sitter_python.language()))


def _payload(source: str) -> dict:
    tree = _PY_PARSER.parse(source.encode("utf-8"))
    return _extract_symbols(tree, source, "python")


def _symbols(source: str) -> list[dict]:
    return _payload(source)["symbols"]


def _by_kind(symbols: list[dict], kind: str) -> list[dict]:
    return [s for s in symbols if s.get("kind") == kind]


# ---------------------------------------------------------------------------
# BUG-1: future_import_statement
# ---------------------------------------------------------------------------


def test_future_import_is_extracted_as_import_symbol() -> None:
    """``from __future__ import annotations`` must yield an import symbol."""
    symbols = _symbols("from __future__ import annotations\nimport os\n")
    texts = [s.get("text", "") for s in _by_kind(symbols, "import")]

    assert any("__future__" in t for t in texts), (
        f"future import missing from extracted symbols: {texts}"
    )
    assert len(texts) == 2, f"expected 2 import symbols, got {texts}"


def test_future_import_reaches_imports_json() -> None:
    """The future import must also land in the imports_json projection."""
    payload = _payload("from __future__ import annotations\n")
    imports = [s for s in payload["symbols"] if s.get("kind") == "import"]
    assert imports, "imports_json projection lost the future import"
    assert imports[0]["line"] == 1


# ---------------------------------------------------------------------------
# BUG-2: nested function inside a method
# ---------------------------------------------------------------------------


NESTED_SRC = """\
class Widget:
    def method_a(self):
        def inner_helper():
            return 1
        return inner_helper

    async def method_b(self):
        async def inner_async():
            return 2
        return inner_async


def module_level():
    def nested_in_function():
        return 3
    return nested_in_function
"""


def test_function_nested_in_method_is_not_a_method() -> None:
    """A def inside a method body is a plain function, not a class member."""
    symbols = _symbols(NESTED_SRC)
    by_name = {s["name"]: s for s in symbols if "name" in s}

    for nested in ("inner_helper", "inner_async"):
        sym = by_name[nested]
        assert sym["kind"] == "function", (
            f"{nested} should be a function, got kind={sym['kind']!r} "
            f"class={sym.get('class')!r}"
        )
        assert "class" not in sym, (
            f"{nested} must not be attributed to a class, got {sym.get('class')!r}"
        )


def test_real_methods_are_still_methods() -> None:
    """The fix must not regress genuine class members."""
    symbols = _symbols(NESTED_SRC)
    by_name = {s["name"]: s for s in symbols if "name" in s}

    for method in ("method_a", "method_b"):
        assert by_name[method]["kind"] == "method"
        assert by_name[method]["class"] == "Widget"


def test_function_nested_in_function_stays_a_function() -> None:
    """Control case that already passed — guard against over-correction."""
    symbols = _symbols(NESTED_SRC)
    by_name = {s["name"]: s for s in symbols if "name" in s}

    assert by_name["module_level"]["kind"] == "function"
    assert by_name["nested_in_function"]["kind"] == "function"


def test_class_nested_in_method_still_resolves_its_own_members() -> None:
    """A class defined inside a method still owns its methods."""
    src = """\
class Outer:
    def build(self):
        class Inner:
            def inner_method(self):
                return 1
        return Inner
"""
    symbols = _symbols(src)
    by_name = {s["name"]: s for s in symbols if "name" in s}

    assert by_name["inner_method"]["kind"] == "method"
    assert by_name["inner_method"]["class"] == "Inner"
    assert by_name["build"]["kind"] == "method"
    assert by_name["build"]["class"] == "Outer"


# ---------------------------------------------------------------------------
# BUG-4: parenthesised multi-line import with a trailing comment
# ---------------------------------------------------------------------------


def test_multiline_import_with_trailing_comment_keeps_all_names() -> None:
    """A trailing ``# noqa`` must not swallow the imported names."""
    text = "from typing import (  # noqa: F401\n    Any,\n    Dict,\n)"
    entries = parse_imports(text, "python", "sample.py", 4)

    names = sorted(e.local_name for e in entries)
    assert names == ["Any", "Dict"], f"expected Any/Dict, got {names}"
    assert all(e.module_path == "typing" for e in entries)


def test_multiline_import_without_comment_still_works() -> None:
    """Control case for the comment-stripping change."""
    text = "from typing import (\n    Any,\n    Dict,\n)"
    entries = parse_imports(text, "python", "sample.py", 1)
    assert sorted(e.local_name for e in entries) == ["Any", "Dict"]


def test_single_line_trailing_comment_is_still_stripped() -> None:
    """The original purpose of the ``#`` split must be preserved."""
    entries = parse_imports(
        "from os import path  # noqa: F401", "python", "sample.py", 1
    )
    assert [e.local_name for e in entries] == ["path"]


def test_plain_import_trailing_comment_is_still_stripped() -> None:
    entries = parse_imports("import os  # noqa: F401", "python", "sample.py", 1)
    assert [e.local_name for e in entries] == ["os"]


def test_multiline_import_with_per_name_comments() -> None:
    """Comments on individual continuation lines must not drop later names."""
    text = "from typing import (  # noqa: F401\n    Any,  # anything\n    Dict,\n)"
    entries = parse_imports(text, "python", "sample.py", 1)
    assert sorted(e.local_name for e in entries) == ["Any", "Dict"]


def test_aliased_multiline_import_with_comment() -> None:
    text = "from collections import (  # noqa: F401\n    OrderedDict as OD,\n)"
    entries = parse_imports(text, "python", "sample.py", 1)
    assert len(entries) == 1
    assert entries[0].local_name == "OD"
    assert entries[0].alias_of == "OrderedDict"


# ---------------------------------------------------------------------------
# BUG-3: ast_imports.line persisted end to end
# ---------------------------------------------------------------------------


END_TO_END_SRC = """\
from __future__ import annotations

import os
from typing import (  # noqa: F401
    Any,
    Dict,
)


class Widget:
    def method_a(self):
        def inner_helper():
            return 1
        return inner_helper
"""


@pytest.fixture
def indexed_db(tmp_path):
    (tmp_path / "sample.py").write_text(END_TO_END_SRC, encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_project()
    con = sqlite3.connect(str(tmp_path / ".ast-cache" / "index.db"))
    try:
        yield con
    finally:
        con.close()


def test_ast_imports_line_is_persisted(indexed_db) -> None:
    """Every ast_imports row must carry the source line it came from."""
    rows = indexed_db.execute(
        "SELECT local_name, line FROM ast_imports ORDER BY line, local_name"
    ).fetchall()

    assert rows, "no import rows were written"
    zero = [name for name, line in rows if line == 0]
    assert not zero, f"these imports lost their line number: {zero}"


def test_ast_imports_line_values_are_correct(indexed_db) -> None:
    lines = dict(
        indexed_db.execute("SELECT local_name, line FROM ast_imports").fetchall()
    )
    assert lines["annotations"] == 1
    assert lines["os"] == 3
    assert lines["Any"] == 4
    assert lines["Dict"] == 4


def test_end_to_end_symbol_rows_are_correct(indexed_db) -> None:
    """All four defects, observed through the persisted index."""
    rows = indexed_db.execute(
        "SELECT kind, name, line FROM ast_symbol_rows ORDER BY line"
    ).fetchall()
    kinds = {(kind, name) for kind, name, _ in rows}

    # BUG-1
    assert any(kind == "import" and "__future__" in name for kind, name in kinds)
    # BUG-2
    assert ("function", "inner_helper") in kinds
    assert ("method", "inner_helper") not in kinds
    assert ("method", "method_a") in kinds
    # BUG-4
    assert any(kind == "import" and "typing" in name for kind, name in kinds)


def test_no_bogus_contains_edge_for_nested_function(indexed_db) -> None:
    """BUG-2 also produced phantom class->function containment edges."""
    bogus = indexed_db.execute(
        "SELECT caller_name, callee_name FROM edges "
        "WHERE kind='contains' AND callee_name='inner_helper'"
    ).fetchall()
    assert not bogus, f"phantom contains edge(s): {bogus}"
