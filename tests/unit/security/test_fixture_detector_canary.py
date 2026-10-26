"""The java_plugin.py fixture canary (feedback_test-fixture-files).

If this regresses, agents can refactor ``java_plugin.py`` again and re-burn a
session. Split from ``test_fixture_detector.py`` to keep that file under the
800-line threshold.
"""

from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.security.fixture_detector import (
    fixture_to_verdict,
    is_fixture,
)


def _make_project(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


class TestRealRepoRegression:
    """The feedback_test-fixture-files incident, on a tree that reproduces it.

    This used to scan the whole repository from a unit test: ~7 s after #1784
    and a 30 s timeout on a loaded macOS runner (CI run 40255714163), and the
    #1779 lesson is that unit tests do not scan the real repo. The tree below
    copies the two shapes in the real repo that decide the verdict:

    * ``tests/unit/mcp/test_refactoring_suggestions_tool.py`` binds
      ``java_plugin.py`` to a module constant via a ``PROJECT_ROOT /`` join
      (the 0.85 ``constant_assignment`` signal), and
    * ``tests/contracts/test_plugin_architecture_contract.py`` lists it in a
      plugin manifest inside a test function. Only module-level manifests
      feed the sibling-cluster suppression
      (``test_fixture_detector.py::test_plugin_manifest_exclusion``), so this
      one must NOT cancel the constant signal.

    The whole-repository canary lives on as an integration test:
    ``tests/integration/test_fixture_detector_real_repo.py``.
    """

    def test_real_repo_finds_java_plugin(self, tmp_path: Path) -> None:
        target = "tree_sitter_analyzer/languages/java_plugin.py"
        root = _make_project(
            tmp_path,
            {
                "tests/unit/mcp/test_refactoring_suggestions_tool.py": (
                    "from pathlib import Path\n"
                    "PROJECT_ROOT = Path(__file__).parent.parent.parent.parent\n"
                    "SAMPLE_PYTHON = str(\n"
                    '    PROJECT_ROOT / "tree_sitter_analyzer" / "languages"'
                    ' / "java_plugin.py"\n'
                    ")\n"
                ),
                "tests/contracts/test_plugin_architecture_contract.py": (
                    "def test_no_new_single_file_plugins_in_languages_root():\n"
                    "    GRANDFATHERED = {\n"
                    '        "css_plugin.py",\n'
                    '        "go_plugin.py",\n'
                    '        "html_plugin.py",\n'
                    '        "java_plugin.py",\n'
                    "    }\n"
                    "    assert GRANDFATHERED\n"
                ),
                target: "class JavaPlugin:\n    pass\n",
            },
        )
        fact = is_fixture(target, root)
        assert fact.is_fixture is True, (
            f"Detection failed for {target}; got {fact!r}. "
            "This is the canary for feedback_test-fixture-files."
        )
        # confidence must be high enough to escalate safe_to_edit to UNSAFE.
        assert fact.confidence == 0.85
        assert fixture_to_verdict(fact) == "UNSAFE"
