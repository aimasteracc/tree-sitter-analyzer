from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts import run_mutation_baseline


@pytest.mark.parametrize("failed_step", ["run", "results"])
@pytest.mark.parametrize("returncode", [1, 7, -15])
def test_main_propagates_mutmut_failure_and_restores_pyproject(
    monkeypatch, tmp_path: Path, failed_step: str, returncode: int
) -> None:
    # 2026-09-07：外部变异命令失败曾被吞掉，入口必须失败且恢复原配置。
    real_pyproject = tmp_path / "pyproject.toml"
    original = b"[project]\r\nname = 'sample'\r\n"
    real_pyproject.write_bytes(original)
    monkeypatch.setattr(
        run_mutation_baseline, "__file__", tmp_path / "scripts/runner.py"
    )
    monkeypatch.setattr(run_mutation_baseline.sys, "argv", ["runner", "ast_diff"])
    monkeypatch.setattr(
        run_mutation_baseline, "_resolve_mutmut_command", lambda: ["mutmut"]
    )

    def fake_run(cmd, **kwargs):
        assert kwargs["cwd"] == tmp_path
        assert "[tool.mutmut]" in real_pyproject.read_text(encoding="utf-8")
        return subprocess.CompletedProcess(
            cmd, returncode if cmd[-1] == failed_step else 0
        )

    mocked_run = Mock(side_effect=fake_run)
    monkeypatch.setattr(run_mutation_baseline.subprocess, "run", mocked_run)

    with pytest.raises(subprocess.CalledProcessError) as exc:
        run_mutation_baseline.main()

    assert exc.value.returncode == returncode
    assert exc.value.cmd == ["mutmut", failed_step]
    assert [call.args[0] for call in mocked_run.call_args_list] == (
        [["mutmut", "run"]]
        if failed_step == "run"
        else [["mutmut", "run"], ["mutmut", "results"]]
    )
    assert real_pyproject.read_bytes() == original


@pytest.mark.parametrize("failed_step", ["run", "results"])
def test_run_module_restores_pyproject_when_process_cannot_start(
    monkeypatch, tmp_path: Path, failed_step: str
) -> None:
    # 2026-09-07：进程启动异常也必须透传，不能遗留临时配置。
    real_pyproject = tmp_path / "pyproject.toml"
    original = b"[project]\nname = 'sample'\n"
    real_pyproject.write_bytes(original)
    monkeypatch.setattr(
        run_mutation_baseline, "_resolve_mutmut_command", lambda: ["mutmut"]
    )
    error = OSError("cannot start mutmut")

    def fake_run(cmd, **kwargs):
        if cmd[-1] == failed_step:
            raise error
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(run_mutation_baseline.subprocess, "run", fake_run)

    with pytest.raises(OSError) as exc:
        run_mutation_baseline.run_module("ast_diff", tmp_path)

    assert exc.value is error
    assert real_pyproject.read_bytes() == original


