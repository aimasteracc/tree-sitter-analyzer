"""Theme E — Parameter Extraction Hardening.

RED-first tests for:
  - Kotlin: function_value_parameters node type (not a named field), plus vararg prefix
  - Go: variadic_parameter_declaration (numbers ...int) silently dropped
  - PHP: variadic_parameter (method + function contexts)
  - C++: variadic_parameter_declaration emits full text, not bare "..."

Uses real tree-sitter parses — no mocks.
"""

from __future__ import annotations

import pytest

pytest.importorskip("tree_sitter_kotlin")
pytest.importorskip("tree_sitter_go")
pytest.importorskip("tree_sitter_php")
pytest.importorskip("tree_sitter_cpp")

import tree_sitter
import tree_sitter_cpp
import tree_sitter_go
import tree_sitter_kotlin
import tree_sitter_php

# ---------------------------------------------------------------------------
# Helpers — one parser per language
# ---------------------------------------------------------------------------


def _kotlin_parser() -> tree_sitter.Parser:
    return tree_sitter.Parser(tree_sitter.Language(tree_sitter_kotlin.language()))


def _go_parser() -> tree_sitter.Parser:
    return tree_sitter.Parser(tree_sitter.Language(tree_sitter_go.language()))


def _php_parser() -> tree_sitter.Parser:
    return tree_sitter.Parser(tree_sitter.Language(tree_sitter_php.language_php()))


def _cpp_parser() -> tree_sitter.Parser:
    return tree_sitter.Parser(tree_sitter.Language(tree_sitter_cpp.language()))


# ---------------------------------------------------------------------------
# Kotlin — extract_kotlin_parameters
# ---------------------------------------------------------------------------


class TestKotlinParameterExtraction:
    """Theme E: Kotlin parameters were all empty because child_by_field_name
    ('parameters') returns None — the grammar uses function_value_parameters
    as a child type, not a named field."""

    def test_three_params_including_vararg_count(self):
        """greet(name, age, vararg tags) must yield exactly 3 parameters."""
        from tree_sitter_analyzer.languages.kotlin_helpers import (
            extract_kotlin_parameters,
        )

        code = "fun greet(name: String, age: Int, vararg tags: String): Unit {}"
        parser = _kotlin_parser()
        tree = parser.parse(code.encode())
        func_node = tree.root_node.children[0]

        def get_text(n: object) -> str:
            return bytes(n.text).decode()  # type: ignore[attr-defined]

        params = extract_kotlin_parameters(func_node, get_text)
        assert len(params) == 3

    def test_three_params_names_and_types(self):
        """Each parameter must carry its name and type."""
        from tree_sitter_analyzer.languages.kotlin_helpers import (
            extract_kotlin_parameters,
        )

        code = "fun greet(name: String, age: Int, vararg tags: String): Unit {}"
        parser = _kotlin_parser()
        tree = parser.parse(code.encode())
        func_node = tree.root_node.children[0]

        def get_text(n: object) -> str:
            return bytes(n.text).decode()  # type: ignore[attr-defined]

        params = extract_kotlin_parameters(func_node, get_text)
        assert params == ["name: String", "age: Int", "vararg tags: String"]

    def test_two_regular_params_count(self):
        """Functions without vararg still work after the fix."""
        from tree_sitter_analyzer.languages.kotlin_helpers import (
            extract_kotlin_parameters,
        )

        code = "fun add(a: Int, b: Int): Int {}"
        parser = _kotlin_parser()
        tree = parser.parse(code.encode())
        func_node = tree.root_node.children[0]

        def get_text(n: object) -> str:
            return bytes(n.text).decode()  # type: ignore[attr-defined]

        params = extract_kotlin_parameters(func_node, get_text)
        assert len(params) == 2

    def test_zero_params(self):
        """Functions with no parameters yield an empty list."""
        from tree_sitter_analyzer.languages.kotlin_helpers import (
            extract_kotlin_parameters,
        )

        code = "fun hello(): Unit {}"
        parser = _kotlin_parser()
        tree = parser.parse(code.encode())
        func_node = tree.root_node.children[0]

        def get_text(n: object) -> str:
            return bytes(n.text).decode()  # type: ignore[attr-defined]

        params = extract_kotlin_parameters(func_node, get_text)
        assert len(params) == 0


