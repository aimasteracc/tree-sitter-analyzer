"""Tests for import_extractors.py — multi-language import extraction."""


from tree_sitter_analyzer.import_extractors import (
    _extract_cpp_imports,
    _extract_csharp_imports,
    _extract_go_imports,
    _extract_java_imports,
    _extract_js_imports,
    _extract_kotlin_imports,
    _extract_php_imports,
    _extract_python_imports,
    _extract_ruby_imports,
    _extract_rust_imports,
    _extract_swift_imports,
    _node_text,
    _parse_rust_use_path,
    extract_python_import_from,
    extract_python_import_simple,
    walk_imports,
)

# ---------------------------------------------------------------------------
# Helpers — lightweight mock node
# ---------------------------------------------------------------------------


class MockNode:
    def __init__(self, node_type: str, text: str = "", children: list | None = None, **fields):
        self._type = node_type
        self._text = text
        self._children = children or []
        self._fields = fields
        self.start_byte = 0
        self.end_byte = len(text.encode("utf-8")) if text else 0

    @property
    def type(self):
        return self._type

    @property
    def children(self):
        return self._children

    def child_by_field_name(self, name: str):
        return self._fields.get(name)

    def __repr__(self):
        return f"MockNode({self._type!r}, {self._text!r})"


# ---------------------------------------------------------------------------
# _node_text
# ---------------------------------------------------------------------------


class TestNodeText:
    def test_extracts_text_by_byte_range(self):
        source = "hello world"
        node = MockNode("id", "hello world")
        node.start_byte = 0
        node.end_byte = 5
        assert _node_text(node, source) == "hello"

    def test_returns_empty_for_mismatched_range(self):
        node = MockNode("id", "")
        node.start_byte = 100
        node.end_byte = 200
        assert _node_text(node, "short") == ""

    def test_returns_empty_for_none_range(self):
        node = MockNode("id", "x")
        node.start_byte = None
        node.end_byte = None
        assert _node_text(node, "source") == ""


# ---------------------------------------------------------------------------
# _parse_rust_use_path
# ---------------------------------------------------------------------------


class TestParseRustUsePath:
    def test_simple_use(self):
        assert _parse_rust_use_path("use my_crate::module;") == "my_crate::module"

    def test_crate_prefixed(self):
        assert _parse_rust_use_path("use crate::foo::bar;") == "crate::foo::bar"

    def test_super_prefixed(self):
        assert _parse_rust_use_path("use super::sibling;") == "super::sibling"

    def test_group_import_strips_braces(self):
        assert _parse_rust_use_path("use my_mod::{Foo, Bar};") == "my_mod"

    def test_std_crate_still_parsed(self):
        result = _parse_rust_use_path("use std::collections;")
        assert result == "std::collections"

    def test_empty_returns_none(self):
        assert _parse_rust_use_path("") is None
        assert _parse_rust_use_path("use ;") is None


# ---------------------------------------------------------------------------
# Python import extraction
# ---------------------------------------------------------------------------


class TestExtractPythonImportSimple:
    def test_skips_stdlib(self):
        child = MockNode("dotted_name", "os")
        child.start_byte = 7
        child.end_byte = 9
        node = MockNode(
            "import_statement",
            "import os",
            children=[child],
        )
        imports: list[dict] = []
        extract_python_import_simple(node, "import os", imports)
        assert imports == []

    def test_extracts_third_party(self):
        node = MockNode(
            "import_statement",
            "import requests",
            children=[MockNode("dotted_name", "requests")],
        )
        node.children[0].start_byte = 7
        node.children[0].end_byte = 15
        imports: list[dict] = []
        extract_python_import_simple(node, "import requests", imports)
        assert len(imports) == 1
        assert imports[0]["module_name"] == "requests"
        assert imports[0]["is_relative"] is False


class TestExtractPythonImportFrom:
    def test_skips_stdlib_from_import(self):
        node = MockNode(
            "import_from_statement",
            "from os.path import join",
            children=[MockNode("dotted_name", "os.path")],
        )
        node.children[0].start_byte = 5
        node.children[0].end_byte = 12
        imports: list[dict] = []
        extract_python_import_from(node, "from os.path import join", imports)
        assert imports == []

    def test_no_module_name_returns_early(self):
        node = MockNode("import_from_statement", "from import foo", children=[])
        imports: list[dict] = []
        extract_python_import_from(node, "from import foo", imports)
        assert imports == []


