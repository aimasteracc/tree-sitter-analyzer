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
    assert "stateDiagram-v2" in mermaid
    # Must not crash and must produce something
    assert len(mermaid) > 0


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


def test_state_diagram_zero_transitions_not_found(tmp_path: Path) -> None:
    """Zero transitions → verdict='NOT_FOUND' in metadata (honesty rule)."""
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
    assert diagram.metadata.get("verdict") == "NOT_FOUND"
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
# Section J: P3a — NOT_FOUND mermaid suppresses [*] --> lines
# ---------------------------------------------------------------------------


def test_not_found_state_diagram_no_initial_edges(tmp_path: Path) -> None:
    """NOT_FOUND state diagram mermaid must NOT contain '[*] -->' lines.

    An agent reading only mermaid would see a structurally-valid diagram if
    initial-state edges were emitted; the %% NOTE guard must be present instead.
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

    # Verify NOT_FOUND verdict
    assert diagram.metadata.get("verdict") == "NOT_FOUND"
    # Must contain the honesty NOTE guard
    assert "%% NOTE" in diagram.mermaid
    # Must NOT contain any initial-state transition lines
    assert "[*] -->" not in diagram.mermaid


def test_not_found_state_diagram_mermaid_starts_with_header(tmp_path: Path) -> None:
    """NOT_FOUND mermaid output starts with 'stateDiagram-v2' header."""
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

    assert diagram.metadata.get("verdict") == "NOT_FOUND"
    assert diagram.mermaid.startswith("stateDiagram-v2")


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
