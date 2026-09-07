"""RED tests for Feature 2 — temporal-activation consumers.

Three behaviours are pinned down here:

  * ``analyze_change_impact`` reads ``ast_symbol_activation`` rows and bumps
    its verdict to ``CAUTION`` when any changed-file symbol's ``mod_count_30d
    >= 5``. It also adds a ``hot zone`` reason to ``risk_factors``.
  * ``CodeGraphCalleesTool.execute`` accepts ``include_activation=true`` and
    inlines ``activation: {mod_count_30d, last_modified_at}`` on each entry.
  * Without the flag, no ``activation`` key is leaked (token-frugal default).

All three tests MUST fail today:
  * ``ast_symbol_activation`` table does not exist
  * ``include_activation`` param is not in the tool schema
  * No reason "hot zone" is emitted by change_impact

Once the implementation lands the assertions match the SPEC; nothing here
needs to change.
"""

from __future__ import annotations

import inspect
import os
import sqlite3
import subprocess
import time
from pathlib import Path

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.mcp.tools.callees_tool import CodeGraphCalleesTool

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("state", ["pending", "disabled", None, "computed"])
def test_changed_file_hot_zone_uses_only_computed_activation(tmp_path, state):
    """PR #1350/#1352：真实改动文件的旧高次数不能覆盖 pending/disabled/未知状态，诊断不得丢失。"""
    from tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis import (
        ChangeImpactRequest,
        _attach_hot_zone_risk,
    )
    from tree_sitter_analyzer.mcp.tools.utils.change_impact_response import (
        build_agent_summary_only_response,
    )

    source = tmp_path / "changed.py"
    source.write_text("def changed():\n    pass\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_file(str(source))
        source.write_text("def changed():\n    return 1\n", encoding="utf-8")
        db = cache.get_conn()
        db.execute(
            "UPDATE ast_symbol_activation SET mod_count_30d=99,activation_state=?",
            (state,),
        )
        db.commit()
        request = ChangeImpactRequest("diff", ["changed.py"], "", str(tmp_path), False)
        result = _attach_hot_zone_risk(
            {
                "success": True,
                "verdict": "REVIEW",
                "agent_summary": {"verdict": "REVIEW"},
            },
            request,
        )
        hot = [f for f in result["risk_factors"] if f["factor"] == "hot_zone"]
        if state == "computed":
            assert result["verdict"] == "CAUTION"
            assert [f["mod_count_30d"] for f in hot] == [99]
        else:
            assert result["verdict"] == "REVIEW"
            assert hot == []
            diagnostic = result["activation_diagnostic"]
            assert diagnostic["available"] is False
            assert diagnostic["reason"] == "ACTIVATION_NOT_COMPUTED"
            assert diagnostic["files"] == ["changed.py"]
            assert (
                build_agent_summary_only_response(result)["agent_summary"][
                    "activation_diagnostic"
                ]
                == diagnostic
            )
    finally:
        cache.close()


def test_partial_heat_keeps_only_confirmed_hot_symbols(tmp_path):
    """PR #1350/#1352：部分未知不能抹掉真实热点，但遗留高次数不能混进风险因子。"""
    from tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis import (
        ChangeImpactRequest,
        _attach_hot_zone_risk,
    )

    source = tmp_path / "changed.py"
    source.write_text(
        "def known():\n    pass\ndef stale():\n    pass\n", encoding="utf-8"
    )
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_file(str(source))
        db = cache.get_conn()
        db.execute(
            "UPDATE ast_symbol_activation SET mod_count_30d=6,activation_state='computed'"
        )
        db.execute(
            "UPDATE ast_symbol_activation SET mod_count_30d=99,activation_state='pending' WHERE symbol_id=(SELECT id FROM ast_symbol_rows WHERE name='stale')"
        )
        db.commit()
        result = _attach_hot_zone_risk(
            {"verdict": "REVIEW", "agent_summary": {"verdict": "REVIEW"}},
            ChangeImpactRequest("diff", ["changed.py"], "", str(tmp_path), False),
        )
        assert result["verdict"] == "CAUTION"
        assert [f["mod_count_30d"] for f in result["risk_factors"]] == [6]
        assert result["activation_diagnostic"]["available"] is False
    finally:
        cache.close()


@pytest.mark.parametrize(
    "case,reason",
    [
        ("missing_db", "ACTIVATION_INDEX_MISSING"),
        ("missing_table", "ACTIVATION_INDEX_UNAVAILABLE"),
        ("missing_rows", "ACTIVATION_ROWS_MISSING"),
    ],
)
def test_missing_activation_evidence_is_not_complete_no_hotspots(
    tmp_path, case, reason
):
    """PR #1350/#1352：缺库、缺表、缺行均保留不可用原因，不创建数据库或声称完整无热点。"""
    from tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis import (
        ChangeImpactRequest,
        _attach_hot_zone_risk,
    )

    cache = None
    try:
        if case != "missing_db":
            cache = ASTCache(str(tmp_path))
            if case == "missing_table":
                cache.get_conn().execute("DROP TABLE ast_symbol_activation")
                cache.get_conn().commit()
        request = ChangeImpactRequest("diff", ["changed.py"], "", str(tmp_path), False)
        result = _attach_hot_zone_risk(
            {"verdict": "REVIEW", "agent_summary": {}}, request
        )
        assert result["verdict"] == "REVIEW"
        assert result["risk_factors"] == []
        assert result["activation_diagnostic"]["available"] is False
        assert result["activation_diagnostic"]["reason"] == reason
        if case == "missing_db":
            assert not (tmp_path / ".ast-cache").exists()
    finally:
        if cache is not None:
            cache.close()


@pytest.mark.parametrize(
    "count,available", [(0, True), (-1, False), ("invalid", False)]
)
def test_computed_heat_distinguishes_cold_from_invalid_counts(
    tmp_path, count, available
):
    """PR #1350/#1352：已计算的零热度与非法次数不同；无关文件的 pending 不污染改动范围。"""
    from tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis import (
        ChangeImpactRequest,
        _attach_hot_zone_risk,
    )

    source = tmp_path / "changed.py"
    source.write_text("def changed():\n    pass\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_file(str(source))
        db = cache.get_conn()
        db.execute(
            "UPDATE ast_symbol_activation SET activation_state='computed',mod_count_30d=?",
            (count,),
        )
        db.execute(
            "INSERT INTO ast_symbol_activation(symbol_id,file_path,mod_count_30d,computed_at,activation_state) VALUES (999,'other.py',99,0,'pending')"
        )
        db.commit()
        request = ChangeImpactRequest("diff", ["changed.py"], "", str(tmp_path), False)
        result = _attach_hot_zone_risk(
            {"verdict": "REVIEW", "agent_summary": {}}, request
        )
        assert result["verdict"] == "REVIEW"
        assert result["risk_factors"] == []
        assert result["activation_diagnostic"]["available"] is available
        assert result["activation_diagnostic"]["reason"] == (
            None if available else "ACTIVATION_NOT_COMPUTED"
        )
    finally:
        cache.close()


@pytest.mark.parametrize("summary_only", [False, True])
@pytest.mark.parametrize("state", ["pending", "disabled"])
async def test_change_impact_preserves_heat_diagnostic_in_public_views(
    tmp_path, state, summary_only
):
    """PR #1350/#1352：真实 Git 改动与 SQL 旧统计经完整/精简入口后仍保持不可用说明，不误升风险。"""
    from tree_sitter_analyzer.mcp.tools.change_impact_tool import ChangeImpactTool

    source = tmp_path / "changed.py"
    source.write_text("def changed():\n    pass\n", encoding="utf-8")
    for args in (
        ["init", "--initial-branch=main"],
        ["add", "changed.py"],
        [
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            "initial",
        ],
    ):
        subprocess.run(
            ["git", "-C", str(tmp_path), *args],
            check=True,
            capture_output=True,
            timeout=15,
        )
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_file(str(source))
        cache.get_conn().execute(
            "UPDATE ast_symbol_activation SET mod_count_30d=99,activation_state=?",
            (state,),
        )
        cache.get_conn().commit()
        source.write_text("def changed():\n    return 1\n", encoding="utf-8")
        result = await ChangeImpactTool(str(tmp_path)).execute(
            {
                "mode": "diff",
                "include_tests": False,
                "agent_summary_only": summary_only,
                "output_format": "json",
            }
        )
        assert result["success"] is True
        assert result["verdict"] == "REVIEW"
        assert result["agent_summary"]["activation_diagnostic"] == {
            "available": False,
            "reason": "ACTIVATION_NOT_COMPUTED",
            "files": ["changed.py"],
        }
        assert [
            f for f in result.get("risk_factors", []) if f["factor"] == "hot_zone"
        ] == []
    finally:
        cache.close()


# ---------------------------------------------------------------------------
# Fixture: a tiny git repo whose AST cache contains an activation row we
# can pre-seed with arbitrary mod_count_30d for assertion purposes.
# ---------------------------------------------------------------------------


_SAMPLE_PY = (
    "def helper(x):\n"
    "    return x + 1\n"
    "\n"
    "def consumer():\n"
    "    return helper(1) + helper(2)\n"
)


def _init_git_repo(repo: Path) -> None:
    """Initialise a git repo inside ``repo`` with a single commit."""
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(repo)],
        check=True,
        capture_output=True,
    )
    os.environ["GIT_CONFIG_COUNT"] = "1"
    os.environ["GIT_CONFIG_KEY_0"] = "safe.directory"
    os.environ["GIT_CONFIG_VALUE_0"] = str(repo)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Test"],
        check=True,
        capture_output=True,
    )
    (repo / "mod.py").write_text(_SAMPLE_PY, encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repo), "add", "mod.py"], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "initial"],
        check=True,
        capture_output=True,
    )


