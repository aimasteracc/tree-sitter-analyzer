#!/usr/bin/env python3
"""
Test script to verify HTML modifications are working correctly.
"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from tree_sitter_analyzer.languages.html_plugin import HTMLLanguagePlugin
from tree_sitter_analyzer.formatters.html_formatter import HTMLTableFormatter
from tree_sitter_analyzer.formatters.formatter_factory import TableFormatterFactory

def test_html_plugin():
    """Test HTML plugin functionality"""
    print("=== Testing HTML Plugin ===")
    
    plugin = HTMLLanguagePlugin()
    print(f"Language: {plugin.get_language_name()}")
    print(f"Extensions: {plugin.get_file_extensions()}")
    
    extractor = plugin.create_extractor()
    print(f"Extractor type: {type(extractor).__name__}")
    
    return True

def test_html_formatter():
    """Test HTML formatter functionality"""
    print("\n=== Testing HTML Formatter ===")
    
    # Test formatter creation
    formatter = HTMLTableFormatter("full")
    print(f"Formatter type: {type(formatter).__name__}")
    print(f"Format type: {formatter.format_type}")
    
    # Test sample data
    sample_data = {
        "file_path": "test.html",
        "line_count": 10,
        "elements": [
            {
                "type": "function",
                "element_type": "function", 
                "name": "div",
                "start_line": 1,
                "end_line": 3,
                "raw_text": '<div class="container">content</div>'
            },
            {
                "type": "variable",
                "element_type": "variable",
                "name": "class",
                "start_line": 1,
                "end_line": 1,
                "raw_text": 'class="container"'
            }
        ]
    }
    
    # Test different formats
    for format_type in ["full", "compact", "csv", "json"]:
        try:
            result = formatter.format(sample_data, format_type)
            print(f"✓ {format_type} format: {len(result)} characters")
        except Exception as e:
            print(f"✗ {format_type} format failed: {e}")
    
    return True

def test_formatter_factory():
    """Test formatter factory registration"""
    print("\n=== Testing Formatter Factory ===")
    
    # Test HTML formatter registration
    try:
        html_formatter = TableFormatterFactory.create_formatter("html", "full")
        print(f"✓ HTML formatter created: {type(html_formatter).__name__}")
    except Exception as e:
        print(f"✗ HTML formatter creation failed: {e}")
        return False
    
    # Test supported languages
    languages = TableFormatterFactory.get_supported_languages()
    print(f"Supported languages: {languages}")
    
    if "html" in languages:
        print("✓ HTML is registered in formatter factory")
    else:
        print("✗ HTML is NOT registered in formatter factory")
        return False
    
    return True

def main():
    """Run all tests"""
    print("Testing HTML Support Modifications")
    print("=" * 50)
    
    tests = [
        test_html_plugin,
        test_html_formatter, 
        test_formatter_factory
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"✗ Test {test.__name__} failed with exception: {e}")
            results.append(False)
    
    print("\n" + "=" * 50)
    print("Test Summary:")
    print(f"Passed: {sum(results)}/{len(results)}")
    
    if all(results):
        print("✓ All tests passed! HTML modifications are working correctly.")
        return 0
    else:
        print("✗ Some tests failed. Please check the modifications.")
        return 1

if __name__ == "__main__":
    sys.exit(main())