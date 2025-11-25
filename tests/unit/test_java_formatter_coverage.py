import unittest

from tree_sitter_analyzer.formatters.java_formatter import JavaTableFormatter


class TestJavaTableFormatterCoverage(unittest.TestCase):
    def test_format_full_table_multiple_classes_with_package(self):
        """Test full table formatting with multiple classes and package"""
        formatter = JavaTableFormatter()
        data = {
            "package": {"name": "com.example"},
            "file_path": "path/to/MyFile.java",
            "classes": [
                {
                    "name": "ClassA",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 10},
                },
                {
                    "name": "ClassB",
                    "type": "class",
                    "visibility": "package",
                    "line_range": {"start": 11, "end": 20},
                },
            ],
            "methods": [
                {"name": "methodA", "line_range": {"start": 2, "end": 3}},  # in ClassA
                {
                    "name": "methodB",
                    "line_range": {"start": 12, "end": 13},
                },  # in ClassB
            ],
            "fields": [
                {"name": "fieldA", "line_range": {"start": 4, "end": 4}},  # in ClassA
                {"name": "fieldB", "line_range": {"start": 14, "end": 14}},  # in ClassB
            ],
        }

        result = formatter._format_full_table(data)

        # Check header uses package and filename
        self.assertIn("# com.example.MyFile.java", result)

        # Check multi-class table headers
        self.assertIn(
            "| Class | Type | Visibility | Lines | Methods | Fields |", result
        )
        self.assertIn("| ClassA | class | public | 1-10 | 1 | 1 |", result)
        self.assertIn("| ClassB | class | package | 11-20 | 1 | 1 |", result)

    def test_format_full_table_multiple_classes_no_package(self):
        """Test full table formatting with multiple classes without package"""
        formatter = JavaTableFormatter()
        data = {
            "file_path": "path/to/MyFile.java",
            "classes": [
                {"name": "A", "type": "class", "line_range": {"start": 1, "end": 10}},
                {"name": "B", "type": "class", "line_range": {"start": 11, "end": 20}},
            ],
        }

        result = formatter._format_full_table(data)
        self.assertIn("# MyFile.java", result)

    def test_format_full_table_single_class_no_package(self):
        """Test full table formatting single class no package"""
        formatter = JavaTableFormatter()
        data = {
            "classes": [
                {"name": "A", "type": "class", "line_range": {"start": 1, "end": 10}}
            ]
        }
        result = formatter._format_full_table(data)
        self.assertIn("# A", result)

    def test_format_enum_details(self):
        """Test formatting enum details including fields and methods within enum range"""
        formatter = JavaTableFormatter()
        data = {
            "classes": [
                {
                    "name": "MyEnum",
                    "type": "enum",
                    "line_range": {"start": 1, "end": 20},
                    "constants": ["A", "B"],
                }
            ],
            "fields": [
                {
                    "name": "value",
                    "type": "int",
                    "visibility": "private",
                    "line_range": {"start": 5, "end": 5},
                    "modifiers": ["final"],
                }
            ],
            "methods": [
                {
                    "name": "getValue",
                    "visibility": "public",
                    "return_type": "int",
                    "line_range": {"start": 10, "end": 12},
                    "parameters": [],
                }
            ],
        }

        result = formatter._format_full_table(data)

        self.assertIn("## MyEnum", result)
        self.assertIn("| Type | enum |", result)
        self.assertIn("| Constants | A, B |", result)

        self.assertIn("### Fields", result)
        self.assertIn("| value | int | - | final | 5 | - |", result)

        self.assertIn("### Methods", result)
        self.assertIn("getValue", result)

    def test_shorten_type_complex(self):
        """Test shortening of complex types"""
        formatter = JavaTableFormatter()

        # List<Map<String, Object>> -> L<M<S,O>>
        # Current implementation might not be recursive enough for deeply nested types,
        # but let's test what it supports.

        # "List<String>" -> "L<S>"
        self.assertEqual(formatter._shorten_type("List<String>"), "L<S>")

        # "Map<String,Object>" -> "M<S,O>"
        self.assertEqual(formatter._shorten_type("Map<String,Object>"), "M<S,O>")

        # "String[]" -> "S[]"
        self.assertEqual(formatter._shorten_type("String[]"), "S[]")

        # "Object[]" -> "O[]"
        self.assertEqual(formatter._shorten_type("Object[]"), "O[]")

        # "int[]" -> "i[]"
        self.assertEqual(formatter._shorten_type("int[]"), "i[]")

        # "Unknown[]" -> "U[]" (first char upper)
        self.assertEqual(formatter._shorten_type("Unknown[]"), "U[]")

        # "RuntimeException" -> "RE"
        self.assertEqual(formatter._shorten_type("RuntimeException"), "RE")

        # "SQLException" -> "SE"
        self.assertEqual(formatter._shorten_type("SQLException"), "SE")

        # "IllegalArgumentException" -> "IAE"
        self.assertEqual(formatter._shorten_type("IllegalArgumentException"), "IAE")

        # Non-string input
        self.assertEqual(formatter._shorten_type(123), "123")

    def test_format_json_error(self):
        """Test JSON serialization error handling"""
        formatter = JavaTableFormatter()

        # Create an object that cannot be serialized to JSON
        class Unserializable:
            pass

        data = {"key": Unserializable()}

        result = formatter._format_json(data)
        self.assertIn("# JSON serialization error:", result)

    def test_format_advanced_variations(self):
        """Test format_advanced with various outputs"""
        formatter = JavaTableFormatter()
        data = {"classes": [{"name": "Test"}]}

        # JSON
        res_json = formatter.format_advanced(data, "json")
        self.assertIn('"name": "Test"', res_json)

        # CSV (base implementation returns "CSV format not implemented" or empty/headers depending on base)
        # JavaTableFormatter inherits BaseTableFormatter._format_csv which might just return "" or raise
        # Let's just check it returns string
        res_csv = formatter.format_advanced(data, "csv")
        self.assertIsInstance(res_csv, str)

        # Default (full table)
        res_full = formatter.format_advanced(data, "unknown")
        self.assertIn("# Test", res_full)

    def test_format_table_context_manager(self):
        """Test format_table ensures format_type is restored"""
        formatter = JavaTableFormatter()
        formatter.format_type = "compact"

        data = {"classes": [{"name": "Test"}]}

        # Call with "json"
        formatter.format_table(data, "json")

        # Should be restored to "compact"
        self.assertEqual(formatter.format_type, "compact")

    def test_clean_csv_text(self):
        """Test _clean_csv_text inherited method usage in Java formatter context"""
        formatter = JavaTableFormatter()
        # _clean_csv_text is used in _format_compact_table and _format_method_row
        # _extract_doc_summary only returns the first line of the doc

        method = {"name": "test", "javadoc": "Line 1\nLine 2"}

        row = formatter._format_method_row(method)
        # _extract_doc_summary takes first line only, so "Line 1" is expected
        self.assertIn("Line 1", row)
