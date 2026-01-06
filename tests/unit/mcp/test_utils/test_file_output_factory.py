"""
Unit tests for FileOutputManagerFactory.

Tests for the Managed Singleton Factory Pattern that manages FileOutputManager
instances with thread safety and consistent instance management.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.mcp.utils.file_output_factory import (
    FileOutputManagerFactory,
    get_file_output_manager,
)


@pytest.fixture(autouse=True)
def clear_factory_instances():
    """Clear factory instances before and after each test."""
    FileOutputManagerFactory.clear_all_instances()
    yield
    FileOutputManagerFactory.clear_all_instances()


class TestFileOutputManagerFactoryGetInstance:
    """Tests for get_instance method."""

    def test_get_instance_creates_new_instance(self):
        """Test get_instance creates new instance for new project root."""
        instance1 = FileOutputManagerFactory.get_instance("/test/project1")
        instance2 = FileOutputManagerFactory.get_instance("/test/project2")

        assert instance1 is not instance2
        # Paths are normalized to absolute paths
        assert Path(instance1.project_root).is_absolute()
        assert Path(instance2.project_root).is_absolute()
        # Both should contain the relative path portion
        assert "project1" in instance1.project_root
        assert "project2" in instance2.project_root

    def test_get_instance_returns_same_instance(self):
        """Test get_instance returns same instance for same project root."""
        instance1 = FileOutputManagerFactory.get_instance("/test/project")
        instance2 = FileOutputManagerFactory.get_instance("/test/project")

        assert instance1 is instance2

    def test_get_instance_with_none_project_root(self):
        """Test get_instance with None uses current working directory."""
        with patch("pathlib.Path.cwd") as mock_cwd:
            mock_cwd.return_value = Path("/current/dir")

            instance = FileOutputManagerFactory.get_instance(None)

            assert instance.project_root == str(Path("/current/dir").resolve())

    def test_get_instance_normalizes_path(self):
        """Test get_instance normalizes project root path."""
        instance = FileOutputManagerFactory.get_instance("./test/../project")

        # Path should be normalized to absolute path
        assert Path(instance.project_root).is_absolute()
        # Should resolve to project directory (not test)
        assert "project" in instance.project_root

    def test_get_instance_thread_safety(self):
        """Test get_instance is thread-safe."""
        import threading

        instances = []
        errors = []

        def get_instance_thread():
            try:
                instance = FileOutputManagerFactory.get_instance("/thread/test")
                instances.append(instance)
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = [threading.Thread(target=get_instance_thread) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # All threads should complete without errors
        assert len(errors) == 0
        # All instances should be the same (singleton behavior)
        assert all(i is instances[0] for i in instances)


class TestFileOutputManagerFactoryNormalizeProjectRoot:
    """Tests for _normalize_project_root method."""

    def test_normalize_project_root_none(self):
        """Test normalize_project_root with None returns current directory."""
        with patch("pathlib.Path.cwd") as mock_cwd:
            mock_cwd.return_value = Path("/current/dir")

            result = FileOutputManagerFactory._normalize_project_root(None)

            assert result == str(Path("/current/dir").resolve())

    def test_normalize_project_root_absolute_path(self):
        """Test normalize_project_root with absolute path."""
        result = FileOutputManagerFactory._normalize_project_root("/absolute/path")

        assert result == str(Path("/absolute/path").resolve())

    def test_normalize_project_root_relative_path(self):
        """Test normalize_project_root with relative path."""
        result = FileOutputManagerFactory._normalize_project_root("./relative/path")

        assert Path(result).is_absolute()

    def test_normalize_project_root_with_dots(self):
        """Test normalize_project_root resolves path with dots."""
        result = FileOutputManagerFactory._normalize_project_root("./test/../project")

        # Should resolve to project directory
        assert "test" not in result
        assert "project" in result

    def test_normalize_project_root_invalid_path(self, monkeypatch):
        """Test normalize_project_root with invalid path returns resolved path."""
        monkeypatch.setenv("TREE_SITTER_OUTPUT_PATH", None)

        with patch("pathlib.Path.cwd") as mock_cwd:
            mock_cwd.return_value = Path("/fallback/dir")

            # Use an invalid path - Path.resolve() still returns a path even if it doesn't exist
            result = FileOutputManagerFactory._normalize_project_root(
                "/nonexistent/invalid/path/that/does/not/exist"
            )

            # Path.resolve() returns a resolved path, not cwd fallback
            # The function doesn't check if path exists, just resolves it
            assert "nonexistent" in result


class TestFileOutputManagerFactoryClearInstance:
    """Tests for clear_instance method."""

    def test_clear_instance_existing(self):
        """Test clear_instance removes existing instance."""
        # Create instance
        instance = FileOutputManagerFactory.get_instance("/test/project")

        # Clear it
        result = FileOutputManagerFactory.clear_instance("/test/project")

        assert result is True
        # Getting new instance should create different object
        new_instance = FileOutputManagerFactory.get_instance("/test/project")
        assert instance is not new_instance

    def test_clear_instance_nonexistent(self):
        """Test clear_instance with nonexistent instance."""
        result = FileOutputManagerFactory.clear_instance("/nonexistent/project")

        assert result is False

    def test_clear_instance_with_none(self):
        """Test clear_instance with None clears default instance."""
        # Create instance with None
        FileOutputManagerFactory.get_instance(None)

        # Clear it
        result = FileOutputManagerFactory.clear_instance(None)

        assert result is True

    def test_clear_instance_normalizes_path(self):
        """Test clear_instance normalizes project root path."""
        # Create instance with relative path
        FileOutputManagerFactory.get_instance("./test/project")

        # Clear with different path representation
        result = FileOutputManagerFactory.clear_instance(
            str(Path("./test/project").resolve())
        )

        assert result is True


class TestFileOutputManagerFactoryClearAllInstances:
    """Tests for clear_all_instances method."""

    def test_clear_all_instances_with_instances(self):
        """Test clear_all_instances removes all instances."""
        # Create multiple instances
        FileOutputManagerFactory.get_instance("/project1")
        FileOutputManagerFactory.get_instance("/project2")
        FileOutputManagerFactory.get_instance("/project3")

        # Clear all
        count = FileOutputManagerFactory.clear_all_instances()

        assert count == 3
        assert FileOutputManagerFactory.get_instance_count() == 0

    def test_clear_all_instances_no_instances(self):
        """Test clear_all_instances with no instances."""
        count = FileOutputManagerFactory.clear_all_instances()

        assert count == 0


class TestFileOutputManagerFactoryGetInstanceCount:
    """Tests for get_instance_count method."""

    def test_get_instance_count_empty(self):
        """Test get_instance_count with no instances."""
        count = FileOutputManagerFactory.get_instance_count()

        assert count == 0

    def test_get_instance_count_multiple(self):
        """Test get_instance_count with multiple instances."""
        FileOutputManagerFactory.get_instance("/project1")
        FileOutputManagerFactory.get_instance("/project2")
        FileOutputManagerFactory.get_instance("/project3")

        count = FileOutputManagerFactory.get_instance_count()

        assert count == 3

    def test_get_instance_count_same_project_root(self):
        """Test get_instance_count doesn't increase for same project root."""
        FileOutputManagerFactory.get_instance("/project")
        FileOutputManagerFactory.get_instance("/project")
        FileOutputManagerFactory.get_instance("/project")

        count = FileOutputManagerFactory.get_instance_count()

        assert count == 1


