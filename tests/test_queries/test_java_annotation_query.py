#!/usr/bin/env python3
"""
Tests for Java annotation method query fix

This test file validates the fix for the `method_with_annotations` query
which previously failed to match methods with annotations due to incorrect
query pattern syntax.

Issue: The query pattern `(modifiers (annotation) @annotation)*` looked for
multiple modifiers nodes instead of multiple annotations within a single
modifiers node.

Fix: Changed to `(modifiers [(annotation) (marker_annotation)]+ @annotation)`
to correctly match one or more annotations of either type within the modifiers.
"""

import os
import tempfile

import pytest

from tree_sitter_analyzer import api


def _write_temp_java_file(code: str) -> str:
    """Helper to write Java code to a temp file and return the path"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
        f.write(code)
        return f.name


def _cleanup_temp_file(file_path: str) -> None:
    """Helper to clean up temp file"""
    try:
        if os.path.exists(file_path):
            os.unlink(file_path)
    except Exception:
        pass  # Best effort cleanup


class TestJavaAnnotationMethodQuery:
    """Test cases for the method_with_annotations query"""

    def test_single_marker_annotation(self) -> None:
        """Test that query matches method with single marker annotation (@Override)"""
        java_code = """
public class TestClass {
    @Override
    public String toString() {
        return "test";
    }
}
"""
        test_file = _write_temp_java_file(java_code)

        try:
            result = api.execute_query(
                test_file, "method_with_annotations", language="java"
            )

            assert result["success"], f"Query failed: {result.get('error')}"

            method_with_annotations = result.get("results", [])
            assert (
                len(method_with_annotations) == 1
            ), f"Expected 1 method with annotation, found {len(method_with_annotations)}"

            captures = method_with_annotations[0].get("captures", {})
            assert "name" in captures, "Method name not captured"
            assert (
                captures["name"]["text"] == "toString"
            ), f"Expected method name 'toString', got '{captures['name']['text']}'"

            assert "annotation" in captures, "Annotation not captured"
        finally:
            _cleanup_temp_file(test_file)

    def test_annotation_with_parameters(self) -> None:
        """Test that query matches method with annotation that has parameters"""
        java_code = """
public class TestClass {
    @SuppressWarnings("unchecked")
    public List getRawList() {
        return new ArrayList();
    }
}
"""
        test_file = _write_temp_java_file(java_code)

        try:
            result = api.execute_query(
                test_file, "method_with_annotations", language="java"
            )

            assert result["success"], f"Query failed: {result.get('error')}"

            method_with_annotations = result.get("results", [])
            assert len(method_with_annotations) == 1

            captures = method_with_annotations[0].get("captures", {})
            assert captures["name"]["text"] == "getRawList"

            # Check annotation with parameters
            assert "annotation" in captures
        finally:
            _cleanup_temp_file(test_file)

    def test_multiple_annotations(self) -> None:
        """Test that query matches method with multiple annotations"""
        java_code = """
public class TestClass {
    @SuppressWarnings("unchecked")
    @Deprecated
    public void oldMethod() {
        // deprecated code
    }
}
"""
        test_file = _write_temp_java_file(java_code)

        try:
            result = api.execute_query(
                test_file, "method_with_annotations", language="java"
            )

            assert result["success"], f"Query failed: {result.get('error')}"

            method_with_annotations = result.get("results", [])
            assert len(method_with_annotations) == 1

            captures = method_with_annotations[0].get("captures", {})
            assert captures["name"]["text"] == "oldMethod"
            assert "annotation" in captures
        finally:
            _cleanup_temp_file(test_file)

    def test_mixed_methods_only_annotated_matched(self) -> None:
        """Test that query only matches annotated methods, not regular methods"""
        java_code = """
public class TestClass {
    @Override
    public String toString() {
        return "test";
    }

    public void regularMethod() {
        // no annotation
    }

    @Test
    public void testMethod() {
        // test code
    }
}
"""
        test_file = _write_temp_java_file(java_code)

        try:
            result = api.execute_query(
                test_file, "method_with_annotations", language="java"
            )

            assert result["success"], f"Query failed: {result.get('error')}"

            method_with_annotations = result.get("results", [])

            # Should match exactly 2 methods (toString with @Override, testMethod with @Test)
            # Should NOT match regularMethod (no annotation)
            assert (
                len(method_with_annotations) == 2
            ), f"Expected 2 annotated methods, found {len(method_with_annotations)}"

            # Check that the matched methods are the annotated ones
            matched_names = []
            for match in method_with_annotations:
                captures = match.get("captures", {})
                if "name" in captures:
                    matched_names.append(captures["name"]["text"])

            assert "toString" in matched_names
            assert "testMethod" in matched_names
            assert "regularMethod" not in matched_names
        finally:
            _cleanup_temp_file(test_file)

    def test_query_returns_correct_capture_types(self) -> None:
        """Test that query captures have the expected structure"""
        java_code = """
public class TestClass {
    @Override
    public String toString() {
        return "test";
    }
}
"""
        test_file = _write_temp_java_file(java_code)

        try:
            result = api.execute_query(
                test_file, "method_with_annotations", language="java"
            )

            assert result["success"]

            method_with_annotations = result.get("results", [])
            assert len(method_with_annotations) > 0

            # Check structure of first result
            first_result = method_with_annotations[0]

            # Should have standard fields
            assert "text" in first_result
            assert "start_line" in first_result
            assert "end_line" in first_result
            assert "captures" in first_result

            # Captures should include 'name', 'annotation', and 'method'
            captures = first_result["captures"]
            assert "name" in captures, "Missing 'name' capture"
            assert "annotation" in captures, "Missing 'annotation' capture"
            assert "method" in captures, "Missing 'method' capture"
        finally:
            _cleanup_temp_file(test_file)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
