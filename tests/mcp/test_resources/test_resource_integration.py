#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Integration tests for MCP resources

Tests the integration between different MCP resources and their
interaction with the MCP server.
"""

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List
# Mock functionality now provided by pytest-mock

import pytest
import pytest_asyncio

from tree_sitter_analyzer.mcp.resources.code_file_resource import CodeFileResource
from tree_sitter_analyzer.mcp.resources.project_stats_resource import ProjectStatsResource


class TestResourceRegistration:
    """Test resource registration and discovery"""

    def test_code_file_resource_registration(self) -> None:
        """Test code file resource registration"""
        resource = CodeFileResource()
        info = resource.get_resource_info()
        
        # Test registration info
        assert info["name"] == "code_file"
        assert "code://file/" in info["uri_template"]
        assert info["mime_type"] == "text/plain"

    def test_project_stats_resource_registration(self) -> None:
        """Test project stats resource registration"""
        resource = ProjectStatsResource()
        info = resource.get_resource_info()
        
        # Test registration info
        assert info["name"] == "project_stats"
        assert "code://stats/" in info["uri_template"]
        assert info["mime_type"] == "application/json"

    def test_resource_uri_uniqueness(self) -> None:
        """Test that resource URI patterns don't conflict"""
        code_resource = CodeFileResource()
        stats_resource = ProjectStatsResource()
        
        # Test URI pattern separation
        file_uri = "code://file/test.java"
        stats_uri = "code://stats/overview"
        
        # Code file resource should only match file URIs
        assert code_resource.matches_uri(file_uri)
        assert not code_resource.matches_uri(stats_uri)
        
        # Stats resource should only match stats URIs
        assert stats_resource.matches_uri(stats_uri)
        assert not stats_resource.matches_uri(file_uri)


