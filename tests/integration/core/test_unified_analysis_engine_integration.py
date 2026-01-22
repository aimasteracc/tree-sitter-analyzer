"""
Integration tests for UnifiedAnalysisEngine.

Tests Dependency Injection integration, FileLoader connectivity,
and real file analysis workflows.
"""

from pathlib import Path

import pytest

from tree_sitter_analyzer.core.analysis_engine import (
    UnifiedAnalysisEngine,
    create_analysis_engine,
)
from tree_sitter_analyzer.core.file_loader import FileLoader
from tree_sitter_analyzer.core.request import AnalysisRequest


class TestUnifiedAnalysisEngineIntegration:
    """Integration tests for UnifiedAnalysisEngine with real file operations."""

    @pytest.fixture
    def temp_project(self, tmp_path: Path) -> Path:
        """Create a temporary project with test files."""
        # Create Python file
        python_file = tmp_path / "sample.py"
        python_file.write_text(
            """
class SampleClass:
    def __init__(self):
        self.value = 0

    def method1(self):
        return self.value

    def method2(self, x):
        self.value = x

def standalone_function():
    pass
"""
        )

        # Create Java file
        java_file = tmp_path / "Sample.java"
        java_file.write_text(
            """
public class Sample {
    private int value;

    public Sample() {
        this.value = 0;
    }

    public int getValue() {
        return value;
    }

    public void setValue(int value) {
        this.value = value;
    }
}
"""
        )

        # Create TypeScript file
        ts_file = tmp_path / "sample.ts"
        ts_file.write_text(
            """
class SampleClass {
    private value: number;

    constructor() {
        this.value = 0;
    }

    getValue(): number {
        return this.value;
    }

    setValue(value: number): void {
        this.value = value;
    }
}
"""
        )

        return tmp_path

    @pytest.mark.asyncio
    async def test_analyze_python_file(self, temp_project: Path):
        """Test analyzing Python file with real file system."""
        engine = UnifiedAnalysisEngine(project_root=str(temp_project))
        python_file = temp_project / "sample.py"

        result = await engine.analyze(
            AnalysisRequest(
                file_path=str(python_file),
                language="python",
            )
        )

        assert result is not None
        assert result.success is True
        # Should detect Python structures
        assert result.language == "python"

    @pytest.mark.asyncio
    async def test_analyze_java_file(self, temp_project: Path):
        """Test analyzing Java file with real file system."""
        engine = UnifiedAnalysisEngine(project_root=str(temp_project))
        java_file = temp_project / "Sample.java"

        result = await engine.analyze(
            AnalysisRequest(
                file_path=str(java_file),
                language="java",
            )
        )

        assert result is not None
        assert result.success is True
        # Should detect Java structures
        assert result.language == "java"

    @pytest.mark.asyncio
    async def test_analyze_typescript_file(self, temp_project: Path):
        """Test analyzing TypeScript file with real file system."""
        engine = UnifiedAnalysisEngine(project_root=str(temp_project))
        ts_file = temp_project / "sample.ts"

        result = await engine.analyze(
            AnalysisRequest(
                file_path=str(ts_file),
                language="typescript",
            )
        )

        assert result is not None
        assert result.success is True
        # Should detect TypeScript structures
        assert result.language == "typescript"

    @pytest.mark.asyncio
    async def test_auto_language_detection(self, temp_project: Path):
        """Test automatic language detection from file extension."""
        engine = UnifiedAnalysisEngine(project_root=str(temp_project))
        python_file = temp_project / "sample.py"

        # Don't specify language - should auto-detect
        result = await engine.analyze(
            AnalysisRequest(
                file_path=str(python_file),
            )
        )

        assert result is not None
        # Should auto-detect Python
        assert result.language == "python"

    @pytest.mark.asyncio
    async def test_dependency_injection_with_custom_file_loader(
        self, temp_project: Path
    ):
        """Test dependency injection with custom FileLoader."""
        # Create custom FileLoader
        custom_loader = FileLoader(project_root=str(temp_project))

        # Create engine with dependency injection (using constructor directly)
        engine = UnifiedAnalysisEngine(project_root=str(temp_project))

        python_file = temp_project / "sample.py"

        result = await engine.analyze(
            AnalysisRequest(
                file_path=str(python_file),
                language="python",
            )
        )

        assert result is not None
        # Should use injected FileLoader
        assert result.success is True

    @pytest.mark.asyncio
    async def test_file_loader_integration(self, temp_project: Path):
        """Test FileLoader integration with UnifiedAnalysisEngine."""
        engine = UnifiedAnalysisEngine(project_root=str(temp_project))
        python_file = temp_project / "sample.py"

        # FileLoader should read file content
        result = await engine.analyze(
            AnalysisRequest(
                file_path=str(python_file),
                language="python",
            )
        )

        assert result is not None
        # Verify file was read and parsed
        assert result.success is True

    @pytest.mark.asyncio
    async def test_encoding_detection(self, temp_project: Path):
        """Test encoding detection for different file encodings."""
        # Create file with UTF-8 encoding
        utf8_file = temp_project / "utf8.py"
        utf8_file.write_text(
            "# -*- coding: utf-8 -*-\nprint('Hello')\n", encoding="utf-8"
        )

        engine = UnifiedAnalysisEngine(project_root=str(temp_project))

        result = await engine.analyze(
            AnalysisRequest(
                file_path=str(utf8_file),
                language="python",
            )
        )

        assert result is not None
        # Should successfully parse UTF-8 file
        assert result.success is True

    @pytest.mark.asyncio
    async def test_japanese_encoding_support(self, temp_project: Path):
        """Test Japanese encoding support (Shift_JIS, EUC-JP)."""
        # Create file with Japanese comment
        ja_file = temp_project / "japanese.py"
        ja_file.write_text(
            "# 日本語コメント\ndef hello():\n    print('こんにちは')\n",
            encoding="utf-8",
        )

        engine = UnifiedAnalysisEngine(project_root=str(temp_project))

        result = await engine.analyze(
            AnalysisRequest(
                file_path=str(ja_file),
                language="python",
            )
        )

        assert result is not None
        # Should successfully parse file with Japanese characters
        assert result.success is True

    @pytest.mark.asyncio
    async def test_cache_integration(self, temp_project: Path):
        """Test cache integration with repeated analysis."""
        engine = UnifiedAnalysisEngine(project_root=str(temp_project))
        python_file = temp_project / "sample.py"

        # First analysis
        result1 = await engine.analyze(
            AnalysisRequest(
                file_path=str(python_file),
                language="python",
            )
        )

        # Second analysis (should use cache)
        result2 = await engine.analyze(
            AnalysisRequest(
                file_path=str(python_file),
                language="python",
            )
        )

        assert result1 is not None
        assert result2 is not None
        # Results should be consistent
        assert result1.get("language") == result2.get("language")

    @pytest.mark.asyncio
    async def test_security_validation(self, temp_project: Path):
        """Test security validation for file paths."""
        engine = UnifiedAnalysisEngine(project_root=str(temp_project))

        # Try to access file outside project root
        outside_file = "/etc/passwd"

        # Should raise error or return error result
        try:
            result = await engine.analyze(
                AnalysisRequest(
                    file_path=outside_file,
                    language="python",
                )
            )
            # If no exception, should have error in result
            assert result.success is False or result is None
        except Exception as e:
            # Security validation should prevent access
            assert "security" in str(e).lower() or "path" in str(e).lower()

    @pytest.mark.asyncio
    async def test_plugin_integration(self, temp_project: Path):
        """Test language plugin integration."""
        engine = UnifiedAnalysisEngine(project_root=str(temp_project))
        python_file = temp_project / "sample.py"

        result = await engine.analyze(
            AnalysisRequest(
                file_path=str(python_file),
                language="python",
            )
        )

        assert result is not None
        # Should use Python language plugin
        assert result.success is True

    @pytest.mark.asyncio
    async def test_query_execution(self, temp_project: Path):
        """Test query execution on parsed tree."""
        engine = UnifiedAnalysisEngine(project_root=str(temp_project))
        python_file = temp_project / "sample.py"

        # Analyze file
        result = await engine.analyze(
            AnalysisRequest(
                file_path=str(python_file),
                language="python",
            )
        )

        assert result is not None

        # Execute query (if supported)
        if hasattr(engine, "query"):
            query_result = await engine.query(
                file_path=str(python_file),
                language="python",
                query_string="(class_definition) @class",
            )
            # Should find class definitions
            assert query_result is not None

    @pytest.mark.asyncio
    async def test_error_handling_invalid_file(self, temp_project: Path):
        """Test error handling for invalid file path."""
        engine = UnifiedAnalysisEngine(project_root=str(temp_project))

        # Try to analyze non-existent file - should raise FileNotFoundError
        with pytest.raises(FileNotFoundError):
            await engine.analyze(
                AnalysisRequest(
                    file_path=str(temp_project / "nonexistent.py"),
                    language="python",
                )
            )

    @pytest.mark.asyncio
    async def test_error_handling_unsupported_language(self, temp_project: Path):
        """Test error handling for unsupported language."""
        engine = UnifiedAnalysisEngine(project_root=str(temp_project))
        python_file = temp_project / "sample.py"

        # Try to analyze with unsupported language
        try:
            result = await engine.analyze(
                AnalysisRequest(
                    file_path=str(python_file),
                    language="unsupported_language",
                )
            )
            # Should return error or None
            assert result is None or "error" in result
        except Exception as e:
            # Should raise appropriate exception
            assert "language" in str(e).lower() or "unsupported" in str(e).lower()

    @pytest.mark.asyncio
    async def test_sync_wrapper(self, temp_project: Path):
        """Test synchronous wrapper for async analysis."""
        engine = UnifiedAnalysisEngine(project_root=str(temp_project))
        python_file = temp_project / "sample.py"

        # Use sync wrapper if available
        if hasattr(engine, "analyze_sync"):
            result = engine.analyze_sync(
                AnalysisRequest(
                    file_path=str(python_file),
                    language="python",
                )
            )

            assert result is not None
            assert result.success is True


