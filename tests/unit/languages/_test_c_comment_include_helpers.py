"""Tests for C comment extraction and include directive helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tree_sitter_analyzer.languages._c_comment import (
    _collect_block_comment,
    _is_block_comment_start,
    extract_comment_for_line,
)
from tree_sitter_analyzer.languages._c_include import (
    _include_from_line,
    _include_path_match,
    extract_include_info,
    extract_includes_fallback,
)


@dataclass
class FakeNode:
    type: str
    text: str = ""
    children: list[FakeNode] = field(default_factory=list)
    fields: dict[str, FakeNode] = field(default_factory=dict)
    start_point: tuple[int, int] = (0, 0)
    end_point: tuple[int, int] = (0, 0)
    start_byte: int = 0
    end_byte: int = 0
    parent: FakeNode | None = None

    def child_by_field_name(self, name: str) -> FakeNode | None:
        return self.fields.get(name)


def _get_node_text(node: Any) -> str:
    return node.text


class TestIsBlockCommentStart:
    def test_double_slash_star(self) -> None:
        assert _is_block_comment_start("/** comment */") is True

    def test_single_slash_star(self) -> None:
        assert _is_block_comment_start("/* comment */") is True

    def test_triple_slash(self) -> None:
        assert _is_block_comment_start("/// doc comment") is False

    def test_no_comment(self) -> None:
        assert _is_block_comment_start("int x;") is False

    def test_empty_string(self) -> None:
        assert _is_block_comment_start("") is False

    def test_indented_block_comment(self) -> None:
        assert _is_block_comment_start("  /** indented */") is False

    def test_code_line(self) -> None:
        assert _is_block_comment_start("void foo() {}") is False


class TestCollectBlockComment:
    def test_single_line_block(self) -> None:
        lines = ["/** doc */", "int x;"]
        result = _collect_block_comment(0, 2, lines)
        assert "/** doc */" in result

    def test_multi_line_block(self) -> None:
        lines = ["/**", " * line 1", " * line 2", " */", "int x;"]
        result = _collect_block_comment(0, 5, lines)
        assert "/**" in result
        assert "*/" in result

    def test_stops_at_end_marker(self) -> None:
        lines = ["/** start", " * middle", " */", "int x;", "other"]
        result = _collect_block_comment(0, 5, lines)
        assert result.endswith("*/")

    def test_single_line_content(self) -> None:
        lines = ["/* single */", "int x;"]
        result = _collect_block_comment(0, 2, lines)
        assert "/* single */" in result


class TestExtractCommentForLine:
    def test_triple_slash_comment(self) -> None:
        lines = ["/// doc comment", "int x;"]
        result = extract_comment_for_line(2, lines)
        assert result == "/// doc comment"

    def test_block_comment_above(self) -> None:
        lines = ["/** block */", "int x;"]
        result = extract_comment_for_line(2, lines)
        assert "/** block */" in result

    def test_no_comment(self) -> None:
        lines = ["int x;", "int y;"]
        result = extract_comment_for_line(2, lines)
        assert result is None

    def test_line_out_of_range(self) -> None:
        lines = ["int x;"]
        result = extract_comment_for_line(100, lines)
        assert result is None

    def test_empty_lines(self) -> None:
        result = extract_comment_for_line(1, [])
        assert result is None

    def test_comment_too_far_above(self) -> None:
        lines = ["/// far", "code1", "code2", "code3", "code4", "code5", "int x;"]
        result = extract_comment_for_line(7, lines)
        assert result is None

    def test_multi_line_block_comment(self) -> None:
        lines = ["/**", " * Description", " */", "void foo();"]
        result = extract_comment_for_line(4, lines)
        assert "/**" in result

    def test_comment_within_range(self) -> None:
        lines = ["code1", "code2", "/// doc", "code4", "int x;"]
        result = extract_comment_for_line(5, lines)
        assert result == "/// doc"


class TestExtractIncludeInfo:
    def test_system_include(self) -> None:
        node = FakeNode(
            "preproc_include",
            text='#include <stdio.h>',
            start_point=(0, 0),
        )
        result = extract_include_info(node, _get_node_text)
        assert result is not None
        assert result.name == "stdio.h"
        assert result.module_name == "stdio.h"

    def test_local_include(self) -> None:
        node = FakeNode(
            "preproc_include",
            text='#include "myheader.h"',
            start_point=(2, 0),
        )
        result = extract_include_info(node, _get_node_text)
        assert result is not None
        assert result.name == "myheader.h"

    def test_no_match(self) -> None:
        node = FakeNode("preproc_include", text="not an include")
        result = extract_include_info(node, _get_node_text)
        assert result is None

    def test_line_number(self) -> None:
        node = FakeNode(
            "preproc_include",
            text="#include <stdlib.h>",
            start_point=(5, 0),
        )
        result = extract_include_info(node, _get_node_text)
        assert result is not None
        assert result.start_line == 6

    def test_path_with_subdirectory(self) -> None:
        node = FakeNode(
            "preproc_include",
            text='#include "sys/types.h"',
            start_point=(0, 0),
        )
        result = extract_include_info(node, _get_node_text)
        assert result is not None
        assert result.name == "sys/types.h"

    def test_exception_returns_none(self) -> None:
        node = FakeNode("preproc_include")
        node.start_point = None
        result = extract_include_info(node, _get_node_text)
        assert result is None


class TestIncludePathMatch:
    def test_angle_bracket(self) -> None:
        match = _include_path_match('#include <stdio.h>')
        assert match is not None
        assert match.group(1) == "stdio.h"

    def test_quoted(self) -> None:
        match = _include_path_match('#include "foo.h"')
        assert match is not None
        assert match.group(1) == "foo.h"

    def test_no_match(self) -> None:
        match = _include_path_match("no include here")
        assert match is None


class TestIncludeFromLine:
    def test_system_include_line(self) -> None:
        result = _include_from_line("#include <stdio.h>", 1)
        assert result is not None
        assert result.name == "stdio.h"

    def test_local_include_line(self) -> None:
        result = _include_from_line('#include "foo.h"', 3)
        assert result is not None
        assert result.name == "foo.h"

    def test_non_include_line(self) -> None:
        result = _include_from_line("int x;", 1)
        assert result is None

    def test_whitespace_include(self) -> None:
        result = _include_from_line("  #include <test.h>", 1)
        assert result is None


class TestExtractIncludesFallback:
    def test_single_system_include(self) -> None:
        code = '#include <stdio.h>\nint main() {}'
        result = extract_includes_fallback(code)
        assert len(result) == 1
        assert result[0].name == "stdio.h"

    def test_multiple_includes(self) -> None:
        code = '#include <stdio.h>\n#include <stdlib.h>\n#include "my.h"'
        result = extract_includes_fallback(code)
        assert len(result) == 3

    def test_no_includes(self) -> None:
        code = "int x = 1;"
        result = extract_includes_fallback(code)
        assert len(result) == 0

    def test_empty_source(self) -> None:
        result = extract_includes_fallback("")
        assert len(result) == 0

    def test_mixed_includes(self) -> None:
        code = '#include <stdio.h>\n#include "local.h"\n#include <string.h>'
        result = extract_includes_fallback(code)
        names = [imp.name for imp in result]
        assert "stdio.h" in names
        assert "local.h" in names
        assert "string.h" in names

    def test_line_numbers_correct(self) -> None:
        code = '#include <a.h>\nint x;\n#include <b.h>'
        result = extract_includes_fallback(code)
        assert result[0].start_line == 1
        assert result[1].start_line == 3
