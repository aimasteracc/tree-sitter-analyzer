"""
Regression tests for Issue #746 — JS class field declarations dropped.

Class fields using the `field_definition` node type (public data fields,
private `#fields`, and arrow-function class methods) were silently dropped
because only `property_definition` (object literal) was mapped in the
extractor.  This file pins the fixed behaviour:

* Public data fields (`state = {}`, `count = 0`) → extracted as Variable
* Private data fields (`#privateCounter = 0`) → extracted as Variable
* Arrow-function class methods (`handleClick = () => {}`) → extracted as
  Function with the field name, NOT as "anonymous"
* Arrow-function class methods do NOT appear as Variables (no double-entry)
"""

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

pytestmark = pytest.mark.skipif(
    not _TREE_SITTER_AVAILABLE,
    reason="tree-sitter-javascript not installed — tracked: #746",
)

_CLASS_WITH_FIELDS = """\
class Counter {
    count = 0;
    #privateCounter = 0;
    state = { running: false };
    handleClick = (event) => {
        this.#privateCounter++;
    };
    static defaultStep = 1;
}
"""


@pytest.fixture(scope="module")
def js_parser():
    lang = Language(_tsjava.language())
    return Parser(lang)


@pytest.fixture
def extractor():
    return JavaScriptElementExtractor()


class TestClassFieldVariableExtraction:
    """Issue #746 — public / private data fields must be extracted as Variable."""

    def test_public_data_field_extracted(self, extractor, js_parser):
        """count = 0 must appear as a Variable named 'count'."""
        tree = js_parser.parse(_CLASS_WITH_FIELDS.encode())
        variables = extractor.extract_variables(tree, _CLASS_WITH_FIELDS)
        names = [v.name for v in variables]
        assert "count" in names, f"'count' field missing from variables; got {names}"

    def test_private_data_field_extracted(self, extractor, js_parser):
        """#privateCounter = 0 must appear as a Variable named '#privateCounter'."""
        tree = js_parser.parse(_CLASS_WITH_FIELDS.encode())
        variables = extractor.extract_variables(tree, _CLASS_WITH_FIELDS)
        names = [v.name for v in variables]
        assert "#privateCounter" in names, (
            f"'#privateCounter' field missing from variables; got {names}"
        )

    def test_object_initialised_field_extracted(self, extractor, js_parser):
        """state = { running: false } must appear as a Variable named 'state'."""
        tree = js_parser.parse(_CLASS_WITH_FIELDS.encode())
        variables = extractor.extract_variables(tree, _CLASS_WITH_FIELDS)
        names = [v.name for v in variables]
        assert "state" in names, f"'state' field missing from variables; got {names}"

    def test_static_field_extracted(self, extractor, js_parser):
        """static defaultStep = 1 must appear as a Variable named 'defaultStep'."""
        tree = js_parser.parse(_CLASS_WITH_FIELDS.encode())
        variables = extractor.extract_variables(tree, _CLASS_WITH_FIELDS)
        names = [v.name for v in variables]
        assert "defaultStep" in names, (
            f"'defaultStep' static field missing from variables; got {names}"
        )

    def test_static_field_is_static(self, extractor, js_parser):
        """static defaultStep must have is_static=True."""
        tree = js_parser.parse(_CLASS_WITH_FIELDS.encode())
        variables = extractor.extract_variables(tree, _CLASS_WITH_FIELDS)
        by_name = {v.name: v for v in variables}
        assert by_name.get("defaultStep") is not None, "'defaultStep' not found"
        assert by_name["defaultStep"].is_static is True, (
            "static field must have is_static=True"
        )

    def test_arrow_method_not_extracted_as_variable(self, extractor, js_parser):
        """handleClick (arrow fn) must NOT appear as a Variable — it is a Function."""
        tree = js_parser.parse(_CLASS_WITH_FIELDS.encode())
        variables = extractor.extract_variables(tree, _CLASS_WITH_FIELDS)
        names = [v.name for v in variables]
        assert "handleClick" not in names, (
            f"arrow-function field 'handleClick' must not appear as Variable; got {names}"
        )

    def test_exact_data_field_count(self, extractor, js_parser):
        """Exactly 4 data fields (count, #privateCounter, state, defaultStep)."""
        tree = js_parser.parse(_CLASS_WITH_FIELDS.encode())
        variables = extractor.extract_variables(tree, _CLASS_WITH_FIELDS)
        # Keep only variables coming from field_definition (no top-level let/const)
        field_vars = [
            v
            for v in variables
            if v.name in {"count", "#privateCounter", "state", "defaultStep"}
        ]
        assert len(field_vars) == 4, (
            f"Expected exactly 4 class field variables; got {[v.name for v in field_vars]}"
        )


