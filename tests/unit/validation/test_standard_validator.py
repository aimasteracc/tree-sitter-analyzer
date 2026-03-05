"""Tests for standardized input validation."""
import pytest


class TestStandardValidator:
    """Test standardized input validation."""

    @pytest.fixture
    def validator(self):
        """Create StandardValidator instance."""
        from tree_sitter_analyzer.validation.standard_validator import StandardValidator

        return StandardValidator()

    def test_validate_file_path_valid(self, validator, tmp_path):
        """Valid file paths should pass."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        result = validator.validate_file_path(str(test_file))
        assert result.is_valid
        assert result.resolved_path is not None

    def test_validate_file_path_traversal(self, validator):
        """Path traversal should be rejected."""
        result = validator.validate_file_path("../../../etc/passwd")
        assert not result.is_valid
        assert "traversal" in result.error.lower()

    def test_validate_positive_integer(self, validator):
        """Positive integers should pass."""
        result = validator.validate_positive_integer(5, "count")
        assert result.is_valid

    def test_validate_positive_integer_negative(self, validator):
        """Negative values should fail."""
        result = validator.validate_positive_integer(-1, "count")
        assert not result.is_valid

    def test_validate_positive_integer_zero(self, validator):
        """Zero should fail for positive integer."""
        result = validator.validate_positive_integer(0, "count")
        assert not result.is_valid

    def test_validate_output_format_valid(self, validator):
        """Valid output formats should pass."""
        for fmt in ["json", "text", "toon", "table", "csv"]:
            result = validator.validate_output_format(fmt)
            assert result.is_valid, f"Format {fmt} should be valid"

    def test_validate_output_format_invalid(self, validator):
        """Invalid output formats should fail."""
        result = validator.validate_output_format("invalid_format")
        assert not result.is_valid

    def test_validate_file_path_empty(self, validator):
        """Empty path should be rejected."""
        result = validator.validate_file_path("")
        assert not result.is_valid
        assert "empty" in result.error.lower()

    def test_validate_file_path_none(self, validator):
        """None path should be rejected."""
        result = validator.validate_file_path(None)
        assert not result.is_valid

    def test_validate_non_negative_integer(self, validator):
        """Non-negative integers (>= 0) should pass."""
        result = validator.validate_non_negative_integer(0, "count")
        assert result.is_valid

        result = validator.validate_non_negative_integer(5, "count")
        assert result.is_valid

    def test_validate_non_negative_integer_negative(self, validator):
        """Negative values should fail for non-negative integer."""
        result = validator.validate_non_negative_integer(-1, "count")
        assert not result.is_valid

    def test_validate_positive_integer_non_int(self, validator):
        """Non-integer types should fail."""
        result = validator.validate_positive_integer("5", "count")
        assert not result.is_valid
        assert "integer" in result.error.lower()

    def test_validate_output_format_empty(self, validator):
        """Empty format should be rejected."""
        result = validator.validate_output_format("")
        assert not result.is_valid
        assert "empty" in result.error.lower()

    def test_validate_output_format_case_insensitive(self, validator):
        """Output format validation should be case-insensitive."""
        result = validator.validate_output_format("JSON")
        assert result.is_valid
        assert result.value == "json"

        result = validator.validate_output_format("Table")
        assert result.is_valid
        assert result.value == "table"

    def test_validate_file_path_system_paths(self, validator):
        """System paths should be rejected."""
        result = validator.validate_file_path("/etc/passwd")
        assert not result.is_valid
        assert "denied" in result.error.lower() or "system" in result.error.lower()
