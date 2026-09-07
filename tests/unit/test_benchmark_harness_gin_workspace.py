"""Issue #1376：test_benchmark_harness_gin_workspace 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit._benchmark_harness_workspace_helpers import (
    TestGinSmokeWorkspace as _TestGinSmokeWorkspace,
)


class TestGinSmokeWorkspace(_TestGinSmokeWorkspace):
    def test_workspace_accepts_three_independent_clean_checkouts(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import (
            validate_workspace_v1,
        )

        manifest, _, workspace = self._fixture(tmp_path)

        validate_workspace_v1(workspace, manifest)

    def test_workspace_rejects_frozen_index_inside_checkout(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import validate_workspace_v1

        manifest, _, workspace = self._fixture(tmp_path)
        cell = workspace.cell("tsa-warm")
        object.__setattr__(cell, "index_path", cell.checkout_path)

        with pytest.raises(ValueError, match="frozen index overlaps checkout"):
            validate_workspace_v1(workspace, manifest)

    def test_workspace_rejects_existing_runtime_index(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import validate_workspace_v1

        manifest, _, workspace = self._fixture(tmp_path)
        (workspace.cell("tsa-warm").checkout_path / ".ast-cache").mkdir()

        with pytest.raises(ValueError, match="runtime index already exists"):
            validate_workspace_v1(workspace, manifest)

    def test_workspace_rejects_frozen_index_inside_artifact(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import validate_workspace_v1

        manifest, _, workspace = self._fixture(tmp_path)
        cell = workspace.cell("tsa-warm")
        object.__setattr__(cell, "index_path", cell.artifact_path)

        with pytest.raises(ValueError, match="frozen index overlaps artifact"):
            validate_workspace_v1(workspace, manifest)

    def test_workspace_rejects_hardlinked_frozen_index_file(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import validate_workspace_v1

        manifest, _, workspace = self._fixture(tmp_path)
        index = workspace.cell("tsa-warm").index_path
        expected_index = tmp_path / "frozen-indexes" / "tsa-warm" / ".ast-cache"
        assert index == expected_index
        (tmp_path / "alias.db").hardlink_to(expected_index / "index.db")

        with pytest.raises(ValueError, match="hardlinked file"):
            validate_workspace_v1(workspace, manifest)

    def test_cleanup_runtime_index_rejects_path_escape(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import cleanup_runtime_index

        checkout = tmp_path / "checkout"
        checkout.mkdir()
        outside = tmp_path / ".ast-cache"
        outside.mkdir()

        with pytest.raises(ValueError, match="runtime cleanup target mismatch"):
            cleanup_runtime_index(checkout, ".ast-cache", outside)

    def test_cleanup_runtime_index_removes_exact_runtime_tree(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import cleanup_runtime_index

        checkout = tmp_path / "checkout"
        runtime = checkout / ".ast-cache"
        runtime.mkdir(parents=True)
        (runtime / "index.db").write_bytes(b"index")

        cleanup_runtime_index(checkout, ".ast-cache", runtime)

        assert runtime.exists() is False

    @pytest.mark.parametrize(
        "target_kind", ("dotdot", "broken_symlink", "checkout", "baseline", "root")
    )
    def test_cleanup_rejects_unsafe_target(self, tmp_path: Path, target_kind: str):
        from benchmarks.codegraph_compare.smoke_workspace import cleanup_runtime_index

        checkout = tmp_path / "checkout"
        checkout.mkdir()
        baseline = tmp_path / "baseline"
        baseline.mkdir()
        targets = {
            "dotdot": checkout / ".." / ".ast-cache",
            "broken_symlink": checkout / ".ast-cache",
            "checkout": checkout,
            "baseline": baseline,
            "root": Path("/"),
        }
        target = targets[target_kind]
        if target_kind == "broken_symlink":
            target.symlink_to(tmp_path / "missing")
        with pytest.raises(ValueError, match="runtime cleanup"):
            cleanup_runtime_index(checkout, ".ast-cache", target)

    def test_workspace_rejects_cross_arm_artifact_collision(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import (
            parse_workspace_v1,
            validate_workspace_v1,
        )

        manifest, raw, _ = self._fixture(tmp_path)
        raw["cells"][1]["artifact_path"] = raw["cells"][0]["artifact_path"]

        with pytest.raises(ValueError, match="artifact namespace collision"):
            validate_workspace_v1(parse_workspace_v1(raw), manifest)

    def test_workspace_rejects_foreign_index_in_native_checkout(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import (
            validate_workspace_v1,
        )

        manifest, _, workspace = self._fixture(tmp_path)
        (workspace.cell("native-only").checkout_path / ".codegraph").mkdir()

        with pytest.raises(ValueError, match="foreign index namespace"):
            validate_workspace_v1(workspace, manifest)

    def test_workspace_rejects_untracked_checkout_input(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import (
            validate_workspace_v1,
        )

        manifest, _, workspace = self._fixture(tmp_path)
        (workspace.cell("native-only").checkout_path / "misleading.md").write_text(
            "not part of the pinned repository\n", encoding="utf-8"
        )

        with pytest.raises(ValueError, match="unprovenanced paths"):
            validate_workspace_v1(workspace, manifest)

    def test_workspace_rejects_symlinked_index_namespace(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import (
            parse_workspace_v1,
            validate_workspace_v1,
        )

        manifest, raw, workspace = self._fixture(tmp_path)
        tsa_index = workspace.cell("tsa-warm").index_path
        assert tsa_index.name == ".ast-cache"
        (tsa_index / "index.db").unlink()
        tsa_index.rmdir()
        external = tmp_path / "shared-index"
        external.mkdir()
        tsa_index.symlink_to(external, target_is_directory=True)
        raw["cells"][1]["index_path"] = str(tsa_index)

        with pytest.raises(ValueError, match="index namespace contains a symlink"):
            validate_workspace_v1(parse_workspace_v1(raw), manifest)

    def test_workspace_rejects_symlinked_ancestor(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import (
            parse_workspace_v1,
            validate_workspace_v1,
        )

        manifest, raw, workspace = self._fixture(tmp_path)
        checkout = workspace.cell("native-only").checkout_path
        alias = tmp_path / "checkout-alias"
        alias.symlink_to(checkout.parent, target_is_directory=True)
        raw["cells"][0]["checkout_path"] = str(alias / checkout.name)

        with pytest.raises(ValueError, match="contains a symlink"):
            validate_workspace_v1(parse_workspace_v1(raw), manifest)

    def test_workspace_rejects_symlink_nested_in_index(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import (
            validate_workspace_v1,
        )

        manifest, _, workspace = self._fixture(tmp_path)
        index = workspace.cell("tsa-warm").index_path
        assert index.name == ".ast-cache"
        (index / "external.db").symlink_to(tmp_path / "outside.db")

        with pytest.raises(ValueError, match="contains a special node"):
            validate_workspace_v1(workspace, manifest)

    def test_workspace_rejects_index_content_not_bound_to_manifest(
        self, tmp_path: Path
    ):
        from dataclasses import replace

        from benchmarks.codegraph_compare.smoke_evidence import (
            index_content_hash,
        )
        from benchmarks.codegraph_compare.smoke_workspace import (
            validate_index_content_v1,
            validate_workspace_v1,
        )

        manifest, _, workspace = self._fixture(tmp_path)
        tsa_index = workspace.cell("tsa-warm").index_path
        codegraph_index = workspace.cell("codegraph-warm").index_path
        assert tsa_index.name == ".ast-cache"
        assert codegraph_index.name == ".codegraph"
        hashes = tuple(
            (
                arm,
                index_content_hash(index),
            )
            for arm, index in (
                ("tsa-warm", tsa_index),
                ("codegraph-warm", codegraph_index),
            )
        )
        bound_manifest = replace(manifest, index_content_hashes=hashes)
        validate_workspace_v1(workspace, bound_manifest)
        (tsa_index / "tampered.db").write_bytes(b"foreign index bytes")

        with pytest.raises(ValueError, match="index content hash mismatch"):
            validate_workspace_v1(workspace, bound_manifest)

        with pytest.raises(ValueError, match="index content hash mismatch"):
            validate_index_content_v1(workspace, bound_manifest, "tsa-warm")

    def test_workspace_schema_rejects_unknown_fields(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import (
            parse_workspace_v1,
        )

        _, raw, _ = self._fixture(tmp_path)
        raw["undeclared"] = True

        with pytest.raises(ValueError, match="workspace keys mismatch"):
            parse_workspace_v1(raw)
