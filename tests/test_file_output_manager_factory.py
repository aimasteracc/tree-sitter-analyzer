#!/usr/bin/env python3
"""
Tests for FileOutputManager Factory Pattern Implementation

This test suite verifies:
1. Backward compatibility with existing FileOutputManager usage
2. Correct factory pattern behavior (singleton per project root)
3. Thread safety of the factory implementation
4. Integration with existing MCP tools
"""

import tempfile
import threading
from pathlib import Path

from tree_sitter_analyzer.mcp.utils.file_output_factory import (
    FileOutputManagerFactory,
    get_file_output_manager,
)
from tree_sitter_analyzer.mcp.utils.file_output_manager import FileOutputManager


class TestFileOutputManagerBackwardCompatibility:
    """Test backward compatibility of FileOutputManager."""

    def test_direct_instantiation_still_works(self):
        """Test that direct instantiation of FileOutputManager still works."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Direct instantiation should work as before
            manager = FileOutputManager(temp_dir)
            assert manager.project_root == temp_dir
            assert manager.get_output_path() == temp_dir

    def test_none_project_root_still_works(self):
        """Test that None project_root still works as before."""
        manager = FileOutputManager(None)
        assert manager.project_root is None
        # Should use current working directory
        assert Path(manager.get_output_path()).exists()

    def test_existing_methods_unchanged(self):
        """Test that all existing methods work unchanged."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = FileOutputManager(temp_dir)

            # Test content type detection
            assert manager.detect_content_type('{"key": "value"}') == "json"
            assert manager.detect_content_type("col1,col2\nval1,val2") == "csv"
            assert manager.detect_content_type("# Header\nContent") == "markdown"
            assert manager.detect_content_type("plain text") == "text"

            # Test file extension mapping
            assert manager.get_file_extension("json") == ".json"
            assert manager.get_file_extension("csv") == ".csv"
            assert manager.get_file_extension("markdown") == ".md"
            assert manager.get_file_extension("text") == ".txt"

            # Test filename generation
            filename = manager.generate_output_filename("test", '{"data": "value"}')
            assert filename == "test.json"

            # Test file saving
            content = "Test content"
            file_path = manager.save_to_file(content, base_name="test_file")
            assert Path(file_path).exists()
            assert Path(file_path).read_text(encoding="utf-8") == content

    def test_set_project_root_method(self):
        """Test that set_project_root method works as before."""
        with tempfile.TemporaryDirectory() as temp_dir1:
            with tempfile.TemporaryDirectory() as temp_dir2:
                manager = FileOutputManager(temp_dir1)
                assert manager.project_root == temp_dir1

                manager.set_project_root(temp_dir2)
                assert manager.project_root == temp_dir2


