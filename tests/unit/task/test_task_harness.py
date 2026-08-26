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


def _strip_timing(report: dict) -> dict:
    """Drop per-execution timing measurements (not deterministic)."""
    for result in report.get("results", []):
        consumed = result.get("consumed") or {}
        for key in ("routing_wall_ms", "cleanup_wall_ms", "deadline_overrun_ms"):
            consumed.pop(key, None)
    return report


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
    # Byte-identical except per-execution timing fields (wall clocks vary).
    second = harness.run_corpus(corpus, project_root=".")
    assert _strip_timing(json.loads(second)) == _strip_timing(json.loads(report))


def test_cli_main_request_json_mode(monkeypatch, capsys) -> None:
    import tree_sitter_analyzer.task_harness as harness

    async def fake_run(*args, **kwargs):
        return "{}"

    monkeypatch.setattr(harness, "run_operation", fake_run)
    monkeypatch.setattr(
        sys, "stdin", io.StringIO(json.dumps({"task": "explain dispatch"}))
    )
    assert harness.main(["--operation", "understand", "--request-json", "-"]) == 0
    assert capsys.readouterr().out == "{}\n"


def test_cli_main_corpus_mode(monkeypatch, capsys) -> None:
    import tree_sitter_analyzer.task_harness as harness

    def fake_corpus(*args, **kwargs):
        return '{"results": []}'

    monkeypatch.setattr(harness, "run_corpus", fake_corpus)
    assert harness.main(["--corpus", "-"]) == 0
    assert capsys.readouterr().out == '{"results": []}\n'
    assert harness.main(["--corpus", "-", "--task", "x"]) == 2


def test_load_corpus_rejects_non_object_line(tmp_path) -> None:
    from tree_sitter_analyzer.task_harness import load_corpus

    corpus = tmp_path / "arr.jsonl"
    corpus.write_text("[1, 2]\n")
    with pytest.raises(ValueError, match="not an object"):
        load_corpus(str(corpus))


def test_cli_main_requires_operation_without_corpus(monkeypatch, capsys) -> None:
    import tree_sitter_analyzer.task_harness as harness

    assert harness.main(["--task", "x"]) == 2
    assert "operation is required" in capsys.readouterr().err


def test_cli_main_corpus_invalid_json(monkeypatch, capsys) -> None:
    import tree_sitter_analyzer.task_harness as harness

    async def fake_run(*args, **kwargs):
        raise ValueError("boom")

    monkeypatch.setattr(harness, "run_operation", fake_run)
    corpus = "-"
    monkeypatch.setattr(sys, "stdin", io.StringIO("not-json\n"))
    assert harness.main(["--corpus", corpus]) == 2
    assert "invalid corpus" in capsys.readouterr().err


def test_cli_main_request_json_invalid_payloads(monkeypatch, capsys) -> None:
    import tree_sitter_analyzer.task_harness as harness

    monkeypatch.setattr(sys, "stdin", io.StringIO("not-json"))
    assert harness.main(["--operation", "understand", "--request-json", "-"]) == 2
    assert "invalid request JSON" in capsys.readouterr().err

    monkeypatch.setattr(sys, "stdin", io.StringIO("[1,2]"))
    assert harness.main(["--operation", "understand", "--request-json", "-"]) == 2
    assert "not an object" in capsys.readouterr().err

    monkeypatch.setattr(
        sys, "stdin", io.StringIO('{"task": "x", "diff": {"source": "workspace"}}')
    )
    assert harness.main(["--operation", "understand", "--request-json", "-"]) == 2
    assert "invalid request" in capsys.readouterr().err


def test_cli_main_request_json_from_file(monkeypatch, capsys, tmp_path) -> None:
    import tree_sitter_analyzer.task_harness as harness

    async def fake_run(*args, **kwargs):
        return "{}"

    monkeypatch.setattr(harness, "run_operation", fake_run)
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps({"task": "x"}))
    assert (
        harness.main(
            [
                "--operation",
                "understand",
                "--request-json",
                str(request_file),
                "--project-root",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert capsys.readouterr().out == "{}\n"
    # A missing file is a hard CLI error, not a crash.
    assert (
        harness.main(
            [
                "--operation",
                "understand",
                "--request-json",
                str(tmp_path / "nope.json"),
                "--project-root",
                str(tmp_path),
            ]
        )
        == 2
    )
    assert "invalid request JSON" in capsys.readouterr().err


# --- Codex #1292 review fixes ------------------------------------------------


def test_request_from_dict_normalizes_malformed_types() -> None:
    with pytest.raises(ValueError, match="task must be a string"):
        request_from_dict("understand", {"task": 1})
    with pytest.raises(ValueError, match="task must be a string"):
        request_from_dict("plan_change", {"task": 1})
    with pytest.raises(ValueError, match="diff must be a dict"):
        request_from_dict("assess_change", {"diff": "workspace"})


def test_top_level_budget_ceilings_are_honored() -> None:
    from tree_sitter_analyzer.task_harness import _budget_from_dict

    budget = _budget_from_dict({"max_primitive_calls": 1})
    assert budget.max_primitive_calls == 1
    budget = _budget_from_dict({"max_evidence_items": 2})
    assert budget.max_evidence_items == 2
    budget = _budget_from_dict({"routing_deadline_ms": 100})
    assert budget.routing_deadline_ms == 100


def test_strict_json_rejects_duplicate_keys_and_constants(tmp_path) -> None:
    from tree_sitter_analyzer.task_harness import load_corpus

    corpus = tmp_path / "dup.jsonl"
    corpus.write_text('{"operation": "understand", "task": "a", "task": "b"}\n')
    with pytest.raises(ValueError, match="duplicate key"):
        load_corpus(str(corpus))
    corpus.write_text(
        '{"operation": "understand", "task": "x", "routing_deadline_ms": NaN}\n'
    )
    with pytest.raises(ValueError, match="invalid JSON"):
        load_corpus(str(corpus))


def test_corpus_input_bound_is_enforced(tmp_path) -> None:
    from tree_sitter_analyzer.task_harness import MAX_CORPUS_BYTES, load_corpus

    corpus = tmp_path / "huge.jsonl"
    corpus.write_text("x" * (MAX_CORPUS_BYTES + 1))
    with pytest.raises(ValueError, match="8 MiB input bound"):
        load_corpus(str(corpus))


def test_cli_input_paths_are_project_boundary_checked(
    monkeypatch, capsys, tmp_path
) -> None:
    import tree_sitter_analyzer.task_harness as harness

    outside = tmp_path / "outside.jsonl"
    outside.write_text('{"operation": "understand", "task": "x"}\n')
    project = tmp_path / "project"
    project.mkdir()
    assert harness.main(["--corpus", str(outside), "--project-root", str(project)]) == 2
    assert "outside the project" in capsys.readouterr().err
    assert (
        harness.main(
            [
                "--operation",
                "understand",
                "--request-json",
                str(outside),
                "--project-root",
                str(project),
            ]
        )
        == 2
    )
    assert "outside the project" in capsys.readouterr().err


def test_cli_option_presence_exclusivity(monkeypatch, capsys) -> None:
    import tree_sitter_analyzer.task_harness as harness

    async def fake_run(*args, **kwargs):
        return "{}"

    monkeypatch.setattr(harness, "run_operation", fake_run)
    # An explicitly supplied empty task still conflicts with --request-json.
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"task": "x"}'))
    assert (
        harness.main(["--operation", "understand", "--request-json", "-", "--task", ""])
        == 2
    )
    assert "exclusive" in capsys.readouterr().err
