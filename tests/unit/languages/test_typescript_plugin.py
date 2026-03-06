#!/usr/bin/env python3
"""
Tests for tree_sitter_analyzer.languages.typescript_plugin module.

This module tests the TypeScriptPlugin class which provides TypeScript language
support with comprehensive feature coverage including interfaces, type aliases,
enums, generics, decorators, and modern JavaScript features with type annotations.
"""

from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.languages.typescript_plugin import (
    TypeScriptElementExtractor,
    TypeScriptPlugin,
)
from tree_sitter_analyzer.plugins import ElementExtractorBase
from tree_sitter_analyzer.plugins.base import ElementExtractor, LanguagePlugin


class TestTypeScriptElementExtractor:
    """Test cases for TypeScriptElementExtractor class"""

    @pytest.fixture
    def extractor(self) -> TypeScriptElementExtractor:
        """Create a TypeScriptElementExtractor instance for testing"""
        return TypeScriptElementExtractor()

    @pytest.fixture
    def mock_tree(self) -> Mock:
        """Create a mock tree-sitter tree"""
        tree = Mock()
        root_node = Mock()
        root_node.children = []
        tree.root_node = root_node
        tree.language = Mock()
        return tree

    @pytest.fixture
    def sample_typescript_code(self) -> str:
        """Sample TypeScript code for testing"""
        return """
import { Component } from 'react';
import type { User } from './types';

// Type alias
type Status = 'active' | 'inactive' | 'pending';

// Interface
interface UserProfile extends User {
    status: Status;
    lastLogin?: Date;
}

// Enum
enum UserRole {
    ADMIN = 'admin',
    USER = 'user',
    GUEST = 'guest'
}

// Generic interface
interface Repository<T> {
    findById(id: string): Promise<T | null>;
    save(entity: T): Promise<T>;
    delete(id: string): Promise<void>;
}

// Abstract class
abstract class BaseService<T> {
    protected repository: Repository<T>;

    constructor(repository: Repository<T>) {
        this.repository = repository;
    }

    abstract validate(entity: T): boolean;

    async save(entity: T): Promise<T> {
        if (!this.validate(entity)) {
            throw new Error('Validation failed');
        }
        return this.repository.save(entity);
    }
}

// Concrete class
class UserService extends BaseService<UserProfile> {
    private static instance: UserService;

    private constructor(repository: Repository<UserProfile>) {
        super(repository);
    }

    static getInstance(repository: Repository<UserProfile>): UserService {
        if (!UserService.instance) {
            UserService.instance = new UserService(repository);
        }
        return UserService.instance;
    }

    validate(user: UserProfile): boolean {
        return user.status !== undefined && user.lastLogin !== undefined;
    }

    async getUsersByStatus(status: Status): Promise<UserProfile[]> {
        return [];
    }
}

// Arrow function with generics
const mapArray = <T, U>(array: T[], mapper: (item: T) => U): U[] => {
    return array.map(mapper);
};

// Async function
async function fetchUserData(userId: string): Promise<UserProfile | null> {
    try {
        const response = await fetch(`/api/users/${userId}`);
        if (!response.ok) {
            throw new Error('Failed to fetch user');
        }
        return response.json();
    } catch (error) {
        console.error('Error fetching user:', error);
        return null;
    }
}

// Decorator
function log(target: any, propertyName: string, descriptor: PropertyDescriptor) {
    const method = descriptor.value;
    descriptor.value = function (...args: any[]) {
        console.log(`Calling ${propertyName} with args:`, args);
        return method.apply(this, args);
    };
}

// React component
class UserComponent extends Component<{ user: UserProfile }> {
    @log
    handleClick(): void {
        console.log('User clicked:', this.props.user.status);
    }

    render() {
        const { user } = this.props;
        return `<div>User: ${user.status}</div>`;
    }
}

// Export statements
export { UserService, UserRole, mapArray };
export type { UserProfile, Status };
export default UserComponent;
"""

    def test_extractor_initialization(self, extractor):
        """Test that extractor initializes properly"""
        assert isinstance(extractor, ElementExtractorBase)
        assert extractor.current_file == ""
        assert extractor.source_code == ""
        assert extractor.content_lines == []
        assert extractor.imports == []
        assert extractor.exports == []
        assert extractor.is_module is False
        assert extractor.is_tsx is False
        assert extractor.framework_type == ""

    def test_detect_file_characteristics_module(self, extractor):
        """Test detection of TypeScript module characteristics"""
        extractor.source_code = "import React from 'react'; export default MyComponent;"
        extractor._detect_file_characteristics()

        assert extractor.is_module is True
        assert extractor.framework_type == "react"

    def test_detect_file_characteristics_tsx(self, extractor):
        """Test detection of TSX characteristics"""
        extractor.current_file = "Component.tsx"
        extractor.source_code = "return <div>Hello World</div>;"
        extractor._detect_file_characteristics()

        assert extractor.is_tsx is True

    def test_detect_file_characteristics_angular(self, extractor):
        """Test detection of Angular framework"""
        extractor.source_code = "import { Component } from '@angular/core';"
        extractor._detect_file_characteristics()

        assert extractor.framework_type == "angular"

    def test_detect_file_characteristics_vue(self, extractor):
        """Test detection of Vue framework"""
        extractor.source_code = "import Vue from 'vue';"
        extractor._detect_file_characteristics()

        assert extractor.framework_type == "vue"

    def test_reset_caches(self, extractor):
        """Test cache reset functionality"""
        # Populate caches
        extractor._node_text_cache[1] = "test"
        extractor._processed_nodes.add(1)
        extractor._element_cache[(1, "test")] = "element"
        extractor._tsdoc_cache[1] = "doc"
        extractor._complexity_cache[1] = 5

        # Reset caches
        extractor._reset_caches()

        # Verify all caches are empty
        assert len(extractor._node_text_cache) == 0
        assert len(extractor._processed_nodes) == 0
        assert len(extractor._element_cache) == 0
        assert len(extractor._tsdoc_cache) == 0
        assert len(extractor._complexity_cache) == 0

    def test_infer_type_from_value(self, extractor):
        """Test TypeScript type inference from values"""
        assert extractor._infer_type_from_value('"hello"') == "string"
        assert extractor._infer_type_from_value("'world'") == "string"
        assert extractor._infer_type_from_value("`template`") == "string"
        assert extractor._infer_type_from_value("true") == "boolean"
        assert extractor._infer_type_from_value("false") == "boolean"
        assert extractor._infer_type_from_value("null") == "null"
        assert extractor._infer_type_from_value("undefined") == "undefined"
        assert extractor._infer_type_from_value("[]") == "array"
        assert extractor._infer_type_from_value("{}") == "object"
        assert extractor._infer_type_from_value("42") == "number"
        assert extractor._infer_type_from_value("3.14") == "number"
        assert extractor._infer_type_from_value("() => {}") == "function"
        assert extractor._infer_type_from_value("function() {}") == "function"
        assert extractor._infer_type_from_value("unknown") == "any"
        assert extractor._infer_type_from_value(None) == "any"

    def test_clean_tsdoc(self, extractor):
        """Test TSDoc comment cleaning"""
        tsdoc = """/**
         * This is a TSDoc comment
         * @param user The user object
         * @returns Promise with user data
         */"""

        cleaned = extractor._clean_tsdoc(tsdoc)
        expected = "This is a TSDoc comment @param user The user object @returns Promise with user data"
        assert cleaned == expected

    def test_clean_tsdoc_empty(self, extractor):
        """Test TSDoc cleaning with empty input"""
        assert extractor._clean_tsdoc("") == ""
        assert extractor._clean_tsdoc(None) == ""

    def test_extract_functions_empty_tree(self, extractor, mock_tree):
        """Test function extraction with empty tree"""
        functions = extractor.extract_functions(mock_tree, "")
        assert functions == []

    def test_extract_classes_empty_tree(self, extractor, mock_tree):
        """Test class extraction with empty tree"""
        classes = extractor.extract_classes(mock_tree, "")
        assert classes == []

    def test_extract_variables_empty_tree(self, extractor, mock_tree):
        """Test variable extraction with empty tree"""
        variables = extractor.extract_variables(mock_tree, "")
        assert variables == []

    def test_extract_imports_empty_tree(self, extractor, mock_tree):
        """Test import extraction with empty tree"""
        imports = extractor.extract_imports(mock_tree, "")
        assert imports == []

    def test_is_framework_component_react(self, extractor):
        """Test React component detection"""
        extractor.framework_type = "react"

        # Mock node with React component pattern
        node = Mock()
        node_text = "class MyComponent extends Component"
        extractor._get_node_text_optimized = Mock(return_value=node_text)

        assert extractor._is_framework_component(node, "MyComponent") is True

    def test_is_framework_component_angular(self, extractor):
        """Test Angular component detection"""
        extractor.framework_type = "angular"
        extractor.source_code = "@Component({ selector: 'app-test' })"

        node = Mock()
        assert extractor._is_framework_component(node, "TestComponent") is True

    def test_is_framework_component_vue(self, extractor):
        """Test Vue component detection"""
        extractor.framework_type = "vue"
        extractor.source_code = "Vue.component('test', {})"

        node = Mock()
        assert extractor._is_framework_component(node, "TestComponent") is True

    def test_is_exported_class(self, extractor):
        """Test exported class detection"""
        extractor.source_code = "export class TestClass {}"
        assert extractor._is_exported_class("TestClass") is True

        extractor.source_code = "export default TestClass"
        assert extractor._is_exported_class("TestClass") is True

        extractor.source_code = "class TestClass {}"
        assert extractor._is_exported_class("TestClass") is False

    def test_calculate_complexity_optimized(self, extractor):
        """Test complexity calculation"""
        # Mock node
        node = Mock()
        node_id = id(node)

        # Test caching
        extractor._complexity_cache[node_id] = 5
        assert extractor._calculate_complexity_optimized(node) == 5

        # Test calculation
        extractor._complexity_cache.clear()
        extractor._get_node_text_optimized = Mock(
            return_value="if (condition) { while (true) { for (let i = 0; i < 10; i++) {} } }"
        )
        complexity = extractor._calculate_complexity_optimized(node)
        assert complexity > 1  # Should be greater than base complexity


