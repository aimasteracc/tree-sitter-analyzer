"""
Regression tests for Issues #890, #891, #892 — JS class field bugs.

#890 — is_method=True and parent_class for class-field arrow methods
    Arrow-function class fields (e.g. `build = () => {}`) are extracted as
    Function objects, but must have is_method=True and parent_class set to
    the owning class name.

#891 — field_definition missing from JS query surface
    The VARIABLES query string and get_element_categories() 'variable' key
    both omit 'field_definition', so query_code(query_key='variable') returns
    no results for files that only contain class fields.

#892 — computed/string/numeric class field names silently dropped
    _extract_field_definition_optimized only handles property_identifier and
    private_property_identifier.  Computed property names ([x] = 1), numeric
    keys (0 = 'zero'), and string keys ('key' = val) are silently dropped.
"""

from __future__ import annotations

import pytest

try:
    import tree_sitter_javascript as _tsjava
    from tree_sitter import Language, Parser

    _TREE_SITTER_AVAILABLE = True
except ImportError:
    _TREE_SITTER_AVAILABLE = False

from tree_sitter_analyzer.languages.javascript_plugin.extractor import (
    JavaScriptElementExtractor,
)
from tree_sitter_analyzer.languages.javascript_plugin.plugin import JavaScriptPlugin
from tree_sitter_analyzer.queries.javascript import VARIABLES

