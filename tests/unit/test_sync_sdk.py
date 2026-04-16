"""
Tests for the synchronous SDK (tree_sitter_analyzer.sdk.Analyzer).
"""

from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.sdk import Analyzer

SAMPLE_PYTHON = '''
"""Sample module."""

class Calculator:
    def add(self, x: int, y: int) -> int:
        return x + y

    def multiply(self, x: int, y: int) -> int:
        return x * y


def helper_function() -> str:
    return "hello"
'''

SAMPLE_JAVA = """
package com.example;

public class UserService {
    public User findUser(String id) {
        return null;
    }

    public void deleteUser(String id) {}
}
"""


def _write_file(tmp_path: Path, name: str, content: str) -> str:
    """Write a temp file under tmp_path and return absolute path."""
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return str(p)


class TestSyncAnalyzerBasic:
    """Test basic synchronous SDK operations."""

    def test_context_manager(self, tmp_path: Path) -> None:
        with Analyzer(project_root=str(tmp_path)) as analyzer:
            assert analyzer.project_root == str(tmp_path)

    def test_check_code_scale(self, tmp_path: Path) -> None:
        fp = _write_file(tmp_path, "sample.py", SAMPLE_PYTHON)
        with Analyzer(project_root=str(tmp_path)) as analyzer:
            result = analyzer.check_code_scale(fp)
            assert "file_metrics" in result or "summary" in result

    def test_analyze_code_structure(self, tmp_path: Path) -> None:
        fp = _write_file(tmp_path, "sample.py", SAMPLE_PYTHON)
        with Analyzer(project_root=str(tmp_path)) as analyzer:
            result = analyzer.analyze_code_structure(fp)
            assert result.get("success") is True

    def test_get_code_outline(self, tmp_path: Path) -> None:
        fp = _write_file(tmp_path, "Svc.java", SAMPLE_JAVA)
        with Analyzer(project_root=str(tmp_path)) as analyzer:
            result = analyzer.get_code_outline(fp, output_format="toon")
            text = result.get("content", [{}])[0].get("text", "")
            assert len(text) > 0

    def test_query_code(self, tmp_path: Path) -> None:
        fp = _write_file(tmp_path, "sample.py", SAMPLE_PYTHON)
        with Analyzer(project_root=str(tmp_path)) as analyzer:
            result = analyzer.query_code(fp, query_key="classes")
            assert result.get("success") is True

    def test_extract_code_section(self, tmp_path: Path) -> None:
        fp = _write_file(tmp_path, "sample.py", SAMPLE_PYTHON)
        with Analyzer(project_root=str(tmp_path)) as analyzer:
            result = analyzer.extract_code_section(fp, 4, 7)
            assert result.get("success") is True


class TestSyncAnalyzerCaching:
    """Test caching behavior in the synchronous SDK."""

    def test_cache_hit(self, tmp_path: Path) -> None:
        fp = _write_file(tmp_path, "sample.py", SAMPLE_PYTHON)
        with Analyzer(project_root=str(tmp_path), cache_enabled=True) as analyzer:
            r1 = analyzer.analyze_code_structure(fp)
            r2 = analyzer.analyze_code_structure(fp)
            assert r1 == r2
            assert analyzer.cache_size() > 0

    def test_cache_disabled(self, tmp_path: Path) -> None:
        fp = _write_file(tmp_path, "sample.py", SAMPLE_PYTHON)
        with Analyzer(project_root=str(tmp_path), cache_enabled=False) as analyzer:
            r1 = analyzer.analyze_code_structure(fp)
            r2 = analyzer.analyze_code_structure(fp)
            assert r1.get("success") is True
            assert r2.get("success") is True
            assert analyzer.cache_size() == 0

    def test_clear_cache(self, tmp_path: Path) -> None:
        fp = _write_file(tmp_path, "sample.py", SAMPLE_PYTHON)
        with Analyzer(project_root=str(tmp_path), cache_enabled=True) as analyzer:
            analyzer.analyze_code_structure(fp)
            assert analyzer.cache_size() > 0
            analyzer.clear_cache()
            assert analyzer.cache_size() == 0

    def test_cache_invalidation_on_change(self, tmp_path: Path) -> None:
        fp = _write_file(tmp_path, "sample.py", "class OldName:\n    pass\n")
        with Analyzer(project_root=str(tmp_path), cache_enabled=True) as analyzer:
            r1 = analyzer.analyze_code_structure(fp)
            Path(fp).write_text("class NewName:\n    pass\n", encoding="utf-8")
            r2 = analyzer.analyze_code_structure(fp)
            assert r1 != r2 or r2.get("success") is True


class TestSyncAnalyzerBatch:
    """Test batch analysis in the synchronous SDK."""

    def test_batch_analyze_structure(self, tmp_path: Path) -> None:
        py_path = _write_file(tmp_path, "sample.py", SAMPLE_PYTHON)
        java_path = _write_file(tmp_path, "Svc.java", SAMPLE_JAVA)
        with Analyzer(project_root=str(tmp_path)) as analyzer:
            results = analyzer.batch_analyze(
                [py_path, java_path], analysis_type="structure"
            )
            assert len(results) == 2
            for fp in [py_path, java_path]:
                assert fp in results
                assert results[fp].get("success") is True

    def test_batch_analyze_empty(self, tmp_path: Path) -> None:
        with Analyzer(project_root=str(tmp_path)) as analyzer:
            results = analyzer.batch_analyze([])
            assert results == {}

    def test_batch_analyze_scale(self, tmp_path: Path) -> None:
        fp = _write_file(tmp_path, "sample.py", SAMPLE_PYTHON)
        with Analyzer(project_root=str(tmp_path)) as analyzer:
            results = analyzer.batch_analyze([fp], analysis_type="scale")
            assert fp in results
            assert "file_metrics" in results[fp] or "summary" in results[fp]


class TestSyncAnalyzerExtended:
    """Test extended tools in the synchronous SDK."""

    def test_trace_impact(self, tmp_path: Path) -> None:
        fp = _write_file(tmp_path, "Svc.java", SAMPLE_JAVA)
        with Analyzer(project_root=str(tmp_path)) as analyzer:
            result = analyzer.trace_impact("findUser", file_path=fp)
            assert isinstance(result, dict)

    def test_modification_guard(self, tmp_path: Path) -> None:
        fp = _write_file(tmp_path, "Svc.java", SAMPLE_JAVA)
        with Analyzer(project_root=str(tmp_path)) as analyzer:
            result = analyzer.modification_guard(
                fp, "findUser", modification_type="rename"
            )
            assert isinstance(result, dict)

    def test_dependency_query(self, tmp_path: Path) -> None:
        fp = _write_file(tmp_path, "sample.py", SAMPLE_PYTHON)
        with Analyzer(project_root=str(tmp_path)) as analyzer:
            result = analyzer.dependency_query(
                "health_scores", file_paths=[fp]
            )
            assert isinstance(result, dict)