# ---------------------------------------------------------------------------
# Go — extract_parameters in _go_common_helpers.py
# ---------------------------------------------------------------------------


class TestGoVariadicParameterExtraction:
    """Theme E: variadic_parameter_declaration (e.g. numbers ...int)
    was silently dropped — only parameter_declaration was collected."""

    def test_variadic_sum_count(self):
        """func sum(a int, numbers ...int) must yield exactly 2 parameters."""
        from tree_sitter_analyzer.languages._go_common_helpers import (
            extract_parameters,
        )

        code = "func sum(a int, numbers ...int) int { return 0 }"
        parser = _go_parser()
        tree = parser.parse(code.encode())
        func_node = tree.root_node.children[0]

        def get_text(n: object) -> str:
            return bytes(n.text).decode()  # type: ignore[attr-defined]

        params = extract_parameters(func_node, get_text)
        assert len(params) == 2

    def test_variadic_sum_contains_variadic_param(self):
        """The variadic parameter text must contain 'numbers' and '...'."""
        from tree_sitter_analyzer.languages._go_common_helpers import (
            extract_parameters,
        )

        code = "func sum(a int, numbers ...int) int { return 0 }"
        parser = _go_parser()
        tree = parser.parse(code.encode())
        func_node = tree.root_node.children[0]

        def get_text(n: object) -> str:
            return bytes(n.text).decode()  # type: ignore[attr-defined]

        params = extract_parameters(func_node, get_text)
        assert params == ["a int", "numbers ...int"]

    def test_regular_params_unchanged(self):
        """Regular (non-variadic) parameters still work."""
        from tree_sitter_analyzer.languages._go_common_helpers import (
            extract_parameters,
        )

        code = "func add(x int, y int) int { return x + y }"
        parser = _go_parser()
        tree = parser.parse(code.encode())
        func_node = tree.root_node.children[0]

        def get_text(n: object) -> str:
            return bytes(n.text).decode()  # type: ignore[attr-defined]

        params = extract_parameters(func_node, get_text)
        assert len(params) == 2

    def test_only_variadic_param(self):
        """func with only a variadic param must yield exactly 1 parameter."""
        from tree_sitter_analyzer.languages._go_common_helpers import (
            extract_parameters,
        )

        code = "func printAll(args ...string) { }"
        parser = _go_parser()
        tree = parser.parse(code.encode())
        func_node = tree.root_node.children[0]

        def get_text(n: object) -> str:
            return bytes(n.text).decode()  # type: ignore[attr-defined]

        params = extract_parameters(func_node, get_text)
        assert params == ["args ...string"]


# ---------------------------------------------------------------------------
# PHP — variadic_parameter in extract_php_method_element and
#       extract_php_function_element
# ---------------------------------------------------------------------------


