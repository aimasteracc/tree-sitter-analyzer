#!/usr/bin/env python3
"""
File Output Manager Factory

This module provides a Managed Singleton Factory Pattern for FileOutputManager
to prevent duplicate initialization and ensure consistent instance management
across MCP tools.
"""

import threading
from pathlib import Path

from ...utils import setup_logger
from .file_output_manager import FileOutputManager

# Set up logging
logger = setup_logger(__name__)


class FileOutputManagerFactory:
    """
    Factory class that manages FileOutputManager instances using a Managed Singleton
    pattern. Each project root gets its own singleton instance, ensuring consistency
    across MCP tools while preventing duplicate initialization.
    """

    # Class-level lock for thread safety
    _lock = threading.RLock()

    # Dictionary to store instances by project root
    _instances: dict[str, FileOutputManager] = {}

    @classmethod
    def get_instance(cls, project_root: str | None = None) -> FileOutputManager:
        """
        Get or create a FileOutputManager instance for the specified project root.

        This method implements the Managed Singleton pattern - one instance per
        project root, ensuring consistency across all MCP tools.

        Args:
            project_root: Project root directory. If None, uses current working directory.

        Returns:
            FileOutputManager instance for the specified project root
        """
        # Normalize project root path
        normalized_root = cls._normalize_project_root(project_root)

        # Double-checked locking pattern for thread safety
        if normalized_root not in cls._instances:
            with cls._lock:
                if normalized_root not in cls._instances:
                    logger.info(
                        f"Creating new FileOutputManager instance for project root: {normalized_root}"
                    )
                    cls._instances[normalized_root] = FileOutputManager(normalized_root)
                else:
                    logger.debug(
                        f"Using existing FileOutputManager instance for project root: {normalized_root}"
                    )
        else:
            logger.debug(
                f"Using existing FileOutputManager instance for project root: {normalized_root}"
            )

        return cls._instances[normalized_root]

    @classmethod
    def _normalize_project_root(cls, project_root: str | None) -> str:
        """
        Normalize project root path for consistent key generation.

        Args:
            project_root: Raw project root path

        Returns:
            Normalized absolute path string
        """
        if project_root is None:
            return str(Path.cwd().resolve())

        try:
            return str(Path(project_root).resolve())
        except Exception as e:
            logger.warning(f"Failed to resolve project root path '{project_root}': {e}")
            return str(Path.cwd().resolve())

    @classmethod
    def clear_instance(cls, project_root: str | None = None) -> bool:
        """
        Clear a specific FileOutputManager instance from the factory.

        This method is primarily for testing purposes or when you need to
        force recreation of an instance.

        Args:
            project_root: Project root directory. If None, uses current working directory.

        Returns:
            True if instance was cleared, False if it didn't exist
        """
        normalized_root = cls._normalize_project_root(project_root)

        with cls._lock:
            if normalized_root in cls._instances:
                logger.info(
                    f"Clearing FileOutputManager instance for project root: {normalized_root}"
                )
                del cls._instances[normalized_root]
                return True
            else:
                logger.debug(
                    f"No FileOutputManager instance found for project root: {normalized_root}"
                )
                return False

    @classmethod
    def clear_all_instances(cls) -> int:
        """
        Clear all FileOutputManager instances from the factory.

        This method is primarily for testing purposes or cleanup.

        Returns:
            Number of instances that were cleared
        """
        with cls._lock:
            count = len(cls._instances)
            if count > 0:
                logger.info(f"Clearing all {count} FileOutputManager instances")
                cls._instances.clear()
            else:
                logger.debug("No FileOutputManager instances to clear")
            return count

    @classmethod
    def get_instance_count(cls) -> int:
        """
        Get the current number of managed instances.

        Returns:
            Number of currently managed FileOutputManager instances
        """
        with cls._lock:
            return len(cls._instances)

    @classmethod
    def get_managed_project_roots(cls) -> list[str]:
        """
        Get list of all currently managed project roots.

        Returns:
            List of project root paths that have managed instances
        """
        with cls._lock:
            return list(cls._instances.keys())

    @classmethod
    def update_project_root(cls, old_root: str | None, new_root: str) -> bool:
        """
        Update the project root for an existing instance.

        This method moves an existing instance from one project root key to another,
        and updates the instance's internal project root.

        Args:
            old_root: Current project root (None for current working directory)
            new_root: New project root

        Returns:
            True if update was successful, False if old instance didn't exist
        """
        old_normalized = cls._normalize_project_root(old_root)
        new_normalized = cls._normalize_project_root(new_root)

        if old_normalized == new_normalized:
            logger.debug(f"Project root update not needed: {old_normalized}")
            return True

        with cls._lock:
            if old_normalized in cls._instances:
                instance = cls._instances[old_normalized]

                # Update the instance's internal project root
                instance.set_project_root(new_root)

                # Move to new key
                cls._instances[new_normalized] = instance
                del cls._instances[old_normalized]

                logger.info(
                    f"Updated FileOutputManager project root: {old_normalized} -> {new_normalized}"
                )
                return True
            else:
                logger.warning(
                    f"No FileOutputManager instance found for old project root: {old_normalized}"
                )
                return False


# Convenience function for backward compatibility and ease of use
def get_file_output_manager(project_root: str | None = None) -> FileOutputManager:
    """
    Convenience function to get a FileOutputManager instance.

    This function provides a simple interface to the factory while maintaining
    the singleton behavior per project root.

    Args:
        project_root: Project root directory. If None, uses current working directory.

    Returns:
        FileOutputManager instance for the specified project root
    """
    return FileOutputManagerFactory.get_instance(project_root)
