#!/usr/bin/env python3
"""
Tests for tree_sitter_analyzer.core.query module.

This module tests the QueryExecutor class which handles Tree-sitter
query execution in the new architecture.
"""

import pytest
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
from typing import List, Dict, Any, Optional

from tree_sitter_analyzer.core.query import QueryExecutor


class TestQueryExecutor:
    """Test cases for QueryExecutor class"""

    @pytest.fixture
    def query_executor(self) -> QueryExecutor:
        """Create a QueryExecutor instance for testing"""
        return QueryExecutor()

    @pytest.fixture
    def mock_tree(self) -> Mock:
        """Create a mock tree-sitter tree"""
        tree = Mock()
        root_node = Mock()
        root_node.children = []
        tree.root_node = root_node
        return tree

    @pytest.fixture
    def mock_language(self) -> Mock:
        """Create a mock tree-sitter language"""
        language = Mock()
        return language

    @pytest.fixture
    def sample_java_code(self) -> str:
        """Sample Java code for testing"""
        return '''
public class TestClass {
    private String name;
    
    public TestClass(String name) {
        this.name = name;
    }
    
    public String getName() {
        return name;
    }
    
    public void setName(String name) {
        this.name = name;
    }
}
'''

    def test_query_executor_initialization(self, query_executor: QueryExecutor) -> None:
        """Test QueryExecutor initialization"""
        assert query_executor is not None
        assert hasattr(query_executor, 'execute_query')
        assert hasattr(query_executor, 'execute_query_string')

    def test_execute_query_success(self, query_executor: QueryExecutor, mock_tree: Mock, mock_language: Mock) -> None:
        """Test successful query execution"""
        with patch('tree_sitter_analyzer.query_loader.get_query') as mock_get_query:
            mock_query = Mock()
            mock_get_query.return_value = mock_query
            
            # Mock query captures
            mock_captures = [
                {'node': Mock(), 'name': 'function_name'},
                {'node': Mock(), 'name': 'function_body'}
            ]
            mock_query.captures.return_value = mock_captures
            
            result = query_executor.execute_query(mock_tree, mock_language, 'functions', 'test code')
            
            assert isinstance(result, dict)
            assert 'captures' in result
            assert 'query_name' in result
            assert result['query_name'] == 'functions'

    def test_execute_query_no_query_found(self, query_executor: QueryExecutor, mock_tree: Mock, mock_language: Mock) -> None:
        """Test query execution when query is not found"""
        with patch('tree_sitter_analyzer.query_loader.get_query') as mock_get_query:
            mock_get_query.return_value = None
            
            result = query_executor.execute_query(mock_tree, mock_language, 'nonexistent', 'test code')
            
            assert isinstance(result, dict)
            assert result['captures'] == []
            assert 'error' in result

    def test_execute_query_string_success(self, query_executor: QueryExecutor, mock_tree: Mock, mock_language: Mock) -> None:
        """Test successful query string execution"""
        query_string = '(method_declaration name: (identifier) @method-name)'
        
        with patch('tree_sitter.Language.query') as mock_language_query:
            mock_query = Mock()
            mock_language_query.return_value = mock_query
            
            # Mock query captures
            mock_captures = [
                (Mock(), 'method-name')
            ]
            mock_query.captures.return_value = mock_captures
            
            result = query_executor.execute_query_string(mock_tree, mock_language, query_string, 'test code')
            
            assert isinstance(result, dict)
            assert 'captures' in result
            assert 'query_string' in result

    def test_execute_query_string_invalid_query(self, query_executor: QueryExecutor, mock_tree: Mock, mock_language: Mock) -> None:
        """Test query string execution with invalid query"""
        invalid_query = '(invalid_syntax'
        
        mock_language.query.side_effect = Exception("Invalid query syntax")
        result = query_executor.execute_query_string(mock_tree, mock_language, invalid_query, 'test code')
        
        assert isinstance(result, dict)
        assert 'error' in result
        assert 'Query execution failed' in result['error']
        assert result['captures'] == []

    def test_process_captures_dict_format(self, query_executor: QueryExecutor) -> None:
        """Test processing captures in dictionary format"""
        mock_node = Mock()
        mock_node.start_point = (1, 0)
        mock_node.end_point = (1, 10)
        mock_node.text = b'test_method'
        
        captures = [
            {'node': mock_node, 'name': 'method_name'}
        ]
        
        with patch.object(query_executor, '_create_result_dict') as mock_create_result:
            mock_create_result.return_value = {'name': 'test_method', 'type': 'method'}
            
            result = query_executor._process_captures(captures, 'test code')
            
            assert isinstance(result, list)
            assert len(result) == 1

    def test_process_captures_tuple_format(self, query_executor: QueryExecutor) -> None:
        """Test processing captures in tuple format (old Tree-sitter API)"""
        mock_node = Mock()
        mock_node.start_point = (1, 0)
        mock_node.end_point = (1, 10)
        mock_node.text = b'test_method'
        
        captures = [
            (mock_node, 'method_name')
        ]
        
        with patch.object(query_executor, '_create_result_dict') as mock_create_result:
            mock_create_result.return_value = {'name': 'test_method', 'type': 'method'}
            
            result = query_executor._process_captures(captures, 'test code')
            
            assert isinstance(result, list)
            assert len(result) == 1

    def test_create_result_dict(self, query_executor: QueryExecutor) -> None:
        """Test creating result dictionary from node"""
        mock_node = Mock()
        mock_node.start_point = (1, 5)
        mock_node.end_point = (3, 10)
        mock_node.type = 'method_declaration'
        mock_node.text = b'public void testMethod() {}'
        
        result = query_executor._create_result_dict(mock_node, 'method_name', 'test source code')
        
        assert isinstance(result, dict)
        assert 'capture_name' in result
        assert 'node_type' in result
        assert 'start_point' in result
        assert 'end_point' in result
        assert 'text' in result
        assert result['capture_name'] == 'method_name'
        assert result['node_type'] == 'method_declaration'

    def test_create_result_dict_with_exception(self, query_executor: QueryExecutor) -> None:
        """Test creating result dictionary when node processing fails"""
        mock_node = Mock()
        mock_node.start_point = (1, 5)
        mock_node.end_point = (3, 10)
        mock_node.type = 'method_declaration'
        mock_node.text = None  # This might cause an exception
        
        result = query_executor._create_result_dict(mock_node, 'method_name', 'test source code')
        
        # Should handle exceptions gracefully
        assert isinstance(result, dict)
        assert 'capture_name' in result

    def test_get_available_queries(self, query_executor: QueryExecutor) -> None:
        """Test getting available queries for a language"""
        with patch.object(query_executor, '_query_loader') as mock_loader:
            mock_loader.get_all_queries_for_language.return_value = {
                'functions': '...', 'classes': '...'
            }
            
            queries = query_executor.get_available_queries('java')
            
            assert isinstance(queries, dict)
            assert 'functions' in queries
            assert 'classes' in queries

    def test_get_available_queries_unknown_language(self, query_executor: QueryExecutor) -> None:
        """Test getting available queries for unknown language"""
        with patch.object(query_executor, '_query_loader') as mock_loader:
            mock_loader.get_all_queries_for_language.return_value = {}
            
            queries = query_executor.get_available_queries('unknown')
            
            assert isinstance(queries, dict)
            assert len(queries) == 0

    def test_get_query_description(self, query_executor: QueryExecutor) -> None:
        """Test getting query description"""
        with patch.object(query_executor, '_query_loader') as mock_loader:
            mock_loader.get_query_description.return_value = "すべての関数/メソッド宣言を検索（methodのエイリアス）"
            
            description = query_executor.get_query_description('java', 'functions')
            
            assert description == "すべての関数/メソッド宣言を検索（methodのエイリアス）"
            mock_loader.get_query_description.assert_called_once_with('java', 'functions')

    def test_get_query_description_not_found(self, query_executor: QueryExecutor) -> None:
        """Test getting description for non-existent query"""
        with patch.object(query_executor, '_query_loader') as mock_loader:
            mock_loader.get_query_description.return_value = None
            
            description = query_executor.get_query_description('java', 'nonexistent')
            
            assert description is None
            mock_loader.get_query_description.assert_called_once_with('java', 'nonexistent')

    def test_validate_query_valid(self, query_executor: QueryExecutor, mock_language: Mock) -> None:
        """Test validating a valid query"""
        valid_query = '(method_declaration name: (identifier) @method-name)'
        
        with patch('tree_sitter.Language.query') as mock_language_query:
            mock_language_query.return_value = Mock()  # Successful creation
            
            is_valid = query_executor.validate_query('java', valid_query)
            
            assert is_valid is True

    def test_validate_query_invalid(self, query_executor: QueryExecutor, mock_language: Mock) -> None:
        """Test validating an invalid query"""
        invalid_query = '(invalid_syntax'
        
        with patch('tree_sitter.Language.query') as mock_language_query:
            mock_language_query.side_effect = Exception("Invalid syntax")
            
            is_valid = query_executor.validate_query('java', invalid_query)
            
            assert is_valid is False

    def test_execute_multiple_queries(self, query_executor: QueryExecutor, mock_tree: Mock, mock_language: Mock) -> None:
        """Test executing multiple queries"""
        query_names = ['functions', 'classes']
        
        with patch.object(query_executor, 'execute_query') as mock_execute:
            mock_execute.side_effect = [
                {'captures': [{'name': 'func1'}], 'query_name': 'functions'},
                {'captures': [{'name': 'class1'}], 'query_name': 'classes'}
            ]
            
            results = query_executor.execute_multiple_queries(mock_tree, mock_language, query_names, 'test code')
            
            assert isinstance(results, dict)
            assert 'functions' in results
            assert 'classes' in results

    def test_execute_multiple_queries_with_failure(self, query_executor: QueryExecutor, mock_tree: Mock, mock_language: Mock) -> None:
        """Test executing multiple queries with some failures"""
        query_names = ['functions', 'invalid_query']
        
        with patch.object(query_executor, 'execute_query') as mock_execute:
            mock_execute.side_effect = [
                {'captures': [{'name': 'func1'}], 'query_name': 'functions'},
                {'captures': [], 'error': 'Query not found', 'query_name': 'invalid_query'}
            ]
            
            results = query_executor.execute_multiple_queries(mock_tree, mock_language, query_names, 'test code')
            
            assert isinstance(results, dict)
            assert 'functions' in results
            assert 'invalid_query' in results

    def test_get_query_statistics(self, query_executor: QueryExecutor) -> None:
        """Test getting query execution statistics"""
        # This method might track execution times, success rates, etc.
        stats = query_executor.get_query_statistics()
        
        assert isinstance(stats, dict)
        # The exact structure depends on implementation


