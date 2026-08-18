"""Issue #614 — docstring/return_type/params serialized into symbols_json.

RFC-0016 prerequisite: the embedding input
``"{kind} {qualified_name}({params}) -> {return_type}\\n{docstring}"`` must be
constructible from the cache. The raw-AST walker (``_walk_for_symbols``) is
the path that feeds ``ast_index.symbols_json`` — it already carries ``params``
but dropped docstring/return_type.

The BM25-enrichment arm (docstring tokens in a low-weight FTS column) was
implemented, measured on the RFC-0016 pilot query set at weights 1.0 and
0.3, and REJECTED: no conceptual gap closed, control-query regressions at
both weights. Only the serialization half ships; pilot data on #517.
"""

from __future__ import annotations

import ast
from types import SimpleNamespace

import pytest

from tree_sitter_analyzer.cache import _symbol_walker as walker_module
from tree_sitter_analyzer.cache._symbol_walker import (
    _cpp_code_mask,
    _python_dynamic_loader_analysis,
    _python_module_control_bindings,
    _python_module_scope_statements,
    _SymbolWalker,
    _walk_for_symbols,
)
from tree_sitter_analyzer.cache.extraction import (
    _DOCSTRING_MAX_CHARS,
    _extract_imports,
)


def _symbols_for(source: str, lang: str) -> list[dict]:
    from tree_sitter_analyzer.cache.extraction import _extract_symbols
    from tree_sitter_analyzer.core.parser import Parser

    result = Parser().parse_code(source, lang)
    assert result.success and result.tree is not None
    return _extract_symbols(result.tree, source, lang)["symbols"]


def _extraction_for(source: str, lang: str) -> dict:
    from tree_sitter_analyzer.cache.extraction import _extract_symbols
    from tree_sitter_analyzer.core.parser import Parser

    result = Parser().parse_code(source, lang)
    assert result.success and result.tree is not None
    return _extract_symbols(result.tree, source, lang)


_PY_SRC = '''\
"""Module docstring — must NOT become a symbol docstring."""

CACHE_TTL = 60


def dispatch(request: dict, *, strict: bool = False) -> str:
    """Route an incoming request to the matching facade action."""
    return "ok"


def no_doc(x):
    return x


class Router:
    """Holds the routing table for tool dispatch."""

    def handle(self, name):
        """Resolve name and invoke the handler."""
        return name

    def _bare(self):
        pass
'''


class TestPythonDocstringSerialized:
    def _by_name(self) -> dict[str, dict]:
        return {s["name"]: s for s in _symbols_for(_PY_SRC, "python") if "name" in s}

    def test_function_docstring_serialized(self):
        syms = self._by_name()
        assert (
            syms["dispatch"]["docstring"]
            == "Route an incoming request to the matching facade action."
        )

    def test_method_docstring_serialized(self):
        syms = self._by_name()
        assert syms["handle"]["docstring"] == "Resolve name and invoke the handler."

    def test_class_docstring_serialized(self):
        syms = self._by_name()
        assert (
            syms["Router"]["docstring"] == "Holds the routing table for tool dispatch."
        )

    def test_absent_docstring_field_absent_not_empty_string(self):
        syms = self._by_name()
        assert "docstring" not in syms["no_doc"]
        assert "docstring" not in syms["_bare"]

    def test_docstring_capped_at_exactly_500_chars(self):
        assert _DOCSTRING_MAX_CHARS == 500
        long_doc = "x" * 600
        src = f'def f():\n    """{long_doc}"""\n'
        syms = {s["name"]: s for s in _symbols_for(src, "python") if "name" in s}
        assert len(syms["f"]["docstring"]) == 500
        assert syms["f"]["docstring"] == "x" * 500

    def test_whitespace_only_docstring_field_absent(self):
        src = 'def f():\n    """   """\n    return 1\n'
        syms = {s["name"]: s for s in _symbols_for(src, "python") if "name" in s}
        assert "docstring" not in syms["f"]

    def test_incomplete_function_without_body_is_safe(self):
        # tree-sitter error recovery: `def f():` with no body must not crash
        # the docstring helper and must not emit a docstring key.
        syms = {
            s["name"]: s for s in _symbols_for("def f():\n", "python") if "name" in s
        }
        assert "docstring" not in syms["f"]

    def test_multiline_docstring_stripped_and_preserved(self):
        src = 'def f():\n    """First line.\n\n    Body detail.\n    """\n'
        syms = {s["name"]: s for s in _symbols_for(src, "python") if "name" in s}
        assert syms["f"]["docstring"] == "First line.\n\n    Body detail."


class TestReturnTypeAndParamsSerialized:
    def _by_name(self) -> dict[str, dict]:
        return {s["name"]: s for s in _symbols_for(_PY_SRC, "python") if "name" in s}

    def test_return_type_serialized(self):
        syms = self._by_name()
        assert syms["dispatch"]["return_type"] == "str"

    def test_absent_return_type_field_absent(self):
        syms = self._by_name()
        assert "return_type" not in syms["no_doc"]

    def test_params_already_serialized(self):
        syms = self._by_name()
        assert syms["dispatch"]["params"] == "(request: dict, *, strict: bool = False)"

    def test_rust_return_type_serialized(self):
        src = "fn add(a: i32, b: i32) -> i32 { a + b }\n"
        syms = {s["name"]: s for s in _symbols_for(src, "rust") if "name" in s}
        assert syms["add"]["return_type"] == "i32"

    def test_non_python_function_has_no_docstring(self):
        src = 'function f() { return "doc-like string"; }\n'
        syms = {s["name"]: s for s in _symbols_for(src, "javascript") if "name" in s}
        assert "docstring" not in syms["f"]


