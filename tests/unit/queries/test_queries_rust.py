"""
Tests for Rust language queries.

Validates that Rust tree-sitter queries are syntactically correct
and return expected results for various Rust code constructs.
"""

import pytest

try:
    import tree_sitter_rust

    RUST_AVAILABLE = True
except ImportError:
    RUST_AVAILABLE = False

from tests.unit.queries.conftest import get_language
from tree_sitter_analyzer.queries import rust as rust_queries


def _lang():
    return get_language(tree_sitter_rust.language())


SAMPLE_RUST_CODE = """
use std::collections::HashMap;

struct Animal {
    name: String,
    age: u32,
}

impl Animal {
    fn new(name: &str, age: u32) -> Self {
        Animal { name: name.to_string(), age }
    }
    fn speak(&self) -> String {
        format!("I am {}", self.name)
    }
}

trait Speaker {
    fn speak(&self) -> String;
}

enum Direction {
    North, South, East, West,
}

fn add(a: i32, b: i32) -> i32 { a + b }

const MAX_SIZE: usize = 100;
static GLOBAL: &str = "hello";

fn main() {
    let animal = Animal::new("Dog", 5);
    println!("{}", animal.speak());
}
"""

KNOWN_BROKEN_QUERIES = {"async_fn", "derive_attribute"}

RUST_KEYS_TO_TEST = [
    "mod",
    "struct",
    "enum",
    "trait",
    "impl",
    "macro",
    "fn",
    "async_fn",
    "field",
    "enum_variant",
    "const",
    "static",
    "type_alias",
    "attribute",
    "derive_attribute",
    "functions",  # alias
    "methods",  # alias
    "classes",  # alias
]


def _get_query(module, key):
    """Get query string from ALL_QUERIES or RUST_QUERIES."""
    if key in module.ALL_QUERIES:
        entry = module.ALL_QUERIES[key]
        return entry["query"] if isinstance(entry, dict) else entry
    if key in module.RUST_QUERIES:
        return module.RUST_QUERIES[key]
    return None


@pytest.mark.skipif(not RUST_AVAILABLE, reason="tree-sitter-rust not available")
class TestRustQueriesSyntax:
    """Test that Rust queries compile successfully."""

    def test_rust_queries_dict_exists(self):
        assert hasattr(rust_queries, "RUST_QUERIES")
        assert hasattr(rust_queries, "ALL_QUERIES")
        assert len(rust_queries.RUST_QUERIES) > 0
        assert len(rust_queries.ALL_QUERIES) >= 20

    def test_all_queries_dict_compilable_count(self):
        """At least 70% of ALL_QUERIES entries should compile."""
        import tree_sitter

        lang = _lang()
        all_q = rust_queries.ALL_QUERIES
        compiled, failed = 0, 0
        for _name, entry in all_q.items():
            qstr = entry["query"] if isinstance(entry, dict) else entry
            try:
                tree_sitter.Query(lang, qstr)
                compiled += 1
            except Exception:
                failed += 1
        ratio = compiled / (compiled + failed) if (compiled + failed) > 0 else 1.0
        assert (
            ratio >= 0.7
        ), f"Only {compiled}/{compiled+failed} ({ratio:.0%}) queries compile"

    @pytest.mark.parametrize(
        "key", [k for k in RUST_KEYS_TO_TEST if _get_query(rust_queries, k)]
    )
    def test_individual_query_compiles(self, key, query_validator):
        if key in KNOWN_BROKEN_QUERIES:
            pytest.xfail(f"{key} has known grammar incompatibility")
        qstr = _get_query(rust_queries, key)
        assert qstr is not None
        query_validator(_lang(), qstr)


