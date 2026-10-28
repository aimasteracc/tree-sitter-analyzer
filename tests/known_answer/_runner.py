"""已知答案语料的执行器：每个用例真实全量索引一次，两种模式各查询一次。"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.wrong_complete.py_oracle import python_sites
from scripts.wrong_complete.scorer import ListedCaller, listed_callers
from scripts.wrong_complete.sites import TARGET, Site
from scripts.wrong_complete.token_oracle import token_sites
from scripts.wrong_complete.tsa_driver import (
    index_project,
    query_callers,
    write_project,
)
from tests.known_answer._cases import MODES, Case


@dataclass(frozen=True)
class Observation:
    """一个用例的 TSA 回答（按模式）与独立判定器结果。"""

    case: Case
    answers: Mapping[str, Mapping[str, Any]]
    sites: tuple[Site, ...]
    #: RFC-0041 跨名批量：一次 ``execute_batch``（查询作用域内）与逐个单次调用的答复
    #: 不一致的输入；应为空。
    batch_mismatches: tuple[str, ...] = ()
    #: #1798：同两种模式、但不带 ``file_path`` 的回答。
    unscoped: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    def callers(self, mode: str) -> list[ListedCaller]:
        """该模式列出的调用方（TS 缺失的 ``end_line`` 按源码补齐）。"""
        return listed_callers(self.answers[mode], self.case.files)

    def listed_truth(self, mode: str) -> frozenset[tuple[str, int]]:
        """该模式下被某个已列出调用方覆盖的真值调用点。"""
        callers = self.callers(mode)
        return frozenset(
            site.key()
            for site in truth_sites(self.case)
            if any(c.covers(site) for c in callers)
        )


def truth_sites(case: Case) -> tuple[Site, ...]:
    """把手写真值包装成 ``Site``（用于覆盖判定）。"""
    return tuple(
        Site(f, line, "call", TARGET, "hand_label", "")
        for f, line in sorted(case.truth)
    )


def oracle_sites(case: Case) -> tuple[Site, ...]:
    """独立判定器（Python ``ast`` 或 token 扫描）对该用例的结果。"""
    target = case.target
    oracle = python_sites if target.file.endswith(".py") else token_sites
    return tuple(oracle(dict(case.files), target))


#: 夹具里出现的名字（Python ``def`` / ``class``，JS/TS ``function``，形如方法头的行）。
#: 只用来凑一个跨名批量：多收的名字同样是合法输入。
_DEFINED = re.compile(
    r"^[ \t]*(?:async[ \t]+)?(?:def|class|function)[ \t]+(\w+)"
    r"|^[ \t]*(?:(?:public|private|protected|static)[ \t]+)*[\w<>\[\]]+[ \t]+(\w+)\(",
    re.MULTILINE,
)


def batch_requests(case: Case) -> list[dict[str, Any]]:
    """两种模式的目标，加上夹具里定义的每个其他名字（不限文件），作为一次批量。"""
    requests = [
        {
            "function_name": case.query_name(mode),
            "file_path": case.target.file,
            "include_bodies": False,
            "limit": 5000,
        }
        for mode in MODES
    ]
    names = sorted(
        {
            name
            for text in case.files.values()
            for match in _DEFINED.finditer(text)
            if (name := match.group(1) or match.group(2))
        }
    )
    requests.extend(
        {"function_name": name, "include_bodies": False, "limit": 5000}
        for name in names
    )
    return requests


async def _batch_mismatches(root: Path, case: Case) -> tuple[str, ...]:
    """查询作用域内一次批量回答全部输入；与逐个单次调用逐字节比较。"""
    from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool
    from tree_sitter_analyzer.query_scope import query_scope

    tool = CodeGraphCallersTool(str(root))
    requests = batch_requests(case)
    single = [await tool.execute(dict(r)) for r in requests]
    with query_scope():
        batched = await tool.execute_batch([dict(r) for r in requests])
    return tuple(
        f"{r['function_name']}@{r.get('file_path')}"
        for r, one, many in zip(requests, single, batched, strict=True)
        if json.dumps(one, sort_keys=True) != json.dumps(many, sort_keys=True)
    )


async def _observe(case: Case, root: Path) -> Observation:
    write_project(root, dict(case.files))
    await index_project(root)
    answers = {
        mode: await query_callers(root, case.query_name(mode), case.target.file)
        for mode in MODES
    }
    unscoped = {
        mode: await query_callers(root, case.query_name(mode), None) for mode in MODES
    }
    return Observation(
        case=case,
        answers=answers,
        sites=oracle_sites(case),
        batch_mismatches=await _batch_mismatches(root, case),
        unscoped=unscoped,
    )


def observe(case: Case, root: Path) -> Observation:
    """同步入口（测试函数本身是同步的，避免与 Hypothesis / 事件循环夹具纠缠）。"""
    return asyncio.run(_observe(case, root))
