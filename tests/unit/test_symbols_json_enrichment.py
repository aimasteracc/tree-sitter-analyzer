"""Issue #614 — docstring/return_type/params serialized into symbols_json.

RFC-0016 prerequisite: the embedding input
``"{kind} {qualified_name}({params}) -> {return_type}\\n{docstring}"`` must be
constructible from the cache. The raw-AST walker (``_walk_for_symbols``) is
the path that feeds ``ast_index.symbols_json`` — it already carries ``params``
but dropped docstring/return_type.

Also covers the BM25-enrichment arm: docstring tokens enter
``ast_symbols_fts`` as a NEW low-weight column (bm25 weight 1.0 vs name 10.0)
so conceptual queries can match docstring text without polluting name-rank.
"""

from __future__ import annotations

import sqlite3

from tree_sitter_analyzer._ast_extraction import (
    _DOCSTRING_MAX_CHARS,
    _worker_index_file,
)


def _symbols_for(source: str, lang: str) -> list[dict]:
    from tree_sitter_analyzer._ast_extraction import _extract_symbols
    from tree_sitter_analyzer.core.parser import Parser

    result = Parser().parse_code(source, lang)
    assert result.success and result.tree is not None
    return _extract_symbols(result.tree, source, lang)["symbols"]


_PY_SRC = '''\
"""Module docstring — must NOT become a symbol docstring."""

CACHE_TTL = 60


def dispatch(request: dict, *, strict: bool = False) -> str:
    """Route an incoming request to the matching facade action."""
    return "ok"


def no_doc(x):
    return x


class Router:
    """Holds the routing table for tool dispatch."""

    def handle(self, name):
        """Resolve name and invoke the handler."""
        return name

    def _bare(self):
        pass
'''


class TestPythonDocstringSerialized:
    def _by_name(self) -> dict[str, dict]:
        return {s["name"]: s for s in _symbols_for(_PY_SRC, "python") if "name" in s}

    def test_function_docstring_serialized(self):
        syms = self._by_name()
        assert (
            syms["dispatch"]["docstring"]
            == "Route an incoming request to the matching facade action."
        )

    def test_method_docstring_serialized(self):
        syms = self._by_name()
        assert syms["handle"]["docstring"] == "Resolve name and invoke the handler."

    def test_class_docstring_serialized(self):
        syms = self._by_name()
        assert (
            syms["Router"]["docstring"] == "Holds the routing table for tool dispatch."
        )

    def test_absent_docstring_field_absent_not_empty_string(self):
        syms = self._by_name()
        assert "docstring" not in syms["no_doc"]
        assert "docstring" not in syms["_bare"]

    def test_docstring_capped_at_exactly_500_chars(self):
        assert _DOCSTRING_MAX_CHARS == 500
        long_doc = "x" * 600
        src = f'def f():\n    """{long_doc}"""\n'
        syms = {s["name"]: s for s in _symbols_for(src, "python") if "name" in s}
        assert len(syms["f"]["docstring"]) == 500
        assert syms["f"]["docstring"] == "x" * 500

    def test_whitespace_only_docstring_field_absent(self):
        src = 'def f():\n    """   """\n    return 1\n'
        syms = {s["name"]: s for s in _symbols_for(src, "python") if "name" in s}
        assert "docstring" not in syms["f"]

    def test_incomplete_function_without_body_is_safe(self):
        # tree-sitter error recovery: `def f():` with no body must not crash
        # the docstring helper and must not emit a docstring key.
        syms = {
            s["name"]: s for s in _symbols_for("def f():\n", "python") if "name" in s
        }
        assert "docstring" not in syms["f"]

    def test_multiline_docstring_stripped_and_preserved(self):
        src = 'def f():\n    """First line.\n\n    Body detail.\n    """\n'
        syms = {s["name"]: s for s in _symbols_for(src, "python") if "name" in s}
        assert syms["f"]["docstring"] == "First line.\n\n    Body detail."


class TestReturnTypeAndParamsSerialized:
    def _by_name(self) -> dict[str, dict]:
        return {s["name"]: s for s in _symbols_for(_PY_SRC, "python") if "name" in s}

    def test_return_type_serialized(self):
        syms = self._by_name()
        assert syms["dispatch"]["return_type"] == "str"

    def test_absent_return_type_field_absent(self):
        syms = self._by_name()
        assert "return_type" not in syms["no_doc"]

    def test_params_already_serialized(self):
        syms = self._by_name()
        assert syms["dispatch"]["params"] == "(request: dict, *, strict: bool = False)"

    def test_rust_return_type_serialized(self):
        src = "fn add(a: i32, b: i32) -> i32 { a + b }\n"
        syms = {s["name"]: s for s in _symbols_for(src, "rust") if "name" in s}
        assert syms["add"]["return_type"] == "i32"

    def test_non_python_function_has_no_docstring(self):
        src = 'function f() { return "doc-like string"; }\n'
        syms = {s["name"]: s for s in _symbols_for(src, "javascript") if "name" in s}
        assert "docstring" not in syms["f"]


