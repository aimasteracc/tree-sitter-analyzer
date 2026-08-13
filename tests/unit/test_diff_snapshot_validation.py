"""Authority, generation, and deadline coverage for diff snapshots."""

from __future__ import annotations

from pathlib import Path

import pytest

import tree_sitter_analyzer.diff_snapshot_registry as snapshots
from tests.unit._diff_snapshot_support import install_fake_snapshot_materializer


def _created(tmp_path: Path, monkeypatch):
    install_fake_snapshot_materializer(monkeypatch, tmp_path)
    registry = snapshots.DiffSnapshotRegistry()
    result = registry.create(str(tmp_path), "diff", [])
    return tmp_path, registry, result


def test_create_rejects_lifetime_elapsed_during_materialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = [0.0]
    install_fake_snapshot_materializer(monkeypatch, tmp_path)
    registry = snapshots.DiffSnapshotRegistry(clock=lambda: now[0])
    capture = snapshots._capture_payload

    def finish_after_expiry(*args, **kwargs):
        result = capture(*args, **kwargs)
        now[0] = snapshots.HARD_LIFETIME_SECONDS
        return result

    monkeypatch.setattr(snapshots, "_capture_payload", finish_after_expiry)

    result = registry.create(str(tmp_path), "diff", [])

    assert result == {"success": False, "error_code": "DIFF_SNAPSHOT_TIMEOUT"}
    assert registry.stats() == (0, 0)


def test_create_rechecks_capacity_after_materialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fake_snapshot_materializer(monkeypatch, tmp_path)
    registry = snapshots.DiffSnapshotRegistry()
    capture = snapshots._capture_payload

    def reserve_capacity_while_capturing(*args, **kwargs):
        result = capture(*args, **kwargs)
        registry._reservations["competing"] = snapshots.MAX_MATERIALIZED_BYTES + 1
        return result

    monkeypatch.setattr(snapshots, "_capture_payload", reserve_capacity_while_capturing)

    result = registry.create(str(tmp_path), "diff", [])

    assert result == {"success": False, "error_code": "DIFF_SNAPSHOT_CAPACITY"}
    assert registry.stats() == (0, 0)


def test_validate_publish_rejects_generation_change_during_validation(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path
    identity = install_fake_snapshot_materializer(monkeypatch, root)
    registry = snapshots.DiffSnapshotRegistry()
    created = registry.create(str(root), "diff", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(root))
    assert error is None
    assert consumer is not None
    generations = iter(("before", "after"))
    monkeypatch.setattr(
        snapshots,
        "oracle_generation",
        lambda *args, **kwargs: (next(generations), identity),
    )

    result = registry.validate_publish(consumer)

    assert result == "DIFF_SNAPSHOT_SOURCE_CHANGED"
    consumer.release()


def test_validate_publish_rejects_consumer_released_by_publish_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, registry, created = _created(tmp_path, monkeypatch)
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(root))
    assert error is None
    assert consumer is not None

    result = registry.validate_publish(consumer, publish_guard=consumer.release)

    assert result == "DIFF_SNAPSHOT_EXPIRED"


def test_generic_snapshot_records_unsafe_constraint_config(tmp_path, monkeypatch):
    # PR #1254 review 3769193867: generic consumers remain config-independent.
    install_fake_snapshot_materializer(monkeypatch, tmp_path)
    from tree_sitter_analyzer.source_oracle import SafePath

    monkeypatch.setattr(
        snapshots,
        "safe_workspace_path",
        lambda *_a, **_k: SafePath(None, (), "symlink"),
    )
    registry = snapshots.DiffSnapshotRegistry()
    result = registry.create(str(tmp_path), "diff", [])
    consumer, error = registry.acquire(str(result["diff_snapshot_id"]), str(tmp_path))

    assert (result["success"], error, consumer is not None) == (True, None, True)
    assert consumer is not None
    assert consumer.snapshot.constraint_config_error == "CONSTRAINT_CONFIG_UNSAFE"
    consumer.release()


