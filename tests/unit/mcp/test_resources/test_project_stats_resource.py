#!/usr/bin/env python3
"""
Unit tests for ProjectStatsResource module.

Tests MCP resource implementation for accessing project statistics.
"""

import json
import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.resources.project_stats_resource import (
    ProjectStatsResource,
)


class TestProjectStatsResourceInit:
    """Test ProjectStatsResource initialization"""

    def test_initialization(self):
        """Test resource initialization"""
        resource = ProjectStatsResource()
        assert resource is not None
        assert resource._uri_pattern is not None
        assert resource._project_path is None
        assert resource.analysis_engine is not None

    def test_supported_stats_types(self):
        """Test supported statistics types"""
        resource = ProjectStatsResource()
        assert "overview" in resource._supported_stats_types
        assert "languages" in resource._supported_stats_types
        assert "complexity" in resource._supported_stats_types
        assert "files" in resource._supported_stats_types


class TestGetResourceInfo:
    """Test get_resource_info method"""

    def test_get_resource_info(self):
        """Test getting resource information"""
        resource = ProjectStatsResource()
        info = resource.get_resource_info()

        assert info["name"] == "project_stats"
        assert "project statistics" in info["description"].lower()
        assert info["uri_template"] == "code://stats/{stats_type}"
        assert info["mime_type"] == "application/json"


class TestMatchesUri:
    """Test matches_uri method"""

    @pytest.fixture
    def resource(self):
        """Create resource instance"""
        return ProjectStatsResource()

    def test_matches_valid_uri(self, resource):
        """Test matching valid URIs"""
        assert resource.matches_uri("code://stats/overview")
        assert resource.matches_uri("code://stats/languages")
        assert resource.matches_uri("code://stats/complexity")
        assert resource.matches_uri("code://stats/files")

    def test_matches_uri_with_anyurl_type(self, resource):
        """Test matching URI with AnyUrl type (string conversion)"""

        # Simulate AnyUrl type that converts to string
        class MockAnyUrl:
            def __str__(self):
                return "code://stats/overview"

        assert resource.matches_uri(MockAnyUrl())

    def test_rejects_invalid_scheme(self, resource):
        """Test rejecting URIs with wrong scheme"""
        assert not resource.matches_uri("stats://overview")
        assert not resource.matches_uri("http://example.com/stats")
        assert not resource.matches_uri("data://stats/overview")

    def test_rejects_malformed_uri(self, resource):
        """Test rejecting malformed URIs"""
        assert not resource.matches_uri("code://stats/")
        assert not resource.matches_uri("code://stats")
        assert not resource.matches_uri("invalid")


class TestExtractStatsType:
    """Test _extract_stats_type method"""

    @pytest.fixture
    def resource(self):
        """Create resource instance"""
        return ProjectStatsResource()

    def test_extract_valid_stats_type(self, resource):
        """Test extracting valid stats type"""
        assert resource._extract_stats_type("code://stats/overview") == "overview"
        assert resource._extract_stats_type("code://stats/languages") == "languages"
        assert resource._extract_stats_type("code://stats/complexity") == "complexity"
        assert resource._extract_stats_type("code://stats/files") == "files"

    def test_extract_invalid_uri_raises_error(self, resource):
        """Test that invalid URI raises ValueError"""
        with pytest.raises(ValueError, match="Invalid URI format"):
            resource._extract_stats_type("invalid://stats/overview")


class TestProjectPathProperty:
    """Test project_path property"""

    def test_get_project_root_default(self):
        """Test getting default project root"""
        resource = ProjectStatsResource()
        assert resource.project_root is None

    def test_set_project_root(self):
        """Test setting project root"""
        resource = ProjectStatsResource()
        resource.project_root = "/test/path"
        assert resource.project_root == "/test/path"


class TestSetProjectPath:
    """Test set_project_path method"""

    @pytest.fixture
    def resource(self):
        """Create resource instance"""
        return ProjectStatsResource()

    def test_set_valid_project_path(self, resource):
        """Test setting a valid project path"""
        resource.set_project_path("/valid/path")
        assert resource._project_path == "/valid/path"

    def test_set_empty_path_raises_error(self, resource):
        """Test that empty path raises ValueError"""
        with pytest.raises(ValueError, match="cannot be empty"):
            resource.set_project_path("")

    def test_set_non_string_path_raises_error(self, resource):
        """Test that non-string path raises TypeError"""
        with pytest.raises(TypeError, match="must be a string"):
            resource.set_project_path(123)


