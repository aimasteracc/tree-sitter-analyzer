"""有界重建描述符：绑定完整计划，不把测试集合塞进启动命令。"""

from __future__ import annotations

import base64
import hashlib
import json
import shlex
import subprocess
import sys
from contextvars import ContextVar
from pathlib import Path
from typing import Any, cast

_CAPTURE: ContextVar[dict[str, Any] | None] = ContextVar(
    "verification_plan_capture", default=None
)
_STAGES = ("verification", "focused", "local", "ci", "low_focused")
_FIELDS = {
    "version",
    "root",
    "request",
    "changed",
    "plan",
    "stage",
    "pr_identity",
    "timeout",
}
_REQUEST_FIELDS = {"mode", "scope_paths", "include_tests", "resource_profile", "pr_url"}


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
    ).hexdigest()


def within_budget(command: str) -> bool:
    return (
        len(command.encode("utf-8")) <= 6000
        and len(command.encode("utf-16-le")) // 2 + 1 <= 6000
    )


def compile_stages(context: Any) -> dict[str, list[dict[str, Any]]]:
    """复用 argv 编译器，按角色与资源阶段生成完整有序计划。"""
    from .mcp.tools.utils.change_impact_analysis import (
        _drop_pytest_quiet_and_worker_flags,
    )
    from .mcp.tools.utils.change_impact_verification import _has_runtime_auto_discovery
    from .mcp.tools.utils.verification_command import (
        DefaultTestCommand,
        _argv_within_budget,
        build_test_argv_batches,
    )

    verification = context.verification
    default = DefaultTestCommand(
        verification["test_runner"], verification["default_test_command"]
    )
    focused = (
        [
            {"role": "focused", "argv": argv}
            for argv in build_test_argv_batches(default, context.all_tests)
        ]
        if verification["test_required"] and context.all_tests
        else []
    )
    ci = list(focused)
    if verification["test_required"]:
        if not ci or _has_runtime_auto_discovery(context.test_mapping):
            gate = {"role": "default_gate", "argv": shlex.split(default.command)}
            if not ci or ci[-1]["argv"] != gate["argv"]:
                ci.append(gate)
    else:
        ci = [{"role": "non_test_check", "argv": ["git", "diff", "--check"]}]

    def low(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = []
        for step in steps:
            argv = step["argv"]
            if argv[:3] == ["uv", "run", "pytest"]:
                prefix = [] if sys.platform == "win32" else ["nice", "-n", "15"]
                argv = [
                    *prefix,
                    *argv[:3],
                    *_drop_pytest_quiet_and_worker_flags(argv[3:]),
                    "-n",
                    "2",
                    "-q",
                ]
            if not _argv_within_budget(argv):
                targets = step["argv"][3:-1]
                if step["role"] != "focused" or len(targets) < 2:
                    raise ValueError("VERIFICATION_REQUEST_TOO_LARGE")
                middle = len(targets) // 2
                result.extend(
                    low(
                        [
                            {
                                "role": "focused",
                                "argv": [*step["argv"][:3], *part, "-q"],
                            }
                            for part in (targets[:middle], targets[middle:])
                        ]
                    )
                )
                continue
            result.append({"role": step["role"], "argv": argv})
        return result

    local = low(ci) if context.request.resource_profile == "local_low_impact" else ci
    return {
        "verification": local,
        "focused": focused,
        "local": local,
        "ci": ci,
        "low_focused": low(focused),
    }


def pr_identity(root: str, url: str) -> dict[str, str]:
    """PR 重建仅接受干净的远端 head checkout，查询失败不能继续运行测试。"""

    def run(argv: list[str]) -> str:
        return subprocess.run(
            argv, cwd=root, check=True, capture_output=True, text=True, timeout=30
        ).stdout.strip()

    remote = json.loads(
        run(["gh", "pr", "view", url, "--json", "headRefOid,baseRefOid"])
    )
    head = run(["git", "rev-parse", "HEAD"])
    if head != remote["headRefOid"] or run(
        ["git", "status", "--porcelain", "--untracked-files=no"]
    ):
        raise ValueError("VERIFICATION_PR_CHECKOUT_MISMATCH")
    return {"head": head, "base": remote["baseRefOid"]}


def request_binding(context: Any) -> dict[str, Any]:
    request = context.request
    return {
        "mode": request.mode,
        "scope_paths": request.scope_paths or [],
        "include_tests": request.include_tests,
        "resource_profile": request.resource_profile,
        "pr_url": request.pr_url,
    }


def attach_commands(response: dict[str, Any], context: Any) -> dict[str, Any]:
    """仅过长命令使用间接入口；分析不写清单也不启动测试。"""
    captured = _CAPTURE.get()
    if captured is not None:
        captured.update(
            stages=compile_stages(context), changed=context.request.changed_files
        )
        return response
    fields = {
        "verification_command": "verification",
        "test_command": "verification",
        "pytest_command": "verification",
        "focused_test_command": "focused",
        "local_verification_command": "local",
        "ci_verification_command": "ci",
        "low_impact_focused_test_command": "low_focused",
    }
    oversized = {
        key: stage
        for key, stage in fields.items()
        if response.get(key) and not within_budget(response[key])
    }
    if not oversized:
        return response
    root = str(Path(context.request.project_root or ".").resolve())
    try:
        if context.request.read_only:
            raise ValueError("VERIFICATION_SNAPSHOT_NOT_REPLAYABLE")
        stages = compile_stages(context)
        request = request_binding(context)
        identity = (
            pr_identity(root, request["pr_url"]) if request["mode"] == "pr" else None
        )
        replacements = {}
        for key, stage in oversized.items():
            descriptor = {
                "version": 1,
                "root": digest(root),
                "request": request,
                "changed": digest(context.request.changed_files),
                "plan": digest(stages[stage]),
                "stage": stage,
                "pr_identity": identity,
                "timeout": 900,
            }
            token = base64.urlsafe_b64encode(
                json.dumps(descriptor, sort_keys=True, separators=(",", ":")).encode()
            ).decode()
            command = "uv run python -m tree_sitter_analyzer --verify-plan " + token
            if len(token) > 5800 or not within_budget(command):
                raise ValueError("VERIFICATION_REQUEST_TOO_LARGE")
            replacements[response[key]] = command

        def replace(value: Any) -> Any:
            if isinstance(value, str):
                for old, new in sorted(
                    replacements.items(), key=lambda item: len(item[0]), reverse=True
                ):
                    value = value.replace(old, new)
                return value
            if isinstance(value, list):
                return [replace(item) for item in value]
            if isinstance(value, dict):
                return {key: replace(item) for key, item in value.items()}
            return value

        return cast(dict[str, Any], replace(response))
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        # 错误响应保留全部结构化步骤，但绝不继续推荐无法启动的总命令。
        for key in fields:
            if key in response:
                response[key] = ""
        response.update(success=False, verdict="ERROR", error_code=str(exc))
        response["agent_summary"] = {
            "verdict": "ERROR",
            "next_step": "Verification request could not be represented safely.",
            "verification_command": "",
        }
        return response


def decode_request(token: str) -> dict[str, Any]:
    """只接受固定字段与有界原始输入，不反序列化命令或 Python 对象。"""
    try:
        if not isinstance(token, str) or len(token) > 5800:
            raise ValueError
        value = json.loads(base64.b64decode(token, altchars=b"-_", validate=True))
        if not isinstance(value, dict) or set(value) != _FIELDS:
            raise ValueError
        request = value["request"]
        if not isinstance(request, dict) or set(request) != _REQUEST_FIELDS:
            raise ValueError
        if type(value["version"]) is not int or value["version"] != 1:
            raise ValueError
        if (
            value["stage"] not in _STAGES
            or type(value["timeout"]) is not int
            or not 1 <= value["timeout"] <= 900
        ):
            raise ValueError
        if (
            request["mode"] not in ("diff", "staged", "branch", "pr")
            or type(request["include_tests"]) is not bool
        ):
            raise ValueError
        if request["resource_profile"] not in ("default", "local_low_impact"):
            raise ValueError
        if not isinstance(request["scope_paths"], list) or any(
            not isinstance(path, str) or "\x00" in path
            for path in request["scope_paths"]
        ):
            raise ValueError
        if not isinstance(request["pr_url"], str):
            raise ValueError
        for key in ("root", "changed", "plan"):
            if (
                not isinstance(value[key], str)
                or len(value[key]) != 64
                or any(c not in "0123456789abcdef" for c in value[key])
            ):
                raise ValueError
        if request["mode"] != "pr" and (
            request["pr_url"] or value["pr_identity"] is not None
        ):
            raise ValueError
        if request["mode"] == "pr":
            from .pr_url import parse_pr_url

            if parse_pr_url(request["pr_url"]) is None:
                raise ValueError
            if not isinstance(value["pr_identity"], dict) or set(
                value["pr_identity"]
            ) != {"head", "base"}:
                raise ValueError
        return value
    except (ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise ValueError("VERIFICATION_REQUEST_INVALID") from exc
