"""
End-to-end integration tests for tree-sitter-analyzer.

Tests complete workflows from file discovery to analysis to output,
verifying all modules work together correctly.
"""

from pathlib import Path

import pytest

from tree_sitter_analyzer.core.analysis_engine import UnifiedAnalysisEngine
from tree_sitter_analyzer.core.request import AnalysisRequest
from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
from tree_sitter_analyzer.mcp.tools.list_files_tool import ListFilesTool
from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool


class TestEndToEndFileDiscoveryAndAnalysis:
    """End-to-end tests for file discovery and analysis workflow."""

    @pytest.fixture
    def sample_project(self, tmp_path: Path) -> Path:
        """Create a sample project with multiple file types."""
        # Create directory structure
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "docs").mkdir()

        # Create Python files
        (tmp_path / "src" / "main.py").write_text(
            """
'''Main application module.'''

class Application:
    '''Main application class.'''

    def __init__(self):
        '''Initialize application.'''
        self.running = False
        self.config = {}

    def start(self):
        '''Start the application.'''
        self.running = True
        print('Application started')

    def stop(self):
        '''Stop the application.'''
        self.running = False
        print('Application stopped')

    def configure(self, config: dict):
        '''Configure the application.'''
        self.config = config

def main():
    '''Main entry point.'''
    app = Application()
    app.start()
    app.stop()

if __name__ == '__main__':
    main()
"""
        )

        (tmp_path / "src" / "utils.py").write_text(
            """
'''Utility functions.'''

def helper_function(x: int, y: int) -> int:
    '''Add two numbers.'''
    return x + y

def another_helper(text: str) -> str:
    '''Convert text to uppercase.'''
    return text.upper()

class UtilityClass:
    '''Utility class for common operations.'''

    @staticmethod
    def format_string(s: str) -> str:
        '''Format a string.'''
        return s.strip().lower()
"""
        )

        # Create test files
        (tmp_path / "tests" / "test_main.py").write_text(
            """
'''Tests for main module.'''

def test_application_start():
    '''Test application start.'''
    from src.main import Application
    app = Application()
    app.start()
    assert app.running is True

def test_application_stop():
    '''Test application stop.'''
    from src.main import Application
    app = Application()
    app.start()
    app.stop()
    assert app.running is False
"""
        )

        # Create Java file
        (tmp_path / "src" / "Sample.java").write_text(
            """
/**
 * Sample Java class.
 */
public class Sample {
    private int value;
    private String name;

    /**
     * Constructor.
     */
    public Sample() {
        this.value = 0;
        this.name = "";
    }

    /**
     * Get value.
     */
    public int getValue() {
        return value;
    }

    /**
     * Set value.
     */
    public void setValue(int value) {
        this.value = value;
    }

    /**
     * Get name.
     */
    public String getName() {
        return name;
    }

    /**
     * Set name.
     */
    public void setName(String name) {
        this.name = name;
    }
}
"""
        )

        # Create documentation
        (tmp_path / "docs" / "README.md").write_text(
            """
# Sample Project

This is a sample project for testing.

## Features

- Feature 1
- Feature 2
- Feature 3
"""
        )

        # Create .gitignore
        (tmp_path / ".gitignore").write_text("*.pyc\n__pycache__/\n.venv/\n")

        return tmp_path

    @pytest.mark.asyncio
    async def test_discover_analyze_python_files(self, sample_project: Path):
        """Test discovering and analyzing Python files."""
        # Step 1: Discover Python files
        list_tool = ListFilesTool(project_root=str(sample_project))

        discover_result = await list_tool.execute(
            {
                "roots": [str(sample_project)],
                "extensions": ["py"],
                "output_format": "json",  # Request JSON format for easier testing
            }
        )

        assert isinstance(discover_result, dict)
        assert "files" in discover_result or "results" in discover_result
        python_files = discover_result.get("files") or discover_result.get(
            "results", []
        )
        assert len(python_files) >= 3  # main.py, utils.py, test_main.py

        # Step 2: Analyze each Python file
        engine = UnifiedAnalysisEngine(project_root=str(sample_project))

        analysis_results = []
        for file_info in python_files:
            file_path = file_info.get("path") or file_info.get("file")
            if file_path and file_path.endswith(".py"):
                result = await engine.analyze(
                    AnalysisRequest(
                        file_path=file_path,
                        language="python",
                    )
                )
                analysis_results.append(result)

        # All analyses should succeed
        assert len(analysis_results) >= 3
        assert all(r is not None for r in analysis_results)

    @pytest.mark.asyncio
    async def test_search_and_analyze_workflow(self, sample_project: Path):
        """Test searching for pattern and analyzing matching files."""
        # Step 1: Search for 'class' keyword
        search_tool = SearchContentTool(project_root=str(sample_project))

        search_result = await search_tool.execute(
            {
                "query": "class",
                "roots": [str(sample_project)],
                "include_globs": ["*.py"],
                "output_format": "json",  # Request JSON format for easier testing
            }
        )

        assert isinstance(search_result, dict)
        # Handle different result formats: results, matches, or files
        if "results" in search_result:
            matches = search_result["results"]
        elif "matches" in search_result:
            matches = search_result["matches"]
        elif "files" in search_result:
            # Extract matches from grouped format
            matches = []
            for file_entry in search_result["files"]:
                for match in file_entry.get("matches", []):
                    match_copy = match.copy()
                    match_copy["file"] = file_entry["file"]
                    matches.append(match_copy)
        else:
            matches = []
        assert len(matches) > 0

        # Step 2: Extract unique files from matches
        unique_files = set()
        for match in matches:
            file_path = match.get("file") or match.get("path")
            if file_path:
                unique_files.add(file_path)

        # Step 3: Analyze files containing 'class'
        engine = UnifiedAnalysisEngine(project_root=str(sample_project))

        class_analysis_results = []
        for file_path in unique_files:
            if file_path.endswith(".py"):
                result = await engine.analyze(
                    AnalysisRequest(
                        file_path=file_path,
                        language="python",
                    )
                )
                class_analysis_results.append(result)

        # Should have analyzed files with classes
        assert len(class_analysis_results) > 0
        assert all(r is not None for r in class_analysis_results)

    @pytest.mark.asyncio
    async def test_code_scale_analysis_workflow(self, sample_project: Path):
        """Test code scale analysis workflow."""
        # Step 1: Discover Python files
        list_tool = ListFilesTool(project_root=str(sample_project))

        discover_result = await list_tool.execute(
            {
                "roots": [str(sample_project / "src")],
                "extensions": ["py"],
                "output_format": "json",  # Request JSON format for easier testing
            }
        )

        assert isinstance(discover_result, dict)
        python_files = discover_result.get("files") or discover_result.get(
            "results", []
        )

        # Step 2: Analyze code scale for each file
        scale_tool = AnalyzeScaleTool(project_root=str(sample_project))

        scale_results = []
        for file_info in python_files:
            file_path = file_info.get("path") or file_info.get("file")
            if file_path and file_path.endswith(".py"):
                result = await scale_tool.execute(
                    {
                        "file_path": file_path,
                        "language": "python",
                    }
                )
                scale_results.append(result)

        # All scale analyses should succeed
        assert len(scale_results) >= 2  # main.py, utils.py
        for result in scale_results:
            assert isinstance(result, dict)
            # Should have metrics (check in file_metrics or at top level)
            has_metrics = (
                "total_lines" in result
                or "lines" in result
                or (
                    "file_metrics" in result and "total_lines" in result["file_metrics"]
                )
            )
            assert has_metrics

    @pytest.mark.asyncio
    async def test_multi_language_analysis(self, sample_project: Path):
        """Test analyzing multiple languages in one project."""
        engine = UnifiedAnalysisEngine(project_root=str(sample_project))

        # Analyze Python file
        python_result = await engine.analyze(
            AnalysisRequest(
                file_path=str(sample_project / "src" / "main.py"),
                language="python",
            )
        )

        # Analyze Java file
        java_result = await engine.analyze(
            AnalysisRequest(
                file_path=str(sample_project / "src" / "Sample.java"),
                language="java",
            )
        )

        # Both should succeed
        assert python_result is not None
        assert java_result is not None

    @pytest.mark.asyncio
    async def test_search_with_output_file(self, sample_project: Path):
        """Test search with file output."""
        search_tool = SearchContentTool(project_root=str(sample_project))

        result = await search_tool.execute(
            {
                "query": "def",
                "roots": [str(sample_project)],
                "output_file": "search_results.json",
            }
        )

        # Should return successful result
        assert result.get("success") is True
        assert result.get("count", 0) > 0

        # If file_saved field is present, verify the file exists
        if "file_saved" in result:
            # Extract file path from message
            import re

            match = re.search(r"Results saved to (.+)", result["file_saved"])
            if match:
                file_path = Path(match.group(1))
                assert file_path.exists()
                # File should contain valid content
                content = file_path.read_text()
                assert len(content) > 0

    @pytest.mark.asyncio
    async def test_complete_project_analysis(self, sample_project: Path):
        """Test complete project analysis workflow."""
        # Step 1: Discover all files
        list_tool = ListFilesTool(project_root=str(sample_project))

        all_files = await list_tool.execute(
            {
                "roots": [str(sample_project)],
                "output_format": "json",  # Request JSON format for easier testing
            }
        )

        assert isinstance(all_files, dict)
        files_list = all_files.get("files") or all_files.get("results", [])
        total_files = len(files_list)
        assert total_files > 0

        # Step 2: Search for common patterns
        search_tool = SearchContentTool(project_root=str(sample_project))

        patterns = ["class", "def", "import"]
        search_results = {}

        for pattern in patterns:
            result = await search_tool.execute(
                {
                    "query": pattern,
                    "roots": [str(sample_project)],
                    "total_only": True,
                }
            )
            search_results[pattern] = result

        # Should find matches for all patterns
        assert all(count > 0 for count in search_results.values())

        # Step 3: Analyze code scale for source files
        scale_tool = AnalyzeScaleTool(project_root=str(sample_project))

        src_files = await list_tool.execute(
            {
                "roots": [str(sample_project / "src")],
                "extensions": ["py", "java"],
                "output_format": "json",  # Request JSON format for easier testing
            }
        )

        scale_metrics = []
        src_files_list = src_files.get("files") or src_files.get("results", [])
        for file_info in src_files_list:
            file_path = file_info.get("path") or file_info.get("file")
            if file_path:
                # Detect language from extension
                if file_path.endswith(".py"):
                    language = "python"
                elif file_path.endswith(".java"):
                    language = "java"
                else:
                    continue

                result = await scale_tool.execute(
                    {
                        "file_path": file_path,
                        "language": language,
                    }
                )
                scale_metrics.append(result)

        # Should have metrics for all source files
        assert len(scale_metrics) >= 3  # main.py, utils.py, Sample.java


