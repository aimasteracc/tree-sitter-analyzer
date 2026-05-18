#!/usr/bin/env python3
"""
Unified tests for AnalysisEngine and related components.

This module consolidates all engine-related tests from:
- test_engine.py (original)
- test_engine_unification.py
- test_analysis_engine.py
- test_core_engine_comprehensive.py
- test_core_engine_extended.py
- test_engine_manager.py
- test_engine_security_regression.py

Total: 103 tests
"""

import pytest

from tests.unit.core._test_engine_test_mixin import (
    TestAnalysisEngineAnalyzeCodeComprehensiveTestMixin,
    TestAnalysisEngineAnalyzeFileComprehensiveTestMixin,
    TestAnalysisEngineConcurrencyTestMixin,
    TestAnalysisEngineConfigurationTestMixin,
    TestAnalysisEngineDetermineLanguageTestMixin,
    TestAnalysisEngineEdgeCasesTestMixin,
    TestAnalysisEngineHelperMethodsTestMixin,
    TestAnalysisEngineInitComprehensiveTestMixin,
    TestAnalysisEnginePerformanceExtendedTestMixin,
    TestAnalysisEnginePublicAPITestMixin,
    TestAnalysisEngineTestMixin,
    TestEngineManagerEdgeCasesTestMixin,
    TestEngineManagerGetInstanceTestMixin,
    TestEngineManagerResetInstancesTestMixin,
    TestEngineManagerThreadSafetyTestMixin,
    TestEngineSecurityRegressionTestMixin,
    TestMockLanguagePluginTestMixin,
    TestUnifiedAnalysisEngineAnalysisTestMixin,
    TestUnifiedAnalysisEngineCacheManagementTestMixin,
    TestUnifiedAnalysisEngineCleanupTestMixin,
    TestUnifiedAnalysisEngineInitTestMixin,
    TestUnifiedAnalysisEngineLanguageDetectionTestMixin,
    TestUnifiedAnalysisEnginePerformanceTestMixin,
    TestUnifiedAnalysisEnginePluginManagementTestMixin,
    TestUnifiedAnalysisEnginePropertiesTestMixin,
    TestUnifiedAnalysisEngineQueriesTestMixin,
    TestUnifiedAnalysisEngineSecurityTestMixin,
    TestUnifiedEngineAnalyzeCodeTestMixin,
    TestUnifiedEngineCompatibilityPropertiesTestMixin,
    TestUnifiedEngineNonexistentFileTestMixin,
    TestUnifiedEngineQueryExecutionTestMixin,
    TestUnifiedEngineSingletonTestMixin,
    TestUnifiedEngineSyncAnalysisTestMixin,
)
from tree_sitter_analyzer.core import AnalysisEngine
from tree_sitter_analyzer.core.analysis_engine import (
    UnifiedAnalysisEngine,
)

# =============================================================================
# Test Classes from test_engine.py (original)
# =============================================================================


@pytest.fixture
def engine():
    """Fixture to provide an AnalysisEngine instance."""
    return AnalysisEngine()


class TestAnalysisEngine(TestAnalysisEngineTestMixin):
    """Test cases for the core AnalysisEngine."""

    __test__ = True

    pass


# =============================================================================
# Test Classes from test_engine_unification.py
# =============================================================================


class TestUnifiedEngineSingleton(TestUnifiedEngineSingletonTestMixin):
    """Verify that UnifiedAnalysisEngine acts as a singleton."""

    __test__ = True

    pass


class TestUnifiedEngineSyncAnalysis(TestUnifiedEngineSyncAnalysisTestMixin):
    """Verify synchronous analysis of a file."""

    __test__ = True

    pass


class TestUnifiedEngineAnalyzeCode(TestUnifiedEngineAnalyzeCodeTestMixin):
    """Verify code string analysis."""

    __test__ = True

    pass


class TestUnifiedEngineQueryExecution(TestUnifiedEngineQueryExecutionTestMixin):
    """Verify post-processing query execution."""

    __test__ = True

    pass


class TestUnifiedEngineNonexistentFile(TestUnifiedEngineNonexistentFileTestMixin):
    """Verify FileNotFoundError is raised for missing files."""

    __test__ = True

    pass


class TestUnifiedEngineCompatibilityProperties(
    TestUnifiedEngineCompatibilityPropertiesTestMixin
):
    """Verify compatibility properties for API/MCP layer."""

    __test__ = True

    pass


# =============================================================================
# Test Classes from test_analysis_engine.py
# =============================================================================


class TestUnifiedAnalysisEngineInit(TestUnifiedAnalysisEngineInitTestMixin):
    """Test cases for UnifiedAnalysisEngine initialization and singleton pattern."""

    __test__ = True

    def setup_method(self):
        UnifiedAnalysisEngine._reset_instance()

    @classmethod
    def teardown_class(cls):
        """Clean up singleton instances."""
        UnifiedAnalysisEngine._reset_instance()


class TestUnifiedAnalysisEnginePluginManagement(
    TestUnifiedAnalysisEnginePluginManagementTestMixin
):
    """Test cases for plugin registration and management."""

    __test__ = True

    @classmethod
    def teardown_class(cls):
        """Clean up singleton instances."""
        UnifiedAnalysisEngine._reset_instance()


class TestUnifiedAnalysisEngineCacheManagement(
    TestUnifiedAnalysisEngineCacheManagementTestMixin
):
    """Test cases for cache operations."""

    __test__ = True

    @classmethod
    def teardown_class(cls):
        """Clean up singleton instances."""
        UnifiedAnalysisEngine._reset_instance()


