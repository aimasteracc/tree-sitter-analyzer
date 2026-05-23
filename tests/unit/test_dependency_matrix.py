
from unittest.mock import MagicMock, patch

from tree_sitter_analyzer.dependency_matrix import (
    CouplingEntry,
    DependencyMatrix,
    DependencyMatrixResult,
    ModuleStats,
    _pair_key,
)


class TestPairKey:
    def test_ordering(self):
        assert _pair_key("b.py", "a.py") == ("a.py", "b.py")
        assert _pair_key("a.py", "b.py") == ("a.py", "b.py")

    def test_same(self):
        assert _pair_key("x.py", "x.py") == ("x.py", "x.py")


class TestCouplingEntry:
    def test_to_dict(self):
        e = CouplingEntry(file_a="a.py", file_b="b.py", import_count=3, call_count=2, score=8.0)
        d = e.to_dict()
        assert d["file_a"] == "a.py"
        assert d["import_count"] == 3
        assert d["score"] == 8.0


class TestModuleStats:
    def test_to_dict(self):
        s = ModuleStats(file="mod.py", afferent_coupling=5, efferent_coupling=3, instability=0.375)
        d = s.to_dict()
        assert d["afferent_coupling"] == 5
        assert d["instability"] == 0.375


class TestDependencyMatrixResult:
    def test_to_dict_empty(self):
        r = DependencyMatrixResult()
        d = r.to_dict()
        assert d["module_count"] == 0
        assert d["coupling_pair_count"] == 0


class TestDependencyMatrixBuild:
    def test_build_with_mock_cache(self, tmp_path):
        a_py = tmp_path / "a.py"
        a_py.write_text("from b import foo\n\ndef bar():\n    foo()\n")
        b_py = tmp_path / "b.py"
        b_py.write_text("def foo():\n    pass\n")

        mock_cache = MagicMock()
        mock_cache.get_imports.return_value = {
            "a.py": ["from b import foo"],
            "b.py": [],
        }
        mock_cache.get_call_edges.return_value = [
            {"source_file": "a.py", "target_file": "b.py"},
        ]
        mock_cache.close.return_value = None

        with patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache):
            dm = DependencyMatrix(str(tmp_path))
            result = dm.build()

        assert "a.py" in result.modules
        assert "b.py" in result.modules
        assert len(result.coupling_pairs) >= 1
        assert result.coupling_pairs[0].import_count >= 1

    def test_build_empty_cache(self, tmp_path):
        mock_cache = MagicMock()
        mock_cache.get_imports.return_value = {}
        mock_cache.get_call_edges.return_value = []
        mock_cache.close.return_value = None

        with patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache):
            dm = DependencyMatrix(str(tmp_path))
            result = dm.build()

        assert len(result.modules) == 0
        assert len(result.coupling_pairs) == 0

    def test_build_cache_failure(self, tmp_path):
        with patch("tree_sitter_analyzer.ast_cache.ASTCache", side_effect=Exception("no db")):
            dm = DependencyMatrix(str(tmp_path))
            result = dm.build()

        assert len(result.modules) == 0

    def test_coupling_between(self, tmp_path):
        mock_cache = MagicMock()
        mock_cache.get_imports.return_value = {
            "a.py": ["from b import x"],
            "b.py": ["from a import y"],
        }
        mock_cache.get_call_edges.return_value = []
        mock_cache.close.return_value = None

        with patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache):
            dm = DependencyMatrix(str(tmp_path))
            entry = dm.coupling_between("a.py", "b.py")

        assert entry is not None
        assert entry.import_count == 2

    def test_coupling_between_not_found(self, tmp_path):
        mock_cache = MagicMock()
        mock_cache.get_imports.return_value = {"a.py": []}
        mock_cache.get_call_edges.return_value = []
        mock_cache.close.return_value = None

        with patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache):
            dm = DependencyMatrix(str(tmp_path))
            entry = dm.coupling_between("a.py", "z.py")

        assert entry is None

    def test_most_coupled(self, tmp_path):
        mock_cache = MagicMock()
        mock_cache.get_imports.return_value = {
            "a.py": ["from b import x", "from c import y"],
            "b.py": ["from c import z"],
            "c.py": [],
        }
        mock_cache.get_call_edges.return_value = [
            {"source_file": "a.py", "target_file": "b.py"},
            {"source_file": "a.py", "target_file": "b.py"},
            {"source_file": "b.py", "target_file": "c.py"},
        ]
        mock_cache.close.return_value = None

        with patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache):
            dm = DependencyMatrix(str(tmp_path))
            top = dm.most_coupled(top_k=2)

        assert len(top) <= 2
        if len(top) >= 1:
            assert top[0].score > 0

    def test_unstable_modules(self, tmp_path):
        mock_cache = MagicMock()
        mock_cache.get_imports.return_value = {
            "a.py": ["from b import x", "from c import y", "from d import z"],
            "b.py": [],
            "c.py": [],
            "d.py": [],
        }
        mock_cache.get_call_edges.return_value = []
        mock_cache.close.return_value = None

        with patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache):
            dm = DependencyMatrix(str(tmp_path))
            unstable = dm.unstable_modules(threshold=0.7)

        assert any(m.file == "a.py" for m in unstable)

    def test_summary(self, tmp_path):
        mock_cache = MagicMock()
        mock_cache.get_imports.return_value = {
            "a.py": ["from b import x"],
            "b.py": [],
        }
        mock_cache.get_call_edges.return_value = []
        mock_cache.close.return_value = None

        with patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache):
            dm = DependencyMatrix(str(tmp_path))
            s = dm.summary()

        assert s["module_count"] >= 2
        assert s["coupling_pair_count"] >= 1

    def test_high_coupling_pairs(self, tmp_path):
        mock_cache = MagicMock()
        imports = {}
        for i in range(5):
            src = f"a{i}.py"
            imports[src] = [f"from b import x{j}" for j in range(5)]
        imports["b.py"] = []
        mock_cache.get_imports.return_value = imports
        mock_cache.get_call_edges.return_value = [
            {"source_file": f"a{i}.py", "target_file": "b.py"} for i in range(5)
        ]
        mock_cache.close.return_value = None

        with patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache):
            dm = DependencyMatrix(str(tmp_path))
            result = dm.build()

        assert len(result.high_coupling_pairs) >= 1


class TestDependencyMatrixSelfCallFilter:
    def test_self_edges_filtered(self, tmp_path):
        mock_cache = MagicMock()
        mock_cache.get_imports.return_value = {
            "a.py": ["from a import helper"],
        }
        mock_cache.get_call_edges.return_value = [
            {"source_file": "a.py", "target_file": "a.py"},
        ]
        mock_cache.close.return_value = None

        with patch("tree_sitter_analyzer.ast_cache.ASTCache", return_value=mock_cache):
            dm = DependencyMatrix(str(tmp_path))
            result = dm.build()

        assert len(result.coupling_pairs) == 0
