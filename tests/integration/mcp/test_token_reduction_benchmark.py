#!/usr/bin/env python3
"""Token reduction benchmark tests."""
import json


class TestTokenReductionBenchmark:
    """Benchmark tests to verify token reduction."""

    def test_toon_vs_json_token_reduction(self):
        """TOON format should achieve significant token reduction."""
        from tree_sitter_analyzer.mcp.utils.format_helper import (
            apply_toon_format_to_response,
            format_as_json,
        )

        # Create realistic large response
        large_response = {
            "success": True,
            "file_path": "/project/src/main/java/com/example/Service.java",
            "language": "java",
            "file_metrics": {
                "total_lines": 500,
                "code_lines": 400,
                "comment_lines": 50,
                "blank_lines": 50,
                "estimated_tokens": 2500,
            },
            "summary": {
                "classes": 5,
                "methods": 50,
                "fields": 20,
                "imports": 15,
            },
            "structural_overview": {
                "classes": [
                    {
                        "name": f"Class{i}",
                        "type": "class",
                        "start_line": i * 100,
                        "end_line": i * 100 + 80,
                        "line_span": 80,
                        "visibility": "public",
                    }
                    for i in range(5)
                ],
                "methods": [
                    {
                        "name": f"method{i}",
                        "start_line": i * 10,
                        "end_line": i * 10 + 5,
                        "line_span": 5,
                        "visibility": "public" if i % 2 == 0 else "private",
                        "complexity": i % 10,
                    }
                    for i in range(50)
                ],
            },
        }

        # Measure JSON size
        json_output = format_as_json(large_response)
        json_size = len(json_output)

        # Measure optimized TOON response size
        toon_response = apply_toon_format_to_response(large_response, output_format="toon")
        toon_size = len(json.dumps(toon_response))

        # Calculate reduction
        reduction = 1 - (toon_size / json_size)

        print(f"\nJSON size: {json_size:,} chars")
        print(f"TOON optimized size: {toon_size:,} chars")
        print(f"Reduction: {reduction*100:.1f}%")

        # Should achieve at least 40% reduction
        assert reduction >= 0.40, f"Expected >= 40% reduction, got {reduction*100:.1f}%"

    def test_redundant_fields_removed(self):
        """Verify all redundant fields are removed in TOON response."""
        from tree_sitter_analyzer.mcp.utils.format_helper import (
            TOON_REDUNDANT_FIELDS,
            apply_toon_format_to_response,
        )

        # Create response with all possible redundant fields
        response = {
            "success": True,
            "file_path": "/test.py",
            "language": "python",
        }

        # Add all redundant fields with data
        for field in TOON_REDUNDANT_FIELDS:
            response[field] = {"data": f"value_for_{field}"}

        toon_response = apply_toon_format_to_response(response, output_format="toon")

        # Verify no redundant fields in response
        for field in TOON_REDUNDANT_FIELDS:
            assert field not in toon_response, f"Redundant field '{field}' should be removed"

        # Verify metadata preserved
        assert toon_response["success"] is True
        assert toon_response["file_path"] == "/test.py"
        assert "toon_content" in toon_response

    def test_attach_toon_content_reduction(self):
        """Verify attach_toon_content_to_response achieves reduction."""
        import json

        from tree_sitter_analyzer.mcp.utils.format_helper import (
            attach_toon_content_to_response,
        )

        # Create large data structure
        large_data = {
            "success": True,
            "file_path": "/test/large.py",
            "language": "python",
            "results": [
                {"id": i, "name": f"item_{i}", "data": "x" * 50}
                for i in range(100)
            ],
            "structural_overview": {
                "classes": [{"name": f"Class{i}"} for i in range(20)],
                "methods": [{"name": f"method{i}"} for i in range(100)],
            },
            "summary": {"classes": 20, "methods": 100},
        }

        result = attach_toon_content_to_response(large_data)

        # Original size vs optimized size
        original_size = len(json.dumps(large_data))
        optimized_size = len(json.dumps(result))

        # Calculate reduction
        reduction = 1 - (optimized_size / original_size)

        print(f"\nOriginal size: {original_size:,} chars")
        print(f"Optimized size: {optimized_size:,} chars")
        print(f"Reduction: {reduction*100:.1f}%")

        # Should achieve at least 25% reduction (realistic for varied data structures)
        assert reduction >= 0.25, f"Expected >= 25% reduction, got {reduction*100:.1f}%"
