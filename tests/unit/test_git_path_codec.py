from __future__ import annotations

import pytest

import tree_sitter_analyzer.diff_snapshot_registry as snapshots


def test_wire_codec_round_trips_non_utf8_path() -> None:
    from tree_sitter_analyzer.git_path_codec import (
        path_from_wire,
        path_to_raw,
        path_to_wire,
        raw_to_path,
    )

    path = b"bad-\xff.py".decode("utf-8", "surrogateescape")
    token = path_to_wire(path)

    assert (token.startswith("git-path-b64:"), path_from_wire(token)) == (True, path)
    assert (path_to_raw(path), raw_to_path(b"bad-\xff.py")) == (b"bad-\xff.py", path)


def test_wire_codec_escapes_reserved_literal_prefix() -> None:
    from tree_sitter_analyzer.git_path_codec import path_from_wire, path_to_wire

    path = "git-path-b64:literal"
    token = path_to_wire(path)

    assert (token == path, path_from_wire(token)) == (False, path)


@pytest.mark.parametrize(
    "value", [None, "git-path-b64:", "git-path-b64:!", "git-path-b64:YQ"]
)
def test_wire_codec_rejects_invalid_tokens(value) -> None:
    from tree_sitter_analyzer.git_path_codec import path_from_wire

    with pytest.raises(snapshots.SourceOracleError, match="DIFF_SNAPSHOT_INVALID_PATH"):
        path_from_wire(value)


def test_wire_codec_rejects_non_unicode_literal() -> None:
    from tree_sitter_analyzer.git_path_codec import path_from_wire

    with pytest.raises(snapshots.SourceOracleError, match="DIFF_SNAPSHOT_INVALID_PATH"):
        path_from_wire("bad-\udcff")
