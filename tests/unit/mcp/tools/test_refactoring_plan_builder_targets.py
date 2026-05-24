#!/usr/bin/env python3


import pytest

from tree_sitter_analyzer.mcp.tools._refactoring_plan_builder import (
    ExtractionTargetContext,
    _body_indent,
    _build_extraction_target,
    _build_extraction_targets,
    _build_plan_for_func,
    _classify_line,
    _find_extractable_blocks,
    _helper_import_statement,
    _helper_module_path,
    _helper_module_stem,
    _is_block_continuation,
    _next_extractable_block,
    _scan_block_end,
    build_precise_plans,
)


class TestExtractionTargetContext:
    def test_creation(self):
        ctx = ExtractionTargetContext(
            lines=["a", "b"], func_name="foo", func_assigned={"x"}, ext=".py"
        )
        assert ctx.lines == ["a", "b"]
        assert ctx.func_name == "foo"
        assert ctx.func_assigned == {"x"}
        assert ctx.ext == ".py"

    def test_frozen(self):
        ctx = ExtractionTargetContext(
            lines=[], func_name="f", func_assigned=set(), ext=".py"
        )
        with pytest.raises(AttributeError):
            ctx.func_name = "bar"

    def test_equality(self):
        a = ExtractionTargetContext(
            lines=["x"], func_name="f", func_assigned=set(), ext=".py"
        )
        b = ExtractionTargetContext(
            lines=["x"], func_name="f", func_assigned=set(), ext=".py"
        )
        assert a == b


class TestBuildPrecisePlans:
    def test_none_analysis_returns_early(self):
        suggestions = [{"name": "long_function", "line_range": {"start": 1}}]
        build_precise_plans("f.py", "x = 1\n", None, suggestions)
        assert "precise_plan" not in suggestions[0]

    def test_no_matching_function(self):
        from unittest.mock import MagicMock

        mock_analysis = MagicMock()
        mock_analysis.elements = []
        suggestions = [{"name": "long_function", "line_range": {"start": 99}}]
        build_precise_plans(
            "f.py", "def foo():\n    pass\n", mock_analysis, suggestions
        )
        assert "precise_plan" not in suggestions[0]

    def test_skips_non_long_function_suggestions(self):
        suggestions = [{"name": "other_issue", "line_range": {"start": 1}}]
        build_precise_plans("f.py", "", {}, suggestions)
        assert "precise_plan" not in suggestions[0]

    def test_skips_suggestions_without_line_range(self):
        suggestions = [{"name": "long_function"}]
        build_precise_plans("f.py", "", {}, suggestions)
        assert "precise_plan" not in suggestions[0]


class TestBuildPlanForFunc:
    def test_returns_none_for_no_blocks(self):
        lines = ["def tiny():", "    pass"]
        func = {"line": 1, "end_line": 2, "name": "tiny"}
        assert (
            _build_plan_for_func("f.py", lines, func, "def tiny():\n    pass") is None
        )

    def test_returns_plan_for_extractable_function(self):
        source = (
            "def process(data):\n"
            "    result = []\n"
            "    for item in data:\n"
            "        value = transform(item)\n"
            "        result.append(value)\n"
            "        extra = value * 2\n"
            "        result.append(extra)\n"
            "    summary = {}\n"
            "    summary['count'] = len(result)\n"
            "    summary['total'] = sum(result)\n"
            "    summary['avg'] = summary['total'] / summary['count']\n"
            "    summary['max'] = max(result)\n"
            "    return summary\n"
        )
        lines = source.splitlines()
        func = {"line": 1, "end_line": 13, "name": "process"}
        plan = _build_plan_for_func("process.py", lines, func, source)
        assert plan is not None
        assert plan["function"] == "process"
        assert "extractions" in plan
        assert "steps" in plan
        assert len(plan["steps"]) == 4

    def test_helper_module_in_plan(self):
        source = (
            "def big_func(items):\n"
            "    data = load_data()\n"
            "    for item in data:\n"
            "        processed = handle(item)\n"
            "        x = processed * 2\n"
            "        y = x + 1\n"
            "        z = y * 3\n"
            "        w = z + 4\n"
            "    result = sum(data)\n"
            "    return result\n"
        )
        lines = source.splitlines()
        func = {"line": 1, "end_line": 10, "name": "big_func"}
        plan = _build_plan_for_func("my_module.py", lines, func, source)
        assert plan is not None
        assert "_my_module_helpers" in plan["helper_module"]


