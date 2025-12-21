#!/usr/bin/env python3
"""
Property-based tests for serialization round-trip consistency.

**Feature: test-coverage-improvement, Property 1: Serialization Round-Trip Consistency**

Tests that serializing analysis results to JSON and deserializing produces
equivalent data structures.

**Validates: Requirements 2.4, 6.4, 10.3**
"""

import json

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer.formatters.java_formatter import JavaTableFormatter
from tree_sitter_analyzer.models import (
    AnalysisResult,
    Class,
    Function,
    Import,
    JavaPackage,
    Package,
    Variable,
)

# ========================================
# Hypothesis Strategies for Code Elements
# ========================================

# Strategy for generating valid identifiers
identifier = st.sampled_from(
    [
        "TestClass",
        "MyClass",
        "Service",
        "Controller",
        "Repository",
        "User",
        "Order",
        "Product",
        "Item",
        "Config",
        "Handler",
        "Manager",
        "name",
        "value",
        "data",
        "result",
        "count",
        "index",
        "status",
        "getName",
        "setValue",
        "process",
        "execute",
        "validate",
        "create",
        "field1",
        "field2",
        "method1",
        "method2",
        "param1",
        "param2",
        "MyService",
        "DataProcessor",
        "EventHandler",
        "RequestMapper",
    ]
)

# Strategy for package names
package_name = st.sampled_from(
    [
        "com.example",
        "com.test",
        "org.sample",
        "net.app",
        "com.example.service",
        "com.example.model",
        "com.example.util",
    ]
)

# Strategy for Java types
java_type = st.sampled_from(
    [
        "int",
        "long",
        "double",
        "float",
        "boolean",
        "byte",
        "short",
        "char",
        "void",
        "String",
        "Object",
        "Integer",
        "Long",
        "Double",
        "Boolean",
        "List<String>",
        "Map<String,Object>",
        "Set<Integer>",
    ]
)

# Strategy for visibility
visibility = st.sampled_from(["public", "private", "protected", "package"])

# Strategy for line numbers
line_number = st.integers(min_value=1, max_value=1000)


# Strategy for generating a Function element
@st.composite
def function_element(draw):
    start = draw(line_number)
    end = start + draw(st.integers(min_value=1, max_value=50))
    return Function(
        name=draw(identifier),
        start_line=start,
        end_line=end,
        raw_text="",
        language="java",
        docstring=draw(st.text(min_size=0, max_size=50)) or None,
        element_type="function",
        parameters=draw(
            st.lists(st.text(min_size=1, max_size=20), min_size=0, max_size=3)
        ),
        return_type=draw(java_type),
        modifiers=draw(
            st.lists(
                st.sampled_from(["static", "final", "abstract", "synchronized"]),
                min_size=0,
                max_size=2,
                unique=True,
            )
        ),
        is_async=draw(st.booleans()),
        is_static=draw(st.booleans()),
        is_private=draw(st.booleans()),
        is_public=draw(st.booleans()),
        is_constructor=draw(st.booleans()),
        visibility=draw(visibility),
    )


# Strategy for generating a Class element
@st.composite
def class_element(draw):
    start = draw(line_number)
    end = start + draw(st.integers(min_value=10, max_value=200))
    return Class(
        name=draw(identifier),
        start_line=start,
        end_line=end,
        raw_text="",
        language="java",
        docstring=draw(st.text(min_size=0, max_size=50)) or None,
        element_type="class",
        class_type=draw(st.sampled_from(["class", "interface", "enum", "record"])),
        full_qualified_name=draw(st.text(min_size=0, max_size=50)) or None,
        package_name=draw(package_name) if draw(st.booleans()) else None,
        superclass=draw(identifier) if draw(st.booleans()) else None,
        interfaces=draw(st.lists(identifier, min_size=0, max_size=3)),
        modifiers=draw(
            st.lists(
                st.sampled_from(["public", "abstract", "final"]),
                min_size=0,
                max_size=2,
                unique=True,
            )
        ),
        visibility=draw(visibility),
    )


# Strategy for generating a Variable element
@st.composite
def variable_element(draw):
    start = draw(line_number)
    return Variable(
        name=draw(identifier),
        start_line=start,
        end_line=start,
        raw_text="",
        language="java",
        docstring=draw(st.text(min_size=0, max_size=50)) or None,
        element_type="variable",
        variable_type=draw(java_type),
        modifiers=draw(
            st.lists(
                st.sampled_from(["static", "final", "volatile"]),
                min_size=0,
                max_size=2,
                unique=True,
            )
        ),
        is_constant=draw(st.booleans()),
        is_static=draw(st.booleans()),
        visibility=draw(visibility),
        field_type=draw(java_type),
    )