class TestTypeScriptPlugin:
    """Test cases for TypeScriptPlugin class"""

    @pytest.fixture
    def plugin(self) -> TypeScriptPlugin:
        """Create a TypeScriptPlugin instance for testing"""
        return TypeScriptPlugin()

    def test_plugin_initialization(self, plugin):
        """Test that plugin initializes properly"""
        assert isinstance(plugin, TypeScriptPlugin)
        assert isinstance(plugin, LanguagePlugin)

    def test_language_name(self, plugin):
        """Test language name property"""
        assert plugin.language_name == "typescript"
        assert plugin.get_language_name() == "typescript"

    def test_file_extensions(self, plugin):
        """Test file extensions property"""
        expected_extensions = [".ts", ".tsx", ".d.ts"]
        assert plugin.file_extensions == expected_extensions
        assert plugin.get_file_extensions() == expected_extensions

    def test_create_extractor(self, plugin):
        """Test extractor creation"""
        extractor = plugin.create_extractor()
        assert isinstance(extractor, TypeScriptElementExtractor)
        assert isinstance(extractor, ElementExtractorBase)

    def test_get_extractor(self, plugin):
        """Test extractor getter"""
        extractor = plugin.get_extractor()
        assert isinstance(extractor, TypeScriptElementExtractor)

    def test_supported_queries(self, plugin):
        """Test supported queries"""
        queries = plugin.get_supported_queries()
        expected_queries = [
            "function",
            "class",
            "interface",
            "type_alias",
            "enum",
            "variable",
            "import",
            "export",
            "async_function",
            "arrow_function",
            "method",
            "constructor",
            "generic",
            "decorator",
            "signature",
            "react_component",
            "angular_component",
            "vue_component",
        ]

        for query in expected_queries:
            assert query in queries

    def test_is_applicable(self, plugin):
        """Test file applicability"""
        assert plugin.is_applicable("test.ts") is True
        assert plugin.is_applicable("component.tsx") is True
        assert plugin.is_applicable("types.d.ts") is True
        assert plugin.is_applicable("test.js") is False
        assert plugin.is_applicable("test.py") is False
        assert plugin.is_applicable("test.java") is False

    def test_plugin_info(self, plugin):
        """Test plugin information"""
        info = plugin.get_plugin_info()

        assert info["name"] == "TypeScript Plugin"
        assert info["language"] == "typescript"
        assert info["extensions"] == [".ts", ".tsx", ".d.ts"]
        assert info["version"] == "2.0.0"
        assert "supported_queries" in info
        assert "features" in info

        # Check some expected features
        features = info["features"]
        assert "TypeScript syntax support" in features
        assert "Interface declarations" in features
        assert "Type aliases" in features
        assert "Enums" in features
        assert "Generics" in features
        assert "Decorators" in features
        assert "TSX/JSX support" in features

    @patch(
        "tree_sitter_analyzer.languages.typescript_plugin.TREE_SITTER_AVAILABLE", False
    )
    @pytest.mark.asyncio
    async def test_analyze_file_no_tree_sitter(self, plugin):
        """Test file analysis when tree-sitter is not available"""
        from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest

        request = AnalysisRequest(file_path="test.ts")
        result = await plugin.analyze_file("test.ts", request)

        assert result.success is False
        assert "Tree-sitter library not available" in result.error_message

    @patch("tree_sitter_analyzer.languages.typescript_plugin.loader.load_language")
    @pytest.mark.asyncio
    async def test_analyze_file_no_language(self, mock_load_language, plugin):
        """Test file analysis when TypeScript language cannot be loaded"""
        from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest

        mock_load_language.return_value = None
        request = AnalysisRequest(file_path="test.ts")
        result = await plugin.analyze_file("test.ts", request)

        assert result.success is False
        assert "Could not load TypeScript language for parsing" in result.error_message

    @pytest.mark.asyncio
    async def test_analyze_file_missing_file(self, plugin):
        """Test file analysis with missing file"""
        from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest

        request = AnalysisRequest(file_path="nonexistent.ts")
        result = await plugin.analyze_file("nonexistent.ts", request)

        assert result.success is False
        assert result.error_message is not None

    def test_get_tree_sitter_language_caching(self, plugin):
        """Test tree-sitter language caching"""
        # First call should load the language
        with patch(
            "tree_sitter_analyzer.languages.typescript_plugin.loader.load_language"
        ) as mock_load:
            mock_language = Mock()
            mock_load.return_value = mock_language

            language1 = plugin.get_tree_sitter_language()
            assert language1 == mock_language
            assert mock_load.call_count == 1

            # Second call should use cached language
            language2 = plugin.get_tree_sitter_language()
            assert language2 == mock_language
            assert mock_load.call_count == 1  # Should not be called again


