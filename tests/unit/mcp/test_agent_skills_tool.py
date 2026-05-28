"""Tests for the MCP agent skills inventory tool.

r37fC (round-37f): the quality audit flagged this file at 1/5 — only
three happy-path tests. The block below adds error-path, boundary,
and envelope-contract coverage:

* missing skills_root directory (no ``.agents/skills`` on disk)
* empty skills_root (directory exists but holds no skills)
* malformed front matter (best-effort YAML parser must not raise)
* permission-denied skill file (SKILL.md unreadable)
* large-skill stress path (~50 skills + many support files)
* concurrent re-entrant execute() calls (tool must be stateless)
* envelope contract: verdict ∈ legal vocabulary, summary_line non-empty,
  agent_summary.next_step populated

The tests use real fixture directories (not mocks) and run against
``AgentSkillsTool`` exactly as MCP callers do — ``await
tool.execute({...})``. They never modify tool source; if a bug is
exposed, they mark ``xfail`` with a clear reason so the test board
shows the gap without blocking the suite.
"""

from __future__ import annotations

import asyncio
import sys

import pytest

from tree_sitter_analyzer.mcp.tools.agent_skills_tool import AgentSkillsTool

# Legal verdict vocabulary, mirrored from
# ``tree_sitter_analyzer.mcp.tools.base_tool._LEGAL_VERDICTS``. Kept
# local so the tests still fail loudly if anyone widens the vocabulary
# without updating the contract.
_LEGAL_VERDICTS = frozenset(
    {"SAFE", "CAUTION", "REVIEW", "UNSAFE", "INFO", "WARN", "ERROR", "NOT_FOUND"}
)


def _create_large_skill_fixture(skills_root, index: int) -> str:
    """Create one skill directory + SKILL.md for the large-inventory stress test."""
    name = f"skill-{index:02d}"
    skill_dir = skills_root / name
    skill_dir.mkdir()
    if index % 2 == 0:
        body = (
            f"---\nname: {name}\n"
            "description: Use when testing the large-skill stress path.\n"
            "---\n\n"
            f"# {name}\n\n"
            "## Acceptance Criteria\n\n"
            "- Verification step described here.\n"
        )
    else:
        body = (
            f"---\nname: {name}\n---\n\n# {name}\n\nBody without acceptance criteria.\n"
        )
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")
    for support_idx in range(3):
        (skill_dir / f"NOTES-{support_idx}.md").write_text(
            f"Notes {support_idx} for {name}\n", encoding="utf-8"
        )
    return name


def _probe_chmod_enforcement(skill_path) -> None:
    """Skip the test if the OS did not honour chmod 0 (e.g., running as root)."""
    import os
    import stat

    try:
        with skill_path.open("rb"):
            pass
        os.chmod(skill_path, stat.S_IRUSR | stat.S_IWUSR)
        pytest.skip("OS ignored chmod 0 (likely running as root)")
    except PermissionError:
        pass  # Expected — chmod was enforced.


@pytest.mark.asyncio
async def test_agent_skills_tool_lists_project_skills(tmp_path):
    """MCP output should mirror the CLI inventory shape."""
    skill_dir = tmp_path / ".agents" / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: demo\n"
        "description: Use when testing MCP skill inventory.\n"
        "---\n\n"
        "# Demo\n\n"
        "## Acceptance Criteria\n\n"
        "- MCP sees this skill.\n",
        encoding="utf-8",
    )

    result = await AgentSkillsTool(str(tmp_path)).execute({"output_format": "json"})

    assert result["success"] is True
    assert result["inventory"] == "project agent skills"
    assert result["skill_count"] == 1
    assert result["skills"][0]["name"] == "demo"
    assert result["skills"][0]["ready_for_use"] is True
    assert result["skills"][0]["actionability"] == "ready"
    assert result["agent_summary"]["ready_for_use_count"] == 1
    assert result["skills"][0]["actionability_score"] >= 85
    assert result["validation"]["status"] == "ready"
    assert result["agent_summary"]["inspection_command"] == (
        "uv run tree-sitter-analyzer agent-skills --format json"
    )


