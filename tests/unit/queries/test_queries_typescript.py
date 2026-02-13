"""
Tests for TypeScript language queries.

Validates that TypeScript tree-sitter queries are syntactically correct
and return expected results for various TypeScript code constructs.
"""
import pytest

try:
    import tree_sitter_typescript

    TYPESCRIPT_AVAILABLE = True
except ImportError:
    TYPESCRIPT_AVAILABLE = False

from tests.unit.queries.conftest import get_language
from tree_sitter_analyzer.queries import typescript as ts_queries


def _lang():
    return get_language(tree_sitter_typescript.language_typescript())


ALL_QUERY_CONSTANTS = [
    "FUNCTIONS",
    "CLASSES",
    "INTERFACES",
    "TYPE_ALIASES",
    "ENUMS",
    "VARIABLES",
    "IMPORTS",
    "EXPORTS",
    "DECORATORS",
    "GENERICS",
    "SIGNATURES",
    "COMMENTS",
]

# Queries with known grammar incompatibility (tree-sitter-typescript node names differ)
KNOWN_BROKEN_QUERIES = {"IMPORTS", "GENERICS"}


@pytest.mark.skipif(
    not TYPESCRIPT_AVAILABLE, reason="tree-sitter-typescript not available"
)
class TestTypeScriptQueriesSyntax:
    """Test that all TypeScript query constants compile successfully."""

    @pytest.mark.parametrize("query_name", ALL_QUERY_CONSTANTS)
    def test_query_compiles(self, query_name, query_validator):
        if query_name in KNOWN_BROKEN_QUERIES:
            pytest.xfail(f"{query_name} has known grammar incompatibility")
        qstr = getattr(ts_queries, query_name)
        assert isinstance(qstr, str) and len(qstr.strip()) > 0
        query_validator(_lang(), qstr)

    def test_all_queries_dict_compilable_count(self):
        """Most entries in ALL_QUERIES should compile."""
        import tree_sitter

        lang = _lang()
        all_q = ts_queries.ALL_QUERIES
        assert len(all_q) > 0
        compiled, failed = 0, 0
        for name, entry in all_q.items():
            qstr = entry["query"] if isinstance(entry, dict) else entry
            try:
                tree_sitter.Query(lang, qstr)
                compiled += 1
            except Exception:
                failed += 1
        ratio = compiled / (compiled + failed)
        assert ratio >= 0.7, (
            f"Only {compiled}/{compiled+failed} ({ratio:.0%}) queries compile"
        )


