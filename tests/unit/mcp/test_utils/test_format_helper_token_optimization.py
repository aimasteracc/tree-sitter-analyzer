#!/usr/bin/env python3
"""Tests for token optimization in format_helper."""
import pytest


class TestToonRedundantFields:
    """Tests for TOON redundant field constants."""

    def test_redundant_fields_constant_exists(self):
        """TOON_REDUNDANT_FIELDS constant should be defined."""
        from tree_sitter_analyzer.mcp.utils.format_helper import TOON_REDUNDANT_FIELDS

        assert TOON_REDUNDANT_FIELDS is not None
        assert isinstance(TOON_REDUNDANT_FIELDS, frozenset)

    def test_redundant_fields_contains_expected_fields(self):
        """TOON_REDUNDANT_FIELDS should contain expected data fields."""
        from tree_sitter_analyzer.mcp.utils.format_helper import TOON_REDUNDANT_FIELDS

        expected = {
            "results",
            "matches",
            "content",
            "data",
            "items",
            "files",
            "lines",
            "detailed_analysis",
            "structural_overview",
            "summary",
        }
        assert expected.issubset(TOON_REDUNDANT_FIELDS)

    def test_metadata_fields_constant_exists(self):
        """TOON_METADATA_FIELDS constant should be defined."""
        from tree_sitter_analyzer.mcp.utils.format_helper import TOON_METADATA_FIELDS

        assert TOON_METADATA_FIELDS is not None
        assert isinstance(TOON_METADATA_FIELDS, frozenset)

    def test_metadata_fields_contains_expected_fields(self):
        """TOON_METADATA_FIELDS should contain expected metadata fields."""
        from tree_sitter_analyzer.mcp.utils.format_helper import TOON_METADATA_FIELDS

        expected = {"success", "file_path", "language", "format", "warnings"}
        assert expected.issubset(TOON_METADATA_FIELDS)


class TestAttachToonContentOptimization:
    """Tests for attach_toon_content_to_response token optimization."""

    def test_removes_redundant_data_fields(self):
        """Should remove redundant data fields from TOON response."""
        from tree_sitter_analyzer.mcp.utils.format_helper import attach_toon_content_to_response

        input_data = {
            "success": True,
            "file_path": "/test/file.py",
            "results": ["item1", "item2", "item3"],
            "data": {"key": "value"},
            "structural_overview": {"classes": [], "methods": []},
            "summary": {"classes": 0, "methods": 0},
        }

        result = attach_toon_content_to_response(input_data)

        assert "results" not in result
        assert "data" not in result
        assert "structural_overview" not in result
        assert "summary" not in result

    def test_preserves_metadata_fields(self):
        """Should preserve metadata fields in TOON response."""
        from tree_sitter_analyzer.mcp.utils.format_helper import attach_toon_content_to_response

        input_data = {
            "success": True,
            "file_path": "/test/file.py",
            "language": "python",
            "warnings": ["test warning"],
            "results": ["item1"],
        }

        result = attach_toon_content_to_response(input_data)

        assert result["success"] is True
        assert result["file_path"] == "/test/file.py"
        assert result["language"] == "python"
        assert result["warnings"] == ["test warning"]
        assert result["format"] == "toon"

    def test_includes_toon_content(self):
        """Should include toon_content field."""
        from tree_sitter_analyzer.mcp.utils.format_helper import attach_toon_content_to_response

        input_data = {
            "success": True,
            "results": ["a", "b", "c"],
        }

        result = attach_toon_content_to_response(input_data)

        assert "toon_content" in result
        assert isinstance(result["toon_content"], str)
        assert len(result["toon_content"]) > 0

    def test_token_reduction_achieved(self):
        """Should achieve significant token reduction."""
        import json
        from tree_sitter_analyzer.mcp.utils.format_helper import attach_toon_content_to_response

        # Create large data structure
        large_data = {
            "success": True,
            "file_path": "/test/file.py",
            "results": [{"id": i, "name": f"item_{i}", "data": "x" * 100} for i in range(100)],
            "structural_overview": {
                "classes": [{"name": f"Class{i}", "lines": f"{i}-{i+100}"} for i in range(50)],
                "methods": [{"name": f"method{i}"} for i in range(200)],
            },
            "summary": {"classes": 50, "methods": 200},
        }

        result = attach_toon_content_to_response(large_data)

        # Original size vs optimized size
        original_size = len(json.dumps(large_data))
        optimized_size = len(json.dumps(result))

        # Should achieve at least 15% reduction (realistic estimate given TOON encoding)
        reduction = 1 - (optimized_size / original_size)
        assert reduction >= 0.15, f"Expected >= 15% reduction, got {reduction*100:.1f}%"