@pytest.mark.skipif(
    sys.platform == "win32", reason="Windows path drift — tracked separately"
)
@pytest.mark.asyncio
async def test_agent_skills_tool_supports_custom_relative_root(tmp_path):
    """Custom skills_root should be validated and passed to the shared builder."""
    skill_dir = tmp_path / "docs" / "skills" / "local"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: local\n"
        "description: Use when testing custom roots.\n"
        "---\n\n"
        "# Local\n",
        encoding="utf-8",
    )

    result = await AgentSkillsTool(str(tmp_path)).execute(
        {"skills_root": "docs/skills", "output_format": "toon"}
    )

    assert result["format"] == "toon"
    assert result["skills_root"] == "docs/skills"
    # M2 (round-26): MCP consumers can now see the full skills list, not
    # just the count. The TOON envelope keeps ``toon_content`` for compact
    # rendering AND exposes the structured ``skills`` list alongside.
    assert "skills" in result
    assert isinstance(result["skills"], list)
    assert len(result["skills"]) == result["skill_count"]
    assert result["agent_summary"]["ready_for_use_count"] == 0
    assert result["validation"]["status"] == "caution"
    assert "toon_content" in result
    assert "validation_status: caution" in result["toon_content"]
    assert "local" in result["toon_content"]


@pytest.mark.asyncio
async def test_agent_skills_tool_rejects_external_absolute_root(tmp_path):
    """MCP callers cannot inspect skills outside the configured project root."""
    tool = AgentSkillsTool(str(tmp_path))

    with pytest.raises(ValueError, match="Invalid skills_root"):
        await tool.execute({"skills_root": "/tmp/outside-skills"})


# ----------------------------------------------------------------------
# r37fC: error-path coverage (audit gap — was 1/5 only happy path)
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_skills_tool_missing_skills_root_returns_blocked(tmp_path):
    """A project with no ``.agents/skills`` directory must still answer.

    Audit gap (missing_dir): the original suite only ran against a
    populated skills directory. The contract is that the inventory
    builder gracefully degrades to ``skill_count=0`` and a
    ``validation_status='blocked'`` so the agent_summary stops the
    caller before they invoke a non-existent skill.
    """
    # Note: tmp_path exists but contains no .agents/skills directory.
    result = await AgentSkillsTool(str(tmp_path)).execute({"output_format": "json"})

    assert result["success"] is True
    assert result["skill_count"] == 0
    assert result["skills"] == []
    # The skills_root path is reported as the project-relative default
    # even though it doesn't exist on disk — callers branch on
    # ``skills_root_exists`` to know they need to create it.
    assert result["skills_root_exists"] is False
    assert result["validation"]["status"] == "blocked"
    assert result["agent_summary"]["validation_status"] == "blocked"
    # Verdict contract: blocked → REVIEW per _build_agent_summary.
    assert result["agent_summary"]["verdict"] == "REVIEW"
    assert result["agent_summary"]["verdict"] in _LEGAL_VERDICTS
    # next_step must guide the agent to create the directory.
    assert "create" in result["agent_summary"]["next_step"].lower()
    # Envelope mirrors: top-level summary_line + verdict.
    assert isinstance(result["summary_line"], str) and result["summary_line"]
    assert result["verdict"] == "REVIEW"


@pytest.mark.asyncio
async def test_agent_skills_tool_empty_skills_dir_pins_actual_status(tmp_path):
    """Pin the behaviour of an existing-but-empty skills directory.

    Audit gap (empty): there's a meaningful difference between "no
    skills dir at all" and "skills dir exists with zero skills". The
    current implementation pins ``validation_status='ready'`` for both
    cases when the directory exists, because ``_build_gaps`` only
    flags ``skills_root_missing`` when ``not root_path.exists()`` and
    the empty ``missing_skill_md`` list contributes zero to the
    blocking count.

    This is arguably a UX bug — an empty skills directory still gives
    callers nothing to invoke — but until the design changes the test
    pins the existing behaviour so future refactors trip if the
    semantics flip silently. See r37fC notes.
    """
    skills_dir = tmp_path / ".agents" / "skills"
    skills_dir.mkdir(parents=True)
    # No SKILL.md children — the directory exists but is empty.

    result = await AgentSkillsTool(str(tmp_path)).execute({"output_format": "json"})

    assert result["success"] is True
    assert result["skill_count"] == 0
    assert result["skills_root_exists"] is True
    # Current behaviour (pinned, not aspirational): empty dir → "ready"
    # because no skill files are present to flag as missing metadata.
    assert result["validation"]["status"] == "ready"
    # ``ready`` maps to ``INFO`` per the agent_summary verdict table.
    assert result["agent_summary"]["verdict"] == "INFO"
    assert result["agent_summary"]["verdict"] in _LEGAL_VERDICTS
    assert result["agent_summary"]["readiness_ratio"] == 0.0
    assert result["agent_summary"]["actionable_skills"] == []
    # Top-level mirrors still required even when nothing is found.
    assert isinstance(result["summary_line"], str) and result["summary_line"]
    assert result["verdict"] == "INFO"


