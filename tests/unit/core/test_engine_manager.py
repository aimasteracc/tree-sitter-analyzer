#!/usr/bin/env python3
"""
Unit tests for EngineManager (TDD)
"""

from tree_sitter_analyzer.core.engine_manager import EngineManager


class MockEngine:
    """Mock engine class for testing"""

    def __init__(self, project_root=None):
        self.project_root = project_root


class TestEngineManager:
    """Test suite for EngineManager"""

    def setup_method(self):
        """Reset EngineManager before each test"""
        EngineManager.reset_instances()

    def test_singleton_basic(self):
        """Test basic singleton behavior"""
        instance1 = EngineManager.get_instance(MockEngine)
        instance2 = EngineManager.get_instance(MockEngine)
        assert instance1 is instance2
        assert instance1.project_root is None

    def test_singleton_per_root(self):
        """Test singleton separation per project root"""
        root1 = "/path/to/project1"
        root2 = "/path/to/project2"

        instance1 = EngineManager.get_instance(MockEngine, root1)
        instance2 = EngineManager.get_instance(MockEngine, root2)
        instance1_again = EngineManager.get_instance(MockEngine, root1)

        assert instance1 is not instance2
        assert instance1 is instance1_again
        assert instance1.project_root == root1
        assert instance2.project_root == root2

    def test_reset_instances(self):
        """Test resetting instances"""
        instance1 = EngineManager.get_instance(MockEngine)
        EngineManager.reset_instances()
        instance2 = EngineManager.get_instance(MockEngine)
        assert instance1 is not instance2
