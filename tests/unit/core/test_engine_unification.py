import asyncio

import pytest

from tree_sitter_analyzer.api import get_engine
from tree_sitter_analyzer.core.analysis_engine import (
    AnalysisRequest,
    UnifiedAnalysisEngine,
)


def test_unified_engine_singleton():
    """Verify that UnifiedAnalysisEngine acts as a singleton."""
    engine1 = UnifiedAnalysisEngine()
    engine2 = UnifiedAnalysisEngine()
    assert engine1 is engine2


def test_unified_engine_sync_analysis(tmp_path):
    """Verify synchronous analysis of a file."""
    # Create a dummy Java file
    java_file = tmp_path / "Test.java"
    java_file.write_text("public class Test { public void hello() {} }")

    engine = get_engine()
    request = AnalysisRequest(file_path=str(java_file), language="java")

    result = engine.analyze_sync(request)
    assert result.success is True
    assert result.language == "java"
    assert len(result.elements) >= 2  # Class and Method


def test_unified_engine_analyze_code(tmp_path):
    """Verify code string analysis."""
    code = "def hello(): print('world')"
    engine = get_engine()

    # Write code to temporary file
    py_file = tmp_path / "test_code.py"
    py_file.write_text(code)

    result = asyncio.run(
        engine.analyze(
            AnalysisRequest(
                file_path=str(py_file),
                language="python",
            )
        )
    )
    assert result.success is True
    assert result.language == "python"
    assert any(el.name == "hello" for el in result.elements)


def test_unified_engine_query_execution(tmp_path):
    """Verify post-processing query execution."""
    py_file = tmp_path / "test.py"
    py_file.write_text("def my_func(): pass")

    engine = get_engine()
    request = AnalysisRequest(
        file_path=str(py_file),
        language="python",
        queries=["function"],
        include_queries=True,
    )

    result = engine.analyze_sync(request)
    assert result.success is True
    assert "function" in result.query_results
    assert len(result.query_results["function"]) > 0


def test_unified_engine_nonexistent_file():
    """Verify FileNotFoundError is raised for missing files."""
    engine = get_engine()
    request = AnalysisRequest(file_path="nonexistent_file.java", language="java")

    with pytest.raises(FileNotFoundError):
        engine.analyze_sync(request)


def test_unified_engine_compatibility_properties():
    """Verify compatibility properties for API/MCP layer."""
    engine = get_engine()

    # Check properties
    assert hasattr(engine, "language_detector")
    assert hasattr(engine, "plugin_manager")
    assert hasattr(engine, "parser")
    assert hasattr(engine, "query_executor")

    # Check methods
    assert hasattr(engine, "get_available_queries")
    assert hasattr(engine, "get_supported_languages")
    assert hasattr(engine, "analyze_sync")