@pytest.mark.asyncio
async def test_agent_skills_tool_handles_malformed_yaml_front_matter(tmp_path):
    """A skill whose SKILL.md has broken front matter must not crash.

    Audit gap (malformed_yaml): the project's front-matter reader is a
    purpose-built mini-parser (``cli/agent_skills_metadata.py``) that
    falls back to "no metadata" on bad input — not a full YAML parser
    that would raise. The contract: the skill still appears in the
    inventory but lands in the ``missing_name``/``missing_description``
    gap bucket so callers see the broken state explicitly.
    """
    skill_dir = tmp_path / ".agents" / "skills" / "broken"
    skill_dir.mkdir(parents=True)
    # Front-matter delimiter is present but inner content is unparseable
    # garbage (no key:value lines, just freeform text + bogus colons).
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "this is not yaml: [unterminated\n"
        "  - nested item with no key\n"
        "***   garbage   ***\n"
        "---\n\n"
        "# Broken skill\n\n"
        "Body without acceptance criteria.\n",
        encoding="utf-8",
    )

    result = await AgentSkillsTool(str(tmp_path)).execute({"output_format": "json"})

    assert result["success"] is True
    assert result["skill_count"] == 1
    skill = result["skills"][0]
    # The directory name is the fallback when the front-matter has no
    # ``name`` key.
    assert skill["name"] == "broken"
    # Missing-name and missing-description should both be flagged.
    assert "missing_name" in skill["gaps"]
    assert "missing_description" in skill["gaps"]
    # The skill is not ready for use — actionability score must reflect.
    assert skill["ready_for_use"] is False
    # Aggregate gaps should pick up the broken skill.
    assert "broken" in result["gaps"]["missing_trigger_text"]
    # Verdict still in canonical vocabulary.
    assert result["agent_summary"]["verdict"] in _LEGAL_VERDICTS


@pytest.mark.xfail(
    reason=(
        "r37fC bug: cli/agent_skills_metadata.read_skill_metadata uses "
        "Path.read_text(errors='replace') which only suppresses *decoding* "
        "errors. A permission-denied read raises PermissionError unhandled "
        "and crashes the whole inventory build — one bad SKILL.md takes "
        "down the entire tool. Fix: wrap the read in try/except OSError and "
        "treat it as 'missing_skill_md'."
    ),
    raises=PermissionError,
    strict=True,
)
@pytest.mark.asyncio
async def test_agent_skills_tool_permission_denied_skill_is_still_listed(tmp_path):
    """One unreadable SKILL.md must not crash the whole inventory build.

    Audit gap (permission_error): the parser uses ``errors='replace'``
    on ``Path.read_text`` — but that flag only suppresses decoding
    errors. A permission-denied I/O raises ``PermissionError`` before
    decoding starts, and it bubbles all the way out of
    :func:`build_agent_skills_inventory`. The contract this test
    encodes (currently xfail): the tool should treat an unreadable
    skill as ``missing_skill_md`` and continue, so a single broken
    file does not poison the entire response.

    Marked ``xfail strict=True``: when the fix lands, the test
    automatically flips to pass and the xfail marker can be removed.
    Skipped on platforms where chmod 0 is not enforced (CI as root).
    """
    import os
    import stat

    skill_dir = tmp_path / ".agents" / "skills" / "locked"
    skill_dir.mkdir(parents=True)
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(
        "---\n"
        "name: locked\n"
        "description: Use when testing permission errors.\n"
        "---\n\n"
        "# Locked\n\n"
        "## Acceptance Criteria\n\n"
        "- Skill should be readable.\n",
        encoding="utf-8",
    )
    # Strip every permission bit — makes the file unreadable on non-root Linux/macOS.
    os.chmod(skill_path, 0)
    _probe_chmod_enforcement(skill_path)

    try:
        result = await AgentSkillsTool(str(tmp_path)).execute({"output_format": "json"})
    finally:
        # Restore so pytest's tmp_path teardown can delete the file.
        os.chmod(skill_path, stat.S_IRUSR | stat.S_IWUSR)

    # If we get here, the bug is fixed — pin the recovered contract.
    assert result["success"] is True
    names = {skill["name"] for skill in result["skills"]}
    assert "locked" in names
    locked_skill = next(
        skill for skill in result["skills"] if skill["name"] == "locked"
    )
    assert locked_skill["ready_for_use"] is False
    assert result["agent_summary"]["verdict"] in _LEGAL_VERDICTS


