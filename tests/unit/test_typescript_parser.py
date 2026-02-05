"""
Test TypeScript language parser implementation.

Following TDD: Write tests FIRST to define the contract.
This is T1.5: First Three Languages - TypeScript
"""


class TestTypeScriptParserBasics:
    """Test basic TypeScript parser functionality."""

    def test_parser_can_be_imported(self):
        """Test that TypeScriptParser can be imported."""
        from tree_sitter_analyzer_v2.languages.typescript_parser import TypeScriptParser

        assert TypeScriptParser is not None

    def test_parser_initialization(self):
        """Test creating a parser instance."""
        from tree_sitter_analyzer_v2.languages.typescript_parser import TypeScriptParser

        parser = TypeScriptParser()
        assert parser is not None

    def test_parse_simple_code(self):
        """Test parsing simple TypeScript code."""
        from tree_sitter_analyzer_v2.languages.typescript_parser import TypeScriptParser

        parser = TypeScriptParser()
        code = "const x = 1;"

        result = parser.parse(code)

        assert result is not None
        assert "ast" in result
        assert "metadata" in result


class TestTypeScriptFunctionExtraction:
    """Test extracting functions from TypeScript code."""

    def test_extract_simple_function(self):
        """Test extracting a simple function."""
        from tree_sitter_analyzer_v2.languages.typescript_parser import TypeScriptParser

        parser = TypeScriptParser()
        code = """
function hello() {
    console.log("Hello");
}
"""

        result = parser.parse(code)

        assert "functions" in result
        assert len(result["functions"]) == 1

        func = result["functions"][0]
        assert func["name"] == "hello"
        assert func["parameters"] == []

    def test_extract_arrow_function(self):
        """Test extracting arrow function."""
        from tree_sitter_analyzer_v2.languages.typescript_parser import TypeScriptParser

        parser = TypeScriptParser()
        code = """
const greet = (name: string): string => {
    return `Hello, ${name}`;
};
"""

        result = parser.parse(code)

        # Arrow functions assigned to const should be detected
        assert len(result["functions"]) >= 1

    def test_extract_function_with_type_params(self):
        """Test extracting function with typed parameters."""
        from tree_sitter_analyzer_v2.languages.typescript_parser import TypeScriptParser

        parser = TypeScriptParser()
        code = """
function add(a: number, b: number): number {
    return a + b;
}
"""

        result = parser.parse(code)
        func = result["functions"][0]

        assert func["name"] == "add"
        assert len(func["parameters"]) == 2
        assert func["return_type"] == "number"


class TestTypeScriptInterfaceExtraction:
    """Test extracting interfaces from TypeScript code."""

    def test_extract_simple_interface(self):
        """Test extracting a simple interface."""
        from tree_sitter_analyzer_v2.languages.typescript_parser import TypeScriptParser

        parser = TypeScriptParser()
        code = """
interface User {
    name: string;
    age: number;
}
"""

        result = parser.parse(code)

        assert "interfaces" in result
        assert len(result["interfaces"]) == 1

        iface = result["interfaces"][0]
        assert iface["name"] == "User"

    def test_extract_interface_with_properties(self):
        """Test extracting interface with properties."""
        from tree_sitter_analyzer_v2.languages.typescript_parser import TypeScriptParser

        parser = TypeScriptParser()
        code = """
interface Person {
    name: string;
    age: number;
    email?: string;
}
"""

        result = parser.parse(code)
        iface = result["interfaces"][0]

        assert iface["name"] == "Person"
        assert "properties" in iface
        assert len(iface["properties"]) == 3

        prop_names = [p["name"] for p in iface["properties"]]
        assert "name" in prop_names
        assert "age" in prop_names
        assert "email" in prop_names

    def test_extract_interface_with_methods(self):
        """Test extracting interface with method signatures."""
        from tree_sitter_analyzer_v2.languages.typescript_parser import TypeScriptParser

        parser = TypeScriptParser()
        code = """
interface Calculator {
    add(a: number, b: number): number;
    subtract(a: number, b: number): number;
}
"""

        result = parser.parse(code)
        iface = result["interfaces"][0]

        assert "methods" in iface
        assert len(iface["methods"]) == 2

        method_names = [m["name"] for m in iface["methods"]]
        assert "add" in method_names
        assert "subtract" in method_names


class TestTypeScriptTypeAliasExtraction:
    """Test extracting type aliases from TypeScript code."""

    def test_extract_type_alias(self):
        """Test extracting type alias."""
        from tree_sitter_analyzer_v2.languages.typescript_parser import TypeScriptParser

        parser = TypeScriptParser()
        code = """
type ID = string | number;
type Point = { x: number; y: number };
"""

        result = parser.parse(code)

        assert "types" in result
        assert len(result["types"]) == 2

        type_names = [t["name"] for t in result["types"]]
        assert "ID" in type_names
        assert "Point" in type_names