class TestTypeScriptPluginIntegration:
    """Integration tests for TypeScript plugin"""

    @pytest.fixture
    def plugin(self) -> TypeScriptPlugin:
        """Create a TypeScriptPlugin instance for testing"""
        return TypeScriptPlugin()

    def test_plugin_registration(self):
        """Test that TypeScript plugin can be discovered by plugin manager"""
        from tree_sitter_analyzer.plugins.manager import PluginManager

        manager = PluginManager()
        mock_plugin = TypeScriptPlugin()

        # Register the plugin directly (simulates discovery)
        manager.register_plugin(mock_plugin)
        plugins = manager.load_plugins()

        # Find TypeScript plugin
        typescript_plugin = None
        for plugin in plugins:
            if plugin.get_language_name() == "typescript":
                typescript_plugin = plugin
                break

        assert typescript_plugin is not None
        assert isinstance(typescript_plugin, TypeScriptPlugin)

    def test_formatter_integration(self):
        """Test TypeScript formatter integration"""
        from tree_sitter_analyzer.formatters.formatter_registry import (
            FormatterRegistry,
        )

        # Test that TypeScript formatter can be created
        formatter = FormatterRegistry.get_formatter_for_language("typescript", "full")
        assert formatter is not None

        # Test alias
        formatter_alias = FormatterRegistry.get_formatter_for_language("ts", "full")
        assert formatter_alias is not None

        # Test supported languages includes TypeScript
        supported = FormatterRegistry.get_supported_languages()
        assert "typescript" in supported or "ts" in supported

    def test_language_detection_integration(self):
        """Test TypeScript language detection integration"""
        from tree_sitter_analyzer.language_detector import detector

        # Test file extension detection
        assert detector.detect_from_extension("test.ts") == "typescript"
        assert detector.detect_from_extension("component.tsx") == "typescript"
        assert detector.detect_from_extension("types.d.ts") == "typescript"

        # Test language support
        assert detector.is_supported("typescript") is True

    def test_language_loader_integration(self):
        """Test TypeScript language loader integration"""
        from tree_sitter_analyzer.language_loader import get_loader

        loader = get_loader()

        # Test language availability check
        # Note: This might fail if tree-sitter-typescript is not installed
        # but the method should exist and not crash
        try:
            is_available = loader.is_language_available("typescript")
            assert isinstance(is_available, bool)
        except Exception:
            # If tree-sitter-typescript is not available, that's OK for testing
            pass

        # Test supported languages includes TypeScript
        loader.get_supported_languages()
        # TypeScript should be in the supported list (even if not available)
        assert "typescript" in loader.LANGUAGE_MODULES