class TestValidateProjectPath:
    """Test _validate_project_path method"""

    @pytest.fixture
    def resource(self):
        """Create resource instance"""
        return ProjectStatsResource()

    def test_validate_path_not_set_raises_error(self, resource):
        """Test that unset path raises ValueError"""
        with pytest.raises(ValueError, match="not set"):
            resource._validate_project_path()

    def test_validate_nonexistent_path_raises_error(self, resource, tmp_path):
        """Test that non-existent path raises FileNotFoundError"""
        resource._project_path = str(tmp_path / "nonexistent")
        with pytest.raises(FileNotFoundError, match="does not exist"):
            resource._validate_project_path()

    def test_validate_file_path_raises_error(self, resource, tmp_path):
        """Test that file path (not directory) raises error"""
        # Create a file instead of directory
        test_file = tmp_path / "test_file.txt"
        test_file.write_text("test")

        resource._project_path = str(test_file)
        with pytest.raises(FileNotFoundError, match="not a directory"):
            resource._validate_project_path()

    def test_validate_valid_directory(self, resource, tmp_path):
        """Test validating a valid directory"""
        resource._project_path = str(tmp_path)
        # Should not raise any exception
        resource._validate_project_path()


class TestIsSupportedCodeFile:
    """Test _is_supported_code_file method"""

    @pytest.fixture
    def resource(self):
        """Create resource instance"""
        return ProjectStatsResource()

    @pytest.fixture
    def tmp_path(self):
        """Create temporary directory"""
        with tempfile.TemporaryDirectory() as tmp:
            yield Path(tmp)

    def test_is_supported_python_file(self, resource, tmp_path):
        """Test Python file is supported"""
        test_file = tmp_path / "test.py"
        test_file.write_text("def test(): pass")
        resource._project_path = str(tmp_path)
        assert resource._is_supported_code_file(test_file) is True

    def test_is_supported_javascript_file(self, resource, tmp_path):
        """Test JavaScript file is supported"""
        test_file = tmp_path / "test.js"
        test_file.write_text("function test() {}")
        resource._project_path = str(tmp_path)
        assert resource._is_supported_code_file(test_file) is True

    def test_unsupported_file(self, resource, tmp_path):
        """Test unsupported file type"""
        test_file = tmp_path / "test.txt"
        test_file.write_text("plain text")
        resource._project_path = str(tmp_path)
        # May return False for unsupported file types
        result = resource._is_supported_code_file(test_file)
        # Just ensure it doesn't crash


class TestGetLanguageFromFile:
    """Test _get_language_from_file method"""

    @pytest.fixture
    def resource(self):
        """Create resource instance"""
        return ProjectStatsResource()

    @pytest.fixture
    def tmp_path(self):
        """Create temporary directory"""
        with tempfile.TemporaryDirectory() as tmp:
            yield Path(tmp)

    def test_get_python_language(self, resource, tmp_path):
        """Test getting language from Python file"""
        test_file = tmp_path / "test.py"
        test_file.write_text("def test(): pass")
        resource._project_path = str(tmp_path)
        language = resource._get_language_from_file(test_file)
        assert language == "python"

    def test_get_javascript_language(self, resource, tmp_path):
        """Test getting language from JavaScript file"""
        test_file = tmp_path / "test.js"
        test_file.write_text("function test() {}")
        resource._project_path = str(tmp_path)
        language = resource._get_language_from_file(test_file)
        assert language == "javascript"

    def test_get_unknown_language(self, resource, tmp_path):
        """Test getting language from unknown file type"""
        test_file = tmp_path / "test.unknown"
        test_file.write_text("some content")
        resource._project_path = str(tmp_path)
        language = resource._get_language_from_file(test_file)
        assert language == "unknown"


