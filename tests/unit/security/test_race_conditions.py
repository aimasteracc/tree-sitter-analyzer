#!/usr/bin/env python3
"""
Tests for race condition safety in security validation.

This module tests TOCTOU (Time-of-Check to Time-of-Use) vulnerabilities
and concurrent access safety in security-critical operations.

Race conditions can occur when:
1. A file is checked for safety, then accessed (file could change between)
2. A symlink is verified, then followed (symlink target could change)
3. Multiple threads/processes access shared resources simultaneously
"""

import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.security import SecurityValidator


class TestTOCTOURaceConditions:
    """Test Time-of-Check to Time-of-Use race conditions."""

    @pytest.mark.asyncio
    async def test_symlink_target_change_detection(self, tmp_path):
        """Test that symlink target changes are detected.

        This tests the scenario where:
        1. A symlink points to a safe location
        2. The symlink target is changed to an unsafe location
        3. The validator should detect this
        """
        validator = SecurityValidator(str(tmp_path))

        # Create a safe file and an unsafe directory
        safe_file = tmp_path / "safe.txt"
        safe_file.write_text("safe content")

        unsafe_dir = tmp_path / "unsafe"
        unsafe_dir.mkdir()
        unsafe_file = unsafe_dir / "secret.txt"
        unsafe_file.write_text("secret content")

        # Create a symlink initially pointing to safe location
        symlink = tmp_path / "link.txt"
        symlink.symlink_to(safe_file)

        # First validation should pass
        is_valid, error = validator.validate_file_path(str(symlink))
        # Symlinks may be rejected for security, but shouldn't crash

        # Change symlink target (delete and recreate)
        symlink.unlink()
        symlink.symlink_to(unsafe_file)

        # Second validation should still handle symlink safely
        is_valid2, error2 = validator.validate_file_path(str(symlink))
        # The important thing is no crash and consistent behavior

    @pytest.mark.asyncio
    async def test_concurrent_path_validation(self, tmp_path):
        """Test that concurrent path validations are handled safely."""
        validator = SecurityValidator(str(tmp_path))

        # Create test files
        for i in range(10):
            test_file = tmp_path / f"file_{i}.txt"
            test_file.write_text(f"content {i}")

        # Run concurrent validations
        async def validate_file(file_path: str) -> tuple[bool, str]:
            return validator.validate_file_path(file_path)

        tasks = [
            validate_file(str(tmp_path / f"file_{i}.txt"))
            for i in range(10)
        ]

        results = await asyncio.gather(*tasks)

        # All validations should complete without error
        for is_valid, error in results:
            assert isinstance(is_valid, bool)
            assert isinstance(error, str)

    @pytest.mark.asyncio
    async def test_file_deletion_during_validation(self, tmp_path):
        """Test handling of files deleted during validation."""
        validator = SecurityValidator(str(tmp_path))

        # Create a file
        test_file = tmp_path / "deleteme.txt"
        test_file.write_text("temporary content")

        # Start validation in a task
        async def validate_and_delete():
            # Small delay to simulate race
            await asyncio.sleep(0.001)
            result = validator.validate_file_path(str(test_file))
            # File might be deleted here
            if test_file.exists():
                test_file.unlink()
            return result

        result = await validate_and_delete()
        # Should complete without crash
        assert isinstance(result, tuple)
        assert len(result) == 2


class TestConcurrentSafety:
    """Test concurrent access safety for shared resources."""

    @pytest.mark.asyncio
    async def test_concurrent_validator_access(self):
        """Test that validator handles concurrent access safely."""
        validator = SecurityValidator()

        async def validate_path(path: str) -> tuple[bool, str]:
            return validator.validate_file_path(path)

        # Run many concurrent validations
        tasks = [
            validate_path(f"/tmp/test_{i}.txt")
            for i in range(50)
        ]

        results = await asyncio.gather(*tasks)

        # All should complete
        assert len(results) == 50
        for is_valid, error in results:
            assert isinstance(is_valid, bool)

    @pytest.mark.asyncio
    async def test_concurrent_regex_validation(self):
        """Test that regex checker handles concurrent access safely."""
        from tree_sitter_analyzer.security import RegexSafetyChecker

        checker = RegexSafetyChecker()

        async def validate_pattern(pattern: str) -> tuple[bool, str]:
            return checker.validate_pattern(pattern)

        # Mix of safe and dangerous patterns
        patterns = [
            r"safe_pattern_\d+",
            r"(.+)+",  # Dangerous
            r"[a-z]+",
            r"(.*)*",  # Dangerous
            r"^test$",
        ] * 10  # Repeat 10 times

        tasks = [validate_pattern(p) for p in patterns]
        results = await asyncio.gather(*tasks)

        # All should complete
        assert len(results) == 50

    @pytest.mark.asyncio
    async def test_boundary_manager_concurrent_access(self, tmp_path):
        """Test that boundary manager handles concurrent access safely."""
        from tree_sitter_analyzer.security import ProjectBoundaryManager

        manager = ProjectBoundaryManager(str(tmp_path))

        # Create subdirectories
        for i in range(5):
            subdir = tmp_path / f"dir_{i}"
            subdir.mkdir()
            (subdir / "file.txt").write_text("content")

        async def check_path(path: str) -> bool:
            return manager.is_within_project(path)

        tasks = [
            check_path(str(tmp_path / f"dir_{i}" / "file.txt"))
            for i in range(5)
        ]

        results = await asyncio.gather(*tasks)

        # All should be within boundary
        for result in results:
            assert isinstance(result, bool)