class TestFileOutputManagerFactoryGetManagedProjectRoots:
    """Tests for get_managed_project_roots method."""

    def test_get_managed_project_roots_empty(self):
        """Test get_managed_project_roots with no instances."""
        # Clear any existing instances
        FileOutputManagerFactory.clear_all_instances()

        roots = FileOutputManagerFactory.get_managed_project_roots()

        assert roots == []

    def test_get_managed_project_roots_multiple(self):
        """Test get_managed_project_roots with multiple instances."""
        FileOutputManagerFactory.get_instance("/project1")
        FileOutputManagerFactory.get_instance("/project2")
        FileOutputManagerFactory.get_instance("/project3")

        roots = FileOutputManagerFactory.get_managed_project_roots()

        assert len(roots) == 3
        # Check all paths are included
        assert any("project1" in root for root in roots)
        assert any("project2" in root for root in roots)
        assert any("project3" in root for root in roots)


class TestFileOutputManagerFactoryUpdateProjectRoot:
    """Tests for update_project_root method."""

    def test_update_project_root_success(self):
        """Test update_project_root successfully updates instance."""
        # Create instance
        instance = FileOutputManagerFactory.get_instance("/old/project")

        # Update to new root
        result = FileOutputManagerFactory.update_project_root(
            "/old/project", "/new/project"
        )

        assert result is True
        # Check new project root is set
        assert "new" in instance.project_root
        assert "project" in instance.project_root
        # Old key should be removed (normalized path)
        old_normalized = FileOutputManagerFactory._normalize_project_root(
            "/old/project"
        )
        assert (
            old_normalized not in FileOutputManagerFactory.get_managed_project_roots()
        )
        # New key should be added (normalized path)
        new_normalized = FileOutputManagerFactory._normalize_project_root(
            "/new/project"
        )
        assert new_normalized in FileOutputManagerFactory.get_managed_project_roots()

    def test_update_project_root_nonexistent(self):
        """Test update_project_root with nonexistent instance."""
        result = FileOutputManagerFactory.update_project_root(
            "/nonexistent", "/new/project"
        )

        assert result is False

    def test_update_project_root_same_path(self):
        """Test update_project_root with same path returns True."""
        # Create instance
        FileOutputManagerFactory.get_instance("/project")

        # Try to update to same path
        result = FileOutputManagerFactory.update_project_root("/project", "/project")

        assert result is True

    def test_update_project_root_normalizes_paths(self):
        """Test update_project_root normalizes both paths."""
        # Create instance with relative path
        FileOutputManagerFactory.get_instance("./old/project")

        # Update with different path representation
        result = FileOutputManagerFactory.update_project_root(
            "./old/project", str(Path("./old/project").resolve())
        )

        assert result is True

    def test_update_project_root_updates_instance(self):
        """Test update_project_root updates instance's internal project root."""
        # Create instance
        instance = FileOutputManagerFactory.get_instance("/old/project")

        # Update to new root
        FileOutputManagerFactory.update_project_root("/old/project", "/new/project")

        # Instance should have new project root (normalized)
        assert "new" in instance.project_root
        assert "project" in instance.project_root


