"""RED tests for the safe_to_edit ↔ constraints integration (Feature 3).

The contract these tests pin down is the cross-cut: constraint violations
that were detected by ``check_constraints`` must promote
``safe_to_edit``'s verdict and surface in ``analyze_change_impact``'s
output, so the agent's first read of either tool tells them they are
about to make an architectural mistake.

Today, ``SafeToEditTool._safe_to_edit_verdict`` only maps risk_level to
``SAFE / REVIEW / CAUTION``. After this feature lands, it must:

* return ``UNSAFE`` when an error-severity violation references the file
  being edited (currently safe_to_edit never emits UNSAFE — this becomes
  the first producer);
* return ``CAUTION`` when only warn-severity violations are present;
* attach a ``constraint_violation`` entry to ``risk_factors`` so the
  agent can see the offending rule_id without a second tool call.

We deliberately keep this in its own file (per coordination rules,
``test_safe_to_edit_tool.py`` must not be modified by the test-author).
"""

from __future__ import annotations

import asyncio
import sqlite3
import time
from pathlib import Path

import pytest

pytest.importorskip("yaml")


# ---------------------------------------------------------------------------
# Helpers — paralleling the constraint_check helpers so the seeding shape
# stays consistent across test files. Duplication is intentional: each
# RED test file must be readable in isolation by the GREEN-phase author.
# ---------------------------------------------------------------------------


TARGET_FILE_REL = "tree_sitter_analyzer/mcp/tools/safe_to_edit_tool.py"


def _run(coro):
    return asyncio.run(coro)


def _scaffold_min_project(tmp_path: Path) -> Path:
    """Create the minimum directory shape the SafeToEditTool needs.

    SafeToEditTool builds a DependencyGraph rooted at ``project_root`` and
    calls into ``HealthScorer.score_file(resolved_path)``. We need a real
    file at the target path, a pyproject.toml so security validation
    succeeds, and at least one Python file the graph can walk.
    """
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'sample'\n")

    target = tmp_path / TARGET_FILE_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "class SafeToEditTool:\n    def execute(self):\n        return 'safe'\n"
    )
    return tmp_path


