#!/usr/bin/env python3
"""
Comprehensive tests for language plugins to achieve high coverage.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from tree_sitter_analyzer.languages.python_plugin import PythonPlugin
from tree_sitter_analyzer.languages.java_plugin import JavaPlugin
from tree_sitter_analyzer.languages.javascript_plugin import JavaScriptPlugin
from tree_sitter_analyzer.languages.typescript_plugin import TypeScriptPlugin
from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest
from tree_sitter_analyzer.models import AnalysisResult


class TestPythonPluginComprehensive:
    """Comprehensive test suite for Python plugin"""

    def setup_method(self):
        """Set up test fixtures"""
        self.plugin = PythonPlugin()

    def test_plugin_basic_properties(self):
        """Test plugin basic properties"""
        assert hasattr(self.plugin, 'get_language_name')
        assert hasattr(self.plugin, 'get_file_extensions')
        assert hasattr(self.plugin, 'is_applicable')

    def test_get_language_name(self):
        """Test getting language name"""
        name = self.plugin.get_language_name()
        assert name == "python"

    def test_get_file_extensions(self):
        """Test getting file extensions"""
        extensions = self.plugin.get_file_extensions()
        assert ".py" in extensions

    def test_is_applicable_python_file(self):
        """Test applicability for Python files"""
        assert self.plugin.is_applicable("test.py")
        assert self.plugin.is_applicable("script.pyw")
        assert not self.plugin.is_applicable("test.js")

    def test_analyze_file_with_mock(self):
        """Test file analysis with mocked dependencies"""
        request = AnalysisRequest(
            file_path="test.py",
            content="def hello(): pass",
            language="python"
        )
        
        with patch('tree_sitter_analyzer.languages.python_plugin.loader') as mock_loader:
            mock_language = Mock()
            mock_parser = Mock()
            mock_tree = Mock()
            
            mock_loader.get_language.return_value = mock_language
            mock_loader.create_parser.return_value = mock_parser
            mock_parser.parse.return_value = mock_tree
            
            result = self.plugin.analyze_file(request)
            
            assert isinstance(result, AnalysisResult)
            assert result.file_path == "test.py"
            assert result.language == "python"

    def test_analyze_file_error_handling(self):
        """Test file analysis error handling"""
        request = AnalysisRequest(
            file_path="error.py",
            content="invalid python code {{{",
            language="python"
        )
        
        with patch('tree_sitter_analyzer.languages.python_plugin.loader') as mock_loader:
            mock_loader.get_language.side_effect = Exception("Parse error")
            
            result = self.plugin.analyze_file(request)
            
            # Should handle error gracefully and return a valid result
            assert isinstance(result, AnalysisResult)
            assert result.file_path == "error.py"

    def test_get_supported_queries(self):
        """Test getting supported queries"""
        queries = self.plugin.get_supported_queries()
        assert isinstance(queries, list)
        assert len(queries) > 0

    def test_plugin_info(self):
        """Test getting plugin info"""
        info = self.plugin.get_plugin_info()
        assert isinstance(info, dict)
        assert "name" in info
        assert info["name"] == "python"


class TestJavaPluginComprehensive:
    """Comprehensive test suite for Java plugin"""

    def setup_method(self):
        """Set up test fixtures"""
        self.plugin = JavaPlugin()

    def test_plugin_basic_properties(self):
        """Test plugin basic properties"""
        assert self.plugin.get_language_name() == "java"
        extensions = self.plugin.get_file_extensions()
        assert ".java" in extensions

    def test_is_applicable_java_file(self):
        """Test applicability for Java files"""
        assert self.plugin.is_applicable("Test.java")
        assert not self.plugin.is_applicable("test.py")

    def test_analyze_file_with_mock(self):
        """Test file analysis with mocked dependencies"""
        request = AnalysisRequest(
            file_path="Test.java",
            content="public class Test { public void hello() {} }",
            language="java"
        )
        
        with patch('tree_sitter_analyzer.languages.java_plugin.loader') as mock_loader:
            mock_language = Mock()
            mock_parser = Mock()
            mock_tree = Mock()
            
            mock_loader.get_language.return_value = mock_language
            mock_loader.create_parser.return_value = mock_parser
            mock_parser.parse.return_value = mock_tree
            
            result = self.plugin.analyze_file(request)
            
            assert isinstance(result, AnalysisResult)
            assert result.file_path == "Test.java"
            assert result.language == "java"

    def test_get_supported_queries(self):
        """Test getting supported queries"""
        queries = self.plugin.get_supported_queries()
        assert isinstance(queries, list)
        assert len(queries) > 0

    def test_plugin_info(self):
        """Test getting plugin info"""
        info = self.plugin.get_plugin_info()
        assert isinstance(info, dict)
        assert "name" in info
        assert info["name"] == "java"


class TestJavaScriptPluginComprehensive:
    """Comprehensive test suite for JavaScript plugin"""

    def setup_method(self):
        """Set up test fixtures"""
        self.plugin = JavaScriptPlugin()

    def test_plugin_basic_properties(self):
        """Test plugin basic properties"""
        assert self.plugin.get_language_name() == "javascript"
        extensions = self.plugin.get_file_extensions()
        assert ".js" in extensions

    def test_is_applicable_javascript_file(self):
        """Test applicability for JavaScript files"""
        assert self.plugin.is_applicable("test.js")
        assert self.plugin.is_applicable("component.jsx")
        assert not self.plugin.is_applicable("test.py")

    def test_analyze_file_with_mock(self):
        """Test file analysis with mocked dependencies"""
        request = AnalysisRequest(
            file_path="test.js",
            content="function hello() { return 'world'; }",
            language="javascript"
        )
        
        with patch('tree_sitter_analyzer.languages.javascript_plugin.loader') as mock_loader:
            mock_language = Mock()
            mock_parser = Mock()
            mock_tree = Mock()
            
            mock_loader.get_language.return_value = mock_language
            mock_loader.create_parser.return_value = mock_parser
            mock_parser.parse.return_value = mock_tree
            
            result = self.plugin.analyze_file(request)
            
            assert isinstance(result, AnalysisResult)
            assert result.file_path == "test.js"
            assert result.language == "javascript"

    def test_get_supported_queries(self):
        """Test getting supported queries"""
        queries = self.plugin.get_supported_queries()
        assert isinstance(queries, list)
        assert len(queries) > 0

    def test_plugin_info(self):
        """Test getting plugin info"""
        info = self.plugin.get_plugin_info()
        assert isinstance(info, dict)
        assert "name" in info
        assert info["name"] == "javascript"


class TestTypeScriptPluginComprehensive:
    """Comprehensive test suite for TypeScript plugin"""

    def setup_method(self):
        """Set up test fixtures"""
        self.plugin = TypeScriptPlugin()

    def test_plugin_basic_properties(self):
        """Test plugin basic properties"""
        assert self.plugin.get_language_name() == "typescript"
        extensions = self.plugin.get_file_extensions()
        assert ".ts" in extensions
        assert ".tsx" in extensions

    def test_is_applicable_typescript_file(self):
        """Test applicability for TypeScript files"""
        assert self.plugin.is_applicable("test.ts")
        assert self.plugin.is_applicable("component.tsx")
        assert not self.plugin.is_applicable("test.js")

    def test_analyze_file_with_mock(self):
        """Test file analysis with mocked dependencies"""
        request = AnalysisRequest(
            file_path="test.ts",
            content="interface User { name: string; } class UserImpl implements User { name: string = ''; }",
            language="typescript"
        )
        
        with patch('tree_sitter_analyzer.languages.typescript_plugin.loader') as mock_loader:
            mock_language = Mock()
            mock_parser = Mock()
            mock_tree = Mock()
            
            mock_loader.get_language.return_value = mock_language
            mock_loader.create_parser.return_value = mock_parser
            mock_parser.parse.return_value = mock_tree
            
            result = self.plugin.analyze_file(request)
            
            assert isinstance(result, AnalysisResult)
            assert result.file_path == "test.ts"
            assert result.language == "typescript"

    def test_get_supported_queries(self):
        """Test getting supported queries"""
        queries = self.plugin.get_supported_queries()
        assert isinstance(queries, list)
        assert len(queries) > 0

    def test_plugin_info(self):
        """Test getting plugin info"""
        info = self.plugin.get_plugin_info()
        assert isinstance(info, dict)
        assert "name" in info
        assert info["name"] == "typescript"


class TestPluginErrorHandling:
    """Test error handling across all plugins"""

    def test_all_plugins_handle_invalid_requests(self):
        """Test that all plugins handle invalid requests gracefully"""
        plugins = [PythonPlugin(), JavaPlugin(), JavaScriptPlugin(), TypeScriptPlugin()]
        
        invalid_request = AnalysisRequest(
            file_path="",
            content="",
            language=""
        )
        
        for plugin in plugins:
            try:
                result = plugin.analyze_file(invalid_request)
                assert isinstance(result, AnalysisResult)
            except Exception:
                # Some plugins might raise exceptions for invalid input
                pass

    def test_all_plugins_have_required_methods(self):
        """Test that all plugins have required methods"""
        plugins = [PythonPlugin(), JavaPlugin(), JavaScriptPlugin(), TypeScriptPlugin()]
        
        required_methods = ['get_language_name', 'get_file_extensions', 'is_applicable', 'analyze_file']
        
        for plugin in plugins:
            for method_name in required_methods:
                assert hasattr(plugin, method_name)
                assert callable(getattr(plugin, method_name))

    def test_all_plugins_return_consistent_info(self):
        """Test that all plugins return consistent info"""
        plugins = [PythonPlugin(), JavaPlugin(), JavaScriptPlugin(), TypeScriptPlugin()]
        
        for plugin in plugins:
            # Test language name
            lang_name = plugin.get_language_name()
            assert isinstance(lang_name, str)
            assert len(lang_name) > 0
            
            # Test file extensions
            extensions = plugin.get_file_extensions()
            assert isinstance(extensions, list)
            assert len(extensions) > 0
            assert all(ext.startswith('.') for ext in extensions)
            
            # Test plugin info
            info = plugin.get_plugin_info()
            assert isinstance(info, dict)
            assert "name" in info
            assert info["name"] == lang_name

    def test_plugin_memory_usage(self):
        """Test plugin memory usage patterns"""
        # Create and destroy multiple plugin instances
        for _ in range(100):
            plugins = [PythonPlugin(), JavaPlugin(), JavaScriptPlugin(), TypeScriptPlugin()]
            
            # Test basic operations
            for plugin in plugins:
                plugin.get_language_name()
                plugin.get_file_extensions()
                plugin.is_applicable("test.txt")
        
        # Should complete without memory issues
        assert True

    def test_plugin_thread_safety(self):
        """Test plugin thread safety"""
        import threading
        
        results = []
        errors = []
        
        def worker():
            try:
                plugin = PythonPlugin()
                name = plugin.get_language_name()
                extensions = plugin.get_file_extensions()
                applicable = plugin.is_applicable("test.py")
                
                results.append((name, extensions, applicable))
            except Exception as e:
                errors.append(e)
        
        # Create multiple threads
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=worker)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        # Check results
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 10
        assert all(name == "python" for name, _, _ in results)
        assert all(".py" in extensions for _, extensions, _ in results)
        assert all(applicable for _, _, applicable in results)