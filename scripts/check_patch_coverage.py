#!/usr/bin/env python3
"""Fail when PR-added executable source lines are missing coverage.

This is a local companion to Codecov patch coverage. Generate
``coverage.json`` with pytest-cov, then run this script before pushing a
PR branch. The check is intentionally strict: every added executable line
under ``tree_sitter_analyzer/`` must be covered, and added branch source
lines must not have missing branch arcs.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HUNK_RE = re.compile(r"\+(?P<start>\d+)(?:,(?P<count>\d+))?")
DEFAULT_PATHS = ("tree_sitter_analyzer",)


@dataclass(frozen=True)
class PatchCoverageMiss:
    """A missing coverage finding on a PR-added line."""

    path: str
    line: int
    reason: str


def parse_added_lines(diff_text: str) -> dict[str, set[int]]:
    """Return added destination line numbers by path from unified diff text."""
    added: dict[str, set[int]] = {}
    current_file: str | None = None
    new_line: int | None = None

    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
            added.setdefault(current_file, set())
            new_line = None
            continue
        if line.startswith("+++ /dev/null"):
            current_file = None
            new_line = None
            continue
        if line.startswith("@@"):
            match = HUNK_RE.search(line)
            new_line = int(match.group("start")) if match else None
            continue
        if current_file is None or new_line is None:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            added[current_file].add(new_line)
            new_line += 1
        elif line.startswith("-") and not line.startswith("---"):
            continue
        elif line.startswith("\\ No newline"):
            continue
        else:
            new_line += 1

    return {path: lines for path, lines in added.items() if lines}


def load_coverage(path: Path) -> dict[str, Any]:
    """Load a coverage.py JSON report."""
    if not path.exists():
        raise FileNotFoundError(
            f"{path} does not exist. Run pytest with --cov-report=json first."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_coverage_files(
    coverage_data: dict[str, Any],
    project_root: Path,
) -> dict[str, dict[str, Any]]:
    """Return coverage file entries keyed by repo-relative POSIX path."""
    raw_files = coverage_data.get("files", {})
    if isinstance(raw_files, list):
        iterable = (
            (entry.get("filename", ""), entry)
            for entry in raw_files
            if isinstance(entry, dict)
        )
    else:
        iterable = raw_files.items()

    files: dict[str, dict[str, Any]] = {}
    for raw_path, entry in iterable:
        if not isinstance(entry, dict):
            continue
        normalized = normalize_repo_path(str(raw_path), project_root)
        files[normalized] = entry
    return files


def normalize_repo_path(path: str, project_root: Path) -> str:
    """Normalize absolute or relative paths to repo-relative POSIX form."""
    path_obj = Path(path)
    if path_obj.is_absolute():
        try:
            path_obj = path_obj.resolve().relative_to(project_root.resolve())
        except ValueError:
            return path_obj.as_posix()
    return path_obj.as_posix()


def is_tracked_python_source(path: str) -> bool:
    """Return true for package source paths covered by Codecov patch gate."""
    return path.endswith(".py") and path.startswith("tree_sitter_analyzer/")


def missing_patch_coverage(
    added_lines: dict[str, set[int]],
    coverage_data: dict[str, Any],
    project_root: Path,
) -> list[PatchCoverageMiss]:
    """Find added executable lines and branch source lines missing coverage."""
    coverage_files = normalize_coverage_files(coverage_data, project_root)
    misses: list[PatchCoverageMiss] = []

    for path, lines in sorted(added_lines.items()):
        if not is_tracked_python_source(path):
            continue
        file_coverage = coverage_files.get(path)
        if file_coverage is None:
            for line in sorted(lines):
                misses.append(PatchCoverageMiss(path, line, "no coverage data"))
            continue

        excluded = set(file_coverage.get("excluded_lines", []))
        missing = set(file_coverage.get("missing_lines", []))
        executed = set(file_coverage.get("executed_lines", []))
        executable = executed | missing
        missing_branch_sources = {
            int(branch[0])
            for branch in file_coverage.get("missing_branches", [])
            if branch
        }

        for line in sorted(lines):
            if line in excluded:
                continue
            if line in missing:
                misses.append(PatchCoverageMiss(path, line, "line not covered"))
            elif line in executable and line in missing_branch_sources:
                misses.append(PatchCoverageMiss(path, line, "branch partially covered"))

    return misses


def git_diff(
    project_root: Path,
    base: str,
    pathspecs: list[str],
    worktree: bool,
) -> str:
    """Return unified diff text for the PR patch or current worktree."""
    ref = base if worktree else f"{base}...HEAD"
    cmd = ["git", "diff", "--unified=0", ref, "--", *pathspecs]
    result = subprocess.run(
        cmd,
        cwd=project_root,
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git diff failed")
    return result.stdout


def print_report(misses: list[PatchCoverageMiss]) -> None:
    """Print a human-readable gate result."""
    if not misses:
        print("Patch coverage gate passed: no added executable misses.")
        return

    print("Patch coverage gate failed:")
    for miss in misses:
        print(f"  {miss.path}:{miss.line}: {miss.reason}")
    print(
        "\nRun focused tests with --cov=tree_sitter_analyzer "
        "--cov-report=json, then add effective tests for the lines above."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check coverage on PR-added executable source lines."
    )
    parser.add_argument(
        "--base",
        default="origin/develop",
        help="Base ref for PR diff semantics (default: origin/develop).",
    )
    parser.add_argument(
        "--coverage-json",
        type=Path,
        default=Path("coverage.json"),
        help="coverage.py JSON report path (default: coverage.json).",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root (default: inferred from script location).",
    )
    parser.add_argument(
        "--path",
        action="append",
        dest="paths",
        help="Git pathspec to check. Can be passed multiple times.",
    )
    parser.add_argument(
        "--diff-file",
        type=Path,
        help="Read unified diff from a file instead of running git diff.",
    )
    parser.add_argument(
        "--worktree",
        action="store_true",
        help="Compare base directly to the worktree instead of base...HEAD.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    project_root = args.project_root.resolve()
    coverage_path = args.coverage_json
    if not coverage_path.is_absolute():
        coverage_path = project_root / coverage_path

    try:
        diff_text = (
            args.diff_file.read_text(encoding="utf-8")
            if args.diff_file
            else git_diff(
                project_root,
                args.base,
                args.paths or list(DEFAULT_PATHS),
                args.worktree,
            )
        )
        coverage_data = load_coverage(coverage_path)
        misses = missing_patch_coverage(
            parse_added_lines(diff_text),
            coverage_data,
            project_root,
        )
    except (FileNotFoundError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"Patch coverage gate error: {exc}", file=sys.stderr)
        return 2

    print_report(misses)
    return 1 if misses else 0


if __name__ == "__main__":
    raise SystemExit(main())
