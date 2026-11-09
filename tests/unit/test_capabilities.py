"""机器可读能力清单（dogfood §12.4）：agent 的规划面必须自洽且完整。"""

from __future__ import annotations

import json

from tree_sitter_analyzer.capabilities import build_capability_manifest


def test_manifest_covers_every_registered_action() -> None:
    """8 个 facade 的 94 个 action 全部出现，且每个都有规划所需的字段。"""
    manifest = build_capability_manifest(".")
    actions = {name: set(tool["actions"]) for name, tool in manifest["tools"].items()}

    assert sum(len(entries) for entries in actions.values()) == 94
    for tool in manifest["tools"].values():
        for action, entry in tool["actions"].items():
            assert entry["tier"] in {"instant", "indexed"}
            assert entry["preconditions"] == (
                [] if entry["tier"] == "instant" else ["index"]
            )
            # example 是该 facade 的最小调用（不要求与遍历到的 action 同名）
            assert entry["example"]["action"] in tool["actions"]
            assert entry["self_describing"] is (action == "help")


def test_known_actions_land_in_the_expected_tier() -> None:
    manifest = build_capability_manifest(".")

    assert manifest["tools"]["search"]["actions"]["text"]["tier"] == "instant"
    assert manifest["tools"]["nav"]["actions"]["callers"]["tier"] == "indexed"
    assert manifest["tools"]["index"]["actions"]["help"]["self_describing"] is True


def test_manifest_is_serialisable_for_planning(monkeypatch) -> None:
    """缺示例的 facade 退化为 {action}，清单仍然可 JSON 序列化。"""
    import tree_sitter_analyzer.capabilities as capabilities

    monkeypatch.setattr(capabilities, "_EXAMPLES", {})
    manifest = capabilities.build_capability_manifest(".")

    assert manifest["tools"]["nav"]["actions"]["callers"]["example"] == {
        "action": "callers"
    }
    assert json.loads(json.dumps(manifest))["tiers"]["instant"]


def test_cli_capabilities_flag_emits_the_manifest() -> None:
    """dogfood §12.4：`--capabilities --format json` 是 agent 的规划入口。"""
    import json
    import subprocess
    import sys
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "tree_sitter_analyzer",
            "--capabilities",
            "--format",
            "json",
        ],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=180,
    )

    payload = json.loads(proc.stdout)
    assert (proc.returncode, len(payload["tools"])) == (0, 8)
    assert sum(len(tool["actions"]) for tool in payload["tools"].values()) == 94
    assert payload["tiers"]["instant"]


def test_preflight_reports_the_tier_and_live_precondition() -> None:
    """dogfood §12.3：预检回答「要花哪一档、现在能不能直接跑」。"""
    from tree_sitter_analyzer.capabilities import preflight_action

    indexed = preflight_action("nav.callers", ".")
    instant = preflight_action("search.text", ".")

    assert (indexed["tier"], indexed["precondition_met"]) == ("indexed", True)
    assert (instant["tier"], instant["index_present"]) == ("instant", None)
    assert instant["precondition_met"] is True


def test_preflight_rejects_unknown_and_ambiguous_actions() -> None:
    from tree_sitter_analyzer.capabilities import preflight_action

    unknown = preflight_action("nav.no_such_action", ".")
    ambiguous = preflight_action("help", ".")

    assert (unknown["success"], unknown["error_code"]) == (False, "UNKNOWN_ACTION")
    assert (ambiguous["success"], ambiguous["error_code"]) == (
        False,
        "AMBIGUOUS_ACTION",
    )
    assert len(ambiguous["candidates"]) == 8


def test_cli_capabilities_preflights_one_action() -> None:
    import json
    import subprocess
    import sys
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "tree_sitter_analyzer",
            "--capabilities",
            "nav.callers",
            "--format",
            "json",
        ],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        timeout=180,
    )

    payload = json.loads(proc.stdout)
    assert (proc.returncode, payload["action"], payload["tier"]) == (
        0,
        "nav.callers",
        "indexed",
    )


def test_cli_preflight_dispatch_is_in_process_safe(monkeypatch) -> None:
    """进程内覆盖 dispatch 的两条分支（子进程测试不计覆盖率）。"""
    import pytest

    import tree_sitter_analyzer.cli_main as cli_main
    import tree_sitter_analyzer.output_manager as output_manager

    captured: list[dict] = []
    monkeypatch.setattr(output_manager, "output_json", captured.append)
    namespace = type("Args", (), {"capabilities": "nav.callers", "project_root": "."})()

    with pytest.raises(SystemExit) as excinfo:
        cli_main._emit_capability_manifest_if_requested(namespace)

    assert (excinfo.value.code, captured[0]["action"]) == (0, "nav.callers")

    full = type("Args", (), {"capabilities": "", "project_root": "."})()
    with pytest.raises(SystemExit):
        cli_main._emit_capability_manifest_if_requested(full)
    assert len(captured[1]["tools"]) == 8