class TestBuildExtractionTargets:
    def test_builds_targets_for_blocks(self):
        blocks = [(3, 7, "loop"), (8, 12, "computation")]
        lines = [
            "def f():",
            "    x = 1",
            "    for i in range(10):",
            "        y = i * 2",
            "        print(y)",
            "        z = y + 1",
            "        w = z * 3",
            "    result = x + 1",
            "    return result",
        ]
        func_assigned = {"x", "result"}
        targets = _build_extraction_targets(blocks, lines, "f", func_assigned, ".py")
        assert len(targets) == 2
        assert targets[0]["helper_name"]
        assert targets[0]["hint"] == "loop"

    def test_limits_to_three_targets(self):
        blocks = [
            (1, 5, "loop"),
            (6, 10, "conditional"),
            (11, 15, "computation"),
            (16, 20, "result_building"),
        ]
        lines = ["line"] * 25
        targets = _build_extraction_targets(blocks, lines, "f", set(), ".py")
        assert len(targets) == 3


class TestBuildExtractionTarget:
    def test_target_fields(self):
        ctx = ExtractionTargetContext(
            lines=["line"] * 20,
            func_name="compute",
            func_assigned={"data"},
            ext=".py",
        )
        block = (2, 6, "computation")
        target = _build_extraction_target(0, block, ctx)
        assert "helper_name" in target
        assert "extract_lines" in target
        assert "params" in target
        assert "returns" in target
        assert "hint" in target
        assert "skeleton" in target
        assert target["hint"] == "computation"
        assert target["extract_lines"] == "2-6"


class TestHelperModuleStem:
    def test_simple_file(self):
        assert _helper_module_stem("module.py") == "_module_helpers"

    def test_private_file(self):
        assert _helper_module_stem("_private.py") == "_private_helpers"

    def test_deeply_nested(self):
        assert _helper_module_stem("a/b/c.py") == "_c_helpers"

    def test_all_underscores(self):
        assert _helper_module_stem("____.py") == "______helpers"


class TestHelperModulePath:
    def test_current_dir(self):
        result = _helper_module_path("foo.py", "_foo_helpers")
        assert result == "_foo_helpers.py"

    def test_nested_dir(self):
        # ``_helper_module_path`` uses ``os.path`` join semantics, so the
        # separator follows the host OS. Normalise both sides to POSIX
        # forward slashes for a portable comparison.
        result = _helper_module_path("pkg/foo.py", "_foo_helpers")
        assert result.replace("\\", "/") == "pkg/_foo_helpers.py"

    def test_deep_nested(self):
        result = _helper_module_path("a/b/c/foo.py", "_foo_helpers")
        assert result.replace("\\", "/") == "a/b/c/_foo_helpers.py"


class TestHelperImportStatement:
    def test_without_init(self, tmp_path):
        f = tmp_path / "module.py"
        f.write_text("x = 1")
        result = _helper_import_statement(
            str(f), "_module_helpers", "helper_a, helper_b"
        )
        assert result == "from _module_helpers import helper_a, helper_b"

    def test_with_init(self, tmp_path):
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        f = pkg / "module.py"
        f.write_text("x = 1")
        result = _helper_import_statement(str(f), "_module_helpers", "helper_a")
        assert result == "from ._module_helpers import helper_a"


class TestFindExtractableBlocks:
    def test_empty_lines(self):
        assert _find_extractable_blocks([], 1) == []

    def test_no_indented_body(self):
        lines = ["x = 1", "y = 2"]
        assert _find_extractable_blocks(lines, 1) == []

    def test_finds_loop_block(self):
        lines = [
            "def f():",
            "    for i in range(10):",
            "        x = i * 2",
            "        y = x + 1",
            "        z = y * 3",
            "        w = z + 4",
            "        r = w * 5",
            "    return None",
        ]
        blocks = _find_extractable_blocks(lines, 1)
        assert len(blocks) >= 1
        assert blocks[0][2] == "loop"

    def test_finds_conditional_block(self):
        lines = [
            "def f():",
            "    if condition:",
            "        x = 1",
            "        y = 2",
            "        z = 3",
            "        w = 4",
            "        r = 5",
            "    return None",
        ]
        blocks = _find_extractable_blocks(lines, 1)
        assert len(blocks) >= 1
        assert blocks[0][2] == "conditional"

    def test_finds_computation_block_with_continuation(self):
        lines = [
            "def f():",
            "    data = load()",
            "    for item in data:",
            "        processed = transform(item)",
            "        filtered = filter(processed)",
            "        sorted_items = sorted(filtered)",
            "        result = aggregate(sorted_items)",
            "    return result",
        ]
        blocks = _find_extractable_blocks(lines, 1)
        assert len(blocks) >= 1

    def test_blocks_sorted_by_size_descending(self):
        lines = [
            "def f():",
            "    if True:",
            "        x = 1",
            "        y = 2",
            "    for i in range(10):",
            "        a = i",
            "        b = a + 1",
            "        c = b + 2",
            "        d = c + 3",
            "        e = d + 4",
            "    return None",
        ]
        blocks = _find_extractable_blocks(lines, 1)
        if len(blocks) >= 2:
            first_size = blocks[0][1] - blocks[0][0]
            second_size = blocks[1][1] - blocks[1][0]
            assert first_size >= second_size

    def test_short_blocks_excluded(self):
        lines = [
            "def f():",
            "    x = 1",
            "    return x",
        ]
        blocks = _find_extractable_blocks(lines, 1)
        assert len(blocks) == 0

    def test_absolute_start_offset(self):
        lines = [
            "def f():",
            "    for i in range(10):",
            "        x = i * 2",
            "        y = x + 1",
            "        z = y * 3",
            "        w = z + 4",
            "        r = w * 5",
            "    return None",
        ]
        blocks = _find_extractable_blocks(lines, 10)
        assert blocks[0][0] >= 10


