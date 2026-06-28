#!/usr/bin/env python3
"""Manager-level engine tests extracted from consolidated `test_engine.py`."""

import os
import threading

import pytest

from tree_sitter_analyzer.core.analysis_engine import (
    AnalysisRequest,
    UnifiedAnalysisEngine,
    UnsupportedLanguageError,
    get_analysis_engine,
)
from tree_sitter_analyzer.core.engine_manager import EngineManager


class TestEngineManagerGetInstance:
    """Test cases for get_instance method."""

    __test__ = True

    def test_get_instance_default_project_root(self):
        """Test get_instance with default project root."""
        EngineManager.reset_instances()

        instance1 = EngineManager.get_instance(UnifiedAnalysisEngine)
        instance2 = EngineManager.get_instance(UnifiedAnalysisEngine)

        assert instance1 is instance2

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

        assert instance1 is instance2

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

        assert instance1 is not instance2

        EngineManager.reset_instances()

    def test_get_instance_none_project_root(self):
        """Test get_instance with None project root."""
        EngineManager.reset_instances()

        instance1 = EngineManager.get_instance(UnifiedAnalysisEngine, project_root=None)
        instance2 = EngineManager.get_instance(UnifiedAnalysisEngine, project_root=None)

        assert instance1 is instance2
        EngineManager.reset_instances()


class TestEngineManagerThreadSafety:
    """Test cases for thread safety."""

    __test__ = True

    def test_concurrent_get_instance(self):
        """Test concurrent calls to get_instance."""
        EngineManager.reset_instances()
        instances = []
        lock = threading.Lock()

        def create_instance():
            instance = EngineManager.get_instance(UnifiedAnalysisEngine)
            with lock:
                instances.append(instance)

        threads = [threading.Thread(target=create_instance) for _ in range(10)]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(instances) == 10
        assert all(inst is instances[0] for inst in instances)
        EngineManager.reset_instances()

    def test_double_checked_locking(self):
        """Test concurrent access does not create duplicate instances."""
        EngineManager.reset_instances()
        instances = []

        def create_instance():
            instance = EngineManager.get_instance(UnifiedAnalysisEngine)
            instances.append(instance)

        threads = [threading.Thread(target=create_instance) for _ in range(5)]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(instances) == 5
        assert all(inst is instances[0] for inst in instances)
        EngineManager.reset_instances()


class TestEngineManagerResetInstances:
    """Test cases for reset_instances method."""

    __test__ = True

    def test_reset_instances_clears_all(self):
        """Test that reset_instances clears all instances."""
        EngineManager.reset_instances()

        instance1 = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path1"
        )
        instance2 = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path2"
        )
        assert EngineManager._instances == {  # noqa: SLF001
            "/path1": instance1,
            "/path2": instance2,
        }

        EngineManager.reset_instances()
        assert EngineManager._instances == {}  # noqa: SLF001

        instance3 = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path1"
        )
        instance4 = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path2"
        )

        assert isinstance(instance3, UnifiedAnalysisEngine)
        assert isinstance(instance4, UnifiedAnalysisEngine)
        assert instance3 is not instance4
        assert instance3._project_root == "/path1"  # noqa: SLF001
        assert instance4._project_root == "/path2"  # noqa: SLF001
        assert EngineManager._instances == {  # noqa: SLF001
            "/path1": instance3,
            "/path2": instance4,
        }
        EngineManager.reset_instances()

    def test_reset_instances_thread_safety(self):
        """Test that reset_instances remains safe under concurrent access."""
        EngineManager.reset_instances()
        EngineManager.get_instance(UnifiedAnalysisEngine)
        instances = []
        lock = threading.Lock()

        def reset_and_create():
            EngineManager.reset_instances()
            instance = EngineManager.get_instance(UnifiedAnalysisEngine)
            with lock:
                instances.append(instance)

        threads = [threading.Thread(target=reset_and_create) for _ in range(5)]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(instances) == 5
        assert all(
            isinstance(instance, UnifiedAnalysisEngine) for instance in instances
        )
        assert set(EngineManager._instances) == {"default"}  # noqa: SLF001
        assert any(  # noqa: SLF001
            EngineManager._instances["default"] is instance for instance in instances
        )
        EngineManager.reset_instances()


class TestEngineManagerEdgeCases:
    """Test cases for edge cases."""

    __test__ = True

    def test_instance_key_generation(self):
        """Test instance key generation for falsy project roots."""
        EngineManager.reset_instances()

        instance1 = EngineManager.get_instance(UnifiedAnalysisEngine, project_root=None)
        instance2 = EngineManager.get_instance(UnifiedAnalysisEngine, project_root=None)
        assert instance1 is instance2

        instance3 = EngineManager.get_instance(UnifiedAnalysisEngine, project_root="")
        instance4 = EngineManager.get_instance(UnifiedAnalysisEngine, project_root="")
        assert instance3 is instance4

        assert instance1 is instance3
        EngineManager.reset_instances()

    def test_multiple_project_roots(self):
        """Test managing multiple separate project roots."""
        EngineManager.reset_instances()

        instance1 = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project1"
        )
        instance2 = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project2"
        )
        instance3 = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project3"
        )

        assert instance1 is not instance2
        assert instance2 is not instance3
        assert instance1 is not instance3

        instance1_again = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project1"
        )
        assert instance1 is instance1_again
        EngineManager.reset_instances()

    def test_reset_clears_all_project_roots(self):
        """Test reset clears all project-root-scoped instances."""
        EngineManager.reset_instances()

        EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project1"
        )
        EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project2"
        )
        EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project3"
        )
        EngineManager.reset_instances()

        instance1_new = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project1"
        )
        instance2_new = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project2"
        )
        instance3_new = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project3"
        )

        assert isinstance(instance1_new, UnifiedAnalysisEngine)
        assert isinstance(instance2_new, UnifiedAnalysisEngine)
        assert isinstance(instance3_new, UnifiedAnalysisEngine)
        assert instance1_new is not instance2_new
        assert instance2_new is not instance3_new
        assert instance1_new is not instance3_new
        assert instance1_new._project_root == "/path/to/project1"  # noqa: SLF001
        assert instance2_new._project_root == "/path/to/project2"  # noqa: SLF001
        assert instance3_new._project_root == "/path/to/project3"  # noqa: SLF001
        assert EngineManager._instances == {  # noqa: SLF001
            "/path/to/project1": instance1_new,
            "/path/to/project2": instance2_new,
            "/path/to/project3": instance3_new,
        }
        EngineManager.reset_instances()


class TestEngineSecurityRegression:
    """Regression tests for security boundaries"""

    __test__ = True

    @pytest.mark.asyncio
    async def test_path_traversal_prevention(self):
        """Path traversal attempts should still be blocked."""
        engine = get_analysis_engine(project_root=os.getcwd())
        request = AnalysisRequest(file_path="../../../../../etc/passwd")

        with pytest.raises(ValueError) as excinfo:
            await engine.analyze(request)

        assert "Invalid file path" in str(excinfo.value)
        assert "traversal" in str(excinfo.value).lower()

    @pytest.mark.asyncio
    async def test_unsupported_language_handling(self):
        """Unsupported languages should still surface the expected error."""
        engine = get_analysis_engine()
        request = AnalysisRequest(file_path="pyproject.toml", language="brainfuck")

        with pytest.raises(UnsupportedLanguageError):
            await engine.analyze(request)

    def test_singleton_engine_cleanup(self):
        """Cleanup should remain safe after refactoring."""
        engine = get_analysis_engine()
        engine.cleanup()


if __name__ == "__main__":
    pytest.main([__file__])
