"""文档里写出来的 `--flag` 必须真的存在，否则它就是一个幽灵接口。

为什么需要这条契约：dogfood 报告曾把 `--since`、`--cost` 写成既有旗标（第 67 轮更正），
而没有任何测试会发现——`cli.md` 的计数契约只比对**数量**，不比对**被文档承诺的名字**。
一个 agent 读到不存在的旗标，会构造一个必然失败的调用，然后把失败归因到索引或自己的语法。

范围限定在「面向 agent 的 TSA 文档」：AGENTS.md / CLAUDE.md 里混有其他工具（pytest、git、
ruff、npx claude-flow）的旗标，整篇扫描会变成一张巨大且无意义的白名单。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: 二手材料里明确提到、但**故意不存在**的旗标：它们是「反例」，不是承诺。
DOCUMENTED_NON_FLAGS = {
    # §12.3 修订：报告承认 `--cost` 从未实现，用来说明「按查询估算仍是设计题」。
    "--cost",
    # CLAUDE.md 规则 4 的反例：`--smart-context --query` 是 agent 自己编的用法。
    "--query",
}

DOCUMENTED_FILES = (
    "docs/agent-envelope-contract.md",
    "docs/dev/dogfood-trust-2026-11-09.md",
    "docs/CODEMAPS/cli.md",
    "docs/CODEMAPS/mcp-tools.md",
    "tree_sitter_analyzer/skills/tsa-graph/SKILL.md",
)

_FLAG = re.compile(r"(?<![\w-])--[a-z][a-z0-9-]+")


#: 反引号片段里出现这些词，说明它讲的是**别的工具**的旗标（git / pytest / ruff / uv / npm…）。
OTHER_TOOL_TOKENS = (
    "git ",
    "pytest",
    "ruff",
    "uv ",
    "npm ",
    "npx ",
    "gh ",
    "python -m tree_sitter_analyzer.mcp",
    "mcp-publisher",
    "claude-flow",
    "kcov",
)


def _is_main_cli_claim(span: str) -> bool:
    """只有「主 CLI 的调用」才算承诺：`tsa …` 或 `python -m tree_sitter_analyzer …`。"""
    if any(token in span for token in OTHER_TOOL_TOKENS):
        return False
    return span.startswith("tsa ") or "python -m tree_sitter_analyzer " in span


def _documented_flags(text: str) -> set[str]:
    """只认反引号代码片段里的旗标：正文散文里提到工具名不算承诺。

    **逐行**配对反引号，而不是全文配对：全文 `re.findall(r"`([^`]+)`", text)` 在文件
    总反引号数为奇数时整体错位，末尾的片段会被漏掉——那会让这条契约变成「看不见自己要
    看的输入」的门禁（本仓库已经为此付过一次代价，见 AI_LESSONS 第 31 条）。
    """
    flags: set[str] = set()
    for line in text.splitlines():
        for span in re.findall(r"`([^`]+)`", line):
            if _is_main_cli_claim(span):
                flags.update(_FLAG.findall(span))
    return flags


def _parser_flags() -> set[str]:
    from tree_sitter_analyzer.cli_main import create_argument_parser

    parser = create_argument_parser()
    return {
        option
        for action in parser._actions
        for option in action.option_strings
        if option.startswith("--")
    }


def test_every_documented_flag_exists_in_the_real_parser() -> None:
    """文档承诺的每个 `--flag` 都必须在真实 argparse 里存在（反例除外）。"""
    real = _parser_flags()
    documented: dict[str, str] = {}
    for relative in DOCUMENTED_FILES:
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        for flag in _documented_flags(text):
            documented.setdefault(flag, relative)

    phantom = sorted(set(documented) - real - DOCUMENTED_NON_FLAGS)

    assert phantom == [], (
        "these flags appear in agent-facing docs but do not exist in the CLI: "
        + ", ".join(f"{flag} ({documented[flag]})" for flag in phantom)
    )


def test_the_non_flag_allowlist_stays_honest() -> None:
    """白名单不能变成藏污纳垢处：其中每一项都必须仍然是一个不存在的旗标。"""
    real = _parser_flags()

    assert sorted(DOCUMENTED_NON_FLAGS - real) == sorted(DOCUMENTED_NON_FLAGS)


def test_the_capability_table_flags_all_exist() -> None:
    """`docs/CODEMAPS/mcp-tools.md` 的「CLI flag」列写的旗标必须真实存在。

    这一列的片段是裸旗标（`--check-scale`），没有 `tsa ` 前缀，所以主 CLI 片段规则
    覆盖不到它们——而这一列正是「能力 → 命令」的承诺表，写错就等于教 agent 用错命令。
    """
    from tree_sitter_analyzer.cli_main import create_argument_parser

    real = {
        option
        for action in create_argument_parser()._actions
        for option in action.option_strings
        if option.startswith("--")
    }
    rows = [
        line
        for line in (REPO_ROOT / "docs/CODEMAPS/mcp-tools.md")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.startswith("| `")
    ]
    phantom: dict[str, str] = {}
    for line in rows:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        for span in re.findall(r"`([^`]+)`", cells[1]):
            for flag in _FLAG.findall(span):
                if flag not in real and flag not in DOCUMENTED_NON_FLAGS:
                    phantom.setdefault(flag, cells[0])

    assert phantom == {}, (
        "these flags appear in the capability table but do not exist: "
        + ", ".join(f"{flag} ({row})" for flag, row in sorted(phantom.items()))
    )


def test_the_generated_facade_table_cli_twins_all_exist() -> None:
    """`docs/api/facade-actions.md` 的「CLI twin」列必须指向真实旗标。

    这张表是生成物（`scripts/generate_facade_actions_doc.py`），参数列已由 drift 测试
    保证与 schema 一致；但**CLI twin 来自 facade map 的映射**，映射写错（指向已删旗标）
    时 drift 测试不会红——只有这条能发现。
    """
    from tree_sitter_analyzer.cli_main import create_argument_parser

    real = {
        option
        for action in create_argument_parser()._actions
        for option in action.option_strings
        if option.startswith("--")
    }
    rows = [
        line
        for line in (REPO_ROOT / "docs/api/facade-actions.md")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.startswith("| `")
    ]
    phantom: dict[str, str] = {}
    for line in rows:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 4:
            continue
        for flag in _FLAG.findall(cells[3]):
            if flag not in real:
                phantom.setdefault(flag, cells[0])

    assert phantom == {}, "these CLI twins do not exist in the parser: " + ", ".join(
        f"{flag} ({row})" for flag, row in sorted(phantom.items())
    )
