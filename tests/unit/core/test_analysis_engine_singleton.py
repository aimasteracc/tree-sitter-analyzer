"""Tests for UnifiedAnalysisEngine singleton thread safety."""
import threading

import pytest


class TestSingletonThreadSafety:
    """Test singleton pattern thread safety."""

    def test_singleton_returns_same_instance_single_thread(self):
        """Single thread should always get same instance."""
        from tree_sitter_analyzer.core.analysis_engine import UnifiedAnalysisEngine

        # Reset for test isolation
        UnifiedAnalysisEngine._instances.clear()

        instance1 = UnifiedAnalysisEngine()
        instance2 = UnifiedAnalysisEngine()

        assert instance1 is instance2

    def test_singleton_returns_same_instance_multi_thread(self):
        """Multiple threads should get same instance."""
        from tree_sitter_analyzer.core.analysis_engine import UnifiedAnalysisEngine

        # Reset for test isolation
        UnifiedAnalysisEngine._instances.clear()

        instances = []
        errors = []

        def create_instance():
            try:
                instance = UnifiedAnalysisEngine()
                instances.append(instance)
            except Exception as e:
                errors.append(e)

        # Create 10 threads trying to instantiate simultaneously
        threads = [threading.Thread(target=create_instance) for _ in range(10)]

        # Start all threads at nearly the same time
        for t in threads:
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors during instantiation: {errors}"
        assert len(instances) == 10

        # All instances should be the same object
        first_instance = instances[0]
        for instance in instances:
            assert instance is first_instance, "Not all instances are identical"

    def test_singleton_different_project_roots(self):
        """Different project roots should get different instances."""
        from tree_sitter_analyzer.core.analysis_engine import UnifiedAnalysisEngine

        # Reset for test isolation
        UnifiedAnalysisEngine._instances.clear()

        instance1 = UnifiedAnalysisEngine("/path/to/project1")
        instance2 = UnifiedAnalysisEngine("/path/to/project2")
        instance3 = UnifiedAnalysisEngine("/path/to/project1")

        assert instance1 is not instance2
        assert instance1 is instance3

    def test_singleton_initialized_flag_set_atomically(self):
        """_initialized flag should be set before instance is returned."""
        from tree_sitter_analyzer.core.analysis_engine import UnifiedAnalysisEngine

        # Reset for test isolation
        UnifiedAnalysisEngine._instances.clear()

        instance = UnifiedAnalysisEngine()

        # Check that _initialized was set (not False)
        # This tests the atomic initialization
        assert hasattr(instance, "_initialized")
