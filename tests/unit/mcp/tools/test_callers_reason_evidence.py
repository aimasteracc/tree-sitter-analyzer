"""#1672：每个原因码都要把 Agent 引到证据上。

dogfood 第 8 轮：(1) ``NAME_ONLY_INBOUND`` 的答案没有计数、没有调用点、也没有
``next_step``，Agent 只能自己 grep；(2) 刷新前在作用域外的已索引文件里新增调用，
非调用引用扫描在“源码已与索引不一致”的文件里命中，却报告为
``NON_CALL_REFERENCES``（freshness ``unknown``）而不是 ``SOURCE_INDEX_MISMATCH``。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool
from tree_sitter_analyzer.mcp.tools.relation_freshness import REFRESH_COMMAND

#: ``self._reset()`` 来自一个 MRO 未知的类（基类是第三方类）：接收者无法绑定，只按同名匹配。
#: #1677：MRO 完全已知的继承调用会绑定到基类方法，这里因此用外部基类。
_BASE = (
    "class Base:\n"
    "    def _reset(self):\n"
    "        return 1\n\n"
    "    def direct(self):\n"
    "        return Base()._reset()\n"
)
_CHILD = (
    "from external_pkg import Mixin\n\n\n"
    "class Child(Mixin):\n"
    "    def run(self):\n"
    "        self._reset()\n"
    "        return 2\n\n"
    "    def again(self):\n"
    "        return self._reset()\n"
)
_OTHER = "class Other:\n    def _reset(self):\n        return 3\n"


async def _index_files(root: Path, files: dict[str, str]) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    for rel_path, text in files.items():
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 50}
    )
    assert indexed["published"] is True
    return str(root)


async def _callers(root: str, name: str, file_path: str | None = None) -> dict:
    arguments: dict = {"function_name": name, "include_bodies": False}
    if file_path:
        arguments["file_path"] = file_path
    return await CodeGraphCallersTool(root).execute(arguments)


# ---------------------------------------------------------------------------
# (1) NAME_ONLY_INBOUND：计数 + 有上限的调用点 + 点名它们的 next_step
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_name_only_inbound_names_its_call_sites(tmp_path) -> None:
    root = await _index_files(
        tmp_path, {"base.py": _BASE, "child.py": _CHILD, "other.py": _OTHER}
    )

    result = await _callers(root, "Base._reset", "base.py")

    assert "NAME_ONLY_INBOUND" in result["completeness_reasons"]
    assert result["name_only_inbound"] == 2
    assert result["name_only_sites"] == [
        {"file": "child.py", "line": 6, "caller": "Child.run"},
        {"file": "child.py", "line": 10, "caller": "Child.again"},
    ]
    assert result["name_only_sites_total"] == 2
    assert result["name_only_sites_truncated"] is False
    step = result["next_step"]
    assert "child.py:6 (Child.run)" in step
    assert "child.py:10 (Child.again)" in step
    # 已限定名时，指出如何判断：看调用点的接收者是不是该类（或子类）的实例。
    assert "`Base`" in step
    assert result["agent_summary"]["next_step"] == step


@pytest.mark.asyncio
async def test_name_only_sites_are_capped_with_an_honest_total(tmp_path) -> None:
    callers = "".join(
        f"    def call_{index}(self):\n        return self._reset()\n\n"
        for index in range(25)
    )
    child = "from external_pkg import Mixin\n\n\nclass Child(Mixin):\n" + callers
    root = await _index_files(
        tmp_path, {"base.py": _BASE, "child.py": child, "other.py": _OTHER}
    )

    result = await _callers(root, "Base._reset", "base.py")

    assert result["name_only_inbound"] == 25
    assert result["name_only_sites_total"] == 25
    assert len(result["name_only_sites"]) == 20
    assert result["name_only_sites_truncated"] is True
    assert result["name_only_sites"][0] == {
        "file": "child.py",
        "line": 6,
        "caller": "Child.call_0",
    }
    assert "and 22 more" in result["next_step"]


@pytest.mark.asyncio
async def test_not_found_answer_names_its_name_only_sites(tmp_path) -> None:
    # 没有已解析调用方时，NOT_FOUND 分支同样点名同名入边的调用点。
    files = {
        "a.py": "class A:\n    def ping(self):\n        return 1\n",
        "b.py": "class B:\n    def ping(self):\n        return 2\n",
        "use.py": "def use(x):\n    return x.ping()\n",
    }
    root = await _index_files(tmp_path, files)

    result = await _callers(root, "A.ping")

    assert (result["caller_count"], result["completeness"]) == (0, "unknown")
    assert result["completeness_reasons"] == ["UNRESOLVED_INBOUND", "NAME_ONLY_INBOUND"]
    assert result["name_only_sites"] == [{"file": "use.py", "line": 2, "caller": "use"}]
    assert "use.py:2 (use)" in result["next_step"]
    assert "`A` (or subclass) instance" in result["next_step"]


def test_unqualified_name_only_step_says_how_to_qualify() -> None:
    from tree_sitter_analyzer.mcp.tools.callers_name_only import name_only_step

    sites = [{"file": "use.py", "line": 2, "caller": "use"}]

    assert name_only_step("ping", sites) == (
        "1 call site(s) reach a same-named `ping` through a receiver that could "
        "not be bound to 'ping' (`name_only_sites`): use.py:2 (use). Read them, "
        "then qualify the query as `Class.method` (with `file_path`) to bind the "
        "callers that belong to this definition."
    )


def test_name_only_site_falls_back_to_the_caller_line_without_call_edges() -> None:
    from tree_sitter_analyzer.mcp.tools.callers_name_only import name_only_sites

    caller = {"file": "c.py", "name": "run", "line": 4, "end_line": 9, "receiver": "C"}

    assert name_only_sites([caller], None) == [
        {"file": "c.py", "line": 4, "caller": "C.run"}
    ]
    assert name_only_sites([caller], {"c.py": frozenset({2, 5, 7, 12})}) == [
        {"file": "c.py", "line": 5, "caller": "C.run"},
        {"file": "c.py", "line": 7, "caller": "C.run"},
    ]


# ---------------------------------------------------------------------------
# (2) 作用域外、刷新前的编辑：源码与索引不一致时报告 SOURCE_INDEX_MISMATCH
# ---------------------------------------------------------------------------

_LIB = (
    "def target(items):\n"
    "    return list(items)\n\n\n"
    "def user():\n"
    "    return target([])\n"
)
_UNRELATED = "def unrelated():\n    return 0\n"
_PROBE = "\n\ndef probe():\n    import lib as m\n    return m.target([])\n"


@pytest.mark.asyncio
async def test_pre_refresh_call_outside_scope_is_a_source_index_mismatch(
    tmp_path,
) -> None:
    root = await _index_files(tmp_path, {"lib.py": _LIB, "other.py": _UNRELATED})
    other = tmp_path / "other.py"
    other.write_text(_UNRELATED + _PROBE, encoding="utf-8")

    result = await _callers(root, "target")

    assert result["caller_count"] == 1
    assert result["completeness"] == "incomplete"
    assert result["completeness_reason"] == "SOURCE_INDEX_MISMATCH"
    assert result["completeness_reasons"] == ["SOURCE_INDEX_MISMATCH"]
    assert result["source_evidence"]["freshness"] == "stale"
    assert result["source_evidence"]["reason"] == "SOURCE_INDEX_MISMATCH"
    assert result["stale_reference_files"] == ["other.py"]
    assert result["non_call_reference_sites"] == [{"file": "other.py", "line": 7}]
    assert "other.py" in result["next_step"]
    assert REFRESH_COMMAND in result["next_step"]
    assert result["agent_summary"]["next_step"] == result["next_step"]
    assert result["agent_summary"]["summary_line"].endswith("(index stale)")


@pytest.mark.asyncio
async def test_mismatch_keeps_non_call_references_in_unchanged_files(
    tmp_path,
) -> None:
    # 未变文件里的回调引用仍是 NON_CALL_REFERENCES，排在 MISMATCH 之后（表序）。
    callback = "import lib\n\n\ndef wire(register):\n    return register(lib.target)\n"
    root = await _index_files(
        tmp_path, {"lib.py": _LIB, "other.py": _UNRELATED, "wire.py": callback}
    )
    (tmp_path / "other.py").write_text(_UNRELATED + _PROBE, encoding="utf-8")

    result = await _callers(root, "target")

    assert result["completeness_reasons"] == [
        "SOURCE_INDEX_MISMATCH",
        "NON_CALL_REFERENCES",
    ]
    assert result["stale_reference_files"] == ["other.py"]
    assert {site["file"] for site in result["non_call_reference_sites"]} == {
        "other.py",
        "wire.py",
    }


@pytest.mark.asyncio
async def test_touched_but_identical_file_is_not_a_mismatch(tmp_path) -> None:
    # 只改 mtime、内容未变（摘要一致）不是不一致：仍为 NON_CALL_REFERENCES。
    callback = "import lib\n\n\ndef wire(register):\n    return register(lib.target)\n"
    root = await _index_files(tmp_path, {"lib.py": _LIB, "wire.py": callback})
    wire = tmp_path / "wire.py"
    stat = wire.stat()
    os.utime(wire, ns=(stat.st_atime_ns, stat.st_mtime_ns + 3_000_000_000))

    result = await _callers(root, "target")

    assert result["completeness_reasons"] == ["NON_CALL_REFERENCES"]
    assert result["source_evidence"]["freshness"] == "unknown"
    assert result["stale_reference_files"] == []


@pytest.mark.asyncio
async def test_unchanged_reference_keeps_its_old_diagnosis(tmp_path) -> None:
    # 对照组：未编辑时，回调引用仍报告 NON_CALL_REFERENCES，freshness 不变。
    callback = "import lib\n\n\ndef wire(register):\n    return register(lib.target)\n"
    root = await _index_files(tmp_path, {"lib.py": _LIB, "wire.py": callback})

    result = await _callers(root, "target")

    assert result["completeness_reasons"] == ["NON_CALL_REFERENCES"]
    assert result["source_evidence"]["reason"] == "SOURCE_REVALIDATION_SCOPED"
    assert result["stale_reference_files"] == []


def test_final_reasons_lists_the_scan_reasons_after_the_mismatch() -> None:
    # RFC-0040：引用扫描的不一致与仍成立的原因由同一道检查一并报告。
    from tree_sitter_analyzer.mcp.tools.callers_checks import (
        REQUIRED_CHECKS,
        Ledger,
        prove,
    )
    from tree_sitter_analyzer.mcp.tools.callers_outcomes import Checked

    scope = ("f", None)
    clean = Ledger(scope).record_all(
        (spec.name, Checked(scope)) for spec in REQUIRED_CHECKS
    )
    stale = clean.record(
        "reference_freshness",
        Checked(scope, ("SOURCE_INDEX_MISMATCH", "NON_CALL_REFERENCES")),
    )
    proof = prove(stale, 2)
    assert (proof.completeness, proof.reasons) == (
        "incomplete",
        ("SOURCE_INDEX_MISMATCH", "NON_CALL_REFERENCES"),
    )
    assert prove(clean, 2).reasons == ()


def test_stamped_read_returns_the_stat_evidence_of_the_bytes(tmp_path) -> None:
    from tree_sitter_analyzer.mcp.tools.evidence_file_cache import EvidenceFileCache

    target = tmp_path / "f.py"
    target.write_bytes(b"alpha\n")
    info = target.stat()

    data, stamp = EvidenceFileCache().read_stamped(str(target))

    assert data == b"alpha\n"
    assert stamp is not None
    assert (stamp[0], stamp[1]) == (info.st_size, info.st_mtime_ns)
    assert EvidenceFileCache().read_stamped(str(tmp_path / "gone.py")) is None


@pytest.mark.asyncio
async def test_stale_source_downgrades_the_answer_to_warn(tmp_path) -> None:
    """dogfood 2026-11-09 P1-1：过期索引下的答案不能仍是 INFO。

    信封契约把 stale cache 归为 WARN，而 ``complete`` 的证明以下标
    「源码与索引一致」；此前只有嵌套的 ``source_evidence.freshness`` 和散文
    next_step 透露过期，脚本读 ``verdict`` 完全看不见。
    """
    root = await _index_files(tmp_path, {"lib.py": _LIB, "other.py": _UNRELATED})
    (tmp_path / "other.py").write_text(_UNRELATED + _PROBE, encoding="utf-8")

    result = await _callers(root, "target")

    assert (result["verdict"], result["stale"]) == ("WARN", True)
    assert result["completeness_reasons"][0] == "SOURCE_INDEX_MISMATCH"
    assert result["completeness_reason"] == "SOURCE_INDEX_MISMATCH"
    assert result["agent_summary"]["verdict"] == "WARN"
    assert result["agent_summary"]["summary_line"].endswith("(index stale)")


def test_stale_evidence_never_rewrites_an_error_verdict() -> None:
    """已经失败的答案保持 ``ERROR``；过期只追加 stale 标记与原因。"""
    from tree_sitter_analyzer.mcp.tools.relation_freshness import (
        apply_source_evidence,
    )

    result = {
        "verdict": "ERROR",
        "completeness_reasons": ["RELATION_ERROR"],
        "next_step": "Fix the invocation and retry.",
        "agent_summary": {
            "summary_line": "callers: error",
            "verdict": "ERROR",
            "next_step": "Fix the invocation and retry.",
        },
    }

    apply_source_evidence(
        result, {"freshness": "stale", "reason": "SOURCE_INDEX_MISMATCH"}, ["a.py"]
    )

    assert (
        result["verdict"],
        result["stale"],
        result["agent_summary"]["verdict"],
    ) == ("ERROR", True, "ERROR")
    assert result["completeness_reasons"] == ["SOURCE_INDEX_MISMATCH", "RELATION_ERROR"]


@pytest.mark.asyncio
async def test_named_caller_exposes_the_call_site_line(tmp_path) -> None:
    """dogfood 2026-11-09 P1-3：``line`` 是调用方定义行，``call_site_line`` 是调用行。"""
    root = await _index_files(
        tmp_path,
        {
            "lib.py": "def target():\n    return 1\n",
            "c.py": "from lib import target\n\n\ndef wrapper():\n    return target()\n",
        },
    )

    result = await _callers(root, "target")

    entry = result["callers"][0]
    assert (entry["name"], entry["line"], entry["call_site_line"]) == (
        "wrapper",
        4,
        5,
    )


@pytest.mark.asyncio
async def test_module_caller_keeps_its_call_line_without_call_site_line(
    tmp_path,
) -> None:
    """模块级调用点的 ``line`` 本来就是调用行；不重复出 ``call_site_line``。"""
    root = await _index_files(
        tmp_path,
        {
            "lib.py": "def target():\n    return 1\n",
            "c.py": "from lib import target\n\ntarget()\n",
        },
    )

    result = await _callers(root, "target")

    entry = result["callers"][0]
    assert (entry["name"], entry["line"], "call_site_line" in entry) == (
        "<module>",
        3,
        False,
    )


def test_call_site_line_enrichment_tolerates_an_unreadable_index() -> None:
    """读不到调用边时原样返回条目，不冒充调用点坐标。"""
    from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

    class _UnreadableCache:
        def query_callers(self, *args, **kwargs):
            raise RuntimeError("index unreadable")

    entries = [{"name": "wrapper", "file": "c.py", "line": 4}]
    assert (
        CodeGraphCallersTool._attach_call_site_lines(
            _UnreadableCache(), entries, "target", None
        )
        == entries
    )
    assert "call_site_line" not in entries[0]


def test_call_site_line_enrichment_leaves_unmatched_entries_alone() -> None:
    """边里没有对应调用点时，不写 call_site_line（不猜测坐标）。"""
    from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

    class _OtherEdges:
        def query_callers(self, *args, **kwargs):
            return [
                {"caller_name": "someone_else", "caller_file": "x.py", "callee_line": 9}
            ]

    entries = [{"name": "wrapper", "file": "c.py", "line": 4}]
    CodeGraphCallersTool._attach_call_site_lines(_OtherEdges(), entries, "target", None)

    assert ("call_site_line" in entries[0], entries[0]["line"]) == (False, 4)


def test_call_site_line_enrichment_fills_a_graph_entry() -> None:
    """调用图条目按 (file, caller, 定义行) 从边映射到调用点行。"""
    from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

    class _Edges:
        def query_callers(self, *args, **kwargs):
            return [
                {
                    "caller_name": "wrapper",
                    "caller_file": "c.py",
                    "caller_line": 4,
                    "callee_line": 7,
                }
            ]

    entries = [{"name": "wrapper", "file": "c.py", "line": 4}]
    CodeGraphCallersTool._attach_call_site_lines(_Edges(), entries, "target", None)

    assert (entries[0]["line"], entries[0]["call_site_line"]) == (4, 7)


def test_named_caller_without_a_call_line_omits_the_field() -> None:
    """边上没有调用行时不写 ``call_site_line``（不用 0 冒充坐标）。"""
    from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

    class _Cache:
        project_root = "."

        def query_callers(self, *args, **kwargs):
            return [
                {
                    "caller_name": "wrapper",
                    "caller_file": "c.py",
                    "caller_line": 4,
                    "callee_line": 0,
                    "callee_resolved_file": "",
                    "receiver_binding": None,
                }
            ]

        def lookup(self, path):
            return None

    callers, unattributed = CodeGraphCallersTool(".")._sql_native_callers(
        _Cache(), "target", None
    )

    assert (len(callers), "call_site_line" in callers[0], unattributed) == (
        1,
        False,
        0,
    )


@pytest.mark.asyncio
async def test_identical_questions_share_an_answer_etag(tmp_path) -> None:
    """dogfood §12.1：同索引上重复提问得到同一 etag（agent 缓存判断的依据）。"""
    root = await _index_files(
        tmp_path,
        {
            "lib.py": "def target():\n    return 1\n",
            "c.py": "from lib import target\n\n\ndef wrapper():\n    return target()\n",
        },
    )

    first = await _callers(root, "target")
    second = await _callers(root, "target")

    assert first["answer_etag"] == second["answer_etag"]
    assert first["answer_etag"].startswith("sha256:")
    assert len(first["answer_etag"]) == len("sha256:") + 64


@pytest.mark.asyncio
async def test_a_stale_scope_changes_the_answer_etag(tmp_path) -> None:
    """作用域源码变化后 etag 必须变化——ETag 是承诺，不是猜测。"""
    root = await _index_files(
        tmp_path,
        {
            "lib.py": "def target():\n    return 1\n",
            "c.py": "from lib import target\n\n\ndef wrapper():\n    return target()\n",
        },
    )
    before = await _callers(root, "target")

    (tmp_path / "c.py").write_text(
        "from lib import target\n\n\ndef wrapper():\n    return target()\n\n# edited\n",
        encoding="utf-8",
    )
    after = await _callers(root, "target")

    assert (before.get("stale", False), after.get("stale")) == (False, True)
    assert before["answer_etag"] != after["answer_etag"]


def test_answer_etag_ignores_volatile_fields() -> None:
    """etag 不包含耗时/路径前缀等易变字段：只对内容与证据状态敏感。"""
    from tree_sitter_analyzer.mcp.tools.callers_tool import answer_etag

    base = {
        "function": "target",
        "caller_count": 1,
        "completeness": "complete",
        "callers": [{"name": "wrapper", "file": "c.py", "line": 4}],
    }
    noisy = {**base, "elapsed_ms": 123, "cache_age_s": 4.2}

    assert answer_etag(base) == answer_etag(noisy)


def test_caller_body_inlining_failure_is_silent(monkeypatch) -> None:
    """体内联是尽力而为：失败时保留坐标列表并返回 None，不抛给调用方。"""
    import tree_sitter_analyzer.mcp.tools.symbol_body_inline as sbi
    from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

    def _explode(*args, **kwargs):
        raise RuntimeError("inlining failed")

    monkeypatch.setattr(sbi, "inline_neighbor_bodies", _explode)
    tool = CodeGraphCallersTool(".")
    callers = [{"name": "wrapper", "file": "c.py", "line": 4}]

    assert tool._inline_caller_bodies(None, callers) is None
    assert callers == [{"name": "wrapper", "file": "c.py", "line": 4}]


async def _callers_with(root: str, name: str, **extra) -> dict:
    from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

    return await CodeGraphCallersTool(root).execute(
        {"function_name": name, "include_bodies": False, **extra}
    )


@pytest.mark.asyncio
async def test_matching_etag_returns_the_minimal_unchanged_payload(tmp_path) -> None:
    """dogfood §12.1：If-None-Match 命中时只回 tiny payload，不回 15 KB 列表。"""
    root = await _index_files(
        tmp_path,
        {
            "lib.py": "def target():\n    return 1\n",
            "c.py": "from lib import target\n\n\ndef wrapper():\n    return target()\n",
        },
    )
    first = await _callers(root, "target")

    second = await _callers_with(root, "target", if_none_match=first["answer_etag"])

    assert second["unchanged"] is True
    assert "callers" not in second
    assert second["answer_etag"] == first["answer_etag"]


@pytest.mark.asyncio
async def test_a_different_etag_still_returns_the_full_answer(tmp_path) -> None:
    """不匹配时必须回完整答案，不能猜而复用。"""
    root = await _index_files(
        tmp_path,
        {
            "lib.py": "def target():\n    return 1\n",
            "c.py": "from lib import target\n\n\ndef wrapper():\n    return target()\n",
        },
    )

    result = await _callers_with(root, "target", if_none_match="sha256:" + "0" * 64)

    assert ("callers" in result, result["caller_count"]) == (True, 1)


@pytest.mark.asyncio
async def test_a_stale_scope_never_claims_unchanged(tmp_path) -> None:
    """作用域源码变了就回完整答案（WARN/stale），即使 etag 文本相同。"""
    root = await _index_files(
        tmp_path,
        {
            "lib.py": "def target():\n    return 1\n",
            "c.py": "from lib import target\n\n\ndef wrapper():\n    return target()\n",
        },
    )
    before = await _callers(root, "target")
    (tmp_path / "c.py").write_text(
        "from lib import target\n\n\ndef wrapper():\n    return target()\n\n# edited\n",
        encoding="utf-8",
    )

    result = await _callers_with(root, "target", if_none_match=before["answer_etag"])

    assert (result.get("stale"), "unchanged" in result) == (True, False)


def test_callers_delta_reports_added_removed_and_unchanged() -> None:
    """dogfood §12.2：增量答案按 (file,line,call_site_line,name) 对齐。"""
    from tree_sitter_analyzer.mcp.tools.callers_tool import _callers_delta

    previous = [
        {"name": "a", "file": "c.py", "line": 4},
        {"name": "gone", "file": "g.py", "line": 2},
    ]
    current = [
        {"name": "a", "file": "c.py", "line": 4},
        {"name": "b", "file": "d.py", "line": 8},
    ]

    delta = _callers_delta(previous, current)

    assert (
        [entry["name"] for entry in delta["added"]],
        [entry["name"] for entry in delta["removed"]],
        delta["unchanged_count"],
    ) == (["b"], ["gone"], 1)


@pytest.mark.asyncio
async def test_previous_entries_produce_a_delta_not_a_full_list(tmp_path) -> None:
    """带上一次答案的条目时只回增量，不回 15 KB 列表。"""
    root = await _index_files(
        tmp_path,
        {
            "lib.py": "def target():\n    return 1\n",
            "c.py": "from lib import target\n\n\ndef wrapper():\n    return target()\n",
        },
    )
    first = await _callers(root, "target")

    delta = await _callers_with(root, "target", previous_entries=first["callers"])

    assert (
        delta["delta"]["added"],
        delta["delta"]["removed"],
        delta["delta"]["unchanged_count"],
        "callers" in delta,
    ) == ([], [], 1, False)


@pytest.mark.asyncio
async def test_an_empty_complete_answer_carries_an_absence_certificate(
    tmp_path,
) -> None:
    """RFC-0044：0 调用方 + complete + 无开放站点 → proven 缺席证书。"""
    root = await _index_files(
        tmp_path,
        {
            "a.py": "def used():\n    return 1\n\n\ndef entry():\n    return 2\n",
            "b.py": "from a import used\n\n\ndef call():\n    return used()\n",
        },
    )

    result = await _callers(root, "entry")

    assert (result["caller_count"], result["completeness"]) == (0, "complete")
    assert (
        result["absence"]["kind"],
        result["absence"]["confidence"],
        result["absence"]["evidence"][0]["kind"],
    ) == ("unreferenced", "proven", "complete_call_graph")


@pytest.mark.asyncio
async def test_a_referenced_target_has_no_absence_certificate(tmp_path) -> None:
    root = await _index_files(
        tmp_path,
        {
            "a.py": "def used():\n    return 1\n",
            "b.py": "from a import used\n\n\ndef call():\n    return used()\n",
        },
    )

    result = await _callers(root, "used")

    assert (result["caller_count"], "absence" in result) == (1, False)


@pytest.mark.asyncio
async def test_an_unproven_answer_never_claims_absence(tmp_path) -> None:
    """不存在/不完整的答案没有资格证明缺席。"""
    root = await _index_files(tmp_path, {"a.py": "def used():\n    return 1\n"})

    result = await _callers(root, "no_such_symbol")

    assert (result["verdict"], "absence" in result) == ("NOT_FOUND", False)


def test_absence_certificate_requires_zero_open_sites() -> None:
    """即使 completeness 声称 complete，有开放站点也只给 possible。"""
    from tree_sitter_analyzer.mcp.tools.callers_tool import absence_certificate

    result = {
        "caller_count": 0,
        "completeness": "complete",
        "verdict": "WARN",
        "unresolved_inbound": 2,
    }

    certificate = absence_certificate(result)

    assert (certificate["kind"], certificate["confidence"]) == (
        "unknown",
        "possible",
    )


def test_console_script_entry_point_is_recognised(tmp_path) -> None:
    """RFC-0044：`[project.scripts]` 指向的函数是入口点，不是死代码。"""
    from tree_sitter_analyzer.mcp.tools.callers_tool import _console_script_evidence

    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n\n[project.scripts]\nx = "pkg.cli:main"\n'
        '\n[tool.poetry.scripts]\ny = "pkg.cli:run_sub"\n',
        encoding="utf-8",
    )

    # 缺少目标文件时绝不升级（Codex P2：不能把同名函数都当入口点）。
    assert _console_script_evidence(str(tmp_path), "main") is None
    assert (
        _console_script_evidence(str(tmp_path), "main", file_path="pkg/cli.py")
        == '[project.scripts] x = "pkg.cli:main"'
    )
    assert (
        _console_script_evidence(str(tmp_path), "run_sub", file_path="pkg/cli.py")
        == '[tool.poetry.scripts] y = "pkg.cli:run_sub"'
    )
    # 同名但不是脚本模块里的那个函数 → 不签发。
    assert _console_script_evidence(str(tmp_path), "main", file_path="lib.py") is None
    assert _console_script_evidence(str(tmp_path), "not_an_entry") is None


def test_a_missing_manifest_never_proves_an_entry_point(tmp_path) -> None:
    from tree_sitter_analyzer.mcp.tools.callers_tool import _console_script_evidence

    assert (
        _console_script_evidence(str(tmp_path), "main", file_path="pkg/cli.py") is None
    )


@pytest.mark.asyncio
async def test_a_dunder_main_function_is_certified_as_an_entry_point(tmp_path) -> None:
    """``pkg/__main__.py`` 里未被调用的函数 → entry_point + dunder_main 证据。"""
    root = await _index_files(
        tmp_path,
        {
            "pkg/__main__.py": (
                "def helper():\n    return 1\n\n\ndef unused_main():\n    return helper()\n"
            ),
        },
    )

    result = await _callers(root, "unused_main", "pkg/__main__.py")

    absence = result["absence"]
    assert (absence["kind"], absence["confidence"]) == ("entry_point", "proven")
    assert [entry["kind"] for entry in absence["evidence"]] == [
        "complete_call_graph",
        "dunder_main",
    ]


def test_dunder_main_evidence_requires_the_file_to_exist(tmp_path) -> None:
    from tree_sitter_analyzer.mcp.tools.callers_tool import _dunder_main_evidence

    assert _dunder_main_evidence(str(tmp_path), "pkg/missing/__main__.py") is None
    assert _dunder_main_evidence(str(tmp_path), "pkg/cli.py") is None
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__main__.py").write_text("x = 1\n", encoding="utf-8")
    assert _dunder_main_evidence(str(tmp_path), "pkg/__main__.py") == (
        "pkg/__main__.py is the package entry module"
    )


def test_console_script_absence_outranks_plain_unreferenced(tmp_path) -> None:
    """有 console-script 证据时 kind=entry_point，而不是笼统的 unreferenced。"""
    from tree_sitter_analyzer.mcp.tools.callers_tool import absence_certificate

    (tmp_path / "pyproject.toml").write_text(
        '[project.scripts]\nx = "pkg.cli:main"\n', encoding="utf-8"
    )
    result = {"caller_count": 0, "completeness": "complete"}

    certificate = absence_certificate(
        result,
        project_root=str(tmp_path),
        function_name="main",
        file_path="pkg/cli.py",
    )

    assert (certificate["kind"], certificate["evidence"][1]["kind"]) == (
        "entry_point",
        "console_script",
    )


def test_answer_etag_covers_the_inlined_body() -> None:
    """Codex P2：内联函数体是答案内容，改 body 必须改 etag。"""
    from tree_sitter_analyzer.mcp.tools.callers_tool import answer_etag

    base = {
        "function": "target",
        "caller_count": 1,
        "completeness": "complete",
        "callers": [
            {"name": "w", "file": "c.py", "line": 4, "body": "return target() + 1"}
        ],
    }
    edited = {
        **base,
        "callers": [
            {"name": "w", "file": "c.py", "line": 4, "body": "return target() + 2"}
        ],
    }
    without_body = {
        **base,
        "callers": [{"name": "w", "file": "c.py", "line": 4}],
    }

    assert (
        answer_etag(edited) != answer_etag(base),
        answer_etag(without_body) != answer_etag(base),
    ) == (True, True)


def test_sql_fallback_propagates_an_interrupted_read() -> None:
    """#1873：退回 SQL 读时被中断，必须继续传播而不是当作「没有调用行」。"""
    from tree_sitter_analyzer.graph.read_interrupt import ReadInterrupted
    from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

    class _Interrupted:
        def query_callers(self, *args, **kwargs):
            raise ReadInterrupted("interrupted")

    with pytest.raises(ReadInterrupted):
        CodeGraphCallersTool._attach_call_site_lines(
            _Interrupted(), [{"name": "w", "file": "c.py", "line": 4}], "target", None
        )


