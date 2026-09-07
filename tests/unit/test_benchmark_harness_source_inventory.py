"""Issue #1376：test_benchmark_harness_source_inventory 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import hashlib
import os as os
import subprocess
import sys
import time
from functools import partial
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from tests.unit._benchmark_harness_platform import (
    mark_posix_qualification_section_tests,
)
from tests.unit._benchmark_harness_qualification_helpers import (
    _qualification_git_repo,
    _qualification_source_inventory,
)

_POSIX_QUALIFICATION_SECTION_START = sys._getframe().f_lineno
_mark_posix_qualification_section_tests = partial(
    mark_posix_qualification_section_tests, globals()
)


@pytest.mark.parametrize("relative", ("rogue.ts", "qualification-index/artifact.bin"))
def test_source_inventory_rejects_one_untracked_checkout_path(
    tmp_path: Path, relative: str
):
    # PR #1247: 新的资格验证工作副本不能包含未跟踪输入。
    from benchmarks.codegraph_compare.setup_qualification import (
        DEFAULT_SOURCE_RULES,
        inventory_sources,
    )

    repo = tmp_path / "repo"
    _qualification_git_repo(repo)
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"untrusted")

    with pytest.raises(ValueError, match="tracked or untracked changes"):
        inventory_sources("vscode", repo, DEFAULT_SOURCE_RULES)


def test_source_inventory_rechecks_exact_full_status_after_blob_scan(tmp_path: Path):
    # PR #1247: 清单生成前后都要快照检查工作副本是否干净。
    import benchmarks.codegraph_compare.setup_qualification_inventory as module
    from benchmarks.codegraph_compare.setup_qualification import (
        DEFAULT_SOURCE_RULES,
        inventory_sources,
    )

    repo = tmp_path / "repo"
    _qualification_git_repo(repo)
    calls: list[tuple[str, ...]] = []
    original_git = module._git

    def recording_git(path, *arguments, **kwargs):
        calls.append(arguments)
        return original_git(path, *arguments, **kwargs)

    with patch.object(module, "_git", side_effect=recording_git):
        inventory_sources("vscode", repo, DEFAULT_SOURCE_RULES)

    assert (
        calls.count(
            (
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                "--ignored=matching",
            )
        )
        == 2
    )


def test_source_inventory_rejects_assume_unchanged_flag(tmp_path: Path):
    # PR #1247: status porcelain 会隐藏 assume-unchanged 工作副本的偏离。
    from benchmarks.codegraph_compare.setup_qualification import (
        DEFAULT_SOURCE_RULES,
        inventory_sources,
    )

    repo = tmp_path / "repo"
    _qualification_git_repo(repo)
    subprocess.run(
        ["git", "update-index", "--assume-unchanged", "main.ts"],
        cwd=repo,
        check=True,
    )
    (repo / "main.ts").write_text("export class Decoy {}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Hidden tracked index flag"):
        inventory_sources("vscode", repo, DEFAULT_SOURCE_RULES)


def test_source_inventory_rejects_skip_worktree_flag(tmp_path: Path):
    # PR #1247: skip-worktree 条目不能证明构建实际使用的字节。
    from benchmarks.codegraph_compare.setup_qualification import (
        DEFAULT_SOURCE_RULES,
        inventory_sources,
    )

    repo = tmp_path / "repo"
    _qualification_git_repo(repo)
    subprocess.run(
        ["git", "update-index", "--skip-worktree", "main.ts"],
        cwd=repo,
        check=True,
    )

    with pytest.raises(ValueError, match="Hidden tracked index flag S"):
        inventory_sources("vscode", repo, DEFAULT_SOURCE_RULES)


def test_source_inventory_hashes_eligible_worktree_bytes_against_blob(
    tmp_path: Path,
):
    # PR #1247: 构建输入字节须独立于 Git 状态提示进行验证。
    import benchmarks.codegraph_compare.setup_qualification_inventory as module
    from benchmarks.codegraph_compare.setup_qualification import (
        DEFAULT_SOURCE_RULES,
        inventory_sources,
    )

    repo = tmp_path / "repo"
    _qualification_git_repo(repo)
    pristine_flags = module._tracked_flags(repo)
    subprocess.run(
        ["git", "update-index", "--assume-unchanged", "main.ts"],
        cwd=repo,
        check=True,
    )
    (repo / "main.ts").write_text("export class Decoy {}\n", encoding="utf-8")

    with (
        patch.object(module, "_tracked_flags", return_value=pristine_flags),
        pytest.raises(ValueError, match="worktree bytes do not match pinned blob"),
    ):
        inventory_sources("vscode", repo, DEFAULT_SOURCE_RULES)


def test_source_rules_inventory_tracks_only_regular_files(tmp_path: Path):
    inventory = _qualification_source_inventory(tmp_path)

    assert inventory.tracked_regular_paths == ("generated.ts", "main.ts", "notes.md")


def test_source_rules_inventory_selects_eligible_source(tmp_path: Path):
    inventory = _qualification_source_inventory(tmp_path)

    assert inventory.eligible_paths == ("main.ts",)


def test_source_inventory_requires_canonical_worktree_root(tmp_path: Path):
    # PR #1247: 仅限子目录的 ls-files 结果不能代表整个提交。
    from benchmarks.codegraph_compare.setup_qualification import (
        DEFAULT_SOURCE_RULES,
        inventory_sources,
    )

    repo = tmp_path / "repo"
    _qualification_git_repo(repo)

    with pytest.raises(ValueError, match="canonical Git worktree root"):
        inventory_sources("vscode", repo / "deps", DEFAULT_SOURCE_RULES)


@pytest.mark.parametrize(
    ("path", "reason"),
    (
        ("deps/submodule", "gitlink"),
        ("generated.ts", "generated"),
        ("linked.ts", "symlink"),
        ("notes.md", "extension"),
    ),
)
def test_source_rules_inventory_classifies_one_exclusion(
    tmp_path: Path, path: str, reason: str
):
    inventory = _qualification_source_inventory(tmp_path)

    assert dict(inventory.prefilter_exclusions)[path] == reason


def test_source_rules_inventory_hashes_exact_eligible_paths(tmp_path: Path):
    from benchmarks.codegraph_compare.integrity import _sha256

    inventory = _qualification_source_inventory(tmp_path)

    assert inventory.eligible_paths_hash == _sha256(["main.ts"])


def test_git_batch_parser_uses_size_framing_for_embedded_nul():
    import io

    import benchmarks.codegraph_compare.setup_qualification_inventory as inventory_module

    payload = b"before\0after"
    digest = hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()
    output = f"{digest} blob {len(payload)}".encode() + b"\0" + payload + b"\0"

    assert inventory_module._stream_blob(
        io.BytesIO(output), "source.ts", digest, 0
    ) == (hashlib.sha256(payload).hexdigest(), False, len(payload))


def test_git_blob_generated_marker_is_detected_after_former_prefix_limit():
    # PR #1247: 生成文件标记适用于整个固定的 blob。
    import io

    import benchmarks.codegraph_compare.setup_qualification_inventory as inventory_module

    payload = b"x" * 5000 + b"DO NOT EDIT"
    digest = hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()
    output = f"{digest} blob {len(payload)}".encode() + b"\0" + payload + b"\0"

    assert inventory_module._stream_blob(
        io.BytesIO(output), "generated.ts", digest, 0, (b"DO NOT EDIT",)
    ) == (hashlib.sha256(payload).hexdigest(), True, len(payload))


def test_git_blob_generated_marker_is_detected_across_chunk_boundary():
    # PR #1247: 滚动重叠区用于绑定跨越流分块边界的标记。
    import io

    import benchmarks.codegraph_compare.setup_qualification_inventory as inventory_module

    payload = b"1234567DO NOT EDITtail"
    digest = hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()
    output = f"{digest} blob {len(payload)}".encode() + b"\0" + payload + b"\0"
    with patch.object(inventory_module, "_STREAM_CHUNK_BYTES", 8):
        result = inventory_module._stream_blob(
            io.BytesIO(output), "generated.ts", digest, 0, (b"DO NOT EDIT",)
        )

    assert result == (hashlib.sha256(payload).hexdigest(), True, len(payload))


def test_git_batch_rejects_blob_above_trusted_ceiling():
    import io

    import benchmarks.codegraph_compare.setup_qualification_inventory as inventory_module

    digest = "a" * 40
    output = f"{digest} blob 8".encode() + b"\0"
    with (
        patch.object(inventory_module, "_GIT_BLOB_CEILING_BYTES", 7),
        pytest.raises(ValueError, match="blob exceeds trusted size ceiling"),
    ):
        inventory_module._stream_blob(io.BytesIO(output), "large.ts", digest, 0)


def test_git_batch_rejects_repository_above_trusted_total_ceiling():
    import io

    import benchmarks.codegraph_compare.setup_qualification_inventory as inventory_module

    payload = b"content"
    digest = hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()
    output = f"{digest} blob {len(payload)}".encode() + b"\0"
    with (
        patch.object(inventory_module, "_GIT_TOTAL_CEILING_BYTES", len(payload)),
        pytest.raises(ValueError, match="trusted total size ceiling"),
    ):
        inventory_module._stream_blob(io.BytesIO(output), "source.ts", digest, 1)


@pytest.mark.parametrize(
    "mutate",
    (
        lambda header, payload: header.replace(b" blob ", b" tree ") + payload + b"\0",
        lambda header, payload: (
            header.replace(str(len(payload)).encode(), str(len(payload) + 1).encode())
            + payload
            + b"\0"
        ),
        lambda header, payload: header + payload + b"X",
    ),
)
def test_git_batch_parser_rejects_malformed_type_size_or_terminator(mutate):
    # PR #1247: 批量帧解析必须失败关闭，不能错位进入下一个 blob。
    import io

    import benchmarks.codegraph_compare.setup_qualification_inventory as inventory_module

    payload = b"content"
    digest = hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()
    header = f"{digest} blob {len(payload)}".encode() + b"\0"

    with pytest.raises(ValueError, match="Git batch"):
        inventory_module._stream_blob(
            io.BytesIO(mutate(header, payload)), "source.ts", digest, 0
        )


def test_git_batch_timeout_kills_and_reaps_process(tmp_path: Path):
    import io

    import benchmarks.codegraph_compare.setup_qualification_inventory as inventory_module

    class SlowOutput:
        def read(self, _size):
            time.sleep(0.1)
            return b""

    process = Mock(args=["git", "cat-file", "--batch", "-Z"])
    process.stdin = io.BytesIO()
    process.stdout = SlowOutput()
    process.poll.return_value = None
    with (
        patch.object(inventory_module.subprocess, "Popen", return_value=process),
        patch.object(inventory_module, "_GIT_TIMEOUT_SECONDS", 0.01),
    ):
        with pytest.raises(subprocess.TimeoutExpired):
            inventory_module._batch_blob_metadata(tmp_path, (("source.ts", "a" * 40),))

    process.kill.assert_called_once_with()
    process.wait.assert_called_once_with()


def test_large_source_inventory_uses_constant_subprocess_count(tmp_path: Path):
    # PR #1247: 进程数量不能随跟踪的普通 blob 数量线性增长。
    import benchmarks.codegraph_compare.setup_qualification_inventory as inventory_module
    from benchmarks.codegraph_compare.setup_qualification import (
        DEFAULT_SOURCE_RULES,
        inventory_sources,
    )

    repo = tmp_path / "large-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    for number in range(256):
        (repo / f"source-{number:03}.ts").write_text(
            f"export const value{number} = {number};\n", encoding="utf-8"
        )
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=repo, check=True)
    real_popen = subprocess.Popen
    starts: list[tuple[str, ...]] = []

    def counted_popen(*args, **kwargs):
        starts.append(tuple(args[0]))
        return real_popen(*args, **kwargs)

    with patch.object(inventory_module.subprocess, "Popen", side_effect=counted_popen):
        result = inventory_sources("vscode", repo, DEFAULT_SOURCE_RULES)

    assert len(result.tracked_regular_paths) == 256
    assert len(starts) == 12
    assert [command[:3] for command in starts].count(
        ("git", "cat-file", "--batch")
    ) == 1
    assert all("hash-object" not in command for command in starts)


def test_source_inventory_is_exactly_bound_to_git_modes_objects_and_bytes(
    tmp_path: Path,
):
    import hashlib
    import subprocess
    from dataclasses import asdict

    from benchmarks.codegraph_compare.integrity import _sha256
    from benchmarks.codegraph_compare.setup_qualification import (
        DEFAULT_SOURCE_RULES,
        inventory_sources,
    )

    repo = tmp_path / "repo"
    commit = _qualification_git_repo(repo)
    raw_records = subprocess.run(
        ["git", "ls-files", "-z", "--stage"],
        cwd=repo,
        capture_output=True,
        check=True,
    ).stdout
    records = []
    for raw in raw_records.split(b"\0"):
        if raw:
            metadata, encoded = raw.split(b"\t", 1)
            mode, object_id, _stage = metadata.decode("ascii").split(" ")
            records.append((encoded.decode(), mode, object_id))
    records.sort()
    regular = tuple(item for item in records if item[1] in {"100644", "100755"})
    file_hashes = [
        (path, mode, object_id, hashlib.sha256((repo / path).read_bytes()).hexdigest())
        for path, mode, object_id in regular
    ]

    root_tree_id = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"],
        cwd=repo,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()
    assert asdict(inventory_sources("vscode", repo, DEFAULT_SOURCE_RULES)) == {
        "repo_id": "vscode",
        "source_rules_hash": DEFAULT_SOURCE_RULES.digest,
        "commit": commit,
        "tracked_regular_paths": ("generated.ts", "main.ts", "notes.md"),
        "tracked_entries": tuple(records),
        "root_tree_id": root_tree_id,
        "tracked_files": tuple(
            (path, mode, object_id, (repo / path).stat().st_size, content_hash)
            for path, mode, object_id, content_hash in file_hashes
        ),
        "eligible_paths": ("main.ts",),
        "prefilter_exclusions": (
            ("deps/submodule", "gitlink"),
            ("generated.ts", "generated"),
            ("linked.ts", "symlink"),
            ("notes.md", "extension"),
        ),
        "tracked_inventory_hash": _sha256(records),
        "eligible_paths_hash": _sha256(["main.ts"]),
        "repo_fingerprint": _sha256(
            {"commit": commit, "inventory": records, "files": file_hashes}
        ),
    }


def test_source_archive_ceiling_matches_tarfile_record_algorithm(tmp_path: Path):
    # PR #1249 review 3744561292: authority 的上限必须与 tarfile 完全一致。
    import io
    import tarfile

    from benchmarks.codegraph_compare.audit_authority_storage import (
        _source_archive_ceiling,
    )
    from benchmarks.codegraph_compare.receipt_v3 import canonical_json_bytes

    sizes = (1, 513, 8193)
    records = []
    archive_path = tmp_path / "source.tar"
    with tarfile.open(archive_path, "w", format=tarfile.USTAR_FORMAT) as archive:
        for number, size in enumerate(sizes):
            payload = bytes([number + 1]) * size
            name = f"file-{number}"
            info = tarfile.TarInfo(name)
            info.size = size
            archive.addfile(info, io.BytesIO(payload))
            records.append(
                [
                    name,
                    "100644",
                    "a" * 40,
                    size,
                    hashlib.sha256(payload).hexdigest(),
                ]
            )
    inventory = canonical_json_bytes({"eligibility": {"tracked_files": records}})

    assert _source_archive_ceiling(inventory) == archive_path.stat().st_size


_mark_posix_qualification_section_tests()