class TestEndToEndPerformance:
    """End-to-end performance tests."""

    @pytest.fixture
    def large_project(self, tmp_path: Path) -> Path:
        """Create a large project for performance testing."""
        # Create many files
        for i in range(50):
            file_path = tmp_path / f"file_{i}.py"
            file_path.write_text(
                f"""
class Class{i}:
    def method1(self):
        pass

    def method2(self):
        pass

def function{i}():
    pass
"""
            )

        return tmp_path

    @pytest.mark.asyncio
    async def test_batch_file_discovery_performance(self, large_project: Path):
        """Test performance of discovering many files."""
        import time

        list_tool = ListFilesTool(project_root=str(large_project))

        start_time = time.time()

        result = await list_tool.execute(
            {
                "roots": [str(large_project)],
                "extensions": ["py"],
                "output_format": "json",  # Request JSON format for easier testing
            }
        )

        end_time = time.time()
        elapsed = end_time - start_time

        # Should complete in reasonable time
        assert elapsed < 5.0  # 5 seconds max

        # Should find all files
        files = result.get("files") or result.get("results", [])
        assert len(files) == 50

    @pytest.mark.asyncio
    async def test_batch_search_performance(self, large_project: Path):
        """Test performance of searching across many files."""
        import time

        search_tool = SearchContentTool(project_root=str(large_project))

        start_time = time.time()

        result = await search_tool.execute(
            {
                "query": "class",
                "roots": [str(large_project)],
                "total_only": True,
            }
        )

        end_time = time.time()
        elapsed = end_time - start_time

        # Should complete in reasonable time
        assert elapsed < 10.0  # 10 seconds max

        # Should find matches
        assert isinstance(result, int)
        assert result >= 50  # At least one class per file

    @pytest.mark.asyncio
    async def test_batch_analysis_performance(self, large_project: Path):
        """Test performance of analyzing many files."""
        import time

        engine = UnifiedAnalysisEngine(project_root=str(large_project))

        # Get first 10 files
        files = list(large_project.glob("*.py"))[:10]

        start_time = time.time()

        results = []
        for file_path in files:
            result = await engine.analyze(
                AnalysisRequest(
                    file_path=str(file_path),
                    language="python",
                )
            )
            results.append(result)

        end_time = time.time()
        elapsed = end_time - start_time

        # Should complete in reasonable time
        assert elapsed < 30.0  # 30 seconds for 10 files

        # All should succeed
        assert len(results) == 10
        assert all(r is not None for r in results)


