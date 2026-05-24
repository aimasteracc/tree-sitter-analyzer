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
