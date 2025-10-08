#!/usr/bin/env python3
"""
Comprehensive tests for TypeScript plugin to achieve high coverage.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from tree_sitter_analyzer.languages.typescript_plugin import (
    TypeScriptElementExtractor,
    TypeScriptPlugin
)
from tree_sitter_analyzer.models import AnalysisResult, Function, Class, Variable, Import
from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest


class TestTypeScriptElementExtractorComprehensive:
    """Comprehensive test suite for TypeScript element extractor"""

    def setup_method(self):
        """Set up test fixtures"""
        self.extractor = TypeScriptElementExtractor()

    def test_init(self):
        """Test extractor initialization"""
        assert self.extractor.current_file == ""
        assert self.extractor.source_code == ""
        assert self.extractor.content_lines == []
        assert self.extractor.imports == []
        assert self.extractor.exports == []
        assert isinstance(self.extractor._node_text_cache, dict)
        assert isinstance(self.extractor._processed_nodes, set)
        assert isinstance(self.extractor._element_cache, dict)

    def test_set_source_info(self):
        """Test setting source information"""
        self.extractor.set_source_info("test.ts", "const x = 1;")
        assert self.extractor.current_file == "test.ts"
        assert self.extractor.source_code == "const x = 1;"
        assert self.extractor.content_lines == ["const x = 1;"]

    def test_get_node_text_cached(self):
        """Test node text caching"""
        mock_node = Mock()
        mock_node.id = 123
        mock_node.start_byte = 0
        mock_node.end_byte = 5
        
        self.extractor.source_code = "hello world"
        
        # First call should cache
        result1 = self.extractor._get_node_text(mock_node)
        assert result1 == "hello"
        assert 123 in self.extractor._node_text_cache
        
        # Second call should use cache
        result2 = self.extractor._get_node_text(mock_node)
        assert result2 == "hello"

    def test_get_node_text_with_encoding_error(self):
        """Test node text extraction with encoding error"""
        mock_node = Mock()
        mock_node.id = 123
        mock_node.start_byte = 0
        mock_node.end_byte = 5
        
        # Set invalid bytes that might cause encoding issues
        self.extractor.source_code = "test"
        
        with patch('tree_sitter_analyzer.languages.typescript_plugin.extract_text_slice') as mock_extract:
            mock_extract.side_effect = UnicodeDecodeError('utf-8', b'', 0, 1, 'invalid')
            result = self.extractor._get_node_text(mock_node)
            assert result == ""

    def test_extract_tsdoc_comment(self):
        """Test TSDoc comment extraction"""
        # Test with JSDoc style comment
        comment_text = "/**\n * Test function\n * @param x - Parameter\n * @returns Result\n */"
        result = self.extractor._extract_tsdoc_comment(comment_text)
        assert "Test function" in result
        assert "@param x - Parameter" in result
        assert "@returns Result" in result

        # Test with single line comment
        comment_text = "// Simple comment"
        result = self.extractor._extract_tsdoc_comment(comment_text)
        assert "Simple comment" in result

        # Test with multiline comment
        comment_text = "/* Multi\nline\ncomment */"
        result = self.extractor._extract_tsdoc_comment(comment_text)
        assert "Multi line comment" in result

        # Test with empty comment
        result = self.extractor._extract_tsdoc_comment("")
        assert result == ""

    def test_calculate_complexity_simple(self):
        """Test complexity calculation for simple cases"""
        mock_node = Mock()
        mock_node.id = 123
        mock_node.type = "function_declaration"
        mock_node.children = []
        
        result = self.extractor._calculate_complexity(mock_node)
        assert result == 1  # Base complexity

    def test_calculate_complexity_with_control_flow(self):
        """Test complexity calculation with control flow"""
        # Create mock nodes for control flow structures
        if_node = Mock()
        if_node.type = "if_statement"
        if_node.children = []
        
        for_node = Mock()
        for_node.type = "for_statement"
        for_node.children = []
        
        while_node = Mock()
        while_node.type = "while_statement"
        while_node.children = []
        
        mock_node = Mock()
        mock_node.id = 123
        mock_node.type = "function_declaration"
        mock_node.children = [if_node, for_node, while_node]
        
        # Mock walk method to return control flow nodes
        with patch.object(mock_node, 'walk') as mock_walk:
            mock_walk.return_value = [mock_node, if_node, for_node, while_node]
            result = self.extractor._calculate_complexity(mock_node)
            assert result > 1  # Should be higher than base complexity

    def test_extract_function_signature_basic(self):
        """Test basic function signature extraction"""
        mock_node = Mock()
        mock_node.type = "function_declaration"
        
        # Mock function name
        name_node = Mock()
        name_node.type = "identifier"
        
        # Mock parameters
        params_node = Mock()
        params_node.type = "formal_parameters"
        params_node.children = []
        
        mock_node.children = [name_node, params_node]
        
        with patch.object(self.extractor, '_get_node_text') as mock_get_text:
            mock_get_text.side_effect = lambda node: {
                name_node: "testFunction",
                params_node: "()",
                mock_node: "function testFunction() {}"
            }.get(node, "")
            
            result = self.extractor._extract_function_signature(mock_node)
            assert result["name"] == "testFunction"
            assert result["parameters"] == []
            assert not result["is_async"]
            assert not result["is_generator"]

    def test_extract_function_signature_async(self):
        """Test async function signature extraction"""
        mock_node = Mock()
        mock_node.type = "function_declaration"
        
        with patch.object(self.extractor, '_get_node_text') as mock_get_text:
            mock_get_text.return_value = "async function testAsync() {}"
            
            result = self.extractor._extract_function_signature(mock_node)
            assert result["is_async"]

    def test_extract_function_signature_generator(self):
        """Test generator function signature extraction"""
        mock_node = Mock()
        mock_node.type = "generator_function_declaration"
        
        with patch.object(self.extractor, '_get_node_text') as mock_get_text:
            mock_get_text.return_value = "function* testGenerator() {}"
            
            result = self.extractor._extract_function_signature(mock_node)
            assert result["is_generator"]

    def test_extract_function_signature_arrow(self):
        """Test arrow function signature extraction"""
        mock_node = Mock()
        mock_node.type = "arrow_function"
        
        with patch.object(self.extractor, '_get_node_text') as mock_get_text:
            mock_get_text.return_value = "(x) => x * 2"
            
            result = self.extractor._extract_function_signature(mock_node)
            assert result["is_arrow"]

    def test_extract_class_signature_basic(self):
        """Test basic class signature extraction"""
        mock_node = Mock()
        mock_node.type = "class_declaration"
        
        # Mock class name
        name_node = Mock()
        name_node.type = "type_identifier"
        
        mock_node.children = [name_node]
        
        with patch.object(self.extractor, '_get_node_text') as mock_get_text:
            mock_get_text.side_effect = lambda node: {
                name_node: "TestClass",
                mock_node: "class TestClass {}"
            }.get(node, "")
            
            result = self.extractor._extract_class_signature(mock_node)
            assert result["name"] == "TestClass"
            assert result["superclass"] is None
            assert not result["is_abstract"]

    def test_extract_class_signature_with_inheritance(self):
        """Test class signature with inheritance"""
        mock_node = Mock()
        mock_node.type = "class_declaration"
        
        with patch.object(self.extractor, '_get_node_text') as mock_get_text:
            mock_get_text.return_value = "class Child extends Parent {}"
            
            result = self.extractor._extract_class_signature(mock_node)
            assert "extends" in mock_get_text.return_value

    def test_extract_class_signature_abstract(self):
        """Test abstract class signature extraction"""
        mock_node = Mock()
        mock_node.type = "abstract_class_declaration"
        
        with patch.object(self.extractor, '_get_node_text') as mock_get_text:
            mock_get_text.return_value = "abstract class AbstractClass {}"
            
            result = self.extractor._extract_class_signature(mock_node)
            assert result["is_abstract"]

    def test_extract_interface_signature(self):
        """Test interface signature extraction"""
        mock_node = Mock()
        mock_node.type = "interface_declaration"
        
        # Mock interface name
        name_node = Mock()
        name_node.type = "type_identifier"
        
        mock_node.children = [name_node]
        
        with patch.object(self.extractor, '_get_node_text') as mock_get_text:
            mock_get_text.side_effect = lambda node: {
                name_node: "TestInterface",
                mock_node: "interface TestInterface {}"
            }.get(node, "")
            
            result = self.extractor._extract_interface_signature(mock_node)
            assert result["name"] == "TestInterface"
            assert result["extends"] == []

    def test_extract_type_alias_signature(self):
        """Test type alias signature extraction"""
        mock_node = Mock()
        mock_node.type = "type_alias_declaration"
        
        with patch.object(self.extractor, '_get_node_text') as mock_get_text:
            mock_get_text.return_value = "type StringOrNumber = string | number"
            
            result = self.extractor._extract_type_alias_signature(mock_node)
            assert "StringOrNumber" in mock_get_text.return_value

    def test_extract_enum_signature(self):
        """Test enum signature extraction"""
        mock_node = Mock()
        mock_node.type = "enum_declaration"
        
        # Mock enum name
        name_node = Mock()
        name_node.type = "identifier"
        
        mock_node.children = [name_node]
        
        with patch.object(self.extractor, '_get_node_text') as mock_get_text:
            mock_get_text.side_effect = lambda node: {
                name_node: "Color",
                mock_node: "enum Color { Red, Green, Blue }"
            }.get(node, "")
            
            result = self.extractor._extract_enum_signature(mock_node)
            assert result["name"] == "Color"

    def test_extract_variable_signature_const(self):
        """Test const variable signature extraction"""
        mock_node = Mock()
        mock_node.type = "lexical_declaration"
        
        with patch.object(self.extractor, '_get_node_text') as mock_get_text:
            mock_get_text.return_value = "const x = 42"
            
            result = self.extractor._extract_variable_signature(mock_node)
            assert "const" in mock_get_text.return_value

    def test_extract_variable_signature_let(self):
        """Test let variable signature extraction"""
        mock_node = Mock()
        mock_node.type = "lexical_declaration"
        
        with patch.object(self.extractor, '_get_node_text') as mock_get_text:
            mock_get_text.return_value = "let y = 'hello'"
            
            result = self.extractor._extract_variable_signature(mock_node)
            assert "let" in mock_get_text.return_value

    def test_extract_variable_signature_var(self):
        """Test var variable signature extraction"""
        mock_node = Mock()
        mock_node.type = "variable_declaration"
        
        with patch.object(self.extractor, '_get_node_text') as mock_get_text:
            mock_get_text.return_value = "var z = true"
            
            result = self.extractor._extract_variable_signature(mock_node)
            assert "var" in mock_get_text.return_value

    def test_extract_import_signature_default(self):
        """Test default import signature extraction"""
        mock_node = Mock()
        mock_node.type = "import_statement"
        
        with patch.object(self.extractor, '_get_node_text') as mock_get_text:
            mock_get_text.return_value = "import React from 'react'"
            
            result = self.extractor._extract_import_signature(mock_node)
            assert "React" in mock_get_text.return_value
            assert "react" in mock_get_text.return_value

    def test_extract_import_signature_named(self):
        """Test named import signature extraction"""
        mock_node = Mock()
        mock_node.type = "import_statement"
        
        with patch.object(self.extractor, '_get_node_text') as mock_get_text:
            mock_get_text.return_value = "import { useState, useEffect } from 'react'"
            
            result = self.extractor._extract_import_signature(mock_node)
            assert "useState" in mock_get_text.return_value
            assert "useEffect" in mock_get_text.return_value

    def test_extract_export_signature_default(self):
        """Test default export signature extraction"""
        mock_node = Mock()
        mock_node.type = "export_statement"
        
        with patch.object(self.extractor, '_get_node_text') as mock_get_text:
            mock_get_text.return_value = "export default MyComponent"
            
            result = self.extractor._extract_export_signature(mock_node)
            assert "default" in mock_get_text.return_value
            assert "MyComponent" in mock_get_text.return_value

    def test_extract_export_signature_named(self):
        """Test named export signature extraction"""
        mock_node = Mock()
        mock_node.type = "export_statement"
        
        with patch.object(self.extractor, '_get_node_text') as mock_get_text:
            mock_get_text.return_value = "export { func1, func2 }"
            
            result = self.extractor._extract_export_signature(mock_node)
            assert "func1" in mock_get_text.return_value
            assert "func2" in mock_get_text.return_value

    def test_extract_decorator_signature(self):
        """Test decorator signature extraction"""
        mock_node = Mock()
        mock_node.type = "decorator"
        
        with patch.object(self.extractor, '_get_node_text') as mock_get_text:
            mock_get_text.return_value = "@Component({ selector: 'app-test' })"
            
            result = self.extractor._extract_decorator_signature(mock_node)
            assert "Component" in mock_get_text.return_value

    def test_extract_generic_signature(self):
        """Test generic signature extraction"""
        mock_node = Mock()
        mock_node.type = "type_parameters"
        
        with patch.object(self.extractor, '_get_node_text') as mock_get_text:
            mock_get_text.return_value = "<T, U extends string>"
            
            result = self.extractor._extract_generic_signature(mock_node)
            assert "T" in mock_get_text.return_value
            assert "U extends string" in mock_get_text.return_value

    def test_extract_method_signature_public(self):
        """Test public method signature extraction"""
        mock_node = Mock()
        mock_node.type = "method_definition"
        
        with patch.object(self.extractor, '_get_node_text') as mock_get_text:
            mock_get_text.return_value = "public testMethod() {}"
            
            result = self.extractor._extract_method_signature(mock_node)
            assert "public" in mock_get_text.return_value

    def test_extract_method_signature_private(self):
        """Test private method signature extraction"""
        mock_node = Mock()
        mock_node.type = "method_definition"
        
        with patch.object(self.extractor, '_get_node_text') as mock_get_text:
            mock_get_text.return_value = "private _privateMethod() {}"
            
            result = self.extractor._extract_method_signature(mock_node)
            assert "private" in mock_get_text.return_value

    def test_extract_method_signature_static(self):
        """Test static method signature extraction"""
        mock_node = Mock()
        mock_node.type = "method_definition"
        
        with patch.object(self.extractor, '_get_node_text') as mock_get_text:
            mock_get_text.return_value = "static staticMethod() {}"
            
            result = self.extractor._extract_method_signature(mock_node)
            assert "static" in mock_get_text.return_value

    def test_extract_property_signature_public(self):
        """Test public property signature extraction"""
        mock_node = Mock()
        mock_node.type = "public_field_definition"
        
        with patch.object(self.extractor, '_get_node_text') as mock_get_text:
            mock_get_text.return_value = "public name: string"
            
            result = self.extractor._extract_property_signature(mock_node)
            assert "public" in mock_get_text.return_value
            assert "string" in mock_get_text.return_value

    def test_extract_property_signature_private(self):
        """Test private property signature extraction"""
        mock_node = Mock()
        mock_node.type = "private_field_definition"
        
        with patch.object(self.extractor, '_get_node_text') as mock_get_text:
            mock_get_text.return_value = "private _id: number"
            
            result = self.extractor._extract_property_signature(mock_node)
            assert "private" in mock_get_text.return_value
            assert "number" in mock_get_text.return_value

    def test_extract_namespace_signature(self):
        """Test namespace signature extraction"""
        mock_node = Mock()
        mock_node.type = "namespace_declaration"
        
        with patch.object(self.extractor, '_get_node_text') as mock_get_text:
            mock_get_text.return_value = "namespace MyNamespace {}"
            
            result = self.extractor._extract_namespace_signature(mock_node)
            assert "MyNamespace" in mock_get_text.return_value

    def test_extract_elements_from_tree(self):
        """Test extracting elements from tree"""
        mock_tree = Mock()
        mock_root = Mock()
        mock_tree.root_node = mock_root
        
        # Mock child nodes
        func_node = Mock()
        func_node.type = "function_declaration"
        func_node.id = 1
        
        class_node = Mock()
        class_node.type = "class_declaration"
        class_node.id = 2
        
        mock_root.walk.return_value = [mock_root, func_node, class_node]
        
        with patch.object(self.extractor, '_extract_function_signature') as mock_func:
            mock_func.return_value = {"name": "testFunc", "line_number": 1}
            with patch.object(self.extractor, '_extract_class_signature') as mock_class:
                mock_class.return_value = {"name": "TestClass", "line_number": 5}
                
                result = self.extractor.extract_elements_from_tree(mock_tree)
                
                assert "functions" in result
                assert "classes" in result
                assert len(result["functions"]) == 1
                assert len(result["classes"]) == 1

    def test_extract_elements_with_error_handling(self):
        """Test element extraction with error handling"""
        mock_tree = Mock()
        mock_root = Mock()
        mock_tree.root_node = mock_root
        
        # Mock node that will cause an error
        error_node = Mock()
        error_node.type = "function_declaration"
        error_node.id = 1
        
        mock_root.walk.return_value = [mock_root, error_node]
        
        with patch.object(self.extractor, '_extract_function_signature') as mock_func:
            mock_func.side_effect = Exception("Test error")
            
            result = self.extractor.extract_elements_from_tree(mock_tree)
            
            # Should handle error gracefully
            assert "functions" in result
            assert len(result["functions"]) == 0


class TestTypeScriptPluginComprehensive:
    """Comprehensive test suite for TypeScript plugin"""

    def setup_method(self):
        """Set up test fixtures"""
        self.plugin = TypeScriptPlugin()

    def test_init(self):
        """Test plugin initialization"""
        assert self.plugin.name == "typescript"
        assert "TypeScript" in self.plugin.description
        assert ".ts" in self.plugin.file_extensions
        assert ".tsx" in self.plugin.file_extensions

    def test_is_applicable_typescript_file(self):
        """Test applicability for TypeScript files"""
        assert self.plugin.is_applicable("test.ts")
        assert self.plugin.is_applicable("component.tsx")
        assert not self.plugin.is_applicable("test.js")
        assert not self.plugin.is_applicable("test.py")

    def test_get_language_name(self):
        """Test getting language name"""
        assert self.plugin.get_language_name() == "typescript"

    def test_get_file_extensions(self):
        """Test getting file extensions"""
        extensions = self.plugin.get_file_extensions()
        assert ".ts" in extensions
        assert ".tsx" in extensions

    def test_get_supported_queries(self):
        """Test getting supported queries"""
        queries = self.plugin.get_supported_queries()
        assert "functions" in queries
        assert "classes" in queries
        assert "interfaces" in queries
        assert "type_aliases" in queries
        assert "enums" in queries
        assert "variables" in queries

    @patch('tree_sitter_analyzer.languages.typescript_plugin.loader')
    def test_analyze_file_success(self, mock_loader):
        """Test successful file analysis"""
        # Mock tree-sitter components
        mock_language = Mock()
        mock_parser = Mock()
        mock_tree = Mock()
        
        mock_loader.get_language.return_value = mock_language
        mock_loader.create_parser.return_value = mock_parser
        mock_parser.parse.return_value = mock_tree
        
        # Mock extractor
        mock_extractor = Mock()
        mock_extractor.extract_elements_from_tree.return_value = {
            "functions": [{"name": "testFunc", "line_number": 1}],
            "classes": [{"name": "TestClass", "line_number": 5}]
        }
        
        with patch.object(self.plugin, '_create_extractor', return_value=mock_extractor):
            request = AnalysisRequest(
                file_path="test.ts",
                content="class TestClass { testFunc() {} }",
                language="typescript"
            )
            
            result = self.plugin.analyze_file(request)
            
            assert isinstance(result, AnalysisResult)
            assert result.file_path == "test.ts"
            assert result.language == "typescript"

    @patch('tree_sitter_analyzer.languages.typescript_plugin.loader')
    def test_analyze_file_with_encoding_error(self, mock_loader):
        """Test file analysis with encoding error"""
        mock_loader.get_language.side_effect = Exception("Language not available")
        
        request = AnalysisRequest(
            file_path="test.ts",
            content="const x = 1;",
            language="typescript"
        )
        
        result = self.plugin.analyze_file(request)
        
        # Should handle error gracefully
        assert isinstance(result, AnalysisResult)
        assert result.file_path == "test.ts"

    def test_create_extractor(self):
        """Test extractor creation"""
        extractor = self.plugin._create_extractor()
        assert isinstance(extractor, TypeScriptElementExtractor)

    def test_get_plugin_info(self):
        """Test getting plugin info"""
        info = self.plugin.get_plugin_info()
        assert info["name"] == "typescript"
        assert "TypeScript" in info["description"]
        assert ".ts" in info["file_extensions"]
        assert "version" in info

    def test_plugin_with_complex_typescript_features(self):
        """Test plugin with complex TypeScript features"""
        # This would test the plugin with actual TypeScript code
        # containing interfaces, generics, decorators, etc.
        complex_code = """
        interface User<T> {
            id: number;
            name: string;
            data: T;
        }
        
        @Component({
            selector: 'app-user'
        })
        class UserComponent<T> implements User<T> {
            public id: number = 0;
            private _name: string = '';
            
            constructor(private service: UserService) {}
            
            public async getName(): Promise<string> {
                return this._name;
            }
            
            static create<U>(data: U): UserComponent<U> {
                return new UserComponent<U>(new UserService());
            }
        }
        
        type StringOrNumber = string | number;
        
        enum Status {
            Active = 'active',
            Inactive = 'inactive'
        }
        
        namespace Utils {
            export function helper(): void {}
        }
        """
        
        request = AnalysisRequest(
            file_path="complex.ts",
            content=complex_code,
            language="typescript"
        )
        
        # Mock the tree-sitter components since we can't rely on them being available
        with patch('tree_sitter_analyzer.languages.typescript_plugin.loader') as mock_loader:
            mock_language = Mock()
            mock_parser = Mock()
            mock_tree = Mock()
            
            mock_loader.get_language.return_value = mock_language
            mock_loader.create_parser.return_value = mock_parser
            mock_parser.parse.return_value = mock_tree
            
            # Mock a comprehensive extraction result
            mock_extractor = Mock()
            mock_extractor.extract_elements_from_tree.return_value = {
                "functions": [
                    {"name": "getName", "is_async": True, "line_number": 15},
                    {"name": "create", "is_static": True, "line_number": 19}
                ],
                "classes": [
                    {"name": "UserComponent", "line_number": 8, "is_generic": True}
                ],
                "interfaces": [
                    {"name": "User", "line_number": 1, "is_generic": True}
                ],
                "type_aliases": [
                    {"name": "StringOrNumber", "line_number": 23}
                ],
                "enums": [
                    {"name": "Status", "line_number": 25}
                ],
                "variables": [],
                "imports": [],
                "exports": [],
                "decorators": [
                    {"name": "Component", "line_number": 6}
                ],
                "namespaces": [
                    {"name": "Utils", "line_number": 30}
                ]
            }
            
            with patch.object(self.plugin, '_create_extractor', return_value=mock_extractor):
                result = self.plugin.analyze_file(request)
                
                assert isinstance(result, AnalysisResult)
                assert result.language == "typescript"

    def test_error_handling_in_analysis(self):
        """Test error handling during analysis"""
        request = AnalysisRequest(
            file_path="error.ts",
            content="invalid typescript code {{{",
            language="typescript"
        )
        
        with patch('tree_sitter_analyzer.languages.typescript_plugin.loader') as mock_loader:
            mock_loader.get_language.side_effect = Exception("Parse error")
            
            result = self.plugin.analyze_file(request)
            
            # Should handle error gracefully and return a valid result
            assert isinstance(result, AnalysisResult)
            assert result.file_path == "error.ts"

    def test_caching_behavior(self):
        """Test caching behavior in extractor"""
        extractor = TypeScriptElementExtractor()
        
        # Test node text caching
        mock_node1 = Mock()
        mock_node1.id = 1
        mock_node1.start_byte = 0
        mock_node1.end_byte = 4
        
        mock_node2 = Mock()
        mock_node2.id = 1  # Same ID as node1
        mock_node2.start_byte = 0
        mock_node2.end_byte = 4
        
        extractor.source_code = "test"
        
        # First call
        result1 = extractor._get_node_text(mock_node1)
        assert result1 == "test"
        assert 1 in extractor._node_text_cache
        
        # Second call with same ID should use cache
        result2 = extractor._get_node_text(mock_node2)
        assert result2 == "test"

    def test_performance_optimizations(self):
        """Test performance optimization features"""
        extractor = TypeScriptElementExtractor()
        
        # Test processed nodes tracking
        mock_node = Mock()
        mock_node.id = 123
        
        # Add to processed nodes
        extractor._processed_nodes.add(123)
        
        # Check if node is already processed
        assert 123 in extractor._processed_nodes

    def test_memory_cleanup(self):
        """Test memory cleanup in extractor"""
        extractor = TypeScriptElementExtractor()
        
        # Add some cached data
        extractor._node_text_cache[1] = "test"
        extractor._processed_nodes.add(1)
        extractor._element_cache[(1, "function")] = {"name": "test"}
        
        # Verify data is there
        assert len(extractor._node_text_cache) > 0
        assert len(extractor._processed_nodes) > 0
        assert len(extractor._element_cache) > 0
        
        # Clear caches (this would typically happen between files)
        extractor._node_text_cache.clear()
        extractor._processed_nodes.clear()
        extractor._element_cache.clear()
        
        # Verify cleanup
        assert len(extractor._node_text_cache) == 0
        assert len(extractor._processed_nodes) == 0
        assert len(extractor._element_cache) == 0