pytestmark = pytest.mark.skipif(
    not _TREE_SITTER_AVAILABLE,
    reason="tree-sitter-javascript not installed (tracked: #891 environment dependency)",
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def js_parser():
    lang = Language(_tsjava.language())
    return Parser(lang)


@pytest.fixture
def extractor():
    return JavaScriptElementExtractor()


@pytest.fixture
def plugin():
    return JavaScriptPlugin()


# ---------------------------------------------------------------------------
# Source snippets
# ---------------------------------------------------------------------------

_ARROW_CLASS = """\
class Widget {
    build = () => {
        return 42;
    };
    render = async (ctx) => {
        return ctx;
    };
}
"""

_ONLY_CLASS_FIELDS = """\
class Config {
    timeout = 5000;
    retries = 3;
}
"""

_COMPUTED_STRING_NUMERIC_FIELDS = """\
class Fancy {
    ['computed'] = 'yes';
    'string_key' = 'value';
    0 = 'zero';
    name = 'normal';
}
"""


# ===========================================================================
# Bug #890 — is_method=True and parent_class for arrow class-field methods
# ===========================================================================


class TestBug890ArrowFieldIsMethod:
    """Arrow-function class fields must be extracted with is_method=True
    and parent_class set to the owning class name."""

    def test_arrow_field_is_method_true(self, extractor, js_parser):
        """`build = () => {}` inside a class must yield is_method=True."""
        tree = js_parser.parse(_ARROW_CLASS.encode())
        functions = extractor.extract_functions(tree, _ARROW_CLASS)
        by_name = {f.name: f for f in functions}
        assert "build" in by_name, (
            f"'build' missing from functions; got {list(by_name)}"
        )
        assert by_name["build"].is_method is True, (
            f"'build' arrow field must have is_method=True; "
            f"got is_method={by_name['build'].is_method}"
        )

    def test_arrow_field_parent_class_set(self, extractor, js_parser):
        """`build = () => {}` inside class Widget must have parent_class='Widget'."""
        tree = js_parser.parse(_ARROW_CLASS.encode())
        functions = extractor.extract_functions(tree, _ARROW_CLASS)
        by_name = {f.name: f for f in functions}
        assert "build" in by_name, (
            f"'build' missing from functions; got {list(by_name)}"
        )
        assert by_name["build"].parent_class == "Widget", (
            f"'build' arrow field must have parent_class='Widget'; "
            f"got parent_class={by_name['build'].parent_class!r}"
        )

    def test_async_arrow_field_is_method_true(self, extractor, js_parser):
        """`render = async (ctx) => {}` must also get is_method=True."""
        tree = js_parser.parse(_ARROW_CLASS.encode())
        functions = extractor.extract_functions(tree, _ARROW_CLASS)
        by_name = {f.name: f for f in functions}
        assert "render" in by_name, (
            f"'render' missing from functions; got {list(by_name)}"
        )
        assert by_name["render"].is_method is True, (
            f"async arrow field 'render' must have is_method=True; "
            f"got is_method={by_name['render'].is_method}"
        )

    def test_async_arrow_field_parent_class_set(self, extractor, js_parser):
        """`render = async (ctx) => {}` must have parent_class='Widget'."""
        tree = js_parser.parse(_ARROW_CLASS.encode())
        functions = extractor.extract_functions(tree, _ARROW_CLASS)
        by_name = {f.name: f for f in functions}
        assert "render" in by_name, (
            f"'render' missing from functions; got {list(by_name)}"
        )
        assert by_name["render"].parent_class == "Widget", (
            f"async arrow field 'render' must have parent_class='Widget'; "
            f"got parent_class={by_name['render'].parent_class!r}"
        )

    def test_is_arrow_still_true(self, extractor, js_parser):
        """Arrow class fields must keep is_arrow=True alongside is_method=True."""
        tree = js_parser.parse(_ARROW_CLASS.encode())
        functions = extractor.extract_functions(tree, _ARROW_CLASS)
        by_name = {f.name: f for f in functions}
        assert "build" in by_name
        assert by_name["build"].is_arrow is True, (
            "Arrow class field must retain is_arrow=True"
        )


# ===========================================================================
# Bug #891 — field_definition missing from JS query surface
# ===========================================================================


class TestBug891FieldDefinitionQuerySurface:
    """field_definition must appear in VARIABLES query string and in
    get_element_categories() so that query_code(query_key='variable') picks
    up class fields."""

    def test_variables_query_string_includes_field_definition(self):
        """The VARIABLES legacy query string must contain 'field_definition'."""
        assert "field_definition" in VARIABLES, (
            "VARIABLES query string is missing 'field_definition'; "
            f"current content:\n{VARIABLES}"
        )

    def test_element_categories_variable_includes_field_definition(self, plugin):
        """plugin.get_element_categories()['variable'] must include 'field_definition'."""
        cats = plugin.get_element_categories()
        assert "variable" in cats, "'variable' key missing from element_categories"
        assert "field_definition" in cats["variable"], (
            f"'field_definition' missing from element_categories['variable']; "
            f"got {cats['variable']}"
        )

    def test_element_categories_variables_plural_includes_field_definition(
        self, plugin
    ):
        """plugin.get_element_categories()['variables'] must also include 'field_definition'."""
        cats = plugin.get_element_categories()
        assert "variables" in cats, "'variables' key missing from element_categories"
        assert "field_definition" in cats["variables"], (
            f"'field_definition' missing from element_categories['variables']; "
            f"got {cats['variables']}"
        )

    def test_fields_only_file_returns_variables(self, extractor, js_parser):
        """A file containing only class fields must return > 0 variables."""
        tree = js_parser.parse(_ONLY_CLASS_FIELDS.encode())
        variables = extractor.extract_variables(tree, _ONLY_CLASS_FIELDS)
        assert len(variables) == 2, (
            f"Expected exactly 2 class field variables from Config; got {len(variables)}: "
            f"{[v.name for v in variables]}"
        )


# ===========================================================================
# Bug #892 — computed/string/numeric class field names silently dropped
# ===========================================================================


class TestBug892ComputedStringNumericFieldNames:
    """Computed, string, and numeric class field names must be extracted."""

    def test_computed_property_name_extracted(self, extractor, js_parser):
        """`['computed'] = 'yes'` must appear as a variable (name contains 'computed')."""
        tree = js_parser.parse(_COMPUTED_STRING_NUMERIC_FIELDS.encode())
        variables = extractor.extract_variables(tree, _COMPUTED_STRING_NUMERIC_FIELDS)
        names = [v.name for v in variables]
        # The extracted name should capture the computed key content
        computed_vars = [n for n in names if "computed" in n]
        assert len(computed_vars) == 1, (
            f"Expected exactly 1 variable with 'computed' in name; "
            f"got {computed_vars} from all names: {names}"
        )

    def test_string_key_field_extracted(self, extractor, js_parser):
        """`'string_key' = 'value'` must appear as a variable."""
        tree = js_parser.parse(_COMPUTED_STRING_NUMERIC_FIELDS.encode())
        variables = extractor.extract_variables(tree, _COMPUTED_STRING_NUMERIC_FIELDS)
        names = [v.name for v in variables]
        string_key_vars = [n for n in names if "string_key" in n]
        assert len(string_key_vars) == 1, (
            f"Expected exactly 1 variable with 'string_key' in name; "
            f"got {string_key_vars} from all names: {names}"
        )

    def test_numeric_key_field_extracted(self, extractor, js_parser):
        """`0 = 'zero'` must appear as a variable (name is '0')."""
        tree = js_parser.parse(_COMPUTED_STRING_NUMERIC_FIELDS.encode())
        variables = extractor.extract_variables(tree, _COMPUTED_STRING_NUMERIC_FIELDS)
        names = [v.name for v in variables]
        assert "0" in names, f"Expected numeric key '0' in variable names; got {names}"

    def test_normal_field_still_extracted(self, extractor, js_parser):
        """`name = 'normal'` (plain property_identifier) must still be extracted."""
        tree = js_parser.parse(_COMPUTED_STRING_NUMERIC_FIELDS.encode())
        variables = extractor.extract_variables(tree, _COMPUTED_STRING_NUMERIC_FIELDS)
        names = [v.name for v in variables]
        assert "name" in names, f"Expected 'name' in variable names; got {names}"

    def test_exact_variable_count_fancy_class(self, extractor, js_parser):
        """All four fields in Fancy must be extracted (computed, string, numeric, plain)."""
        tree = js_parser.parse(_COMPUTED_STRING_NUMERIC_FIELDS.encode())
        variables = extractor.extract_variables(tree, _COMPUTED_STRING_NUMERIC_FIELDS)
        assert len(variables) == 4, (
            f"Expected exactly 4 variables from Fancy class; "
            f"got {len(variables)}: {[v.name for v in variables]}"
        )
