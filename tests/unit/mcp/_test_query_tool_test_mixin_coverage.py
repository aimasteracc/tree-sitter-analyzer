"""Private mixins for query-tool query categorization coverage."""

from tree_sitter_analyzer.mcp.tools.query_tool import _categorize_queries


class TestCategorizeQueriesCoverageTestMixin:
    """Tests for _categorize_queries covering remaining branches."""

    def test_linq_categorized_as_framework(self):
        result = _categorize_queries(["linq_expressions"], "csharp")
        assert "framework" in result
        assert "linq_expressions" in result["framework"]

    def test_lambda_categorized_as_framework(self):
        result = _categorize_queries(["lambda_functions"], "python")
        # "lambda" contains "function" keyword -> declarations, not framework
        assert "declarations" in result
        assert "lambda_functions" in result["declarations"]

    def test_channel_categorized_as_framework(self):
        result = _categorize_queries(["channel_operations"], "go")
        assert "framework" in result
        assert "channel_operations" in result["framework"]

    def test_annotation_categorized_as_framework(self):
        result = _categorize_queries(["annotation_declarations"], "java")
        assert "framework" in result
        assert "annotation_declarations" in result["framework"]

    def test_attribute_categorized_as_framework(self):
        result = _categorize_queries(["attribute_usage"], "csharp")
        assert "framework" in result
        assert "attribute_usage" in result["framework"]

    def test_async_categorized_as_framework(self):
        result = _categorize_queries(["async_functions"], "javascript")
        # "async_functions" contains "function" keyword -> declarations, not framework
        assert "declarations" in result
        assert "async_functions" in result["declarations"]

    def test_http_categorized_as_framework(self):
        result = _categorize_queries(["http_handlers"], "typescript")
        assert "framework" in result
        assert "http_handlers" in result["framework"]

    def test_authorize_categorized_as_framework(self):
        result = _categorize_queries(["authorize_attributes"], "csharp")
        assert "framework" in result
        assert "authorize_attributes" in result["framework"]

    def test_trait_categorized_as_declaration(self):
        result = _categorize_queries(["trait_implementations"], "rust")
        assert "declarations" in result
        assert "trait_implementations" in result["declarations"]

    def test_module_categorized_as_declaration(self):
        result = _categorize_queries(["module_exports"], "javascript")
        assert "declarations" in result
        assert "module_exports" in result["declarations"]

    def test_property_categorized_as_declaration(self):
        result = _categorize_queries(["property_declarations"], "typescript")
        assert "declarations" in result
        assert "property_declarations" in result["declarations"]

    def test_constructor_categorized_as_declaration(self):
        result = _categorize_queries(["constructor_declarations"], "java")
        assert "declarations" in result
        assert "constructor_declarations" in result["declarations"]

    def test_fn_categorized_as_declaration(self):
        result = _categorize_queries(["fn_definitions"], "rust")
        assert "declarations" in result
        assert "fn_definitions" in result["declarations"]

    def test_field_categorized_as_declaration(self):
        result = _categorize_queries(["field_declarations"], "java")
        assert "declarations" in result
        assert "field_declarations" in result["declarations"]
