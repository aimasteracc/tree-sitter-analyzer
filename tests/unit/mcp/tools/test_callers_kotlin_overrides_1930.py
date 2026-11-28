"""#1930: a Kotlin ``override`` of an external supertype is never ``complete``.

``class F : java.io.Closeable { override fun close() }`` is called by whoever
holds a ``Closeable`` (``use { }``, the JDK, a library). Those callers are outside
the project, so ``0 callers`` is not evidence of absence. Before the fix the
answer was ``complete``.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.callers_java_overrides import OVERRIDE_REASON
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_REPRO = {
    "p/F.kt": (
        "package p\n\n"
        "class F : java.io.Closeable {\n"
        "    override fun close() {\n"
        "    }\n"
        "}\n"
    ),
    "p/G.kt": (
        "package p\n\n"
        "import java.io.Closeable\n\n"
        "class G(override val size: Int) : Closeable, Sized {\n"
        "    override fun close() {\n"
        "    }\n\n"
        '    override fun toString(): String = "g"\n'
        "}\n"
    ),
    "p/Res.kt": (
        "package p\n\n"
        "interface Res : AutoCloseable\n\n"
        "class R : Res {\n"
        "    override fun close() {\n"
        "    }\n"
        "}\n"
    ),
    "p/Shape.kt": (
        "package p\n\n"
        "interface Shape {\n"
        "    fun area(): Int\n"
        "}\n\n"
        "interface Sized {\n"
        "    val size: Int\n"
        "}\n"
    ),
    "q/Square.kt": (
        "package q\n\n"
        "import p.Shape\n\n"
        "class Square : Shape {\n"
        "    override fun area(): Int = 4\n\n"
        "    fun side(): Int = 2\n"
        "}\n"
    ),
    "p/Main.kt": "package p\n\nfun main() {\n    helper()\n}\n\nfun helper() {\n}\n",
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
async def test_override_of_a_qualified_external_interface_is_not_complete(
    tmp_path,
) -> None:
    (result,) = await _answers(tmp_path, "F.close")

    assert result["caller_count"] == 0
    assert result["completeness"] != "complete", result
    assert OVERRIDE_REASON in result["completeness_reasons"], result
    assert "java.io.Closeable" in result["next_step"], result["next_step"]


@pytest.mark.asyncio
async def test_override_of_an_imported_or_inherited_external_member_is_not_complete(
    tmp_path,
) -> None:
    imported, any_member, through_project = await _answers(
        tmp_path, "G.close", "G.toString", "R.close"
    )

    for result in (imported, any_member, through_project):
        assert result["completeness"] != "complete", result
        assert OVERRIDE_REASON in result["completeness_reasons"], result
    assert "Closeable" in imported["next_step"], imported["next_step"]
    assert "kotlin.Any" in any_member["next_step"], any_member["next_step"]
    # ``Res`` is in the project, but it extends ``AutoCloseable``.
    assert "AutoCloseable" in through_project["next_step"]


@pytest.mark.asyncio
async def test_override_closed_in_the_project_and_plain_methods_stay_complete(
    tmp_path,
) -> None:
    square_area, square_side = await _answers(tmp_path, "Square.area", "Square.side")

    # ``Shape`` is declared in the project and nothing calls ``area``.
    assert square_area["completeness"] == "complete", square_area
    assert square_area["caller_count"] == 0
    assert square_side["completeness"] == "complete", square_side
