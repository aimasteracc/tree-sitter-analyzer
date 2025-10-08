#!/usr/bin/env python3
"""
Comprehensive tests for universal analyze tool to achieve high coverage.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from tree_sitter_analyzer.mcp.tools.universal_analyze_tool import UniversalAnalyzeTool
from tree_sitter_analyzer.models import AnalysisResult


class TestUniversalAnalyzeToolComprehensive:
    """Comprehensive test suite for universal analyze tool"""

    def setup_method(self):
        """Set up test fixtures"""
        self.tool = UniversalAnalyzeTool()

    def test_init_default(self):
        """Test default initialization"""
        assert self.tool.project_root is None
        assert hasattr(self.tool, 'analysis_engine')
        assert hasattr(self.tool, 'validator')

    def test_init_with_project_root(self):
        """Test initialization with project root"""
        tool = UniversalAnalyzeTool(project_root="/test/path")
        assert tool.project_root == "/test/path"

    def test_get_name(self):
        """Test getting tool name"""
        assert self.tool.get_name() == "universal_analyze"

    def test_get_description(self):
        """Test getting tool description"""
        description = self.tool.get_description()
        assert "Universal code analysis" in description
        assert "file_path" in description

    def test_get_input_schema(self):
        """Test getting input schema"""
        schema = self.tool.get_input_schema()
        assert "type" in schema
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "file_path" in schema["properties"]
        assert "required" in schema
        assert "file_path" in schema["required"]

    def test_execute_success(self):
        """Test successful execution"""
        # Mock analysis engine
        mock_result = AnalysisResult(
            file_path="test.py",
            language="python",
            elements={
                "functions": [{"name": "test_func", "line_number": 1}],
                "classes": [{"name": "TestClass", "line_number": 5}]
            }
        )
        
        with patch.object(self.tool.analysis_engine, 'analyze_file', return_value=mock_result):
            with patch.object(self.tool.validator, 'validate_file_path'):
                result = self.tool.execute({"file_path": "test.py"})
                
                assert result["success"] is True
                assert "analysis" in result
                assert result["analysis"]["file_path"] == "test.py"
                assert result["analysis"]["language"] == "python"

    def test_execute_with_nonexistent_file(self):
        """Test execution with nonexistent file"""
        with patch('os.path.exists', return_value=False):
            result = self.tool.execute({"file_path": "nonexistent.py"})
            
            assert result["success"] is False
            assert "error" in result
            assert "not found" in result["error"]

    def test_execute_with_validation_error(self):
        """Test execution with validation error"""
        from tree_sitter_analyzer.exceptions import SecurityError
        
        with patch.object(self.tool.validator, 'validate_file_path', side_effect=SecurityError("Invalid path")):
            result = self.tool.execute({"file_path": "../../../etc/passwd"})
            
            assert result["success"] is False
            assert "error" in result
            assert "Invalid path" in result["error"]

    def test_execute_with_analysis_error(self):
        """Test execution with analysis error"""
        with patch.object(self.tool.analysis_engine, 'analyze_file', side_effect=Exception("Analysis failed")):
            with patch.object(self.tool.validator, 'validate_file_path'):
                with patch('os.path.exists', return_value=True):
                    result = self.tool.execute({"file_path": "test.py"})
                    
                    assert result["success"] is False
                    assert "error" in result
                    assert "Analysis failed" in result["error"]

    def test_execute_with_missing_file_path(self):
        """Test execution with missing file_path parameter"""
        result = self.tool.execute({})
        
        assert result["success"] is False
        assert "error" in result
        assert "file_path" in result["error"]

    def test_execute_with_empty_file_path(self):
        """Test execution with empty file_path"""
        result = self.tool.execute({"file_path": ""})
        
        assert result["success"] is False
        assert "error" in result

    def test_execute_with_none_file_path(self):
        """Test execution with None file_path"""
        result = self.tool.execute({"file_path": None})
        
        assert result["success"] is False
        assert "error" in result

    def test_execute_with_language_parameter(self):
        """Test execution with explicit language parameter"""
        mock_result = AnalysisResult(
            file_path="test.js",
            language="javascript",
            elements={"functions": []}
        )
        
        with patch.object(self.tool.analysis_engine, 'analyze_file', return_value=mock_result):
            with patch.object(self.tool.validator, 'validate_file_path'):
                with patch('os.path.exists', return_value=True):
                    result = self.tool.execute({
                        "file_path": "test.js",
                        "language": "javascript"
                    })
                    
                    assert result["success"] is True
                    assert result["analysis"]["language"] == "javascript"

    def test_execute_with_query_parameter(self):
        """Test execution with query parameter"""
        mock_result = AnalysisResult(
            file_path="test.py",
            language="python",
            elements={"functions": [{"name": "test_func"}]}
        )
        
        with patch.object(self.tool.analysis_engine, 'analyze_file', return_value=mock_result):
            with patch.object(self.tool.validator, 'validate_file_path'):
                with patch('os.path.exists', return_value=True):
                    result = self.tool.execute({
                        "file_path": "test.py",
                        "query": "functions"
                    })
                    
                    assert result["success"] is True

    def test_execute_with_include_source_parameter(self):
        """Test execution with include_source parameter"""
        mock_result = AnalysisResult(
            file_path="test.py",
            language="python",
            elements={"functions": []},
            source_code="def test(): pass"
        )
        
        with patch.object(self.tool.analysis_engine, 'analyze_file', return_value=mock_result):
            with patch.object(self.tool.validator, 'validate_file_path'):
                with patch('os.path.exists', return_value=True):
                    result = self.tool.execute({
                        "file_path": "test.py",
                        "include_source": True
                    })
                    
                    assert result["success"] is True
                    assert "source_code" in result["analysis"]

    def test_execute_with_format_parameter(self):
        """Test execution with format parameter"""
        mock_result = AnalysisResult(
            file_path="test.py",
            language="python",
            elements={"functions": []}
        )
        
        with patch.object(self.tool.analysis_engine, 'analyze_file', return_value=mock_result):
            with patch.object(self.tool.validator, 'validate_file_path'):
                with patch('os.path.exists', return_value=True):
                    result = self.tool.execute({
                        "file_path": "test.py",
                        "format": "compact"
                    })
                    
                    assert result["success"] is True

    def test_execute_with_max_depth_parameter(self):
        """Test execution with max_depth parameter"""
        mock_result = AnalysisResult(
            file_path="test.py",
            language="python",
            elements={"functions": []}
        )
        
        with patch.object(self.tool.analysis_engine, 'analyze_file', return_value=mock_result):
            with patch.object(self.tool.validator, 'validate_file_path'):
                with patch('os.path.exists', return_value=True):
                    result = self.tool.execute({
                        "file_path": "test.py",
                        "max_depth": 5
                    })
                    
                    assert result["success"] is True

    def test_execute_with_include_comments_parameter(self):
        """Test execution with include_comments parameter"""
        mock_result = AnalysisResult(
            file_path="test.py",
            language="python",
            elements={"functions": [], "comments": []}
        )
        
        with patch.object(self.tool.analysis_engine, 'analyze_file', return_value=mock_result):
            with patch.object(self.tool.validator, 'validate_file_path'):
                with patch('os.path.exists', return_value=True):
                    result = self.tool.execute({
                        "file_path": "test.py",
                        "include_comments": True
                    })
                    
                    assert result["success"] is True

    def test_execute_with_all_parameters(self):
        """Test execution with all parameters"""
        mock_result = AnalysisResult(
            file_path="test.py",
            language="python",
            elements={"functions": [], "classes": [], "comments": []},
            source_code="# Test file\ndef test(): pass"
        )
        
        with patch.object(self.tool.analysis_engine, 'analyze_file', return_value=mock_result):
            with patch.object(self.tool.validator, 'validate_file_path'):
                with patch('os.path.exists', return_value=True):
                    result = self.tool.execute({
                        "file_path": "test.py",
                        "language": "python",
                        "query": "functions,classes",
                        "include_source": True,
                        "format": "full",
                        "max_depth": 10,
                        "include_comments": True
                    })
                    
                    assert result["success"] is True
                    assert result["analysis"]["language"] == "python"
                    assert "source_code" in result["analysis"]

    def test_execute_with_binary_file(self):
        """Test execution with binary file"""
        with patch('os.path.exists', return_value=True):
            with patch.object(self.tool.validator, 'validate_file_path'):
                with patch.object(self.tool.analysis_engine, 'analyze_file', side_effect=UnicodeDecodeError('utf-8', b'', 0, 1, 'invalid')):
                    result = self.tool.execute({"file_path": "binary.exe"})
                    
                    assert result["success"] is False
                    assert "error" in result

    def test_execute_with_large_file(self):
        """Test execution with large file"""
        mock_result = AnalysisResult(
            file_path="large.py",
            language="python",
            elements={"functions": [f"func_{i}" for i in range(1000)]}
        )
        
        with patch.object(self.tool.analysis_engine, 'analyze_file', return_value=mock_result):
            with patch.object(self.tool.validator, 'validate_file_path'):
                with patch('os.path.exists', return_value=True):
                    result = self.tool.execute({"file_path": "large.py"})
                    
                    assert result["success"] is True
                    assert len(result["analysis"]["elements"]["functions"]) == 1000

    def test_execute_with_permission_error(self):
        """Test execution with permission error"""
        with patch('os.path.exists', return_value=True):
            with patch.object(self.tool.validator, 'validate_file_path'):
                with patch.object(self.tool.analysis_engine, 'analyze_file', side_effect=PermissionError("Permission denied")):
                    result = self.tool.execute({"file_path": "protected.py"})
                    
                    assert result["success"] is False
                    assert "error" in result
                    assert "Permission denied" in result["error"]

    def test_execute_with_timeout_error(self):
        """Test execution with timeout error"""
        with patch('os.path.exists', return_value=True):
            with patch.object(self.tool.validator, 'validate_file_path'):
                with patch.object(self.tool.analysis_engine, 'analyze_file', side_effect=TimeoutError("Analysis timeout")):
                    result = self.tool.execute({"file_path": "slow.py"})
                    
                    assert result["success"] is False
                    assert "error" in result

    def test_execute_with_memory_error(self):
        """Test execution with memory error"""
        with patch('os.path.exists', return_value=True):
            with patch.object(self.tool.validator, 'validate_file_path'):
                with patch.object(self.tool.analysis_engine, 'analyze_file', side_effect=MemoryError("Out of memory")):
                    result = self.tool.execute({"file_path": "huge.py"})
                    
                    assert result["success"] is False
                    assert "error" in result

    def test_execute_with_invalid_syntax_file(self):
        """Test execution with file containing invalid syntax"""
        mock_result = AnalysisResult(
            file_path="invalid.py",
            language="python",
            elements={"functions": []},
            errors=["Syntax error at line 5"]
        )
        
        with patch.object(self.tool.analysis_engine, 'analyze_file', return_value=mock_result):
            with patch.object(self.tool.validator, 'validate_file_path'):
                with patch('os.path.exists', return_value=True):
                    result = self.tool.execute({"file_path": "invalid.py"})
                    
                    assert result["success"] is True
                    assert "errors" in result["analysis"]

    def test_execute_with_unicode_file(self):
        """Test execution with unicode file"""
        mock_result = AnalysisResult(
            file_path="unicode.py",
            language="python",
            elements={"functions": [{"name": "测试函数", "line_number": 1}]},
            source_code="def 测试函数(): pass  # 这是一个测试函数"
        )
        
        with patch.object(self.tool.analysis_engine, 'analyze_file', return_value=mock_result):
            with patch.object(self.tool.validator, 'validate_file_path'):
                with patch('os.path.exists', return_value=True):
                    result = self.tool.execute({
                        "file_path": "unicode.py",
                        "include_source": True
                    })
                    
                    assert result["success"] is True
                    assert "测试函数" in str(result["analysis"])

    def test_execute_with_different_file_types(self):
        """Test execution with different file types"""
        file_types = [
            ("test.py", "python"),
            ("test.js", "javascript"),
            ("test.java", "java"),
            ("test.ts", "typescript"),
            ("test.cpp", "cpp"),
            ("test.c", "c")
        ]
        
        for file_path, language in file_types:
            mock_result = AnalysisResult(
                file_path=file_path,
                language=language,
                elements={"functions": []}
            )
            
            with patch.object(self.tool.analysis_engine, 'analyze_file', return_value=mock_result):
                with patch.object(self.tool.validator, 'validate_file_path'):
                    with patch('os.path.exists', return_value=True):
                        result = self.tool.execute({"file_path": file_path})
                        
                        assert result["success"] is True
                        assert result["analysis"]["language"] == language

    def test_execute_with_project_root_validation(self):
        """Test execution with project root validation"""
        tool = UniversalAnalyzeTool(project_root="/project")
        
        mock_result = AnalysisResult(
            file_path="/project/test.py",
            language="python",
            elements={"functions": []}
        )
        
        with patch.object(tool.analysis_engine, 'analyze_file', return_value=mock_result):
            with patch.object(tool.validator, 'validate_file_path'):
                with patch('os.path.exists', return_value=True):
                    result = tool.execute({"file_path": "/project/test.py"})
                    
                    assert result["success"] is True

    def test_execute_with_relative_path(self):
        """Test execution with relative path"""
        mock_result = AnalysisResult(
            file_path="./test.py",
            language="python",
            elements={"functions": []}
        )
        
        with patch.object(self.tool.analysis_engine, 'analyze_file', return_value=mock_result):
            with patch.object(self.tool.validator, 'validate_file_path'):
                with patch('os.path.exists', return_value=True):
                    result = self.tool.execute({"file_path": "./test.py"})
                    
                    assert result["success"] is True

    def test_execute_with_symlink(self):
        """Test execution with symlink"""
        mock_result = AnalysisResult(
            file_path="link.py",
            language="python",
            elements={"functions": []}
        )
        
        with patch.object(self.tool.analysis_engine, 'analyze_file', return_value=mock_result):
            with patch.object(self.tool.validator, 'validate_file_path'):
                with patch('os.path.exists', return_value=True):
                    with patch('os.path.islink', return_value=True):
                        result = self.tool.execute({"file_path": "link.py"})
                        
                        assert result["success"] is True

    def test_execute_performance_monitoring(self):
        """Test execution with performance monitoring"""
        mock_result = AnalysisResult(
            file_path="test.py",
            language="python",
            elements={"functions": []}
        )
        
        with patch.object(self.tool.analysis_engine, 'analyze_file', return_value=mock_result):
            with patch.object(self.tool.validator, 'validate_file_path'):
                with patch('os.path.exists', return_value=True):
                    with patch('time.time', side_effect=[0.0, 1.5]):  # Mock 1.5 second execution
                        result = self.tool.execute({"file_path": "test.py"})
                        
                        assert result["success"] is True
                        # Performance info might be included in result
                        assert "analysis" in result

    def test_execute_with_caching(self):
        """Test execution with caching behavior"""
        mock_result = AnalysisResult(
            file_path="test.py",
            language="python",
            elements={"functions": []}
        )
        
        with patch.object(self.tool.analysis_engine, 'analyze_file', return_value=mock_result) as mock_analyze:
            with patch.object(self.tool.validator, 'validate_file_path'):
                with patch('os.path.exists', return_value=True):
                    # First call
                    result1 = self.tool.execute({"file_path": "test.py"})
                    # Second call
                    result2 = self.tool.execute({"file_path": "test.py"})
                    
                    assert result1["success"] is True
                    assert result2["success"] is True
                    # Analysis engine should be called for each request
                    assert mock_analyze.call_count == 2

    def test_execute_concurrent_requests(self):
        """Test concurrent execution requests"""
        import threading
        import time
        
        mock_result = AnalysisResult(
            file_path="test.py",
            language="python",
            elements={"functions": []}
        )
        
        results = []
        errors = []
        
        def worker():
            try:
                with patch.object(self.tool.analysis_engine, 'analyze_file', return_value=mock_result):
                    with patch.object(self.tool.validator, 'validate_file_path'):
                        with patch('os.path.exists', return_value=True):
                            result = self.tool.execute({"file_path": "test.py"})
                            results.append(result)
            except Exception as e:
                errors.append(e)
        
        # Create multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=worker)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        # Check results
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 5
        assert all(result["success"] for result in results)

    def test_execute_error_handling_edge_cases(self):
        """Test error handling edge cases"""
        # Test with None arguments
        result = self.tool.execute(None)
        assert result["success"] is False
        
        # Test with invalid argument types
        result = self.tool.execute("invalid")
        assert result["success"] is False
        
        # Test with missing required fields
        result = self.tool.execute({"invalid_field": "value"})
        assert result["success"] is False

    def test_execute_result_serialization(self):
        """Test result serialization"""
        mock_result = AnalysisResult(
            file_path="test.py",
            language="python",
            elements={
                "functions": [
                    {"name": "test_func", "line_number": 1, "parameters": ["param1", "param2"]},
                    {"name": "another_func", "line_number": 5, "complexity": 3}
                ],
                "classes": [
                    {"name": "TestClass", "line_number": 10, "methods": [], "fields": []}
                ]
            },
            metadata={"file_size": 1024, "encoding": "utf-8"}
        )
        
        with patch.object(self.tool.analysis_engine, 'analyze_file', return_value=mock_result):
            with patch.object(self.tool.validator, 'validate_file_path'):
                with patch('os.path.exists', return_value=True):
                    result = self.tool.execute({"file_path": "test.py"})
                    
                    assert result["success"] is True
                    
                    # Check that result is JSON serializable
                    import json
                    json_str = json.dumps(result)
                    parsed = json.loads(json_str)
                    assert parsed["success"] is True
                    assert "analysis" in parsed

    def test_tool_integration_with_mcp_server(self):
        """Test tool integration with MCP server"""
        # This tests the tool's compatibility with MCP server interface
        
        # Test schema validation
        schema = self.tool.get_input_schema()
        assert "properties" in schema
        assert "file_path" in schema["properties"]
        
        # Test name and description
        assert isinstance(self.tool.get_name(), str)
        assert isinstance(self.tool.get_description(), str)
        
        # Test execution returns proper format
        result = self.tool.execute({"file_path": ""})  # Invalid input
        assert isinstance(result, dict)
        assert "success" in result