"""change-impact 的**文本引用**第二通道（dogfood 2026-11-09 P1-4）。

依赖图只认「导入后调用」这一种关系。测试文件里通过 `import tree_sitter_analyzer.cache.search`
再取属性的写法、或经由包 `__init__` 间接引用时，图上看不到边，于是被改动的模块的真实测试
会被漏掉——实测 5 个直接引用 `cache.search` 的测试文件里漏了 4 个。

这里只做**保守的字符串证据**：对每个被改动的 Python 模块，构造两三种导入写法，扫描
`tests/` 下的文件，把「引用了但没被依赖图选中」的文件单独列出来。它不进 `tests_to_run`
（文本匹配不能当确定依赖），而是作为 `text_reference_tests` 供 agent 自行取舍。
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

#: 单次最多列出的补充文件数（防止巨型仓库把响应撑爆）。
TEXT_REFERENCE_LIMIT = 20


def _dotted_module(changed_rel: str) -> str:
    normalized = changed_rel.replace("\\", "/")
    return normalized[: -len(".py")].replace("/", ".")


def _is_real_import(text: str, dotted: str) -> bool:
    """该模块是否被**导入**（而不是只在注释/字符串里被提到）。"""
    import re

    parent, _, leaf = dotted.rpartition(".")
    alternatives = [
        rf"from\s+{re.escape(dotted)}\s+import\b",
        rf"import\s+{re.escape(dotted)}\b",
    ]
    if parent:
        # `from pkg.cache import search` 也是真导入（包属性式引用）。
        alternatives.append(
            rf"from\s+{re.escape(parent)}\s+import\s+[^\n]*\b{re.escape(leaf)}\b"
        )
    pattern = re.compile(r"^\s*(?:" + "|".join(alternatives) + ")", re.MULTILINE)
    return pattern.search(text) is not None


def _import_probes(changed_rel: str) -> tuple[str, ...]:
    """被改动模块的几种常见引用写法（保守：只取足够长的片段）。"""
    normalized = changed_rel.replace("\\", "/")
    if not normalized.endswith(".py") or normalized.endswith("__init__.py"):
        return ()
    stem = normalized[: -len(".py")]
    dotted = stem.replace("/", ".")
    parts = dotted.split(".")
    probes = [dotted]
    if len(parts) >= 2:
        # `from pkg import mod` / `from pkg import mod as x`
        probes.append(f"from {'.'.join(parts[:-1])} import {parts[-1]}")
    if len(parts) >= 3:
        # 相对包的短写：`cache.search`
        probes.append(".".join(parts[-2:]))
    return tuple(probe for probe in probes if len(probe) >= 8)


def _iter_test_files(project_root: str) -> Iterable[Path]:
    tests_root = Path(project_root) / "tests"
    if not tests_root.is_dir():
        return ()
    return tests_root.rglob("*.py")


def text_reference_tests(
    project_root: str,
    *,
    changed_paths: Iterable[str],
    selected: Iterable[str],
    limit: int = TEXT_REFERENCE_LIMIT,
) -> list[dict[str, Any]]:
    """返回「文本引用了改动模块、但依赖图没选中」的测试文件。"""
    probes: dict[str, str] = {}
    for changed in changed_paths:
        for probe in _import_probes(str(changed)):
            probes.setdefault(probe, str(changed))
    if not probes:
        return []
    selected_set = {str(path).replace("\\", "/") for path in selected}
    found: list[dict[str, Any]] = []
    for path in _iter_test_files(project_root):
        rel = os.path.relpath(path, project_root).replace("\\", "/")
        if rel in selected_set:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for probe, changed in probes.items():
            if probe not in text:
                continue
            confidence = (
                "import"
                if _is_real_import(text, _dotted_module(changed))
                else "mention"
            )
            found.append(
                {
                    "file": rel,
                    "matched": probe,
                    "changed": changed,
                    # 两级证据：真的 import 了（高可信）vs 只在文本里出现（提示）。
                    "confidence": confidence,
                }
            )
            break
        if len(found) >= limit:
            break
    # import 级证据排在前面：它们最可能是被漏掉的真实覆盖。
    return sorted(
        found, key=lambda item: (item["confidence"] != "import", item["file"])
    )
