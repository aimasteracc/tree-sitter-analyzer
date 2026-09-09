"""验证执行的真实子进程、失败即停、日志边界与取消回收。"""

import base64
import json
import sys
import threading
import time
from pathlib import Path

import psutil
import pytest

from tree_sitter_analyzer import verification_runner as runner


def request_token(tmp_path, timeout=10):
    from tree_sitter_analyzer.verification_plan import digest

    data = {
        "version": 1,
        "root": digest(str(tmp_path.resolve())),
        "request": {
            "mode": "diff",
            "scope_paths": [],
            "include_tests": True,
            "resource_profile": "default",
            "pr_url": "",
        },
        "changed": digest(["tests/test_missing.py"]),
        "plan": digest([]),
        "stage": "verification",
        "pr_identity": None,
        "timeout": timeout,
    }
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode()


def python_step(code, role="focused"):
    return {"role": role, "argv": [sys.executable, "-c", code]}


@pytest.mark.parametrize("failure", [None, 1, 2])
def test_ordered_execution_stops_at_first_failed_step(tmp_path, monkeypatch, failure):
    steps = []
    for index in range(3):
        code = f"from pathlib import Path; Path('step-{index}').write_text('ran'); raise SystemExit({7 if failure == index else 0})"
        steps.append(python_step(code, "default_gate" if index == 2 else "focused"))
    monkeypatch.setattr(runner, "rebuild_request", lambda *_: steps)
    result = runner.run_verification_request(request_token(tmp_path), str(tmp_path))
    count = 3 if failure is None else failure + 1
    assert [Path(tmp_path / f"step-{index}").exists() for index in range(3)] == [
        index < count for index in range(3)
    ]
    assert len(result["executed_steps"]) == count
    assert result["unexecuted_steps"] == 3 - count
    assert result["status"] == ("passed" if failure is None else "failed")
    assert result["success"] is (failure is None)
    if failure is not None:
        assert result["first_failed_step"] == failure
        assert result["executed_steps"][-1]["exit_code"] == 7


def test_invalid_token_starts_no_process(tmp_path, monkeypatch):
    monkeypatch.setattr(
        runner, "_run_step", lambda *_: pytest.fail("拒绝的输入不得启动测试")
    )
    result = runner.run_verification_request("invalid", str(tmp_path))
    assert result["executed_steps"] == []
    assert result["error_code"] == "VERIFICATION_REQUEST_INVALID"


def test_changed_plan_starts_no_process(tmp_path, monkeypatch):
    monkeypatch.setattr(
        runner, "_run_step", lambda *_: pytest.fail("变化的计划不得启动测试")
    )
    result = runner.run_verification_request(request_token(tmp_path), str(tmp_path))
    assert result["executed_steps"] == []
    assert result["status"] == "changed"


def test_launch_failure_does_not_run_later_steps(tmp_path, monkeypatch):
    steps = [
        {"role": "focused", "argv": [str(tmp_path / "missing-executable")]},
        python_step("raise RuntimeError('must not run')"),
    ]
    monkeypatch.setattr(runner, "rebuild_request", lambda *_: steps)
    result = runner.run_verification_request(request_token(tmp_path), str(tmp_path))
    assert result["status"] == "error"
    assert result["executed_steps"] == []
    assert result["unexecuted_steps"] == 2


@pytest.mark.parametrize("kind", ["cancelled", "timeout"])
def test_stop_before_first_step_keeps_plan_unexecuted(tmp_path, monkeypatch, kind):
    steps = [python_step("raise RuntimeError('must not run')")]
    monkeypatch.setattr(runner, "rebuild_request", lambda *_: steps)
    stopped = threading.Event()
    if kind == "cancelled":
        stopped.set()
    else:
        ticks = iter([0, 100])
        monkeypatch.setattr(
            runner, "time", type("Clock", (), {"monotonic": lambda: next(ticks)})
        )
    result = runner.run_verification_request(
        request_token(tmp_path), str(tmp_path), stopped
    )
    assert result["status"] == kind
    assert result["executed_steps"] == []
    assert result["unexecuted_steps"] == 1


def test_output_budget_is_shared_across_steps(tmp_path, monkeypatch):
    steps = [
        python_step("print('x' * 100000)"),
        python_step("print('second')", "default_gate"),
    ]
    monkeypatch.setattr(runner, "rebuild_request", lambda *_: steps)
    result = runner.run_verification_request(request_token(tmp_path), str(tmp_path))
    assert result["success"] is True
    assert len(result["executed_steps"][0]["output"]) == 65536
    assert result["executed_steps"][0]["output_truncated"] is True
    assert result["executed_steps"][1]["output"] == ""
    assert result["executed_steps"][1]["output_truncated"] is True


@pytest.mark.parametrize("stop", ["timeout", "cancelled", "parent_exit"])
def test_owned_descendant_does_not_survive_completion(tmp_path, monkeypatch, stop):
    pid_file = tmp_path / "child.pid"
    ready_file = tmp_path / "child.ready"
    child = "import time; time.sleep(60)"
    parent = (
        "import subprocess,sys,time; from pathlib import Path; "
        f"p=subprocess.Popen([sys.executable,'-c',{child!r}]); "
        f"Path({str(pid_file)!r}).write_text(str(p.pid)); "
        f"Path({str(ready_file)!r}).touch(); "
        + ("time.sleep(60)" if stop != "parent_exit" else "time.sleep(0.1)")
    )
    cancel = threading.Event()
    from types import SimpleNamespace

    real_clock = time.monotonic

    def clock():
        ready = ready_file.exists()
        if ready and stop == "cancelled":
            cancel.set()
        return real_clock() + (20 if ready and stop == "timeout" else 0)

    monkeypatch.setattr(
        runner, "time", SimpleNamespace(monotonic=clock, sleep=time.sleep)
    )
    result = runner._run_step(
        [sys.executable, "-c", parent],
        str(tmp_path),
        real_clock() + 10,
        cancel,
    )
    assert result["status"] == ("passed" if stop == "parent_exit" else stop)
    assert result["cleanup_complete"] is True
    pid = int(pid_file.read_text(encoding="utf-8"))
    try:
        process = psutil.Process(pid)
        assert process.status() == psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        pass


