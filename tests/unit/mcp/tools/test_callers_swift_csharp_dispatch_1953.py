"""#1953: Swift / C# methods reached by dispatch the earlier gates missed.

* A Swift method that satisfies a requirement of a protocol declared outside the
  project is called by the framework (``ExtensionDelegate.handle`` of a
  ``WKExtensionDelegate``); the conformance may be declared by an extension in
  another file.
* A public method of a C# class ``A`` implements interface ``I`` when a subclass
  ``B : A, I`` lists it; calls through ``I`` reach ``A.M``.
* A C# ``global using`` alias in another file renames a supertype.
* A C# ``static abstract`` interface member is reached through a type parameter
  (``T.Parse(s)``).

Before the fix all of them answered ``complete`` with 0 callers.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.callers_java_overrides import OVERRIDE_REASON
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool


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


def _complete(results: list[dict]) -> None:
    for result in results:
        assert result["completeness"] == "complete", result
        assert result["caller_count"] == 0, result


_SWIFT = {
    # Alamofire 5.9.1, watchOS example.
    "Ext/ExtensionDelegate.swift": (
        "import WatchKit\n\n"
        "class ExtensionDelegate: NSObject, WKExtensionDelegate {\n"
        "    func handle(_ backgroundTasks: Set<WKRefreshBackgroundTask>) {\n"
        "    }\n\n"
        "    private func helper() {\n"
        "    }\n"
        "}\n"
    ),
    "Sources/Session.swift": (
        "open class Session {\n    func didFinish(task: Int) {\n    }\n}\n"
    ),
    "Sources/Session+Delegate.swift": (
        "import Foundation\n\nextension Session: URLSessionTaskDelegate {\n}\n"
    ),
    "Sources/Monitor.swift": (
        "protocol EventMonitor: URLSessionDelegate {\n"
        "    func requestDidResume()\n"
        "}\n\n"
        "protocol Named {\n"
        "    func name() -> String\n"
        "}\n"
    ),
    "Sources/Logger.swift": (
        "final class Logger: EventMonitor {\n"
        "    func requestDidResume() {\n"
        "    }\n\n"
        "    func urlSessionDidFinishEvents() {\n"
        "    }\n"
        "}\n\n"
        "struct Tag: Named {\n"
        '    func name() -> String {\n        return "t"\n    }\n\n'
        "    func other() -> Int {\n        return 1\n    }\n"
        "}\n\n"
        "struct Point: Equatable, Hashable, Codable {\n"
        "    func norm() -> Int {\n        return 0\n    }\n"
        "}\n\n"
        "enum Mode: String, CaseIterable {\n"
        "    case a\n\n"
        "    func flip() -> Int {\n        return 1\n    }\n"
        "}\n\n"
        "class Plain {\n"
        "    func lone() -> Int {\n        return 1\n    }\n"
        "}\n"
    ),
    "Sources/Main.swift": "func main() {\n    helper()\n}\n\nfunc helper() {\n}\n",
}


@pytest.mark.asyncio
async def test_swift_method_of_an_external_protocol_conformance_is_not_complete(
    tmp_path,
) -> None:
    handle, did_finish, inherited = await _answers(
        tmp_path,
        _SWIFT,
        "ExtensionDelegate.handle",
        "Session.didFinish",
        "Logger.urlSessionDidFinishEvents",
    )

    _blocked(handle, "WKExtensionDelegate")
    # The conformance is declared by an extension in another file.
    _blocked(did_finish, "URLSessionTaskDelegate")
    # A project protocol that refines an external one.
    _blocked(inherited, "URLSessionDelegate")


@pytest.mark.asyncio
async def test_swift_methods_outside_any_unknown_requirement_stay_complete(
    tmp_path,
) -> None:
    answers = await _answers(
        tmp_path,
        _SWIFT,
        "ExtensionDelegate.helper",
        "Tag.other",
        "Point.norm",
        "Mode.flip",
        "Plain.lone",
    )

    _complete(answers)


_CSHARP = {
    "T/Base.cs": (
        "namespace T\n{\n"
        "    public interface IRun { void Run(); }\n\n"
        "    public class Engine\n    {\n"
        "        public void Run() { }\n"
        "        public void Idle() { }\n"
        "    }\n\n"
        "    public class Car : Engine, IRun { }\n\n"
        "    public static class Driver\n    {\n"
        "        public static void Go(IRun r) { r.Run(); }\n"
        "    }\n"
        "}\n"
    ),
    "T/Res.cs": (
        "using System;\n\n"
        "namespace T\n{\n"
        "    public class Holder\n    {\n"
        "        public void Dispose() { }\n"
        "    }\n\n"
        "    public sealed class Lease : Holder, IDisposable { }\n"
        "}\n"
    ),
    "T/Quiet.cs": (
        "namespace T\n{\n"
        "    public interface IQuiet { void Hush(); }\n\n"
        "    public class Calm\n    {\n"
        "        public void Breathe() { }\n"
        "    }\n\n"
        "    public class Still : Calm, IQuiet\n    {\n"
        "        public void Hush() { }\n"
        "    }\n"
        "}\n"
    ),
    # A `global using` alias renames the supertype in every file.
    "GlobalUsings.cs": "global using IShape = Ext.IThing;\n",
    "P/Shapes.cs": "namespace P\n{\n    public interface IShape { int Area(); }\n}\n",
    "App/Square.cs": (
        "using P;\n\n"
        "namespace App\n{\n"
        "    public class Square : IShape\n    {\n"
        "        public int Area() { return 4; }\n"
        "    }\n"
        "}\n"
    ),
    "App/Circle.cs": (
        "namespace App\n{\n"
        "    public class Circle : P.IShape\n    {\n"
        "        public int Area() { return 3; }\n"
        "    }\n"
        "}\n"
    ),
    "N/Num.cs": (
        "namespace N\n{\n"
        "    public interface IParse<TSelf> where TSelf : IParse<TSelf>\n    {\n"
        "        static abstract TSelf Parse(string s);\n"
        "    }\n\n"
        "    public readonly struct Num : IParse<Num>\n    {\n"
        "        public static Num Parse(string s) { return default; }\n"
        "        public static Num Zero() { return default; }\n"
        "    }\n\n"
        "    public static class Reader\n    {\n"
        "        public static TSelf Read<TSelf>(string s) where TSelf : IParse<TSelf>\n"
        "        {\n"
        "            return TSelf.Parse(s);\n"
        "        }\n"
        "    }\n"
        "}\n"
    ),
    "N/Money.cs": (
        "using System;\n\n"
        "namespace N\n{\n"
        "    public readonly struct Money : IParsable<Money>\n    {\n"
        "        public static Money From(string s) { return default; }\n"
        "    }\n\n"
        "    public sealed class Util : IDisposable\n    {\n"
        "        public static int Twice(int x) { return x * 2; }\n"
        "        public void Dispose() { }\n"
        "    }\n"
        "}\n"
    ),
}


@pytest.mark.asyncio
async def test_csharp_method_implementing_an_interface_of_a_subclass_is_not_complete(
    tmp_path,
) -> None:
    run, dispose = await _answers(tmp_path, _CSHARP, "Engine.Run", "Holder.Dispose")

    # `r.Run()` through `IRun` reaches `Engine.Run` for a `Car`.
    assert run["completeness"] != "complete", run
    assert run["open_sites"]["enumerated"] is False, run["open_sites"]
    _blocked(dispose, "Lease", "IDisposable")


@pytest.mark.asyncio
async def test_csharp_global_using_alias_in_another_file_is_not_ignored(
    tmp_path,
) -> None:
    (area,) = await _answers(tmp_path, _CSHARP, "Square.Area")

    _blocked(area, "IShape")


@pytest.mark.asyncio
async def test_csharp_static_abstract_interface_members_are_not_complete(
    tmp_path,
) -> None:
    parse, external = await _answers(tmp_path, _CSHARP, "Num.Parse", "Money.From")

    # `TSelf.Parse(s)` dispatches to `Num.Parse`.
    assert parse["completeness"] != "complete", parse
    _blocked(external, "IParsable")


@pytest.mark.asyncio
async def test_csharp_members_closed_in_the_project_stay_complete_1953(
    tmp_path,
) -> None:
    answers = await _answers(
        tmp_path,
        _CSHARP,
        "Engine.Idle",
        "Calm.Breathe",
        "Circle.Area",
        "Num.Zero",
        "Util.Twice",
    )

    _complete(answers)