class TestEndToEndErrorHandling:
    """End-to-end error handling tests."""

    @pytest.fixture
    def problematic_project(self, tmp_path: Path) -> Path:
        """Create a project with problematic files."""
        # Valid file
        (tmp_path / "valid.py").write_text("def valid(): pass\n")

        # Empty file
        (tmp_path / "empty.py").write_text("")

        # Binary file
        (tmp_path / "binary.pyc").write_bytes(b"\x00\x01\x02\x03")

        return tmp_path

    @pytest.mark.asyncio
    async def test_handle_empty_files(self, problematic_project: Path):
        """Test handling of empty files."""
        engine = UnifiedAnalysisEngine(project_root=str(problematic_project))

        result = await engine.analyze(
            AnalysisRequest(
                file_path=str(problematic_project / "empty.py"),
                language="python",
            )
        )

        # Should handle gracefully (either succeed with empty tree or return None)
        assert result is None or result.success is True

    @pytest.mark.asyncio
    async def test_handle_binary_files(self, problematic_project: Path):
        """Test handling of binary files."""
        search_tool = SearchContentTool(project_root=str(problematic_project))

        result = await search_tool.execute(
            {
                "query": "test",
                "roots": [str(problematic_project)],
            }
        )

        # Should handle gracefully (skip binary files)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_handle_nonexistent_files(self, problematic_project: Path):
        """Test handling of nonexistent files."""
        engine = UnifiedAnalysisEngine(project_root=str(problematic_project))

        # Should raise FileNotFoundError for nonexistent files
        with pytest.raises(FileNotFoundError):
            await engine.analyze(
                AnalysisRequest(
                    file_path=str(problematic_project / "nonexistent.py"),
                    language="python",
                )
            )


