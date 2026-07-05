"""Unit tests for _api_validation_helpers — input validation at API boundary."""

from unittest.mock import patch

from tree_sitter_analyzer.internal_api.validation_helpers import (
    apply_language_validation,
    mark_validation_readable,
    validation_result_template,
)


class TestValidationResultTemplate:
    """Tests for validation_result_template."""

    def test_default_shape(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("x = 1")
        result = validation_result_template(f)
        assert result["valid"] is False
        assert result["exists"] is True
        assert result["readable"] is False
        assert result["language"] is None
        assert result["supported"] is False
        assert result["size"] == 0
        assert result["errors"] == []

    def test_nonexistent_file(self, tmp_path):
        f = tmp_path / "nonexistent.py"
        result = validation_result_template(f)
        assert result["exists"] is False


class TestMarkValidationReadable:
    """Tests for mark_validation_readable."""

    def test_readable_file(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("print('hello')")
        result = validation_result_template(f)
        assert mark_validation_readable(f, result) is True
        assert result["readable"] is True
        assert result["size"] == len("print('hello')")

    def test_nonexistent_file(self, tmp_path):
        f = tmp_path / "nope.py"
        result = validation_result_template(f)
        assert mark_validation_readable(f, result) is False
        assert "File does not exist" in result["errors"]

    def test_permission_denied(self, tmp_path):
        f = tmp_path / "secret.py"
        f.write_text("secret")
        result = validation_result_template(f)
        with patch(
            "tree_sitter_analyzer.internal_api.validation_helpers.read_file_safe",
            side_effect=PermissionError("denied"),
        ):
            assert mark_validation_readable(f, result) is False
            assert any("not readable" in e for e in result["errors"])

    def test_unreadable_file_preserves_existing_errors(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("x")
        result = validation_result_template(f)
        result["errors"].append("prior error")
        with patch(
            "tree_sitter_analyzer.internal_api.validation_helpers.read_file_safe",
            side_effect=OSError("boom"),
        ):
            mark_validation_readable(f, result)
            assert len(result["errors"]) == 2


class TestApplyLanguageValidation:
    """Tests for apply_language_validation."""

    def test_supported_language(self):
        result = {"language": None, "supported": False, "errors": []}
        apply_language_validation(result, "python", lambda lang: True)
        assert result["language"] == "python"
        assert result["supported"] is True
        assert result["errors"] == []

    def test_unsupported_language(self):
        result = {"language": None, "supported": False, "errors": []}
        apply_language_validation(result, "brainfuck", lambda lang: False)
        assert result["supported"] is False
        assert any("not supported" in e for e in result["errors"])

    def test_empty_language(self):
        result = {"language": None, "supported": False, "errors": []}
        apply_language_validation(result, "", lambda lang: True)
        assert any("Could not detect" in e for e in result["errors"])

    def test_none_language(self):
        result = {"language": None, "supported": False, "errors": []}
        apply_language_validation(result, None, lambda lang: True)
        assert any("Could not detect" in e for e in result["errors"])

    def test_mutation_is_in_place(self):
        result = {"language": None, "supported": False, "errors": []}
        apply_language_validation(result, "java", lambda lang: True)
        assert result["language"] == "java"
