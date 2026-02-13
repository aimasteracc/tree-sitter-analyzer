"""
Tests for YAML language queries.

Validates that YAML tree-sitter queries are syntactically correct
and return expected results for various YAML constructs.
"""
import pytest

try:
    import tree_sitter_yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

from tests.unit.queries.conftest import get_language
from tree_sitter_analyzer.queries import yaml as yaml_queries


def _lang():
    return get_language(tree_sitter_yaml.language())


SAMPLE_YAML_CODE = """
# Configuration file
name: my-application
version: "1.0.0"

database:
  host: localhost
  port: 5432
  credentials:
    username: admin
    password: secret

servers:
  - name: web-1
    host: 10.0.0.1
    port: 8080
  - name: web-2
    host: 10.0.0.2
    port: 8080

features:
  enabled: true
  debug: false
  tags: [api, web, production]
"""

YAML_KEYS_TO_TEST = [
    "document",
    "stream",
    "block_mapping",
    "block_mapping_pair",
    "block_sequence",
    "block_sequence_item",
    "flow_mapping",
    "flow_sequence",
    "plain_scalar",
    "double_quote_scalar",
    "integer_scalar",
    "float_scalar",
    "boolean_scalar",
    "comment",
    "key",
    "value",
    "all_mappings",
    "all_sequences",
    "all_scalars",
]


def _get_query(module, key):
    """Get query string from ALL_QUERIES or YAML_QUERIES."""
    if key in module.ALL_QUERIES:
        entry = module.ALL_QUERIES[key]
        return entry["query"] if isinstance(entry, dict) else entry
    if key in module.YAML_QUERIES:
        return module.YAML_QUERIES[key]
    return None


@pytest.mark.skipif(not YAML_AVAILABLE, reason="tree-sitter-yaml not available")
class TestYamlQueriesSyntax:
    """Test that YAML queries compile successfully."""

    def test_yaml_queries_dict_exists(self):
        assert hasattr(yaml_queries, "YAML_QUERIES")
        assert hasattr(yaml_queries, "ALL_QUERIES")
        assert len(yaml_queries.YAML_QUERIES) > 0
        assert len(yaml_queries.ALL_QUERIES) >= 25

    def test_all_queries_dict_compilable_count(self):
        """At least 70% of ALL_QUERIES entries should compile."""
        import tree_sitter

        lang = _lang()
        all_q = yaml_queries.ALL_QUERIES
        compiled, failed = 0, 0
        for name, entry in all_q.items():
            qstr = entry["query"] if isinstance(entry, dict) else entry
            try:
                tree_sitter.Query(lang, qstr)
                compiled += 1
            except Exception:
                failed += 1
        ratio = compiled / (compiled + failed) if (compiled + failed) > 0 else 1.0
        assert ratio >= 0.7, (
            f"Only {compiled}/{compiled+failed} ({ratio:.0%}) queries compile"
        )

    @pytest.mark.parametrize("key", [k for k in YAML_KEYS_TO_TEST if _get_query(yaml_queries, k)])
    def test_individual_query_compiles(self, key, query_validator):
        qstr = _get_query(yaml_queries, key)
        assert qstr is not None
        query_validator(_lang(), qstr)


