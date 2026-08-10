"""Temporary Git plumbing for payloads bound to a captured source epoch."""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
from collections.abc import Mapping

from .frozen_git_index import safe_external_temp_parent
from .git_subprocess import run_git_bounded
from .source_epoch import capture_source_epoch
from .source_oracle import (
    SafePath,
    SourceOracleError,
    WorkspaceManifestEntry,
    _remaining,
)
from .source_oracle_git import (
    GitEpoch,
    _strip_one_record_terminator,
    git_output,
)
from .temp_cleanup import cleanup_path


def _lstat(path: str) -> os.stat_result:
    """Module-local seam for temporary-store accounting tests."""
    return os.lstat(path)


def _quote_alternate_object_directory(raw: bytes) -> str:
    """Encode one alternate as one Git C-quoted list element."""
    escaped = bytearray(b'"')
    for value in raw:
        if value == 0x22:
            escaped.extend(b'\\"')
        elif value == 0x5C:
            escaped.extend(b"\\\\")
        elif value == 0x0A:
            escaped.extend(b"\\n")
        elif value == 0x0D:
            escaped.extend(b"\\r")
        elif value == 0x09:
            escaped.extend(b"\\t")
        elif 0x20 <= value < 0x7F:
            escaped.append(value)
        else:
            escaped.extend(f"\\{value:03o}".encode("ascii"))
    escaped.extend(b'"')
    return escaped.decode("ascii")