class TestGenerateOverviewStats:
    """Test _generate_overview_stats method"""

    @pytest.fixture
    def resource(self):
        """Create resource instance"""
        return ProjectStatsResource()

    @pytest.fixture
    def tmp_path(self):
        """Create temporary directory with test files"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            # Create test files
            (tmp_dir / "test.py").write_text("def test(): pass")
            (tmp_dir / "test.js").write_text("function test() {}")
            (tmp_dir / "README.md").write_text("# Test Project")
            yield tmp_dir

    @pytest.mark.asyncio
    async def test_generate_overview_success(self, resource, tmp_path):
        """Test generating overview statistics"""
        resource._project_path = str(tmp_path)
        overview = await resource._generate_overview_stats()

        assert "total_files" in overview
        assert "total_lines" in overview
        assert "languages" in overview
        assert "project_path" in overview
        assert "last_updated" in overview

    @pytest.mark.asyncio
    async def test_generate_overview_no_project_path(self, resource):
        """Test generating overview without project path raises error"""
        resource._project_path = None
        with pytest.raises(ValueError, match="not set"):
            await resource._generate_overview_stats()


class TestGenerateLanguagesStats:
    """Test _generate_languages_stats method"""

    @pytest.fixture
    def resource(self):
        """Create resource instance"""
        return ProjectStatsResource()

    @pytest.fixture
    def tmp_path(self):
        """Create temporary directory with test files"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            # Create test files with different line counts
            (tmp_dir / "test.py").write_text("\n".join(["line"] * 10))
            (tmp_dir / "test.js").write_text("\n".join(["line"] * 5))
            yield tmp_dir

    @pytest.mark.asyncio
    async def test_generate_languages_success(self, resource, tmp_path):
        """Test generating language statistics"""
        resource._project_path = str(tmp_path)
        stats = await resource._generate_languages_stats()

        assert "languages" in stats
        assert "total_languages" in stats
        assert "last_updated" in stats

    @pytest.mark.asyncio
    async def test_generate_languages_percentage(self, resource, tmp_path):
        """Test language percentage calculation"""
        resource._project_path = str(tmp_path)
        stats = await resource._generate_languages_stats()

        languages = stats["languages"]
        total_percentage = sum(lang["percentage"] for lang in languages)
        assert total_percentage == 100.0 or total_percentage == 0.0

    @pytest.mark.asyncio
    async def test_generate_languages_no_project_path(self, resource):
        """Test generating languages without project path raises error"""
        resource._project_path = None
        with pytest.raises(ValueError, match="not set"):
            await resource._generate_languages_stats()


class TestGenerateComplexityStats:
    """Test _generate_complexity_stats method"""

    @pytest.fixture
    def resource(self):
        """Create resource instance"""
        return ProjectStatsResource()

    @pytest.fixture
    def tmp_path(self):
        """Create temporary directory with test files"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            # Create test files
            (tmp_dir / "test.py").write_text("def test(): pass")
            yield tmp_dir

    @pytest.mark.asyncio
    async def test_generate_complexity_success(self, resource, tmp_path):
        """Test generating complexity statistics"""
        resource._project_path = str(tmp_path)
        stats = await resource._generate_complexity_stats()

        assert "average_complexity" in stats
        assert "max_complexity" in stats
        assert "total_files_analyzed" in stats
        assert "files_by_complexity" in stats
        assert "last_updated" in stats

    @pytest.mark.asyncio
    async def test_generate_complexity_no_project_path(self, resource):
        """Test generating complexity without project path raises error"""
        resource._project_path = None
        with pytest.raises(ValueError, match="not set"):
            await resource._generate_complexity_stats()


class TestGenerateFilesStats:
    """Test _generate_files_stats method"""

    @pytest.fixture
    def resource(self):
        """Create resource instance"""
        return ProjectStatsResource()

    @pytest.fixture
    def tmp_path(self):
        """Create temporary directory with test files"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            # Create test files
            (tmp_dir / "test.py").write_text("def test(): pass")
            (tmp_dir / "test.js").write_text("function test() {}")
            yield tmp_dir

    @pytest.mark.asyncio
    async def test_generate_files_success(self, resource, tmp_path):
        """Test generating file statistics"""
        resource._project_path = str(tmp_path)
        stats = await resource._generate_files_stats()

        assert "files" in stats
        assert "total_count" in stats
        assert "last_updated" in stats

    @pytest.mark.asyncio
    async def test_generate_files_sorted(self, resource, tmp_path):
        """Test files are sorted by line count"""
        resource._project_path = str(tmp_path)
        stats = await resource._generate_files_stats()

        files = stats["files"]
        if len(files) > 1:
            # Check that files are sorted by line_count (descending)
            for i in range(len(files) - 1):
                assert files[i]["line_count"] >= files[i + 1]["line_count"]

    @pytest.mark.asyncio
    async def test_generate_files_no_project_path(self, resource):
        """Test generating files without project path raises error"""
        resource._project_path = None
        with pytest.raises(ValueError, match="not set"):
            await resource._generate_files_stats()