def test_generic_snapshot_records_oversized_constraint_config(tmp_path, monkeypatch):
    # PR #1254 review 3769193867: the generic capability survives config limits.
    install_fake_snapshot_materializer(monkeypatch, tmp_path)

    def oversized(*_args, **_kwargs):
        raise snapshots.SourceOracleError("DIFF_SNAPSHOT_CAPACITY")

    monkeypatch.setattr(snapshots, "safe_workspace_path", oversized)
    registry = snapshots.DiffSnapshotRegistry()
    result = registry.create(str(tmp_path), "diff", [])
    consumer, error = registry.acquire(str(result["diff_snapshot_id"]), str(tmp_path))

    assert (result["success"], error, consumer is not None) == (True, None, True)
    assert consumer is not None
    assert consumer.snapshot.constraint_config_error == "CONSTRAINT_CONFIG_CAPACITY"
    consumer.release()


def test_staged_snapshot_requires_production_git_epoch(tmp_path, monkeypatch):
    install_fake_snapshot_materializer(monkeypatch, tmp_path)
    identity = snapshots.RootIdentity(str(tmp_path.resolve()), 1, 2)

    def production_shape(
        root, mode="diff", *, deadline=None, manifest=None, epoch_out=None
    ):
        return "sg_test", identity

    monkeypatch.setattr(snapshots, "oracle_generation", production_shape)
    result = snapshots.DiffSnapshotRegistry().create(str(tmp_path), "staged", [])
    assert result == {"success": False, "error_code": "DIFF_SNAPSHOT_GIT_ERROR"}


def test_snapshot_rejects_final_git_generation_drift(tmp_path, monkeypatch):
    install_fake_snapshot_materializer(monkeypatch, tmp_path)
    identity = snapshots.RootIdentity(str(tmp_path.resolve()), 1, 2)
    calls = 0

    def drift(root, mode="diff", *, deadline=None, manifest=None):
        nonlocal calls
        calls += 1
        return ("changed" if calls == 3 else "sg_test"), identity

    monkeypatch.setattr(snapshots, "oracle_generation", drift)
    result = snapshots.DiffSnapshotRegistry().create(str(tmp_path), "diff", [])
    assert result == {"success": False, "error_code": "DIFF_SNAPSHOT_SOURCE_CHANGED"}


def test_shared_generation_preserves_oracle_monkeypatch_seam(monkeypatch) -> None:
    def oracle(*_args, **_kwargs):
        return "generation", None

    observed = []

    def resolve(root, deadline, *, oracle_generation):
        observed.append((root, deadline, oracle_generation))
        return "shared"

    monkeypatch.setattr(snapshots, "oracle_generation", oracle)
    monkeypatch.setattr(snapshots, "resolve_shared_source_generation", resolve)

    assert snapshots.shared_source_generation("/repo", 4.0) == "shared"
    assert observed == [("/repo", 4.0, oracle)]