def test_sql_fallback_skips_rows_without_a_call_line() -> None:
    """没有调用行/调用方名字的边不参与补注。"""
    from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

    class _Rows:
        def query_callers(self, *args, **kwargs):
            return [
                {
                    "caller_name": "",
                    "caller_file": "c.py",
                    "caller_line": 4,
                    "callee_line": 7,
                },
                {
                    "caller_name": "w",
                    "caller_file": "c.py",
                    "caller_line": 4,
                    "callee_line": 0,
                },
            ]

    entries = [{"name": "w", "file": "c.py", "line": 4}]
    CodeGraphCallersTool._attach_call_site_lines(_Rows(), entries, "target", None)

    assert "call_site_line" not in entries[0]


def test_enrichment_skips_entries_that_are_not_caller_dicts() -> None:
    from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

    class _Rows:
        def query_callers(self, *args, **kwargs):
            return [
                {
                    "caller_name": "w",
                    "caller_file": "c.py",
                    "caller_line": 4,
                    "callee_line": 9,
                }
            ]

    entries = ["not-a-caller", {"name": "w", "file": "c.py", "line": 4}]
    CodeGraphCallersTool._attach_call_site_lines(_Rows(), entries, "target", None)

    assert (entries[0], entries[1]["call_site_line"]) == ("not-a-caller", 9)


