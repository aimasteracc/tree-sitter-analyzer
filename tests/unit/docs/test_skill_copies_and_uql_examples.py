"""技能文档守护: 打包副本与 .claude 副本一致，且其中的 UQL 示例都能被解析。"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tree_sitter_analyzer.uql.errors import Ok
from tree_sitter_analyzer.uql.parser import parse_query

_REPO = Path(__file__).resolve().parents[3]
_DEV_SKILLS = _REPO / ".claude" / "skills"
_PKG_SKILLS = _REPO / "tree_sitter_analyzer" / "skills"

#: 技能文中 ``search action=uql query="..."`` 的查询体。
_UQL_QUERY = re.compile(r'action=uql\s+query="([^"]+)"')
#: 文档占位符 (如 ``<sym1>``) 替换为合法符号名后再解析。
_PLACEHOLDER = re.compile(r"<[^<>'\"]+>")


def _pkg_skill_names() -> list[str]:
    return sorted(p.parent.name for p in _PKG_SKILLS.glob("tsa-*/SKILL.md"))


def _uql_examples() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for skill_md in sorted(_PKG_SKILLS.glob("tsa-*/SKILL.md")):
        text = skill_md.read_text(encoding="utf-8")
        for query in _UQL_QUERY.findall(text):
            found.append((skill_md.parent.name, query))
    return found


@pytest.mark.parametrize("name", _pkg_skill_names())
def test_packaged_skill_matches_dev_copy(name: str) -> None:
    dev = _DEV_SKILLS / name / "SKILL.md"
    if not dev.is_file():
        pytest.skip(f"{name} has no .claude/skills copy in this checkout")
    pkg = _PKG_SKILLS / name / "SKILL.md"
    assert pkg.read_bytes() == dev.read_bytes(), (
        f"{pkg} drifted from {dev}; copy the edited file over the other"
    )


def test_skills_carry_uql_examples() -> None:
    # 至少这些技能承担多跳路由说明; 若示例被删除，此处应当失败而不是静默通过。
    skills_with_uql = {skill for skill, _ in _uql_examples()}
    assert {"tsa-graph", "tsa-find", "tsa-edit-safety", "tsa-pr-review"} <= (
        skills_with_uql
    )


@pytest.mark.parametrize(("skill", "query"), _uql_examples(), ids=lambda v: str(v)[:60])
def test_skill_uql_example_parses(skill: str, query: str) -> None:
    concrete = _PLACEHOLDER.sub("some_symbol", query)
    result = parse_query(concrete)
    assert isinstance(result, Ok), f"{skill}: {query!r} -> {result!r}"