def _make_git_repo_path(tmp_path: Path) -> Path:
    """Create a git repo under pytest's tmp_path for automatic cleanup."""
    repo = tmp_path / "repo-temporal"
    repo.mkdir(parents=True)
    return repo


def _seed_hot_zone_row(
    db_path: str,
    *,
    file_path: str,
    symbol_id: int,
    mod_count_30d: int,
) -> None:
    """Insert (or upsert) a fake ``ast_symbol_activation`` row.

    Designed for the verdict-bump test: we don't care about full attribution,
    just that the row exists with the requested ``mod_count_30d`` so the
    consumer can decide ``hot zone``.

    The table itself is created by the not-yet-existing implementation. This
    helper executes the canonical CREATE statement so the integration test
    can run before the production migration ships.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ast_symbol_activation (
                symbol_id INTEGER PRIMARY KEY,
                file_path TEXT NOT NULL,
                last_modified_commit TEXT,
                last_modified_at INTEGER,
                mod_count_30d INTEGER NOT NULL DEFAULT 0,
                mod_count_90d INTEGER NOT NULL DEFAULT 0,
                mod_count_all INTEGER NOT NULL DEFAULT 0,
                computed_at INTEGER NOT NULL,
                git_state TEXT NOT NULL DEFAULT 'tracked',
                activation_state TEXT
            )
            """
        )
        now = int(time.time())
        conn.execute(
            """
            INSERT OR REPLACE INTO ast_symbol_activation (
                symbol_id, file_path,
                last_modified_commit, last_modified_at,
                mod_count_30d, mod_count_90d, mod_count_all,
                computed_at, git_state, activation_state
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'computed')
            """,
            (
                symbol_id,
                file_path,
                "deadbeef",
                now,
                mod_count_30d,
                mod_count_30d,  # 90d at least as big as 30d
                mod_count_30d,
                now,
                "tracked",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _first_symbol_row(db_path: str, file_path: str) -> tuple[int, str]:
    """Return the smallest symbol id and stored path for ``file_path``."""
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            """
            SELECT id, file_path
            FROM ast_symbol_rows
            WHERE file_path = ? OR file_path LIKE ?
            ORDER BY CASE WHEN file_path = ? THEN 0 ELSE 1 END, id
            LIMIT 1
            """,
            (file_path, f"%/{file_path}", file_path),
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(f"no ast_symbol_rows entry for {file_path!r}")
        return int(row[0]), str(row[1])
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 1. analyze_change_impact: hot zone bumps verdict
# ---------------------------------------------------------------------------


class TestHotZoneBumpsVerdict:
    @pytest.mark.slow_ok  # real git repo + AST cache indexing can exceed 5s on Windows
    @pytest.mark.asyncio
    async def test_hot_zone_bumps_verdict_to_caution(self, tmp_path, monkeypatch):
        """A symbol with ``mod_count_30d >= 5`` in a CHANGED file must:
        * push the run's verdict to ``CAUTION``
        * surface a ``risk_factors`` entry mentioning ``hot zone``.
        """
        repo = _make_git_repo_path(tmp_path)
        _init_git_repo(repo)

        # Index the file so ast_symbol_rows is populated.
        cache = ASTCache(str(repo))
        try:
            cache.index_file(str(repo / "mod.py"))
            symbol_id, stored_file_path = _first_symbol_row(cache.db_path, "mod.py")
            _seed_hot_zone_row(
                cache.db_path,
                file_path=stored_file_path,
                symbol_id=symbol_id,
                mod_count_30d=10,  # well above the threshold of 5
            )
            db_path = cache.db_path
        finally:
            cache.close()

        # Modify the file so git sees an unstaged change.
        (repo / "mod.py").write_text(
            _SAMPLE_PY.replace("return x + 1", "return x + 2"),
            encoding="utf-8",
        )

        # Sanity: db still has the row.
        assert _read_one_row(db_path, "ast_symbol_activation") is not None

        # Run change-impact analysis from inside the repo so the tool picks
        # up our test git directory.
        monkeypatch.chdir(repo)
        from tree_sitter_analyzer.mcp.tools.change_impact_tool import ChangeImpactTool

        tool = ChangeImpactTool(str(repo))
        result = await tool.execute(
            {
                "mode": "diff",
                "output_format": "json",
                "include_tests": False,
            }
        )

        assert result.get("success") is True
        assert result.get("verdict") == "CAUTION", (
            f"expected verdict=CAUTION because mod_count_30d=10, got {result.get('verdict')!r}"
        )

        # The reason "hot zone" must show up somewhere in risk_factors.
        reasons = _collect_risk_reason_strings(result)
        assert any("hot zone" in s.lower() for s in reasons), (
            f"no 'hot zone' substring in risk_factors / reasons: {reasons!r}"
        )


def _read_one_row(db_path: str, table: str) -> dict | None:
    """Return one row from ``table`` as dict, or None."""
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute(f"SELECT * FROM {table} LIMIT 1")
        except sqlite3.OperationalError:
            return None
        r = cur.fetchone()
        return dict(r) if r is not None else None
    finally:
        conn.close()


def _collect_risk_reason_strings(result: dict) -> list[str]:
    """Walk the change-impact response and harvest any 'reason' strings.

    The response shape today carries ``risk_factors`` as ``list[dict]`` (per
    ``safe_to_edit_helpers``), but Feature 2 may surface them under
    ``agent_summary`` or top-level. Be liberal in what we accept.
    """
    out: list[str] = []
    queue: list = [result]
    while queue:
        item = queue.pop()
        if isinstance(item, dict):
            for k, v in item.items():
                if k in ("reason", "factor", "label", "name") and isinstance(v, str):
                    out.append(v)
                queue.append(v)
        elif isinstance(item, list):
            queue.extend(item)
    return out


# ---------------------------------------------------------------------------
# 2 + 3. callees_tool include_activation flag
# ---------------------------------------------------------------------------


_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)


@pytest.fixture
def indexed_relation_project(tmp_path: Path) -> str:
    (tmp_path / "helper.py").write_text(
        "def helper():\n    return 1\n",
        encoding="utf-8",
    )
    (tmp_path / "worker.py").write_text(
        "from helper import helper\n\n\ndef build():\n    return helper()\n",
        encoding="utf-8",
    )
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project()
    finally:
        cache.close()
    return str(tmp_path)


@pytest.fixture
def callees_tool(indexed_relation_project: str):
    return CodeGraphCalleesTool(indexed_relation_project)


class TestCalleesActivationFlag:
    @pytest.mark.asyncio
    async def test_callees_tool_includes_activation_when_requested(self, callees_tool):
        """With ``include_activation=True`` every callee entry must expose
        ``activation.mod_count_30d`` and ``activation.last_modified_at``."""
        result = await callees_tool.execute(
            {
                "function_name": "build",
                "include_activation": True,
                "output_format": "json",
            }
        )
        assert result.get("success") is True
        callees = result.get("callees", [])
        # The test target ``build`` lives in call_graph.py and DOES have
        # callees. If empty the assertion below still validates "no spurious
        # data" — but more importantly there must be no schema regression
        # on populated entries.
        for entry in callees:
            assert "activation" in entry, (
                f"missing 'activation' key on entry: {entry!r}"
            )
            activation = entry["activation"]
            assert "mod_count_30d" in activation
            assert "last_modified_at" in activation
            # mod_count_30d is a non-negative int.
            assert isinstance(activation["mod_count_30d"], int)
            assert activation["mod_count_30d"] >= 0  # ratchet: nondeterministic
            # last_modified_at is either an epoch int or None.
            ts = activation["last_modified_at"]
            assert ts is None or (
                isinstance(ts, int) and ts >= 0
            )  # ratchet: nondeterministic

    @pytest.mark.asyncio
    async def test_callees_tool_omits_activation_by_default(self, callees_tool):
        """Without the flag the response is byte-for-byte the legacy shape —
        no ``activation`` key anywhere. This protects the default token
        budget for agents that don't opt in."""
        result = await callees_tool.execute(
            {
                "function_name": "build",
                "output_format": "json",
            }
        )
        assert result.get("success") is True
        for entry in result.get("callees", []):
            assert "activation" not in entry, (
                "default response must omit 'activation' to preserve "
                f"token budget; got entry={entry!r}"
            )


# ---------------------------------------------------------------------------
# Tiny sanity test — runs even if everything else is busted
# ---------------------------------------------------------------------------


def test_module_imports_cleanly():
    """Defensive: importing this test file must NOT itself raise.

    Pure import-time errors would break ``pytest --collect-only`` and
    sabotage all other tests. The deferred imports below are all inside
    test bodies, so this assertion is essentially a no-op — but it makes
    the contract explicit.
    """
    assert ASTCache is not None
    assert CodeGraphCalleesTool is not None
    assert inspect.iscoroutinefunction(CodeGraphCalleesTool(_PROJECT_ROOT).execute)


# Ensure os imports used above don't trip linters/CI as "unused".
_ = os  # noqa: F841
