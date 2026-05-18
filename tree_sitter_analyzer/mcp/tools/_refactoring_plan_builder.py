#!/usr/bin/env python3
"""
Precise extraction plan builder for refactoring suggestions.

Generates actionable extraction plans with exact line ranges, helper names,
inferred parameters/returns, and code skeletons for long functions.
"""

import ast
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExtractionTargetContext:
    """Shared inputs for building extraction targets."""

    lines: list[str]
    func_name: str
    func_assigned: set[str]
    ext: str


# Build response or data structure: build_precise_plans
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
    helper_stem = _helper_module_stem(file_path)
    helper_module = _helper_module_path(file_path, helper_stem)

    func_src = "\n".join(func_lines)
    func_assigned = _collect_assigned_names(func_src)

    targets = _build_extraction_targets(blocks, lines, func_name, func_assigned, ext)

    helper_names = ", ".join(str(target["helper_name"]) for target in targets)
    helper_import = _helper_import_statement(file_path, helper_stem, helper_names)

    return {
        "function": func_name,
        "function_lines": f"{start}-{end}",
        "helper_module": helper_module,
        "extractions": targets,
        "steps": [
            f"1. Create {helper_module} with extracted helpers",
            f"2. In {Path(file_path).name}, add: {helper_import}",
            f"3. Replace lines in '{func_name}' with calls to extracted helpers",
            f"4. Re-run refactoring_suggestions(file_path='{file_path}') to verify",
        ],
    }


def _build_extraction_targets(
    blocks: list[tuple[int, int, str]],
    lines: list[str],
    func_name: str,
    func_assigned: set[str],
    ext: str,
) -> list[dict[str, Any]]:
    """Build extraction target rows for the largest logical blocks."""
    context = ExtractionTargetContext(lines, func_name, func_assigned, ext)
    return [
        _build_extraction_target(index, block, context)
        for index, block in enumerate(blocks[:3])
    ]


def _build_extraction_target(
    index: int,
    block: tuple[int, int, str],
    context: ExtractionTargetContext,
) -> dict[str, Any]:
    """Build one extraction target with inferred signature details."""
    b_start, b_end, hint = block
    helper_name = _suggest_helper_name(context.func_name, hint, index)
    block_lines = context.lines[b_start - 1 : b_end]
    block_src = "\n".join(block_lines)
    params = _infer_params_for_block(block_src, context.func_assigned)
    returns = _infer_returns(block_src)
    return {
        "helper_name": helper_name,
        "extract_lines": f"{b_start}-{b_end}",
        "params": params,
        "returns": returns,
        "hint": hint,
        "skeleton": _make_skeleton(
            helper_name, params, returns, block_lines, context.ext
        ),
    }


def _helper_module_stem(file_path: str) -> str:
    """Return a single-underscore helper module stem for a source file."""
    source_stem = Path(file_path).stem
    base_stem = source_stem.lstrip("_") or source_stem
    return f"_{base_stem}_helpers"


def _helper_module_path(file_path: str, helper_stem: str) -> str:
    """Return the sibling helper module path shown in extraction plans."""
    parent = Path(file_path).parent
    helper_file = f"{helper_stem}.py"
    if str(parent) == ".":
        return helper_file
    return str(parent / helper_file)


def _helper_import_statement(
    file_path: str,
    helper_stem: str,
    helper_names: str,
) -> str:
    """Return a copy-pasteable sibling helper import for a source file."""
    module_name = helper_stem
    if (Path(file_path).parent / "__init__.py").exists():
        module_name = f".{helper_stem}"
    return f"from {module_name} import {helper_names}"


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
        block, next_index = _next_extractable_block(func_lines, i, n, body_indent)
        if block:
            block_start, block_end, hint = block
            blocks.append((abs_start + block_start, abs_start + block_end, hint))
        i = next_index

    blocks.sort(key=lambda b: -(b[1] - b[0]))
    return blocks


def _next_extractable_block(
    func_lines: list[str],
    index: int,
    total_lines: int,
    body_indent: int,
) -> tuple[tuple[int, int, str] | None, int]:
    """Return the next extractable block and the following scan index."""
    line = func_lines[index]
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None, index + 1

    cur_indent = len(line) - len(line.lstrip())
    if cur_indent != body_indent:
        return None, index + 1

    hint = _classify_line(stripped)
    block_end_exclusive = _scan_block_end(
        func_lines,
        index + 1,
        total_lines,
        body_indent,
        hint,
    )
    if block_end_exclusive - index < 5:
        return None, block_end_exclusive
    return (index, block_end_exclusive - 1, hint), block_end_exclusive


