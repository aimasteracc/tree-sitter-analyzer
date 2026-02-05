"""
Integration tests for complex Python language features.

Tests advanced features using complex_sample.py fixture:
- Decorators (function, class, property)
- Class attributes
- Async functions and methods
- Nested classes
- Multiple inheritance
"""

from pathlib import Path

import pytest


@pytest.fixture
def complex_sample():
    """Return path to complex sample fixture."""
    return Path(__file__).parent.parent / "fixtures" / "analyze_fixtures" / "complex_sample.py"


class TestComplexFeatures:
    """Test parsing of complex Python features."""

    def test_parse_complex_file(self, complex_sample):
        """Test that complex file can be parsed without errors."""
        from tree_sitter_analyzer_v2.languages import PythonParser

        parser = PythonParser()
        content = complex_sample.read_text(encoding="utf-8")

        result = parser.parse(content, str(complex_sample))

        assert result is not None
        assert result["errors"] is False  # Should parse successfully

    def test_decorator_extraction(self, complex_sample):
        """Test extraction of various decorator types."""
        from tree_sitter_analyzer_v2.languages import PythonParser

        parser = PythonParser()
        content = complex_sample.read_text(encoding="utf-8")
        result = parser.parse(content, str(complex_sample))

        # Find Configuration class (has @dataclass decorator)
        config_class = next((c for c in result["classes"] if c["name"] == "Configuration"), None)
        assert config_class is not None
        assert "decorators" in config_class
        assert "dataclass" in config_class["decorators"]

        # Find complex_calculation function (has multiple decorators)
        calc_func = next(
            (f for f in result["functions"] if f["name"] == "complex_calculation"), None
        )
        assert calc_func is not None
        assert "decorators" in calc_func
        assert len(calc_func["decorators"]) >= 2

    def test_class_attributes_extraction(self, complex_sample):
        """Test extraction of class-level attributes."""
        from tree_sitter_analyzer_v2.languages import PythonParser

        parser = PythonParser()
        content = complex_sample.read_text(encoding="utf-8")
        result = parser.parse(content, str(complex_sample))

        # Configuration class has class attributes
        config_class = next((c for c in result["classes"] if c["name"] == "Configuration"), None)
        assert config_class is not None
        assert "attributes" in config_class
        assert len(config_class["attributes"]) > 0

        # Check for specific class attributes
        attr_names = [a["name"] for a in config_class["attributes"]]
        assert "DEFAULT_TIMEOUT" in attr_names
        assert "MAX_RETRIES" in attr_names
        assert "VERSION" in attr_names

    def test_async_function_detection(self, complex_sample):
        """Test detection of async functions."""
        from tree_sitter_analyzer_v2.languages import PythonParser

        parser = PythonParser()
        content = complex_sample.read_text(encoding="utf-8")
        result = parser.parse(content, str(complex_sample))

        # Find async functions
        async_funcs = [f for f in result["functions"] if f.get("is_async")]
        assert len(async_funcs) >= 2  # fetch_data, cached_fetch, main

        # Check specific async function
        fetch_data = next((f for f in result["functions"] if f["name"] == "fetch_data"), None)
        assert fetch_data is not None
        assert fetch_data["is_async"] is True

    def test_async_method_detection(self, complex_sample):
        """Test detection of async methods in classes."""
        from tree_sitter_analyzer_v2.languages import PythonParser

        parser = PythonParser()
        content = complex_sample.read_text(encoding="utf-8")
        result = parser.parse(content, str(complex_sample))

        # DataStore has async method save_async
        datastore_class = next((c for c in result["classes"] if c["name"] == "DataStore"), None)
        assert datastore_class is not None

        async_methods = [m for m in datastore_class["methods"] if m.get("is_async")]
        assert len(async_methods) >= 1

        save_async = next(
            (m for m in datastore_class["methods"] if m["name"] == "save_async"), None
        )
        assert save_async is not None
        assert save_async["is_async"] is True

    def test_property_decorator_detection(self, complex_sample):
        """Test detection of @property decorators."""
        from tree_sitter_analyzer_v2.languages import PythonParser

        parser = PythonParser()
        content = complex_sample.read_text(encoding="utf-8")
        result = parser.parse(content, str(complex_sample))

        # Configuration class has @property endpoint
        config_class = next((c for c in result["classes"] if c["name"] == "Configuration"), None)
        assert config_class is not None

        # Find property methods
        property_methods = [
            m for m in config_class["methods"] if "property" in m.get("decorators", [])
        ]
        assert len(property_methods) > 0

    def test_nested_class_detection(self, complex_sample):
        """Test detection of nested classes."""
        from tree_sitter_analyzer_v2.languages import PythonParser

        parser = PythonParser()
        content = complex_sample.read_text(encoding="utf-8")
        result = parser.parse(content, str(complex_sample))

        # Should find nested Transaction class
        nested_class = next((c for c in result["classes"] if c["name"] == "Transaction"), None)
        assert nested_class is not None

    def test_multiple_inheritance(self, complex_sample):
        """Test detection of multiple base classes."""
        from tree_sitter_analyzer_v2.languages import PythonParser

        parser = PythonParser()
        content = complex_sample.read_text(encoding="utf-8")
        result = parser.parse(content, str(complex_sample))

        # DataStore inherits from Loggable and Serializable
        datastore_class = next((c for c in result["classes"] if c["name"] == "DataStore"), None)
        assert datastore_class is not None
        assert "bases" in datastore_class
        assert len(datastore_class["bases"]) >= 2

    def test_main_block_detection(self, complex_sample):
        """Test detection of main block."""
        from tree_sitter_analyzer_v2.languages import PythonParser

        parser = PythonParser()
        content = complex_sample.read_text(encoding="utf-8")
        result = parser.parse(content, str(complex_sample))

        assert "has_main_block" in result["metadata"]
        assert result["metadata"]["has_main_block"] is True

    def test_structure_counts(self, complex_sample):
        """Test overall structure counts."""
        from tree_sitter_analyzer_v2.languages import PythonParser

        parser = PythonParser()
        content = complex_sample.read_text(encoding="utf-8")
        result = parser.parse(content, str(complex_sample))

        # Should have multiple classes
        assert result["metadata"]["total_classes"] >= 7

        # Should have multiple functions
        assert result["metadata"]["total_functions"] >= 4

        # Should have imports
        assert result["metadata"]["total_imports"] >= 5


class TestCheckCodeScaleWithComplexFile:
    """Test check_code_scale tool with complex file."""

    def test_analyze_complex_file(self, complex_sample):
        """Test analyzing complex file with check_code_scale."""
        from tree_sitter_analyzer_v2.mcp.tools.scale import CheckCodeScaleTool

        tool = CheckCodeScaleTool()

        result = tool.execute({"file_path": str(complex_sample), "include_details": True})

        assert result["success"] is True

        # Check structure counts
        structure = result["structure"]
        assert structure["total_classes"] >= 7
        assert structure["total_functions"] >= 4

        # Check details included
        assert "classes" in structure
        assert "functions" in structure
        assert len(structure["classes"]) >= 7
        assert len(structure["functions"]) >= 4

    def test_complex_file_size_category(self, complex_sample):
        """Test size categorization of complex file."""
        from tree_sitter_analyzer_v2.mcp.tools.scale import CheckCodeScaleTool

        tool = CheckCodeScaleTool()

        result = tool.execute({"file_path": str(complex_sample)})

        assert result["success"] is True
        assert "guidance" in result

        # Complex file is ~230 lines, should be "medium"
        assert result["guidance"]["size_category"] == "medium"
