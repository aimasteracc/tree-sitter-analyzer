#!/usr/bin/env python3
"""
Comprehensive tests for API module to achieve high coverage.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from tree_sitter_analyzer import api
from tree_sitter_analyzer.models import AnalysisResult


class TestAPIComprehensive:
    """Comprehensive test suite for API module"""

    def setup_method(self):
        """Set up test fixtures"""
        # Reset the global engine for each test
        api._engine = None

    def test_get_engine_singleton(self):
        """Test that get_engine returns singleton"""
        engine1 = api.get_engine()
        engine2 = api.get_engine()
        assert engine1 is engine2

    def test_get_engine_initialization(self):
        """Test engine initialization"""
        engine = api.get_engine()
        assert engine is not None
        assert hasattr(engine, 'analyze_file')

    def test_analyze_file_basic(self):
        """Test basic file analysis"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def hello(): pass')
            temp_file = f.name
        
        try:
            with patch.object(api.get_engine(), 'analyze_file') as mock_analyze:
                mock_result = AnalysisResult(
                    file_path=temp_file,
                    language="python",
                    elements={"functions": [{"name": "hello"}]}
                )
                mock_analyze.return_value = mock_result
                
                result = api.analyze_file(temp_file)
                
                assert result is not None
                assert isinstance(result, dict)
                mock_analyze.assert_called_once()
        finally:
            os.unlink(temp_file)

    def test_analyze_file_with_path_object(self):
        """Test file analysis with Path object"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def hello(): pass')
            temp_file = Path(f.name)
        
        try:
            with patch.object(api.get_engine(), 'analyze_file') as mock_analyze:
                mock_result = AnalysisResult(
                    file_path=str(temp_file),
                    language="python",
                    elements={"functions": [{"name": "hello"}]}
                )
                mock_analyze.return_value = mock_result
                
                result = api.analyze_file(temp_file)
                
                assert result is not None
                mock_analyze.assert_called_once()
        finally:
            os.unlink(temp_file)

    def test_analyze_file_with_language(self):
        """Test file analysis with explicit language"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write('def hello(): pass')
            temp_file = f.name
        
        try:
            with patch.object(api.get_engine(), 'analyze_file') as mock_analyze:
                mock_result = AnalysisResult(
                    file_path=temp_file,
                    language="python",
                    elements={"functions": [{"name": "hello"}]}
                )
                mock_analyze.return_value = mock_result
                
                result = api.analyze_file(temp_file, language="python")
                
                assert result is not None
                mock_analyze.assert_called_once()
        finally:
            os.unlink(temp_file)

    def test_analyze_file_with_queries(self):
        """Test file analysis with specific queries"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def hello(): pass')
            temp_file = f.name
        
        try:
            with patch.object(api.get_engine(), 'analyze_file') as mock_analyze:
                mock_result = AnalysisResult(
                    file_path=temp_file,
                    language="python",
                    elements={"functions": [{"name": "hello"}]}
                )
                mock_analyze.return_value = mock_result
                
                result = api.analyze_file(temp_file, queries=["functions"])
                
                assert result is not None
                mock_analyze.assert_called_once()
        finally:
            os.unlink(temp_file)

    def test_analyze_file_with_all_options(self):
        """Test file analysis with all options"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def hello(): pass')
            temp_file = f.name
        
        try:
            with patch.object(api.get_engine(), 'analyze_file') as mock_analyze:
                mock_result = AnalysisResult(
                    file_path=temp_file,
                    language="python",
                    elements={"functions": [{"name": "hello"}]}
                )
                mock_analyze.return_value = mock_result
                
                result = api.analyze_file(
                    temp_file,
                    language="python",
                    queries=["functions", "classes"],
                    include_elements=True,
                    include_details=True,
                    include_queries=True,
                    include_complexity=True
                )
                
                assert result is not None
                mock_analyze.assert_called_once()
        finally:
            os.unlink(temp_file)

    def test_analyze_file_error_handling(self):
        """Test file analysis error handling"""
        with patch.object(api.get_engine(), 'analyze_file') as mock_analyze:
            mock_analyze.side_effect = Exception("Analysis failed")
            
            result = api.analyze_file("nonexistent.py")
            
            assert result is not None
            assert isinstance(result, dict)
            assert "error" in result

    def test_analyze_code_basic(self):
        """Test basic code analysis"""
        code = "def hello(): pass"
        
        with patch.object(api.get_engine(), 'analyze_code') as mock_analyze:
            mock_result = AnalysisResult(
                file_path="<string>",
                language="python",
                elements={"functions": [{"name": "hello"}]}
            )
            mock_analyze.return_value = mock_result
            
            result = api.analyze_code(code, "python")
            
            assert result is not None
            assert isinstance(result, dict)
            mock_analyze.assert_called_once()

    def test_analyze_code_with_filename(self):
        """Test code analysis with filename"""
        code = "def hello(): pass"
        
        with patch.object(api.get_engine(), 'analyze_code') as mock_analyze:
            mock_result = AnalysisResult(
                file_path="test.py",
                language="python",
                elements={"functions": [{"name": "hello"}]}
            )
            mock_analyze.return_value = mock_result
            
            result = api.analyze_code(code, "python", filename="test.py")
            
            assert result is not None
            mock_analyze.assert_called_once()

    def test_analyze_code_with_all_options(self):
        """Test code analysis with all options"""
        code = "def hello(): pass"
        
        with patch.object(api.get_engine(), 'analyze_code') as mock_analyze:
            mock_result = AnalysisResult(
                file_path="test.py",
                language="python",
                elements={"functions": [{"name": "hello"}]}
            )
            mock_analyze.return_value = mock_result
            
            result = api.analyze_code(
                code,
                "python",
                filename="test.py",
                queries=["functions"],
                include_elements=True,
                include_details=True,
                include_queries=True,
                include_complexity=True
            )
            
            assert result is not None
            mock_analyze.assert_called_once()

    def test_analyze_code_error_handling(self):
        """Test code analysis error handling"""
        with patch.object(api.get_engine(), 'analyze_code') as mock_analyze:
            mock_analyze.side_effect = Exception("Analysis failed")
            
            result = api.analyze_code("invalid code", "python")
            
            assert result is not None
            assert isinstance(result, dict)
            assert "error" in result

    def test_extract_elements_basic(self):
        """Test basic element extraction"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def hello(): pass')
            temp_file = f.name
        
        try:
            with patch.object(api.get_engine(), 'extract_elements') as mock_extract:
                mock_result = AnalysisResult(
                    file_path=temp_file,
                    language="python",
                    elements={"functions": [{"name": "hello"}]}
                )
                mock_extract.return_value = mock_result
                
                result = api.extract_elements(temp_file)
                
                assert result is not None
                assert isinstance(result, dict)
                mock_extract.assert_called_once()
        finally:
            os.unlink(temp_file)

    def test_extract_elements_with_options(self):
        """Test element extraction with options"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def hello(): pass')
            temp_file = f.name
        
        try:
            with patch.object(api.get_engine(), 'extract_elements') as mock_extract:
                mock_result = AnalysisResult(
                    file_path=temp_file,
                    language="python",
                    elements={"functions": [{"name": "hello"}]}
                )
                mock_extract.return_value = mock_result
                
                result = api.extract_elements(
                    temp_file,
                    language="python",
                    element_types=["functions", "classes"]
                )
                
                assert result is not None
                mock_extract.assert_called_once()
        finally:
            os.unlink(temp_file)

    def test_extract_elements_error_handling(self):
        """Test element extraction error handling"""
        with patch.object(api.get_engine(), 'extract_elements') as mock_extract:
            mock_extract.side_effect = Exception("Extraction failed")
            
            result = api.extract_elements("nonexistent.py")
            
            assert result is not None
            assert isinstance(result, dict)
            assert "error" in result

    def test_execute_query_basic(self):
        """Test basic query execution"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def hello(): pass')
            temp_file = f.name
        
        try:
            with patch.object(api.get_engine(), 'execute_query') as mock_query:
                mock_result = {"matches": [{"name": "hello"}]}
                mock_query.return_value = mock_result
                
                result = api.execute_query(temp_file, "functions")
                
                assert result is not None
                assert isinstance(result, dict)
                mock_query.assert_called_once()
        finally:
            os.unlink(temp_file)

    def test_execute_query_with_options(self):
        """Test query execution with options"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def hello(): pass')
            temp_file = f.name
        
        try:
            with patch.object(api.get_engine(), 'execute_query') as mock_query:
                mock_result = {"matches": [{"name": "hello"}]}
                mock_query.return_value = mock_result
                
                result = api.execute_query(
                    temp_file,
                    "functions",
                    language="python",
                    query_string="(function_definition) @func"
                )
                
                assert result is not None
                mock_query.assert_called_once()
        finally:
            os.unlink(temp_file)

    def test_execute_query_error_handling(self):
        """Test query execution error handling"""
        with patch.object(api.get_engine(), 'execute_query') as mock_query:
            mock_query.side_effect = Exception("Query failed")
            
            result = api.execute_query("nonexistent.py", "functions")
            
            assert result is not None
            assert isinstance(result, dict)
            assert "error" in result

    def test_get_supported_languages(self):
        """Test getting supported languages"""
        with patch.object(api.get_engine(), 'get_supported_languages') as mock_langs:
            mock_langs.return_value = ["python", "java", "javascript"]
            
            result = api.get_supported_languages()
            
            assert result is not None
            assert isinstance(result, list)
            assert "python" in result
            mock_langs.assert_called_once()

    def test_get_supported_languages_error_handling(self):
        """Test getting supported languages error handling"""
        with patch.object(api.get_engine(), 'get_supported_languages') as mock_langs:
            mock_langs.side_effect = Exception("Failed to get languages")
            
            result = api.get_supported_languages()
            
            assert result is not None
            assert isinstance(result, list)
            assert len(result) == 0

    def test_get_available_queries(self):
        """Test getting available queries"""
        with patch.object(api.get_engine(), 'get_available_queries') as mock_queries:
            mock_queries.return_value = ["functions", "classes", "variables"]
            
            result = api.get_available_queries("python")
            
            assert result is not None
            assert isinstance(result, list)
            assert "functions" in result
            mock_queries.assert_called_once_with("python")

    def test_get_available_queries_error_handling(self):
        """Test getting available queries error handling"""
        with patch.object(api.get_engine(), 'get_available_queries') as mock_queries:
            mock_queries.side_effect = Exception("Failed to get queries")
            
            result = api.get_available_queries("python")
            
            assert result is not None
            assert isinstance(result, list)
            assert len(result) == 0

    def test_validate_file_exists(self):
        """Test file validation for existing file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def hello(): pass')
            temp_file = f.name
        
        try:
            result = api.validate_file(temp_file)
            assert result is True
        finally:
            os.unlink(temp_file)

    def test_validate_file_not_exists(self):
        """Test file validation for non-existing file"""
        result = api.validate_file("nonexistent.py")
        assert result is False

    def test_validate_file_with_path_object(self):
        """Test file validation with Path object"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def hello(): pass')
            temp_file = Path(f.name)
        
        try:
            result = api.validate_file(temp_file)
            assert result is True
        finally:
            os.unlink(temp_file)

    def test_detect_language_by_extension(self):
        """Test language detection by file extension"""
        with patch.object(api.get_engine(), 'detect_language') as mock_detect:
            mock_detect.return_value = "python"
            
            result = api.detect_language("test.py")
            
            assert result == "python"
            mock_detect.assert_called_once_with("test.py")

    def test_detect_language_by_content(self):
        """Test language detection by content"""
        with patch.object(api.get_engine(), 'detect_language') as mock_detect:
            mock_detect.return_value = "python"
            
            result = api.detect_language("test.txt", content="def hello(): pass")
            
            assert result == "python"
            mock_detect.assert_called_once_with("test.txt", content="def hello(): pass")

    def test_detect_language_error_handling(self):
        """Test language detection error handling"""
        with patch.object(api.get_engine(), 'detect_language') as mock_detect:
            mock_detect.side_effect = Exception("Detection failed")
            
            result = api.detect_language("test.py")
            
            assert result is None

    def test_clear_cache(self):
        """Test cache clearing"""
        with patch.object(api.get_engine(), 'clear_cache') as mock_clear:
            api.clear_cache()
            mock_clear.assert_called_once()

    def test_clear_cache_error_handling(self):
        """Test cache clearing error handling"""
        with patch.object(api.get_engine(), 'clear_cache') as mock_clear:
            mock_clear.side_effect = Exception("Clear failed")
            
            # Should not raise exception
            api.clear_cache()

    def test_get_cache_stats(self):
        """Test getting cache statistics"""
        with patch.object(api.get_engine(), 'get_cache_stats') as mock_stats:
            mock_stats.return_value = {"hits": 10, "misses": 5}
            
            result = api.get_cache_stats()
            
            assert result is not None
            assert isinstance(result, dict)
            assert "hits" in result
            mock_stats.assert_called_once()

    def test_get_cache_stats_error_handling(self):
        """Test getting cache statistics error handling"""
        with patch.object(api.get_engine(), 'get_cache_stats') as mock_stats:
            mock_stats.side_effect = Exception("Stats failed")
            
            result = api.get_cache_stats()
            
            assert result is not None
            assert isinstance(result, dict)
            assert len(result) == 0

    def test_result_to_dict_conversion(self):
        """Test AnalysisResult to dict conversion"""
        mock_result = AnalysisResult(
            file_path="test.py",
            language="python",
            elements={"functions": [{"name": "hello"}]}
        )
        
        with patch.object(api.get_engine(), 'analyze_file') as mock_analyze:
            mock_analyze.return_value = mock_result
            
            result = api.analyze_file("test.py")
            
            assert isinstance(result, dict)
            assert "file_path" in result
            assert "language" in result
            assert "elements" in result

    def test_error_response_format(self):
        """Test error response format"""
        with patch.object(api.get_engine(), 'analyze_file') as mock_analyze:
            mock_analyze.side_effect = Exception("Test error")
            
            result = api.analyze_file("test.py")
            
            assert isinstance(result, dict)
            assert "error" in result
            assert "success" in result
            assert result["success"] is False

    def test_concurrent_api_calls(self):
        """Test concurrent API calls"""
        import threading
        
        results = []
        errors = []
        
        def worker():
            try:
                with patch.object(api.get_engine(), 'analyze_file') as mock_analyze:
                    mock_result = AnalysisResult(
                        file_path="test.py",
                        language="python",
                        elements={"functions": []}
                    )
                    mock_analyze.return_value = mock_result
                    
                    result = api.analyze_file("test.py")
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
        assert all(isinstance(result, dict) for result in results)

    def test_api_with_large_files(self):
        """Test API with large files"""
        large_code = "def func_{}(): pass\n" * 1000
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(large_code)
            temp_file = f.name
        
        try:
            with patch.object(api.get_engine(), 'analyze_file') as mock_analyze:
                mock_result = AnalysisResult(
                    file_path=temp_file,
                    language="python",
                    elements={"functions": [{"name": f"func_{i}"} for i in range(1000)]}
                )
                mock_analyze.return_value = mock_result
                
                result = api.analyze_file(temp_file)
                
                assert result is not None
                assert isinstance(result, dict)
                mock_analyze.assert_called_once()
        finally:
            os.unlink(temp_file)

    def test_api_with_unicode_content(self):
        """Test API with unicode content"""
        unicode_code = "def 测试函数(): pass\n# 这是注释"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(unicode_code)
            temp_file = f.name
        
        try:
            with patch.object(api.get_engine(), 'analyze_file') as mock_analyze:
                mock_result = AnalysisResult(
                    file_path=temp_file,
                    language="python",
                    elements={"functions": [{"name": "测试函数"}]}
                )
                mock_analyze.return_value = mock_result
                
                result = api.analyze_file(temp_file)
                
                assert result is not None
                assert isinstance(result, dict)
                mock_analyze.assert_called_once()
        finally:
            os.unlink(temp_file)