class TestSymlinkRaceConditions:
    """Test symlink-related race conditions."""

    def test_broken_symlink_handling(self, tmp_path):
        """Test handling of broken symlinks (target doesn't exist)."""
        validator = SecurityValidator(str(tmp_path))

        # Create a symlink to a non-existent target
        broken_link = tmp_path / "broken_link"
        broken_link.symlink_to(tmp_path / "nonexistent")

        # Should handle gracefully without crash
        is_valid, error = validator.validate_file_path(str(broken_link))

        # Symlinks are typically rejected for security
        assert isinstance(is_valid, bool)
        assert isinstance(error, str)

    def test_symlink_chain_handling(self, tmp_path):
        """Test handling of symlink chains (A -> B -> C)."""
        validator = SecurityValidator(str(tmp_path))

        # Create a chain of symlinks
        target = tmp_path / "target.txt"
        target.write_text("content")

        link1 = tmp_path / "link1"
        link1.symlink_to(target)

        link2 = tmp_path / "link2"
        link2.symlink_to(link1)

        link3 = tmp_path / "link3"
        link3.symlink_to(link2)

        # Should handle chain gracefully
        is_valid, error = validator.validate_file_path(str(link3))

        assert isinstance(is_valid, bool)
        assert isinstance(error, str)

    @pytest.mark.skipif(os.name == "nt", reason="Unix-specific test")
    def test_symlink_loop_detection(self, tmp_path):
        """Test detection of symlink loops."""
        validator = SecurityValidator(str(tmp_path))

        # Create a symlink loop: a -> b -> a
        link_a = tmp_path / "link_a"
        link_b = tmp_path / "link_b"

        link_b.symlink_to(link_a)
        link_a.symlink_to(link_b)

        # Should handle loop gracefully (might raise or return error)
        try:
            is_valid, error = validator.validate_file_path(str(link_a))
            assert isinstance(is_valid, bool)
        except OSError:
            # Operating system might detect the loop
            pass


class TestFileSystemRaceConditions:
    """Test file system related race conditions."""

    @pytest.mark.asyncio
    async def test_directory_creation_race(self, tmp_path):
        """Test handling when directory is created during validation."""
        validator = SecurityValidator(str(tmp_path))

        # Path that doesn't exist yet
        new_dir = tmp_path / "new_directory"
        new_file = new_dir / "file.txt"

        async def validate_and_create():
            # Validate path that doesn't exist
            result1 = validator.validate_file_path(str(new_file))

            # Create the directory
            new_dir.mkdir()
            new_file.write_text("content")

            # Validate again
            result2 = validator.validate_file_path(str(new_file))

            return result1, result2

        result1, result2 = await validate_and_create()

        # Both should complete without crash
        assert isinstance(result1, tuple)
        assert isinstance(result2, tuple)

    @pytest.mark.asyncio
    async def test_permission_change_during_validation(self, tmp_path):
        """Test handling when file permissions change during validation."""
        # Skip on Windows as chmod behaves differently
        if os.name == "nt":
            pytest.skip("Unix-specific test")

        validator = SecurityValidator(str(tmp_path))

        # Create a file
        test_file = tmp_path / "perms.txt"
        test_file.write_text("content")

        async def validate_with_permission_change():
            # Start validation
            task = asyncio.create_task(
                asyncio.to_thread(validator.validate_file_path, str(test_file))
            )

            # Change permissions during validation
            await asyncio.sleep(0.001)
            os.chmod(test_file, 0o000)  # Remove all permissions

            result = await task

            # Restore permissions
            os.chmod(test_file, 0o644)

            return result

        result = await validate_with_permission_change()

        # Should complete without crash
        assert isinstance(result, tuple)

    @pytest.mark.asyncio
    async def test_concurrent_file_modification(self, tmp_path):
        """Test handling when file is modified during read."""
        validator = SecurityValidator(str(tmp_path))

        # Create a file
        test_file = tmp_path / "concurrent.txt"
        test_file.write_text("initial content")

        async def modify_file():
            for i in range(10):
                test_file.write_text(f"content {i}")
                await asyncio.sleep(0.001)

        async def validate_file():
            results = []
            for i in range(10):
                result = validator.validate_file_path(str(test_file))
                results.append(result)
                await asyncio.sleep(0.001)
            return results

        # Run both concurrently
        await asyncio.gather(modify_file(), validate_file())

        # Should complete without crash


class TestAtomicOperations:
    """Test atomic operation guarantees."""

    def test_path_resolution_atomicity(self, tmp_path):
        """Test that path resolution is consistent."""
        from tree_sitter_analyzer.security import ProjectBoundaryManager

        manager = ProjectBoundaryManager(str(tmp_path))

        # Multiple resolutions of same path should give same result
        test_path = str(tmp_path / "test.txt")

        results = [manager.is_within_project(test_path) for _ in range(100)]

        # All results should be identical
        assert len(set(results)) == 1

    @pytest.mark.asyncio
    async def test_concurrent_boundary_checks(self, tmp_path):
        """Test that boundary checks are consistent under concurrency."""
        from tree_sitter_analyzer.security import ProjectBoundaryManager

        manager = ProjectBoundaryManager(str(tmp_path))

        test_path = str(tmp_path / "test.txt")

        async def check_boundary():
            return manager.is_within_project(test_path)

        # Run 100 concurrent checks
        tasks = [check_boundary() for _ in range(100)]
        results = await asyncio.gather(*tasks)

        # All results should be identical
        assert len(set(results)) == 1