class FrozenGitEnvironment:
    """Normal temporary index/object store; never writes inside the project."""

    def __init__(
        self,
        root: str,
        epoch: GitEpoch,
        deadline: float,
        storage_byte_limit: int = 64 * 1024 * 1024,
        storage_file_limit: int = 200_000,
    ) -> None:
        self.root = root
        self.epoch = epoch
        self.deadline = deadline
        self._directory: str | None = None
        self.index_path = ""
        self.object_directory: str | None = None
        self.storage_byte_limit = storage_byte_limit
        self.storage_file_limit = storage_file_limit
        self.temporary_bytes = 0
        self.temporary_files = 0

    def __enter__(self) -> FrozenGitEnvironment:
        temp_parent = safe_external_temp_parent(self.root)
        self._directory = tempfile.mkdtemp(prefix="tsa-frozen-git-", dir=temp_parent)
        try:
            real_project_root = os.path.realpath(self.root)
            real_directory = os.path.realpath(self._directory)
            try:
                inside_project = (
                    os.path.commonpath((real_project_root, real_directory))
                    == real_project_root
                )
            except ValueError:
                inside_project = False
            if inside_project:
                raise SourceOracleError("DIFF_SNAPSHOT_UNSAFE_TEMP")
            os.chmod(self._directory, 0o700)
            self.index_path = os.path.join(self._directory, "index")
            self.object_directory = os.path.join(self._directory, "objects")
            os.mkdir(self.object_directory, 0o700)
            for _path, header in self.epoch.index_entries:
                if header.split(b" ")[-1] != b"0":
                    raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
            if self.epoch.index_bytes:
                with open(self.index_path, "xb") as stream:
                    os.fchmod(stream.fileno(), 0o600)
                    stream.write(self.epoch.index_bytes)
            else:
                self.run(["read-tree", "--empty"], limit=4096)
                os.chmod(self.index_path, 0o600)
            return self
        except Exception:
            self.__exit__()
            raise

    def __exit__(self, *_: object) -> None:
        directory = self._directory
        self._directory = None
        if directory is not None:
            cleanup_path(directory, directory=True)

    def _env(self) -> dict[str, str]:
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.upper().startswith("GIT_")
        }
        env["GIT_OPTIONAL_LOCKS"] = "0"
        env["GIT_ATTR_NOSYSTEM"] = "1"
        env["GIT_INDEX_FILE"] = self.index_path
        if self.object_directory is not None:
            env["GIT_OBJECT_DIRECTORY"] = self.object_directory
            objects = git_output(
                self.root,
                ["rev-parse", "--path-format=absolute", "--git-path", "objects"],
                deadline=self.deadline,
                limit=64 * 1024,
            )
            objects = _strip_one_record_terminator(objects)
            env["GIT_ALTERNATE_OBJECT_DIRECTORIES"] = _quote_alternate_object_directory(
                objects
            )
        return env

    def run(
        self,
        args: list[str],
        *,
        limit: int = 64 * 1024 * 1024,
        input_: bytes | None = None,
        file_size_limit: int | None = None,
    ) -> bytes:
        return run_git_bounded(
            self.root,
            args,
            deadline=self.deadline,
            limit=limit,
            env=self._env(),
            input_=input_,
            file_size_limit=file_size_limit,
        )

    def verify_source_epoch(self) -> None:
        """Reject transient config/attribute changes before hashes or diffs run."""
        expected = self.epoch.source_epoch
        if expected is None:
            return
        current = capture_source_epoch(
            self.root,
            self.epoch.index_bytes,
            tuple(
                sorted(set(self.epoch.tracked_paths) | set(self.epoch.untracked_paths))
            ),
            deadline=self.deadline,
            object_format=self.epoch.object_format,
        )
        if current != expected:
            raise SourceOracleError("DIFF_SNAPSHOT_SOURCE_CHANGED")

    def _refresh_object_usage(self) -> None:
        directory = self.object_directory
        if directory is None:
            return
        total = 0
        files = 0
        try:
            for base, dirs, names in os.walk(directory, followlinks=False):
                for name in dirs + names:
                    info = _lstat(os.path.join(base, name))
                    if stat.S_ISLNK(info.st_mode):
                        raise SourceOracleError("DIFF_SNAPSHOT_UNSAFE_TEMP")
                    files += 1
                    total += info.st_size
        except SourceOracleError:
            raise
        except OSError as exc:
            raise SourceOracleError("DIFF_SNAPSHOT_CAPTURE_ERROR") from exc
        self.temporary_bytes = total
        self.temporary_files = files
        if total > self.storage_byte_limit or files > self.storage_file_limit:
            raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")

    def apply_workspace(
        self,
        paths: Mapping[bytes, SafePath],
        manifest: Mapping[str, WorkspaceManifestEntry] | None = None,
    ) -> dict[bytes, bytes]:
        """Clone the base index, then write Git-cleaned frozen leaves."""
        if self._directory is None:
            raise SourceOracleError("DIFF_SNAPSHOT_CAPTURE_ERROR")
        workspace_index = os.path.join(self._directory, "workspace-index")
        shutil.copyfile(self.index_path, workspace_index)
        os.chmod(workspace_index, 0o600)
        self.index_path = workspace_index
        result: dict[bytes, bytes] = {}
        for raw, safe in paths.items():
            _remaining(self.deadline)
            if safe.kind == "missing":
                self.run(["update-index", "--force-remove", "--", os.fsdecode(raw)])
                continue
            if safe.kind == "directory":
                entry = dict(self.epoch.workspace_gitlinks).get(raw)
                if entry is None:
                    original = self.epoch.index_map().get(raw)
                    if original is None or original.startswith(b"160000 "):
                        raise SourceOracleError("DIFF_SNAPSHOT_SPECIAL_FILE")
                    # A tracked regular leaf replaced by a directory is a
                    # deletion; its untracked descendants remain separate.
                    self.run(["update-index", "--force-remove", "--", os.fsdecode(raw)])
                    continue
                if not entry.startswith(b"160000 "):
                    raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
                mode, oid, _stage = entry.split(b" ")
                self.run(
                    [
                        "update-index",
                        "--add",
                        "--cacheinfo",
                        mode.decode(),
                        oid.decode(),
                        os.fsdecode(raw),
                    ]
                )
                result[raw] = entry
                continue
            if safe.kind not in ("file", "symlink") or safe.data is None:
                raise SourceOracleError("DIFF_SNAPSHOT_SPECIAL_FILE")
            existing = self.epoch.index_map().get(raw)
            existing_mode = existing.split(b" ", 1)[0] if existing is not None else None
            emulated_symlink = (
                not self.epoch.core_symlinks
                and safe.kind == "file"
                and existing_mode == b"120000"
            )
            if safe.kind == "symlink" or emulated_symlink:
                mode = b"120000"
            elif not self.epoch.core_filemode:
                mode = existing_mode or b"100644"
                if mode not in (b"100644", b"100755"):
                    mode = b"100644"
            else:
                try:
                    stat_mode = int(safe.metadata[-1].split(b",")[2])
                except (IndexError, ValueError) as exc:
                    raise SourceOracleError("DIFF_SNAPSHOT_UNSAFE_PATH") from exc
                mode = b"100755" if stat_mode & 0o111 else b"100644"
            hash_args = ["hash-object", "-w", "--stdin"]
            if safe.kind == "file" and not emulated_symlink:
                # ``--path`` applies core.autocrlf, eol, and clean filters using
                # the exact raw repository path.  argv execution is shell-free.
                hash_args.insert(2, "--path=" + os.fsdecode(raw))
            remaining_storage = self.storage_byte_limit - self.temporary_bytes
            oid = self.run(
                hash_args,
                limit=4096,
                input_=safe.data,
                file_size_limit=remaining_storage,
            ).strip()
            self._refresh_object_usage()
            if not oid:
                raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
            if safe.kind == "file":
                expected = (manifest or {}).get(os.fsdecode(raw))
                if expected is None or expected.filtered_oid != oid:
                    raise SourceOracleError("DIFF_SNAPSHOT_SOURCE_CHANGED")
            self.run(
                [
                    "update-index",
                    "--add",
                    "--cacheinfo",
                    mode.decode(),
                    oid.decode(),
                    os.fsdecode(raw),
                ]
            )
            result[raw] = mode + b" " + oid + b" 0"
        return result
