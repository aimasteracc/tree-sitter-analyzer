#!/usr/bin/env python3
"""
Integration tests for security module with MCP server.
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.exceptions import SecurityError
from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
from tree_sitter_analyzer.security import SecurityValidator


class TestSecurityMCPIntegration:
    """Integration test suite for security module with MCP server."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = str(Path(self.temp_dir) / "secure_project")
        Path(self.project_root).mkdir(exist_ok=True)

        # Create test file structure
        self.src_dir = str(Path(self.project_root) / "src")
        Path(self.src_dir).mkdir(exist_ok=True)

        self.test_file = str(Path(self.src_dir) / "main.py")
        with open(self.test_file, "w") as f:
            f.write("print('Hello, World!')")

        # Initialize MCP server
        self.mcp_server = TreeSitterAnalyzerMCPServer()
        self.mcp_server.set_project_path(self.project_root)

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.integration
    def test_security_validator_with_mcp_project_path(self):
        """Test security validator works with MCP server project path."""
        # Arrange
        validator = SecurityValidator(self.project_root)

        # Act & Assert - Valid file path within MCP project
        is_valid, error = validator.validate_file_path("src/main.py", self.project_root)
        assert is_valid
        assert error == ""

        # Act & Assert - Invalid path traversal
        is_valid, error = validator.validate_file_path(
            "../../../etc/passwd", self.project_root
        )
        assert not is_valid
        assert "traversal" in error.lower()

    @pytest.mark.integration
    def test_mcp_server_with_security_validation(self):
        """Test MCP server operations with security validation."""
        # Arrange
        validator = SecurityValidator(self.project_root)

        # Test file paths that MCP server might receive
        test_paths = [
            ("src/main.py", True),  # Valid project file
            ("../../../etc/passwd", False),  # Path traversal attack
            ("", False),  # Empty path
            ("src/test\x00.py", False),  # Null byte injection
        ]

        for file_path, should_be_valid in test_paths:
            # Act
            is_valid, error = validator.validate_file_path(file_path, self.project_root)

            # Assert
            if should_be_valid:
                assert is_valid, f"Path should be valid: {file_path}"
                assert error == ""
            else:
                assert not is_valid, f"Path should be invalid: {file_path}"
                assert error != ""

    @pytest.mark.integration
    def test_regex_validation_for_mcp_queries(self):
        """Test regex validation for MCP query patterns."""
        # Arrange
        validator = SecurityValidator()

        # Test regex patterns that might be used in MCP queries
        test_patterns = [
            (r"def\s+\w+\s*\(", True),  # Safe function definition pattern
            (r"class\s+\w+", True),  # Safe class definition pattern
            (r"(.+)+", False),  # Dangerous ReDoS pattern
            (r"(.*)*", False),  # Another dangerous pattern
            (r"import\s+[\w.]+", True),  # Safe import pattern
        ]

        for pattern, should_be_safe in test_patterns:
            # Act
            is_safe, error = validator.validate_regex_pattern(pattern)

            # Assert
            if should_be_safe:
                assert is_safe, f"Pattern should be safe: {pattern}"
                assert error == ""
            else:
                assert not is_safe, f"Pattern should be dangerous: {pattern}"
                assert "dangerous" in error.lower()

    @pytest.mark.integration
    def test_input_sanitization_for_mcp_requests(self):
        """Test input sanitization for MCP request data."""
        # Arrange
        validator = SecurityValidator()

        # Test inputs that might come from MCP requests
        test_inputs = [
            ("normal_function_name", "normal_function_name"),
            ("function\x00name", "functionname"),  # Null byte removal
            ("func\x01\x02name", "funcname"),  # Control char removal
            ("valid_input_123", "valid_input_123"),
        ]

        for input_text, expected_output in test_inputs:
            # Act
            sanitized = validator.sanitize_input(input_text)

            # Assert
            assert sanitized == expected_output

    @pytest.mark.integration
    def test_mcp_server_security_workflow(self):
        """Test complete security workflow with MCP server."""
        # Arrange
        validator = SecurityValidator(self.project_root)

        # Simulate MCP server receiving a request
        request_data = {
            "file_path": "src/main.py",
            "query_pattern": r"def\s+\w+",
            "user_input": "search_term",
        }

        # Act - Validate all components
        file_valid, file_error = validator.validate_file_path(
            request_data["file_path"], self.project_root
        )

        regex_valid, regex_error = validator.validate_regex_pattern(
            request_data["query_pattern"]
        )

        sanitized_input = validator.sanitize_input(request_data["user_input"])

        # Assert
        assert file_valid, f"File validation failed: {file_error}"
        assert regex_valid, f"Regex validation failed: {regex_error}"
        assert sanitized_input == request_data["user_input"]

        # Overall security check
        overall_safe = file_valid and regex_valid
        assert overall_safe, "Overall security check should pass"

    @pytest.mark.integration
    def test_security_error_handling_in_mcp_context(self):
        """Test security error handling in MCP context."""
        # Arrange
        validator = SecurityValidator()

        # Test various security violations
        security_violations = [
            (
                "path_traversal",
                lambda: validator.validate_file_path("../../../etc/passwd"),
            ),
            ("dangerous_regex", lambda: validator.validate_regex_pattern(r"(.+)+")),
            (
                "input_too_long",
                lambda: validator.sanitize_input("a" * 2000, max_length=100),
            ),
        ]

        for violation_type, violation_func in security_violations:
            # Act & Assert
            if violation_type == "input_too_long":
                with pytest.raises(SecurityError):
                    violation_func()
            else:
                is_valid, error = violation_func()
                assert (
                    not is_valid
                ), f"Security violation should be detected: {violation_type}"
                assert (
                    error != ""
                ), f"Error message should be provided for: {violation_type}"

    @pytest.mark.integration
    def test_mcp_server_project_boundary_enforcement(self):
        """Test MCP server respects project boundaries."""
        # Arrange
        validator = SecurityValidator(self.project_root)

        # Create file outside project
        outside_file = str(Path(self.temp_dir) / "outside.py")
        with open(outside_file, "w") as f:
            f.write("print('Outside project')")

        # Test boundary enforcement
        test_cases = [
            (str(Path("src") / "main.py"), True),  # Inside project
            ("../outside.py", False),  # Outside project
            (outside_file, False),  # Absolute path outside
        ]

        for file_path, should_be_allowed in test_cases:
            # Act
            is_valid, error = validator.validate_file_path(file_path, self.project_root)

            # Assert
            if should_be_allowed:
                assert is_valid, f"File should be allowed: {file_path}"
            else:
                assert not is_valid, f"File should be blocked: {file_path}"

    @pytest.mark.integration
    def test_security_logging_integration(self):
        """Test security logging integration with MCP server."""
        # Arrange
        validator = SecurityValidator(self.project_root)

        # Test operations that should generate security logs
        security_operations = [
            (
                "valid_access",
                lambda: validator.validate_file_path("src/main.py", self.project_root),
            ),
            (
                "blocked_access",
                lambda: validator.validate_file_path(
                    "../../../etc/passwd", self.project_root
                ),
            ),
            ("regex_check", lambda: validator.validate_regex_pattern(r"(.+)+")),
        ]

        for operation_name, operation_func in security_operations:
            # Act - should not raise exceptions
            try:
                result = operation_func()
                # For validation functions, result is a tuple
                if isinstance(result, tuple):
                    is_valid, error = result
                    # Log the result for verification
                    print(f"{operation_name}: valid={is_valid}, error='{error}'")
            except Exception as e:
                pytest.fail(
                    f"Security operation {operation_name} raised unexpected exception: {e}"
                )

    @pytest.mark.integration
    def test_performance_impact_on_mcp_server(self):
        """Test that security validation doesn't significantly impact MCP server performance."""
        import time

        # Arrange
        validator = SecurityValidator(self.project_root)

        # Test performance of security operations
        operations = [
            (
                "file_validation",
                lambda: validator.validate_file_path("src/main.py", self.project_root),
            ),
            (
                "regex_validation",
                lambda: validator.validate_regex_pattern(r"def\s+\w+"),
            ),
            ("input_sanitization", lambda: validator.sanitize_input("test_input")),
        ]

        for operation_name, operation_func in operations:
            # Act - measure execution time
            start_time = time.time()
            for _ in range(100):  # Run 100 times to get average
                operation_func()
            end_time = time.time()

            # Assert - should be fast (< 10ms average)
            avg_time = (end_time - start_time) / 100
            assert (
                avg_time < 0.01
            ), f"{operation_name} too slow: {avg_time:.4f}s average"
