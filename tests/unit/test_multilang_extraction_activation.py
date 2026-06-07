"""Activation + cross-language MOAT tests for C / Ruby symbol extraction.

These guard the fix where C ``function_definition`` (name nested inside
``function_declarator``) and Ruby ``method`` / ``singleton_method`` were missing
from the indexed symbol table — invisible to ``search action=symbol`` and unable
to feed the per-language callee resolver (every local call fell back to
``unknown``).

Two layers:

* **Extraction (fast)** — drive ``_worker_index_file`` directly, asserting the
  symbols land with ``kind='function'`` and that call edges are produced.
* **Resolution + MOAT (end-to-end)** — index a real on-disk project and assert
  same-file local calls resolve to ``local``/``project`` and that a name shared
  across two languages (``add`` in both C and Ruby) never mis-wires across the
  language boundary (0 cross-language mis-wires).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from tree_sitter_analyzer._ast_extraction import _worker_index_file
from tree_sitter_analyzer.ast_cache import ASTCache

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _index_symbols(tmp_path: Path, filename: str, source: str, lang: str) -> list[dict]:
    f = tmp_path / filename
    f.write_text(source, encoding="utf-8")
    result = _worker_index_file((str(f), str(tmp_path), lang))
    assert result["status"] == "ok", result
    return json.loads(result["symbols_json"])["symbols"]


def _index_edges(tmp_path: Path, filename: str, source: str, lang: str) -> list[dict]:
    f = tmp_path / filename
    f.write_text(source, encoding="utf-8")
    result = _worker_index_file((str(f), str(tmp_path), lang))
    assert result["status"] == "ok", result
    return json.loads(result["call_edges_json"])


def _open_db(cache: ASTCache) -> sqlite3.Connection:
    conn = sqlite3.connect(cache.db_path)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# C — function_definition name extraction
# ---------------------------------------------------------------------------


class TestCFunctionExtraction:
    def test_plain_c_functions_are_indexed(self, tmp_path: Path) -> None:
        """``int add(...)`` / ``int main(...)`` land as function symbols."""
        syms = _index_symbols(
            tmp_path,
            "calc.c",
            "int add(int a, int b) { return a + b; }\n"
            "int main() { return add(1, 2); }\n",
            "c",
        )
        funcs = {s["name"] for s in syms if s.get("kind") == "function"}
        assert {"add", "main"} <= funcs

    def test_pointer_returning_function_is_indexed(self, tmp_path: Path) -> None:
        """libc-style ``void *malloc(...)`` (name under pointer_declarator)."""
        syms = _index_symbols(
            tmp_path,
            "mem.c",
            "void *malloc(unsigned long n) { return 0; }\n"
            "char *strdup(const char *s) { return 0; }\n",
            "c",
        )
        funcs = {s["name"] for s in syms if s.get("kind") == "function"}
        assert {"malloc", "strdup"} <= funcs

    def test_no_double_count_for_c_function(self, tmp_path: Path) -> None:
        """function_definition + nested function_declarator must yield ONE symbol."""
        syms = _index_symbols(
            tmp_path, "one.c", "int once(int a) { return a; }\n", "c"
        )
        names = [s["name"] for s in syms if s.get("kind") == "function"]
        assert names.count("once") == 1

    def test_local_variable_is_not_a_function(self, tmp_path: Path) -> None:
        """``int x = add(...)`` must NOT register ``x`` as a function symbol."""
        syms = _index_symbols(
            tmp_path,
            "var.c",
            "int add(int a){return a;}\nint main(){int x = add(1); return x;}\n",
            "c",
        )
        funcs = {s["name"] for s in syms if s.get("kind") == "function"}
        assert "x" not in funcs

    def test_c_call_edges_extracted(self, tmp_path: Path) -> None:
        edges = _index_edges(
            tmp_path,
            "e.c",
            "int add(int a){return a;}\nint main(){return add(1);}\n",
            "c",
        )
        assert any(
            e["caller_name"] == "main" and e["callee_name"] == "add" for e in edges
        )


# ---------------------------------------------------------------------------
# Ruby — method / singleton_method extraction
# ---------------------------------------------------------------------------

_RUBY_SRC = (
    "class Calculator\n"
    "  def add(a, b)\n"
    "    helper(a) + b\n"
    "  end\n"
    "  def helper(x)\n"
    "    x * 2\n"
    "  end\n"
    "  def self.create\n"
    "    Calculator.new\n"
    "  end\n"
    "end\n"
    "\n"
    "def standalone\n"
    "  add(1, 2)\n"
    "end\n"
)


class TestRubyMethodExtraction:
    def test_methods_are_indexed_with_kind_function(self, tmp_path: Path) -> None:
        syms = _index_symbols(tmp_path, "calc.rb", _RUBY_SRC, "ruby")
        funcs = {s["name"] for s in syms if s.get("kind") == "function"}
        assert {"add", "helper", "create", "standalone"} <= funcs

    def test_class_is_still_indexed(self, tmp_path: Path) -> None:
        syms = _index_symbols(tmp_path, "calc.rb", _RUBY_SRC, "ruby")
        classes = {s["name"] for s in syms if s.get("kind") == "class"}
        assert "Calculator" in classes

    def test_methods_carry_enclosing_class(self, tmp_path: Path) -> None:
        syms = _index_symbols(tmp_path, "calc.rb", _RUBY_SRC, "ruby")
        by_name = {s["name"]: s for s in syms if s.get("kind") == "function"}
        assert by_name["add"].get("class") == "Calculator"
        assert by_name["create"].get("class") == "Calculator"
        # A top-level def has no enclosing class.
        assert by_name["standalone"].get("class") is None

    def test_ruby_call_edges_extracted(self, tmp_path: Path) -> None:
        edges = _index_edges(tmp_path, "calc.rb", _RUBY_SRC, "ruby")
        pairs = {(e["caller_name"], e["callee_name"]) for e in edges}
        assert ("add", "helper") in pairs
        assert ("standalone", "add") in pairs

    def test_call_graph_and_symbol_table_agree_on_class(self, tmp_path: Path) -> None:
        """The call-graph path (``walk_tree``) and the symbol-table path
        (``_walk_for_symbols``) must assign the SAME enclosing class to each Ruby
        method — otherwise ``--callers "Calculator.add"`` (which reads the
        call_graph receiver field) disagrees with ``search action=symbol``."""
        from tree_sitter_analyzer.core.parser import Parser
        from tree_sitter_analyzer.function_extraction import walk_tree

        (tmp_path / "calc.rb").write_text(_RUBY_SRC, encoding="utf-8")
        parser = Parser()
        tree = parser.parse_file(str(tmp_path / "calc.rb"), "ruby").tree
        defs, _ = walk_tree(tree.root_node, _RUBY_SRC, "ruby")
        cg_class = {d["name"]: d.get("class") for d in defs}

        syms = _index_symbols(tmp_path, "calc.rb", _RUBY_SRC, "ruby")
        st_class = {
            s["name"]: s.get("class") for s in syms if s.get("kind") == "function"
        }

        for name in ("add", "helper", "create", "standalone"):
            assert cg_class.get(name) == st_class.get(name), (
                f"class mismatch for {name}: call-graph={cg_class.get(name)!r} "
                f"symbol-table={st_class.get(name)!r}"
            )
        assert cg_class["add"] == "Calculator"
        assert cg_class["standalone"] is None


# ---------------------------------------------------------------------------
# End-to-end resolution + cross-language MOAT (0 mis-wires)
# ---------------------------------------------------------------------------


class TestCrossLanguageResolutionMoat:
    def _build_project(self, tmp_path: Path) -> Path:
        proj = tmp_path / "multilang"
        proj.mkdir()
        # ``add`` is defined in BOTH languages — the MOAT is that a C call to
        # ``add`` must resolve to the C file and a Ruby call to ``add`` to the
        # Ruby file; never across the boundary.
        (proj / "calc.c").write_text(
            "int add(int a, int b) { return a + b; }\n"
            "int main() { return add(1, 2); }\n",
            encoding="utf-8",
        )
        (proj / "calc.rb").write_text(
            "class Calculator\n"
            "  def add(a, b)\n"
            "    helper(a) + b\n"
            "  end\n"
            "  def helper(x)\n"
            "    x * 2\n"
            "  end\n"
            "end\n"
            "def standalone\n"
            "  add(1, 2)\n"
            "end\n",
            encoding="utf-8",
        )
        # A project that DEFINES malloc — the custom-libc subsumption: a
        # project-owned malloc must resolve to the project, not stay unknown.
        (proj / "mylib.c").write_text(
            "void *malloc(unsigned long n) { return 0; }\n"
            "int use() { void *p = malloc(8); return 0; }\n",
            encoding="utf-8",
        )
        return proj

    def test_c_and_ruby_local_calls_resolve(self, tmp_path: Path) -> None:
        proj = self._build_project(tmp_path)
        cache = ASTCache(str(proj))
        try:
            cache.index_project(force=True)
            with _open_db(cache) as conn:
                edges = conn.execute(
                    "SELECT caller_name, callee_name, callee_resolution, "
                    "callee_resolved_file FROM edges WHERE kind = 'calls'"
                ).fetchall()
        finally:
            cache.close()
        by_pair = {(e["caller_name"], e["callee_name"]): e for e in edges}

        # C: main -> add resolves locally to calc.c
        c_add = by_pair[("main", "add")]
        assert c_add["callee_resolution"] in ("local", "project")
        assert c_add["callee_resolved_file"].endswith("calc.c")

        # Ruby: add -> helper and standalone -> add resolve to calc.rb
        rb_helper = by_pair[("add", "helper")]
        assert rb_helper["callee_resolution"] in ("local", "project")
        assert rb_helper["callee_resolved_file"].endswith("calc.rb")

        rb_add = by_pair[("standalone", "add")]
        assert rb_add["callee_resolution"] in ("local", "project")
        assert rb_add["callee_resolved_file"].endswith("calc.rb")

    def test_zero_cross_language_miswires(self, tmp_path: Path) -> None:
        """No resolved edge may point at a file of a different language."""
        proj = self._build_project(tmp_path)
        cache = ASTCache(str(proj))
        try:
            cache.index_project(force=True)
            with _open_db(cache) as conn:
                lang_by_file = {
                    r["file_path"]: r["language"]
                    for r in conn.execute(
                        "SELECT file_path, language FROM ast_index"
                    ).fetchall()
                }
                edges = conn.execute(
                    "SELECT file_path, callee_resolution, callee_resolved_file "
                    "FROM edges WHERE kind = 'calls' "
                    "AND callee_resolution IN ('local', 'project')"
                ).fetchall()
        finally:
            cache.close()

        miswires = []
        for e in edges:
            caller_lang = lang_by_file.get(e["file_path"])
            callee_lang = lang_by_file.get(e["callee_resolved_file"])
            if callee_lang is not None and caller_lang != callee_lang:
                miswires.append(dict(e))
        assert miswires == [], f"cross-language mis-wires: {miswires}"

    def test_project_defined_malloc_resolves_to_project(self, tmp_path: Path) -> None:
        """Custom-libc subsumption: an in-project malloc resolves, not unknown."""
        proj = self._build_project(tmp_path)
        cache = ASTCache(str(proj))
        try:
            cache.index_project(force=True)
            with _open_db(cache) as conn:
                row = conn.execute(
                    "SELECT callee_resolution, callee_resolved_file FROM edges "
                    "WHERE kind = 'calls' AND caller_name = 'use' "
                    "AND callee_name = 'malloc'"
                ).fetchone()
        finally:
            cache.close()
        assert row is not None
        assert row["callee_resolution"] in ("local", "project")
        assert row["callee_resolved_file"].endswith("mylib.c")