class TestPHPVariadicParameterExtraction:
    """Theme E: variadic_parameter (e.g. ...$parts) was silently dropped
    in both extract_php_method_element and extract_php_function_element."""

    def test_method_variadic_count(self):
        """Method format(string $sep, ...$parts) must yield exactly 2 params."""
        from tree_sitter_analyzer.languages.php_helpers import (
            extract_modifiers,
            extract_php_method_element,
        )

        code = b"<?php class F { public function format(string $sep, ...$parts): string {} }"
        parser = _php_parser()
        tree = parser.parse(code)

        # navigate to method_declaration
        cls_decl = tree.root_node.children[1]  # class_declaration
        decl_list = cls_decl.children[2]  # declaration_list
        method_node = decl_list.children[1]  # method_declaration

        def get_text(n: object) -> str:
            return bytes(n.text).decode()  # type: ignore[attr-defined]

        def extract_mod(n: object) -> list[str]:
            return extract_modifiers(n, get_text)

        def extract_attr(_n: object) -> list[dict]:
            return []

        result = extract_php_method_element(
            method_node,
            "F",
            get_text,
            extract_mod,
            extract_attr,
        )
        assert result is not None
        assert len(result.parameters) == 2

    def test_method_variadic_text_contains_parts(self):
        """The variadic param entry must mention '$parts' or 'parts'."""
        from tree_sitter_analyzer.languages.php_helpers import (
            extract_modifiers,
            extract_php_method_element,
        )

        code = b"<?php class F { public function format(string $sep, ...$parts): string {} }"
        parser = _php_parser()
        tree = parser.parse(code)

        cls_decl = tree.root_node.children[1]
        decl_list = cls_decl.children[2]
        method_node = decl_list.children[1]

        def get_text(n: object) -> str:
            return bytes(n.text).decode()  # type: ignore[attr-defined]

        def extract_mod(n: object) -> list[str]:
            return extract_modifiers(n, get_text)

        def extract_attr(_n: object) -> list[dict]:
            return []

        result = extract_php_method_element(
            method_node,
            "F",
            get_text,
            extract_mod,
            extract_attr,
        )
        assert result is not None
        variadic_texts = [p for p in result.parameters if "parts" in p]
        assert len(variadic_texts) == 1

    def test_function_variadic_count(self):
        """Free function implode(string $sep, ...$parts) must yield 2 params."""
        from tree_sitter_analyzer.languages.php_helpers import (
            extract_php_function_element,
        )

        code = b"<?php function implode(string $sep, ...$parts): string { return ''; }"
        parser = _php_parser()
        tree = parser.parse(code)

        func_node = tree.root_node.children[1]  # function_definition

        def get_text(n: object) -> str:
            return bytes(n.text).decode()  # type: ignore[attr-defined]

        result = extract_php_function_element(func_node, "", get_text)
        assert result is not None
        assert len(result.parameters) == 2

    def test_function_variadic_text_contains_parts(self):
        """The variadic param entry must include '...$parts' or 'parts'."""
        from tree_sitter_analyzer.languages.php_helpers import (
            extract_php_function_element,
        )

        code = b"<?php function implode(string $sep, ...$parts): string { return ''; }"
        parser = _php_parser()
        tree = parser.parse(code)

        func_node = tree.root_node.children[1]

        def get_text(n: object) -> str:
            return bytes(n.text).decode()  # type: ignore[attr-defined]

        result = extract_php_function_element(func_node, "", get_text)
        assert result is not None
        variadic_texts = [p for p in result.parameters if "parts" in p]
        assert len(variadic_texts) == 1


# ---------------------------------------------------------------------------
# C++ — variadic_parameter_declaration emits full text, not bare "..."
# ---------------------------------------------------------------------------


class TestCppVariadicParameterExtraction:
    """Theme E (C++): _cpp_signature_helpers.extract_parameters previously
    appended the literal string '...' for variadic_parameter_declaration nodes
    instead of the actual node text (e.g. 'Args... args').

    This is a leaf-level node-type change — no type-resolver pipeline involved.
    """

    def test_template_variadic_full_text(self):
        """template variadic param 'Args... args' must appear as full text,
        not a bare '...'."""
        from tree_sitter_analyzer.languages._cpp_signature_helpers import (
            extract_parameters,
        )

        code = b"template <typename... Args> void foo(Args... args) {}"
        parser = _cpp_parser()
        tree = parser.parse(code)

        # Navigate: template_declaration -> function_definition ->
        # function_declarator -> parameter_list
        template_decl = tree.root_node.children[0]
        func_def = template_decl.children[2]  # function_definition
        # find parameter_list via function_declarator
        func_declarator = None
        for child in func_def.children:
            if child.type == "function_declarator":
                func_declarator = child
                break
        assert func_declarator is not None
        param_list = None
        for child in func_declarator.children:
            if child.type == "parameter_list":
                param_list = child
                break
        assert param_list is not None

        def get_text(n: object) -> str:
            return bytes(n.text).decode()  # type: ignore[attr-defined]

        params = extract_parameters(param_list, get_text)
        assert len(params) == 1
        # Must include the actual parameter text, not the bare "..."
        assert params[0] != "..."
        assert "args" in params[0]

    def test_c_style_variadic_printf(self):
        """C-style printf(const char* fmt, ...) variadic: '...' node type is
        different (just '...') — verify it is preserved or captured."""
        from tree_sitter_analyzer.languages._cpp_signature_helpers import (
            extract_parameters,
        )

        code = b"int printf(const char* fmt, ...);"
        parser = _cpp_parser()
        tree = parser.parse(code)

        # Navigate to parameter_list
        decl = tree.root_node.children[0]

        def find_param_list(node: object) -> object | None:
            if hasattr(node, "type") and node.type == "parameter_list":  # type: ignore[union-attr]
                return node
            for child in getattr(node, "children", []):
                result = find_param_list(child)
                if result is not None:
                    return result
            return None

        param_list = find_param_list(decl)
        assert param_list is not None

        def get_text(n: object) -> str:
            return bytes(n.text).decode()  # type: ignore[attr-defined]

        params = extract_parameters(param_list, get_text)
        # fmt is a regular parameter_declaration
        assert len(params) == 2
        assert params[0] == "const char* fmt"
        # C-style variadic node is just "..." — must be captured exactly
        assert params[1] == "..."