@pytest.mark.asyncio
async def test_an_invalid_previous_entries_payload_is_refused(tmp_path) -> None:
    """非法 previous_entries（字符串哨兵）→ INVALID_ARGUMENT，而不是静默回完整答案。"""
    root = await _index_files(tmp_path, {"a.py": "def target():\n    return 1\n"})

    result = await _callers_with(
        root, "target", previous_entries="__INVALID_PREVIOUS_ENTRIES__"
    )

    assert (result["success"], result["error_code"]) == (False, "INVALID_ARGUMENT")
    assert "callers" not in result


def test_sql_native_callers_annotates_activation(monkeypatch) -> None:
    """include_activation=True 时读取激活图（缺失时给零值兜底）。"""
    from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

    class _Cache:
        project_root = "."

        def query_callers(self, *args, **kwargs):
            return [
                {
                    "caller_name": "wrapper",
                    "caller_file": "c.py",
                    "caller_line": 4,
                    "callee_line": 7,
                    "callee_resolved_file": "",
                    "receiver_binding": None,
                }
            ]

        def lookup(self, path):
            return None

    tool = CodeGraphCallersTool(".")
    monkeypatch.setattr(tool, "_fetch_activation_map", lambda cache: {})

    callers, _ = tool._sql_native_callers(
        _Cache(), "target", None, include_activation=True
    )

    assert callers[0]["activation"] == {"mod_count_30d": 0, "last_modified_at": None}