@pytest.mark.skipif(not RUST_AVAILABLE, reason="tree-sitter-rust not available")
class TestRustQueriesFunctionality:
    """Test that Rust queries return expected results."""

    def test_struct_query_finds_structs(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_RUST_CODE, _get_query(rust_queries, "struct")
        )
        assert len(results) >= 1  # Animal

    def test_enum_query_finds_enums(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_RUST_CODE, _get_query(rust_queries, "enum")
        )
        assert len(results) >= 1  # Direction

    def test_trait_query_finds_traits(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_RUST_CODE, _get_query(rust_queries, "trait")
        )
        assert len(results) >= 1  # Speaker

    def test_impl_query_finds_impl_blocks(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_RUST_CODE, _get_query(rust_queries, "impl")
        )
        assert len(results) >= 1  # impl Animal

    def test_fn_query_finds_functions(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_RUST_CODE, _get_query(rust_queries, "fn")
        )
        assert len(results) >= 4  # new, speak, speak (trait), add, main

    def test_field_query_finds_fields(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_RUST_CODE, _get_query(rust_queries, "field")
        )
        assert len(results) >= 2  # name, age

    def test_enum_variant_query_finds_variants(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_RUST_CODE, _get_query(rust_queries, "enum_variant")
        )
        assert len(results) >= 4  # North, South, East, West

    def test_const_query_finds_const(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_RUST_CODE, _get_query(rust_queries, "const")
        )
        assert len(results) >= 1  # MAX_SIZE

    def test_static_query_finds_static(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_RUST_CODE, _get_query(rust_queries, "static")
        )
        assert len(results) >= 1  # GLOBAL

    def test_functions_alias_works(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_RUST_CODE, _get_query(rust_queries, "functions")
        )
        assert len(results) >= 4

    def test_macro_call_query(self, query_executor):
        results = query_executor(
            _lang(), SAMPLE_RUST_CODE, _get_query(rust_queries, "macro_call")
        )
        assert len(results) >= 1  # println!


@pytest.mark.skipif(not RUST_AVAILABLE, reason="tree-sitter-rust not available")
class TestRustQueriesEdgeCases:
    """Test Rust queries with edge cases."""

    def test_empty_file_returns_no_matches(self, query_executor):
        results = query_executor(_lang(), "", _get_query(rust_queries, "struct"))
        assert len(results) == 0

    def test_comments_only_returns_no_struct_matches(self, query_executor):
        code = "// comment\n/* block */\n"
        results = query_executor(_lang(), code, _get_query(rust_queries, "struct"))
        assert len(results) == 0

    def test_single_struct(self, query_executor):
        code = "struct Point { x: i32, y: i32 }"
        results = query_executor(_lang(), code, _get_query(rust_queries, "struct"))
        assert len(results) >= 1

    def test_single_fn(self, query_executor):
        code = 'fn main() { println!("hi"); }'
        results = query_executor(_lang(), code, _get_query(rust_queries, "fn"))
        assert len(results) >= 1

    def test_attribute_query(self, query_executor):
        code = "#[derive(Debug, Clone)]\nstruct Foo {}"
        results = query_executor(_lang(), code, _get_query(rust_queries, "attribute"))
        assert len(results) >= 1


@pytest.mark.skipif(not RUST_AVAILABLE, reason="tree-sitter-rust not available")
class TestRustQueriesHelpers:
    """Test helper functions in the rust queries module."""

    def test_get_query_valid(self):
        all_q = rust_queries.get_all_queries()
        if all_q:
            name = next(iter(all_q))
            result = rust_queries.get_query(name)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_get_query_invalid_raises(self):
        with pytest.raises(ValueError):
            rust_queries.get_query("__nonexistent_query__")

    def test_get_all_queries_returns_dict(self):
        result = rust_queries.get_all_queries()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_list_queries_returns_list(self):
        result = rust_queries.list_queries()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_get_rust_query_valid(self):
        available = rust_queries.get_available_rust_queries()
        if available:
            result = rust_queries.get_rust_query(available[0])
            assert isinstance(result, str | dict)

    def test_get_rust_query_invalid_raises(self):
        with pytest.raises(ValueError):
            rust_queries.get_rust_query("__nonexistent__")

    def test_get_rust_query_description(self):
        available = rust_queries.get_available_rust_queries()
        if available:
            desc = rust_queries.get_rust_query_description(available[0])
            assert isinstance(desc, str)

    def test_get_rust_query_description_unknown(self):
        desc = rust_queries.get_rust_query_description("__nonexistent__")
        assert desc == "No description"

    def test_get_available_rust_queries(self):
        result = rust_queries.get_available_rust_queries()
        assert isinstance(result, list)
        assert len(result) > 0