class TestGetFileOutputManager:
    """Tests for get_file_output_manager convenience function."""

    def test_get_file_output_manager_with_path(self):
        """Test get_file_output_manager with path."""
        manager = get_file_output_manager("/test/project")

        assert isinstance(
            manager, type(FileOutputManagerFactory.get_instance("/test/project"))
        )

    def test_get_file_output_manager_with_none(self):
        """Test get_file_output_manager with None."""
        with patch("pathlib.Path.cwd") as mock_cwd:
            mock_cwd.return_value = Path("/current/dir")

            manager = get_file_output_manager(None)

            assert manager.project_root == str(Path("/current/dir").resolve())

    def test_get_file_output_manager_uses_factory(self):
        """Test get_file_output_manager uses factory."""
        manager1 = get_file_output_manager("/project")
        manager2 = FileOutputManagerFactory.get_instance("/project")

        # Should return same instance (factory behavior)
        assert manager1 is manager2


class TestFileOutputManagerFactoryIntegration:
    """Integration tests for factory behavior."""

    def test_factory_singleton_behavior(self):
        """Test factory maintains singleton behavior across calls."""
        # Get instance multiple times
        instance1 = FileOutputManagerFactory.get_instance("/test/project")
        instance2 = FileOutputManagerFactory.get_instance("/test/project")
        instance3 = FileOutputManagerFactory.get_instance("/test/project")

        # All should be the same instance
        assert instance1 is instance2
        assert instance2 is instance3

    def test_factory_multiple_project_roots(self):
        """Test factory manages multiple project roots separately."""
        # Get instances for different project roots
        instance1 = FileOutputManagerFactory.get_instance("/project1")
        instance2 = FileOutputManagerFactory.get_instance("/project2")
        instance3 = FileOutputManagerFactory.get_instance("/project3")

        # Each should be different instance
        assert instance1 is not instance2
        assert instance2 is not instance3
        assert instance1 is not instance3

        # Count should be 3
        assert FileOutputManagerFactory.get_instance_count() == 3

    def test_factory_clear_and_recreate(self):
        """Test factory can clear and recreate instances."""
        # Create instance
        instance1 = FileOutputManagerFactory.get_instance("/project")

        # Clear it
        FileOutputManagerFactory.clear_instance("/project")

        # Recreate
        instance2 = FileOutputManagerFactory.get_instance("/project")

        # Should be different instances
        assert instance1 is not instance2

    def test_factory_clear_all_and_recreate(self):
        """Test factory can clear all and recreate instances."""
        # Create instances
        FileOutputManagerFactory.get_instance("/project1")
        FileOutputManagerFactory.get_instance("/project2")

        # Clear all
        FileOutputManagerFactory.clear_all_instances()

        # Recreate
        FileOutputManagerFactory.get_instance("/project1")
        FileOutputManagerFactory.get_instance("/project2")

        # Should be new instances
        assert FileOutputManagerFactory.get_instance_count() == 2
