"""Temporary Git plumbing for payloads bound to a captured source epoch."""

from __future__ import annotations

import os
import shutil
import subprocess  # nosec B404
import tempfile
import threading
from collections.abc import Mapping
from typing import BinaryIO

from .source_oracle import SafePath, SourceOracleError, _remaining
from .source_oracle_git import GitEpoch, git_output


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
            ).rstrip(b"\r\n")
            env["GIT_ALTERNATE_OBJECT_DIRECTORIES"] = os.fsdecode(objects)
        return env

    def run(
        self,
        args: list[str],
        *,
        limit: int = 64 * 1024 * 1024,
        input_: bytes | None = None,
    ) -> bytes:
        if limit < 0:
            raise SourceOracleError("DIFF_SNAPSHOT_CAPACITY")
        try:
            proc = subprocess.Popen(  # nosec B603
                ["git", *args],
                cwd=self.root,
                env=self._env(),
                stdin=subprocess.PIPE if input_ is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR") from exc
        output = bytearray()
        errors = bytearray()
        failures: list[str] = []

        def drain(stream: BinaryIO | None, target: bytearray, cap: int) -> None:
            if stream is None:
                failures.append("DIFF_SNAPSHOT_GIT_ERROR")
                return
            try:
                while chunk := stream.read(64 * 1024):
                    if len(target) + len(chunk) > cap:
                        failures.append("DIFF_SNAPSHOT_CAPACITY")
                        proc.kill()
                        return
                    target.extend(chunk)
            except OSError:
                failures.append("DIFF_SNAPSHOT_GIT_ERROR")

        def feed() -> None:
            if proc.stdin is None or input_ is None:
                return
            try:
                proc.stdin.write(input_)
                proc.stdin.close()
            except (BrokenPipeError, OSError):
                pass

        threads = [
            threading.Thread(
                target=drain, args=(proc.stdout, output, limit), daemon=True
            ),
            threading.Thread(
                target=drain, args=(proc.stderr, errors, 64 * 1024), daemon=True
            ),
        ]
        if input_ is not None:
            threads.append(threading.Thread(target=feed, daemon=True))
        for thread in threads:
            thread.start()
        try:
            proc.wait(timeout=_remaining(self.deadline))
            for thread in threads:
                thread.join(timeout=_remaining(self.deadline))
        except subprocess.TimeoutExpired as exc:
            proc.kill()
            proc.wait()
            raise SourceOracleError("DIFF_SNAPSHOT_TIMEOUT") from exc
        if any(thread.is_alive() for thread in threads):
            proc.kill()
            raise SourceOracleError("DIFF_SNAPSHOT_TIMEOUT")
        if failures:
            raise SourceOracleError(failures[0])
        if proc.returncode != 0:
            raise SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")
        return bytes(output)

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
