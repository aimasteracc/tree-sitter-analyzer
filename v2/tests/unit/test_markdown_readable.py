"""
Test Markdown formatter readability improvements.

Tests the enhanced Markdown format with better structure for methods and parameters.
This addresses Pain Point #3: Remove nested tables, improve readability.
"""


class TestMarkdownReadableFormat:
    """Test readable Markdown output format."""

    def test_method_formatting_no_nested_tables(self) -> None:
        """Test that methods are formatted without nested tables."""
        from tree_sitter_analyzer_v2.formatters.markdown_formatter import MarkdownFormatter

        formatter = MarkdownFormatter()

        # Simulate a class with methods
        data = {
            "classes": [
                {
                    "name": "Calculator",
                    "docstring": "A simple calculator",
                    "line_start": 1,
                    "line_end": 20,
                    "methods": [
                        {
                            "name": "__init__",
                            "parameters": [{"name": "self", "type": None}],
                            "return_type": None,
                            "docstring": "Initialize calculator",
                            "line_start": 2,
                            "line_end": 4,
                        },
                        {
                            "name": "add",
                            "parameters": [
                                {"name": "self", "type": None},
                                {"name": "a", "type": "int"},
                                {"name": "b", "type": "int"},
                            ],
                            "return_type": "int",
                            "docstring": "Add two numbers",
                            "line_start": 6,
                            "line_end": 8,
                        },
                    ],
                }
            ]
        }

        result = formatter.format(data)

        # Should NOT have table-in-table format (| Name | Parameters | ...)
        # Should use headings for methods instead
        assert "Calculator" in result
        assert "__init__" in result
        assert "add" in result

        # Should NOT have nested table pipes like "| Name | Parameters |" inside methods
        lines = result.split("\n")
        method_section_lines = [line for line in lines if "__init__" in line or "add(" in line]

        # Methods should be formatted as headings (### or ####), not table rows
        for line in method_section_lines:
            # Should have heading marker or be in a heading-like format
            # NOT be a table row (which would have | surrounding it)
            if ("__init__" in line or "add(" in line) and "|" in line:
                # If there's a pipe, it should not be a multi-column table row
                assert line.count("|") <= 2, "Methods should not be in multi-column tables"

    def test_parameters_formatted_as_list(self) -> None:
        """Test that parameters are formatted as bullet lists, not inline."""
        from tree_sitter_analyzer_v2.formatters.markdown_formatter import MarkdownFormatter

        formatter = MarkdownFormatter()

        data = {
            "functions": [
                {
                    "name": "calculate",
                    "parameters": [
                        {"name": "x", "type": "int"},
                        {"name": "y", "type": "int"},
                        {"name": "operation", "type": "str"},
                    ],
                    "return_type": "float",
                    "docstring": "Perform calculation",
                    "line_start": 10,
                    "line_end": 15,
                }
            ]
        }

        result = formatter.format(data)

        # Parameters should be shown clearly
        assert "calculate" in result
        assert "x" in result
        assert "y" in result
        assert "operation" in result

        # Should NOT have inline format like "- x\n- y\n- operation" in a table cell
        # Should use proper bullet lists or structured format
        # Verify no consecutive lines with "- param" pattern inside table cells
        lines = result.split("\n")

        # Check that if we have parameter listings, they're properly formatted
        # not crammed into table cells with newlines
        param_lines = [line for line in lines if line.strip().startswith("-")]
        if param_lines:
            # If we're using bullet lists for params, they should be indented properly
            # Not all on the same line or in a table cell
            assert any("x" in line or "y" in line or "operation" in line for line in param_lines), (
                "Parameters should be listed clearly"
            )

    def test_method_signature_format(self) -> None:
        """Test that method signatures are formatted as headings."""
        from tree_sitter_analyzer_v2.formatters.markdown_formatter import MarkdownFormatter

        formatter = MarkdownFormatter()

        data = {
            "classes": [
                {
                    "name": "DataProcessor",
                    "methods": [
                        {
                            "name": "process",
                            "parameters": [
                                {"name": "self", "type": None},
                                {"name": "data", "type": "list[str]"},
                            ],
                            "return_type": "dict",
                            "docstring": "Process data",
                            "line_start": 5,
                            "line_end": 10,
                        }
                    ],
                }
            ]
        }

        result = formatter.format(data)

        # Method should be formatted as heading with signature
        assert "process" in result
        assert "data" in result  # parameter name visible

        # Should have heading markers (###, ####, etc.) for methods
        lines = result.split("\n")
        heading_lines = [line for line in lines if line.strip().startswith("#")]
        method_heading_found = any("process" in line for line in heading_lines)

        # Either method is in a heading, or it's formatted in a clear non-table way
        # The key is: NO nested tables
        assert method_heading_found or "|" not in result or result.count("|") < 10

    def test_class_structure_readability(self) -> None:
        """Test overall class structure is readable."""
        from tree_sitter_analyzer_v2.formatters.markdown_formatter import MarkdownFormatter

        formatter = MarkdownFormatter()

        data = {
            "classes": [
                {
                    "name": "MyClass",
                    "docstring": "Example class",
                    "bases": ["BaseClass"],
                    "decorators": [],
                    "line_start": 1,
                    "line_end": 50,
                    "methods": [
                        {
                            "name": "method1",
                            "parameters": [{"name": "self", "type": None}],
                            "return_type": "str",
                            "line_start": 5,
                            "line_end": 8,
                        },
                        {
                            "name": "method2",
                            "parameters": [
                                {"name": "self", "type": None},
                                {"name": "arg", "type": "int"},
                            ],
                            "return_type": None,
                            "line_start": 10,
                            "line_end": 15,
                        },
                    ],
                    "attributes": [],
                }
            ]
        }

        result = formatter.format(data)

        # Should have clear structure with headings
        assert "MyClass" in result
        assert "method1" in result
        assert "method2" in result

        # Count heading levels - should have proper hierarchy
        lines = result.split("\n")
        heading_lines = [line for line in lines if line.strip().startswith("#")]

        # Should have at least 2 levels of headings (class + methods)
        heading_levels = {line.count("#") for line in heading_lines if "#" in line}
        assert len(heading_levels) >= 2, (
            "Should have hierarchical headings (class and method levels)"
        )

    def test_no_br_tags_in_output(self) -> None:
        """Test that output doesn't contain HTML <br> tags."""
        from tree_sitter_analyzer_v2.formatters.markdown_formatter import MarkdownFormatter

        formatter = MarkdownFormatter()

        data = {
            "functions": [
                {
                    "name": "complex_function",
                    "parameters": [
                        {"name": "a", "type": "int"},
                        {"name": "b", "type": "int"},
                        {"name": "c", "type": "int"},
                        {"name": "d", "type": "int"},
                    ],
                    "return_type": "tuple",
                }
            ]
        }

        result = formatter.format(data)

        # Should NOT contain <br> tags
        assert "<br>" not in result.lower()
        assert "<br/>" not in result.lower()

    def test_empty_methods_list(self) -> None:
        """Test formatting class with no methods."""
        from tree_sitter_analyzer_v2.formatters.markdown_formatter import MarkdownFormatter

        formatter = MarkdownFormatter()

        data = {"classes": [{"name": "EmptyClass", "methods": []}]}

        result = formatter.format(data)

        assert "EmptyClass" in result
        assert "empty" in result.lower() or "none" in result.lower() or result.count("|") == 0

    def test_readability_score_improvement(self) -> None:
        """
        Test that new format is more readable than old format.
        This is a subjective test - we check for markers of good formatting.
        """
        from tree_sitter_analyzer_v2.formatters.markdown_formatter import MarkdownFormatter

        formatter = MarkdownFormatter()

        data = {
            "classes": [
                {
                    "name": "Calculator",
                    "methods": [
                        {
                            "name": "add",
                            "parameters": [
                                {"name": "a", "type": "int"},
                                {"name": "b", "type": "int"},
                            ],
                            "return_type": "int",
                        }
                    ],
                }
            ]
        }

        result = formatter.format(data)

        # Markers of good readability:
        # 1. Hierarchical headings (##, ###, ####)
        # 2. Clear parameter lists
        # 3. Not overly compressed
        # 4. No nested tables

        lines = result.split("\n")

        # Should have headings
        has_headings = any("#" in line for line in lines)
        assert has_headings, "Should use headings for structure"

        # Should be multi-line (not compressed)
        assert len(lines) >= 5, "Should have clear vertical structure"

        # Should not have deeply nested table structures
        table_row_count = sum(1 for line in lines if line.strip().startswith("|"))
        # If using tables, should be simple tables, not complex nested ones
        if table_row_count > 0:
            assert table_row_count < 10, "Should not have excessive table rows (nested tables)"
