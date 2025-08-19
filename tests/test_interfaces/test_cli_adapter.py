#!/usr/bin/env python3
"""
Tests for tree_sitter_analyzer.interfaces.cli_adapter module.

This module tests the CLIAdapter class which provides a clean interface
between the CLI and the core analysis engine in the new architecture.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.interfaces.cli_adapter import CLIAdapter
from tree_sitter_analyzer.models import AnalysisResult


class TestCLIAdapter:
    """Test cases for CLIAdapter class"""

    @pytest.fixture
    def cli_adapter(self) -> CLIAdapter:
        """Create a CLIAdapter instance for testing"""
        return CLIAdapter()

    @pytest.fixture
    def sample_java_file(self) -> str:
        """Create a temporary Java file for testing"""
        content = """
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
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(content)
            return f.name

    def test_cli_adapter_initialization(self, cli_adapter: CLIAdapter) -> None:
        """Test CLIAdapter initialization"""
        assert cli_adapter is not None
        assert hasattr(cli_adapter, "analyze_file")
        assert hasattr(cli_adapter, "analyze_structure")
        assert hasattr(cli_adapter, "analyze_batch")

    def test_analyze_file_java_success(
        self, cli_adapter: CLIAdapter, sample_java_file: str
    ) -> None:
        """Test successful Java file analysis through CLI adapter"""
        try:
            result = cli_adapter.analyze_file(sample_java_file)

            assert isinstance(result, AnalysisResult)
            assert result.file_path == sample_java_file
            assert result.language == "java"
            assert result.elements is not None
            assert result.elements is not None
            assert result.node_count > 0

        finally:
            Path(sample_java_file).unlink()

    def test_analyze_file_python_success(
        self, cli_adapter: CLIAdapter, sample_python_file: str
    ) -> None:
        """Test successful Python file analysis through CLI adapter"""
        try:
            result = cli_adapter.analyze_file(sample_python_file)

            assert isinstance(result, AnalysisResult)
            assert result.file_path == sample_python_file
            assert result.language == "python"
            assert result.elements is not None
            assert result.elements is not None

        finally:
            Path(sample_python_file).unlink()

    def test_analyze_file_with_language_override(
        self, cli_adapter: CLIAdapter, sample_java_file: str
    ) -> None:
        """Test file analysis with explicit language specification"""
        try:
            result = cli_adapter.analyze_file(sample_java_file, language="java")

            assert isinstance(result, AnalysisResult)
            assert result.language == "java"

        finally:
            Path(sample_java_file).unlink()

    def test_analyze_file_with_options(
        self, cli_adapter: CLIAdapter, sample_java_file: str
    ) -> None:
        """Test file analysis with additional options"""
        try:
            result = cli_adapter.analyze_file(
                sample_java_file, include_complexity=True, include_details=True
            )

            assert isinstance(result, AnalysisResult)
            assert result.file_path == sample_java_file

        finally:
            Path(sample_java_file).unlink()

    def test_analyze_file_nonexistent(self, cli_adapter: CLIAdapter) -> None:
        """Test analysis of non-existent file"""
        with pytest.raises(FileNotFoundError):
            cli_adapter.analyze_file("/nonexistent/file.java")

    def test_analyze_file_with_path_object(
        self, cli_adapter: CLIAdapter, sample_java_file: str
    ) -> None:
        """Test file analysis with Path object"""
        try:
            path_obj = Path(sample_java_file)
            result = cli_adapter.analyze_file(str(path_obj))

            assert isinstance(result, AnalysisResult)
            assert result.file_path == str(path_obj)

        finally:
            Path(sample_java_file).unlink()

    def test_analyze_structure_success(
        self, cli_adapter: CLIAdapter, sample_java_file: str
    ) -> None:
        """Test successful structure analysis"""
        try:
            result = cli_adapter.analyze_structure(sample_java_file)

            assert isinstance(result, dict)
            assert "file_path" in result
            assert "language" in result
            assert "structure" in result or "elements" in result

        finally:
            Path(sample_java_file).unlink()

    def test_analyze_structure_with_options(
        self, cli_adapter: CLIAdapter, sample_java_file: str
    ) -> None:
        """Test structure analysis with options"""
        try:
            result = cli_adapter.analyze_structure(
                sample_java_file, include_metrics=True, include_relationships=True
            )

            assert isinstance(result, dict)

        finally:
            Path(sample_java_file).unlink()

    def test_analyze_batch_success(self, cli_adapter: CLIAdapter) -> None:
        """Test successful batch analysis"""
        files = []

        try:
            # Create Java file
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".java", delete=False
            ) as f:
                f.write("public class JavaTest { public void test() {} }")
                files.append(f.name)

            # Create Python file
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write("def python_test(): pass")
                files.append(f.name)

            results = cli_adapter.analyze_batch(files)

            assert isinstance(results, list)
            assert len(results) == 2
            assert all(isinstance(result, AnalysisResult) for result in results)
            assert results[0].language == "java"
            assert results[1].language == "python"

        finally:
            for file_path in files:
                path_obj = Path(file_path)
                if path_obj.exists():
                    path_obj.unlink()

    def test_analyze_batch_with_options(self, cli_adapter: CLIAdapter) -> None:
        """Test batch analysis with options"""
        files = []

        try:
            # Create test files
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".java", delete=False
            ) as f:
                f.write("public class Test {}")
                files.append(f.name)

            results = cli_adapter.analyze_batch(
                files, parallel=True, include_complexity=True
            )

            assert isinstance(results, list)
            assert len(results) == 1

        finally:
            for file_path in files:
                path_obj = Path(file_path)
                if path_obj.exists():
                    path_obj.unlink()

    def test_analyze_batch_empty_list(self, cli_adapter: CLIAdapter) -> None:
        """Test batch analysis with empty file list"""
        results = cli_adapter.analyze_batch([])

        assert isinstance(results, list)
        assert len(results) == 0

    def test_get_supported_languages(self, cli_adapter: CLIAdapter) -> None:
        """Test getting list of supported languages"""
        languages = cli_adapter.get_supported_languages()

        assert isinstance(languages, list)
        assert len(languages) > 0
        assert "java" in languages
        assert "python" in languages

    def test_clear_cache(self, cli_adapter: CLIAdapter) -> None:
        """Test cache clearing functionality"""
        # Should not raise any exceptions
        cli_adapter.clear_cache()

    def test_get_cache_stats(self, cli_adapter: CLIAdapter) -> None:
        """Test getting cache statistics"""
        stats = cli_adapter.get_cache_stats()

        assert isinstance(stats, dict)
        # Stats might be empty initially, but should be a dict

    def test_validate_file_existing(
        self, cli_adapter: CLIAdapter, sample_java_file: str
    ) -> None:
        """Test file validation with existing file"""
        try:
            is_valid = cli_adapter.validate_file(sample_java_file)

            assert isinstance(is_valid, bool)
            assert is_valid is True

        finally:
            Path(sample_java_file).unlink()

    def test_validate_file_nonexistent(self, cli_adapter: CLIAdapter) -> None:
        """Test file validation with non-existent file"""
        is_valid = cli_adapter.validate_file("/nonexistent/file.java")

        assert isinstance(is_valid, bool)
        assert is_valid is False

    def test_validate_file_unsupported_extension(self, cli_adapter: CLIAdapter) -> None:
        """Test file validation with unsupported extension"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xyz", delete=False) as f:
            f.write("some content")
            temp_path = f.name

        try:
            is_valid = cli_adapter.validate_file(temp_path)

            # Might be valid (file exists) or invalid (unsupported type)
            assert isinstance(is_valid, bool)

        finally:
            Path(temp_path).unlink()

    def test_get_engine_info(self, cli_adapter: CLIAdapter) -> None:
        """Test getting engine information"""
        info = cli_adapter.get_engine_info()

        assert isinstance(info, dict)
        # Should contain information about the underlying engine


class TestCLIAdapterErrorHandling:
    """Test error handling in CLIAdapter"""

    @pytest.fixture
    def cli_adapter(self) -> CLIAdapter:
        """Create a CLIAdapter instance for testing"""
        return CLIAdapter()

    def test_analyze_file_permission_error(self, cli_adapter: CLIAdapter) -> None:
        """Test handling of file permission errors"""
        with patch.object(cli_adapter, "_engine") as mock_engine:
            mock_engine.analyze.side_effect = PermissionError("Permission denied")

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".java", delete=False
            ) as f:
                f.write("public class Test {}")
                temp_path = f.name

            try:
                with pytest.raises(PermissionError):
                    cli_adapter.analyze_file(temp_path)
            finally:
                Path(temp_path).unlink()

    def test_analyze_file_unsupported_language(self, cli_adapter: CLIAdapter) -> None:
        """Test analysis with unsupported language"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xyz", delete=False) as f:
            f.write("some content")
            temp_path = f.name

        try:
            with pytest.raises((FileNotFoundError, Exception)):
                cli_adapter.analyze_file(temp_path)

        finally:
            Path(temp_path).unlink()

    def test_analyze_structure_nonexistent_file(self, cli_adapter: CLIAdapter) -> None:
        """Test structure analysis with non-existent file"""
        with pytest.raises(FileNotFoundError):
            cli_adapter.analyze_structure("/nonexistent/file.java")

    def test_analyze_batch_with_mixed_files(self, cli_adapter: CLIAdapter) -> None:
        """Test batch analysis with mix of valid and invalid files"""
        files = []

        try:
            # Create valid file
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".java", delete=False
            ) as f:
                f.write("public class Test {}")
                files.append(f.name)

            # Add non-existent file
            files.append("/nonexistent/file.java")

            results = cli_adapter.analyze_batch(files)

            # Should handle gracefully, might return partial results or handle errors
            assert isinstance(results, list)

        finally:
            for file_path in files:
                path_obj = Path(file_path)
                if path_obj.exists():
                    path_obj.unlink()

    def test_analyze_file_engine_failure(self, cli_adapter: CLIAdapter) -> None:
        """Test handling of analysis engine failure"""
        with patch.object(cli_adapter, "_engine") as mock_engine:
            mock_engine.analyze.side_effect = Exception("Engine not available")

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".java", delete=False
            ) as f:
                f.write("public class Test {}")
                temp_path = f.name

            try:
                # Should handle engine failure gracefully
                with pytest.raises(Exception, match="Engine not available"):
                    cli_adapter.analyze_file(temp_path)

            finally:
                Path(temp_path).unlink()


