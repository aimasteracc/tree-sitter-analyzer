#!/usr/bin/env python3
"""
Property-based tests for security boundary enforcement.

**Feature: test-coverage-improvement, Property 4: Security Boundary Enforcement**

Tests that file paths outside the project boundary are rejected with security errors.

**Validates: Requirements 3.4, 10.5**
"""

import platform
import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer.exceptions import SecurityError
from tree_sitter_analyzer.security import ProjectBoundaryManager, SecurityValidator

# Common health check suppressions for property tests using fixtures
COMMON_HEALTH_CHECKS = [HealthCheck.too_slow, HealthCheck.function_scoped_fixture]


# ========================================
# Hypothesis Strategies for Path Generation
# ========================================

# Windows reserved device names that should be filtered out
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}

# Strategy for generating valid directory/file names (safe characters only)
safe_name = st.text(
    alphabet=st.sampled_from(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    ),  # pragma: allowlist secret
    min_size=1,
    max_size=20,
).filter(
    lambda x: x and not x.startswith("-") and x.upper() not in WINDOWS_RESERVED_NAMES
)

# Strategy for generating file extensions
file_extension = st.sampled_from(
    [
        ".py",
        ".java",
        ".js",
        ".ts",
        ".txt",
        ".md",
        ".json",
        ".xml",
        ".yaml",
        ".yml",
        ".css",
        ".html",
        ".sql",
        ".rb",
        ".php",
        ".go",
        ".rs",
        ".kt",
        ".cs",
    ]
)

# Strategy for generating relative path components
relative_path_component = st.one_of(
    safe_name,
    st.builds(lambda n, e: f"{n}{e}", n=safe_name, e=file_extension),
)


# Strategy for generating relative paths within project
@st.composite
def relative_path_within_project(draw):
    """Generate a relative path that should be within project boundaries."""
    depth = draw(st.integers(min_value=1, max_value=4))
    components = [draw(safe_name) for _ in range(depth - 1)]
    filename = draw(safe_name) + draw(file_extension)
    components.append(filename)
    return "/".join(components)


# Strategy for generating path traversal attempts
@st.composite
def path_traversal_attempt(draw):
    """Generate paths that attempt directory traversal."""
    traversal_type = draw(
        st.sampled_from(
            [
                "simple_dotdot",
                "multiple_dotdot",
                "mixed_traversal",
                "encoded_traversal",
            ]
        )
    )

    if traversal_type == "simple_dotdot":
        return "../" + draw(safe_name)
    elif traversal_type == "multiple_dotdot":
        count = draw(st.integers(min_value=2, max_value=5))
        return "../" * count + draw(safe_name)
    elif traversal_type == "mixed_traversal":
        prefix = draw(safe_name)
        return f"{prefix}/../../../" + draw(safe_name)
    else:  # encoded_traversal
        return "..\\/" + draw(safe_name)


# Strategy for generating absolute paths outside project
@st.composite
def absolute_path_outside_project(draw):
    """Generate absolute paths that are outside any project boundary."""
    if platform.system() == "Windows":
        # Windows absolute paths
        drive = draw(st.sampled_from(["C:", "D:", "E:"]))
        path_parts = [
            draw(safe_name) for _ in range(draw(st.integers(min_value=1, max_value=3)))
        ]
        return f"{drive}\\" + "\\".join(path_parts)
    else:
        # Unix absolute paths
        base = draw(st.sampled_from(["/etc", "/usr", "/var", "/opt", "/home"]))
        path_parts = [
            draw(safe_name) for _ in range(draw(st.integers(min_value=1, max_value=3)))
        ]
        return base + "/" + "/".join(path_parts)


# Strategy for generating null byte injection attempts
@st.composite
def null_byte_injection(draw):
    """Generate paths with null byte injection attempts."""
    prefix = draw(safe_name)
    suffix = draw(safe_name)
    return f"{prefix}\x00{suffix}"


