"""Theme E residual — Issue #533: default-valued params dropped in JS/Python;
Bash params structural n/a diagnosis.

RED-first tests for:
  - JS: assignment_pattern (param = default) in formal_parameters silently dropped
  - Python: typed_default_parameter (name: type = default) silently dropped
  - Bash: structural verdict — Bash grammar has no formal param nodes (positional
    $1/$2 at call time); parameters=[] is correct; this test pins that contract.

Convention chosen (matches C# full-text approach):
  - JS:     'limit = 10', 'options = {}' (full assignment_pattern text)
  - Python: 'breed: str = "Mixed"' (full typed_default_parameter text)

Uses real tree-sitter parses — no mocks.
"""

from __future__ import annotations

import pytest

pytest.importorskip("tree_sitter_javascript")
pytest.importorskip("tree_sitter_python")
pytest.importorskip("tree_sitter_bash")

import tree_sitter
import tree_sitter_bash
import tree_sitter_javascript
import tree_sitter_python

# ---------------------------------------------------------------------------
# Helpers — one parser per language
# ---------------------------------------------------------------------------


def _js_parser() -> tree_sitter.Parser:
    return tree_sitter.Parser(tree_sitter.Language(tree_sitter_javascript.language()))


def _py_parser() -> tree_sitter.Parser:
    return tree_sitter.Parser(tree_sitter.Language(tree_sitter_python.language()))


def _bash_parser() -> tree_sitter.Parser:
    return tree_sitter.Parser(tree_sitter.Language(tree_sitter_bash.language()))


# ---------------------------------------------------------------------------
# JavaScript — _extract_parameters in _function_mixin.py
# ---------------------------------------------------------------------------