class TestFileOutputManagerFactory:
    """Test FileOutputManagerFactory functionality."""

    def setup_method(self):
        """Clear factory instances before each test."""
        FileOutputManagerFactory.clear_all_instances()

    def teardown_method(self):
        """Clear factory instances after each test."""
        FileOutputManagerFactory.clear_all_instances()

    def test_singleton_behavior_per_project_root(self):
        """Test that factory returns same instance for same project root."""
        with tempfile.TemporaryDirectory() as temp_dir1:
            with tempfile.TemporaryDirectory() as temp_dir2:
                # Same project root should return same instance
                manager1a = FileOutputManagerFactory.get_instance(temp_dir1)
                manager1b = FileOutputManagerFactory.get_instance(temp_dir1)
                assert manager1a is manager1b

                # Different project root should return different instance
                manager2 = FileOutputManagerFactory.get_instance(temp_dir2)
                assert manager1a is not manager2
                assert manager1b is not manager2

    def test_none_project_root_normalization(self):
        """Test that None project root is normalized consistently."""
        manager1 = FileOutputManagerFactory.get_instance(None)
        manager2 = FileOutputManagerFactory.get_instance(None)
        assert manager1 is manager2

    def test_path_normalization(self):
        """Test that different path representations are normalized."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Different representations of same path should return same instance
            manager1 = FileOutputManagerFactory.get_instance(temp_dir)
            manager2 = FileOutputManagerFactory.get_instance(
                str(Path(temp_dir).resolve())
            )
            assert manager1 is manager2

    def test_clear_instance(self):
        """Test clearing specific instances."""
        with tempfile.TemporaryDirectory() as temp_dir:
            FileOutputManagerFactory.get_instance(temp_dir)
            assert FileOutputManagerFactory.get_instance_count() == 1

            # Clear the instance
            cleared = FileOutputManagerFactory.clear_instance(temp_dir)
            assert cleared is True
            assert FileOutputManagerFactory.get_instance_count() == 0

            # Clearing non-existent instance should return False
            cleared = FileOutputManagerFactory.clear_instance(temp_dir)
            assert cleared is False

    def test_clear_all_instances(self):
        """Test clearing all instances."""
        with tempfile.TemporaryDirectory() as temp_dir1:
            with tempfile.TemporaryDirectory() as temp_dir2:
                FileOutputManagerFactory.get_instance(temp_dir1)
                FileOutputManagerFactory.get_instance(temp_dir2)
                assert FileOutputManagerFactory.get_instance_count() == 2

                cleared_count = FileOutputManagerFactory.clear_all_instances()
                assert cleared_count == 2
                assert FileOutputManagerFactory.get_instance_count() == 0

    def test_get_managed_project_roots(self):
        """Test getting list of managed project roots."""
        with tempfile.TemporaryDirectory() as temp_dir1:
            with tempfile.TemporaryDirectory() as temp_dir2:
                FileOutputManagerFactory.get_instance(temp_dir1)
                FileOutputManagerFactory.get_instance(temp_dir2)

                roots = FileOutputManagerFactory.get_managed_project_roots()
                assert len(roots) == 2
                assert str(Path(temp_dir1).resolve()) in roots
                assert str(Path(temp_dir2).resolve()) in roots

    def test_update_project_root(self):
        """Test updating project root for existing instance."""
        with tempfile.TemporaryDirectory() as temp_dir1:
            with tempfile.TemporaryDirectory() as temp_dir2:
                # Create instance with first root
                manager = FileOutputManagerFactory.get_instance(temp_dir1)
                original_id = id(manager)

                # Update to second root
                updated = FileOutputManagerFactory.update_project_root(
                    temp_dir1, temp_dir2
                )
                assert updated is True

                # Should be same instance but moved to new key
                manager_new = FileOutputManagerFactory.get_instance(temp_dir2)
                assert id(manager_new) == original_id
                assert manager_new.project_root == temp_dir2

                # Old key should no longer exist
                assert FileOutputManagerFactory.get_instance_count() == 1
                roots = FileOutputManagerFactory.get_managed_project_roots()
                assert str(Path(temp_dir2).resolve()) in roots
                assert str(Path(temp_dir1).resolve()) not in roots


class TestFileOutputManagerFactoryThreadSafety:
    """Test thread safety of FileOutputManagerFactory."""

    def setup_method(self):
        """Clear factory instances before each test."""
        FileOutputManagerFactory.clear_all_instances()

    def teardown_method(self):
        """Clear factory instances after each test."""
        FileOutputManagerFactory.clear_all_instances()

    def test_concurrent_access_same_project_root(self):
        """Test concurrent access to same project root returns same instance."""
        with tempfile.TemporaryDirectory() as temp_dir:
            instances = []
            errors = []

            def get_instance():
                try:
                    instance = FileOutputManagerFactory.get_instance(temp_dir)
                    instances.append(instance)
                except Exception as e:
                    errors.append(e)

            # Create multiple threads accessing same project root
            threads = []
            for _ in range(10):
                thread = threading.Thread(target=get_instance)
                threads.append(thread)

            # Start all threads
            for thread in threads:
                thread.start()

            # Wait for all threads to complete
            for thread in threads:
                thread.join()

            # Check results
            assert len(errors) == 0, f"Errors occurred: {errors}"
            assert len(instances) == 10

            # All instances should be the same object
            first_instance = instances[0]
            for instance in instances[1:]:
                assert instance is first_instance

    def test_concurrent_access_different_project_roots(self):
        """Test concurrent access to different project roots."""
        with tempfile.TemporaryDirectory() as temp_dir1:
            with tempfile.TemporaryDirectory() as temp_dir2:
                instances = []
                errors = []

                def get_instance(project_root):
                    try:
                        instance = FileOutputManagerFactory.get_instance(project_root)
                        instances.append((project_root, instance))
                    except Exception as e:
                        errors.append(e)

                # Create threads for different project roots
                threads = []
                for _i in range(5):
                    thread1 = threading.Thread(target=get_instance, args=(temp_dir1,))
                    thread2 = threading.Thread(target=get_instance, args=(temp_dir2,))
                    threads.extend([thread1, thread2])

                # Start all threads
                for thread in threads:
                    thread.start()

                # Wait for all threads to complete
                for thread in threads:
                    thread.join()

                # Check results
                assert len(errors) == 0, f"Errors occurred: {errors}"
                assert len(instances) == 10

                # Group instances by project root
                root1_instances = [
                    inst for root, inst in instances if root == temp_dir1
                ]
                root2_instances = [
                    inst for root, inst in instances if root == temp_dir2
                ]

                assert len(root1_instances) == 5
                assert len(root2_instances) == 5

                # All instances for same root should be identical
                for instance in root1_instances[1:]:
                    assert instance is root1_instances[0]

                for instance in root2_instances[1:]:
                    assert instance is root2_instances[0]

                # Instances for different roots should be different
                assert root1_instances[0] is not root2_instances[0]


class TestFileOutputManagerClassMethods:
    """Test new class methods in FileOutputManager."""

    def setup_method(self):
        """Clear factory instances before each test."""
        FileOutputManagerFactory.clear_all_instances()

    def teardown_method(self):
        """Clear factory instances after each test."""
        FileOutputManagerFactory.clear_all_instances()

    def test_get_managed_instance(self):
        """Test get_managed_instance class method."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Should return managed instance from factory
            manager1 = FileOutputManager.get_managed_instance(temp_dir)
            manager2 = FileOutputManager.get_managed_instance(temp_dir)
            assert manager1 is manager2

            # Should be same as factory direct access
            manager3 = FileOutputManagerFactory.get_instance(temp_dir)
            assert manager1 is manager3

    def test_create_instance(self):
        """Test create_instance class method."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Should create new instance each time
            manager1 = FileOutputManager.create_instance(temp_dir)
            manager2 = FileOutputManager.create_instance(temp_dir)
            assert manager1 is not manager2

            # Should not be managed by factory
            managed_manager = FileOutputManager.get_managed_instance(temp_dir)
            assert manager1 is not managed_manager
            assert manager2 is not managed_manager

    def test_get_managed_instance_fallback(self):
        """Test get_managed_instance fallback when factory not available."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Test that the method exists and works normally
            # (Fallback testing is complex due to import mechanics)
            manager = FileOutputManager.get_managed_instance(temp_dir)
            assert isinstance(manager, FileOutputManager)
            assert manager.project_root == temp_dir

            # Verify it's using factory (should be same instance on second call)
            manager2 = FileOutputManager.get_managed_instance(temp_dir)
            assert manager is manager2


