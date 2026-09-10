"""Issue #1376：test_benchmark_harness_gin_index_snapshot 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from tests.unit._benchmark_harness_workspace_helpers import (
    TestGinSmokeWorkspace as _TestGinSmokeWorkspace,
)


class TestGinSmokeWorkspace(_TestGinSmokeWorkspace):
    def test_freeze_index_baselines_moves_indexes_out_of_checkouts(
        self, tmp_path: Path
    ):
        from benchmarks.codegraph_compare.smoke_plan import freeze_index_baselines

        checkouts = {}
        for arm, name in (
            ("tsa-warm", ".ast-cache"),
            ("codegraph-warm", ".codegraph"),
        ):
            checkout = tmp_path / "checkouts" / arm / "gin"
            index = checkout / name
            index.mkdir(parents=True)
            database_name = "index.db" if arm == "tsa-warm" else "codegraph.db"
            connection = sqlite3.connect(index / database_name)
            if arm == "tsa-warm":
                connection.execute(
                    "CREATE TABLE ast_index(file_path TEXT, symbols_json TEXT)"
                )
                connection.execute(
                    "INSERT INTO ast_index VALUES ('gin.go', 'ServeHTTP')"
                )
            else:
                connection.execute("CREATE TABLE nodes(file_path TEXT, name TEXT)")
                connection.execute("INSERT INTO nodes VALUES ('gin.go', 'ServeHTTP')")
            connection.commit()
            connection.close()
            checkouts[arm] = checkout

        frozen = freeze_index_baselines(
            checkouts,
            tmp_path / "checkouts",
            {"tsa-warm": ("gin.go",), "codegraph-warm": ("gin.go",)},
        )

        assert tuple(sorted(frozen)) == ("codegraph-warm", "tsa-warm")
        assert tuple(
            (checkouts[arm] / name).exists()
            for arm, name in (
                ("tsa-warm", ".ast-cache"),
                ("codegraph-warm", ".codegraph"),
            )
        ) == (False, False)
        assert tuple(path.parent.parent.name for path in frozen.values()) == (
            "frozen-indexes",
            "frozen-indexes",
        )

    def test_snapshot_includes_committed_wal_with_open_writer(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import (
            create_frozen_index_snapshot,
        )

        baseline = tmp_path / "baseline" / ".codegraph"
        baseline.mkdir(parents=True)
        connection = sqlite3.connect(baseline / "codegraph.db")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE nodes (file_path TEXT, name TEXT)")
        connection.execute("INSERT INTO nodes VALUES ('gin.go', 'ServeHTTP')")
        connection.commit()
        assert ((baseline / "codegraph.db-wal").stat().st_size == 0) is False
        frozen = create_frozen_index_snapshot(
            baseline,
            tmp_path / "frozen" / ".codegraph",
            "codegraph-warm",
            ("gin.go",),
        )
        connection.close()
        assert sqlite3.connect(frozen / "codegraph.db").execute(
            "SELECT file_path, name FROM nodes"
        ).fetchone() == ("gin.go", "ServeHTTP")

    def test_snapshot_excludes_uncommitted_rows(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import (
            create_frozen_index_snapshot,
        )

        source = tmp_path / "live" / ".codegraph"
        source.mkdir(parents=True)
        writer = sqlite3.connect(source / "codegraph.db")
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("CREATE TABLE nodes(file_path TEXT, name TEXT)")
        writer.execute("INSERT INTO nodes VALUES ('gin.go', 'ServeHTTP')")
        writer.commit()
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("INSERT INTO nodes VALUES ('secret.go', 'Uncommitted')")
        try:
            frozen = create_frozen_index_snapshot(
                source,
                tmp_path / "frozen" / ".codegraph",
                "codegraph-warm",
                ("gin.go",),
            )
        finally:
            writer.rollback()
            writer.close()
        assert sqlite3.connect(frozen / "codegraph.db").execute(
            "SELECT file_path FROM nodes ORDER BY file_path"
        ).fetchall() == [("gin.go",)]

    def test_snapshot_rejects_multiple_primary_databases(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import (
            create_frozen_index_snapshot,
        )

        source = tmp_path / "live" / ".codegraph"
        source.mkdir(parents=True)
        sqlite3.connect(source / "codegraph.db").close()
        sqlite3.connect(source / "extra.db").close()
        with pytest.raises(ValueError, match="undeclared SQLite database: extra.db"):
            create_frozen_index_snapshot(
                source, tmp_path / "frozen", "codegraph-warm", ()
            )

    @pytest.mark.parametrize(
        ("relative", "message"),
        (
            ("nested/extra.db", "undeclared SQLite database"),
            ("nested/codegraph.db", "undeclared SQLite database"),
            ("nested/codegraph.db-wal", "undeclared SQLite sidecar"),
        ),
    )
    def test_snapshot_rejects_nested_sqlite_artifact(
        self, tmp_path: Path, relative: str, message: str
    ):
        from benchmarks.codegraph_compare.smoke_workspace import (
            create_frozen_index_snapshot,
        )

        source = tmp_path / "live" / ".codegraph"
        source.mkdir(parents=True)
        connection = sqlite3.connect(source / "codegraph.db")
        connection.execute("CREATE TABLE nodes(file_path TEXT, name TEXT)")
        connection.execute("INSERT INTO nodes VALUES ('gin.go', 'ServeHTTP')")
        connection.commit()
        connection.close()
        artifact = source / relative
        artifact.parent.mkdir()
        artifact.write_bytes(b"foreign")
        with pytest.raises(ValueError, match=message):
            create_frozen_index_snapshot(
                source, tmp_path / "frozen", "codegraph-warm", ("gin.go",)
            )

    def test_snapshot_rejects_evidence_path_mismatch(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import (
            create_frozen_index_snapshot,
        )

        source = tmp_path / "live" / ".codegraph"
        source.mkdir(parents=True)
        connection = sqlite3.connect(source / "codegraph.db")
        connection.execute("CREATE TABLE nodes(file_path TEXT, name TEXT)")
        connection.execute("INSERT INTO nodes VALUES ('gin.go', 'ServeHTTP')")
        connection.commit()
        connection.close()
        with pytest.raises(ValueError, match="paths do not match index evidence"):
            create_frozen_index_snapshot(
                source, tmp_path / "frozen", "codegraph-warm", ("other.go",)
            )

    def test_snapshot_oracle_creates_no_sqlite_sidecars(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_workspace import (
            create_frozen_index_snapshot,
        )

        source = tmp_path / "live" / ".codegraph"
        source.mkdir(parents=True)
        connection = sqlite3.connect(source / "codegraph.db")
        connection.execute("CREATE TABLE nodes(file_path TEXT, name TEXT)")
        connection.execute("INSERT INTO nodes VALUES ('gin.go', 'ServeHTTP')")
        connection.commit()
        connection.close()
        frozen = create_frozen_index_snapshot(
            source, tmp_path / "frozen" / ".codegraph", "codegraph-warm", ("gin.go",)
        )
        assert tuple(sorted(path.name for path in frozen.iterdir())) == (
            "codegraph.db",
        )

    def test_snapshot_closes_oracle_connection_before_publish(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        # PR #1213: Windows 拒绝重命名包含已打开数据库的目录。
        from benchmarks.codegraph_compare import smoke_evidence

        source = tmp_path / "live" / ".codegraph"
        source.mkdir(parents=True)
        connection = sqlite3.connect(source / "codegraph.db")
        connection.execute("CREATE TABLE nodes(file_path TEXT, name TEXT)")
        connection.execute("INSERT INTO nodes VALUES ('gin.go', 'ServeHTTP')")
        connection.commit()
        connection.close()

        original_connect = smoke_evidence.sqlite3.connect
        oracle_connections = []

        class TrackingConnection:
            def __init__(self, wrapped):
                self.wrapped = wrapped
                self.closed = False

            def __getattr__(self, name):
                return getattr(self.wrapped, name)

            def __enter__(self):
                self.wrapped.__enter__()
                return self

            def __exit__(self, *args):
                return self.wrapped.__exit__(*args)

            def close(self):
                self.closed = True
                self.wrapped.close()

        def track_connect(database, *args, **kwargs):
            tracked = TrackingConnection(original_connect(database, *args, **kwargs))
            oracle_connections.append(tracked)
            return tracked

        monkeypatch.setattr(smoke_evidence.sqlite3, "connect", track_connect)

        observed = smoke_evidence.inspect_frozen_index("codegraph-warm", source)

        assert observed == ("gin.go",)
        assert tuple(item.closed for item in oracle_connections) == (True,)

    def test_materialize_uses_fixed_arm_oracle_and_distinct_copy(self, tmp_path: Path):
        from benchmarks.codegraph_compare.smoke_evidence import index_content_hash
        from benchmarks.codegraph_compare.smoke_workspace import (
            create_frozen_index_snapshot,
            materialize_runtime_index,
        )

        source = tmp_path / "live" / ".codegraph"
        source.mkdir(parents=True)
        connection = sqlite3.connect(source / "codegraph.db")
        connection.execute("CREATE TABLE nodes(file_path TEXT, name TEXT)")
        connection.execute("INSERT INTO nodes VALUES ('gin.go', 'ServeHTTP')")
        connection.commit()
        connection.close()
        frozen = create_frozen_index_snapshot(
            source, tmp_path / "frozen" / ".codegraph", "codegraph-warm", ("gin.go",)
        )
        checkout = tmp_path / "checkout"
        checkout.mkdir()
        runtime = materialize_runtime_index(
            frozen, checkout, "codegraph-warm", index_content_hash(frozen), ("gin.go",)
        )
        assert (
            (frozen / "codegraph.db").stat().st_ino
            == (runtime / "codegraph.db").stat().st_ino
        ) is False

    def test_freeze_rolls_back_both_live_indexes_when_second_rename_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from benchmarks.codegraph_compare.smoke_plan import freeze_index_baselines

        checkouts = self._indexed_checkout_pair(tmp_path)
        original = Path.rename

        def fail_second(path: Path, target: Path):
            if path.name == ".codegraph" and target.name.endswith("freeze-quarantine"):
                raise OSError("rename failed")
            return original(path, target)

        monkeypatch.setattr(Path, "rename", fail_second)
        with pytest.raises(OSError, match="rename failed"):
            freeze_index_baselines(
                checkouts,
                tmp_path / "checkouts",
                {"tsa-warm": ("gin.go",), "codegraph-warm": ("gin.go",)},
            )
        assert tuple(
            (checkouts[arm] / name).is_dir()
            for arm, name in (
                ("tsa-warm", ".ast-cache"),
                ("codegraph-warm", ".codegraph"),
            )
        ) == (True, True)
        assert tuple((tmp_path / "checkouts").rglob("*.freeze-quarantine")) == ()
        assert tuple((tmp_path / "checkouts" / "frozen-indexes").rglob("*.db")) == ()

    def test_freeze_cleanup_failure_preserves_frozen_authority(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from benchmarks.codegraph_compare.smoke_plan import freeze_index_baselines

        checkouts = self._indexed_checkout_pair(tmp_path)
        original = shutil.rmtree

        def fail_quarantine(path: Path, *args, **kwargs):
            if Path(path).name == ".codegraph.freeze-quarantine":
                raise OSError("cleanup failed")
            return original(path, *args, **kwargs)

        monkeypatch.setattr(shutil, "rmtree", fail_quarantine)
        with pytest.raises(RuntimeError, match="frozen authority"):
            freeze_index_baselines(
                checkouts,
                tmp_path / "checkouts",
                {"tsa-warm": ("gin.go",), "codegraph-warm": ("gin.go",)},
            )
        assert tuple(
            sorted(
                path.name
                for path in (tmp_path / "checkouts" / "frozen-indexes").rglob("*.db")
            )
        ) == ("codegraph.db", "index.db")
        assert (
            checkouts["codegraph-warm"] / ".codegraph.freeze-quarantine"
        ).is_dir() is True