# ---------------------------------------------------------------------------
# _extract_python_imports dispatch
# ---------------------------------------------------------------------------


class TestExtractPythonImports:
    def test_import_statement_dispatches(self):
        node = MockNode(
            "import_statement",
            "import myapp",
            children=[MockNode("dotted_name", "myapp")],
        )
        node.children[0].start_byte = 7
        node.children[0].end_byte = 12
        imports: list[dict] = []
        _extract_python_imports(node, "import myapp", imports)
        assert len(imports) == 1

    def test_non_import_node_skipped(self):
        node = MockNode("expression_statement", "x = 1")
        imports: list[dict] = []
        _extract_python_imports(node, "x = 1", imports)
        assert imports == []


# ---------------------------------------------------------------------------
# _extract_js_imports
# ---------------------------------------------------------------------------


class TestExtractJsImports:
    def test_import_statement_extracts_module(self):
        string_child = MockNode("string", "'./bar'")
        string_child.start_byte = 20
        string_child.end_byte = 27
        node = MockNode(
            "import_statement",
            "import { foo } from './bar'",
            children=[string_child],
        )
        imports: list[dict] = []
        _extract_js_imports(node, "import { foo } from './bar'", imports)
        assert any(i["is_relative"] is True for i in imports)

    def test_require_call_extracts(self):
        string_node = MockNode("string", "'./utils'")
        string_node.start_byte = 8
        string_node.end_byte = 17
        args_node = MockNode("arguments", "", children=[string_node])
        func_node = MockNode("identifier", "require")
        func_node.start_byte = 0
        func_node.end_byte = 7
        node = MockNode(
            "call_expression",
            "require('./utils')",
            children=[],
        )
        node._fields = {"function": func_node, "arguments": args_node}
        imports: list[dict] = []
        _extract_js_imports(node, "require('./utils')", imports)
        assert any(i["is_relative"] is True for i in imports)


# ---------------------------------------------------------------------------
# _extract_go_imports
# ---------------------------------------------------------------------------


class TestExtractGoImports:
    def test_skips_stdlib(self):
        str_child = MockNode(
            "interpreted_string_literal", '"fmt"'
        )
        str_child.start_byte = 7
        str_child.end_byte = 12
        spec = MockNode(
            "import_spec",
            'import "fmt"',
            children=[str_child],
        )
        node = MockNode("import_declaration", 'import "fmt"', children=[spec])
        imports: list[dict] = []
        _extract_go_imports(node, 'import "fmt"', imports)
        assert imports == []

    def test_extracts_third_party(self):
        source = 'import "github.com/gin-gonic/gin"'
        str_child = MockNode("interpreted_string_literal", '"github.com/gin-gonic/gin"')
        str_child.start_byte = 7
        str_child.end_byte = len(source)
        spec = MockNode(
            "import_spec",
            source,
            children=[str_child],
        )
        node = MockNode(
            "import_declaration",
            source,
            children=[spec],
        )
        imports: list[dict] = []
        _extract_go_imports(node, source, imports)
        assert len(imports) == 1
        assert imports[0]["module_name"] == "github.com/gin-gonic/gin"

    def test_non_import_declaration_skipped(self):
        node = MockNode("function_declaration", "func main() {}")
        imports: list[dict] = []
        _extract_go_imports(node, "func main() {}", imports)
        assert imports == []


# ---------------------------------------------------------------------------
# _extract_rust_imports
# ---------------------------------------------------------------------------


class TestExtractRustImports:
    def test_skips_std_crate(self):
        node = MockNode("use_declaration", "use std::io;")
        node.start_byte = 0
        node.end_byte = 12
        imports: list[dict] = []
        _extract_rust_imports(node, "use std::io;", imports)
        assert imports == []

    def test_extracts_crate_local(self):
        node = MockNode("use_declaration", "use crate::models::User;")
        node.start_byte = 0
        node.end_byte = 24
        imports: list[dict] = []
        _extract_rust_imports(node, "use crate::models::User;", imports)
        assert len(imports) == 1
        assert imports[0]["is_relative"] is True

    def test_non_use_declaration_skipped(self):
        node = MockNode("function_item", "fn main() {}")
        imports: list[dict] = []
        _extract_rust_imports(node, "fn main() {}", imports)
        assert imports == []


