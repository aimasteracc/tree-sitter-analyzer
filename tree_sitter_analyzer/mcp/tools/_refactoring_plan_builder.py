#!/usr/bin/env python3
"""
Precise extraction plan builder for refactoring suggestions.

Generates actionable extraction plans with exact line ranges, helper names,
inferred parameters/returns, and code skeletons for long functions.
"""

import ast
import textwrap
from pathlib import Path
from typing import Any


# Build response or data structure: build_precise_plans
# Section: imports and module configuration
# Section: main class definition
# Section: helper functions
# Section: data processing methods
# Section: output formatting methods
# Section: validation and error handling
def build_precise_plans(
    file_path: str,
    source: str,
    analysis: Any,
    suggestions: list[dict[str, Any]],
) -> None:
    """Attach precise extraction plans to long_function suggestions."""
    from .utils.element_extractor import get_functions

    if not analysis:
        return

    lines = source.splitlines()
    functions = get_functions(analysis)
    func_by_line = {f["line"]: f for f in functions}

    for s in suggestions:
        if s.get("name") != "long_function" or "line_range" not in s:
            continue
        start = s["line_range"]["start"]
        func = func_by_line.get(start)
        if not func:
            continue

        plan = _build_plan_for_func(file_path, lines, func, source)
        if plan:
            s["precise_plan"] = plan


# Build response or data structure: _build_plan_for_func
def _build_plan_for_func(
    file_path: str,
    lines: list[str],
    func: dict[str, Any],
    source: str,
) -> dict[str, Any] | None:
    """Build a precise extraction plan for one long function."""
    start = func["line"]
    end = func["end_line"]
    func_name = func["name"]
    func_lines = lines[start - 1 : end]

    blocks = _find_extractable_blocks(func_lines, start)
    if not blocks:
        return None

    ext = Path(file_path).suffix.lower()
    stem = Path(file_path).stem
    parent = str(Path(file_path).parent)
    helper_module = (
        f"{parent}/_{stem}_helpers.py" if parent != "." else f"_{stem}_helpers.py"
    )

    func_src = "\n".join(func_lines)
    func_assigned = _collect_assigned_names(func_src)

    targets = []
    for i, (b_start, b_end, hint) in enumerate(blocks[:3]):
        helper_name = _suggest_helper_name(func_name, hint, i)
        block_src = "\n".join(lines[b_start - 1 : b_end])
        params = _infer_params_for_block(block_src, func_assigned)
        returns = _infer_returns(block_src)
        skeleton = _make_skeleton(
            helper_name, params, returns, lines[b_start - 1 : b_end], ext
        )
        targets.append(
            {
                "helper_name": helper_name,
                "extract_lines": f"{b_start}-{b_end}",
                "params": params,
                "returns": returns,
                "hint": hint,
                "skeleton": skeleton,
            }
        )

    helper_names = ", ".join(str(target["helper_name"]) for target in targets)

    return {
        "function": func_name,
        "function_lines": f"{start}-{end}",
        "helper_module": helper_module,
        "extractions": targets,
        "steps": [
            f"1. Create {helper_module} with extracted helpers",
            f"2. In {Path(file_path).name}, add: from _{stem}_helpers import {helper_names}",
            f"3. Replace lines in '{func_name}' with calls to extracted helpers",
            f"4. Re-run refactoring_suggestions(file_path='{file_path}') to verify",
        ],
    }


# Extract elements from AST: _find_extractable_blocks
def _find_extractable_blocks(
    func_lines: list[str], abs_start: int
) -> list[tuple[int, int, str]]:
    """Identify logical blocks within a function body that can be extracted."""
    blocks: list[tuple[int, int, str]] = []
    n = len(func_lines)
    if n == 0:
        return blocks

    body_indent = _body_indent(func_lines)
    if body_indent <= 0:
        return blocks

    i = 0
    while i < n:
        line = func_lines[i]
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        cur_indent = len(line) - len(line.lstrip())
        if cur_indent < body_indent:
            i += 1
            continue

        if cur_indent == body_indent:
            block_start = i
            hint = _classify_line(stripped)
            j = i + 1
            while j < n:
                next_line = func_lines[j]
                next_stripped = next_line.strip()
                if not next_stripped:
                    j += 1
                    continue
                next_indent = len(next_line) - len(next_line.lstrip())
                if next_indent < body_indent:
                    break
                if next_indent == body_indent:
                    if _is_block_continuation(next_stripped, hint):
                        j += 1
                        continue
                    break
                j += 1

            block_len = j - block_start
            if block_len >= 5:
                blocks.append((abs_start + block_start, abs_start + j - 1, hint))
            i = j
        else:
            i += 1

    blocks.sort(key=lambda b: -(b[1] - b[0]))
    return blocks