# ---------------------------------------------------------------------------
# P3 edge-case additions (adversarial review follow-up)
# ---------------------------------------------------------------------------


class TestPHPByReferenceVariadic:
    """PHP by-reference variadic: function join(string &...$parts)
    The variadic_parameter node text must be captured verbatim."""

    def test_by_reference_variadic_text(self):
        """function join(string &...$parts) → parameter text is '&...$parts'
        (full variadic_parameter node text captured)."""
        from tree_sitter_analyzer.languages.php_helpers import (
            extract_php_function_element,
        )

        code = b"<?php function join(string &...$parts): string { return ''; }"
        parser = _php_parser()
        tree = parser.parse(code)

        func_node = tree.root_node.children[1]  # function_definition

        def get_text(n: object) -> str:
            return bytes(n.text).decode()  # type: ignore[attr-defined]

        result = extract_php_function_element(func_node, "", get_text)
        assert result is not None
        assert result.parameters == ["string &...$parts"]


class TestKotlinDefaultValue:
    """Kotlin default value: fun f(x: Int = 5)
    Current behavior drops the default expression; this test pins that intent."""

    def test_default_value_dropped(self):
        """fun f(x: Int = 5) → ['x: Int']
        Pins existing behavior: the '= 5' default initializer is dropped.
        This is intentional — parameters carry name+type, not initializers."""
        from tree_sitter_analyzer.languages.kotlin_helpers import (
            extract_kotlin_parameters,
        )

        code = "fun f(x: Int = 5) {}"
        parser = _kotlin_parser()
        tree = parser.parse(code.encode())
        func_node = tree.root_node.children[0]

        def get_text(n: object) -> str:
            return bytes(n.text).decode()  # type: ignore[attr-defined]

        params = extract_kotlin_parameters(func_node, get_text)
        # Pins current intentional behavior: default expression '= 5' is dropped.
        assert params == ["x: Int"]


class TestCppCStyleVariadicExact:
    """C-style variadic '...' in printf must appear as the exact string '...'."""

    def test_c_style_variadic_exact_string(self):
        """int printf(const char* fmt, ...) → params[1] == '...' (exact)."""
        from tree_sitter_analyzer.languages._cpp_signature_helpers import (
            extract_parameters,
        )

        code = b"int printf(const char* fmt, ...);"
        parser = _cpp_parser()
        tree = parser.parse(code)

        def find_param_list(node: object) -> object | None:
            if hasattr(node, "type") and node.type == "parameter_list":  # type: ignore[union-attr]
                return node
            for child in getattr(node, "children", []):
                result = find_param_list(child)
                if result is not None:
                    return result
            return None

        param_list = find_param_list(tree.root_node.children[0])
        assert param_list is not None

        def get_text(n: object) -> str:
            return bytes(n.text).decode()  # type: ignore[attr-defined]

        params = extract_parameters(param_list, get_text)
        assert params[1] == "..."
