#!/usr/bin/env python3
"""Smoke tests for F2: ``--format`` alias for ``--output-format`` in subcommands.

Audit finding: ``--format json`` works in the main CLI but was rejected by the
three standalone subcommand parsers (``search-content``, ``find-and-grep``,
``list-files``). They only knew about ``--output-format``. This module locks
the alias in so the flag name stays interchangeable across all CLI surfaces.

Tests are split in two layers:

* **Parser-level** (fast, deterministic): build the subcommand parser and
  parse a minimal arg list with each flag form. Both must populate
  ``args.output_format`` identically and never raise ``SystemExit``.
* **Subprocess smoke** (end-to-end): invoke each subcommand binary with
  ``--format json`` and ``--output-format json`` against a tiny on-disk
  fixture, then verify both calls produce identical, valid JSON.

The subprocess layer is deliberately small (one query per tool) so the
total runtime stays well under the suite's 60s budget.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tree_sitter_analyzer.cli.commands.find_and_grep_cli import (
    _build_parser as build_find_and_grep_parser,
)
from tree_sitter_analyzer.cli.commands.list_files_cli import (
    _build_parser as build_list_files_parser,
)
from tree_sitter_analyzer.cli.commands.search_content_cli import (
    _build_parser as build_search_content_parser,
)

# ---------------------------------------------------------------------------
# Parser-level tests (no subprocess, no filesystem)
# ---------------------------------------------------------------------------


class TestSearchContentFormatAlias:
    """``search-content`` accepts both ``--format`` and ``--output-format``."""

    def test_output_format_long(self) -> None:
        parser = build_search_content_parser()
        args = parser.parse_args(
            ["--roots", "root1", "--query", "x", "--output-format", "json"]
        )
        assert args.output_format == "json"

    def test_format_alias(self) -> None:
        parser = build_search_content_parser()
        args = parser.parse_args(
            ["--roots", "root1", "--query", "x", "--format", "json"]
        )
        assert args.output_format == "json"

    @pytest.mark.parametrize("fmt", ["json", "text", "toon"])
    def test_format_alias_all_choices(self, fmt: str) -> None:
        parser = build_search_content_parser()
        args = parser.parse_args(["--roots", "root1", "--query", "x", "--format", fmt])
        assert args.output_format == fmt


class TestFindAndGrepFormatAlias:
    """``find-and-grep`` accepts both ``--format`` and ``--output-format``."""

    def test_output_format_long(self) -> None:
        parser = build_find_and_grep_parser()
        args = parser.parse_args(
            ["--roots", "root1", "--query", "x", "--output-format", "json"]
        )
        assert args.output_format == "json"

    def test_format_alias(self) -> None:
        parser = build_find_and_grep_parser()
        args = parser.parse_args(
            ["--roots", "root1", "--query", "x", "--format", "json"]
        )
        assert args.output_format == "json"

    @pytest.mark.parametrize("fmt", ["json", "text", "toon"])
    def test_format_alias_all_choices(self, fmt: str) -> None:
        parser = build_find_and_grep_parser()
        args = parser.parse_args(["--roots", "root1", "--query", "x", "--format", fmt])
        assert args.output_format == fmt


class TestListFilesFormatAlias:
    """``list-files`` accepts both ``--format`` and ``--output-format``."""

    def test_output_format_long(self) -> None:
        parser = build_list_files_parser()
        args = parser.parse_args(["root1", "--output-format", "json"])
        assert args.output_format == "json"

    def test_format_alias(self) -> None:
        parser = build_list_files_parser()
        args = parser.parse_args(["root1", "--format", "json"])
        assert args.output_format == "json"

    @pytest.mark.parametrize("fmt", ["json", "text", "toon"])
    def test_format_alias_all_choices(self, fmt: str) -> None:
        parser = build_list_files_parser()
        args = parser.parse_args(["root1", "--format", fmt])
        assert args.output_format == fmt


# ---------------------------------------------------------------------------
# Subprocess smoke tests (end-to-end, validate the wired binaries)
# ---------------------------------------------------------------------------


@pytest.fixture
def fixture_root(tmp_path: Path) -> Path:
    """Tiny tree with one file containing a known token.

    Kept minimal on purpose: ripgrep/fd are external and we only need a
    single hit to prove the output stream parses as JSON.
    """
    src = tmp_path / "src"
    src.mkdir()
    (src / "sample.py").write_text(
        "ALIAS_TOKEN = 'unique-marker-for-f2-tests'\n"
        "def helper():\n"
        "    return ALIAS_TOKEN\n",
        encoding="utf-8",
    )
    return tmp_path


def _run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a subcommand via ``python -m`` to avoid PATH/console-script flakiness."""
    return subprocess.run(
        [sys.executable, "-m", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )


def _module_for(subcommand: str) -> str:
    return {
        "search-content": "tree_sitter_analyzer.cli.commands.search_content_cli",
        "find-and-grep": "tree_sitter_analyzer.cli.commands.find_and_grep_cli",
        "list-files": "tree_sitter_analyzer.cli.commands.list_files_cli",
    }[subcommand]


def _parse_first_json(stdout: str) -> dict:
    """Parse the stdout payload as JSON; fail loudly with the actual stream."""
    stripped = stdout.strip()
    assert stripped, f"expected JSON on stdout, got empty stream: {stdout!r}"
    return json.loads(stripped)


# Wall-clock fields drift between back-to-back invocations and would make
# equality comparisons flaky. Strip them recursively before comparing the
# alias and canonical payloads — we care about *content* parity, not timing.
_VOLATILE_KEY_SUFFIXES = ("elapsed_ms", "elapsed_seconds")
_VOLATILE_KEYS = {"timestamp", "started_at"}


def _is_volatile(key: str) -> bool:
    if key in _VOLATILE_KEYS:
        return True
    return any(key.endswith(suffix) for suffix in _VOLATILE_KEY_SUFFIXES)


def _strip_volatile(value):  # type: ignore[no-untyped-def]
    if isinstance(value, dict):
        return {
            key: _strip_volatile(inner)
            for key, inner in value.items()
            if not _is_volatile(key)
        }
    if isinstance(value, list):
        return [_strip_volatile(item) for item in value]
    return value


@pytest.mark.skipif(
    shutil.which("rg") is None,
    reason="ripgrep (rg) not installed; subprocess smoke tests skipped",
)
class TestSearchContentSubprocessAlias:
    """End-to-end: both flag forms produce equivalent JSON for search-content."""

    def test_format_alias_yields_valid_json(self, fixture_root: Path) -> None:
        result = _run_cli(
            [
                _module_for("search-content"),
                "--roots",
                "src",
                "--query",
                "ALIAS_TOKEN",
                "--project-root",
                str(fixture_root),
                "--format",
                "json",
            ],
            cwd=fixture_root,
        )
        assert result.returncode == 0, result.stderr
        payload = _parse_first_json(result.stdout)
        assert payload.get("success") is True

    @pytest.mark.slow_ok  # Real subprocess smoke invokes Python + rg twice on Windows.
    def test_format_and_output_format_match(self, fixture_root: Path) -> None:
        common = [
            _module_for("search-content"),
            "--roots",
            "src",
            "--query",
            "ALIAS_TOKEN",
            "--project-root",
            str(fixture_root),
        ]
        with_alias = _run_cli([*common, "--format", "json"], cwd=fixture_root)
        with_canonical = _run_cli(
            [*common, "--output-format", "json"], cwd=fixture_root
        )
        assert with_alias.returncode == 0, with_alias.stderr
        assert with_canonical.returncode == 0, with_canonical.stderr
        assert _strip_volatile(_parse_first_json(with_alias.stdout)) == _strip_volatile(
            _parse_first_json(with_canonical.stdout)
        )


@pytest.mark.skipif(
    shutil.which("rg") is None or shutil.which("fd") is None,
    reason="fd or ripgrep not installed; subprocess smoke tests skipped",
)
class TestFindAndGrepSubprocessAlias:
    """End-to-end: both flag forms produce equivalent JSON for find-and-grep."""

    def test_format_alias_yields_valid_json(self, fixture_root: Path) -> None:
        result = _run_cli(
            [
                _module_for("find-and-grep"),
                "--roots",
                "src",
                "--query",
                "ALIAS_TOKEN",
                "--project-root",
                str(fixture_root),
                "--format",
                "json",
            ],
            cwd=fixture_root,
        )
        assert result.returncode == 0, result.stderr
        payload = _parse_first_json(result.stdout)
        assert payload.get("success") is True

    @pytest.mark.slow_ok  # Real subprocess smoke invokes Python + fd/rg twice on Windows.
    def test_format_and_output_format_match(self, fixture_root: Path) -> None:
        common = [
            _module_for("find-and-grep"),
            "--roots",
            "src",
            "--query",
            "ALIAS_TOKEN",
            "--project-root",
            str(fixture_root),
        ]
        with_alias = _run_cli([*common, "--format", "json"], cwd=fixture_root)
        with_canonical = _run_cli(
            [*common, "--output-format", "json"], cwd=fixture_root
        )
        assert with_alias.returncode == 0, with_alias.stderr
        assert with_canonical.returncode == 0, with_canonical.stderr
        assert _strip_volatile(_parse_first_json(with_alias.stdout)) == _strip_volatile(
            _parse_first_json(with_canonical.stdout)
        )


@pytest.mark.skipif(
    shutil.which("fd") is None,
    reason="fd not installed; subprocess smoke tests skipped",
)
class TestListFilesSubprocessAlias:
    """End-to-end: both flag forms produce equivalent JSON for list-files."""

    def test_format_alias_yields_valid_json(self, fixture_root: Path) -> None:
        result = _run_cli(
            [
                _module_for("list-files"),
                "src",
                "--project-root",
                str(fixture_root),
                "--format",
                "json",
            ],
            cwd=fixture_root,
        )
        assert result.returncode == 0, result.stderr
        payload = _parse_first_json(result.stdout)
        assert payload.get("success") is True

    @pytest.mark.slow_ok  # Real subprocess smoke invokes Python + fd twice on Windows.
    def test_format_and_output_format_match(self, fixture_root: Path) -> None:
        common = [
            _module_for("list-files"),
            "src",
            "--project-root",
            str(fixture_root),
        ]
        with_alias = _run_cli([*common, "--format", "json"], cwd=fixture_root)
        with_canonical = _run_cli(
            [*common, "--output-format", "json"], cwd=fixture_root
        )
        assert with_alias.returncode == 0, with_alias.stderr
        assert with_canonical.returncode == 0, with_canonical.stderr
        assert _strip_volatile(_parse_first_json(with_alias.stdout)) == _strip_volatile(
            _parse_first_json(with_canonical.stdout)
        )
