#!/usr/bin/env python3
"""
Regression tests for security boundaries in refactored engine
"""

import os

import pytest

from tree_sitter_analyzer.core.analysis_engine import (
    UnsupportedLanguageError,
    get_analysis_engine,
)
from tree_sitter_analyzer.core.request import AnalysisRequest


class TestEngineSecurityRegression:
    """Regression tests for security boundaries"""

    @pytest.mark.asyncio
    async def test_path_traversal_prevention(self):
        """Test that path traversal is still blocked after refactoring"""
        engine = get_analysis_engine(project_root=os.getcwd())

        # Test directory traversal attack
        request = AnalysisRequest(file_path="../../../../../etc/passwd")

        with pytest.raises(ValueError) as excinfo:
            await engine.analyze(request)

        assert "Invalid file path" in str(excinfo.value)
        assert "traversal" in str(excinfo.value).lower()

    @pytest.mark.asyncio
    async def test_unsupported_language_handling(self):
        """Test that unsupported languages are still handled correctly"""
        engine = get_analysis_engine()
        # Use a relative path to a file that exists
        relative_file = "pyproject.toml"
        request = AnalysisRequest(file_path=relative_file, language="brainfuck")

        with pytest.raises(UnsupportedLanguageError):
            await engine.analyze(request)

    def test_singleton_engine_cleanup(self):
        """Test that cleanup method works correctly after refactoring"""
        engine = get_analysis_engine()
        engine.cleanup()
        # Should not raise any exceptions
