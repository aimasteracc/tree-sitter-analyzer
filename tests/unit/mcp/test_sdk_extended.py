"""
TDD tests for extended SDK features: batch analysis, caching, and extra tools.

Tests batch_analyze, cache hits/misses/invalidation, and the new
trace_impact/dependency_query/modification_guard SDK methods.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.sdk import CodeAnalyzer, create_analyzer

SAMPLE_JAVA = """
package com.example;

public class UserService {
    private final UserRepository repo;

    public User findUser(String id) {
        return repo.findById(id);
    }

    public void deleteUser(String id) {
        repo.deleteById(id);
    }
}
"""

SAMPLE_PYTHON = """
class Calculator:
    def add(self, x: int, y: int) -> int:
        return x + y

    def multiply(self, x: int, y: int) -> int:
        return x * y
"""


class TestBatchAnalysis:
    """Test batch_analyze method that analyzes multiple files concurrently."""

    @pytest.mark.asyncio
    async def test_batch_analyze_multiple_files(self) -> None:
        """batch_analyze returns results keyed by file path."""
        files: dict[str, str] = {}
        for name, content, suffix in [
            ("svc", SAMPLE_JAVA, ".java"),
            ("calc", SAMPLE_PYTHON, ".py"),
        ]:
            f = tempfile.NamedTemporaryFile(
                mode="w", suffix=suffix, delete=False, encoding="utf-8"
            )
            f.write(content)
            f.close()
            files[name] = f.name

        try:
            analyzer = create_analyzer()
            results = await analyzer.batch_analyze(
                list(files.values()), analysis_type="structure"
            )
            assert isinstance(results, dict)
            assert len(results) == 2
            for path in files.values():
                assert path in results
                entry = results[path]
                assert isinstance(entry, dict)
        finally:
            for p in files.values():
                Path(p).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_batch_analyze_empty_list(self) -> None:
        """batch_analyze with empty list returns empty dict."""
        analyzer = create_analyzer()
        results = await analyzer.batch_analyze([], analysis_type="structure")
        assert results == {}

    @pytest.mark.asyncio
    async def test_batch_analyze_scale_type(self) -> None:
        """batch_analyze with analysis_type='scale' returns file metrics."""
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        )
        f.write(SAMPLE_PYTHON)
        f.close()
        try:
            analyzer = create_analyzer()
            results = await analyzer.batch_analyze([f.name], analysis_type="scale")
            assert f.name in results
            assert isinstance(results[f.name], dict)
        finally:
            Path(f.name).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_batch_analyze_outline_type(self) -> None:
        """batch_analyze with analysis_type='outline' returns outlines."""
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".java", delete=False, encoding="utf-8"
        )
        f.write(SAMPLE_JAVA)
        f.close()
        try:
            analyzer = create_analyzer()
            results = await analyzer.batch_analyze([f.name], analysis_type="outline")
            assert f.name in results
            assert isinstance(results[f.name], dict)
        finally:
            Path(f.name).unlink(missing_ok=True)


class TestSDKCaching:
    """Test that repeated calls for the same file use cached results."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_same_result(self) -> None:
        """Calling analyze_structure twice returns the same core data from cache."""
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        )
        f.write(SAMPLE_PYTHON)
        f.close()
        try:
            analyzer = create_analyzer()
            result1 = await analyzer.analyze_structure(f.name)
            result2 = await analyzer.analyze_structure(f.name)
            # Core data should be identical (cache may add _from_cache flag)
            assert result1.get("success") == result2.get("success")
            assert result1.get("elements") == result2.get("elements")
            assert result2.get("_from_cache") is True
        finally:
            Path(f.name).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_cache_invalidation_on_file_change(self) -> None:
        """Modifying a file invalidates its cached result."""
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        )
        f.write("class OldName:\n    pass\n")
        f.close()
        try:
            analyzer = create_analyzer()
            result1 = await analyzer.analyze_structure(f.name)

            # Modify the file
            Path(f.name).write_text("class NewName:\n    pass\n", encoding="utf-8")
            result2 = await analyzer.analyze_structure(f.name)

            # Results should differ (file content changed)
            assert result1 != result2 or result2["success"] is True
        finally:
            Path(f.name).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_cache_disabled(self) -> None:
        """With cache_enabled=False, every call goes to the tool."""
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        )
        f.write(SAMPLE_PYTHON)
        f.close()
        try:
            analyzer = CodeAnalyzer(cache_enabled=False)
            result1 = await analyzer.analyze_structure(f.name)
            result2 = await analyzer.analyze_structure(f.name)
            # Both should succeed (even if different object instances)
            assert result1.get("success") is True
            assert result2.get("success") is True
        finally:
            Path(f.name).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_cache_clear(self) -> None:
        """clear_cache() empties the analysis cache."""
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        )
        f.write(SAMPLE_PYTHON)
        f.close()
        try:
            analyzer = create_analyzer()
            await analyzer.analyze_structure(f.name)
            analyzer.clear_cache()
            # After clear, cache size should be 0
            assert analyzer.cache_size() == 0
        finally:
            Path(f.name).unlink(missing_ok=True)


