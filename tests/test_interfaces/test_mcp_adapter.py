#!/usr/bin/env python3
"""
Tests for tree_sitter_analyzer.interfaces.mcp_adapter module.

This module tests the MCPAdapter class which provides a clean interface
between the MCP server and the core analysis engine in the new architecture.
"""

import pytest
import tempfile
import os
import asyncio
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from typing import List, Dict, Any, Optional

from tree_sitter_analyzer.interfaces.mcp_adapter import MCPAdapter, MCPServerAdapter
from tree_sitter_analyzer.models import AnalysisResult, CodeElement


class TestMCPAdapter:
    """Test cases for MCPAdapter class"""

    @pytest.fixture
    def mcp_adapter(self) -> MCPAdapter:
        """Create an MCPAdapter instance for testing"""
        return MCPAdapter()

    @pytest.fixture
    def sample_java_file(self) -> str:
        """Create a temporary Java file for testing"""
        content = '''
package com.example;

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
            f.write(content)
            return f.name

    @pytest.fixture
    def sample_python_file(self) -> str:
        """Create a temporary Python file for testing"""
        content = '''
from typing import Optional

class Calculator:
    def __init__(self, initial_value: int = 0):
        self.value = initial_value
    
    def add(self, number: int) -> int:
        """Add a number to the current value"""
        self.value += number
        return self.value
    
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
            f.write(content)
            return f.name

    def test_mcp_adapter_initialization(self, mcp_adapter: MCPAdapter) -> None:
        """Test MCPAdapter initialization"""
        assert mcp_adapter is not None
        assert hasattr(mcp_adapter, 'analyze_file_async')
        assert hasattr(mcp_adapter, 'get_file_structure_async')
        assert hasattr(mcp_adapter, 'analyze_batch_async')

    @pytest.mark.asyncio
    async def test_analyze_file_async_java_success(self, mcp_adapter: MCPAdapter, sample_java_file: str) -> None:
        """Test successful async Java file analysis through MCP adapter"""
        try:
            result = await mcp_adapter.analyze_file_async(sample_java_file)
            
            assert isinstance(result, AnalysisResult)
            assert result.file_path == sample_java_file
            assert result.language == 'java'
            assert result.elements is not None
            assert result.elements is not None
            assert result.node_count > 0
            
        finally:
            os.unlink(sample_java_file)

    @pytest.mark.asyncio
    async def test_analyze_file_async_python_success(self, mcp_adapter: MCPAdapter, sample_python_file: str) -> None:
        """Test successful async Python file analysis through MCP adapter"""
        try:
            result = await mcp_adapter.analyze_file_async(sample_python_file)
            
            assert isinstance(result, AnalysisResult)
            assert result.file_path == sample_python_file
            assert result.language == 'python'
            assert result.elements is not None
            assert result.elements is not None
            
        finally:
            os.unlink(sample_python_file)

    @pytest.mark.asyncio
    async def test_analyze_file_async_with_options(self, mcp_adapter: MCPAdapter, sample_java_file: str) -> None:
        """Test async file analysis with additional options"""
        try:
            result = await mcp_adapter.analyze_file_async(
                sample_java_file,
                include_complexity=True,
                include_details=True
            )
            
            assert isinstance(result, AnalysisResult)
            assert result.file_path == sample_java_file
            
        finally:
            os.unlink(sample_java_file)

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_analyze_file_async_nonexistent(self, mcp_adapter: MCPAdapter) -> None:
        """Test async analysis of non-existent file"""
        with patch.object(mcp_adapter, 'engine') as mock_engine:
            mock_engine.analyze.side_effect = FileNotFoundError
            with pytest.raises(FileNotFoundError):
                await mcp_adapter.analyze_file_async('/nonexistent/file.java')

    @pytest.mark.asyncio
    async def test_get_file_structure_async_success(self, mcp_adapter: MCPAdapter, sample_java_file: str) -> None:
        """Test successful async file structure analysis"""
        try:
            result = await mcp_adapter.get_file_structure_async(sample_java_file)
            
            assert isinstance(result, dict)
            assert 'file_path' in result
            assert 'language' in result
            assert 'structure' in result or 'elements' in result
            
        finally:
            os.unlink(sample_java_file)

    @pytest.mark.asyncio
    async def test_get_file_structure_async_with_options(self, mcp_adapter: MCPAdapter, sample_java_file: str) -> None:
        """Test async structure analysis with options"""
        try:
            result = await mcp_adapter.get_file_structure_async(
                sample_java_file,
                include_metrics=True,
                include_relationships=True
            )
            
            assert isinstance(result, dict)
            
        finally:
            os.unlink(sample_java_file)

    @pytest.mark.asyncio
    async def test_analyze_batch_async_success(self, mcp_adapter: MCPAdapter) -> None:
        """Test successful async batch analysis"""
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
            
            results = await mcp_adapter.analyze_batch_async(files)
            
            assert isinstance(results, list)
            assert len(results) == 2
            assert all(isinstance(result, AnalysisResult) for result in results)
            assert results[0].language == 'java'
            assert results[1].language == 'python'
            
        finally:
            for file_path in files:
                if os.path.exists(file_path):
                    os.unlink(file_path)

    @pytest.mark.asyncio
    async def test_analyze_batch_async_with_options(self, mcp_adapter: MCPAdapter) -> None:
        """Test async batch analysis with options"""
        files = []
        
        try:
            # Create test files
            with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False) as f:
                f.write('public class Test {}')
                files.append(f.name)
            
            results = await mcp_adapter.analyze_batch_async(
                files,
                parallel=True,
                include_complexity=True
            )
            
            assert isinstance(results, list)
            assert len(results) == 1
            
        finally:
            for file_path in files:
                if os.path.exists(file_path):
                    os.unlink(file_path)

    @pytest.mark.asyncio
    async def test_analyze_batch_async_empty_list(self, mcp_adapter: MCPAdapter) -> None:
        """Test async batch analysis with empty file list"""
        results = await mcp_adapter.analyze_batch_async([])
        
        assert isinstance(results, list)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_handle_mcp_tool_request_success(self, mcp_adapter: MCPAdapter) -> None:
        """Test successful MCP tool request handling"""
        request = {
            'tool_name': 'analyze_file',
            'arguments': {
                'file_path': 'test.java',
                'language': 'java'
            }
        }
        
        with patch.object(mcp_adapter, 'analyze_file_async') as mock_analyze:
            mock_result = Mock(spec=AnalysisResult)
            mock_analyze.return_value = mock_result
            
            result = await mcp_adapter.handle_mcp_tool_request(request['tool_name'], request['arguments'])
            
            assert isinstance(result, dict)
            assert 'success' in result

    @pytest.mark.asyncio
    async def test_handle_mcp_tool_request_invalid(self, mcp_adapter: MCPAdapter) -> None:
        """Test MCP tool request handling with invalid request"""
        invalid_request = {
            'invalid_field': 'value'
        }
        
        result = await mcp_adapter.handle_mcp_tool_request(invalid_request.get('tool_name'), invalid_request.get('arguments'))
        
        assert isinstance(result, dict)
        assert 'error' in result

    @pytest.mark.asyncio
    async def test_handle_mcp_resource_request_success(self, mcp_adapter: MCPAdapter) -> None:
        """Test successful MCP resource request handling"""
        resource_uri = 'code://file/test.java'
        
        with patch('tree_sitter_analyzer.interfaces.mcp_adapter.read_file_safe') as mock_read:
            mock_read.return_value = 'public class Test {}'
            
            result = await mcp_adapter.handle_mcp_resource_request(resource_uri)
            
            assert isinstance(result, dict)
            assert 'content' in result or 'data' in result

    @pytest.mark.asyncio
    async def test_handle_mcp_resource_request_invalid_uri(self, mcp_adapter: MCPAdapter) -> None:
        """Test MCP resource request handling with invalid URI"""
        invalid_uri = 'invalid://uri'
        
        result = await mcp_adapter.handle_mcp_resource_request(invalid_uri)
        
        assert isinstance(result, dict)
        assert 'error' in result

    @pytest.mark.asyncio
    async def test_analyze_with_mcp_request_success(self, mcp_adapter: MCPAdapter) -> None:
        """Test analysis with MCP request format"""
        mcp_request = {
            'file_path': 'test.java',
            'language': 'java',
            'include_complexity': True
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False) as f:
            f.write('public class Test {}')
            mcp_request['file_path'] = f.name
        
        try:
            result = await mcp_adapter.analyze_with_mcp_request(mcp_request)
            
            assert isinstance(result, AnalysisResult)
            assert result.language == 'java'
            
        finally:
            os.unlink(mcp_request['file_path'])

    @pytest.mark.asyncio
    async def test_analyze_with_mcp_request_missing_file_path(self, mcp_adapter: MCPAdapter) -> None:
        """Test analysis with MCP request missing file path"""
        mcp_request = {
            'language': 'java'
        }
        
        with pytest.raises(KeyError):
            await mcp_adapter.analyze_with_mcp_request(mcp_request)

    def test_cleanup_method(self, mcp_adapter: MCPAdapter) -> None:
        """Test cleanup method"""
        # Should not raise any exceptions
        mcp_adapter.cleanup()

    @pytest.mark.asyncio
    async def test_aclose_method(self, mcp_adapter: MCPAdapter) -> None:
        """Test async close method"""
        # Should not raise any exceptions
        await mcp_adapter.aclose()

    def test_context_manager_property(self, mcp_adapter: MCPAdapter) -> None:
        """Test context manager property"""
        # Should return self or appropriate context manager
        context_manager = mcp_adapter.cleanup
        assert callable(context_manager)


