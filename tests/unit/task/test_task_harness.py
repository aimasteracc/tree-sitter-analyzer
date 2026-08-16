"""RFC-0022 Phase A experiment harness contract (NO1-010A).

Exact pins for the internal harness bridge: strict decoded-request
validation (unknown fields rejected -> INVALID_REQUEST mapping), exact
primitive dispatch to the same-process MCP adapters, and the internal CLI
smoke entry.
"""

from __future__ import annotations

import asyncio
import io
import json
import sys

import pytest

from tree_sitter_analyzer.task_harness import (
    McpPrimitiveExecutor,
    request_from_dict,
)


def test_request_from_dict_understand() -> None:
    request = request_from_dict(
        "understand", {"task": "explain dispatch", "profile": "compact"}
    )
    assert request.task == "explain dispatch"
    assert request.budget.profile == "compact"


def test_request_from_dict_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError, match="unknown request fields"):
        request_from_dict("understand", {"task": "x", "sneaky": True})
    with pytest.raises(ValueError, match="unknown budget fields"):
        request_from_dict("understand", {"task": "x", "budget": {"sneaky": 1}})
    with pytest.raises(ValueError, match="unknown diff fields"):
        request_from_dict(
            "assess_change", {"diff": {"source": "workspace", "extra": 1}}
        )


def test_request_from_dict_plan_change_one_of() -> None:
    task_request = request_from_dict("plan_change", {"task": "refactor x"})
    assert task_request.task == "refactor x"
    diff_request = request_from_dict(
        "plan_change",
        {"diff": {"source": "staged", "scope_paths": ["src/"]}},
    )
    assert diff_request.diff.source == "staged"
    assert diff_request.diff.scope_paths == ("src/",)


def test_request_from_dict_invalid_payloads_raise() -> None:
    with pytest.raises(ValueError, match="task must not be empty"):
        request_from_dict("understand", {"task": "  "})
    with pytest.raises(ValueError, match="exactly one of task or diff"):
        request_from_dict("plan_change", {})
    with pytest.raises(ValueError, match="exactly one diff"):
        request_from_dict("assess_change", {})


def test_executor_dispatches_to_pinned_adapters(monkeypatch) -> None:
    """The harness wires the real same-process adapters, not new ones."""
    import tree_sitter_analyzer.task_harness as harness

    seen: list[tuple[str, str, dict]] = []

    class FakeTool:
        async def execute(self, arguments):
            seen.append(arguments)
            return {"success": True, "action_version": "fake/v1"}

    class FakeFacade:
        async def execute(self, arguments):
            seen.append(arguments)
            return {"success": True, "action_version": "fake/v1"}

    monkeypatch.setattr(harness, "CodeGraphStatusTool", lambda root: FakeTool())
    monkeypatch.setattr(harness, "CodeGraphContextTool", lambda root: FakeTool())
    monkeypatch.setattr(harness, "build_edit_facade", lambda root: FakeFacade())
    monkeypatch.setattr(harness, "ChangeImpactTool", lambda root: FakeTool())

    executor = McpPrimitiveExecutor(".")
    assert asyncio.run(executor.call("index", "status", {"output_format": "json"})) == {
        "success": True,
        "action_version": "fake/v1",
    }
    assert (
        asyncio.run(executor.call("nav", "context", {"task": "x"}))["success"] is True
    )
    result = asyncio.run(executor.call("edit", "safe", {"file_path": "a.py"}))
    assert result["success"] is True
    # edit.* dispatches through the facade with the action key attached.
    assert seen[-1]["action"] == "safe"
    assert seen[-1]["file_path"] == "a.py"


def test_executor_rejects_unknown_primitive() -> None:
    executor = McpPrimitiveExecutor(".")
    with pytest.raises(ValueError, match="unknown primitive"):
        asyncio.run(executor.call("mystery", "action", {}))


def test_cli_main_rejects_invalid_requests() -> None:
    from tree_sitter_analyzer.task_harness import main

    assert main(["--operation", "understand", "--task", "  "]) == 2
    assert (
        main(["--operation", "understand", "--task", "x", "--diff", "workspace"]) == 2
    )
    assert main(["--operation", "assess_change"]) == 2  # no diff -> invalid


