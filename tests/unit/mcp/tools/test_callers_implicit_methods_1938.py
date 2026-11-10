"""#1938: methods the language or a test framework calls implicitly.

PHP runs ``__invoke`` when an object is called (``$handler($request)``) and the
other magic methods on conversions, property access and the like; XCTest runs
every ``test*`` method of an ``XCTestCase`` subclass by reflection. No call edge
names them, so ``0 callers`` is not evidence of absence. Before the fix they
answered ``complete``. A Swift ``override`` is reached through its superclass
(#1937), here ``XCTestCase.setUp``.
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


_FILES = {
    "src/Mw.php": (
        "<?php\n"
        "class Mw {\n"
        "    public function __invoke($req) { return $req; }\n"
        "    public function __toString(): string { return 'mw'; }\n"
        "    public function plain() { }\n"
        "}\n"
        "function run(callable $h) { return $h(1); }\n"
        "run(new Mw());\n"
    ),
    "Tests/DownloadTests.swift": (
        "import XCTest\n\n"
        "final class DownloadTests: XCTestCase {\n"
        "    func testThatTryMapCatchesTransformationError() throws {\n"
        "    }\n\n"
        "    override func setUp() {\n"
        "        super.setUp()\n"
        "    }\n\n"
        "    func helper(value: Int) {\n"
        "    }\n"
        "}\n"
    ),
    "Sources/Shape.swift": (
        "class Shape {\n"
        "    func area() -> Int {\n        return 0\n    }\n\n"
        "    func describe() -> Int {\n        return area()\n    }\n"
        "}\n"
    ),
    "Sources/Square.swift": (
        "class Square: Shape {\n"
        "    override func area() -> Int {\n        return 4\n    }\n\n"
        "    func lone() -> Int {\n        return 1\n    }\n"
        "}\n"
    ),
}


@pytest.mark.asyncio
async def test_php_magic_methods_are_not_complete(tmp_path) -> None:
    invoke, to_string, plain = await _answers(
        tmp_path, _FILES, "Mw.__invoke", "Mw.__toString", "Mw.plain"
    )

    _blocked(invoke, "magic method", "__invoke")
    _blocked(to_string, "magic method")
    assert plain["completeness"] == "complete", plain


@pytest.mark.asyncio
async def test_xctest_methods_and_swift_overrides_are_not_complete(tmp_path) -> None:
    test, set_up, area, helper, lone = await _answers(
        tmp_path,
        _FILES,
        "DownloadTests.testThatTryMapCatchesTransformationError",
        "DownloadTests.setUp",
        "Square.area",
        "DownloadTests.helper",
        "Square.lone",
    )

    _blocked(test, "XCTest")
    # ``super.setUp()`` already keeps it unknown; XCTest calls it as well, so
    # that site is not all there is.
    assert set_up["completeness"] != "complete", set_up
    assert set_up["open_sites"]["enumerated"] is False, set_up["open_sites"]
    _blocked(area, "Shape.swift")
    assert helper["completeness"] == "complete", helper
    assert lone["completeness"] == "complete", lone


@pytest.mark.asyncio
async def test_xctest_method_in_a_body_the_grammar_cannot_recover_is_not_complete(
    tmp_path,
) -> None:
    # Alamofire: inside `#if` the Swift grammar leaves the class body in ERROR
    # nodes, so the index records no owner and the method is asked by bare name.
    files = {
        "Tests/ReachTests.swift": (
            "#if canImport(SystemConfiguration)\n\n"
            "import SystemConfiguration\nimport XCTest\n\n"
            "final class ReachTests: XCTestCase {\n"
            "    // MARK: - Tests\n\n"
            "    func testThatManagerCanBeInitializedFromHost() {\n"
            '        let manager = Manager(host: "localhost")\n'
            "        XCTAssertNotNil(manager)\n"
            "    }\n"
            "}\n\n#endif\n"
        ),
        "Sources/Main.swift": "func main() {\n    helper()\n}\n\nfunc helper() {\n}\n",
    }
    (result,) = await _answers(
        tmp_path, files, "testThatManagerCanBeInitializedFromHost"
    )

    _blocked(result, "XCTest")
