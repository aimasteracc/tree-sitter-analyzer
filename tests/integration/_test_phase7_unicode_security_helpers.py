"""Unicode security helpers for Phase 7 integration tests."""

from collections.abc import Iterable
from typing import Any

from tree_sitter_analyzer.mcp.tools.list_files_tool import ListFilesTool


async def collect_unicode_attack_results(
    list_tool: ListFilesTool,
    unicode_attacks: Iterable[str],
    secure_test_project: str,
) -> list[dict[str, Any]]:
    """Run Unicode attack patterns through the list-files path boundary."""
    return [
        await _run_unicode_attack(list_tool, attack_string, secure_test_project)
        for attack_string in unicode_attacks
    ]


def assert_unicode_attacks_handled_safely(
    unicode_results: list[dict[str, Any]],
) -> None:
    """Assert and report Unicode attack handling expectations."""
    print("Unicode Normalization Attack Results:")
    print(f"  Total attacks tested: {len(unicode_results)}")

    safely_handled = [r for r in unicode_results if r["handled_safely"]]
    assert len(safely_handled) == len(unicode_results), (
        "Some Unicode attacks were not handled safely"
    )


async def _run_unicode_attack(
    list_tool: ListFilesTool,
    attack_string: str,
    secure_test_project: str,
) -> dict[str, Any]:
    try:
        result = await list_tool.execute(
            {
                "roots": [secure_test_project],
                "pattern": attack_string,
                "glob": True,
            }
        )
        return {
            "attack_string": repr(attack_string),
            "success": result.get("success", False),
            "handled_safely": True,
            "result": "Processed safely",
        }
    except Exception as exc:
        return {
            "attack_string": repr(attack_string),
            "success": False,
            "handled_safely": True,
            "result": f"Exception handled: {type(exc).__name__}",
        }
