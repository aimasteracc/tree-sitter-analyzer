"""Contract tests split from the former agent workflow monolith."""
# ruff: noqa: F401

from __future__ import annotations

import ast
import configparser
import os
import re
from pathlib import Path

import pytest

try:
    import tomllib  # Python 3.11+ stdlib
except ImportError:  # Python 3.10 — fall back to the tomli back-port
    import tomli as tomllib
from hypothesis import settings as hypothesis_settings

from tree_sitter_analyzer.cli_main import create_argument_parser
from tree_sitter_analyzer.mcp.server import _create_tool_registry

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKIPPED_SCAN_DIRS = {
    ".git",
    ".benchmark-repos",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".uv-cache",
    ".venv",
}

# ---------------------------------------------------------------------------
# v1.13 postmortem defenses — see docs/POSTMORTEM_v1.13.md
# ---------------------------------------------------------------------------


def test_postmortem_v1_13_doc_exists() -> None:
    """The v1.13 postmortem is the source of truth for the anti-patterns
    catalogued in AGENTS.md. If the doc gets deleted, the anti-pattern
    rules lose their explanation and become cargo-cult.
    """
    doc = PROJECT_ROOT / "docs" / "POSTMORTEM_v1.13.md"
    assert doc.exists(), (
        "docs/POSTMORTEM_v1.13.md must exist — it documents the failure "
        "modes the AGENTS.md Anti-Patterns section is defending against."
    )
    text = doc.read_text(encoding="utf-8")
    # Each numbered section is a defended failure mode. If any of these
    # headings goes away, AGENTS.md will reference a missing anchor.
    for section in (
        "Skip-and-paper-over",
        "GitFlow not enforced",
        "YAML block scalar",
        "Stale `@v1` action ref",
        "Windows PowerShell 5.1",
        "tree-sitter-c-sharp 0.23.1",
        "Python 3.10 compat",
        "Branch divergence",
        "`--maxfail=10`",
        "Squash-merged 95-commit PR",
    ):
        assert section in text, (
            f"docs/POSTMORTEM_v1.13.md must keep its {section!r} section — "
            "it's referenced by AGENTS.md Anti-Patterns."
        )


def test_agents_md_documents_v1_13_anti_patterns() -> None:
    """AGENTS.md must surface the v1.13 anti-patterns so they hit any
    agent reading it. Without this, the postmortem becomes a one-time
    read instead of a standing rule.
    """
    agents_md = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    # Section header
    assert "Anti-Patterns (from v1.13 postmortem)" in agents_md, (
        "AGENTS.md must contain an 'Anti-Patterns (from v1.13 postmortem)' "
        "section. See docs/POSTMORTEM_v1.13.md for the catalogue."
    )
    # Pointer to the doc itself
    assert "POSTMORTEM_v1.13.md" in agents_md, (
        "The Anti-Patterns section must link back to docs/POSTMORTEM_v1.13.md."
    )


def test_check_ps_ascii_script_is_present_and_pre_commit_wired() -> None:
    """The non-ASCII PowerShell guard must remain wired into pre-commit.
    Without the hook, the rule is just a script nobody runs.
    """
    script = PROJECT_ROOT / "scripts" / "check_ps_ascii.py"
    config = PROJECT_ROOT / ".pre-commit-config.yaml"
    assert script.exists(), (
        "scripts/check_ps_ascii.py must exist — it guards against the "
        "Windows PowerShell 5.1 cp1252 mojibake incident "
        "(docs/POSTMORTEM_v1.13.md sec 5)."
    )
    config_text = config.read_text(encoding="utf-8")
    assert "check_ps_ascii.py" in config_text, (
        ".pre-commit-config.yaml must wire scripts/check_ps_ascii.py "
        "into a `repo: local` hook so emoji can't sneak into Windows "
        "PowerShell blocks at commit time."
    )


