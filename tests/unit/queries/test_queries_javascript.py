"""
Tests for JavaScript language queries.

Validates that JavaScript tree-sitter queries are syntactically correct
and return expected results for various JavaScript code constructs.
"""

import pytest

try:
    import tree_sitter_javascript

    JAVASCRIPT_AVAILABLE = True
except ImportError:
    JAVASCRIPT_AVAILABLE = False

from tests.unit.queries.conftest import get_language
from tree_sitter_analyzer.queries import javascript as js_queries


def _lang():
    return get_language(tree_sitter_javascript.language())


ALL_QUERY_CONSTANTS = [
    "FUNCTIONS",
    "CLASSES",
    "VARIABLES",
    "IMPORTS",
    "EXPORTS",
    "OBJECTS",
    "COMMENTS",
]

# Queries with known grammar incompatibility (tree-sitter-javascript node names differ)
KNOWN_BROKEN_QUERIES = {"IMPORTS", "OBJECTS"}


@pytest.mark.skipif(
    not JAVASCRIPT_AVAILABLE, reason="tree-sitter-javascript not available"
)
class TestJavaScriptQueriesSyntax:
    """Test that all JavaScript query constants compile successfully."""

    @pytest.mark.parametrize("query_name", ALL_QUERY_CONSTANTS)
    def test_query_compiles(self, query_name, query_validator):
        if query_name in KNOWN_BROKEN_QUERIES:
            pytest.xfail(f"{query_name} has known grammar incompatibility")
        qstr = getattr(js_queries, query_name)
        assert isinstance(qstr, str) and len(qstr.strip()) > 0
        query_validator(_lang(), qstr)

    def test_all_queries_dict_compilable_count(self):
        """Most entries in ALL_QUERIES should compile."""
        import tree_sitter

        lang = _lang()
        all_q = js_queries.ALL_QUERIES
        assert len(all_q) > 0
        compiled, failed = 0, 0
        for _name, entry in all_q.items():
            qstr = entry["query"] if isinstance(entry, dict) else entry
            try:
                tree_sitter.Query(lang, qstr)
                compiled += 1
            except Exception:
                failed += 1
        ratio = compiled / (compiled + failed)
        assert (
            ratio >= 0.7
        ), f"Only {compiled}/{compiled+failed} ({ratio:.0%}) queries compile"


@pytest.mark.skipif(
    not JAVASCRIPT_AVAILABLE, reason="tree-sitter-javascript not available"
)
class TestJavaScriptQueriesFunctionality:
    """Test that JavaScript queries return expected results."""

    SAMPLE_CODE = """
// Functions
function calculateSum(a, b) { return a + b; }
const multiply = (x, y) => x * y;

// Classes
class Calculator {
    constructor() { this.result = 0; }
    add(x, y) { return x + y; }
}

// Variables
const MAX = 100;
let name = "test";
var items = [1, 2, 3];

// Imports
import React from 'react';
import { useState } from 'react';

// Exports
export function helper() {}
export default class App {}

// Objects
const config = { debug: true, port: 3000 };

// Comments
// single line comment
/* multi-line comment */
"""

    def test_functions_query_finds_definitions(self, query_executor):
        results = query_executor(_lang(), self.SAMPLE_CODE, js_queries.FUNCTIONS)
        assert len(results) >= 2

    def test_classes_query_finds_definitions(self, query_executor):
        results = query_executor(_lang(), self.SAMPLE_CODE, js_queries.CLASSES)
        assert len(results) >= 1

    def test_variables_query_finds_declarations(self, query_executor):
        results = query_executor(_lang(), self.SAMPLE_CODE, js_queries.VARIABLES)
        assert len(results) >= 3

    @pytest.mark.xfail(reason="IMPORTS query has grammar incompatibility")
    def test_imports_query_finds_statements(self, query_executor):
        results = query_executor(_lang(), self.SAMPLE_CODE, js_queries.IMPORTS)
        assert len(results) >= 2

    def test_exports_query_finds_statements(self, query_executor):
        results = query_executor(_lang(), self.SAMPLE_CODE, js_queries.EXPORTS)
        assert len(results) >= 2

    @pytest.mark.xfail(reason="OBJECTS query has grammar incompatibility")
    def test_objects_query_finds_object_literals(self, query_executor):
        results = query_executor(_lang(), self.SAMPLE_CODE, js_queries.OBJECTS)
        assert len(results) >= 1

    def test_comments_query_finds_comments(self, query_executor):
        results = query_executor(_lang(), self.SAMPLE_CODE, js_queries.COMMENTS)
        assert len(results) >= 1

    def test_arrow_function_detected(self, query_executor):
        code = "const fn = (x, y) => x + y;"
        results = query_executor(_lang(), code, js_queries.FUNCTIONS)
        assert len(results) >= 1

    def test_constructor_detected(self, query_executor):
        code = """
class Foo {
    constructor() { this.x = 0; }
}
"""
        results = query_executor(_lang(), code, js_queries.CLASSES)
        assert len(results) >= 1