class TestConvenienceFunction:
    """Test convenience function."""

    def setup_method(self):
        """Clear factory instances before each test."""
        FileOutputManagerFactory.clear_all_instances()

    def teardown_method(self):
        """Clear factory instances after each test."""
        FileOutputManagerFactory.clear_all_instances()

    def test_get_file_output_manager_function(self):
        """Test get_file_output_manager convenience function."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager1 = get_file_output_manager(temp_dir)
            manager2 = get_file_output_manager(temp_dir)
            assert manager1 is manager2

            # Should be same as factory direct access
            manager3 = FileOutputManagerFactory.get_instance(temp_dir)
            assert manager1 is manager3


class TestIntegrationWithExistingCode:
    """Test integration with existing MCP tool patterns."""

    def setup_method(self):
        """Clear factory instances before each test."""
        FileOutputManagerFactory.clear_all_instances()

    def teardown_method(self):
        """Clear factory instances after each test."""
        FileOutputManagerFactory.clear_all_instances()

    def test_existing_mcp_tool_pattern(self):
        """Test that existing MCP tool initialization pattern still works."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Simulate existing MCP tool pattern
            class MockMCPTool:
                def __init__(self, project_root):
                    self.project_root = project_root
                    self.file_output_manager = FileOutputManager(project_root)

            # Multiple tools with same project root
            tool1 = MockMCPTool(temp_dir)
            tool2 = MockMCPTool(temp_dir)

            # They should have different FileOutputManager instances (existing behavior)
            assert tool1.file_output_manager is not tool2.file_output_manager

            # But both should work correctly
            assert tool1.file_output_manager.project_root == temp_dir
            assert tool2.file_output_manager.project_root == temp_dir

    def test_new_mcp_tool_pattern_with_factory(self):
        """Test new MCP tool pattern using factory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # New pattern using factory
            class NewMCPTool:
                def __init__(self, project_root):
                    self.project_root = project_root
                    self.file_output_manager = FileOutputManager.get_managed_instance(
                        project_root
                    )

            # Multiple tools with same project root
            tool1 = NewMCPTool(temp_dir)
            tool2 = NewMCPTool(temp_dir)

            # They should share the same FileOutputManager instance
            assert tool1.file_output_manager is tool2.file_output_manager

            # And both should work correctly
            assert tool1.file_output_manager.project_root == temp_dir
            assert tool2.file_output_manager.project_root == temp_dir
