"""Model-free MCP launch-contract preflight for NO1-002C canary arms."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from benchmarks.codegraph_compare.adapters import CODEGRAPH_NPM_PACKAGE

SCHEMA_VERSION = 1
TSA_ARM = "tsa-warm"
CODEGRAPH_ARM = "codegraph-warm"
_ANALYZER_ROOT = Path(__file__).resolve().parents[2]


def _sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _executable(path: Path) -> tuple[str, str]:
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"Canary executable is not a file: {resolved}")
    windows_suffixes = {
        suffix.lower()
        for suffix in os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(";")
    }
    executable = (
        resolved.suffix.lower() in windows_suffixes
        if os.name == "nt"
        else os.access(resolved, os.X_OK)
    )
    if not executable:
        raise ValueError(f"Canary executable is not executable: {resolved}")
    return str(resolved), hashlib.sha256(resolved.read_bytes()).hexdigest()


def _tree_digest(root: Path) -> str:
    records = [
        (
            path.relative_to(root).as_posix(),
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in sorted(root.rglob("*.py"))
        if path.is_file()
    ]
    return _sha256({"files": records})


def _tsa_identity(executable: Path) -> dict[str, str]:
    source = _ANALYZER_ROOT / "tree_sitter_analyzer"
    lock = _ANALYZER_ROOT / "uv.lock"
    if not source.is_dir() or not lock.is_file():
        raise ValueError("TSA source or dependency lock is unavailable")
    trusted_python = Path(sys.executable).resolve(strict=True)
    if executable.resolve(strict=True) != trusted_python:
        raise ValueError("TSA executable is not the trusted repository interpreter")
    entrypoint = source / "mcp" / "server.py"
    if not entrypoint.is_file():
        raise ValueError("TSA trusted MCP entrypoint is unavailable")
    return {
        "trusted_repo": str(_ANALYZER_ROOT),
        "entrypoint": str(entrypoint.resolve()),
        "entrypoint_sha256": hashlib.sha256(entrypoint.read_bytes()).hexdigest(),
        "source_root": str(source.resolve()),
        "source_sha256": _tree_digest(source),
        "dependency_lock": str(lock.resolve()),
        "dependency_lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
    }


def _codegraph_identity(executable: Path) -> dict[str, str]:
    result = subprocess.run(
        [str(executable), "--version"],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
        env={
            "CODEGRAPH_NO_DAEMON": "1",
            "CODEGRAPH_NO_UPDATE_CHECK": "1",
            "CODEGRAPH_TELEMETRY": "0",
            "PATH": os.defpath,
        },
    )
    version = (result.stdout or result.stderr).strip()
    if version != "1.5.0":
        raise ValueError(f"CodeGraph version identity mismatch: {version!r}")
    return {"package": CODEGRAPH_NPM_PACKAGE, "version": version}


IdentityProbe = Callable[[str, Path], dict[str, str]]


def _production_identity_probe(arm: str, executable: Path) -> dict[str, str]:
    if arm == TSA_ARM:
        return _tsa_identity(executable)
    if arm == CODEGRAPH_ARM:
        return _codegraph_identity(executable)
    raise ValueError(f"unsupported identity arm: {arm}")


def _seal(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, "launch_config_hash": _sha256(payload)}


def build_canary_launch_contracts(
    checkout: Path,
    *,
    tsa_executable: Path,
    codegraph_executable: Path,
    identity_probe: IdentityProbe | None = None,
) -> dict[str, dict[str, Any]]:
    """Build exact, hash-bound MCP launch contracts for both indexed arms."""

    resolved_checkout = checkout.resolve(strict=True)
    if not resolved_checkout.is_dir():
        raise ValueError(f"Canary checkout is not a directory: {resolved_checkout}")
    root = str(resolved_checkout)
    tsa_command, tsa_digest = _executable(tsa_executable)
    codegraph_command, codegraph_digest = _executable(codegraph_executable)
    common = {
        "schema_version": SCHEMA_VERSION,
        "required": True,
        "network": False,
        "inherit_environment": False,
    }
    probe = identity_probe or _production_identity_probe
    tsa_identity = probe(TSA_ARM, Path(tsa_command))
    codegraph_identity = probe(CODEGRAPH_ARM, Path(codegraph_command))
    if not tsa_identity or not codegraph_identity:
        raise ValueError("canary identity probe returned incomplete evidence")
    tsa = _seal(
        {
            **common,
            "arm": TSA_ARM,
            "server": "tree-sitter-analyzer",
            "command": tsa_command,
            "args": [
                "-m",
                "tree_sitter_analyzer.mcp.server",
                "--project-root",
                root,
            ],
            "env": {
                "PYTHONHASHSEED": "0",
                "PYTHONNOUSERSITE": "1",
                "TREE_SITTER_PROJECT_ROOT": root,
            },
            "enabled_tools": ["nav"],
            "executable_sha256": tsa_digest,
            "tsa_identity": tsa_identity,
            "production_ready": False,
        }
    )
    codegraph = _seal(
        {
            **common,
            "arm": CODEGRAPH_ARM,
            "server": "codegraph",
            "package": CODEGRAPH_NPM_PACKAGE,
            "command": codegraph_command,
            "args": ["serve", "--mcp", "--no-watch", "-p", root],
            "env": {
                "CODEGRAPH_MCP_TOOLS": "search",
                "CODEGRAPH_NO_DAEMON": "1",
                "CODEGRAPH_NO_UPDATE_CHECK": "1",
                "CODEGRAPH_TELEMETRY": "0",
                "PATH": os.defpath,
            },
            "enabled_tools": ["codegraph_search"],
            "executable_sha256": codegraph_digest,
            "codegraph_identity": codegraph_identity,
            "production_ready": False,
        }
    )
    return {TSA_ARM: tsa, CODEGRAPH_ARM: codegraph}


def validate_canary_launch_contracts(
    contracts: dict[str, Any],
    checkout: Path,
    *,
    tsa_executable: Path,
    codegraph_executable: Path,
    identity_probe: IdentityProbe | None = None,
) -> dict[str, dict[str, Any]]:
    """Reject any launch surface not identical to the model-free contract."""

    expected = build_canary_launch_contracts(
        checkout,
        tsa_executable=tsa_executable,
        codegraph_executable=codegraph_executable,
        identity_probe=identity_probe,
    )
    if set(contracts) != set(expected):
        raise ValueError("Canary launch contracts have an invalid arm set")
    for arm, expected_contract in expected.items():
        observed = contracts.get(arm)
        if not isinstance(observed, dict):
            raise ValueError(f"Canary launch contract is not an object: {arm}")
        if set(observed) != set(expected_contract):
            raise ValueError(f"Canary launch contract has an invalid field set: {arm}")
        unsigned = {
            key: value for key, value in observed.items() if key != "launch_config_hash"
        }
        if observed["launch_config_hash"] != _sha256(unsigned):
            raise ValueError(f"Canary launch config hash is invalid: {arm}")
        for key, value in expected_contract.items():
            if observed[key] != value:
                raise ValueError(f"Canary launch contract mismatch: {arm}.{key}")
    return expected
