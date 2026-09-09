"""短描述符保留完整计划，且拒绝篡改或无法重建的分析输入。"""

import base64
import json
import shlex
from dataclasses import replace

import pytest

from tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis import (
    ChangeImpactRequest,
    _build_test_only_change_impact_result,
)
from tree_sitter_analyzer.verification_plan import decode_request, digest, within_budget
from tree_sitter_analyzer.verification_runner import rebuild_request


def make_plan(tmp_path, *, profile="default", count=1000, **kwargs):
    paths = [f"tests/unit/test_feature_{index:04d}.py" for index in range(count)]
    request = ChangeImpactRequest(
        mode="diff",
        changed_files=paths,
        diff_stat="",
        project_root=str(tmp_path),
        include_tests=True,
        resource_profile=profile,
    )
    request = replace(request, **kwargs)
    response = _build_test_only_change_impact_result(request)
    return request, response


def descriptor(response, field="verification_command"):
    return decode_request(shlex.split(response[field])[-1])


@pytest.mark.parametrize("mode", ["diff", "staged", "branch"])
@pytest.mark.parametrize("profile", ["default", "local_low_impact"])
def test_thousand_targets_rebuild_without_inline_target_list(
    tmp_path, monkeypatch, profile, mode
):
    request, response = make_plan(tmp_path, profile=profile, mode=mode)
    command = response["verification_command"]
    assert within_budget(command) is True
    assert "test_feature_0999.py" not in command
    value = descriptor(response)
    assert value["request"]["resource_profile"] == profile
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.utils.change_impact_git._get_changed_files",
        lambda *args: request.changed_files,
    )
    stages = rebuild_request(value, str(tmp_path.resolve()))
    targets = [
        arg for step in stages for arg in step["argv"] if arg.startswith("tests/")
    ]
    assert targets == request.changed_files
    assert len(stages) == 50
    assert response["pytest_command"] == command
    assert response["test_command"] == command
    assert response["agent_summary"]["verification_command"] == command


def test_complete_plan_digest_preserves_order_role_and_arguments():
    plan = [
        {"role": "focused", "argv": ["pytest", "测试.py", ""]},
        {"role": "default_gate", "argv": ["pytest"]},
    ]
    assert digest(plan) == digest(json.loads(json.dumps(plan)))
    for changed in (
        plan[::-1],
        plan[:1],
        [{"role": "focused", "argv": ["pytest", "测试.py"]}, plan[1]],
    ):
        assert digest(changed) != digest(plan)


@pytest.mark.parametrize("change", ["root", "paths", "plan"])
def test_changed_request_never_reaches_execution(tmp_path, monkeypatch, change):
    request, response = make_plan(tmp_path)
    value = descriptor(response)
    if change == "root":
        value["root"] = "0" * 64
    if change == "plan":
        value["plan"] = "0" * 64
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.utils.change_impact_git._get_changed_files",
        lambda *args: (
            request.changed_files[:-1] if change == "paths" else request.changed_files
        ),
    )
    with pytest.raises(ValueError, match="VERIFICATION_PLAN_CHANGED"):
        rebuild_request(value, str(tmp_path.resolve()))


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", 2),
        ("version", True),
        ("stage", "shell"),
        ("timeout", 0),
        ("timeout", 901),
        ("timeout", True),
        ("root", "wrong"),
        ("plan", "z" * 64),
        ("request", []),
        ("unknown", "execute"),
    ],
)
def test_invalid_descriptor_is_rejected(tmp_path, field, value):
    _, response = make_plan(tmp_path)
    request = descriptor(response)
    request[field] = value
    token = base64.urlsafe_b64encode(json.dumps(request).encode()).decode()
    with pytest.raises(ValueError, match="VERIFICATION_REQUEST_INVALID"):
        decode_request(token)


@pytest.mark.parametrize("value", ["!", "", "a" * 5801, None, "bnVsbA=="])
def test_invalid_encoding_is_rejected(value):
    with pytest.raises(ValueError, match="VERIFICATION_REQUEST_INVALID"):
        decode_request(value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("mode", "shell"),
        ("include_tests", 1),
        ("resource_profile", "unlimited"),
        ("scope_paths", "tests/"),
        ("scope_paths", [1]),
        ("scope_paths", ["a\x00b"]),
        ("pr_url", 1),
        ("pr_url", "https://github.com/a/b/pull/1"),
    ],
)
def test_invalid_analysis_arguments_are_rejected(tmp_path, field, value):
    _, response = make_plan(tmp_path)
    request = descriptor(response)
    request["request"][field] = value
    token = base64.urlsafe_b64encode(json.dumps(request).encode()).decode()
    with pytest.raises(ValueError, match="VERIFICATION_REQUEST_INVALID"):
        decode_request(token)