def test_run_module_does_not_invoke_uv_while_pyproject_is_swapped(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    real_pyproject = repo_root / "pyproject.toml"
    real_pyproject.write_text("[project]\nname = 'sample'\n", encoding="utf-8")

    calls: list[list[str]] = []

    def fake_run(cmd, *, cwd=None, capture_output=False):
        assert cwd == repo_root
        assert "Temporary pyproject.toml" in real_pyproject.read_text(encoding="utf-8")
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(
        run_mutation_baseline,
        "_resolve_mutmut_command",
        lambda: ["/venv/bin/mutmut"],
        raising=False,
    )
    monkeypatch.setattr(run_mutation_baseline.subprocess, "run", fake_run)

    run_mutation_baseline.run_module("ast_diff", repo_root)

    assert calls == [
        ["/venv/bin/mutmut", "run"],
        ["/venv/bin/mutmut", "results"],
        ["/venv/bin/mutmut", "export-cicd-stats"],
    ]
    assert real_pyproject.read_text(encoding="utf-8") == "[project]\nname = 'sample'\n"


def test_resolve_mutmut_command_prefers_current_environment_script(
    monkeypatch,
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "venv" / "bin"
    bin_dir.mkdir(parents=True)
    python = bin_dir / "python"
    mutmut = bin_dir / "mutmut"
    python.write_text("", encoding="utf-8")
    mutmut.write_text("", encoding="utf-8")

    monkeypatch.setattr(run_mutation_baseline.sys, "executable", str(python))
    monkeypatch.setattr(run_mutation_baseline.shutil, "which", lambda name: None)

    assert run_mutation_baseline._resolve_mutmut_command() == [str(mutmut)]


def test_resolve_mutmut_command_falls_back_to_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
    python = tmp_path / "python"
    path_mutmut = tmp_path / "mutmut"
    monkeypatch.setattr(run_mutation_baseline.sys, "executable", str(python))
    monkeypatch.setattr(
        run_mutation_baseline.shutil,
        "which",
        lambda name: str(path_mutmut) if name == "mutmut" else None,
    )

    assert run_mutation_baseline._resolve_mutmut_command() == [str(path_mutmut)]


def test_resolve_mutmut_command_falls_back_to_python_module(
    monkeypatch,
    tmp_path: Path,
) -> None:
    python = tmp_path / "python"
    monkeypatch.setattr(run_mutation_baseline.sys, "executable", str(python))
    monkeypatch.setattr(run_mutation_baseline.shutil, "which", lambda name: None)

    assert run_mutation_baseline._resolve_mutmut_command() == [
        str(python),
        "-m",
        "mutmut",
    ]


def test_run_module_rejects_unknown_module(capsys, tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        run_mutation_baseline.run_module("missing", tmp_path)

    assert exc.value.code == 1
    assert "Unknown module: missing." in capsys.readouterr().out


def _fake_repo(monkeypatch, tmp_path: Path, stats: dict | None, ratchet: dict) -> None:
    """A repo whose mutmut run "succeeds" and leaves ``stats`` behind."""
    monkeypatch.setattr(
        run_mutation_baseline, "__file__", str(tmp_path / "scripts" / "runner.py")
    )
    if stats is not None:
        report = tmp_path / run_mutation_baseline.STATS_PATH
        report.parent.mkdir(parents=True)
        report.write_text(json.dumps(stats), encoding="utf-8")
    ratchet_file = tmp_path / run_mutation_baseline.RATCHET_PATH
    ratchet_file.parent.mkdir(parents=True)
    ratchet_file.write_text(json.dumps({"max_unkilled": ratchet}), encoding="utf-8")
    monkeypatch.setattr(run_mutation_baseline, "run_module", lambda key, root: None)


def _stats(total: int = 10, survived: int = 2, no_tests: int = 1) -> dict:
    return {
        "killed": total - survived - no_tests,
        "survived": survived,
        "no_tests": no_tests,
        "total": total,
        "check_was_interrupted_by_user": False,
    }


def test_main_defaults_to_ast_diff(monkeypatch, tmp_path: Path) -> None:
    _fake_repo(monkeypatch, tmp_path, _stats(), {"ast_diff": 3})
    calls: list[str] = []
    monkeypatch.setattr(
        run_mutation_baseline, "run_module", lambda key, root: calls.append(key)
    )

    assert (run_mutation_baseline.main([]), calls) == (0, ["ast_diff"])


def test_missing_stats_report_fails_closed(monkeypatch, tmp_path: Path) -> None:
    """2026-10-19 run 39216448214: a module with no report still passed."""
    _fake_repo(monkeypatch, tmp_path, None, {"ast_diff": 3})

    with pytest.raises(run_mutation_baseline.MutationReportError):
        run_mutation_baseline.main(["ast_diff"])


@pytest.mark.parametrize(
    ("stats", "ratchet", "problem"),
    [
        (_stats(total=0, survived=0, no_tests=0), {"ast_diff": 0}, "zero mutants"),
        (_stats(survived=3), {"ast_diff": 3}, "exceed the ratchet of 3"),
        (_stats(), {}, "no ratchet entry for ast_diff; record 3"),
    ],
)
def test_report_that_breaks_the_gate_fails(
    monkeypatch, tmp_path: Path, capsys, stats: dict, ratchet: dict, problem: str
) -> None:
    _fake_repo(monkeypatch, tmp_path, stats, ratchet)

    assert (
        run_mutation_baseline.main(["ast_diff", "--report-dir", str(tmp_path / "r")])
        == 1
    )
    assert problem in capsys.readouterr().err
    report = json.loads((tmp_path / "r" / "ast_diff.json").read_text(encoding="utf-8"))
    assert report["problems"] and problem in report["problems"][0]


def test_beating_the_ratchet_passes_and_asks_to_lower_it(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    _fake_repo(monkeypatch, tmp_path, _stats(survived=0, no_tests=0), {"ast_diff": 5})

    assert run_mutation_baseline.main(["ast_diff"]) == 0
    assert "lower tests/effectiveness/mutation_ratchet.json to 0" in (
        capsys.readouterr().out.replace("\\", "/")
    )


def test_list_prints_every_module(capsys) -> None:
    assert run_mutation_baseline.main(["--list"]) == 0
    assert json.loads(capsys.readouterr().out) == list(run_mutation_baseline.MODULES)


def test_every_module_targets_existing_files() -> None:
    """toon_encoder.py was deleted and the baseline kept "mutating" it."""
    root = Path(run_mutation_baseline.__file__).parent.parent
    missing = [
        path
        for source, tests in run_mutation_baseline.MODULES.values()
        for path in (source, *tests)
        if not (root / path).is_file()
    ]

    assert missing == []


def test_completeness_modules_are_mutated() -> None:
    assert {"callers_checks", "callers_outcomes", "callers_target_set"} <= set(
        run_mutation_baseline.MODULES
    )


def test_ratchet_entries_name_known_modules() -> None:
    root = Path(run_mutation_baseline.__file__).parent.parent
    ratchet = run_mutation_baseline.load_ratchet(root)

    assert set(ratchet) == set(run_mutation_baseline.MODULES)
    invalid = {m: v for m, v in ratchet.items() if type(v) is not int or v < 0}
    assert invalid == {}


def test_workflow_fails_closed() -> None:
    root = Path(run_mutation_baseline.__file__).parent.parent
    text = (root / ".github" / "workflows" / "mutation-baseline.yml").read_text(
        encoding="utf-8"
    )

    assert "|| true" not in text
    assert "if-no-files-found: error" in text
    assert "timeout-minutes: 30" in text
