"""Tests for ``tree_sitter_analyzer.security.fixture_detector`` (P3).

Two responsibilities are tested independently:

* **Detection** (``is_fixture``, ``list_fixtures``) — the
  allowlist-then-AST-scan pipeline with content-hash caching.
* **Verdict mapping** (``fixture_to_verdict``) — confidence → ``UNSAFE`` /
  ``CAUTION`` / ``None``, the contract that ``safe_to_edit_helpers``
  consumes via ``_max_verdict``.

The most important regression test in this file is
``test_real_repo_finds_java_plugin`` — it pins the
``feedback_test-fixture-files`` incident class. If that test regresses,
agents can refactor ``java_plugin.py`` again and re-burn a session.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from tree_sitter_analyzer.security.fixture_detector import (
    FixtureFact,
    fixture_to_verdict,
    is_fixture,
    list_fixtures,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_project(tmp_path: Path, files: dict[str, str]) -> Path:
    """Materialise a fake project tree under ``tmp_path``.

    ``files`` maps repo-relative paths (POSIX form) to file bodies. The
    returned ``Path`` is the project root.
    """

    root = tmp_path / "project"
    root.mkdir()
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


def _frontmatter(allowlist: list[dict[str, str]]) -> str:
    """Render an ``intentional_design``-style CLAUDE.md frontmatter block."""

    body = ["---", "fixture_allowlist:"]
    for entry in allowlist:
        body.append(f"  - path: {entry['path']}")
        body.append(f"    note: {entry.get('note', '')!r}")
    body.append("---")
    body.append("")
    body.append("# Body prose follows the frontmatter.")
    return "\n".join(body) + "\n"


# ---------------------------------------------------------------------------
# Tier 1 — allowlist
# ---------------------------------------------------------------------------


class TestAllowlist:
    def test_allowlist_hit_returns_confidence_1(self, tmp_path: Path) -> None:
        root = _make_project(
            tmp_path,
            {
                "CLAUDE.md": _frontmatter(
                    [{"path": "tree_sitter_analyzer/foo.py", "note": "test note"}]
                ),
                "tree_sitter_analyzer/foo.py": "def f(): pass\n",
            },
        )
        fact = is_fixture("tree_sitter_analyzer/foo.py", root)
        assert isinstance(fact, FixtureFact)
        assert fact.is_fixture is True
        assert fact.confidence == 1.0
        assert fact.source == "allowlist"
        assert fact.note == "test note"

    def test_no_claude_md_returns_negative(self, tmp_path: Path) -> None:
        root = _make_project(
            tmp_path, {"tree_sitter_analyzer/foo.py": "def f(): pass\n"}
        )
        fact = is_fixture("tree_sitter_analyzer/foo.py", root)
        assert fact.is_fixture is False
        assert fact.source == "none"

    def test_path_outside_project_returns_negative(self, tmp_path: Path) -> None:
        root = _make_project(tmp_path, {"x.py": ""})
        # Absolute path that can't be made relative to root.
        fact = is_fixture("/tmp/does_not_exist.py", root)
        assert fact.is_fixture is False


# ---------------------------------------------------------------------------
# Tier 2 — AST scan
# ---------------------------------------------------------------------------


class TestTier2Scan:
    def test_sample_python_constant_idiom(self, tmp_path: Path) -> None:
        # The canonical pattern observed in
        # tests/unit/mcp/test_refactoring_suggestions_tool.py — a
        # SAMPLE_* assigned to ``str(PROJECT_ROOT / ... / "foo.py")``
        # should mark foo.py as a fixture (0.85+ confidence ⇒ UNSAFE).
        test_body = (
            "from pathlib import Path\n"
            "PROJECT_ROOT = Path(__file__).parent.parent\n"
            "SAMPLE_FOO = str(PROJECT_ROOT / 'tree_sitter_analyzer' / 'foo.py')\n"
        )
        root = _make_project(
            tmp_path,
            {
                "tests/test_x.py": test_body,
                "tree_sitter_analyzer/foo.py": "def f(): pass\n",
            },
        )
        fact = is_fixture("tree_sitter_analyzer/foo.py", root)
        assert fact.is_fixture is True
        assert fact.confidence >= 0.85
        assert fact.source in {"path_literal", "constant_assignment"}
        assert any("test_x.py" in line for line in fact.evidence)

    def test_bare_repo_relative_literal_is_caution(self, tmp_path: Path) -> None:
        # A bare string ``"tree_sitter_analyzer/foo.py"`` outside any
        # SAMPLE_ assignment hits the lowest-confidence tier (0.7).
        # That translates to CAUTION (per fixture_to_verdict), not
        # UNSAFE.
        root = _make_project(
            tmp_path,
            {
                "tests/test_x.py": "name = 'tree_sitter_analyzer/foo.py'\n",
                "tree_sitter_analyzer/foo.py": "def f(): pass\n",
            },
        )
        fact = is_fixture("tree_sitter_analyzer/foo.py", root)
        assert fact.is_fixture is True
        assert 0.7 <= fact.confidence < 0.85
        assert fixture_to_verdict(fact) == "CAUTION"

    def test_plugin_manifest_exclusion(self, tmp_path: Path) -> None:
        # A list of plugin filenames (≥3 siblings matching *_plugin.py)
        # should NOT mark java_plugin.py as a fixture — it is being
        # tested *as a plugin*, not used as a fixture.
        test_body = (
            "PLUGINS = ['go_plugin.py', 'java_plugin.py', "
            "'python_plugin.py', 'rust_plugin.py']\n"
        )
        root = _make_project(
            tmp_path,
            {
                "tests/test_plugins.py": test_body,
                "tree_sitter_analyzer/languages/java_plugin.py": "X = 1\n",
            },
        )
        fact = is_fixture("tree_sitter_analyzer/languages/java_plugin.py", root)
        # No other signal exists → suppressed → negative.
        assert fact.is_fixture is False

    def test_no_signal_returns_negative(self, tmp_path: Path) -> None:
        # tests/ exists but doesn't reference foo.py in any way → False.
        root = _make_project(
            tmp_path,
            {
                "tests/test_x.py": "def test_x(): assert True\n",
                "tree_sitter_analyzer/foo.py": "def f(): pass\n",
            },
        )
        fact = is_fixture("tree_sitter_analyzer/foo.py", root)
        assert fact.is_fixture is False


class TestRealRepoRegression:
    def test_real_repo_finds_java_plugin(self) -> None:
        # Regression test for feedback_test-fixture-files (memory):
        # java_plugin.py IS a negative fixture in the real repo and the
        # detector must flag it as UNSAFE-grade.
        target = "tree_sitter_analyzer/languages/java_plugin.py"
        fact = is_fixture(target, REPO_ROOT)
        assert fact.is_fixture is True, (
            f"Real-repo detection failed for {target}; got {fact!r}. "
            "This is the canary for feedback_test-fixture-files."
        )
        # confidence must be high enough to escalate safe_to_edit to UNSAFE.
        assert fact.confidence >= 0.85
        assert len(fact.evidence) >= 1


# ---------------------------------------------------------------------------
# Cache behaviour
# ---------------------------------------------------------------------------


class TestCache:
    def test_cache_written_on_first_scan(self, tmp_path: Path) -> None:
        root = _make_project(
            tmp_path,
            {
                "tests/test_x.py": (
                    "from pathlib import Path\n"
                    "PROJECT_ROOT = Path('.')\n"
                    "name = PROJECT_ROOT / 'tree_sitter_analyzer' / 'foo.py'\n"
                ),
                "tree_sitter_analyzer/foo.py": "",
            },
        )
        assert not (root / ".ast-cache" / "fixture_index.json").exists()
        is_fixture("tree_sitter_analyzer/foo.py", root)
        assert (root / ".ast-cache" / "fixture_index.json").is_file()

    def test_cache_corrupt_falls_through_to_scan(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        root = _make_project(
            tmp_path,
            {
                "tests/test_x.py": (
                    "from pathlib import Path\n"
                    "PROJECT_ROOT = Path('.')\n"
                    "SAMPLE_FOO = PROJECT_ROOT / 'tree_sitter_analyzer' / 'foo.py'\n"
                ),
                "tree_sitter_analyzer/foo.py": "",
            },
        )
        cache_path = root / ".ast-cache" / "fixture_index.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text("{not valid json", encoding="utf-8")

        with caplog.at_level(
            logging.WARNING,
            logger="tree_sitter_analyzer.security.fixture_detector",
        ):
            fact = is_fixture("tree_sitter_analyzer/foo.py", root)

        # Detection still works despite the broken cache …
        assert fact.is_fixture is True
        # … and the broken cache produces a single warning so the
        # operator notices.
        assert any("cache" in record.message.lower() for record in caplog.records)


# ---------------------------------------------------------------------------
# Verdict mapping
# ---------------------------------------------------------------------------


class TestVerdictMapping:
    @pytest.mark.parametrize(
        "confidence, expected",
        [
            (1.0, "UNSAFE"),
            (0.9, "UNSAFE"),
            (0.85, "UNSAFE"),
            (0.84, "CAUTION"),
            (0.7, "CAUTION"),
            (0.69, None),
            (0.5, None),
            (0.0, None),
        ],
    )
    def test_threshold_mapping(self, confidence: float, expected: str | None) -> None:
        fact = FixtureFact(
            is_fixture=confidence >= 0.7,
            confidence=confidence,
            source="test",
            evidence=(),
            note="",
        )
        assert fixture_to_verdict(fact) == expected

    def test_unsafe_threshold_is_inclusive(self) -> None:
        # The boundary at 0.85 must be UNSAFE — fixture-with-evidence
        # must not slip into CAUTION because of floating-point quirks.
        fact = FixtureFact(True, 0.85, "src", ("e",), "")
        assert fixture_to_verdict(fact) == "UNSAFE"


# ---------------------------------------------------------------------------
# Disable env var (roll-back lever)
# ---------------------------------------------------------------------------


class TestDisableEnvVar:
    def test_disable_short_circuits_detection(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Even an explicit allowlist entry must be ignored when the
        # roll-back env var is set — this is the kill-switch.
        root = _make_project(
            tmp_path,
            {
                "CLAUDE.md": _frontmatter(
                    [{"path": "tree_sitter_analyzer/foo.py", "note": "n"}]
                ),
                "tree_sitter_analyzer/foo.py": "",
            },
        )
        monkeypatch.setenv("TSA_DISABLE_FIXTURE_DETECTION", "1")
        fact = is_fixture("tree_sitter_analyzer/foo.py", root)
        assert fact.is_fixture is False
        assert fact.source == "disabled"
        # list_fixtures must also short-circuit.
        assert list_fixtures(root) == []


# ---------------------------------------------------------------------------
# list_fixtures
# ---------------------------------------------------------------------------


class TestListFixtures:
    def test_list_includes_allowlist_and_scanned(self, tmp_path: Path) -> None:
        root = _make_project(
            tmp_path,
            {
                "CLAUDE.md": _frontmatter(
                    [
                        {
                            "path": "tree_sitter_analyzer/allowed.py",
                            "note": "allowlist note",
                        }
                    ]
                ),
                "tree_sitter_analyzer/allowed.py": "",
                "tree_sitter_analyzer/scanned.py": "",
                "tests/test_x.py": (
                    "from pathlib import Path\n"
                    "PROJECT_ROOT = Path('.')\n"
                    "SAMPLE_X = PROJECT_ROOT / 'tree_sitter_analyzer' / 'scanned.py'\n"
                ),
            },
        )
        facts = list_fixtures(root)
        sources = {fact.source for fact in facts}
        assert "allowlist" in sources
        # Tier-2 source labels are "path_literal" / "constant_assignment".
        assert sources & {"path_literal", "constant_assignment"}

        # Sorted by descending confidence — allowlist (1.0) must come
        # before any Tier-2 fact.
        assert facts[0].confidence == 1.0

    def test_empty_project_returns_empty_list(self, tmp_path: Path) -> None:
        root = _make_project(tmp_path, {})
        assert list_fixtures(root) == []