def test_script_with_a_shebang_is_certified_as_a_script(tmp_path) -> None:
    """RFC-0044 `script`：带 shebang 的可执行文件里的零调用方函数。"""
    from tree_sitter_analyzer.mcp.tools.callers_tool import absence_certificate

    (tmp_path / "run.py").write_text(
        "#!/usr/bin/env python\n\ndef main_body():\n    return 1\n", encoding="utf-8"
    )
    result = {"caller_count": 0, "completeness": "complete"}

    certificate = absence_certificate(
        result,
        project_root=str(tmp_path),
        function_name="main_body",
        file_path="run.py",
    )

    assert (certificate["kind"], certificate["evidence"][1]["kind"]) == (
        "script",
        "shebang",
    )
    assert certificate["evidence"][1]["detail"] == "run.py starts with #!/usr/bin/env"


def test_a_file_without_a_shebang_stays_unreferenced(tmp_path) -> None:
    """没有 shebang 的普通模块不升级为 script（宁可少说）。"""
    from tree_sitter_analyzer.mcp.tools.callers_tool import absence_certificate

    (tmp_path / "lib.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    result = {"caller_count": 0, "completeness": "complete"}

    certificate = absence_certificate(
        result, project_root=str(tmp_path), function_name="helper", file_path="lib.py"
    )

    assert certificate["kind"] == "unreferenced"


def test_a_missing_script_file_never_proves_anything(tmp_path) -> None:
    from tree_sitter_analyzer.mcp.tools.callers_tool import _script_evidence

    assert _script_evidence(str(tmp_path), "missing.py") is None
    assert _script_evidence(str(tmp_path), None) is None


def test_an_incomplete_empty_answer_is_a_possible_absence() -> None:
    """RFC-0044 降级：空但没有证据时给 unknown/possible，并点名开放站点。"""
    from tree_sitter_analyzer.mcp.tools.callers_tool import absence_certificate

    certificate = absence_certificate(
        {
            "caller_count": 0,
            "completeness": "unknown",
            "verdict": "WARN",
            "unresolved_inbound": 2,
            "completeness_reasons": ["UNRESOLVED_INBOUND"],
        }
    )

    assert (
        certificate["kind"],
        certificate["confidence"],
        certificate["evidence"][0]["kind"],
    ) == ("unknown", "possible", "incomplete_call_graph")
    assert "unresolved=2" in certificate["evidence"][0]["detail"]
    assert "UNRESOLVED_INBOUND" in certificate["evidence"][0]["detail"]


def test_a_not_found_answer_is_never_an_absence() -> None:
    """not-found 不是「没人调用」：没有证书，连 possible 都不给。"""
    from tree_sitter_analyzer.mcp.tools.callers_tool import absence_certificate

    assert (
        absence_certificate(
            {"caller_count": 0, "completeness": "unknown", "verdict": "NOT_FOUND"}
        )
        is None
    )


def test_console_script_entry_certifies_identification_without_completeness(tmp_path):
    """RFC-0044（2026-11-10 补充）：证据不全时，入口点仍签发**识别性**证书。

    真实入口常常是 NOT_FOUND + NON_CALL_REFERENCES（声明文件里有非调用引用），
    此时「零调用方」无法证明，但「它由 console script 进入」是可证的识别性事实。
    """
    from tree_sitter_analyzer.mcp.tools.callers_tool import absence_certificate

    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "cli.py").write_text(
        "def unused_main():\n    return 1\n", encoding="utf-8"
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n\n[project.scripts]\nx = "pkg.cli:unused_main"\n',
        encoding="utf-8",
    )
    result = {
        "verdict": "NOT_FOUND",
        "caller_count": 0,
        "completeness": "unknown",
        "completeness_reasons": ["NON_CALL_REFERENCES"],
    }

    certificate = absence_certificate(
        result,
        project_root=str(tmp_path),
        function_name="unused_main",
        file_path="pkg/cli.py",
    )

    assert certificate is not None
    assert (
        certificate["kind"],
        certificate["confidence"],
        certificate["identification_only"],
    ) == ("entry_point", "proven", True)
    assert [item["kind"] for item in certificate["evidence"]] == [
        "console_script",
        "symbol_defined",
    ]