class TestNextExtractableBlock:
    def test_empty_line_skipped(self):
        lines = ["def f():", "", "    x = 1"]
        block, idx = _next_extractable_block(lines, 1, 3, 4)
        assert block is None
        assert idx == 2

    def test_comment_line_skipped(self):
        lines = ["def f():", "    # comment", "    x = 1"]
        block, idx = _next_extractable_block(lines, 1, 3, 4)
        assert block is None
        assert idx == 2

    def test_wrong_indent_skipped(self):
        lines = ["def f():", "x = 1"]
        block, idx = _next_extractable_block(lines, 1, 2, 4)
        assert block is None

    def test_valid_block_returned(self):
        lines = [
            "    for i in range(10):",
            "        x = i",
            "        y = x + 1",
            "        z = y + 2",
            "        w = z + 3",
            "        r = w + 4",
        ]
        block, idx = _next_extractable_block(lines, 0, 6, 4)
        assert block is not None
        assert block[2] == "loop"
        assert idx > 0


class TestScanBlockEnd:
    def test_stops_at_lower_indent(self):
        lines = [
            "    for i in range(10):",
            "        x = i",
            "        y = i + 1",
            "done = True",
        ]
        end = _scan_block_end(lines, 1, 4, 4, "loop")
        assert end == 3

    def test_stops_at_same_indent_non_continuation(self):
        lines = [
            "    for i in range(10):",
            "        x = i",
            "        y = i + 1",
            "    z = 99",
        ]
        end = _scan_block_end(lines, 1, 4, 4, "loop")
        assert end == 3

    def test_continues_through_blank_lines(self):
        lines = [
            "    for i in range(10):",
            "        x = i",
            "",
            "        y = i + 1",
            "        z = i + 2",
        ]
        end = _scan_block_end(lines, 1, 5, 4, "loop")
        assert end == 5

    def test_all_lines_consumed(self):
        lines = [
            "    for i in range(10):",
            "        x = i",
            "        y = i + 1",
            "        z = i + 2",
        ]
        end = _scan_block_end(lines, 1, 4, 4, "loop")
        assert end == 4


class TestBodyIndent:
    def test_first_indented_line(self):
        lines = ["def f():", "    x = 1"]
        assert _body_indent(lines) == 4

    def test_skips_blank_lines(self):
        lines = ["def f():", "", "    x = 1"]
        assert _body_indent(lines) == 4

    def test_skips_comments(self):
        lines = ["def f():", "    # docstring", "    x = 1"]
        assert _body_indent(lines) == 4

    def test_no_body(self):
        lines = ["def f():"]
        assert _body_indent(lines) == 0


class TestClassifyLine:
    @pytest.mark.parametrize(
        "line,expected",
        [
            ("if x > 0:", "conditional"),
            ("elif x < 0:", "conditional"),
            ("else:", "conditional"),
            ("for i in items:", "loop"),
            ("while True:", "loop"),
            ("try:", "resource"),
            ("with open(f) as fp:", "resource"),
            ("x = compute(y)", "computation"),
            ("return result", "result_building"),
            ("def foo():", "logic"),
            ("class Foo:", "logic"),
            ("print('hello')", "logic"),
            ("pass", "logic"),
            ("break", "logic"),
        ],
    )
    def test_classifications(self, line, expected):
        assert _classify_line(line) == expected


class TestIsBlockContinuation:
    def test_resource_except(self):
        assert _is_block_continuation("except ValueError:", "resource") is True

    def test_resource_else(self):
        assert _is_block_continuation("else:", "resource") is True

    def test_resource_finally(self):
        assert _is_block_continuation("finally:", "resource") is True

    def test_conditional_elif(self):
        assert _is_block_continuation("elif x:", "conditional") is True

    def test_conditional_else(self):
        assert _is_block_continuation("else:", "conditional") is True

    def test_unrelated_hint(self):
        assert _is_block_continuation("else:", "loop") is False

    def test_unrelated_line(self):
        assert _is_block_continuation("x = 1", "resource") is False
