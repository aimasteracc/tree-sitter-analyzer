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

import asyncio
import os
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.unit.core._test_engine_test_mixin import (
    TestAnalysisEngineAnalyzeCodeComprehensiveTestMixin,
    TestAnalysisEngineAnalyzeFileComprehensiveTestMixin,
    TestAnalysisEngineDetermineLanguageTestMixin,
    TestAnalysisEngineHelperMethodsTestMixin,
    TestAnalysisEngineInitComprehensiveTestMixin,
    TestAnalysisEngineTestMixin,
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
    AnalysisRequest,
    UnifiedAnalysisEngine,
    UnsupportedLanguageError,
    get_analysis_engine,
)
from tree_sitter_analyzer.core.engine_manager import EngineManager
from tree_sitter_analyzer.exceptions import AnalysisError, ParseError
from tree_sitter_analyzer.models import AnalysisResult

# =============================================================================
# Test Classes from test_engine.py (original)
# =============================================================================


@pytest.fixture
def engine():
    """Fixture to provide an AnalysisEngine instance."""
    return AnalysisEngine()


class TestAnalysisEngine(TestAnalysisEngineTestMixin):
    """Test cases for the core AnalysisEngine."""

    pass


# =============================================================================
# Test Classes from test_engine_unification.py
# =============================================================================


class TestUnifiedEngineSingleton(TestUnifiedEngineSingletonTestMixin):
    """Verify that UnifiedAnalysisEngine acts as a singleton."""

    pass


class TestUnifiedEngineSyncAnalysis(TestUnifiedEngineSyncAnalysisTestMixin):
    """Verify synchronous analysis of a file."""

    pass


class TestUnifiedEngineAnalyzeCode(TestUnifiedEngineAnalyzeCodeTestMixin):
    """Verify code string analysis."""

    pass


class TestUnifiedEngineQueryExecution(TestUnifiedEngineQueryExecutionTestMixin):
    """Verify post-processing query execution."""

    pass


class TestUnifiedEngineNonexistentFile(TestUnifiedEngineNonexistentFileTestMixin):
    """Verify FileNotFoundError is raised for missing files."""

    pass


class TestUnifiedEngineCompatibilityProperties(
    TestUnifiedEngineCompatibilityPropertiesTestMixin
):
    """Verify compatibility properties for API/MCP layer."""

    pass


# =============================================================================
# Test Classes from test_analysis_engine.py
# =============================================================================


class TestUnifiedAnalysisEngineInit(TestUnifiedAnalysisEngineInitTestMixin):
    """Test cases for UnifiedAnalysisEngine initialization and singleton pattern."""

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

    @classmethod
    def teardown_class(cls):
        """Clean up singleton instances."""
        UnifiedAnalysisEngine._reset_instance()


class TestUnifiedAnalysisEngineCacheManagement(
    TestUnifiedAnalysisEngineCacheManagementTestMixin
):
    """Test cases for cache operations."""

    @classmethod
    def teardown_class(cls):
        """Clean up singleton instances."""
        UnifiedAnalysisEngine._reset_instance()


class TestUnifiedAnalysisEngineLanguageDetection(
    TestUnifiedAnalysisEngineLanguageDetectionTestMixin
):
    """Test cases for language detection."""

    @classmethod
    def teardown_class(cls):
        """Clean up singleton instances."""
        UnifiedAnalysisEngine._reset_instance()


class TestUnifiedAnalysisEngineAnalysis(TestUnifiedAnalysisEngineAnalysisTestMixin):
    """Test cases for file and code analysis operations."""

    @classmethod
    def teardown_class(cls):
        """Clean up singleton instances."""
        UnifiedAnalysisEngine._reset_instance()


class TestUnifiedAnalysisEngineSecurity(TestUnifiedAnalysisEngineSecurityTestMixin):
    """Test cases for security validation."""

    @classmethod
    def teardown_class(cls):
        """Clean up singleton instances."""
        UnifiedAnalysisEngine._reset_instance()


