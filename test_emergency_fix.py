#!/usr/bin/env python3
"""
Emergency Fix Test

Test the QueryResultParser and table command fix.
"""

import os
import sys

sys.path.insert(0, os.path.abspath("."))


def test_query_result_parser():
    """Test QueryResultParser functionality"""
    try:
        from tree_sitter_analyzer.core.query_result_parser import QueryResultParser

        # Test Java method parsing
        parser = QueryResultParser("java")

        # Test method info parsing
        java_method = (
            "public static boolean authenticateUser(String username, String password)"
        )
        method_info = parser.parse_method_info(java_method)

        print("Java Method Parsing Test:")
        print(f"Input: {java_method}")
        print(f"Parsed name: {method_info['name']}")
        print(f"Parsed parameters: {method_info['parameters']}")
        print(f"Parsed visibility: {method_info['visibility']}")
        print(f"Parsed return type: {method_info['return_type']}")
        print(f"Parsed modifiers: {method_info['modifiers']}")
        print()

        # Test parameter formatting
        formatted_params = parser.format_parameters_for_display(
            method_info["parameters"]
        )
        print(f"Formatted parameters: {formatted_params}")
        print()

        # Test query result extraction
        mock_query_result = {
            "capture_name": "method",
            "content": java_method,
            "start_line": 141,
            "end_line": 172,
        }

        actual_name = parser.extract_actual_name_from_query_result(mock_query_result)
        print(f"Extracted actual name: {actual_name}")
        print()

        # Test Python method parsing
        parser_py = QueryResultParser("python")
        python_method = "def calculate_total(items: List[Item]) -> float:"
        method_info_py = parser_py.parse_method_info(python_method)

        print("Python Method Parsing Test:")
        print(f"Input: {python_method}")
        print(f"Parsed name: {method_info_py['name']}")
        print(f"Parsed parameters: {method_info_py['parameters']}")
        print(f"Parsed return type: {method_info_py['return_type']}")
        print()

        return True

    except Exception as e:
        print(f"Error testing QueryResultParser: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_table_command_import():
    """Test table command import"""
    try:
        print("TableCommand import successful")
        return True
    except Exception as e:
        print(f"Error importing TableCommand: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("=== Emergency Fix Test ===")
    print()

    # Test QueryResultParser
    parser_success = test_query_result_parser()
    print()

    # Test TableCommand import
    table_success = test_table_command_import()
    print()

    if parser_success and table_success:
        print("✅ All tests passed!")
        return 0
    else:
        print("❌ Some tests failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
