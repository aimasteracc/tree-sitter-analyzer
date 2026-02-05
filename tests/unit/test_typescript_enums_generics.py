"""
Unit tests for TypeScript enum declarations and generic types.

Following TDD methodology:
1. RED: Write failing tests first
2. GREEN: Implement minimal code to pass
3. REFACTOR: Improve code quality

Phase 1: Enum Declarations + Generic Types (7 tests)
"""


class TestEnumDeclarations:
    """Tests for TypeScript enum extraction."""

    def test_enum_declaration_basic(self):
        """Test basic enum extraction without values."""
        from tree_sitter_analyzer_v2.languages import TypeScriptParser

        code = """
enum Color {
    Red,
    Green,
    Blue
}
"""
        parser = TypeScriptParser()
        result = parser.parse(code, "test.ts")

        assert "enums" in result
        assert len(result["enums"]) == 1

        enum = result["enums"][0]
        assert enum["name"] == "Color"
        assert len(enum["members"]) == 3
        assert enum["members"][0]["name"] == "Red"
        assert enum["members"][1]["name"] == "Green"
        assert enum["members"][2]["name"] == "Blue"
        assert enum["is_const"] is False

    def test_enum_with_values(self):
        """Test enum with explicit values."""
        from tree_sitter_analyzer_v2.languages import TypeScriptParser

        code = """
enum Status {
    Active = "ACTIVE",
    Inactive = "INACTIVE",
    Pending = "PENDING"
}
"""
        parser = TypeScriptParser()
        result = parser.parse(code, "test.ts")

        assert len(result["enums"]) == 1

        enum = result["enums"][0]
        assert enum["name"] == "Status"
        assert len(enum["members"]) == 3
        assert enum["members"][0]["name"] == "Active"
        assert enum["members"][0]["value"] == '"ACTIVE"'
        assert enum["members"][1]["name"] == "Inactive"
        assert enum["members"][1]["value"] == '"INACTIVE"'

    def test_const_enum(self):
        """Test const enum extraction."""
        from tree_sitter_analyzer_v2.languages import TypeScriptParser

        code = """
const enum Direction {
    Up = 1,
    Down = 2,
    Left = 3,
    Right = 4
}
"""
        parser = TypeScriptParser()
        result = parser.parse(code, "test.ts")

        assert len(result["enums"]) == 1

        enum = result["enums"][0]
        assert enum["name"] == "Direction"
        assert enum["is_const"] is True
        assert len(enum["members"]) == 4


class TestGenericTypes:
    """Tests for TypeScript generic type extraction."""

    def test_function_with_generics(self):
        """Test function with generic type parameters."""
        from tree_sitter_analyzer_v2.languages import TypeScriptParser

        code = """
function identity<T>(arg: T): T {
    return arg;
}

function pair<T, K>(first: T, second: K): [T, K] {
    return [first, second];
}
"""
        parser = TypeScriptParser()
        result = parser.parse(code, "test.ts")

        assert len(result["functions"]) == 2

        # Test identity<T>
        func1 = result["functions"][0]
        assert func1["name"] == "identity"
        assert "generics" in func1
        assert func1["generics"] == ["T"]
        assert func1["return_type"] == "T"

        # Test pair<T, K>
        func2 = result["functions"][1]
        assert func2["name"] == "pair"
        assert func2["generics"] == ["T", "K"]
        assert "[T, K]" in func2["return_type"]

    def test_interface_with_generics(self):
        """Test interface with generic type parameters."""
        from tree_sitter_analyzer_v2.languages import TypeScriptParser

        code = """
interface Box<T> {
    value: T;
}

interface Pair<K, V> {
    key: K;
    value: V;
}
"""
        parser = TypeScriptParser()
        result = parser.parse(code, "test.ts")

        assert len(result["interfaces"]) == 2

        # Test Box<T>
        interface1 = result["interfaces"][0]
        assert interface1["name"] == "Box"
        assert "generics" in interface1
        assert interface1["generics"] == ["T"]

        # Test Pair<K, V>
        interface2 = result["interfaces"][1]
        assert interface2["name"] == "Pair"
        assert interface2["generics"] == ["K", "V"]

    def test_class_with_generics(self):
        """Test class with generic type parameters."""
        from tree_sitter_analyzer_v2.languages import TypeScriptParser

        code = """
class Container<T, K> {
    constructor(public value: T, public key: K) {}

    getValue(): T {
        return this.value;
    }
}
"""
        parser = TypeScriptParser()
        result = parser.parse(code, "test.ts")

        assert len(result["classes"]) == 1

        cls = result["classes"][0]
        assert cls["name"] == "Container"
        assert "generics" in cls
        assert cls["generics"] == ["T", "K"]

    def test_type_alias_with_generics(self):
        """Test type alias with generic parameters."""
        from tree_sitter_analyzer_v2.languages import TypeScriptParser

        code = """
type Response<T> = {
    data: T;
    error: string | null;
};

type Result<T, E> =
    | { success: true; value: T }
    | { success: false; error: E };
"""
        parser = TypeScriptParser()
        result = parser.parse(code, "test.ts")

        assert len(result["types"]) == 2

        # Test Response<T>
        type1 = result["types"][0]
        assert type1["name"] == "Response"
        assert "generics" in type1
        assert type1["generics"] == ["T"]

        # Test Result<T, E>
        type2 = result["types"][1]
        assert type2["name"] == "Result"
        assert type2["generics"] == ["T", "E"]
