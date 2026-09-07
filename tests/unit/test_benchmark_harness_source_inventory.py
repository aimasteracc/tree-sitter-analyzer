"""Issue #1376：source inventory 行为组，已有 UTF-8 编码仅转为同值 keyword。"""

from __future__ import annotations

import hashlib
import json
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
    # PR #1247: a fresh qualification checkout must contain no untracked inputs.
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
    # PR #1247: checkout cleanliness is snapshotted both before and after inventory.
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
    # PR #1247: status porcelain hides assume-unchanged worktree divergence.
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
    # PR #1247: skip-worktree entries cannot attest bytes consumed by a build.
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
    # PR #1247: build input bytes are verified independently of Git status hints.
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
    # PR #1247: a subdirectory-scoped ls-files result cannot label the full commit.
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
    # PR #1247: generated markers apply to the complete pinned blob.
    import io

    import benchmarks.codegraph_compare.setup_qualification_inventory as inventory_module

    payload = b"x" * 5000 + b"DO NOT EDIT"
    digest = hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()
    output = f"{digest} blob {len(payload)}".encode() + b"\0" + payload + b"\0"

    assert inventory_module._stream_blob(
        io.BytesIO(output), "generated.ts", digest, 0, (b"DO NOT EDIT",)
    ) == (hashlib.sha256(payload).hexdigest(), True, len(payload))


def test_git_blob_generated_marker_is_detected_across_chunk_boundary():
    # PR #1247: rolling overlap binds markers straddling stream chunks.
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
    # PR #1247: batch framing must fail closed rather than shift into the next blob.
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
    # PR #1247: process count must not scale with tracked regular blobs.
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
    # PR #1249 review 3744561292: the authority ceiling mirrors tarfile exactly.
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


def test_seven_repo_inventory_lists_exactly_the_canonical_repositories() -> None:
    from benchmarks.codegraph_compare.setup_qualification_inventory import (
        load_seven_repo_inventory,
    )
    from benchmarks.codegraph_compare.setup_qualification_plan import REPOSITORIES

    payload = load_seven_repo_inventory()
    assert [entry["repo_id"] for entry in payload["repositories"]] == list(REPOSITORIES)


def test_seven_repo_inventory_commit_pins_match_repos_yaml() -> None:
    import yaml

    from benchmarks.codegraph_compare.run import REPOS_YAML
    from benchmarks.codegraph_compare.setup_qualification_inventory import (
        load_seven_repo_inventory,
    )

    payload = load_seven_repo_inventory()
    registry = yaml.safe_load(REPOS_YAML.read_text(encoding="utf-8"))
    # Codex P2 (#1260): compare every shared field across the exact
    # seven-entry mapping, so name/language/url/approx_files drift (or a
    # removed repository) turns the parity test red, not just commit pins.
    pinned = {
        entry["repo_id"]: {
            "commit": entry["commit"],
            "name": entry["name"],
            "language": entry["language"],
            "url": entry["url"],
            "approx_files": entry["approx_files"],
        }
        for entry in payload["repositories"]
    }
    assert len(pinned) == 7
    yaml_repos = registry["repos"]
    assert len(yaml_repos) == 7
    for repo in yaml_repos:
        expected = {
            "commit": repo["commit"],
            "name": repo["name"],
            "language": repo["language"],
            "url": repo["url"],
            "approx_files": repo["approx_files"],
        }
        assert pinned[repo["id"]] == expected, repo["id"]


def test_seven_repo_inventory_extensions_match_default_source_rules() -> None:
    from benchmarks.codegraph_compare.setup_qualification_inventory import (
        load_seven_repo_inventory,
    )
    from benchmarks.codegraph_compare.setup_qualification_plan import (
        DEFAULT_SOURCE_RULES,
    )

    payload = load_seven_repo_inventory()
    for entry in payload["repositories"]:
        assert entry["source_extensions"] == list(
            DEFAULT_SOURCE_RULES.extensions(entry["repo_id"])
        ), entry["repo_id"]


