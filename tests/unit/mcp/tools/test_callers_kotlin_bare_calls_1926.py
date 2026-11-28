"""#1926: a Kotlin bare call to an inherited method may reach a subclass override.

In Kotlin the usual style calls an inherited method without a receiver: ``make()``
inside ``A.run`` means ``this.make()``. Only Java treated a bare call as ``this``,
so the override ``B.make`` in ``class B : A()`` answered ``complete`` with 0
callers although ``A.run`` may call it.

A bare call does not always mean ``this``: inside a lambda with receiver
(``apply {}``, ``with(x) {}``, ``run {}``, DSL builders) it may be the receiver's
method, and a local or top-level function of the same name shadows the member
for the bare name. Those sites stay open; the override is still not ``complete``.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_BASE = {
    "p/A.kt": (
        "package p\n\n"
        "open class A {\n"
        "    fun run(): String {\n"
        "        return make()\n"
        "    }\n\n"
        '    open fun make(): String = "a"\n\n'
        '    open fun other(): String = "o"\n'
        "}\n"
    ),
    "p/B.kt": (
        "package p\n\n"
        "class B : A() {\n"
        '    override fun make(): String = "b"\n\n'
        '    override fun other(): String = "ob"\n'
        "}\n"
    ),
    "p/C.kt": ('package p\n\nclass C {\n    fun make(): String = "c"\n}\n'),
}


async def _answers(tmp_path, files: dict[str, str], *names: str) -> list[dict]:
    """Index ``files`` once, then ask ``callers`` for each name."""
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    for rel_path, text in files.items():
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
async def test_override_reached_by_a_bare_call_in_the_base_is_not_complete(
    tmp_path,
) -> None:
    (result,) = await _answers(tmp_path, _BASE, "B.make")

    # Before #1926: ``complete`` with 0 callers.
    assert result["caller_count"] == 0
    assert result["completeness"] != "complete", result
    assert "p/A.kt:5" in result["next_step"], result["next_step"]


@pytest.mark.asyncio
async def test_unrelated_names_stay_complete(tmp_path) -> None:
    base, other, unrelated = await _answers(
        tmp_path, _BASE, "A.make", "B.other", "C.make"
    )

    # ``make()`` in ``A.run`` is certain for ``A``'s own ``make``.
    assert base["completeness"] == "complete", base
    assert base["caller_count"] == 1
    # Nothing calls ``other``; ``C`` does not extend ``A``.
    assert other["completeness"] == "complete", other
    assert other["caller_count"] == 0
    assert unrelated["completeness"] == "complete", unrelated
    assert unrelated["caller_count"] == 0


_NO_RECEIVER_LAMBDA = {
    **_BASE,
    "p/A.kt": (
        "package p\n\n"
        "open class A {\n"
        "    fun run(items: List<Int>) {\n"
        "        items.forEach { make() }\n"
        "    }\n\n"
        '    open fun make(): String = "a"\n\n'
        '    open fun other(): String = "o"\n'
        "}\n"
    ),
}


@pytest.mark.asyncio
async def test_bare_call_in_a_lambda_without_receiver_binds_like_this(
    tmp_path,
) -> None:
    override, base, unrelated = await _answers(
        tmp_path, _NO_RECEIVER_LAMBDA, "B.make", "A.make", "C.make"
    )

    # ``forEach``'s lambda has no receiver: ``make()`` is still ``this.make()``.
    assert override["completeness"] != "complete", override
    assert "p/A.kt:5" in override["next_step"], override["next_step"]
    assert base["completeness"] == "complete", base
    assert base["caller_count"] == 1
    assert unrelated["completeness"] == "complete", unrelated


_APPLY_ON_THIS = {
    **_BASE,
    "p/A.kt": (
        "package p\n\n"
        "open class A {\n"
        "    fun run(): A = apply {\n"
        "        make()\n"
        "    }\n\n"
        '    open fun make(): String = "a"\n\n'
        '    open fun other(): String = "o"\n'
        "}\n"
    ),
}


@pytest.mark.asyncio
async def test_bare_call_in_apply_on_this_binds_like_this(tmp_path) -> None:
    override, base, unrelated = await _answers(
        tmp_path, _APPLY_ON_THIS, "B.make", "A.make", "C.make"
    )

    # ``apply { }`` called on the implicit ``this`` has that ``this`` as receiver.
    assert override["completeness"] != "complete", override
    assert "p/A.kt:5" in override["next_step"], override["next_step"]
    assert base["completeness"] == "complete", base
    assert base["caller_count"] == 1
    assert unrelated["completeness"] == "complete", unrelated


_INHERITED = {
    **_BASE,
    "p/B.kt": (
        "package p\n\n"
        "class B : A() {\n"
        "    fun go(): String = make()\n\n"
        '    override fun other(): String = "ob"\n'
        "}\n"
    ),
}


@pytest.mark.asyncio
async def test_bare_call_to_an_inherited_method_stays_open(tmp_path) -> None:
    base, unrelated = await _answers(tmp_path, _INHERITED, "A.make", "B.other")

    # ``B`` does not declare ``make``: the inherited (or an outer / companion)
    # ``make`` is called; the site is open and ``A.make`` is not ``complete``.
    assert base["completeness"] != "complete", base
    assert unrelated["completeness"] == "complete", unrelated


_LAMBDA = {
    **_BASE,
    "p/A.kt": (
        "package p\n\n"
        "class Box {\n"
        '    fun make(): String = "box"\n'
        "}\n\n"
        "open class A {\n"
        "    fun run(box: Box): String {\n"
        "        return box.apply { make() }.toString()\n"
        "    }\n\n"
        '    open fun make(): String = "a"\n\n'
        '    open fun other(): String = "o"\n'
        "}\n"
    ),
}


@pytest.mark.asyncio
async def test_bare_call_inside_a_lambda_with_receiver_stays_open(tmp_path) -> None:
    override, box, base, other_type, unrelated = await _answers(
        tmp_path, _LAMBDA, "B.make", "Box.make", "A.make", "C.make", "B.other"
    )

    # ``make()`` inside ``apply {}`` is the receiver's ``make`` when it has one,
    # else ``A.make`` (and so ``B.make``). The site is open: no ``make`` method is
    # certain and none may answer ``complete`` -- the index does not know the
    # receiver's type, so ``C.make`` is a possible target too.
    for answer in (override, box, base, other_type):
        assert answer["completeness"] != "complete", answer
        assert answer["caller_count"] == 0, answer
    assert "p/A.kt:9" in override["next_step"], override["next_step"]
    # A name nobody calls stays provable.
    assert unrelated["completeness"] == "complete", unrelated


_LOCAL = {
    **_BASE,
    "p/A.kt": (
        "package p\n\n"
        "open class A {\n"
        "    fun run(): String {\n"
        '        fun make(): String = "local"\n'
        "        return make()\n"
        "    }\n\n"
        '    open fun make(): String = "a"\n\n'
        '    open fun other(): String = "o"\n'
        "}\n"
    ),
}


@pytest.mark.asyncio
async def test_bare_call_next_to_a_local_function_is_not_complete(tmp_path) -> None:
    (override,) = await _answers(tmp_path, _LOCAL, "B.make")

    # The local ``make`` shadows the member; the site is not guessed either way,
    # and the override does not answer ``complete``.
    assert override["completeness"] != "complete", override


_TOP_LEVEL = {
    **_BASE,
    "p/A.kt": (
        "package p\n\n"
        'fun make(): String = "top"\n\n'
        "open class A {\n"
        "    fun run(): String {\n"
        "        return make()\n"
        "    }\n\n"
        '    open fun make(): String = "a"\n\n'
        '    open fun other(): String = "o"\n'
        "}\n"
    ),
}


@pytest.mark.asyncio
async def test_bare_call_next_to_a_top_level_function_is_not_complete(
    tmp_path,
) -> None:
    (override,) = await _answers(tmp_path, _TOP_LEVEL, "B.make")

    # The member wins over the top-level function in Kotlin, but the index
    # cannot tell; the site stays open and the override is not ``complete``.
    assert override["completeness"] != "complete", override
