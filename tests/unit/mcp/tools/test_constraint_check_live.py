"""Exact behavior tests for live constraint configuration reads."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

import tree_sitter_analyzer.mcp.tools.constraint_check_live as live
from tree_sitter_analyzer.source_oracle import SafePath, SourceOracleError


class _ModuleProxy:
    def __init__(self, module: ModuleType, **overrides: Any) -> None:
        self._module = module
        self._overrides = overrides

    def __getattr__(self, name: str) -> Any:
        if name in self._overrides:
            return self._overrides[name]
        return getattr(self._module, name)


def _resized(info: os.stat_result) -> os.stat_result:
    values = list(info)
    values[stat.ST_SIZE] = int(info.st_size) + 1
    return os.stat_result(values)


def test_portable_probe_reads_nested_regular_config(tmp_path: Path) -> None:
    parent = tmp_path / ".tree-sitter-analyzer"
    parent.mkdir()
    config = parent / "constraints.yml"
    payload = b"version: 1\nconstraints: []\n"
    config.write_bytes(payload)

    result = live._portable_probe(
        str(tmp_path), ".tree-sitter-analyzer/constraints.yml", float("inf")
    )

    assert result == (
        payload,
        (
            live._identity(os.lstat(tmp_path)),
            live._identity(os.lstat(parent)),
            live._identity(os.lstat(config)),
        ),
        "file",
    )


def test_portable_probe_reports_missing_project_root(tmp_path: Path) -> None:
    result = live._portable_probe(
        str(tmp_path / "absent"),
        ".tree-sitter-analyzer/constraints.yml",
        float("inf"),
    )

    assert result == (None, (b"missing",), "missing")


def test_portable_probe_rejects_non_directory_project_root(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.write_text("not a directory")

    with pytest.raises(SourceOracleError, match="^CONSTRAINT_CONFIG_UNSAFE$"):
        live._portable_probe(
            str(project), ".tree-sitter-analyzer/constraints.yml", float("inf")
        )


def test_portable_probe_reports_missing_nested_parent(tmp_path: Path) -> None:
    result = live._portable_probe(
        str(tmp_path), ".tree-sitter-analyzer/constraints.yml", float("inf")
    )

    assert result == (
        None,
        (live._identity(os.lstat(tmp_path)), b"missing"),
        "missing",
    )


def test_portable_probe_rejects_non_directory_parent(tmp_path: Path) -> None:
    (tmp_path / ".tree-sitter-analyzer").write_text("not a directory")

    with pytest.raises(SourceOracleError, match="^CONSTRAINT_CONFIG_UNSAFE$"):
        live._portable_probe(
            str(tmp_path), ".tree-sitter-analyzer/constraints.yml", float("inf")
        )


def test_portable_probe_reports_missing_leaf(tmp_path: Path) -> None:
    result = live._portable_probe(
        str(tmp_path), "architectural-constraints.yml", float("inf")
    )

    assert result == (
        None,
        (live._identity(os.lstat(tmp_path)), b"missing"),
        "missing",
    )


def test_portable_probe_rejects_reparse_leaf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "architectural-constraints.yml"
    config.write_text("version: 1\nconstraints: []\n")
    leaf_identity = (config.stat().st_dev, config.stat().st_ino)
    monkeypatch.setattr(
        live,
        "_is_reparse",
        lambda info: (info.st_dev, info.st_ino) == leaf_identity,
    )

    with pytest.raises(SourceOracleError, match="^CONSTRAINT_CONFIG_UNSAFE$"):
        live._portable_probe(
            str(tmp_path), "architectural-constraints.yml", float("inf")
        )


def test_portable_probe_classifies_directory_leaf(tmp_path: Path) -> None:
    config = tmp_path / "architectural-constraints.yml"
    config.mkdir()

    result = live._portable_probe(
        str(tmp_path), "architectural-constraints.yml", float("inf")
    )

    assert result == (
        None,
        (
            live._identity(os.lstat(tmp_path)),
            live._identity(os.lstat(config)),
        ),
        "directory",
    )


def test_portable_probe_rejects_nonregular_leaf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "architectural-constraints.yml").write_text("content")
    monkeypatch.setattr(
        live,
        "stat",
        _ModuleProxy(stat, S_ISREG=lambda _mode: False),
    )

    with pytest.raises(SourceOracleError, match="^CONSTRAINT_CONFIG_UNSAFE$"):
        live._portable_probe(
            str(tmp_path), "architectural-constraints.yml", float("inf")
        )


def test_portable_probe_rejects_opened_identity_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "architectural-constraints.yml").write_text("content")

    def changed_fstat(fd: int) -> os.stat_result:
        return _resized(os.fstat(fd))

    monkeypatch.setattr(live, "os", _ModuleProxy(os, fstat=changed_fstat))

    with pytest.raises(SourceOracleError, match="^CONSTRAINT_CONFIG_CHANGED$"):
        live._portable_probe(
            str(tmp_path), "architectural-constraints.yml", float("inf")
        )


def test_portable_probe_enforces_read_deadline(tmp_path: Path) -> None:
    (tmp_path / "architectural-constraints.yml").write_text("content")

    with pytest.raises(RuntimeError, match="^CONSTRAINT_CONFIG_DEADLINE$"):
        live._portable_probe(str(tmp_path), "architectural-constraints.yml", 0.0)


def test_portable_probe_enforces_config_byte_capacity(tmp_path: Path) -> None:
    (tmp_path / "architectural-constraints.yml").write_bytes(b"x" * (1024 * 1024 + 1))

    with pytest.raises(SourceOracleError, match="^CONSTRAINT_CONFIG_CAPACITY$"):
        live._portable_probe(
            str(tmp_path), "architectural-constraints.yml", float("inf")
        )


def test_portable_probe_rejects_descriptor_change_after_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "architectural-constraints.yml").write_text("content")
    calls = 0

    def changing_fstat(fd: int) -> os.stat_result:
        nonlocal calls
        calls += 1
        info = os.fstat(fd)
        return _resized(info) if calls == 2 else info

    monkeypatch.setattr(live, "os", _ModuleProxy(os, fstat=changing_fstat))

    with pytest.raises(SourceOracleError, match="^CONSTRAINT_CONFIG_CHANGED$"):
        live._portable_probe(
            str(tmp_path), "architectural-constraints.yml", float("inf")
        )

    assert calls == 2


def test_portable_probe_rejects_leaf_change_after_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "architectural-constraints.yml"
    config.write_text("content")
    leaf_reads = 0

    def changing_lstat(path: os.PathLike[str] | str) -> os.stat_result:
        nonlocal leaf_reads
        info = os.lstat(path)
        if Path(path) == config:
            leaf_reads += 1
            return _resized(info) if leaf_reads == 2 else info
        return info

    monkeypatch.setattr(live, "os", _ModuleProxy(os, lstat=changing_lstat))

    with pytest.raises(SourceOracleError, match="^CONSTRAINT_CONFIG_CHANGED$"):
        live._portable_probe(str(tmp_path), config.name, float("inf"))

    assert leaf_reads == 2


def test_portable_probe_rejects_ancestor_change_after_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / ".tree-sitter-analyzer"
    parent.mkdir()
    (parent / "constraints.yml").write_text("content")
    root_reads = 0

    def changing_lstat(path: os.PathLike[str] | str) -> os.stat_result:
        nonlocal root_reads
        info = os.lstat(path)
        if Path(path) == tmp_path:
            root_reads += 1
            return _resized(info) if root_reads == 2 else info
        return info

    monkeypatch.setattr(live, "os", _ModuleProxy(os, lstat=changing_lstat))

    with pytest.raises(SourceOracleError, match="^CONSTRAINT_CONFIG_CHANGED$"):
        live._portable_probe(
            str(tmp_path), ".tree-sitter-analyzer/constraints.yml", float("inf")
        )

    assert root_reads == 2


def test_portable_probe_normalizes_operating_system_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def denied_lstat(_path: os.PathLike[str] | str) -> os.stat_result:
        raise PermissionError("denied")

    monkeypatch.setattr(live, "os", _ModuleProxy(os, lstat=denied_lstat))

    with pytest.raises(SourceOracleError) as caught:
        live._portable_probe(
            str(tmp_path), "architectural-constraints.yml", float("inf")
        )

    assert (
        str(caught.value),
        type(caught.value.__cause__),
        str(caught.value.__cause__),
    ) == ("CONSTRAINT_CONFIG_UNSAFE", PermissionError, "denied")


def test_live_config_snapshot_portable_falls_back_to_nested_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / ".tree-sitter-analyzer"
    parent.mkdir()
    config = parent / "constraints.yml"
    payload = b"version: 1\nconstraints: []\n"
    config.write_bytes(payload)
    monkeypatch.setattr(live, "_portable_config_required", lambda: True)

    result = live.live_config_snapshot(str(tmp_path), float("inf"))

    assert result == (
        ".tree-sitter-analyzer/constraints.yml",
        payload,
        (
            live._identity(os.lstat(tmp_path)),
            live._identity(os.lstat(parent)),
            live._identity(os.lstat(config)),
        ),
    )


def test_live_config_snapshot_portable_reports_absent_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(live, "_portable_config_required", lambda: True)

    result = live.live_config_snapshot(str(tmp_path), float("inf"))

    assert result == (None, None, ())


def test_live_config_snapshot_posix_reports_absent_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, str, float, int, bool]] = []

    def missing(
        root: str,
        candidate: str,
        *,
        deadline: float,
        limit: int,
        allow_directory: bool,
    ) -> SafePath:
        calls.append((root, candidate, deadline, limit, allow_directory))
        return SafePath(None, (b"missing",), "missing")

    monkeypatch.setattr(live, "_portable_config_required", lambda: False)
    monkeypatch.setattr(live, "safe_workspace_path", missing)

    result = live.live_config_snapshot(str(tmp_path), 9.0)

    assert result == (None, None, ())
    assert calls == [
        (str(tmp_path), "architectural-constraints.yml", 9.0, 1024 * 1024, True),
        (
            str(tmp_path),
            ".tree-sitter-analyzer/constraints.yml",
            9.0,
            1024 * 1024,
            True,
        ),
    ]


def test_live_config_snapshot_posix_rejects_ambiguous_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(live, "_portable_config_required", lambda: False)
    monkeypatch.setattr(
        live,
        "safe_workspace_path",
        lambda *_args, **_kwargs: SafePath(b"payload", (b"identity",), "special"),
    )

    with pytest.raises(SourceOracleError, match="^CONSTRAINT_CONFIG_UNSAFE$"):
        live.live_config_snapshot(str(tmp_path), float("inf"))


def test_config_changed_response_maps_snapshot_error() -> None:
    before = ("architectural-constraints.yml", b"content", (b"identity",))

    def unavailable(_root: str, _deadline: float):
        raise OSError("snapshot unavailable")

    def error_response(code: str, output_format: str, detail: str | None):
        return {"code": code, "format": output_format, "detail": detail}

    result = live.config_changed_response(
        "/project",
        before,
        7.0,
        "json",
        error_response,
        snapshot=unavailable,
    )

    assert result == {
        "code": "CONSTRAINT_CONFIG_UNKNOWN",
        "format": "json",
        "detail": "snapshot unavailable",
    }