class TestUnifiedAnalysisEngineLanguageDetection(
    TestUnifiedAnalysisEngineLanguageDetectionTestMixin
):
    """Test cases for language detection."""

    __test__ = True

    @classmethod
    def teardown_class(cls):
        """Clean up singleton instances."""
        UnifiedAnalysisEngine._reset_instance()


class TestUnifiedAnalysisEngineAnalysis(TestUnifiedAnalysisEngineAnalysisTestMixin):
    """Test cases for file and code analysis operations."""

    __test__ = True

    @classmethod
    def teardown_class(cls):
        """Clean up singleton instances."""
        UnifiedAnalysisEngine._reset_instance()


class TestUnifiedAnalysisEngineSecurity(TestUnifiedAnalysisEngineSecurityTestMixin):
    """Test cases for security validation."""

    __test__ = True

    @classmethod
    def teardown_class(cls):
        """Clean up singleton instances."""
        UnifiedAnalysisEngine._reset_instance()


class TestUnifiedAnalysisEngineQueries(TestUnifiedAnalysisEngineQueriesTestMixin):
    """Test cases for query execution."""

    __test__ = True

    @classmethod
    def teardown_class(cls):
        """Clean up singleton instances."""
        UnifiedAnalysisEngine._reset_instance()


class TestUnifiedAnalysisEngineCleanup(TestUnifiedAnalysisEngineCleanupTestMixin):
    """Test cases for resource cleanup."""

    __test__ = True

    @classmethod
    def teardown_class(cls):
        """Clean up singleton instances."""
        UnifiedAnalysisEngine._reset_instance()


class TestUnifiedAnalysisEnginePerformance(
    TestUnifiedAnalysisEnginePerformanceTestMixin
):
    """Test cases for performance monitoring."""

    __test__ = True

    @classmethod
    def teardown_class(cls):
        """Clean up singleton instances."""
        UnifiedAnalysisEngine._reset_instance()


class TestUnifiedAnalysisEngineProperties(TestUnifiedAnalysisEnginePropertiesTestMixin):
    """Test cases for engine property accessors."""

    __test__ = True

    @classmethod
    def teardown_class(cls):
        """Clean up singleton instances."""
        UnifiedAnalysisEngine._reset_instance()


class TestMockLanguagePlugin(TestMockLanguagePluginTestMixin):
    """Test cases for MockLanguagePlugin."""

    __test__ = True


# =============================================================================
# Test Classes from test_core_engine_comprehensive.py
# =============================================================================


class TestAnalysisEngineInitComprehensive(TestAnalysisEngineInitComprehensiveTestMixin):
    """Test AnalysisEngine initialization"""

    __test__ = True

    pass


@pytest.mark.asyncio
class TestAnalysisEngineAnalyzeFileComprehensive(
    TestAnalysisEngineAnalyzeFileComprehensiveTestMixin
):
    """Test analyze_file method"""

    __test__ = True

    pass


@pytest.mark.asyncio
class TestAnalysisEngineAnalyzeCodeComprehensive(
    TestAnalysisEngineAnalyzeCodeComprehensiveTestMixin
):
    """Test analyze_code method"""

    __test__ = True

    pass


class TestAnalysisEngineDetermineLanguage(TestAnalysisEngineDetermineLanguageTestMixin):
    """Test _determine_language method"""

    __test__ = True

    pass


class TestAnalysisEngineHelperMethods(TestAnalysisEngineHelperMethodsTestMixin):
    """Test helper methods"""

    __test__ = True

    pass


class TestAnalysisEnginePublicAPI(TestAnalysisEnginePublicAPITestMixin):
    """Test public API methods"""

    __test__ = True

    pass


class TestAnalysisEngineConcurrency(TestAnalysisEngineConcurrencyTestMixin):
    """Test concurrent analysis scenarios"""

    __test__ = True

    pass


# =============================================================================
# Test Classes from test_core_engine_extended.py
# =============================================================================


class TestAnalysisEngineEdgeCases(TestAnalysisEngineEdgeCasesTestMixin):
    """Test edge cases and error conditions in AnalysisEngine."""

    __test__ = True

    pass


class TestAnalysisEngineConfiguration(TestAnalysisEngineConfigurationTestMixin):
    """Test AnalysisEngine configuration and initialization."""

    __test__ = True

    pass


class TestAnalysisEnginePerformanceExtended(
    TestAnalysisEnginePerformanceExtendedTestMixin
):
    """Test AnalysisEngine performance characteristics."""

    __test__ = True

    pass


# =============================================================================
# Test Classes from test_engine_manager.py
# =============================================================================


class TestEngineManagerGetInstance(TestEngineManagerGetInstanceTestMixin):
    """Test cases for get_instance method."""

    __test__ = True

    pass


class TestEngineManagerThreadSafety(TestEngineManagerThreadSafetyTestMixin):
    """Test cases for thread safety."""

    __test__ = True

    pass


class TestEngineManagerResetInstances(TestEngineManagerResetInstancesTestMixin):
    """Test cases for reset_instances method."""

    __test__ = True

    pass


class TestEngineManagerEdgeCases(TestEngineManagerEdgeCasesTestMixin):
    """Test cases for edge cases."""

    __test__ = True

    pass


class TestEngineSecurityRegression(TestEngineSecurityRegressionTestMixin):
    """Regression tests for security boundaries"""

    __test__ = True

    pass


# =============================================================================
# Test Classes from test_engine_security_regression.py
# =============================================================================


if __name__ == "__main__":
    pytest.main([__file__])