class TestJSDefaultParameterExtraction:
    """Issue #533 (JS half): assignment_pattern (param = default) was silently
    dropped from _extract_parameters because only 'identifier', 'rest_parameter',
    'object_pattern', and 'array_pattern' were handled.

    Fix: treat 'assignment_pattern' the same way — capture full node text.
    Convention: emit full text, e.g. 'limit = 10', 'options = {}'.
    """

    def test_fibonacciSequence_only_default_param(self):
        """function fibonacciSequence(limit = 10) → ['limit = 10'] (1 param)."""
        from tree_sitter_analyzer.languages.javascript_plugin._function_mixin import (
            JavaScriptFunctionExtractionMixin,
        )
        from tree_sitter_analyzer.languages.javascript_plugin._text_helpers import (
            get_node_text_optimized,
        )

        code = "function fibonacciSequence(limit = 10) { return []; }"
        parser = _js_parser()
        tree = parser.parse(code.encode())

        content_lines = code.splitlines()
        cache: dict = {}

        def get_text(node: object) -> str:
            return get_node_text_optimized(node, content_lines, None, cache, None, None)  # type: ignore[arg-type]

        # Find formal_parameters node
        func_node = tree.root_node.children[0]  # function_declaration
        params_node = None
        for child in func_node.children:
            if child.type == "formal_parameters":
                params_node = child
                break
        assert params_node is not None

        # Build a minimal extractor-like object with _get_node_text_optimized wired
        class _MinimalExtractor(JavaScriptFunctionExtractionMixin):
            def _get_node_text_optimized(self, n: object) -> str:  # type: ignore[override]
                return get_text(n)

        extractor = _MinimalExtractor()
        params = extractor._extract_parameters(params_node)
        assert params == ["limit = 10"]

    def test_processData_mixed_plain_and_default(self):
        """function processData(items, options = {}) → ['items', 'options = {}']."""
        from tree_sitter_analyzer.languages.javascript_plugin._function_mixin import (
            JavaScriptFunctionExtractionMixin,
        )
        from tree_sitter_analyzer.languages.javascript_plugin._text_helpers import (
            get_node_text_optimized,
        )

        code = "function processData(items, options = {}) { return items; }"
        parser = _js_parser()
        tree = parser.parse(code.encode())

        content_lines = code.splitlines()
        cache: dict = {}

        def get_text(node: object) -> str:
            return get_node_text_optimized(node, content_lines, None, cache, None, None)  # type: ignore[arg-type]

        func_node = tree.root_node.children[0]
        params_node = None
        for child in func_node.children:
            if child.type == "formal_parameters":
                params_node = child
                break
        assert params_node is not None

        class _MinimalExtractor(JavaScriptFunctionExtractionMixin):
            def _get_node_text_optimized(self, n: object) -> str:  # type: ignore[override]
                return get_text(n)

        extractor = _MinimalExtractor()
        params = extractor._extract_parameters(params_node)
        assert params == ["items", "options = {}"]

    def test_generateSequence_all_defaults(self):
        """generateSequence(start = 0, end = 10) → ['start = 0', 'end = 10'] (2 params)."""
        from tree_sitter_analyzer.languages.javascript_plugin._function_mixin import (
            JavaScriptFunctionExtractionMixin,
        )
        from tree_sitter_analyzer.languages.javascript_plugin._text_helpers import (
            get_node_text_optimized,
        )

        code = "function generateSequence(start = 0, end = 10) { return []; }"
        parser = _js_parser()
        tree = parser.parse(code.encode())

        content_lines = code.splitlines()
        cache: dict = {}

        def get_text(node: object) -> str:
            return get_node_text_optimized(node, content_lines, None, cache, None, None)  # type: ignore[arg-type]

        func_node = tree.root_node.children[0]
        params_node = None
        for child in func_node.children:
            if child.type == "formal_parameters":
                params_node = child
                break
        assert params_node is not None

        class _MinimalExtractor(JavaScriptFunctionExtractionMixin):
            def _get_node_text_optimized(self, n: object) -> str:  # type: ignore[override]
                return get_text(n)

        extractor = _MinimalExtractor()
        params = extractor._extract_parameters(params_node)
        assert params == ["start = 0", "end = 10"]

    def test_full_plugin_fibonacciSequence_count(self):
        """End-to-end: fibonacciSequence(limit = 10) function has 1 parameter."""
        from tree_sitter_analyzer.languages.javascript_plugin.plugin import (
            JavaScriptPlugin,
        )

        code = "function fibonacciSequence(limit = 10) { return []; }"
        plugin = JavaScriptPlugin()
        extractor = plugin.get_extractor()
        import tree_sitter as ts
        import tree_sitter_javascript as tsjs

        lang = ts.Language(tsjs.language())
        parser = ts.Parser()
        parser.language = lang
        tree = parser.parse(code.encode())
        fns = extractor.extract_functions(tree, code)
        fibo = next((f for f in fns if f.name == "fibonacciSequence"), None)
        assert fibo is not None, "fibonacciSequence not found"
        assert len(fibo.parameters) == 1

    def test_full_plugin_processData_param_list(self):
        """End-to-end: processData(items, options = {}) yields exactly 2 params."""
        from tree_sitter_analyzer.languages.javascript_plugin.plugin import (
            JavaScriptPlugin,
        )

        code = "function processData(items, options = {}) { return items; }"
        plugin = JavaScriptPlugin()
        extractor = plugin.get_extractor()
        import tree_sitter as ts
        import tree_sitter_javascript as tsjs

        lang = ts.Language(tsjs.language())
        parser = ts.Parser()
        parser.language = lang
        tree = parser.parse(code.encode())
        fns = extractor.extract_functions(tree, code)
        pd = next((f for f in fns if f.name == "processData"), None)
        assert pd is not None, "processData not found"
        assert len(pd.parameters) == 2

    def test_full_plugin_processData_param_values(self):
        """End-to-end: processData params are ['items', 'options = {}']."""
        from tree_sitter_analyzer.languages.javascript_plugin.plugin import (
            JavaScriptPlugin,
        )

        code = "function processData(items, options = {}) { return items; }"
        plugin = JavaScriptPlugin()
        extractor = plugin.get_extractor()
        import tree_sitter as ts
        import tree_sitter_javascript as tsjs

        lang = ts.Language(tsjs.language())
        parser = ts.Parser()
        parser.language = lang
        tree = parser.parse(code.encode())
        fns = extractor.extract_functions(tree, code)
        pd = next((f for f in fns if f.name == "processData"), None)
        assert pd is not None
        assert pd.parameters == ["items", "options = {}"]


# ---------------------------------------------------------------------------
# Python — _extract_parameters_from_node_optimized in _core_extractor_mixin.py
# ---------------------------------------------------------------------------


