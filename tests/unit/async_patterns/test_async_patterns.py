"""
Tests for Async Pattern Analyzer - Python core.
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.async_patterns import (
    AsyncPatternAnalyzer,
    AsyncPatternResult,
    AsyncPatternType,
    PatternSeverity,
)


@pytest.fixture
def analyzer() -> AsyncPatternAnalyzer:
    return AsyncPatternAnalyzer()


def _write_tmp(content: str, suffix: str = ".py") -> Path:
    """Write content to a temp file and return its path."""
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False, mode="w")
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)


# --- Python: async without await ---


class TestPythonAsyncWithoutAwait:
    def test_async_function_with_await_ok(self, analyzer: AsyncPatternAnalyzer) -> None:
        code = """
import asyncio

async def fetch_data():
    result = await asyncio.sleep(1)
    return result
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        assert result.total_async_functions == 1
        assert not any(
            p.pattern_type == AsyncPatternType.ASYNC_WITHOUT_AWAIT
            for p in result.patterns
        )

    def test_async_function_without_await(self, analyzer: AsyncPatternAnalyzer) -> None:
        code = """
async def compute():
    return 42
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        assert result.total_async_functions == 1
        warnings = [
            p for p in result.patterns
            if p.pattern_type == AsyncPatternType.ASYNC_WITHOUT_AWAIT
        ]
        assert len(warnings) == 1
        assert "compute" in warnings[0].message
        assert warnings[0].severity == PatternSeverity.WARNING

    def test_multiple_async_functions(self, analyzer: AsyncPatternAnalyzer) -> None:
        code = """
async def good():
    await some_async_call()

async def bad():
    return 1 + 1

async def also_good():
    await another_call()
    return 42
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        assert result.total_async_functions == 3
        bad = [
            p for p in result.patterns
            if p.pattern_type == AsyncPatternType.ASYNC_WITHOUT_AWAIT
        ]
        assert len(bad) == 1
        assert "bad" in bad[0].message

    def test_sync_function_not_flagged(self, analyzer: AsyncPatternAnalyzer) -> None:
        code = """
def regular_function():
    return 42
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        assert result.total_async_functions == 0
        assert result.error_count == 0
        assert result.warning_count == 0


# --- Python: missing await ---


class TestPythonMissingAwait:
    def test_missing_await_on_asyncio_call(self, analyzer: AsyncPatternAnalyzer) -> None:
        code = """
import asyncio

async def fetch():
    asyncio.sleep(1)
    return "done"
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        missing = [
            p for p in result.patterns
            if p.pattern_type == AsyncPatternType.MISSING_AWAIT
        ]
        assert len(missing) >= 1
        assert missing[0].severity == PatternSeverity.ERROR

    def test_properly_awaited_call(self, analyzer: AsyncPatternAnalyzer) -> None:
        code = """
import asyncio

async def fetch():
    await asyncio.sleep(1)
    return "done"
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        missing = [
            p for p in result.patterns
            if p.pattern_type == AsyncPatternType.MISSING_AWAIT
        ]
        assert len(missing) == 0

    def test_asyncio_gather_missing_await(self, analyzer: AsyncPatternAnalyzer) -> None:
        code = """
import asyncio

async def fetch_all():
    asyncio.gather(task1(), task2())
    return "done"
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        missing = [
            p for p in result.patterns
            if p.pattern_type == AsyncPatternType.MISSING_AWAIT
        ]
        assert len(missing) >= 1


# --- Python: result structure ---


class TestAsyncResultStructure:
    def test_result_counts(self, analyzer: AsyncPatternAnalyzer) -> None:
        code = """
async def bad():
    return 1

async def ok():
    await asyncio.sleep(1)
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        assert isinstance(result, AsyncPatternResult)
        assert result.total_async_functions == 2
        assert result.total_await_expressions == 1
        assert result.warning_count >= 1

    def test_unknown_extension(self, analyzer: AsyncPatternAnalyzer) -> None:
        path = _write_tmp("x = 1", suffix=".txt")
        result = analyzer.analyze_file(path)
        assert result.language == "unknown"
        assert result.total_async_functions == 0

    def test_empty_file(self, analyzer: AsyncPatternAnalyzer) -> None:
        path = _write_tmp("", suffix=".py")
        result = analyzer.analyze_file(path)
        assert result.total_async_functions == 0
        assert len(result.patterns) == 0

    def test_pattern_match_fields(self, analyzer: AsyncPatternAnalyzer) -> None:
        code = """
async def no_await():
    return 42
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        assert len(result.patterns) >= 1
        p = result.patterns[0]
        assert p.file_path == str(path)
        assert p.line >= 1
        assert p.column >= 1
        assert p.language == "python"
        assert p.suggestion != ""

    def test_error_warning_info_counts(self, analyzer: AsyncPatternAnalyzer) -> None:
        code = """
import asyncio

async def bad():
    return 1

async def missing():
    asyncio.sleep(1)
    return 2
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        total = result.error_count + result.warning_count + result.info_count
        assert total == len(result.patterns)


# --- Python: edge cases ---


class TestPythonEdgeCases:
    def test_async_with_no_body(self, analyzer: AsyncPatternAnalyzer) -> None:
        code = "async def empty(): pass"
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        # Should handle gracefully
        assert result.total_async_functions == 1

    def test_nested_async_functions(self, analyzer: AsyncPatternAnalyzer) -> None:
        code = """
async def outer():
    async def inner():
        await asyncio.sleep(1)
    await inner()
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        assert result.total_async_functions >= 1

    def test_async_method_in_class(self, analyzer: AsyncPatternAnalyzer) -> None:
        code = """
class Service:
    async def fetch(self):
        return 42

    async def process(self):
        await asyncio.sleep(1)
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        assert result.total_async_functions == 2

    def test_async_with_for_loop(self, analyzer: AsyncPatternAnalyzer) -> None:
        code = """
async def process_items():
    async for item in aiter():
        pass
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        assert result.total_async_functions == 1

    def test_async_context_manager(self, analyzer: AsyncPatternAnalyzer) -> None:
        code = """
async def process():
    async with lock:
        await do_work()
"""
        path = _write_tmp(code)
        result = analyzer.analyze_file(path)
        assert result.total_async_functions == 1
        assert not any(
            p.pattern_type == AsyncPatternType.ASYNC_WITHOUT_AWAIT
            for p in result.patterns
        )