def test_actionlint_is_wired_into_pre_commit() -> None:
    """actionlint catches the failure class behind PR #138 — dead
    `uses:` refs and bad GitHub Actions expression syntax. Without it,
    YAML-valid-but-Actions-invalid workflows produce phantom
    `startup_failure` runs that are nearly impossible to diagnose from
    the GH Actions UI.
    """
    config = (PROJECT_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "rhysd/actionlint" in config, (
        ".pre-commit-config.yaml must include the rhysd/actionlint hook — "
        "see docs/POSTMORTEM_v1.13.md sec 4."
    )


def test_no_powershell_blocks_contain_non_ascii() -> None:
    """End-to-end check at test time, complementing the pre-commit hook.
    The hook catches diffs at commit; this test catches drift in code
    that escaped via --no-verify, squash-merge, or hook-bypassed
    automation.
    """
    import importlib.util

    script = PROJECT_ROOT / "scripts" / "check_ps_ascii.py"
    spec = importlib.util.spec_from_file_location("check_ps_ascii", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Stash cwd OUTSIDE the chdir so we always have something to restore,
    # then put the chdir inside the try so any failure between chdir and
    # restore-cwd still runs the finally. Without this, an exception
    # raised by exec_module / glob / scan_file would leak the changed
    # cwd to the xdist worker and corrupt every subsequent test.
    cwd = os.getcwd()
    offenders: list[str] = []
    try:
        os.chdir(PROJECT_ROOT)
        spec.loader.exec_module(module)
        import glob

        yaml_paths = sorted(
            set(
                glob.glob(".github/workflows/*.yml")
                + glob.glob(".github/workflows/*.yaml")
                + glob.glob(".github/actions/**/action.yml", recursive=True)
                + glob.glob(".github/actions/**/action.yaml", recursive=True)
            )
        )
        for path in yaml_paths:
            hits = module.scan_file(path)
            for line_no, col, ln in hits:
                offenders.append(f"{path}:{line_no}:{col}: {ln.rstrip()}")
    finally:
        os.chdir(cwd)
    assert offenders == [], (
        "Found non-ASCII bytes inside `shell: powershell` run blocks. "
        "Windows PowerShell 5.1 will trip TerminatorExpectedAtEndOfString. "
        "See docs/POSTMORTEM_v1.13.md sec 5. Offenders:\n  " + "\n  ".join(offenders)
    )


def test_skips_have_tracking_references() -> None:
    """Every ``pytest.skip``/``pytest.mark.skipif`` MUST carry a tracking
    reference in its reason text — issue number, postmortem section,
    or 'tracked: ...' tag.

    Why: r34/r36 dogfood rounds revealed multiple ``skip`` calls used
    as paper-over for real product bugs. Without a tracking reference,
    the skip becomes invisible institutional debt. With one, the next
    agent can grep for it and reopen the conversation.

    Acceptable patterns in the ``reason=...`` text:
      * ``"#123"`` or ``"GH-123"`` or ``"issue 123"`` — issue tracker
      * ``"POSTMORTEM"`` — links back to a documented incident
      * ``"tracked: <something>"`` — explicit follow-up marker
      * ``"flaky"`` plus a ``# tracked`` neighbouring comment

    Pre-existing skips are grandfathered via the
    ``GRANDFATHERED_SKIPS`` allowlist. To remove an entry, fix the
    underlying bug and delete the skip — do not extend the allowlist
    without filing a tracking issue.
    """
    skip_call_re = re.compile(
        r"(?:pytest\.skip|pytest\.mark\.skipif|pytest\.mark\.skip)\b"
    )
    has_tracker = re.compile(
        r"#\d+|GH-\d+|issue\s+\d+|POSTMORTEM|tracked\s*:|TODO\b|FIXME\b|XXX\b",
        re.IGNORECASE,
    )
    tests_root = PROJECT_ROOT / "tests"
    untracked: list[str] = []

    for path in sorted(tests_root.rglob("*.py")):
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        if not skip_call_re.search(text):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if not skip_call_re.search(line):
                continue
            # Stitch up to 8 surrounding lines so multi-line decorators
            # and split reason= strings get inspected as a unit.
            start = max(0, lineno - 4)
            end = min(len(text.splitlines()), lineno + 4)
            window = "\n".join(text.splitlines()[start:end])
            if has_tracker.search(window):
                continue
            untracked.append(f"{rel}:{lineno}: {line.strip()}")

    if untracked:
        # Ratchet pattern: ``BUDGET`` is the count at the time this
        # contract landed. The test FAILS the moment a new untracked
        # skip pushes the count above the budget. To add a new skip
        # you MUST either:
        #   (a) give the new skip a tracking reference (issue #,
        #       POSTMORTEM, or 'tracked:' tag), or
        #   (b) fix an existing untracked skip first and drop BUDGET
        #       by 1 in the same commit.
        # This lets the rule start applying immediately without a
        # big-bang cleanup PR, and forces the count to monotonically
        # shrink.
        BUDGET = 291
        msg = (
            f"{len(untracked)} pytest skip/skipif call(s) lack a tracking "
            f"reference (issue #, POSTMORTEM, or 'tracked:' tag).\n"
            f"Budget: {BUDGET}. See docs/POSTMORTEM_v1.13.md sec 1.\n"
            f"Offenders (first 20):\n  " + "\n  ".join(untracked[:20])
        )
        # Print so a green run still surfaces the count.
        print(msg)
        assert len(untracked) <= BUDGET, msg


def test_python_version_floor_is_consistent() -> None:
    """The repo's Python floor must be expressed coherently across
    pyproject.toml, ruff target-version, and mypy python_version.

    Why: the v1.13 release shipped ``from datetime import UTC`` and
    ``import tomllib`` against a ``>=3.10`` floor. Both are 3.11+
    stdlib. Local dev was on 3.14 so the bug only surfaced in CI.

    Defense: assert all three knobs agree on the floor.
    """
    pyproject_path = PROJECT_ROOT / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    requires_python = pyproject["project"]["requires-python"]
    # Expect ">=3.10" or similar
    floor_match = re.search(r">=\s*(3\.\d+)", requires_python)
    assert floor_match, (
        f"Expected requires-python to declare a >=3.x floor; got {requires_python!r}"
    )
    floor = floor_match.group(1)
    floor_short = "py" + floor.replace(".", "")  # "py310"

    # ruff target-version
    ruff_target = pyproject.get("tool", {}).get("ruff", {}).get("target-version", "")
    if ruff_target:
        assert ruff_target == floor_short, (
            f"[tool.ruff].target-version is {ruff_target!r} but "
            f"[project].requires-python implies {floor_short!r}. "
            "See docs/POSTMORTEM_v1.13.md sec 7."
        )

    # mypy python_version
    mypy_pyver = pyproject.get("tool", {}).get("mypy", {}).get("python_version", "")
    if mypy_pyver:
        assert mypy_pyver == floor, (
            f"[tool.mypy].python_version is {mypy_pyver!r} but "
            f"[project].requires-python implies {floor!r}. "
            "See docs/POSTMORTEM_v1.13.md sec 7."
        )


def test_readme_counts_match_registry() -> None:
    """README headline numbers must match the actual registry counts.

    The v1.13.1 audit found ``README.md`` claiming "50 MCP tools" while
    the registry actually exposed 58, and "248 CLI flags" while the
    parser exposed 237. The ``tsa-codemap-sync`` hook guards
    ``docs/CODEMAPS/*.md`` but not prose docs, so drift accumulated
    silently across three locales (en/ja/zh).

    This contract closes that gap. For each headline number in any
    ``README*.md``, assert it matches the live count derived from
    source. If you change the registry, run the suite — the test will
    tell you which README lines need a refresh, and which number.
    """
    # ---- Authoritative counts ---------------------------------------
    tool_count = len(_create_tool_registry(str(PROJECT_ROOT))[0])

    parser = create_argument_parser()
    long_flags = {
        s for a in parser._actions for s in a.option_strings if s.startswith("--")
    }
    flag_count = len(long_flags)

    # ---- README claims to verify ------------------------------------
    # Each entry: (file, regex that captures the integer, expected_value, human label).
    # The regex must contain a single group `(\d+)` over the number.
    claims = [
        # MCP tool counts — appear at top, in skill section, and in
        # "All N tools" sentence. Each locale has 3 mentions.
        (
            "README.md",
            re.compile(r"(\d+) MCP tools"),
            tool_count,
            "MCP tool count (en headline)",
        ),
        (
            "README.md",
            re.compile(r"triage (\d+) tools"),
            tool_count,
            "MCP tool count (en skills paragraph)",
        ),
        (
            "README.md",
            re.compile(r"All (\d+) tools read"),
            tool_count,
            "MCP tool count (en cache section)",
        ),
        (
            "README_ja.md",
            re.compile(r"(\d+) MCP ツール"),
            tool_count,
            "MCP tool count (ja headline)",
        ),
        (
            "README_ja.md",
            re.compile(r"(\d+) 個のツール"),
            tool_count,
            "MCP tool count (ja skills paragraph)",
        ),
        (
            "README_zh.md",
            re.compile(r"(\d+) 个 MCP 工具"),
            tool_count,
            "MCP tool count (zh headline)",
        ),
        (
            "README_zh.md",
            re.compile(r"(\d+) 个工具间"),
            tool_count,
            "MCP tool count (zh skills paragraph)",
        ),
        (
            "README_zh.md",
            re.compile(r"所有 (\d+) 个工具"),
            tool_count,
            "MCP tool count (zh cache section)",
        ),
        # CLI flag counts — section headers
        (
            "README.md",
            re.compile(r"### (\d+) CLI flags"),
            flag_count,
            "CLI flag count (en section)",
        ),
        (
            "README_ja.md",
            re.compile(r"### (\d+) の CLI フラグ"),
            flag_count,
            "CLI flag count (ja section)",
        ),
        (
            "README_zh.md",
            re.compile(r"### (\d+) 个 CLI flag"),
            flag_count,
            "CLI flag count (zh section)",
        ),
    ]

    failures: list[str] = []
    for filename, pattern, expected, label in claims:
        path = PROJECT_ROOT / filename
        text = path.read_text(encoding="utf-8")
        match = pattern.search(text)
        if match is None:
            failures.append(
                f"{filename}: {label} — pattern {pattern.pattern!r} did not match. "
                "Did the README copy change? Update the regex in this test "
                "OR restore the original wording."
            )
            continue
        found = int(match.group(1))
        if found != expected:
            failures.append(
                f"{filename}: {label} — README says {found}, registry says "
                f"{expected}. Either update the README number to {expected}, "
                "or, if this README claim is intentionally rounded, drop the "
                "specific number and update this test."
            )

    assert failures == [], "README ↔ registry drift:\n  " + "\n  ".join(failures)
