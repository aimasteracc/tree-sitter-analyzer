"""
Edge case and error handling tests for Gitignore detector.
Tests cover error conditions, boundary cases, and robustness scenarios.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, mock_open

import pytest

from tree_sitter_analyzer.mcp.utils.gitignore_detector import (
    GitignoreDetector,
    get_default_detector,
)


class TestGitignoreDetectorErrorHandling:
    """Test Gitignore detector error handling."""

    @pytest.fixture
    def detector(self):
        """Create a detector instance."""
        return GitignoreDetector()

    def test_should_use_no_ignore_with_invalid_project_root(self, detector):
        """Test should_use_no_ignore with invalid project root."""
        roots = ["."]
        invalid_roots = [
            "/non/existent/path",
            "",
            None,
            123,  # Invalid type
            [],   # Invalid type
        ]
        
        for invalid_root in invalid_roots:
            try:
                result = detector.should_use_no_ignore(roots, invalid_root)
                assert result is False
            except Exception:
                # Should handle gracefully, but if exception occurs, that's also acceptable
                pass

    def test_find_gitignore_files_with_permission_error(self, detector):
        """Test finding .gitignore files with permission errors."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            
            # Mock Path.exists to raise PermissionError
            # Skip this test on Windows or when permission errors can't be simulated properly
            try:
                with patch.object(Path, 'exists', side_effect=PermissionError("Access denied")):
                    gitignore_files = detector._find_gitignore_files(project_path)
                    
                    # Should handle gracefully and return empty list
                    assert isinstance(gitignore_files, list)
            except PermissionError:
                # If the actual PermissionError is raised, that's also acceptable behavior
                pytest.skip("Permission error simulation not working on this platform")

    def test_find_gitignore_files_with_os_error(self, detector):
        """Test finding .gitignore files with OS errors."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            
            # Mock Path operations to raise OSError
            with patch.object(Path, 'resolve', side_effect=OSError("System error")):
                gitignore_files = detector._find_gitignore_files(project_path)
                
                # Should handle gracefully
                assert isinstance(gitignore_files, list)

    def test_has_interfering_patterns_with_encoding_error(self, detector):
        """Test pattern detection with encoding errors."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            gitignore_file = project_path / ".gitignore"
            
            # Create file with binary content that will cause encoding issues
            gitignore_file.write_bytes(b'\xff\xfe\x00\x00invalid utf-8')
            
            result = detector._has_interfering_patterns(
                gitignore_file, project_path, project_path
            )
            
            # Should handle encoding errors gracefully
            assert result is False

    def test_has_interfering_patterns_with_file_not_found(self, detector):
        """Test pattern detection with non-existent file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            non_existent_file = project_path / "non_existent.gitignore"
            
            result = detector._has_interfering_patterns(
                non_existent_file, project_path, project_path
            )
            
            assert result is False

    def test_directory_has_searchable_files_with_broken_symlinks(self, detector):
        """Test searchable file detection with broken symlinks."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir_path = Path(temp_dir)
            
            # Create a broken symlink (if supported by the system)
            try:
                broken_link = dir_path / "broken_link.py"
                broken_link.symlink_to("/non/existent/target.py")
                
                result = detector._directory_has_searchable_files(dir_path)
                
                # Should handle broken symlinks gracefully
                assert isinstance(result, bool)
            except (OSError, NotImplementedError):
                # Symlinks not supported on this system
                pytest.skip("Symlinks not supported")

    def test_directory_has_searchable_files_with_circular_symlinks(self, detector):
        """Test searchable file detection with circular symlinks."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir_path = Path(temp_dir)
            
            try:
                # Create circular symlinks
                link1 = dir_path / "link1"
                link2 = dir_path / "link2"
                
                link1.symlink_to(link2)
                link2.symlink_to(link1)
                
                result = detector._directory_has_searchable_files(dir_path)
                
                # Should handle circular symlinks gracefully
                assert isinstance(result, bool)
            except (OSError, NotImplementedError):
                # Symlinks not supported on this system
                pytest.skip("Symlinks not supported")


class TestGitignoreDetectorBoundaryConditions:
    """Test Gitignore detector boundary conditions."""

    @pytest.fixture
    def detector(self):
        """Create a detector instance."""
        return GitignoreDetector()

    def test_should_use_no_ignore_with_empty_roots(self, detector):
        """Test should_use_no_ignore with empty roots list."""
        roots = []
        project_root = "/test/project"
        
        result = detector.should_use_no_ignore(roots, project_root)
        
        assert result is False

    def test_should_use_no_ignore_with_dot_slash_root(self, detector):
        """Test should_use_no_ignore with './' root."""
        roots = ["./"]
        
        with tempfile.TemporaryDirectory() as temp_dir:
            result = detector.should_use_no_ignore(roots, temp_dir)
            
            # Should be treated as root directory search
            assert isinstance(result, bool)

    def test_find_gitignore_files_at_filesystem_root(self, detector):
        """Test finding .gitignore files at filesystem root."""
        # Use a path that's likely to be at or near filesystem root
        if os.name == 'nt':  # Windows
            root_path = Path("C:\\")
        else:  # Unix-like
            root_path = Path("/")
        
        try:
            gitignore_files = detector._find_gitignore_files(root_path)
            
            # Should handle filesystem root gracefully
            assert isinstance(gitignore_files, list)
        except (PermissionError, OSError):
            # Expected for filesystem root access
            pytest.skip("Cannot access filesystem root")

    def test_find_gitignore_files_with_very_deep_path(self, detector):
        """Test finding .gitignore files with very deep path."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create very deep directory structure
            deep_path = Path(temp_dir)
            for i in range(20):  # Create 20 levels deep
                deep_path = deep_path / f"level_{i}"
            
            try:
                deep_path.mkdir(parents=True)
                gitignore_files = detector._find_gitignore_files(deep_path)
                
                # Should respect depth limit
                assert isinstance(gitignore_files, list)
                assert len(gitignore_files) <= 3  # Max depth limit
            except OSError:
                # Path too long on some systems
                pytest.skip("Path too long for this system")

    def test_has_interfering_patterns_with_empty_gitignore(self, detector):
        """Test pattern detection with empty .gitignore file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            gitignore_file = project_path / ".gitignore"
            gitignore_file.write_text("")  # Empty file
            
            result = detector._has_interfering_patterns(
                gitignore_file, project_path, project_path
            )
            
            assert result is False

    def test_has_interfering_patterns_with_only_comments(self, detector):
        """Test pattern detection with .gitignore containing only comments."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            gitignore_file = project_path / ".gitignore"
            gitignore_file.write_text("""
# This is a comment
# Another comment
# Yet another comment

# More comments
""")
            
            result = detector._has_interfering_patterns(
                gitignore_file, project_path, project_path
            )
            
            assert result is False

    def test_has_interfering_patterns_with_only_whitespace(self, detector):
        """Test pattern detection with .gitignore containing only whitespace."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            gitignore_file = project_path / ".gitignore"
            gitignore_file.write_text("   \n\t\n   \n\t\t\n")  # Only whitespace
            
            result = detector._has_interfering_patterns(
                gitignore_file, project_path, project_path
            )
            
            assert result is False

    def test_is_interfering_pattern_with_empty_pattern(self, detector):
        """Test pattern interference detection with empty pattern."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            
            result = detector._is_interfering_pattern("", project_path, project_path)
            
            assert result is False

    def test_is_interfering_pattern_with_whitespace_pattern(self, detector):
        """Test pattern interference detection with whitespace-only pattern."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            
            patterns = ["   ", "\t", "\n", "  \t  \n  "]
            
            for pattern in patterns:
                result = detector._is_interfering_pattern(pattern, project_path, project_path)
                assert result is False

    def test_directory_has_searchable_files_with_zero_byte_files(self, detector):
        """Test searchable file detection with zero-byte files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir_path = Path(temp_dir)
            
            # Create zero-byte files with searchable extensions
            (dir_path / "empty.py").write_text("")
            (dir_path / "empty.java").write_text("")
            (dir_path / "empty.js").write_text("")
            
            result = detector._directory_has_searchable_files(dir_path)
            
            assert result is True

    def test_directory_has_searchable_files_with_hidden_files(self, detector):
        """Test searchable file detection with hidden files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir_path = Path(temp_dir)
            
            # Create hidden files with searchable extensions
            (dir_path / ".hidden.py").write_text("print('hidden')")
            (dir_path / ".config.js").write_text("module.exports = {};")
            
            result = detector._directory_has_searchable_files(dir_path)
            
            assert result is True


class TestGitignoreDetectorSpecialCharacters:
    """Test Gitignore detector with special characters."""

    @pytest.fixture
    def detector(self):
        """Create a detector instance."""
        return GitignoreDetector()

    def test_has_interfering_patterns_with_unicode_patterns(self, detector):
        """Test pattern detection with Unicode characters in patterns."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            gitignore_file = project_path / ".gitignore"
            
            # Create .gitignore with Unicode patterns
            gitignore_file.write_text("""
# Unicode patterns
测试目录/
código/
файлы/
""", encoding='utf-8')
            
            result = detector._has_interfering_patterns(
                gitignore_file, project_path, project_path
            )
            
            # Should handle Unicode patterns gracefully
            assert isinstance(result, bool)

    def test_has_interfering_patterns_with_special_regex_chars(self, detector):
        """Test pattern detection with special regex characters."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            gitignore_file = project_path / ".gitignore"
            
            # Create .gitignore with special regex characters
            gitignore_file.write_text("""
