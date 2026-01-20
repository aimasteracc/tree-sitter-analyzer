#!/usr/bin/env python3
"""
True integration tests for UnifiedAnalysisEngine.
Covers real file analysis, caching, and multi-language support.
"""

from pathlib import Path

import pytest

from tree_sitter_analyzer.core.analysis_engine import (
    UnifiedAnalysisEngine,
    get_analysis_engine,
)
from tree_sitter_analyzer.core.request import AnalysisRequest


@pytest.fixture(autouse=True)
def reset_engine():
    """Ensure a clean slate for each test."""
    UnifiedAnalysisEngine._reset_instance()
    yield
    UnifiedAnalysisEngine._reset_instance()


class TestEngineIntegration:
    """End-to-end tests for the core engine logic."""

    @pytest.mark.asyncio
    async def test_analyze_python_example(self):
        # Use a real file from the repository
        file_path = Path("examples/sample.py").resolve()
        engine = get_analysis_engine(project_root=str(Path.cwd()))

        result = await engine.analyze_file(str(file_path))

        assert result.success is True
        assert result.language == "python"
        assert len(result.elements) > 0
        # Verify specific elements are found
        element_names = [e.name for e in result.elements]
        assert "Person" in element_names
        assert "Dog" in element_names

    @pytest.mark.asyncio
    async def test_cache_logic_integration(self):
        file_path = Path("examples/sample.py").resolve()
        engine = get_analysis_engine(project_root=str(Path.cwd()))

        # 1st run: Cache miss
        engine.clear_cache()
        res1 = await engine.analyze_file(str(file_path))

        # 2nd run: Cache hit
        res2 = await engine.analyze_file(str(file_path))

        assert res1.success is True
        assert res2.success is True
        # Logic check: result objects should be identical or equivalent
        assert res1.file_path == res2.file_path

        stats = engine.get_cache_stats()
        assert stats["hits"] >= 1

    @pytest.mark.asyncio
    async def test_analyze_java_example(self):
        file_path = Path("examples/BigService.java").resolve()
        engine = get_analysis_engine(project_root=str(Path.cwd()))

        result = await engine.analyze_file(str(file_path))

        assert result.success is True
        assert result.language == "java"
        assert "BigService" in [e.name for e in result.elements]

    @pytest.mark.asyncio
    async def test_analyze_with_complexity_integration(self):
        file_path = Path("examples/sample.py").resolve()
        engine = get_analysis_engine(project_root=str(Path.cwd()))

        request = AnalysisRequest(file_path=str(file_path), include_complexity=True)
        result = await engine.analyze(request)

        assert result.success is True
        # Verify that complexity data is actually present in elements
        found_function_with_complexity = False
        for element in result.elements:
            if element.element_type == "function":
                if (
                    hasattr(element, "complexity_score")
                    and element.complexity_score is not None
                ):
                    assert element.complexity_score >= 1
                    found_function_with_complexity = True

        assert found_function_with_complexity

    def test_sync_analyze_integration(self):
        file_path = Path("examples/sample.py").resolve()
        engine = get_analysis_engine(project_root=str(Path.cwd()))

        request = AnalysisRequest(file_path=str(file_path))
        result = engine.analyze_sync(request)
        assert result.success is True
        assert result.language == "python"
