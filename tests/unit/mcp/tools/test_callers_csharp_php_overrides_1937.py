"""#1937: C# ``override`` / interface members and PHP redefined methods.

A C# ``override`` (``JProperty.ContainsItem`` overrides the virtual
``JContainer.ContainsItem``) is reached by every call through the base type, and
an override of a BCL member (``KeyedCollection<,>.GetKeyForItem``) is called by
the BCL. PHP has no ``override`` keyword: any method of a class with a supertype
may redefine one (``setUp`` of a PHPUnit ``TestCase``). Before the fix all of
them answered ``complete`` with 0 callers.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.callers_java_overrides import OVERRIDE_REASON
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_CSHARP = {
    "Base.cs": (
        "public abstract class Base {\n"
        "    internal virtual bool Has(int x) { return false; }\n"
        "    public bool Check(int x) { return Has(x); }\n"
        "}\n"
    ),
    "Derived.cs": (
        "public class Derived : Base {\n"
        "    internal override bool Has(int x) { return true; }\n"
        "    public void Plain() { }\n"
        "}\n"
    ),
    "T/Coll.cs": (
        "using System.Collections.ObjectModel;\n\n"
        "namespace T\n{\n"
        "    public class Item { }\n\n"
        "    public class VersionKeyedCollection : KeyedCollection<string, Item>\n"
        "    {\n"
        '        protected override string GetKeyForItem(Item item) { return ""; }\n'
        "    }\n"
        "}\n"
    ),
    "T/Named.cs": (
        "namespace T\n{\n"
        "    public class Named\n    {\n"
        '        public override string ToString() { return "n"; }\n'
        "    }\n"
        "}\n"
    ),
    "T/Res.cs": (
        "using System;\n\n"
        "namespace T\n{\n"
        "    public sealed class Res : IDisposable\n    {\n"
        "        public void Dispose() { }\n"
        "        private void Helper() { }\n"
        "    }\n"
        "}\n"
    ),
    "T/Shapes.cs": (
        "namespace T\n{\n"
        "    public interface IShape { int Area(); }\n\n"
        "    public class Square : IShape\n    {\n"
        "        public int Area() { return 4; }\n"
        "        public int Side() { return 2; }\n"
        "    }\n"
        "}\n"
    ),
    "T/Sub/Leaf.cs": (
        "namespace T.Sub\n{\n"
        "    public class Leaf : Square\n    {\n"
        "        public int Lone() { return 1; }\n"
        "    }\n"
        "}\n"
    ),
    "T/Jobs.cs": (
        "namespace T\n{\n"
        "    public interface IRun { void Run(); }\n\n"
        "    public class Job : IRun\n    {\n"
        "        void IRun.Run() { }\n"
        "    }\n\n"
        "    public static class Runner\n    {\n"
        "        public static void Go(IRun r) { r.Run(); }\n"
        "    }\n"
        "}\n"
    ),
    # Newtonsoft.Json: overrides inside `#if` regions of a class body.
    "T/Cond.cs": (
        "namespace T\n{\n"
        "    public class CondStream : System.IO.Stream\n    {\n"
        "#if HAVE_ASYNC\n"
        "        public override void Flush() { }\n"
        "#endif\n"
        "    }\n"
        "}\n"
    ),
}

_PHP = {
    "tests/StreamHandlerTest.php": (
        "<?php\n\n"
        "namespace GuzzleHttp\\Tests\\Handler\\Network;\n\n"
        "use PHPUnit\\Framework\\TestCase;\n\n"
        "class StreamHandlerTest extends TestCase\n{\n"
        "    protected function setUp(): void\n    {\n    }\n\n"
        "    private function helper()\n    {\n    }\n"
        "}\n"
    ),
    "src/Base.php": (
        "<?php\n\nnamespace App;\n\n"
        "abstract class Base\n{\n"
        "    public function run()\n    {\n        return $this->step();\n    }\n\n"
        "    protected function step()\n    {\n        return 1;\n    }\n"
        "}\n"
    ),
    "src/Child.php": (
        "<?php\n\nnamespace App;\n\n"
        "class Child extends Base\n{\n"
        "    protected function step()\n    {\n        return 2;\n    }\n\n"
        "    public function extra()\n    {\n        return 3;\n    }\n"
        "}\n"
    ),
    "src/Plain.php": (
        "<?php\n\nnamespace App;\n\n"
        "class Plain\n{\n    public function solo()\n    {\n    }\n}\n"
    ),
    "src/Err.php": (
        "<?php\n\nnamespace App;\n\n"
        "class Err extends \\RuntimeException\n{\n"
        "    public function detail()\n    {\n    }\n}\n"
    ),
}


async def _answers(tmp_path, files: dict[str, str], *names: str) -> list[dict]:
    """Index the repro once, then ask ``callers`` for each name."""
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    for rel_path, text in files.items():
        path = tmp_path / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 50}
    )
    assert indexed["published"] is True
    tool = CodeGraphCallersTool(str(tmp_path))
    return [
        await tool.execute({"function_name": name, "include_bodies": False})
        for name in names
    ]


def _blocked(result: dict, *needles: str) -> None:
    assert result["completeness"] != "complete", result
    assert OVERRIDE_REASON in result["completeness_reasons"], result
    for needle in needles:
        assert needle in result["next_step"], result["next_step"]


@pytest.mark.asyncio
async def test_csharp_override_reached_through_the_base_type_is_not_complete(
    tmp_path,
) -> None:
    has, bcl, obj, conditional = await _answers(
        tmp_path,
        _CSHARP,
        "Derived.Has",
        "VersionKeyedCollection.GetKeyForItem",
        "Named.ToString",
        "CondStream.Flush",
    )

    _blocked(conditional, "System.IO.Stream")

    assert has["caller_count"] == 0
    _blocked(has, "Base.cs:3")
    _blocked(bcl, "KeyedCollection")
    _blocked(obj, "System.Object")


@pytest.mark.asyncio
async def test_csharp_interface_implementations_are_not_complete(tmp_path) -> None:
    dispose, explicit = await _answers(tmp_path, _CSHARP, "Res.Dispose", "Job.Run")

    _blocked(dispose, "IDisposable")
    # ``r.Run()`` already keeps it unknown; the override gate must keep the
    # bound from claiming that site is all there is.
    assert explicit["completeness"] != "complete", explicit
    assert explicit["open_sites"]["enumerated"] is False, explicit["open_sites"]


@pytest.mark.asyncio
async def test_csharp_members_closed_in_the_project_stay_complete(tmp_path) -> None:
    answers = await _answers(
        tmp_path,
        _CSHARP,
        "Derived.Plain",
        "Res.Helper",
        "Square.Area",
        "Square.Side",
        "Leaf.Lone",
    )

    for result in answers:
        assert result["completeness"] == "complete", result
        assert result["caller_count"] == 0


@pytest.mark.asyncio
async def test_php_method_redefining_a_supertype_method_is_not_complete(
    tmp_path,
) -> None:
    set_up, step, detail = await _answers(
        tmp_path, _PHP, "StreamHandlerTest.setUp", "Child.step", "Err.detail"
    )

    _blocked(set_up, "TestCase")
    _blocked(step, "Base.php")
    _blocked(detail, "RuntimeException")


@pytest.mark.asyncio
async def test_php_methods_closed_in_the_project_stay_complete(tmp_path) -> None:
    answers = await _answers(
        tmp_path, _PHP, "Child.extra", "Plain.solo", "StreamHandlerTest.helper"
    )

    for result in answers:
        assert result["completeness"] == "complete", result