class TestQueryExecutorErrorHandling:
    """Test error handling in QueryExecutor"""

    @pytest.fixture
    def query_executor(self) -> QueryExecutor:
        """Create a QueryExecutor instance for testing"""
        return QueryExecutor()

    @pytest.fixture
    def mock_tree(self) -> Mock:
        """Create a mock tree-sitter tree"""
        return Mock()

    @pytest.fixture
    def mock_language(self) -> Mock:
        """Create a mock tree-sitter language"""
        return Mock()

    def test_execute_query_with_none_tree(self, query_executor: QueryExecutor, mock_language: Mock) -> None:
        """Test query execution with None tree"""
        result = query_executor.execute_query(None, mock_language, 'functions', 'test code')
        
        assert isinstance(result, dict)
        assert 'error' in result
        assert result['captures'] == []

    def test_execute_query_with_none_language(self, query_executor: QueryExecutor, mock_tree: Mock) -> None:
        """Test query execution with None language"""
        result = query_executor.execute_query(mock_tree, None, 'functions', 'test code')
        
        assert isinstance(result, dict)
        assert 'error' in result
        assert result['captures'] == []

    def test_execute_query_with_exception_in_processing(self, query_executor: QueryExecutor, mock_tree: Mock, mock_language: Mock) -> None:
        """Test query execution when processing raises exception"""
        with patch('tree_sitter_analyzer.query_loader.get_query') as mock_get_query:
            mock_get_query.return_value = None  # Query not found

            result = query_executor.execute_query(mock_tree, mock_language, 'method', 'test code')

            assert isinstance(result, dict)
            assert 'error' in result
            assert "Query 'method' not found" in result['error']

    def test_process_captures_with_malformed_data(self, query_executor: QueryExecutor) -> None:
        """Test processing captures with malformed data"""
        # Test with unexpected capture format
        malformed_captures = [
            "not a dict or tuple",
            {'missing_node': True},
            (None, 'name')
        ]
        
        result = query_executor._process_captures(malformed_captures, 'test code')
        
        # Should handle gracefully and return empty or partial results
        assert isinstance(result, list)

    def test_create_result_dict_with_unicode_text(self, query_executor: QueryExecutor) -> None:
        """Test creating result dictionary with Unicode text"""
        mock_node = Mock()
        mock_node.start_point = (1, 0)
        mock_node.end_point = (1, 10)
        mock_node.type = 'string_literal'
        mock_node.text = 'こんにちは'.encode('utf-8')  # Japanese text in bytes
        
        result = query_executor._create_result_dict(mock_node, 'string_value', 'test source')
        
        assert isinstance(result, dict)
        assert 'text' in result
        # Should handle Unicode properly