class TestExtractorVersionBump:
    def test_extractor_version_matches_in_both_sites(self):
        # The two declarations must stay equal (they gate cache staleness).
        # v14: #1094 — function symbols carry the extractor's canonical
        # ``complexity``; the bump forces existing rows to re-index.
        from tree_sitter_analyzer import ast_cache
        from tree_sitter_analyzer.cache import indexer as _ast_cache_indexer

        # v26: parse-error state and current projection semantics are persisted.
        assert ast_cache._AST_CACHE_EXTRACTOR_VERSION == 26
        assert _ast_cache_indexer._AST_CACHE_EXTRACTOR_VERSION == 26


def test_python_module_control_bindings_cover_all_module_control_targets() -> None:
    """Control-flow rebinding is complete without descending into nested scopes."""
    module = ast.parse(
        """
async def nested_async():
    hidden_async = 1

class Nested:
    hidden_class = 1

lambda: hidden_lambda
[hidden_list for hidden_list in values]
{hidden_set for hidden_set in values}
{hidden_key: hidden_value for hidden_key, hidden_value in pairs}
(hidden_generator for hidden_generator in values)

async for async_item in items:
    pass

async with manager(), other() as async_bound:
    pass

with manager(), other() as sync_bound:
    pass

try:
    pass
except Exception:
    pass

match value:
    case [*rest]:
        pass
    case [*_]:
        pass
    case {"key": item, **remaining}:
        pass
    case {}:
        pass
    case _:
        pass
"""
    )

    assert _python_module_control_bindings(module.body) == {
        "async_item",
        "async_bound",
        "sync_bound",
        "rest",
        "item",
        "remaining",
    }


def test_python_star_imported_loader_fails_closed() -> None:
    loaders, complete = _python_dynamic_loader_analysis(
        'from importlib import *\nimport_module("pkg.util")\n'
    )

    assert "import_module" not in loaders
    assert complete is False


def test_commonjs_loader_stored_in_composite_fails_closed() -> None:
    extraction = _extraction_for(
        'const loaders = [require];\nloaders[0]("./util.js");\n',
        "javascript",
    )

    assert extraction["import_projection_complete"] is False


def test_commonjs_loader_passed_to_unknown_call_fails_closed() -> None:
    extraction = _extraction_for(
        "const loaders = wrap(require);\n",
        "javascript",
    )

    assert extraction["import_projection_complete"] is False


def test_commonjs_loader_call_result_is_not_loader_storage() -> None:
    extraction = _extraction_for(
        'const loaded = require("./util.js");\n',
        "javascript",
    )

    assert extraction["import_projection_complete"] is True


