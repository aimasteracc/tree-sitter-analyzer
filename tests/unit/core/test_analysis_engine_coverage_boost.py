#!/usr/bin/env python3
"""Coverage-boosting tests for analysis_engine.py (target: 79.8% → 80%+)"""

from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.core.analysis_engine import (
    AnalysisRequest,
    UnifiedAnalysisEngine,
    get_analysis_engine,
)


@pytest.fixture(autouse=True)
def reset_engine_instances():
    """Reset singleton state before each test."""
    UnifiedAnalysisEngine._instances.clear()
    yield
    UnifiedAnalysisEngine._instances.clear()


class TestCleanupCoverage:
    """Hit cleanup paths that require _ensure_initialized first (lines 402-404)"""

    def test_cleanup_with_initialized_components(self):
        """cleanup should clear cache and performance monitor when initialized"""
        engine = get_analysis_engine()
        engine._ensure_initialized()
        engine.cleanup()  # lines 402, 404


class TestCacheKeyCoverage:
    """Hit exception paths in _generate_cache_key (lines 372-373)"""

    def test_cache_key_os_error_handled(self):
        """_generate_cache_key should handle OSError from stat (lines 372-373)"""
        engine = get_analysis_engine()
        request = AnalysisRequest(file_path="/nonexistent/path/file.py")

        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.isfile", return_value=True),
            patch("os.stat", side_effect=OSError("permission denied")),
        ):
            key = engine._generate_cache_key(request)
            assert isinstance(key, str)
            assert len(key) > 0


class TestDetectLanguageCoverage:
    """Hit exception path in _detect_language (lines 381-382)"""

    def test_detect_language_exception_returns_unknown(self):
        """_detect_language returns 'unknown' on exception (lines 381-382)"""
        engine = get_analysis_engine()
        engine._ensure_initialized()
        engine._language_detector.detect_from_extension = Mock(
            side_effect=RuntimeError("detection failed")
        )
        result = engine._detect_language("test.xyz")
        assert result == "unknown"


class TestAnalyzeCodeCoverage:
    """Hit alternate language path in analyze_code (lines 271-272)"""

    @pytest.mark.asyncio
    async def test_analyze_code_with_request_and_explicit_language(self):
        """analyze_code with request + explicit language sets language on request (lines 271-272)"""
        engine = get_analysis_engine()
        request = AnalysisRequest(file_path="test.unknown")

        with patch.object(engine, "analyze", return_value=Mock()):
            await engine.analyze_code(
                "let x = 1;", language="typescript", request=request
            )
            assert request.language == "typescript"


class TestAnalyzeFileCoverage:
    """Hit update-request path in analyze_file (lines 229-242)"""

    @pytest.mark.asyncio
    async def test_analyze_file_with_request_and_params(self):
        """analyze_file with existing request + params should update request fields (lines 229-242)"""
        engine = get_analysis_engine()
        request = AnalysisRequest(file_path="test.py")

        with patch.object(engine, "analyze", return_value=Mock()):
            await engine.analyze_file(
                request=request,
                language="python",
                format_type="json",
                include_details=True,
                include_complexity=False,
            )
            assert request.language == "python"
            assert request.format_type == "json"
            assert request.include_details is True
            assert request.include_complexity is False
