"""Tests for Circular Dependency Detector."""
from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.circular_dependency import (
    CircularDependencyAnalyzer,
    CircularDependencyResult,
    ImportEdge,
)


@pytest.fixture
def analyzer() -> CircularDependencyAnalyzer:
    return CircularDependencyAnalyzer()


def _write_tmp(content: str, suffix: str, prefix: str = "test_") -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, prefix=prefix, delete=False, dir="/tmp")
    f.write(textwrap.dedent(content))
    f.close()
    return Path(f.name)


def _write_dir(files: dict[str, str]) -> Path:
    d = Path(tempfile.mkdtemp(dir="/tmp"))
    for name, content in files.items():
        (d / name).write_text(textwrap.dedent(content))
    return d


# --- Python tests ---

class TestPythonCircularDependency:
    def test_no_cycle_single_file(self, analyzer: CircularDependencyAnalyzer) -> None:
        path = _write_tmp("""
            import os
            def foo():
                pass
        """, ".py")
        result = analyzer.analyze_file(path)
        assert result.total_cycles == 0

    def test_self_import_cycle(self, analyzer: CircularDependencyAnalyzer) -> None:
        d = _write_dir({
            "a.py": "import b\n",
            "b.py": "import a\n",
        })
        result = analyzer.analyze_project(d)
        assert result.total_cycles >= 1

    def test_three_way_cycle(self, analyzer: CircularDependencyAnalyzer) -> None:
        d = _write_dir({
            "a.py": "import b\n",
            "b.py": "import c\n",
            "c.py": "import a\n",
        })
        result = analyzer.analyze_project(d)
        assert result.total_cycles >= 1

    def test_no_cycle_linear(self, analyzer: CircularDependencyAnalyzer) -> None:
        d = _write_dir({
            "a.py": "import b\n",
            "b.py": "import c\n",
            "c.py": "",
        })
        result = analyzer.analyze_project(d)
        assert result.total_cycles == 0

    def test_from_import_detected(self, analyzer: CircularDependencyAnalyzer) -> None:
        d = _write_dir({
            "a.py": "from b import foo\n",
            "b.py": "import a\n",
        })
        result = analyzer.analyze_project(d)
        assert result.total_cycles >= 1

    def test_extracts_import_edges(self, analyzer: CircularDependencyAnalyzer) -> None:
        path = _write_tmp("""
            import os
            import sys
            from pathlib import Path
        """, ".py")
        edges = analyzer.extract_imports(path)
        assert isinstance(edges, list)
        names = [e.target_module for e in edges]
        assert "os" in names
        assert "sys" in names
        assert "pathlib" in names


# --- JavaScript tests ---

class TestJSCircularDependency:
    def test_js_require_cycle(self, analyzer: CircularDependencyAnalyzer) -> None:
        d = _write_dir({
            "a.js": "const b = require('./b');\n",
            "b.js": "const a = require('./a');\n",
        })
        result = analyzer.analyze_project(d)
        assert result.total_cycles >= 1

    def test_js_es6_import_cycle(self, analyzer: CircularDependencyAnalyzer) -> None:
        d = _write_dir({
            "a.js": "import { foo } from './b';\n",
            "b.js": "import { bar } from './a';\n",
        })
        result = analyzer.analyze_project(d)
        assert result.total_cycles >= 1

    def test_js_no_cycle(self, analyzer: CircularDependencyAnalyzer) -> None:
        d = _write_dir({
            "a.js": "const b = require('./b');\n",
            "b.js": "",
        })
        result = analyzer.analyze_project(d)
        assert result.total_cycles == 0

    def test_ts_import_cycle(self, analyzer: CircularDependencyAnalyzer) -> None:
        d = _write_dir({
            "a.ts": "import { foo } from './b';\n",
            "b.ts": "import { bar } from './a';\n",
        })
        result = analyzer.analyze_project(d)
        assert result.total_cycles >= 1


# --- Result structure ---

class TestResultStructure:
    def test_result_has_fields(self) -> None:
        result = CircularDependencyResult(root_path="/tmp")
        assert result.root_path == "/tmp"
        assert result.total_cycles == 0
        assert result.cycles == []
        assert result.edges == []

    def test_to_dict(self) -> None:
        result = CircularDependencyResult(root_path="/tmp")
        d = result.to_dict()
        assert "root_path" in d
        assert "total_cycles" in d
        assert "cycles" in d
        assert "edges" in d

    def test_import_edge(self) -> None:
        edge = ImportEdge(
            source_file="a.py",
            target_module="b",
            line_number=1,
            import_type="import",
        )
        assert edge.source_file == "a.py"
        assert edge.target_module == "b"

    def test_unsupported_file(self, analyzer: CircularDependencyAnalyzer) -> None:
        path = _write_tmp("data", ".csv")
        result = analyzer.analyze_file(path)
        assert result.total_cycles == 0