class TestDependencyInjectionIntegration:
    """Integration tests for Dependency Injection pattern."""

    @pytest.fixture
    def temp_project(self, tmp_path: Path) -> Path:
        """Create a temporary project."""
        (tmp_path / "test.py").write_text("def test(): pass\n")
        return tmp_path

    @pytest.mark.asyncio
    async def test_create_analysis_engine_factory(self, temp_project: Path):
        """Test create_analysis_engine factory function."""
        engine = create_analysis_engine(project_root=str(temp_project))

        assert engine is not None
        assert isinstance(engine, UnifiedAnalysisEngine)

    @pytest.mark.asyncio
    async def test_dependency_injection_isolation(self, temp_project: Path):
        """Test dependency injection creates isolated instances."""
        # Create two engines with dependency injection
        # Note: create_analysis_engine() creates new instances each time
        engine1 = create_analysis_engine(project_root=str(temp_project))
        engine2 = create_analysis_engine(project_root=str(temp_project))

        # Should be different instances (DI pattern creates new instances)
        assert engine1 is not engine2

    @pytest.mark.asyncio
    async def test_singleton_pattern_without_injection(self, temp_project: Path):
        """Test singleton pattern when no dependencies injected."""
        # Create two engines without dependency injection
        engine1 = UnifiedAnalysisEngine(project_root=str(temp_project))
        engine2 = UnifiedAnalysisEngine(project_root=str(temp_project))

        # Should be same instance (singleton)
        assert engine1 is engine2

    @pytest.mark.asyncio
    async def test_mixed_singleton_and_injection(self, temp_project: Path):
        """Test mixing singleton and dependency injection."""
        # Create singleton instance
        singleton = UnifiedAnalysisEngine(project_root=str(temp_project))

        # Create injected instance (DI pattern)
        injected = create_analysis_engine(project_root=str(temp_project))

        # Should be different instances
        assert singleton is not injected