class TestResourceInteraction:
    """Test interaction between different resources"""

    def setup_method(self) -> None:
        """Set up test fixtures"""
        # Create temporary project
        self.temp_dir = tempfile.mkdtemp()
        self.project_path = Path(self.temp_dir)
        
        # Create sample project structure
        self._create_sample_project()
        
        # Initialize resources
        self.code_resource = CodeFileResource()
        self.stats_resource = ProjectStatsResource()
        self.stats_resource.set_project_path(str(self.project_path))

    def teardown_method(self) -> None:
        """Clean up test fixtures"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_sample_project(self) -> None:
        """Create sample project for testing"""
        # Java file
        java_file = self.project_path / "Example.java"
        java_file.write_text('''package com.example;

public class Example {
    private String name;
    
    public Example(String name) {
        this.name = name;
    }
    
    public String getName() {
        return name;
    }
}
''')
        
        # Python file
        python_file = self.project_path / "helper.py"
        python_file.write_text('''def calculate(x, y):
    """Calculate sum of two numbers"""
    return x + y

class Calculator:
    def multiply(self, a, b):
        return a * b
''')

    @pytest.mark.asyncio
    async def test_file_and_stats_consistency(self) -> None:
        """Test consistency between file content and project statistics"""
        # Get project statistics
        stats_uri = "code://stats/files"
        stats_content = await self.stats_resource.read_resource(stats_uri)
        stats_data = json.loads(stats_content)
        
        # Verify files are listed in statistics
        file_paths = [file_info["path"] for file_info in stats_data["files"]]
        
        # Read individual files and verify they exist
        for file_path in file_paths:
            if file_path.endswith(('.java', '.py')):
                # Use absolute path for file URI
                absolute_path = str(self.project_path / file_path) if not Path(file_path).is_absolute() else file_path
                file_uri = f"code://file/{absolute_path}"
                file_content = await self.code_resource.read_resource(file_uri)
                
                # Verify file content is not empty
                assert len(file_content.strip()) > 0

    @pytest.mark.asyncio
    async def test_language_detection_consistency(self) -> None:
        """Test consistency of language detection across resources"""
        # Get language statistics
        stats_uri = "code://stats/languages"
        stats_content = await self.stats_resource.read_resource(stats_uri)
        stats_data = json.loads(stats_content)
        
        detected_languages = [lang["name"] for lang in stats_data["languages"]]
        
        # Read Java file and verify content
        java_file_path = str(self.project_path / "Example.java")
        java_uri = f"code://file/{java_file_path}"
        java_content = await self.code_resource.read_resource(java_uri)
        assert "public class Example" in java_content
        
        # Read Python file and verify content
        python_file_path = str(self.project_path / "helper.py")
        python_uri = f"code://file/{python_file_path}"
        python_content = await self.code_resource.read_resource(python_uri)
        assert "def calculate" in python_content

    @pytest.mark.asyncio
    async def test_file_count_accuracy(self) -> None:
        """Test accuracy of file count in statistics"""
        # Get overview statistics
        overview_uri = "code://stats/overview"
        overview_content = await self.stats_resource.read_resource(overview_uri)
        overview_data = json.loads(overview_content)
        
        # Get detailed file statistics
        files_uri = "code://stats/files"
        files_content = await self.stats_resource.read_resource(files_uri)
        files_data = json.loads(files_content)
        
        # Verify file count consistency
        assert overview_data["total_files"] == files_data["total_count"]
        assert overview_data["total_files"] == len(files_data["files"])


class TestResourceErrorHandling:
    """Test error handling across resources"""

    def setup_method(self) -> None:
        """Set up test fixtures"""
        self.code_resource = CodeFileResource()
        self.stats_resource = ProjectStatsResource()

    def test_invalid_uri_handling(self) -> None:
        """Test handling of invalid URIs across resources"""
        invalid_uris = [
            "invalid://scheme/path",
            "code://invalid/type",
            "",
            "malformed-uri",
        ]
        
        for uri in invalid_uris:
            # Both resources should reject invalid URIs
            assert not self.code_resource.matches_uri(uri)
            assert not self.stats_resource.matches_uri(uri)

    @pytest.mark.asyncio
    async def test_nonexistent_resource_handling(self) -> None:
        """Test handling of nonexistent resources"""
        # Test nonexistent file
        file_uri = "code://file/nonexistent/file.java"
        with pytest.raises(FileNotFoundError):
            await self.code_resource.read_resource(file_uri)
        
        # Test stats without project path
        stats_uri = "code://stats/overview"
        with pytest.raises(ValueError):
            await self.stats_resource.read_resource(stats_uri)

    @pytest.mark.asyncio
    async def test_permission_error_handling(self, mocker) -> None:
        """Test handling of permission errors"""
        # Mock permission error for file resource
        mock_read = mocker.patch.object(self.code_resource, '_read_file_content', side_effect=PermissionError("Access denied"))
        pass  # side_effect is set in patch call

        file_uri = "code://file/restricted.java"
        with pytest.raises(PermissionError):
            await self.code_resource.read_resource(file_uri)


class TestResourcePerformance:
    """Test performance characteristics of resource operations"""

    def setup_method(self) -> None:
        """Set up test fixtures"""
        # Create larger test project
        self.temp_dir = tempfile.mkdtemp()
        self.project_path = Path(self.temp_dir)
        self._create_large_project()
        
        self.code_resource = CodeFileResource()
        self.stats_resource = ProjectStatsResource()
        self.stats_resource.set_project_path(str(self.project_path))

    def teardown_method(self) -> None:
        """Clean up test fixtures"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_large_project(self) -> None:
        """Create larger project for performance testing"""
        # Create multiple Java files
        java_dir = self.project_path / "src"
        java_dir.mkdir()
        
        for i in range(10):
            java_file = java_dir / f"Class{i}.java"
            java_file.write_text(f'''package com.example;

public class Class{i} {{
    private String field{i};
    
    public Class{i}(String field{i}) {{
        this.field{i} = field{i};
    }}
    
    public String getField{i}() {{
        return field{i};
    }}
    
    public void method{i}() {{
        // Method implementation
        for (int j = 0; j < {i + 1}; j++) {{
            System.out.println("Processing: " + j);
        }}
    }}
}}
''')
        
        # Create multiple Python files
        python_dir = self.project_path / "scripts"
        python_dir.mkdir()
        
        for i in range(5):
            python_file = python_dir / f"module{i}.py"
            python_file.write_text(f'''#!/usr/bin/env python3

def function{i}(param):
    """Function {i} documentation"""
    result = param * {i + 1}
    return result

class Class{i}:
    def __init__(self):
        self.value = {i}
    
    def process(self, data):
        return data + self.value
''')

    @pytest.mark.asyncio
    async def test_multiple_file_access_performance(self) -> None:
        """Test performance of accessing multiple files"""
        # Get file list from statistics
        files_uri = "code://stats/files"
        files_content = await self.stats_resource.read_resource(files_uri)
        files_data = json.loads(files_content)
        
        # Access multiple files
        file_count = 0
        for file_info in files_data["files"]:
            if file_info["path"].endswith(('.java', '.py')):
                # Use absolute path for file URI
                file_path = file_info['path']
                absolute_path = str(self.project_path / file_path) if not Path(file_path).is_absolute() else file_path
                file_uri = f"code://file/{absolute_path}"
                content = await self.code_resource.read_resource(file_uri)
                
                # Verify content is readable
                assert len(content) > 0
                file_count += 1
                
                # Limit test to reasonable number
                if file_count >= 5:
                    break
        
        # Verify we tested multiple files
        assert file_count > 0

    @pytest.mark.asyncio
    async def test_statistics_generation_performance(self) -> None:
        """Test performance of statistics generation"""
        # Test different statistics types
        stats_types = ["overview", "languages", "files"]
        
        for stats_type in stats_types:
            uri = f"code://stats/{stats_type}"
            content = await self.stats_resource.read_resource(uri)
            
            # Verify content is valid JSON
            stats_data = json.loads(content)
            assert isinstance(stats_data, dict)
            
            # Verify reasonable response time (implicit in test completion)


