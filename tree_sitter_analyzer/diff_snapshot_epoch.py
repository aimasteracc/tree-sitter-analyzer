"""Temporary Git plumbing for payloads bound to a captured source epoch."""
# fmt: off

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
import threading
from collections.abc import Mapping
from dataclasses import replace

from .frozen_git_index import safe_external_temp_parent
from .frozen_git_settings import (
    ConfigEntry,
    FrozenGitSettings,
    FrozenSettingFile,
    config_fingerprint,
    parse_effective_config,
    reject_active_filters,
    serialize_config,
)
from .git_subprocess import run_git_bounded
from .private_temp_materialization import copy_private, write_private
from .source_oracle import (
    SafePath,
    SourceOracleError,
    WorkspaceManifestEntry,
    _remaining,
)
from .source_oracle_git import GitEpoch
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
        self.git_dir = ""
        self.worktree_path = ""
        self._materialized_config: tuple[ConfigEntry, ...] = ()
        self._base_temporary_bytes = 0
        self._base_temporary_files = 0
        self._storage_lock = threading.RLock()
        self.storage_byte_limit = storage_byte_limit
        self.storage_file_limit = storage_file_limit
        self.temporary_bytes = 0
        self.temporary_files = 0

    def _settings(self) -> FrozenGitSettings:
        settings = self.epoch.git_settings
        if isinstance(settings, FrozenGitSettings):
            return settings
        # Compatibility for direct unit construction; production epochs always
        # carry settings captured by the first source-oracle pass.
        entries = (
            ConfigEntry(b"core.repositoryformatversion", b"0"),
            ConfigEntry(b"core.bare", b"false"),
        )
        info = FrozenSettingFile(b"info/attributes", "missing", None)
        objects = os.fsencode(
            os.path.abspath(os.path.join(self.root, ".git", "objects"))
        )
        return FrozenGitSettings(entries, None, None, info, (), objects, b"")

    def __enter__(self) -> FrozenGitEnvironment:
        settings = self._settings()
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
            self.git_dir = os.path.join(self._directory, "git-dir")
            self.worktree_path = os.path.join(self._directory, "worktree")
            self.object_directory = os.path.join(self.git_dir, "objects")
            for path in (
                self.git_dir,
                self.worktree_path,
                self.object_directory,
                os.path.join(self.git_dir, "info"),
                os.path.join(self.git_dir, "refs"),
            ):
                os.mkdir(path, 0o700)
                self._account_temporary(0, 1)
            self.index_path = os.path.join(self._directory, "index")
            core_shadow = os.path.join(self.git_dir, "frozen-core-attributes")
            config, materialized = serialize_config(
                settings.config_entries,
                os.fsencode(core_shadow) if settings.core_attributes_path else None,
            )
            self._materialized_config = materialized
            self._write_private(os.path.join(self.git_dir, "config"), config)
            self._write_private(
                os.path.join(self.git_dir, "HEAD"), b"ref: refs/heads/frozen\n"
            )
            if settings.core_attributes is not None:
                self._materialize_regular(settings.core_attributes, core_shadow)
            self._materialize_regular(
                settings.info_attributes,
                os.path.join(self.git_dir, "info", "attributes"),
            )
            for item in settings.worktree_attributes:
                destination = os.path.join(self.worktree_path, os.fsdecode(item.path))
                if item.kind == "file":
                    self._ensure_worktree_parent(destination)
                    self._write_private(destination, item.data or b"")
                elif item.kind not in ("missing", "symlink"):
                    raise SourceOracleError("DIFF_SNAPSHOT_SPECIAL_FILE")
            for _path, header in self.epoch.index_entries:
                if header.split(b" ")[-1] != b"0":
                    raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
            if self.epoch.index_bytes:
                self._write_private(self.index_path, self.epoch.index_bytes)
            else:
                header = b"DIRC" + (2).to_bytes(4, "big") + (0).to_bytes(4, "big")
                checksum = hashlib.new(self.epoch.object_format, header).digest()
                self._write_private(self.index_path, header + checksum)
            return self
        except Exception:
            self.__exit__()
            raise

    def _reserve_temporary(self, size: int, files: int) -> None:
        with self._storage_lock:
            next_bytes = self.temporary_bytes + size
            next_files = self.temporary_files + files
            if (
                next_bytes > self.storage_byte_limit
                or next_files > self.storage_file_limit
            ):
                raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
            self._base_temporary_bytes += size
            self._base_temporary_files += files
            self.temporary_bytes = next_bytes
            self.temporary_files = next_files

    def _rollback_temporary(self, size: int, files: int) -> None:
        with self._storage_lock:
            self._base_temporary_bytes -= size
            self._base_temporary_files -= files
            self.temporary_bytes -= size
            self.temporary_files -= files

    def _account_temporary(self, size: int, files: int) -> None:
        self._reserve_temporary(size, files)

    def _ensure_worktree_parent(self, destination: str) -> None:
        parent = os.path.dirname(destination)
        try:
            if os.path.commonpath((self.worktree_path, parent)) != self.worktree_path:
                raise SourceOracleError("DIFF_SNAPSHOT_UNSAFE_TEMP")
            relative = os.path.relpath(parent, self.worktree_path)
            current = self.worktree_path
            for part in () if relative == "." else relative.split(os.sep):
                current = os.path.join(current, part)
                try:
                    os.mkdir(current, 0o700)
                except FileExistsError:
                    continue
                self._account_temporary(0, 1)
        except SourceOracleError:
            raise
        except OSError as exc:
            raise SourceOracleError("DIFF_SNAPSHOT_CAPTURE_ERROR") from exc
    def _write_private(self, path: str, data: bytes) -> None:
        write_private(path, data, self._reserve_temporary, self._rollback_temporary)
    def _copy_private(self, source: str, destination: str) -> None:
        copy_private(
            source,
            destination,
            self._reserve_temporary,
            self._rollback_temporary,
        )
    def _materialize_regular(self, item: object, destination: str) -> None:
        kind = getattr(item, "kind", None)
        data = getattr(item, "data", None)
        if kind == "missing":
            return
        if kind != "file" or not isinstance(data, bytes):
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        self._write_private(destination, data)
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
        env.update(
            {
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_ATTR_NOSYSTEM": "1",
                "GIT_INDEX_FILE": self.index_path,
            }
        )
        if self.object_directory is not None:
            settings = self._settings()
            env.update(
                {
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": os.devnull,
                    "GIT_CONFIG_SYSTEM": os.devnull,
                    "GIT_DIR": self.git_dir,
                    "GIT_WORK_TREE": self.worktree_path,
                    "GIT_OBJECT_DIRECTORY": self.object_directory,
                    "GIT_ALTERNATE_OBJECT_DIRECTORIES": (
                        _quote_alternate_object_directory(settings.object_directory)
                    ),
                }
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
            self.worktree_path,
            args,
            deadline=self.deadline,
            limit=limit,
            env=self._env(),
            input_=input_,
            file_size_limit=file_size_limit,
        )
    def verify_source_epoch(self) -> None:
        """Recompute the pre-oracle fingerprints inside the isolated shadow."""
        expected = self.epoch.source_epoch
        settings = self.epoch.git_settings
        if expected is None:
            return
        if not isinstance(settings, FrozenGitSettings):
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        paths = self.epoch.settings_paths or tuple(
            sorted(set(self.epoch.tracked_paths) | set(self.epoch.untracked_paths))
        )
        path_input = b"".join(path + b"\0" for path in paths)
        if len(path_input) > 16 * 1024 * 1024:
            raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
        filter_paths = tuple(
            sorted(set(self.epoch.dirty_paths) | set(self.epoch.untracked_paths))
        )
        if filter_paths:
            filter_input = b"".join(path + b"\0" for path in filter_paths)
            filter_attributes = self.run(
                ["check-attr", "-z", "filter", "--stdin"],
                limit=16 * 1024 * 1024,
                input_=filter_input,
            )
            reject_active_filters(filter_attributes, filter_paths)
        attributes = self.run(
            ["check-attr", "-z", "--all", "--stdin"],
            limit=16 * 1024 * 1024,
            input_=path_input,
        )
        attribute_hash = hashlib.sha256(b"tsa-attributes-v1\0" + attributes).digest()
        raw_config = self.run(
            ["config", "--null", "--list", "--show-origin", "--includes"],
            limit=16 * 1024 * 1024,
        )
        actual = parse_effective_config(raw_config)
        if actual != self._materialized_config:
            raise SourceOracleError("DIFF_SNAPSHOT_SOURCE_CHANGED")
        restored: list[ConfigEntry] = []
        for actual_entry, captured_entry in zip(
            actual, settings.config_entries, strict=True
        ):
            value = (
                captured_entry.value
                if actual_entry.key.lower() == b"core.attributesfile"
                else actual_entry.value
            )
            restored.append(ConfigEntry(actual_entry.key, value))
        if (
            attribute_hash != expected.attribute_fingerprint
            or config_fingerprint(restored) != expected.config_hash
        ):
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
        self.temporary_bytes = self._base_temporary_bytes + total
        self.temporary_files = self._base_temporary_files + files
        if (
            self.temporary_bytes > self.storage_byte_limit
            or self.temporary_files > self.storage_file_limit
        ):
            raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
    def _refresh_all_usage(self) -> None:
        directory = self._directory
        if directory is None:
            raise SourceOracleError("DIFF_SNAPSHOT_CAPTURE_ERROR")
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
        manifest: dict[str, WorkspaceManifestEntry] | None = None,
    ) -> dict[bytes, bytes]:
        """Clone the base index, then write Git-cleaned frozen leaves."""
        if self._directory is None:
            raise SourceOracleError("DIFF_SNAPSHOT_CAPTURE_ERROR")
        workspace_index = os.path.join(self._directory, "workspace-index")
        self._copy_private(self.index_path, workspace_index)
        self.index_path = workspace_index
        result: dict[bytes, bytes] = {}
        # Remove deletions before additions: an untracked regular/symlink may
        # replace the directory that previously contained a tracked descendant.
        for raw, safe in paths.items():
            if safe.kind == "missing":
                _remaining(self.deadline)
                self.run(["update-index", "--force-remove", "--", os.fsdecode(raw)])
        for raw, safe in paths.items():
            _remaining(self.deadline)
            if safe.kind == "missing":
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
            # A loose object can be slightly larger than its input because of
            # the Git header and zlib framing. Reserve that bounded overhead,
            # plus the fan-out directory and object entry, before Git writes.
            zlib_overhead = ((len(safe.data) + 16_382) // 16_383) * 5 + 128
            object_reservation = len(safe.data) + zlib_overhead
            self._reserve_temporary(object_reservation, 2)
            try:
                oid = self.run(
                    hash_args,
                    limit=4096,
                    input_=safe.data,
                    file_size_limit=object_reservation,
                ).strip()
            finally:
                self._rollback_temporary(object_reservation, 2)
            self._refresh_object_usage()
            if not oid:
                raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
            if safe.kind == "file":
                path = os.fsdecode(raw)
                expected = (manifest or {}).get(path)
                if expected is None or expected.raw_bytes != safe.data:
                    raise SourceOracleError("DIFF_SNAPSHOT_SOURCE_CHANGED")
                if manifest is not None:  # pragma: no branch - production mapping
                    # Keep the published frozen evidence immutable.  The
                    # cleaned identity belongs only to this private manifest
                    # copy and to the reconstructed index below.
                    manifest[path] = replace(expected, filtered_oid=oid)
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
        self._refresh_all_usage()
        return result
# fmt: on
