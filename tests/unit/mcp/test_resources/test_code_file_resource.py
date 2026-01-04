#!/usr/bin/env python3
"""
Unit tests for CodeFileResource module.

Tests the MCP resource implementation for accessing code file content.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.mcp.resources.code_file_resource import CodeFileResource


class TestCodeFileResourceInit:
    """Test CodeFileResource initialization"""

    def test_initialization(self):
        """Test resource initialization"""
        resource = CodeFileResource()
        assert resource is not None
        assert resource._uri_pattern is not None


class TestGetResourceInfo:
    """Test get_resource_info method"""

    def test_get_resource_info(self):
        """Test getting resource information"""
        resource = CodeFileResource()
        info = resource.get_resource_info()

        assert info["name"] == "code_file"
        assert "URI-based identification" in info["description"]
        assert info["uri_template"] == "code://file/{file_path}"
        assert info["mime_type"] == "text/plain"


class TestMatchesUri:
    """Test matches_uri method"""

    @pytest.fixture
    def resource(self):
        """Create resource instance"""
        return CodeFileResource()

    def test_matches_valid_uri(self, resource):
        """Test matching valid URI"""
        assert resource.matches_uri("code://file/src/main.py")
        assert resource.matches_uri("code://file/test.js")
        assert resource.matches_uri("code://file/scripts/helper.sh")

    def test_matches_uri_with_anyurl_type(self, resource):
        """Test matching URI with AnyUrl type (string conversion)"""

        # Simulate AnyUrl type that converts to string
        class MockAnyUrl:
            def __str__(self):
                return "code://file/src/main.py"

        assert resource.matches_uri(MockAnyUrl())

    def test_rejects_invalid_scheme(self, resource):
        """Test rejecting URIs with wrong scheme"""
        assert not resource.matches_uri("file://src/main.py")
        assert not resource.matches_uri("http://example.com/file.py")
        assert not resource.matches_uri("data://file/test.py")

    def test_rejects_malformed_uri(self, resource):
        """Test rejecting malformed URIs"""
        assert not resource.matches_uri("code://file/")
        assert not resource.matches_uri("code://file")
        assert not resource.matches_uri("code://")
        assert not resource.matches_uri("invalid")


class TestExtractFilePath:
    """Test _extract_file_path method"""

    @pytest.fixture
    def resource(self):
        """Create resource instance"""
        return CodeFileResource()

    def test_extract_valid_path(self, resource):
        """Test extracting valid file path"""
        uri = "code://file/src/main.py"
        path = resource._extract_file_path(uri)
        assert path == "src/main.py"

    def test_extract_path_with_subdirectories(self, resource):
        """Test extracting path with multiple subdirectories"""
        uri = "code://file/src/components/Button.tsx"
        path = resource._extract_file_path(uri)
        assert path == "src/components/Button.tsx"

    def test_extract_path_with_special_chars(self, resource):
        """Test extracting path with special characters"""
        uri = "code://file/my-file_v1.0.py"
        path = resource._extract_file_path(uri)
        assert path == "my-file_v1.0.py"

    def test_extract_invalid_uri_raises_error(self, resource):
        """Test that invalid URI raises ValueError"""
        with pytest.raises(ValueError, match="Invalid URI format"):
            resource._extract_file_path("invalid://file/test.py")

        with pytest.raises(ValueError, match="Invalid URI format"):
            resource._extract_file_path("code://wrong/test.py")


class TestValidateFilePath:
    """Test _validate_file_path method"""

    @pytest.fixture
    def resource(self):
        """Create resource instance"""
        return CodeFileResource()

    def test_validate_valid_path(self, resource):
        """Test validating a valid file path"""
        # Should not raise any exception
        resource._validate_file_path("src/main.py")
        resource._validate_file_path("test.js")
        resource._validate_file_path("scripts/helper.sh")

    def test_validate_empty_path_raises_error(self, resource):
        """Test that empty path raises ValueError"""
        with pytest.raises(ValueError, match="cannot be empty"):
            resource._validate_file_path("")

    def test_validate_null_bytes_raises_error(self, resource):
        """Test that null bytes in path raise ValueError"""
        with pytest.raises(ValueError, match="null bytes"):
            resource._validate_file_path("test\x00.py")

    def test_validate_path_traversal_raises_error(self, resource):
        """Test that path traversal raises ValueError"""
        with pytest.raises(ValueError, match="Path traversal"):
            resource._validate_file_path("../etc/passwd")

        with pytest.raises(ValueError, match="Path traversal"):
            resource._validate_file_path("src/../../etc/passwd")

        with pytest.raises(ValueError, match="Path traversal"):
            resource._validate_file_path("./test/../config.py")


class TestReadFileContent:
    """Test _read_file_content method"""

    @pytest.fixture
    def resource(self):
        """Create resource instance"""
        return CodeFileResource()

    @pytest.mark.asyncio
    async def test_read_existing_file(self, resource):
        """Test reading an existing file"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("print('hello world')")
            temp_path = f.name

        try:
            content = await resource._read_file_content(temp_path)
            assert content == "print('hello world')"
        finally:
            Path(temp_path).unlink()

    @pytest.mark.asyncio
    async def test_read_file_with_encoding(self, resource):
        """Test reading file with UTF-8 encoding"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write("# 日本語のコメント\nprint('こんにちは')")
            temp_path = f.name

        try:
            content = await resource._read_file_content(temp_path)
            assert "日本語のコメント" in content
            assert "こんにちは" in content
        finally:
            Path(temp_path).unlink()

    @pytest.mark.asyncio
    async def test_read_nonexistent_file_raises_error(self, resource):
        """Test reading non-existent file raises FileNotFoundError"""
        with pytest.raises(FileNotFoundError, match="not found"):
            await resource._read_file_content("/nonexistent/file.py")

    @pytest.mark.asyncio
    @patch("tree_sitter_analyzer.mcp.resources.code_file_resource.Path")
    @patch("tree_sitter_analyzer.mcp.resources.code_file_resource.read_file_safe")
    async def test_read_file_permission_error(self, mock_read, mock_path, resource):
        """Test reading file with permission error"""
        # Mock Path.exists() to return True
        mock_path.return_value.exists.return_value = True
        mock_read.side_effect = PermissionError("Permission denied")

        with pytest.raises(PermissionError):
            await resource._read_file_content("test.py")

    @pytest.mark.asyncio
    @patch("tree_sitter_analyzer.mcp.resources.code_file_resource.Path")
    @patch("tree_sitter_analyzer.mcp.resources.code_file_resource.read_file_safe")
    async def test_read_file_os_error(self, mock_read, mock_path, resource):
        """Test reading file with OS error"""
        # Mock Path.exists() to return True
        mock_path.return_value.exists.return_value = True
        mock_read.side_effect = OSError("Disk full")

        with pytest.raises(OSError):
            await resource._read_file_content("test.py")

    @pytest.mark.asyncio
    @patch("tree_sitter_analyzer.mcp.resources.code_file_resource.Path")
    @patch("tree_sitter_analyzer.mcp.resources.code_file_resource.read_file_safe")
    async def test_read_file_unexpected_error(self, mock_read, mock_path, resource):
        """Test reading file with unexpected error"""
        # Mock Path.exists() to return True
        mock_path.return_value.exists.return_value = True
        mock_read.side_effect = RuntimeError("Unexpected error")

        with pytest.raises(OSError, match="Failed to read file"):
            await resource._read_file_content("test.py")


class TestReadResource:
    """Test read_resource method"""

    @pytest.fixture
    def resource(self):
        """Create resource instance"""
        return CodeFileResource()

    @pytest.mark.asyncio
    async def test_read_resource_success(self, resource):
        """Test reading resource successfully"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def test():\n    pass")
            temp_path = f.name

        try:
            uri = f"code://file/{temp_path}"
            content = await resource.read_resource(uri)
            assert "def test():" in content
        finally:
            Path(temp_path).unlink()

    @pytest.mark.asyncio
    async def test_read_resource_invalid_uri(self, resource):
        """Test reading resource with invalid URI"""
        with pytest.raises(ValueError, match="does not match"):
            await resource.read_resource("invalid://file/test.py")

    @pytest.mark.asyncio
    async def test_read_resource_nonexistent_file(self, resource):
        """Test reading resource for non-existent file"""
        uri = "code://file/nonexistent.py"
        with pytest.raises(FileNotFoundError):
            await resource.read_resource(uri)

    @pytest.mark.asyncio
    async def test_read_resource_with_path_traversal(self, resource):
        """Test reading resource with path traversal is blocked"""
        uri = "code://file/../etc/passwd"
        with pytest.raises(ValueError, match="Path traversal"):
            await resource.read_resource(uri)

    @pytest.mark.asyncio
    async def test_read_resource_empty_path(self, resource):
        """Test reading resource with empty path"""
        uri = "code://file/"
        # Empty path should fail validation
        with pytest.raises(ValueError):
            await resource.read_resource(uri)

    @pytest.mark.asyncio
    async def test_read_resource_with_null_bytes(self, resource):
        """Test reading resource with null bytes in path"""
        uri = "code://file/test\x00.py"
        with pytest.raises(ValueError, match="null bytes"):
            await resource.read_resource(uri)