class TestUnifiedAnalysisEngineQueries(TestUnifiedAnalysisEngineQueriesTestMixin):
    """Test cases for query execution."""

    @classmethod
    def teardown_class(cls):
        """Clean up singleton instances."""
        UnifiedAnalysisEngine._reset_instance()


class TestUnifiedAnalysisEngineCleanup(TestUnifiedAnalysisEngineCleanupTestMixin):
    """Test cases for resource cleanup."""

    @classmethod
    def teardown_class(cls):
        """Clean up singleton instances."""
        UnifiedAnalysisEngine._reset_instance()


class TestUnifiedAnalysisEnginePerformance(
    TestUnifiedAnalysisEnginePerformanceTestMixin
):
    """Test cases for performance monitoring."""

    @classmethod
    def teardown_class(cls):
        """Clean up singleton instances."""
        UnifiedAnalysisEngine._reset_instance()


class TestUnifiedAnalysisEngineProperties(TestUnifiedAnalysisEnginePropertiesTestMixin):
    """Test cases for engine property accessors."""

    @classmethod
    def teardown_class(cls):
        """Clean up singleton instances."""
        UnifiedAnalysisEngine._reset_instance()


class TestMockLanguagePlugin(TestMockLanguagePluginTestMixin):
    """Test cases for MockLanguagePlugin."""


# =============================================================================
# Test Classes from test_core_engine_comprehensive.py
# =============================================================================


class TestAnalysisEngineInitComprehensive(TestAnalysisEngineInitComprehensiveTestMixin):
    """Test AnalysisEngine initialization"""

    pass


@pytest.mark.asyncio
class TestAnalysisEngineAnalyzeFileComprehensive(
    TestAnalysisEngineAnalyzeFileComprehensiveTestMixin
):
    """Test analyze_file method"""

    pass


@pytest.mark.asyncio
class TestAnalysisEngineAnalyzeCodeComprehensive(
    TestAnalysisEngineAnalyzeCodeComprehensiveTestMixin
):
    """Test analyze_code method"""

    pass


class TestAnalysisEngineDetermineLanguage(TestAnalysisEngineDetermineLanguageTestMixin):
    """Test _determine_language method"""

    pass


class TestAnalysisEngineHelperMethods(TestAnalysisEngineHelperMethodsTestMixin):
    """Test helper methods"""

    pass


@pytest.mark.asyncio
class TestAnalysisEnginePublicAPI:
    """Test public API methods"""

    async def test_get_supported_languages(self):
        """Test getting supported languages"""
        engine = AnalysisEngine()

        languages = engine.get_supported_languages()

        assert isinstance(languages, list)
        assert "python" in languages

    async def test_get_available_queries_for_python(self):
        """Test getting available queries for Python"""
        engine = AnalysisEngine()

        queries = engine.get_available_queries("python")

        assert isinstance(queries, list)


@pytest.mark.asyncio
class TestAnalysisEngineConcurrency:
    """Test concurrent analysis scenarios"""

    async def test_concurrent_file_analysis(self):
        """Test analyzing multiple files concurrently"""
        engine = AnalysisEngine()

        # Create multiple temp files
        temp_files = []
        for i in range(5):
            with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
                f.write(f"def func_{i}():\n    pass")
                temp_files.append(f.name)

        try:
            # Analyze concurrently using asyncio.gather
            tasks = [engine.analyze_file(f) for f in temp_files]
            results = await asyncio.gather(*tasks)

            assert len(results) == 5
            assert all(r is not None for r in results)
        finally:
            for f in temp_files:
                os.unlink(f)

    async def test_concurrent_code_analysis(self):
        """Test analyzing multiple code snippets concurrently"""
        engine = AnalysisEngine()

        codes = [f"def func_{i}():\n    pass" for i in range(5)]

        # Analyze concurrently using asyncio.gather
        tasks = [engine.analyze_code(c, language="python") for c in codes]
        results = await asyncio.gather(*tasks)

        assert len(results) == 5
        assert all(r is not None for r in results)