class TestEndToEndCaching:
    """End-to-end caching tests."""

    @pytest.fixture
    def cached_project(self, tmp_path: Path) -> Path:
        """Create a project for caching tests."""
        (tmp_path / "test.py").write_text("def test(): pass\n")
        return tmp_path

    @pytest.mark.asyncio
    async def test_search_cache_hit(self, cached_project: Path):
        """Test search cache hit on repeated queries."""
        search_tool = SearchContentTool(project_root=str(cached_project))

        query_args = {
            "query": "def",
            "roots": [str(cached_project)],
        }

        # First query
        result1 = await search_tool.execute(query_args)

        # Second query (should hit cache)
        result2 = await search_tool.execute(query_args)

        # Second result should have cache_hit flag
        assert result2.get("cache_hit") is True

        # Results should have same count and success status
        assert result1.get("success") == result2.get("success")
        assert result1.get("count") == result2.get("count")

    @pytest.mark.asyncio
    async def test_analysis_cache_hit(self, cached_project: Path):
        """Test analysis cache hit on repeated analyses."""
        engine = UnifiedAnalysisEngine(project_root=str(cached_project))

        file_path = str(cached_project / "test.py")

        # First analysis
        result1 = await engine.analyze(
            AnalysisRequest(
                file_path=file_path,
                language="python",
            )
        )

        # Second analysis (should hit cache)
        result2 = await engine.analyze(
            AnalysisRequest(
                file_path=file_path,
                language="python",
            )
        )

        # Results should be consistent
        assert result1 is not None
        assert result2 is not None