class TestJavaScriptModuleCallProjection:
    def test_module_variable_remains_a_module_symbol(self):
        symbols = _symbols_for("const visible = 1;\n", "typescript")

        assert [item["name"] for item in symbols if item["kind"] == "variable"] == [
            "visible"
        ]

    def test_enclosed_variable_is_not_a_module_symbol(self):
        symbols = _symbols_for("function f() { const hidden = 1; }\n", "typescript")

        assert [item["name"] for item in symbols if item["kind"] == "variable"] == []

    def test_commonjs_literal_is_projected_as_import(self):
        symbols = {"symbols": _symbols_for("require('./legacy');", "typescript")}

        assert _extract_imports(symbols) == [{"text": "require('./legacy')", "line": 1}]

    def test_dynamic_import_literal_is_projected_as_import(self):
        symbols = {"symbols": _symbols_for("import('./lazy');", "typescript")}

        assert _extract_imports(symbols) == [{"text": "import('./lazy')", "line": 1}]

    def test_dynamic_import_static_template_is_projected_as_import(self):
        # PR #1308 review: no-substitution templates are static module loads.
        symbols = {"symbols": _symbols_for("import(`./lazy`);", "typescript")}

        assert _extract_imports(symbols) == [{"text": "import(`./lazy`)", "line": 1}]

    def test_dynamic_import_interpolated_template_is_projected_for_fail_closed(self):
        symbols = {"symbols": _symbols_for("import(`./${name}`);", "typescript")}

        assert _extract_imports(symbols) == [{"text": "import(`./${name}`)", "line": 1}]

    def test_ordinary_call_is_not_projected_as_import(self):
        symbols = {"symbols": _symbols_for("load('./module');", "typescript")}

        assert _extract_imports(symbols) == []

    def test_nonliteral_require_is_projected_for_fail_closed(self):
        symbols = {"symbols": _symbols_for("require(moduleName);", "typescript")}

        assert _extract_imports(symbols) == [{"text": "require(moduleName)", "line": 1}]

    @pytest.mark.parametrize(
        "call", ["module.require('./legacy')", "module.require(moduleName)"]
    )
    def test_module_require_is_projected(self, call: str) -> None:
        symbols = {"symbols": _symbols_for(f"{call};", "typescript")}

        assert _extract_imports(symbols) == [{"text": call, "line": 1}]

    @pytest.mark.parametrize("quote", ["'", '"', "`"])
    def test_computed_module_require_is_projected(self, quote: str) -> None:
        call = f"module[{quote}require{quote}]('./legacy')"
        symbols = {"symbols": _symbols_for(f"{call};", "typescript")}

        assert _extract_imports(symbols) == [{"text": call, "line": 1}]

    def test_computed_commonjs_loader_alias_call_is_projected(self) -> None:
        source = "const load = module['require'];\nload('./legacy');"
        symbols = {"symbols": _symbols_for(source, "typescript")}

        assert _extract_imports(symbols) == [{"text": "load('./legacy')", "line": 2}]

    @pytest.mark.parametrize(
        "source",
        [
            "function run(require) { require('./util'); }",
            "const run = require => require('./util');",
            "function run() { const module = {}; module.require('./util'); }",
            "const { require } = runtime; require('./util');",
            "import require from './loader'; require('./util');",
            "import * as module from './loader'; module.require('./util');",
            "import { load as require } from './loader'; require('./util');",
            "try {} catch (require) { require('./util'); }",
            "function require() { require('./util'); }",
            "class module {}",
            "require = fake; require('./util');",
        ],
    )
    def test_shadowed_commonjs_loader_marks_projection_incomplete(
        self, source: str
    ) -> None:
        extraction = _extraction_for(source, "typescript")

        assert extraction["import_projection_complete"] is False

    def test_renamed_commonjs_import_does_not_shadow_loader(self) -> None:
        extraction = _extraction_for(
            "import { require as load, module as local } from './loader';",
            "typescript",
        )

        assert extraction["import_projection_complete"] is True

    @pytest.mark.parametrize("declaration", ["const", "let", "var"])
    def test_commonjs_loader_alias_call_is_projected(self, declaration: str) -> None:
        source = f"{declaration} load = require;\nload('./legacy');"
        symbols = {"symbols": _symbols_for(source, "typescript")}

        assert _extract_imports(symbols) == [{"text": "load('./legacy')", "line": 2}]

    def test_comment_text_does_not_create_commonjs_loader_alias(self) -> None:
        source = (
            "// const load = require\n"
            "function load(value) { return value; }\n"
            "load('./legacy');"
        )
        extraction = _extraction_for(source, "typescript")

        assert _extract_imports(extraction) == []
        assert extraction["import_projection_complete"] is True

    def test_commonjs_loader_rebound_by_loop_marks_projection_incomplete(self) -> None:
        extraction = _extraction_for(
            "for (require of loaders) { require('./legacy'); }", "typescript"
        )

        assert extraction["import_projection_complete"] is False

    def test_syntax_error_is_persisted_with_projection(self) -> None:
        from tree_sitter_analyzer.cache.extraction import _extract_symbols
        from tree_sitter_analyzer.core.parser import Parser

        source = "if ( {\nrequire('./legacy');"
        result = Parser().parse_code(source, "typescript")
        assert result.tree is not None

        extraction = _extract_symbols(result.tree, source, "typescript")

        assert extraction["syntax_error"] is True

    def test_incomplete_call_node_is_not_projected_as_import(self):
        from tree_sitter_analyzer.cache._symbol_walker import _SymbolWalker

        class _IncompleteCall:
            type = "call_expression"

            @staticmethod
            def child_by_field_name(name: str):
                return None

        walker = _SymbolWalker("", [], "typescript", None)

        assert walker._append_jsts_module_call(_IncompleteCall()) is False

    @pytest.mark.parametrize(
        "source",
        ["export { run } from './util';", "export * from './util';"],
    )
    def test_reexport_is_projected_as_import(self, source: str) -> None:
        symbols = {"symbols": _symbols_for(source, "typescript")}

        assert _extract_imports(symbols) == [{"text": source, "line": 1}]

    def test_local_export_is_not_projected_as_import(self) -> None:
        symbols = {"symbols": _symbols_for("export const value = 1;", "typescript")}

        assert _extract_imports(symbols) == []

    def test_triple_slash_path_reference_is_projected(self) -> None:
        source = '/// <reference path="./types.d.ts" />\nconst value = 1;'
        symbols = {"symbols": _symbols_for(source, "typescript")}

        assert _extract_imports(symbols) == [
            {"text": '/// <reference path="./types.d.ts" />', "line": 1}
        ]

    def test_triple_slash_types_reference_is_not_projected(self) -> None:
        source = '/// <reference types="node" />\nconst value = 1;'
        symbols = {"symbols": _symbols_for(source, "typescript")}

        assert _extract_imports(symbols) == []


