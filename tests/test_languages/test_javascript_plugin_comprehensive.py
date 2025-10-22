"""
Comprehensive tests for JavaScript plugin.
Tests all major functionality including functions, classes, variables, imports,
caching, performance optimizations, and JavaScript-specific features.
"""

from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.languages.javascript_plugin import JavaScriptElementExtractor
from tree_sitter_analyzer.models import Class, Function, Import


class TestJavaScriptElementExtractor:
    """Test JavaScript element extractor functionality"""

    @pytest.fixture
    def extractor(self):
        """Create a JavaScript element extractor instance"""
        return JavaScriptElementExtractor()

    @pytest.fixture
    def mock_tree(self):
        """Create a mock tree-sitter tree"""
        tree = Mock()
        tree.root_node = Mock()
        tree.language = Mock()
        return tree

    @pytest.fixture
    def sample_javascript_code(self):
        """Sample JavaScript code for testing"""
        return """
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { debounce } from 'lodash';

/**
 * User management component
 * @class UserManager
 * @extends React.Component
 */
class UserManager extends React.Component {
    /**
     * Constructor for UserManager
     * @param {Object} props - Component props
     */
    constructor(props) {
        super(props);
        this.state = {
            users: [],
            loading: false,
            error: null
        };
    }

    /**
     * Component did mount lifecycle method
     */
    componentDidMount() {
        this.loadUsers();
    }

    /**
     * Load users from API
     * @async
     * @returns {Promise<void>}
     */
    async loadUsers() {
        this.setState({ loading: true, error: null });
        try {
            const response = await axios.get('/api/users');
            this.setState({ users: response.data, loading: false });
        } catch (error) {
            this.setState({ error: error.message, loading: false });
        }
    }

    /**
     * Static method to validate user data
     * @static
     * @param {Object} userData - User data to validate
     * @returns {boolean} True if valid
     */
    static validateUser(userData) {
        return userData && userData.name && userData.email;
    }

    /**
     * Get user display name
     * @param {Object} user - User object
     * @returns {string} Display name
     */
    getUserDisplayName = (user) => {
        return `${user.firstName} ${user.lastName}`;
    }

    /**
     * Render method
     * @returns {JSX.Element}
     */
    render() {
        const { users, loading, error } = this.state;

        if (loading) return <div>Loading...</div>;
        if (error) return <div>Error: {error}</div>;

        return (
            <div className="user-manager">
                {users.map(user => (
                    <UserCard
                        key={user.id}
                        user={user}
                        displayName={this.getUserDisplayName(user)}
                    />
                ))}
            </div>
        );
    }
}

/**
 * Functional component for user card
 * @param {Object} props - Component props
 * @returns {JSX.Element}
 */
const UserCard = ({ user, displayName }) => {
    const [expanded, setExpanded] = useState(false);

    useEffect(() => {
        console.log(`UserCard for ${displayName} mounted`);
    }, [displayName]);

    const toggleExpanded = () => setExpanded(!expanded);

    return (
        <div className={`user-card ${expanded ? 'expanded' : ''}`}>
            <h3 onClick={toggleExpanded}>{displayName}</h3>
            {expanded && (
                <div className="user-details">
                    <p>Email: {user.email}</p>
                    <p>Phone: {user.phone}</p>
                </div>
            )}
        </div>
    );
};

// Utility functions
const formatDate = (date) => {
    return new Date(date).toLocaleDateString();
};

const debounceSearch = debounce((query) => {
    console.log(`Searching for: ${query}`);
}, 300);

// Generator function
function* userGenerator(users) {
    for (const user of users) {
        yield user;
    }
}

// Async generator
async function* asyncUserGenerator(userIds) {
    for (const id of userIds) {
        const user = await fetchUser(id);
        yield user;
    }
}

// Arrow function with async
const fetchUser = async (id) => {
    const response = await axios.get(`/api/users/${id}`);
    return response.data;
};

// Constants and variables
const API_BASE_URL = 'https://api.example.com';
let currentUser = null;
var globalConfig = {
    theme: 'dark',
    language: 'en'
};

// Export statements
export default UserManager;
export { UserCard, formatDate, debounceSearch };
export const API_ENDPOINTS = {
    users: '/api/users',
    profile: '/api/profile'
};
"""

    def test_initialization(self, extractor):
        """Test extractor initialization"""
        assert extractor.current_file == ""
        assert extractor.source_code == ""
        assert extractor.content_lines == []
        assert extractor.imports == []
        assert extractor.exports == []
        assert isinstance(extractor._node_text_cache, dict)
        assert isinstance(extractor._processed_nodes, set)
        assert isinstance(extractor._element_cache, dict)
        assert extractor._file_encoding is None
        assert isinstance(extractor._jsdoc_cache, dict)
        assert isinstance(extractor._complexity_cache, dict)
        assert extractor.is_module is False
        assert extractor.is_jsx is False
        assert extractor.framework_type == ""

    def test_reset_caches(self, extractor):
        """Test cache reset functionality"""
        # Populate caches
        extractor._node_text_cache[1] = "test"
        extractor._processed_nodes.add(1)
        extractor._element_cache[(1, "test")] = "value"
        extractor._jsdoc_cache[1] = "doc"
        extractor._complexity_cache[1] = 5

        # Reset caches
        extractor._reset_caches()

        # Verify caches are empty
        assert len(extractor._node_text_cache) == 0
        assert len(extractor._processed_nodes) == 0
        assert len(extractor._element_cache) == 0
        assert len(extractor._jsdoc_cache) == 0
        assert len(extractor._complexity_cache) == 0

    def test_detect_file_characteristics(self, extractor, sample_javascript_code):
        """Test file characteristics detection"""
        extractor.source_code = sample_javascript_code
        extractor.current_file = "UserManager.jsx"
        extractor._detect_file_characteristics()

        # Should detect as module due to imports/exports
        assert extractor.is_module is True

        # Should detect JSX
        assert extractor.is_jsx is True

        # Should detect React framework
        assert extractor.framework_type == "react"

        # Test Vue detection
        vue_code = "import Vue from 'vue'; export default { name: 'Component' }"
        extractor.source_code = vue_code
        extractor._detect_file_characteristics()
        assert extractor.framework_type == "vue"

        # Test Angular detection
        angular_code = "import { Component } from '@angular/core';"
        extractor.source_code = angular_code
        extractor._detect_file_characteristics()
        assert extractor.framework_type == "angular"

    def test_extract_functions_basic(
        self, extractor, mock_tree, sample_javascript_code
    ):
        """Test basic function extraction"""
        # Mock tree structure for function extraction
        mock_function_node = Mock()
        mock_function_node.type = "function_declaration"
        mock_function_node.start_point = (10, 0)
        mock_function_node.end_point = (15, 0)
        mock_function_node.start_byte = 100
        mock_function_node.end_byte = 200
        mock_function_node.children = []

        mock_tree.root_node.children = [mock_function_node]

        # Mock the extraction method
        with patch.object(
            extractor, "_traverse_and_extract_iterative"
        ) as mock_traverse:
            functions = extractor.extract_functions(mock_tree, sample_javascript_code)

            # Verify traversal was called
            mock_traverse.assert_called_once()
            assert isinstance(functions, list)

    def test_extract_classes_basic(self, extractor, mock_tree, sample_javascript_code):
        """Test basic class extraction"""
        # Mock tree structure for class extraction
        mock_class_node = Mock()
        mock_class_node.type = "class_declaration"
        mock_class_node.start_point = (5, 0)
        mock_class_node.end_point = (25, 0)
        mock_class_node.start_byte = 50
        mock_class_node.end_byte = 300
        mock_class_node.children = []

        mock_tree.root_node.children = [mock_class_node]

        # Mock the extraction method
        with patch.object(
            extractor, "_traverse_and_extract_iterative"
        ) as mock_traverse:
            classes = extractor.extract_classes(mock_tree, sample_javascript_code)

            # Verify traversal was called
            mock_traverse.assert_called_once()
            assert isinstance(classes, list)

    def test_extract_variables_basic(
        self, extractor, mock_tree, sample_javascript_code
    ):
        """Test basic variable extraction"""
        # Mock tree structure for variable extraction
        mock_var_node = Mock()
        mock_var_node.type = "variable_declaration"
        mock_var_node.start_point = (1, 0)
        mock_var_node.end_point = (1, 20)
        mock_var_node.children = []

        mock_tree.root_node.children = [mock_var_node]

        # Mock the extraction method
        with patch.object(
            extractor, "_traverse_and_extract_iterative"
        ) as mock_traverse:
            variables = extractor.extract_variables(mock_tree, sample_javascript_code)

            # Verify traversal was called
            mock_traverse.assert_called_once()
            assert isinstance(variables, list)

    def test_extract_imports_basic(self, extractor, mock_tree, sample_javascript_code):
        """Test basic import extraction"""
        # Mock import statement
        mock_import_node = Mock()
        mock_import_node.type = "import_statement"

        mock_tree.root_node.children = [mock_import_node]

        with patch.object(extractor, "_extract_import_info_simple") as mock_extract:
            mock_import = Import(
                name="react",
                start_line=1,
                end_line=1,
                raw_text="import React from 'react'",
                language="javascript",
            )
            mock_extract.return_value = mock_import

            imports = extractor.extract_imports(mock_tree, sample_javascript_code)

            assert isinstance(imports, list)
            mock_extract.assert_called_once()

    def test_extract_exports_basic(self, extractor, mock_tree, sample_javascript_code):
        """Test basic export extraction"""
        # Mock export statement
        mock_export_node = Mock()
        mock_export_node.type = "export_statement"

        mock_tree.root_node.children = [mock_export_node]

        with patch.object(extractor, "_extract_export_info") as mock_extract:
            mock_export = {"name": "UserManager", "is_default": True}
            mock_extract.return_value = mock_export

            with patch.object(extractor, "_extract_commonjs_exports") as mock_commonjs:
                mock_commonjs.return_value = []

                exports = extractor.extract_exports(mock_tree, sample_javascript_code)

                assert isinstance(exports, list)
                mock_extract.assert_called_once()

    def test_get_node_text_optimized_caching(self, extractor):
        """Test node text extraction with caching"""
        # Create mock node
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 10
        node_id = id(mock_node)

        # Set up extractor state
        extractor.content_lines = ["test content line"]
        extractor._file_encoding = "utf-8"

        # Mock extract_text_slice to return test text
        with patch(
            "tree_sitter_analyzer.languages.javascript_plugin.extract_text_slice"
        ) as mock_extract:
            mock_extract.return_value = "test text"

            # First call should extract and cache
            result1 = extractor._get_node_text_optimized(mock_node)
            assert result1 == "test text"
            assert node_id in extractor._node_text_cache

            # Second call should use cache
            result2 = extractor._get_node_text_optimized(mock_node)
            assert result2 == "test text"
            assert mock_extract.call_count == 1  # Should only be called once

    def test_get_node_text_optimized_fallback(self, extractor):
        """Test node text extraction fallback mechanism"""
        # Create mock node
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 10
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 10)

        # Set up extractor state
        extractor.content_lines = ["test content line"]
        extractor._file_encoding = "utf-8"

        # Mock extract_text_slice to raise exception
        with patch(
            "tree_sitter_analyzer.languages.javascript_plugin.extract_text_slice"
        ) as mock_extract:
            mock_extract.side_effect = Exception("Test error")

            # Should fallback to simple extraction
            result = extractor._get_node_text_optimized(mock_node)
            assert result == "test conte"  # Characters 0-10 from first line

    def test_extract_function_optimized_complete(self, extractor):
        """Test complete function extraction"""
        # Create mock function node
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (5, 0)

        # Set up extractor state
        extractor.content_lines = [
            "/**",
            " * Test function",
            " */",
            "async function testFunction(param1, param2) {",
            "    return param1 + param2;",
            "}",
        ]
        extractor.framework_type = "react"

        # Mock helper methods
        with patch.object(
            extractor, "_parse_function_signature_optimized"
        ) as mock_parse:
            mock_parse.return_value = (
                "testFunction",
                ["param1", "param2"],
                True,
                False,
            )

            with patch.object(extractor, "_extract_jsdoc_for_line") as mock_jsdoc:
                mock_jsdoc.return_value = "Test function"

                with patch.object(
                    extractor, "_calculate_complexity_optimized"
                ) as mock_complexity:
                    mock_complexity.return_value = 2

                    result = extractor._extract_function_optimized(mock_node)

                    assert isinstance(result, Function)
                    assert result.name == "testFunction"
                    assert result.start_line == 1
                    assert result.end_line == 6
                    assert result.language == "javascript"
                    assert result.parameters == ["param1", "param2"]
                    assert result.return_type == "unknown"
                    assert result.is_async is True
                    assert result.is_generator is False
                    assert result.docstring == "Test function"
                    assert result.complexity_score == 2
                    assert result.is_arrow is False
                    assert result.is_method is False
                    assert result.framework_type == "react"

    def test_extract_arrow_function_optimized(self, extractor):
        """Test arrow function extraction"""
        # Create mock arrow function node
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)

        # Mock parent variable declarator
        mock_parent = Mock()
        mock_parent.type = "variable_declarator"
        mock_identifier = Mock()
        mock_identifier.type = "identifier"
        mock_parent.children = [mock_identifier]
        mock_node.parent = mock_parent

        # Mock formal parameters
        mock_params = Mock()
        mock_params.type = "formal_parameters"
        mock_node.children = [mock_params]

        extractor.content_lines = [
            "const arrowFunc = async (param1, param2) => {",
            "    return param1 * param2;",
            "};",
        ]

        with patch.object(extractor, "_get_node_text_optimized") as mock_get_text:
            mock_get_text.side_effect = [
                "arrowFunc",  # identifier text
                "async (param1, param2) => { return param1 * param2; }",  # full function text
                "async (param1, param2) => { return param1 * param2; }",  # for async check
            ]

            with patch.object(extractor, "_extract_parameters") as mock_extract_params:
                mock_extract_params.return_value = ["param1", "param2"]

                with patch.object(extractor, "_extract_jsdoc_for_line") as mock_jsdoc:
                    mock_jsdoc.return_value = None

                    with patch.object(
                        extractor, "_calculate_complexity_optimized"
                    ) as mock_complexity:
                        mock_complexity.return_value = 1

                        result = extractor._extract_arrow_function_optimized(mock_node)

                        assert isinstance(result, Function)
                        assert result.name == "arrowFunc"
                        assert result.is_arrow is True
                        assert result.is_async is True
                        assert result.parameters == ["param1", "param2"]

    def test_extract_method_optimized(self, extractor):
        """Test method extraction"""
        # Create mock method node
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (3, 0)

        extractor.content_lines = [
            "static async validateUser(userData) {",
            "    return userData && userData.name;",
            "}",
        ]

        with patch.object(extractor, "_parse_method_signature_optimized") as mock_parse:
            mock_parse.return_value = (
                "validateUser",
                ["userData"],
                True,
                True,
                False,
                False,
                False,
            )

            with patch.object(extractor, "_extract_jsdoc_for_line") as mock_jsdoc:
                mock_jsdoc.return_value = "Validate user data"

                with patch.object(
                    extractor, "_calculate_complexity_optimized"
                ) as mock_complexity:
                    mock_complexity.return_value = 2

                    with patch.object(
                        extractor, "_get_node_text_optimized"
                    ) as mock_get_text:
                        mock_get_text.return_value = "static async validateUser(userData) { return userData && userData.name; }"

                        result = extractor._extract_method_optimized(mock_node)

                        assert isinstance(result, Function)
                        assert result.name == "validateUser"
                        assert result.is_method is True
                        assert result.is_static is True
                        assert result.is_async is True
                        assert result.is_constructor is False

    def test_extract_generator_function_optimized(self, extractor):
        """Test generator function extraction"""
        # Create mock generator function node
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (4, 0)

        extractor.content_lines = [
            "function* userGenerator(users) {",
            "    for (const user of users) {",
            "        yield user;",
            "    }",
            "}",
        ]

        with patch.object(
            extractor, "_parse_function_signature_optimized"
        ) as mock_parse:
            mock_parse.return_value = ("userGenerator", ["users"], False, True)

            with patch.object(extractor, "_extract_jsdoc_for_line") as mock_jsdoc:
                mock_jsdoc.return_value = "Generate users"

                with patch.object(
                    extractor, "_calculate_complexity_optimized"
                ) as mock_complexity:
                    mock_complexity.return_value = 2

                    with patch.object(
                        extractor, "_get_node_text_optimized"
                    ) as mock_get_text:
                        mock_get_text.return_value = "function* userGenerator(users) { for (const user of users) { yield user; } }"

                        result = extractor._extract_generator_function_optimized(
                            mock_node
                        )

                        assert isinstance(result, Function)
                        assert result.name == "userGenerator"
                        assert result.is_generator is True
                        assert result.return_type == "Generator"
                        assert result.parameters == ["users"]

    def test_extract_class_optimized_complete(self, extractor):
        """Test complete class extraction"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (10, 0)

        # Mock identifier child
        mock_identifier = Mock()
        mock_identifier.type = "identifier"
        mock_identifier.text = b"UserManager"

        # Mock class heritage (extends clause)
        mock_heritage = Mock()
        mock_heritage.type = "class_heritage"

        mock_node.children = [mock_identifier, mock_heritage]

        extractor.content_lines = [
            "/**",
            " * User management class",
            " */",
            "class UserManager extends React.Component {",
            "    constructor(props) {",
            "        super(props);",
            "    }",
            "}",
        ] * 2
        extractor.framework_type = "react"

        with patch.object(extractor, "_get_node_text_optimized") as mock_get_text:
            mock_get_text.side_effect = [
                "extends React.Component",  # Heritage text
                "class UserManager extends React.Component { constructor(props) { super(props); } }",  # Full class text
            ]

            with patch.object(extractor, "_extract_jsdoc_for_line") as mock_jsdoc:
                mock_jsdoc.return_value = "User management class"

                with patch.object(extractor, "_is_react_component") as mock_is_react:
                    mock_is_react.return_value = True

                    with patch.object(
                        extractor, "_is_exported_class"
                    ) as mock_is_exported:
                        mock_is_exported.return_value = True

                        result = extractor._extract_class_optimized(mock_node)

                        assert isinstance(result, Class)
                        assert result.name == "UserManager"
                        assert result.start_line == 1
                        assert result.end_line == 11
                        assert result.language == "javascript"
                        assert result.class_type == "class"
                        assert result.superclass == "React.Component"
                        assert result.docstring == "User management class"
                        assert result.is_react_component is True
                        assert result.framework_type == "react"
                        assert result.is_exported is True

    def test_traverse_and_extract_iterative(self, extractor):
        """Test iterative traversal and extraction"""
        # Create mock root node with children
        mock_root = Mock()
        mock_child1 = Mock()
        mock_child1.type = "function_declaration"
        mock_child1.children = []

        mock_child2 = Mock()
        mock_child2.type = "class_declaration"
        mock_child2.children = []

        mock_root.children = [mock_child1, mock_child2]

        # Mock extractor functions
        mock_func_extractor = Mock()
        mock_func_extractor.return_value = Function(
            name="test_func",
            start_line=1,
            end_line=3,
            raw_text="function test_func() {}",
            language="javascript",
        )

        mock_class_extractor = Mock()
        mock_class_extractor.return_value = Class(
            name="TestClass",
            start_line=5,
            end_line=10,
            raw_text="class TestClass {}",
            language="javascript",
        )

        extractors = {
            "function_declaration": mock_func_extractor,
            "class_declaration": mock_class_extractor,
        }

        results = []
        extractor._traverse_and_extract_iterative(
            mock_root, extractors, results, "mixed"
        )

        assert len(results) == 2
        assert isinstance(results[0], Function)
        assert isinstance(results[1], Class)

    def test_traverse_and_extract_iterative_with_caching(self, extractor):
        """Test iterative traversal with caching"""
        mock_root = Mock()
        mock_child = Mock()
        mock_child.type = "function_declaration"
        mock_child.children = []
        mock_root.children = [mock_child]

        # Set up cache
        node_id = id(mock_child)
        cache_key = (node_id, "function")
        cached_function = Function(
            name="cached_func",
            start_line=1,
            end_line=2,
            raw_text="function cached_func() {}",
            language="javascript",
        )
        extractor._element_cache[cache_key] = cached_function

        extractors = {"function_declaration": Mock()}
        results = []

        extractor._traverse_and_extract_iterative(
            mock_root, extractors, results, "function"
        )

        # Should use cached result
        assert len(results) == 1
        assert results[0] == cached_function
        assert (
            extractors["function_declaration"].call_count == 0
        )  # Should not call extractor

    def test_traverse_and_extract_iterative_max_depth(self, extractor):
        """Test max depth protection in traversal"""
        # Create deeply nested structure
        root_node = Mock()
        root_node.type = "program"
        root_node.children = []

        current_node = root_node

        # Create 60 levels of nesting (exceeds max_depth of 50)
        for _i in range(60):
            child = Mock()
            child.type = "statement_block"
            child.children = []
            current_node.children = [child]
            current_node = child

        # Add target node at the end
        target_node = Mock()
        target_node.type = "function_declaration"
        target_node.children = []
        current_node.children = [target_node]

        extractors = {"function_declaration": Mock()}
        results = []

        # Should not process deeply nested nodes
        with patch(
            "tree_sitter_analyzer.languages.javascript_plugin.log_warning"
        ) as mock_log:
            extractor._traverse_and_extract_iterative(
                root_node, extractors, results, "function"
            )

            # Should log warning about max depth
            mock_log.assert_called()

    def test_performance_with_large_codebase(self, extractor):
        """Test performance with large codebase simulation"""
        import time

        # Create large mock tree
        mock_tree = Mock()
        mock_root = Mock()
        mock_tree.root_node = mock_root

        # Create many function nodes
        function_nodes = []
        for i in range(100):
            node = Mock()
            node.type = "function_declaration"
            node.children = []
            node.start_point = (i, 0)
            node.end_point = (i + 2, 0)
            function_nodes.append(node)

        mock_root.children = function_nodes

        # Create large source code
        large_source = "\n".join(
            [f"function func_{i}() {{ return {i}; }}" for i in range(100)]
        )

        # Mock extraction method to return simple functions
        def mock_extract_function(node):
            return Function(
                name=f"func_{node.start_point[0]}",
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=f"function func_{node.start_point[0]}() {{ return {node.start_point[0]}; }}",
                language="javascript",
            )

        with patch.object(
            extractor, "_extract_function_optimized", side_effect=mock_extract_function
        ):
            start_time = time.time()
            functions = extractor.extract_functions(mock_tree, large_source)
            end_time = time.time()

            # Should complete within reasonable time (5 seconds)
            assert end_time - start_time < 5.0
            assert len(functions) == 100

    def test_memory_usage_with_caching(self, extractor):
        """Test memory usage with caching"""
        import gc

        # Perform many operations to populate caches
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 10
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 10)

        extractor.content_lines = ["test content"] * 1000

        # Populate caches
        for i in range(1000):
            mock_node_copy = Mock()
            mock_node_copy.start_byte = i
            mock_node_copy.end_byte = i + 10
            mock_node_copy.start_point = (0, 0)
            mock_node_copy.end_point = (0, 10)

            with patch(
                "tree_sitter_analyzer.languages.javascript_plugin.extract_text_slice"
            ) as mock_extract:
                mock_extract.return_value = f"text_{i}"
                extractor._get_node_text_optimized(mock_node_copy)

        # Check cache sizes
        assert len(extractor._node_text_cache) <= 1000

        # Reset caches and force garbage collection
        extractor._reset_caches()
        gc.collect()

        # Caches should be empty
        assert len(extractor._node_text_cache) == 0

    def test_error_handling_in_extraction(self, extractor):
        """Test error handling during extraction"""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []
