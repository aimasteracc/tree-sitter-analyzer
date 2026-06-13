"""Tests for xref.py — AST-cache-backed cross-reference engine."""

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.xref import XRefEngine, XRefResult


@pytest.fixture
def indexed_project(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "a.py").write_text(
        "import b\n\ndef alpha():\n    b.beta()\n    gamma()\n\ndef gamma():\n    pass\n"
    )
    (project / "b.py").write_text(
        "def beta():\n    pass\n\ndef delta():\n    alpha()\n"
    )
    (project / "c.py").write_text(
        "from a import alpha\n\ndef epsilon():\n    alpha()\n"
    )
    cache = ASTCache(str(project))
    cache.index_project(max_files=100)
    return str(project), cache


class TestXRefEngineSymbol:
    def test_xref_definitions_use_shared_backend_and_file_filter(self):
        class MockCursor:
            def fetchone(self):
                return None

        class MockConn:
            def execute(self, *args, **kwargs):
                return MockCursor()

        class MockCache:
            def get_conn(self):
                return MockConn()

            def _get_conn(self):  # backward-compat alias
                return self.get_conn()

        cache = MockCache()

        class FakeBackend:
            def resolve_definitions(self, symbol):
                assert symbol == "target"
                return [
                    {
                        "name": "target",
                        "kind": "function",
                        "file": "a.py",
                        "language": "python",
                        "line": 1,
                        "end_line": 2,
                    },
                    {
                        "name": "target",
                        "kind": "function",
                        "file": "b.py",
                        "language": "python",
                        "line": 5,
                        "end_line": 6,
                    },
                ]

        result = XRefEngine(cache, backend=FakeBackend()).xref(
            "target",
            file_path="b.py",
            include_callers=False,
            include_callees=False,
            include_imports=False,
            include_file_deps=False,
        )

        assert [definition["file"] for definition in result.definitions] == ["b.py"]

    def test_xref_alpha(self, indexed_project):
        _, cache = indexed_project
        engine = XRefEngine(cache)
        result = engine.xref("alpha")
        assert isinstance(result, XRefResult)
        assert result.symbol == "alpha"
        assert result.data_source == "cache"
        assert len(result.definitions) >= 1
        assert result.definitions[0]["name"] == "alpha"
        assert result.definitions[0]["kind"] == "function"

    def test_xref_callers(self, indexed_project):
        _, cache = indexed_project
        engine = XRefEngine(cache)
        result = engine.xref(
            "alpha",
            include_callees=False,
            include_imports=False,
            include_file_deps=False,
        )
        caller_names = [c["name"] for c in result.callers]
        assert "delta" in caller_names or "epsilon" in caller_names

    def test_xref_callees(self, indexed_project):
        _, cache = indexed_project
        engine = XRefEngine(cache)
        result = engine.xref(
            "alpha",
            include_callers=False,
            include_imports=False,
            include_file_deps=False,
        )
        callee_names = [c["name"] for c in result.callees]
        assert "beta" in callee_names or "gamma" in callee_names

    def test_xref_import_dependents(self, indexed_project):
        _, cache = indexed_project
        engine = XRefEngine(cache)
        result = engine.xref(
            "alpha",
            include_callers=False,
            include_callees=False,
            include_file_deps=False,
        )
        dep_files = [d["file"] for d in result.import_dependents]
        assert any("c.py" in f for f in dep_files)

    def test_xref_file_path_filter(self, indexed_project):
        _, cache = indexed_project
        engine = XRefEngine(cache)
        result = engine.xref("beta", file_path="b.py")
        assert len(result.definitions) >= 1
        assert result.definitions[0]["file"] == "b.py"

    def test_xref_unknown_symbol(self, indexed_project):
        _, cache = indexed_project
        engine = XRefEngine(cache)
        result = engine.xref("nonexistent_function_xyz")
        assert len(result.definitions) == 0
        assert len(result.callers) == 0
        assert len(result.callees) == 0

    def test_xref_exclude_dimensions(self, indexed_project):
        _, cache = indexed_project
        engine = XRefEngine(cache)
        result = engine.xref(
            "alpha",
            include_callers=False,
            include_callees=False,
            include_imports=False,
            include_file_deps=False,
        )
        assert len(result.callers) == 0
        assert len(result.callees) == 0
        assert len(result.import_dependents) == 0
        assert len(result.file_dependents) == 0


