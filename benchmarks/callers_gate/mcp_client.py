"""A long-lived MCP stdio server per (repo, side), with an isolated environment."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, BinaryIO

BOOT = Path(__file__).with_name("_boot.py")

#: Parent variables passed through unchanged (tool locations, Windows plumbing).
PASS_THROUGH = (
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "WINDIR",
    "COMSPEC",
    "OS",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    "PROGRAMDATA",
    "PROGRAMFILES",
)
#: Fixed variables: part of the env fingerprint (and so of every cache key).
#: ``TSA_EVIDENCE_STORE=off`` disables the query-time disk memos (evidence-memo,
#: index facts, reference vocab, certification timeouts): they are keyed by
#: TSA's ``source_fingerprint`` (path + size + mtime), which two package trees can
#: share, and some live in the index's shared ``.ast-cache``. ``graph-memo`` has
#: no switch; ``index_store.block_query_memos`` disables it per index.
SERVER_ENV_TEMPLATE = {
    "PYTHONUTF8": "1",
    "PYTHONIOENCODING": "utf-8",
    "PYTHONHASHSEED": "0",
    "TSA_EVIDENCE_STORE": "off",
}
#: Per-server private directories (values differ per server; names are fixed).
PRIVATE_DIRS = (
    "TEMP",
    "TMP",
    "HOME",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "XDG_CACHE_HOME",
)


class ServerError(RuntimeError):
    pass


def server_env(pythonpath: Path, private: Path) -> dict[str, str]:
    """A clean environment: no inherited TSA_* / TREE_SITTER_* / PYTHON* settings."""
    env = {name: os.environ[name] for name in PASS_THROUGH if name in os.environ}
    env.update(SERVER_ENV_TEMPLATE)
    env["PYTHONPATH"] = str(pythonpath)
    for name in PRIVATE_DIRS:
        path = private / name.lower()
        path.mkdir(parents=True, exist_ok=True)
        env[name] = str(path)
    return env


class Server:
    def __init__(
        self, python: Path, pkg_parent: Path, root: Path, log: Path, private: Path
    ) -> None:
        log.parent.mkdir(parents=True, exist_ok=True)
        self._log: BinaryIO = open(log, "ab")  # noqa: SIM115 - closed in close()
        self.log_path = log
        pkg_dir = pkg_parent / "tree_sitter_analyzer"
        self.proc = subprocess.Popen(
            [str(python), "-s", "-P", str(BOOT), "server", str(pkg_dir), str(root)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._log,
            cwd=str(root),
            env=server_env(pkg_parent, private),
        )
        self._id = 0
        self._lines: list[bytes] = []
        self._cv = threading.Condition()
        threading.Thread(target=self._read, daemon=True).start()
        self.request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "callers-gate", "version": "1"},
            },
            timeout=600,
        )
        self._send(
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        )

    def _read(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            with self._cv:
                self._lines.append(line)
                self._cv.notify_all()
        with self._cv:
            self._lines.append(b"")
            self._cv.notify_all()

    def _send(self, payload: dict[str, Any]) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
        self.proc.stdin.flush()

    def request(
        self, method: str, params: dict[str, Any], timeout: float = 900
    ) -> dict[str, Any]:
        self._id += 1
        rid = self._id
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while True:
            with self._cv:
                while not self._lines:
                    if time.monotonic() > deadline:
                        raise ServerError(
                            f"{method} timed out after {timeout}s (log {self.log_path})"
                        )
                    self._cv.wait(1)
                line = self._lines.pop(0)
            if line == b"":
                raise ServerError(
                    f"server exited with {self.proc.poll()} (log {self.log_path})"
                )
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == rid:
                if msg.get("error") is not None:
                    return {"__error__": msg["error"]}
                result = msg.get("result")
                return (
                    result if isinstance(result, dict) else {"__error__": "no result"}
                )

    def call(
        self, tool: str, args: dict[str, Any]
    ) -> tuple[dict[str, Any], float, int]:
        started = time.perf_counter()
        res = self.request("tools/call", {"name": tool, "arguments": args})
        seconds = time.perf_counter() - started
        if "__error__" in res:
            return {"__error__": res["__error__"]}, seconds, 0
        raw = "".join(
            c.get("text", "") for c in res.get("content", []) if c.get("type") == "text"
        )
        payload = res.get("structuredContent")
        if payload is None:
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {"__text__": raw[:500]}
        if res.get("isError"):
            payload = {
                "__error__": "isError",
                **(payload if isinstance(payload, dict) else {}),
            }
        return payload, seconds, len(raw.encode("utf-8"))

    def close(self) -> None:
        try:
            if self.proc.stdin is not None:
                self.proc.stdin.close()
            self.proc.wait(timeout=60)
        except Exception:  # noqa: BLE001 - best effort shutdown
            self.proc.kill()
            self.proc.wait(timeout=30)
        finally:
            self._log.close()
