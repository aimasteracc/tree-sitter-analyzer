"""Temporary Git plumbing for payloads bound to a captured source epoch."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Mapping

from .git_subprocess import run_git_bounded
from .source_oracle import (
    SafePath,
    SourceOracleError,
    _remaining,
    canonical_root,
)
from .source_oracle_git import (
    GitEpoch,
    _strip_one_record_terminator,
    git_output,
)


class FrozenGitEnvironment:
    """Normal temporary index/object store; never writes inside the project."""

    def __init__(self, root: str, epoch: GitEpoch, deadline: float) -> None:
        self.root = root
        self.epoch = epoch
        self.deadline = deadline
        self._directory: str | None = None
        self.index_path = ""
        self.object_directory: str | None = None

    def __enter__(self) -> FrozenGitEnvironment:
        self._directory = tempfile.mkdtemp(prefix="tsa-frozen-git-")
        try:
            project_root, _ = canonical_root(self.root)
            real_project_root = os.path.realpath(project_root)
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
            self.run(
                ["hash-object", "-w", "-t", "tree", "--stdin"],
                limit=4096,
                input_=b"",
            )
            self.run(["read-tree", "--empty"], limit=4096)
            os.chmod(self.index_path, 0o600)
            payload = bytearray()
            for path, header in self.epoch.index_entries:
                mode, oid, stage = header.split(b" ")
                if stage != b"0":
                    raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
                payload.extend(mode + b" " + oid + b"\t" + path + b"\0")
            if payload:
                self.run(["update-index", "-z", "--index-info"], input_=bytes(payload))
            return self
        except Exception:
            self.__exit__()
            raise

    def __exit__(self, *_: object) -> None:
        directory = self._directory
        self._directory = None
        if directory is not None:
            shutil.rmtree(directory, ignore_errors=True)

    def _env(self) -> dict[str, str]:
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.upper().startswith("GIT_")
        }
        env["GIT_OPTIONAL_LOCKS"] = "0"
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
            env["GIT_ALTERNATE_OBJECT_DIRECTORIES"] = os.fsdecode(objects)
        return env

    def run(
        self,
        args: list[str],
        *,
        limit: int = 64 * 1024 * 1024,
        input_: bytes | None = None,
    ) -> bytes:
        return run_git_bounded(
            self.root,
            args,
            deadline=self.deadline,
            limit=limit,
            env=self._env(),
            input_=input_,
        )

    def apply_workspace(self, paths: Mapping[bytes, SafePath]) -> dict[bytes, bytes]:
        """Clone the base index, then write frozen leaves into the second index."""
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
                if entry is None or not entry.startswith(b"160000 "):
                    raise SourceOracleError("DIFF_SNAPSHOT_SPECIAL_FILE")
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
            oid = self.run(
                ["hash-object", "-w", "--stdin"],
                limit=4096,
                input_=safe.data,
            ).strip()
            if not oid:
                raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
            if safe.kind == "symlink":
                mode = b"120000"
            else:
                try:
                    stat_mode = int(safe.metadata[-1].split(b",")[2])
                except (IndexError, ValueError) as exc:
                    raise SourceOracleError("DIFF_SNAPSHOT_UNSAFE_PATH") from exc
                mode = b"100755" if stat_mode & 0o111 else b"100644"
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
