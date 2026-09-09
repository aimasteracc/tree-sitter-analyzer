"""重建验证计划后顺序执行；拒绝变化的请求并回收拥有的测试进程。"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, cast

import psutil

from .verification_plan import _CAPTURE, decode_request, digest, pr_identity


def rebuild_request(value: dict[str, Any], root: str) -> list[dict[str, Any]]:
    """调用同一分析编译路径，只收集 argv，不执行返回的命令文本。"""
    from .mcp.tools.utils.change_impact_analysis import (
        ChangeImpactRequest,
        _build_change_impact_result,
    )
    from .mcp.tools.utils.change_impact_git import _get_changed_files
    from .mcp.tools.utils.verification_command import _argv_within_budget
    from .pr_url import fetch_pr_changed_files, parse_pr_url

    if digest(root) != value["root"]:
        raise ValueError("VERIFICATION_PLAN_CHANGED")
    request = value["request"]
    scope = request["scope_paths"]
    if request["mode"] == "pr":
        if pr_identity(root, request["pr_url"]) != value["pr_identity"]:
            raise ValueError("VERIFICATION_PLAN_CHANGED")
        parsed = parse_pr_url(request["pr_url"])
        if parsed is None:
            raise ValueError("VERIFICATION_REQUEST_INVALID")
        changed = fetch_pr_changed_files(parsed)
        if scope:
            changed = [
                path
                for path in changed
                if any(path.startswith(item.rstrip("/")) for item in scope)
            ]
    else:
        changed = _get_changed_files(request["mode"], root, scope)
    if digest(changed) != value["changed"]:
        raise ValueError("VERIFICATION_PLAN_CHANGED")
    captured: dict[str, Any] = {}
    token = _CAPTURE.set(captured)
    try:
        _build_change_impact_result(
            ChangeImpactRequest(
                mode=request["mode"],
                changed_files=changed,
                diff_stat="",
                project_root=root,
                include_tests=request["include_tests"],
                scope_paths=scope,
                resource_profile=request["resource_profile"],
                pr_url=request["pr_url"],
                read_only=True,
                agent_summary_only=True,
            )
        )
    finally:
        _CAPTURE.reset(token)
    steps = captured.get("stages", {}).get(value["stage"], [])
    if not steps or digest(steps) != value["plan"]:
        raise ValueError("VERIFICATION_PLAN_CHANGED")
    if any(not _argv_within_budget(step["argv"]) for step in steps):
        raise ValueError("VERIFICATION_REQUEST_TOO_LARGE")
    if (
        request["mode"] == "pr"
        and pr_identity(root, request["pr_url"]) != value["pr_identity"]
    ):
        raise ValueError("VERIFICATION_PLAN_CHANGED")
    return cast(list[dict[str, Any]], steps)


def _cleanup(
    proc: subprocess.Popen[bytes], owned: dict[int, psutil.Process], token: str
) -> bool:
    """按进程身份与继承标记清理；两次空扫描后才认为测试树已退出。"""
    deadline = time.monotonic() + 2
    empty = 0
    while time.monotonic() < deadline:
        for process in psutil.process_iter():
            if time.monotonic() >= deadline:
                return False
            try:
                if process.environ().get("TSA_VERIFICATION_PROCESS_TOKEN") == token:
                    owned.setdefault(process.pid, process)
            except (psutil.Error, OSError):
                continue
        alive = []
        for process in list(owned.values()):
            try:
                if process.is_running() and process.status() != psutil.STATUS_ZOMBIE:
                    alive.append(process)
                    process.kill()
            except psutil.NoSuchProcess:
                continue
            except psutil.AccessDenied:
                alive.append(process)
        if os.name != "nt":
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if not alive:
            empty += 1
            if empty == 2:
                return True
        else:
            empty = 0
            psutil.wait_procs(alive, timeout=0.05)
        time.sleep(0.02)
    return False


def _run_step(
    argv: list[str], root: str, deadline: float, cancel: threading.Event
) -> dict[str, Any]:
    """有界日志与等待；成功退出也不能留下后台子进程。"""
    token = uuid.uuid4().hex
    options = (
        {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    proc = subprocess.Popen(
        argv,
        cwd=root,
        env={**os.environ, "TSA_VERIFICATION_PROCESS_TOKEN": token},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        **options,
    )
    owned: dict[int, psutil.Process] = {}
    try:
        owned[proc.pid] = psutil.Process(proc.pid)
    except psutil.NoSuchProcess:
        pass
    output = bytearray()
    total = 0

    def drain() -> None:
        nonlocal total
        assert proc.stdout is not None
        while chunk := proc.stdout.read(8192):
            total += len(chunk)
            output.extend(chunk[: max(0, 65536 - len(output))])

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    status = "passed"
    try:
        while proc.poll() is None:
            for process in list(owned.values()):
                try:
                    for child in process.children(recursive=True):
                        owned.setdefault(child.pid, child)
                except psutil.Error:
                    continue
            if cancel.is_set():
                status = "cancelled"
                break
            if time.monotonic() >= deadline:
                status = "timeout"
                break
            cancel.wait(0.02)
        if status == "passed" and proc.returncode != 0:
            status = "failed"
    finally:
        quiet = _cleanup(proc, owned, token)
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            quiet = False
        reader.join(timeout=1)
        if not reader.is_alive() and proc.stdout is not None:
            proc.stdout.close()
    if not quiet or reader.is_alive():
        status = "error"
    return {
        "status": status,
        "exit_code": proc.returncode,
        "output": bytes(output).decode("utf-8", errors="replace"),
        "output_truncated": total > len(output) or reader.is_alive(),
        "cleanup_complete": quiet,
    }


def run_verification_request(
    request: str, project_root: str, cancel: threading.Event | None = None
) -> dict[str, Any]:
    """只有描述符与重新发现的完整计划相符时，才启动第一个测试。"""
    result: dict[str, Any] = {
        "success": False,
        "verdict": "ERROR",
        "status": "error",
        "executed_steps": [],
        "total_steps": 0,
        "unexecuted_steps": 0,
    }
    started = time.monotonic()
    try:
        value = decode_request(request)
        root = str(Path(project_root).resolve(strict=True))
        steps = rebuild_request(value, root)
        result.update(
            plan_digest=value["plan"],
            stage=value["stage"],
            total_steps=len(steps),
            unexecuted_steps=len(steps),
        )
        deadline = started + value["timeout"]
        stopped = cancel or threading.Event()
        log_remaining = 65536
        for index, step in enumerate(steps):
            if stopped.is_set() or time.monotonic() >= deadline:
                result["status"] = "cancelled" if stopped.is_set() else "timeout"
                return result
            completed = _run_step(step["argv"], root, deadline, stopped)
            raw_output = completed["output"].encode("utf-8")
            completed["output"] = raw_output[:log_remaining].decode(
                "utf-8", errors="ignore"
            )
            completed["output_truncated"] |= len(raw_output) > log_remaining
            log_remaining = max(0, log_remaining - len(raw_output))
            result["executed_steps"].append(
                {"index": index, "role": step["role"], **completed}
            )
            result["unexecuted_steps"] -= 1
            if completed["status"] != "passed":
                result.update(status=completed["status"], first_failed_step=index)
                return result
        result.update(success=True, verdict="SAFE", status="passed")
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        result["error_code"] = str(exc)
        if str(exc) == "VERIFICATION_PLAN_CHANGED":
            result["status"] = "changed"
    return result
