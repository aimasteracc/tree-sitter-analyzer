"""
Regression tests for Issue #745 — JS destructured object parameters mangled.

When a JavaScript function uses object destructuring as a parameter:
    function foo({ title, onUpdate, ...otherProps }) { ... }

the parameter was split on the last space, producing:
    name="}", type="{ title, onUpdate, ...otherProps"

This file pins the fixed behaviour: the entire destructuring pattern is
preserved as the parameter name, not torn apart by whitespace splitting.

Two code paths are affected:
* ``_parse_string_parameter``  (analyze_code_structure_helpers.py — MCP path)
* ``_process_type_prefix_parameter`` (table_command_helpers.py — CLI path)
"""

from tree_sitter_analyzer.cli.commands.table_command_helpers import (
    _process_type_prefix_parameter,
    process_parameters,
)
from tree_sitter_analyzer.mcp.tools.analyze_code_structure_helpers import (
    _parse_string_parameter,
)


class TestParseStringParameterDestructuring:
    """_parse_string_parameter must preserve destructuring patterns intact."""

    def test_object_destructuring_name_preserved(self):
        pattern = "{ title, onUpdate, ...otherProps }"
        result = _parse_string_parameter(pattern)
        assert result is not None
        assert result["name"] == pattern, (
            f"Destructuring pattern was mangled: got name={result['name']!r}"
        )

    def test_object_destructuring_no_closing_brace_as_name(self):
        result = _parse_string_parameter("{ title, onUpdate, ...otherProps }")
        assert result is not None
        assert result["name"] != "}", (
            "name must not be '}' — destructuring was split on last space"
        )

    def test_simple_object_destructuring(self):
        result = _parse_string_parameter("{ x, y }")
        assert result is not None
        assert result["name"] == "{ x, y }"

    def test_array_destructuring_name_preserved(self):
        pattern = "[first, second]"
        result = _parse_string_parameter(pattern)
        assert result is not None
        assert result["name"] == pattern

    def test_array_destructuring_no_bracket_as_name(self):
        result = _parse_string_parameter("[first, second]")
        assert result is not None
        assert result["name"] != "]"

    def test_normal_typed_param_unchanged(self):
        result = _parse_string_parameter("name: string")
        assert result is not None
        assert result["name"] == "name"
        assert result["type"] == "string"

    def test_default_valued_param_unchanged(self):
        result = _parse_string_parameter("limit = 10")
        assert result is not None
        assert result["name"] == "limit"
        assert result["default"] == "10"

    def test_destructuring_with_default_preserves_pattern_and_default(self):
        # {title} = {} must NOT return name="{title} = {}" — Codex P2 on #745
        result = _parse_string_parameter("{title} = {}")
        assert result is not None
        assert result["name"] == "{title}"
        assert result.get("default") == "{}"

    def test_ts_typed_destructuring_preserves_type(self):
        # { id }: Props must return name="{ id }", type="Props" — Codex P2 on #745
        result = _parse_string_parameter("{ id }: Props")
        assert result is not None
        assert result["name"] == "{ id }"
        assert result["type"] == "Props"

    def test_ts_typed_destructuring_with_default(self):
        # { id }: Props = {} must return all three fields
        result = _parse_string_parameter("{ id }: Props = {}")
        assert result is not None
        assert result["name"] == "{ id }"
        assert result["type"] == "Props"
        assert result.get("default") == "{}"


class TestProcessParametersDestructuring:
    """process_parameters must preserve JS object-destructuring param names."""

    def test_js_destructured_param_not_mangled(self):
        params = ["{ title, onUpdate, ...otherProps }"]
        result = process_parameters(params, "javascript")
        assert len(result) == 1
        assert result[0]["name"] == "{ title, onUpdate, ...otherProps }"

    def test_js_destructured_name_not_closing_brace(self):
        params = ["{ title, onUpdate, ...otherProps }"]
        result = process_parameters(params, "javascript")
        assert result[0]["name"] != "}"

    def test_js_array_destructuring_preserved(self):
        params = ["[head, ...tail]"]
        result = process_parameters(params, "javascript")
        assert len(result) == 1
        assert result[0]["name"] == "[head, ...tail]"

    def test_js_normal_param_unchanged(self):
        params = ["event"]
        result = process_parameters(params, "javascript")
        assert len(result) == 1
        assert result[0]["name"] == "event"

    def test_mixed_params_all_correct(self):
        params = ["{ title, onUpdate }", "callback", "options"]
        result = process_parameters(params, "javascript")
        assert len(result) == 3
        assert result[0]["name"] == "{ title, onUpdate }"
        assert result[1]["name"] == "callback"
        assert result[2]["name"] == "options"


class TestTypePrefixParameterCSharpAttributes:
    """C# attribute parameters must NOT be treated as destructuring (#745 Codex P2)."""

    def test_csharp_frombody_attribute_preserved(self):
        # [FromBody] UserDto dto -> name="dto", type="[FromBody] UserDto"
        result = _process_type_prefix_parameter("[FromBody] UserDto dto")
        assert result["name"] == "dto"
        assert result["type"] == "[FromBody] UserDto"

    def test_cpp_maybe_unused_attribute_preserved(self):
        # [[maybe_unused]] int value -> name="value", type="[[maybe_unused]] int"
        result = _process_type_prefix_parameter("[[maybe_unused]] int value")
        assert result["name"] == "value"
        assert result["type"] == "[[maybe_unused]] int"
