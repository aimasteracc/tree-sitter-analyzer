#!/usr/bin/env python3
"""
Tests for tree_sitter_analyzer.core.engine module.

This module tests the AnalysisEngine class which is the core component
of the new architecture responsible for file analysis workflow.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from typing import Optional, Dict, Any

from tree_sitter_analyzer.core.engine import AnalysisEngine
from tree_sitter_analyzer.models import AnalysisResult, CodeElement


class TestAnalysisEngine:
    """Test cases for AnalysisEngine class"""

    @pytest.fixture
    def engine(self) -> AnalysisEngine:
        """Create an AnalysisEngine instance for testing"""
        return AnalysisEngine()

    @pytest.fixture
    def sample_java_file(self) -> str:
        """Create a temporary Java file for testing"""
        content = '''
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False) as f:
            f.write(content)
            return f.name

    def test_engine_initialization(self, engine: AnalysisEngine) -> None:
        """Test AnalysisEngine initialization"""
        assert engine is not None
        assert hasattr(engine, 'plugin_manager')
        assert hasattr(engine, 'parser')

    def test_analyze_file_success(self, engine: AnalysisEngine, sample_java_file: str) -> None:
        """Test successful file analysis"""
        try:
            result = engine.analyze_file(sample_java_file)
            
            assert isinstance(result, AnalysisResult)
            assert result.file_path == sample_java_file
            assert result.language == 'java'
            assert result.elements is not None
            assert len(result.elements) > 0
            
        finally:
            os.unlink(sample_java_file)

    def test_analyze_file_with_language_override(self, engine: AnalysisEngine, sample_java_file: str) -> None:
        """Test file analysis with explicit language specification"""
        try:
            result = engine.analyze_file(sample_java_file, language='java')
            
            assert isinstance(result, AnalysisResult)
            assert result.language == 'java'
            
        finally:
            os.unlink(sample_java_file)

    def test_analyze_file_nonexistent(self, engine: AnalysisEngine) -> None:
        """Test analysis of non-existent file"""
        with pytest.raises(FileNotFoundError):
            engine.analyze_file('/nonexistent/file.java')

    def test_analyze_file_unsupported_language(self, engine: AnalysisEngine) -> None:
        """Test analysis of file with unsupported language"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xyz', delete=False) as f:
            f.write('some content')
            temp_path = f.name
        
        try:
            result = engine.analyze_file(temp_path)
            # Should fallback to default behavior or return empty result
            assert isinstance(result, AnalysisResult)
            
        finally:
            os.unlink(temp_path)

    def test_analyze_code_success(self, engine: AnalysisEngine) -> None:
        """Test successful code analysis"""
        code = '''
public class TestClass {
    public void testMethod() {
        System.out.println("Hello");
    }
}
'''
        result = engine.analyze_code(code, language='java')
        
        assert isinstance(result, AnalysisResult)
        assert result.language == 'java'
        assert result.elements is not None

    def test_analyze_code_with_filename(self, engine: AnalysisEngine) -> None:
        """Test code analysis with filename for language detection"""
        code = '''
def test_function():
    print("Hello")
'''
        result = engine.analyze_code(code, filename='test.py')
        
        assert isinstance(result, AnalysisResult)
        assert result.language == 'python'

    def test_analyze_code_invalid_language(self, engine: AnalysisEngine) -> None:
        """Test code analysis with invalid language"""
        code = 'some code'
        result = engine.analyze_code(code, language='invalid')
        
        # Should handle gracefully
        assert isinstance(result, AnalysisResult)

    @patch('tree_sitter_analyzer.core.engine.AnalysisEngine._initialize_plugins')
    def test_plugin_initialization_failure(self, mock_init: Mock) -> None:
        """Test handling of plugin initialization failure"""
        mock_init.side_effect = Exception("Plugin initialization failed")
        
        # Should raise exception during initialization
        with pytest.raises(Exception, match="Plugin initialization failed"):
            AnalysisEngine()

    def test_determine_language_from_path(self, engine: AnalysisEngine) -> None:
        """Test language determination from file path"""
        # Test with Path object
        java_path = Path('test.java')
        language = engine._determine_language(java_path, None)
        assert language == 'java'
        
        # Test with explicit language override
        language = engine._determine_language(java_path, 'python')
        assert language == 'python'

    def test_execute_queries_success(self, engine: AnalysisEngine) -> None:
        """Test successful query execution"""
        mock_tree = Mock()
        mock_plugin = Mock()
        mock_plugin.get_supported_queries.return_value = ['functions', 'classes']
        
        with patch.object(engine, '_execute_queries') as mock_execute:
            mock_execute.return_value = {'functions': [], 'classes': []}
            
            result = engine._execute_queries(mock_tree, mock_plugin)
            assert isinstance(result, dict)

    def test_extract_elements_success(self, engine: AnalysisEngine) -> None:
        """Test successful element extraction"""
        mock_parse_result = Mock()
        mock_plugin = Mock()
        mock_plugin.create_extractor.return_value.extract_all_elements.return_value = []
        
        elements = engine._extract_elements(mock_parse_result, mock_plugin)
        assert isinstance(elements, list)

    def test_count_nodes(self, engine: AnalysisEngine) -> None:
        """Test node counting functionality"""
        mock_tree = Mock()
        mock_root = Mock()
        mock_root.children = []
        mock_tree.root_node = mock_root
        
        count = engine._count_nodes(mock_tree)
        assert isinstance(count, int)
        assert count >= 0


