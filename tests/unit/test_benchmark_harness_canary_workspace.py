"""Issue #1376：test_benchmark_harness_canary_workspace 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest


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