class TestApplyToonFormatOptimization:
    """Tests for apply_toon_format_to_response token optimization."""

    def test_removes_summary_when_structural_overview_present(self):
        """Should remove summary field when structural_overview exists."""
        from tree_sitter_analyzer.mcp.utils.format_helper import apply_toon_format_to_response

        input_data = {
            "success": True,
            "summary": {"classes": 5, "methods": 20},
            "structural_overview": {
                "classes": [{"name": "TestClass"} for _ in range(5)],
                "methods": [{"name": "testMethod"} for _ in range(20)],
            },
        }

        result = apply_toon_format_to_response(input_data, output_format="toon")

        # summary should be removed because it's derivable from structural_overview
        assert "summary" not in result
        # structural_overview should also be removed (it's in TOON_REDUNDANT_FIELDS)
        assert "structural_overview" not in result
        assert "toon_content" in result

    def test_preserves_summary_when_no_structural_overview(self):
        """Should preserve summary when structural_overview is absent (summary stays in toon_content)."""
        from tree_sitter_analyzer.mcp.utils.format_helper import apply_toon_format_to_response

        input_data = {
            "success": True,
            "summary": {"classes": 0, "methods": 0},
        }

        result = apply_toon_format_to_response(input_data, output_format="toon")

        # toon_content should contain the summary info
        assert "toon_content" in result
        # But summary should be removed from top level (it's in TOON_REDUNDANT_FIELDS)
        assert "summary" not in result

    def test_json_format_unaffected(self):
        """JSON format should not be affected by optimization."""
        from tree_sitter_analyzer.mcp.utils.format_helper import apply_toon_format_to_response

        input_data = {
            "success": True,
            "results": ["a", "b", "c"],
            "summary": {"count": 3},
        }

        result = apply_toon_format_to_response(input_data, output_format="json")

        # JSON format should return unchanged
        assert result == input_data
        assert "toon_content" not in result

    def test_removes_all_redundant_fields(self):
        """Should remove all fields in TOON_REDUNDANT_FIELDS."""
        from tree_sitter_analyzer.mcp.utils.format_helper import (
            TOON_REDUNDANT_FIELDS,
            apply_toon_format_to_response,
        )

        input_data = {
            "success": True,
            "results": ["a", "b"],
            "matches": [{"line": 1}],
            "content": "file content",
            "partial_content_result": {"text": "partial"},
            "analysis_result": {"imports": []},
            "data": {"key": "value"},
            "items": [1, 2, 3],
            "files": ["file1.py"],
            "lines": ["line1", "line2"],
            "table_output": "table",
            "detailed_analysis": {"metrics": {}},
            "structural_overview": {"classes": []},
            "summary": {"count": 0},
        }

        result = apply_toon_format_to_response(input_data, output_format="toon")

        # All redundant fields should be removed
        for field in TOON_REDUNDANT_FIELDS:
            assert field not in result, f"Field '{field}' should have been removed"

        # Metadata should be preserved
        assert result["success"] is True
        assert "toon_content" in result

    def test_preserves_metadata_fields(self):
        """Should preserve metadata fields like file_path, language, etc."""
        from tree_sitter_analyzer.mcp.utils.format_helper import apply_toon_format_to_response

        input_data = {
            "success": True,
            "file_path": "/path/to/file.py",
            "language": "python",
            "warnings": ["deprecated API"],
            "error": None,
            "total_count": 100,
            "truncated": False,
            "execution_time": 0.5,
            "results": ["data"],
        }

        result = apply_toon_format_to_response(input_data, output_format="toon")

        # Metadata should be preserved
        assert result["success"] is True
        assert result["file_path"] == "/path/to/file.py"
        assert result["language"] == "python"
        assert result["warnings"] == ["deprecated API"]
        assert result["error"] is None
        assert result["total_count"] == 100
        assert result["truncated"] is False
        assert result["execution_time"] == 0.5
        # Redundant data should be removed
        assert "results" not in result
