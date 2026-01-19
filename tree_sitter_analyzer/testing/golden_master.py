#!/usr/bin/env python3
"""
Golden Master Utilities

Provides utilities for loading, saving, and comparing golden master files
for regression testing of MCP tools.
"""

import difflib
import json
from pathlib import Path
from typing import Any

# Default golden master directory
GOLDEN_MASTER_DIR = Path(__file__).parent.parent.parent / "tests" / "golden_masters"


def get_golden_master_path(
    tool_name: str,
    category: str = "mcp",
    base_dir: Path | None = None,
) -> Path:
    """
    Get the path to a golden master file.

    Args:
        tool_name: Name of the MCP tool (e.g., "check_code_scale")
        category: Category subdirectory (default: "mcp")
        base_dir: Base directory for golden masters (default: tests/golden_masters)

    Returns:
        Path to the golden master JSON file
    """
    if base_dir is None:
        base_dir = GOLDEN_MASTER_DIR
    return base_dir / category / f"{tool_name}.json"


def load_golden_master(
    tool_name: str,
    category: str = "mcp",
    base_dir: Path | None = None,
) -> dict[str, Any]:
    """
    Load a golden master file.

    Args:
        tool_name: Name of the MCP tool
        category: Category subdirectory
        base_dir: Base directory for golden masters

    Returns:
        Parsed JSON content of the golden master

    Raises:
        FileNotFoundError: If golden master doesn't exist
        json.JSONDecodeError: If file is not valid JSON
    """
    path = get_golden_master_path(tool_name, category, base_dir)
    if not path.exists():
        raise FileNotFoundError(f"Golden master not found: {path}")

    with open(path, encoding="utf-8") as f:
        result: dict[str, Any] = json.load(f)
        return result


def save_golden_master(
    data: dict[str, Any],
    tool_name: str,
    category: str = "mcp",
    base_dir: Path | None = None,
) -> Path:
    """
    Save a golden master file.

    Args:
        data: Data to save as golden master
        tool_name: Name of the MCP tool
        category: Category subdirectory
        base_dir: Base directory for golden masters

    Returns:
        Path to the saved golden master file
    """
    path = get_golden_master_path(tool_name, category, base_dir)

    # Ensure directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)

    return path


def generate_diff(
    actual: dict[str, Any],
    expected: dict[str, Any],
    context_lines: int = 3,
) -> str:
    """
    Generate a human-readable diff between actual and expected output.

    Args:
        actual: Actual output from MCP tool
        expected: Expected output from golden master
        context_lines: Number of context lines around changes

    Returns:
        Unified diff string, empty if outputs match
    """
    actual_json = json.dumps(actual, indent=2, sort_keys=True).splitlines(keepends=True)
    expected_json = json.dumps(expected, indent=2, sort_keys=True).splitlines(
        keepends=True
    )

    diff_lines = list(
        difflib.unified_diff(
            expected_json,
            actual_json,
            fromfile="expected (golden master)",
            tofile="actual (current output)",
            n=context_lines,
        )
    )

    return "".join(diff_lines)


def compare_golden_master(
    actual: dict[str, Any],
    tool_name: str,
    category: str = "mcp",
    base_dir: Path | None = None,
) -> tuple[bool, str]:
    """
    Compare actual output against golden master.

    Args:
        actual: Actual output from MCP tool
        tool_name: Name of the MCP tool
        category: Category subdirectory
        base_dir: Base directory for golden masters

    Returns:
        Tuple of (matches, diff_string)
        - matches: True if outputs are identical
        - diff_string: Empty if matches, otherwise contains the diff
    """
    try:
        expected = load_golden_master(tool_name, category, base_dir)
    except FileNotFoundError:
        return False, f"Golden master not found for {tool_name}"

    if actual == expected:
        return True, ""

    diff = generate_diff(actual, expected)
    return False, diff


def update_golden_master_if_changed(
    actual: dict[str, Any],
    tool_name: str,
    category: str = "mcp",
    base_dir: Path | None = None,
    force: bool = False,
) -> tuple[bool, str]:
    """
    Update golden master if it differs from actual output.

    Args:
        actual: Actual output from MCP tool
        tool_name: Name of the MCP tool
        category: Category subdirectory
        base_dir: Base directory for golden masters
        force: If True, update even if golden master exists and matches

    Returns:
        Tuple of (updated, message)
        - updated: True if golden master was updated
        - message: Description of what happened
    """
    path = get_golden_master_path(tool_name, category, base_dir)

    if not path.exists():
        save_golden_master(actual, tool_name, category, base_dir)
        return True, f"Created new golden master: {path}"

    if not force:
        matches, diff = compare_golden_master(actual, tool_name, category, base_dir)
        if matches:
            return False, f"Golden master unchanged: {path}"

    save_golden_master(actual, tool_name, category, base_dir)
    return True, f"Updated golden master: {path}"


def list_golden_masters(
    category: str = "mcp",
    base_dir: Path | None = None,
) -> list[str]:
    """
    List all available golden masters in a category.

    Args:
        category: Category subdirectory
        base_dir: Base directory for golden masters

    Returns:
        List of tool names with golden masters
    """
    if base_dir is None:
        base_dir = GOLDEN_MASTER_DIR

    category_dir = base_dir / category
    if not category_dir.exists():
        return []

    return [p.stem for p in category_dir.glob("*.json")]