def test_shared_generation_uses_fresh_reusable_capability(monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace

    import tree_sitter_analyzer.index_snapshot as index_snapshot

    @contextmanager
    def reusable(_root):
        yield SimpleNamespace(source_generation="idxsrc-v3:fresh")

    monkeypatch.setattr(index_snapshot, "lease_reusable_snapshot", reusable)
    assert (
        snapshots.shared_source_generation("/repo", float("inf")) == "idxsrc-v3:fresh"
    )


def test_shared_generation_falls_back_to_direct_oracle_for_incompatible_index(
    monkeypatch,
):
    # PR #1254 review 3766246594: source-only capture must not require graph usability.
    from contextlib import contextmanager
    from types import SimpleNamespace

    import tree_sitter_analyzer.index_snapshot as index_snapshot
    import tree_sitter_analyzer.index_source_snapshot as source_snapshot

    @contextmanager
    def none(_root):
        yield None

    @contextmanager
    def incompatible(_root):
        yield SimpleNamespace(source_generation=None, reason="INCOMPATIBLE_SCHEMA")

    captures = []

    def capture(root, *, deadline):
        captures.append((root, deadline))
        return SimpleNamespace(
            state="exact", generation="idxsrc-v3:direct", reason=None
        )

    monkeypatch.setattr(index_snapshot, "lease_reusable_snapshot", none)
    monkeypatch.setattr(index_snapshot, "lease_existing_snapshot", incompatible)
    monkeypatch.setattr(source_snapshot, "capture_current_source_snapshot", capture)

    result = snapshots.shared_source_generation("/repo", float("inf"))

    assert (result, captures) == (
        "idxsrc-v3:direct",
        [("/repo", float("inf"))],
    )


def test_shared_generation_uses_existing_index_token(monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace

    import tree_sitter_analyzer.index_snapshot as index_snapshot

    @contextmanager
    def none(_root):
        yield None

    @contextmanager
    def existing(_root):
        yield SimpleNamespace(source_generation="idxsrc-v3:existing", reason=None)

    monkeypatch.setattr(index_snapshot, "lease_reusable_snapshot", none)
    monkeypatch.setattr(index_snapshot, "lease_existing_snapshot", existing)
    assert snapshots.shared_source_generation("/repo", float("inf")) == (
        "idxsrc-v3:existing"
    )


def test_shared_generation_deadline_is_exact(monkeypatch):
    monkeypatch.setattr(snapshots.time, "monotonic", lambda: 2.0)
    with pytest.raises(snapshots.SourceOracleError, match="DIFF_SNAPSHOT_TIMEOUT"):
        snapshots.shared_source_generation("/repo", 1.0)


def test_staged_snapshot_preserves_live_config_metadata_when_index_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tree_sitter_analyzer.source_epoch import GitEpoch

    install_fake_snapshot_materializer(monkeypatch, tmp_path)
    config = tmp_path / "architectural-constraints.yml"
    config.write_bytes(b"version: 1\nconstraints: []\n")
    live = snapshots.safe_workspace_path(
        str(tmp_path.resolve()), config.name, deadline=float("inf"), limit=1024 * 1024
    )
    epoch = GitEpoch(b"head", "sha1", (), (), (), ())
    identity = snapshots.RootIdentity(str(tmp_path.resolve()), 1, 2)

    def oracle(root, mode="diff", *, deadline=None, manifest=None, epoch_out=None):
        if epoch_out is not None:
            epoch_out.append(epoch)
        return "sg_test", identity

    monkeypatch.setattr(snapshots, "oracle_generation", oracle)
    monkeypatch.setattr(
        snapshots,
        "frozen_index_constraint_config",
        lambda *_a, **_k: (config.name, live.data, ("index-metadata",)),
    )
    registry = snapshots.DiffSnapshotRegistry()
    result = registry.create(str(tmp_path), "staged", [])
    consumer, error = registry.acquire(str(result["diff_snapshot_id"]), str(tmp_path))

    assert error is None
    assert consumer is not None
    assert (
        consumer.snapshot.constraint_config_path,
        consumer.snapshot.constraint_config_data,
        consumer.snapshot.constraint_config_metadata,
        consumer.snapshot.staged_config_matches_worktree,
    ) == (config.name, live.data, live.metadata, True)
    consumer.release()


def test_staged_snapshot_retains_index_config_metadata_when_worktree_differs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tree_sitter_analyzer.source_epoch import GitEpoch

    install_fake_snapshot_materializer(monkeypatch, tmp_path)
    epoch = GitEpoch(b"head", "sha1", (), (), (), ())
    identity = snapshots.RootIdentity(str(tmp_path.resolve()), 1, 2)

    def oracle(root, mode="diff", *, deadline=None, manifest=None, epoch_out=None):
        if epoch_out is not None:
            epoch_out.append(epoch)
        return "sg_test", identity

    monkeypatch.setattr(snapshots, "oracle_generation", oracle)
    monkeypatch.setattr(
        snapshots,
        "frozen_index_constraint_config",
        lambda *_a, **_k: (
            "architectural-constraints.yml",
            b"version: 1\nconstraints: []\n",
            ("index-metadata",),
        ),
    )
    registry = snapshots.DiffSnapshotRegistry()
    result = registry.create(str(tmp_path), "staged", [])
    consumer, error = registry.acquire(str(result["diff_snapshot_id"]), str(tmp_path))

    assert error is None
    assert consumer is not None
    assert (
        consumer.snapshot.constraint_config_metadata,
        consumer.snapshot.staged_config_matches_worktree,
    ) == (("index-metadata",), False)
    consumer.release()


def test_snapshot_constraint_config_directory_falls_back_to_second_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fake_snapshot_materializer(monkeypatch, tmp_path)
    (tmp_path / "architectural-constraints.yml").mkdir()
    fallback = tmp_path / ".tree-sitter-analyzer" / "constraints.yml"
    fallback.parent.mkdir()
    fallback.write_text("version: 1\nconstraints: []\n")

    registry = snapshots.DiffSnapshotRegistry()
    created = registry.create(str(tmp_path), "diff", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(tmp_path))

    assert error is None
    assert consumer is not None
    assert consumer.snapshot.constraint_config_path == (
        ".tree-sitter-analyzer/constraints.yml"
    )
    assert consumer.snapshot.constraint_config_data == fallback.read_bytes()
    consumer.release()


def test_acquire_rejects_elapsed_caller_deadline_and_releases_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fake_snapshot_materializer(monkeypatch, tmp_path)
    registry = snapshots.DiffSnapshotRegistry(clock=lambda: 5.0)
    created = registry.create(str(tmp_path), "diff", [])

    consumer, error = registry.acquire(
        str(created["diff_snapshot_id"]), str(tmp_path), deadline=5.0
    )

    assert (consumer, error) == (None, "DIFF_SNAPSHOT_EXPIRED")
    state = registry._states[str(created["diff_snapshot_id"])]
    assert state.pins == {}


def test_validate_publish_rejects_elapsed_caller_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fake_snapshot_materializer(monkeypatch, tmp_path)
    registry = snapshots.DiffSnapshotRegistry(clock=lambda: 5.0)
    created = registry.create(str(tmp_path), "diff", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(tmp_path))
    assert error is None
    assert consumer is not None

    result = registry.validate_publish(consumer, deadline=5.0)

    assert result == "DIFF_SNAPSHOT_EXPIRED"
    consumer.release()


def test_validate_publish_bounds_oracle_by_remaining_lifetime(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1252 review thread 3746940417.
    now = [0.0]
    root = tmp_path
    install_fake_snapshot_materializer(monkeypatch, root)
    registry = snapshots.DiffSnapshotRegistry(clock=lambda: now[0])
    created = registry.create(str(root), "diff", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(root))
    assert error is None
    assert consumer is not None
    now[0] = snapshots.HARD_LIFETIME_SECONDS - 1.0
    deadlines: list[float] = []
    monkeypatch.setattr(snapshots.time, "monotonic", lambda: 100.0)

    def oracle_with_deadline(root, mode, *, deadline=None):
        deadlines.append(deadline)
        return consumer.snapshot.source_generation, consumer.snapshot.root_identity

    monkeypatch.setattr(snapshots, "oracle_generation", oracle_with_deadline)

    result = registry.validate_publish(consumer)

    assert result is None
    assert deadlines == [35.0, 35.0]
    consumer.release()


def test_staged_submodule_probe_failure_remains_constraint_scoped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #1254 review 3771670605: ast_diff/classify snapshots stay available.
    import tree_sitter_analyzer.diff_snapshot_constraints as constraints
    from tree_sitter_analyzer.source_epoch import GitEpoch

    install_fake_snapshot_materializer(monkeypatch, tmp_path)
    epoch = GitEpoch(b"head", "sha1", (), (), (), ())
    identity = snapshots.RootIdentity(str(tmp_path.resolve()), 1, 2)

    def oracle(root, mode="diff", *, deadline=None, manifest=None, epoch_out=None):
        if epoch_out is not None:
            epoch_out.append(epoch)
        return "sg_test", identity

    def rejected(*_args, **_kwargs):
        raise snapshots.SourceOracleError("DIFF_SNAPSHOT_GIT_ERROR")

    monkeypatch.setattr(snapshots, "oracle_generation", oracle)
    monkeypatch.setattr(constraints, "frozen_index_output", rejected)
    monkeypatch.setattr(
        snapshots,
        "staged_sources_match_worktree",
        constraints.staged_sources_match_worktree,
    )
    registry = snapshots.DiffSnapshotRegistry()

    created = registry.create(str(tmp_path), "staged", [])
    consumer, error = registry.acquire(str(created["diff_snapshot_id"]), str(tmp_path))

    assert (created["success"], error, consumer is not None) == (True, None, True)
    assert consumer is not None
    assert consumer.snapshot.staged_source_matches_worktree is False
    consumer.release()


@pytest.mark.parametrize(
    "failure",
    [RuntimeError("oracle failed"), KeyboardInterrupt("oracle cancelled")],
)
def test_acquire_releases_pin_after_unexpected_oracle_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: BaseException
) -> None:
    # PR #1254 final zero-gate: recoverable failures cannot exhaust snapshot slots.
    root, registry, created = _created(tmp_path, monkeypatch)

    def fail(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(snapshots, "oracle_generation", fail)

    with pytest.raises(type(failure), match=f"^{failure}$"):
        registry.acquire(str(created["diff_snapshot_id"]), str(root))

    assert next(iter(registry._states.values())).pins == {}
