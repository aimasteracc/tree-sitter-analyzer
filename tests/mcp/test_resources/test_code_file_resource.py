#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test cases for code file MCP resource

Tests the code file resource that provides dynamic access to code file
content through the MCP resource protocol.
"""

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any, Dict
# Mock functionality now provided by pytest-mock

import pytest
import pytest_asyncio

from tree_sitter_analyzer.mcp.resources.code_file_resource import CodeFileResource


class TestCodeFileResourceSchema:
    """Test code file resource schema and validation"""

    def setup_method(self) -> None:
        """Set up test fixtures"""
        self.resource = CodeFileResource()

    def test_resource_info_structure(self) -> None:
        """Test that resource info has required structure"""
        info = self.resource.get_resource_info()
        
        # Test info structure
        assert "name" in info
        assert "description" in info
        assert "uri_template" in info
        assert "mime_type" in info
        
        # Test expected values
        assert info["name"] == "code_file"
        assert info["mime_type"] == "text/plain"
        assert "code://file/" in info["uri_template"]

    def test_uri_pattern_validation(self) -> None:
        """Test URI pattern validation"""
        # Valid URIs
        valid_uris = [
            "code://file/path/to/file.java",
            "code://file/src/main/java/Example.java",
            "code://file/test.py",
        ]
        
        for uri in valid_uris:
            result = self.resource.matches_uri(uri)
            assert result, f"URI should match: {uri}"
        
        # Invalid URIs
        invalid_uris = [
            "file://path/to/file.java",
            "code://stats/project",
            "code://file/",
            "invalid://uri",
        ]
        
        for uri in invalid_uris:
            result = self.resource.matches_uri(uri)
            assert not result, f"URI should not match: {uri}"

    def test_extract_file_path(self) -> None:
        """Test file path extraction from URI"""
        test_cases = [
            ("code://file/path/to/file.java", "path/to/file.java"),
            ("code://file/src/Example.java", "src/Example.java"),
            ("code://file/test.py", "test.py"),
        ]
        
        for uri, expected_path in test_cases:
            extracted_path = self.resource._extract_file_path(uri)
            assert extracted_path == expected_path


class TestCodeFileResourceFunctionality:
    """Test code file resource core functionality"""

    def setup_method(self) -> None:
        """Set up test fixtures"""
        self.resource = CodeFileResource()
        self.sample_java_code = '''package com.example;

import java.util.List;

/**
 * Sample class for testing resource access
 */
public class SampleClass {
    private String name;
    
    public SampleClass(String name) {
        this.name = name;
    }
    
    public String getName() {
        return name;
    }
}
'''

    @pytest.mark.asyncio
    async def test_read_existing_file(self) -> None:
        """Test reading an existing file"""
        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False) as f:
            f.write(self.sample_java_code)
            temp_path = f.name
        
        try:
            uri = f"code://file/{temp_path}"
            content = await self.resource.read_resource(uri)
            
            # Test content
            assert isinstance(content, str)
            assert "package com.example" in content
            assert "public class SampleClass" in content
            
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self) -> None:
        """Test error handling for nonexistent file"""
        uri = "code://file/nonexistent/file.java"
        
        with pytest.raises(FileNotFoundError):
            await self.resource.read_resource(uri)

    @pytest.mark.asyncio
    async def test_read_invalid_uri(self) -> None:
        """Test error handling for invalid URI"""
        invalid_uri = "invalid://uri/format"
        
        with pytest.raises(ValueError):
            await self.resource.read_resource(invalid_uri)

    @pytest.mark.asyncio
    async def test_read_file_with_encoding(self) -> None:
        """Test reading file with different encodings"""
        # Create file with UTF-8 content
        unicode_content = '''package com.example;

/**
 * クラスの説明 (Japanese comment)
 * Описание класса (Russian comment)
 */
public class UnicodeClass {
    private String message = "こんにちは世界";
}
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False, encoding='utf-8') as f:
            f.write(unicode_content)
            temp_path = f.name
        
        try:
            uri = f"code://file/{temp_path}"
            content = await self.resource.read_resource(uri)
            
            # Test Unicode content
            assert "こんにちは世界" in content
            assert "クラスの説明" in content
            assert "Описание класса" in content
            
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_read_large_file(self) -> None:
        """Test reading larger files"""
        # Create a larger file
        large_content = '''package com.example;

public class LargeClass {
''' + '\n'.join([f'''
    private String field{i} = "value{i}";
    
    public String getField{i}() {{
        return field{i};
    }}
''' for i in range(100)]) + '''
}
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False) as f:
            f.write(large_content)
            temp_path = f.name
        
        try:
            uri = f"code://file/{temp_path}"
            content = await self.resource.read_resource(uri)
            
            # Test large content handling
            assert len(content) > 1000
            assert "field99" in content
            assert "getField99" in content
            
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestCodeFileResourceIntegration:
    """Test integration with existing file handler components"""

    def setup_method(self) -> None:
        """Set up test fixtures"""
        self.resource = CodeFileResource()

    def test_integration_with_file_handler(self) -> None:
        """Test integration with existing file_handler module"""
        # This should use the existing read_file_safe function
        from tree_sitter_analyzer.encoding_utils import read_file_safe
        
        # Verify function exists and is callable
        assert callable(read_file_safe)
        
        # Test resource uses the same function
        assert hasattr(self.resource, '_read_file_content')

    def test_integration_with_encoding_utils(self) -> None:
        """Test integration with encoding utilities"""
        from tree_sitter_analyzer.encoding_utils import EncodingManager
        
        # Verify encoding manager exists
        assert hasattr(EncodingManager, 'read_file_safe')


class TestCodeFileResourceErrorHandling:
    """Test error handling in code file resource"""

    def setup_method(self) -> None:
        """Set up test fixtures"""
        self.resource = CodeFileResource()

    @pytest.mark.asyncio
    async def test_permission_denied_error(self, mocker) -> None:
        """Test handling of permission denied errors"""
        # This test would require creating a file with restricted permissions
        # For now, we'll test the error handling structure
        uri = "code://file/restricted/file.java"
        
        # Mock the file reading to simulate permission error
        mock_read = mocker.patch.object(self.resource, '_read_file_content')
        mock_read.side_effect = PermissionError("Permission denied")
        
        with pytest.raises(PermissionError):
            await self.resource.read_resource(uri)

    @pytest.mark.asyncio
    async def test_invalid_file_path_characters(self) -> None:
        """Test handling of invalid file path characters"""
        invalid_uris = [
            "code://file/../../../etc/passwd",
            "code://file/path/with/null\x00byte",
        ]
        
        for uri in invalid_uris:
            with pytest.raises((ValueError, OSError)):
                await self.resource.read_resource(uri)

    def test_malformed_uri_handling(self) -> None:
        """Test handling of malformed URIs"""
        malformed_uris = [
            "code://file",  # Missing path
            "code://",      # Missing resource type
            "://file/path", # Missing scheme
            "",             # Empty URI
        ]
        
        for uri in malformed_uris:
            result = self.resource.matches_uri(uri)
            assert not result, f"Malformed URI should not match: {uri}"


class TestCodeFileResourcePerformance:
    """Test performance characteristics of code file resource"""

    def setup_method(self) -> None:
        """Set up test fixtures"""
        self.resource = CodeFileResource()

    @pytest.mark.asyncio
    async def test_multiple_file_access(self) -> None:
        """Test accessing multiple files efficiently"""
        # Create multiple temporary files
        temp_files = []
        
        try:
            for i in range(5):
                content = f'''package com.example.test{i};

public class TestClass{i} {{
    private String value = "test{i}";
}}
'''
                with tempfile.NamedTemporaryFile(mode='w', suffix=f'.java', delete=False) as f:
                    f.write(content)
                    temp_files.append(f.name)
            
            # Read all files
            for i, temp_path in enumerate(temp_files):
                uri = f"code://file/{temp_path}"
                content = await self.resource.read_resource(uri)
                
                assert f"TestClass{i}" in content
                assert f"test{i}" in content
        
        finally:
            # Clean up
            for temp_path in temp_files:
                Path(temp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    pytest.main([__file__])