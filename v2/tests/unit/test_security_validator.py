"""
Unit tests for security validation.

Following TDD methodology:
1. RED: Write failing tests first
2. GREEN: Implement minimal code to pass
3. REFACTOR: Improve code quality

This is T4.5: Security Validation
"""

import pytest


class TestPathTraversalPrevention:
    """Tests for path traversal attack prevention."""

    def test_validator_creation(self):
        """Test creating a security validator."""
        from tree_sitter_analyzer_v2.security.validator import SecurityValidator

        validator = SecurityValidator(project_root="/tmp/project")
        assert validator is not None

    def test_absolute_path_within_project(self, tmp_path):
        """Test absolute path within project is allowed."""
        from tree_sitter_analyzer_v2.security.validator import SecurityValidator

        project_root = tmp_path / "project"
        project_root.mkdir()
        file_path = project_root / "test.py"
        file_path.write_text("print('hello')")

        validator = SecurityValidator(project_root=str(project_root))
        result = validator.validate_file_path(str(file_path))

        assert result["valid"] is True
        assert "normalized_path" in result

    def test_relative_path_within_project(self, tmp_path):
        """Test relative path within project is allowed."""
        from tree_sitter_analyzer_v2.security.validator import SecurityValidator

        project_root = tmp_path / "project"
        project_root.mkdir()

        validator = SecurityValidator(project_root=str(project_root))
        result = validator.validate_file_path("test.py")

        assert result["valid"] is True

    def test_path_traversal_attack_blocked(self, tmp_path):
        """Test path traversal attack is blocked."""
        from tree_sitter_analyzer_v2.security.validator import SecurityValidator

        project_root = tmp_path / "project"
        project_root.mkdir()

        validator = SecurityValidator(project_root=str(project_root))

        # Try to access parent directory
        result = validator.validate_file_path("../../../etc/passwd")

        assert result["valid"] is False
        assert "error" in result
        assert "outside project" in result["error"].lower()

    def test_absolute_path_outside_project_blocked(self, tmp_path):
        """Test absolute path outside project is blocked."""
        from tree_sitter_analyzer_v2.security.validator import SecurityValidator

        project_root = tmp_path / "project"
        project_root.mkdir()

        validator = SecurityValidator(project_root=str(project_root))

        # Try to access different directory
        other_dir = tmp_path / "other"
        other_dir.mkdir()
        other_file = other_dir / "test.py"

        result = validator.validate_file_path(str(other_file))

        assert result["valid"] is False
        assert "error" in result

    def test_symlink_outside_project_blocked(self, tmp_path):
        """Test symlink pointing outside project is blocked."""
        from tree_sitter_analyzer_v2.security.validator import SecurityValidator

        project_root = tmp_path / "project"
        project_root.mkdir()

        # Create a file outside project
        outside_file = tmp_path / "outside.txt"
        outside_file.write_text("secret")

        # Create symlink inside project pointing outside
        symlink = project_root / "link.txt"
        try:
            symlink.symlink_to(outside_file)
        except OSError:
            # Windows may not allow symlinks without admin
            pytest.skip("Symlinks not supported")

        validator = SecurityValidator(project_root=str(project_root))
        result = validator.validate_file_path(str(symlink))

        assert result["valid"] is False

    def test_windows_path_traversal_blocked(self, tmp_path):
        """Test Windows-style path traversal is blocked."""
        from tree_sitter_analyzer_v2.security.validator import SecurityValidator

        project_root = tmp_path / "project"
        project_root.mkdir()

        validator = SecurityValidator(project_root=str(project_root))

        # Windows path traversal attempts
        result1 = validator.validate_file_path("..\\..\\..\\windows\\system32")
        result2 = validator.validate_file_path("C:\\Windows\\System32\\config\\sam")

        assert result1["valid"] is False
        assert result2["valid"] is False


