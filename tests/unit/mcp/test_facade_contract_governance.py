"""Governance ratchet: detects new duplicate boilerplate in facade test files.

Canonical location for the 4 common facade invariants:
    tests/unit/mcp/test_facade_envelope_contract.py

Any function added to tests/unit/mcp/tools/ whose name matches the 4 duplicate
patterns and is NOT in KNOWN_EXISTING_VIOLATIONS causes this test to fail.

REQ covered: REQ-GR-001, REQ-GR-003
"""

import ast
import re
from pathlib import Path

# Patterns that should live only in test_facade_envelope_contract.py.
# These 4 patterns represent the common facade invariants that are now
# parametrized over all 8 facades in the canonical contract test.
DUPLICATE_PATTERNS = [
    re.compile(r"test_.*envelope_preserved"),
    re.compile(r"test_.*arg_projection_strips_action"),
    re.compile(r"test_.*missing_action_returns_error"),
    re.compile(r"test_.*unknown_action_returns_error"),
]

TOOLS_DIR = Path(__file__).parent / "tools"

# Pre-existing violations present before Queue 3 (ratchet baseline).
# These are NOT new violations — do not add new entries to this set.
# Remove entries as Queue 4+ cleans up the original duplicates.
# Discovered by pre-flight grep on 2026-06-21.
KNOWN_EXISTING_VIOLATIONS: frozenset[tuple[str, str]] = frozenset(
    {
        # test_edit_facade.py
        ("test_edit_facade.py", "test_arg_projection_strips_action_key"),
        ("test_edit_facade.py", "test_missing_action_returns_error_envelope"),
        ("test_edit_facade.py", "test_unknown_action_returns_error_envelope"),
        # test_facade_tool.py
        ("test_facade_tool.py", "test_arg_projection_strips_action_control_key"),
        ("test_facade_tool.py", "test_envelope_preserved_verbatim"),
        ("test_facade_tool.py", "test_missing_action_returns_error_envelope"),
        ("test_facade_tool.py", "test_unknown_action_returns_error_envelope"),
        # test_health_facade.py
        ("test_health_facade.py", "test_envelope_preserved_verbatim"),
        ("test_health_facade.py", "test_missing_action_returns_error_envelope"),
        ("test_health_facade.py", "test_unknown_action_returns_error_envelope"),
        # test_index_facade.py
        ("test_index_facade.py", "test_arg_projection_strips_action_key"),
        ("test_index_facade.py", "test_envelope_preserved_verbatim"),
        ("test_index_facade.py", "test_missing_action_returns_error_envelope"),
        (
            "test_index_facade.py",
            "test_unknown_action_returns_error_with_available_actions",
        ),
        # test_nav_facade.py
        ("test_nav_facade.py", "test_arg_projection_strips_action_from_impact"),
        ("test_nav_facade.py", "test_arg_projection_strips_action_from_navigate"),
        ("test_nav_facade.py", "test_missing_action_returns_error_envelope"),
        ("test_nav_facade.py", "test_unknown_action_returns_error_envelope"),
        # test_project_facade.py
        ("test_project_facade.py", "test_arg_projection_strips_action_key"),
        ("test_project_facade.py", "test_envelope_preserved_verbatim"),
        ("test_project_facade.py", "test_missing_action_returns_error_envelope"),
        (
            "test_project_facade.py",
            "test_unknown_action_returns_error_with_available_actions",
        ),
        # test_structure_facade.py
        ("test_structure_facade.py", "test_arg_projection_strips_action_key"),
        ("test_structure_facade.py", "test_envelope_preserved"),
        ("test_structure_facade.py", "test_missing_action_returns_error_envelope"),
        ("test_structure_facade.py", "test_unknown_action_returns_error_envelope"),
        # test_viz_facade.py
        ("test_viz_facade.py", "test_envelope_preserved_verbatim"),
        ("test_viz_facade.py", "test_missing_action_returns_error_envelope"),
        ("test_viz_facade.py", "test_unknown_action_returns_error_envelope"),
    }
)


def _collect_violations() -> list[tuple[str, str]]:
    """Return list of (filename, func_name) that match duplicate patterns."""
    violations = []
    for path in sorted(TOOLS_DIR.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for pat in DUPLICATE_PATTERNS:
                    if pat.search(node.name):
                        key = (path.name, node.name)
                        if key not in KNOWN_EXISTING_VIOLATIONS:
                            violations.append(key)
                        break
    return violations


def test_no_new_duplicate_boilerplate() -> None:
    """Fail if any NEW duplicate invariant function is added to tools/.

    Uses KNOWN_EXISTING_VIOLATIONS as the ratchet baseline: any function
    in tests/unit/mcp/tools/ that matches one of the 4 duplicate patterns
    AND is not in the baseline set is reported as a new violation.

    This prevents re-introduction of the 4 common facade invariants that
    are now canonically tested in test_facade_envelope_contract.py.
    """
    new_violations = _collect_violations()
    if new_violations:
        lines = "\n".join(f"  {f}: {fn}" for f, fn in sorted(new_violations))
        raise AssertionError(
            "New duplicate facade boilerplate detected in tests/unit/mcp/tools/.\n"
            "Move these invariants to test_facade_envelope_contract.py instead:\n"
            f"{lines}"
        )