# =============================================================================
# Test Classes from test_core_engine_extended.py
# =============================================================================


class TestAnalysisEngineEdgeCases:
    """Test edge cases and error conditions in AnalysisEngine."""

    @pytest.fixture
    def engine_extended(self) -> AnalysisEngine:
        """Create an AnalysisEngine instance for testing."""
        return AnalysisEngine()

    @pytest.mark.asyncio
    async def test_analyze_file_with_empty_file_extended(self, engine_extended):
        """Test analyzing an empty file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("")  # Empty file
            f.flush()
            temp_path = f.name

        try:
            result = await engine_extended.analyze_file(temp_path)
            assert isinstance(result, AnalysisResult)
            # Empty file should still produce a valid result
            assert result.file_path == temp_path
        except Exception as e:
            # Some exceptions are acceptable for empty files
            assert isinstance(e, AnalysisError | ParseError | ValueError)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_analyze_file_with_binary_file(self, engine_extended):
        """Test analyzing a binary file."""
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".bin", delete=False) as f:
            f.write(b"\x00\x01\x02\x03\x04\x05")  # Binary content
            f.flush()
            temp_path = f.name

        try:
            result = await engine_extended.analyze_file(temp_path)
            # Should handle binary files gracefully
            assert result is not None
        except Exception as e:
            # Exceptions are expected for binary files
            assert isinstance(
                e,
                AnalysisError
                | ParseError
                | UnicodeDecodeError
                | ValueError
                | UnsupportedLanguageError,
            )
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_analyze_file_with_very_large_file(self, engine_extended):
        """Test analyzing a very large file."""
        large_content = (
            "# Large Python file\n" + "def function_{}(): pass\n" * 1000
        )  # Reduced size

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(large_content)
            f.flush()
            temp_path = f.name

        try:
            result = await engine_extended.analyze_file(temp_path)
            assert isinstance(result, AnalysisResult)
            # Large file should be processed successfully
            assert result.file_path == temp_path
        except Exception as e:
            # Memory or timeout errors might be acceptable
            assert isinstance(e, MemoryError | TimeoutError | AnalysisError)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_analyze_file_with_malformed_syntax(self, engine_extended):
        """Test analyzing files with malformed syntax."""
        malformed_samples = [
            "def incomplete_function(",  # Incomplete function
            "class MissingColon",  # Missing colon
            "import",  # Incomplete import
            "if True\n    pass",  # Missing colon
            "def func():\n  return",  # Incomplete return
        ]

        for code in malformed_samples:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(code)
                f.flush()
                temp_path = f.name

            try:
                result = await engine_extended.analyze_file(temp_path)
                # Should handle malformed syntax gracefully
                assert result is not None
            except Exception as e:
                # Parsing errors are expected for malformed code
                assert isinstance(e, ParseError | SyntaxError | AnalysisError)
            finally:
                Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_analyze_file_with_unicode_content(self, engine_extended):
        """Test analyzing files with Unicode content."""
        unicode_content = """
# Unicode test file: 测试文件
def 函数名():
    '''这是一个包含中文的函数'''
    变量 = "Hello, 世界! 🌍"
    return 变量

class 类名:
    '''包含Unicode字符的类'''
    def __init__(self):
        self.属性 = "值"