@pytest.mark.parametrize("mode", ["scope", "snapshot"])
def test_unrepresentable_request_does_not_advertise_oversized_commands(tmp_path, mode):
    kwargs = {"scope_paths": ["x" * 6000]} if mode == "scope" else {"read_only": True}
    _, response = make_plan(tmp_path, **kwargs)
    assert response["success"] is False
    assert response["error_code"] == (
        "VERIFICATION_REQUEST_TOO_LARGE"
        if mode == "scope"
        else "VERIFICATION_SNAPSHOT_NOT_REPLAYABLE"
    )
    assert response["verification_command"] == ""
    assert len(response["verification_steps"]) == 50


@pytest.mark.parametrize("drift", [False, True])
def test_pr_replay_binds_remote_identity_at_both_boundaries(
    tmp_path, monkeypatch, drift
):
    from tree_sitter_analyzer import verification_plan, verification_runner

    identity = {"head": "a" * 40, "base": "b" * 40}
    monkeypatch.setattr(verification_plan, "pr_identity", lambda *args: identity)
    request, response = make_plan(
        tmp_path, mode="pr", pr_url="https://github.com/example/project/pull/1"
    )
    value = descriptor(response)
    identities = iter([identity, {**identity, "base": "c" * 40} if drift else identity])
    monkeypatch.setattr(
        verification_runner, "pr_identity", lambda *args: next(identities)
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.pr_url.fetch_pr_changed_files",
        lambda *_: request.changed_files,
    )
    if drift:
        with pytest.raises(ValueError, match="VERIFICATION_PLAN_CHANGED"):
            rebuild_request(value, str(tmp_path.resolve()))
    else:
        assert len(rebuild_request(value, str(tmp_path.resolve()))) == 50


@pytest.mark.parametrize("state", ["clean", "dirty", "other_head"])
def test_pr_checkout_identity_uses_actual_git_state(tmp_path, monkeypatch, state):
    from types import SimpleNamespace

    from tree_sitter_analyzer.verification_plan import pr_identity

    remote = {"headRefOid": "a" * 40, "baseRefOid": "b" * 40}
    responses = iter(
        [
            json.dumps(remote),
            "c" * 40 if state == "other_head" else remote["headRefOid"],
            " M a.py" if state == "dirty" else "",
        ]
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.verification_plan.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(stdout=next(responses)),
    )
    if state == "clean":
        assert pr_identity(
            str(tmp_path), "https://github.com/example/project/pull/1"
        ) == {"head": "a" * 40, "base": "b" * 40}
    else:
        with pytest.raises(ValueError, match="VERIFICATION_PR_CHECKOUT_MISMATCH"):
            pr_identity(str(tmp_path), "https://github.com/example/project/pull/1")


def test_oversized_scope_error_survives_compact_cli_response(tmp_path):
    from tree_sitter_analyzer.mcp.tools.utils.change_impact_response import (
        build_agent_summary_only_response,
    )

    _, response = make_plan(tmp_path, scope_paths=["x" * 6000])
    compact = build_agent_summary_only_response(response)
    assert compact["success"] is False
    assert compact["error_code"] == "VERIFICATION_REQUEST_TOO_LARGE"
    assert compact["verification_command"] == ""


def test_ten_thousand_targets_do_not_expand_launcher(tmp_path):
    _, small = make_plan(tmp_path, count=1000)
    request, large = make_plan(tmp_path, count=10000)
    assert len(large["verification_command"]) == len(small["verification_command"])
    assert len(large["verification_steps"]) == 500
    targets = [
        arg
        for step in large["verification_steps"]
        for arg in shlex.split(step)
        if arg.startswith("tests/")
    ]
    assert targets == request.changed_files


