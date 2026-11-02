"""``nav callers`` latency through a real MCP stdio server (RFC-0042 V2 measures).

Usage::

    python benchmarks/resident/mcp_latency.py --repo PATH [--sample sample.json]
        [--targets 10] [--rounds 2] [--settle 0] [--idle 40] [--inproc]
        [--env TSA_RESIDENT=off ...] [--out out.json]

One fresh server process (``python -m tree_sitter_analyzer.mcp.server``, the
same interpreter and ``PYTHONPATH`` as this script) per run:

1. ``initialize`` + ``notifications/initialized`` + ``tools/list`` (timed);
2. sleep ``--settle`` seconds (0 = ask while any background load still runs);
3. the **first query**: ``nav action=callers`` on the first target, qualified;
4. **warm**: ``--rounds`` rounds over every target, qualified and bare;
5. **after idle**: sleep ``--idle`` seconds (past the 35 s snapshot TTL), ask
   the first target again, then once more (``after_idle_warm``).

``--inproc`` then answers the same warm queries in this process through
``CodeGraphCallersTool.execute`` (one untimed round first), so the report can
state the MCP-level share (facade, TOON/JSON encode, stdio transport) as
``mcp_warm_median - inproc_warm_median``.

Every record carries ``suspended`` (wall and monotonic clocks drifted more than
3 s): drop such runs. ``--env`` sets variables for the server only, e.g. the
``TSA_RESIDENT`` switch of RFC-0042.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import SuspendClock, load_targets, summary_ms, write_json  # noqa: E402


class StdioClient:
    """Newline-delimited JSON-RPC 2.0 client for one MCP server process."""

    def __init__(
        self, repo: str, env: dict[str, str], stderr_path: str, cwd: str | None = None
    ) -> None:
        self._id = 0
        self._stderr = open(stderr_path, "ab")  # noqa: SIM115 — closed in close()
        self.proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer.mcp.server",
                "--project-root",
                repo,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr,
            # ``cwd`` outside the repo when the repo shadows a server dependency
            # (``python -m`` puts the working directory first on ``sys.path``).
            cwd=cwd or repo,
            env=env,
        )
        self._lines: list[bytes] = []
        self._cv = threading.Condition()
        threading.Thread(target=self._read, daemon=True).start()

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

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def request(
        self, method: str, params: dict[str, Any], timeout: float = 600.0
    ) -> dict[str, Any]:
        self._id += 1
        rid = self._id
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while True:
            with self._cv:
                while not self._lines:
                    left = deadline - time.monotonic()
                    if left <= 0:
                        raise TimeoutError(method)
                    self._cv.wait(left)
                line = self._lines.pop(0)
            if line == b"":
                raise RuntimeError("server exited")
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if message.get("id") == rid:
                return message.get("result") or {"__rpc_error__": message.get("error")}

    def call(
        self, tool: str, arguments: dict[str, Any]
    ) -> tuple[float, int, dict[str, Any]]:
        """``(seconds, response bytes, parsed payload)`` of one ``tools/call``."""
        t0 = time.perf_counter()
        result = self.request("tools/call", {"name": tool, "arguments": arguments})
        seconds = time.perf_counter() - t0
        text = "".join(
            c.get("text", "")
            for c in result.get("content", [])
            if c.get("type") == "text"
        )
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {"__text__": text[:200]}
        return seconds, len(text.encode("utf-8")), payload

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
            self.proc.wait(timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            self.proc.kill()
        self._stderr.close()


def nav_args(name: str, file: str) -> dict[str, Any]:
    return {
        "action": "callers",
        "function_name": name,
        "file_path": file,
        "include_bodies": False,
        "limit": 5000,
    }


def answer_kind(payload: dict[str, Any]) -> str:
    """``review`` when the RFC-0040 review gates ran (more than the 5 edge checks
    recorded), else ``edge_only``; the in-process split of ``prof_callers.py``."""
    checks = payload.get("completeness_checks") or {}
    checked = checks.get("checked") if isinstance(checks, dict) else None
    if not isinstance(checked, int):
        return "unclassified"
    return "review" if checked > 5 else "edge_only"


def server_env(pairs: list[str]) -> dict[str, str]:
    env = dict(os.environ)
    for pair in pairs:
        key, _, value = pair.partition("=")
        env[key] = value
    return env


def run_server(
    args: argparse.Namespace, targets: list[tuple[str, str, str]]
) -> dict[str, Any]:
    clock = SuspendClock()
    stderr_path = args.stderr or os.path.join(
        tempfile.gettempdir(), "tsa-mcp-latency.stderr.log"
    )
    started = time.perf_counter()
    client = StdioClient(args.repo, server_env(args.env), stderr_path)
    rec: dict[str, Any] = {
        "repo": Path(args.repo).name,
        "env": args.env,
        "settle_s": args.settle,
    }
    try:
        client.request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "tsa-resident-bench", "version": "1"},
            },
        )
        client.notify("notifications/initialized", {})
        rec["initialize_ms"] = round((time.perf_counter() - started) * 1000, 1)
        t0 = time.perf_counter()
        client.request("tools/list", {})
        rec["tools_list_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        if args.settle:
            time.sleep(args.settle)
        qual, _bare, file = targets[0]
        seconds, size, payload = client.call("nav", nav_args(qual, file))
        rec["first_query_ms"] = round(seconds * 1000, 1)
        rec["first_completeness"] = payload.get("completeness")
        warm: list[float] = []
        sizes: list[int] = []
        by_kind: dict[str, list[float]] = {}
        for _ in range(args.rounds):
            for qual_name, bare, target_file in targets:
                for name in (qual_name, bare):
                    seconds, size, answer = client.call(
                        "nav", nav_args(name, target_file)
                    )
                    warm.append(seconds)
                    sizes.append(size)
                    by_kind.setdefault(answer_kind(answer), []).append(seconds)
        rec["warm"] = summary_ms(warm)
        rec["warm_by_kind"] = {k: summary_ms(v) for k, v in sorted(by_kind.items())}
        rec["warm_median_bytes"] = sorted(sizes)[len(sizes) // 2] if sizes else 0
        if args.idle:
            time.sleep(args.idle)
            for label in ("after_idle", "after_idle_warm"):
                seconds, _size, _payload = client.call("nav", nav_args(qual, file))
                rec[f"{label}_ms"] = round(seconds * 1000, 1)
    finally:
        client.close()
    rec["suspended"] = clock.suspended()
    return rec


async def run_inproc(
    args: argparse.Namespace, targets: list[tuple[str, str, str]]
) -> dict[str, Any]:
    from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

    tool = CodeGraphCallersTool(args.repo)

    async def ask(name: str, file: str) -> None:
        await tool.execute(
            {
                "function_name": name,
                "file_path": file,
                "include_bodies": False,
                "limit": 5000,
            }
        )

    for qual, bare, file in targets:
        for name in (qual, bare):
            await ask(name, file)
    warm: list[float] = []
    for _ in range(args.rounds):
        for qual, bare, file in targets:
            for name in (qual, bare):
                t0 = time.perf_counter()
                await ask(name, file)
                warm.append(time.perf_counter() - t0)
    return summary_ms(warm)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--sample")
    parser.add_argument("--targets", type=int, default=10)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--settle", type=float, default=0.0)
    parser.add_argument("--idle", type=float, default=40.0)
    parser.add_argument("--inproc", action="store_true")
    parser.add_argument("--env", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--stderr", help="server stderr log (default: temp dir)")
    parser.add_argument("--out")
    args = parser.parse_args()
    args.repo = os.path.abspath(args.repo)
    targets = load_targets(args.sample, args.repo, args.targets)
    rec = run_server(args, targets)
    if args.inproc:
        rec["inproc_warm"] = asyncio.run(run_inproc(args, targets))
        mcp_median = rec["warm"].get("median_ms")
        inproc_median = rec["inproc_warm"].get("median_ms")
        if mcp_median and inproc_median:
            rec["mcp_layer_median_ms"] = round(mcp_median - inproc_median, 1)
            rec["mcp_layer_share"] = round((mcp_median - inproc_median) / mcp_median, 3)
    write_json(args.out, rec)


if __name__ == "__main__":
    main()