class TestCLIAdapterIntegration:
    """Integration tests for CLIAdapter"""

    @pytest.fixture
    def cli_adapter(self) -> CLIAdapter:
        """Create a CLIAdapter instance for testing"""
        return CLIAdapter()

    def test_full_analysis_workflow(self, cli_adapter: CLIAdapter) -> None:
        """Test complete analysis workflow through CLI adapter"""
        java_code = """
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
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(java_code)
            temp_path = f.name

        try:
            # Step 1: Validate file
            assert cli_adapter.validate_file(temp_path) is True

            # Step 2: Analyze file
            result = cli_adapter.analyze_file(temp_path)
            assert isinstance(result, AnalysisResult)
            assert result.language == "java"

            # Step 3: Analyze structure
            structure = cli_adapter.analyze_structure(temp_path)
            assert isinstance(structure, dict)

            # Step 4: Get engine info
            engine_info = cli_adapter.get_engine_info()
            assert isinstance(engine_info, dict)

        finally:
            Path(temp_path).unlink()

    def test_multiple_file_analysis_workflow(self, cli_adapter: CLIAdapter) -> None:
        """Test analysis workflow with multiple files"""
        files = []

        try:
            # Create Java file
            java_code = "public class JavaTest { public void test() {} }"
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".java", delete=False
            ) as f:
                f.write(java_code)
                files.append(f.name)

            # Create Python file
            python_code = "def python_test(): pass"
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(python_code)
                files.append(f.name)

            # Validate all files
            for file_path in files:
                assert cli_adapter.validate_file(file_path) is True

            # Batch analysis
            results = cli_adapter.analyze_batch(files)
            assert len(results) == 2
            assert results[0].language == "java"
            assert results[1].language == "python"

            # Individual analysis
            for file_path in files:
                result = cli_adapter.analyze_file(file_path)
                assert isinstance(result, AnalysisResult)

        finally:
            for file_path in files:
                path_obj = Path(file_path)
                if path_obj.exists():
                    path_obj.unlink()

    def test_cli_adapter_performance_with_large_file(
        self, cli_adapter: CLIAdapter
    ) -> None:
        """Test CLI adapter performance with large code files"""
        # Create a large Java class
        large_code = "public class LargeClass {\n"
        for i in range(100):
            large_code += f"""
    public void method{i}() {{
        System.out.println("Method {i}");
        int value = {i};
        return;
    }}
"""
        large_code += "}"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(large_code)
            temp_path = f.name

        try:
            # Should handle large files efficiently
            result = cli_adapter.analyze_file(temp_path)
            assert isinstance(result, AnalysisResult)
            assert result.node_count > 0

        finally:
            Path(temp_path).unlink()

    def test_cli_adapter_caching_behavior(self, cli_adapter: CLIAdapter) -> None:
        """Test CLI adapter caching behavior"""
        java_code = "public class Test { public void method() {} }"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(java_code)
            temp_path = f.name

        try:
            # First analysis
            result1 = cli_adapter.analyze_file(temp_path)

            # Get cache stats
            # stats_before = cli_adapter.get_cache_stats()  # Not used currently

            # Second analysis (might use cache)
            result2 = cli_adapter.analyze_file(temp_path)

            # Results should be consistent
            assert result1.language == result2.language
            assert result1.file_path == result2.file_path

            # Clear cache
            cli_adapter.clear_cache()

            # Third analysis (should not use cache)
            result3 = cli_adapter.analyze_file(temp_path)
            assert result3.language == result1.language

        finally:
            Path(temp_path).unlink()
