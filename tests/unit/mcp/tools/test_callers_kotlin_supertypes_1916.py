"""#1916: a Kotlin override reached by dynamic dispatch is not ``complete, 0``.

Kotlin classes had no supertype edges, so ``this.make()`` in ``A.run`` was bound
to ``A.make`` and the overrides in ``class B : A<String>()`` / ``class C :
A<String>()`` were never offered as possible targets: ``B.make`` answered
``complete`` with 0 callers although ``A.run`` may call it.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.callers_reasons import NAME_ONLY_REASON
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_REPRO = {
    "p/A.kt": (
        "package p\n\n"
        "open class A<T> {\n"
        "    fun run(): String {\n"
        "        return this.make()\n"
        "    }\n\n"
        '    open fun make(): String = "a"\n'
        "}\n"
    ),
    "p/B.kt": (
        'package p\n\nclass B : A<String>() {\n    override fun make(): String = "b"\n}\n'
    ),
    "p/C.kt": (
        'package p\n\nclass C : pkg.Other(), I {\n    fun make(): String = "c"\n}\n'
    ),
}


async def _answers(tmp_path, *names: str) -> list[dict]:
    """Index the repro once, then ask ``callers`` for each name."""
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    for rel_path, text in _REPRO.items():
        path = tmp_path / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 20}
    )
    assert indexed["published"] is True
    tool = CodeGraphCallersTool(str(tmp_path))
    return [
        await tool.execute({"function_name": name, "include_bodies": False})
        for name in names
    ]


@pytest.mark.asyncio
async def test_override_of_a_generic_kotlin_supertype_is_not_complete(
    tmp_path,
) -> None:
    (result,) = await _answers(tmp_path, "B.make")

    # Before #1916: ``complete`` with 0 callers. Now ``this.make()`` in
    # ``A.run`` is a possible target and the answer names that site.
    assert result["caller_count"] == 0
    assert result["completeness"] == "unknown", result
    assert result["completeness_reasons"] == [NAME_ONLY_REASON]
    assert "p/A.kt:5" in result["next_step"], result["next_step"]


@pytest.mark.asyncio
async def test_the_base_method_and_an_unrelated_class_stay_provable(tmp_path) -> None:
    base, unrelated = await _answers(tmp_path, "A.make", "C.make")

    assert base["completeness"] == "complete", base
    assert base["caller_count"] == 1
    # ``C`` does not extend ``A``: ``this.make()`` in ``A`` cannot reach it.
    assert unrelated["completeness"] == "complete", unrelated
    assert unrelated["caller_count"] == 0
