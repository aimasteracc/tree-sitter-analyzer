"""Tests for core/request_builder.py — build_request_from_params, update_request_from_params."""


from tree_sitter_analyzer.core.request_builder import (
    build_request_from_params,
    update_request_from_params,
)


class TestBuildRequestFromParams:
    def test_defaults_with_file_path_only(self):
        req = build_request_from_params(file_path="/tmp/test.py")
        assert req.file_path == "/tmp/test.py"
        assert req.language is None
        assert req.format_type == "json"
        assert req.include_details is False
        assert req.include_complexity is True
        assert req.include_elements is True
        assert req.include_queries is True
        assert req.queries is None

    def test_all_params_explicit(self):
        req = build_request_from_params(
            file_path="/tmp/test.py",
            language="python",
            format_type="text",
            include_details=True,
            include_complexity=False,
            include_elements=False,
            include_queries=False,
            queries=["functions", "classes"],
        )
        assert req.language == "python"
        assert req.format_type == "text"
        assert req.include_details is True
        assert req.include_complexity is False
        assert req.include_elements is False
        assert req.include_queries is False
        assert req.queries == ["functions", "classes"]

    def test_format_type_none_defaults_to_json(self):
        req = build_request_from_params(file_path="/tmp/a.py", format_type=None)
        assert req.format_type == "json"

    def test_include_details_none_defaults_to_false(self):
        req = build_request_from_params(file_path="/tmp/a.py", include_details=None)
        assert req.include_details is False

    def test_include_complexity_none_defaults_to_true(self):
        req = build_request_from_params(file_path="/tmp/a.py", include_complexity=None)
        assert req.include_complexity is True


class TestUpdateRequestFromParams:
    def test_update_language(self):
        req = build_request_from_params(file_path="/tmp/a.py")
        update_request_from_params(req, language="java")
        assert req.language == "java"

    def test_update_format_type(self):
        req = build_request_from_params(file_path="/tmp/a.py")
        update_request_from_params(req, format_type="toon")
        assert req.format_type == "toon"

    def test_update_boolean_fields(self):
        req = build_request_from_params(file_path="/tmp/a.py")
        update_request_from_params(
            req,
            include_details=True,
            include_complexity=False,
            include_elements=False,
            include_queries=False,
        )
        assert req.include_details is True
        assert req.include_complexity is False
        assert req.include_elements is False
        assert req.include_queries is False

    def test_update_queries(self):
        req = build_request_from_params(file_path="/tmp/a.py")
        update_request_from_params(req, queries=["imports"])
        assert req.queries == ["imports"]

    def test_no_changes_when_none(self):
        req = build_request_from_params(file_path="/tmp/a.py")
        original_lang = req.language
        original_format = req.format_type
        update_request_from_params(req)
        assert req.language == original_lang
        assert req.format_type == original_format

    def test_update_does_not_mutate_file_path(self):
        req = build_request_from_params(file_path="/tmp/a.py")
        update_request_from_params(req, language="go")
        assert req.file_path == "/tmp/a.py"

    def test_include_details_false_is_respected(self):
        req = build_request_from_params(file_path="/tmp/a.py", include_details=True)
        assert req.include_details is True
        update_request_from_params(req, include_details=False)
        assert req.include_details is False
