#!/usr/bin/env python3
"""Test Java method-only annotation filtering - Bug 2 from fix-java-implements-generics-and-annotation-attribution

Bug 2: @Override and other method-only annotations attributed to classes
  - @Override, @Test, @Before, etc. should never appear in class/field annotations
  - These are method-only annotations

TDD Order: Write FAILING tests first, then implement fixes
"""

from __future__ import annotations

import tree_sitter
import tree_sitter_java as ts_java

from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor


class TestMethodOnlyAnnotations:
    """@Override and other method-only annotations must never appear on classes/fields."""

    METHOD_ONLY_ANNOTATIONS = {
        "Override", "Test", "Before", "After",
        "BeforeEach", "AfterEach", "BeforeAll", "AfterAll",
        "ParameterizedTest", "ValueSource",
    }

    def test_override_never_on_class_unit(self):
        """@Override on a method must not bleed into the next class's annotations."""
        src = """\
package test;

class Outer {
    @Override
    public String toString() { return "outer"; }

    @Override
    public int hashCode() { return 0; }
}

// This class should NOT inherit @Override from the method above
class Inner {
    public void run() {}
}
"""
        lang = tree_sitter.Language(ts_java.language())
        parser = tree_sitter.Parser()
        parser.language = lang
        tree = parser.parse(src.encode())

        ext = JavaElementExtractor()
        classes = ext.extract_classes(tree, src)

        assert len(classes) == 2, f"Should extract 2 classes, got {len(classes)}"

        # Check Outer class - should NOT have @Override in class annotations
        outer = next((c for c in classes if c.name == "Outer"), None)
        assert outer is not None, "Should find Outer class"
        outer_annotation_names = {a.get("name", "") for a in outer.annotations}
        assert "Override" not in outer_annotation_names, (
            f"@Override should not be in class annotations for Outer. Got: {outer_annotation_names}"
        )

        # Check Inner class - should NOT have @Override in class annotations
        inner = next((c for c in classes if c.name == "Inner"), None)
        assert inner is not None, "Should find Inner class"
        inner_annotation_names = {a.get("name", "") for a in inner.annotations}
        assert "Override" not in inner_annotation_names, (
            f"@Override should not bleed from preceding method to Inner class annotations. "
            f"Got: {inner_annotation_names}"
        )

    def test_test_annotations_never_on_class(self):
        """JUnit @Test, @Before, @After should never appear on class annotations."""
        src = """\
package test;

class MyTest {
    @Test
    public void testSomething() {}

    @Before
    public void setUp() {}

    @After
    public void tearDown() {}
}

class AnotherClass {
    public void run() {}
}
"""
        lang = tree_sitter.Language(ts_java.language())
        parser = tree_sitter.Parser()
        parser.language = lang
        tree = parser.parse(src.encode())

        ext = JavaElementExtractor()
        classes = ext.extract_classes(tree, src)

        assert len(classes) == 2, f"Should extract 2 classes, got {len(classes)}"

        for cls in classes:
            class_annotation_names = {a.get("name", "") for a in cls.annotations}
            method_only_in_class = class_annotation_names & self.METHOD_ONLY_ANNOTATIONS
            assert not method_only_in_class, (
                f"Class {cls.name} should not have method-only annotations. "
                f"Found: {method_only_in_class} in {class_annotation_names}"
            )

    def test_method_only_annotations_on_fields(self):
        """@Override, @Test should never appear on field annotations."""
        src = """\
package test;

class Data {
    @Override
    public String toString() { return "data"; }

    private String name;
}
"""
        lang = tree_sitter.Language(ts_java.language())
        parser = tree_sitter.Parser()
        parser.language = lang
        tree = parser.parse(src.encode())

        ext = JavaElementExtractor()
        # Need to call extract_classes first to populate annotations
        _ = ext.extract_classes(tree, src)
        variables = ext.extract_variables(tree, src)

        assert variables, "Should extract field 'name'"
        name_field = next((v for v in variables if "name" in v.name.lower()), None)
        assert name_field is not None, "Should find 'name' field"

        field_annotation_names = {a.get("name", "") for a in name_field.annotations}
        method_only_in_field = field_annotation_names & self.METHOD_ONLY_ANNOTATIONS
        assert not method_only_in_field, (
            f"Field 'name' should not have method-only annotations. "
            f"Found: {method_only_in_field} in {field_annotation_names}"
        )

    def test_junit5_annotations_never_on_class(self):
        """JUnit 5 annotations (@Test, @BeforeEach, etc.) should not appear on classes."""
        src = """\
package test;

class JUnit5Test {
    @org.junit.jupiter.api.Test
    void test1() {}

    @org.junit.jupiter.api.BeforeEach
    void setup() {}
}

class PlainClass {
    void run() {}
}
"""
        lang = tree_sitter.Language(ts_java.language())
        parser = tree_sitter.Parser()
        parser.language = lang
        tree = parser.parse(src.encode())

        ext = JavaElementExtractor()
        classes = ext.extract_classes(tree, src)

        for cls in classes:
            class_annotation_names = {a.get("name", "") for a in cls.annotations}
            # Check for both simple names and qualified names
            method_only_in_class = class_annotation_names & self.METHOD_ONLY_ANNOTATIONS
            assert not method_only_in_class, (
                f"Class {cls.name} should not have method-only annotations. "
                f"Found: {method_only_in_class} in {class_annotation_names}"
            )

    def test_class_annotations_preserved(self):
        """Valid class annotations like @Entity, @Controller should be preserved."""
        src = """\
package test;

@Entity
@Table(name = "users")
class UserController {
    @Override
    public String toString() { return "user"; }
}
"""
        lang = tree_sitter.Language(ts_java.language())
        parser = tree_sitter.Parser()
        parser.language = lang
        tree = parser.parse(src.encode())

        ext = JavaElementExtractor()
        classes = ext.extract_classes(tree, src)

        assert classes, "Should extract UserController"
        cls = classes[0]
        class_annotation_names = {a.get("name", "") for a in cls.annotations}

        # Class annotations should be present
        assert "Entity" in class_annotation_names, f"@Entity should be in class annotations, got {class_annotation_names}"
        assert "Table" in class_annotation_names, f"@Table should be in class annotations, got {class_annotation_names}"

        # Method annotations should NOT be in class annotations
        assert "Override" not in class_annotation_names, (
            f"@Override should not be in class annotations, got {class_annotation_names}"
        )
