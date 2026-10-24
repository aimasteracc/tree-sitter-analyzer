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
