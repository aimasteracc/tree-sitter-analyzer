#!/usr/bin/env python3
"""
Integration tests for Java plugin annotation extraction.

These tests use real tree-sitter parsing and real tempfiles.
They verify that annotations are correctly associated with classes and methods
after the full analysis pipeline runs.

Spec: openspec/changes/fix-java-plugin-annotation-extraction/specs/java-annotation-extraction/spec.md
"""

import os
import tempfile

import pytest

from tree_sitter_analyzer.languages.java_plugin import JavaPlugin
from tree_sitter_analyzer.models import Class, Function


def _make_request(file_path: str):
    """Create a minimal AnalysisRequest mock."""
    from unittest.mock import Mock

    req = Mock()
    req.file_path = file_path
    req.language = "java"
    req.include_complexity = False
    req.include_details = False
    return req


class TestClassAnnotationExtraction:
    """JAA-001: Class annotations are populated after extraction."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_class_single_annotation_populated(self):
        """@RestController annotation must appear in class.annotations."""
        java_code = """\
@RestController
public class UserController {
    public void index() {}
}
"""
        plugin = JavaPlugin()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".java", delete=False, encoding="utf-8"
        ) as f:
            f.write(java_code)
            temp_path = f.name

        try:
            result = await plugin.analyze_file(temp_path, _make_request(temp_path))

            assert result is not None
            assert result.success, f"Analysis failed: {result.error_message}"

            classes = [e for e in result.elements if isinstance(e, Class)]
            assert classes, "No Class elements found in result"

            user_controller = next(
                (c for c in classes if c.name == "UserController"), None
            )
            assert user_controller is not None, "UserController class not found"

            # JAA-001: annotations must be non-empty
            assert user_controller.annotations, (
                "UserController.annotations is empty — "
                "annotation extraction ordering bug not fixed"
            )
            annotation_names = [a.get("name") for a in user_controller.annotations]
            assert (
                "RestController" in annotation_names
            ), f"Expected 'RestController' in annotations, got: {annotation_names}"
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_class_multiple_annotations_populated(self):
        """Class with two annotations must have both in annotations list."""
        java_code = """\
@RestController
@RequestMapping("/api/users")
public class UserController {
    public void index() {}
}
"""
        plugin = JavaPlugin()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".java", delete=False, encoding="utf-8"
        ) as f:
            f.write(java_code)
            temp_path = f.name

        try:
            result = await plugin.analyze_file(temp_path, _make_request(temp_path))
            assert result.success

            classes = [e for e in result.elements if isinstance(e, Class)]
            user_controller = next(
                (c for c in classes if c.name == "UserController"), None
            )
            assert user_controller is not None

            assert len(user_controller.annotations) >= 2, (
                f"Expected >= 2 annotations, got {len(user_controller.annotations)}: "
                f"{user_controller.annotations}"
            )
        finally:
            os.unlink(temp_path)


class TestMethodAnnotationExtraction:
    """JAA-002: Method annotations are populated after extraction."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_method_marker_annotation_populated(self):
        """@Override marker annotation must appear in method.annotations."""
        java_code = """\
public class MyService {
    @Override
    public String toString() {
        return "MyService";
    }
}
"""
        plugin = JavaPlugin()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".java", delete=False, encoding="utf-8"
        ) as f:
            f.write(java_code)
            temp_path = f.name

        try:
            result = await plugin.analyze_file(temp_path, _make_request(temp_path))
            assert result.success

            functions = [e for e in result.elements if isinstance(e, Function)]
            to_string = next((f for f in functions if f.name == "toString"), None)
            assert to_string is not None, "toString method not found"

            # JAA-002: method annotations must be non-empty
            assert to_string.annotations, (
                "toString.annotations is empty — "
                "annotation extraction ordering bug not fixed"
            )
            annotation_names = [a.get("name") for a in to_string.annotations]
            assert (
                "Override" in annotation_names
            ), f"Expected 'Override' in annotations, got: {annotation_names}"
        finally:
            os.unlink(temp_path)


class TestSpringAnnotationsEndToEnd:
    """JAA-003: Spring Framework annotations are correctly scoped to class/method."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_spring_controller_class_and_method_annotations(self):
        """@RestController goes to class, @GetMapping goes to method — no mixing."""
        java_code = """\
@RestController
@RequestMapping("/api")
public class ApiController {

    @GetMapping("/users")
    public String getUsers() {
        return "users";
    }

    public String noAnnotation() {
        return "none";
    }
}
"""
        plugin = JavaPlugin()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".java", delete=False, encoding="utf-8"
        ) as f:
            f.write(java_code)
            temp_path = f.name

        try:
            result = await plugin.analyze_file(temp_path, _make_request(temp_path))
            assert result.success

            classes = [e for e in result.elements if isinstance(e, Class)]
            functions = [e for e in result.elements if isinstance(e, Function)]

            api_controller = next(
                (c for c in classes if c.name == "ApiController"), None
            )
            assert api_controller is not None, "ApiController class not found"

            get_users = next((f for f in functions if f.name == "getUsers"), None)
            assert get_users is not None, "getUsers method not found"

            no_annotation = next(
                (f for f in functions if f.name == "noAnnotation"), None
            )
            assert no_annotation is not None, "noAnnotation method not found"

            # Class must have @RestController and @RequestMapping
            class_annotation_names = [a.get("name") for a in api_controller.annotations]
            assert (
                "RestController" in class_annotation_names
            ), f"Class missing @RestController: {class_annotation_names}"

            # getUsers must have @GetMapping
            method_annotation_names = [a.get("name") for a in get_users.annotations]
            assert (
                "GetMapping" in method_annotation_names
            ), f"getUsers missing @GetMapping: {method_annotation_names}"

            # noAnnotation must have empty annotations
            assert no_annotation.annotations == [], (
                f"noAnnotation should have no annotations, "
                f"got: {no_annotation.annotations}"
            )

            # Class and method annotations must not overlap
            class_names_set = set(class_annotation_names)
            method_names_set = set(method_annotation_names)
            assert (
                "GetMapping" not in class_names_set
            ), "@GetMapping must not appear in class annotations"
            assert (
                "RestController" not in method_names_set
            ), "@RestController must not appear in method annotations"
        finally:
            os.unlink(temp_path)