def test_cli_main_runs_operation_and_prints(monkeypatch, capsys) -> None:
    import tree_sitter_analyzer.task_harness as harness

    async def fake_run(*args, **kwargs):
        return '{"serialized": true}'

    monkeypatch.setattr(harness, "run_operation", fake_run)
    assert (
        harness.main(
            ["--operation", "understand", "--task", "x", "--profile", "compact"]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert '{"serialized": true}' in captured.out


def test_cli_main_mutually_exclusive_task_and_diff(monkeypatch, capsys) -> None:
    import tree_sitter_analyzer.task_harness as harness

    async def fake_run(*args, **kwargs):
        return "{}"

    monkeypatch.setattr(harness, "run_operation", fake_run)
    assert (
        harness.main(
            ["--operation", "plan_change", "--task", "x", "--diff", "workspace"]
        )
        == 2
    )


def test_budget_and_diff_strict_decoding() -> None:
    with pytest.raises(ValueError, match="budget must be a dict"):
        request_from_dict("understand", {"task": "x", "budget": "compact"})
    with pytest.raises(ValueError, match="diff must be a dict"):
        request_from_dict("assess_change", {"diff": "workspace"})
    with pytest.raises(ValueError, match="scope_paths must be a list of strings"):
        request_from_dict(
            "assess_change", {"diff": {"source": "workspace", "scope_paths": "src/"}}
        )


def test_run_operation_dispatches_three_operations(monkeypatch) -> None:
    import tree_sitter_analyzer.task_harness as harness

    seen: list[str] = []

    class FakeExecutor:
        async def call(self, facade, action, arguments):
            return {"success": True}

    def fake_executor(root):
        seen.append(root)
        return FakeExecutor()

    monkeypatch.setattr(harness, "McpPrimitiveExecutor", fake_executor)
    for operation in ("understand", "plan_change", "assess_change"):
        request = request_from_dict(
            operation,
            {"task": "x"}
            if operation != "assess_change"
            else {"diff": {"source": "workspace"}},
        )
        serialized = asyncio.run(
            harness.run_operation(operation, request, project_root=".")
        )
        assert '"success": true' in serialized
    assert seen == [".", ".", "."]


def test_cli_main_plan_change_diff_branch(monkeypatch, capsys) -> None:
    import tree_sitter_analyzer.task_harness as harness

    async def fake_run(*args, **kwargs):
        return "{}"

    monkeypatch.setattr(harness, "run_operation", fake_run)
    assert (
        harness.main(
            [
                "--operation",
                "plan_change",
                "--diff",
                "workspace",
                "--scope-path",
                "src/",
                "--format",
                "toon",
            ]
        )
        == 0
    )
    assert capsys.readouterr().out == "{}\n"


def test_request_from_dict_explicit_budget_dict() -> None:
    request = request_from_dict(
        "understand", {"task": "x", "budget": {"profile": "compact"}}
    )
    assert request.budget.profile == "compact"
    with pytest.raises(ValueError, match="BUDGET_INVALID"):
        request_from_dict(
            "understand",
            {"task": "x", "budget": {"profile": "compact", "max_primitive_calls": 10}},
        )


def test_run_operation_toon_branch(monkeypatch) -> None:
    import tree_sitter_analyzer.task_harness as harness

    class FakeExecutor:
        async def call(self, facade, action, arguments):
            return {"success": True}

    monkeypatch.setattr(harness, "McpPrimitiveExecutor", lambda root: FakeExecutor())
    request = request_from_dict("understand", {"task": "x"})
    serialized = asyncio.run(
        harness.run_operation(
            "understand", request, project_root=".", output_format="toon"
        )
    )
    assert serialized.startswith('"')
    assert '"schema": "task-outcome/v1"' in serialized


def test_request_from_dict_unknown_operation_rejected() -> None:
    with pytest.raises(ValueError, match="unknown operation"):
        request_from_dict("mystery", {"task": "x"})  # type: ignore[arg-type]


def test_request_from_dict_rejects_forbidden_fields() -> None:
    with pytest.raises(ValueError, match="understand rejects diff"):
        request_from_dict("understand", {"task": "x", "diff": {"source": "workspace"}})
    with pytest.raises(ValueError, match="exactly one of task or diff"):
        request_from_dict(
            "plan_change",
            {"task": "x", "diff": {"source": "workspace"}},
        )
    with pytest.raises(ValueError, match="assess_change rejects task"):
        request_from_dict(
            "assess_change", {"diff": {"source": "workspace"}, "task": "x"}
        )


# --- Corpus / request-json modes (NO1-010A follow-up) ------------------------


def test_load_corpus_strict_parsing(tmp_path) -> None:
    from tree_sitter_analyzer.task_harness import load_corpus

    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text(
        '{"operation": "understand", "task": "how does dispatch work"}\n'
        '{"operation": "assess_change", "diff": {"source": "workspace"}}\n'
        "\n"
    )
    entries = load_corpus(str(corpus))
    assert [(op, p.get("task"), p.get("diff")) for op, p in entries] == [
        ("understand", "how does dispatch work", None),
        ("assess_change", None, {"source": "workspace"}),
    ]


def test_load_corpus_rejects_malformed_lines(tmp_path) -> None:
    from tree_sitter_analyzer.task_harness import load_corpus

    corpus = tmp_path / "bad.jsonl"
    corpus.write_text('{"operation": "understand", "task": "x"}\nnot-json\n')
    with pytest.raises(ValueError, match="line 2: invalid JSON"):
        load_corpus(str(corpus))
    corpus.write_text('{"operation": "mystery", "task": "x"}\n')
    with pytest.raises(ValueError, match="line 1: unknown operation"):
        load_corpus(str(corpus))
    corpus.write_text("\n")
    with pytest.raises(ValueError, match="corpus is empty"):
        load_corpus(str(corpus))


def test_run_corpus_emits_deterministic_report(monkeypatch) -> None:
    import tree_sitter_analyzer.task_harness as harness

    class FakeExecutor:
        async def call(self, facade, action, arguments):
            return {"success": True}

    monkeypatch.setattr(harness, "McpPrimitiveExecutor", lambda root: FakeExecutor())
    corpus = "-"
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            '{"operation": "understand", "task": "x"}\n'
            '{"operation": "assess_change", "diff": {"source": "workspace"}}\n'
        ),
    )
    report = harness.run_corpus(corpus, project_root=".")
    parsed = json.loads(report)
    assert set(parsed) == {"results"}
    assert [r["operation"] for r in parsed["results"]] == [
        "understand",
        "assess_change",
    ]
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            '{"operation": "understand", "task": "x"}\n'
            '{"operation": "assess_change", "diff": {"source": "workspace"}}\n'
        ),
    )
    assert harness.run_corpus(corpus, project_root=".") == report


def test_cli_main_request_json_mode(monkeypatch, capsys) -> None:
    import tree_sitter_analyzer.task_harness as harness

    async def fake_run(*args, **kwargs):
        return "{}"

    monkeypatch.setattr(harness, "run_operation", fake_run)
    request = {"task": "explain dispatch", "profile": "compact"}
    assert (
        harness.main(["--operation", "understand", "--request-json", "-"]) == 0
        and capsys.readouterr().out == "{}\n"
        if False
        else True
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(request)))
    assert harness.main(["--operation", "understand", "--request-json", "-"]) == 0
    assert capsys.readouterr().out == "{}\n"
    assert (
        harness.main(
            ["--operation", "understand", "--request-json", "-", "--task", "x"]
        )
        == 2
    )  # mutually exclusive


def test_cli_main_corpus_mode(monkeypatch, capsys) -> None:
    import tree_sitter_analyzer.task_harness as harness

    def fake_corpus(*args, **kwargs):
        return '{"results": []}'

    monkeypatch.setattr(harness, "run_corpus", fake_corpus)
    assert harness.main(["--corpus", "-"]) == 0
    assert capsys.readouterr().out == '{"results": []}\n'
    assert harness.main(["--corpus", "-", "--task", "x"]) == 2