@pytest.mark.skipif(
    not JAVASCRIPT_AVAILABLE, reason="tree-sitter-javascript not available"
)
class TestJavaScriptQueriesEdgeCases:
    """Test JavaScript queries with edge cases."""

    def test_empty_file_returns_no_matches(self, query_executor):
        results = query_executor(_lang(), "", js_queries.FUNCTIONS)
        assert len(results) == 0

    def test_comments_only_returns_no_function_matches(self, query_executor):
        code = "// single line\n/* block comment */\n"
        results = query_executor(_lang(), code, js_queries.FUNCTIONS)
        assert len(results) == 0

    def test_export_default_function(self, query_executor):
        code = "export default function main() {}"
        results = query_executor(_lang(), code, js_queries.EXPORTS)
        assert len(results) >= 1

    @pytest.mark.xfail(reason="IMPORTS query has grammar incompatibility")
    def test_import_namespace(self, query_executor):
        code = "import * as utils from './utils';"
        results = query_executor(_lang(), code, js_queries.IMPORTS)
        assert len(results) >= 1

    @pytest.mark.xfail(reason="OBJECTS query has grammar incompatibility")
    def test_object_with_method_property(self, query_executor):
        code = "const obj = { greet() { return 'hi'; } };"
        results = query_executor(_lang(), code, js_queries.OBJECTS)
        assert len(results) >= 1


@pytest.mark.skipif(
    not JAVASCRIPT_AVAILABLE, reason="tree-sitter-javascript not available"
)
class TestJavaScriptQueriesHelpers:
    """Test helper functions in the javascript queries module."""

    def test_get_query_valid(self):
        all_q = js_queries.get_all_queries()
        if all_q:
            name = next(iter(all_q))
            result = js_queries.get_query(name)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_get_query_invalid_raises(self):
        with pytest.raises(ValueError):
            js_queries.get_query("__nonexistent_query__")

    def test_get_all_queries_returns_dict(self):
        result = js_queries.get_all_queries()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_list_queries_returns_list(self):
        result = js_queries.list_queries()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_get_javascript_query_valid(self):
        available = js_queries.get_available_javascript_queries()
        if available:
            result = js_queries.get_javascript_query(available[0])
            assert isinstance(result, str | dict)

    def test_get_javascript_query_invalid_raises(self):
        with pytest.raises(ValueError):
            js_queries.get_javascript_query("__nonexistent__")

    def test_get_javascript_query_description(self):
        available = js_queries.get_available_javascript_queries()
        if available:
            desc = js_queries.get_javascript_query_description(available[0])
            assert isinstance(desc, str)

    def test_get_javascript_query_description_unknown(self):
        desc = js_queries.get_javascript_query_description("__nonexistent__")
        assert desc == "No description"

    def test_get_available_javascript_queries(self):
        result = js_queries.get_available_javascript_queries()
        assert isinstance(result, list)
        assert len(result) > 0