@pytest.mark.skipif(not YAML_AVAILABLE, reason="tree-sitter-yaml not available")
class TestYamlQueriesFunctionality:
    """Test that YAML queries return expected results."""

    def test_block_mapping_query_finds_mappings(self, query_executor):
        results = query_executor(_lang(), SAMPLE_YAML_CODE, _get_query(yaml_queries, "block_mapping"))
        assert len(results) >= 3  # database, credentials, servers items, features

    def test_block_mapping_pair_query_finds_pairs(self, query_executor):
        results = query_executor(_lang(), SAMPLE_YAML_CODE, _get_query(yaml_queries, "block_mapping_pair"))
        assert len(results) >= 5  # name, version, host, port, etc.

    def test_block_sequence_query_finds_sequences(self, query_executor):
        results = query_executor(_lang(), SAMPLE_YAML_CODE, _get_query(yaml_queries, "block_sequence"))
        assert len(results) >= 1  # servers list

    def test_block_sequence_item_query_finds_items(self, query_executor):
        results = query_executor(_lang(), SAMPLE_YAML_CODE, _get_query(yaml_queries, "block_sequence_item"))
        assert len(results) >= 2  # web-1, web-2

    def test_plain_scalar_query_finds_scalars(self, query_executor):
        results = query_executor(_lang(), SAMPLE_YAML_CODE, _get_query(yaml_queries, "plain_scalar"))
        assert len(results) >= 5

    def test_double_quote_scalar_query(self, query_executor):
        results = query_executor(_lang(), SAMPLE_YAML_CODE, _get_query(yaml_queries, "double_quote_scalar"))
        assert len(results) >= 1  # "1.0.0"

    def test_boolean_scalar_query(self, query_executor):
        results = query_executor(_lang(), SAMPLE_YAML_CODE, _get_query(yaml_queries, "boolean_scalar"))
        assert len(results) >= 2  # true, false

    def test_flow_sequence_query(self, query_executor):
        results = query_executor(_lang(), SAMPLE_YAML_CODE, _get_query(yaml_queries, "flow_sequence"))
        assert len(results) >= 1  # [api, web, production]

    def test_comment_query_finds_comments(self, query_executor):
        results = query_executor(_lang(), SAMPLE_YAML_CODE, _get_query(yaml_queries, "comment"))
        assert len(results) >= 1  # # Configuration file

    def test_key_query_finds_keys(self, query_executor):
        results = query_executor(_lang(), SAMPLE_YAML_CODE, _get_query(yaml_queries, "key"))
        assert len(results) >= 5

    def test_all_mappings_query(self, query_executor):
        results = query_executor(_lang(), SAMPLE_YAML_CODE, _get_query(yaml_queries, "all_mappings"))
        assert len(results) >= 3

    def test_all_sequences_query(self, query_executor):
        results = query_executor(_lang(), SAMPLE_YAML_CODE, _get_query(yaml_queries, "all_sequences"))
        assert len(results) >= 2  # servers list + flow sequence


@pytest.mark.skipif(not YAML_AVAILABLE, reason="tree-sitter-yaml not available")
class TestYamlQueriesEdgeCases:
    """Test YAML queries with edge cases."""

    def test_empty_file_returns_no_matches(self, query_executor):
        results = query_executor(_lang(), "", _get_query(yaml_queries, "block_mapping"))
        assert len(results) == 0

    def test_single_key_value(self, query_executor):
        code = "key: value"
        results = query_executor(_lang(), code, _get_query(yaml_queries, "block_mapping_pair"))
        assert len(results) >= 1

    def test_empty_mapping(self, query_executor):
        code = "empty: {}"
        results = query_executor(_lang(), code, _get_query(yaml_queries, "flow_mapping"))
        assert len(results) >= 1

    def test_empty_sequence(self, query_executor):
        code = "empty: []"
        results = query_executor(_lang(), code, _get_query(yaml_queries, "flow_sequence"))
        assert len(results) >= 1

    def test_integer_scalar(self, query_executor):
        code = "port: 8080"
        results = query_executor(_lang(), code, _get_query(yaml_queries, "integer_scalar"))
        assert len(results) >= 1


@pytest.mark.skipif(not YAML_AVAILABLE, reason="tree-sitter-yaml not available")
class TestYamlQueriesHelpers:
    """Test helper functions in the yaml queries module."""

    def test_get_query_valid(self):
        all_q = yaml_queries.get_all_queries()
        if all_q:
            name = next(iter(all_q))
            result = yaml_queries.get_query(name)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_get_query_invalid_raises(self):
        with pytest.raises(ValueError):
            yaml_queries.get_query("__nonexistent_query__")

    def test_get_all_queries_returns_dict(self):
        result = yaml_queries.get_all_queries()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_list_queries_returns_list(self):
        result = yaml_queries.list_queries()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_get_yaml_query_valid(self):
        available = yaml_queries.get_available_yaml_queries()
        if available:
            result = yaml_queries.get_yaml_query(available[0])
            assert isinstance(result, (str, dict))

    def test_get_yaml_query_invalid_raises(self):
        with pytest.raises(ValueError):
            yaml_queries.get_yaml_query("__nonexistent__")

    def test_get_yaml_query_description(self):
        available = yaml_queries.get_available_yaml_queries()
        if available:
            desc = yaml_queries.get_yaml_query_description(available[0])
            assert isinstance(desc, str)

    def test_get_yaml_query_description_unknown(self):
        desc = yaml_queries.get_yaml_query_description("__nonexistent__")
        assert desc == "No description"

    def test_get_available_yaml_queries(self):
        result = yaml_queries.get_available_yaml_queries()
        assert isinstance(result, list)
        assert len(result) > 0