@pytest.mark.parametrize("marker", [None, "not network and not benchmark"])
def test_low_impact_prefix_rebatches_near_limit_targets(monkeypatch, marker):
    from types import SimpleNamespace

    from tree_sitter_analyzer import verification_plan
    from tree_sitter_analyzer.mcp.tools.utils.verification_command import (
        _argv_within_budget,
    )

    monkeypatch.setattr(verification_plan, "sys", SimpleNamespace(platform="linux"))
    prefix = (
        "tests/"
        + "/".join(["x" * 50] * 57)
        + "/"
        + "x" * (60 if marker is None else 43)
    )
    targets = [prefix + f"/test_{suffix}.py" for suffix in ("a", "b")]
    context = SimpleNamespace(
        verification={
            "test_runner": "pytest",
            "default_test_command": "uv run pytest -q",
            "test_required": True,
            "_pytest_marker": marker,
        },
        all_tests=targets,
        test_mapping={"a.py": targets},
        request=SimpleNamespace(resource_profile="local_low_impact"),
    )
    stages = verification_plan.compile_stages(context)
    assert len(stages["focused"]) == 1
    assert len(stages["verification"]) == 2
    assert [
        arg
        for step in stages["verification"]
        for arg in step["argv"]
        if arg.startswith("tests/")
    ] == targets
    assert all(_argv_within_budget(step["argv"]) for step in stages["verification"])
    if marker:
        assert [step["argv"][6:8] for step in stages["verification"]] == [
            ["-m", marker]
        ] * 2