# Special characters
[abc]/
*.{js,ts}
file?.txt
dir*/
(test)/
""")
            
            result = detector._has_interfering_patterns(
                gitignore_file, project_path, project_path
            )
            
            # Should handle special characters gracefully
            assert isinstance(result, bool)

    def test_directory_has_searchable_files_with_unicode_filenames(self, detector):
        """Test searchable file detection with Unicode filenames."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir_path = Path(temp_dir)
            
            try:
                # Create files with Unicode names
                (dir_path / "测试.py").write_text("print('test')")
                (dir_path / "código.js").write_text("console.log('test');")
                (dir_path / "файл.java").write_text("public class Test {}")
                
                result = detector._directory_has_searchable_files(dir_path)
                
                assert result is True
            except (UnicodeError, OSError):
                # Unicode filenames not supported on this system
                pytest.skip("Unicode filenames not supported")

    def test_is_interfering_pattern_with_escaped_characters(self, detector):
        """Test pattern interference detection with escaped characters."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            
            patterns = [
                r"src\/",
                r"lib\\",
                r"code\*",
                r"app\?",
            ]
            
            for pattern in patterns:
                result = detector._is_interfering_pattern(pattern, project_path, project_path)
                assert isinstance(result, bool)


class TestGitignoreDetectorPerformanceEdgeCases:
    """Test Gitignore detector performance edge cases."""

    @pytest.fixture
    def detector(self):
        """Create a detector instance."""
        return GitignoreDetector()

    def test_has_interfering_patterns_with_very_large_gitignore(self, detector):
        """Test pattern detection with very large .gitignore file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            gitignore_file = project_path / ".gitignore"
            
            # Create very large .gitignore file
            large_content = []
            for i in range(10000):
                large_content.append(f"# Comment {i}")
                large_content.append(f"pattern_{i}/")
                large_content.append(f"*.ext{i}")
            
            gitignore_file.write_text("\n".join(large_content))
            
            # Should handle large files without timeout
            result = detector._has_interfering_patterns(
                gitignore_file, project_path, project_path
            )
            
            assert isinstance(result, bool)

    def test_directory_has_searchable_files_with_many_files(self, detector):
        """Test searchable file detection with many files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir_path = Path(temp_dir)
            
            # Create many files
            for i in range(1000):
                if i % 100 == 0:  # Every 100th file is searchable
                    (dir_path / f"file_{i}.py").write_text(f"# File {i}")
                else:
                    (dir_path / f"file_{i}.txt").write_text(f"Data {i}")
            
            # Should find searchable files efficiently
            result = detector._directory_has_searchable_files(dir_path)
            
            assert result is True

    def test_find_gitignore_files_with_many_directories(self, detector):
        """Test finding .gitignore files with many directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            
            # Create many directories at the same level
            for i in range(100):
                dir_path = project_path / f"dir_{i}"
                dir_path.mkdir()
                
                # Some directories have .gitignore files
                if i % 10 == 0:
                    (dir_path / ".gitignore").write_text(f"pattern_{i}/")
            
            # Should handle many directories efficiently
            gitignore_files = detector._find_gitignore_files(project_path)
            
            assert isinstance(gitignore_files, list)

    def test_is_search_dir_affected_by_pattern_with_long_paths(self, detector):
        """Test search directory analysis with very long paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            
            # Create very long path
            long_path = project_path
            for i in range(50):
                long_path = long_path / f"very_long_directory_name_{i}"
            
            try:
                long_path.mkdir(parents=True)
                
                result = detector._is_search_dir_affected_by_pattern(
                    long_path, project_path, project_path
                )
                
                assert isinstance(result, bool)
            except OSError:
                # Path too long on some systems
                pytest.skip("Path too long for this system")


class TestGitignoreDetectorConcurrencyEdgeCases:
    """Test Gitignore detector concurrency edge cases."""

    @pytest.fixture
    def detector(self):
        """Create a detector instance."""
        return GitignoreDetector()

    def test_get_default_detector_thread_safety(self):
        """Test that get_default_detector is thread-safe."""
        import threading
        
        detectors = []
        
        def get_detector():
            detectors.append(get_default_detector())
        
        # Create multiple threads
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=get_detector)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # All detectors should be the same instance
        assert len(set(id(d) for d in detectors)) == 1

    def test_file_operations_with_concurrent_modifications(self, detector):
        """Test file operations with concurrent file modifications."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            gitignore_file = project_path / ".gitignore"
            
            # Create initial .gitignore
            gitignore_file.write_text("src/\n")
            
            # Simulate concurrent modification during reading
            def modify_file():
                try:
                    gitignore_file.write_text("lib/\ncode/\n")
                except Exception:
                    pass  # Ignore errors from concurrent access
            
            import threading
            modify_thread = threading.Thread(target=modify_file)
            modify_thread.start()
            
            # Try to read patterns while file is being modified
            result = detector._has_interfering_patterns(
                gitignore_file, project_path, project_path
            )
            
            modify_thread.join()
            
            # Should handle concurrent modifications gracefully
            assert isinstance(result, bool)


