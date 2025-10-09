"""
Edge case tests for JavaScript plugin.
Tests error handling, boundary conditions, malformed code, and unusual scenarios.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from tree_sitter_analyzer.languages.javascript_plugin import JavaScriptElementExtractor, JavaScriptPlugin
from tree_sitter_analyzer.models import Function, Class, Variable, Import


class TestJavaScriptPluginEdgeCases:
    """Test edge cases and error handling for JavaScript plugin"""
    
    @pytest.fixture
    def extractor(self):
        """Create a JavaScript element extractor instance"""
        return JavaScriptElementExtractor()

    @pytest.fixture
    def plugin(self):
        """Create a JavaScript plugin instance"""
        return JavaScriptPlugin()

    def test_empty_source_code(self, extractor):
        """Test handling of empty source code"""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []
        
        functions = extractor.extract_functions(mock_tree, "")
        classes = extractor.extract_classes(mock_tree, "")
        variables = extractor.extract_variables(mock_tree, "")
        imports = extractor.extract_imports(mock_tree, "")
        exports = extractor.extract_exports(mock_tree, "")
        
        assert functions == []
        assert classes == []
        assert variables == []
        assert imports == []
        assert exports == []

    def test_malformed_javascript_code(self, extractor):
        """Test handling of malformed JavaScript code"""
        malformed_code = """
        function incomplete(
        class MissingBrace {
            method() {
                // missing closing brace
        
        const incomplete = 
        
        import from 'module';
        export ;
        """
        
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []
        
        # Should not crash with malformed code
        functions = extractor.extract_functions(mock_tree, malformed_code)
        classes = extractor.extract_classes(mock_tree, malformed_code)
        variables = extractor.extract_variables(mock_tree, malformed_code)
        
        assert isinstance(functions, list)
        assert isinstance(classes, list)
        assert isinstance(variables, list)

    def test_very_long_lines(self, extractor):
        """Test handling of very long lines"""
        # Create a very long line (10000 characters)
        long_line = "const veryLongVariable = " + "a" * 9970 + ";"
        
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []
        
        # Should handle long lines without crashing
        variables = extractor.extract_variables(mock_tree, long_line)
        assert isinstance(variables, list)

    def test_unicode_and_special_characters(self, extractor):
        """Test handling of Unicode and special characters"""
        unicode_code = """
        // 日本語のコメント
        const 変数名 = "値";
        
        function 関数名(パラメータ) {
            return "結果";
        }
        
        class クラス名 {
            メソッド名() {
                return "🎉";
            }
        }
        
        const emoji = "😀🎯🚀";
        const symbols = "!@#$%^&*()_+-=[]{}|;':\",./<>?";
        """
        
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []
        
        # Should handle Unicode without crashing
        functions = extractor.extract_functions(mock_tree, unicode_code)
        classes = extractor.extract_classes(mock_tree, unicode_code)
        variables = extractor.extract_variables(mock_tree, unicode_code)
        
        assert isinstance(functions, list)
        assert isinstance(classes, list)
        assert isinstance(variables, list)

    def test_deeply_nested_structures(self, extractor):
        """Test handling of deeply nested code structures"""
        nested_code = """
        function level1() {
            function level2() {
                function level3() {
                    function level4() {
                        function level5() {
                            return "deep";
                        }
                        return level5();
                    }
                    return level4();
                }
                return level3();
            }
            return level2();
        }
        """
        
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []
        
        # Should handle nested structures
        functions = extractor.extract_functions(mock_tree, nested_code)
        assert isinstance(functions, list)

    def test_node_text_extraction_errors(self, extractor):
        """Test error handling in node text extraction"""
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 10
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 10)
        
        extractor.content_lines = ["test content"]
        extractor._file_encoding = "utf-8"
        
        # Test with encoding error
        with patch('tree_sitter_analyzer.languages.javascript_plugin.extract_text_slice') as mock_extract:
            mock_extract.side_effect = UnicodeDecodeError("utf-8", b"", 0, 1, "test error")
            
            result = extractor._get_node_text_optimized(mock_node)
            # Should fallback to simple extraction
            assert result == "test conte"

    def test_node_text_extraction_index_error(self, extractor):
        """Test index error handling in node text extraction"""
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 10
        mock_node.start_point = (100, 0)  # Line that doesn't exist
        mock_node.end_point = (100, 10)
        
        extractor.content_lines = ["test content"]
        
        # Should handle index errors gracefully
        with patch('tree_sitter_analyzer.languages.javascript_plugin.extract_text_slice') as mock_extract:
            mock_extract.side_effect = Exception("Test error")
            
            result = extractor._get_node_text_optimized(mock_node)
            assert result == ""  # Should return empty string on error

    def test_function_extraction_with_missing_signature(self, extractor):
        """Test function extraction when signature parsing fails"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)
        
        extractor.content_lines = ["function() {", "}"]
        
        # Mock signature parsing to return None
        with patch.object(extractor, '_parse_function_signature_optimized') as mock_parse:
            mock_parse.return_value = None
            
            result = extractor._extract_function_optimized(mock_node)
            assert result is None

    def test_function_extraction_with_exception(self, extractor):
        """Test function extraction when an exception occurs"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)
        
        # Mock to raise exception
        with patch.object(extractor, '_parse_function_signature_optimized') as mock_parse:
            mock_parse.side_effect = Exception("Test error")
            
            result = extractor._extract_function_optimized(mock_node)
            assert result is None

    def test_arrow_function_without_parent(self, extractor):
        """Test arrow function extraction without proper parent"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (1, 0)
        mock_node.parent = None
        mock_node.children = []
        
        extractor.content_lines = ["() => {}"]
        
        with patch.object(extractor, '_get_node_text_optimized') as mock_get_text:
            mock_get_text.return_value = "() => {}"
            
            with patch.object(extractor, '_extract_jsdoc_for_line') as mock_jsdoc:
                mock_jsdoc.return_value = None
                
                with patch.object(extractor, '_calculate_complexity_optimized') as mock_complexity:
                    mock_complexity.return_value = 1
                    
                    result = extractor._extract_arrow_function_optimized(mock_node)
                    
                    assert isinstance(result, Function)
                    assert result.name == "anonymous"

    def test_arrow_function_with_invalid_parent(self, extractor):
        """Test arrow function extraction with invalid parent type"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (1, 0)
        
        # Mock parent that's not a variable_declarator
        mock_parent = Mock()
        mock_parent.type = "expression_statement"
        mock_parent.children = []
        mock_node.parent = mock_parent
        mock_node.children = []
        
        extractor.content_lines = ["() => {}"]
        
        with patch.object(extractor, '_get_node_text_optimized') as mock_get_text:
            mock_get_text.return_value = "() => {}"
            
            with patch.object(extractor, '_extract_jsdoc_for_line') as mock_jsdoc:
                mock_jsdoc.return_value = None
                
                with patch.object(extractor, '_calculate_complexity_optimized') as mock_complexity:
                    mock_complexity.return_value = 1
                    
                    result = extractor._extract_arrow_function_optimized(mock_node)
                    
                    assert isinstance(result, Function)
                    assert result.name == "anonymous"

    def test_method_extraction_with_missing_signature(self, extractor):
        """Test method extraction when signature parsing fails"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)
        
        # Mock signature parsing to return None
        with patch.object(extractor, '_parse_method_signature_optimized') as mock_parse:
            mock_parse.return_value = None
            
            result = extractor._extract_method_optimized(mock_node)
            assert result is None

    def test_method_extraction_with_exception(self, extractor):
        """Test method extraction when an exception occurs"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)
        
        # Mock to raise exception
        with patch.object(extractor, '_parse_method_signature_optimized') as mock_parse:
            mock_parse.side_effect = Exception("Test error")
            
            # Should re-raise the exception for debugging
            with pytest.raises(Exception):
                extractor._extract_method_optimized(mock_node)

    def test_class_extraction_without_name(self, extractor):
        """Test class extraction when class has no name"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)
        mock_node.children = []  # No identifier child
        
        result = extractor._extract_class_optimized(mock_node)
        assert result is None

    def test_class_extraction_with_invalid_identifier(self, extractor):
        """Test class extraction with invalid identifier"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)
        
        # Mock identifier with None text
        mock_identifier = Mock()
        mock_identifier.type = "identifier"
        mock_identifier.text = None
        mock_node.children = [mock_identifier]
        
        result = extractor._extract_class_optimized(mock_node)
        assert result is None

    def test_class_extraction_with_exception(self, extractor):
        """Test class extraction when an exception occurs"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)
        mock_node.children = []
        
        # Mock to raise exception during processing
        with patch.object(extractor, '_extract_jsdoc_for_line') as mock_jsdoc:
            mock_jsdoc.side_effect = Exception("Test error")
            
            result = extractor._extract_class_optimized(mock_node)
            assert result is None

    def test_variable_extraction_with_complex_destructuring(self, extractor):
        """Test variable extraction with complex destructuring patterns"""
        complex_code = """
        const { a: { b: { c } } } = deeply.nested.object;
        const [first, ...rest] = array;
        const { prop = defaultValue } = obj;
        const { [dynamicKey]: value } = obj;
        """
        
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []
        
        # Should handle complex destructuring without crashing
        variables = extractor.extract_variables(mock_tree, complex_code)
        assert isinstance(variables, list)

    def test_import_extraction_with_malformed_imports(self, extractor):
        """Test import extraction with malformed import statements"""
        malformed_imports = """
        import from 'module';
        import 'module'
        import { } from 'module';
        import { a, } from 'module';
        import * as from 'module';
        """
        
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []
        
        # Should handle malformed imports gracefully
        imports = extractor.extract_imports(mock_tree, malformed_imports)
        assert isinstance(imports, list)

    def test_export_extraction_with_malformed_exports(self, extractor):
        """Test export extraction with malformed export statements"""
        malformed_exports = """
        export from 'module';
        export { };
        export { a, };
        export default;
        export * from;
        """
        
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []
        
        # Should handle malformed exports gracefully
        exports = extractor.extract_exports(mock_tree, malformed_exports)
        assert isinstance(exports, list)

    def test_jsdoc_extraction_with_malformed_comments(self, extractor):
        """Test JSDoc extraction with malformed comments"""
        extractor.content_lines = [
            "/**",
            " * Incomplete JSDoc",
            " * @param {string incomplete",
            " * @returns",
            "function test() {}"
        ]
        
        # Should handle malformed JSDoc gracefully
        jsdoc = extractor._extract_jsdoc_for_line(5)
        assert isinstance(jsdoc, (str, type(None)))

    def test_complexity_calculation_with_extreme_nesting(self, extractor):
        """Test complexity calculation with extremely nested code"""
        mock_node = Mock()
        
        # Create mock children representing deeply nested control structures
        mock_children = []
        for i in range(100):  # Very high nesting
            child = Mock()
            child.type = "if_statement"
            child.children = []
            mock_children.append(child)
        
        mock_node.children = mock_children
        
        # Should handle extreme nesting without crashing
        complexity = extractor._calculate_complexity_optimized(mock_node)
        assert isinstance(complexity, int)
        assert complexity >= 0

    def test_framework_detection_with_mixed_frameworks(self, extractor):
        """Test framework detection with mixed framework imports"""
        mixed_code = """
        import React from 'react';
        import Vue from 'vue';
        import { Component } from '@angular/core';
        """
        
        extractor.source_code = mixed_code
        extractor._detect_file_characteristics()
        
        # Should detect one of the frameworks (first one found)
        assert extractor.framework_type in ["react", "vue", "angular", ""]

    def test_jsx_detection_with_false_positives(self, extractor):
        """Test JSX detection with potential false positives"""
        false_positive_code = """
        const template = '<div>Not JSX</div>';
        const comparison = a < b && c > d;
        const generic = new Map<string, number>();
        """
        
        extractor.source_code = false_positive_code
        extractor.current_file = "test.js"
        extractor._detect_file_characteristics()
        
        # Should not detect as JSX
        assert extractor.is_jsx is False

    def test_memory_pressure_simulation(self, extractor):
        """Test behavior under memory pressure simulation"""
        # Simulate memory pressure by creating many large objects
        large_objects = []
        try:
            for i in range(1000):
                large_objects.append("x" * 10000)  # 10KB strings
                
                # Test extraction during memory pressure
                mock_tree = Mock()
                mock_tree.root_node = Mock()
                mock_tree.root_node.children = []
                
                functions = extractor.extract_functions(mock_tree, "function test() {}")
                assert isinstance(functions, list)
                
        except MemoryError:
            # If we hit memory error, that's expected in this test
            pass
        finally:
            # Clean up
            large_objects.clear()

    def test_concurrent_access_simulation(self, extractor):
        """Test simulation of concurrent access to caches"""
        import threading
        import time
        
        results = []
        errors = []
        
        def worker():
            try:
                for i in range(10):
                    mock_node = Mock()
                    mock_node.start_byte = i
                    mock_node.end_byte = i + 5
                    mock_node.start_point = (0, 0)
                    mock_node.end_point = (0, 5)
                    
                    extractor.content_lines = [f"test content {i}"]
                    
                    with patch('tree_sitter_analyzer.languages.javascript_plugin.extract_text_slice') as mock_extract:
                        mock_extract.return_value = f"text_{i}"
                        result = extractor._get_node_text_optimized(mock_node)
                        results.append(result)
                    
                    time.sleep(0.001)  # Small delay to increase chance of race conditions
            except Exception as e:
                errors.append(e)
        
        # Create multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=worker)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Should not have any errors
        assert len(errors) == 0
        assert len(results) == 50  # 5 threads * 10 operations each

    def test_plugin_initialization_edge_cases(self, plugin):
        """Test plugin initialization with edge cases"""
        # Test with None language
        assert plugin.language == "javascript"
        
        # Test supported extensions
        assert ".js" in plugin.supported_extensions
        assert ".jsx" in plugin.supported_extensions
        assert ".mjs" in plugin.supported_extensions
        assert ".cjs" in plugin.supported_extensions

    def test_plugin_with_invalid_tree(self, plugin):
        """Test plugin behavior with invalid tree"""
        # Test with None tree
        result = plugin.extract_elements(None, "function test() {}")
        assert result == {"functions": [], "classes": [], "variables": [], "imports": [], "exports": []}
        
        # Test with tree that has no root_node
        invalid_tree = Mock()
        invalid_tree.root_node = None
        
        result = plugin.extract_elements(invalid_tree, "function test() {}")
        assert result == {"functions": [], "classes": [], "variables": [], "imports": [], "exports": []}

    def test_plugin_with_extraction_errors(self, plugin):
        """Test plugin behavior when extraction methods raise errors"""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []
        
        # Mock extractor to raise exceptions
        with patch.object(plugin, 'extractor') as mock_extractor:
            mock_extractor.extract_functions.side_effect = Exception("Function extraction error")
            mock_extractor.extract_classes.side_effect = Exception("Class extraction error")
            mock_extractor.extract_variables.side_effect = Exception("Variable extraction error")
            mock_extractor.extract_imports.side_effect = Exception("Import extraction error")
            mock_extractor.extract_exports.side_effect = Exception("Export extraction error")
            
            # Should handle exceptions gracefully
            result = plugin.extract_elements(mock_tree, "function test() {}")
            
            # Should return empty lists instead of crashing
            assert result == {"functions": [], "classes": [], "variables": [], "imports": [], "exports": []}

    def test_extreme_file_sizes(self, extractor):
        """Test handling of extremely large files"""
        # Simulate very large file
        large_content = "function test() {}\n" * 10000  # 10k functions
        
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []
        
        # Should handle large files without crashing
        functions = extractor.extract_functions(mock_tree, large_content)
        assert isinstance(functions, list)

    def test_encoding_edge_cases(self, extractor):
        """Test various encoding edge cases"""
        # Test with different encodings
        encodings = ["utf-8", "latin1", "ascii", "utf-16"]
        
        for encoding in encodings:
            extractor._file_encoding = encoding
            mock_node = Mock()
            mock_node.start_byte = 0
            mock_node.end_byte = 5
            mock_node.start_point = (0, 0)
            mock_node.end_point = (0, 5)
            
            extractor.content_lines = ["test"]
            
            # Should handle different encodings
            with patch('tree_sitter_analyzer.languages.javascript_plugin.extract_text_slice') as mock_extract:
                mock_extract.return_value = "test"
                result = extractor._get_node_text_optimized(mock_node)
                assert isinstance(result, str)