class TestTypeScriptClassExtraction:
    """Test extracting classes from TypeScript code."""

    def test_extract_simple_class(self):
        """Test extracting a simple class."""
        from tree_sitter_analyzer_v2.languages.typescript_parser import TypeScriptParser

        parser = TypeScriptParser()
        code = """
class Calculator {
}
"""

        result = parser.parse(code)

        assert "classes" in result
        assert len(result["classes"]) == 1

        cls = result["classes"][0]
        assert cls["name"] == "Calculator"

    def test_extract_class_with_methods(self):
        """Test extracting class with methods."""
        from tree_sitter_analyzer_v2.languages.typescript_parser import TypeScriptParser

        parser = TypeScriptParser()
        code = """
class Calculator {
    add(a: number, b: number): number {
        return a + b;
    }

    subtract(a: number, b: number): number {
        return a - b;
    }
}
"""

        result = parser.parse(code)
        cls = result["classes"][0]

        assert cls["name"] == "Calculator"
        assert "methods" in cls
        assert len(cls["methods"]) == 2

    def test_extract_class_with_implements(self):
        """Test extracting class that implements interface."""
        from tree_sitter_analyzer_v2.languages.typescript_parser import TypeScriptParser

        parser = TypeScriptParser()
        code = """
interface Animal {
    speak(): void;
}

class Dog implements Animal {
    speak() {
        console.log("Woof!");
    }
}
"""

        result = parser.parse(code)

        dog_class = next(c for c in result["classes"] if c["name"] == "Dog")
        assert "implements" in dog_class
        assert "Animal" in dog_class["implements"]


class TestTypeScriptImportExportExtraction:
    """Test extracting imports and exports from TypeScript code."""

    def test_extract_import_statement(self):
        """Test extracting import statement."""
        from tree_sitter_analyzer_v2.languages.typescript_parser import TypeScriptParser

        parser = TypeScriptParser()
        code = """
import { User } from './types';
import * as utils from './utils';
"""

        result = parser.parse(code)

        assert "imports" in result
        assert len(result["imports"]) == 2

    def test_extract_export_statement(self):
        """Test extracting export statement."""
        from tree_sitter_analyzer_v2.languages.typescript_parser import TypeScriptParser

        parser = TypeScriptParser()
        code = """
export interface User {
    name: string;
}

export function greet(name: string) {
    return `Hello, ${name}`;
}
"""

        result = parser.parse(code)

        # Exported items should be marked as exported
        assert "exports" in result
        assert len(result["exports"]) >= 2


class TestTypeScriptMetadata:
    """Test metadata extraction."""

    def test_metadata_includes_counts(self):
        """Test that metadata includes counts."""
        from tree_sitter_analyzer_v2.languages.typescript_parser import TypeScriptParser

        parser = TypeScriptParser()
        code = """
interface User { name: string; }
type ID = number;
function greet() {}
class App {}
"""

        result = parser.parse(code)

        assert "metadata" in result
        assert "total_interfaces" in result["metadata"]
        assert "total_types" in result["metadata"]
        assert "total_functions" in result["metadata"]
        assert "total_classes" in result["metadata"]

        assert result["metadata"]["total_interfaces"] == 1
        assert result["metadata"]["total_types"] == 1
        assert result["metadata"]["total_functions"] == 1
        assert result["metadata"]["total_classes"] == 1

    def test_metadata_includes_line_numbers(self):
        """Test that extracted items include line numbers."""
        from tree_sitter_analyzer_v2.languages.typescript_parser import TypeScriptParser

        parser = TypeScriptParser()
        code = """
interface User {
    name: string;
}

function greet() {}
"""

        result = parser.parse(code)

        # Interfaces should have line numbers
        iface = result["interfaces"][0]
        assert "line_start" in iface
        assert "line_end" in iface

        # Functions should have line numbers
        func = result["functions"][0]
        assert "line_start" in func
        assert "line_end" in func


class TestTypeScriptEdgeCases:
    """Test edge cases and error handling."""

    def test_parse_empty_file(self):
        """Test parsing empty TypeScript file."""
        from tree_sitter_analyzer_v2.languages.typescript_parser import TypeScriptParser

        parser = TypeScriptParser()
        result = parser.parse("")

        assert result is not None
        assert result["functions"] == []
        assert result["classes"] == []
        assert result["interfaces"] == []
        assert result["types"] == []

    def test_parse_syntax_error(self):
        """Test parsing code with syntax errors."""
        from tree_sitter_analyzer_v2.languages.typescript_parser import TypeScriptParser

        parser = TypeScriptParser()
        code = "function broken("

        result = parser.parse(code)

        # Should still return result, but mark errors
        assert result is not None
        assert "errors" in result
        assert result["errors"] is True

    def test_parse_tsx_react_code(self):
        """Test that parser works with JSX/TSX code."""
        from tree_sitter_analyzer_v2.languages.typescript_parser import TypeScriptParser

        parser = TypeScriptParser()
        code = """
function Component() {
    return <div>Hello</div>;
}
"""

        result = parser.parse(code)

        # Should parse without crashing
        assert result is not None
        # TSX not fully supported yet, but shouldn't crash