class TestRegexSafety:
    """Tests for regex safety (ReDoS prevention)."""

    def test_safe_regex_allowed(self):
        """Test safe regex patterns are allowed."""
        from tree_sitter_analyzer_v2.security.validator import SecurityValidator

        validator = SecurityValidator(project_root="/tmp")

        safe_patterns = [
            "hello",
            "test.*",
            "[a-z]+",
            "\\d{3}-\\d{4}",
            "^start",
            "end$",
        ]

        for pattern in safe_patterns:
            result = validator.validate_regex(pattern)
            assert result["valid"] is True, f"Pattern should be safe: {pattern}"

    def test_dangerous_regex_blocked(self):
        """Test dangerous regex patterns (ReDoS) are blocked."""
        from tree_sitter_analyzer_v2.security.validator import SecurityValidator

        validator = SecurityValidator(project_root="/tmp")

        # Known ReDoS patterns
        dangerous_patterns = [
            "(a+)+",  # Catastrophic backtracking
            "(a*)*",  # Nested quantifiers
            "(a|a)*",  # Alternation with overlap
            "(a|ab)*",  # Nested alternation
            "^(a+)+$",  # Anchored nested quantifiers
            "(.*)*",  # Very dangerous
            "(x+x+)+y",  # Complex backtracking
        ]

        for pattern in dangerous_patterns:
            result = validator.validate_regex(pattern)
            assert result["valid"] is False, f"Pattern should be blocked: {pattern}"
            assert "error" in result

    def test_regex_timeout_protection(self):
        """Test regex execution has timeout protection."""
        from tree_sitter_analyzer_v2.security.validator import SecurityValidator

        validator = SecurityValidator(project_root="/tmp")

        # This pattern + input would cause ReDoS without timeout
        result = validator.validate_regex("(a+)+", test_string="a" * 50 + "b")

        # Should either block pattern or timeout quickly
        assert result["valid"] is False or result.get("timeout", False)

    def test_empty_regex_allowed(self):
        """Test empty regex is handled gracefully."""
        from tree_sitter_analyzer_v2.security.validator import SecurityValidator

        validator = SecurityValidator(project_root="/tmp")

        result = validator.validate_regex("")

        assert result["valid"] is True  # Empty pattern is safe

    def test_invalid_regex_blocked(self):
        """Test invalid regex syntax is blocked."""
        from tree_sitter_analyzer_v2.security.validator import SecurityValidator

        validator = SecurityValidator(project_root="/tmp")

        invalid_patterns = [
            "[",  # Unclosed bracket
            "(?P<incomplete",  # Incomplete named group
            "(?P<>test)",  # Empty group name
            "(?P<123>test)",  # Invalid group name
        ]

        for pattern in invalid_patterns:
            result = validator.validate_regex(pattern)
            assert result["valid"] is False


class TestResourceLimits:
    """Tests for resource limits."""

    def test_file_size_limit_enforced(self, tmp_path):
        """Test file size limit is enforced."""
        from tree_sitter_analyzer_v2.security.validator import SecurityValidator

        project_root = tmp_path / "project"
        project_root.mkdir()

        # Create file larger than limit (200KB file, 100KB limit)
        # Use small sizes to avoid "No space left on device" on CI/limited disks
        large_file = project_root / "large.py"
        large_file.write_bytes(b"x" * (200 * 1024))

        validator = SecurityValidator(
            project_root=str(project_root),
            max_file_size=100 * 1024,  # 100KB limit
        )

        result = validator.validate_file_path(str(large_file))

        assert result["valid"] is False
        assert "too large" in result["error"].lower()

    def test_file_within_size_limit_allowed(self, tmp_path):
        """Test file within size limit is allowed."""
        from tree_sitter_analyzer_v2.security.validator import SecurityValidator

        project_root = tmp_path / "project"
        project_root.mkdir()

        # Create small file
        small_file = project_root / "small.py"
        small_file.write_text("print('hello')")

        validator = SecurityValidator(
            project_root=str(project_root),
            max_file_size=100 * 1024,  # 100KB limit
        )

        result = validator.validate_file_path(str(small_file))

        assert result["valid"] is True

    def test_default_file_size_limit(self, tmp_path):
        """Test default file size limit is reasonable."""
        from tree_sitter_analyzer_v2.security.validator import SecurityValidator

        project_root = tmp_path / "project"
        project_root.mkdir()

        validator = SecurityValidator(project_root=str(project_root))

        # Should have a default limit (e.g., 50MB)
        assert validator.max_file_size > 0
        assert validator.max_file_size <= 100 * 1024 * 1024  # At most 100MB