# ---------------------------------------------------------------------------
# _extract_cpp_imports
# ---------------------------------------------------------------------------


class TestExtractCppImports:
    def test_local_include(self):
        str_child = MockNode("string_literal", '"myheader.h"')
        str_child.start_byte = 9
        str_child.end_byte = 21
        node = MockNode(
            "preproc_include",
            '#include "myheader.h"',
            children=[str_child],
        )
        imports: list[dict] = []
        _extract_cpp_imports(node, '#include "myheader.h"', imports)
        assert len(imports) == 1
        assert imports[0]["is_relative"] is True
        assert imports[0]["module_name"] == "myheader.h"

    def test_system_include(self):
        sys_child = MockNode("system_lib_string", "<vector>")
        sys_child.start_byte = 9
        sys_child.end_byte = 17
        node = MockNode(
            "preproc_include",
            "#include <vector>",
            children=[sys_child],
        )
        imports: list[dict] = []
        _extract_cpp_imports(node, "#include <vector>", imports)
        assert len(imports) == 1
        assert imports[0]["is_relative"] is False

    def test_non_include_skipped(self):
        node = MockNode("function_definition", "int main() {}")
        imports: list[dict] = []
        _extract_cpp_imports(node, "int main() {}", imports)
        assert imports == []


# ---------------------------------------------------------------------------
# _extract_java_imports
# ---------------------------------------------------------------------------


class TestExtractJavaImports:
    def test_skips_java_stdlib(self):
        node = MockNode("import_declaration", "import java.util.List;")
        node.start_byte = 0
        node.end_byte = 22
        imports: list[dict] = []
        _extract_java_imports(node, "import java.util.List;", imports)
        assert imports == []

    def test_extracts_third_party(self):
        node = MockNode("import_declaration", "import com.example.MyClass;")
        node.start_byte = 0
        node.end_byte = 27
        imports: list[dict] = []
        _extract_java_imports(node, "import com.example.MyClass;", imports)
        assert len(imports) == 1
        assert "com/example/MyClass.java" in imports[0]["resolved_path"]

    def test_static_import(self):
        node = MockNode("import_declaration", "import static org.example.Util.method;")
        node.start_byte = 0
        node.end_byte = 38
        imports: list[dict] = []
        _extract_java_imports(node, "import static org.example.Util.method;", imports)
        assert len(imports) == 1

    def test_wildcard_import(self):
        node = MockNode("import_declaration", "import com.example.*;")
        node.start_byte = 0
        node.end_byte = len(b"import com.example.*;")
        imports: list[dict] = []
        _extract_java_imports(node, "import com.example.*;", imports)
        assert len(imports) == 1
        assert ".*" not in imports[0]["module_name"]


# ---------------------------------------------------------------------------
# walk_imports top-level dispatch
# ---------------------------------------------------------------------------


class TestWalkImports:
    def test_unsupported_language_no_error(self):
        node = MockNode("module", "", children=[])
        imports: list[dict] = []
        walk_imports(node, "", "perl", imports)
        assert imports == []

    def test_walks_children_recursively(self):
        inner = MockNode("import_statement", "import app", children=[])
        outer = MockNode("module", "", children=[inner])
        imports: list[dict] = []
        walk_imports(outer, "import app", "python", imports)

    def test_csharp_dispatch(self):
        inner = MockNode("using_directive", "using Foo;", children=[MockNode("identifier", "Foo")])
        inner.children[0].start_byte = 6
        inner.children[0].end_byte = 9
        outer = MockNode("compilation_unit", "", children=[inner])
        imports: list[dict] = []
        walk_imports(outer, "using Foo;", "csharp", imports)
        assert len(imports) == 1

    def test_kotlin_dispatch(self):
        inner = MockNode("import", "import com.foo.Bar", children=[])
        inner.start_byte = 0
        inner.end_byte = 18
        outer = MockNode("source_file", "", children=[inner])
        imports: list[dict] = []
        walk_imports(outer, "import com.foo.Bar", "kotlin", imports)
        assert len(imports) == 1

    def test_swift_dispatch(self):
        inner = MockNode("import_declaration", "import MyKit", children=[MockNode("identifier", "MyKit")])
        inner.children[0].start_byte = 7
        inner.children[0].end_byte = 12
        outer = MockNode("source_file", "", children=[inner])
        imports: list[dict] = []
        walk_imports(outer, "import MyKit", "swift", imports)
        assert len(imports) == 1

    def test_ruby_dispatch(self):
        string_node = MockNode("string", "'my_lib'")
        string_node.start_byte = 8
        string_node.end_byte = 16
        args_node = MockNode("argument_list", "", children=[string_node])
        func_node = MockNode("identifier", "require")
        func_node.start_byte = 0
        func_node.end_byte = 7
        inner = MockNode("call", "require 'my_lib'", children=[])
        inner._fields = {"function": func_node, "arguments": args_node}
        outer = MockNode("program", "", children=[inner])
        imports: list[dict] = []
        walk_imports(outer, "require 'my_lib'", "ruby", imports)
        assert len(imports) == 1

    def test_php_dispatch(self):
        inner = MockNode("namespace_use_declaration", "use App\\Foo;", children=[])
        inner.start_byte = 0
        inner.end_byte = 12
        outer = MockNode("program", "", children=[inner])
        imports: list[dict] = []
        walk_imports(outer, "use App\\Foo;", "php", imports)
        assert len(imports) == 1