class TestTypeScriptExtractorMerged:
    """Merged tests from variant files covering unique code paths."""

    @pytest.fixture
    def extractor(self) -> TypeScriptElementExtractor:
        """Create a TypeScriptElementExtractor instance for testing"""
        return TypeScriptElementExtractor()

    def test_get_node_text_optimized_cached(self, extractor):
        """Test node text extraction with caching"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (5, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 100
        mock_node.children = []
        mock_node.text = b"function test() {}"

        extractor.content_lines = ["function test() {", "  return 42;", "}"]
        extractor._file_encoding = "utf-8"

        text1 = extractor._get_node_text_optimized(mock_node)
        assert text1 is not None

        text2 = extractor._get_node_text_optimized(mock_node)
        assert text1 == text2
        assert (mock_node.start_byte, mock_node.end_byte) in extractor._node_text_cache

    def test_get_node_text_optimized_error_handling(self, extractor):
        """Test node text extraction error handling when content is empty"""
        mock_node = Mock()
        mock_node.start_point = (10, 0)
        mock_node.end_point = (15, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 100
        mock_node.children = []
        mock_node.text = b"function test() {}"

        extractor.content_lines = []

        with patch(
            "tree_sitter_analyzer.languages.typescript_plugin.extract_text_slice",
            side_effect=Exception("Primary error"),
        ):
            text = extractor._get_node_text_optimized(mock_node)
            assert text == ""

    def test_parse_function_signature_optimized(self, extractor):
        """Test function signature parsing with async and generics"""
        mock_node = Mock()
        mock_node.type = "function_declaration"

        identifier = Mock()
        identifier.type = "identifier"
        identifier.text = b"testFunction"

        params = Mock()
        params.type = "formal_parameters"

        type_annotation = Mock()
        type_annotation.type = "type_annotation"

        type_params = Mock()
        type_params.type = "type_parameters"

        mock_node.children = [identifier, params, type_annotation, type_params]

        extractor._get_node_text_optimized = Mock(
            side_effect=lambda n: {
                mock_node: "async function testFunction<T>()",
                type_annotation: ": Promise<T>",
            }.get(n, "")
        )
        extractor._extract_parameters_with_types = Mock(return_value=["param1: string"])
        extractor._extract_generics = Mock(return_value=["T"])

        result = extractor._parse_function_signature_optimized(mock_node)

        assert result is not None
        name, parameters, is_async, is_generator, return_type, generics = result
        assert name == "testFunction"
        assert parameters == ["param1: string"]
        assert is_async is True
        assert is_generator is False
        assert return_type == "Promise<T>"
        assert generics == ["T"]

    def test_parse_method_signature_optimized(self, extractor):
        """Test method signature parsing with visibility, static, and async"""
        mock_node = Mock()

        prop_id = Mock()
        prop_id.type = "property_identifier"
        prop_id.text = b"methodName"

        params = Mock()
        params.type = "formal_parameters"

        type_annotation = Mock()
        type_annotation.type = "type_annotation"

        mock_node.children = [prop_id, params, type_annotation]

        extractor._get_node_text_optimized = Mock(
            side_effect=lambda n: {
                mock_node: "public static async methodName()",
                type_annotation: ": Promise<void>",
            }.get(n, "")
        )
        extractor._extract_parameters_with_types = Mock(return_value=["param: string"])
        extractor._extract_generics = Mock(return_value=[])

        result = extractor._parse_method_signature_optimized(mock_node)

        assert result is not None
        (
            name, parameters, is_async, is_static,
            is_getter, is_setter, is_constructor,
            return_type, visibility, generics,
        ) = result

        assert name == "methodName"
        assert parameters == ["param: string"]
        assert is_async is True
        assert is_static is True
        assert visibility == "public"
        assert return_type == "Promise<void>"

    def test_parse_method_signature_getter_setter(self, extractor):
        """Test getter/setter method signature parsing"""
        mock_node = Mock()
        mock_node.children = []

        extractor._get_node_text_optimized = Mock(return_value="get value()")
        result = extractor._parse_method_signature_optimized(mock_node)
        assert result is not None
        (_, _, _, _, is_getter, is_setter, _, _, _, _) = result
        assert is_getter is True
        assert is_setter is False

        extractor._get_node_text_optimized = Mock(return_value="set value(val: string)")
        result = extractor._parse_method_signature_optimized(mock_node)
        assert result is not None
        (_, _, _, _, is_getter, is_setter, _, _, _, _) = result
        assert is_getter is False
        assert is_setter is True

    def test_extract_parameters_with_types(self, extractor):
        """Test parameter extraction with type annotations"""
        mock_params_node = Mock()

        param1 = Mock()
        param1.type = "required_parameter"
        param1_id = Mock()
        param1_id.type = "identifier"
        param1_id.text = b"param1"
        param1_type = Mock()
        param1_type.type = "type_annotation"
        param1.children = [param1_id, param1_type]

        param2 = Mock()
        param2.type = "optional_parameter"
        param2_id = Mock()
        param2_id.type = "identifier"
        param2_id.text = b"param2"
        param2.children = [param2_id]

        mock_params_node.children = [param1, param2]

        extractor._get_node_text_optimized = Mock(
            side_effect=lambda n: {
                param1_type: ": string",
                param1: "param1: string",
                param2: "param2?",
            }.get(n, "")
        )

        result = extractor._extract_parameters_with_types(mock_params_node)
        assert len(result) == 2
        assert "param1: string" in result
        assert "param2?" in result

    def test_extract_generics(self, extractor):
        """Test generic type parameter extraction"""
        mock_type_params = Mock()

        type_param1 = Mock()
        type_param1.type = "type_parameter"
        type_param2 = Mock()
        type_param2.type = "type_parameter"

        mock_type_params.children = [type_param1, type_param2]

        extractor._get_node_text_optimized = Mock(
            side_effect=lambda n: {
                type_param1: "T",
                type_param2: "U extends string",
            }.get(n, "")
        )

        result = extractor._extract_generics(mock_type_params)
        assert len(result) == 2
        assert "T" in result
        assert "U extends string" in result

    def test_extract_import_info_simple(self, extractor):
        """Test import statement parsing"""
        mock_import_node = Mock()
        mock_import_node.type = "import_statement"
        mock_import_node.start_point = (0, 0)
        mock_import_node.end_point = (0, 30)

        import_clause = Mock()
        import_clause.type = "import_clause"

        string_literal = Mock()
        string_literal.type = "string"
        string_literal.text = b"'./module'"

        mock_import_node.children = [import_clause, string_literal]

        extractor._get_node_text_optimized = Mock(
            side_effect=lambda n: {
                mock_import_node: "import { Component } from './module'",
                import_clause: "{ Component }",
            }.get(n, "")
        )
        extractor._extract_import_names = Mock(return_value=["Component"])

        result = extractor._extract_import_info_simple(mock_import_node)

        assert result is not None
        assert result.module_name == "./module"
        assert result.imported_names == ["Component"]
        assert result.language == "typescript"

    def test_extract_dynamic_import(self, extractor):
        """Test dynamic import() extraction"""
        mock_expr_stmt = Mock()
        mock_expr_stmt.type = "expression_statement"
        mock_expr_stmt.start_point = (10, 0)
        mock_expr_stmt.end_point = (10, 30)

        call_expr = Mock()
        call_expr.type = "call_expression"

        import_id = Mock()
        import_id.type = "import"

        arguments = Mock()
        arguments.type = "arguments"

        string_literal = Mock()
        string_literal.type = "string"
        string_literal.text = b"'./dynamic-module'"

        arguments.children = [string_literal]
        call_expr.children = [import_id, arguments]
        mock_expr_stmt.children = [call_expr]

        extractor._get_node_text_optimized = Mock(
            return_value="import('./dynamic-module')"
        )

        result = extractor._extract_dynamic_import(mock_expr_stmt)

        assert result is not None
        assert result.module_name == "./dynamic-module"
        assert "dynamic_import" in result.imported_names

    def test_extract_tsdoc_for_line(self, extractor):
        """Test TSDoc extraction for a function line"""
        extractor.content_lines = [
            "/**",
            " * This is a TSDoc comment",
            " * @param user The user object",
            " * @returns Promise with result",
            " */",
            "function testFunction(user: User): Promise<Result> {",
            "  return Promise.resolve();",
            "}",
        ]

        result = extractor._extract_tsdoc_for_line(6)
        assert result is not None
        assert "This is a TSDoc comment" in result
        assert "@param user The user object" in result

    def test_extract_arrow_function_optimized_with_parent(self, extractor):
        """Test arrow function extraction with variable declarator parent"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)
        mock_node.children = []

        parent = Mock()
        parent.type = "variable_declarator"
        identifier = Mock()
        identifier.type = "identifier"
        identifier.text = b"myArrowFunc"
        parent.children = [identifier]
        mock_node.parent = parent

        extractor._get_node_text_optimized = Mock(
            side_effect=lambda n: {
                mock_node: "() => 42",
                identifier: "myArrowFunc",
            }.get(n, "")
        )
        extractor._extract_parameters_with_types = Mock(return_value=[])
        extractor._extract_tsdoc_for_line = Mock(return_value=None)
        extractor._calculate_complexity_optimized = Mock(return_value=1)
        extractor.content_lines = ["const myArrowFunc = () => 42;"]

        result = extractor._extract_arrow_function_optimized(mock_node)

        assert result is not None
        assert result.name == "myArrowFunc"
        assert result.is_arrow is True

    def test_extract_class_optimized_with_heritage(self, extractor):
        """Test class extraction with extends and implements"""
        mock_node = Mock()
        mock_node.type = "class_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (10, 0)

        type_id = Mock()
        type_id.type = "type_identifier"
        type_id.text = b"MyClass"

        heritage = Mock()
        heritage.type = "class_heritage"

        type_params = Mock()
        type_params.type = "type_parameters"

        mock_node.children = [type_id, heritage, type_params]

        extractor._get_node_text_optimized = Mock(
            side_effect=lambda n: {
                heritage: "extends BaseClass implements IInterface1, IInterface2",
                mock_node: "class MyClass<T> extends BaseClass implements IInterface1, IInterface2 {}",
            }.get(n, "")
        )
        extractor._extract_generics = Mock(return_value=["T"])
        extractor._extract_tsdoc_for_line = Mock(return_value="Class documentation")
        extractor._is_framework_component = Mock(return_value=False)
        extractor._is_exported_class = Mock(return_value=True)

        result = extractor._extract_class_optimized(mock_node)

        assert result is not None
        assert result.name == "MyClass"
        assert result.superclass == "BaseClass"
        assert "IInterface1" in result.interfaces
        assert "IInterface2" in result.interfaces

    def test_extract_interface_optimized_with_extends(self, extractor):
        """Test interface extraction with extends clause"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (5, 0)

        type_id = Mock()
        type_id.type = "type_identifier"
        type_id.text = b"MyInterface"

        extends_clause = Mock()
        extends_clause.type = "extends_clause"

        mock_node.children = [type_id, extends_clause]

        extractor._get_node_text_optimized = Mock(
            side_effect=lambda n: {
                extends_clause: "extends BaseInterface, OtherInterface",
                mock_node: "interface MyInterface extends BaseInterface, OtherInterface {}",
            }.get(n, "")
        )
        extractor._extract_tsdoc_for_line = Mock(return_value=None)
        extractor._is_exported_class = Mock(return_value=False)

        result = extractor._extract_interface_optimized(mock_node)

        assert result is not None
        assert result.name == "MyInterface"
        assert result.class_type == "interface"
        assert "BaseInterface" in result.interfaces
        assert "OtherInterface" in result.interfaces

    def test_extract_property_optimized_with_modifiers(self, extractor):
        """Test property extraction with visibility modifiers"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (1, 0)

        prop_id = Mock()
        prop_id.type = "property_identifier"

        type_annotation = Mock()
        type_annotation.type = "type_annotation"

        string_value = Mock()
        string_value.type = "string"

        mock_node.children = [prop_id, type_annotation, string_value]

        extractor._get_node_text_optimized = Mock(
            side_effect=lambda n: {
                prop_id: "myProperty",
                type_annotation: ": string",
                string_value: "'default value'",
                mock_node: "private static myProperty: string = 'default value'",
            }.get(n, "")
        )

        result = extractor._extract_property_optimized(mock_node)

        assert result is not None
        assert result.name == "myProperty"
        assert result.variable_type == "string"
        assert result.initializer == "'default value'"
        assert result.is_static is True
        assert result.visibility == "private"