class TestSecurityValidatorIntegration:
    """Integration tests for security validator."""

    def test_validate_multiple_constraints(self, tmp_path):
        """Test validating multiple security constraints."""
        from tree_sitter_analyzer_v2.security.validator import SecurityValidator

        project_root = tmp_path / "project"
        project_root.mkdir()

        file_path = project_root / "test.py"
        file_path.write_text("print('test')")

        validator = SecurityValidator(project_root=str(project_root))

        # Validate both path and regex
        path_result = validator.validate_file_path(str(file_path))
        regex_result = validator.validate_regex("test.*")

        assert path_result["valid"] is True
        assert regex_result["valid"] is True

    def test_validator_state_isolation(self, tmp_path):
        """Test validator instances are isolated."""
        from tree_sitter_analyzer_v2.security.validator import SecurityValidator

        root1 = tmp_path / "project1"
        root2 = tmp_path / "project2"
        root1.mkdir()
        root2.mkdir()

        validator1 = SecurityValidator(project_root=str(root1))
        validator2 = SecurityValidator(project_root=str(root2))

        # Each validator should have independent state
        assert validator1.project_root != validator2.project_root

    def test_error_messages_informative(self, tmp_path):
        """Test error messages are informative."""
        from tree_sitter_analyzer_v2.security.validator import SecurityValidator

        project_root = tmp_path / "project"
        project_root.mkdir()

        validator = SecurityValidator(project_root=str(project_root))

        # Path traversal error
        result1 = validator.validate_file_path("../../../etc/passwd")
        assert len(result1["error"]) > 20  # Should have detailed message

        # Regex error
        result2 = validator.validate_regex("(a+)+")
        assert len(result2["error"]) > 20  # Should have detailed message


class TestRegexWithTestString:
    """Tests for regex validation with test string execution."""

    def test_safe_regex_with_test_string(self):
        """Safe regex with test string should pass."""
        from tree_sitter_analyzer_v2.security.validator import SecurityValidator

        validator = SecurityValidator(project_root="/tmp")
        result = validator.validate_regex("[a-z]+", test_string="hello world")
        assert result["valid"] is True

    def test_safe_regex_with_no_match(self):
        """Safe regex with non-matching test string should pass."""
        from tree_sitter_analyzer_v2.security.validator import SecurityValidator

        validator = SecurityValidator(project_root="/tmp")
        result = validator.validate_regex("^\\d+$", test_string="no digits here")
        assert result["valid"] is True

    def test_regex_with_complex_test_string(self):
        """Regex with complex but safe pattern and test string should pass."""
        from tree_sitter_analyzer_v2.security.validator import SecurityValidator

        validator = SecurityValidator(project_root="/tmp")
        result = validator.validate_regex(
            r"def\s+\w+\(.*\)\s*->",
            test_string="def hello(name: str) -> str:",
        )
        assert result["valid"] is True

    def test_invalid_regex_syntax_with_test_string(self):
        """Invalid regex should fail even before test string execution."""
        from tree_sitter_analyzer_v2.security.validator import SecurityValidator

        validator = SecurityValidator(project_root="/tmp")
        result = validator.validate_regex("[", test_string="test")
        assert result["valid"] is False
        assert "Invalid regex" in result["error"]


class TestPathValidationEdgeCases:
    """Edge case tests for path validation."""

    def test_path_validation_with_null_bytes(self, tmp_path):
        """Path with null bytes should fail gracefully."""
        from tree_sitter_analyzer_v2.security.validator import SecurityValidator

        project_root = tmp_path / "project"
        project_root.mkdir()
        validator = SecurityValidator(project_root=str(project_root))

        result = validator.validate_file_path("test\x00.py")
        # Should handle gracefully (either valid=False or exception caught)
        assert isinstance(result, dict)
        assert "valid" in result

    def test_nonexistent_file_path_valid(self, tmp_path):
        """Nonexistent file within project should be valid (path check only)."""
        from tree_sitter_analyzer_v2.security.validator import SecurityValidator

        project_root = tmp_path / "project"
        project_root.mkdir()
        validator = SecurityValidator(project_root=str(project_root))

        result = validator.validate_file_path("nonexistent.py")
        assert result["valid"] is True

    def test_directory_path_within_project(self, tmp_path):
        """Directory path within project should be valid."""
        from tree_sitter_analyzer_v2.security.validator import SecurityValidator

        project_root = tmp_path / "project"
        subdir = project_root / "src"
        subdir.mkdir(parents=True)
        validator = SecurityValidator(project_root=str(project_root))

        result = validator.validate_file_path(str(subdir))
        assert result["valid"] is True


class TestSecurityException:
    """Tests for security exception."""

    def test_security_violation_exception_exists(self):
        """Test SecurityViolationError exception exists."""
        from tree_sitter_analyzer_v2.core.exceptions import SecurityViolationError

        exception = SecurityViolationError("test violation")
        assert isinstance(exception, Exception)
        assert "test violation" in str(exception)

    def test_security_violation_with_details(self):
        """Test SecurityViolationError can include details."""
        from tree_sitter_analyzer_v2.core.exceptions import SecurityViolationError

        exception = SecurityViolationError(
            "Path traversal detected", details={"path": "../etc/passwd", "project_root": "/app"}
        )

        assert "Path traversal" in str(exception)
        assert hasattr(exception, "details")