# Strategy for generating an Import element
@st.composite
def import_element(draw):
    start = draw(st.integers(min_value=1, max_value=20))
    pkg = draw(package_name)
    cls = draw(identifier)
    return Import(
        name=f"{pkg}.{cls}",
        start_line=start,
        end_line=start,
        raw_text=f"import {pkg}.{cls};",
        language="java",
        element_type="import",
        module_name=pkg,
        module_path=pkg,
        imported_names=[cls],
        is_wildcard=draw(st.booleans()),
        is_static=draw(st.booleans()),
    )


# Strategy for generating a Package element
@st.composite
def package_element(draw):
    return Package(
        name=draw(package_name),
        start_line=1,
        end_line=1,
        raw_text="",
        language="java",
        element_type="package",
    )


# Strategy for generating a complete AnalysisResult
@st.composite
def analysis_result(draw):
    pkg_name = draw(package_name)
    classes = draw(st.lists(class_element(), min_size=0, max_size=3))
    methods = draw(st.lists(function_element(), min_size=0, max_size=5))
    fields = draw(st.lists(variable_element(), min_size=0, max_size=5))
    imports = draw(st.lists(import_element(), min_size=0, max_size=5))

    # Create package element
    pkg = Package(
        name=pkg_name,
        start_line=1,
        end_line=1,
        raw_text="",
        language="java",
        element_type="package",
    )

    # Combine all elements
    elements = [pkg] + list(classes) + list(methods) + list(fields) + list(imports)

    return AnalysisResult(
        file_path=f"src/{draw(identifier)}.java",
        language="java",
        line_count=draw(st.integers(min_value=10, max_value=1000)),
        elements=elements,
        node_count=draw(st.integers(min_value=1, max_value=500)),
        query_results={},
        source_code="",
        package=JavaPackage(name=pkg_name, start_line=1, end_line=1),
        analysis_time=draw(st.floats(min_value=0.0, max_value=10.0)),
        success=True,
        error_message=None,
    )


# Strategy for generating Java formatter analysis data (dict format)
@st.composite
def java_formatter_data(draw):
    """Generate data in the format expected by JavaTableFormatter."""
    classes = draw(
        st.lists(
            st.fixed_dictionaries(
                {
                    "name": identifier,
                    "type": st.sampled_from(["class", "interface", "enum", "record"]),
                    "visibility": visibility,
                    "line_range": st.builds(
                        lambda s, length: {"start": s, "end": s + length},
                        s=st.integers(min_value=1, max_value=100),
                        length=st.integers(min_value=10, max_value=100),
                    ),
                }
            ),
            min_size=1,
            max_size=3,
        )
    )

    methods = draw(
        st.lists(
            st.fixed_dictionaries(
                {
                    "name": identifier,
                    "visibility": st.sampled_from(["public", "private"]),
                    "return_type": java_type,
                    "parameters": st.lists(
                        st.fixed_dictionaries(
                            {
                                "name": identifier,
                                "type": java_type,
                            }
                        ),
                        min_size=0,
                        max_size=3,
                    ),
                    "is_constructor": st.booleans(),
                    "line_range": st.builds(
                        lambda s, length: {"start": s, "end": s + length},
                        s=st.integers(min_value=1, max_value=100),
                        length=st.integers(min_value=1, max_value=20),
                    ),
                    "complexity_score": st.integers(min_value=1, max_value=20),
                    "javadoc": st.text(min_size=0, max_size=50),
                }
            ),
            min_size=0,
            max_size=5,
        )
    )

    fields = draw(
        st.lists(
            st.fixed_dictionaries(
                {
                    "name": identifier,
                    "type": java_type,
                    "visibility": visibility,
                    "modifiers": st.lists(
                        st.sampled_from(["static", "final", "volatile"]),
                        min_size=0,
                        max_size=2,
                        unique=True,
                    ),
                    "line_range": st.builds(
                        lambda s: {"start": s, "end": s},
                        s=st.integers(min_value=1, max_value=100),
                    ),
                    "javadoc": st.text(min_size=0, max_size=50),
                }
            ),
            min_size=0,
            max_size=5,
        )
    )

    imports = draw(
        st.lists(
            st.builds(
                lambda pkg, cls: {"statement": f"import {pkg}.{cls};"},
                pkg=package_name,
                cls=identifier,
            ),
            min_size=0,
            max_size=5,
        )
    )

    return {
        "package": {"name": draw(package_name)},
        "file_path": f"{draw(identifier)}.java",
        "classes": classes,
        "methods": methods,
        "fields": fields,
        "imports": imports,
        "statistics": {
            "method_count": len(methods),
            "field_count": len(fields),
        },
    }