# ---------------------------------------------------------------------------
# _extract_csharp_imports
# ---------------------------------------------------------------------------


class TestExtractCSharpImports:
    def test_skips_stdlib_system(self):
        node = MockNode("using_directive", "using System;", children=[MockNode("identifier", "System")])
        node.children[0].start_byte = 6
        node.children[0].end_byte = 12
        imports: list[dict] = []
        _extract_csharp_imports(node, "using System;", imports)
        assert imports == []

    def test_extracts_third_party(self):
        ident = MockNode("identifier", "MyApp")
        ident.start_byte = 6
        ident.end_byte = 11
        ident2 = MockNode("identifier", "Services")
        ident2.start_byte = 12
        ident2.end_byte = 20
        qn = MockNode("qualified_name", "MyApp.Services", children=[ident, ident2])
        node = MockNode("using_directive", "using MyApp.Services;", children=[qn])
        imports: list[dict] = []
        _extract_csharp_imports(node, "using MyApp.Services;", imports)
        assert len(imports) == 1
        assert imports[0]["module_name"] == "MyApp.Services"
        assert imports[0]["language"] == "csharp"

    def test_non_using_directive_skipped(self):
        node = MockNode("namespace_declaration", "namespace Foo {}", children=[])
        imports: list[dict] = []
        _extract_csharp_imports(node, "namespace Foo {}", imports)
        assert imports == []


# ---------------------------------------------------------------------------
# _extract_kotlin_imports
# ---------------------------------------------------------------------------


class TestExtractKotlinImports:
    def test_skips_kotlin_stdlib(self):
        node = MockNode("import", "import kotlin.collections.List")
        node.start_byte = 0
        node.end_byte = 29
        imports: list[dict] = []
        _extract_kotlin_imports(node, "import kotlin.collections.List", imports)
        assert imports == []

    def test_extracts_third_party(self):
        node = MockNode("import", "import com.example.app.Data")
        node.start_byte = 0
        node.end_byte = 27
        imports: list[dict] = []
        _extract_kotlin_imports(node, "import com.example.app.Data", imports)
        assert len(imports) == 1
        assert imports[0]["module_name"] == "com.example.app.Data"
        assert imports[0]["language"] == "kotlin"

    def test_wildcard_import(self):
        node = MockNode("import", "import com.example.utils.*")
        node.start_byte = 0
        node.end_byte = 26
        imports: list[dict] = []
        _extract_kotlin_imports(node, "import com.example.utils.*", imports)
        assert len(imports) == 1
        assert ".*" not in imports[0]["module_name"]

    def test_non_import_skipped(self):
        node = MockNode("class_declaration", "class Foo")
        imports: list[dict] = []
        _extract_kotlin_imports(node, "class Foo", imports)
        assert imports == []


# ---------------------------------------------------------------------------
# _extract_swift_imports
# ---------------------------------------------------------------------------


