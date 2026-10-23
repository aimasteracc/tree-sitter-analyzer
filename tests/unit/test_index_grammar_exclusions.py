"""index_grammar_exclusions：缺少可选语法文件的如实说明（#1581）。"""

from __future__ import annotations

import pytest

from tests.unit._ast_cache_helpers import without_grammar
from tree_sitter_analyzer import index_grammar_exclusions as exclusions_module
from tree_sitter_analyzer.index_grammar_exclusions import (
    GrammarExclusions,
    explain_incomplete,
    find_grammar_exclusions,
    missing_grammar_languages,
    with_exclusions,
)

_SWIFT_INSTALL = 'pip install "tree-sitter-analyzer[swift]"'
_SWIFT_REASON = f"Swift grammar not installed — {_SWIFT_INSTALL}"


@pytest.fixture
def all_grammars_installed(monkeypatch):
    monkeypatch.setattr(
        exclusions_module._core_parser, "is_grammar_installed", lambda language: True
    )


@pytest.fixture
def only_swift_missing(monkeypatch):
    monkeypatch.setattr(
        exclusions_module._core_parser,
        "is_grammar_installed",
        lambda language: language != "swift",
    )


def _write(root, name: str, text: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_missing_languages_follow_the_parser_predicate(only_swift_missing) -> None:
    # Issue #1581: 与解析器拒绝文件时使用同一谓词。
    assert missing_grammar_languages() == ("swift",)


def test_no_missing_grammar_skips_the_walk(
    all_grammars_installed, tmp_path, monkeypatch
) -> None:
    # Issue #1581: 语法齐全时不遍历目录，状态答复零额外开销。
    def no_walk(_root):
        raise AssertionError("must not walk")

    monkeypatch.setattr(exclusions_module, "_walk_source_files", no_walk)
    assert find_grammar_exclusions(str(tmp_path)) == GrammarExclusions((), ())


def test_exclusions_list_only_files_of_missing_languages(
    only_swift_missing, tmp_path
) -> None:
    _write(tmp_path, "a.py", "def a():\n    return 1\n")
    _write(tmp_path, "ios/b.swift", "func b() {}\n")
    assert find_grammar_exclusions(str(tmp_path)) == GrammarExclusions(
        (("ios/b.swift", "swift"),), (("swift", _SWIFT_REASON),)
    )


def test_exclusions_honour_default_corpus_excludes(
    only_swift_missing, tmp_path
) -> None:
    # Issue #1581: 默认排除的语料目录本就不在索引范围内，不能算作被排除的文件。
    _write(tmp_path, "tests/golden/corpus_swift/c.swift", "func c() {}\n")
    assert find_grammar_exclusions(str(tmp_path)) == GrammarExclusions((), ())


def test_walk_past_deadline_is_unknown(
    only_swift_missing, tmp_path, monkeypatch
) -> None:
    # Issue #1581: 超出遍历上界时如实返回未知，不给出不完整的名单。
    _write(tmp_path, "b.swift", "func b() {}\n")
    monkeypatch.setattr(exclusions_module, "_WALK_DEADLINE_SECONDS", -1.0)
    assert find_grammar_exclusions(str(tmp_path)) is None


def test_payload_caps_listed_files() -> None:
    files = tuple((f"f{i}.swift", "swift") for i in range(7))
    payload = GrammarExclusions(files, (("swift", _SWIFT_REASON),)).payload()
    assert [item["file"] for item in payload] == [f"f{i}.swift" for i in range(5)]


def test_next_step_counts_files_beyond_the_listed_ones() -> None:
    files = tuple((f"f{i}.swift", "swift") for i in range(7))
    step = GrammarExclusions(files, (("swift", _SWIFT_REASON),)).next_step()
    assert step.startswith(
        "The index stays partial because 7 file(s) need an optional grammar that "
        "is not installed (f0.swift, f1.swift, f2.swift, f3.swift, f4.swift, and 2 "
        "more). Re-running indexing without it reproduces the same partial index. "
        f"To certify the index: {_SWIFT_INSTALL}, then run index action=full."
    )


def test_explain_ignores_reasons_unrelated_to_exclusions(
    only_swift_missing, tmp_path
) -> None:
    # Issue #1581: 并发写入、源码过期等原因与缺失语法无关，保留原有提示。
    _write(tmp_path, "b.swift", "func b() {}\n")
    assert explain_incomplete(str(tmp_path), "CONCURRENT_WRITER") is None


def test_with_exclusions_returns_refusal_unchanged_without_exclusions(
    all_grammars_installed, tmp_path
) -> None:
    refusal = {"success": False, "source_evidence": {"reason": "CALL_GRAPH_INCOMPLETE"}}
    assert with_exclusions(refusal, str(tmp_path)) is refusal


@pytest.mark.asyncio
async def test_pulse_refusal_explains_the_excluded_file(tmp_path, monkeypatch) -> None:
    # Issue #1581: 索引因缺少语法停在 partial 时，Pulse 如实拒绝并写明安装什么。
    from tree_sitter_analyzer.mcp.tools.ast_cache_tool import ASTCacheTool
    from tree_sitter_analyzer.mcp.tools.pulse_tool import PulseTool

    _write(tmp_path, "a.py", "def leaf():\n    return 1\n")
    _write(tmp_path, "greet.swift", 'func greet() -> String { return "hi" }\n')
    without_grammar(monkeypatch, "swift")
    await ASTCacheTool(str(tmp_path)).execute({"mode": "index"})
    result = await PulseTool(str(tmp_path)).execute({"file": "a.py", "symbol": "leaf"})

    assert (
        result["error_code"],
        result["source_evidence"]["reason"],
        result["excluded_files"],
        result["next_step"],
    ) == (
        "SOURCE_EVIDENCE_UNAVAILABLE",
        "CALL_GRAPH_INCOMPLETE",
        [{"file": "greet.swift", "language": "swift", "reason": _SWIFT_REASON}],
        GrammarExclusions(
            (("greet.swift", "swift"),), (("swift", _SWIFT_REASON),)
        ).next_step(),
    )
