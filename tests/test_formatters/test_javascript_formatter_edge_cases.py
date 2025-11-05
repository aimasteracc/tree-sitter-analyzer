"""
Edge case tests for JavaScript formatter.
Tests error handling, boundary conditions, and unusual scenarios.
"""

from unittest.mock import patch

import pytest

from tree_sitter_analyzer.formatters.javascript_formatter import (
    JavaScriptTableFormatter,
)


class TestJavaScriptTableFormatterEdgeCases:
    """Edge case tests for JavaScript formatter"""

    @pytest.fixture
    def formatter(self):
        """Create a JavaScript formatter instance"""
        return JavaScriptTableFormatter()

    def test_format_with_none_data(self, formatter):
        """Test formatting with None data"""
        result = formatter.format(None, "full")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_with_invalid_format_type(self, formatter):
        """Test formatting with invalid format type"""
        data = {"file_path": "test.js"}

        # Should raise ValueError for invalid format
        with pytest.raises(ValueError, match="Unsupported format type"):
            formatter.format(data, "invalid_format")

    def test_format_with_missing_file_path(self, formatter):
        """Test formatting with missing file_path"""
        data = {
            "imports": [],
            "exports": [],
            "classes": [],
            "variables": [],
            "functions": [],
            "statistics": {"function_count": 0},
        }

        result = formatter.format(data, "full")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_with_circular_references(self, formatter):
        """Test formatting with circular references in data"""
        # Create circular reference
        data = {"file_path": "test.js"}
        data["self_ref"] = data

        # Should handle gracefully without infinite recursion
        result = formatter.format(data, "json")
        assert isinstance(result, str)

    def test_format_with_extremely_long_names(self, formatter):
        """Test formatting with extremely long names"""
        long_name = "a" * 1000
        data = {
            "file_path": f"{long_name}.js",
            "imports": [{"name": long_name, "source": long_name}],
            "exports": [{"name": long_name, "is_named": True}],
            "classes": [{"name": long_name, "methods": []}],
            "variables": [{"name": long_name, "type": "string"}],
            "functions": [{"name": long_name, "parameters": []}],
            "statistics": {"function_count": 1},
        }

        result = formatter.format(data, "full")
        assert isinstance(result, str)
        assert long_name in result

    def test_format_with_special_unicode_characters(self, formatter):
        """Test formatting with special Unicode characters"""
        special_chars = "🚀💻🔥⚡️🎯🌟💡🔧🎨🚨"
        data = {
            "file_path": f"{special_chars}.js",
            "imports": [{"name": special_chars, "source": special_chars}],
            "exports": [{"name": special_chars, "is_named": True}],
            "classes": [{"name": special_chars, "methods": []}],
            "variables": [{"name": special_chars, "type": "string"}],
            "functions": [{"name": special_chars, "parameters": []}],
            "statistics": {"function_count": 1},
        }

        result = formatter.format(data, "full")
        assert isinstance(result, str)
        assert special_chars in result

    def test_format_with_control_characters(self, formatter):
        """Test formatting with control characters"""
        control_chars = "\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f"
        data = {
            "file_path": "test.js",
            "imports": [{"name": f"module{control_chars}", "source": "lib"}],
            "exports": [{"name": f"export{control_chars}", "is_named": True}],
            "classes": [{"name": f"Class{control_chars}", "methods": []}],
            "variables": [{"name": f"var{control_chars}", "type": "string"}],
            "functions": [{"name": f"func{control_chars}", "parameters": []}],
            "statistics": {"function_count": 1},
        }

        # Should handle control characters without crashing
        result = formatter.format(data, "full")
        assert isinstance(result, str)

    def test_format_with_nested_data_structures(self, formatter):
        """Test formatting with deeply nested data structures"""
        nested_data = {
            "file_path": "nested.js",
            "functions": [
                {
                    "name": "complexFunc",
                    "parameters": [
                        {
                            "name": "config",
                            "type": "object",
                            "properties": {
                                "nested": {
                                    "deep": {"very_deep": {"extremely_deep": "value"}}
                                }
                            },
                        }
                    ],
                }
            ],
            "statistics": {"function_count": 1},
        }

        result = formatter.format(nested_data, "full")
        assert isinstance(result, str)
        assert "complexFunc" in result

    def test_format_with_binary_data(self, formatter):
        """Test formatting with binary data in strings"""
        binary_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        try:
            binary_string = binary_data.decode("utf-8", errors="ignore")
        except Exception:
            binary_string = str(binary_data)

        data = {
            "file_path": "binary.js",
            "variables": [{"name": "binaryData", "value": binary_string}],
            "statistics": {"variable_count": 1},
        }

        # Should handle binary data gracefully
        result = formatter.format(data, "full")
        assert isinstance(result, str)

    def test_format_with_extremely_large_numbers(self, formatter):
        """Test formatting with extremely large numbers"""
        large_number = str(10**100)
        data = {
            "file_path": "numbers.js",
            "variables": [{"name": "largeNumber", "value": large_number}],
            "statistics": {"variable_count": 1},
        }

        result = formatter.format(data, "full")
        assert isinstance(result, str)

    def test_format_with_malformed_json_strings(self, formatter):
        """Test formatting with malformed JSON strings"""
        malformed_json = '{"incomplete": "json", "missing":'
        data = {
            "file_path": "malformed.js",
            "variables": [{"name": "jsonData", "value": malformed_json}],
            "statistics": {"variable_count": 1},
        }

        result = formatter.format(data, "json")
        assert isinstance(result, str)

    def test_format_with_recursive_data_structures(self, formatter):
        """Test formatting with recursive data structures"""
        # Create a list that references itself
        recursive_list = []
        recursive_list.append(recursive_list)

        data = {
            "file_path": "recursive.js",
            "functions": [{"name": "test", "parameters": recursive_list}],
            "statistics": {"function_count": 1},
        }

        # Should handle without infinite recursion
        result = formatter.format(data, "full")
        assert isinstance(result, str)

    def test_format_with_memory_intensive_data(self, formatter):
        """Test formatting with memory-intensive data"""
        # Create large string
        large_string = "x" * 10000

        data = {
            "file_path": "memory_test.js",
            "variables": [{"name": "largeString", "value": large_string}] * 100,
            "statistics": {"variable_count": 100},
        }

        result = formatter.format(data, "full")
        assert isinstance(result, str)

    def test_format_with_invalid_utf8_sequences(self, formatter):
        """Test formatting with invalid UTF-8 sequences"""
        # Create invalid UTF-8 byte sequences
        invalid_utf8 = b"\xff\xfe\xfd\xfc"
        try:
            invalid_string = invalid_utf8.decode("utf-8", errors="replace")
        except Exception:
            invalid_string = str(invalid_utf8)

        data = {
            "file_path": "invalid_utf8.js",
            "variables": [{"name": "invalidData", "value": invalid_string}],
            "statistics": {"variable_count": 1},
        }

        result = formatter.format(data, "full")
        assert isinstance(result, str)

    def test_format_with_zero_width_characters(self, formatter):
        """Test formatting with zero-width characters"""
        zero_width_chars = (
            "\u200b\u200c\u200d\ufeff"  # Zero-width space, ZWNJ, ZWJ, BOM
        )
        data = {
            "file_path": f"zero{zero_width_chars}width.js",
            "functions": [{"name": f"func{zero_width_chars}name", "parameters": []}],
            "statistics": {"function_count": 1},
        }

        result = formatter.format(data, "full")
        assert isinstance(result, str)

    def test_format_with_rtl_characters(self, formatter):
        """Test formatting with right-to-left characters"""
        rtl_text = "مرحبا بالعالم"  # Arabic "Hello World"
        hebrew_text = "שלום עולם"  # Hebrew "Hello World"

        data = {
            "file_path": "rtl.js",
            "functions": [
                {"name": rtl_text, "parameters": []},
                {"name": hebrew_text, "parameters": []},
            ],
            "statistics": {"function_count": 2},
        }

        result = formatter.format(data, "full")
        assert isinstance(result, str)
        assert rtl_text in result
        assert hebrew_text in result

    def test_format_with_mathematical_symbols(self, formatter):
        """Test formatting with mathematical symbols"""
        math_symbols = "∑∏∫∂∇∆∞±≤≥≠≈∈∉∪∩⊂⊃∀∃∄"
        data = {
            "file_path": "math.js",
            "functions": [{"name": f"calc{math_symbols}", "parameters": []}],
            "statistics": {"function_count": 1},
        }

        result = formatter.format(data, "full")
        assert isinstance(result, str)
        assert math_symbols in result

    def test_format_with_mixed_line_endings(self, formatter):
        """Test formatting with mixed line endings"""
        mixed_endings = "line1\nline2\r\nline3\rline4"
        data = {
            "file_path": "mixed_endings.js",
            "variables": [{"name": "text", "value": mixed_endings}],
            "statistics": {"variable_count": 1},
        }

        result = formatter.format(data, "full")
        assert isinstance(result, str)

    def test_format_with_tab_characters(self, formatter):
        """Test formatting with various tab characters"""
        tab_chars = "\t\v\f"  # Tab, vertical tab, form feed
        data = {
            "file_path": "tabs.js",
            "functions": [{"name": f"func{tab_chars}name", "parameters": []}],
            "statistics": {"function_count": 1},
        }

        result = formatter.format(data, "full")
        assert isinstance(result, str)

    def test_format_with_surrogate_pairs(self, formatter):
        """Test formatting with Unicode surrogate pairs"""
        # Emoji that uses surrogate pairs
        emoji_with_surrogates = "👨‍💻👩‍🔬🧑‍🎨"
        data = {
            "file_path": "emoji.js",
            "functions": [{"name": f"handle{emoji_with_surrogates}", "parameters": []}],
            "statistics": {"function_count": 1},
        }

        result = formatter.format(data, "full")
        assert isinstance(result, str)
        assert emoji_with_surrogates in result

    def test_format_with_combining_characters(self, formatter):
        """Test formatting with Unicode combining characters"""
        # Text with combining diacritical marks
        combining_text = "e\u0301"  # é using combining acute accent
        data = {
            "file_path": "combining.js",
            "functions": [{"name": f"caf{combining_text}", "parameters": []}],
            "statistics": {"function_count": 1},
        }

        result = formatter.format(data, "full")
        assert isinstance(result, str)

    def test_format_with_normalization_forms(self, formatter):
        """Test formatting with different Unicode normalization forms"""
        import unicodedata

        # Same character in different normalization forms
        nfc_text = unicodedata.normalize("NFC", "café")
        nfd_text = unicodedata.normalize("NFD", "café")

        data = {
            "file_path": "normalization.js",
            "functions": [
                {"name": f"nfc{nfc_text}", "parameters": []},
                {"name": f"nfd{nfd_text}", "parameters": []},
            ],
            "statistics": {"function_count": 2},
        }

        result = formatter.format(data, "full")
        assert isinstance(result, str)

    def test_format_with_exception_in_helper_methods(self, formatter):
        """Test formatting when helper methods raise exceptions"""
        data = {
            "file_path": "exception_test.js",
            "functions": [{"name": "test", "parameters": []}],
            "statistics": {"function_count": 1},
        }

        # Mock a helper method to raise an exception
        with patch.object(
            formatter, "_get_function_signature", side_effect=Exception("Test error")
        ):
            # Should handle exception gracefully
            result = formatter.format(data, "full")
            assert isinstance(result, str)

    def test_format_with_json_serialization_error(self, formatter):
        """Test formatting when JSON serialization fails"""

        # Create object that can't be JSON serialized
        class NonSerializable:
            def __str__(self):
                raise Exception("Cannot convert to string")

        data = {
            "file_path": "json_error.js",
            "functions": [{"name": "test", "custom_obj": NonSerializable()}],
            "statistics": {"function_count": 1},
        }

        # Should handle JSON serialization error gracefully
        result = formatter.format(data, "json")
        assert isinstance(result, str)

    def test_format_with_csv_special_characters(self, formatter):
        """Test CSV formatting with special CSV characters"""
        csv_special = 'name,with"quotes,and\nnewlines'
        data = {
            "file_path": "csv_special.js",
            "functions": [{"name": csv_special, "parameters": []}],
            "statistics": {"function_count": 1},
        }

        result = formatter.format(data, "csv")
        assert isinstance(result, str)
        # CSV should escape special characters
        assert '"' in result or "," in result

    def test_format_with_markdown_special_characters(self, formatter):
        """Test formatting with Markdown special characters"""
        markdown_special = "# Header | Table | *Bold* | `Code` | [Link](url)"
        data = {
            "file_path": "markdown.js",
            "functions": [{"name": markdown_special, "parameters": []}],
            "statistics": {"function_count": 1},
        }

        result = formatter.format(data, "full")
        assert isinstance(result, str)

    def test_format_with_html_entities(self, formatter):
        """Test formatting with HTML entities"""
        html_entities = "&lt;&gt;&amp;&quot;&#39;"
        data = {
            "file_path": "html.js",
            "functions": [{"name": html_entities, "parameters": []}],
            "statistics": {"function_count": 1},
        }

        result = formatter.format(data, "full")
        assert isinstance(result, str)

    def test_format_with_sql_injection_patterns(self, formatter):
        """Test formatting with SQL injection-like patterns"""
        sql_pattern = "'; DROP TABLE users; --"
        data = {
            "file_path": "sql.js",
            "functions": [{"name": sql_pattern, "parameters": []}],
            "statistics": {"function_count": 1},
        }

        result = formatter.format(data, "full")
        assert isinstance(result, str)
        # Should not execute any SQL, just format as text
        assert sql_pattern in result

    def test_format_with_script_injection_patterns(self, formatter):
        """Test formatting with script injection-like patterns"""
        script_pattern = "<script>alert('xss')</script>"
        data = {
            "file_path": "script.js",
            "functions": [{"name": script_pattern, "parameters": []}],
            "statistics": {"function_count": 1},
        }

        result = formatter.format(data, "full")
        assert isinstance(result, str)
        # Should not execute any scripts, just format as text
        assert "script" in result.lower()

    def test_format_with_path_traversal_patterns(self, formatter):
        """Test formatting with path traversal patterns"""
        path_traversal = "../../../etc/passwd"
        data = {
            "file_path": path_traversal,
            "functions": [{"name": "test", "parameters": []}],
            "statistics": {"function_count": 1},
        }

        result = formatter.format(data, "full")
        assert isinstance(result, str)
        # Should not access any files, just format as text
        # The formatter shows only the filename, not the full path
        assert "passwd" in result

    def test_format_with_regex_patterns(self, formatter):
        """Test formatting with complex regex patterns"""
        regex_pattern = r"^(?:[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*|\"(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21\x23-\x5b\x5d-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])*\")@(?:(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?|\[(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?|[a-z0-9-]*[a-z0-9]:(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21-\x5a\x53-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])+)\])$"
        data = {
            "file_path": "regex.js",
            "variables": [{"name": "emailRegex", "value": regex_pattern}],
            "statistics": {"variable_count": 1},
        }

        result = formatter.format(data, "full")
        assert isinstance(result, str)

    def test_format_with_url_patterns(self, formatter):
        """Test formatting with various URL patterns"""
        urls = [
            "http://example.com",
            "https://subdomain.example.com:8080/path?query=value#fragment",
            "ftp://user:pass@ftp.example.com/file.txt",
            "file:///C:/Windows/System32/",
            "data:text/plain;base64,SGVsbG8gV29ybGQ=",
        ]

        data = {
            "file_path": "urls.js",
            "variables": [
                {"name": f"url{i}", "value": url} for i, url in enumerate(urls)
            ],
            "statistics": {"variable_count": len(urls)},
        }

        result = formatter.format(data, "full")
        assert isinstance(result, str)
        # URLs may be truncated in the output, so check for partial matches
        assert "http://example.com" in result
        assert (
            "https://subdomain.example.com:" in result
        )  # Partial match due to truncation
        assert (
            "ftp://user:pass@ftp.example.co" in result
        )  # Partial match due to truncation

    def test_format_with_base64_data(self, formatter):
        """Test formatting with Base64 encoded data"""
        base64_data = (
            "SGVsbG8gV29ybGQhIFRoaXMgaXMgYSB0ZXN0IG1lc3NhZ2UgZW5jb2RlZCBpbiBCYXNlNjQ="
        )
        data = {
            "file_path": "base64.js",
            "variables": [{"name": "encodedData", "value": base64_data}],
            "statistics": {"variable_count": 1},
        }

        result = formatter.format(data, "full")
        assert isinstance(result, str)
        # Base64 data may be truncated in the output, so check for partial match
        assert (
            "SGVsbG8gV29ybGQhIFRoaXMgaXMgYS" in result
        )  # Partial match due to truncation

    def test_format_with_jwt_tokens(self, formatter):
        """Test formatting with JWT-like tokens"""
        jwt_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        data = {
            "file_path": "jwt.js",
            "variables": [{"name": "token", "value": jwt_token}],
            "statistics": {"variable_count": 1},
        }

        result = formatter.format(data, "full")
        assert isinstance(result, str)
        # JWT token may be truncated in the output, so check for partial match
        assert (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6Ik" in result
        )  # Partial match due to truncation

    def test_format_with_hash_values(self, formatter):
        """Test formatting with various hash values"""
        hashes = {
            "md5": "5d41402abc4b2a76b9719d911017c592",
            "sha1": "aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d",
            "sha256": "2cf24dba4f21d4288094e9b9b6e313c1d9030c6e6b4b8d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3",
        }

        data = {
            "file_path": "hashes.js",
            "variables": [
                {"name": f"{alg}Hash", "value": hash_val}
                for alg, hash_val in hashes.items()
            ],
            "statistics": {"variable_count": len(hashes)},
        }

        result = formatter.format(data, "full")
        assert isinstance(result, str)
        # Hash values may be truncated in the output, so check for partial matches
        assert "5d41402abc4b2a76b9719d911017c5" in result  # MD5 partial match
        assert "aaf4c61ddcc5e8a2dabede0f3b482c" in result  # SHA1 partial match
        assert "2cf24dba4f21d4288094e9b9b6e313" in result  # SHA256 partial match