class TestPythonDynamicImportProjection:
    @pytest.mark.parametrize(
        "source", ["importlib.import_module('pkg.util')", "__import__('pkg.util')"]
    )
    def test_literal_dynamic_import_is_projected(self, source: str) -> None:
        # PR #1308 review: literal Python loads participate in causal facts.
        symbols = {"symbols": _symbols_for(source, "python")}

        assert _extract_imports(symbols) == [{"text": source, "line": 1}]

    def test_nonliteral_dynamic_import_is_projected_for_fail_closed_read(self) -> None:
        symbols = {"symbols": _symbols_for("__import__(module_name)", "python")}

        assert _extract_imports(symbols) == [
            {"text": "__import__(module_name)", "line": 1}
        ]

    def test_builtins_qualified_dynamic_import_is_projected(self) -> None:
        source = "import builtins\nbuiltins.__import__('pkg.util')"
        symbols = {"symbols": _symbols_for(source, "python")}

        assert _extract_imports(symbols) == [
            {"text": "import builtins", "line": 1},
            {"text": "builtins.__import__('pkg.util')", "line": 2},
        ]

    def test_aliased_import_module_call_is_projected(self) -> None:
        source = "from importlib import import_module as load\nload('pkg.util')"
        symbols = {"symbols": _symbols_for(source, "python")}

        assert _extract_imports(symbols) == [
            {"text": "from importlib import import_module as load", "line": 1},
            {"text": "load('pkg.util')", "line": 2},
        ]

    def test_alias_survives_unrelated_syntax_error(self) -> None:
        source = "from importlib import import_module as load\nload('pkg.util')\nif ("
        symbols = {"symbols": _symbols_for(source, "python")}

        assert {item["text"] for item in _extract_imports(symbols)} == {
            "from importlib import import_module as load",
            "load('pkg.util')",
        }

    def test_alias_declared_after_deferred_call_is_projected(self) -> None:
        source = (
            "def load_plugin():\n"
            "    return load('pkg.util')\n"
            "from importlib import import_module as load\n"
        )
        symbols = {"symbols": _symbols_for(source, "python")}

        assert {item["text"] for item in _extract_imports(symbols)} == {
            "load('pkg.util')",
            "from importlib import import_module as load",
        }

    def test_assignment_alias_is_projected(self) -> None:
        source = (
            "import importlib\n"
            "loader = importlib.import_module\n"
            "plugin = loader('pkg.util')\n"
        )
        symbols = {"symbols": _symbols_for(source, "python")}

        assert {item["text"] for item in _extract_imports(symbols)} == {
            "import importlib",
            "loader = importlib.import_module",
            "loader('pkg.util')",
        }

    def test_assignment_alias_preserves_module_symbol(self) -> None:
        source = "import importlib\nLOADER = importlib.import_module\n"
        extraction = _extraction_for(source, "python")

        assert any(symbol.get("name") == "LOADER" for symbol in extraction["symbols"])
        assert {item["text"] for item in _extract_imports(extraction)} == {
            "import importlib",
            "LOADER = importlib.import_module",
        }

    def test_scope_shadowing_marks_import_projection_incomplete(self) -> None:
        source = (
            "import importlib\n"
            "loader = importlib.import_module\n"
            "def second(loader):\n"
            "    return loader('pkg.util')\n"
        )

        assert _extraction_for(source, "python")["import_projection_complete"] is False

    def test_partial_parse_with_deferred_alias_marks_projection_incomplete(
        self,
    ) -> None:
        source = (
            "def load_plugin():\n"
            "    return load('pkg.util')\n"
            "from importlib import import_module as load\n"
            "if (\n"
        )

        assert _extraction_for(source, "python")["import_projection_complete"] is False

    @pytest.mark.parametrize("missing_field", ["function", "arguments"])
    def test_incomplete_dynamic_import_node_is_not_projected(
        self, missing_field: str
    ) -> None:
        from types import SimpleNamespace

        from tree_sitter_analyzer.cache._symbol_walker import _SymbolWalker

        class _IncompleteCall:
            type = "call"

            @staticmethod
            def child_by_field_name(name: str):
                return None if name == missing_field else SimpleNamespace()

        walker = _SymbolWalker("", [], "python", None)

        assert walker._append_python_module_call(_IncompleteCall()) is False


class TestCIncludeProjection:
    def test_c_project_local_include_is_projected_as_import(self):
        symbols = {"symbols": _symbols_for('#include "util.h"\n', "c")}

        assert _extract_imports(symbols) == [{"text": '#include "util.h"\n', "line": 1}]

    def test_cpp_project_local_include_is_projected_as_import(self):
        symbols = {"symbols": _symbols_for('#include "util.hpp"\n', "cpp")}

        assert _extract_imports(symbols) == [
            {"text": '#include "util.hpp"\n', "line": 1}
        ]

    def test_macro_include_is_projected_for_fail_closed_read(self):
        symbols = {"symbols": _symbols_for('#define HDR "util.h"\n#include HDR\n', "c")}

        assert _extract_imports(symbols) == [{"text": "#include HDR\n", "line": 2}]

    def test_include_next_is_projected_for_fail_closed_read(self) -> None:
        symbols = {"symbols": _symbols_for('#include_next "util.h"\n', "cpp")}

        assert _extract_imports(symbols) == [
            {"text": '#include_next "util.h"\n', "line": 1}
        ]

    @pytest.mark.parametrize(
        "source",
        ['import "util.h";', "import project.core;", "export import project.core;"],
    )
    def test_cpp20_import_is_projected(self, source: str) -> None:
        symbols = {"symbols": _symbols_for(source, "cpp")}

        assert _extract_imports(symbols) == [{"text": source, "line": 1}]

    @pytest.mark.parametrize(
        "source",
        [
            '/*\nimport "fake.h";\n*/\n',
            'const char *text = R"tag(\nimport "fake.h";\n)tag";\n',
        ],
    )
    def test_cpp20_import_like_text_in_noncode_is_ignored(self, source: str) -> None:
        symbols = {"symbols": _symbols_for(source, "cpp")}

        assert _extract_imports(symbols) == []

    @pytest.mark.parametrize("line_ending", ["\n", "\r\n"])
    def test_cpp20_import_in_continued_line_comment_is_ignored(
        self, line_ending: str
    ) -> None:
        source = f'// disabled \\{line_ending}import "fake.h";{line_ending}int value;'
        symbols = {"symbols": _symbols_for(source, "cpp")}

        assert _extract_imports(symbols) == []