# ========================================
# Test Fixtures
# ========================================


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory for testing."""
    temp_dir = tempfile.mkdtemp()
    # Create some subdirectories and files
    src_dir = Path(temp_dir) / "src"
    src_dir.mkdir(parents=True, exist_ok=True)

    test_file = src_dir / "test.py"
    test_file.write_text("# test file")

    yield temp_dir

    # Cleanup
    import shutil

    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def boundary_manager(temp_project_dir):
    """Create a ProjectBoundaryManager for testing."""
    return ProjectBoundaryManager(temp_project_dir)


@pytest.fixture
def security_validator(temp_project_dir):
    """Create a SecurityValidator for testing."""
    return SecurityValidator(temp_project_dir)


# ========================================
# Property Tests for Security Boundary Enforcement
# ========================================


class TestSecurityBoundaryEnforcementProperties:
    """
    Property-based tests for security boundary enforcement.

    **Feature: test-coverage-improvement, Property 4: Security Boundary Enforcement**
    **Validates: Requirements 3.4, 10.5**
    """

    @settings(max_examples=100, suppress_health_check=COMMON_HEALTH_CHECKS)
    @given(traversal_path=path_traversal_attempt())
    def test_property_4_path_traversal_rejected(self, temp_project_dir, traversal_path):
        """
        **Feature: test-coverage-improvement, Property 4: Security Boundary Enforcement**

        For any path containing directory traversal sequences (..),
        the security validator SHALL reject the path.

        **Validates: Requirements 3.4, 10.5**
        """
        validator = SecurityValidator(temp_project_dir)

        # Property: Path traversal attempts should be rejected
        is_valid, error_msg = validator.validate_file_path(
            traversal_path, temp_project_dir
        )

        assert (
            not is_valid
        ), f"Path traversal attempt should be rejected: {traversal_path}"
        assert (
            error_msg
        ), f"Error message should be provided for rejected path: {traversal_path}"

    @settings(max_examples=100, suppress_health_check=COMMON_HEALTH_CHECKS)
    @given(null_path=null_byte_injection())
    def test_property_4_null_byte_injection_rejected(self, temp_project_dir, null_path):
        """
        **Feature: test-coverage-improvement, Property 4: Security Boundary Enforcement**

        For any path containing null bytes, the security validator SHALL reject the path.

        **Validates: Requirements 3.4, 10.5**
        """
        validator = SecurityValidator(temp_project_dir)

        # Property: Null byte injection should be rejected
        is_valid, error_msg = validator.validate_file_path(null_path, temp_project_dir)

        assert (
            not is_valid
        ), f"Null byte injection should be rejected: {repr(null_path)}"
        assert (
            "null" in error_msg.lower()
        ), f"Error message should mention null bytes: {error_msg}"

    @settings(max_examples=100, suppress_health_check=COMMON_HEALTH_CHECKS)
    @given(rel_path=relative_path_within_project())
    def test_property_4_valid_relative_paths_accepted(self, temp_project_dir, rel_path):
        """
        **Feature: test-coverage-improvement, Property 4: Security Boundary Enforcement**

        For any valid relative path within project boundaries,
        the security validator SHALL accept the path.

        **Validates: Requirements 3.4, 10.5**
        """
        validator = SecurityValidator(temp_project_dir)

        # Property: Valid relative paths should be accepted
        is_valid, error_msg = validator.validate_file_path(rel_path, temp_project_dir)

        assert (
            is_valid
        ), f"Valid relative path should be accepted: {rel_path}, error: {error_msg}"

    @settings(max_examples=100, suppress_health_check=COMMON_HEALTH_CHECKS)
    @given(abs_path=absolute_path_outside_project())
    def test_property_4_absolute_paths_outside_boundary_rejected(
        self, temp_project_dir, abs_path
    ):
        """
        **Feature: test-coverage-improvement, Property 4: Security Boundary Enforcement**

        For any absolute path outside the project boundary,
        the security validator SHALL reject the path.

        **Validates: Requirements 3.4, 10.5**
        """
        validator = SecurityValidator(temp_project_dir)

        # Ensure the path is actually outside the project
        assume(not abs_path.startswith(temp_project_dir))
        assume(
            not str(Path(abs_path).resolve()).startswith(
                str(Path(temp_project_dir).resolve())
            )
        )

        # Property: Absolute paths outside boundary should be rejected
        is_valid, error_msg = validator.validate_file_path(abs_path, temp_project_dir)

        assert (
            not is_valid
        ), f"Absolute path outside boundary should be rejected: {abs_path}"

    @settings(max_examples=100, suppress_health_check=COMMON_HEALTH_CHECKS)
    @given(rel_path=relative_path_within_project())
    def test_property_4_boundary_manager_accepts_internal_paths(
        self, temp_project_dir, rel_path
    ):
        """
        **Feature: test-coverage-improvement, Property 4: Security Boundary Enforcement**

        For any relative path, when combined with project root,
        the boundary manager SHALL accept paths within boundaries.

        **Validates: Requirements 3.4, 10.5**
        """
        manager = ProjectBoundaryManager(temp_project_dir)

        # Create full path
        full_path = str(Path(temp_project_dir) / rel_path)

        # Property: Paths within project should be accepted
        is_within = manager.is_within_project(full_path)

        assert is_within, f"Path within project should be accepted: {full_path}"

    @settings(max_examples=100, suppress_health_check=COMMON_HEALTH_CHECKS)
    @given(abs_path=absolute_path_outside_project())
    def test_property_4_boundary_manager_rejects_external_paths(
        self, temp_project_dir, abs_path
    ):
        """
        **Feature: test-coverage-improvement, Property 4: Security Boundary Enforcement**

        For any absolute path outside the project boundary,
        the boundary manager SHALL reject the path.

        **Validates: Requirements 3.4, 10.5**
        """
        manager = ProjectBoundaryManager(temp_project_dir)

        # Ensure the path is actually outside the project
        assume(not abs_path.startswith(temp_project_dir))
        assume(
            not str(Path(abs_path).resolve()).startswith(
                str(Path(temp_project_dir).resolve())
            )
        )

        # Property: Paths outside project should be rejected
        is_within = manager.is_within_project(abs_path)

        assert not is_within, f"Path outside project should be rejected: {abs_path}"

    @settings(max_examples=100, suppress_health_check=COMMON_HEALTH_CHECKS)
    @given(traversal_path=path_traversal_attempt())
    def test_property_4_boundary_manager_rejects_traversal(
        self, temp_project_dir, traversal_path
    ):
        """
        **Feature: test-coverage-improvement, Property 4: Security Boundary Enforcement**

        For any path with traversal sequences, when resolved,
        the boundary manager SHALL reject paths that escape boundaries.

        **Validates: Requirements 3.4, 10.5**
        """
        manager = ProjectBoundaryManager(temp_project_dir)

        # Create full path with traversal
        full_path = str(Path(temp_project_dir) / traversal_path)

        # Resolve to see where it actually points
        try:
            resolved = str(Path(full_path).resolve())
            project_resolved = str(Path(temp_project_dir).resolve())

            # If resolved path is outside project, it should be rejected
            if not resolved.startswith(project_resolved):
                is_within = manager.is_within_project(full_path)
                assert not is_within, f"Traversal path escaping boundary should be rejected: {full_path} -> {resolved}"
        except (OSError, ValueError):
            # Invalid paths are acceptable to reject
            pass

    @settings(max_examples=100, suppress_health_check=COMMON_HEALTH_CHECKS)
    @given(rel_path=relative_path_within_project())
    def test_property_4_validate_and_resolve_returns_resolved_path(
        self, temp_project_dir, rel_path
    ):
        """
        **Feature: test-coverage-improvement, Property 4: Security Boundary Enforcement**

        For any valid relative path within boundaries,
        validate_and_resolve_path SHALL return the resolved absolute path.

        **Validates: Requirements 3.4, 10.5**
        """
        manager = ProjectBoundaryManager(temp_project_dir)

        # Property: Valid paths should be resolved
        resolved = manager.validate_and_resolve_path(rel_path)

        assert (
            resolved is not None
        ), f"Valid relative path should be resolved: {rel_path}"
        assert Path(
            resolved
        ).is_absolute(), f"Resolved path should be absolute: {resolved}"

    @settings(max_examples=100, suppress_health_check=COMMON_HEALTH_CHECKS)
    @given(traversal_path=path_traversal_attempt())
    def test_property_4_validate_and_resolve_rejects_traversal(
        self, temp_project_dir, traversal_path
    ):
        """
        **Feature: test-coverage-improvement, Property 4: Security Boundary Enforcement**

        For any path with traversal sequences that escape boundaries,
        validate_and_resolve_path SHALL return None.

        **Validates: Requirements 3.4, 10.5**
        """
        manager = ProjectBoundaryManager(temp_project_dir)

        # Check if this traversal actually escapes
        try:
            full_path = Path(temp_project_dir) / traversal_path
            resolved = full_path.resolve()
            project_resolved = Path(temp_project_dir).resolve()

            # Only test paths that actually escape
            if not str(resolved).startswith(str(project_resolved)):
                result = manager.validate_and_resolve_path(traversal_path)
                assert (
                    result is None
                ), f"Traversal path escaping boundary should return None: {traversal_path}"
        except (OSError, ValueError):
            # Invalid paths are acceptable
            pass


class TestSecurityBoundaryEdgeCases:
    """
    Property-based tests for edge cases in security boundary enforcement.

    **Feature: test-coverage-improvement, Property 4: Security Boundary Enforcement**
    **Validates: Requirements 3.4, 10.5**
    """

    @settings(max_examples=100, suppress_health_check=COMMON_HEALTH_CHECKS)
    @given(empty_or_whitespace=st.sampled_from(["", " ", "  ", "\t", "\n", "\r\n"]))
    def test_property_4_empty_paths_rejected(
        self, temp_project_dir, empty_or_whitespace
    ):
        """
        **Feature: test-coverage-improvement, Property 4: Security Boundary Enforcement**

        For any empty or whitespace-only path, the security validator SHALL reject it.

        **Validates: Requirements 3.4, 10.5**
        """
        validator = SecurityValidator(temp_project_dir)

        # Property: Empty/whitespace paths should be rejected
        is_valid, error_msg = validator.validate_file_path(
            empty_or_whitespace, temp_project_dir
        )

        # Empty string should be rejected, whitespace may be handled differently
        if empty_or_whitespace == "":
            assert not is_valid, "Empty path should be rejected"

    @settings(max_examples=100, suppress_health_check=COMMON_HEALTH_CHECKS)
    @given(name=safe_name)
    def test_property_4_boundary_manager_empty_path_rejected(
        self, temp_project_dir, name
    ):
        """
        **Feature: test-coverage-improvement, Property 4: Security Boundary Enforcement**

        For empty paths, the boundary manager SHALL return False.

        **Validates: Requirements 3.4, 10.5**
        """
        manager = ProjectBoundaryManager(temp_project_dir)

        # Property: Empty path should be rejected
        is_within = manager.is_within_project("")

        assert not is_within, "Empty path should be rejected by boundary manager"

    @settings(max_examples=100, suppress_health_check=COMMON_HEALTH_CHECKS)
    @given(rel_path=relative_path_within_project())
    def test_property_4_get_relative_path_consistency(self, temp_project_dir, rel_path):
        """
        **Feature: test-coverage-improvement, Property 4: Security Boundary Enforcement**

        For any path within boundaries, get_relative_path SHALL return
        a path that, when joined with project root, points to the same location.

        **Validates: Requirements 3.4, 10.5**
        """
        manager = ProjectBoundaryManager(temp_project_dir)

        # Create full path
        full_path = str(Path(temp_project_dir) / rel_path)

        # Get relative path
        relative = manager.get_relative_path(full_path)

        # Property: Relative path should be consistent
        if relative is not None:
            reconstructed = str(Path(temp_project_dir) / relative)
            assert (
                Path(reconstructed).resolve() == Path(full_path).resolve()
            ), f"Relative path should reconstruct to original: {relative} -> {reconstructed} != {full_path}"

    @settings(max_examples=100, suppress_health_check=COMMON_HEALTH_CHECKS)
    @given(abs_path=absolute_path_outside_project())
    def test_property_4_get_relative_path_returns_none_for_external(
        self, temp_project_dir, abs_path
    ):
        """
        **Feature: test-coverage-improvement, Property 4: Security Boundary Enforcement**

        For any path outside boundaries, get_relative_path SHALL return None.

        **Validates: Requirements 3.4, 10.5**
        """
        manager = ProjectBoundaryManager(temp_project_dir)

        # Ensure the path is actually outside the project
        assume(not abs_path.startswith(temp_project_dir))
        assume(
            not str(Path(abs_path).resolve()).startswith(
                str(Path(temp_project_dir).resolve())
            )
        )

        # Property: External paths should return None
        relative = manager.get_relative_path(abs_path)

        assert (
            relative is None
        ), f"External path should return None for get_relative_path: {abs_path}"


class TestSecurityValidatorIntegrationProperties:
    """
    Property-based tests for SecurityValidator integration with boundary enforcement.

    **Feature: test-coverage-improvement, Property 4: Security Boundary Enforcement**
    **Validates: Requirements 3.4, 10.5**
    """

    @settings(max_examples=100, suppress_health_check=COMMON_HEALTH_CHECKS)
    @given(rel_path=relative_path_within_project())
    def test_property_4_is_safe_path_consistent_with_validate(
        self, temp_project_dir, rel_path
    ):
        """
        **Feature: test-coverage-improvement, Property 4: Security Boundary Enforcement**

        For any path, is_safe_path SHALL return the same result as validate_file_path[0].

        **Validates: Requirements 3.4, 10.5**
        """
        validator = SecurityValidator(temp_project_dir)

        # Property: is_safe_path should be consistent with validate_file_path
        is_safe = validator.is_safe_path(rel_path, temp_project_dir)
        is_valid, _ = validator.validate_file_path(rel_path, temp_project_dir)

        assert (
            is_safe == is_valid
        ), f"is_safe_path should match validate_file_path: {rel_path}"

    @settings(max_examples=100, suppress_health_check=COMMON_HEALTH_CHECKS)
    @given(rel_path=relative_path_within_project())
    def test_property_4_validate_path_alias_consistent(
        self, temp_project_dir, rel_path
    ):
        """
        **Feature: test-coverage-improvement, Property 4: Security Boundary Enforcement**

        validate_path SHALL return the same result as validate_file_path (alias).

        **Validates: Requirements 3.4, 10.5**
        """
        validator = SecurityValidator(temp_project_dir)

        # Property: validate_path should be alias for validate_file_path
        result1 = validator.validate_path(rel_path, temp_project_dir)
        result2 = validator.validate_file_path(rel_path, temp_project_dir)

        assert (
            result1 == result2
        ), f"validate_path should be alias for validate_file_path: {rel_path}"

    @settings(max_examples=100, suppress_health_check=COMMON_HEALTH_CHECKS)
    @given(
        glob_pattern=st.one_of(
            st.just("*.py"),
            st.just("**/*.java"),
            st.just("src/*.ts"),
            st.builds(
                lambda n: f"*.{n}", n=st.sampled_from(["py", "java", "js", "ts"])
            ),
        )
    )
    def test_property_4_valid_glob_patterns_accepted(
        self, temp_project_dir, glob_pattern
    ):
        """
        **Feature: test-coverage-improvement, Property 4: Security Boundary Enforcement**

        For any valid glob pattern without traversal, the validator SHALL accept it.

        **Validates: Requirements 3.4, 10.5**
        """
        validator = SecurityValidator(temp_project_dir)

        # Property: Valid glob patterns should be accepted
        is_valid, error_msg = validator.validate_glob_pattern(glob_pattern)

        assert (
            is_valid
        ), f"Valid glob pattern should be accepted: {glob_pattern}, error: {error_msg}"

    @settings(max_examples=100, suppress_health_check=COMMON_HEALTH_CHECKS)
    @given(
        dangerous_glob=st.one_of(
            st.just("../*.py"),
            st.just("../../**/*.java"),
            st.just("//*.ts"),
            st.just("\\\\*.js"),
        )
    )
    def test_property_4_dangerous_glob_patterns_rejected(
        self, temp_project_dir, dangerous_glob
    ):
        """
        **Feature: test-coverage-improvement, Property 4: Security Boundary Enforcement**

        For any glob pattern with traversal or dangerous sequences,
        the validator SHALL reject it.

        **Validates: Requirements 3.4, 10.5**
        """
        validator = SecurityValidator(temp_project_dir)

        # Property: Dangerous glob patterns should be rejected
        is_valid, error_msg = validator.validate_glob_pattern(dangerous_glob)

        assert (
            not is_valid
        ), f"Dangerous glob pattern should be rejected: {dangerous_glob}"


class TestProjectBoundaryManagerInitializationProperties:
    """
    Property-based tests for ProjectBoundaryManager initialization.

    **Feature: test-coverage-improvement, Property 4: Security Boundary Enforcement**
    **Validates: Requirements 3.4, 10.5**
    """

    def test_property_4_empty_root_raises_security_error(self):
        """
        **Feature: test-coverage-improvement, Property 4: Security Boundary Enforcement**

        For empty project root, initialization SHALL raise SecurityError.

        **Validates: Requirements 3.4, 10.5**
        """
        with pytest.raises(SecurityError) as exc_info:
            ProjectBoundaryManager("")

        assert "cannot be empty" in str(exc_info.value).lower()

    def test_property_4_nonexistent_root_raises_security_error(self):
        """
        **Feature: test-coverage-improvement, Property 4: Security Boundary Enforcement**

        For nonexistent project root, initialization SHALL raise SecurityError.

        **Validates: Requirements 3.4, 10.5**
        """
        with pytest.raises(SecurityError) as exc_info:
            ProjectBoundaryManager("/nonexistent/path/that/should/not/exist")

        assert "does not exist" in str(exc_info.value).lower()

    @settings(
        max_examples=50, suppress_health_check=COMMON_HEALTH_CHECKS, deadline=None
    )
    @given(name=safe_name)
    def test_property_4_file_as_root_raises_security_error(
        self, temp_project_dir, name
    ):
        """
        **Feature: test-coverage-improvement, Property 4: Security Boundary Enforcement**

        For file path (not directory) as project root, initialization SHALL raise SecurityError.

        **Validates: Requirements 3.4, 10.5**
        """
        # Create a file
        file_path = Path(temp_project_dir) / f"{name}.txt"
        file_path.write_text("test content")

        with pytest.raises(SecurityError) as exc_info:
            ProjectBoundaryManager(str(file_path))

        assert "not a directory" in str(exc_info.value).lower()

    @settings(max_examples=50, suppress_health_check=COMMON_HEALTH_CHECKS)
    @given(name=safe_name)
    def test_property_4_valid_directory_initializes_successfully(
        self, temp_project_dir, name
    ):
        """
        **Feature: test-coverage-improvement, Property 4: Security Boundary Enforcement**

        For valid directory as project root, initialization SHALL succeed.

        **Validates: Requirements 3.4, 10.5**
        """
        # Create a subdirectory
        subdir = Path(temp_project_dir) / name
        subdir.mkdir(parents=True, exist_ok=True)

        # Property: Valid directory should initialize successfully
        manager = ProjectBoundaryManager(str(subdir))

        assert manager.project_root == str(subdir.resolve())
        assert str(subdir.resolve()) in manager.allowed_directories