class TestReadResource:
    """Test read_resource method"""

    @pytest.fixture
    def resource(self):
        """Create resource instance"""
        return ProjectStatsResource()

    @pytest.fixture
    def tmp_path(self):
        """Create temporary directory with test files"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            (tmp_dir / "test.py").write_text("def test(): pass")
            yield tmp_dir

    @pytest.mark.asyncio
    async def test_read_overview_resource(self, resource, tmp_path):
        """Test reading overview resource"""
        resource._project_path = str(tmp_path)
        content = await resource.read_resource("code://stats/overview")

        data = json.loads(content)
        assert "total_files" in data
        assert "total_lines" in data

    @pytest.mark.asyncio
    async def test_read_languages_resource(self, resource, tmp_path):
        """Test reading languages resource"""
        resource._project_path = str(tmp_path)
        content = await resource.read_resource("code://stats/languages")

        data = json.loads(content)
        assert "languages" in data
        assert "total_languages" in data

    @pytest.mark.asyncio
    async def test_read_complexity_resource(self, resource, tmp_path):
        """Test reading complexity resource"""
        resource._project_path = str(tmp_path)
        content = await resource.read_resource("code://stats/complexity")

        data = json.loads(content)
        assert "average_complexity" in data
        assert "max_complexity" in data

    @pytest.mark.asyncio
    async def test_read_files_resource(self, resource, tmp_path):
        """Test reading files resource"""
        resource._project_path = str(tmp_path)
        content = await resource.read_resource("code://stats/files")

        data = json.loads(content)
        assert "files" in data
        assert "total_count" in data

    @pytest.mark.asyncio
    async def test_read_invalid_uri(self, resource):
        """Test reading resource with invalid URI"""
        with pytest.raises(ValueError, match="does not match"):
            await resource.read_resource("invalid://stats/overview")

    @pytest.mark.asyncio
    async def test_read_unsupported_stats_type(self, resource):
        """Test reading resource with unsupported stats type"""
        resource._project_path = "/tmp"
        with pytest.raises(ValueError, match="Unsupported statistics type"):
            await resource.read_resource("code://stats/unsupported")

    @pytest.mark.asyncio
    async def test_read_no_project_path(self, resource):
        """Test reading resource without project path raises error"""
        resource._project_path = None
        with pytest.raises(ValueError, match="not set"):
            await resource.read_resource("code://stats/overview")


class TestGetSupportedSchemes:
    """Test get_supported_schemes method"""

    def test_get_supported_schemes(self):
        """Test getting supported URI schemes"""
        resource = ProjectStatsResource()
        schemes = resource.get_supported_schemes()

        assert isinstance(schemes, list)
        assert "code" in schemes


class TestGetSupportedResourceTypes:
    """Test get_supported_resource_types method"""

    def test_get_supported_resource_types(self):
        """Test getting supported resource types"""
        resource = ProjectStatsResource()
        types = resource.get_supported_resource_types()

        assert isinstance(types, list)
        assert "stats" in types


class TestGetSupportedStatsTypes:
    """Test get_supported_stats_types method"""

    def test_get_supported_stats_types(self):
        """Test getting supported statistics types"""
        resource = ProjectStatsResource()
        types = resource.get_supported_stats_types()

        assert isinstance(types, list)
        assert "overview" in types
        assert "languages" in types
        assert "complexity" in types
        assert "files" in types


class TestStringRepresentations:
    """Test __str__ and __repr__ methods"""

    def test_str_representation(self):
        """Test string representation"""
        resource = ProjectStatsResource()
        str_repr = str(resource)

        assert "ProjectStatsResource" in str_repr
        assert "code://stats/{stats_type}" in str_repr

    def test_repr_representation(self):
        """Test detailed string representation"""
        resource = ProjectStatsResource()
        repr_str = repr(resource)

        assert "ProjectStatsResource" in repr_str
        assert "uri_pattern" in repr_str
        assert "project_path" in repr_str