def test_unicode_log_truncation_respects_encoded_budget(tmp_path, monkeypatch):
    steps = [
        python_step(
            "import sys; sys.stdout.buffer.write(('☃' * 40000).encode('utf-8'))"
        )
    ]
    monkeypatch.setattr(runner, "rebuild_request", lambda *_: steps)
    result = runner.run_verification_request(request_token(tmp_path), str(tmp_path))
    assert result["success"] is True
    output = result["executed_steps"][0]
    assert len(output["output"].encode("utf-8")) == 65535
    assert output["output_truncated"] is True


def test_windows_process_options_do_not_request_posix_session(tmp_path, monkeypatch):
    import os
    import subprocess
    from types import SimpleNamespace

    monkeypatch.setattr(runner, "os", SimpleNamespace(**{**vars(os), "name": "nt"}))
    original = subprocess.Popen
    observed = []

    def launch(*args, **kwargs):
        observed.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(
        runner, "subprocess", SimpleNamespace(**{**vars(subprocess), "Popen": launch})
    )
    result = runner._run_step(
        [sys.executable, "-c", "print('complete')"],
        str(tmp_path),
        time.monotonic() + 10,
        threading.Event(),
    )
    assert result["status"] == "passed"
    assert observed[0]["creationflags"] == getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )
    assert "start_new_session" not in observed[0]


@pytest.mark.parametrize("failure", ["deadline", "scan_deadline", "denied", "vanished"])
def test_cleanup_never_claims_success_for_live_unreaped_process(monkeypatch, failure):
    from types import SimpleNamespace

    killed = []

    def kill():
        killed.append(101)
        if failure == "denied":
            raise psutil.AccessDenied(101)
        raise psutil.NoSuchProcess(101)

    process = SimpleNamespace(
        pid=101,
        environ=lambda: {},
        is_running=lambda: not killed if failure == "vanished" else True,
        status=lambda: psutil.STATUS_RUNNING,
        kill=kill,
    )
    ticks = iter(
        [0, 3]
        if failure == "deadline"
        else [0, 0, 3]
        if failure == "scan_deadline"
        else [0, 0, 0, 3]
        if failure == "denied"
        else [0, 0, 0, 0, 0, 0, 0]
    )
    monkeypatch.setattr(
        runner,
        "time",
        SimpleNamespace(monotonic=lambda: next(ticks), sleep=lambda _: None),
    )
    monkeypatch.setattr(runner, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(runner.psutil, "process_iter", lambda: [process])
    monkeypatch.setattr(runner.psutil, "wait_procs", lambda procs, timeout: ([], procs))
    result = runner._cleanup(SimpleNamespace(pid=101), {101: process}, "owned")
    assert result is (failure == "vanished")
    assert killed == ([101] if failure in {"vanished", "denied"} else [])


@pytest.mark.parametrize(
    "failure", ["disappeared", "children_denied", "wait_timeout", "reader_alive"]
)
def test_step_lifecycle_errors_preserve_truthful_status(tmp_path, monkeypatch, failure):
    import io
    from types import SimpleNamespace

    polls = iter([None, 0])
    process = SimpleNamespace(
        pid=12345,
        returncode=0,
        stdout=io.BytesIO(b"complete"),
        poll=lambda: next(polls),
    )

    def wait(timeout):
        if failure == "wait_timeout":
            raise runner.subprocess.TimeoutExpired("test", timeout)
        return 0

    process.wait = wait
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *args, **kwargs: process)

    def owned(pid):
        if failure == "disappeared":
            raise psutil.NoSuchProcess(pid)

        def children(recursive):
            raise psutil.AccessDenied(pid)

        return SimpleNamespace(children=children)

    monkeypatch.setattr(runner.psutil, "Process", owned)
    monkeypatch.setattr(runner, "_cleanup", lambda *args: True)
    if failure == "reader_alive":
        monkeypatch.setattr(
            runner.threading,
            "Thread",
            lambda **kwargs: SimpleNamespace(
                start=lambda: None, join=lambda timeout: None, is_alive=lambda: True
            ),
        )
    result = runner._run_step(
        ["test"], str(tmp_path), time.monotonic() + 10, threading.Event()
    )
    assert result["status"] == (
        "error" if failure in {"wait_timeout", "reader_alive"} else "passed"
    )
    assert result["cleanup_complete"] is (failure != "wait_timeout")
    assert result["output_truncated"] is (failure == "reader_alive")
    assert process.stdout.closed is (failure != "reader_alive")


def test_cleanup_does_not_signal_a_bare_process_group_id(monkeypatch):
    # 2026-09-09：macOS 的已退出组可能拒绝信号；清理以保留的进程身份为准。
    from types import SimpleNamespace

    monkeypatch.setattr(runner.psutil, "process_iter", lambda: [])
    monkeypatch.setattr(
        runner,
        "os",
        SimpleNamespace(
            name="posix", killpg=lambda *_: pytest.fail("不得凭旧组号发送信号")
        ),
    )
    assert runner._cleanup(SimpleNamespace(pid=12345), {}, "owned") is True
