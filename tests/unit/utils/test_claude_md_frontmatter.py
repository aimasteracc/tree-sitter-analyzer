"""Tests for the CLAUDE.md YAML frontmatter parser (PR-0.3).

The parser is the shared building block for two downstream proposals:

* **P3 (``is_fixture`` flag)** uses ``fixture_allowlist`` entries to mark
  files that must never be machine-refactored.
* **P5 (``intentional_design`` frontmatter)** uses ``intentional_design``
  rules to drive ``safe_to_edit`` verdict overrides.

The verdict vocabulary aligns with ``base_tool._LEGAL_VERDICTS`` —
``{SAFE, CAUTION, REVIEW, UNSAFE, INFO, WARN, ERROR, NOT_FOUND}``. Note
the absence of ``REFUSE`` (PRD §0 errata F5). The parser must coerce
anything outside this set to ``INFO`` (rank-0 passthrough in
``_VERDICT_SEVERITY``) and emit a warning so legacy rule files do not
silently bypass the override path.
"""

from __future__ import annotations

import logging
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from tree_sitter_analyzer.utils.claude_md_frontmatter import (
    VALID_VERDICT_ACTIONS,
    FixtureAllowlistEntry,
    IntentionalDesignRule,
    load_frontmatter,
    parse_fixture_allowlist,
    parse_intentional_design,
)