class TestJavaReflectionProjection:
    @pytest.mark.parametrize(
        "call",
        [
            'Class.forName("com.acme.Util")',
            'java.lang.Class.forName("com.acme.Util")',
            "Class.forName(className)",
        ],
    )
    def test_class_for_name_is_projected(self, call: str) -> None:
        source = f"class Main {{ void load() {{ {call}; }} }}"
        symbols = {"symbols": _symbols_for(source, "java")}

        assert _extract_imports(symbols) == [{"text": call, "line": 1}]

    def test_static_imported_for_name_is_projected(self) -> None:
        source = (
            "import static java.lang.Class.forName;\n"
            'class Main { void load() { forName("com.acme.Util"); } }'
        )
        extraction = _extraction_for(source, "java")

        assert {item["text"] for item in _extract_imports(extraction)} == {
            "import static java.lang.Class.forName;",
            'forName("com.acme.Util")',
        }

    @pytest.mark.parametrize(
        "call",
        ['forName("com.acme.Util")', 'loader.forName("com.acme.Util")'],
    )
    def test_unbound_reflective_for_name_is_not_projected(self, call: str) -> None:
        source = f"class Main {{ void load() {{ {call}; }} }}"
        extraction = _extraction_for(source, "java")

        assert _extract_imports(extraction) == []


class TestBashVariableAssignmentScope:
    """#949 Codex P2 — bash variable_assignment extraction edge cases."""

    def test_command_prefix_env_var_not_recorded(self):
        # ``FOO=bar make`` makes tree-sitter-bash emit ``FOO=bar`` as a
        # variable_assignment child of a ``command`` node — a transient env
        # override for that one command, not a script-level variable. It must
        # NOT be recorded as a symbol.
        syms = {
            s["name"] for s in _symbols_for("FOO=bar make\n", "bash") if "name" in s
        }
        assert "FOO" not in syms

    def test_standalone_assignment_recorded(self):
        # A real standalone assignment (parent is the program) IS recorded.
        syms = {s["name"] for s in _symbols_for("X=1\n", "bash") if "name" in s}
        assert "X" in syms

    def test_subscript_assignment_target_unwrapped_to_base(self):
        # ``arr[0]=x`` exposes the target as a subscript; unwrap to the base
        # variable so the symbol is ``arr``.
        syms = {s["name"] for s in _symbols_for("arr[0]=x\n", "bash") if "name" in s}
        assert "arr" in syms


class _FakeChild:
    """Minimal stand-in for a tree-sitter child node (only ``.type`` is read)."""

    def __init__(self, type_: str) -> None:
        self.type = type_


class _FakeSubscript:
    """Minimal stand-in for a ``subscript`` node exercising the fallback path.

    ``_bash_subscript_base`` first tries ``child_by_field_name("name")`` and,
    only when that returns ``None``, scans ``children`` for the first
    ``variable_name``/``word``. Real tree-sitter-bash always populates the
    ``name`` field, so this synthetic node is the only way to drive the
    documented defensive fallback (#949).
    """

    def __init__(self, named_base, children) -> None:
        self._named_base = named_base
        self.children = children

    def child_by_field_name(self, field: str):
        return self._named_base if field == "name" else None


class TestBashSubscriptBaseFallback:
    """#949 — ``_bash_subscript_base`` field-vs-fallback-vs-None branches."""

    def test_name_field_present_returns_field_node(self):
        # When the ``name`` field is set, return it directly (no child scan).
        from tree_sitter_analyzer.cache.extraction import _bash_subscript_base

        base = _FakeChild("variable_name")
        sub = _FakeSubscript(
            named_base=base,
            children=[_FakeChild("variable_name"), _FakeChild("[")],
        )
        assert _bash_subscript_base(sub) is base

    def test_no_name_field_falls_back_to_variable_name_child(self):
        # No ``name`` field: scan children, return the first ``variable_name``.
        from tree_sitter_analyzer.cache.extraction import _bash_subscript_base

        var_child = _FakeChild("variable_name")
        sub = _FakeSubscript(
            named_base=None,
            children=[_FakeChild("["), var_child, _FakeChild("]")],
        )
        assert _bash_subscript_base(sub) is var_child

    def test_no_name_field_falls_back_to_word_child(self):
        # No ``name`` field, no ``variable_name``: first ``word`` child wins.
        from tree_sitter_analyzer.cache.extraction import _bash_subscript_base

        word_child = _FakeChild("word")
        sub = _FakeSubscript(
            named_base=None,
            children=[_FakeChild("["), word_child],
        )
        assert _bash_subscript_base(sub) is word_child

    def test_no_base_anywhere_returns_none(self):
        # Neither a ``name`` field nor a ``variable_name``/``word`` child.
        from tree_sitter_analyzer.cache.extraction import _bash_subscript_base

        sub = _FakeSubscript(
            named_base=None,
            children=[_FakeChild("["), _FakeChild("number"), _FakeChild("]")],
        )
        assert _bash_subscript_base(sub) is None


class TestCodexP2sOn621:
    def test_concatenated_string_docstring_preserved(self):
        src = 'def f():\n    "first " "second"\n    return 1\n'
        syms = {x["name"]: x for x in _symbols_for(src, "python")}
        assert syms["f"]["docstring"] == "first second"

    def test_typescript_return_annotation_stripped(self):
        src = "function f(): string { return 'x'; }\n"
        syms = {x["name"]: x for x in _symbols_for(src, "typescript")}
        assert syms["f"]["return_type"] == "string"


