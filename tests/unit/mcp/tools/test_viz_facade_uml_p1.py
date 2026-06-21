"""Integration test: viz facade passes file_path/class_name to inner UML tool.

Root cause fix for viz-08 (RFC-0015): the facade's _project_args strips params
not declared in the inner tool's schema. Before P1-A, file_path and class_name
were not declared → silently dropped → always whole-project diagram.
"""

# ---------------------------------------------------------------------------
# INVARIANT DELEGATION NOTICE
# The following 4 common facade invariants are tested canonically in:
#   tests/unit/mcp/test_facade_envelope_contract.py
#
# Delegated invariants (do NOT add new duplicates here):
#   - envelope preserved       (verdict / agent_summary verbatim pass-through)
#   - arg projection           (action key stripped before reaching inner tool)
#   - missing action error     (success=False, verdict in {ERROR, NOT_FOUND})
#   - unknown action error     (success=False, available_actions listed)
#
# Facade-specific tests that remain in this file:
#   - viz facade passes file_path and class_name to inner UML tool
#   - _project_args schema compliance for uml_tool (RFC-0015 P1-A regression)
# ---------------------------------------------------------------------------

from __future__ import annotations


def test_file_path_not_dropped_after_fix() -> None:
    """file_path declared in uml_tool schema → passes through _project_args."""
    from tree_sitter_analyzer.mcp.tools.facade_tool import FacadeTool
    from tree_sitter_analyzer.mcp.tools.viz_facade import build_viz_facade

    facade = build_viz_facade("/repo")
    inner = facade.action_map["uml"]
    projected = FacadeTool._project_args(
        facade,
        inner,
        {"action": "uml", "diagram": "class", "file_path": "src/foo.py"},
    )
    assert "file_path" in projected
    assert projected["file_path"] == "src/foo.py"


def test_class_name_not_dropped_after_fix() -> None:
    """class_name declared in uml_tool schema → passes through _project_args."""
    from tree_sitter_analyzer.mcp.tools.facade_tool import FacadeTool
    from tree_sitter_analyzer.mcp.tools.viz_facade import build_viz_facade

    facade = build_viz_facade("/repo")
    inner = facade.action_map["uml"]
    projected = FacadeTool._project_args(
        facade,
        inner,
        {"action": "uml", "diagram": "class", "class_name": "MyClass"},
    )
    assert "class_name" in projected
    assert projected["class_name"] == "MyClass"


def test_include_tests_not_dropped() -> None:
    """include_tests declared in uml_tool schema → passes through _project_args."""
    from tree_sitter_analyzer.mcp.tools.facade_tool import FacadeTool
    from tree_sitter_analyzer.mcp.tools.viz_facade import build_viz_facade

    facade = build_viz_facade("/repo")
    inner = facade.action_map["uml"]
    projected = FacadeTool._project_args(
        facade,
        inner,
        {"action": "uml", "diagram": "class", "include_tests": True},
    )
    assert "include_tests" in projected
    assert projected["include_tests"] is True