class TestGetSupportedSchemes:
    """Test get_supported_schemes method"""

    def test_get_supported_schemes(self):
        """Test getting supported URI schemes"""
        resource = CodeFileResource()
        schemes = resource.get_supported_schemes()

        assert isinstance(schemes, list)
        assert "code" in schemes


class TestGetSupportedResourceTypes:
    """Test get_supported_resource_types method"""

    def test_get_supported_resource_types(self):
        """Test getting supported resource types"""
        resource = CodeFileResource()
        types = resource.get_supported_resource_types()

        assert isinstance(types, list)
        assert "file" in types


class TestStringRepresentations:
    """Test __str__ and __repr__ methods"""

    def test_str_representation(self):
        """Test string representation"""
        resource = CodeFileResource()
        str_repr = str(resource)

        assert "CodeFileResource" in str_repr
        assert "code://file/{file_path}" in str_repr

    def test_repr_representation(self):
        """Test detailed string representation"""
        resource = CodeFileResource()
        repr_str = repr(resource)

        assert "CodeFileResource" in repr_str
        assert "uri_pattern" in repr_str
        assert "code://file/(.+)$" in repr_str


class TestIntegration:
    """Integration tests for CodeFileResource"""

    @pytest.fixture
    def resource(self):
        """Create resource instance"""
        return CodeFileResource()

    @pytest.mark.asyncio
    async def test_full_workflow(self, resource):
        """Test complete workflow from URI to content"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write("""
def hello():
    print('Hello, World!')
    return 42
""")
            temp_path = f.name

        try:
            # Check URI matches
            uri = f"code://file/{temp_path}"
            assert resource.matches_uri(uri)

            # Extract path
            extracted_path = resource._extract_file_path(uri)
            assert extracted_path == temp_path

            # Validate path
            resource._validate_file_path(extracted_path)

            # Read resource
            content = await resource.read_resource(uri)

            # Verify content
            assert "def hello():" in content
            assert "Hello, World!" in content
            assert "return 42" in content

        finally:
            Path(temp_path).unlink()

    @pytest.mark.asyncio
    async def test_multiple_files(self, resource):
        """Test reading multiple files"""
        test_files = []

        try:
            # Create multiple test files
            for i in range(3):
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".py", delete=False
                ) as f:
                    f.write(f"# File {i}\ndef func{i}():\n    return {i}")
                    test_files.append(f.name)

            # Read all files
            for i, temp_path in enumerate(test_files):
                uri = f"code://file/{temp_path}"
                content = await resource.read_resource(uri)
                assert f"File {i}" in content
                assert f"func{i}" in content
                assert f"return {i}" in content

        finally:
            # Clean up all files
            for temp_path in test_files:
                Path(temp_path).unlink()