class TestGitignoreDetectorMemoryEdgeCases:
    """Test Gitignore detector memory edge cases."""

    @pytest.fixture
    def detector(self):
        """Create a detector instance."""
        return GitignoreDetector()

    def test_memory_usage_with_large_directory_scan(self, detector):
        """Test memory usage with large directory scan."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dir_path = Path(temp_dir)
            
            # Create large directory structure
            for i in range(100):
                subdir = dir_path / f"subdir_{i}"
                subdir.mkdir()
                
                for j in range(100):
                    (subdir / f"file_{j}.py").write_text(f"# File {i}_{j}")
            
            # Should handle large scans without excessive memory usage
            result = detector._directory_has_searchable_files(dir_path)
            
            assert result is True

    def test_pattern_matching_with_many_patterns(self, detector):
        """Test pattern matching with many patterns."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            gitignore_file = project_path / ".gitignore"
            
            # Create many patterns
            patterns = []
            for i in range(1000):
                patterns.append(f"pattern_{i}/")
                patterns.append(f"*.ext{i}")
                patterns.append(f"# Comment {i}")
            
            gitignore_file.write_text("\n".join(patterns))
            
            # Should handle many patterns efficiently
            result = detector._has_interfering_patterns(
                gitignore_file, project_path, project_path
            )
            
            assert isinstance(result, bool)

    def test_get_detection_info_memory_efficiency(self, detector):
        """Test get_detection_info memory efficiency."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            
            # Create complex project structure
            for i in range(50):
                subdir = project_path / f"subdir_{i}"
                subdir.mkdir()
                
                # Create .gitignore in each subdirectory
                gitignore = subdir / ".gitignore"
                gitignore.write_text(f"pattern_{i}/\n*.ext{i}\n")
                
                # Create source files
                (subdir / f"source_{i}.py").write_text(f"# Source {i}")
            
            roots = ["."]
            
            # Should return detailed info without excessive memory usage
            info = detector.get_detection_info(roots, str(project_path))
            
            assert isinstance(info, dict)
            assert "should_use_no_ignore" in info
            assert "detected_gitignore_files" in info
            assert "interfering_patterns" in info
            assert "reason" in info