class TestMCPAdapterErrorHandling:
    """Test error handling in MCPAdapter"""

    @pytest.fixture
    def mcp_adapter(self) -> MCPAdapter:
        """Create an MCPAdapter instance for testing"""
        return MCPAdapter()

    @pytest.mark.asyncio
    async def test_analyze_file_async_permission_error(self, mcp_adapter: MCPAdapter) -> None:
        """Test handling of file permission errors in async analysis"""
        with patch.object(mcp_adapter, 'engine') as mock_engine:
            mock_engine.analyze.side_effect = PermissionError("Permission denied")
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False) as f:
                f.write('public class Test {}')
                temp_path = f.name
            
            try:
                with pytest.raises(PermissionError):
                    await mcp_adapter.analyze_file_async(temp_path)
            finally:
                os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_analyze_file_async_unsupported_language(self, mcp_adapter: MCPAdapter) -> None:
        """Test async analysis with unsupported language"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xyz', delete=False) as f:
            f.write('some content')
            temp_path = f.name
        
        try:
            with pytest.raises(Exception):
                await mcp_adapter.analyze_file_async(temp_path)
            
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_get_file_structure_async_nonexistent_file(self, mcp_adapter: MCPAdapter) -> None:
        """Test async structure analysis with non-existent file"""
        with patch.object(mcp_adapter, 'engine') as mock_engine:
            mock_engine.analyze.side_effect = FileNotFoundError
            with pytest.raises(FileNotFoundError):
                await mcp_adapter.get_file_structure_async('/nonexistent/file.java')

    @pytest.mark.asyncio
    async def test_analyze_batch_async_with_mixed_files(self, mcp_adapter: MCPAdapter) -> None:
        """Test async batch analysis with mix of valid and invalid files"""
        files = []
        
        try:
            # Create valid file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False) as f:
                f.write('public class Test {}')
                files.append(f.name)
            
            # Add non-existent file
            files.append('/nonexistent/file.java')
            
            results = await mcp_adapter.analyze_batch_async(files)
            
            # Should handle gracefully, might return partial results or handle errors
            assert isinstance(results, list)
            
        finally:
            for file_path in files:
                if os.path.exists(file_path):
                    os.unlink(file_path)

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_handle_mcp_tool_request_exception(self, mcp_adapter: MCPAdapter) -> None:
        """Test MCP tool request handling with exception"""
        with patch.object(mcp_adapter, 'analyze_file_async') as mock_analyze:
            mock_analyze.side_effect = Exception("Analysis failed")
            request = {
                'tool_name': 'analyze_file',
                'arguments': {
                    'file_path': '/nonexistent/file.java'
                }
            }
            
            result = await mcp_adapter.handle_mcp_tool_request(request['tool_name'], request['arguments'])
            
            assert isinstance(result, dict)
            assert 'error' in result
            assert 'Analysis failed' in result['error']

    @pytest.mark.asyncio
    async def test_handle_mcp_resource_request_exception(self, mcp_adapter: MCPAdapter) -> None:
        """Test MCP resource request handling with exception"""
        resource_uri = 'code://file/nonexistent.java'
        
        result = await mcp_adapter.handle_mcp_resource_request(resource_uri)
        
        assert isinstance(result, dict)
        assert 'error' in result

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_analyze_file_async_engine_failure(self, mcp_adapter: MCPAdapter) -> None:
        """Test handling of analysis engine failure in async analysis"""
        with patch.object(mcp_adapter, 'engine') as mock_engine:
            mock_engine.analyze.side_effect = Exception("Engine not available")
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False) as f:
                f.write('public class Test {}')
                temp_path = f.name
            
            try:
                # Should handle engine failure gracefully
                with pytest.raises(Exception, match="Engine not available"):
                    await mcp_adapter.analyze_file_async(temp_path)
                    
            finally:
                os.unlink(temp_path)


class TestMCPServerAdapter:
    """Test cases for MCPServerAdapter class"""

    @pytest.fixture
    def mcp_server_adapter(self) -> MCPServerAdapter:
        """Create an MCPServerAdapter instance for testing"""
        return MCPServerAdapter()

    def test_mcp_server_adapter_initialization(self, mcp_server_adapter: MCPServerAdapter) -> None:
        """Test MCPServerAdapter initialization"""
        assert mcp_server_adapter is not None
        assert hasattr(mcp_server_adapter, 'mcp_adapter')
        assert isinstance(mcp_server_adapter.mcp_adapter, MCPAdapter)
        assert hasattr(mcp_server_adapter, 'handle_request')

    @pytest.mark.asyncio
    async def test_handle_request_analyze_file(self, mcp_server_adapter: MCPServerAdapter) -> None:
        """Test handling analyze_file request"""
        request = {
            'method': 'analyze_file',
            'params': {
                'file_path': 'test.java',
                'language': 'java'
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False) as f:
            f.write('public class Test {}')
            request['params']['file_path'] = f.name
        
        try:
            result = await mcp_server_adapter.handle_request(request['method'], request['params'])
            
            assert isinstance(result, dict)
            assert 'result' in result or 'error' in result
            
        finally:
            os.unlink(request['params']['file_path'])

    @pytest.mark.asyncio
    async def test_handle_request_get_structure(self, mcp_server_adapter: MCPServerAdapter) -> None:
        """Test handling get_structure request"""
        request = {
            'method': 'get_structure',
            'params': {
                'file_path': 'test.java'
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False) as f:
            f.write('public class Test {}')
            request['params']['file_path'] = f.name
        
        try:
            result = await mcp_server_adapter.handle_request(request['method'], request['params'])
            
            assert isinstance(result, dict)
            
        finally:
            os.unlink(request['params']['file_path'])

    @pytest.mark.asyncio
    async def test_handle_request_invalid_method(self, mcp_server_adapter: MCPServerAdapter) -> None:
        """Test handling request with invalid method"""
        request = {
            'method': 'invalid_method',
            'params': {}
        }
        
        result = await mcp_server_adapter.handle_request(request['method'], request.get('params'))
        
        assert isinstance(result, dict)
        assert 'error' in result

    @pytest.mark.asyncio
    async def test_handle_request_missing_params(self, mcp_server_adapter: MCPServerAdapter) -> None:
        """Test handling request with missing parameters"""
        request = {
            'method': 'analyze_file'
            # Missing params
        }
        
        result = await mcp_server_adapter.handle_request(request['method'], request.get('params'))
        
        assert isinstance(result, dict)
        assert 'error' in result


class TestMCPAdapterIntegration:
    """Integration tests for MCPAdapter"""

    @pytest.fixture
    def mcp_adapter(self) -> MCPAdapter:
        """Create an MCPAdapter instance for testing"""
        return MCPAdapter()

    @pytest.mark.asyncio
    async def test_full_async_analysis_workflow(self, mcp_adapter: MCPAdapter) -> None:
        """Test complete async analysis workflow through MCP adapter"""
        java_code = '''
package com.example;

import java.util.List;
import java.util.ArrayList;

public class DataProcessor {
    private List<String> data;
    
    public DataProcessor() {
        this.data = new ArrayList<>();
    }
    
    public void addData(String item) {
        data.add(item);
    }
    
    public List<String> processData() {
        return data.stream()
                   .map(String::toUpperCase)
                   .collect(ArrayList::new);
    }
    
    public int getDataCount() {
        return data.size();
    }
}
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False) as f:
            f.write(java_code)
            temp_path = f.name
        
        try:
            # Step 1: Analyze file
            result = await mcp_adapter.analyze_file_async(temp_path)
            assert isinstance(result, AnalysisResult)
            assert result.language == 'java'
            
            # Step 2: Get structure
            structure = await mcp_adapter.get_file_structure_async(temp_path)
            assert isinstance(structure, dict)
            
            # Step 3: Handle as MCP request
            mcp_request = {
                'file_path': temp_path,
                'language': 'java',
                'include_complexity': True
            }
            mcp_result = await mcp_adapter.analyze_with_mcp_request(mcp_request)
            assert isinstance(mcp_result, AnalysisResult)
            
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_concurrent_analysis_requests(self, mcp_adapter: MCPAdapter) -> None:
        """Test concurrent analysis requests"""
        files = []
        
        try:
            # Create multiple test files
            for i in range(3):
                with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False) as f:
                    f.write(f'public class Test{i} {{ public void method{i}() {{}} }}')
                    files.append(f.name)
            
            # Run concurrent analyses
            tasks = [mcp_adapter.analyze_file_async(file_path) for file_path in files]
            results = await asyncio.gather(*tasks)
            
            assert len(results) == 3
            assert all(isinstance(result, AnalysisResult) for result in results)
            assert all(result.language == 'java' for result in results)
            
        finally:
            for file_path in files:
                if os.path.exists(file_path):
                    os.unlink(file_path)

    @pytest.mark.asyncio
    async def test_mcp_adapter_resource_management(self, mcp_adapter: MCPAdapter) -> None:
        """Test MCP adapter resource management"""
        # Test that adapter can be used multiple times
        java_code = 'public class Test { public void method() {} }'
        
        for i in range(5):
            with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False) as f:
                f.write(java_code)
                temp_path = f.name
            
            try:
                result = await mcp_adapter.analyze_file_async(temp_path)
                assert isinstance(result, AnalysisResult)
                
            finally:
                os.unlink(temp_path)
        
        # Test cleanup
        mcp_adapter.cleanup()
        await mcp_adapter.aclose()

    @pytest.mark.asyncio
    async def test_mcp_adapter_performance_with_large_file(self, mcp_adapter: MCPAdapter) -> None:
        """Test MCP adapter performance with large code files"""
        # Create a large Java class
        large_code = 'public class LargeClass {\n'
        for i in range(100):
            large_code += f'''
    public void method{i}() {{
        System.out.println("Method {i}");
        int value = {i};
        return;
    }}
'''
        large_code += '}'
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False) as f:
            f.write(large_code)
            temp_path = f.name
        
        try:
            # Should handle large files efficiently
            result = await mcp_adapter.analyze_file_async(temp_path)
            assert isinstance(result, AnalysisResult)
            assert result.node_count > 0
            
        finally:
            os.unlink(temp_path)