class TestTypeScriptPluginMerged:
    """Merged plugin tests from variant files covering unique code paths."""

    @pytest.fixture
    def plugin(self) -> TypeScriptPlugin:
        """Create a TypeScriptPlugin instance for testing"""
        return TypeScriptPlugin()

    def test_get_tree_sitter_language_exception(self, plugin):
        """Test tree-sitter language getter when loading raises an exception"""
        with patch(
            "tree_sitter_analyzer.languages.typescript_plugin.TREE_SITTER_AVAILABLE",
            True,
        ):
            with patch(
                "tree_sitter_analyzer.languages.typescript_plugin.loader.load_language",
                side_effect=Exception("Load error"),
            ):
                result = plugin.get_tree_sitter_language()
                assert result is None


# ===================================================================
# NEW TESTS: Real tree-sitter parsing for comprehensive coverage
# ===================================================================


class TestTypeScriptRealParsing:
    """Tests using real tree-sitter parsing to cover actual extraction code paths."""

    @pytest.fixture
    def plugin(self) -> TypeScriptPlugin:
        return TypeScriptPlugin()

    @pytest.fixture
    def extractor(self) -> TypeScriptElementExtractor:
        return TypeScriptElementExtractor()

    def _parse(self, plugin, code: str):
        """Helper to parse TypeScript code into a tree-sitter tree."""
        import tree_sitter

        language = plugin.get_tree_sitter_language()
        assert language is not None, "TypeScript language must be available"
        parser = tree_sitter.Parser(language)
        return parser.parse(code.encode("utf-8"))

    def test_extract_function_declaration(self, plugin, extractor):
        code = "function greet(name: string): string {\n  return 'Hello ' + name;\n}"
        tree = self._parse(plugin, code)
        functions = extractor.extract_functions(tree, code)
        assert len(functions) >= 1
        assert functions[0].name == "greet"

    def test_extract_async_function(self, plugin, extractor):
        code = "async function fetchData(url: string): Promise<any> {\n  return fetch(url);\n}"
        tree = self._parse(plugin, code)
        functions = extractor.extract_functions(tree, code)
        assert len(functions) >= 1
        assert functions[0].is_async is True

    def test_extract_arrow_function(self, plugin, extractor):
        code = "const add = (a: number, b: number): number => {\n  return a + b;\n};"
        tree = self._parse(plugin, code)
        functions = extractor.extract_functions(tree, code)
        arrow_fns = [f for f in functions if f.is_arrow]
        assert len(arrow_fns) >= 1

    def test_extract_constructor(self, plugin, extractor):
        code = "class Person {\n  constructor(public name: string) {}\n}"
        tree = self._parse(plugin, code)
        functions = extractor.extract_functions(tree, code)
        constructors = [f for f in functions if f.name == "constructor"]
        assert len(constructors) >= 1

    def test_extract_static_method(self, plugin, extractor):
        code = "class Factory {\n  static create(): Factory {\n    return new Factory();\n  }\n}"
        tree = self._parse(plugin, code)
        functions = extractor.extract_functions(tree, code)
        static_methods = [f for f in functions if f.is_static]
        assert len(static_methods) >= 1

    def test_extract_private_method(self, plugin, extractor):
        code = "class Service {\n  private doWork(): void {}\n}"
        tree = self._parse(plugin, code)
        functions = extractor.extract_functions(tree, code)
        private_methods = [f for f in functions if f.visibility == "private"]
        assert len(private_methods) >= 1

    def test_extract_getter_setter(self, plugin, extractor):
        code = "class Box {\n  private _w: number = 0;\n  get width(): number { return this._w; }\n  set width(v: number) { this._w = v; }\n}"
        tree = self._parse(plugin, code)
        functions = extractor.extract_functions(tree, code)
        names = [f.name for f in functions]
        assert "width" in names

    def test_extract_class_with_extends_and_implements(self, plugin, extractor):
        code = "interface Serializable { serialize(): string; }\nclass Base { id: number = 0; }\nclass Entity extends Base implements Serializable {\n  serialize(): string { return ''; }\n}"
        tree = self._parse(plugin, code)
        classes = extractor.extract_classes(tree, code)
        entity = [c for c in classes if c.name == "Entity"]
        assert len(entity) == 1
        assert entity[0].superclass == "Base"

    def test_extract_abstract_class(self, plugin, extractor):
        code = "abstract class Shape {\n  abstract area(): number;\n}"
        tree = self._parse(plugin, code)
        classes = extractor.extract_classes(tree, code)
        shapes = [c for c in classes if c.name == "Shape"]
        assert len(shapes) >= 1
        assert shapes[0].is_abstract is True

    def test_extract_interface_basic(self, plugin, extractor):
        code = "interface User {\n  id: number;\n  name: string;\n}"
        tree = self._parse(plugin, code)
        classes = extractor.extract_classes(tree, code)
        ifaces = [c for c in classes if c.class_type == "interface"]
        assert len(ifaces) >= 1

    def test_extract_interface_with_extends(self, plugin, extractor):
        code = "interface Base { id: number; }\ninterface Extended extends Base { extra: string; }"
        tree = self._parse(plugin, code)
        classes = extractor.extract_classes(tree, code)
        extended = [c for c in classes if c.name == "Extended"]
        assert len(extended) == 1

    def test_extract_type_alias(self, plugin, extractor):
        code = "type Status = 'active' | 'inactive' | 'pending';"
        tree = self._parse(plugin, code)
        classes = extractor.extract_classes(tree, code)
        type_aliases = [c for c in classes if c.class_type == "type"]
        assert len(type_aliases) >= 1

    def test_extract_enum(self, plugin, extractor):
        code = "enum Direction {\n  Up = 'UP',\n  Down = 'DOWN',\n}"
        tree = self._parse(plugin, code)
        classes = extractor.extract_classes(tree, code)
        enums = [c for c in classes if c.class_type == "enum"]
        assert len(enums) >= 1

    def test_extract_exported_class(self, plugin, extractor):
        code = "export class AppService {\n  run(): void {}\n}"
        tree = self._parse(plugin, code)
        classes = extractor.extract_classes(tree, code)
        exported = [c for c in classes if c.name == "AppService"]
        assert len(exported) >= 1
        assert exported[0].is_exported is True

    def test_extract_const_variable(self, plugin, extractor):
        code = "const MAX_RETRIES: number = 3;"
        tree = self._parse(plugin, code)
        variables = extractor.extract_variables(tree, code)
        consts = [v for v in variables if v.name == "MAX_RETRIES"]
        assert len(consts) >= 1

    def test_extract_let_variable(self, plugin, extractor):
        code = "let count: number = 0;"
        tree = self._parse(plugin, code)
        variables = extractor.extract_variables(tree, code)
        lets = [v for v in variables if v.name == "count"]
        assert len(lets) >= 1

    def test_extract_named_import(self, plugin, extractor):
        code = "import { useState, useEffect } from 'react';"
        tree = self._parse(plugin, code)
        imports = extractor.extract_imports(tree, code)
        assert len(imports) >= 1
        assert imports[0].module_path == "react"

    def test_extract_default_import(self, plugin, extractor):
        code = "import React from 'react';"
        tree = self._parse(plugin, code)
        imports = extractor.extract_imports(tree, code)
        assert len(imports) >= 1

    def test_extract_namespace_import(self, plugin, extractor):
        code = "import * as path from 'path';"
        tree = self._parse(plugin, code)
        imports = extractor.extract_imports(tree, code)
        assert len(imports) >= 1

    def test_extract_commonjs_require(self, plugin, extractor):
        code = "const fs = require('fs');\nconst path = require('path');"
        tree = self._parse(plugin, code)
        imports = extractor.extract_imports(tree, code)
        require_imports = [i for i in imports if i.module_path in ("fs", "path")]
        assert len(require_imports) >= 2

    def test_tsdoc_extraction_for_function(self, plugin, extractor):
        code = "/**\n * Calculates the sum.\n * @param a First\n * @param b Second\n */\nfunction sum(a: number, b: number): number {\n  return a + b;\n}"
        tree = self._parse(plugin, code)
        functions = extractor.extract_functions(tree, code)
        assert len(functions) >= 1
        assert functions[0].docstring is not None

    def test_complexity_complex_function(self, plugin, extractor):
        code = "function process(x: number): string {\n  if (x > 0) {\n    for (let i = 0; i < x; i++) {\n      while (i > 0) { break; }\n    }\n    return x > 5 ? 'medium' : 'small';\n  }\n  return 'none';\n}"
        tree = self._parse(plugin, code)
        functions = extractor.extract_functions(tree, code)
        assert len(functions) >= 1
        assert functions[0].complexity_score > 1

    def test_extract_generator_function(self, plugin, extractor):
        code = "function* counter(): Generator<number> {\n  let i = 0;\n  while (true) { yield i++; }\n}"
        tree = self._parse(plugin, code)
        functions = extractor.extract_functions(tree, code)
        generators = [f for f in functions if f.is_generator]
        assert len(generators) >= 1

    def test_extract_elements_legacy(self, plugin, extractor):
        code = "import { x } from 'mod';\nconst val: number = 10;\nfunction foo(): void {}\nclass Bar {}\n"
        tree = self._parse(plugin, code)
        elements = extractor.extract_elements(tree, code)
        assert len(elements) >= 4

    def test_full_typescript_module(self, plugin, extractor):
        code = "import { EventEmitter } from 'events';\ntype Status = 'active' | 'inactive';\ninterface Disposable { dispose(): void; }\nenum LogLevel { DEBUG = 0, INFO = 1 }\nexport class Logger extends EventEmitter implements Disposable {\n  private level: LogLevel = LogLevel.INFO;\n  constructor(private name: string) { super(); }\n  log(message: string): void { console.log(message); }\n  dispose(): void { this.removeAllListeners(); }\n}\nconst defaultLogger = new Logger('default');\n"
        tree = self._parse(plugin, code)
        func_list = extractor.extract_functions(tree, code)
        classes = extractor.extract_classes(tree, code)
        imports = extractor.extract_imports(tree, code)
        class_names = [c.name for c in classes]
        assert "Logger" in class_names
        assert len(imports) >= 1
        assert len(func_list) >= 1

    def test_rest_parameters(self, plugin, extractor):
        code = "function concat(...parts: string[]): string {\n  return parts.join('');\n}"
        tree = self._parse(plugin, code)
        functions = extractor.extract_functions(tree, code)
        assert len(functions) >= 1

    def test_destructuring_parameters(self, plugin, extractor):
        code = "function printUser({ name, age }: { name: string; age: number }): void {\n  console.log(name, age);\n}"
        tree = self._parse(plugin, code)
        functions = extractor.extract_functions(tree, code)
        assert len(functions) >= 1

    def test_generic_function(self, plugin, extractor):
        code = "function identity<T>(arg: T): T {\n  return arg;\n}"
        tree = self._parse(plugin, code)
        functions = extractor.extract_functions(tree, code)
        assert len(functions) >= 1