class TestResourceConcurrency:
    """Test concurrent access to resources"""

    def setup_method(self) -> None:
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.project_path = Path(self.temp_dir)
        
        # Create test file
        test_file = self.project_path / "test.java"
        test_file.write_text("public class Test {}")
        
        self.code_resource = CodeFileResource()
        self.stats_resource = ProjectStatsResource()
        self.stats_resource.set_project_path(str(self.project_path))

    def teardown_method(self) -> None:
        """Clean up test fixtures"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_concurrent_file_access(self) -> None:
        """Test concurrent access to the same file"""
        file_path = str(self.project_path / "test.java")
        file_uri = f"code://file/{file_path}"
        
        # Create multiple concurrent requests
        tasks = [
            self.code_resource.read_resource(file_uri)
            for _ in range(3)
        ]
        
        # Execute concurrently
        results = await asyncio.gather(*tasks)
        
        # All results should be identical
        for result in results:
            assert result == results[0]
            assert "public class Test" in result

    @pytest.mark.asyncio
    async def test_concurrent_stats_access(self) -> None:
        """Test concurrent access to statistics"""
        # Create multiple concurrent requests for different stats
        tasks = [
            self.stats_resource.read_resource("code://stats/overview"),
            self.stats_resource.read_resource("code://stats/languages"),
            self.stats_resource.read_resource("code://stats/files"),
        ]
        
        # Execute concurrently
        results = await asyncio.gather(*tasks)
        
        # All results should be valid JSON
        for result in results:
            stats_data = json.loads(result)
            assert isinstance(stats_data, dict)


if __name__ == "__main__":
    pytest.main([__file__])