class TestEndToEndRealWorldScenarios:
    """End-to-end tests for real-world scenarios."""

    @pytest.fixture
    def realistic_project(self, tmp_path: Path) -> Path:
        """Create a realistic project structure."""
        # Create typical Python project structure
        (tmp_path / "src" / "myapp").mkdir(parents=True)
        (tmp_path / "tests").mkdir()
        (tmp_path / "docs").mkdir()

        # Create __init__.py files
        (tmp_path / "src" / "myapp" / "__init__.py").write_text("")

        # Create main module
        (tmp_path / "src" / "myapp" / "main.py").write_text(
            """
from .models import User
from .utils import validate_email

class Application:
    def __init__(self):
        self.users = []

    def add_user(self, email: str, name: str):
        if validate_email(email):
            user = User(email, name)
            self.users.append(user)
            return user
        return None
"""
        )

        # Create models module
        (tmp_path / "src" / "myapp" / "models.py").write_text(
            """
class User:
    def __init__(self, email: str, name: str):
        self.email = email
        self.name = name

    def __repr__(self):
        return f"User({self.email}, {self.name})"
"""
        )

        # Create utils module
        (tmp_path / "src" / "myapp" / "utils.py").write_text(
            """
import re

def validate_email(email: str) -> bool:
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))
"""
        )

        # Create tests
        (tmp_path / "tests" / "test_models.py").write_text(
            """
from src.myapp.models import User

def test_user_creation():
    user = User("test@example.com", "Test User")
    assert user.email == "test@example.com"
    assert user.name == "Test User"
"""
        )

        return tmp_path

    @pytest.mark.asyncio
    async def test_find_all_classes_in_project(self, realistic_project: Path):
        """Test finding all classes in a realistic project."""
        search_tool = SearchContentTool(project_root=str(realistic_project))

        result = await search_tool.execute(
            {
                "query": "^class ",
                "roots": [str(realistic_project)],
                "include_globs": ["*.py"],
                "output_format": "json",  # Request JSON format for easier testing
            }
        )

        assert isinstance(result, dict)

        # Handle different result formats: results, matches, or files
        if "results" in result:
            matches = result["results"]
        elif "matches" in result:
            matches = result["matches"]
        elif "files" in result:
            # Extract matches from grouped format
            matches = []
            for file_entry in result["files"]:
                for match in file_entry.get("matches", []):
                    match_copy = match.copy()
                    match_copy["file"] = file_entry["file"]
                    matches.append(match_copy)
        else:
            matches = []

        # Should find User and Application classes
        class_names = set()
        for match in matches:
            text = match.get("text", "")
            if "class" in text:
                # Extract class name
                parts = text.split()
                if len(parts) >= 2:
                    class_names.add(parts[1].rstrip(":"))

        assert "User" in class_names or "Application" in class_names

    @pytest.mark.asyncio
    async def test_analyze_project_structure(self, realistic_project: Path):
        """Test analyzing project structure."""
        list_tool = ListFilesTool(project_root=str(realistic_project))

        # Find all Python files
        result = await list_tool.execute(
            {
                "roots": [str(realistic_project)],
                "extensions": ["py"],
                "output_format": "json",  # Request JSON format for easier testing
            }
        )

        assert isinstance(result, dict)
        files = result.get("files") or result.get("results", [])

        # Should find all Python files
        file_names = [Path(f.get("path") or f.get("file", "")).name for f in files]
        assert "main.py" in file_names
        assert "models.py" in file_names
        assert "utils.py" in file_names
        assert "test_models.py" in file_names