@pytest.mark.parametrize(
    ("source", "visible"),
    [
        ("// comment", ""),
        ("// comment\nx", "\nx"),
        ('R"(unterminated', ""),
        ('R"12345678901234567(payload)', "R"),
        ('"a\\"b"x', "x"),
    ],
)
def test_cpp_code_mask_excludes_comments_and_literals(
    source: str, visible: str
) -> None:
    mask = _cpp_code_mask(source)

    assert (
        "".join(char for char, is_code in zip(source, mask, strict=True) if is_code)
        == visible
    )


def test_cpp_module_fallback_does_not_duplicate_walker_projection(monkeypatch) -> None:
    source = "import project.core;"

    def project_import(walker: _SymbolWalker, *_args: object) -> None:
        walker.symbols.append(
            {
                "kind": "import",
                "text": source,
                "line": 1,
                "language": "cpp",
            }
        )

    monkeypatch.setattr(_SymbolWalker, "walk", project_import)
    tree = SimpleNamespace(root_node=SimpleNamespace(children=[]))

    result = walker_module._extract_symbols(tree, source, "cpp")

    assert result["symbols"] == [
        {
            "kind": "import",
            "text": source,
            "line": 1,
            "language": "cpp",
        }
    ]


def test_python_loader_analysis_fails_closed_on_invalid_module() -> None:
    names, complete = _python_dynamic_loader_analysis("if (")

    assert names == frozenset(
        {"__import__", "builtins.__import__", "importlib.import_module"}
    )
    assert complete is False


def test_python_loader_analysis_tracks_module_alias_chains() -> None:
    source = """
import importlib as il
from importlib import import_module, invalidate_caches
loader: object = il.import_module
later = loader
annotation_only: object
"""

    names, complete = _python_dynamic_loader_analysis(source)

    assert names == frozenset(
        {
            "__import__",
            "builtins.__import__",
            "importlib.import_module",
            "il.import_module",
            "import_module",
            "loader",
            "later",
        }
    )
    assert complete is True


def test_python_loader_analysis_rejects_nested_bindings_and_aliases() -> None:
    source = """
import importlib

def load(positional, /, regular, *items, keyword, **options):
    nested = importlib.import_module
    holder.loader = importlib.import_module
    annotated: object = importlib.import_module
    import importlib as nested_importlib
    from importlib import import_module as nested_load
"""

    names, complete = _python_dynamic_loader_analysis(source)

    assert "importlib.import_module" in names
    assert complete is False


@pytest.mark.parametrize(
    "body",
    [
        "for loader in values:\n        loader('pkg.util')",
        "try:\n        pass\n    except Exception as loader:\n        loader('pkg.util')",
        "if (nested := importlib.import_module):\n        nested('pkg.util')",
    ],
)
def test_python_loader_analysis_rejects_additional_lexical_bindings(
    body: str,
) -> None:
    source = (
        "import importlib\n"
        "loader = importlib.import_module\n"
        "def load(values):\n"
        f"    {body}\n"
    )

    _names, complete = _python_dynamic_loader_analysis(source)

    assert complete is False


def test_python_loader_analysis_discovers_module_control_flow_alias() -> None:
    source = """
def load_plugin():
    return load("pkg.util")

if enabled:
    from importlib import import_module as load
"""

    names, complete = _python_dynamic_loader_analysis(source)

    assert "load" in names
    assert complete is True


@pytest.mark.parametrize(
    "control_flow",
    [
        "for load in loaders:\n    load('pkg.util')",
        "with manager() as load:\n    load('pkg.util')",
        "try:\n    pass\nexcept Exception as load:\n    load('pkg.util')",
        "if (load := fake):\n    load('pkg.util')",
        "match value:\n    case load:\n        load('pkg.util')",
    ],
)
def test_python_loader_analysis_rejects_module_control_flow_rebinding(
    control_flow: str,
) -> None:
    source = f"from importlib import import_module as load\n{control_flow}\n"

    _names, complete = _python_dynamic_loader_analysis(source)

    assert complete is False


def test_python_loader_analysis_rejects_module_rebinding() -> None:
    source = """
from importlib import import_module as load
load = fake
load("pkg.util")
"""

    names, complete = _python_dynamic_loader_analysis(source)

    assert "load" in names
    assert complete is False


@pytest.mark.parametrize(
    "source",
    [
        "import importlib\nimportlib.import_module = fake\n"
        "importlib.import_module('pkg.util')\n",
        "import builtins as runtime\nruntime.__import__ = fake\n"
        "runtime.__import__('pkg.util')\n",
        "import importlib\nimportlib.import_module, other = fake, value\n"
        "importlib.import_module('pkg.util')\n",
        "import builtins as runtime\n[other, [runtime.__import__]] = values\n"
        "runtime.__import__('pkg.util')\n",
        "import builtins as runtime\nother, *runtime.__import__ = values\n"
        "runtime.__import__('pkg.util')\n",
        "import importlib\nload, other = importlib.import_module, value\n"
        "load('pkg.util')\n",
        "import importlib\npair = (importlib.import_module, value)\n"
        "load, other = pair\nload('pkg.util')\n",
        "import importlib\npair = {'load': importlib.import_module}\n"
        "load = pair['load']\nload('pkg.util')\n",
        "import importlib\npair = wrap(importlib.import_module)\n"
        "load = pair[0]\nload('pkg.util')\n",
        "import importlib\nholder.load = importlib.import_module\n"
        "holder.load('pkg.util')\n",
        "import importlib\nregistry['load'] = importlib.import_module\n"
        "registry['load']('pkg.util')\n",
    ],
)
def test_python_loader_analysis_rejects_qualified_loader_rebinding(
    source: str,
) -> None:
    names, complete = _python_dynamic_loader_analysis(source)

    assert any(name.endswith((".import_module", ".__import__")) for name in names)
    assert complete is False


