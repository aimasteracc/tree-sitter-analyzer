#!/usr/bin/env python3

import textwrap

import pytest

from tree_sitter_analyzer.mcp.tools._refactoring_plan_builder import (
    ExtractionTargetContext,
    _assigned_names_from_statement,
    _assigned_names_from_statement_and_body,
    _assigned_names_from_statements,
    _assigned_names_from_target,
    _assigned_names_from_targets,
    _body_indent,
    _build_extraction_target,
    _build_extraction_targets,
    _build_plan_for_func,
    _classify_line,
    _collect_assigned_names,
    _find_extractable_blocks,
    _helper_import_statement,
    _helper_module_path,
    _helper_module_stem,
    _infer_params_for_block,
    _infer_returns,
    _is_block_continuation,
    _make_skeleton,
    _nested_bodies_for_return_inference,
    _next_extractable_block,
    _scan_block_end,
    _suggest_helper_name,
    _unique_names,
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
        suggestions = [
            {"name": "long_function", "line_range": {"start": 99}}
        ]
        build_precise_plans("f.py", "def foo():\n    pass\n", mock_analysis, suggestions)
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
        assert _build_plan_for_func("f.py", lines, func, "def tiny():\n    pass") is None

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
        blocks = [(1, 5, "loop"), (6, 10, "conditional"), (11, 15, "computation"), (16, 20, "result_building")]
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
        result = _helper_module_path("pkg/foo.py", "_foo_helpers")
        assert result == "pkg/_foo_helpers.py"

    def test_deep_nested(self):
        result = _helper_module_path("a/b/c/foo.py", "_foo_helpers")
        assert result == "a/b/c/_foo_helpers.py"


class TestHelperImportStatement:
    def test_without_init(self, tmp_path):
        f = tmp_path / "module.py"
        f.write_text("x = 1")
        result = _helper_import_statement(str(f), "_module_helpers", "helper_a, helper_b")
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


class TestSuggestHelperName:
    def test_conditional_suffix(self):
        assert _suggest_helper_name("process", "conditional", 0) == "_process_check_conditions"

    def test_loop_suffix(self):
        assert _suggest_helper_name("process", "loop", 0) == "_process_process_items"

    def test_resource_suffix(self):
        assert _suggest_helper_name("handle", "resource", 0) == "_handle_handle_resource"

    def test_computation_suffix(self):
        assert _suggest_helper_name("calc", "computation", 0) == "_calc_compute"

    def test_result_building_suffix(self):
        assert _suggest_helper_name("build", "result_building", 0) == "_build_build_result"

    def test_logic_suffix(self):
        assert _suggest_helper_name("do", "logic", 0) == "_do_step"

    def test_index_zero_no_suffix_number(self):
        name = _suggest_helper_name("f", "loop", 0)
        assert not name.endswith("_1")

    def test_index_nonzero_adds_number(self):
        name = _suggest_helper_name("f", "loop", 2)
        assert name.endswith("_3")

    def test_private_func_stripped(self):
        assert _suggest_helper_name("_private", "loop", 0) == "_private_process_items"


class TestCollectAssignedNames:
    def test_simple_assignment(self):
        assert "x" in _collect_assigned_names("x = 1")

    def test_multiple_assignments(self):
        names = _collect_assigned_names("x = 1\ny = 2\nz = x + y")
        assert "x" in names
        assert "y" in names
        assert "z" in names

    def test_function_args(self):
        names = _collect_assigned_names("def f(a, b):\n    return a + b")
        assert "a" in names
        assert "b" in names

    def test_syntax_error_returns_empty(self):
        assert _collect_assigned_names("def [invalid") == set()

    def test_augmented_assignment(self):
        assert "x" in _collect_assigned_names("x += 1")


class TestInferParamsForBlock:
    def test_uses_outer_dep(self):
        src = "y = x + 1\nz = y * 2"
        params = _infer_params_for_block(src, {"x", "y"})
        assert "x" in params

    def test_no_params_for_self_contained(self):
        src = "x = 1\ny = 2"
        params = _infer_params_for_block(src, set())
        assert params == []

    def test_limits_to_six(self):
        src = "r = a + b + c + d + e + f + g"
        params = _infer_params_for_block(src, {"a", "b", "c", "d", "e", "f", "g"})
        assert len(params) <= 6

    def test_syntax_error_returns_empty(self):
        assert _infer_params_for_block("def [", set()) == []

    def test_excludes_builtins(self):
        src = "result = len(items)"
        params = _infer_params_for_block(src, {"items"})
        assert "items" in params
        assert "len" not in params

    def test_attribute_access(self):
        src = "x = obj.value"
        params = _infer_params_for_block(src, {"obj"})
        assert "obj" in params


class TestInferReturns:
    def test_simple_assignment(self):
        assert "x" in _infer_returns("x = 1\ny = 2")

    def test_empty_source(self):
        assert _infer_returns("") == []

    def test_syntax_error(self):
        assert _infer_returns("def [invalid") == []

    def test_tuple_unpacking(self):
        returns = _infer_returns("a, b = func()")
        assert "a" in returns
        assert "b" in returns

    def test_ann_assign(self):
        returns = _infer_returns("x: int = 5")
        assert "x" in returns

    def test_limits_to_four(self):
        src = "a = 1\nb = 2\nc = 3\nd = 4\ne = 5"
        assert len(_infer_returns(src)) <= 4


class TestAssignedNamesFromStatement:
    def test_assign(self):
        import ast

        node = ast.parse("x = 1").body[0]
        assert _assigned_names_from_statement(node) == ["x"]

    def test_ann_assign(self):
        import ast

        node = ast.parse("x: int = 1").body[0]
        assert _assigned_names_from_statement(node) == ["x"]

    def test_aug_assign(self):
        import ast

        node = ast.parse("x += 1").body[0]
        assert _assigned_names_from_statement(node) == ["x"]

    def test_non_assignment(self):
        import ast

        node = ast.parse("pass").body[0]
        assert _assigned_names_from_statement(node) == []


class TestAssignedNamesFromTarget:
    def test_name_target(self):
        import ast

        node = ast.parse("x = 1").body[0].targets[0]
        assert _assigned_names_from_target(node) == ["x"]

    def test_tuple_target(self):
        import ast

        node = ast.parse("a, b = 1, 2").body[0].targets[0]
        names = _assigned_names_from_target(node)
        assert "a" in names
        assert "b" in names

    def test_subscript_target(self):
        import ast

        node = ast.parse("d['key'] = 1").body[0].targets[0]
        assert _assigned_names_from_target(node) == []


class TestAssignedNamesFromTargets:
    def test_multiple_targets(self):
        import ast

        node = ast.parse("x = y = 1").body[0]
        names = _assigned_names_from_targets(node.targets)
        assert "x" in names
        assert "y" in names


class TestAssignedNamesFromStatements:
    def test_multiple_statements(self):
        import ast

        tree = ast.parse("x = 1\ny = 2")
        names = _assigned_names_from_statements(tree.body)
        assert "x" in names
        assert "y" in names


class TestAssignedNamesFromStatementAndBody:
    def test_try_body(self):
        import ast

        tree = ast.parse("try:\n    x = 1\nexcept:\n    pass")
        node = tree.body[0]
        names = _assigned_names_from_statement_and_body(node)
        assert "x" in names

    def test_with_body(self):
        import ast

        tree = ast.parse("with open('f') as fp:\n    x = fp.read()")
        node = tree.body[0]
        names = _assigned_names_from_statement_and_body(node)
        assert "x" in names

    def test_if_body(self):
        import ast

        tree = ast.parse("if True:\n    x = 1")
        node = tree.body[0]
        names = _assigned_names_from_statement_and_body(node)
        assert "x" in names

    def test_regular_statement(self):
        import ast

        tree = ast.parse("x = 1")
        node = tree.body[0]
        names = _assigned_names_from_statement_and_body(node)
        assert "x" in names


class TestNestedBodiesForReturnInference:
    def test_try(self):
        import ast

        node = ast.parse("try:\n    pass\nexcept:\n    pass").body[0]
        bodies = _nested_bodies_for_return_inference(node)
        assert len(bodies) == 1

    def test_with(self):
        import ast

        node = ast.parse("with open('f'):\n    pass").body[0]
        bodies = _nested_bodies_for_return_inference(node)
        assert len(bodies) == 1

    def test_async_with(self):
        import ast

        node = ast.parse("async def f():\n    async with x:\n        pass").body[0].body[0]
        bodies = _nested_bodies_for_return_inference(node)
        assert len(bodies) == 1

    def test_if(self):
        import ast

        node = ast.parse("if True:\n    pass").body[0]
        bodies = _nested_bodies_for_return_inference(node)
        assert len(bodies) == 1

    def test_for_loop(self):
        import ast

        node = ast.parse("for i in range(10):\n    pass").body[0]
        bodies = _nested_bodies_for_return_inference(node)
        assert bodies == []


class TestUniqueNames:
    def test_deduplicates(self):
        assert _unique_names(["a", "b", "a", "c"]) == ["a", "b", "c"]

    def test_preserves_order(self):
        assert _unique_names(["z", "a", "m", "a", "z"]) == ["z", "a", "m"]

    def test_empty(self):
        assert _unique_names([]) == []

    def test_single(self):
        assert _unique_names(["x"]) == ["x"]


class TestMakeSkeleton:
    def test_python_skeleton(self):
        result = _make_skeleton(
            "_helper_func",
            ["data", "count"],
            ["result"],
            ["    x = data + count"],
            ".py",
        )
        assert "def _helper_func(data, count):" in result
        assert "return result" in result

    def test_python_skeleton_no_returns(self):
        result = _make_skeleton("_do_thing", [], [], ["    pass"], ".py")
        assert "def _do_thing():" in result
        assert "return" not in result

    def test_non_python_skeleton(self):
        result = _make_skeleton("helper", ["x"], [], [], ".js")
        assert "// TODO: extract helper(x)" == result

    def test_python_skeleton_dedents(self):
        result = _make_skeleton(
            "_f", [], [], ["        x = 1", "        y = 2"], ".py"
        )
        assert "    x = 1" in result
        assert "    y = 2" in result

    def test_non_python_various_extensions(self):
        for ext in [".ts", ".java", ".c", ".cpp", ".go"]:
            result = _make_skeleton("fn", ["a"], [], [], ext)
            assert result.startswith("// TODO:")


class TestIntegration:
    def test_full_pipeline_long_function(self):
        source = textwrap.dedent("""\
            def process_data(data, config):
                items = load_items(data)
                filtered = []
                for item in items:
                    if item.active:
                        filtered.append(item)
                    x = item.value * 2
                    y = x + 1
                result = {}
                result['count'] = len(filtered)
                result['total'] = sum(i.value for i in filtered)
                result['avg'] = result['total'] / result['count'] if result['count'] else 0
                result['max_val'] = max(i.value for i in filtered)
                report = format_report(result)
                return report
        """)
        lines = source.splitlines()
        func = {"line": 1, "end_line": 14, "name": "process_data"}
        plan = _build_plan_for_func("data_processing.py", lines, func, source)
        assert plan is not None
        assert plan["function"] == "process_data"
        assert "data_processing_helpers" in plan["helper_module"]
        assert len(plan["extractions"]) >= 1
        assert all("helper_name" in t for t in plan["extractions"])
        assert len(plan["steps"]) == 4

    def test_full_pipeline_tiny_function_returns_none(self):
        source = "def tiny():\n    return 42\n"
        lines = source.splitlines()
        func = {"line": 1, "end_line": 2, "name": "tiny"}
        assert _build_plan_for_func("f.py", lines, func, source) is None

    def test_full_pipeline_nested_conditionals(self):
        source = textwrap.dedent("""\
            def analyze(input_data):
                if not input_data:
                    return None
                primary = extract_primary(input_data)
                secondary = extract_secondary(input_data)
                if primary and secondary:
                    combined = merge(primary, secondary)
                    extra = post_process(combined)
                    final = validate(extra)
                    audit = log_audit(final)
                else:
                    combined = primary or secondary
                    backup = fallback(combined)
                    safety = check(safety)
                    report = build_report(combined)
                return report
        """)
        lines = source.splitlines()
        func = {"line": 1, "end_line": 16, "name": "analyze"}
        plan = _build_plan_for_func("analysis.py", lines, func, source)
        assert plan is not None
