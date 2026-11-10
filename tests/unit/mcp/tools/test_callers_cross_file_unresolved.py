"""An unresolved call in another file must keep ``callers`` from answering ``complete``.

Found by the audit of the languages without a callers-gate repo: with
``file_path`` set, an unresolved CALLS edge whose placeholder target sits in the
*calling* file was dropped before ``UNRESOLVED_INBOUND`` counted it, and the
non-call reference scan skipped its line because a CALLS edge of that name is
there. Swift subclasses calling an inherited method without a receiver, C#
partial classes, and Ruby reopened classes all answered ``complete``.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool


async def _answers(
    tmp_path, files: dict[str, str], *targets: tuple[str, str]
) -> list[dict]:
    """Index ``files`` once, then ask ``callers`` for each ``(name, file)``."""
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
        await tool.execute(
            {"function_name": name, "file_path": file, "include_bodies": False}
        )
        for name, file in targets
    ]


_SWIFT = {
    "Base.swift": (
        "class Base {\n"
        "    func stored(_ x: Int) -> Int { return x }\n"
        "\n"
        "    func local() -> Int { return 1 }\n"
        "\n"
        "    func useLocal() -> Int { return local() }\n"
        "}\n"
    ),
    "Sub.swift": (
        "final class Sub: Base {\n"
        "    func run() -> Int {\n"
        "        return stored(1)\n"
        "    }\n"
        "}\n"
    ),
}

_CSHARP = {
    "Writer.cs": (
        "public abstract partial class Writer\n"
        "{\n"
        "    internal void Finish()\n"
        "    {\n"
        "    }\n"
        "\n"
        "    internal void WriteSync()\n"
        "    {\n"
        "        Finish();\n"
        "    }\n"
        "}\n"
    ),
    "Writer.Async.cs": (
        "public abstract partial class Writer\n"
        "{\n"
        "    internal void WriteAsync()\n"
        "    {\n"
        "        Finish();\n"
        "    }\n"
        "}\n"
    ),
    # A second ``Finish`` elsewhere makes the bare name ambiguous, so the call
    # in ``Writer.Async.cs`` stays unresolved (as in Newtonsoft.Json's
    # ``JsonReader`` / ``JsonWriter``).
    "Reader.cs": (
        "public abstract class Reader\n"
        "{\n"
        "    private void Finish()\n"
        "    {\n"
        "    }\n"
        "\n"
        "    internal void Read()\n"
        "    {\n"
        "        Finish();\n"
        "    }\n"
        "}\n"
    ),
}

_RUBY = {
    "helper.rb": ("class Spec\n  def capture(target)\n    target\n  end\nend\n"),
    "spec_a.rb": ("class ATest < Spec\n  def test_a\n    capture(1)\n  end\nend\n"),
}


@pytest.mark.asyncio
async def test_swift_inherited_bare_call_in_another_file_is_not_complete(
    tmp_path,
) -> None:
    (result,) = await _answers(tmp_path, _SWIFT, ("stored", "Base.swift"))

    # Before the fix: ``complete`` with 0 callers.
    assert result["completeness"] != "complete", result
    assert "UNRESOLVED_INBOUND" in result["completeness_reasons"], result
    sites = result["unresolved_inbound_sites"]
    assert {(s["file"], s["line"]) for s in sites} == {("Sub.swift", 3)}, sites


@pytest.mark.asyncio
async def test_csharp_partial_class_call_in_another_file_is_not_complete(
    tmp_path,
) -> None:
    (result,) = await _answers(tmp_path, _CSHARP, ("Finish", "Writer.cs"))

    # Before the fix: ``complete`` with only ``WriteSync`` listed.
    assert result["completeness"] != "complete", result
    assert "UNRESOLVED_INBOUND" in result["completeness_reasons"], result
    sites = result["unresolved_inbound_sites"]
    assert ("Writer.Async.cs", 5) in {(s["file"], s["line"]) for s in sites}, sites


@pytest.mark.asyncio
async def test_ruby_reopened_class_call_in_another_file_is_not_complete(
    tmp_path,
) -> None:
    (result,) = await _answers(tmp_path, _RUBY, ("capture", "helper.rb"))

    assert result["completeness"] != "complete", result
    assert "UNRESOLVED_INBOUND" in result["completeness_reasons"], result


@pytest.mark.asyncio
async def test_ruby_namespaced_reopened_class_is_not_complete(tmp_path) -> None:
    files = {
        **_RUBY,
        "helper.rb": (
            "class Mini::Spec\n  def capture(target)\n    target\n  end\nend\n"
        ),
        "spec_a.rb": (
            "class ATest < Mini::Spec\n  it 'warns' do\n    capture(1)\n  end\nend\n"
        ),
    }

    (result,) = await _answers(tmp_path, files, ("capture", "helper.rb"))

    # Before the fix: the bare name was rewritten to ``Mini::Spec.capture``,
    # which is not a qualified name, so every count looked up the whole string
    # and the answer was ``complete`` with 0 callers (rack ``capture_warnings``).
    assert result["completeness"] != "complete", result
    assert "UNRESOLVED_INBOUND" in result["completeness_reasons"], result


@pytest.mark.asyncio
async def test_same_file_call_stays_complete(tmp_path) -> None:
    (result,) = await _answers(tmp_path, _SWIFT, ("local", "Base.swift"))

    # Nothing outside ``Base.swift`` names ``local``: the answer is unchanged.
    assert result["completeness"] == "complete", result
    assert result["caller_count"] == 1
