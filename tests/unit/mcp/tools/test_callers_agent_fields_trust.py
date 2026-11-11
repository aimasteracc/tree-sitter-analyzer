"""PR #1939 review: agent-native fields must never claim more than their evidence.

Each test pins one over-claim found in review:

1. a shebang / ``__main__.py`` file alone never proves a function is an entry;
2. a console-script module path matches on a path-segment boundary only;
3. ``expires_when`` never invites reuse-without-re-asking when it cannot know
   the index generation (a new call in ANY other file invalidates the answer);
4. ``previous_entries`` deltas never report truncated-away callers as removed;
5. ``test_map`` never proves "untested" from direct test-call edges alone.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.callers_agent_fields import (
    absence_certificate,
    answer_etag,
    callers_delta_response,
    expires_when,
)
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_COMPLETE_ZERO = {"caller_count": 0, "completeness": "complete", "callers": []}
_INCOMPLETE_ZERO = {
    "verdict": "WARN",
    "caller_count": 0,
    "completeness": "unknown",
    "completeness_reasons": ["NON_CALL_REFERENCES"],
}


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _certify(result: dict, root: Path, name: str, path: str) -> dict | None:
    return absence_certificate(
        dict(result), project_root=str(root), function_name=name, file_path=path
    )


# ---------------------------------------------------------------------------
# (1) shebang / __main__.py: a file property never certifies a function
# ---------------------------------------------------------------------------


def test_a_dead_helper_in_a_shebang_script_stays_unreferenced(tmp_path) -> None:
    _write(
        tmp_path,
        "tool.py",
        "#!/usr/bin/env python3\ndef unused_helper():\n    pass\n\n"
        "def main():\n    pass\n\nmain()\n",
    )

    cert = _certify(_COMPLETE_ZERO, tmp_path, "unused_helper", "tool.py")

    assert (cert["kind"], cert["confidence"]) == ("unreferenced", "proven")


def test_a_dead_function_in_dunder_main_stays_unreferenced(tmp_path) -> None:
    _write(tmp_path, "pkg/__main__.py", "def dead():\n    pass\n")

    cert = _certify(_COMPLETE_ZERO, tmp_path, "dead", "pkg/__main__.py")

    assert (cert["kind"], cert["confidence"]) == ("unreferenced", "proven")


@pytest.mark.parametrize(
    ("path", "text"),
    [
        ("run.py", "#!/usr/bin/env python\ndef body():\n    return 1\n"),
        ("pkg/__main__.py", "def entry():\n    return 1\n"),
    ],
)
def test_an_incomplete_script_answer_is_only_a_possible_absence(
    tmp_path, path, text
) -> None:
    """Incomplete + shebang/__main__ → the honest downgrade, never ``proven``."""
    _write(tmp_path, path, text)
    name = "body" if path == "run.py" else "entry"

    cert = _certify(_INCOMPLETE_ZERO, tmp_path, name, path)

    assert (cert["kind"], cert["confidence"]) == ("unknown", "possible")
    assert "identification_only" not in cert


# ---------------------------------------------------------------------------
# (2) console scripts: path-segment boundary, src/ layout, package __init__
# ---------------------------------------------------------------------------


def _scripts(root: Path, target: str) -> None:
    _write(root, "pyproject.toml", f'[project.scripts]\napp = "{target}"\n')


def test_console_script_module_does_not_match_a_longer_file_stem(tmp_path) -> None:
    """``cli:main`` must not certify ``main`` in ``src/mycli.py``."""
    _scripts(tmp_path, "cli:main")
    _write(tmp_path, "src/mycli.py", "def main():\n    pass\n")

    cert = _certify(_COMPLETE_ZERO, tmp_path, "main", "src/mycli.py")

    assert cert["kind"] == "unreferenced"


def test_console_script_module_does_not_match_a_nested_same_named_file(
    tmp_path,
) -> None:
    """``cli:main`` names the top-level module, not ``tests/fixtures/cli.py``."""
    _scripts(tmp_path, "cli:main")
    _write(tmp_path, "tests/fixtures/cli.py", "def main():\n    pass\n")

    cert = _certify(_COMPLETE_ZERO, tmp_path, "main", "tests/fixtures/cli.py")

    assert cert["kind"] == "unreferenced"


@pytest.mark.parametrize(
    ("target", "path"),
    [
        ("cli:main", "cli.py"),
        ("cli:main", "src/cli.py"),
        ("pkg.cli:main", "pkg/cli.py"),
        ("pkg.cli:main", "src/pkg/cli.py"),
        ("pkg:main", "pkg/__init__.py"),
        ("pkg:main", "src/pkg/__init__.py"),
    ],
)
def test_console_script_matches_the_module_file_it_names(tmp_path, target, path):
    _scripts(tmp_path, target)
    _write(tmp_path, path, "def main():\n    pass\n")

    cert = _certify(_COMPLETE_ZERO, tmp_path, "main", path)

    assert (cert["kind"], cert["confidence"]) == ("entry_point", "proven")
    assert cert["evidence"][1]["kind"] == "console_script"


def test_console_script_accepts_an_absolute_declaring_path(tmp_path) -> None:
    _scripts(tmp_path, "pkg.cli:main")
    _write(tmp_path, "pkg/cli.py", "def main():\n    pass\n")

    cert = _certify(_COMPLETE_ZERO, tmp_path, "main", str(tmp_path / "pkg" / "cli.py"))

    assert cert["kind"] == "entry_point"


def test_console_script_requires_the_function_to_be_defined_in_that_file(
    tmp_path,
) -> None:
    """The manifest names ``pkg.cli:main`` but ``pkg/cli.py`` defines no ``main``."""
    _scripts(tmp_path, "pkg.cli:main")
    _write(tmp_path, "pkg/cli.py", "from pkg.impl import main as main\n")

    assert _certify(_INCOMPLETE_ZERO, tmp_path, "main", "pkg/cli.py")["kind"] == (
        "unknown"
    )


def test_a_dotted_console_attribute_does_not_certify_a_module_function(
    tmp_path,
) -> None:
    """``pkg.cli:App.run`` is a method; a module-level ``run`` is not that entry."""
    _scripts(tmp_path, "pkg.cli:App.run")
    _write(
        tmp_path,
        "pkg/cli.py",
        "def run():\n    pass\n\nclass App:\n    def run(self):\n        pass\n",
    )

    assert _certify(_COMPLETE_ZERO, tmp_path, "run", "pkg/cli.py")["kind"] == (
        "unreferenced"
    )


def test_a_stale_answer_never_carries_a_proven_certificate(tmp_path) -> None:
    _scripts(tmp_path, "pkg.cli:main")
    _write(tmp_path, "pkg/cli.py", "def main():\n    pass\n")
    stale = {**_COMPLETE_ZERO, "stale": True}

    assert _certify(stale, tmp_path, "main", "pkg/cli.py")["confidence"] == "possible"
    assert _certify(stale, tmp_path, "other", "lib.py")["confidence"] == "possible"


@pytest.mark.parametrize(
    "open_field",
    [
        {"unattributed_call_sites": 1},
        {"non_call_references": 2},
    ],
)
def test_open_module_or_reference_sites_block_unreferenced(open_field) -> None:
    cert = absence_certificate({**_COMPLETE_ZERO, "verdict": "WARN", **open_field})

    assert (cert["kind"], cert["confidence"]) == ("unknown", "possible")


# ---------------------------------------------------------------------------
# (3) expires_when: reuse without re-asking needs a known generation
# ---------------------------------------------------------------------------


def test_expires_when_without_a_generation_is_not_reusable() -> None:
    scope = expires_when({"file_path": "pkg/mod.py", "callers": []})

    assert (scope["index_generation"], scope["reusable_without_reask"]) == (
        None,
        False,
    )
    assert "re-ask" in scope["rule"]


def test_expires_when_with_a_generation_is_reusable_only_under_both_conditions():
    scope = expires_when(
        {
            "file_path": "pkg/mod.py",
            "callers": [],
            "source_evidence": {"source_generation": "gen-1"},
        }
    )

    assert (scope["index_generation"], scope["reusable_without_reask"]) == (
        "gen-1",
        True,
    )
    assert "index_generation" in scope["rule"] and "files" in scope["rule"]


def test_a_stale_answer_is_never_reusable_without_reasking() -> None:
    scope = expires_when(
        {
            "file_path": "pkg/mod.py",
            "callers": [],
            "stale": True,
            "source_evidence": {"source_generation": "gen-1"},
        }
    )

    assert scope["reusable_without_reask"] is False


@pytest.mark.asyncio
async def test_a_live_callers_answer_does_not_invite_blind_reuse(tmp_path) -> None:
    """End to end: callers never reads a generation, so it must say "re-ask"."""
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    _write(tmp_path, "lib.py", "def target():\n    return 1\n")
    _write(
        tmp_path, "a.py", "from lib import target\n\ndef w():\n    return target()\n"
    )
    await CodeGraphFullIndexTool(str(tmp_path)).execute({"mode": "full"})

    result = await CodeGraphCallersTool(str(tmp_path)).execute(
        {"function_name": "target", "include_bodies": False}
    )

    scope = result["expires_when"]
    assert scope["reusable_without_reask"] is (scope["index_generation"] is not None)
    if scope["index_generation"] is None:
        assert "do not reuse" in scope["rule"]


# ---------------------------------------------------------------------------
# (4) etag / delta: the fingerprint covers every open-site count; a truncated
#     list never yields "removed"
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field",
    [
        "unresolved_inbound",
        "name_only_inbound",
        "unresolved_in_declaring_files",
        "unattributed_call_sites",
        "non_call_references",
        "callers_listed",
    ],
)
def test_answer_etag_changes_when_an_open_site_count_changes(field) -> None:
    base = {"function": "t", "caller_count": 0, "completeness": "unknown", field: 2}

    assert answer_etag(base) != answer_etag({**base, field: 3})


def test_a_truncated_answer_never_returns_a_delta() -> None:
    previous = [{"name": f"c{i}", "file": "a.py", "line": i} for i in range(5)]
    result = {
        "function": "t",
        "caller_count": 5,
        "truncated": True,
        "callers": previous[:2],
        "answer_etag": "sha256:x",
    }

    assert callers_delta_response(result, previous, "t") is None


def test_an_untruncated_answer_returns_its_delta() -> None:
    previous = [{"name": "a", "file": "a.py", "line": 1}]
    result = {
        "function": "t",
        "caller_count": 1,
        "truncated": False,
        "callers": [{"name": "b", "file": "b.py", "line": 2}],
        "answer_etag": "sha256:x",
    }

    response = callers_delta_response(result, previous, "t")

    assert (len(response["delta"]["added"]), len(response["delta"]["removed"])) == (
        1,
        1,
    )