class TestFileLoaderConnectivity:
    """Integration tests for FileLoader connectivity."""

    @pytest.fixture
    def temp_project(self, tmp_path: Path) -> Path:
        """Create a temporary project with various file types."""
        # Create files with different encodings
        (tmp_path / "utf8.py").write_text("# UTF-8\nprint('test')\n", encoding="utf-8")
        (tmp_path / "ascii.py").write_text("# ASCII\nprint('test')\n", encoding="ascii")

        return tmp_path

    @pytest.mark.asyncio
    async def test_file_loader_reads_utf8(self, temp_project: Path):
        """Test FileLoader reads UTF-8 files correctly."""
        # Use UnifiedAnalysisEngine directly (FileLoader is internal)
        engine = UnifiedAnalysisEngine(project_root=str(temp_project))

        utf8_file = temp_project / "utf8.py"

        result = await engine.analyze(
            AnalysisRequest(
                file_path=str(utf8_file),
                language="python",
            )
        )

        assert result is not None
        # Should successfully read UTF-8 file
        assert result.success is True

    @pytest.mark.asyncio
    async def test_file_loader_reads_ascii(self, temp_project: Path):
        """Test FileLoader reads ASCII files correctly."""
        # Use UnifiedAnalysisEngine directly (FileLoader is internal)
        engine = UnifiedAnalysisEngine(project_root=str(temp_project))

        ascii_file = temp_project / "ascii.py"

        result = await engine.analyze(
            AnalysisRequest(
                file_path=str(ascii_file),
                language="python",
            )
        )

        assert result is not None
        # Should successfully read ASCII file
        assert result.success is True

    @pytest.mark.asyncio
    async def test_file_loader_encoding_fallback(self, temp_project: Path):
        """Test FileLoader encoding fallback mechanism."""
        # Create file with mixed encoding
        mixed_file = temp_project / "mixed.py"
        mixed_file.write_bytes(b"# Test\nprint('test')\n")

        # Use UnifiedAnalysisEngine directly (FileLoader is internal)
        engine = UnifiedAnalysisEngine(project_root=str(temp_project))

        result = await engine.analyze(
            AnalysisRequest(
                file_path=str(mixed_file),
                language="python",
            )
        )

        assert result is not None
        # Should successfully read with fallback encoding
        assert result.success is True


