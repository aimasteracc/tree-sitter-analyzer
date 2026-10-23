"""NO1-010B B1 verifier 测试共用的合成夹具与补丁构造（非测试模块）。

合成 corpus 让 oracle / verification 行为可控：``src/value.py`` 是 oracle 观察的
目标，``src/extra.py`` 只被 verification 命令导入，用于构造"通过 oracle 却破坏
verification"的补丁（RFC-0026 §5）。
"""

from __future__ import annotations

import difflib
import sys
import time
from pathlib import Path

import psutil

from tree_sitter_analyzer.no1_010b.record import BenchmarkRecord, record_from_dict
from tree_sitter_analyzer.no1_010b.runner import Verdict
from tree_sitter_analyzer.no1_010b.transcript_specs import REFERENCE_EDIT_SPECS
from tree_sitter_analyzer.no1_010b.verifier import verify_patch

CORPUS_ROOT = Path(__file__).resolve().parents[3] / "benchmarks" / "no1_010b"
VALUE_PY = "def value():\n    return 1\n"
EXTRA_PY = "def extra():\n    return 'ok'\n"
VALUE_ORACLE = (
    "import os\n"
    "import sys\n"
    "sys.path.insert(0, os.getcwd())\n"
    "from src.value import value  # noqa: E402\n"
    "\n"
    "\n"
    "def main():\n"
    "    try:\n"
    "        held = value() == 2\n"
    "    except Exception as exc:\n"
    "        print(f'oracle could not decide: {exc!r}', file=sys.stderr)\n"
    "        return 1\n"
    "    print('NO1_010B_ORACLE_REASON: value-is-one')\n"
    "    print(f\"NO1_010B_ORACLE_RESULT: {'PASS' if held else 'FAIL'}\")\n"
    "    return 0\n"
)
NO_REASON_ORACLE = (
    "def main():\n    print('NO1_010B_ORACLE_RESULT: PASS')\n    return 0\n"
)
RAISING_ORACLE = "def main():\n    raise RuntimeError('oracle bug')\n"
IMPORTS_SRC = [
    sys.executable,
    "-c",
    "import sys; sys.path.insert(0, '.'); import src.value, src.extra",
]
EXPECTED_NOT_IMPLEMENTED = (
    "read_only_candidate_mount",
    "write_journal",
    "network_isolation",
    "runner_venv_isolation",
    "home_isolation",
    "process_escape_containment",
    "output_volume_containment",
    "stale_rows",
    "unsupported_relationship",
    "registration_registry",
)


def diff(path: str, before: str, after: str) -> str:
    """生成 ``git apply`` 可解析的单文件统一 diff（新文件用 /dev/null）。"""
    lines = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{path}" if before else "/dev/null",
        tofile=f"b/{path}",
    )
    return "".join(lines)


def value_patch(body: str) -> str:
    return diff("src/value.py", VALUE_PY, body)


GOOD_PATCH = value_patch("def value():\n    return 2\n")


def write_value_corpus(root: Path) -> Path:
    files = {
        "fixtures/app/src/__init__.py": "",
        "fixtures/app/src/value.py": VALUE_PY,
        "fixtures/app/src/extra.py": EXTRA_PY,
        "oracles/value.py": VALUE_ORACLE,
        "oracles/no_reason.py": NO_REASON_ORACLE,
        "oracles/raising.py": RAISING_ORACLE,
    }
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        # 写字节而非文本：Windows 文本模式会把 LF 转成 CRLF，使补丁上下文失配。
        (root / rel).write_bytes(text.encode("utf-8"))
    return root


def make_record(**overrides: object) -> BenchmarkRecord:
    payload: dict[str, object] = {
        "id": "no1-010b/test-synthetic-value",
        "task_class": "bugfix",
        "repo": "fixtures/app",
        "repo_commit": "0" * 40,
        "operation": "plan_change",
        "task": "value returns 1; make it return 2",
        "allowed_paths": ["src/"],
        "oracle": "oracles/value.py",
        "oracle_baseline_reason": "value-is-one",
        "verification_argv": IMPORTS_SRC,
        "expected_terminal": {"verdict": "PASS", "reason_code": None},
    }
    payload.update(overrides)
    return record_from_dict(payload)


def verify(
    corpus: Path,
    patch: str,
    record: BenchmarkRecord | None = None,
    **timeouts: float,
) -> Verdict:
    return verify_patch(
        record or make_record(), corpus, patch, **timeouts
    ).checks_verdict


def reference_patch(record: BenchmarkRecord) -> str:
    """由已提交的参考编辑规格生成该任务的正确补丁。"""
    spec = REFERENCE_EDIT_SPECS[record.id]
    (replacement,) = spec.replacements
    source = CORPUS_ROOT / record.repo / replacement.path
    before = source.read_text(encoding="utf-8")
    after = before.replace(replacement.before, replacement.after, 1)
    return diff(replacement.path, before, after)


def write_exit_script(stem: Path, code: int) -> Path:
    """写出以 ``code`` 退出的可执行脚本并返回其路径。

    POSIX 写带 shebang 的 ``stem`` 并设为可执行；Windows 写 ``stem.cmd``，
    ``shutil.which`` 会按 PATHEXT 把无后缀的 ``stem`` 解析到它。
    """
    stem.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        script = stem.with_suffix(".cmd")
        script.write_bytes(f"@exit /b {code}\r\n".encode("ascii"))
        return script
    stem.write_bytes(f"#!/bin/sh\nexit {code}\n".encode("ascii"))
    stem.chmod(0o755)
    return stem


def spawn_grandchild_argv(pid_file: Path, *, linger: bool) -> list[str]:
    """verification 命令：派生长睡孙进程并写出其 pid，然后挂起或立即退出。"""
    script = (
        "import pathlib, subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"pathlib.Path({str(pid_file)!r}).write_text(str(child.pid))\n"
        + ("time.sleep(60)\n" if linger else "")
    )
    return [sys.executable, "-c", script]


def still_running(pid: int, within_s: float = 5.0) -> bool:
    """在截止时间内轮询：进程消失或成为僵尸即视为已死。"""
    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return False
    deadline = time.monotonic() + within_s
    while time.monotonic() < deadline:
        try:
            if proc.status() == psutil.STATUS_ZOMBIE:
                return False
        except psutil.NoSuchProcess:
            return False
        _, alive = psutil.wait_procs([proc], timeout=0.1)
        if not alive:
            return False
    return True


def kill_quietly(pid: int) -> None:
    """测试清理：已知缺口下幸存的孙进程必须被收掉，不污染后续测试。"""
    try:
        psutil.Process(pid).kill()
    except psutil.Error:
        pass
