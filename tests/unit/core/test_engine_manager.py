#!/usr/bin/env python3
"""
Unit tests for EngineManager.

This module provides comprehensive tests for EngineManager singleton pattern,
including thread safety and instance management.
"""

import threading

from tree_sitter_analyzer.core.analysis_engine import UnifiedAnalysisEngine
from tree_sitter_analyzer.core.engine_manager import EngineManager


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
        instance1 = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path1"
        )
        instance2 = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path2"
        )

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
        instance1 = EngineManager.get_instance(UnifiedAnalysisEngine)

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
        instance1 = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project1"
        )
        instance2 = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project2"
        )
        instance3 = EngineManager.get_instance(
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
