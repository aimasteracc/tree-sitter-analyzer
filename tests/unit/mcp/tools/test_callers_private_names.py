"""PR-1: an ECMAScript private name ``#x`` names only a member literally called ``#x``.

``this.#renderer(...)`` in hono's ``Context`` was read as a shape whose called name
could not be determined, so it counted as "may name any symbol" and blocked
``Context.#newResponse``. A private name is resolved lexically to the ``#x``
declared in an enclosing class body; it can never name a public ``x`` (nor a
public site name ``#x``). TS/JS only; bracket and computed access are unchanged.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.callers_dispatch import (
    NAMES_OTHER_REASON,
    could_name_target,
    partition_by_target,
)
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool


@pytest.mark.parametrize(
    ("callee", "target", "expected"),
    [
        # A private name names only the identical private member.
        ("this.#renderer", "#newResponse", False),
        ("this.#newResponse", "#newResponse", True),
        ("subApp.#addRoute", "#addRoute", True),
        ("other.#addRoute", "#dispatch", False),
        # Private never matches public, and public never matches private.
        ("this.#render", "render", False),
        ("this.render", "#render", False),
        # Bracket / computed access is as before: the guard stays.
        ('this["#render"]', "#newResponse", True),
        ("this[key]", "#newResponse", True),
        ("this.#table[key]", "#newResponse", True),
        ("getattr(x, name)", "#newResponse", True),
        # A public tail after a private prefix is judged by the tail, as before.
        ("this.#fn.call", "#newResponse", False),
        ("this.#fn.apply", "apply", True),
    ],
)
def test_private_name_matches_only_itself_in_ts_js(
    callee: str, target: str, expected: bool
) -> None:
    assert could_name_target(callee, target, private_names=True) is expected


@pytest.mark.parametrize("callee", ["this.#renderer", "x.#y"])
def test_private_name_rule_is_ts_js_only(callee: str) -> None:
    # Without the language opt-in the shape stays undeterminable (guard kept).
    assert could_name_target(callee, "#newResponse") is True
    assert could_name_target(callee, "other") is True


@pytest.mark.parametrize(
    ("file", "kept"),
    [
        ("src/context.ts", False),
        ("src/context.tsx", False),
        ("src/context.js", False),
        ("src/context.mjs", False),
        ("src/context.cjs", False),
        ("src/context.mts", False),
        ("src/context.cts", False),
        ("src/context.jsx", False),
        ("pkg/context.py", True),
        ("Context.java", True),
    ],
)
def test_partition_applies_the_private_rule_by_file_language(
    file: str, kept: bool
) -> None:
    site = {"file": file, "line": 4, "callee": "this.#renderer"}
    remaining, excluded = partition_by_target([site], "#newResponse")
    assert (remaining == [site]) is kept
    if not kept:
        assert excluded[0]["reason_code"] == NAMES_OTHER_REASON


_TS = (
    "export class Ctx {\n"
    "  #renderer: () => string = () => 'x'\n"
    "  #make(): string {\n"
    "    return 'm'\n"
    "  }\n"
    "  render(): string {\n"
    "    return this.#renderer()\n"
    "  }\n"
    "  build(): string {\n"
    "    return this.#make()\n"
    "  }\n"
    "}\n"
)


async def _index(root: Path, files: dict[str, str]) -> str:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    indexed = await CodeGraphFullIndexTool(str(root)).execute(
        {"mode": "full", "max_files": 20}
    )
    assert indexed["published"] is True
    return str(root)


async def _callers(root: str, name: str) -> dict:
    return await CodeGraphCallersTool(root).execute(
        {"function_name": name, "include_bodies": False}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["Ctx.#make", "#make"])
async def test_private_field_call_no_longer_blocks_another_private_method(
    tmp_path: Path, name: str
) -> None:
    root = await _index(tmp_path, {"src/ctx.ts": _TS})

    result = await _callers(root, name)

    assert "this.#renderer" not in [s["callee"] for s in result["unresolved_sites"]]
    assert "UNRESOLVED_IN_DECLARING_FILE" not in result["completeness_reasons"]
    assert result["completeness"] == "complete"
    assert [c["name"] for c in result["callers"]] == ["build"]


@pytest.mark.asyncio
async def test_public_target_with_the_same_spelling_is_not_named_by_a_private_call(
    tmp_path: Path,
) -> None:
    text = _TS.replace("  render(): string {", "  renderer(): string {")
    root = await _index(tmp_path, {"src/ctx.ts": text})

    result = await _callers(root, "Ctx.renderer")

    assert "this.#renderer" not in [s["callee"] for s in result["unresolved_sites"]]


@pytest.mark.asyncio
async def test_bracket_access_on_this_still_blocks(tmp_path: Path) -> None:
    text = _TS.replace("return this.#make()", "return this[key]()")
    root = await _index(tmp_path, {"src/ctx.ts": text})

    result = await _callers(root, "Ctx.#make")

    assert result["completeness"] != "complete"
    assert "UNRESOLVED_IN_DECLARING_FILE" in result["completeness_reasons"]