def test_undefined_symbol_never_gets_an_identification_certificate(tmp_path):
    """符号不在索引里时连「是入口点」都不能说——那是没索引到，不是入口。"""
    from tree_sitter_analyzer.mcp.tools.callers_tool import absence_certificate

    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "cli.py").write_text(
        "def helper():\n    return 1\n", encoding="utf-8"
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n\n[project.scripts]\nx = "pkg.cli:ghost"\n',
        encoding="utf-8",
    )
    result = {
        "verdict": "NOT_FOUND",
        "caller_count": 0,
        "completeness": "unknown",
        "completeness_reasons": ["SYMBOL_NOT_DEFINED"],
    }

    assert (
        absence_certificate(
            result,
            project_root=str(tmp_path),
            function_name="ghost",
            file_path="pkg/cli.py",
        )
        is None
    )


def test_package_dunder_main_certifies_identification_when_incomplete(tmp_path):
    """证据不全时 `__main__.py` 里的函数同样算识别性入口。"""
    from tree_sitter_analyzer.mcp.tools.callers_tool import absence_certificate

    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__main__.py").write_text(
        "def entry():\n    return 1\n", encoding="utf-8"
    )
    result = {
        "verdict": "WARN",
        "caller_count": 0,
        "completeness": "unknown",
        "completeness_reasons": ["NON_CALL_REFERENCES"],
    }

    certificate = absence_certificate(
        result,
        project_root=str(tmp_path),
        function_name="entry",
        file_path="pkg/__main__.py",
    )

    assert certificate is not None
    assert (certificate["kind"], certificate["identification_only"]) == (
        "entry_point",
        True,
    )
    assert [item["kind"] for item in certificate["evidence"]] == [
        "dunder_main",
        "symbol_defined",
    ]


def test_shebang_script_certifies_identification_when_incomplete(tmp_path):
    """证据不全时，带 shebang 的脚本同样算识别性入口。"""
    from tree_sitter_analyzer.mcp.tools.callers_tool import absence_certificate

    (tmp_path / "run.py").write_text(
        "#!/usr/bin/env python\ndef body():\n    return 1\n", encoding="utf-8"
    )
    result = {
        "verdict": "WARN",
        "caller_count": 0,
        "completeness": "unknown",
        "completeness_reasons": ["NON_CALL_REFERENCES"],
    }

    certificate = absence_certificate(
        result,
        project_root=str(tmp_path),
        function_name="body",
        file_path="run.py",
    )

    assert certificate is not None
    assert (certificate["kind"], certificate["identification_only"]) == ("script", True)
    assert [item["kind"] for item in certificate["evidence"]] == [
        "shebang",
        "symbol_defined",
    ]
