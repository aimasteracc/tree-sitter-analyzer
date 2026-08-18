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

import pytest

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

        # v24: CommonJS aliases and C++20 imports enter the projection.
        assert ast_cache._AST_CACHE_EXTRACTOR_VERSION == 24
        assert _ast_cache_indexer._AST_CACHE_EXTRACTOR_VERSION == 24


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

    @pytest.mark.parametrize("declaration", ["const", "let", "var"])
    def test_commonjs_loader_alias_call_is_projected(self, declaration: str) -> None:
        source = f"{declaration} load = require;\nload('./legacy');"
        symbols = {"symbols": _symbols_for(source, "typescript")}

        assert _extract_imports(symbols) == [{"text": "load('./legacy')", "line": 2}]

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