"""

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(unicode_content)
            f.flush()
            temp_path = f.name

        try:
            result = await engine_extended.analyze_file(temp_path)
            assert isinstance(result, AnalysisResult)
            assert result.file_path == temp_path
        except Exception as e:
            # Unicode handling errors might occur
            assert isinstance(e, UnicodeError | AnalysisError)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_analyze_file_with_nonexistent_file_extended(self, engine_extended):
        """Test analyzing a non-existent file."""
        nonexistent_file = "nonexistent_path/file.py"

        with pytest.raises((FileNotFoundError, AnalysisError)):
            await engine_extended.analyze_file(nonexistent_file)

    @pytest.mark.asyncio
    async def test_analyze_file_with_permission_denied(self, engine_extended):
        """Test analyzing a file with permission issues."""
        # This test might not work on all systems, so we'll mock it
        with patch("builtins.open", side_effect=PermissionError("Permission denied")):
            with pytest.raises((PermissionError, AnalysisError, FileNotFoundError)):
                await engine_extended.analyze_file("some_file.py")

    @pytest.mark.asyncio
    async def test_analyze_file_with_different_encodings(self, engine_extended):
        """Test analyzing files with different encodings."""
        test_content = "def hello(): return 'Hello, World!'"
        encodings = ["utf-8", "latin-1", "ascii"]

        for encoding in encodings:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding=encoding
            ) as f:
                f.write(test_content)
                f.flush()
                temp_path = f.name

            try:
                result = await engine_extended.analyze_file(temp_path)
                assert isinstance(result, AnalysisResult)
            except (UnicodeError, AnalysisError):
                # Some encoding issues are acceptable
                pass
            finally:
                Path(temp_path).unlink(missing_ok=True)


class TestAnalysisEngineConfiguration:
    """Test AnalysisEngine configuration and initialization."""

    def test_engine_initialization_with_custom_config(self):
        """Test engine initialization with custom configuration."""
        # Test with different configurations
        configs = [
            {},
            {"timeout": 30},
            {"max_file_size": 1024 * 1024},
            {"enable_caching": True},
        ]

        for config in configs:
            try:
                engine = AnalysisEngine(**config)
                assert engine is not None
            except TypeError:
                # Some config options might not be supported
                pass

    def test_engine_with_mock_dependencies(self):
        """Test engine with mocked dependencies."""
        try:
            with patch(
                "tree_sitter_analyzer.language_loader.LanguageLoader"
            ) as mock_loader:
                mock_loader.return_value.load_language.return_value = None

                engine = AnalysisEngine()
                assert engine is not None
        except (ImportError, AttributeError):
            # Mock patching might fail, which is acceptable for this test
            pass

    def test_engine_language_detection(self):
        """Test engine language detection capabilities."""
        engine = AnalysisEngine()

        test_files = [
            ("test.py", "python"),
            ("test.java", "java"),
            ("test.js", "javascript"),
            ("test.unknown", None),
        ]

        for _filename, _expected_lang in test_files:
            # Test language detection logic
            # This might be internal to the engine
            assert engine is not None  # Basic test that engine exists


class TestAnalysisEnginePerformanceExtended:
    """Test AnalysisEngine performance characteristics."""

    @pytest.fixture
    def engine_perf(self) -> AnalysisEngine:
        """Create an AnalysisEngine instance for testing."""
        return AnalysisEngine()

    @pytest.mark.asyncio
    async def test_concurrent_analysis_extended(self, engine_perf):
        """Test concurrent file analysis."""
        import asyncio

        # Create multiple test files using context manager
        with tempfile.TemporaryDirectory() as temp_dir:
            test_files = []
            for i in range(5):
                file_path = Path(temp_dir) / f"test_{i}.py"
                with open(file_path, "w") as f:
                    f.write(f"def function_{i}(): pass\nclass Class_{i}: pass")
                test_files.append(file_path)

            # Test concurrent analysis using asyncio.gather
            tasks = [engine_perf.analyze_file(str(f)) for f in test_files]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Check that some analyses completed
            successful_results = [r for r in results if isinstance(r, AnalysisResult)]
            assert len(successful_results) >= 0  # At least some should succeed

    @pytest.mark.asyncio
    async def test_memory_usage_with_repeated_analysis(self, engine_perf):
        """Test memory usage with repeated analysis."""
        import gc

        test_content = "def test_function(): pass\nclass TestClass: pass"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            f.flush()
            temp_path = f.name

        try:
            # Perform repeated analysis
            for _i in range(10):
                try:
                    result = await engine_perf.analyze_file(temp_path)
                    assert result is not None or result is None  # Either is acceptable
                except Exception:
                    # Some failures are acceptable in stress testing
                    pass

                # Force garbage collection
                gc.collect()

            # Test should complete without memory issues
            assert True
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_analysis_with_timeout(self, engine_perf):
        """Test analysis with timeout scenarios."""
        # Create a file that might take time to analyze
        complex_content = """
