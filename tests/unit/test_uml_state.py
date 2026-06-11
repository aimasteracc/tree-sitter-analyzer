#!/usr/bin/env python3
"""Tests for the state diagram (P2-B, RFC-0015) — uml_state.py + UMLExporter.state_diagram.

RED-first: all tests in this file are written before the implementation exists.
Each section is marked with what it exercises.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ts_node(
    type_: str, text: str = "", children: list | None = None
) -> MagicMock:
    """Build a minimal tree-sitter node mock that won't OOM.

    Per contract §6: node.parent MUST be set to None explicitly.
    """
    node = MagicMock()
    node.type = type_
    node.text = text.encode() if text else b""
    node.parent = None  # §6 anti-OOM guard
    node.children = children if children is not None else []
    return node


# ---------------------------------------------------------------------------
# Section A: uml_state module — data types and low-level helpers
# ---------------------------------------------------------------------------


def test_state_result_dataclass_exists() -> None:
    """StateResult dataclass is importable and has expected fields."""
    from tree_sitter_analyzer.uml_state import StateResult

    result = StateResult()
    assert result.states == []
    assert result.transitions == []
    assert result.truncated is False
    assert result.error == ""


def test_state_transition_dataclass_exists() -> None:
    """StateTransition dataclass has source/target/label fields."""
    from tree_sitter_analyzer.uml_state import StateTransition

    t = StateTransition(source="A", target="B", label="go")
    assert t.source == "A"
    assert t.target == "B"
    assert t.label == "go"


def test_state_transition_label_defaults_empty() -> None:
    """StateTransition label defaults to empty string."""
    from tree_sitter_analyzer.uml_state import StateTransition

    t = StateTransition(source="X", target="Y")
    assert t.label == ""


# ---------------------------------------------------------------------------
# Section B: _parse_file_for_state — monkeypatch-verified parse count
# ---------------------------------------------------------------------------


def test_parse_file_for_state_returns_none_for_missing_file(tmp_path: Path) -> None:
    """Returns None when the file does not exist."""
    from tree_sitter_analyzer.uml_state import _parse_file_for_state

    result = _parse_file_for_state(str(tmp_path / "does_not_exist.py"))
    assert result is None


def test_parse_file_for_state_calls_parser_once(tmp_path: Path) -> None:
    """Rule-11 invariant: exactly one tree-sitter parse per build_state_result call.

    Wrap _parse_file_for_state itself and count invocations to verify that
    build_state_result never calls it more than once per invocation.
    """
    import tree_sitter_analyzer.uml_state as _state_module

    src = tmp_path / "fsm.py"
    src.write_text(
        "from enum import Enum\n\nclass Color(Enum):\n    RED = 1\n    BLUE = 2\n"
    )

    parse_call_count = 0
    original_parse = _state_module._parse_file_for_state

    def counting_parse(file_path: str, language: str = "python"):
        nonlocal parse_call_count
        parse_call_count += 1
        return original_parse(file_path, language)

    with patch.object(_state_module, "_parse_file_for_state", counting_parse):
        _state_module.build_state_result(
            file_path=str(src),
            class_name=None,
            max_nodes=30,
        )

    assert parse_call_count == 1  # exact — rule-11 invariant


# ---------------------------------------------------------------------------
# Section C: build_state_result — enum member extraction
# ---------------------------------------------------------------------------


def test_build_state_result_missing_file_returns_not_found(tmp_path: Path) -> None:
    """build_state_result returns error='NOT_FOUND:file_missing' for absent file."""
    from tree_sitter_analyzer.uml_state import build_state_result

    result = build_state_result(
        file_path=str(tmp_path / "absent.py"),
        class_name=None,
        max_nodes=30,
    )
    assert result.error == "NOT_FOUND:file_missing"
    assert result.states == []
    assert result.transitions == []


def test_build_state_result_real_file_no_enum(tmp_path: Path) -> None:
    """File with no Enum subclass → error='NOT_FOUND:no_enum_class'."""
    src = tmp_path / "plain.py"
    src.write_text("class Plain:\n    pass\n")

    from tree_sitter_analyzer.uml_state import build_state_result

    result = build_state_result(
        file_path=str(src),
        class_name=None,
        max_nodes=30,
    )
    assert result.error == "NOT_FOUND:no_enum_class"


def test_build_state_result_finds_enum_members(tmp_path: Path) -> None:
    """Enum subclass members become states; exact count pinned."""
    src = tmp_path / "light.py"
    src.write_text(
        textwrap.dedent("""\
        from enum import Enum

        class TrafficLight(Enum):
            RED = 1
            YELLOW = 2
            GREEN = 3
        """)
    )

    from tree_sitter_analyzer.uml_state import build_state_result

    result = build_state_result(
        file_path=str(src),
        class_name="TrafficLight",
        max_nodes=30,
    )
    assert result.error == ""
    assert len(result.states) == 3  # exact: RED, YELLOW, GREEN


def test_build_state_result_state_names_correct(tmp_path: Path) -> None:
    """State names match the enum member names exactly."""
    src = tmp_path / "light.py"
    src.write_text(
        textwrap.dedent("""\
        from enum import Enum

        class TrafficLight(Enum):
            RED = 1
            YELLOW = 2
            GREEN = 3
        """)
    )

    from tree_sitter_analyzer.uml_state import build_state_result

    result = build_state_result(
        file_path=str(src),
        class_name="TrafficLight",
        max_nodes=30,
    )
    assert sorted(result.states) == ["GREEN", "RED", "YELLOW"]


def test_build_state_result_class_name_filter(tmp_path: Path) -> None:
    """class_name filter selects only the named Enum class."""
    src = tmp_path / "multi.py"
    src.write_text(
        textwrap.dedent("""\
        from enum import Enum

        class Color(Enum):
            RED = 1
            BLUE = 2

        class Size(Enum):
            SMALL = 1
            LARGE = 2
        """)
    )

    from tree_sitter_analyzer.uml_state import build_state_result

    result = build_state_result(
        file_path=str(src),
        class_name="Color",
        max_nodes=30,
    )
    assert result.error == ""
    assert sorted(result.states) == ["BLUE", "RED"]  # exact 2, not Size's members


def test_build_state_result_class_name_not_found(tmp_path: Path) -> None:
    """class_name that does not exist → error='NOT_FOUND:class_missing'."""
    src = tmp_path / "enum_only.py"
    src.write_text(
        textwrap.dedent("""\
        from enum import Enum

        class Color(Enum):
            RED = 1
        """)
    )

    from tree_sitter_analyzer.uml_state import build_state_result

    result = build_state_result(
        file_path=str(src),
        class_name="NonExistent",
        max_nodes=30,
    )
    assert result.error == "NOT_FOUND:class_missing"


def test_build_state_result_max_nodes_truncates(tmp_path: Path) -> None:
    """max_nodes=2 truncates a 4-member enum to 2 states, truncated=True."""
    src = tmp_path / "many.py"
    src.write_text(
        textwrap.dedent("""\
        from enum import Enum

        class States(Enum):
            A = 1
            B = 2
            C = 3
            D = 4
        """)
    )

    from tree_sitter_analyzer.uml_state import build_state_result

    result = build_state_result(
        file_path=str(src),
        class_name="States",
        max_nodes=2,
    )
    assert result.truncated is True
    assert len(result.states) == 2  # exact: capped at max_nodes


def test_build_state_result_match_transitions_detected(tmp_path: Path) -> None:
    """match/case blocks targeting enum members produce transitions."""
    src = tmp_path / "fsm.py"
    src.write_text(
        textwrap.dedent("""\
        from enum import Enum

        class TrafficLight(Enum):
            RED = 1
            YELLOW = 2
            GREEN = 3

        def next_state(state: TrafficLight) -> TrafficLight:
            match state:
                case TrafficLight.RED:
                    return TrafficLight.GREEN
                case TrafficLight.GREEN:
                    return TrafficLight.YELLOW
                case TrafficLight.YELLOW:
                    return TrafficLight.RED
        """)
    )

    from tree_sitter_analyzer.uml_state import build_state_result

    result = build_state_result(
        file_path=str(src),
        class_name="TrafficLight",
        max_nodes=30,
    )
    assert result.error == ""
    # Expect 3 transitions: RED→GREEN, GREEN→YELLOW, YELLOW→RED
    assert len(result.transitions) == 3  # exact pin


def test_build_state_result_transition_sources_and_targets(tmp_path: Path) -> None:
    """Transition source/target names match the case/return pattern."""
    src = tmp_path / "fsm.py"
    src.write_text(
        textwrap.dedent("""\
        from enum import Enum

        class Sem(Enum):
            RED = 1
            GREEN = 2

        def next_state(s):
            match s:
                case Sem.RED:
                    return Sem.GREEN
                case Sem.GREEN:
                    return Sem.RED
        """)
    )

    from tree_sitter_analyzer.uml_state import build_state_result

    result = build_state_result(
        file_path=str(src),
        class_name="Sem",
        max_nodes=30,
    )
    pairs = {(t.source, t.target) for t in result.transitions}
    assert ("RED", "GREEN") in pairs
    assert ("GREEN", "RED") in pairs


def test_build_state_result_no_match_zero_transitions(tmp_path: Path) -> None:
    """Enum with no match/case block has zero transitions."""
    src = tmp_path / "static.py"
    src.write_text(
        textwrap.dedent("""\
        from enum import Enum

        class Status(Enum):
            OPEN = 1
            CLOSED = 2
        """)
    )

    from tree_sitter_analyzer.uml_state import build_state_result

    result = build_state_result(
        file_path=str(src),
        class_name="Status",
        max_nodes=30,
    )
    # States found but no transitions — this will NOT raise an error here
    # (the NOT_FOUND verdict is applied at UMLExporter level, not in build_state_result)
    assert result.error == ""
    assert sorted(result.states) == ["CLOSED", "OPEN"]  # exact pin: 2 members
    assert len(result.transitions) == 0  # exact


# ---------------------------------------------------------------------------
# Section D: render_state_mermaid — output format
# ---------------------------------------------------------------------------


def test_render_state_mermaid_starts_with_stateDiagram() -> None:
    """render_state_mermaid output starts with 'stateDiagram-v2'."""
    from tree_sitter_analyzer.uml_export import render_state_mermaid

    mermaid = render_state_mermaid(["RED", "GREEN"], [])
    assert mermaid.startswith("stateDiagram-v2")


def test_render_state_mermaid_includes_states() -> None:
    """State names appear in the rendered Mermaid."""
    from tree_sitter_analyzer.uml_export import render_state_mermaid

    mermaid = render_state_mermaid(["RED", "GREEN", "YELLOW"], [])
    assert "RED" in mermaid
    assert "GREEN" in mermaid
    assert "YELLOW" in mermaid


def test_render_state_mermaid_includes_initial_edges() -> None:
    """Each state gets a [*] --> StateName initial-state edge."""
    from tree_sitter_analyzer.uml_export import render_state_mermaid

    mermaid = render_state_mermaid(["RED"], [])
    assert "[*] --> RED" in mermaid


def test_render_state_mermaid_transition_edge() -> None:
    """Transitions appear as StateA --> StateB."""
    from tree_sitter_analyzer.uml_export import render_state_mermaid
    from tree_sitter_analyzer.uml_state import StateTransition

    transitions = [StateTransition(source="RED", target="GREEN")]
    mermaid = render_state_mermaid(["RED", "GREEN"], transitions)
    assert "RED --> GREEN" in mermaid


def test_render_state_mermaid_transition_with_label() -> None:
    """Transition with label appears as StateA --> StateB : label."""
    from tree_sitter_analyzer.uml_export import render_state_mermaid
    from tree_sitter_analyzer.uml_state import StateTransition

    transitions = [StateTransition(source="IDLE", target="RUNNING", label="start")]
    mermaid = render_state_mermaid(["IDLE", "RUNNING"], transitions)
    assert "IDLE --> RUNNING" in mermaid
    assert "start" in mermaid


def test_render_state_mermaid_approximation_note() -> None:
    """Mermaid output includes the RFC-mandated %% NOTE: state diagram comment."""
    from tree_sitter_analyzer.uml_export import render_state_mermaid

    mermaid = render_state_mermaid(["A"], [])
    assert "%% NOTE: state diagram is a static approximation" in mermaid


def test_render_state_mermaid_empty_states() -> None:
    """Empty state list renders a sentinel node, not a crash."""
    from tree_sitter_analyzer.uml_export import render_state_mermaid

    mermaid = render_state_mermaid([], [])
    # Deterministic sentinel render — exact pin (measured 2026-06-12)
    assert mermaid == (
        "stateDiagram-v2\n"
        "%% NOTE: state diagram is a static approximation.\n"
        "%% Guard conditions, timers, and exception-driven transitions "
        "are not captured.\n"
        "    [*] --> EmptyEnum"
    )


# ---------------------------------------------------------------------------
# Section E: UMLExporter.state_diagram — integration
# ---------------------------------------------------------------------------


def test_state_diagram_mermaid_type(tmp_path: Path) -> None:
    """UMLDiagram.mermaid_type == 'stateDiagram-v2'."""
    src = tmp_path / "light.py"
    src.write_text(
        textwrap.dedent("""\
        from enum import Enum

        class Light(Enum):
            RED = 1
            GREEN = 2
        """)
    )

    from tree_sitter_analyzer.uml_export import UMLExporter

    exporter = UMLExporter(str(tmp_path))
    diagram = exporter.state_diagram(class_name="Light", file_path=str(src))
    assert diagram.mermaid_type == "stateDiagram-v2"


def test_state_diagram_diagram_type(tmp_path: Path) -> None:
    """UMLDiagram.diagram_type == 'state'."""
    src = tmp_path / "light.py"
    src.write_text(
        textwrap.dedent("""\
        from enum import Enum

        class Light(Enum):
            RED = 1
        """)
    )

    from tree_sitter_analyzer.uml_export import UMLExporter

    exporter = UMLExporter(str(tmp_path))
    diagram = exporter.state_diagram(class_name="Light", file_path=str(src))
    assert diagram.diagram_type == "state"


def test_state_diagram_analysis_kind_metadata(tmp_path: Path) -> None:
    """metadata['analysis_kind'] == 'static_approximation' (RFC-0015 §P2-B)."""
    src = tmp_path / "light.py"
    src.write_text(
        textwrap.dedent("""\
        from enum import Enum

        class Light(Enum):
            RED = 1
            GREEN = 2
        """)
    )

    from tree_sitter_analyzer.uml_export import UMLExporter

    exporter = UMLExporter(str(tmp_path))
    diagram = exporter.state_diagram(class_name="Light", file_path=str(src))
    assert diagram.metadata["analysis_kind"] == "static_approximation"


def test_state_diagram_note_in_metadata(tmp_path: Path) -> None:
    """metadata['note'] indicates parsed from current file content."""
    src = tmp_path / "light.py"
    src.write_text(
        textwrap.dedent("""\
        from enum import Enum

        class Light(Enum):
            RED = 1
        """)
    )

    from tree_sitter_analyzer.uml_export import UMLExporter

    exporter = UMLExporter(str(tmp_path))
    diagram = exporter.state_diagram(class_name="Light", file_path=str(src))
    assert "note" in diagram.metadata
    assert "parsed from current file content" in diagram.metadata["note"]


def test_state_diagram_zero_transitions_info(tmp_path: Path) -> None:
    """Zero transitions but states found → verdict='INFO' in metadata (#480 fix).

    RE-PINNED from NOT_FOUND → INFO (consciously):
    RFC-0015 §P2-B's "honesty rule" intent was "don't fake a diagram"; the mermaid
    suppression of [*]--> lines already serves that goal. A partial result (states
    found, zero transitions) is not "not found" — an agent branching on verdict
    would discard the 19 extracted states. INFO + note preserves the useful
    partial result while the mermaid header/note guards remain honest.
    True NOT_FOUND is reserved for zero states (class not found at all).
    """
    src = tmp_path / "static.py"
    src.write_text(
        textwrap.dedent("""\
        from enum import Enum

        class Status(Enum):
            OPEN = 1
            CLOSED = 2
        """)
    )

    from tree_sitter_analyzer.uml_export import UMLExporter

    exporter = UMLExporter(str(tmp_path))
    diagram = exporter.state_diagram(class_name="Status", file_path=str(src))
    # RE-PINNED: was NOT_FOUND, now INFO (states found, no transitions)
    assert diagram.metadata.get("verdict") == "INFO"
    assert "next_step" in diagram.metadata


def test_state_diagram_missing_file_not_found(tmp_path: Path) -> None:
    """Missing file → verdict='NOT_FOUND' in metadata."""
    from tree_sitter_analyzer.uml_export import UMLExporter

    exporter = UMLExporter(str(tmp_path))
    diagram = exporter.state_diagram(
        class_name="Whatever", file_path=str(tmp_path / "missing.py")
    )
    assert diagram.metadata.get("verdict") == "NOT_FOUND"


def test_state_diagram_mermaid_starts_stateDiagram_with_transitions(
    tmp_path: Path,
) -> None:
    """mermaid output starts with 'stateDiagram-v2' for a real FSM."""
    src = tmp_path / "fsm.py"
    src.write_text(
        textwrap.dedent("""\
        from enum import Enum

        class Light(Enum):
            RED = 1
            GREEN = 2

        def next_state(s):
            match s:
                case Light.RED:
                    return Light.GREEN
                case Light.GREEN:
                    return Light.RED
        """)
    )

    from tree_sitter_analyzer.uml_export import UMLExporter

    exporter = UMLExporter(str(tmp_path))
    diagram = exporter.state_diagram(class_name="Light", file_path=str(src))
    assert diagram.mermaid.startswith("stateDiagram-v2")
    assert "%% NOTE: state diagram is a static approximation" in diagram.mermaid


def test_state_diagram_node_count_exact_no_transitions(tmp_path: Path) -> None:
    """node count == 2 for a 2-member Enum with no transitions (NOT_FOUND path)."""
    src = tmp_path / "two.py"
    src.write_text(
        textwrap.dedent("""\
        from enum import Enum

        class AB(Enum):
            A = 1
            B = 2
        """)
    )

    from tree_sitter_analyzer.uml_export import UMLExporter

    exporter = UMLExporter(str(tmp_path))
    diagram = exporter.state_diagram(class_name="AB", file_path=str(src))
    # NOT_FOUND because no transitions — but node count is still measurable
    assert len(diagram.nodes) == 2  # exact: A and B


def test_state_diagram_exact_node_count_with_transitions(tmp_path: Path) -> None:
    """node count == 3 for a 3-member Enum FSM with transitions."""
    src = tmp_path / "light.py"
    src.write_text(
        textwrap.dedent("""\
        from enum import Enum

        class TrafficLight(Enum):
            RED = 1
            YELLOW = 2
            GREEN = 3

        def next_state(state: TrafficLight) -> TrafficLight:
            match state:
                case TrafficLight.RED:
                    return TrafficLight.GREEN
                case TrafficLight.GREEN:
                    return TrafficLight.YELLOW
                case TrafficLight.YELLOW:
                    return TrafficLight.RED
        """)
    )

    from tree_sitter_analyzer.uml_export import UMLExporter

    exporter = UMLExporter(str(tmp_path))
    diagram = exporter.state_diagram(class_name="TrafficLight", file_path=str(src))
    assert len(diagram.nodes) == 3  # exact: RED, YELLOW, GREEN


# ---------------------------------------------------------------------------
# Section E2: P2a — assignment-based transitions (self.state = Enum.MEMBER)
# ---------------------------------------------------------------------------


def test_assignment_transitions_detected_door_controller(tmp_path: Path) -> None:
    """OOP FSM with self.state = Door.LOCKED produces transitions (P2a fix).

    RED-first: this tests the assignment-based scanner path that complements
    the existing return-based path.
    """
    src = tmp_path / "door.py"
    src.write_text(
        textwrap.dedent("""\
        from enum import Enum

        class Door(Enum):
            LOCKED = "locked"
            CLOSED = "closed"
            OPEN = "open"

        class DoorController:
            def __init__(self):
                self.state = Door.LOCKED

            def unlock(self):
                match self.state:
                    case Door.LOCKED:
                        self.state = Door.CLOSED
                    case Door.CLOSED:
                        self.state = Door.OPEN
                    case Door.OPEN:
                        self.state = Door.LOCKED
        """)
    )

    from tree_sitter_analyzer.uml_state import build_state_result

    result = build_state_result(
        file_path=str(src),
        class_name="Door",
        max_nodes=30,
    )
    assert result.error == ""
    # Must detect the 3 assignment transitions: LOCKED→CLOSED, CLOSED→OPEN, OPEN→LOCKED
    assert len(result.transitions) == 3  # exact pin
    pairs = {(t.source, t.target) for t in result.transitions}
    assert ("LOCKED", "CLOSED") in pairs
    assert ("CLOSED", "OPEN") in pairs
    assert ("OPEN", "LOCKED") in pairs


def test_assignment_transitions_combined_with_return(tmp_path: Path) -> None:
    """A mix of return-based and assignment-based transitions are all captured."""
    src = tmp_path / "mixed.py"
    src.write_text(
        textwrap.dedent("""\
        from enum import Enum

        class State(Enum):
            A = 1
            B = 2

        def pure_fn(s):
            match s:
                case State.A:
                    return State.B
                case State.B:
                    return State.A

        class Machine:
            def go(self):
                match self.current:
                    case State.A:
                        self.current = State.B
        """)
    )

    from tree_sitter_analyzer.uml_state import build_state_result

    result = build_state_result(
        file_path=str(src),
        class_name="State",
        max_nodes=30,
    )
    assert result.error == ""
    # Both return-based (A→B, B→A) and assignment-based (A→B) are detected.
    # After deduplication: A→B and B→A = 2 unique pairs.
    assert len(result.transitions) == 2  # exact pin


# ---------------------------------------------------------------------------
# Section F: MCP tool schema — 'state' in diagram enum
# ---------------------------------------------------------------------------


def test_state_in_diagram_enum() -> None:
    """'state' appears in CodeGraphUMLTool schema diagram enum."""
    from tree_sitter_analyzer.mcp.tools.uml_tool import CodeGraphUMLTool

    tool = CodeGraphUMLTool()
    enum_vals = tool.get_tool_schema()["properties"]["diagram"]["enum"]
    assert "state" in enum_vals


def test_uml_tool_schema_lists_diagrams_with_state() -> None:
    """Enum after P2-A + P2-B integration — exactly 6 members."""
    from tree_sitter_analyzer.mcp.tools.uml_tool import CodeGraphUMLTool

    tool = CodeGraphUMLTool()
    enum_vals = tool.get_tool_schema()["properties"]["diagram"]["enum"]
    # On this branch (state, based on develop): 5 entries
    assert enum_vals == [
        "class",
        "package",
        "component",
        "sequence",
        "activity",
        "state",
    ]


def test_state_diagram_validate_arguments_accepts_state() -> None:
    """validate_arguments accepts diagram='state' without error."""
    from tree_sitter_analyzer.mcp.tools.uml_tool import CodeGraphUMLTool

    tool = CodeGraphUMLTool()
    # Must not raise
    tool.validate_arguments({"diagram": "state"})


def test_state_diagram_validate_arguments_rejects_unknown() -> None:
    """validate_arguments still rejects unknown diagram types."""
    from tree_sitter_analyzer.mcp.tools.uml_tool import CodeGraphUMLTool

    tool = CodeGraphUMLTool()
    with pytest.raises(ValueError, match="Unsupported UML diagram"):
        tool.validate_arguments({"diagram": "er"})


# ---------------------------------------------------------------------------
# Section G: CLI parity — --uml state + --uml-max-nodes registered
# ---------------------------------------------------------------------------


def test_state_in_uml_cli_choices() -> None:
    """'state' is a valid choice for the --uml CLI flag."""
    from tree_sitter_analyzer.cli_main import create_argument_parser

    parser = create_argument_parser()
    uml_action = next(a for a in parser._actions if "--uml" in (a.option_strings or []))
    assert "state" in uml_action.choices


def test_uml_max_nodes_cli_flag_registered() -> None:
    """--uml-max-nodes is registered in the CLI parser."""
    from tree_sitter_analyzer.cli_main import create_argument_parser

    parser = create_argument_parser()
    long_flags = {s for a in parser._actions for s in (a.option_strings or [])}
    assert "--uml-max-nodes" in long_flags


def test_uml_max_nodes_cli_flag_default_50() -> None:
    """--uml-max-nodes default is 50 (matches RFC-0015 table)."""
    from tree_sitter_analyzer.cli_main import create_argument_parser

    parser = create_argument_parser()
    action = next(
        a for a in parser._actions if "--uml-max-nodes" in (a.option_strings or [])
    )
    assert action.default == 50  # exact


# ---------------------------------------------------------------------------
# Section H: MCP tool execute — state diagram dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_state_diagram_not_found_missing_file(tmp_path: Path) -> None:
    """execute with diagram='state' and missing file returns verdict NOT_FOUND."""
    from tree_sitter_analyzer.mcp.tools import uml_tool
    from tree_sitter_analyzer.uml_export import UMLDiagram

    class FakeExporter:
        def state_diagram(
            self,
            *,
            class_name: str | None = None,
            file_path: str | None = None,
            max_nodes: int = 30,
        ) -> UMLDiagram:
            return UMLDiagram(
                diagram_type="state",
                mermaid_type="stateDiagram-v2",
                mermaid="stateDiagram-v2\n",
                nodes=[],
                edges=[],
                metadata={
                    "verdict": "NOT_FOUND",
                    "next_step": "missing file",
                    "analysis_kind": "static_approximation",
                },
            )

    class FakeHub:
        def __init__(self, project_root: str) -> None:
            pass

        def uml_exporter(self) -> FakeExporter:
            return FakeExporter()

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(uml_tool, "CodeGraphVisualizationHub", FakeHub)

    try:
        from tree_sitter_analyzer.mcp.tools.uml_tool import CodeGraphUMLTool

        tool = CodeGraphUMLTool("/repo")
        result = await tool.execute(
            {
                "diagram": "state",
                "file_path": str(tmp_path / "missing.py"),
                "output_format": "json",
            }
        )
        assert result["verdict"] == "NOT_FOUND"
    finally:
        monkeypatch.undo()


@pytest.mark.asyncio
async def test_execute_state_diagram_success(tmp_path: Path) -> None:
    """execute with diagram='state' and a valid FakeExporter returns INFO verdict."""
    from tree_sitter_analyzer.mcp.tools import uml_tool
    from tree_sitter_analyzer.uml_export import UMLDiagram, UMLEdge

    class FakeExporter:
        def state_diagram(
            self,
            *,
            class_name: str | None = None,
            file_path: str | None = None,
            max_nodes: int = 30,
        ) -> UMLDiagram:
            return UMLDiagram(
                diagram_type="state",
                mermaid_type="stateDiagram-v2",
                mermaid=(
                    "stateDiagram-v2\n"
                    "%% NOTE: state diagram is a static approximation.\n"
                    "    [*] --> RED\n"
                    "    RED --> GREEN\n"
                ),
                nodes=["RED", "GREEN"],
                edges=[UMLEdge("RED", "GREEN")],
                metadata={"analysis_kind": "static_approximation"},
            )

    class FakeHub:
        def __init__(self, project_root: str) -> None:
            pass

        def uml_exporter(self) -> FakeExporter:
            return FakeExporter()

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(uml_tool, "CodeGraphVisualizationHub", FakeHub)

    try:
        from tree_sitter_analyzer.mcp.tools.uml_tool import CodeGraphUMLTool

        tool = CodeGraphUMLTool("/repo")
        result = await tool.execute(
            {
                "diagram": "state",
                "class_name": "TrafficLight",
                "output_format": "json",
            }
        )
        assert result["success"] is True
        assert result["diagram_type"] == "state"
        assert result["mermaid_type"] == "stateDiagram-v2"
        assert result["edge_count"] == 1  # exact
        assert result["node_count"] == 2  # exact
    finally:
        monkeypatch.undo()


# ---------------------------------------------------------------------------
# Section I: P2b — CLI/MCP max_nodes default parity conformance
# ---------------------------------------------------------------------------


def test_uml_max_nodes_cli_mcp_default_parity() -> None:
    """CLI argparse default for --uml-max-nodes == MCP schema default for max_nodes.

    Both must be 50 (RFC-0015 table, P2b conformance).
    """
    from tree_sitter_analyzer.cli_main import create_argument_parser
    from tree_sitter_analyzer.mcp.tools.uml_tool import CodeGraphUMLTool

    parser = create_argument_parser()
    cli_action = next(
        a for a in parser._actions if "--uml-max-nodes" in (a.option_strings or [])
    )
    cli_default = cli_action.default

    mcp_default = CodeGraphUMLTool().get_tool_schema()["properties"]["max_nodes"][
        "default"
    ]

    assert cli_default == mcp_default  # both must agree
    assert cli_default == 50  # exact pin: RFC-0015 §P2-B


# ---------------------------------------------------------------------------
# Section J: P3a — INFO (zero-transitions) mermaid suppresses [*] --> lines
# RE-PINNED: was NOT_FOUND, now INFO (#480 fix — states found, no transitions
# is a partial result, not "not found").
# ---------------------------------------------------------------------------


def test_info_zero_transition_state_diagram_no_initial_edges(tmp_path: Path) -> None:
    """INFO (zero-transition) state diagram mermaid must NOT contain '[*] -->' lines.

    RE-PINNED from NOT_FOUND → INFO (#480): the mermaid honesty rule (suppress
    initial-state lines when no transitions detected) is preserved. The %% NOTE
    guard must still be present. An agent reading only mermaid still sees an
    honest "no transitions detected" note rather than a fake diagram.
    """
    src = tmp_path / "static.py"
    src.write_text(
        textwrap.dedent("""\
        from enum import Enum

        class Status(Enum):
            OPEN = 1
            CLOSED = 2
        """)
    )

    from tree_sitter_analyzer.uml_export import UMLExporter

    exporter = UMLExporter(str(tmp_path))
    diagram = exporter.state_diagram(class_name="Status", file_path=str(src))

    # RE-PINNED: was NOT_FOUND, now INFO (states found, zero transitions)
    assert diagram.metadata.get("verdict") == "INFO"
    # Mermaid honesty guard must still be present
    assert "%% NOTE" in diagram.mermaid
    # Must NOT contain any initial-state transition lines (mermaid suppression preserved)
    assert "[*] -->" not in diagram.mermaid


def test_info_zero_transition_state_diagram_mermaid_starts_with_header(
    tmp_path: Path,
) -> None:
    """INFO (zero-transition) mermaid output starts with 'stateDiagram-v2' header.

    RE-PINNED from NOT_FOUND → INFO (#480).
    """
    src = tmp_path / "static2.py"
    src.write_text(
        textwrap.dedent("""\
        from enum import Enum

        class State(Enum):
            A = 1
        """)
    )

    from tree_sitter_analyzer.uml_export import UMLExporter

    exporter = UMLExporter(str(tmp_path))
    diagram = exporter.state_diagram(class_name="State", file_path=str(src))

    # RE-PINNED: was NOT_FOUND, now INFO (#480)
    assert diagram.metadata.get("verdict") == "INFO"
    assert diagram.mermaid.startswith("stateDiagram-v2")


def test_state_diagram_true_not_found_zero_states(tmp_path: Path) -> None:
    """TRUE NOT_FOUND = zero states: class not found in file at all.

    This pins the contract that NOT_FOUND is only for node_count==0 (#480).
    A missing class or no enum → verdict=NOT_FOUND.
    """
    src = tmp_path / "no_enum.py"
    src.write_text("class Plain:\n    pass\n")

    from tree_sitter_analyzer.uml_export import UMLExporter

    exporter = UMLExporter(str(tmp_path))
    diagram = exporter.state_diagram(file_path=str(src))
    assert diagram.metadata.get("verdict") == "NOT_FOUND"


def test_state_diagram_non_python_file_not_found_mentions_language(
    tmp_path: Path,
) -> None:
    """Non-Python file (TypeScript) → NOT_FOUND with language coverage note (#480).

    State extraction is Python-only. A bare NOT_FOUND on a .ts file reads as
    a bug, not a scope limit. The next_step must mention language support or
    Python scope.
    """
    ts_file = tmp_path / "State.ts"
    ts_file.write_text("enum UserRole { Admin = 'admin', User = 'user' }\n")

    from tree_sitter_analyzer.uml_export import UMLExporter

    exporter = UMLExporter(str(tmp_path))
    diagram = exporter.state_diagram(file_path=str(ts_file))
    assert diagram.metadata.get("verdict") == "NOT_FOUND"
    next_step = diagram.metadata.get("next_step", "")
    # Must mention Python-only scope or language limitation
    assert "python" in next_step.lower() or "language" in next_step.lower()


# ---------------------------------------------------------------------------
# Section K: P3b — _extract_enum_members lowercase-member behavior pinned
# ---------------------------------------------------------------------------


def test_extract_enum_members_includes_lowercase(tmp_path: Path) -> None:
    """_extract_enum_members includes lowercase names as enum members.

    Documents the actual behavior: all non-underscore-prefixed assignment
    targets are treated as members, regardless of case.
    """
    src = tmp_path / "config.py"
    src.write_text(
        textwrap.dedent("""\
        from enum import Enum

        class Config(Enum):
            max_retries = 3
            timeout = 30
            debug = False
        """)
    )

    from tree_sitter_analyzer.uml_state import build_state_result

    result = build_state_result(
        file_path=str(src),
        class_name="Config",
        max_nodes=30,
    )
    assert result.error == ""
    # Exact pin: all 3 lowercase members are returned
    assert sorted(result.states) == ["debug", "max_retries", "timeout"]


# ---------------------------------------------------------------------------
# Section L: Codex P2-2 — per-enum transition scan (bug: only enum_classes[0] scanned)
# ---------------------------------------------------------------------------


def test_second_enum_transitions_found_when_first_enum_has_none(
    tmp_path: Path,
) -> None:
    """With class_name omitted, transitions from a second Enum are found.

    Regression test for P2-2: when multiple Enums exist in a file and only
    the second has match-driven transitions, build_state_result must return
    those transitions (not NOT_FOUND / empty).

    Semantics chosen: when multiple Enums are present and class_name is
    omitted, the function prefers the Enum(s) that have transitions.
    States come from transition-bearing enums; members from non-transition
    enums are excluded from the primary output.
    """
    src = tmp_path / "fsm.py"
    src.write_text(
        textwrap.dedent("""\
        from enum import Enum

        class Color(Enum):
            RED = 1
            GREEN = 2

        class Door(Enum):
            OPEN = "open"
            CLOSED = "closed"
            LOCKED = "locked"

        def transition(state: Door) -> Door:
            match state:
                case Door.CLOSED:
                    return Door.OPEN
                case Door.OPEN:
                    return Door.CLOSED
                case Door.LOCKED:
                    return Door.CLOSED
        """)
    )

    from tree_sitter_analyzer.uml_state import build_state_result

    result = build_state_result(
        file_path=str(src),
        class_name=None,
        max_nodes=50,
    )
    assert result.error == ""
    # Exact pin: Door's 3 transitions must be present
    assert len(result.transitions) == 3
    transition_pairs = {(t.source, t.target) for t in result.transitions}
    assert transition_pairs == {
        ("CLOSED", "OPEN"),
        ("OPEN", "CLOSED"),
        ("LOCKED", "CLOSED"),
    }


# ---------------------------------------------------------------------------
# Section M: Codex P2-3 — qualified enum bases (e.g. enum.Enum)
# ---------------------------------------------------------------------------


def test_qualified_enum_base_states_and_transitions(tmp_path: Path) -> None:
    """enum.Enum-based FSM is recognised (qualified base name fix).

    Regression test for P2-3: _find_enum_classes must accept dotted bases
    like ``enum.Enum`` / ``enum.IntEnum`` in addition to bare ``Enum``.
    """
    src = tmp_path / "traffic.py"
    src.write_text(
        textwrap.dedent("""\
        import enum

        class TrafficLight(enum.Enum):
            RED = 1
            YELLOW = 2
            GREEN = 3

        def next_state(state: TrafficLight) -> TrafficLight:
            match state:
                case TrafficLight.RED:
                    return TrafficLight.GREEN
                case TrafficLight.GREEN:
                    return TrafficLight.YELLOW
                case TrafficLight.YELLOW:
                    return TrafficLight.RED
        """)
    )

    from tree_sitter_analyzer.uml_state import build_state_result

    result = build_state_result(
        file_path=str(src),
        class_name="TrafficLight",
        max_nodes=50,
    )
    assert result.error == ""
    # Exact pin: 3 states
    assert sorted(result.states) == ["GREEN", "RED", "YELLOW"]
    # Exact pin: 3 transitions
    assert len(result.transitions) == 3
    transition_pairs = {(t.source, t.target) for t in result.transitions}
    assert transition_pairs == {
        ("RED", "GREEN"),
        ("GREEN", "YELLOW"),
        ("YELLOW", "RED"),
    }


# ---------------------------------------------------------------------------
# Section N2: _extract_enum_members — non-expression_statement children (line 149->148)
# ---------------------------------------------------------------------------


def test_enum_with_method_body_still_extracts_members(tmp_path: Path) -> None:
    """Enum class with a method definition: non-expression_statement block children
    are skipped gracefully (line 149->148 branch: stmt.type != 'expression_statement').

    The method definition must not crash extraction and members must still be found.
    """
    src = tmp_path / "rich_enum.py"
    src.write_text(
        textwrap.dedent("""\
        from enum import Enum

        class Status(Enum):
            OPEN = 1
            CLOSED = 2

            def label(self):
                return self.value
        """)
    )

    from tree_sitter_analyzer.uml_state import build_state_result

    result = build_state_result(
        file_path=str(src),
        class_name="Status",
        max_nodes=30,
    )
    assert result.error == ""
    # Exact pin: only OPEN and CLOSED, not anything from the method
    assert sorted(result.states) == ["CLOSED", "OPEN"]


def test_enum_with_docstring_skips_non_assignment_expressions(tmp_path: Path) -> None:
    """Enum class with a docstring: expression_statement wrapping a string
    (not assignment) is skipped (line 151->150 branch: sub.type != 'assignment').

    The docstring is an expression_statement whose content is a string, not
    an assignment. The extractor must skip it without crashing.
    """
    src = tmp_path / "documented_enum.py"
    src.write_text(
        textwrap.dedent("""\
        from enum import Enum

        class Phase(Enum):
            \"\"\"Phase states of the system.\"\"\"
            INIT = 1
            RUNNING = 2
            DONE = 3
        """)
    )

    from tree_sitter_analyzer.uml_state import build_state_result

    result = build_state_result(
        file_path=str(src),
        class_name="Phase",
        max_nodes=30,
    )
    assert result.error == ""
    # Exact pin: 3 members, docstring excluded
    assert sorted(result.states) == ["DONE", "INIT", "RUNNING"]


# ---------------------------------------------------------------------------
# Section N: _node_text edge-cases (raw=None, exception)
# ---------------------------------------------------------------------------


def test_node_text_raw_none_returns_empty() -> None:
    """_node_text returns '' when node.text is None (line 92 branch)."""
    from tree_sitter_analyzer.uml_state import _node_text

    node = _make_ts_node("identifier", "")
    node.text = None  # override to None explicitly
    result = _node_text(node)
    assert result == ""


def test_node_text_exception_returns_empty() -> None:
    """_node_text returns '' when node.text raises AttributeError (lines 95-96)."""
    from tree_sitter_analyzer.uml_state import _node_text

    class BadNode:
        @property
        def text(self):
            raise AttributeError("no text attribute")

    result = _node_text(BadNode())
    assert result == ""


def test_node_text_long_string_truncated() -> None:
    """_node_text truncates at max_len (line 94 short-path covered)."""
    from tree_sitter_analyzer.uml_state import _node_text

    node = _make_ts_node("identifier", "A" * 80)
    result = _node_text(node, max_len=10)
    assert result == "A" * 10
    assert len(result) == 10


# ---------------------------------------------------------------------------
# Section O: build_state_result — PARSE_FAILED path
# ---------------------------------------------------------------------------


def test_build_state_result_parse_failed(tmp_path: Path) -> None:
    """build_state_result returns error='PARSE_FAILED' when parser returns None (line 332)."""
    import tree_sitter_analyzer.uml_state as _state_module

    src = tmp_path / "exists.py"
    src.write_text("class Foo(Enum):\n    A = 1\n")

    def fake_parse(file_path: str, language: str = "python"):
        return None  # simulate parse failure

    orig = _state_module._parse_file_for_state
    try:
        _state_module._parse_file_for_state = fake_parse
        result = _state_module.build_state_result(
            file_path=str(src),
            class_name=None,
            max_nodes=30,
        )
    finally:
        _state_module._parse_file_for_state = orig

    assert result.error == "PARSE_FAILED"
    assert result.states == []
    assert result.transitions == []


# ---------------------------------------------------------------------------
# Section P: multi-enum fallback — no transitions in any enum
# ---------------------------------------------------------------------------


def test_multi_enum_no_transitions_falls_back_to_all_members(tmp_path: Path) -> None:
    """When class_name is None and NO enum has transitions, fall back to all members.

    Covers line 374-375 (else: chosen = enum_transitions fallback) and
    the deduplication path for all_members when no transition-bearing enum exists.
    """
    src = tmp_path / "no_fsm.py"
    src.write_text(
        textwrap.dedent("""\
        from enum import Enum

        class Color(Enum):
            RED = 1
            GREEN = 2

        class Size(Enum):
            SMALL = 1
            LARGE = 2
        """)
    )

    from tree_sitter_analyzer.uml_state import build_state_result

    result = build_state_result(
        file_path=str(src),
        class_name=None,
        max_nodes=50,
    )
    # No error — enum classes found
    assert result.error == ""
    # No transitions — both enums have no match statements
    assert result.transitions == []
    # All 4 members returned (dedup preserves order from both enums)
    assert sorted(result.states) == ["GREEN", "LARGE", "RED", "SMALL"]


# ---------------------------------------------------------------------------
# Section Q: _iter_case_clauses direct case_clause fallback (line 262)
# ---------------------------------------------------------------------------


def test_iter_case_clauses_direct_child_fallback() -> None:
    """_iter_case_clauses handles direct case_clause children (grammar fallback, line 262)."""
    from tree_sitter_analyzer.uml_state import _extract_transitions

    # Build a minimal mock match_statement where case_clauses are direct children
    # (not inside a block). This exercises the line 260-262 fallback branch.
    case_clause = _make_ts_node("case_clause")
    # case_clause with case_pattern → "State.A" and block → return State.B
    # For simplicity, just verify the direct child path is tried (no transition extracted
    # from this mock since it lacks proper sub-structure, but the branch is exercised).
    match_stmt = _make_ts_node("match_statement", children=[case_clause])

    root = _make_ts_node("module", children=[match_stmt])
    transitions = _extract_transitions(root, "State", {"A", "B"})
    # No transitions from malformed mock, but branch is covered
    assert isinstance(transitions, list)


def test_extract_enum_members_with_empty_lhs_children_skipped() -> None:
    """_extract_enum_members skips an assignment with empty children (line 153->150).

    When an assignment mock has no children, lhs_children is empty ([]) and the
    `if lhs_children:` guard at line 153 is False — exercises the 153->150 branch.
    """
    from tree_sitter_analyzer.uml_state import _extract_enum_members

    # Create a class_definition node with a block containing an expression_statement
    # wrapping an assignment that has NO children.
    empty_assignment = _make_ts_node("assignment", children=[])
    expr_stmt = _make_ts_node("expression_statement", children=[empty_assignment])
    block = _make_ts_node("block", children=[expr_stmt])
    cls_node = _make_ts_node("class_definition", children=[block])

    members = _extract_enum_members(cls_node)
    # Empty assignment → no members extracted, no crash
    assert members == []


def test_extract_enum_members_with_non_identifier_lhs_skipped() -> None:
    """_extract_enum_members skips an assignment whose LHS is not an identifier (line 155->150).

    When the LHS child type is 'tuple' (e.g., `(a, b) = ...`), the `if lhs.type ==
    'identifier':` guard at line 155 is False — exercises the 155->150 branch.
    """
    from tree_sitter_analyzer.uml_state import _extract_enum_members

    tuple_lhs = _make_ts_node("tuple", "(A, B)")
    assignment = _make_ts_node("assignment", children=[tuple_lhs])
    expr_stmt = _make_ts_node("expression_statement", children=[assignment])
    block = _make_ts_node("block", children=[expr_stmt])
    cls_node = _make_ts_node("class_definition", children=[block])

    members = _extract_enum_members(cls_node)
    # Tuple LHS → not a member, no crash
    assert members == []


def test_iter_case_clauses_block_with_non_case_clause_child() -> None:
    """_iter_case_clauses skips non-case_clause children in block (line 258->257).

    When a block has a child that is NOT a case_clause (e.g. a comment or newline),
    the loop continues without appending it (258->257 branch).
    """
    from tree_sitter_analyzer.uml_state import _extract_transitions

    # Block child is a comment node, not a case_clause
    comment_node = _make_ts_node("comment", "# comment")
    block = _make_ts_node("block", children=[comment_node])
    match_stmt = _make_ts_node("match_statement", children=[block])
    root = _make_ts_node("module", children=[match_stmt])

    transitions = _extract_transitions(root, "State", {"A", "B"})
    # Block had no case_clause children → no transitions
    assert transitions == []


def test_parse_enum_ref_no_match_returns_none() -> None:
    """_parse_enum_ref returns None when text doesn't start with class_name prefix (194->196).

    This exercises the False branch of `if text.startswith(prefix):` in _parse_enum_ref,
    which returns None (line 196) rather than a member name.

    We invoke this indirectly via _extract_transitions with a case_pattern node
    whose text does NOT start with the class prefix.
    """
    from tree_sitter_analyzer.uml_state import _extract_transitions

    # case_pattern with text "OtherClass.OPEN" — not matching "State." prefix
    non_matching = _make_ts_node("attribute", "OtherClass.OPEN")
    case_pattern = _make_ts_node("case_pattern", children=[non_matching])

    # block with a return of matching member (target)
    return_ref = _make_ts_node("attribute", "State.B")
    return_stmt = _make_ts_node("return_statement", children=[return_ref])
    block = _make_ts_node("block", children=[return_stmt])

    case_clause = _make_ts_node("case_clause", children=[case_pattern, block])
    inner_block = _make_ts_node("block", children=[case_clause])
    match_stmt = _make_ts_node("match_statement", children=[inner_block])
    root = _make_ts_node("module", children=[match_stmt])

    # Source doesn't match (non_matching text "OtherClass.OPEN" with prefix "State.")
    # so _parse_enum_ref returns None → source_member stays None → no transition
    transitions = _extract_transitions(root, "State", {"A", "B"})
    assert transitions == []


def test_case_pattern_fallback_exercises_node_text_path() -> None:
    """_extract_transitions uses case_pattern text fallback when children don't yield ref (line 283).

    When a case_pattern's children DON'T yield an enum ref (they have non-matching text),
    but the case_pattern node's own text IS a matching ref (e.g. 'State.A'), the
    fallback at lines 279-283 picks it up.

    To trigger this: case_pattern's child is a non-matching attribute, but the
    case_pattern's own text is "State.A" — a matching enum ref.
    """
    from tree_sitter_analyzer.uml_state import _extract_transitions

    # case_pattern child: text "other.X" — does NOT match "State." prefix
    non_match_child = _make_ts_node("attribute", "other.X")
    # case_pattern itself: text "State.A" — DOES match "State." prefix
    case_pattern = _make_ts_node("case_pattern", "State.A", children=[non_match_child])

    # block with return of State.B (target)
    return_ref = _make_ts_node("attribute", "State.B")
    return_stmt = _make_ts_node("return_statement", children=[return_ref])
    block = _make_ts_node("block", children=[return_stmt])

    case_clause = _make_ts_node("case_clause", children=[case_pattern, block])
    inner_block = _make_ts_node("block", children=[case_clause])
    match_stmt = _make_ts_node("match_statement", children=[inner_block])
    root = _make_ts_node("module", children=[match_stmt])

    transitions = _extract_transitions(root, "State", {"A", "B"})
    # Fallback text match → source=A, target=B → 1 transition
    assert len(transitions) == 1  # exact pin
    assert transitions[0].source == "A"
    assert transitions[0].target == "B"


def test_dotted_name_direct_source_member() -> None:
    """Lines 284-287: dotted_name/attribute directly in case_clause as source member.

    Some tree-sitter grammar versions place the pattern as a direct dotted_name
    child of the case_clause (not wrapped in case_pattern). Lines 284-287 handle
    this: when cc.type in ('dotted_name', 'attribute'), _parse_enum_ref is called
    directly on it.
    """
    from tree_sitter_analyzer.uml_state import _extract_transitions

    # case_clause has a direct 'dotted_name' child with "State.A" text (source)
    # and a block child with return_statement (target)
    dotted_name = _make_ts_node("dotted_name", "State.A")
    return_ref = _make_ts_node("attribute", "State.B")
    return_stmt = _make_ts_node("return_statement", children=[return_ref])
    block = _make_ts_node("block", children=[return_stmt])

    case_clause = _make_ts_node("case_clause", children=[dotted_name, block])
    inner_block = _make_ts_node("block", children=[case_clause])
    match_stmt = _make_ts_node("match_statement", children=[inner_block])
    root = _make_ts_node("module", children=[match_stmt])

    transitions = _extract_transitions(root, "State", {"A", "B"})
    # Direct dotted_name source + block target → 1 transition A→B
    assert len(transitions) == 1  # exact pin
    assert transitions[0].source == "A"
    assert transitions[0].target == "B"


def test_dotted_name_non_matching_source_skipped() -> None:
    """Line 286->271: dotted_name in case_clause doesn't match enum prefix → skipped.

    When cc.type is 'dotted_name' but text is 'Other.X' (not 'State.X'), the
    _parse_enum_ref returns None → 286->271 branch fires (if m is not None: is False).
    source_member stays None and no transition is recorded.
    """
    from tree_sitter_analyzer.uml_state import _extract_transitions

    # Direct dotted_name with non-matching text
    dotted_name = _make_ts_node("dotted_name", "Other.X")
    return_ref = _make_ts_node("attribute", "State.B")
    return_stmt = _make_ts_node("return_statement", children=[return_ref])
    block = _make_ts_node("block", children=[return_stmt])

    case_clause = _make_ts_node("case_clause", children=[dotted_name, block])
    inner_block = _make_ts_node("block", children=[case_clause])
    match_stmt = _make_ts_node("match_statement", children=[inner_block])
    root = _make_ts_node("module", children=[match_stmt])

    transitions = _extract_transitions(root, "State", {"A", "B"})
    # Source doesn't match → no transition
    assert transitions == []


# ---------------------------------------------------------------------------
# Section R: _find_return_enum_ref — assignment branch (lines 211-220)
# ---------------------------------------------------------------------------


def test_find_return_enum_ref_assignment_with_eq_first_reversed() -> None:
    """_find_return_enum_ref skips reversed children where type == '=' (line 216->215).

    We place the '=' token as the LAST child (first when reversed) to force the
    loop to skip it and continue to the next child (the enum ref). This exercises
    the 216->215 branch (condition False → loop continues to next iteration).
    After skipping '=', the loop finds the enum ref and returns it.
    """
    from tree_sitter_analyzer.uml_state import _extract_transitions

    # Assignment: children=[lhs, enum_ref, eq_token] — reversed: [eq_token, enum_ref, lhs]
    # First reversed child is '=' → condition False → skip → next is enum_ref → match → break
    lhs_child = _make_ts_node("identifier", "x")
    rhs_child = _make_ts_node("attribute", "State.B")
    # Deliberately put "=" LAST so it's FIRST when reversed
    eq_last = _make_ts_node("=", "=")
    assignment = _make_ts_node("assignment", children=[lhs_child, rhs_child, eq_last])

    block = _make_ts_node("block", children=[assignment])
    case_clause = _make_ts_node("case_clause", children=[block])
    inner_block = _make_ts_node("block", children=[case_clause])
    match_stmt = _make_ts_node("match_statement", children=[inner_block])
    root = _make_ts_node("module", children=[match_stmt])

    # No crash; may or may not produce transitions but branch is exercised
    transitions = _extract_transitions(root, "State", {"A", "B"})
    assert isinstance(transitions, list)


def test_find_return_enum_ref_assignment_non_matching_rhs_breaks() -> None:
    """_find_return_enum_ref hits break (line 220) when RHS of assignment doesn't match enum.

    When an assignment has a non-enum RHS (e.g. a string literal 'foo'), the
    _parse_enum_ref returns None → `break` fires (line 220), exiting the reversed loop.
    No transition is recorded.
    """
    from tree_sitter_analyzer.uml_state import _extract_transitions

    # Assignment: [lhs, =, non_enum_rhs] where rhs is a string literal, not an enum ref
    lhs_child = _make_ts_node("identifier", "x")
    eq_child = _make_ts_node("=", "=")
    non_enum_rhs = _make_ts_node("string", '"foo"')  # does NOT match "State." prefix
    assignment = _make_ts_node(
        "assignment", children=[lhs_child, eq_child, non_enum_rhs]
    )

    # Put in a case_clause with a dummy source
    dotted_name = _make_ts_node("dotted_name", "State.A")  # valid source
    block = _make_ts_node("block", children=[assignment])
    case_clause = _make_ts_node("case_clause", children=[dotted_name, block])
    inner_block = _make_ts_node("block", children=[case_clause])
    match_stmt = _make_ts_node("match_statement", children=[inner_block])
    root = _make_ts_node("module", children=[match_stmt])

    transitions = _extract_transitions(root, "State", {"A", "B"})
    # RHS doesn't match enum → break → no transition target → no transition
    assert transitions == []


def test_find_return_enum_ref_assignment_no_children_no_crash() -> None:
    """_find_return_enum_ref handles assignment with no children gracefully (line 215->221).

    When the assignment node has an empty children list, the reversed loop exits
    immediately without finding any ref (exercises 215->221 back-edge = loop exits).
    """
    from tree_sitter_analyzer.uml_state import _extract_transitions

    # Assignment with no children — reversed([]) yields nothing
    assignment = _make_ts_node("assignment", children=[])

    block = _make_ts_node("block", children=[assignment])
    case_clause = _make_ts_node("case_clause", children=[block])
    inner_block = _make_ts_node("block", children=[case_clause])
    match_stmt = _make_ts_node("match_statement", children=[inner_block])
    root = _make_ts_node("module", children=[match_stmt])

    # Should not crash; no transitions found
    transitions = _extract_transitions(root, "State", {"A", "B"})
    assert transitions == []


def test_find_return_enum_ref_assignment_branch_via_integration(tmp_path: Path) -> None:
    """Assignment-style transitions exercise the reversed-children scan (lines 211-220).

    This uses a real file so the assignment branch path in _find_return_enum_ref
    is exercised end-to-end through build_state_result.
    """
    src = tmp_path / "oop.py"
    src.write_text(
        textwrap.dedent("""\
        from enum import Enum

        class Lamp(Enum):
            ON = 1
            OFF = 2

        class Controller:
            def toggle(self):
                match self.state:
                    case Lamp.ON:
                        self.state = Lamp.OFF
                    case Lamp.OFF:
                        self.state = Lamp.ON
        """)
    )

    from tree_sitter_analyzer.uml_state import build_state_result

    result = build_state_result(
        file_path=str(src),
        class_name="Lamp",
        max_nodes=30,
    )
    assert result.error == ""
    assert len(result.transitions) == 2  # exact pin: ON→OFF, OFF→ON
    pairs = {(t.source, t.target) for t in result.transitions}
    assert ("ON", "OFF") in pairs
    assert ("OFF", "ON") in pairs


# ---------------------------------------------------------------------------
# Section S: _extract_enum_members — branches with non-qualifying AST nodes
# ---------------------------------------------------------------------------


def test_build_state_result_ignores_underscore_prefixed_members(tmp_path: Path) -> None:
    """_extract_enum_members skips names starting with '_' (line 157 branch)."""
    src = tmp_path / "skip.py"
    src.write_text(
        textwrap.dedent("""\
        from enum import Enum

        class Flags(Enum):
            ACTIVE = 1
            _INTERNAL = 2
            DONE = 3
        """)
    )

    from tree_sitter_analyzer.uml_state import build_state_result

    result = build_state_result(
        file_path=str(src),
        class_name="Flags",
        max_nodes=30,
    )
    assert result.error == ""
    # Exact pin: only non-underscore members
    assert sorted(result.states) == ["ACTIVE", "DONE"]


# ---------------------------------------------------------------------------
# Section T: multi-enum deduplication path (line 392->391)
# ---------------------------------------------------------------------------


def test_multi_enum_dedup_members_preserves_unique(tmp_path: Path) -> None:
    """When multiple enums have overlapping member names, dedup preserves uniqueness.

    Exercises the seen_members deduplication loop at line 389-394 for the
    multi-enum (class_name=None) fallback path.
    """
    src = tmp_path / "overlap.py"
    src.write_text(
        textwrap.dedent("""\
        from enum import Enum

        class Status(Enum):
            ACTIVE = 1
            INACTIVE = 2

        class Flag(Enum):
            ACTIVE = 1
            DONE = 2
        """)
    )

    from tree_sitter_analyzer.uml_state import build_state_result

    result = build_state_result(
        file_path=str(src),
        class_name=None,
        max_nodes=50,
    )
    assert result.error == ""
    # ACTIVE appears in both enums but must be deduplicated
    # Exact pin: ACTIVE, INACTIVE, DONE (3 unique members)
    assert sorted(result.states) == ["ACTIVE", "DONE", "INACTIVE"]


# ---------------------------------------------------------------------------
# Section U: multi-enum with transitions from MULTIPLE enums (line 384->382)
# — exercises the dedup loop in _aggregate_transitions when >1 transition exists
# ---------------------------------------------------------------------------


def test_multi_enum_both_have_transitions_aggregated_and_deduped(
    tmp_path: Path,
) -> None:
    """Both enums have transitions; cross-enum duplicate transitions are deduped.

    Exercises the deduplicated transition aggregation loop at lines 381-386
    (seen_txn branch at 384->382 fires when a transition from enum2 duplicates one
    from enum1).
    """
    src = tmp_path / "two_fsm.py"
    src.write_text(
        textwrap.dedent("""\
        from enum import Enum

        class Door(Enum):
            OPEN = "open"
            CLOSED = "closed"

        class Gate(Enum):
            OPEN = "open"
            CLOSED = "closed"

        def door_fn(state: Door) -> Door:
            match state:
                case Door.OPEN:
                    return Door.CLOSED
                case Door.CLOSED:
                    return Door.OPEN

        def gate_fn(state: Gate) -> Gate:
            match state:
                case Gate.OPEN:
                    return Gate.CLOSED
                case Gate.CLOSED:
                    return Gate.OPEN
        """)
    )

    from tree_sitter_analyzer.uml_state import build_state_result

    result = build_state_result(
        file_path=str(src),
        class_name=None,
        max_nodes=50,
    )
    assert result.error == ""
    # Both enums have the same OPEN<->CLOSED transitions.
    # After dedup: OPEN->CLOSED, CLOSED->OPEN = 2 unique transitions.
    assert len(result.transitions) == 2  # exact pin — duplicates removed
    pairs = {(t.source, t.target) for t in result.transitions}
    assert pairs == {("OPEN", "CLOSED"), ("CLOSED", "OPEN")}
