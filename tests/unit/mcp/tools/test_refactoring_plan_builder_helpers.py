#!/usr/bin/env python3

import textwrap

from tree_sitter_analyzer.mcp.tools._refactoring_plan_builder import (
    _assigned_names_from_statement,
    _assigned_names_from_statement_and_body,
    _assigned_names_from_statements,
    _assigned_names_from_target,
    _assigned_names_from_targets,
    _build_plan_for_func,
    _collect_assigned_names,
    _infer_params_for_block,
    _infer_returns,
    _make_skeleton,
    _nested_bodies_for_return_inference,
    _suggest_helper_name,
    _unique_names,
)


class TestSuggestHelperName:
    def test_conditional_suffix(self):
        assert (
            _suggest_helper_name("process", "conditional", 0)
            == "_process_check_conditions"
        )

    def test_loop_suffix(self):
        assert _suggest_helper_name("process", "loop", 0) == "_process_process_items"

    def test_resource_suffix(self):
        assert (
            _suggest_helper_name("handle", "resource", 0) == "_handle_handle_resource"
        )

    def test_computation_suffix(self):
        assert _suggest_helper_name("calc", "computation", 0) == "_calc_compute"

    def test_result_building_suffix(self):
        assert (
            _suggest_helper_name("build", "result_building", 0) == "_build_build_result"
        )

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

        node = (
            ast.parse("async def f():\n    async with x:\n        pass").body[0].body[0]
        )
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
        result = _make_skeleton("_f", [], [], ["        x = 1", "        y = 2"], ".py")
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
        assert len(plan["extractions"]) == 1  # Measured 2026-06-28 with grammar v0.21.3
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
        assert "function" in plan
        assert plan["function"] == "analyze"