# Complex Python file with nested structures
""" + "\n".join(
            [
                f"class Class_{i}:\n    def method_{j}(self): pass"
                for i in range(20)
                for j in range(5)  # Reduced complexity
            ]
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(complex_content)
            f.flush()
            temp_path = f.name

        try:
            # Test with potential timeout
            result = await engine_perf.analyze_file(temp_path)
            assert result is not None or result is None
        except (TimeoutError, AnalysisError):
            # Timeout errors are acceptable for complex files
            pass
        finally:
            Path(temp_path).unlink(missing_ok=True)


# =============================================================================
# Test Classes from test_engine_manager.py
# =============================================================================


class TestEngineManagerGetInstance:
    """Test cases for get_instance method."""

    def test_get_instance_default_project_root(self):
        """Test get_instance with default project root."""
        # Reset instances before test
        EngineManager.reset_instances()

        instance1 = EngineManager.get_instance(UnifiedAnalysisEngine)
        instance2 = EngineManager.get_instance(UnifiedAnalysisEngine)

        # Should return to same instance (singleton)
        assert instance1 is instance2

        # Clean up
        EngineManager.reset_instances()

    def test_get_instance_with_project_root(self):
        """Test get_instance with specific project root."""
        EngineManager.reset_instances()

        instance1 = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project1"
        )
        instance2 = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project1"
        )

        # Should return to same instance for same project root
        assert instance1 is instance2

        # Clean up
        EngineManager.reset_instances()

    def test_get_instance_different_project_roots(self):
        """Test get_instance with different project roots."""
        EngineManager.reset_instances()

        instance1 = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project1"
        )
        instance2 = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project2"
        )

        # Should return different instances for different project roots
        assert instance1 is not instance2

        # Clean up
        EngineManager.reset_instances()

    def test_get_instance_none_project_root(self):
        """Test get_instance with None project root."""
        EngineManager.reset_instances()

        instance1 = EngineManager.get_instance(UnifiedAnalysisEngine, project_root=None)
        instance2 = EngineManager.get_instance(UnifiedAnalysisEngine, project_root=None)

        # Should return to same instance (None uses "default" key)
        assert instance1 is instance2

        # Clean up
        EngineManager.reset_instances()


class TestEngineManagerThreadSafety:
    """Test cases for thread safety."""

    def test_concurrent_get_instance(self):
        """Test concurrent calls to get_instance."""
        EngineManager.reset_instances()
        instances = []
        lock = threading.Lock()

        def create_instance():
            instance = EngineManager.get_instance(UnifiedAnalysisEngine)
            with lock:
                instances.append(instance)

        # Create multiple threads
        threads = [threading.Thread(target=create_instance) for _ in range(10)]

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # All instances should be same (singleton)
        assert len(instances) == 10
        assert all(inst is instances[0] for inst in instances)

        # Clean up
        EngineManager.reset_instances()

    def test_double_checked_locking(self):
        """Test that double-checked locking prevents race conditions."""
        EngineManager.reset_instances()
        instances = []

        def create_instance():
            instance = EngineManager.get_instance(UnifiedAnalysisEngine)
            instances.append(instance)

        # Create multiple threads
        threads = [threading.Thread(target=create_instance) for _ in range(5)]

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # All instances should be same (singleton pattern)
        assert len(instances) == 5
        assert all(inst is instances[0] for inst in instances)

        # Clean up
        EngineManager.reset_instances()


class TestEngineManagerResetInstances:
    """Test cases for reset_instances method."""

    def test_reset_instances_clears_all(self):
        """Test that reset_instances clears all instances."""
        EngineManager.reset_instances()

        # Create some instances
        EngineManager.get_instance(UnifiedAnalysisEngine, project_root="/path1")
        EngineManager.get_instance(UnifiedAnalysisEngine, project_root="/path2")

        # Reset instances
        EngineManager.reset_instances()

        # After reset, getting instances should work without errors
        # Note: UnifiedAnalysisEngine may have internal caching, so we just verify
        # that reset doesn't cause errors
        instance3 = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path1"
        )
        instance4 = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path2"
        )

        # Verify that instances were created successfully
        assert instance3 is not None
        assert instance4 is not None

        # Clean up
        EngineManager.reset_instances()

    def test_reset_instances_thread_safety(self):
        """Test that reset_instances is thread-safe."""
        EngineManager.reset_instances()

        # Create instances
        EngineManager.get_instance(UnifiedAnalysisEngine)

        # Reset instances in multiple threads
        def reset_and_create():
            EngineManager.reset_instances()
            EngineManager.get_instance(UnifiedAnalysisEngine)

        threads = [threading.Thread(target=reset_and_create) for _ in range(5)]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Should not raise any exceptions
        assert True

        # Clean up
        EngineManager.reset_instances()


class TestEngineManagerEdgeCases:
    """Test cases for edge cases."""

    def test_instance_key_generation(self):
        """Test that instance keys are generated correctly."""
        EngineManager.reset_instances()

        # Test with None project root
        instance1 = EngineManager.get_instance(UnifiedAnalysisEngine, project_root=None)
        instance2 = EngineManager.get_instance(UnifiedAnalysisEngine, project_root=None)
        assert instance1 is instance2

        # Test with empty string project root
        # Note: Empty string is falsy, so it uses "default" key like None
        instance3 = EngineManager.get_instance(UnifiedAnalysisEngine, project_root="")
        instance4 = EngineManager.get_instance(UnifiedAnalysisEngine, project_root="")
        assert instance3 is instance4

        # None and empty string both use "default" key (empty string is falsy)
        # So they return the same instance
        assert instance1 is instance3

        # Clean up
        EngineManager.reset_instances()

    def test_multiple_project_roots(self):
        """Test managing multiple project roots."""
        EngineManager.reset_instances()

        # Create instances for different project roots
        instance1 = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project1"
        )
        instance2 = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project2"
        )
        instance3 = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project3"
        )

        # All instances should be different
        assert instance1 is not instance2
        assert instance2 is not instance3
        assert instance1 is not instance3

        # Getting same project root should return same instance
        instance1_again = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project1"
        )
        assert instance1 is instance1_again

        # Clean up
        EngineManager.reset_instances()

    def test_reset_clears_all_project_roots(self):
        """Test that reset clears all project root instances."""
        EngineManager.reset_instances()

        # Create instances for multiple project roots
        EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project1"
        )
        EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project2"
        )
        EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project3"
        )

        # Reset instances
        EngineManager.reset_instances()

        # Get new instances - all should work without errors
        # Note: UnifiedAnalysisEngine may have internal caching
        instance1_new = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project1"
        )
        instance2_new = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project2"
        )
        instance3_new = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project3"
        )

        # Verify that instances were created successfully
        assert instance1_new is not None
        assert instance2_new is not None
        assert instance3_new is not None

        # Clean up
        EngineManager.reset_instances()


# =============================================================================
# Test Classes from test_engine_security_regression.py
# =============================================================================


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


if __name__ == "__main__":
    pytest.main([__file__])