@pytest.mark.asyncio
async def test_agent_skills_tool_handles_large_inventory(tmp_path):
    """A 50-skill inventory must build quickly and stay sorted.

    Audit gap (large-skill): the original suite only ran with a single
    skill. With dozens of skills the sort and dedupe loops dominate;
    the contract: the response must remain alphabetically sorted by
    name and the agent_summary must reflect aggregate counts.
    """
    import time

    skills_root = tmp_path / ".agents" / "skills"
    skills_root.mkdir(parents=True)

    # Build 50 skills, alternating ready / missing-description.
    expected_names = [_create_large_skill_fixture(skills_root, i) for i in range(50)]

    start = time.perf_counter()
    result = await AgentSkillsTool(str(tmp_path)).execute({"output_format": "json"})
    duration = time.perf_counter() - start

    # Performance gate: should fit comfortably in 5 seconds on CI.
    assert duration < 5.0, (
        f"Inventory of 50 skills took {duration:.2f}s — perf regression suspected"
    )
    assert result["success"] is True
    assert result["skill_count"] == 50
    # Names returned in sort order.
    actual_names = [skill["name"] for skill in result["skills"]]
    assert actual_names == sorted(expected_names)
    # Half of the skills are ready (even-indexed).
    assert result["agent_summary"]["ready_for_use_count"] == 25
    assert result["agent_summary"]["readiness_ratio"] == round(25 / 50, 2)
    assert result["agent_summary"]["verdict"] in _LEGAL_VERDICTS


@pytest.mark.asyncio
async def test_agent_skills_tool_concurrent_calls_are_safe(tmp_path):
    """Re-entrant concurrent calls must each return an independent result.

    Audit gap (concurrent / re-entrant): the tool keeps a single
    ``SecurityValidator`` per instance but no per-call state. Two
    parallel ``execute`` calls must each produce a complete inventory
    that doesn't share lists with the other call.
    """
    skill_dir = tmp_path / ".agents" / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: demo\n"
        "description: Use when testing concurrent execute calls.\n"
        "---\n\n"
        "# Demo\n\n"
        "## Acceptance Criteria\n\n"
        "- Concurrent path is safe.\n",
        encoding="utf-8",
    )
    tool = AgentSkillsTool(str(tmp_path))

    # Fire 8 concurrent calls — gather waits for all to complete.
    results = await asyncio.gather(
        *(tool.execute({"output_format": "json"}) for _ in range(8)),
    )

    assert all(result["success"] is True for result in results)
    assert all(result["skill_count"] == 1 for result in results)
    # Each call should have its own ``skills`` list — no shared mutation.
    skill_lists = [id(result["skills"]) for result in results]
    assert len(set(skill_lists)) == len(skill_lists), (
        "execute() leaks the same list reference across concurrent calls — "
        "callers mutating the response would corrupt other callers"
    )
    # Content equivalence: every call sees the same demo skill.
    assert all(result["skills"][0]["name"] == "demo" for result in results)


@pytest.mark.asyncio
async def test_agent_skills_tool_envelope_contract_holds(tmp_path):
    """Both output formats must honour the canonical envelope.

    Audit gap (envelope contract): the original suite only spot-checked
    a couple of fields per format. This pins the full cross-format
    contract — verdict ∈ legal vocabulary, summary_line populated,
    agent_summary.next_step non-empty — on a single fixture so a
    drift on either format trips the test.
    """
    skill_dir = tmp_path / ".agents" / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: demo\n"
        "description: Use when testing the envelope contract.\n"
        "---\n\n"
        "# Demo\n\n"
        "## Acceptance Criteria\n\n"
        "- Envelope is canonical.\n",
        encoding="utf-8",
    )
    tool = AgentSkillsTool(str(tmp_path))

    for output_format in ("json", "toon"):
        result = await tool.execute({"output_format": output_format})
        assert result["success"] is True, (
            f"format={output_format} returned success=False"
        )
        agent_summary = result["agent_summary"]
        # verdict surface — required vocabulary on every tool.
        assert agent_summary["verdict"] in _LEGAL_VERDICTS, (
            f"agent_summary.verdict drifted for format={output_format}"
        )
        # next_step surface — must be a non-empty hint.
        next_step = agent_summary["next_step"]
        assert isinstance(next_step, str) and next_step.strip(), (
            f"agent_summary.next_step empty for format={output_format}"
        )
        # summary_line mirror — both surfaces match.
        summary_line = result.get("summary_line")
        assert isinstance(summary_line, str) and summary_line, (
            f"top-level summary_line missing for format={output_format}"
        )
        assert summary_line == agent_summary.get("summary_line"), (
            f"summary_line mirror diverges for format={output_format}"
        )
        # Top-level verdict mirror.
        assert result.get("verdict") == agent_summary["verdict"], (
            f"top-level verdict mirror diverges for format={output_format}"
        )