_MODULE_LOGGER = "tree_sitter_analyzer.utils.claude_md_frontmatter"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_claude_md(root: Path, body: str) -> Path:
    """Write ``body`` to ``<root>/CLAUDE.md`` and return the path."""

    path = root / "CLAUDE.md"
    path.write_text(body, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# load_frontmatter
# ---------------------------------------------------------------------------


class TestLoadFrontmatter:
    def test_no_claude_md_returns_empty_dict(self, tmp_path: Path) -> None:
        assert load_frontmatter(tmp_path) == {}

    def test_no_frontmatter_block_returns_empty_dict(self, tmp_path: Path) -> None:
        _write_claude_md(
            tmp_path, "# CLAUDE.md\n\nRegular prose, no front matter here.\n"
        )
        assert load_frontmatter(tmp_path) == {}

    def test_empty_frontmatter_returns_empty_dict(self, tmp_path: Path) -> None:
        _write_claude_md(tmp_path, "---\n---\n\n# Body\n")
        # An empty frontmatter block parses to ``None``; the loader must
        # surface this as ``{}`` rather than propagating ``None``.
        assert load_frontmatter(tmp_path) == {}

    def test_valid_frontmatter_returns_dict(self, tmp_path: Path) -> None:
        _write_claude_md(
            tmp_path,
            (
                "---\n"
                "intentional_design:\n"
                "  - id: rule_one\n"
                "    files: ['src/foo.py']\n"
                "    note: 'do not touch'\n"
                "    action_when_touched: UNSAFE\n"
                "---\n\n# Body\n"
            ),
        )
        data = load_frontmatter(tmp_path)
        assert isinstance(data, dict)
        assert data["intentional_design"][0]["id"] == "rule_one"

    def test_malformed_yaml_returns_empty_dict_and_warns(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Unbalanced YAML — colon without value, broken indent — must fail
        # gracefully rather than raising.
        _write_claude_md(
            tmp_path,
            "---\nintentional_design:\n  - id: rule_one\n    files: [unclosed\n---\n",
        )
        with caplog.at_level(logging.WARNING, logger=_MODULE_LOGGER):
            data = load_frontmatter(tmp_path)
        assert data == {}
        assert any("frontmatter" in record.message.lower() for record in caplog.records)

    def test_accepts_str_or_path_project_root(self, tmp_path: Path) -> None:
        _write_claude_md(tmp_path, "---\nintentional_design: []\n---\n")
        assert load_frontmatter(tmp_path) == load_frontmatter(str(tmp_path))

    def test_frontmatter_is_list_not_dict_warns_and_returns_empty(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        # A top-level YAML list (rather than mapping) is malformed for our
        # purposes — sections are named, so the root must be a dict.
        _write_claude_md(tmp_path, "---\n- not\n- a\n- mapping\n---\n")
        with caplog.at_level(logging.WARNING, logger=_MODULE_LOGGER):
            assert load_frontmatter(tmp_path) == {}
        assert any("mapping" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# parse_intentional_design
# ---------------------------------------------------------------------------


class TestParseIntentionalDesign:
    def test_empty_input_returns_empty_list(self) -> None:
        assert parse_intentional_design({}) == []
        assert parse_intentional_design({"unrelated": []}) == []

    def test_single_valid_rule(self) -> None:
        data = {
            "intentional_design": [
                {
                    "id": "mcp_default_toon",
                    "files": ["tree_sitter_analyzer/mcp/server.py"],
                    "symbols": ['arguments.get("output_format", "toon")'],
                    "note": "TOON default locked by user r37b",
                    "action_when_touched": "UNSAFE",
                }
            ]
        }
        rules = parse_intentional_design(data)
        assert len(rules) == 1
        rule = rules[0]
        assert isinstance(rule, IntentionalDesignRule)
        assert rule.id == "mcp_default_toon"
        assert rule.action == "UNSAFE"
        assert rule.note == "TOON default locked by user r37b"
        assert rule.raw_globs == ("tree_sitter_analyzer/mcp/server.py",)
        assert len(rule.file_patterns) == 1
        # The compiled spec must actually match the path it was built from.
        assert rule.file_patterns[0].match_file("tree_sitter_analyzer/mcp/server.py")
        assert rule.symbols == ('arguments.get("output_format", "toon")',)

    def test_glob_pattern_compiles_and_matches(self) -> None:
        data = {
            "intentional_design": [
                {
                    "id": "all_mcp_tools",
                    "files": ["tree_sitter_analyzer/mcp/tools/*.py"],
                    "note": "MCP tool surface — review carefully",
                }
            ]
        }
        rules = parse_intentional_design(data)
        spec = rules[0].file_patterns[0]
        assert spec.match_file("tree_sitter_analyzer/mcp/tools/foo.py")
        assert not spec.match_file("tree_sitter_analyzer/mcp/server.py")

    def test_missing_action_defaults_to_info(self) -> None:
        data = {
            "intentional_design": [
                {
                    "id": "implicit",
                    "files": ["a.py"],
                    "note": "n",
                }
            ]
        }
        rule = parse_intentional_design(data)[0]
        assert rule.action == "INFO"

    def test_invalid_action_coerced_to_info_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # F5 fix from PRD §0 errata: REFUSE is NOT a valid TSA verdict
        # (vocab is SAFE/CAUTION/REVIEW/UNSAFE/INFO/WARN/ERROR/NOT_FOUND,
        # matching base_tool._LEGAL_VERDICTS). A legacy rule using
        # REFUSE must be coerced to INFO (rank-0 neutral passthrough in
        # safe_to_edit_helpers._VERDICT_SEVERITY) and surface a warning
        # so the author can update the spec — silently downgrading is
        # the failure mode we want to avoid.
        data = {
            "intentional_design": [
                {
                    "id": "legacy_refuse",
                    "files": ["x.py"],
                    "note": "n",
                    "action_when_touched": "REFUSE",
                }
            ]
        }
        with caplog.at_level(logging.WARNING, logger=_MODULE_LOGGER):
            rule = parse_intentional_design(data)[0]
        assert rule.action == "INFO"
        assert any(
            "REFUSE" in record.message or "action" in record.message.lower()
            for record in caplog.records
        )

    @pytest.mark.parametrize("action", sorted(VALID_VERDICT_ACTIONS))
    def test_all_valid_actions_round_trip(self, action: str) -> None:
        data = {
            "intentional_design": [
                {
                    "id": f"id_{action.lower()}",
                    "files": ["x.py"],
                    "note": "n",
                    "action_when_touched": action,
                }
            ]
        }
        assert parse_intentional_design(data)[0].action == action

    def test_missing_required_field_skips_rule_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        data = {
            "intentional_design": [
                {"id": "good", "files": ["a.py"], "note": "n"},
                {"id": "no_files", "note": "n"},  # missing files
                {"files": ["b.py"], "note": "n"},  # missing id
                {"id": "no_note", "files": ["c.py"]},  # missing note
            ]
        }
        with caplog.at_level(logging.WARNING, logger=_MODULE_LOGGER):
            rules = parse_intentional_design(data)
        assert len(rules) == 1
        assert rules[0].id == "good"
        assert any("intentional_design" in r.message for r in caplog.records)

    def test_symbols_defaults_to_empty_tuple_not_none(self) -> None:
        data = {"intentional_design": [{"id": "x", "files": ["a.py"], "note": "n"}]}
        assert parse_intentional_design(data)[0].symbols == ()

    def test_action_case_normalised_to_upper(self) -> None:
        data = {
            "intentional_design": [
                {
                    "id": "x",
                    "files": ["a.py"],
                    "note": "n",
                    "action_when_touched": "unsafe",
                }
            ]
        }
        assert parse_intentional_design(data)[0].action == "UNSAFE"

    def test_rule_is_frozen_dataclass(self) -> None:
        data = {"intentional_design": [{"id": "x", "files": ["a.py"], "note": "n"}]}
        rule = parse_intentional_design(data)[0]
        with pytest.raises(FrozenInstanceError):
            rule.id = "mutated"  # type: ignore[misc]

    def test_section_is_not_list_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        # If someone writes ``intentional_design: {key: value}`` (a non-empty
        # dict instead of a list), don't crash — log and degrade to empty.
        # An *empty* dict {} is intentionally treated as "no rules" without
        # a warning because that's how YAML often degenerates.
        with caplog.at_level(logging.WARNING, logger=_MODULE_LOGGER):
            assert parse_intentional_design({"intentional_design": {"a": 1}}) == []
        assert any("list" in record.message.lower() for record in caplog.records)

    def test_entry_is_not_dict_skipped(self, caplog: pytest.LogCaptureFixture) -> None:
        data = {
            "intentional_design": [
                "just-a-string",
                {"id": "ok", "files": ["a.py"], "note": "n"},
            ]
        }
        with caplog.at_level(logging.WARNING, logger=_MODULE_LOGGER):
            rules = parse_intentional_design(data)
        assert len(rules) == 1
        assert rules[0].id == "ok"

    def test_files_as_single_string_wrapped_in_list(self) -> None:
        # YAML allows ``files: 'a.py'`` (scalar) instead of ``files: [...]``;
        # treat scalars as a 1-element list rather than rejecting outright.
        data = {
            "intentional_design": [{"id": "scalar", "files": "single.py", "note": "n"}]
        }
        rule = parse_intentional_design(data)[0]
        assert rule.raw_globs == ("single.py",)

    def test_files_empty_list_skipped(self, caplog: pytest.LogCaptureFixture) -> None:
        data = {
            "intentional_design": [
                {"id": "empty_files", "files": [], "note": "n"},
                {"id": "ok", "files": ["a.py"], "note": "n"},
            ]
        }
        # ``files: []`` is caught by the second guard
        # (``not isinstance(raw_globs, list) or not raw_globs``) — an
        # empty list passes ``entry.get(k) in (None, "")`` (the
        # required-field check) but fails the dedicated
        # non-empty-list guard immediately after. Net effect: the
        # ``empty_files`` rule is skipped with a WARNING and only
        # ``ok`` survives.
        with caplog.at_level(logging.WARNING, logger=_MODULE_LOGGER):
            rules = parse_intentional_design(data)
        assert {r.id for r in rules} == {"ok"}

    def test_symbols_as_single_string_wrapped_in_tuple(self) -> None:
        data = {
            "intentional_design": [
                {
                    "id": "s",
                    "files": ["a.py"],
                    "note": "n",
                    "symbols": "single_symbol",
                }
            ]
        }
        rule = parse_intentional_design(data)[0]
        assert rule.symbols == ("single_symbol",)


# ---------------------------------------------------------------------------
# parse_fixture_allowlist
# ---------------------------------------------------------------------------


class TestParseFixtureAllowlist:
    def test_empty_input_returns_empty_list(self) -> None:
        assert parse_fixture_allowlist({}) == []

    def test_single_entry(self) -> None:
        data = {
            "fixture_allowlist": [
                {
                    "path": "tree_sitter_analyzer/languages/java_plugin.py",
                    "note": "SAMPLE_PYTHON negative fixture",
                }
            ]
        }
        entries = parse_fixture_allowlist(data)
        assert len(entries) == 1
        entry = entries[0]
        assert isinstance(entry, FixtureAllowlistEntry)
        assert entry.path == "tree_sitter_analyzer/languages/java_plugin.py"
        assert entry.note == "SAMPLE_PYTHON negative fixture"

    def test_missing_path_skipped_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        data = {
            "fixture_allowlist": [
                {"path": "good.py", "note": "n"},
                {"note": "no path"},
            ]
        }
        with caplog.at_level(logging.WARNING, logger=_MODULE_LOGGER):
            entries = parse_fixture_allowlist(data)
        assert len(entries) == 1
        assert entries[0].path == "good.py"
        assert any("fixture_allowlist" in r.message for r in caplog.records)

    def test_missing_note_defaults_to_empty_string(self) -> None:
        data = {"fixture_allowlist": [{"path": "x.py"}]}
        entry = parse_fixture_allowlist(data)[0]
        assert entry.note == ""

    def test_entry_is_frozen_dataclass(self) -> None:
        data = {"fixture_allowlist": [{"path": "x.py", "note": "n"}]}
        entry = parse_fixture_allowlist(data)[0]
        with pytest.raises(FrozenInstanceError):
            entry.path = "mutated"  # type: ignore[misc]

    def test_section_is_not_list_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger=_MODULE_LOGGER):
            assert parse_fixture_allowlist({"fixture_allowlist": "oops"}) == []
        assert any("list" in record.message.lower() for record in caplog.records)

    def test_entry_is_not_dict_skipped(self, caplog: pytest.LogCaptureFixture) -> None:
        data = {"fixture_allowlist": ["just-a-string", {"path": "ok.py"}]}
        with caplog.at_level(logging.WARNING, logger=_MODULE_LOGGER):
            entries = parse_fixture_allowlist(data)
        assert len(entries) == 1
        assert entries[0].path == "ok.py"


# ---------------------------------------------------------------------------
# End-to-end: load + parse together (the typical caller path)
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def test_real_claude_md_layout(self, tmp_path: Path) -> None:
        _write_claude_md(
            tmp_path,
            (
                "---\n"
                "intentional_design:\n"
                "  - id: mcp_default_toon\n"
                "    files: ['tree_sitter_analyzer/mcp/server.py', 'tree_sitter_analyzer/mcp/tools/*.py']\n"
                '    symbols: [\'arguments.get("output_format", "toon")\']\n'
                "    note: 'TOON default locked by user r37b'\n"
                "    action_when_touched: UNSAFE\n"
                "  - id: project_root_canonicalization\n"
                "    files: ['tree_sitter_analyzer/mcp/tools/base_tool.py']\n"
                "    note: 'macOS symlink trap; solo-commit gate'\n"
                "    action_when_touched: CAUTION\n"
                "fixture_allowlist:\n"
                "  - path: tree_sitter_analyzer/languages/java_plugin.py\n"
                "    note: 'SAMPLE_PYTHON negative fixture'\n"
                "---\n"
                "\n"
                "# Project rules (regular markdown body)\n"
            ),
        )
        data = load_frontmatter(tmp_path)
        rules = parse_intentional_design(data)
        fixtures = parse_fixture_allowlist(data)
        assert len(rules) == 2
        assert {r.id for r in rules} == {
            "mcp_default_toon",
            "project_root_canonicalization",
        }
        assert (
            rules[0]
            .file_patterns[1]
            .match_file("tree_sitter_analyzer/mcp/tools/anything.py")
        )
        assert len(fixtures) == 1
        assert fixtures[0].path.endswith("java_plugin.py")