def _init_violations_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ast_constraint_violations (
                rule_id      TEXT NOT NULL,
                caller_file  TEXT NOT NULL,
                caller_name  TEXT NOT NULL,
                caller_line  INTEGER NOT NULL,
                callee_name  TEXT NOT NULL,
                callee_file  TEXT NOT NULL DEFAULT '',
                severity     TEXT NOT NULL,
                detected_at  INTEGER NOT NULL,
                PRIMARY KEY (rule_id, caller_file, caller_line, callee_name)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _seed_violation(
    db_path: Path,
    *,
    rule_id: str,
    caller_file: str,
    severity: str,
    callee_file: str = "tree_sitter_analyzer/cli/y.py",
    caller_line: int = 1,
) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO ast_constraint_violations
                (rule_id, caller_file, caller_name, caller_line,
                 callee_name, callee_file, severity, detected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rule_id,
                caller_file,
                "caller_fn",
                caller_line,
                "callee_fn",
                callee_file,
                severity,
                int(time.time()),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _stage_dogfood_constraints(project: Path) -> None:
    """Drop a minimal architectural-constraints.yml so the loader has rules."""
    (project / "architectural-constraints.yml").write_text(
        """
version: 1
constraints:
  - id: mcp-no-cli
    severity: error
    rule: forbid
    from: "tree_sitter_analyzer/mcp/**"
    to: "tree_sitter_analyzer/cli/**"
    reason: "Dogfood: MCP must not depend on CLI."
""".lstrip()
    )


def _make_safe_to_edit_tool(project_root: Path):
    from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import SafeToEditTool

    tool = SafeToEditTool(str(project_root))
    tool.set_project_path(str(project_root))
    return tool


def _make_change_impact_tool(project_root: Path):
    from tree_sitter_analyzer.mcp.tools.change_impact_tool import ChangeImpactTool

    tool = ChangeImpactTool(str(project_root))
    tool.set_project_path(str(project_root))
    return tool


# ---------------------------------------------------------------------------
# SafeToEdit integration
# ---------------------------------------------------------------------------


class TestSafeToEditConstraintIntegration:
    """An error-severity violation on the target file must promote verdict."""

    def test_safe_to_edit_emits_UNSAFE_on_error_violation(self, tmp_path: Path) -> None:
        """Pre-existing error-severity violation → safe_to_edit returns UNSAFE.

        This is the first producer of the ``UNSAFE`` verdict from
        safe_to_edit. Without this, an agent reading safe_to_edit can
        cheerfully edit a file that is structurally forbidden from
        making the call it makes, because the SAFE/REVIEW/CAUTION
        vocabulary never escalates.
        """
        project = _scaffold_min_project(tmp_path)
        _stage_dogfood_constraints(project)

        db_path = project / ".ast-cache" / "index.db"
        _init_violations_db(db_path)
        _seed_violation(
            db_path,
            rule_id="mcp-no-cli",
            caller_file=TARGET_FILE_REL,
            severity="error",
            caller_line=2,
        )

        tool = _make_safe_to_edit_tool(project)
        # Use json to access the risk_factors list directly (value-kind rule
        # strips non-empty lists at top level in TOON mode)
        result = _run(
            tool.execute({"file_path": TARGET_FILE_REL, "output_format": "json"})
        )

        assert result["verdict"] == "UNSAFE", (
            f"safe_to_edit must return verdict='UNSAFE' when an "
            f"error-severity constraint violation references the file. "
            f"Got: {result.get('verdict')!r}"
        )

        # The risk_factors list must carry the constraint context so the
        # agent doesn't have to make a second MCP call to discover *why*
        # the file was flagged.
        risk_factors = result.get("risk_factors", [])
        constraint_factors = [
            f
            for f in risk_factors
            if (
                f.get("kind") == "constraint_violation"
                or f.get("factor") == "constraint_violation"
            )
        ]
        assert constraint_factors, (
            "risk_factors must include an entry with "
            "kind/factor == 'constraint_violation'. "
            f"Got risk_factors: {risk_factors}"
        )

    def test_summary_line_matches_escalated_verdict(self, tmp_path: Path) -> None:
        """#781: an escalated verdict must reach the summary_line too.

        Before the fix, a constraint escalation patched ``summary["verdict"]``
        to UNSAFE but left ``summary_line`` built from the un-escalated base
        verdict, so the one-line decision surface read verdict=CAUTION/SAFE
        while the structured verdict said UNSAFE — a gating disagreement that
        can let an unsafe edit slip through.
        """
        project = _scaffold_min_project(tmp_path)
        _stage_dogfood_constraints(project)

        db_path = project / ".ast-cache" / "index.db"
        _init_violations_db(db_path)
        _seed_violation(
            db_path,
            rule_id="mcp-no-cli",
            caller_file=TARGET_FILE_REL,
            severity="error",
            caller_line=2,
        )

        tool = _make_safe_to_edit_tool(project)
        result = _run(
            tool.execute({"file_path": TARGET_FILE_REL, "output_format": "json"})
        )

        verdict = result["verdict"]
        assert verdict == "UNSAFE", verdict
        summary = result["agent_summary"]
        assert summary["verdict"] == verdict
        assert f"verdict={verdict}" in summary["summary_line"], summary["summary_line"]
        # The mirrored top-level summary_line must be present and agree too.
        assert "summary_line" in result, sorted(result)
        assert f"verdict={verdict}" in result["summary_line"], result["summary_line"]

    def test_recommendation_matches_escalated_verdict(self, tmp_path: Path) -> None:
        """#1027: ``recommendation`` must agree with the escalated ``verdict``.

        Before the fix, ``recommendation`` was rebuilt from the original,
        un-escalated ``risk`` (``_risk_to_verdict(risk)``), while ``verdict``
        was promoted to UNSAFE by a constraint violation. The result was a
        self-contradicting envelope: ``verdict=UNSAFE`` next to a
        ``recommendation`` that opened with "SAFE to edit". An agent reading
        the two fields gets opposite instructions → false-positive work stop.
        """
        project = _scaffold_min_project(tmp_path)
        _stage_dogfood_constraints(project)

        db_path = project / ".ast-cache" / "index.db"
        _init_violations_db(db_path)
        _seed_violation(
            db_path,
            rule_id="mcp-no-cli",
            caller_file=TARGET_FILE_REL,
            severity="error",
            caller_line=2,
        )

        tool = _make_safe_to_edit_tool(project)
        result = _run(
            tool.execute({"file_path": TARGET_FILE_REL, "output_format": "json"})
        )

        verdict = result["verdict"]
        assert verdict == "UNSAFE", verdict
        recommendation = result["recommendation"]
        # The recommendation is escalated alongside the verdict: it must open
        # with the UNSAFE phrasing and must NOT contain the SAFE-branch text.
        assert recommendation.startswith("UNSAFE to edit"), recommendation
        assert "SAFE to edit (health" not in recommendation, recommendation

    def test_safe_to_edit_emits_CAUTION_on_warn_violation(self, tmp_path: Path) -> None:
        """Only warn-severity → CAUTION (not the legacy ``REVIEW``).

        The mapping must distinguish constraint-driven CAUTION from the
        existing risk-level-driven REVIEW so downstream tooling can see
        ``CAUTION`` and know to surface the violation specifically,
        rather than the generic "this file needs refactor prep" hint.
        """
        project = _scaffold_min_project(tmp_path)
        _stage_dogfood_constraints(project)

        db_path = project / ".ast-cache" / "index.db"
        _init_violations_db(db_path)
        _seed_violation(
            db_path,
            rule_id="mcp-no-cli",
            caller_file=TARGET_FILE_REL,
            severity="warn",
            caller_line=2,
        )

        tool = _make_safe_to_edit_tool(project)
        result = _run(tool.execute({"file_path": TARGET_FILE_REL}))

        assert result["verdict"] == "CAUTION", (
            f"safe_to_edit must return verdict='CAUTION' for warn-severity "
            f"constraint violations. Got: {result.get('verdict')!r}"
        )


# ---------------------------------------------------------------------------
# Change-impact integration
# ---------------------------------------------------------------------------


class TestChangeImpactConstraintIntegration:
    """analyze_change_impact must expose ``constraint_violations``."""

    def test_change_impact_includes_constraint_violations_field(
        self, tmp_path: Path
    ) -> None:
        """When the diff touches a forbidden caller, surface the violation.

        Two requirements:

        1. The response payload has a ``constraint_violations`` field
           (list, may be empty in the no-violation case, but the key
           itself must exist so the agent can branch on its presence
           rather than catching KeyError).
        2. When violations exist for files in the diff, the verdict
           must be promoted to UNSAFE (or CAUTION for warn-only).
           "Diff impact says SAFE but constraints say UNSAFE" is the
           failure mode we explicitly cannot ship.

        We construct a real git diff via the project's own repo: the
        ChangeImpactTool reads ``git diff`` output, so the file we
        seed a violation against must show up in the worktree as
        "changed".
        """
        import os
        import subprocess

        project = _scaffold_min_project(tmp_path)
        _stage_dogfood_constraints(project)

        # Initialise a git repo with one committed state, then dirty
        # the target file so it appears in ``git diff``.
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=project, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=project,
            check=True,
        )
        subprocess.run(["git", "config", "user.name", "test"], cwd=project, check=True)
        subprocess.run(
            ["git", "config", "commit.gpgsign", "false"],
            cwd=project,
            check=True,
        )
        subprocess.run(["git", "add", "-A"], cwd=project, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "initial"],
            cwd=project,
            check=True,
            env={
                **os.environ,
                "GIT_COMMITTER_NAME": "test",
                "GIT_COMMITTER_EMAIL": "test@example.com",
            },
        )

        # Dirty the file so the unstaged diff contains it.
        target = project / TARGET_FILE_REL
        target.write_text(target.read_text() + "\n# touched\n")

        db_path = project / ".ast-cache" / "index.db"
        _init_violations_db(db_path)
        _seed_violation(
            db_path,
            rule_id="mcp-no-cli",
            caller_file=TARGET_FILE_REL,
            severity="error",
            caller_line=2,
        )

        tool = _make_change_impact_tool(project)
        result = _run(tool.execute({"mode": "diff", "output_format": "json"}))

        # (1) The field must exist.
        assert "constraint_violations" in result, (
            f"analyze_change_impact response must include "
            f"'constraint_violations' key. Got keys: {sorted(result)}"
        )

        # (2) The field must be a non-empty list when the diff intersects
        # the violation's caller_file.
        cv = result["constraint_violations"]
        assert isinstance(cv, list)
        assert len(cv) >= 1, (
            f"Expected at least one constraint_violations entry for the "
            f"forbidden caller, got: {cv}"
        )

        # (3) The verdict must promote to UNSAFE — diff impact alone
        # would otherwise have produced INFO/REVIEW.
        assert result.get("verdict") == "UNSAFE", (
            f"analyze_change_impact must promote verdict to UNSAFE when "
            f"the diff touches a file with an error-severity constraint "
            f"violation. Got: {result.get('verdict')!r}"
        )