# Process: _body_indent
def _body_indent(func_lines: list[str]) -> int:
    for line in func_lines[1:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        return len(line) - len(line.lstrip())
    return 0


# Process: _classify_line
def _classify_line(stripped: str) -> str:
    if stripped.startswith(("if ", "elif ", "else")):
        return "conditional"
    if stripped.startswith(("for ", "while ")):
        return "loop"
    if stripped.startswith(("try:", "with ")):
        return "resource"
    if "=" in stripped and not stripped.startswith(("def ", "class ", "return ")):
        return "computation"
    if stripped.startswith("return "):
        return "result_building"
    return "logic"


# Process: _is_block_continuation
def _is_block_continuation(next_stripped: str, hint: str) -> bool:
    if hint == "resource" and next_stripped.startswith(("except", "else:", "finally:")):
        return True
    if hint == "conditional" and next_stripped.startswith(("elif ", "else:", "else:")):
        return True
    return False


# Process: _suggest_helper_name
def _suggest_helper_name(func_name: str, hint: str, index: int) -> str:
    suffix_map = {
        "conditional": "check_conditions",
        "loop": "process_items",
        "resource": "handle_resource",
        "computation": "compute",
        "result_building": "build_result",
        "logic": "step",
    }
    suffix = suffix_map.get(hint, "step")
    if index == 0:
        return f"_{func_name}_{suffix}"
    return f"_{func_name}_{suffix}_{index + 1}"


# Process: _collect_assigned_names
def _collect_assigned_names(source: str) -> set[str]:
    try:
        tree = ast.parse(textwrap.dedent(source))
    except SyntaxError:
        return set()

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
    return names


_BUILTINS = {
    "self",
    "cls",
    "True",
    "False",
    "None",
    "print",
    "len",
    "range",
    "str",
    "int",
    "list",
    "dict",
    "set",
    "tuple",
    "type",
    "isinstance",
    "hasattr",
    "getattr",
    "setattr",
    "sorted",
    "max",
    "min",
    "enumerate",
    "zip",
    "map",
    "filter",
    "any",
    "all",
    "abs",
    "round",
    "reversed",
}


# Process: _infer_params_for_block
def _infer_params_for_block(
    block_src: str,
    func_assigned: set[str],
) -> list[str]:
    try:
        tree = ast.parse(textwrap.dedent(block_src))
    except SyntaxError:
        return []

    used: set[str] = set()
    block_assigned: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.add(node.id)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            block_assigned.add(node.id)
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            used.add(node.value.id)

    outer_deps = (used - block_assigned) & func_assigned
    params = sorted(outer_deps - _BUILTINS)
    return params[:6]


# Process: _infer_returns
def _infer_returns(block_src: str) -> list[str]:
    try:
        tree = ast.parse(textwrap.dedent(block_src))
    except SyntaxError:
        return []

    # Process: _collect
    def _collect(stmts: list[Any]) -> list[str]:
        assigned: list[str] = []
        for node in stmts:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assigned.append(target.id)
                    elif isinstance(target, ast.Tuple):
                        for elt in target.elts:
                            if isinstance(elt, ast.Name):
                                assigned.append(elt.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                assigned.append(node.target.id)
            elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
                assigned.append(node.target.id)
        return assigned

    top_assigned: list[str] = []
    for node in ast.iter_child_nodes(tree):
        top_assigned.extend(_collect([node]))
        if isinstance(node, ast.Try):
            top_assigned.extend(_collect(node.body))
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            top_assigned.extend(_collect(node.body))
        elif isinstance(node, ast.If):
            top_assigned.extend(_collect(node.body))

    seen: set[str] = set()
    unique: list[str] = []
    # Iterate over a
    for a in top_assigned:
        # Check: a not in seen
        if a not in seen:
            seen.add(a)
            unique.append(a)
    # Return result
    return unique[:4]


# Process: _make_skeleton
def _make_skeleton(
    name: str,
    params: list[str],
    returns: list[str],
    block_lines: list[str],
    ext: str,
) -> str:
    # Check: ext != ".py"
    if ext != ".py":
        # Return result
        return f"// TODO: extract {name}({', '.join(params)})"

    param_str = ", ".join(params)
    dedented = textwrap.dedent("\n".join(block_lines))
    clean = dedented.strip()

    lines = [f"def {name}({param_str}):"]
    # Iterate over bl
    for bl in clean.splitlines():
        lines.append(f"    {bl}")
    # Check: returns
    if returns:
        lines.append(f"    return {', '.join(returns)}")

    # Return result
    return "\n".join(lines)
