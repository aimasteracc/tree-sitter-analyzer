"""大测试文件清单契约：LARGE_TEST_FILE_EXCEPTIONS.md 必须与现实同步。

背景（2026-09-06）：该清单曾是 2026-06-20 的手工快照且无任何强制——
此后超限文件从 13 个悄悄涨到 52 个，16,567 行的巨无霸无声滑入。
本契约把清单变成活文档：新文件越线而不入册、或册上条目已瘦身未除名，
都在 CI 当场变红。阈值 800 行与既有政策一致；无永久豁免。
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
THRESHOLD = 800
DOC = PROJECT_ROOT / "tests" / "LARGE_TEST_FILE_EXCEPTIONS.md"


def _current_oversized() -> dict[str, int]:
    """扫描 tests/ 下全部测试文件,返回 {相对路径: 行数}(超过阈值者)。"""
    result: dict[str, int] = {}
    for path in sorted(PROJECT_ROOT.glob("tests/**/test_*.py")):
        lines = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
        if lines > THRESHOLD:
            result[str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")] = lines
    return result


def _doc_registered() -> set[str]:
    """解析清单表格里的已登记条目路径。"""
    text = DOC.read_text(encoding="utf-8")
    return set(re.findall(r"\|\s*\d+\s*\|\s*`([^`]+)`\s*\|", text))


def test_large_test_file_inventory_matches_reality() -> None:
    current = _current_oversized()
    registered = _doc_registered()
    unregistered = sorted(set(current) - registered)
    stale = sorted(registered - set(current))
    assert not unregistered, (
        "新文件越过 800 行阈值但未登记进 tests/LARGE_TEST_FILE_EXCEPTIONS.md"
        "（拆分它,或带 tracked 引用登记）:\n  "
        + "\n  ".join(f"{current[p]} 行  {p}" for p in unregistered)
    )
    assert not stale, (
        "清单里有文件已瘦身到阈值以下,请从 LARGE_TEST_FILE_EXCEPTIONS.md 除名:\n  "
        + "\n  ".join(stale)
    )


def test_doc_declares_threshold_and_no_permanent_exception_policy() -> None:
    """政策文本必须保留:阈值 800、无永久豁免、触碰时优先拆分。"""
    text = DOC.read_text(encoding="utf-8")
    assert "800" in text
    assert "No file has a permanent size exception" in text


def test_benchmark_harness_modules_follow_project_size_cap() -> None:
    """PR #1393 / #1376：迁移模块遵守 500 行硬上限，而非 800 行告警线。"""
    paths = set(PROJECT_ROOT.glob("tests/unit/test_benchmark_harness*.py"))
    paths.update(PROJECT_ROOT.glob("tests/unit/_benchmark_harness*.py"))
    oversized = {
        path.name: count
        for path in sorted(paths)
        if (count := len(path.read_text(encoding="utf-8").splitlines())) > 500
    }
    assert oversized == {}