class TestWorkerSymbolRowsCarryDocstring:
    def test_worker_tuples_are_5_tuples_with_docstring(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text(_PY_SRC, encoding="utf-8")
        result = _worker_index_file((str(f), str(tmp_path), "python"))
        assert result["status"] == "ok"
        rows = {r[0]: r for r in result["symbol_rows"]}
        assert len(rows["dispatch"]) == 5
        assert (
            rows["dispatch"][4]
            == "Route an incoming request to the matching facade action."
        )
        # symbols without a docstring carry "" in the FTS row (TEXT column),
        # while the symbols_json dict omits the key entirely.
        assert rows["no_doc"][4] == ""


class TestFtsDocstringColumn:
    def _fresh_conn(self) -> sqlite3.Connection:
        from tree_sitter_analyzer._ast_cache_schema import SCHEMA_V2_FTS

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA_V2_FTS)
        return conn

    def test_fts_schema_has_docstring_column(self):
        from tree_sitter_analyzer._ast_cache_schema import SCHEMA_V2_FTS

        assert "docstring" in SCHEMA_V2_FTS

    def test_docstring_token_matches_via_fts(self):
        from tree_sitter_analyzer import _ast_cache_write as w

        conn = self._fresh_conn()
        symbols = {
            "symbols": [
                {
                    "kind": "function",
                    "name": "dispatch",
                    "line": 1,
                    "end_line": 2,
                    "docstring": "Route an incoming request to the facade.",
                },
                {"kind": "function", "name": "no_doc", "line": 4, "end_line": 5},
            ]
        }
        w.write_fts5_symbols(conn, "mod.py", "python", symbols)
        rows = conn.execute(
            "SELECT r.name FROM ast_symbols_fts f "
            "JOIN ast_symbol_rows r ON f.rowid = r.id "
            "WHERE ast_symbols_fts MATCH ?",
            ('docstring:"incoming"',),
        ).fetchall()
        assert [r["name"] for r in rows] == ["dispatch"]

    def test_tuple_writer_indexes_docstring(self):
        from tree_sitter_analyzer import _ast_cache_write as w

        conn = self._fresh_conn()
        w.write_fts5_symbols_from_tuples(
            conn,
            "mod.py",
            "python",
            [
                ("dispatch", "function", 1, 2, "Route an incoming request."),
                ("no_doc", "function", 4, 5, ""),
            ],
        )
        rows = conn.execute(
            "SELECT r.name FROM ast_symbols_fts f "
            "JOIN ast_symbol_rows r ON f.rowid = r.id "
            "WHERE ast_symbols_fts MATCH ?",
            ('docstring:"incoming"',),
        ).fetchall()
        assert [r["name"] for r in rows] == ["dispatch"]

    def test_bm25_weights_carry_explicit_low_docstring_weight(self):
        # name 10.0 >> docstring 1.0 — docstring tokens must not pollute
        # name-rank (issue #614 design point).
        import inspect

        from tree_sitter_analyzer._ast_cache_query import fts_search_ranked

        src = inspect.getsource(fts_search_ranked)
        assert "bm25(ast_symbols_fts, 10.0, 0.5, 0.5, 0.1, 1.0)" in src


class TestMigrationV13:
    def test_v13_rebuilds_fts_with_docstring_column(self):
        from tree_sitter_analyzer._ast_cache_schema import (
            SCHEMA_VERSIONS_DDL,
            apply_migration_v13,
            record_schema_version,
        )

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA_VERSIONS_DDL)
        # Simulate a pre-v13 cache: 4-column FTS + populated symbol rows.
        conn.executescript(
            "CREATE VIRTUAL TABLE ast_symbols_fts USING fts5("
            "name, kind, file_path, language, content='', "
            "tokenize='porter unicode61');"
            "CREATE TABLE ast_symbol_rows ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, "
            "kind TEXT NOT NULL, file_path TEXT NOT NULL, "
            "language TEXT NOT NULL, line INTEGER NOT NULL DEFAULT 0, "
            "end_line INTEGER NOT NULL DEFAULT 0);"
        )
        conn.execute(
            "INSERT INTO ast_symbol_rows (name, kind, file_path, language, line, end_line) "
            "VALUES ('dispatch', 'function', 'mod.py', 'python', 1, 2)"
        )
        apply_migration_v13(conn, record_schema_version)
        # docstring column exists and is queryable (empty until re-extract).
        rows = conn.execute(
            "SELECT r.name FROM ast_symbols_fts f "
            "JOIN ast_symbol_rows r ON f.rowid = r.id "
            "WHERE ast_symbols_fts MATCH 'name:dispatch'"
        ).fetchall()
        assert [r["name"] for r in rows] == ["dispatch"]
        version = conn.execute(
            "SELECT version FROM ast_schema_version WHERE version = 13"
        ).fetchone()
        assert version is not None


class TestExtractorVersionBump:
    def test_extractor_version_is_6_in_both_sites(self):
        from tree_sitter_analyzer import _ast_cache_indexer, ast_cache

        assert ast_cache._AST_CACHE_EXTRACTOR_VERSION == 6
        assert _ast_cache_indexer._AST_CACHE_EXTRACTOR_VERSION == 6
