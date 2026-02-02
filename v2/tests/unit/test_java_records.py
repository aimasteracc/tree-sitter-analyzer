"""
Unit tests for Java record support (Java 14+).

Following TDD methodology:
1. RED: Write failing tests first
2. GREEN: Implement minimal code to pass
3. REFACTOR: Improve code quality

Phase 3: Record Support (3 tests)
"""


class TestJavaRecords:
    """Tests for Java record declaration support."""

    def test_simple_record(self):
        """Test simple record with two components."""
        from tree_sitter_analyzer_v2.languages import JavaParser

        code = """
public record Point(int x, int y) {
}
"""
        parser = JavaParser()
        result = parser.parse(code, "Point.java")

        assert result["errors"] is False
        assert len(result["classes"]) == 1

        record = result["classes"][0]
        assert record["name"] == "Point"

        # Check record metadata
        assert "metadata" in record
        assert record["metadata"]["is_record"] is True

        # Check record components
        assert "record_components" in record["metadata"]
        components = record["metadata"]["record_components"]
        assert len(components) == 2

        assert components[0]["name"] == "x"
        assert components[0]["type"] == "int"

        assert components[1]["name"] == "y"
        assert components[1]["type"] == "int"

    def test_record_with_multiple_components(self):
        """Test record with multiple components of different types."""
        from tree_sitter_analyzer_v2.languages import JavaParser

        code = """
public record User(
    String name,
    int age,
    boolean active
) {
}
"""
        parser = JavaParser()
        result = parser.parse(code, "User.java")

        record = result["classes"][0]
        assert record["name"] == "User"
        assert record["metadata"]["is_record"] is True

        components = record["metadata"]["record_components"]
        assert len(components) == 3

        assert components[0]["name"] == "name"
        assert components[0]["type"] == "String"

        assert components[1]["name"] == "age"
        assert components[1]["type"] == "int"

        assert components[2]["name"] == "active"
        assert components[2]["type"] == "boolean"

    def test_record_with_generic_components(self):
        """Test record with generic type components."""
        from tree_sitter_analyzer_v2.languages import JavaParser

        code = """
public record Container<T>(
    T value,
    List<String> metadata
) {
}
"""
        parser = JavaParser()
        result = parser.parse(code, "Container.java")

        record = result["classes"][0]
        assert record["name"] == "Container"
        assert record["metadata"]["is_record"] is True

        components = record["metadata"]["record_components"]
        assert len(components) == 2

        # Generic type parameter
        assert components[0]["name"] == "value"
        assert components[0]["type"] == "T"

        # Generic component type
        assert components[1]["name"] == "metadata"
        assert components[1]["type"] == "List<String>"

    def test_record_methods(self):
        """Test record with custom methods."""
        from tree_sitter_analyzer_v2.languages import JavaParser

        code = """
public record Point(int x, int y) {
    public double distance() {
        return Math.sqrt(x * x + y * y);
    }

    public Point translate(int dx, int dy) {
        return new Point(x + dx, y + dy);
    }
}
"""
        parser = JavaParser()
        result = parser.parse(code, "Point.java")

        record = result["classes"][0]
        assert record["name"] == "Point"
        assert record["metadata"]["is_record"] is True

        # Check record components
        components = record["metadata"]["record_components"]
        assert len(components) == 2

        # Check methods
        assert len(record["methods"]) == 2
        assert record["methods"][0]["name"] == "distance"
        assert record["methods"][0]["return_type"] == "double"

        assert record["methods"][1]["name"] == "translate"
        assert record["methods"][1]["return_type"] == "Point"
