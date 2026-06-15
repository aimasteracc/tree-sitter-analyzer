"""
Regression tests for JS extraction bugs #747 and #748.

#747: Destructuring RHS identifiers were extracted as phantom variable names.
      `const { a, b } = obj` → only the bound names `a`, `b` should be skipped
      (they are patterns, not declarations); the RHS `obj` must NOT appear as a
      declared variable.

#748: Computed-property method names were extracted as '' (empty string).
      `[post](){}` → name should be `'[post]'`.
      `[Symbol.iterator](){}` → name should be `'[Symbol.iterator]'`.
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
    not _TREE_SITTER_AVAILABLE, reason="tree-sitter-javascript not installed"
)


@pytest.fixture(scope="module")
def js_parser():
    lang = Language(_tsjava.language())
    return Parser(lang)


@pytest.fixture
def extractor():
    return JavaScriptElementExtractor()


# ---------------------------------------------------------------------------
# Bug #747 — destructuring RHS identifiers must NOT appear as variable names
# ---------------------------------------------------------------------------


class TestDestructuringPhantomFields:
    """Bug #747: RHS identifier of destructuring must not be extracted as a variable."""

    def test_object_destructuring_rhs_not_extracted(self, extractor, js_parser):
        """const { a, b } = obj  →  no variable named 'obj' extracted."""
        code = "const { a, b } = obj;\n"
        tree = js_parser.parse(code.encode())
        variables = extractor.extract_variables(tree, code)
        names = [v.name for v in variables]
        assert "obj" not in names, (
            f"RHS 'obj' must not appear as a variable; got {names}"
        )

    def test_array_destructuring_rhs_not_extracted(self, extractor, js_parser):
        """const [x, y] = arr  →  no variable named 'arr' extracted."""
        code = "const [x, y] = arr;\n"
        tree = js_parser.parse(code.encode())
        variables = extractor.extract_variables(tree, code)
        names = [v.name for v in variables]
        assert "arr" not in names, (
            f"RHS 'arr' must not appear as a variable; got {names}"
        )

    def test_plain_variable_still_extracted(self, extractor, js_parser):
        """const name = 'hello'  →  variable 'name' IS extracted (regression guard)."""
        code = "const name = 'hello';\n"
        tree = js_parser.parse(code.encode())
        variables = extractor.extract_variables(tree, code)
        names = [v.name for v in variables]
        assert "name" in names, f"Plain variable 'name' must be extracted; got {names}"

    def test_mixed_declarations(self, extractor, js_parser):
        """Mix of destructuring and plain declarations: only plain ones are extracted."""
        code = "const { a, b } = obj;\nconst [x, y] = arr;\nconst greeting = 'hi';\n"
        tree = js_parser.parse(code.encode())
        variables = extractor.extract_variables(tree, code)
        names = [v.name for v in variables]
        assert "obj" not in names
        assert "arr" not in names
        assert "greeting" in names

    def test_object_destructuring_empty_result(self, extractor, js_parser):
        """A lone destructuring produces zero extracted variables (no phantom names)."""
        code = "const { foo, bar } = source;\n"
        tree = js_parser.parse(code.encode())
        variables = extractor.extract_variables(tree, code)
        assert variables == [], (
            f"Expected no variables from destructuring; got {[v.name for v in variables]}"
        )


# ---------------------------------------------------------------------------
# Bug #748 — computed-property method names must not be ''
# ---------------------------------------------------------------------------


class TestComputedPropertyMethodName:
    """Bug #748: method_definition with computed_property_name must yield non-empty name."""

    def test_simple_computed_identifier(self, extractor, js_parser):
        """class Foo { [post]() {} }  →  method name is '[post]', not ''."""
        code = "class Foo {\n  [post]() { return 1; }\n}\n"
        tree = js_parser.parse(code.encode())
        functions = extractor.extract_functions(tree, code)
        methods = [f for f in functions if f.is_method]
        assert len(methods) == 1
        assert methods[0].name == "[post]"

    def test_member_expression_computed_name(self, extractor, js_parser):
        """class Foo { [Symbol.iterator]() {} }  →  method name is '[Symbol.iterator]'."""
        code = "class Foo {\n  [Symbol.iterator]() { return this; }\n}\n"
        tree = js_parser.parse(code.encode())
        functions = extractor.extract_functions(tree, code)
        methods = [f for f in functions if f.is_method]
        assert len(methods) == 1
        assert methods[0].name == "[Symbol.iterator]"

    def test_regular_method_name_unchanged(self, extractor, js_parser):
        """Regular method name is still extracted correctly (regression guard)."""
        code = "class Foo {\n  regularMethod() {}\n}\n"
        tree = js_parser.parse(code.encode())
        functions = extractor.extract_functions(tree, code)
        methods = [f for f in functions if f.is_method]
        assert len(methods) == 1
        assert methods[0].name == "regularMethod"

    def test_mixed_class_methods(self, extractor, js_parser):
        """Class with computed and regular methods: all names are non-empty."""
        code = (
            "class Foo {\n"
            "  [post]() { return 1; }\n"
            "  [Symbol.iterator]() { return this; }\n"
            "  regularMethod() {}\n"
            "}\n"
        )
        tree = js_parser.parse(code.encode())
        functions = extractor.extract_functions(tree, code)
        methods = [f for f in functions if f.is_method]
        assert len(methods) == 3
        names = [m.name for m in methods]
        assert "[post]" in names
        assert "[Symbol.iterator]" in names
        assert "regularMethod" in names
        # No empty names
        assert "" not in names
