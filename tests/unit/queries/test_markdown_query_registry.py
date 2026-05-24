from tree_sitter_analyzer.queries.markdown import (
    ALL_QUERIES,
    MARKDOWN_QUERIES,
    QUERY_ALIASES,
    get_all_queries,
    list_queries,
)


class TestGetAllQueries:
    def test_returns_dict(self):
        result = get_all_queries()
        assert isinstance(result, dict)

    def test_contains_all_base_queries(self):
        result = get_all_queries()
        for name in MARKDOWN_QUERIES:
            assert name in result

    def test_contains_aliases(self):
        result = get_all_queries()
        for alias in QUERY_ALIASES:
            assert alias in result

    def test_each_entry_has_query_and_description(self):
        result = get_all_queries()
        for _key, val in result.items():
            assert "query" in val
            assert "description" in val


class TestListQueries:
    def test_returns_list(self):
        result = list_queries()
        assert isinstance(result, list)

    def test_includes_base_query_names(self):
        result = list_queries()
        for name in MARKDOWN_QUERIES:
            assert name in result

    def test_includes_alias_names(self):
        result = list_queries()
        for alias in QUERY_ALIASES:
            assert alias in result


class TestAllQueriesModuleDict:
    def test_alias_points_to_same_query_as_target(self):
        assert ALL_QUERIES["heading"]["query"] == MARKDOWN_QUERIES["headers"]
        assert ALL_QUERIES["code"]["query"] == MARKDOWN_QUERIES["code_blocks"]

    def test_alias_entry_has_description(self):
        assert "description" in ALL_QUERIES["h1"]
        assert "description" in ALL_QUERIES["link"]