@pytest.mark.parametrize(
    "source",
    [
        "import importlib\nloaded = importlib.import_module('pkg.util')\n",
        "import importlib\ndef load():\n"
        "    loaded = importlib.import_module('pkg.util')\n"
        "    return loaded\n",
    ],
)
def test_python_loader_analysis_accepts_assigned_loader_call_result(
    source: str,
) -> None:
    names, complete = _python_dynamic_loader_analysis(source)

    assert "importlib.import_module" in names
    assert complete is True


@pytest.mark.parametrize(
    "source",
    [
        "import importlib\ndef load(callback=importlib.import_module):\n"
        "    return callback('pkg.util')\n",
        "import importlib\ndef load(value):\n"
        "    pair = (importlib.import_module, value)\n"
        "    callback, other = pair\n"
        "    return callback('pkg.util')\n",
        "import importlib\nload = lambda callback=importlib.import_module: "
        "callback('pkg.util')\n",
    ],
)
def test_python_loader_analysis_rejects_nested_stored_loader(source: str) -> None:
    _names, complete = _python_dynamic_loader_analysis(source)

    assert complete is False


@pytest.mark.parametrize(
    "source",
    [
        "import importlib\ndef holder(value: importlib.import_module):\n    pass\n",
        "import importlib\ndef holder(*values: importlib.import_module):\n    pass\n",
        "import importlib\ndef holder(**values: importlib.import_module):\n    pass\n",
        "import importlib\ndef holder() -> importlib.import_module:\n    pass\n",
        "import importlib\nholder: importlib.import_module\n",
        "import importlib\ndef outer():\n    holder: importlib.import_module\n",
    ],
)
def test_python_loader_analysis_rejects_annotation_storage(source: str) -> None:
    _names, complete = _python_dynamic_loader_analysis(source)

    assert complete is False


@pytest.mark.parametrize(
    "rebind",
    [
        "from helpers import load",
        "def load():\n    pass",
        "class load:\n    pass",
        "del load",
    ],
)
def test_python_loader_analysis_rejects_nonassignment_rebinding(
    rebind: str,
) -> None:
    source = (
        f"from importlib import import_module as load\n{rebind}\nload('pkg.util')\n"
    )

    names, complete = _python_dynamic_loader_analysis(source)

    assert "load" in names
    assert complete is False


def test_python_loader_analysis_tracks_builtins_alias() -> None:
    names, complete = _python_dynamic_loader_analysis(
        "import builtins as runtime\nruntime.__import__('pkg.util')\n"
    )

    assert "runtime.__import__" in names
    assert complete is True


@pytest.mark.parametrize(
    "expression",
    [
        "callback = lambda load: load('pkg.util')",
        "results = [load('pkg.util') for load in loaders]",
    ],
)
def test_python_loader_analysis_rejects_expression_scope_shadowing(
    expression: str,
) -> None:
    source = f"from importlib import import_module as load\n{expression}\n"

    names, complete = _python_dynamic_loader_analysis(source)

    assert "load" in names
    assert complete is False


def test_module_scope_statement_walk_skips_nested_function_body() -> None:
    module = ast.parse("if enabled:\n    def nested():\n        import importlib\n")

    statements = _python_module_scope_statements(module)

    assert [type(statement) for statement in statements] == [ast.If, ast.FunctionDef]


@pytest.mark.parametrize(
    ("language", "node_type", "enclosed"),
    [
        ("python", "class_definition", False),
        ("scala", "identifier", False),
        ("scala", "object_definition", True),
    ],
)
def test_scala_projection_rejects_non_top_level_class_like_nodes(
    language: str, node_type: str, enclosed: bool
) -> None:
    walker = _SymbolWalker("", [], language, None)
    node = SimpleNamespace(type=node_type)

    assert walker._append_scala(node, enclosed) is False


def test_scala_projection_handles_empty_and_present_symbols(monkeypatch) -> None:
    walker = _SymbolWalker("", [], "scala", None)
    node = SimpleNamespace(type="object_definition")
    monkeypatch.setattr(walker_module, "_scala_symbol_from_node", lambda *_: None)

    assert walker._append_scala(node, False) is True
    assert walker.symbols == []

    expected = {"kind": "class", "name": "User"}
    monkeypatch.setattr(walker_module, "_scala_symbol_from_node", lambda *_: expected)
    assert walker._append_scala(node, False) is True
    assert walker.symbols == [expected]


def test_collect_node_stops_after_scala_projection(monkeypatch) -> None:
    expected = {"kind": "object", "name": "Registry"}
    monkeypatch.setattr(walker_module, "_scala_symbol_from_node", lambda *_: expected)
    node = SimpleNamespace(
        type="object_definition", child_by_field_name=lambda _name: None
    )
    walker = _SymbolWalker("", [], "scala", None)

    walker._collect_node(node, 0, False)

    assert walker.symbols == [expected]


class _TextNode:
    def __init__(self, node_type: str, source: str) -> None:
        self.type = node_type
        self.start_byte = 0
        self.end_byte = len(source.encode())
        self.start_point = (0, 0)
        self.end_point = (0, len(source))


def test_python_loader_assignment_rejects_invalid_syntax() -> None:
    source = "if ("
    walker = _SymbolWalker(source, [], "python", None)

    assert (
        walker._append_python_loader_assignment(_TextNode("assignment", source))
        is False
    )