# ========================================
# Property Tests for Serialization Round-Trip
# ========================================


class TestSerializationRoundTripProperties:
    """
    Property-based tests for serialization round-trip consistency.

    **Feature: test-coverage-improvement, Property 1: Serialization Round-Trip Consistency**
    **Validates: Requirements 2.4, 6.4, 10.3**
    """

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(result=analysis_result())
    def test_property_1_analysis_result_to_dict_roundtrip(self, result: AnalysisResult):
        """
        **Feature: test-coverage-improvement, Property 1: Serialization Round-Trip Consistency**

        For any valid AnalysisResult object, serializing to dict and then to JSON
        and back SHALL produce equivalent data.

        **Validates: Requirements 2.4, 6.4, 10.3**
        """
        # Serialize to dict
        serialized = result.to_dict()

        # Property: Serialized result should be a dictionary
        assert isinstance(serialized, dict), "to_dict() should return a dictionary"

        # Property: Serialized result should be JSON-serializable
        json_str = json.dumps(serialized)
        assert isinstance(json_str, str), "Serialized dict should be JSON-serializable"

        # Property: JSON deserialization should produce equivalent dict
        deserialized = json.loads(json_str)
        assert deserialized == serialized, "JSON round-trip should preserve data"

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(result=analysis_result())
    def test_property_1_analysis_result_to_json_roundtrip(self, result: AnalysisResult):
        """
        **Feature: test-coverage-improvement, Property 1: Serialization Round-Trip Consistency**

        For any valid AnalysisResult object, the to_json() method SHALL produce
        JSON-serializable output that round-trips correctly.

        **Validates: Requirements 2.4, 6.4, 10.3**
        """
        # Serialize using to_json (alias for to_dict)
        serialized = result.to_json()

        # Property: Should be JSON-serializable
        json_str = json.dumps(serialized)
        deserialized = json.loads(json_str)

        # Property: Round-trip should preserve all keys
        assert set(serialized.keys()) == set(
            deserialized.keys()
        ), "All keys should be preserved in round-trip"

        # Property: Round-trip should preserve file_path
        assert (
            serialized["file_path"] == deserialized["file_path"]
        ), "file_path should be preserved"

        # Property: Round-trip should preserve success status
        assert (
            serialized["success"] == deserialized["success"]
        ), "success status should be preserved"

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(result=analysis_result())
    def test_property_1_analysis_result_to_mcp_format_roundtrip(
        self, result: AnalysisResult
    ):
        """
        **Feature: test-coverage-improvement, Property 1: Serialization Round-Trip Consistency**

        For any valid AnalysisResult object, the to_mcp_format() method SHALL produce
        JSON-serializable output that round-trips correctly.

        **Validates: Requirements 2.4, 6.4, 10.3**
        """
        # Serialize to MCP format
        mcp_format = result.to_mcp_format()

        # Property: MCP format should be a dictionary
        assert isinstance(
            mcp_format, dict
        ), "to_mcp_format() should return a dictionary"

        # Property: MCP format should be JSON-serializable
        json_str = json.dumps(mcp_format)
        deserialized = json.loads(json_str)

        # Property: Round-trip should preserve structure
        assert "file_path" in deserialized, "file_path should be in MCP format"
        assert "structure" in deserialized, "structure should be in MCP format"
        assert "metadata" in deserialized, "metadata should be in MCP format"

        # Property: Round-trip should preserve file_path
        assert (
            mcp_format["file_path"] == deserialized["file_path"]
        ), "file_path should be preserved in MCP format round-trip"

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(result=analysis_result())
    def test_property_1_analysis_result_summary_dict_roundtrip(
        self, result: AnalysisResult
    ):
        """
        **Feature: test-coverage-improvement, Property 1: Serialization Round-Trip Consistency**

        For any valid AnalysisResult object, the to_summary_dict() method SHALL produce
        JSON-serializable output that round-trips correctly.

        **Validates: Requirements 2.4, 6.4, 10.3**
        """
        # Serialize to summary dict
        summary = result.to_summary_dict()

        # Property: Summary should be a dictionary
        assert isinstance(summary, dict), "to_summary_dict() should return a dictionary"

        # Property: Summary should be JSON-serializable
        json_str = json.dumps(summary)
        deserialized = json.loads(json_str)

        # Property: Round-trip should preserve file_path
        assert (
            summary["file_path"] == deserialized["file_path"]
        ), "file_path should be preserved in summary round-trip"

        # Property: Round-trip should preserve summary_elements list
        assert len(summary["summary_elements"]) == len(
            deserialized["summary_elements"]
        ), "summary_elements count should be preserved"

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(data=java_formatter_data())
    def test_property_1_java_formatter_json_roundtrip(self, data: dict):
        """
        **Feature: test-coverage-improvement, Property 1: Serialization Round-Trip Consistency**

        For any valid Java formatter data, serializing to JSON format and deserializing
        SHALL produce equivalent data.

        **Validates: Requirements 2.4, 6.4, 10.3**
        """
        formatter = JavaTableFormatter()

        # Serialize to JSON using formatter
        json_output = formatter._format_json(data)

        # Property: JSON output should be valid JSON
        deserialized = json.loads(json_output)

        # Property: Round-trip should preserve package name
        if data.get("package", {}).get("name"):
            assert (
                deserialized.get("package", {}).get("name") == data["package"]["name"]
            ), "Package name should be preserved in JSON round-trip"

        # Property: Round-trip should preserve class count
        assert len(deserialized.get("classes", [])) == len(
            data.get("classes", [])
        ), "Class count should be preserved in JSON round-trip"

        # Property: Round-trip should preserve method count
        assert len(deserialized.get("methods", [])) == len(
            data.get("methods", [])
        ), "Method count should be preserved in JSON round-trip"

        # Property: Round-trip should preserve field count
        assert len(deserialized.get("fields", [])) == len(
            data.get("fields", [])
        ), "Field count should be preserved in JSON round-trip"

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(data=java_formatter_data())
    def test_property_1_java_formatter_json_preserves_all_class_names(self, data: dict):
        """
        **Feature: test-coverage-improvement, Property 1: Serialization Round-Trip Consistency**

        For any valid Java formatter data, JSON serialization SHALL preserve all class names.

        **Validates: Requirements 2.4, 6.4, 10.3**
        """
        formatter = JavaTableFormatter()

        # Serialize to JSON
        json_output = formatter._format_json(data)
        deserialized = json.loads(json_output)

        # Property: All class names should be preserved
        original_class_names = {c["name"] for c in data.get("classes", [])}
        deserialized_class_names = {c["name"] for c in deserialized.get("classes", [])}

        assert (
            original_class_names == deserialized_class_names
        ), f"All class names should be preserved. Original: {original_class_names}, Got: {deserialized_class_names}"

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(data=java_formatter_data())
    def test_property_1_java_formatter_json_preserves_all_method_names(
        self, data: dict
    ):
        """
        **Feature: test-coverage-improvement, Property 1: Serialization Round-Trip Consistency**

        For any valid Java formatter data, JSON serialization SHALL preserve all method names.

        **Validates: Requirements 2.4, 6.4, 10.3**
        """
        formatter = JavaTableFormatter()

        # Serialize to JSON
        json_output = formatter._format_json(data)
        deserialized = json.loads(json_output)

        # Property: All method names should be preserved
        original_method_names = {m["name"] for m in data.get("methods", [])}
        deserialized_method_names = {m["name"] for m in deserialized.get("methods", [])}

        assert (
            original_method_names == deserialized_method_names
        ), f"All method names should be preserved. Original: {original_method_names}, Got: {deserialized_method_names}"

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(data=java_formatter_data())
    def test_property_1_java_formatter_json_preserves_all_field_names(self, data: dict):
        """
        **Feature: test-coverage-improvement, Property 1: Serialization Round-Trip Consistency**

        For any valid Java formatter data, JSON serialization SHALL preserve all field names.

        **Validates: Requirements 2.4, 6.4, 10.3**
        """
        formatter = JavaTableFormatter()

        # Serialize to JSON
        json_output = formatter._format_json(data)
        deserialized = json.loads(json_output)

        # Property: All field names should be preserved
        original_field_names = {f["name"] for f in data.get("fields", [])}
        deserialized_field_names = {f["name"] for f in deserialized.get("fields", [])}

        assert (
            original_field_names == deserialized_field_names
        ), f"All field names should be preserved. Original: {original_field_names}, Got: {deserialized_field_names}"