def test_marker_policy_changes_invalidate_replayed_plan(tmp_path, monkeypatch):
    """2026-09-09：重放必须绑定定向筛选策略，不能采用变化后的配置。"""
    monkeypatch.delenv("PYTEST_ADDOPTS", raising=False)
    config = tmp_path / "pytest.ini"
    config.write_text(
        "[pytest]\naddopts = -m 'not slow and not custom'\n", encoding="utf-8"
    )
    request, response = make_plan(tmp_path)
    value = descriptor(response)
    monkeypatch.setattr(
        "tree_sitter_analyzer.mcp.tools.utils.change_impact_git._get_changed_files",
        lambda *args: request.changed_files,
    )
    stages = rebuild_request(value, str(tmp_path.resolve()))
    assert [step["argv"][3:5] for step in stages] == [
        ["-m", "not custom and not network and not benchmark"]
    ] * 50
    config.write_text(
        "[pytest]\naddopts = -m 'not slow and not other'\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="VERIFICATION_PLAN_CHANGED"):
        rebuild_request(value, str(tmp_path.resolve()))


def test_mapped_batches_keep_unmapped_default_gate(tmp_path):
    from types import SimpleNamespace

    from tree_sitter_analyzer.mcp.tools.utils.change_impact_verification import (
        AUTO_DISCOVER_TEST_HINT,
    )
    from tree_sitter_analyzer.verification_plan import compile_stages

    targets = [f"tests/test_feature_{index:04d}.py" for index in range(1000)]
    context = SimpleNamespace(
        verification={
            "test_runner": "pytest",
            "default_test_command": "uv run pytest -q",
            "test_required": True,
        },
        all_tests=targets,
        test_mapping={"unmapped.py": [AUTO_DISCOVER_TEST_HINT]},
        request=SimpleNamespace(resource_profile="default"),
    )
    steps = compile_stages(context)["verification"]
    assert len(steps) == 51
    assert steps[-1] == {"role": "default_gate", "argv": ["uv", "run", "pytest", "-q"]}
    assert [
        arg for step in steps[:-1] for arg in step["argv"] if arg.startswith("tests/")
    ] == targets


@pytest.mark.parametrize("scope_size", [3800, 4000])
def test_generated_descriptor_obeys_decoder_budget(tmp_path, scope_size):
    # PR #1407：外层仍可启动不代表解码器接受该输入。
    _, response = make_plan(tmp_path, scope_paths=["x" * scope_size])
    if scope_size == 3800:
        assert descriptor(response)["request"]["scope_paths"] == ["x" * scope_size]
    else:
        assert response["success"] is False
        assert response["error_code"] == "VERIFICATION_REQUEST_TOO_LARGE"
        assert response["verification_command"] == ""


@pytest.mark.parametrize("identity", [None, {}, {"head": "a"}])
def test_pr_descriptor_requires_complete_identity(tmp_path, monkeypatch, identity):
    from tree_sitter_analyzer import verification_plan

    monkeypatch.setattr(verification_plan, "pr_identity", lambda *_: identity)
    _, response = make_plan(tmp_path, mode="pr", pr_url="https://github.com/a/b/pull/1")
    with pytest.raises(ValueError, match="VERIFICATION_REQUEST_INVALID"):
        descriptor(response)


def test_pr_descriptor_rejects_non_pr_url(tmp_path, monkeypatch):
    from tree_sitter_analyzer import verification_plan

    monkeypatch.setattr(verification_plan, "pr_identity", lambda *_: {})
    _, response = make_plan(tmp_path, mode="pr", pr_url="https://example.com/no-pr")
    with pytest.raises(ValueError, match="VERIFICATION_REQUEST_INVALID"):
        descriptor(response)


@pytest.mark.parametrize(
    "kind", ["docs", "default_only", "same_gate", "non_pytest", "oversized"]
)
def test_stage_compiler_preserves_required_gate_behavior(kind):
    from types import SimpleNamespace

    from tree_sitter_analyzer.mcp.tools.utils.change_impact_verification import (
        AUTO_DISCOVER_TEST_HINT,
    )
    from tree_sitter_analyzer.verification_plan import compile_stages

    context = SimpleNamespace(
        verification={
            "test_runner": "pytest",
            "default_test_command": "uv run pytest -q",
            "test_required": kind != "docs",
        },
        all_tests=[],
        test_mapping={},
        request=SimpleNamespace(resource_profile="default"),
    )
    expected = [{"role": "default_gate", "argv": ["uv", "run", "pytest", "-q"]}]
    if kind == "docs":
        expected = [{"role": "non_test_check", "argv": ["git", "diff", "--check"]}]
    elif kind == "same_gate":
        context.all_tests = ["tests/test_one.py"]
        context.verification["default_test_command"] = (
            "uv run pytest tests/test_one.py -q"
        )
        context.test_mapping = {"unknown.py": [AUTO_DISCOVER_TEST_HINT]}
        expected = [
            {
                "role": "focused",
                "argv": ["uv", "run", "pytest", "tests/test_one.py", "-q"],
            }
        ]
    elif kind == "non_pytest":
        context.verification.update(test_runner="npm", default_test_command="npm test")
        context.all_tests = ["tests/one.test.js"]
        expected = [
            {"role": "focused", "argv": ["npm", "test", "--", "tests/one.test.js"]}
        ]
    elif kind == "oversized":
        context.verification["default_test_command"] = "uv run pytest " + "x" * 6000
        context.request.resource_profile = "local_low_impact"
        with pytest.raises(ValueError, match="VERIFICATION_REQUEST_TOO_LARGE"):
            compile_stages(context)
        return
    stages = compile_stages(context)
    assert stages["verification"] == expected
    if kind == "non_pytest":
        assert stages["low_focused"] == expected


@pytest.mark.parametrize("case", ["early_drift", "invalid_url", "scope", "oversized"])
def test_pr_rebuild_fails_closed_or_preserves_scope(tmp_path, monkeypatch, case):
    from tree_sitter_analyzer import verification_plan, verification_runner

    identity = {"head": "a" * 40, "base": "b" * 40}
    monkeypatch.setattr(verification_plan, "pr_identity", lambda *_: identity)
    request, response = make_plan(
        tmp_path,
        mode="pr",
        pr_url="https://github.com/a/b/pull/1",
        scope_paths=["tests/unit/"],
    )
    value = descriptor(response)
    monkeypatch.setattr(
        verification_runner,
        "pr_identity",
        lambda *_: {} if case == "early_drift" else identity,
    )
    monkeypatch.setattr(
        "tree_sitter_analyzer.pr_url.fetch_pr_changed_files",
        lambda *_: [*request.changed_files, "outside.py"],
    )
    if case == "invalid_url":
        value["request"]["pr_url"] = "invalid"
    if case == "oversized":
        monkeypatch.setattr(
            "tree_sitter_analyzer.mcp.tools.utils.verification_command._argv_within_budget",
            lambda *_: False,
        )
        # 仅在实际 argv 的最终边界注入失败，不能破坏重建编译器本身。
        original = verification_runner._CAPTURE

        class Capture:
            def set(self, captured):
                captured["stages"] = {
                    value["stage"]: [{"role": "focused", "argv": ["x"]}]
                }
                return original.set({})

            def reset(self, token):
                original.reset(token)

        monkeypatch.setattr(verification_runner, "_CAPTURE", Capture())
        monkeypatch.setattr(
            "tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis._build_change_impact_result",
            lambda *_: {},
        )
        value["plan"] = digest([{"role": "focused", "argv": ["x"]}])
    if case == "scope":
        assert len(rebuild_request(value, str(tmp_path.resolve()))) == 50
    else:
        code = {
            "early_drift": "VERIFICATION_PLAN_CHANGED",
            "invalid_url": "VERIFICATION_REQUEST_INVALID",
            "oversized": "VERIFICATION_REQUEST_TOO_LARGE",
        }[case]
        with pytest.raises(ValueError, match=code):
            rebuild_request(value, str(tmp_path.resolve()))
