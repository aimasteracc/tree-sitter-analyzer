from __future__ import annotations

import os
from pathlib import Path

import pytest

from tree_sitter_analyzer import frozen_git_settings as settings
from tree_sitter_analyzer.source_oracle import SafePath, SourceOracleError


def test_capture_settings_rejects_nul_core_attributes_path(tmp_path: Path) -> None:
    def output(_root, args, **_kwargs):
        if args[0] == "config" and "--path" in args:
            return b"bad\0path\n"
        return b""

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_GIT_ERROR$"):
        settings.capture_frozen_git_settings(str(tmp_path), (), 1e20, output)


def test_capture_settings_enforces_total_byte_budget(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "_MAX_SETTINGS_BYTES", 1)

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_CAPACITY$"):
        settings.capture_frozen_git_settings(
            str(tmp_path), (), 1e20, lambda *_a, **_k: b""
        )


def test_capture_settings_enforces_attribute_file_budget(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "_MAX_SETTINGS_FILES", 1)

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_CAPACITY$"):
        settings.capture_frozen_git_settings(
            str(tmp_path), (b".gitattributes",), 1e20, lambda *_a, **_k: b""
        )


def test_capture_settings_rejects_invalid_attribute_leaf(
    tmp_path: Path, monkeypatch
) -> None:
    reader = lambda *_a, **_k: SafePath(None, (), "directory")  # noqa: E731
    monkeypatch.setattr(settings, "safe_workspace_path", reader)
    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_SPECIAL_FILE$"):
        settings.capture_frozen_git_settings(
            str(tmp_path), (b".gitattributes",), 1e20, lambda *_a, **_k: b""
        )
    oversized = SafePath(b"x" * settings._MAX_SETTINGS_BYTES, (), "file")
    monkeypatch.setattr(settings, "safe_workspace_path", lambda *_a, **_k: oversized)
    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_CAPACITY$"):
        settings.capture_frozen_git_settings(
            str(tmp_path), (), 1e20, lambda *_a, **_k: b""
        )


def test_capture_settings_charges_attribute_path_bytes(
    tmp_path: Path, monkeypatch
) -> None:
    info = os.fsencode(settings._absolute_path(str(tmp_path), b".git/info/attributes"))
    objects = os.fsencode(settings._absolute_path(str(tmp_path), b".git/objects"))
    budget = len(info) + len(objects) + len(b".gitattributes") - 1
    monkeypatch.setattr(settings, "_MAX_SETTINGS_BYTES", budget)

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_CAPACITY$"):
        settings.capture_frozen_git_settings(
            str(tmp_path), (), 1e20, lambda *_a, **_k: b""
        )


def test_attribute_candidates_stop_hostile_deep_inventory_at_file_budget(
    monkeypatch,
) -> None:
    # PR #1252 review thread 3751175565.
    normalized = 0
    original = settings.normalize_repo_path

    def count_normalize(path: str) -> str:
        nonlocal normalized
        normalized += 1
        return original(path)

    monkeypatch.setattr(settings, "normalize_repo_path", count_normalize)
    inventory = tuple(
        f"unique-{index}/a/b/c/d/e/file.py".encode() for index in range(10_000)
    )

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_CAPACITY$"):
        settings._attribute_candidates(
            inventory, 1e20, file_budget=3, byte_budget=settings._MAX_SETTINGS_BYTES
        )

    assert normalized == 1


def test_attribute_candidates_stop_hostile_inventory_at_deadline(monkeypatch) -> None:
    # PR #1252 review thread 3751175565.
    clock_calls = 0
    normalized = 0
    original = settings.normalize_repo_path

    def hostile_clock() -> float:
        nonlocal clock_calls
        clock_calls += 1
        return 0.0 if clock_calls < 8 else 2.0

    def count_normalize(path: str) -> str:
        nonlocal normalized
        normalized += 1
        return original(path)

    monkeypatch.setattr(settings.time, "monotonic", hostile_clock)
    monkeypatch.setattr(settings, "normalize_repo_path", count_normalize)
    inventory = tuple(
        f"unique-{index}/a/b/c/d/e/file.py".encode() for index in range(10_000)
    )

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_TIMEOUT$"):
        settings._attribute_candidates(
            inventory, 1.0, file_budget=20_000, byte_budget=10_000_000
        )

    assert (clock_calls, normalized) == (8, 1)


def test_attribute_candidates_deduplicate_shared_ancestors() -> None:
    candidates = settings._attribute_candidates(
        (b"pkg/one.py", b"pkg/two.py"),
        1e20,
        file_budget=2,
        byte_budget=1024,
    )

    assert candidates == [b".gitattributes", b"pkg/.gitattributes"]


def test_capture_settings_rejects_candidate_path_beyond_remaining_budget(
    tmp_path: Path, monkeypatch
) -> None:
    info = os.fsencode(settings._absolute_path(str(tmp_path), b".git/info/attributes"))
    objects = os.fsencode(settings._absolute_path(str(tmp_path), b".git/objects"))
    monkeypatch.setattr(settings, "_MAX_SETTINGS_BYTES", len(info) + len(objects))
    monkeypatch.setattr(settings, "_attribute_candidates", lambda *a, **k: [b"x"])

    with pytest.raises(SourceOracleError, match="^DIFF_SNAPSHOT_CAPACITY$"):
        settings.capture_frozen_git_settings(
            str(tmp_path), (), 1e20, lambda *_a, **_k: b""
        )
