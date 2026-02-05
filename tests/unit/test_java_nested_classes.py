"""
Unit tests for Java nested class detection.

Following TDD methodology:
1. RED: Write failing tests first
2. GREEN: Implement minimal code to pass
3. REFACTOR: Improve code quality

Phase 4: Nested Class Detection (3 tests)
"""


class TestNestedClasses:
    """Tests for nested and inner class detection."""

    def test_nested_class_detection(self):
        """Test basic nested class detection."""
        from tree_sitter_analyzer_v2.languages import JavaParser

        code = """
public class OuterClass {
    public static class NestedClass {
        public void nestedMethod() {}
    }

    public void outerMethod() {}
}
"""
        parser = JavaParser()
        result = parser.parse(code, "OuterClass.java")

        assert result["errors"] is False
        assert len(result["classes"]) == 2  # Both outer and nested

        # Check outer class
        outer = result["classes"][0]
        assert outer["name"] == "OuterClass"
        assert len(outer["methods"]) == 1
        assert outer["methods"][0]["name"] == "outerMethod"

        # Check metadata for outer class
        assert "metadata" in outer
        assert outer["metadata"].get("is_nested", False) is False

        # Check nested class
        nested = result["classes"][1]
        assert nested["name"] == "NestedClass"
        assert len(nested["methods"]) == 1
        assert nested["methods"][0]["name"] == "nestedMethod"

        # Check metadata for nested class
        assert "metadata" in nested
        assert nested["metadata"]["is_nested"] is True
        assert nested["metadata"]["parent_class"] == "OuterClass"

    def test_inner_class_detection(self):
        """Test non-static inner class detection."""
        from tree_sitter_analyzer_v2.languages import JavaParser

        code = """
public class Container {
    private class InnerClass {
        private int value;

        public void setValue(int v) {
            value = v;
        }
    }

    public void containerMethod() {}
}
"""
        parser = JavaParser()
        result = parser.parse(code, "Container.java")

        assert len(result["classes"]) == 2

        # Check inner class
        inner = result["classes"][1]
        assert inner["name"] == "InnerClass"
        assert inner["metadata"]["is_nested"] is True
        assert inner["metadata"]["parent_class"] == "Container"

    def test_multiple_nested_classes(self):
        """Test multiple nested classes in the same outer class."""
        from tree_sitter_analyzer_v2.languages import JavaParser

        code = """
public class Outer {
    public static class Nested1 {
        public void method1() {}
    }

    public static class Nested2 {
        public void method2() {}
    }

    private class Inner1 {
        public void method3() {}
    }
}
"""
        parser = JavaParser()
        result = parser.parse(code, "Outer.java")

        assert len(result["classes"]) == 4  # 1 outer + 3 nested

        # Check outer
        outer = result["classes"][0]
        assert outer["name"] == "Outer"
        assert outer["metadata"].get("is_nested", False) is False

        # Check all nested classes have correct metadata
        nested_classes = result["classes"][1:]
        for nested_class in nested_classes:
            assert nested_class["metadata"]["is_nested"] is True
            assert nested_class["metadata"]["parent_class"] == "Outer"

        # Check individual nested class names
        nested_names = {cls["name"] for cls in nested_classes}
        assert nested_names == {"Nested1", "Nested2", "Inner1"}