class TestPythonTypedDefaultParameterExtraction:
    """Issue #533 (Python half): typed_default_parameter (name: type = default)
    was absent from _PARAMETER_NODE_TYPES in _signature_helpers.py, so any
    param with a type annotation AND a default (e.g. 'breed: str = "Mixed"')
    was silently dropped.

    Fix: add 'typed_default_parameter' to _PARAMETER_NODE_TYPES.
    Convention: emit full node text, e.g. 'breed: str = "Mixed"'.
    """

    def test_dog_init_three_params(self):
        """__init__(self, name: str, breed: str = 'Mixed') → 3 params."""
        from tree_sitter_analyzer.languages.python_plugin.plugin import PythonPlugin

        code = 'def __init__(self, name: str, breed: str = "Mixed"):\n    pass\n'
        plugin = PythonPlugin()
        extractor = plugin.get_extractor()
        import tree_sitter as ts
        import tree_sitter_python as tspy

        lang = ts.Language(tspy.language())
        parser = ts.Parser()
        parser.language = lang
        tree = parser.parse(code.encode())
        fns = extractor.extract_functions(tree, code)
        init = next((f for f in fns if f.name == "__init__"), None)
        assert init is not None, "__init__ not found"
        assert len(init.parameters) == 3

    def test_dog_init_param_values(self):
        """params are ['self', 'name: str', 'breed: str = \"Mixed\"']."""
        from tree_sitter_analyzer.languages.python_plugin.plugin import PythonPlugin

        code = 'def __init__(self, name: str, breed: str = "Mixed"):\n    pass\n'
        plugin = PythonPlugin()
        extractor = plugin.get_extractor()
        import tree_sitter as ts
        import tree_sitter_python as tspy

        lang = ts.Language(tspy.language())
        parser = ts.Parser()
        parser.language = lang
        tree = parser.parse(code.encode())
        fns = extractor.extract_functions(tree, code)
        init = next((f for f in fns if f.name == "__init__"), None)
        assert init is not None
        assert init.parameters == ["self", "name: str", 'breed: str = "Mixed"']

    def test_cat_init_bool_default(self):
        """__init__(self, name: str, indoor: bool = True) → 3 params."""
        from tree_sitter_analyzer.languages.python_plugin.plugin import PythonPlugin

        code = "def __init__(self, name: str, indoor: bool = True):\n    pass\n"
        plugin = PythonPlugin()
        extractor = plugin.get_extractor()
        import tree_sitter as ts
        import tree_sitter_python as tspy

        lang = ts.Language(tspy.language())
        parser = ts.Parser()
        parser.language = lang
        tree = parser.parse(code.encode())
        fns = extractor.extract_functions(tree, code)
        init = next((f for f in fns if f.name == "__init__"), None)
        assert init is not None, "__init__ not found"
        assert len(init.parameters) == 3

    def test_cat_init_param_values(self):
        """params are ['self', 'name: str', 'indoor: bool = True']."""
        from tree_sitter_analyzer.languages.python_plugin.plugin import PythonPlugin

        code = "def __init__(self, name: str, indoor: bool = True):\n    pass\n"
        plugin = PythonPlugin()
        extractor = plugin.get_extractor()
        import tree_sitter as ts
        import tree_sitter_python as tspy

        lang = ts.Language(tspy.language())
        parser = ts.Parser()
        parser.language = lang
        tree = parser.parse(code.encode())
        fns = extractor.extract_functions(tree, code)
        init = next((f for f in fns if f.name == "__init__"), None)
        assert init is not None
        assert init.parameters == ["self", "name: str", "indoor: bool = True"]

    def test_untyped_default_still_works(self):
        """Plain default_parameter (no type) still extracted: def f(x=5) → ['x=5']."""
        from tree_sitter_analyzer.languages.python_plugin.plugin import PythonPlugin

        code = "def f(x=5):\n    pass\n"
        plugin = PythonPlugin()
        extractor = plugin.get_extractor()
        import tree_sitter as ts
        import tree_sitter_python as tspy

        lang = ts.Language(tspy.language())
        parser = ts.Parser()
        parser.language = lang
        tree = parser.parse(code.encode())
        fns = extractor.extract_functions(tree, code)
        f = next((fn for fn in fns if fn.name == "f"), None)
        assert f is not None
        assert len(f.parameters) == 1

    def test_args_kwargs_unaffected(self):
        """*args/**kwargs are not broken by the fix."""
        from tree_sitter_analyzer.languages.python_plugin.plugin import PythonPlugin

        code = "def g(*args, **kwargs):\n    pass\n"
        plugin = PythonPlugin()
        extractor = plugin.get_extractor()
        import tree_sitter as ts
        import tree_sitter_python as tspy

        lang = ts.Language(tspy.language())
        parser = ts.Parser()
        parser.language = lang
        tree = parser.parse(code.encode())
        fns = extractor.extract_functions(tree, code)
        g = next((fn for fn in fns if fn.name == "g"), None)
        assert g is not None
        assert len(g.parameters) == 2


