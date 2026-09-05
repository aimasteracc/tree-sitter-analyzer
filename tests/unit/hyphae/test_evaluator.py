"""Tests for the Hyphae evaluator over a fake edges-backed ASTCache."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.hyphae.evaluator import Evaluator
from tree_sitter_analyzer.hyphae.parser import HyphaeSyntaxError, parse


class FakeCache:
    """ASTCache stand-in backed by in-memory symbols + edges fixtures."""

    def __init__(self, functions, classes, edges):
        self._functions = functions
        self._classes = classes
        self._edges = edges  # list of {kind, caller_name, callee_name, file_path}

    def get_functions(self):
        return list(self._functions)

    def get_symbols_by_kind(self, kind, limit=50000):
        if kind == "class":
            return list(self._classes)
        return []

    def search_symbols_cascade(self, query, limit=100):
        pool = self._functions + self._classes
        return [s for s in pool if s.get("name") == query]

    def query_edges(self, kind, caller_name=None, callee_name=None, limit=10000):
        out = []
        for e in self._edges:
            if e["kind"] != kind:
                continue
            if caller_name is not None and e.get("caller_name") != caller_name:
                continue
            if callee_name is not None and e.get("callee_name") != callee_name:
                continue
            out.append(e)
        return out


def _names(rows):
    return sorted(r["name"] for r in rows)


def _fixture():
    functions = [
        {
            "name": "save",
            "file": "svc/UserService.java",
            "line": 10,
            "language": "java",
            "class": "UserService",
        },
        {
            "name": "delete",
            "file": "svc/UserService.java",
            "line": 20,
            "language": "java",
            "class": "UserService",
        },
        {
            "name": "find",
            "file": "svc/UserRepo.java",
            "line": 55,
            "language": "java",
            "class": "UserRepo",
        },
        {
            "name": "helper",
            "file": "util/Helpers.java",
            "line": 100,
            "language": "java",
            "class": None,
        },
    ]
    classes = [
        {
            "name": "UserService",
            "file": "svc/UserService.java",
            "line": 5,
            "language": "java",
            "kind": "class",
        },
        {
            "name": "UserRepo",
            "file": "svc/UserRepo.java",
            "line": 50,
            "language": "java",
            "kind": "class",
        },
        {
            "name": "BaseService",
            "file": "svc/BaseService.java",
            "line": 1,
            "language": "java",
            "kind": "class",
        },
    ]
    edges = [
        {
            "kind": "calls",
            "caller_name": "save",
            "callee_name": "find",
            "file_path": "svc/UserService.java",
        },
        {
            "kind": "calls",
            "caller_name": "delete",
            "callee_name": "helper",
            "file_path": "svc/UserService.java",
        },
        {
            "kind": "contains",
            "caller_name": "UserService",
            "callee_name": "save",
            "file_path": "svc/UserService.java",
        },
        {
            "kind": "contains",
            "caller_name": "UserService",
            "callee_name": "delete",
            "file_path": "svc/UserService.java",
        },
        {
            "kind": "contains",
            "caller_name": "UserRepo",
            "callee_name": "find",
            "file_path": "svc/UserRepo.java",
        },
        {
            "kind": "extends",
            "caller_name": "UserService",
            "callee_name": "BaseService",
            "file_path": "svc/UserService.java",
        },
        {
            "kind": "imports",
            "caller_name": "",
            "callee_name": "com.acme.Repo",
            "file_path": "svc/UserService.java",
        },
    ]
    return Evaluator(FakeCache(functions, classes, edges))


# -- base ----------------------------------------------------------------------
def test_name_lookup():
    assert _names(_fixture().eval(parse("#save"))) == ["save"]


def test_kind_method_requires_class_field():
    got = _names(_fixture().eval(parse(".method")))
    assert "helper" not in got and "save" in got and "find" in got


def test_kind_class_enumerates_class_symbols():
    got = _names(_fixture().eval(parse(".class")))
    assert got == ["BaseService", "UserRepo", "UserService"]


def test_kind_interface_aliases_class():
    # .interface maps to class enumeration in the MVP.
    assert "UserService" in _names(_fixture().eval(parse(".interface")))


# -- edge pseudo-classes -------------------------------------------------------
def test_calls_edge_driven():
    got = _names(_fixture().eval(parse(".method:calls(#find)")))
    assert got == ["save"]


def test_callees_edge_driven():
    # methods that find is called-from? callees(#save) = what save calls = find
    got = _names(_fixture().eval(parse("*:callees(#save)")))
    assert "find" in got


def test_extends_edge():
    got = _names(_fixture().eval(parse(".class:extends(#BaseService)")))
    assert got == ["UserService"]


def test_implements_aliases_extends():
    got = _names(_fixture().eval(parse(".class:implements(#BaseService)")))
    assert got == ["UserService"]


# -- structural pseudo-classes -------------------------------------------------
def test_has_via_contains_edge():
    got = _names(_fixture().eval(parse(".class:has(#save)")))
    assert got == ["UserService"]


def test_first_child_per_class():
    got = _names(_fixture().eval(parse(".method:first-child")))
    # save (first in UserService), find (only/first in UserRepo)
    assert got == ["find", "save"]


def test_nth_child_second():
    got = _names(_fixture().eval(parse(".method:nth-child(2)")))
    assert got == ["delete"]


def test_only_child():
    got = _names(_fixture().eval(parse(".method:only-child")))
    assert got == ["find"]  # UserRepo has a single method


def test_imports_file_level():
    got = _names(_fixture().eval(parse(".method:imports(com.acme.Repo)")))
    # methods in svc/UserService.java (which imports com.acme.Repo)
    assert "save" in got and "delete" in got
    assert "find" not in got


# -- filters -------------------------------------------------------------------
def test_not_excludes():
    got = _names(_fixture().eval(parse(".method:calls(#find):not(#save)")))
    assert got == []


def test_in_path_filter():
    got = _names(_fixture().eval(parse(".method:in(svc/)")))
    assert "helper" not in got and "save" in got


def test_attribute_file_filter():
    got = _names(_fixture().eval(parse(".method[file=UserService]")))
    assert got == ["delete", "save"]


# -- combinators ---------------------------------------------------------------
def test_child_combinator():
    got = _names(_fixture().eval(parse("#UserService > .method")))
    assert got == ["delete", "save"]


def test_selector_list_union():
    assert _names(_fixture().eval(parse("#save, #find"))) == ["find", "save"]


# -- error handling ------------------------------------------------------------
def test_unknown_pseudo_raises():
    with pytest.raises(HyphaeSyntaxError):
        _fixture().eval(parse(".method:bogus(#x)"))


def test_nth_child_requires_number():
    with pytest.raises(HyphaeSyntaxError):
        _fixture().eval(parse(".method:nth-child(#x)"))


# -- codex review fixes --------------------------------------------------------
def test_subclasses_returns_children():
    # :subclasses(#Base) must match the parent endpoint (callee) and return
    # children (caller) — same direction as :extends.
    got = _names(_fixture().eval(parse(".class:subclasses(#BaseService)")))
    assert got == ["UserService"]


def test_calls_distinguishes_same_name_across_files():
    # Two methods named 'save' in different files; only one calls 'find'.
    functions = [
        {"name": "save", "file": "a/A.java", "line": 10, "class": "A"},
        {"name": "save", "file": "b/B.java", "line": 20, "class": "B"},
    ]
    edges = [
        {
            "kind": "calls",
            "caller_name": "save",
            "callee_name": "find",
            "file_path": "a/A.java",
            "callee_resolved_file": "r/R.java",
        },
    ]
    ev = Evaluator(FakeCache(functions, [], edges))
    got = ev.eval(parse(".method:calls(#find)"))
    # file identity: only a/A.java's save, not b/B.java's.
    assert len(got) == 1
    assert got[0]["file"] == "a/A.java"


def test_implements_queries_implements_edge_kind():
    # An indexer that emits a distinct 'implements' edge must be matched.
    classes = [
        {"name": "JsonWriter", "file": "JsonWriter.java", "line": 1, "kind": "class"},
    ]
    edges = [
        {
            "kind": "implements",
            "caller_name": "JsonWriter",
            "callee_name": "Writeable",
            "file_path": "JsonWriter.java",
        },
    ]
    ev = Evaluator(FakeCache([], classes, edges))
    got = _names(ev.eval(parse(".class:implements(#Writeable)")))
    assert got == ["JsonWriter"]


# ===========================================================================
# FakeCacheWithConn — extends FakeCache with get_conn() for temporal/depth
# ===========================================================================

class FakeCacheWithConn(FakeCache):
    """FakeCache subclass that provides a real sqlite3 connection.

    Used for tests of temporal, depth-BFS, violates, reaches, and branch
    pseudo-classes that call `getattr(self._cache, "get_conn", None)()`.
    """

    def __init__(self, functions, classes, edges, conn):
        super().__init__(functions, classes, edges)
        self._conn = conn

    def get_conn(self):
        return self._conn


# ---------------------------------------------------------------------------
# Private seed helpers for the new test cases
# ---------------------------------------------------------------------------

def _seed_sym(conn, name: str, file_path: str = "f.py", language: str = "python", line: int = 1) -> int:
    """Insert a row into ast_symbol_rows; return the new id."""
    cur = conn.execute(
        "INSERT INTO ast_symbol_rows (name, kind, file_path, language, line, end_line) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, "function", file_path, language, line, line + 5),
    )
    conn.commit()
    return cur.lastrowid


def _seed_activation(conn, sym_id: int, mod_count_30d: int = 0, last_modified_at: int | None = None) -> None:
    """Insert a row into ast_symbol_activation."""
    if last_modified_at is None:
        last_modified_at = 0
    conn.execute(
        "INSERT OR REPLACE INTO ast_symbol_activation "
        "(symbol_id, file_path, last_modified_at, mod_count_30d, computed_at) "
        "VALUES (?, "
        "(SELECT file_path FROM ast_symbol_rows WHERE id = ?), "
        "?, ?, 0)",
        (sym_id, sym_id, last_modified_at, mod_count_30d),
    )
    conn.commit()


def _seed_edge(
    conn,
    src_name: str,
    tgt_name: str,
    kind: str = "calls",
    callee_symbol_id: int | None = None,
    metadata: str | None = None,
    file_path: str = "f.py",
) -> int:
    """Insert a row into edges; return the new id."""
    cur = conn.execute(
        "INSERT INTO edges "
        "(source_node_id, target_node_id, kind, line, caller_name, callee_name, "
        "file_path, callee_symbol_id, metadata) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            src_name,
            tgt_name,
            kind,
            1,
            src_name,
            tgt_name,
            file_path,
            callee_symbol_id,
            metadata,
        ),
    )
    conn.commit()
    return cur.lastrowid


def _seed_violation(
    conn,
    rule_id: str,
    caller_file: str,
    caller_name: str,
    caller_line: int = 1,
    callee_name: str = "something",
    severity: str = "error",
) -> None:
    """Insert a row into ast_constraint_violations."""
    import time as _time
    conn.execute(
        "INSERT OR REPLACE INTO ast_constraint_violations "
        "(rule_id, caller_file, caller_name, caller_line, callee_name, severity, detected_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (rule_id, caller_file, caller_name, caller_line, callee_name, severity, int(_time.time())),
    )
    conn.commit()


# ===========================================================================
# Temporal filter tests
# ===========================================================================

def test_filter_temporal_hot(ast_cache_conn):
    """Symbols with mod_count_30d > threshold are kept; others dropped."""
    id_hot = _seed_sym(ast_cache_conn, "hot_fn")
    id_cold = _seed_sym(ast_cache_conn, "cold_fn")
    _seed_activation(ast_cache_conn, id_hot, mod_count_30d=10)
    _seed_activation(ast_cache_conn, id_cold, mod_count_30d=2)

    cache = FakeCacheWithConn(
        [
            {"name": "hot_fn", "file": "f.py", "line": 1, "language": "python"},
            {"name": "cold_fn", "file": "f.py", "line": 6, "language": "python"},
        ],
        [],
        [],
        ast_cache_conn,
    )
    ev = Evaluator(cache)
    # threshold=5: hot_fn (10>5) kept, cold_fn (2<=5) dropped
    result = ev._filter_temporal(
        [
            {"name": "hot_fn", "file": "f.py"},
            {"name": "cold_fn", "file": "f.py"},
        ],
        "hot",
        5,
    )
    assert _names(result) == ["hot_fn"]


def test_filter_temporal_hotspot(ast_cache_conn):
    """Top 10% by mod_count_30d within a file are kept as hotspots."""
    syms = []
    for i in range(10):
        sid = _seed_sym(ast_cache_conn, f"fn_{i}", file_path="hot.py", line=i * 10 + 1)
        _seed_activation(ast_cache_conn, sid, mod_count_30d=i + 1)
        syms.append({"name": f"fn_{i}", "file": "hot.py"})

    cache = FakeCacheWithConn([], [], [], ast_cache_conn)
    ev = Evaluator(cache)
    result = ev._filter_temporal(syms, "hotspot", None)
    # top 10% of 10 = max(1, 1) = 1 symbol (fn_9 with mod_count=10)
    assert len(result) == 1
    assert result[0]["name"] == "fn_9"


def test_filter_temporal_recently_modified(ast_cache_conn):
    """Symbols modified within 30 days are kept; older ones dropped."""
    import time as _time
    now = int(_time.time())

    id_recent = _seed_sym(ast_cache_conn, "recent_fn")
    id_old = _seed_sym(ast_cache_conn, "old_fn")
    _seed_activation(ast_cache_conn, id_recent, last_modified_at=now)
    _seed_activation(ast_cache_conn, id_old, last_modified_at=0)

    cache = FakeCacheWithConn([], [], [], ast_cache_conn)
    ev = Evaluator(cache)
    result = ev._filter_temporal(
        [
            {"name": "recent_fn", "file": "f.py"},
            {"name": "old_fn", "file": "f.py"},
        ],
        "recently_modified",
        None,
    )
    assert _names(result) == ["recent_fn"]


# ===========================================================================
# Violates filter test
# ===========================================================================

def test_filter_violates(ast_cache_conn):
    """Symbols with a matching violation are kept; clean symbols dropped."""
    _seed_violation(ast_cache_conn, "no_db", "f.py", "dirty_fn")

    cache = FakeCacheWithConn([], [], [], ast_cache_conn)
    ev = Evaluator(cache)
    result = ev._filter_violates(
        [
            {"name": "dirty_fn", "file": "f.py"},
            {"name": "clean_fn", "file": "f.py"},
        ],
        "no_db",
    )
    assert _names(result) == ["dirty_fn"]


# ===========================================================================
# Branch filter test
# ===========================================================================

def test_filter_branch_loop(ast_cache_conn):
    """Symbols called inside a loop branch are kept; others dropped."""
    import json
    _seed_edge(
        ast_cache_conn,
        "caller",
        "fn_in_loop",
        kind="calls",
        metadata=json.dumps({"branch": {"kind": "loop"}}),
    )

    cache = FakeCacheWithConn([], [], [], ast_cache_conn)
    ev = Evaluator(cache)
    result = ev._filter_branch(
        [
            {"name": "fn_in_loop", "file": "f.py"},
            {"name": "fn_not_loop", "file": "f.py"},
        ],
        "loop",
    )
    assert _names(result) == ["fn_in_loop"]


# ===========================================================================
# Depth BFS test
# ===========================================================================

def test_eval_depth_bfs_callee(ast_cache_conn):
    """BFS in callee direction traverses A→B→C correctly."""
    id_a = _seed_sym(ast_cache_conn, "A")
    id_b = _seed_sym(ast_cache_conn, "B")
    id_c = _seed_sym(ast_cache_conn, "C")
    _seed_edge(ast_cache_conn, "A", "B", callee_symbol_id=id_b)
    _seed_edge(ast_cache_conn, "B", "C", callee_symbol_id=id_c)

    cache = FakeCacheWithConn([], [], [], ast_cache_conn)
    ev = Evaluator(cache)

    # depth 1-2: both B and C reachable
    result_2 = ev._eval_depth_bfs([id_a], "callee", 1, 2)
    assert id_b in result_2
    assert id_c in result_2

    # depth 1 only: just B
    result_1 = ev._eval_depth_bfs([id_a], "callee", 1, 1)
    assert id_b in result_1
    assert id_c not in result_1


# ===========================================================================
# Hit cap truncation test
# ===========================================================================

def test_eval_hit_cap_truncated():
    """Evaluator truncates at max_results and reports was_truncated correctly."""
    functions = [
        {"name": f"fn_{i}", "file": "f.py", "line": i, "language": "python"}
        for i in range(5)
    ]
    cache = FakeCache(functions, [], [])
    ev = Evaluator(cache, max_results=3)
    results = ev.eval(parse("*"))

    assert len(results) == 3
    assert ev.was_truncated() is True
    assert ev.total_matches() == 5


# ===========================================================================
# Reaches filter test
# ===========================================================================

def test_filter_reaches(ast_cache_conn):
    """_filter_reaches: only candidates that can reach the target are kept."""
    id_a = _seed_sym(ast_cache_conn, "A")
    id_b = _seed_sym(ast_cache_conn, "B")
    id_c = _seed_sym(ast_cache_conn, "C")
    _seed_edge(ast_cache_conn, "A", "B", callee_symbol_id=id_b)
    _seed_edge(ast_cache_conn, "B", "C", callee_symbol_id=id_c)

    cache = FakeCacheWithConn([], [], [], ast_cache_conn)
    ev = Evaluator(cache)

    from tree_sitter_analyzer.hyphae.ast import PseudoClass, SelectorList, SimpleSelector

    # pc for :reaches(#C){1,1} — direct callers of C only (depth 1)
    target_sl = SelectorList((SimpleSelector(base=("name", "C")),))
    pc = PseudoClass(name="reaches", arg=target_sl, depth_min=1, depth_max=1)

    cands = [
        {"name": "A", "file": "f.py"},
        {"name": "B", "file": "f.py"},
    ]
    result = ev._filter_reaches(cands, pc)
    # Only B directly calls C (1 hop); A is 2 hops away
    assert _names(result) == ["B"]


# ===========================================================================
# End-to-end _filter_edge_depth via selector evaluation (MED-3)
# ===========================================================================

def test_filter_edge_depth_via_selector(ast_cache_conn):
    """_filter_edge_depth exercised end-to-end through ev.eval(parse(...)).

    Selector '*:calls(#C){1,2}' means: all symbols that call C within 1-2 hops.
    Chain: A→B→C.  B calls C directly (depth 1); A calls C via B (depth 2).
    Expected: both A and B in results, C excluded.
    """
    id_a = _seed_sym(ast_cache_conn, "A")
    id_b = _seed_sym(ast_cache_conn, "B")
    id_c = _seed_sym(ast_cache_conn, "C")
    _seed_edge(ast_cache_conn, "A", "B", callee_symbol_id=id_b)
    _seed_edge(ast_cache_conn, "B", "C", callee_symbol_id=id_c)

    cache = FakeCacheWithConn(
        [
            {"name": "A", "file": "f.py", "line": 1, "language": "python"},
            {"name": "B", "file": "f.py", "line": 10, "language": "python"},
            {"name": "C", "file": "f.py", "line": 20, "language": "python"},
        ],
        [],
        [],
        ast_cache_conn,
    )
    ev = Evaluator(cache)

    # depth 1-2: A (2 hops) and B (1 hop) both call C within range
    results = ev.eval(parse("*:calls(#C){1,2}"))
    result_names = set(_names(results))
    assert "B" in result_names, "B calls C at depth 1, must be included"
    assert "A" in result_names, "A calls C at depth 2, must be included"
    assert "C" not in result_names, "C does not call itself"

    # depth 2 exact: only A (B is depth 1, excluded by depth_min=2)
    results_exact = ev.eval(parse("*:calls(#C){2,2}"))
    result_names_exact = set(_names(results_exact))
    assert "A" in result_names_exact, "A is exactly 2 hops from C"
    assert "B" not in result_names_exact, "B is 1 hop, outside {2,2}"