def test_python_loader_assignment_rejects_multiple_statements() -> None:
    source = "first = importlib.import_module\nsecond = first"
    walker = _SymbolWalker(source, [], "python", None)

    assert (
        walker._append_python_loader_assignment(_TextNode("assignment", source))
        is False
    )


def test_python_loader_assignment_accepts_annotated_alias() -> None:
    source = "loader: object = importlib.import_module"
    walker = _SymbolWalker(source, [], "python", None)

    assert (
        walker._append_python_loader_assignment(
            _TextNode("annotated_assignment", source)
        )
        is True
    )


def test_python_loader_assignment_rejects_annotation_without_value() -> None:
    source = "loader: object"
    walker = _SymbolWalker(source, [], "python", None)

    assert (
        walker._append_python_loader_assignment(
            _TextNode("annotated_assignment", source)
        )
        is False
    )


class _FieldNode(_TextNode):
    def __init__(
        self, node_type: str, source: str, fields: dict[str, _TextNode]
    ) -> None:
        super().__init__(node_type, source)
        self.fields = fields

    def child_by_field_name(self, name: str):
        return self.fields.get(name)


def test_java_reflection_rejects_missing_name() -> None:
    source = "forName()"
    node = _FieldNode(
        "method_invocation", source, {"arguments": _TextNode("arguments", source)}
    )

    assert (
        _SymbolWalker(source, [], "java", None)._append_java_reflective_load(node)
        is False
    )


def test_java_reflection_rejects_other_method_name() -> None:
    source = "load()"
    node = _FieldNode(
        "method_invocation",
        source,
        {
            "name": _TextNode("identifier", "load"),
            "arguments": _TextNode("arguments", source),
        },
    )

    assert (
        _SymbolWalker(source, [], "java", None)._append_java_reflective_load(node)
        is False
    )


def test_include_next_projection_ignores_other_preprocessor_calls() -> None:
    source = "#pragma once"
    node = _TextNode("preproc_call", source)

    assert _SymbolWalker(source, [], "cpp", None)._append_include_next(node) is False


def test_historical_walk_wrapper_delegates_to_walker() -> None:
    node = SimpleNamespace(
        type="comment", children=[], child_by_field_name=lambda _name: None
    )
    symbols: list[dict] = []

    _walk_for_symbols(node, "", symbols, "unknown")

    assert symbols == []


def test_symbol_walk_records_depth_truncation() -> None:
    truncated = [False]
    walker = _SymbolWalker("", [], "unknown", truncated)

    walker.walk(object(), depth=10_000)

    assert truncated == [True]


def test_symbol_walk_without_truncation_sink_stops_cleanly() -> None:
    walker = _SymbolWalker("", [], "unknown", None)

    walker.walk(object(), depth=10_000)

    assert walker.symbols == []


def test_php_constant_projection_appends_extracted_constants(monkeypatch) -> None:
    expected = {"kind": "constant", "name": "LIMIT"}
    monkeypatch.setattr(walker_module, "_php_constants", lambda *_: [expected])
    node = SimpleNamespace(type="const_declaration")
    walker = _SymbolWalker("", [], "php", None)

    walker._append_constant(node, None, False)

    assert walker.symbols == [expected]


def test_go_constant_projection_appends_extracted_constants(monkeypatch) -> None:
    expected = {"kind": "constant", "name": "Limit"}
    monkeypatch.setattr(walker_module, "_go_package_constants", lambda *_: [expected])
    node = SimpleNamespace(type="const_declaration")
    walker = _SymbolWalker("", [], "go", None)

    walker._append_constant(node, None, False)

    assert walker.symbols == [expected]


def test_rust_constant_projection_appends_named_constant() -> None:
    source = "LIMIT"
    name = _TextNode("identifier", source)
    node = SimpleNamespace(
        type="const_item", start_point=(0, 0), end_point=(0, len(source))
    )
    walker = _SymbolWalker(source, [], "rust", None)

    walker._append_constant(node, name, False)

    assert walker.symbols == [
        {
            "kind": "constant",
            "name": "LIMIT",
            "line": 1,
            "end_line": 1,
            "language": "rust",
        }
    ]


def test_class_projection_covers_empty_fallback_and_parents(monkeypatch) -> None:
    empty_name = SimpleNamespace(type="identifier", start_byte=0, end_byte=0)
    node = SimpleNamespace(
        type="class_definition",
        children=[SimpleNamespace(type="comment"), empty_name],
        start_point=(0, 0),
        end_point=(0, 0),
    )
    walker = _SymbolWalker("", [], "python", None)

    assert walker._class_name_node(node, object()) is not None
    assert walker._class_name_node(node, None) is empty_name
    assert (
        walker._class_name_node(
            SimpleNamespace(children=[SimpleNamespace(type="comment")]), None
        )
        is None
    )
    walker._append_class(node, None)
    assert walker.symbols == []

    monkeypatch.setattr(walker_module, "_node_text", lambda *_: "Child")
    monkeypatch.setattr(walker_module, "_extract_parent_classes", lambda *_: ["Base"])
    monkeypatch.setattr(walker_module, "_python_docstring", lambda *_: None)
    walker._append_class(node, None)
    assert walker.symbols == [
        {
            "kind": "class",
            "name": "Child",
            "line": 1,
            "end_line": 1,
            "language": "python",
            "parents": ["Base"],
        }
    ]