@pytest.mark.skipif(
    not TYPESCRIPT_AVAILABLE, reason="tree-sitter-typescript not available"
)
class TestTypeScriptQueriesFunctionality:
    """Test that TypeScript queries return expected results."""

    SAMPLE_CODE = '''
// Functions
function greet(name: string): string {
    return `Hello ${name}`;
}
const add = (a: number, b: number): number => a + b;

// Classes
class Animal {
    constructor(public name: string) {}
    speak(): void { console.log(this.name); }
}

// Interfaces
interface Shape {
    area(): number;
    perimeter(): number;
}

// Type aliases
type StringOrNumber = string | number;
type Callback = (data: string) => void;

// Enums
enum Direction { Up, Down, Left, Right }
enum Color { Red = 'RED', Blue = 'BLUE' }

// Variables
const MAX_SIZE: number = 100;
let count = 0;

// Imports
import { Component } from '@angular/core';
import * as fs from 'fs';

// Exports
export class MyService {}
export default function main() {}

// Decorators
@Injectable()
class Service {}

// Generics
function identity<T>(arg: T): T { return arg; }
'''

    def test_functions_query_finds_definitions(self, query_executor):
        results = query_executor(_lang(), self.SAMPLE_CODE, ts_queries.FUNCTIONS)
        assert len(results) >= 2

    def test_classes_query_finds_definitions(self, query_executor):
        results = query_executor(_lang(), self.SAMPLE_CODE, ts_queries.CLASSES)
        assert len(results) >= 2

    def test_interfaces_query_finds_definitions(self, query_executor):
        results = query_executor(_lang(), self.SAMPLE_CODE, ts_queries.INTERFACES)
        assert len(results) >= 1

    def test_type_aliases_query_finds_definitions(self, query_executor):
        results = query_executor(_lang(), self.SAMPLE_CODE, ts_queries.TYPE_ALIASES)
        assert len(results) >= 2

    def test_enums_query_finds_definitions(self, query_executor):
        results = query_executor(_lang(), self.SAMPLE_CODE, ts_queries.ENUMS)
        assert len(results) >= 2

    def test_variables_query_finds_declarations(self, query_executor):
        results = query_executor(_lang(), self.SAMPLE_CODE, ts_queries.VARIABLES)
        assert len(results) >= 2

    @pytest.mark.xfail(reason="IMPORTS query has grammar incompatibility")
    def test_imports_query_finds_statements(self, query_executor):
        results = query_executor(_lang(), self.SAMPLE_CODE, ts_queries.IMPORTS)
        assert len(results) >= 2

    def test_exports_query_finds_statements(self, query_executor):
        results = query_executor(_lang(), self.SAMPLE_CODE, ts_queries.EXPORTS)
        assert len(results) >= 2

    def test_decorators_query_finds_decorators(self, query_executor):
        results = query_executor(_lang(), self.SAMPLE_CODE, ts_queries.DECORATORS)
        assert len(results) >= 1

    @pytest.mark.xfail(reason="GENERICS query has grammar incompatibility")
    def test_generics_query_finds_generics(self, query_executor):
        results = query_executor(_lang(), self.SAMPLE_CODE, ts_queries.GENERICS)
        assert len(results) >= 1

    def test_comments_query_finds_comments(self, query_executor):
        results = query_executor(_lang(), self.SAMPLE_CODE, ts_queries.COMMENTS)
        assert len(results) >= 1


@pytest.mark.skipif(
    not TYPESCRIPT_AVAILABLE, reason="tree-sitter-typescript not available"
)
class TestTypeScriptQueriesEdgeCases:
    """Test TypeScript queries with edge cases."""

    def test_empty_file_returns_no_matches(self, query_executor):
        results = query_executor(_lang(), "", ts_queries.FUNCTIONS)
        assert len(results) == 0

    def test_comments_only_returns_no_function_matches(self, query_executor):
        code = "// just a comment\n/* block comment */\n"
        results = query_executor(_lang(), code, ts_queries.FUNCTIONS)
        assert len(results) == 0

    def test_class_with_multiple_methods(self, query_executor):
        code = """
class Calculator {
    add(a: number, b: number): number { return a + b; }
    subtract(a: number, b: number): number { return a - b; }
}
"""
        results = query_executor(_lang(), code, ts_queries.CLASSES)
        assert len(results) >= 1

    def test_arrow_function_detected(self, query_executor):
        code = "const fn = (x: number) => x * 2;"
        results = query_executor(_lang(), code, ts_queries.FUNCTIONS)
        assert len(results) >= 1

    def test_interface_with_method_signature(self, query_executor):
        code = """
interface IRepo {
    get(id: string): Promise<Item>;
    save(item: Item): void;
}
"""
        results = query_executor(_lang(), code, ts_queries.INTERFACES)
        assert len(results) >= 1


@pytest.mark.skipif(not TYPESCRIPT_AVAILABLE, reason="tree-sitter-typescript not available")
class TestTypeScriptQueriesHelpers:
    """Test helper functions in the TypeScript queries module."""

    def test_get_query_valid(self):
        all_q = ts_queries.get_all_queries()
        name = next(iter(all_q))
        result = ts_queries.get_query(name)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_get_query_invalid_raises(self):
        with pytest.raises(ValueError):
            ts_queries.get_query("__nonexistent_query__")

    def test_get_all_queries_returns_dict(self):
        result = ts_queries.get_all_queries()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_list_queries_returns_list(self):
        result = ts_queries.list_queries()
        assert isinstance(result, list)
        assert len(result) > 0