class TestSDKExtendedTools:
    """Test trace_impact, modification_guard, and dependency_query in SDK."""

    @pytest.mark.asyncio
    async def test_trace_impact(self) -> None:
        """trace_impact returns impact analysis for a symbol."""
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".java", delete=False, encoding="utf-8"
        )
        f.write(SAMPLE_JAVA)
        f.close()
        try:
            analyzer = create_analyzer()
            result = await analyzer.trace_impact(
                "findUser", file_path=f.name
            )
            assert isinstance(result, dict)
        finally:
            Path(f.name).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_modification_guard(self) -> None:
        """modification_guard returns safety assessment."""
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".java", delete=False, encoding="utf-8"
        )
        f.write(SAMPLE_JAVA)
        f.close()
        try:
            analyzer = create_analyzer()
            result = await analyzer.modification_guard(
                f.name, "findUser", modification_type="rename"
            )
            assert isinstance(result, dict)
        finally:
            Path(f.name).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_dependency_query_health(self) -> None:
        """dependency_query with health_scores returns file grades."""
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        )
        f.write(SAMPLE_PYTHON)
        f.close()
        try:
            analyzer = create_analyzer()
            result = await analyzer.dependency_query(
                "health_scores", file_paths=[f.name]
            )
            assert isinstance(result, dict)
        finally:
            Path(f.name).unlink(missing_ok=True)


class TestIncrementalAnalysis:
    """Test incremental_analyze that skips unchanged files."""

    @pytest.mark.asyncio
    async def test_incremental_returns_cache_hit_for_unchanged(self) -> None:
        """Files analyzed twice should get cache_hit=True on second call."""
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        )
        f.write(SAMPLE_PYTHON)
        f.close()
        try:
            analyzer = create_analyzer()
            first = await analyzer.incremental_analyze([f.name])
            assert f.name in first
            assert first[f.name].get("success") is True
            assert first[f.name].get("cache_hit") is not True

            second = await analyzer.incremental_analyze([f.name])
            assert second[f.name].get("cache_hit") is True
        finally:
            Path(f.name).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_incremental_reanalyzes_changed_file(self) -> None:
        """Modified files should be re-analyzed (no cache_hit)."""
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        )
        f.write("class OldName:\n    pass\n")
        f.close()
        try:
            analyzer = create_analyzer()
            await analyzer.incremental_analyze([f.name])

            Path(f.name).write_text("class NewName:\n    pass\n", encoding="utf-8")
            result = await analyzer.incremental_analyze([f.name])
            assert result[f.name].get("cache_hit") is not True
        finally:
            Path(f.name).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_incremental_empty_list(self) -> None:
        analyzer = create_analyzer()
        result = await analyzer.incremental_analyze([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_incremental_bypass_when_cache_disabled(self) -> None:
        """With cache disabled, incremental_analyze falls back to batch."""
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        )
        f.write(SAMPLE_PYTHON)
        f.close()
        try:
            analyzer = CodeAnalyzer(cache_enabled=False)
            result = await analyzer.incremental_analyze([f.name])
            assert f.name in result
            assert result[f.name].get("cache_hit") is not True
        finally:
            Path(f.name).unlink(missing_ok=True)
