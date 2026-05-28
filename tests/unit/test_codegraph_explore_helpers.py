"""Focused tests for codegraph_explore helper functions."""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock

from tree_sitter_analyzer.mcp.tools import _codegraph_explore_helpers as helpers


class TestConceptSearchHelpers:
    def test_extract_snippet_from_lines_handles_invalid_ranges(self):
        assert helpers.extract_snippet_from_lines(["one\n"], 0, 1) == ""
        assert helpers.extract_snippet_from_lines(["one\n"], 2, 1) == ""
        assert helpers.extract_snippet_from_lines([], 1, 1) == ""
        assert helpers.extract_snippet_from_lines(["one\n"], 3, 4) == ""

    def test_search_terms_drops_short_and_duplicate_tokens(self):
        assert helpers._search_terms(["to marker marker-service"]) == [
            "marker",
            "service",
        ]

    def test_concept_search_returns_empty_without_search_terms(self):
        cache = MagicMock()
        assert helpers.concept_search(cache, [], [], "/tmp/project", max_files=5) == []

    def test_concept_candidate_paths_handles_tuple_rows_caps_and_fallback(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE ast_index (file_path TEXT)")
        conn.executemany(
            "INSERT INTO ast_index VALUES (?)",
            [("src/a.py",), ("src/b.py",), ("tests/c.py",)],
        )

        capped = helpers._concept_candidate_paths(conn, [], ["src"], max_paths=1)
        assert capped == {"src/a.py"}

        fallback = helpers._concept_candidate_paths(
            conn, ["missing_symbol_rows"], [], max_paths=5
        )
        assert fallback == set()

    def test_concept_candidate_paths_stops_when_already_capped(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE ast_index (file_path TEXT)")
        conn.execute("INSERT INTO ast_index VALUES ('src/a.py')")

        assert helpers._concept_candidate_paths(conn, [], ["src"], max_paths=0) == set()

    def test_concept_candidate_paths_returns_empty_without_tokens(self):
        conn = sqlite3.connect(":memory:")

        assert helpers._concept_candidate_paths(conn, [], [], max_paths=5) == set()

    def test_concept_candidate_paths_full_scans_declaration_queries(self):
        conn = sqlite3.connect(":memory:")

        assert (
            helpers._concept_candidate_paths(
                conn, ["node", "type", "struct"], [], max_paths=5
            )
            == set()
        )

    def test_concept_candidate_paths_breaks_after_term_cap(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE ast_index (file_path TEXT)")
        conn.execute("CREATE TABLE ast_symbol_rows (file_path TEXT, name TEXT)")
        conn.executemany(
            "INSERT INTO ast_symbol_rows VALUES (?, ?)",
            [("src/a.py", "target"), ("src/b.py", "target")],
        )

        candidates = helpers._concept_candidate_paths(
            conn, ["target", "other"], [], max_paths=1
        )

        assert candidates == {"src/a.py"}

    def test_ranks_src_multi_term_match_above_test_fixture(self, tmp_path):
        src = tmp_path / "src/vs/platform/markers/common/markerService.ts"
        src.parent.mkdir(parents=True)
        src.write_text(
            "export class MarkerService {\n"
            "  public readDiagnosticsMarkerService() { return true; }\n"
            "}\n",
            encoding="utf-8",
        )
        fixture = tmp_path / "extensions/copilot/test/fixtures/service.ts"
        fixture.parent.mkdir(parents=True)
        fixture.write_text(
            "export function service() { return diagnostics; }\n", encoding="utf-8"
        )

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            """CREATE TABLE ast_index (
                file_path TEXT,
                language TEXT,
                file_size INTEGER,
                symbols_json TEXT
            )"""
        )
        for path in (fixture, src):
            rel = path.relative_to(tmp_path).as_posix()
            conn.execute(
                "INSERT INTO ast_index VALUES (?, ?, ?, ?)",
                (
                    rel,
                    "typescript",
                    path.stat().st_size,
                    json.dumps(
                        {"symbols": [{"name": path.stem, "kind": "class", "line": 1}]}
                    ),
                ),
            )

        cache = MagicMock()
        cache.get_conn.return_value = conn
        cache._get_conn.return_value = conn  # backward-compat alias
        result = helpers.concept_search(
            cache,
            ["diagnostics", "marker", "service"],
            [],
            str(tmp_path),
            max_files=2,
        )

        assert (
            result[0]["file_path"] == "src/vs/platform/markers/common/markerService.ts"
        )
        assert result[0]["matches"]
        assert result[0]["symbols"][0]["name"] == "markerService"

    def test_concept_search_skips_candidate_filters_and_unreadable_files(
        self, tmp_path
    ):
        src = tmp_path / "src" / "hit.py"
        src.parent.mkdir(parents=True)
        src.write_text("def target():\n    return 'needle'\n", encoding="utf-8")

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            """CREATE TABLE ast_index (
                file_path TEXT,
                language TEXT,
                file_size INTEGER,
                symbols_json TEXT
            )"""
        )
        rows = [
            (
                "src/hit.py",
                "python",
                src.stat().st_size,
                '{"symbols": [{"name": "target", "kind": "function", "line": 1}]}',
            ),
            ("src/unreadable.py", "python", 10, '{"symbols": []}'),
            ("src/huge.py", "python", 2_000_000, '{"symbols": []}'),
            ("tests/other.py", "python", 20, '{"symbols": []}'),
        ]
        conn.executemany("INSERT INTO ast_index VALUES (?, ?, ?, ?)", rows)
        cache = MagicMock()
        cache.get_conn.return_value = conn
        cache._get_conn.return_value = conn  # backward-compat alias

        result = helpers.concept_search(
            cache,
            ["needle"],
            ["src"],
            str(tmp_path),
            max_files=5,
        )

        assert [entry["file_path"] for entry in result] == ["src/hit.py"]

    def test_concept_search_skips_rows_outside_index_candidates(self, tmp_path):
        src = tmp_path / "src" / "hit.py"
        other = tmp_path / "src" / "other.py"
        src.parent.mkdir(parents=True)
        src.write_text("def target():\n    return 'needle'\n", encoding="utf-8")
        other.write_text("def other():\n    return 'needle'\n", encoding="utf-8")

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            """CREATE TABLE ast_index (
                file_path TEXT,
                language TEXT,
                file_size INTEGER,
                symbols_json TEXT
            )"""
        )
        conn.execute("CREATE TABLE ast_symbol_rows (file_path TEXT, name TEXT)")
        conn.executemany(
            "INSERT INTO ast_index VALUES (?, ?, ?, ?)",
            [
                ("src/hit.py", "python", src.stat().st_size, '{"symbols": []}'),
                ("src/other.py", "python", other.stat().st_size, '{"symbols": []}'),
            ],
        )
        conn.execute(
            "INSERT INTO ast_symbol_rows VALUES (?, ?)", ("src/hit.py", "needle")
        )
        cache = MagicMock()
        cache.get_conn.return_value = conn
        cache._get_conn.return_value = conn  # backward-compat alias

        result = helpers.concept_search(
            cache,
            ["needle"],
            [],
            str(tmp_path),
            max_files=5,
        )

        assert [entry["file_path"] for entry in result] == ["src/hit.py"]

    def test_concept_file_entry_returns_none_without_text_matches(self, tmp_path):
        source = tmp_path / "nomatch.py"
        source.write_text("def alpha():\n    return 1\n", encoding="utf-8")

        entry = helpers._concept_file_entry(
            project_root=str(tmp_path),
            rel_path="nomatch.py",
            language="python",
            symbols_json='{"symbols": []}',
            terms=["needle"],
            max_matches=3,
        )

        assert entry is None

    def test_concept_file_entry_stops_at_max_matches(self, tmp_path):
        source = tmp_path / "matches.py"
        source.write_text("needle one\nneedle two\n", encoding="utf-8")

        entry = helpers._concept_file_entry(
            project_root=str(tmp_path),
            rel_path="matches.py",
            language="python",
            symbols_json='{"symbols": []}',
            terms=["needle"],
            max_matches=1,
        )

        assert entry is not None
        assert len(entry["matches"]) == 1

    def test_concept_file_entry_prioritizes_type_declaration_matches(self, tmp_path):
        source = tmp_path / "tree.go"
        source.write_text(
            "package gin\n\n"
            "type Param struct {\n"
            "\tKey string\n"
            "}\n\n"
            "type methodTree struct {\n"
            "\troot *node\n"
            "}\n\n"
            "type nodeType uint8\n\n"
            "type node struct {\n"
            "\tpath string\n"
            "\tchildren []*node\n"
            "}\n\n"
            "func (n *node) addChild(child *node) {}\n",
            encoding="utf-8",
        )

        entry = helpers._concept_file_entry(
            project_root=str(tmp_path),
            rel_path="tree.go",
            language="go",
            symbols_json='{"symbols": [{"name": "addChild", "kind": "function", "line": 18}]}',
            terms=["node", "type", "struct"],
            max_matches=2,
        )

        assert entry is not None
        assert any(match["text"] == "type node struct {" for match in entry["matches"])
        assert entry["symbols"][0]["name"] == "node"
        assert entry["symbols"][0]["kind"] == "type"
        assert "children []*node" in entry["symbols"][0]["code"]

    def test_concept_search_ranks_declaration_file_above_test_usage(self, tmp_path):
        src = tmp_path / "tree.go"
        test = tmp_path / "tree_test.go"
        src.write_text(
            "package gin\n\ntype node struct {\n\tpath string\n}\n",
            encoding="utf-8",
        )
        test.write_text(
            "package gin\n\nfunc checkRequests(t *testing.T, tree *node) {}\n",
            encoding="utf-8",
        )
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            """CREATE TABLE ast_index (
                file_path TEXT,
                language TEXT,
                file_size INTEGER,
                symbols_json TEXT
            )"""
        )
        for path in (test, src):
            conn.execute(
                "INSERT INTO ast_index VALUES (?, ?, ?, ?)",
                (
                    path.name,
                    "go",
                    path.stat().st_size,
                    '{"symbols": []}',
                ),
            )
        cache = MagicMock()
        cache.get_conn.return_value = conn
        cache._get_conn.return_value = conn  # backward-compat alias

        result = helpers.concept_search(
            cache,
            ["node", "type", "struct"],
            [],
            str(tmp_path),
            max_files=2,
        )

        assert result[0]["file_path"] == "tree.go"
        assert result[0]["symbols"][0]["name"] == "node"

    def test_declaration_helpers_cover_invalid_lines_and_unclosed_blocks(self):
        symbols = helpers._declaration_symbols_from_matches(
            ["type node struct {}\n"],
            [{"line": 0}, {"line": 2}, {"line": 1}],
            ["node"],
        )

        assert [symbol["name"] for symbol in symbols] == ["node"]
        assert helpers._declaration_symbol_from_line(
            "class Router {}", 1, [], ["router"]
        ) == {
            "name": "Router",
            "kind": "type",
            "start_line": 1,
            "end_line": 1,
            "code": "class Router {}",
        }
        assert (
            helpers._declaration_end_line(
                ["type node struct {\n", "\tpath string\n"], 1
            )
            == 1
        )

    def test_declaration_symbol_from_line_supports_go_type_aliases(self):
        assert helpers._declaration_symbol_from_line(
            "type HandlerFunc func(*Context)", 9, [], ["handlerfunc"]
        ) == {
            "name": "HandlerFunc",
            "kind": "type",
            "start_line": 9,
            "end_line": 9,
            "code": "type HandlerFunc func(*Context)",
        }
        assert (
            helpers._declaration_symbol_from_line(
                "type Params []Param", 12, [], ["params"]
            )["name"]
            == "Params"
        )
        assert (
            helpers._declaration_symbol_from_line(
                "type Params []Param", 12, [], ["node"]
            )
            is None
        )

    def test_declaration_symbol_from_line_supports_go_const_blocks(self):
        lines = [
            "const (\n",
            "\tstatic nodeType = iota\n",
            "\troot\n",
            "\tparam\n",
            "\tcatchAll\n",
            ")\n",
        ]

        assert helpers._declaration_symbol_from_line(
            lines[1], 2, lines, ["static"]
        ) == {
            "name": "static",
            "kind": "constant",
            "start_line": 2,
            "end_line": 6,
            "code": "".join(lines),
        }
        assert (
            helpers._declaration_symbol_from_line(lines[4], 5, lines, ["catchall"])[
                "name"
            ]
            == "catchAll"
        )
        assert (
            helpers._declaration_symbol_from_line(lines[4], 5, lines, ["node"]) is None
        )
        assert helpers._term_position("missing", ["static"]) == 1
        assert helpers._declaration_symbol_from_line(
            "const maxParams = 8", 11, [], ["maxparams"]
        ) == {
            "name": "maxParams",
            "kind": "constant",
            "start_line": 11,
            "end_line": 11,
            "code": "const maxParams = 8",
        }
        assert (
            helpers._declaration_symbol_from_line(
                "var routeCache = map[string]int{}", 12, [], ["routecache"]
            )["kind"]
            == "variable"
        )

    def test_block_declaration_bounds_cover_invalid_and_unclosed_blocks(self):
        assert helpers._block_declaration_bounds(["const (\n"], 0) is None
        assert (
            helpers._block_declaration_bounds([")\n", "\tstatic nodeType = iota\n"], 2)
            is None
        )
        assert helpers._block_declaration_bounds(["var (\n", "\tcurrent = 1\n"], 2) == (
            1,
            2,
            "variable",
        )

    def test_concept_search_ranks_const_block_source_above_test_usage(self, tmp_path):
        src = tmp_path / "tree.go"
        src.write_text(
            "package gin\n\n"
            "type nodeType uint8\n\n"
            "const (\n"
            "\tstatic nodeType = iota\n"
            "\troot\n"
            "\tparam\n"
            "\tcatchAll\n"
            ")\n",
            encoding="utf-8",
        )
        test = tmp_path / "tree_test.go"
        test.write_text(
            "package gin\n\n"
            "func TestTreeCatchAllConflict(t *testing.T) {}\n"
            "func TestTreeInvalidNodeType(t *testing.T) {}\n",
            encoding="utf-8",
        )
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            """CREATE TABLE ast_index (
                file_path TEXT,
                language TEXT,
                file_size INTEGER,
                symbols_json TEXT
            )"""
        )
        for path in (test, src):
            conn.execute(
                "INSERT INTO ast_index VALUES (?, ?, ?, ?)",
                (
                    path.name,
                    "go",
                    path.stat().st_size,
                    '{"symbols": []}',
                ),
            )
        cache = MagicMock()
        cache.get_conn.return_value = conn
        cache._get_conn.return_value = conn  # backward-compat alias

        result = helpers.concept_search(
            cache,
            ["catchAll", "nodeType"],
            [],
            str(tmp_path),
            max_files=2,
        )

        assert result[0]["file_path"] == "tree.go"
        assert result[0]["symbols"][0]["name"] == "catchAll"

    def test_dedupe_concept_symbols_skips_invalid_and_duplicates(self):
        deduped = helpers._dedupe_concept_symbols(
            [
                {},
                {"name": "node"},
                {"name": "node", "start_line": 1},
                {"name": "node", "start_line": 1},
                {"name": "nodeValue", "start_line": 2},
            ]
        )

        assert [symbol["name"] for symbol in deduped] == ["node", "nodeValue"]

    def test_nearby_symbols_skips_far_duplicates_and_caps_results(self):
        matches = [{"line": 50}]
        symbols = [
            {"name": 'import "fmt"', "kind": "import", "line": 49},
            {"name": "missing_line", "kind": "function"},
            {"name": "far", "kind": "function", "line": 1},
            {"name": "dup", "kind": "function", "line": 45},
            {"name": "dup", "kind": "function", "line": 45},
            *[
                {"name": f"near_{i}", "kind": "function", "line": 46 + i}
                for i in range(10)
            ],
        ]

        nearby = helpers._nearby_symbols(json.dumps({"symbols": symbols}), matches)

        assert [s["name"] for s in nearby][:2] == ["dup", "near_0"]
        assert len(nearby) == 8

    def test_nearby_symbols_degrades_on_invalid_json(self):
        assert helpers._nearby_symbols("{not json", [{"line": 1}]) == []

    def test_definition_like_and_test_path_helpers_cover_go(self):
        assert helpers._is_definition_like_match(
            "func addRoute(path string) {}", ["route"]
        )
        assert helpers._is_test_like_path("gin_test.go")

        rank = helpers._concept_rank(
            {
                "file_path": "gin_test.go",
                "matched_terms": ["route"],
                "matches": [{"text": "func TestRoute(t *testing.T) {", "line": 1}],
            },
            ["route"],
        )

        assert rank < helpers._concept_rank(
            {
                "file_path": "gin.go",
                "matched_terms": ["route"],
                "matches": [{"text": "func addRoute(path string) {", "line": 1}],
            },
            ["route"],
        )

    def test_definition_like_match_requires_term_in_text(self):
        assert helpers._is_definition_like_match(
            "export class MarkerService {}", ["marker"]
        )
        assert not helpers._is_definition_like_match(
            "export class MarkerService {}", ["route"]
        )