def _scan_block_end(
    func_lines: list[str],
    index: int,
    total_lines: int,
    body_indent: int,
    hint: str,
) -> int:
    """Return the exclusive end index for one top-level logical block."""
    current = index
    while current < total_lines:
        next_line = func_lines[current]
        next_stripped = next_line.strip()
        if not next_stripped:
            current += 1
            continue

        next_indent = len(next_line) - len(next_line.lstrip())
        if next_indent < body_indent:
            break
        if next_indent == body_indent and not _is_block_continuation(
            next_stripped, hint
        ):
            break
        current += 1
    return current


def _body_indent(func_lines: list[str]) -> int:
    for line in func_lines[1:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        return len(line) - len(line.lstrip())
    return 0


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


def _is_block_continuation(next_stripped: str, hint: str) -> bool:
    if hint == "resource" and next_stripped.startswith(("except", "else:", "finally:")):
        return True
    if hint == "conditional" and next_stripped.startswith(("elif ", "else:", "else:")):
        return True
    return False


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
    base_name = func_name.lstrip("_") or func_name
    if index == 0:
        return f"_{base_name}_{suffix}"
    return f"_{base_name}_{suffix}_{index + 1}"


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


def _infer_returns(block_src: str) -> list[str]:
    try:
        tree = ast.parse(textwrap.dedent(block_src))
    except SyntaxError:
        return []

    top_assigned: list[str] = []
    for node in ast.iter_child_nodes(tree):
        top_assigned.extend(_assigned_names_from_statement_and_body(node))
    return _unique_names(top_assigned)[:4]


def _assigned_names_from_statement_and_body(node: ast.AST) -> list[str]:
    """Return names assigned by a statement and selected direct child bodies."""
    assigned = _assigned_names_from_statement(node)
    for body in _nested_bodies_for_return_inference(node):
        assigned.extend(_assigned_names_from_statements(body))
    return assigned


def _assigned_names_from_statements(statements: list[ast.stmt]) -> list[str]:
    """Return names assigned by a list of direct statements."""
    assigned: list[str] = []
    for statement in statements:
        assigned.extend(_assigned_names_from_statement(statement))
    return assigned


def _assigned_names_from_statement(node: ast.AST) -> list[str]:
    """Return direct assignment targets for one AST statement."""
    if isinstance(node, ast.Assign):
        return _assigned_names_from_targets(node.targets)
    if isinstance(node, ast.AnnAssign):
        return _assigned_names_from_target(node.target)
    if isinstance(node, ast.AugAssign):
        return _assigned_names_from_target(node.target)
    return []


def _assigned_names_from_targets(targets: list[ast.expr]) -> list[str]:
    """Return assigned names from assignment targets."""
    names: list[str] = []
    for target in targets:
        names.extend(_assigned_names_from_target(target))
    return names


def _assigned_names_from_target(target: ast.expr) -> list[str]:
    """Return assigned names from one target expression."""
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, ast.Tuple):
        return [elt.id for elt in target.elts if isinstance(elt, ast.Name)]
    return []


def _nested_bodies_for_return_inference(node: ast.AST) -> list[list[ast.stmt]]:
    """Return direct child bodies whose assignments should become returns."""
    if isinstance(node, ast.Try):
        return [node.body]
    if isinstance(node, (ast.With, ast.AsyncWith)):
        return [node.body]
    if isinstance(node, ast.If):
        return [node.body]
    return []


def _unique_names(names: list[str]) -> list[str]:
    """Return names without duplicates while preserving order."""
    seen: set[str] = set()
    unique: list[str] = []
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        unique.append(name)
    return unique


def _make_skeleton(
    name: str,
    params: list[str],
    returns: list[str],
    block_lines: list[str],
    ext: str,
) -> str:
    if ext != ".py":
        return f"// TODO: extract {name}({', '.join(params)})"

    param_str = ", ".join(params)
    dedented = textwrap.dedent("\n".join(block_lines))
    clean = dedented.strip()

    lines = [f"def {name}({param_str}):"]
    for bl in clean.splitlines():
        lines.append(f"    {bl}")
    if returns:
        lines.append(f"    return {', '.join(returns)}")

    return "\n".join(lines)
