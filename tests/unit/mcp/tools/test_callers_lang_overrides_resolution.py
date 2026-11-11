"""#1937 / #1938: how the C#, PHP and Swift override gates resolve supertypes.

A supertype that resolves to a project type and declares nothing reachable
keeps ``complete``; a name that could denote an outside type (an alias, a
generic arity that no project type has, a ``using`` that may import an outside
type) does not.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.callers_java_overrides import OVERRIDE_REASON
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

_FILES = {
    "Lib/Handler.cs": (
        "namespace Lib\n{\n"
        "    public abstract class Handler { public virtual void Go() { } }\n"
        "    public class Box { }\n"
        "}\n"
    ),
    "App/Handlers.cs": (
        "using Lib;\n"
        "using HB = Lib.Handler;\n\n"
        "namespace App\n{\n"
        "    public class H : Handler { public override void Go() { } }\n"
        "    public class Q : Lib.Handler { public override void Go() { } }\n"
        "    public class G2 : global::Lib.Handler { public override void Go() { } }\n"
        "    public class Al : HB { public override void Go() { } }\n"
        "    public class B2 : Box<int> { public void Pub() { } }\n"
        "    public class Handler2 { public virtual void Run() { } }\n"
        "    public class Host\n    {\n"
        "        public class Node { public virtual void Visit() { } }\n"
        "        public class Leaf : Node { public override void Visit() { } }\n"
        "    }\n"
        "    public record Rec(int X)\n    {\n"
        "        public virtual bool Equals(Rec other) { return true; }\n"
        "    }\n"
        "}\n"
    ),
    "App/Inner/Hidden.cs": (
        "namespace App.Inner\n{\n"
        "    using Ext;\n\n"
        "    public class HC : Handler2 { public override void Run() { } }\n"
        "}\n"
    ),
    "App/Pt1.cs": (
        "using System;\n\nnamespace App\n{\n"
        "    public partial class Pt : IDisposable { }\n}\n"
    ),
    "App/Pt2.cs": (
        "namespace App\n{\n"
        "    public partial class Pt { public void Dispose() { } }\n}\n"
    ),
    "src/Core/Base.php": (
        "<?php\n\nnamespace App\\Core;\n\nabstract class Base\n{\n}\n"
    ),
    "src/Http/Ctl.php": (
        "<?php\n\nnamespace App\\Http;\n\n"
        "use App\\Core\\{Base as CoreBase, Other};\n\n"
        "class Ctl extends CoreBase\n{\n    public function act()\n    {\n    }\n}\n"
    ),
    "src/Blk.php": (
        "<?php\n\nnamespace App\\Blk {\n"
        "    class In extends \\App\\Core\\Base\n    {\n"
        "        public function m2()\n        {\n        }\n    }\n}\n"
    ),
    "src/Runners.php": (
        "<?php\n\nnamespace App;\n\n"
        "interface Runner\n{\n    public function run();\n}\n\n"
        "trait Helps\n{\n    public function aid()\n    {\n    }\n}\n\n"
        "class R1 implements Runner\n{\n    use Helps;\n\n"
        "    public function run()\n    {\n    }\n}\n\n"
        "function go(Runner $r)\n{\n    $r->RUN();\n}\n"
    ),
    "Sources/Animals.swift": (
        "class Animal {\n    func speak() {\n    }\n}\n\n"
        "class Dog: Animal {\n    override func speak() {\n    }\n\n"
        "    func testHelper(_ value: Int) {\n    }\n}\n"
    ),
}


async def _answers(tmp_path, *names: str) -> dict[str, dict]:
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    for rel_path, text in _FILES.items():
        path = tmp_path / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    indexed = await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "max_files": 50}
    )
    assert indexed["published"] is True
    tool = CodeGraphCallersTool(str(tmp_path))
    return {
        name: await tool.execute({"function_name": name, "include_bodies": False})
        for name in names
    }


@pytest.mark.asyncio
async def test_project_supertypes_resolve_and_keep_complete(tmp_path) -> None:
    answers = await _answers(
        tmp_path,
        "H.Go",
        "Q.Go",
        "G2.Go",
        "Leaf.Visit",
        "Ctl.act",
        "In.m2",
        "Dog.speak",
        "Dog.testHelper",
    )

    for name, result in answers.items():
        assert result["completeness"] == "complete", (name, result)


@pytest.mark.asyncio
async def test_names_that_may_denote_outside_types_block(tmp_path) -> None:
    answers = await _answers(
        tmp_path, "Al.Go", "B2.Pub", "HC.Run", "Pt.Dispose", "Rec.Equals"
    )
    expected = {
        "Al.Go": "alias",
        "B2.Pub": "Box<int>",
        "HC.Run": "using",
        "Pt.Dispose": "IDisposable",
        "Rec.Equals": "synthesized",
    }

    for name, needle in expected.items():
        result = answers[name]
        assert result["completeness"] != "complete", (name, result)
        assert OVERRIDE_REASON in result["completeness_reasons"], (name, result)
        assert needle in result["next_step"], (name, result["next_step"])


@pytest.mark.asyncio
async def test_php_traits_and_case_insensitive_dispatch_block(tmp_path) -> None:
    answers = await _answers(tmp_path, "Helps.aid", "R1.run")

    assert answers["Helps.aid"]["completeness"] != "complete"
    assert "trait" in answers["Helps.aid"]["next_step"]
    run = answers["R1.run"]
    assert run["completeness"] != "complete", run
    assert run["open_sites"]["enumerated"] is False, run["open_sites"]