class TestTypeScriptExtractorEdgeCases:
    """Edge case tests for specific uncovered branches."""

    @pytest.fixture
    def extractor(self) -> TypeScriptElementExtractor:
        return TypeScriptElementExtractor()

    def test_extract_function_optimized_no_name(self, extractor):
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)
        mock_node.children = []
        extractor.content_lines = ["function () { }"]
        extractor._parse_function_signature_optimized = Mock(return_value=None)
        result = extractor._extract_function_optimized(mock_node)
        assert result is None

    def test_extract_function_optimized_exception(self, extractor):
        mock_node = Mock()
        mock_node.start_point = Mock(side_effect=Exception("error"))
        extractor.content_lines = []
        result = extractor._extract_function_optimized(mock_node)
        assert result is None

    def test_extract_method_optimized_no_info(self, extractor):
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)
        extractor._parse_method_signature_optimized = Mock(return_value=None)
        result = extractor._extract_method_optimized(mock_node)
        assert result is None

    def test_extract_method_optimized_exception(self, extractor):
        mock_node = Mock()
        mock_node.start_point = Mock(side_effect=Exception("error"))
        result = extractor._extract_method_optimized(mock_node)
        assert result is None

    def test_extract_class_optimized_no_name(self, extractor):
        mock_node = Mock()
        mock_node.type = "class_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (5, 0)
        mock_node.children = []
        extractor._get_node_text_optimized = Mock(return_value="class { }")
        result = extractor._extract_class_optimized(mock_node)
        assert result is None

    def test_extract_class_optimized_exception(self, extractor):
        mock_node = Mock()
        mock_node.start_point = Mock(side_effect=Exception("error"))
        result = extractor._extract_class_optimized(mock_node)
        assert result is None

    def test_extract_interface_optimized_no_name(self, extractor):
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (5, 0)
        mock_node.children = []
        extractor._get_node_text_optimized = Mock(return_value="interface { }")
        result = extractor._extract_interface_optimized(mock_node)
        assert result is None

    def test_extract_interface_optimized_exception(self, extractor):
        mock_node = Mock()
        mock_node.start_point = Mock(side_effect=Exception("error"))
        result = extractor._extract_interface_optimized(mock_node)
        assert result is None

    def test_extract_type_alias_optimized_no_name(self, extractor):
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 10)
        mock_node.children = []
        extractor._get_node_text_optimized = Mock(return_value="type = string")
        result = extractor._extract_type_alias_optimized(mock_node)
        assert result is None

    def test_extract_type_alias_optimized_exception(self, extractor):
        mock_node = Mock()
        mock_node.start_point = Mock(side_effect=Exception("error"))
        result = extractor._extract_type_alias_optimized(mock_node)
        assert result is None

    def test_extract_enum_optimized_no_name(self, extractor):
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (3, 0)
        mock_node.children = []
        extractor._get_node_text_optimized = Mock(return_value="enum { A, B }")
        result = extractor._extract_enum_optimized(mock_node)
        assert result is None

    def test_extract_enum_optimized_exception(self, extractor):
        mock_node = Mock()
        mock_node.start_point = Mock(side_effect=Exception("error"))
        result = extractor._extract_enum_optimized(mock_node)
        assert result is None

    def test_extract_generator_function_optimized_exception(self, extractor):
        mock_node = Mock()
        mock_node.start_point = Mock(side_effect=Exception("error"))
        result = extractor._extract_generator_function_optimized(mock_node)
        assert result is None

    def test_extract_import_info_simple_exception(self, extractor):
        mock_node = Mock()
        mock_node.start_point = Mock(side_effect=Exception("error"))
        result = extractor._extract_import_info_simple(mock_node)
        assert result is None

    def test_extract_dynamic_import_no_match(self, extractor):
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 30)
        extractor._get_node_text_optimized = Mock(return_value="console.log('hello')")
        result = extractor._extract_dynamic_import(mock_node)
        assert result is None

    def test_extract_dynamic_import_exception(self, extractor):
        mock_node = Mock()
        extractor._get_node_text_optimized = Mock(side_effect=Exception("error"))
        result = extractor._extract_dynamic_import(mock_node)
        assert result is None

    def test_extract_commonjs_requires_error(self, extractor):
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        extractor._get_node_text_optimized = Mock(side_effect=Exception("error"))
        result = extractor._extract_commonjs_requires(mock_tree, "const x = require('x');")
        assert result == []

    def test_calculate_complexity_exception(self, extractor):
        mock_node = Mock()
        extractor._get_node_text_optimized = Mock(side_effect=Exception("error"))
        result = extractor._calculate_complexity_optimized(mock_node)
        assert result == 1

    def test_extract_tsdoc_for_line_no_content(self, extractor):
        extractor.content_lines = []
        result = extractor._extract_tsdoc_for_line(5)
        assert result is None

    def test_extract_tsdoc_for_line_cache_hit(self, extractor):
        extractor._tsdoc_cache[10] = "Cached"
        result = extractor._extract_tsdoc_for_line(10)
        assert result == "Cached"

    def test_extract_variables_from_declaration_exception(self, extractor):
        mock_node = Mock()
        mock_node.start_point = Mock(side_effect=Exception("error"))
        result = extractor._extract_variables_from_declaration(mock_node, "const")
        assert result == []

    def test_extract_property_optimized_exception(self, extractor):
        mock_node = Mock()
        mock_node.start_point = Mock(side_effect=Exception("error"))
        result = extractor._extract_property_optimized(mock_node)
        assert result is None

    def test_extract_property_signature_optimized_exception(self, extractor):
        mock_node = Mock()
        mock_node.start_point = Mock(side_effect=Exception("error"))
        result = extractor._extract_property_signature_optimized(mock_node)
        assert result is None

    def test_traverse_with_none_root(self, extractor):
        results = []
        extractor._traverse_and_extract_iterative(None, {}, results, "function")
        assert results == []


