"""Unit tests for _exceptions_security — security exception hierarchy."""

from tree_sitter_analyzer._exceptions_core import TreeSitterAnalyzerError
from tree_sitter_analyzer._exceptions_security import (
    FileRestrictionError,
    PathTraversalError,
    RegexSecurityError,
    SecurityError,
)


class TestSecurityError:
    """Tests for SecurityError base class."""

    def test_basic_construction(self):
        exc = SecurityError("access denied")
        assert str(exc) == "access denied"
        assert exc.security_type is None
        assert exc.file_path is None

    def test_with_security_type(self):
        exc = SecurityError("blocked", security_type="path_traversal")
        assert exc.security_type == "path_traversal"
        assert exc.context["security_type"] == "path_traversal"

    def test_with_file_path(self):
        exc = SecurityError("blocked", file_path="/etc/passwd")
        assert exc.file_path == "/etc/passwd"
        assert exc.context["file_path"] == "/etc/passwd"

    def test_path_object_converted_to_string(self):
        from pathlib import Path

        exc = SecurityError("blocked", file_path=Path("/etc/shadow"))
        assert isinstance(exc.file_path, str)

    def test_inherits_from_base(self):
        exc = SecurityError("msg")
        assert isinstance(exc, TreeSitterAnalyzerError)

    def test_to_dict_includes_context(self):
        exc = SecurityError("msg", security_type="xss", file_path="/tmp/x")
        d = exc.to_dict()
        assert d["context"]["security_type"] == "xss"


class TestPathTraversalError:
    """Tests for PathTraversalError."""

    def test_with_attempted_path(self):
        exc = PathTraversalError(
            "traversal detected", attempted_path="../../../etc/passwd"
        )
        assert exc.attempted_path == "../../../etc/passwd"
        assert exc.security_type == "path_traversal"
        assert exc.context["attempted_path"] == "../../../etc/passwd"

    def test_without_attempted_path(self):
        exc = PathTraversalError("traversal")
        assert exc.attempted_path is None

    def test_inherits_security_type(self):
        exc = PathTraversalError("msg")
        assert exc.security_type == "path_traversal"

    def test_inherits_from_security_error(self):
        exc = PathTraversalError("msg")
        assert isinstance(exc, SecurityError)
        assert isinstance(exc, TreeSitterAnalyzerError)


class TestRegexSecurityError:
    """Tests for RegexSecurityError."""

    def test_with_pattern_and_construct(self):
        exc = RegexSecurityError(
            "dangerous regex",
            pattern="(a+)+b",
            dangerous_construct="nested_quantifier",
        )
        assert exc.pattern == "(a+)+b"
        assert exc.dangerous_construct == "nested_quantifier"
        assert exc.context["pattern"] == "(a+)+b"
        assert exc.context["dangerous_construct"] == "nested_quantifier"

    def test_without_optional_fields(self):
        exc = RegexSecurityError("bad")
        assert exc.pattern is None
        assert exc.dangerous_construct is None

    def test_security_type_is_regex(self):
        exc = RegexSecurityError("msg")
        assert exc.security_type == "regex_security"


class TestFileRestrictionError:
    """Tests for FileRestrictionError."""

    def test_with_mode_and_patterns(self):
        exc = FileRestrictionError(
            "restricted",
            file_path="/sys/kernel",
            current_mode="safe",
            allowed_patterns=["*.py", "*.js"],
        )
        assert exc.current_mode == "safe"
        assert exc.allowed_patterns == ["*.py", "*.js"]
        assert exc.context["current_mode"] == "safe"
        assert exc.file_path == "/sys/kernel"

    def test_security_type_is_file_restriction(self):
        exc = FileRestrictionError("msg")
        assert exc.security_type == "file_restriction"

    def test_without_optional_fields(self):
        exc = FileRestrictionError("msg")
        assert exc.current_mode is None
        assert exc.allowed_patterns is None