class TestExtractSwiftImports:
    def test_skips_stdlib_foundation(self):
        ident = MockNode("identifier", "Foundation")
        ident.start_byte = 7
        ident.end_byte = 17
        node = MockNode("import_declaration", "import Foundation", children=[ident])
        imports: list[dict] = []
        _extract_swift_imports(node, "import Foundation", imports)
        assert imports == []

    def test_extracts_custom_framework(self):
        ident = MockNode("identifier", "MyFramework")
        ident.start_byte = 7
        ident.end_byte = 18
        node = MockNode("import_declaration", "import MyFramework", children=[ident])
        imports: list[dict] = []
        _extract_swift_imports(node, "import MyFramework", imports)
        assert len(imports) == 1
        assert imports[0]["module_name"] == "MyFramework"
        assert imports[0]["language"] == "swift"

    def test_non_import_skipped(self):
        node = MockNode("class_declaration", "class Foo {}")
        imports: list[dict] = []
        _extract_swift_imports(node, "class Foo {}", imports)
        assert imports == []


# ---------------------------------------------------------------------------
# _extract_ruby_imports
# ---------------------------------------------------------------------------


class TestExtractRubyImports:
    def test_require_extracts_gem(self):
        string_node = MockNode("string", "'my_gem'")
        string_node.start_byte = 8
        string_node.end_byte = 16
        args_node = MockNode("argument_list", "", children=[string_node])
        func_node = MockNode("identifier", "require")
        func_node.start_byte = 0
        func_node.end_byte = 7
        node = MockNode("call", "require 'my_gem'", children=[])
        node._fields = {"function": func_node, "arguments": args_node}
        imports: list[dict] = []
        _extract_ruby_imports(node, "require 'my_gem'", imports)
        assert len(imports) == 1
        assert imports[0]["module_name"] == "my_gem"
        assert imports[0]["is_relative"] is False

    def test_require_relative_extracts(self):
        string_node = MockNode("string", "'my_lib'")
        string_node.start_byte = 17
        string_node.end_byte = 25
        args_node = MockNode("argument_list", "", children=[string_node])
        func_node = MockNode("identifier", "require_relative")
        func_node.start_byte = 0
        func_node.end_byte = 16
        node = MockNode("call", "require_relative 'my_lib'", children=[])
        node._fields = {"function": func_node, "arguments": args_node}
        imports: list[dict] = []
        _extract_ruby_imports(node, "require_relative 'my_lib'", imports)
        assert len(imports) == 1
        assert imports[0]["is_relative"] is True

    def test_require_skips_stdlib(self):
        string_node = MockNode("string", "'json'")
        string_node.start_byte = 8
        string_node.end_byte = 14
        args_node = MockNode("argument_list", "", children=[string_node])
        func_node = MockNode("identifier", "require")
        func_node.start_byte = 0
        func_node.end_byte = 7
        node = MockNode("call", "require 'json'", children=[])
        node._fields = {"function": func_node, "arguments": args_node}
        imports: list[dict] = []
        _extract_ruby_imports(node, "require 'json'", imports)
        assert imports == []

    def test_non_call_skipped(self):
        node = MockNode("method_def", "def foo")
        imports: list[dict] = []
        _extract_ruby_imports(node, "def foo", imports)
        assert imports == []


# ---------------------------------------------------------------------------
# _extract_php_imports
# ---------------------------------------------------------------------------


class TestExtractPhpImports:
    def test_extracts_use_declaration(self):
        node = MockNode("namespace_use_declaration", "use App\\Services\\UserService;")
        node.start_byte = 0
        node.end_byte = 28
        imports: list[dict] = []
        _extract_php_imports(node, "use App\\Services\\UserService;", imports)
        assert len(imports) == 1
        assert imports[0]["module_name"] == "App/Services/UserService"
        assert imports[0]["language"] == "php"

    def test_function_use(self):
        node = MockNode("namespace_use_declaration", "use function App\\Utils\\helper;")
        node.start_byte = 0
        node.end_byte = 30
        imports: list[dict] = []
        _extract_php_imports(node, "use function App\\Utils\\helper;", imports)
        assert len(imports) == 1

    def test_aliased_use(self):
        node = MockNode("namespace_use_declaration", "use App\\Models\\User as UserModel;")
        node.start_byte = 0
        node.end_byte = 33
        imports: list[dict] = []
        _extract_php_imports(node, "use App\\Models\\User as UserModel;", imports)
        assert len(imports) == 1
        assert "as" not in imports[0]["module_name"]

    def test_non_use_skipped(self):
        node = MockNode("function_definition", "function foo() {}")
        imports: list[dict] = []
        _extract_php_imports(node, "function foo() {}", imports)
        assert imports == []