# ---------------------------------------------------------------------------
# Bash — structural n/a verdict
# ---------------------------------------------------------------------------


class TestBashParamStructuralNa:
    """Issue #533 (Bash): Bash grammar has no formal parameter nodes.
    Functions use positional args ($1/$2) at call time — there is nothing
    for the extractor to capture.  parameters=[] is the correct empty-list
    sentinel; this test pins that contract and documents why.

    The honest representation is an empty list (n/a), not an error.
    """

    def test_greet_params_empty(self):
        """greet() { echo $1 $2; } → parameters == [] (Bash has no formal params)."""
        from tree_sitter_analyzer.languages.bash_plugin import BashPlugin

        code = 'greet() {\n    echo "Hello $1 $2"\n}\n'
        plugin = BashPlugin()
        extractor = plugin.get_extractor()
        import tree_sitter as ts
        import tree_sitter_bash as tsbash

        lang = ts.Language(tsbash.language())
        parser = ts.Parser()
        parser.language = lang
        tree = parser.parse(code.encode())
        fns = extractor.extract_functions(tree, code)
        greet = next((f for f in fns if f.name == "greet"), None)
        assert greet is not None, "greet not found"
        assert greet.parameters == []

    def test_function_keyword_params_empty(self):
        """function process() { ... } → parameters == [] (same structural reason)."""
        from tree_sitter_analyzer.languages.bash_plugin import BashPlugin

        code = "function process() {\n    local x=$1\n}\n"
        plugin = BashPlugin()
        extractor = plugin.get_extractor()
        import tree_sitter as ts
        import tree_sitter_bash as tsbash

        lang = ts.Language(tsbash.language())
        parser = ts.Parser()
        parser.language = lang
        tree = parser.parse(code.encode())
        fns = extractor.extract_functions(tree, code)
        proc = next((f for f in fns if f.name == "process"), None)
        assert proc is not None, "process not found"
        assert proc.parameters == []


class TestStructureConversionOfDefaults:
    """Codex P2 on #581: get_method_parameters must not whitespace-split
    'limit = 10' into {'name': '10', 'type': 'limit ='}."""

    def test_js_default_param_parses(self):
        from tree_sitter_analyzer.mcp.tools.analyze_code_structure_helpers import (
            _parse_string_parameter,
        )

        assert _parse_string_parameter("limit = 10") == {
            "name": "limit",
            "type": "Any",
            "default": "10",
        }

    def test_python_typed_default_parses(self):
        from tree_sitter_analyzer.mcp.tools.analyze_code_structure_helpers import (
            _parse_string_parameter,
        )

        assert _parse_string_parameter('breed: str = "Mixed"') == {
            "name": "breed",
            "type": "str",
            "default": '"Mixed"',
        }

    def test_legacy_java_form_unchanged(self):
        from tree_sitter_analyzer.mcp.tools.analyze_code_structure_helpers import (
            _parse_string_parameter,
        )

        assert _parse_string_parameter("String name") == {
            "name": "name",
            "type": "String",
        }

    def test_get_method_parameters_string_form(self):
        from types import SimpleNamespace

        from tree_sitter_analyzer.mcp.tools.analyze_code_structure_helpers import (
            get_method_parameters,
        )

        method = SimpleNamespace(parameters=["limit = 10", "name: str", ""])
        assert get_method_parameters(method) == [
            {"name": "limit", "type": "Any", "default": "10"},
            {"name": "name", "type": "str"},
        ]

    def test_empty_and_blank_param_strings(self):
        from tree_sitter_analyzer.mcp.tools.analyze_code_structure_helpers import (
            _parse_string_parameter,
        )

        assert _parse_string_parameter("") is None
        assert _parse_string_parameter("   ") is None
