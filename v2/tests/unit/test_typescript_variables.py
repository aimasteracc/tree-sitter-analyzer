"""
Unit tests for TypeScript variable extraction.

Following TDD methodology:
1. RED: Write failing tests first
2. GREEN: Implement minimal code to pass
3. REFACTOR: Improve code quality

Phase 3: Variables (4 tests)
"""


class TestVariables:
    """Tests for TypeScript variable extraction."""

    def test_variable_let_const_var(self):
        """Test let, const, and var declarations."""
        from tree_sitter_analyzer_v2.languages import TypeScriptParser

        code = """
let counter = 0;
const MAX_SIZE = 100;
var legacy: string;
"""
        parser = TypeScriptParser()
        result = parser.parse(code, "test.ts")

        assert "variables" in result
        assert len(result["variables"]) == 3

        # let counter
        var1 = result["variables"][0]
        assert var1["name"] == "counter"
        assert var1["kind"] == "let"

        # const MAX_SIZE
        var2 = result["variables"][1]
        assert var2["name"] == "MAX_SIZE"
        assert var2["kind"] == "const"

        # var legacy
        var3 = result["variables"][2]
        assert var3["name"] == "legacy"
        assert var3["kind"] == "var"
        assert var3["type"] == "string"

    def test_variable_with_type_annotation(self):
        """Test variables with type annotations."""
        from tree_sitter_analyzer_v2.languages import TypeScriptParser

        code = """
let value: string | number;
const items: Array<string> = [];
let callback: (x: number) => void;
"""
        parser = TypeScriptParser()
        result = parser.parse(code, "test.ts")

        assert len(result["variables"]) == 3

        # Union type
        var1 = result["variables"][0]
        assert var1["name"] == "value"
        assert "string | number" in var1["type"]

        # Generic type
        var2 = result["variables"][1]
        assert var2["name"] == "items"
        assert "Array<string>" in var2["type"]

        # Function type
        var3 = result["variables"][2]
        assert var3["name"] == "callback"
        assert var3["type"] is not None

    def test_destructuring_assignment(self):
        """Test destructuring assignments."""
        from tree_sitter_analyzer_v2.languages import TypeScriptParser

        code = """
const {name, age} = person;
const [first, ...rest] = array;
const {x, y}: Point = getPoint();
"""
        parser = TypeScriptParser()
        result = parser.parse(code, "test.ts")

        # Destructuring creates multiple variables
        assert len(result["variables"]) >= 3

        # Should extract at least the destructured names
        var_names = [v["name"] for v in result["variables"]]
        assert "name" in var_names
        assert "age" in var_names

    def test_metadata_counts(self):
        """Test variable metadata counts."""
        from tree_sitter_analyzer_v2.languages import TypeScriptParser

        code = """
let x = 1;
const y = 2;
var z = 3;
"""
        parser = TypeScriptParser()
        result = parser.parse(code, "test.ts")

        assert "metadata" in result
        assert "total_variables" in result["metadata"]
        assert result["metadata"]["total_variables"] == 3