class TestClassFieldArrowMethodExtraction:
    """Issue #746 — arrow-function class fields must be Functions with correct name."""

    def test_arrow_method_extracted_as_function(self, extractor, js_parser):
        """handleClick = () => {} must appear as a Function."""
        tree = js_parser.parse(_CLASS_WITH_FIELDS.encode())
        functions = extractor.extract_functions(tree, _CLASS_WITH_FIELDS)
        names = [f.name for f in functions]
        assert "handleClick" in names, (
            f"arrow-function field 'handleClick' missing from functions; got {names}"
        )

    def test_arrow_method_not_anonymous(self, extractor, js_parser):
        """handleClick must NOT have name 'anonymous'."""
        tree = js_parser.parse(_CLASS_WITH_FIELDS.encode())
        functions = extractor.extract_functions(tree, _CLASS_WITH_FIELDS)
        anon = [f for f in functions if f.name == "anonymous"]
        assert len(anon) == 0, (
            f"No anonymous functions expected for named class fields; got {[f.name for f in anon]}"
        )


class TestClassFieldVisibility:
    """Codex P2 on #746 — visibility must reflect JS privacy rules."""

    def test_public_field_has_public_visibility(self, extractor, js_parser):
        """count = 0 is public; visibility must be 'public' not 'private'."""
        tree = js_parser.parse(_CLASS_WITH_FIELDS.encode())
        variables = extractor.extract_variables(tree, _CLASS_WITH_FIELDS)
        by_name = {v.name: v for v in variables}
        field = by_name.get("count")
        assert field is not None, "'count' not found"
        assert field.visibility == "public", (
            f"public field 'count' must have visibility='public'; got {field.visibility!r}"
        )

    def test_private_field_has_private_visibility(self, extractor, js_parser):
        """#privateCounter = 0 is private; visibility must be 'private'."""
        tree = js_parser.parse(_CLASS_WITH_FIELDS.encode())
        variables = extractor.extract_variables(tree, _CLASS_WITH_FIELDS)
        by_name = {v.name: v for v in variables}
        field = by_name.get("#privateCounter")
        assert field is not None, "'#privateCounter' not found"
        assert field.visibility == "private", (
            f"private field '#privateCounter' must have visibility='private'; "
            f"got {field.visibility!r}"
        )


class TestClassFieldInitializer:
    """Codex P2 on #746 — non-primitive initializers must not be silently dropped."""

    def test_object_initializer_preserved(self, extractor, js_parser):
        """state = { running: false } must have a non-None initializer."""
        tree = js_parser.parse(_CLASS_WITH_FIELDS.encode())
        variables = extractor.extract_variables(tree, _CLASS_WITH_FIELDS)
        by_name = {v.name: v for v in variables}
        field = by_name.get("state")
        assert field is not None, "'state' not found"
        assert field.initializer is not None, (
            "Object-initialised class field 'state' must have initializer != None"
        )
        assert "running" in (field.initializer or ""), (
            f"Initializer should contain 'running'; got {field.initializer!r}"
        )
