from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts import run_mutation_baseline


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


def test_main_defaults_to_ast_diff(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, Path]] = []
    monkeypatch.setattr(run_mutation_baseline.sys, "argv", ["runner"])
    monkeypatch.setattr(
        run_mutation_baseline,
        "run_module",
        lambda module_key, repo_root: calls.append((module_key, repo_root)),
    )

    run_mutation_baseline.main()

    assert calls == [
        (
            "ast_diff",
            Path(run_mutation_baseline.__file__).parent.parent.resolve(),
        )
    ]
