from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "check_patch_coverage.py"

spec = importlib.util.spec_from_file_location("check_patch_coverage", SCRIPT_PATH)
assert spec is not None
check_patch_coverage = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["check_patch_coverage"] = check_patch_coverage
spec.loader.exec_module(check_patch_coverage)


def test_parse_added_lines_from_zero_context_diff() -> None:
    diff = """diff --git a/tree_sitter_analyzer/foo.py b/tree_sitter_analyzer/foo.py
--- a/tree_sitter_analyzer/foo.py
+++ b/tree_sitter_analyzer/foo.py
@@ -1,2 +1,4 @@
 context
+if flag:
+    return 1
-old
+return 2
"""

    assert check_patch_coverage.parse_added_lines(diff) == {
        "tree_sitter_analyzer/foo.py": {2, 3, 4}
    }


def test_missing_patch_coverage_reports_added_missing_lines() -> None:
    coverage = {
        "files": {
            "tree_sitter_analyzer/foo.py": {
                "executed_lines": [2],
                "missing_lines": [3],
                "excluded_lines": [],
                "missing_branches": [],
            }
        }
    }

    misses = check_patch_coverage.missing_patch_coverage(
        {"tree_sitter_analyzer/foo.py": {2, 3, 10}},
        coverage,
        PROJECT_ROOT,
    )

    assert misses == [
        check_patch_coverage.PatchCoverageMiss(
            "tree_sitter_analyzer/foo.py", 3, "line not covered"
        )
    ]


def test_missing_patch_coverage_reports_added_partial_branches() -> None:
    coverage = {
        "files": {
            "tree_sitter_analyzer/foo.py": {
                "executed_lines": [2],
                "missing_lines": [],
                "excluded_lines": [],
                "missing_branches": [[2, 5]],
            }
        }
    }

    misses = check_patch_coverage.missing_patch_coverage(
        {"tree_sitter_analyzer/foo.py": {2}},
        coverage,
        PROJECT_ROOT,
    )

    assert misses == [
        check_patch_coverage.PatchCoverageMiss(
            "tree_sitter_analyzer/foo.py", 2, "branch partially covered"
        )
    ]


def test_missing_patch_coverage_skips_tests_and_non_executable_lines() -> None:
    coverage = {
        "files": {
            "tree_sitter_analyzer/foo.py": {
                "executed_lines": [4],
                "missing_lines": [],
                "excluded_lines": [2],
                "missing_branches": [],
            },
            "tests/unit/test_foo.py": {
                "executed_lines": [],
                "missing_lines": [2],
                "excluded_lines": [],
                "missing_branches": [],
            },
        }
    }

    misses = check_patch_coverage.missing_patch_coverage(
        {
            "tree_sitter_analyzer/foo.py": {1, 2, 4},
            "tests/unit/test_foo.py": {2},
        },
        coverage,
        PROJECT_ROOT,
    )

    assert misses == []


def test_cli_fails_when_diff_has_added_missing_line(tmp_path: Path) -> None:
    diff_file = tmp_path / "patch.diff"
    coverage_file = tmp_path / "coverage.json"
    diff_file.write_text(
        """diff --git a/tree_sitter_analyzer/foo.py b/tree_sitter_analyzer/foo.py
--- a/tree_sitter_analyzer/foo.py
+++ b/tree_sitter_analyzer/foo.py
@@ -1,0 +1,2 @@
+def new_func():
+    return 1
""",
        encoding="utf-8",
    )
    coverage_file.write_text(
        json.dumps(
            {
                "files": {
                    "tree_sitter_analyzer/foo.py": {
                        "executed_lines": [1],
                        "missing_lines": [2],
                        "excluded_lines": [],
                        "missing_branches": [],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--diff-file",
            str(diff_file),
            "--coverage-json",
            str(coverage_file),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
    )

    assert result.returncode == 1
    assert "tree_sitter_analyzer/foo.py:2: line not covered" in result.stdout
