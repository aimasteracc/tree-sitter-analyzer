"""Issue #1376：canary preflight 行为组，保留测试逻辑，文本 I/O 显式使用 UTF-8。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


class TestSmokeModelPreflight:
    def test_preflight_runs_exact_model_outside_benchmark_tree(self, tmp_path: Path):
        # Issue #1201: unconstrained prompts produced "Acknowledged." intermittently.
        from benchmarks.codegraph_compare import smoke_preflight

        identity = {
            "command": "codex --version",
            "version": "codex-cli 1.2.3",
            "executable": "/tools/codex",
            "executable_sha256": "a" * 64,
        }
        event = json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "type": "agent_message",
                    "text": json.dumps({"status": smoke_preflight.SENTINEL}),
                },
            }
        )
        output = tmp_path / "preflight.json"
        completed = subprocess.CompletedProcess([], 0, stdout=event, stderr="")

        with (
            patch.object(smoke_preflight, "_codex_identity", return_value=identity),
            patch.object(smoke_preflight, "_account_surface", return_value="ChatGPT"),
            patch.object(
                smoke_preflight.subprocess, "run", return_value=completed
            ) as run,
        ):
            evidence = smoke_preflight.run_model_preflight(
                model="gpt-fixture", output_path=output
            )

        command = run.call_args.args[0]
        assert command[command.index("--model") + 1] == "gpt-fixture"
        assert "--ephemeral" in command
        assert "--ignore-user-config" in command
        assert "--skip-git-repo-check" in command
        assert "--output-schema" in command
        assert Path(run.call_args.kwargs["cwd"]) != Path.cwd()
        assert evidence["status"] == "PASSED"
        assert json.loads(output.read_text(encoding="utf-8")) == evidence

    def test_preflight_rejects_unstructured_acknowledgement(self):
        # Issue #1201: availability must be proven by schema-bound output.
        from benchmarks.codegraph_compare import smoke_preflight

        event = json.dumps(
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "Acknowledged."},
            }
        )

        with pytest.raises(ValueError, match="terminal message is not JSON"):
            smoke_preflight._agent_message(event)

    @pytest.mark.parametrize(
        ("field", "value", "message"),
        [
            ("status", "FAILED", "not a successful V1 record"),
            ("model", "wrong-model", "does not match"),
            ("account_surface", "API", "not approved"),
            ("agent_cli_fingerprint", "stale", "stale or mismatched"),
        ],
    )
    def test_preflight_rejects_unbound_evidence(
        self, tmp_path: Path, field: str, value: str, message: str
    ):
        from benchmarks.codegraph_compare import smoke_preflight

        evidence = {
            "schema_version": 1,
            "status": "PASSED",
            "provider": "OpenAI",
            "account_surface": "ChatGPT",
            "model": "gpt-fixture",
            "checked_at": "2026-07-31T00:00:00+00:00",
            "agent_cli": {},
            "agent_cli_fingerprint": "bound",
            "sentinel_sha256": hashlib.sha256(
                smoke_preflight.SENTINEL.encode()
            ).hexdigest(),
        }
        evidence[field] = value
        path = tmp_path / "preflight.json"
        path.write_text(json.dumps(evidence), encoding="utf-8")

        with pytest.raises(ValueError, match=message):
            smoke_preflight.validate_model_preflight(
                path,
                expected_model="gpt-fixture",
                expected_cli_fingerprint="bound",
            )

    def test_preflight_rejects_stale_evidence_before_freeze(self, tmp_path: Path):
        from benchmarks.codegraph_compare import smoke_preflight

        path = tmp_path / "preflight.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "PASSED",
                    "provider": "OpenAI",
                    "account_surface": "ChatGPT",
                    "model": "gpt-fixture",
                    "checked_at": "2020-01-01T00:00:00+00:00",
                    "agent_cli": {},
                    "agent_cli_fingerprint": "bound",
                    "sentinel_sha256": hashlib.sha256(
                        smoke_preflight.SENTINEL.encode()
                    ).hexdigest(),
                }
            ),
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="stale or has a future timestamp"):
            smoke_preflight.validate_model_preflight(
                path,
                expected_model="gpt-fixture",
                expected_cli_fingerprint="bound",
                max_age_seconds=900,
            )


class TestCanaryLaunchPreflight:
    @staticmethod
    def _identity_probe(arm: str, executable: Path) -> dict[str, str]:
        if arm == "tsa-warm":
            return {
                "trusted_repo": "fixture",
                "entrypoint": "fixture",
                "entrypoint_sha256": "1" * 64,
                "source_root": "fixture",
                "source_sha256": "2" * 64,
                "dependency_lock": "fixture",
                "dependency_lock_sha256": "3" * 64,
            }
        return {
            "package": "@colbymchenry/codegraph@1.5.0",
            "version": "1.5.0",
        }

    @staticmethod
    def _fixture(tmp_path: Path):
        from benchmarks.codegraph_compare import canary_preflight

        checkout = tmp_path / "checkout"
        checkout.mkdir()
        tsa = Path(sys.executable)
        codegraph = Path(sys.executable)
        contracts = canary_preflight.build_canary_launch_contracts(
            checkout,
            tsa_executable=tsa,
            codegraph_executable=codegraph,
            identity_probe=TestCanaryLaunchPreflight._identity_probe,
        )
        return canary_preflight, checkout, tsa, codegraph, contracts

    def test_builder_pins_exact_tsa_nav_launch(self, tmp_path: Path):
        module, checkout, _tsa, _codegraph, contracts = self._fixture(tmp_path)

        contract = contracts[module.TSA_ARM]

        assert contract["args"] == [
            "-m",
            "tree_sitter_analyzer.mcp.server",
            "--project-root",
            str(checkout.resolve()),
        ]
        assert contract["enabled_tools"] == ["nav"]
        assert contract["required"] is True
        assert contract["network"] is False
        assert contract["env"] == {
            "PYTHONHASHSEED": "0",
            "PYTHONNOUSERSITE": "1",
            "TREE_SITTER_PROJECT_ROOT": str(checkout.resolve()),
        }
        assert contract["inherit_environment"] is False
        assert set(contract["tsa_identity"]) == {
            "trusted_repo",
            "entrypoint",
            "entrypoint_sha256",
            "source_root",
            "source_sha256",
            "dependency_lock",
            "dependency_lock_sha256",
        }
        assert contract["production_ready"] is False

    def test_builder_pins_exact_codegraph_search_launch(self, tmp_path: Path):
        module, checkout, _tsa, _codegraph, contracts = self._fixture(tmp_path)

        contract = contracts[module.CODEGRAPH_ARM]

        assert contract["package"] == "@colbymchenry/codegraph@1.5.0"
        assert contract["args"] == [
            "serve",
            "--mcp",
            "--no-watch",
            "-p",
            str(checkout.resolve()),
        ]
        assert contract["env"] == {
            "CODEGRAPH_MCP_TOOLS": "search",
            "CODEGRAPH_NO_DAEMON": "1",
            "CODEGRAPH_NO_UPDATE_CHECK": "1",
            "CODEGRAPH_TELEMETRY": "0",
            "PATH": os.defpath,
        }
        assert contract["enabled_tools"] == ["codegraph_search"]
        assert contract["required"] is True
        assert contract["network"] is False
        assert contract["inherit_environment"] is False
        assert contract["codegraph_identity"] == {
            "package": "@colbymchenry/codegraph@1.5.0",
            "version": "1.5.0",
        }
        assert contract["production_ready"] is False

    def test_builder_binds_absolute_executables_and_digests(self, tmp_path: Path):
        module, _checkout, tsa, codegraph, contracts = self._fixture(tmp_path)

        assert contracts[module.TSA_ARM]["command"] == str(tsa.resolve())
        assert (
            contracts[module.TSA_ARM]["executable_sha256"]
            == hashlib.sha256(tsa.read_bytes()).hexdigest()
        )
        assert contracts[module.CODEGRAPH_ARM]["command"] == str(codegraph.resolve())
        assert (
            contracts[module.CODEGRAPH_ARM]["executable_sha256"]
            == hashlib.sha256(codegraph.read_bytes()).hexdigest()
        )

    def test_builder_rejects_non_executable_server(self, tmp_path: Path):
        module, checkout, tsa, _codegraph, _contracts = self._fixture(tmp_path)
        codegraph = tmp_path / "codegraph"
        codegraph.write_bytes(b"not executable")

        with pytest.raises(ValueError, match="is not executable"):
            module.build_canary_launch_contracts(
                checkout,
                tsa_executable=tsa,
                codegraph_executable=codegraph,
                identity_probe=self._identity_probe,
            )

    def test_builder_rejects_untrusted_tsa_interpreter(self, tmp_path: Path):
        module, checkout, tsa, codegraph, _contracts = self._fixture(tmp_path)
        foreign = tmp_path / f"foreign-python{tsa.suffix}"
        shutil.copy2(tsa, foreign)

        with pytest.raises(ValueError, match="trusted repository interpreter"):
            module.build_canary_launch_contracts(
                checkout, tsa_executable=foreign, codegraph_executable=codegraph
            )

    def test_builder_rejects_wrong_codegraph_version(self, tmp_path: Path):
        module, checkout, tsa, codegraph, _contracts = self._fixture(tmp_path)

        def wrong_version(arm: str, executable: Path) -> dict[str, str]:
            if arm == module.CODEGRAPH_ARM:
                raise ValueError("CodeGraph version identity mismatch: '1.4.9'")
            return self._identity_probe(arm, executable)

        with pytest.raises(ValueError, match="version identity mismatch"):
            module.build_canary_launch_contracts(
                checkout,
                tsa_executable=tsa,
                codegraph_executable=codegraph,
                identity_probe=wrong_version,
            )

    def test_injected_identity_probe_marks_contract_as_scaffold(self, tmp_path: Path):
        from benchmarks.codegraph_compare import canary_preflight

        checkout = tmp_path / "checkout"
        checkout.mkdir()
        tsa = Path(sys.executable)
        codegraph = Path(sys.executable)

        contracts = canary_preflight.build_canary_launch_contracts(
            checkout,
            tsa_executable=tsa,
            codegraph_executable=codegraph,
            identity_probe=lambda arm, executable: {
                "fixture_arm": arm,
                "fixture_executable": str(executable),
            },
        )

        assert contracts["tsa-warm"]["production_ready"] is False
        assert contracts["codegraph-warm"]["production_ready"] is False

    @pytest.mark.parametrize(
        ("arm", "field", "value"),
        [
            ("tsa-warm", "args", ["--project-root", "/wrong"]),
            ("tsa-warm", "enabled_tools", ["search"]),
            ("tsa-warm", "required", False),
            ("tsa-warm", "network", True),
            ("tsa-warm", "executable_sha256", "0" * 64),
            ("codegraph-warm", "args", ["serve", "--mcp"]),
            ("codegraph-warm", "enabled_tools", ["search", "read"]),
            ("codegraph-warm", "env", {"CODEGRAPH_MCP_TOOLS": "search"}),
            ("codegraph-warm", "required", False),
            ("codegraph-warm", "executable_sha256", "f" * 64),
        ],
    )
    def test_validator_rejects_mutated_launch_surface(
        self, tmp_path: Path, arm: str, field: str, value: object
    ):
        module, checkout, tsa, codegraph, contracts = self._fixture(tmp_path)
        contracts[arm][field] = value

        with pytest.raises(ValueError, match="launch config hash is invalid"):
            module.validate_canary_launch_contracts(
                contracts,
                checkout,
                tsa_executable=tsa,
                codegraph_executable=codegraph,
                identity_probe=self._identity_probe,
            )

    def test_validator_rejects_rehashed_foreign_tool(self, tmp_path: Path):
        module, checkout, tsa, codegraph, contracts = self._fixture(tmp_path)
        contract = contracts[module.CODEGRAPH_ARM]
        contract["enabled_tools"] = ["read"]
        unsigned = {
            key: value for key, value in contract.items() if key != "launch_config_hash"
        }
        contract["launch_config_hash"] = module._sha256(unsigned)

        with pytest.raises(ValueError, match="codegraph-warm.enabled_tools"):
            module.validate_canary_launch_contracts(
                contracts,
                checkout,
                tsa_executable=tsa,
                codegraph_executable=codegraph,
                identity_probe=self._identity_probe,
            )

    def test_validator_rejects_rehashed_ambient_environment_inheritance(
        self, tmp_path: Path
    ):
        module, checkout, tsa, codegraph, contracts = self._fixture(tmp_path)
        contract = contracts[module.TSA_ARM]
        contract["inherit_environment"] = True
        unsigned = {
            key: value for key, value in contract.items() if key != "launch_config_hash"
        }
        contract["launch_config_hash"] = module._sha256(unsigned)

        with pytest.raises(ValueError, match="tsa-warm.inherit_environment"):
            module.validate_canary_launch_contracts(
                contracts,
                checkout,
                tsa_executable=tsa,
                codegraph_executable=codegraph,
                identity_probe=self._identity_probe,
            )

    def test_validator_accepts_exact_contracts(self, tmp_path: Path):
        module, checkout, tsa, codegraph, contracts = self._fixture(tmp_path)

        validated = module.validate_canary_launch_contracts(
            contracts,
            checkout,
            tsa_executable=tsa,
            codegraph_executable=codegraph,
            identity_probe=self._identity_probe,
        )

        assert validated == contracts


class TestCanaryWorkspaceImmutability:
    def _checkout(self, tmp_path: Path) -> Path:
        checkout = tmp_path / "checkout"
        checkout.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=checkout, check=True)
        subprocess.run(
            ["git", "config", "user.email", "canary@example.invalid"],
            cwd=checkout,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Canary"], cwd=checkout, check=True
        )
        (checkout / "gin.go").write_text("package gin\n", encoding="utf-8")
        (checkout / "README.md").write_text("fixture\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=checkout, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "fixture"], cwd=checkout, check=True
        )
        return checkout.resolve()

    def test_audit_records_exact_source_and_runtime_inventories(self, tmp_path: Path):
        from benchmarks.codegraph_compare.canary_workspace import (
            audit_canary_checkout,
            cleanup_and_verify_canary_checkout,
            snapshot_canary_checkout,
        )

        checkout = self._checkout(tmp_path)
        snapshot = snapshot_canary_checkout(checkout, "tsa-warm")
        runtime = checkout / ".ast-cache"
        runtime.mkdir()
        (runtime / "index.db").write_bytes(b"index")

        audit = audit_canary_checkout(snapshot)

        assert audit.checkout_root == checkout
        assert audit.head_commit == snapshot.head_commit
        assert audit.tracked_paths == ("README.md", "gin.go")
        assert audit.repository_fingerprint == snapshot.repository_fingerprint
        assert audit.source_after == audit.source_before
        assert audit.runtime_before == ()
        assert audit.runtime_after == (
            ("index.db", hashlib.sha256(b"index").hexdigest()),
        )
        cleanup_and_verify_canary_checkout(snapshot, audit)
        assert os.path.lexists(runtime) is False

    def test_runtime_inventory_includes_nested_git_metadata(self, tmp_path: Path):
        from benchmarks.codegraph_compare.canary_workspace import (
            audit_canary_checkout,
            snapshot_canary_checkout,
        )

        checkout = self._checkout(tmp_path)
        snapshot = snapshot_canary_checkout(checkout, "tsa-warm")
        runtime_git = checkout / ".ast-cache" / ".git"
        runtime_git.mkdir(parents=True)
        (runtime_git / "config").write_bytes(b"runtime-metadata")

        audit = audit_canary_checkout(snapshot)

        assert audit.runtime_after == (
            (
                ".git/config",
                hashlib.sha256(b"runtime-metadata").hexdigest(),
            ),
        )

    @pytest.mark.parametrize(
        ("mutation", "message"),
        [
            ("tracked", "tracked repository content changed"),
            ("new", "non-runtime checkout inventory changed"),
            ("delete", "tracked repository content changed"),
            ("rename", "tracked repository content changed"),
        ],
    )
    def test_audit_rejects_checkout_namespace_mutation(
        self, tmp_path: Path, mutation: str, message: str
    ):
        from benchmarks.codegraph_compare.canary_workspace import (
            audit_canary_checkout,
            snapshot_canary_checkout,
        )

        checkout = self._checkout(tmp_path)
        snapshot = snapshot_canary_checkout(checkout, "codegraph-warm")
        (checkout / ".codegraph").mkdir()
        if mutation == "tracked":
            (checkout / "gin.go").write_text("mutated\n", encoding="utf-8")
        elif mutation == "new":
            (checkout / "unprovenanced.txt").write_text("new\n", encoding="utf-8")
        elif mutation == "delete":
            (checkout / "gin.go").unlink()
        else:
            (checkout / "gin.go").rename(checkout / "renamed.go")

        with pytest.raises(ValueError, match=message):
            audit_canary_checkout(snapshot)

    def test_audit_rejects_symlinked_runtime_namespace(self, tmp_path: Path):
        from benchmarks.codegraph_compare.canary_workspace import (
            audit_canary_checkout,
            snapshot_canary_checkout,
        )

        checkout = self._checkout(tmp_path)
        snapshot = snapshot_canary_checkout(checkout, "tsa-warm")
        target = tmp_path / "escaped"
        target.mkdir()
        (checkout / ".ast-cache").symlink_to(target, target_is_directory=True)

        with pytest.raises(
            ValueError, match="runtime namespace must be a real directory"
        ):
            audit_canary_checkout(snapshot)

    def test_snapshot_rejects_cross_arm_namespace(self, tmp_path: Path):
        from benchmarks.codegraph_compare.canary_workspace import (
            snapshot_canary_checkout,
        )

        checkout = self._checkout(tmp_path)
        (checkout / ".codegraph").mkdir()

        with pytest.raises(ValueError, match="cross-arm runtime namespace"):
            snapshot_canary_checkout(checkout, "tsa-warm")

    def test_audit_rejects_hardlinked_runtime_file(self, tmp_path: Path):
        from benchmarks.codegraph_compare.canary_workspace import (
            audit_canary_checkout,
            snapshot_canary_checkout,
        )

        checkout = self._checkout(tmp_path)
        snapshot = snapshot_canary_checkout(checkout, "codegraph-warm")
        runtime = checkout / ".codegraph"
        runtime.mkdir()
        source = tmp_path / "shared.db"
        source.write_bytes(b"shared")
        os.link(source, runtime / "codegraph.db")

        with pytest.raises(ValueError, match="checkout inventory contains hardlink"):
            audit_canary_checkout(snapshot)

    def test_cleanup_restores_checkout_when_audit_failed(self, tmp_path: Path):
        from benchmarks.codegraph_compare.canary_workspace import (
            cleanup_and_verify_canary_checkout,
            snapshot_canary_checkout,
        )

        checkout = self._checkout(tmp_path)
        snapshot = snapshot_canary_checkout(checkout, "tsa-warm")
        runtime = checkout / ".ast-cache"
        runtime.mkdir()
        (runtime / "partial.db").write_bytes(b"partial")

        cleanup_and_verify_canary_checkout(snapshot, None)

        assert os.path.lexists(runtime) is False
