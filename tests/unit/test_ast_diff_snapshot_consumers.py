"""Frozen snapshot consumer coverage for AST diff and semantic classify."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

import tree_sitter_analyzer.diff_snapshot_epoch as epoch_verification
import tree_sitter_analyzer.diff_snapshot_registry as snapshots
from tests.unit._diff_snapshot_support import POSIX_SNAPSHOT_TEST, make_repo
from tree_sitter_analyzer.mcp.tools.ast_diff_tool import ASTDiffTool
from tree_sitter_analyzer.mcp.tools.semantic_classify_tool import SemanticClassifyTool


@pytest.fixture
def tool():
    return ASTDiffTool(project_root="/tmp/test_project")


def _create_stable_consumer_snapshot(
    monkeypatch: pytest.MonkeyPatch, root: Path
) -> dict[str, object]:
    """Capture once, then make consumer publication verification deterministic."""
    monkeypatch.setattr(
        epoch_verification.FrozenGitEnvironment,
        "verify_source_epoch",
        lambda self: None,
    )
    created = snapshots.REGISTRY.create(str(root), "diff", [])
    identity = snapshots.canonical_root(str(root))[1]
    generation = str(created["source_generation"])
    state = snapshots.REGISTRY._states[str(created["diff_snapshot_id"])]
    git_generation = state.snapshot.git_generation
    monkeypatch.setattr(
        snapshots,
        "oracle_generation",
        lambda project_root, mode="diff", *, deadline=None: (git_generation, identity),
    )
    monkeypatch.setattr(
        snapshots,
        "shared_source_generation",
        lambda *_args, **_kwargs: generation,
    )
    return created


@pytest.mark.asyncio
async def test_snapshot_requires_file_path(tool) -> None:
    with pytest.raises(ValueError, match="DIFF_SNAPSHOT_FILE_REQUIRED"):
        await tool.execute({"diff_snapshot_id": "ds"})


@pytest.mark.asyncio
async def test_snapshot_translates_registry_error(tool, monkeypatch) -> None:
    from tree_sitter_analyzer import diff_snapshot_registry as registry

    monkeypatch.setattr(
        registry.REGISTRY, "acquire", lambda *a: (None, "DIFF_SNAPSHOT_EXPIRED")
    )
    result = await tool.execute(
        {"diff_snapshot_id": "ds", "file_path": "x.py", "output_format": "json"}
    )
    assert result["error_code"] == "DIFF_SNAPSHOT_EXPIRED"


@pytest.mark.asyncio
async def test_snapshot_reports_missing_frozen_file(tool, monkeypatch) -> None:
    from types import SimpleNamespace

    from tree_sitter_analyzer import diff_snapshot_registry as registry

    consumer = SimpleNamespace(
        snapshot=SimpleNamespace(file=lambda path: None), release=lambda: None
    )
    monkeypatch.setattr(registry.REGISTRY, "acquire", lambda *a: (consumer, None))
    result = await tool.execute(
        {"diff_snapshot_id": "ds", "file_path": "x.py", "output_format": "json"}
    )
    assert result["error_code"] == "DIFF_SNAPSHOT_FILE_NOT_FOUND"


@pytest.mark.asyncio
async def test_snapshot_rejects_non_utf8_frozen_bytes(tool, monkeypatch) -> None:
    from types import SimpleNamespace

    from tree_sitter_analyzer import diff_snapshot_registry as registry

    frozen = SimpleNamespace(
        record=SimpleNamespace(path="x.py", binary=False),
        old_bytes=b"\xff",
        new_bytes=b"",
    )
    consumer = SimpleNamespace(
        snapshot=SimpleNamespace(file=lambda path: frozen), release=lambda: None
    )
    monkeypatch.setattr(registry.REGISTRY, "acquire", lambda *a: (consumer, None))
    result = await tool.execute(
        {"diff_snapshot_id": "ds", "file_path": "x.py", "output_format": "json"}
    )
    assert result["error_code"] == "DIFF_SNAPSHOT_UNSUPPORTED_CONTENT"


@pytest.mark.parametrize(
    ("tool_type", "field", "expected"),
    [(ASTDiffTool, "hunks", 2), (SemanticClassifyTool, "change_count", 2)],
)
@POSIX_SNAPSHOT_TEST
def test_snapshot_consumer_uses_frozen_utf8_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tool_type,
    field: str,
    expected: int,
) -> None:
    root = make_repo(tmp_path)
    (root / "old.py").write_text("value = 2\n")
    result = _create_stable_consumer_snapshot(monkeypatch, root)
    request = {
        "diff_snapshot_id": result["diff_snapshot_id"],
        "file_path": "old.py",
        "output_format": "json",
    }
    response = asyncio.run(tool_type(str(root)).execute(request))
    assert (
        len(response[field]) if isinstance(response[field], list) else response[field]
    ) == expected
    assert (
        snapshots.REGISTRY.close_lease(
            str(result["diff_snapshot_id"]), str(result["route_lease_id"])
        )
        is True
    )


@pytest.mark.parametrize("tool_type", [ASTDiffTool, SemanticClassifyTool])
@pytest.mark.parametrize("output_format", ["json", "toon"])
@POSIX_SNAPSHOT_TEST
@pytest.mark.slow_ok  # real git diff capture x2; brushes the 5s budget under --cov
def test_snapshot_consumer_echoes_exact_frozen_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tool_type,
    output_format: str,
) -> None:
    # PR #1252 review thread 3748730795: consumers must not infer identity.
    root = make_repo(tmp_path)
    (root / "old.py").write_text("value = 2\n")
    created = _create_stable_consumer_snapshot(monkeypatch, root)
    response = asyncio.run(
        tool_type(str(root)).execute(
            {
                "diff_snapshot_id": created["diff_snapshot_id"],
                "file_path": "old.py",
                "output_format": output_format,
            }
        )
    )
    assert response["diff_snapshot_id"] == created["diff_snapshot_id"]
    assert response["source_generation"] == created["source_generation"]
    assert (
        snapshots.REGISTRY.close_lease(
            str(created["diff_snapshot_id"]), str(created["route_lease_id"])
        )
        is True
    )


@pytest.mark.parametrize("tool_type", [ASTDiffTool, SemanticClassifyTool])
@POSIX_SNAPSHOT_TEST
def test_snapshot_consumer_rejects_binary_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tool_type
) -> None:
    root = make_repo(tmp_path)
    (root / "blob.py").write_bytes(b"a\0b")
    result = _create_stable_consumer_snapshot(monkeypatch, root)
    request = {
        "diff_snapshot_id": result["diff_snapshot_id"],
        "file_path": "blob.py",
        "output_format": "json",
    }
    response = asyncio.run(tool_type(str(root)).execute(request))
    assert response["error_code"] == "DIFF_SNAPSHOT_UNSUPPORTED_CONTENT"
    assert (
        snapshots.REGISTRY.close_lease(
            str(result["diff_snapshot_id"]), str(result["route_lease_id"])
        )
        is True
    )


@pytest.mark.parametrize(
    ("tool_type", "module_name"),
    [
        (ASTDiffTool, "tree_sitter_analyzer.mcp.tools.ast_diff_tool"),
        (
            SemanticClassifyTool,
            "tree_sitter_analyzer.mcp.tools.semantic_classify_tool",
        ),
    ],
)
@pytest.mark.parametrize(
    ("validation_error", "request_format", "expected_error"),
    [
        (
            "DIFF_SNAPSHOT_SOURCE_CHANGED",
            "toon",
            "DIFF_SNAPSHOT_SOURCE_CHANGED",
        ),
        ("DIFF_SNAPSHOT_EXPIRED", None, "DIFF_SNAPSHOT_EXPIRED"),
        (
            "DIFF_SNAPSHOT_FUTURE_ERROR",
            None,
            "DIFF_SNAPSHOT_VALIDATION_ERROR",
        ),
    ],
)
@pytest.mark.asyncio
async def test_strict_snapshot_final_publish_errors_preserve_toon(
    tool_type,
    module_name: str,
    validation_error: str,
    request_format: str | None,
    expected_error: str,
    monkeypatch,
) -> None:
    from importlib import import_module
    from types import SimpleNamespace

    from tree_sitter_analyzer import diff_snapshot_registry as registry

    events: list[tuple[str, bool]] = []
    released = False
    frozen = SimpleNamespace(
        record=SimpleNamespace(path="x.py", binary=False),
        old_bytes=b"value = 1\n",
        new_bytes=b"value = 2\n",
    )

    def release() -> None:
        nonlocal released
        released = True
        events.append(("release", released))

    consumer = SimpleNamespace(
        snapshot=SimpleNamespace(file=lambda path: frozen), release=release
    )
    monkeypatch.setattr(registry.REGISTRY, "acquire", lambda *a: (consumer, None))

    def validate_publish(pinned) -> str:
        events.append(("validate", released))
        return validation_error

    monkeypatch.setattr(registry.REGISTRY, "validate_publish", validate_publish)
    tool_module = import_module(module_name)
    original_formatter = tool_module.apply_toon_format_to_response

    def formatting(response, output_format):
        events.append(("format", released))
        return original_formatter(response, output_format)

    monkeypatch.setattr(tool_module, "apply_toon_format_to_response", formatting)
    request = {"diff_snapshot_id": "ds", "file_path": "x.py"}
    if request_format is not None:
        request["output_format"] = request_format
    response = await tool_type(".").execute(request)
    # PR #1252 review thread 3750964908: final validation must not bypass TOON.
    assert response["error_code"] == expected_error
    assert response["format"] == "toon"
    assert isinstance(response["toon_content"], str)
    assert events == [("format", False)] * 22 + [
        ("validate", False),
        ("release", True),
    ]


def test_snapshot_consumers_reject_symlink_kind() -> None:
    # PR #1252 review thread 3746878582.
    from types import SimpleNamespace

    from tree_sitter_analyzer.mcp.tools.ast_diff_tool import ASTDiffTool

    frozen = SimpleNamespace(
        record=SimpleNamespace(
            path="module.py", binary=False, old_kind="symlink", new_kind="symlink"
        ),
        old_bytes=b"target.py",
        new_bytes=b"other.py",
    )
    consumer = SimpleNamespace(
        snapshot=SimpleNamespace(file=lambda path: frozen), release=lambda: None
    )
    with patch(
        "tree_sitter_analyzer.diff_snapshot_registry.REGISTRY.acquire",
        return_value=(consumer, None),
    ):
        result = asyncio.run(
            ASTDiffTool(".").execute(
                {
                    "diff_snapshot_id": "ds",
                    "file_path": "module.py",
                    "output_format": "json",
                }
            )
        )
    assert result["error_code"] == "DIFF_SNAPSHOT_UNSUPPORTED_CONTENT"


def test_snapshot_ast_options_are_not_source_conflicts() -> None:
    # PR #1252 review thread 3746878597.
    from tree_sitter_analyzer.mcp.tools.ast_diff_tool import ASTDiffTool

    assert (
        ASTDiffTool(".").validate_arguments(
            {
                "diff_snapshot_id": "ds",
                "file_path": "module.py",
                "include_node_bodies": True,
                "output_format": "json",
            }
        )
        is True
    )


def test_ast_diff_execute_rejects_unreachable_unknown_mode() -> None:
    tool = ASTDiffTool(".")
    with (
        patch.object(tool, "validate_arguments", return_value=True),
        patch.object(tool, "_resolve_mode", return_value="unknown"),
        pytest.raises(ValueError, match="Unknown mode: unknown"),
    ):
        asyncio.run(tool.execute({"output_format": "json"}))


@pytest.mark.parametrize("tool_type", [ASTDiffTool, SemanticClassifyTool])
@pytest.mark.parametrize("unavailable_side", ["old_available", "new_available"])
@pytest.mark.asyncio
async def test_snapshot_consumer_rejects_each_unavailable_side(
    tool_type, unavailable_side: str, monkeypatch
) -> None:
    # PR #1252 review thread 3748259951.
    from types import SimpleNamespace

    from tree_sitter_analyzer import diff_snapshot_registry as registry

    availability = {"old_available": True, "new_available": True}
    availability[unavailable_side] = False
    frozen = SimpleNamespace(
        record=SimpleNamespace(path="x.py", binary=False, **availability),
        old_bytes=b"value = 1\n",
        new_bytes=b"value = 2\n",
    )
    consumer = SimpleNamespace(
        snapshot=SimpleNamespace(file=lambda path: frozen), release=lambda: None
    )
    monkeypatch.setattr(registry.REGISTRY, "acquire", lambda *a: (consumer, None))

    result = await tool_type(".").execute(
        {"diff_snapshot_id": "ds", "file_path": "x.py", "output_format": "json"}
    )

    assert result["error_code"] == "DIFF_SNAPSHOT_UNSUPPORTED_CONTENT"


@pytest.mark.parametrize("tool_type", [ASTDiffTool, SemanticClassifyTool])
@pytest.mark.parametrize("status", ["R", "C"])
@pytest.mark.asyncio
async def test_snapshot_consumer_rejects_rename_and_copy_status(
    tool_type, status: str, monkeypatch
) -> None:
    # PR #1252 review thread 3748575979.
    from types import SimpleNamespace

    frozen = SimpleNamespace(
        record=SimpleNamespace(path="x.py", status=status, binary=False),
        old_bytes=b"value = 1\n",
        new_bytes=b"value = 2\n",
    )
    consumer = SimpleNamespace(
        snapshot=SimpleNamespace(file=lambda path: frozen), release=lambda: None
    )
    monkeypatch.setattr(snapshots.REGISTRY, "acquire", lambda *a: (consumer, None))
    result = await tool_type(".").execute(
        {"diff_snapshot_id": "ds", "file_path": "x.py", "output_format": "json"}
    )
    assert result["error_code"] == "DIFF_SNAPSHOT_UNSUPPORTED_CONTENT"


@pytest.mark.parametrize("tool_type", [ASTDiffTool, SemanticClassifyTool])
def test_snapshot_consumer_rejects_caller_language_override(tool_type) -> None:
    # PR #1252 review thread 4873: strict language is bound to captured path.
    with pytest.raises(ValueError, match="DIFF_SNAPSHOT_CONFLICTING_ARGUMENTS"):
        tool_type(".").validate_arguments(
            {
                "diff_snapshot_id": "ds",
                "file_path": "module.py",
                "language": "javascript",
            }
        )


@pytest.mark.parametrize("tool_type", [ASTDiffTool, SemanticClassifyTool])
@pytest.mark.asyncio
async def test_snapshot_consumer_rejects_unknown_captured_extension(
    tool_type, monkeypatch
) -> None:
    # PR #1252 review thread 4873: unknown captured extension is stable unsupported.
    from types import SimpleNamespace

    from tree_sitter_analyzer import diff_snapshot_registry as registry

    frozen = SimpleNamespace(
        record=SimpleNamespace(path="module.unknown", binary=False),
        old_bytes=b"old",
        new_bytes=b"new",
    )
    consumer = SimpleNamespace(
        snapshot=SimpleNamespace(file=lambda path: frozen), release=lambda: None
    )
    monkeypatch.setattr(registry.REGISTRY, "acquire", lambda *a: (consumer, None))

    result = await tool_type(".").execute(
        {
            "diff_snapshot_id": "ds",
            "file_path": "module.unknown",
            "output_format": "json",
        }
    )

    assert result["error_code"] == "DIFF_SNAPSHOT_UNSUPPORTED_LANGUAGE"