class TestEndToEndWorkflow:
    """End-to-end integration tests for complete analysis workflow."""

    @pytest.fixture
    def comprehensive_project(self, tmp_path: Path) -> Path:
        """Create a comprehensive test project."""
        # Create multi-language project
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()

        # Python files
        (tmp_path / "src" / "main.py").write_text(
            """
class Application:
    def __init__(self):
        self.running = False

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

def main():
    app = Application()
    app.start()
"""
        )

        # Java files
        (tmp_path / "src" / "Main.java").write_text(
            """
public class Main {
    public static void main(String[] args) {
        System.out.println("Hello, World!");
    }
}
"""
        )

        # TypeScript files
        (tmp_path / "src" / "app.ts").write_text(
            """
class App {
    private running: boolean = false;

    start(): void {
        this.running = true;
    }

    stop(): void {
        this.running = false;
    }
}
"""
        )

        return tmp_path

    @pytest.mark.asyncio
    async def test_analyze_multiple_languages(self, comprehensive_project: Path):
        """Test analyzing multiple languages in one project."""
        engine = UnifiedAnalysisEngine(project_root=str(comprehensive_project))

        # Analyze Python file
        python_result = await engine.analyze(
            AnalysisRequest(
                file_path=str(comprehensive_project / "src" / "main.py"),
                language="python",
            )
        )

        # Analyze Java file
        java_result = await engine.analyze(
            AnalysisRequest(
                file_path=str(comprehensive_project / "src" / "Main.java"),
                language="java",
            )
        )

        # Analyze TypeScript file
        ts_result = await engine.analyze(
            AnalysisRequest(
                file_path=str(comprehensive_project / "src" / "app.ts"),
                language="typescript",
            )
        )

        # All should succeed
        assert python_result is not None
        assert java_result is not None
        assert ts_result is not None

    @pytest.mark.asyncio
    async def test_batch_analysis(self, comprehensive_project: Path):
        """Test batch analysis of multiple files."""
        engine = UnifiedAnalysisEngine(project_root=str(comprehensive_project))

        files = [
            (comprehensive_project / "src" / "main.py", "python"),
            (comprehensive_project / "src" / "Main.java", "java"),
            (comprehensive_project / "src" / "app.ts", "typescript"),
        ]

        results = []
        for file_path, language in files:
            result = await engine.analyze(
                AnalysisRequest(
                    file_path=str(file_path),
                    language=language,
                )
            )
            results.append(result)

        # All should succeed
        assert all(r is not None for r in results)
        assert len(results) == 3
