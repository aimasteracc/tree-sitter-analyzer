#!/usr/bin/env python3
"""复制品一致性：改了打包 skill 就必须同一次提交里改开发副本（反之亦然）。

为什么需要它（2026-11-10，PR #1939 第 76 轮）：我把
``tree_sitter_analyzer/skills/tsa-graph/SKILL.md`` 更新了，却漏了被跟踪的
``.claude/skills/tsa-graph/SKILL.md``。本地 ``tests/unit/docs`` 之所以全绿，是因为
工作区两份内容一致——**差异只存在于提交之后**（一份已提交、一份在工作区）。也就是说：
这个错误在本地静态测试里天然不可见，只有在 CI 检出那次提交后才红。

pre-commit 能看到「这次要提交什么」，所以它才是能拦住这个错误的层。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PACKAGED = "tree_sitter_analyzer/skills/"
DEV = ".claude/skills/"


def _staged() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def _pairs(path: str) -> tuple[str, str] | None:
    """返回 (打包路径, 开发副本路径)；不是 skill 文件则 None。"""
    if path.startswith(PACKAGED) and path.endswith("SKILL.md"):
        return path, DEV + path[len(PACKAGED) :]
    if path.startswith(DEV) and path.endswith("SKILL.md"):
        return PACKAGED + path[len(DEV) :], path
    return None


def main() -> int:
    staged = set(_staged())
    problems: list[str] = []
    for path in sorted(staged):
        pair = _pairs(path)
        if pair is None:
            continue
        packaged, dev = pair
        if not Path(dev).exists() and not Path(packaged).exists():
            continue
        if not Path(dev).exists():
            # 开发副本不存在（例如浅检出或仅打包发布的场景）：不阻塞。
            continue
        if packaged in staged and dev in staged:
            continue
        if Path(packaged).read_bytes() != Path(dev).read_bytes():
            missing = dev if path == packaged else packaged
            problems.append(f"{path} 已暂存，但 {missing} 内容不同且未一起暂存")
    if problems:
        sys.stderr.write(
            "复制品不一致（CI 的 test_packaged_skill_matches_dev_copy 会红）：\n  "
            + "\n  ".join(problems)
            + "\n修复：把另一份也同步后一起 git add。\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
