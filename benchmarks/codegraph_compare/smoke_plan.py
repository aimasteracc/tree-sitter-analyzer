"""Freeze the complete model-free execution plan for NO1-001B."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from benchmarks.codegraph_compare.adapters import codegraph_executable_identity
from benchmarks.codegraph_compare.integrity import (
    ExpectedCellV1,
    _sha256,
    create_manifest,
)
from benchmarks.codegraph_compare.setup_validation import (
    selected_matrix_config_hash,
    selected_questions_hash,
    selected_schedule_hash,
)
from benchmarks.codegraph_compare.smoke_evidence import (
    READINESS_ORACLE,
    produce_gin_index_evidence,
)

ARMS = ("native-only", "tsa-warm", "codegraph-warm")
INDEXED_ARMS = ("tsa-warm", "codegraph-warm")


def _git_output(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _command_identity(command: list[str]) -> dict[str, str]:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=True,
        env={
            **os.environ,
            "CODEGRAPH_TELEMETRY": "0",
            "CODEGRAPH_NO_DAEMON": "1",
        },
    )
    executable = shutil.which(command[0])
    if executable is None:
        raise ValueError(f"Required executable is unavailable: {command[0]}")
    binary = Path(executable).resolve()
    return {
        "command": " ".join(command),
        "version": (result.stdout or result.stderr).strip(),
        "executable": str(binary),
        "executable_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
    }


def tool_fingerprints(benchmark_repo: Path) -> tuple[dict[str, str], str]:
    """Fingerprint the exact agent and indexed tool implementations."""

    benchmark_sha = _git_output(benchmark_repo, "rev-parse", "HEAD")
    codex = _command_identity(["codex", "--version"])
    codegraph = codegraph_executable_identity()
    tools = {
        "native-only": _sha256(
            {
                "arm": "native-only",
                "mcp_servers": [],
                "sandbox": "read-only",
                "network": "disabled",
            }
        ),
        "tsa-warm": _sha256(
            {
                "arm": "tsa-warm",
                "benchmark_git_sha": benchmark_sha,
                "mcp_module": "tree_sitter_analyzer.mcp.server",
                "sandbox": "workspace-write",
                "network": "disabled",
            }
        ),
        "codegraph-warm": _sha256(
            {
                "arm": "codegraph-warm",
                "binary": codegraph,
                "telemetry": False,
                "daemon": False,
                "sandbox": "workspace-write",
                "network": "disabled",
            }
        ),
    }
    return tools, _sha256(codex)


def _load_selected_config(config_dir: Path) -> tuple[dict, list[dict], dict]:
    repos = yaml.safe_load((config_dir / "repos.yaml").read_text(encoding="utf-8"))
    arms = yaml.safe_load((config_dir / "arms.yaml").read_text(encoding="utf-8"))
    questions = yaml.safe_load(
        (config_dir / "questions.yaml").read_text(encoding="utf-8")
    )
    repo = next(item for item in repos["repos"] if item["id"] == "gin")
    selected_arms = [
        next(item for item in arms["arms"] if item["id"] == arm) for arm in ARMS
    ]
    question = next(
        item
        for item in questions["questions"]
        if item["id"] == "gin-route-matching"
    )
    return repo, selected_arms, question


def _environment_fingerprint() -> tuple[str, str]:
    details = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
    }
    return platform.platform(), _sha256(details)


def _write_exclusive(path: Path, payload: Any) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=True, indent=2, sort_keys=True)
        stream.write("\n")


def freeze_smoke_plan(
    *,
    benchmark_repo: Path,
    checkout_root: Path,
    destination: Path,
    model: str,
    session_id: str,
    timeout_seconds: int,
    seed: int,
) -> dict[str, Path]:
    """Build indexes and freeze manifest/workspace evidence before model use."""

    benchmark_repo = benchmark_repo.resolve()
    if _git_output(
        benchmark_repo, "status", "--porcelain", "--untracked-files=no"
    ):
        raise ValueError("Benchmark implementation has tracked modifications")
    destination.mkdir(parents=True, exist_ok=False)
    config_dir = benchmark_repo / "benchmarks" / "codegraph_compare"
    repo, arms, question = _load_selected_config(config_dir)
    checkouts = {
        arm: (checkout_root / arm / "gin").resolve() for arm in ARMS
    }
    tools, agent_fingerprint = tool_fingerprints(benchmark_repo)
    index_path = destination / "index-evidence.json"
    eligibility_path = destination / "eligibility.json"
    eligibility = produce_gin_index_evidence(
        tsa_repo=checkouts["tsa-warm"],
        codegraph_repo=checkouts["codegraph-warm"],
        output_path=index_path,
        eligibility_path=eligibility_path,
        tool_fingerprints=tools,
    )
    expected_cells = tuple(
        ExpectedCellV1(
            repo="gin",
            question_id="gin-route-matching",
            arm=arm,
            repeat=0,
            agent_backend="codex",
            run_id=f"gin-route-matching__{arm}__codex__00",
        )
        for arm in ARMS
    )
    questions = {"gin": [question]}
    platform_name, environment = _environment_fingerprint()
    oracle = {
        key: question[key]
        for key in (
            "expected_key_points",
            "must_cite_files",
            "anti_hallucination_checks",
        )
    }
    manifest = create_manifest(
        benchmark_git_sha=_git_output(benchmark_repo, "rev-parse", "HEAD"),
        config_hash=selected_matrix_config_hash([repo], arms),
        question_hash=selected_questions_hash(questions),
        oracle_hash=_sha256(oracle),
        seed=seed,
        timeout_seconds=timeout_seconds,
        schedule_hash=selected_schedule_hash(
            [repo], arms, questions, repeats=1, agent_backend="codex"
        ),
        agent_backend="codex",
        model=model,
        agent_cli_fingerprint=agent_fingerprint,
        platform=platform_name,
        environment_fingerprint=environment,
        primary_session_id=session_id,
        retry_session_ids=(),
        expected_cells=expected_cells,
        required_arms=ARMS,
        indexed_arms=INDEXED_ARMS,
        tool_fingerprints=tools,
        repo_commits={"gin": str(repo["commit"])},
        repo_fingerprints={"gin": eligibility["repo_fingerprint"]},
        eligible_paths={"gin": tuple(eligibility["eligible_paths"])},
        eligible_paths_hashes={"gin": eligibility["eligible_paths_hash"]},
        parse_error_allowlists={"gin": ()},
        required_readiness_oracles=dict.fromkeys(
            INDEXED_ARMS, (READINESS_ORACLE,)
        ),
    )
    artifacts = destination / "artifacts"
    workspace_cells = []
    for arm in ARMS:
        artifact = artifacts / arm
        artifact.mkdir(parents=True)
        index_dir = {
            "native-only": None,
            "tsa-warm": checkouts[arm] / ".ast-cache",
            "codegraph-warm": checkouts[arm] / ".codegraph",
        }[arm]
        workspace_cells.append(
            {
                "arm_id": arm,
                "checkout_path": str(checkouts[arm]),
                "index_path": str(index_dir) if index_dir else None,
                "artifact_path": str(artifact.resolve()),
            }
        )
    manifest_path = destination / "experiment-manifest.json"
    workspace_path = destination / "workspace-evidence.json"
    _write_exclusive(manifest_path, asdict(manifest))
    _write_exclusive(
        workspace_path,
        {
            "schema_version": 1,
            "experiment_id": manifest.experiment_id,
            "manifest_hash": manifest.manifest_hash,
            "cells": workspace_cells,
        },
    )
    return {
        "manifest": manifest_path,
        "index_evidence": index_path,
        "eligibility": eligibility_path,
        "workspace": workspace_path,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout-root", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--seed", type=int, default=210021)
    args = parser.parse_args(argv)
    try:
        paths = freeze_smoke_plan(
            benchmark_repo=Path.cwd(),
            checkout_root=args.checkout_root,
            destination=args.destination,
            model=args.model,
            session_id=args.session_id,
            timeout_seconds=args.timeout_seconds,
            seed=args.seed,
        )
    except (OSError, subprocess.SubprocessError, TypeError, ValueError) as exc:
        print(f"Smoke plan failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({key: str(value) for key, value in paths.items()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
