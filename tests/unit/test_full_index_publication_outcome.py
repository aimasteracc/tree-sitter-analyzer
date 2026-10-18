"""``index action=full`` 的答复如实反映是否发布（#1674）。

已发布且可用的索引（只缺可选语法的文件）返回 ``success: true`` / ``WARN``；
未发布的运行返回带 ``error``、``error_code`` 与 ``next_step`` 的类型化失败，
而不是没有 ``error`` 字段、被信封补成 ``error_type: internal`` 的 ``success: false``。
"""

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.server_utils.error_recovery import (
    ensure_canonical_error_envelope,
)


@pytest.fixture
def project_root(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "main.py").write_text(
        "def hello(): return 1\ndef goodbye(): return hello()\n", encoding="utf-8"
    )
    return str(tmp_path)


def _without_swift_grammar(monkeypatch):
    """让 Swift 语法表现为未安装（与 test_generation_indexing 相同的做法）。"""
    import tree_sitter_analyzer.core.parser as parser_module
    from tree_sitter_analyzer.language_loader import LanguageLoader

    installed = parser_module.is_grammar_installed
    monkeypatch.setattr(
        parser_module,
        "is_grammar_installed",
        lambda language: language != "swift" and installed(language),
    )
    available = LanguageLoader.is_language_available
    load = LanguageLoader.load_language
    monkeypatch.setattr(
        LanguageLoader,
        "is_language_available",
        lambda self, language: language != "swift" and available(self, language),
    )
    monkeypatch.setattr(
        LanguageLoader,
        "load_language",
        lambda self, language: None if language == "swift" else load(self, language),
    )


async def _full_index(project_root):
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    return await CodeGraphFullIndexTool(project_root).execute({"mode": "full"})


@pytest.mark.asyncio
async def test_published_index_missing_only_optional_grammars_is_a_success(
    project_root, monkeypatch
):
    (Path(project_root) / "src" / "greet.swift").write_text(
        'func greet() -> String { return "hi" }\n', encoding="utf-8"
    )
    _without_swift_grammar(monkeypatch)
    result = await _full_index(project_root)

    assert result["published"] is True
    assert result["success"] is True
    assert result["verdict"] == "WARN"
    assert result["agent_summary"]["verdict"] == "WARN"
    assert result["completeness"] == "incomplete"
    assert result["scope_complete"] is False
    assert "error" not in result
    assert "error_type" not in result
    assert result["skipped_files"] == [
        {
            "file": "src/greet.swift",
            "reason": (
                "Swift grammar not installed — pip install "
                '"tree-sitter-analyzer[swift]"'
            ),
        }
    ]
    assert result["skipped_files_total"] == 1


@pytest.mark.asyncio
async def test_unpublished_run_returns_a_typed_error(project_root, monkeypatch):
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    def failing_phase(self, *args, **kwargs):
        return {"status": "error", "error": "RuntimeError: boom", "processed": 0}

    monkeypatch.setattr(CodeGraphFullIndexTool, "_phase_ast_cache", failing_phase)
    result = await _full_index(project_root)

    assert result["published"] is False
    assert result["success"] is False
    assert result["verdict"] == "ERROR"
    assert result["agent_summary"]["verdict"] == "ERROR"
    assert result["error_code"] == "INDEX_RUN_FAILED"
    assert result["error_type"] == "index_not_published"
    assert result["error"] == (
        "index not published: INDEX_RUN_FAILED (phase ast_cache: RuntimeError: boom)"
    )
    assert result["next_step"].startswith("Nothing was published")
    assert result["agent_summary"]["next_step"] == result["next_step"]


@pytest.mark.asyncio
async def test_aborted_snapshot_handoff_reuses_the_admission_code(
    project_root, monkeypatch
):
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization
    from tree_sitter_analyzer.cache.admission import ADMISSION_CODES

    monkeypatch.setattr(
        materialization,
        "index_candidate_cache_hierarchy_is_current",
        lambda *args, **kwargs: False,
    )
    result = await _full_index(project_root)

    assert (result["success"], result["published"], result["verdict"]) == (
        False,
        False,
        "ERROR",
    )
    assert result["error_code"] == "INDEX_CANDIDATE_SUPERSEDED"
    assert result["cause_code"] == "INDEX_CACHE_HIERARCHY_CHANGED"
    assert result["retryable"] is True
    assert result["next_step"] == ADMISSION_CODES["INDEX_CANDIDATE_SUPERSEDED"].next_step
    assert "INDEX_CACHE_HIERARCHY_CHANGED" in result["error"]


def test_error_envelope_keeps_the_tools_own_next_step():
    response = {
        "success": False,
        "verdict": "ERROR",
        "error": "Candidate discovery failed: INDEX_GENERATION_SOURCE_HASH_BUDGET_EXCEEDED",
        "error_code": "INDEX_GENERATION_SOURCE_HASH_BUDGET_EXCEEDED",
        "error_type": "index_not_published",
        "next_step": "Nothing was published: retry the same index call.",
    }
    shaped = ensure_canonical_error_envelope("index", response, arguments={"mode": "full"})

    assert shaped["agent_summary"]["next_step"] == (
        "Nothing was published: retry the same index call."
    )
    assert shaped["recovery_hint"] == "Nothing was published: retry the same index call."
    assert shaped["error_type"] == "index_not_published"
    assert "internal" not in shaped["summary_line"]
