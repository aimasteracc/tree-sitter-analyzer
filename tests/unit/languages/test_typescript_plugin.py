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
        assert isinstance(extractor, TypeScriptElementExtractor)
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
        assert isinstance(extractor, ElementExtractor)

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
        from tree_sitter_analyzer.formatters.formatter_factory import (
            TableFormatterFactory,
        )

        # Test that TypeScript formatter can be created
        formatter = TableFormatterFactory.create_formatter("typescript", "full")
        assert formatter is not None

        # Test alias
        formatter_alias = TableFormatterFactory.create_formatter("ts", "full")
        assert formatter_alias is not None

        # Test supported languages includes TypeScript
        supported = TableFormatterFactory.get_supported_languages()
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


if __name__ == "__main__":
    pytest.main([__file__])
