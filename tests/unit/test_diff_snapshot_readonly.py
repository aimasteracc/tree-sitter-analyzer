"""RFC-0022 P0.4 zero-write oracle differential contract.

The read-only oracle (``diff_snapshot_readonly``) must produce the exact
same source-generation token as the frozen oracle
(``source_oracle_git``) on identical source state — otherwise task routes
comparing impact tokens against the index oracle would diverge. These
tests prove byte-equality across clean/dirty/untracked/staged states and
assert the read-only invocation set never materializes a temporary index.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import time
from pathlib import Path

import pytest

from tests.unit._diff_snapshot_support import POSIX_SNAPSHOT_TEST
from tree_sitter_analyzer.diff_snapshot_readonly import (
    _live_index_output,
    oracle_generation_readonly,
)
from tree_sitter_analyzer.source_oracle_git import GitEpoch, oracle_generation


@pytest.fixture()
def git_repo(tmp_path) -> str:
    root = str(tmp_path)
    subprocess.run(["git", "init", "-q", root], check=True)
    subprocess.run(["git", "-C", root, "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", root, "config", "user.name", "t"], check=True)
    (tmp_path / "base.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "keep.py").write_text("keep = True\n", encoding="utf-8")
    subprocess.run(["git", "-C", root, "add", "."], check=True)
    subprocess.run(["git", "-C", root, "commit", "-qm", "init"], check=True)
    return root


def _epochs(root: str, mode: str) -> tuple[GitEpoch, GitEpoch]:
    frozen_epochs: list[GitEpoch] = []
    readonly_epochs: list[GitEpoch] = []
    frozen_gen, _ = oracle_generation(root, mode, epoch_out=frozen_epochs)
    readonly_gen, _ = oracle_generation_readonly(root, mode, epoch_out=readonly_epochs)
    assert frozen_gen == readonly_gen
    return frozen_epochs[0], readonly_epochs[0]


@POSIX_SNAPSHOT_TEST
def test_clean_repo_generations_match(git_repo: str) -> None:
    for mode in ("diff", "staged"):
        frozen_epoch, readonly_epoch = _epochs(git_repo, mode)
        assert frozen_epoch.tracked_paths == readonly_epoch.tracked_paths
        assert frozen_epoch.dirty_paths == readonly_epoch.dirty_paths
        assert frozen_epoch.untracked_paths == readonly_epoch.untracked_paths


@POSIX_SNAPSHOT_TEST
def test_dirty_and_untracked_generations_match(git_repo: str) -> None:
    import pathlib

    root = pathlib.Path(git_repo)
    (root / "base.py").write_text("value = 2\n", encoding="utf-8")
    (root / "new_file.py").write_text("brand = 'new'\n", encoding="utf-8")
    (root / "ignored.log").write_text("noise\n", encoding="utf-8")
    (root / ".gitignore").write_text("*.log\n", encoding="utf-8")

    frozen_epoch, readonly_epoch = _epochs(git_repo, "diff")
    # The frozen oracle's stat-invalidation framing conservatively reports
    # every tracked path dirty; the P0.4 oracle replicates it exactly.
    assert frozen_epoch.dirty_paths == (b"base.py", b"keep.py")
    assert frozen_epoch.untracked_paths == (b".gitignore", b"new_file.py")
    assert readonly_epoch.dirty_paths == frozen_epoch.dirty_paths
    assert readonly_epoch.untracked_paths == frozen_epoch.untracked_paths

    # Staged mode ignores the worktree dirt but includes the staged change.
    subprocess.run(["git", "-C", git_repo, "add", "base.py"], check=True)
    frozen_epoch, readonly_epoch = _epochs(git_repo, "staged")
    assert readonly_epoch.dirty_paths == frozen_epoch.dirty_paths
    assert readonly_epoch.untracked_paths == frozen_epoch.untracked_paths


@POSIX_SNAPSHOT_TEST
def test_generation_changes_when_source_changes(git_repo: str) -> None:
    import pathlib

    before = oracle_generation_readonly(git_repo, "diff")[0]
    pathlib.Path(git_repo, "base.py").write_text("value = 3\n", encoding="utf-8")
    after = oracle_generation_readonly(git_repo, "diff")[0]
    assert before != after
    # Deterministic for the same state.
    assert after == oracle_generation_readonly(git_repo, "diff")[0]


@POSIX_SNAPSHOT_TEST
def test_readonly_never_materializes_temporary_index(
    git_repo: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tempfile

    mkstemp_calls: list[str] = []

    def spy_mkstemp(*args, **kwargs):
        mkstemp_calls.append("mkstemp")
        return tempfile.mkstemp(*args, **kwargs)

    monkeypatch.setattr(tempfile, "mkstemp", spy_mkstemp)
    # The read-only oracle must never invoke the temp-index machinery.
    frozen_epochs: list[GitEpoch] = []
    oracle_generation_readonly(git_repo, "diff", epoch_out=frozen_epochs)
    assert mkstemp_calls == []


@POSIX_SNAPSHOT_TEST
def test_live_index_output_is_readonly_invocation(git_repo: str) -> None:
    """GIT_OPTIONAL_LOCKS=0 is set and no GIT_INDEX_FILE is injected."""
    import tree_sitter_analyzer.diff_snapshot_readonly as module

    seen_env: dict[str, str] = {}

    def spy(root, args, *, deadline, limit, env=None, input_=None, ok_returncodes=None):
        seen_env.update(dict(env or {}))
        return b""

    original = module.run_git_readonly
    module.run_git_readonly = spy
    try:
        import time as _time

        _live_index_output(
            git_repo,
            b"",
            ["ls-files", "--others"],
            deadline=_time.monotonic() + 35.0,
            limit=1024,
        )
    finally:
        module.run_git_readonly = original
    assert seen_env.get("GIT_OPTIONAL_LOCKS") == "0"
    assert "GIT_INDEX_FILE" not in seen_env


@POSIX_SNAPSHOT_TEST
def test_workspace_unsupported_fails_closed(git_repo: str, monkeypatch) -> None:
    import tree_sitter_analyzer.diff_snapshot_readonly as module

    monkeypatch.setattr(module, "_supports_nofollow", lambda: False)
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_WORKSPACE_UNSUPPORTED"):
        oracle_generation_readonly(git_repo, "diff")


@POSIX_SNAPSHOT_TEST
def test_root_mismatch_fails_closed(git_repo: str) -> None:
    import os

    subdir = os.path.join(git_repo, "sub")
    os.mkdir(subdir)
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_ROOT_MISMATCH"):
        oracle_generation_readonly(subdir, "diff")


@POSIX_SNAPSHOT_TEST
def test_gitlink_generations_match(git_repo: str) -> None:
    import pathlib

    # A local-path submodule produces a 160000 gitlink entry; both oracles
    # frame it identically (dirty marker + index identity).
    sub_repo = pathlib.Path(git_repo, "vendor")
    sub_repo.mkdir()
    subprocess.run(["git", "init", "-q", str(sub_repo)], check=True)
    subprocess.run(
        ["git", "-C", str(sub_repo), "config", "user.email", "t@t"], check=True
    )
    subprocess.run(["git", "-C", str(sub_repo), "config", "user.name", "t"], check=True)
    (sub_repo / "lib.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(sub_repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(sub_repo), "commit", "-qm", "sub"], check=True)
    subprocess.run(
        ["git", "-C", git_repo, "submodule", "add", "-q", str(sub_repo), "vendor"],
        check=True,
    )
    frozen_epoch, readonly_epoch = _epochs(git_repo, "diff")
    assert frozen_epoch.workspace_gitlinks == readonly_epoch.workspace_gitlinks
    # git's diff-files name-only never reports gitlink entries (live or
    # stat-invalidated), so neither oracle frames gitlink-dirty evidence;
    # the gitlink is framed as an opaque tracked path instead.
    assert frozen_epoch.workspace_gitlinks == ()
    assert b"vendor" in frozen_epoch.tracked_paths


@POSIX_SNAPSHOT_TEST
def test_split_index_fails_closed(git_repo: str) -> None:
    subprocess.run(["git", "-C", git_repo, "update-index", "--split-index"], check=True)
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_UNSUPPORTED_INDEX"):
        oracle_generation_readonly(git_repo, "diff")


@POSIX_SNAPSHOT_TEST
def test_capacity_fails_closed(git_repo: str) -> None:
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_CAPACITY"):
        oracle_generation_readonly(git_repo, "diff", byte_ceiling=1)


@POSIX_SNAPSHOT_TEST
def test_runner_popen_failure_is_stable_error(git_repo: str, monkeypatch) -> None:
    import tree_sitter_analyzer.git_readonly as module

    def boom(*args, **kwargs):
        raise OSError("no git here")

    monkeypatch.setattr(module.subprocess, "Popen", boom)
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_GIT_ERROR"):
        _live_index_output(
            git_repo,
            b"",
            ["ls-files", "--others"],
            deadline=time.monotonic() + 35.0,
            limit=1024,
        )


@POSIX_SNAPSHOT_TEST
def test_runner_negative_limit_fails_closed(git_repo: str) -> None:
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_CAPACITY"):
        _live_index_output(
            git_repo,
            b"",
            ["ls-files", "--others"],
            deadline=time.monotonic() + 35.0,
            limit=-1,
        )


class _FakeProc:
    """Minimal fake subprocess for runner error-path tests."""

    def __init__(self, stdout, stderr, stdin=None, returncode=1):
        self.stdout = stdout
        self.stderr = stderr
        self.stdin = stdin
        self.returncode = returncode

    def wait(self, timeout=0):
        return 0

    def kill(self):
        pass


class _RaisingStream:
    def read(self, size):
        raise OSError("stream gone")


class _UnboundedStream:
    def read(self, size):
        return b"x" * 65536


@POSIX_SNAPSHOT_TEST
def test_runner_stream_failure_is_stable_error(git_repo: str, monkeypatch) -> None:
    import tree_sitter_analyzer.git_readonly as module

    for proc in (
        _FakeProc(stdout=None, stderr=None),  # missing streams
        _FakeProc(stdout=_RaisingStream(), stderr=_RaisingStream()),
        _FakeProc(stdout=_UnboundedStream(), stderr=_UnboundedStream()),
    ):

        def fake_popen(*a, _proc=proc, **k):
            return _proc

        monkeypatch.setattr(module.subprocess, "Popen", fake_popen)
        with pytest.raises(
            Exception, match="DIFF_SNAPSHOT_GIT_ERROR|DIFF_SNAPSHOT_CAPACITY"
        ):
            _live_index_output(
                git_repo,
                b"",
                ["ls-files", "--others"],
                deadline=time.monotonic() + 35.0,
                limit=1024,
            )


@POSIX_SNAPSHOT_TEST
def test_dirty_gitlink_frames_opaque_evidence(git_repo: str, monkeypatch) -> None:
    # Mirrors the frozen oracle's own dirty-gitlink test (monkeypatched
    # inventory): a gitlink the read-only probe reports dirty frames
    # opaque evidence and is retained as workspace_gitlinks.
    import tree_sitter_analyzer.diff_snapshot_readonly as module

    sub_repo = os.path.join(git_repo, "vendor")
    os.mkdir(sub_repo)
    subprocess.run(["git", "init", "-q", sub_repo], check=True)
    subprocess.run(["git", "-C", sub_repo, "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", sub_repo, "config", "user.name", "t"], check=True)
    (Path(sub_repo) / "lib.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", sub_repo, "add", "."], check=True)
    subprocess.run(["git", "-C", sub_repo, "commit", "-qm", "sub"], check=True)
    subprocess.run(
        ["git", "-C", git_repo, "submodule", "add", "-q", sub_repo, "vendor"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", git_repo, "commit", "-qm", "add submodule"], check=True
    )

    monkeypatch.setattr(
        module, "_dirty_gitlink_probes_readonly", lambda *a, **k: {b"vendor"}
    )
    epochs: list = []
    oracle_generation_readonly(git_repo, "diff", epoch_out=epochs)
    entry = dict(epochs[0].index_entries)[b"vendor"]
    assert entry.startswith(b"160000 ")
    assert epochs[0].workspace_gitlinks == ((b"vendor", entry),)
    assert b"vendor" in epochs[0].dirty_paths


@POSIX_SNAPSHOT_TEST
def test_inventory_consistency_check_fails_closed(git_repo: str, monkeypatch) -> None:
    import tree_sitter_analyzer.diff_snapshot_readonly as module

    original = module._live_index_output

    def fake_live_output(root, index_bytes, args, **kwargs):
        if args and args[0] == "diff-files":
            return b"not-tracked.py\0"
        return original(root, index_bytes, args, **kwargs)

    monkeypatch.setattr(module, "_live_index_output", fake_live_output)
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_GIT_ERROR"):
        oracle_generation_readonly(git_repo, "diff")


@POSIX_SNAPSHOT_TEST
def test_worktree_path_capacity_fails_closed(git_repo: str, monkeypatch) -> None:
    import tree_sitter_analyzer.diff_snapshot_readonly as module

    original = module._live_index_output
    many = b"".join(f"f{i}.py\0".encode() for i in range(250_000))

    def fake_live_output(root, index_bytes, args, **kwargs):
        if args and args[0] == "ls-files":
            return many
        return original(root, index_bytes, args, **kwargs)

    monkeypatch.setattr(module, "_live_index_output", fake_live_output)
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_CAPACITY"):
        oracle_generation_readonly(git_repo, "diff")


@POSIX_SNAPSHOT_TEST
@pytest.mark.slow_ok  # two git captures + generation oracle: real subprocess work
def test_empty_repo_generations_match(tmp_path) -> None:
    root = str(tmp_path / "empty")
    os.mkdir(root)
    subprocess.run(["git", "init", "-q", root], check=True)
    for mode in ("diff", "staged"):
        frozen_epochs: list = []
        readonly_epochs: list = []
        frozen_gen, _ = oracle_generation(root, mode, epoch_out=frozen_epochs)
        readonly_gen, _ = oracle_generation_readonly(
            root, mode, epoch_out=readonly_epochs
        )
        assert frozen_gen == readonly_gen


@POSIX_SNAPSHOT_TEST
def test_root_resolution_failure_fails_closed(git_repo: str, monkeypatch) -> None:
    import tree_sitter_analyzer.diff_snapshot_readonly as module

    original = module._git_output_readonly

    def fake_git_output(root, args, *, deadline, limit):
        if args and args[0] == "rev-parse" and "--show-toplevel" in args:
            return b"no-such-dir-xyz\n"  # canonical_root stat fails
        return original(root, args, deadline=deadline, limit=limit)

    monkeypatch.setattr(module, "_git_output_readonly", fake_git_output)
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_ROOT_MISMATCH"):
        oracle_generation_readonly(git_repo, "diff")


class _BlockingStream:
    def read(self, size):
        import time as _t

        _t.sleep(30)  # blocks past any reasonable deadline
        return b""


class _BrokenStdin:
    def write(self, data):
        raise BrokenPipeError("pipe closed")

    def close(self):
        pass


@POSIX_SNAPSHOT_TEST
def test_runner_feed_broken_pipe_is_ignored(git_repo: str, monkeypatch) -> None:
    import tree_sitter_analyzer.git_readonly as module

    class _EmptyStream:
        def read(self, size):
            return b""

    for stdin in (None, _BrokenStdin()):
        proc = _FakeProc(
            stdout=_EmptyStream(),
            stderr=_EmptyStream(),
            stdin=stdin,
            returncode=0,
        )

        def fake_popen(*a, _proc=proc, **k):
            return _proc

        monkeypatch.setattr(module.subprocess, "Popen", fake_popen)
        out = _live_index_output(
            git_repo,
            b"",
            ["ls-files", "--others"],
            deadline=time.monotonic() + 35.0,
            limit=1024,
            input_=b"input-data",
        )
        assert out == b""


@POSIX_SNAPSHOT_TEST
def test_runner_blocking_stream_times_out(git_repo: str, monkeypatch) -> None:
    import tree_sitter_analyzer.git_readonly as module

    proc = _FakeProc(stdout=_BlockingStream(), stderr=_BlockingStream())
    monkeypatch.setattr(module.subprocess, "Popen", lambda *a, **k: proc)
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_TIMEOUT"):
        _live_index_output(
            git_repo,
            b"",
            ["ls-files", "--others"],
            deadline=time.monotonic() + 0.8,
            limit=1024,
        )


@POSIX_SNAPSHOT_TEST
def test_runner_kill_cleanup_swallows_wait_errors(git_repo: str, monkeypatch) -> None:
    import tree_sitter_analyzer.git_readonly as module

    class _SlowKillProc(_FakeProc):
        def wait(self, timeout=0):
            if self._wait_calls:
                raise subprocess.TimeoutExpired("git", 0)
            self._wait_calls = True
            return 0

    class _EmptyStream:
        def read(self, size):
            return b""

    proc = _SlowKillProc(stdout=_EmptyStream(), stderr=_EmptyStream(), returncode=1)
    proc._wait_calls = False
    monkeypatch.setattr(module.subprocess, "Popen", lambda *a, **k: proc)
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_GIT_ERROR"):
        _live_index_output(
            git_repo,
            b"",
            ["ls-files", "--others"],
            deadline=time.monotonic() + 35.0,
            limit=1024,
        )


@POSIX_SNAPSHOT_TEST
def test_runner_nonzero_exit_is_stable_error(git_repo: str, monkeypatch) -> None:
    import tree_sitter_analyzer.git_readonly as module

    class _EmptyStream:
        def read(self, size):
            return b""

    proc = _FakeProc(stdout=_EmptyStream(), stderr=_EmptyStream(), returncode=2)
    monkeypatch.setattr(module.subprocess, "Popen", lambda *a, **k: proc)
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_GIT_ERROR"):
        _live_index_output(
            git_repo,
            b"",
            ["ls-files", "--others"],
            deadline=time.monotonic() + 35.0,
            limit=1024,
        )


@POSIX_SNAPSHOT_TEST
def test_assume_unchanged_hint_preserves_generation_equality(
    git_repo: str,
) -> None:
    # Codex #1293 P1: assume-unchanged paths are never dirty and never
    # content-framed by the frozen oracle; the P0.4 oracle must replicate.
    subprocess.run(
        ["git", "-C", git_repo, "update-index", "--assume-unchanged", "keep.py"],
        check=True,
    )
    frozen_epoch, readonly_epoch = _epochs(git_repo, "diff")
    assert b"keep.py" not in frozen_epoch.dirty_paths
    assert readonly_epoch.dirty_paths == frozen_epoch.dirty_paths


@POSIX_SNAPSHOT_TEST
def test_configured_orderfile_fails_closed(git_repo: str) -> None:
    subprocess.run(
        ["git", "-C", git_repo, "config", "diff.orderFile", "order.txt"],
        check=True,
    )
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_UNSUPPORTED_ORDERFILE"):
        oracle_generation_readonly(git_repo, "staged")


@POSIX_SNAPSHOT_TEST
def test_index_entries_parser_matches_ls_files(git_repo: str) -> None:
    from tree_sitter_analyzer.diff_snapshot_readonly import (
        _index_entries_from_bytes,
    )
    from tree_sitter_analyzer.source_oracle_git import _index_entries

    index_bytes = pathlib.Path(git_repo, ".git", "index").read_bytes()
    mine = _index_entries_from_bytes(index_bytes, "sha1", 200_000)
    frozen = _index_entries(
        git_repo, deadline=time.monotonic() + 35.0, index_bytes=None
    )
    assert mine == frozen


@POSIX_SNAPSHOT_TEST
def test_hinted_paths_detection(git_repo: str) -> None:
    from tree_sitter_analyzer.diff_snapshot_readonly import _hinted_paths

    subprocess.run(
        ["git", "-C", git_repo, "update-index", "--assume-unchanged", "keep.py"],
        check=True,
    )
    index_bytes = pathlib.Path(git_repo, ".git", "index").read_bytes()
    assert _hinted_paths(index_bytes, "sha1", 200_000) == {b"keep.py"}


@POSIX_SNAPSHOT_TEST
def test_object_format_readonly_rejects_unknown(git_repo: str, monkeypatch) -> None:
    import tree_sitter_analyzer.diff_snapshot_readonly as module

    monkeypatch.setattr(
        module,
        "_git_output_readonly",
        lambda root, args, *, deadline, limit: b"md5\n",
    )
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_GIT_ERROR"):
        module._object_format_readonly(git_repo, deadline=time.monotonic() + 35.0)


@POSIX_SNAPSHOT_TEST
def test_head_identity_symbolic_ref_failure(git_repo: str, monkeypatch) -> None:
    import tree_sitter_analyzer.diff_snapshot_readonly as module

    def fake(root, args, *, deadline, limit):
        if "--verify" in args:
            raise module.SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        raise module.SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")

    monkeypatch.setattr(module, "_git_output_readonly", fake)
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_GIT_ERROR"):
        module._head_identity_readonly(git_repo, deadline=time.monotonic() + 35.0)


@POSIX_SNAPSHOT_TEST
def test_index_parser_rejects_unknown_version() -> None:
    from tree_sitter_analyzer.diff_snapshot_readonly import (
        _hinted_paths,
        _index_entries_from_bytes,
    )

    bogus = b"DIRC" + (4).to_bytes(4, "big") + (0).to_bytes(4, "big")
    for parser in (_hinted_paths, _index_entries_from_bytes):
        with pytest.raises(Exception, match="DIFF_SNAPSHOT_UNSUPPORTED_INDEX"):
            parser(bogus, "sha1", 100)


@POSIX_SNAPSHOT_TEST
def test_index_parser_rejects_malformed_entry() -> None:
    from tree_sitter_analyzer.diff_snapshot_readonly import _hinted_paths

    # v2 header claiming one entry but no entry bytes.
    truncated = b"DIRC" + (2).to_bytes(4, "big") + (1).to_bytes(4, "big")
    truncated += b"\0" * 20  # far too short for an entry
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_GIT_ERROR"):
        _hinted_paths(truncated, "sha1", 100)
    # Entry with a valid fixed part but an unterminated path.
    entry = b"\0" * 62 + b"no-nul-path"
    truncated2 = b"DIRC" + (2).to_bytes(4, "big") + (1).to_bytes(4, "big")
    truncated2 += entry + b"\0" * 20
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_GIT_ERROR"):
        _hinted_paths(truncated2, "sha1", 100)


@POSIX_SNAPSHOT_TEST
def test_entries_parser_rejects_malformed_and_skips_staged() -> None:
    from tree_sitter_analyzer.diff_snapshot_readonly import _index_entries_from_bytes

    # Truncated entry (fixed part beyond the content end).
    short = b"DIRC" + (2).to_bytes(4, "big") + (1).to_bytes(4, "big")
    short += b"\0" * 30 + b"\0" * 20
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_GIT_ERROR"):
        _index_entries_from_bytes(short, "sha1", 100)
    # Unterminated path.
    bad = b"DIRC" + (2).to_bytes(4, "big") + (1).to_bytes(4, "big")
    bad += b"\0" * 62 + b"no-nul-path" + b"\0" * 20
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_GIT_ERROR"):
        _index_entries_from_bytes(bad, "sha1", 100)
    # A stage-1 entry (conflict) is skipped; stage-0 is kept. Each entry is
    # padded to a multiple of 8 bytes total.
    flags_stage1 = (1 << 12).to_bytes(2, "big")
    fixed = b"\0" * 40 + b"\x01" * 20 + flags_stage1
    entry1 = fixed + b"conflict.py\x00" + b"\x00" * 6  # 62+12 -> 80
    flags_stage0 = (0).to_bytes(2, "big")
    fixed0 = b"\0" * 24 + (0o100644).to_bytes(4, "big") + b"\0" * 12
    fixed0 += b"\x02" * 20 + flags_stage0
    entry0 = fixed0 + b"ok.py\x00" + b"\x00" * 4  # 62+6 -> 72
    payload = b"DIRC" + (2).to_bytes(4, "big") + (2).to_bytes(4, "big")
    payload += entry1 + entry0 + b"\0" * 20
    parsed = _index_entries_from_bytes(payload, "sha1", 100)
    assert set(parsed) == {b"ok.py"}
    assert parsed[b"ok.py"] == (
        b"100644 " + (b"\x02" * 20).hex().encode("ascii") + b" 0"
    )


@POSIX_SNAPSHOT_TEST
def test_entries_parser_capacity_bound() -> None:
    from tree_sitter_analyzer.diff_snapshot_readonly import _index_entries_from_bytes

    flags_stage0 = (0).to_bytes(2, "big")
    fixed0 = b"\0" * 24 + (0o100644).to_bytes(4, "big") + b"\0" * 12
    fixed0 += b"\x02" * 20 + flags_stage0
    entry0 = fixed0 + b"ok.py\x00" + b"\x00" * 4  # 62+6 -> 72
    payload = b"DIRC" + (2).to_bytes(4, "big") + (1).to_bytes(4, "big")
    payload += entry0 + b"\0" * 20
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_CAPACITY"):
        _index_entries_from_bytes(payload, "sha1", max_paths=0)


class _ByteStream:
    """Minimal readable stream for fake-proc runner tests."""

    def __init__(self, data: bytes):
        self.data = data

    def read(self, size: int) -> bytes:
        chunk, self.data = self.data[:size], self.data[size:]
        return chunk


@POSIX_SNAPSHOT_TEST
def test_runner_ok_returncodes_accepts_exit_one(git_repo: str, monkeypatch) -> None:
    """``git diff --no-index`` exits 1 on differences (RFC-0022 P0.4)."""
    import tree_sitter_analyzer.git_readonly as module

    class _ExitOneProc(_FakeProc):
        def __init__(self):
            super().__init__(
                stdout=_ByteStream(b"diff --git a/x b/x\n"),
                stderr=_ByteStream(b""),
                returncode=1,
            )

    monkeypatch.setattr(module.subprocess, "Popen", lambda *a, **k: _ExitOneProc())
    out = module.run_git_readonly(
        git_repo,
        ["diff", "--no-index", "/dev/null", "x"],
        deadline=time.monotonic() + 35.0,
        limit=1024,
        ok_returncodes=frozenset({0, 1}),
    )
    assert out == b"diff --git a/x b/x\n"
    # The default invocation set still rejects exit 1.
    monkeypatch.setattr(module.subprocess, "Popen", lambda *a, **k: _ExitOneProc())
    with pytest.raises(Exception, match="DIFF_SNAPSHOT_GIT_ERROR"):
        module.run_git_readonly(
            git_repo,
            ["diff", "--no-index", "/dev/null", "x"],
            deadline=time.monotonic() + 35.0,
            limit=1024,
        )