# ====================================================================== #
# TARGETED TESTS for coverage boost (79.7% -> 80%+)
# ====================================================================== #


class TestTypeScriptFallbackBranches:
    """Tests targeting specific uncovered fallback/exception branches."""

    @pytest.fixture
    def extractor(self) -> TypeScriptElementExtractor:
        return TypeScriptElementExtractor()

    def test_get_node_text_fallback_multiline(self, extractor):
        """Cover lines 308-319: fallback multiline text extraction"""
        node = Mock()
        node.start_byte = 0
        node.end_byte = 30
        node.start_point = (0, 5)
        node.end_point = (2, 3)

        extractor.content_lines = ["Hello World!", "Middle line", "End text"]

        with patch(
            "tree_sitter_analyzer.languages.typescript_plugin.extract_text_slice",
            side_effect=Exception("primary error"),
        ):
            result = extractor._get_node_text_optimized(node)
            assert "World!" in result
            assert "Middle line" in result
            assert "End" in result

    def test_get_node_text_fallback_single_line(self, extractor):
        """Cover lines 305-307: fallback single-line text extraction"""
        node = Mock()
        node.start_byte = 0
        node.end_byte = 10
        node.start_point = (0, 2)
        node.end_point = (0, 7)

        extractor.content_lines = ["Hello World!"]

        with patch(
            "tree_sitter_analyzer.languages.typescript_plugin.extract_text_slice",
            side_effect=Exception("primary error"),
        ):
            result = extractor._get_node_text_optimized(node)
            assert result == "llo W"

    def test_get_node_text_both_fallbacks_fail(self, extractor):
        """Cover lines 320-322: both primary and fallback fail"""
        node = Mock()
        node.start_byte = 0
        node.end_byte = 10
        type(node).start_point = property(
            lambda self: (_ for _ in ()).throw(Exception("bad"))
        )

        extractor.content_lines = ["test"]

        with patch(
            "tree_sitter_analyzer.languages.typescript_plugin.extract_text_slice",
            side_effect=Exception("primary error"),
        ):
            result = extractor._get_node_text_optimized(node)
            assert result == ""

    def test_extract_function_name_none(self, extractor):
        """Cover line 341: function signature returns name=None"""
        node = Mock()
        node.start_point = (0, 0)
        node.end_point = (2, 0)
        extractor.content_lines = ["function () {}"]
        extractor._parse_function_signature_optimized = Mock(
            return_value=(None, [], False, False, None, [])
        )
        result = extractor._extract_function_optimized(node)
        assert result is None

    def test_extract_arrow_function_type_annotation(self, extractor):
        """Cover lines 406-409: arrow function with type_annotation child"""
        node = Mock()
        node.start_point = (0, 0)
        node.end_point = (0, 30)
        node.children = []

        parent = Mock()
        parent.type = "variable_declarator"
        id_node = Mock()
        id_node.type = "identifier"
        parent.children = [id_node]
        node.parent = parent

        type_ann = Mock()
        type_ann.type = "type_annotation"
        formal_params = Mock()
        formal_params.type = "formal_parameters"
        node.children = [formal_params, type_ann]

        extractor._get_node_text_optimized = Mock(
            side_effect=lambda n: {
                node: "const fn = (x: number): string => x.toString()",
                id_node: "fn",
                type_ann: ": string",
            }.get(n, "")
        )
        extractor._extract_parameters_with_types = Mock(return_value=["x: number"])
        extractor._extract_tsdoc_for_line = Mock(return_value=None)
        extractor._calculate_complexity_optimized = Mock(return_value=1)
        extractor.content_lines = ["const fn = (x: number): string => x.toString()"]

        result = extractor._extract_arrow_function_optimized(node)
        assert result is not None
        assert result.return_type == "string"

    def test_extract_method_name_none_with_regex_fallback(self, extractor):
        """Cover lines 1098-1109: method name None falls back to regex"""
        node = Mock()
        node.start_point = (0, 0)
        node.end_point = (2, 0)
        node.children = []

        extractor._get_node_text_optimized = Mock(
            return_value="public async myMethod(param: string)"
        )
        extractor._extract_parameters_with_types = Mock(return_value=[])
        extractor._extract_generics = Mock(return_value=[])

        result = extractor._parse_method_signature_optimized(node)
        assert result is not None
        name = result[0]
        assert name == "myMethod"

    def test_extract_method_signature_constructor(self, extractor):
        """Cover line 1113: constructor detection after name determined"""
        node = Mock()
        prop_id = Mock()
        prop_id.type = "property_identifier"
        node.children = [prop_id]

        extractor._get_node_text_optimized = Mock(
            side_effect=lambda n: {
                node: "constructor()",
                prop_id: "constructor",
            }.get(n, "")
        )
        extractor._extract_parameters_with_types = Mock(return_value=[])
        extractor._extract_generics = Mock(return_value=[])

        result = extractor._parse_method_signature_optimized(node)
        assert result is not None
        is_constructor = result[6]
        assert is_constructor is True

    def test_extract_method_signature_protected_visibility(self, extractor):
        """Cover line 1078: protected visibility"""
        node = Mock()
        node.children = []
        extractor._get_node_text_optimized = Mock(
            return_value="protected doWork()"
        )
        extractor._extract_parameters_with_types = Mock(return_value=[])
        extractor._extract_generics = Mock(return_value=[])

        result = extractor._parse_method_signature_optimized(node)
        assert result is not None
        visibility = result[8]
        assert visibility == "protected"

    def test_extract_method_optimized_name_none(self, extractor):
        """Cover line 471: method info returns name=None"""
        node = Mock()
        node.start_point = (0, 0)
        node.end_point = (2, 0)
        extractor._parse_method_signature_optimized = Mock(
            return_value=(None, [], False, False, False, False, False, None, "public", [])
        )
        result = extractor._extract_method_optimized(node)
        assert result is None

    def test_extract_method_signature_optimized_name_none(self, extractor):
        """Cover line 533: method_signature returns name=None"""
        node = Mock()
        node.start_point = (0, 0)
        node.end_point = (2, 0)
        extractor._parse_method_signature_optimized = Mock(
            return_value=(None, [], False, False, False, False, False, None, "public", [])
        )
        result = extractor._extract_method_signature_optimized(node)
        assert result is None

    def test_extract_generator_function_name_none(self, extractor):
        """Cover line 579: generator function with name=None"""
        node = Mock()
        node.start_point = (0, 0)
        node.end_point = (2, 0)
        extractor._parse_function_signature_optimized = Mock(
            return_value=(None, [], False, True, None, [])
        )
        result = extractor._extract_generator_function_optimized(node)
        assert result is None

    def test_tsdoc_single_line(self, extractor):
        """Cover lines 1556-1560: single-line TSDoc comment"""
        extractor.content_lines = [
            "/** Single line doc */",
            "function test(): void {}",
        ]
        result = extractor._extract_tsdoc_for_line(2)
        assert result is not None
        assert "Single line doc" in result

    def test_tsdoc_no_comment_before(self, extractor):
        """Cover lines 1580-1581: no comment found, caches empty string"""
        extractor.content_lines = [
            "const x = 1;",
            "function test(): void {}",
        ]
        result = extractor._extract_tsdoc_for_line(2)
        assert result is None
        assert extractor._tsdoc_cache[2] == ""

    def test_extract_property_signature_no_name(self, extractor):
        """Cover line 911: property signature with no property_identifier"""
        node = Mock()
        node.start_point = (0, 0)
        node.end_point = (0, 10)
        node.children = []  # No children
        extractor._get_node_text_optimized = Mock(return_value="string")
        result = extractor._extract_property_signature_optimized(node)
        assert result is None

    def test_extract_property_no_name(self, extractor):
        """Cover line 864: property without property_identifier child"""
        node = Mock()
        node.start_point = (0, 0)
        node.end_point = (0, 10)
        node.children = []  # No property_identifier
        extractor._get_node_text_optimized = Mock(return_value="value")
        result = extractor._extract_property_optimized(node)
        assert result is None

    def test_is_framework_component_not_react(self, extractor):
        """Cover line 1495: framework_type that is not react/angular/vue"""
        extractor.framework_type = "svelte"
        node = Mock()
        assert extractor._is_framework_component(node, "MyComp") is False

    def test_extract_dynamic_import_alternative_pattern(self, extractor):
        """Cover lines 1411-1414: dynamic import with alternative pattern"""
        node = Mock()
        node.start_point = (0, 0)
        node.end_point = (0, 30)
        extractor._get_node_text_optimized = Mock(
            return_value="import(variable)"
        )
        result = extractor._extract_dynamic_import(node)
        assert result is not None
        assert result.module_path == "variable"

    def test_parse_variable_declarator_skip_arrow_function(self, extractor):
        """Cover lines 980-982: variable declarator that contains arrow_function"""
        node = Mock()
        node.type = "variable_declarator"

        identifier = Mock()
        identifier.type = "identifier"
        arrow = Mock()
        arrow.type = "arrow_function"
        node.children = [identifier, arrow]

        extractor._get_node_text_optimized = Mock(
            side_effect=lambda n: {
                identifier: "myFunc",
                node: "myFunc = () => {}",
            }.get(n, "")
        )
        extractor._extract_tsdoc_for_line = Mock(return_value=None)
        extractor.content_lines = ["const myFunc = () => {}"]

        result = extractor._parse_variable_declarator(node, "const", 1, 1)
        assert result is None

    def test_parse_variable_declarator_no_name(self, extractor):
        """Cover line 976: variable declarator with no identifier"""
        node = Mock()
        node.children = []
        extractor._get_node_text_optimized = Mock(return_value="")
        result = extractor._parse_variable_declarator(node, "const", 1, 1)
        assert result is None