class TestXRefEngineFile:
    def test_file_xref(self, indexed_project):
        _, cache = indexed_project
        engine = XRefEngine(cache)
        result = engine.file_xref("a.py")
        assert result["file"] == "a.py"
        assert result["symbol_count"] >= 2
        assert result["data_source"] == "cache"

    def test_file_xref_symbols(self, indexed_project):
        _, cache = indexed_project
        engine = XRefEngine(cache)
        result = engine.file_xref("a.py")
        names = [s["name"] for s in result["symbols"]]
        assert "alpha" in names
        assert "gamma" in names

    def test_file_xref_unknown(self, indexed_project):
        _, cache = indexed_project
        engine = XRefEngine(cache)
        result = engine.file_xref("nonexistent.py")
        assert result["symbol_count"] == 0

    def test_file_xref_inbound_callers_resolved(self, indexed_project):
        # #669 Codex P2: the file-mode inbound counts were structurally always 0
        # (caller query bound `file_path = ? AND file_path != ?`; file-dependent
        # query selected edges where THIS file is the caller, then discarded them
        # all). a.py defines alpha/gamma; b.delta() and c.epsilon() both call
        # alpha() from other files, so the real inbound count is exactly 2.
        _, cache = indexed_project
        engine = XRefEngine(cache)
        result = engine.file_xref("a.py")
        assert result["caller_count"] == 2
        caller_files = sorted(c["caller_file"] for c in result["callers"])
        assert caller_files == ["b.py", "c.py"]
        assert result["file_dependent_count"] == 2
        assert sorted(d["file"] for d in result["file_dependents"]) == ["b.py", "c.py"]

    def test_symbol_xref_file_dependents_resolved(self, indexed_project):
        # Same shared `_find_file_dependents` bug surfaced in symbol mode: alpha
        # is called from b.py and c.py, so file_dependents is exactly those two.
        _, cache = indexed_project
        engine = XRefEngine(cache)
        result = engine.xref("alpha")
        assert sorted(d["file"] for d in result.file_dependents) == ["b.py", "c.py"]

    def test_file_xref_excludes_same_name_resolved_to_other_file(self, tmp_path):
        # Codex P2 (round 2): bare callee_name matching over-counts when two
        # files define the same callable. a.py and b.py both define `helper`;
        # c.py calls the resolved `b.helper` (callee_resolved_file='b.py'). The
        # callee_resolved_file gate must keep c.py OUT of a.py's callers and IN
        # b.py's — name-only matching wrongly credited a.py with c.py.
        project = tmp_path / "proj_same_name"
        project.mkdir()
        (project / "a.py").write_text("def helper():\n    pass\n")
        (project / "b.py").write_text("def helper():\n    pass\n")
        (project / "c.py").write_text("import b\n\ndef caller():\n    b.helper()\n")
        cache = ASTCache(str(project))
        cache.index_project(max_files=100)
        engine = XRefEngine(cache)
        a_result = engine.file_xref("a.py")
        assert a_result["caller_count"] == 0
        assert a_result["file_dependent_count"] == 0
        b_result = engine.file_xref("b.py")
        assert b_result["caller_count"] == 1
        assert [c["caller_file"] for c in b_result["callers"]] == ["c.py"]
        assert [d["file"] for d in b_result["file_dependents"]] == ["c.py"]

    def test_file_xref_excludes_unresolved_stdlib_name_collision(self, tmp_path):
        # Codex P2 (round 4): the resolved-only gate must NOT fall back to
        # name-only for unresolved rows. a.py defines `format`; b.py calls
        # str.format via "x".format() — an unresolved edge (callee_name='format',
        # callee_resolved_file=''). It must NOT be credited to a.py, or every
        # file defining a common method name (format/get/items) over-reports its
        # blast radius.
        project = tmp_path / "proj_stdlib"
        project.mkdir()
        (project / "a.py").write_text("def format():\n    pass\n")
        (project / "b.py").write_text('def use():\n    return "x".format()\n')
        cache = ASTCache(str(project))
        cache.index_project(max_files=100)
        engine = XRefEngine(cache)
        a_result = engine.file_xref("a.py")
        assert a_result["caller_count"] == 0
        assert a_result["file_dependent_count"] == 0

    def test_file_xref_includes_methods(self, tmp_path):
        """Codex P2 on #314: class methods (kind='method') must appear in file
        xref, not be dropped by a function/class-only filter. A file with only
        a class + methods must report the methods, not just symbol_count=1."""
        project = tmp_path / "proj_methods"
        project.mkdir()
        (project / "svc.py").write_text(
            "class Service:\n"
            "    def handle(self):\n"
            "        pass\n\n"
            "    def process(self):\n"
            "        pass\n"
        )
        cache = ASTCache(str(project))
        cache.index_project(max_files=100)

        engine = XRefEngine(cache)
        result = engine.file_xref("svc.py")
        names = [s["name"] for s in result["symbols"]]
        assert "handle" in names, f"method missing from xref: {names}"
        assert "process" in names, f"method missing from xref: {names}"
        assert "Service" in names
        # class + 2 methods, all surfaced.
        assert result["symbol_count"] >= 3


class TestXRefResult:
    def test_to_dict_minimal(self):
        r = XRefResult(symbol="foo", file_path=None)
        d = r.to_dict()
        assert d["symbol"] == "foo"
        assert "file_path" not in d
        assert d["definition_count"] == 0
        assert d["data_source"] == "cache"

    def test_to_dict_full(self):
        r = XRefResult(
            symbol="bar",
            file_path="x.py",
            definitions=[{"name": "bar", "file": "x.py", "line": 1}],
            callers=[{"name": "baz", "file": "y.py", "line": 5}],
            callees=[],
            import_dependents=[{"file": "z.py", "imports_via": "from x import bar"}],
            file_dependents=[],
        )
        d = r.to_dict()
        assert d["file_path"] == "x.py"
        assert d["definition_count"] == 1
        assert d["caller_count"] == 1
        assert d["callee_count"] == 0
        assert d["import_dependent_count"] == 1
        assert len(d["definitions"]) == 1
        assert len(d["callers"]) == 1
        assert "callees" not in d
        assert len(d["import_dependents"]) == 1


class TestXRefEngineNoCache:
    def test_empty_cache(self, tmp_path):
        project = tmp_path / "empty"
        project.mkdir()
        (project / "x.py").write_text("def hello(): pass\n")
        cache = ASTCache(str(project))
        engine = XRefEngine(cache)
        result = engine.xref("hello")
        assert len(result.definitions) == 0
        assert result.data_source == "cache"