def test_seven_repo_inventory_rejects_bad_commit_pin() -> None:
    from benchmarks.codegraph_compare.setup_qualification_inventory import (
        SEVEN_REPO_INVENTORY_PATH,
        _validate_inventory_entry,
    )

    payload = json.loads(SEVEN_REPO_INVENTORY_PATH.read_text(encoding="utf-8"))
    entry = dict(payload["repositories"][0])
    entry["commit"] = entry["commit"][:-1]  # 39 hex: bad pin
    with pytest.raises(ValueError, match="bad commit pin"):
        _validate_inventory_entry(entry, 0)


def test_seven_repo_inventory_rejects_unsorted_extensions() -> None:
    from benchmarks.codegraph_compare.setup_qualification_inventory import (
        SEVEN_REPO_INVENTORY_PATH,
        _validate_inventory_entry,
    )

    payload = json.loads(SEVEN_REPO_INVENTORY_PATH.read_text(encoding="utf-8"))
    entry = dict(payload["repositories"][0])
    entry["source_extensions"] = [".tsx", ".ts"]
    with pytest.raises(ValueError, match="not sorted unique"):
        _validate_inventory_entry(entry, 0)


def test_seven_repo_inventory_rejects_duplicate_repo_id(tmp_path: Path) -> None:
    from unittest.mock import patch

    from benchmarks.codegraph_compare.setup_qualification_inventory import (
        SEVEN_REPO_INVENTORY_PATH,
        load_seven_repo_inventory,
    )

    payload = json.loads(SEVEN_REPO_INVENTORY_PATH.read_text(encoding="utf-8"))
    payload["repositories"][6] = dict(payload["repositories"][0])
    broken = tmp_path / "broken-inventory.json"
    broken.write_text(json.dumps(payload), encoding="utf-8")
    with patch(
        "benchmarks.codegraph_compare.setup_qualification_inventory"
        ".SEVEN_REPO_INVENTORY_PATH",
        broken,
    ):
        with pytest.raises(ValueError, match="duplicates repo_id"):
            load_seven_repo_inventory()


def test_seven_repo_inventory_schema_rejects_wrong_repository_count(
    tmp_path: Path,
) -> None:
    from unittest.mock import patch

    from benchmarks.codegraph_compare.setup_qualification_inventory import (
        SEVEN_REPO_INVENTORY_PATH,
        load_seven_repo_inventory,
    )

    payload = json.loads(SEVEN_REPO_INVENTORY_PATH.read_text(encoding="utf-8"))
    del payload["repositories"][-1]
    broken = tmp_path / "broken-inventory.json"
    broken.write_text(json.dumps(payload), encoding="utf-8")
    with patch(
        "benchmarks.codegraph_compare.setup_qualification_inventory"
        ".SEVEN_REPO_INVENTORY_PATH",
        broken,
    ):
        with pytest.raises(ValueError, match="violates its schema"):
            load_seven_repo_inventory()


def test_seven_repo_inventory_rejects_duplicate_json_members(
    tmp_path: Path,
) -> None:
    # Codex P2 (#1260): a duplicated member (e.g. two "commit" keys) must
    # be rejected up front — json.loads would silently keep the last value
    # and the schema would validate only the collapsed object.
    from unittest.mock import patch

    from benchmarks.codegraph_compare.setup_qualification_inventory import (
        SEVEN_REPO_INVENTORY_PATH,
        load_seven_repo_inventory,
    )

    payload = json.loads(SEVEN_REPO_INVENTORY_PATH.read_text(encoding="utf-8"))
    first = payload["repositories"][0]
    duplicated = (
        "{"
        + '"repo_id": "gin", "commit": "'
        + first["commit"]
        + '", "commit": "'
        + first["commit"]
        + '", "name": "Gin", "language": "Go", "url": "https://github.com/gin-gonic/gin", "approx_files": 200, "source_extensions": [".go"]'
        + "}"
    )
    broken = tmp_path / "broken-duplicate.json"
    broken.write_text(
        '{"schema_version": 1, "repositories": ['
        + duplicated
        + ","
        + json.dumps(payload["repositories"][1:])[1:]
        + "}",
        encoding="utf-8",
    )
    with patch(
        "benchmarks.codegraph_compare.setup_qualification_inventory"
        ".SEVEN_REPO_INVENTORY_PATH",
        broken,
    ):
        with pytest.raises(ValueError, match="not strict JSON"):
            load_seven_repo_inventory()


_mark_posix_qualification_section_tests()