class TestTypeScriptPluginExtractMethods:
    """Tests for plugin-level extract methods."""

    @pytest.fixture
    def plugin(self) -> TypeScriptPlugin:
        return TypeScriptPlugin()

    def test_extract_elements_legacy(self, plugin):
        """Cover lines 1829-1838: plugin.extract_elements creates new extractor"""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []
        mock_extractor = Mock()
        mock_extractor.extract_functions.return_value = []
        mock_extractor.extract_classes.return_value = []
        mock_extractor.extract_variables.return_value = []
        mock_extractor.extract_imports.return_value = []

        with patch.object(plugin, "create_extractor", return_value=mock_extractor):
            elements = plugin.extract_elements(mock_tree, "")
            assert elements == []
            mock_extractor.extract_functions.assert_called_once()
            mock_extractor.extract_classes.assert_called_once()
            mock_extractor.extract_variables.assert_called_once()
            mock_extractor.extract_imports.assert_called_once()

    def test_execute_query_strategy(self, plugin):
        """Cover lines 1844-1845: execute_query_strategy"""
        result = plugin.execute_query_strategy(None, "typescript")
        assert result is None

        result = plugin.execute_query_strategy("function", "typescript")
        # Should return None or a query string from get_queries()
        assert result is None or isinstance(result, str)

    def test_get_element_categories(self, plugin):
        """Cover lines 1847-1893: get_element_categories"""
        cats = plugin.get_element_categories()
        assert isinstance(cats, dict)
        assert "function" in cats
        assert "class" in cats
        assert "interface" in cats
        assert "enum" in cats
        assert "variable" in cats
        assert "import" in cats
        assert "export" in cats
        assert "react_component" in cats

    def test_get_tree_sitter_language_not_available(self, plugin):
        """Cover lines 1686-1687: TREE_SITTER_AVAILABLE is False"""
        with patch(
            "tree_sitter_analyzer.languages.typescript_plugin.TREE_SITTER_AVAILABLE",
            False,
        ):
            plugin._language = None
            result = plugin.get_tree_sitter_language()
            assert result is None


if __name__ == "__main__":
    pytest.main([__file__])