class TestQueryExecutorIntegration:
    """Integration tests for QueryExecutor"""

    @pytest.fixture
    def query_executor(self) -> QueryExecutor:
        """Create a QueryExecutor instance for testing"""
        return QueryExecutor()

    def test_real_java_query_execution(self, query_executor: QueryExecutor) -> None:
        """Test query execution with real Java code and tree"""
        # This would require actual tree-sitter parsing
        # For now, we'll mock the components but test the integration
        java_code = '''
public class TestClass {
    public void testMethod() {
        System.out.println("Hello");
    }
}
'''
        
        with patch('tree_sitter_analyzer.query_loader.get_query') as mock_get_query, \
             patch('tree_sitter_analyzer.query_loader.query_loader') as mock_loader:
            
            # Mock the query and language
            mock_query = Mock()
            mock_get_query.return_value = mock_query
            mock_query.captures.return_value = []
            
            mock_language = Mock()
            mock_loader.create_parser_safely.return_value = Mock()
            
            # Mock tree
            mock_tree = Mock()
            
            result = query_executor.execute_query(mock_tree, mock_language, 'functions', java_code)
            
            assert isinstance(result, dict)
            assert 'query_name' in result

    def test_query_workflow_end_to_end(self, query_executor: QueryExecutor) -> None:
        """Test complete query workflow from validation to execution"""
        query_string = '(method_declaration name: (identifier) @method-name)'
        
        with patch('tree_sitter.Language.query') as mock_language_query:
            mock_query = Mock()
            mock_language_query.return_value = mock_query
            mock_query.captures.return_value = []
            
            mock_language = Mock()
            mock_tree = Mock()
            
            # First validate the query
            is_valid = query_executor.validate_query('java', query_string)
            assert is_valid is True
            
            # Then execute it
            result = query_executor.execute_query_string(mock_tree, mock_language, query_string, 'test code')
            assert isinstance(result, dict)

    def test_multiple_language_support(self, query_executor: QueryExecutor) -> None:
        """Test query execution across multiple languages"""
        languages = ['java', 'python', 'javascript']
        
        for language in languages:
            with patch.object(query_executor, '_query_loader') as mock_loader:
                mock_loader.get_all_queries_for_language.return_value = {'functions': '...', 'classes': '...'}
                
                queries = query_executor.get_available_queries(language)
                assert isinstance(queries, dict)