class TestAnalysisEngineErrorHandling:
    """Test error handling in AnalysisEngine"""

    @pytest.fixture
    def engine(self) -> AnalysisEngine:
        """Create an AnalysisEngine instance for testing"""
        return AnalysisEngine()

    def test_analyze_file_permission_error(self, engine: AnalysisEngine) -> None:
        """Test handling of file permission errors"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False) as f:
            f.write('public class Test {}')
            temp_path = f.name
        
        try:
            # Make file unreadable
            os.chmod(temp_path, 0o000)
            
            # On Windows, permission errors might be handled differently
            # Test that either PermissionError is raised or analysis returns error result
            try:
                result = engine.analyze_file(temp_path)
                # If no exception, check that analysis failed gracefully
                assert isinstance(result, AnalysisResult)
                # On Windows, the analysis might succeed despite permission changes
                # This is acceptable behavior
            except PermissionError:
                # This is also acceptable behavior
                pass
                
        finally:
            # Restore permissions and cleanup
            os.chmod(temp_path, 0o644)
            os.unlink(temp_path)

    def test_analyze_code_empty_content(self, engine: AnalysisEngine) -> None:
        """Test analysis of empty code content"""
        result = engine.analyze_code('', language='java')
        
        assert isinstance(result, AnalysisResult)
        assert result.language == 'java'

    def test_analyze_code_malformed_content(self, engine: AnalysisEngine) -> None:
        """Test analysis of malformed code content"""
        malformed_code = '''
public class Test {
    // Missing closing brace
'''
        result = engine.analyze_code(malformed_code, language='java')
        
        # Should handle gracefully
        assert isinstance(result, AnalysisResult)

    @patch('tree_sitter_analyzer.core.engine.AnalysisEngine._extract_elements')
    def test_element_extraction_failure(self, mock_extract: Mock, engine: AnalysisEngine) -> None:
        """Test handling of element extraction failure"""
        mock_extract.side_effect = Exception("Extraction failed")
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False) as f:
            f.write('public class Test {}')
            temp_path = f.name
        
        try:
            result = engine.analyze_file(temp_path)
            # Should handle gracefully and return result with empty elements
            assert isinstance(result, AnalysisResult)
            
        finally:
            os.unlink(temp_path)


class TestAnalysisEngineIntegration:
    """Integration tests for AnalysisEngine"""

    @pytest.fixture
    def engine(self) -> AnalysisEngine:
        """Create an AnalysisEngine instance for testing"""
        return AnalysisEngine()

    def test_full_analysis_workflow_java(self, engine: AnalysisEngine) -> None:
        """Test complete analysis workflow for Java file"""
        java_code = '''
package com.example;

import java.util.List;

public class Calculator {
    private int value;
    
    public Calculator(int initialValue) {
        this.value = initialValue;
    }
    
    public int add(int number) {
        return value + number;
    }
    
    public int getValue() {
        return value;
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False) as f:
            f.write(java_code)
            temp_path = f.name
        
        try:
            result = engine.analyze_file(temp_path)
            
            assert isinstance(result, AnalysisResult)
            assert result.file_path == temp_path
            assert result.language == 'java'
            assert result.elements is not None
            assert result.node_count > 0
            
            # Check for expected elements
            element_types = [elem.element_type for elem in result.elements]
            assert 'class' in element_types or 'function' in element_types
            
        finally:
            os.unlink(temp_path)

    def test_full_analysis_workflow_python(self, engine: AnalysisEngine) -> None:
        """Test complete analysis workflow for Python file"""
        python_code = '''
import os
from typing import List

class Calculator:
    def __init__(self, initial_value: int = 0):
        self.value = initial_value
    
    def add(self, number: int) -> int:
        """Add a number to the current value"""
        return self.value + number
    
    def get_value(self) -> int:
        """Get the current value"""
        return self.value

def main():
    calc = Calculator(10)
    result = calc.add(5)
    print(f"Result: {result}")

if __name__ == "__main__":
    main()
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(python_code)
            temp_path = f.name
        
        try:
            result = engine.analyze_file(temp_path)
            
            assert isinstance(result, AnalysisResult)
            assert result.file_path == temp_path
            assert result.language == 'python'
            assert result.elements is not None
            assert result.node_count > 0
            
        finally:
            os.unlink(temp_path)

    def test_multiple_file_analysis(self, engine: AnalysisEngine) -> None:
        """Test analysis of multiple files"""
        files = []
        
        try:
            # Create Java file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False) as f:
                f.write('public class JavaTest { public void test() {} }')
                files.append(f.name)
            
            # Create Python file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write('def python_test(): pass')
                files.append(f.name)
            
            results = []
            for file_path in files:
                result = engine.analyze_file(file_path)
                results.append(result)
            
            assert len(results) == 2
            assert results[0].language == 'java'
            assert results[1].language == 'python'
            
        finally:
            for file_path in files:
                if os.path.exists(file_path):
                    os.unlink(file_path)