class TestSerializationDataIntegrityProperties:
    """
    Property-based tests for data integrity during serialization.

    **Feature: test-coverage-improvement, Property 1: Serialization Round-Trip Consistency**
    **Validates: Requirements 2.4, 6.4, 10.3**
    """

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(result=analysis_result())
    def test_property_1_serialization_preserves_element_counts(
        self, result: AnalysisResult
    ):
        """
        **Feature: test-coverage-improvement, Property 1: Serialization Round-Trip Consistency**

        For any valid AnalysisResult, serialization SHALL preserve the count of each element type.

        **Validates: Requirements 2.4, 6.4, 10.3**
        """
        # Get summary before serialization
        summary_before = result.get_summary()

        # Serialize and deserialize
        serialized = result.to_dict()
        json_str = json.dumps(serialized)
        deserialized = json.loads(json_str)

        # Property: Class count should be preserved
        assert (
            len(deserialized.get("classes", [])) == summary_before["class_count"]
        ), "Class count should be preserved after serialization"

        # Property: Method count should be preserved
        assert (
            len(deserialized.get("methods", [])) == summary_before["method_count"]
        ), "Method count should be preserved after serialization"

        # Property: Field count should be preserved
        assert (
            len(deserialized.get("fields", [])) == summary_before["field_count"]
        ), "Field count should be preserved after serialization"

        # Property: Import count should be preserved
        assert (
            len(deserialized.get("imports", [])) == summary_before["import_count"]
        ), "Import count should be preserved after serialization"

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(result=analysis_result())
    def test_property_1_serialization_preserves_metadata(self, result: AnalysisResult):
        """
        **Feature: test-coverage-improvement, Property 1: Serialization Round-Trip Consistency**

        For any valid AnalysisResult, serialization SHALL preserve all metadata fields.

        **Validates: Requirements 2.4, 6.4, 10.3**
        """
        # Serialize
        serialized = result.to_dict()
        json_str = json.dumps(serialized)
        deserialized = json.loads(json_str)

        # Property: file_path should be preserved
        assert (
            deserialized["file_path"] == result.file_path
        ), "file_path should be preserved"

        # Property: success should be preserved
        assert deserialized["success"] == result.success, "success should be preserved"

        # Property: analysis_time should be preserved (with float tolerance)
        assert (
            abs(deserialized["analysis_time"] - result.analysis_time) < 0.0001
        ), "analysis_time should be preserved"

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(data=java_formatter_data())
    def test_property_1_format_table_json_is_valid(self, data: dict):
        """
        **Feature: test-coverage-improvement, Property 1: Serialization Round-Trip Consistency**

        For any valid formatter data, format_table with json type SHALL produce valid JSON.

        **Validates: Requirements 2.4, 6.4, 10.3**
        """
        formatter = JavaTableFormatter()

        # Use format_table with json type
        json_output = formatter.format_table(data, table_type="json")

        # Property: Output should be valid JSON
        try:
            parsed = json.loads(json_output)
            assert parsed is not None, "JSON output should parse to non-None value"
        except json.JSONDecodeError as e:
            pytest.fail(f"format_table(json) should produce valid JSON: {e}")

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(data=java_formatter_data())
    def test_property_1_format_advanced_json_is_valid(self, data: dict):
        """
        **Feature: test-coverage-improvement, Property 1: Serialization Round-Trip Consistency**

        For any valid formatter data, format_advanced with json format SHALL produce valid JSON.

        **Validates: Requirements 2.4, 6.4, 10.3**
        """
        formatter = JavaTableFormatter()

        # Use format_advanced with json format
        json_output = formatter.format_advanced(data, output_format="json")

        # Property: Output should be valid JSON
        try:
            parsed = json.loads(json_output)
            assert parsed is not None, "JSON output should parse to non-None value"
        except json.JSONDecodeError as e:
            pytest.fail(f"format_advanced(json) should produce valid JSON: {e}")
