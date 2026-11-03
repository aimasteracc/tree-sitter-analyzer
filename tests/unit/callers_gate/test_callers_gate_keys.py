"""Cache keys of the callers gate: a code change that can shape the index must miss."""

from __future__ import annotations

import pytest

from benchmarks.callers_gate import keys

BLOBS = {
    "__init__.py": "a" * 40,
    "cache/indexer.py": "b" * 40,
    "queries/java.scm": "c" * 40,
    "mcp/tools/callers_tool.py": "d" * 40,
    "mcp/tools/callers_java_overrides.py": "e" * 40,
}


def _key(**over: object) -> str:
    args: dict[str, object] = {
        "repo": "gson",
        "repo_sha": "1" * 40,
        "package_blobs": BLOBS,
        "pyproject_blob": "f" * 40,
        "env_fingerprint": "env1",
    }
    args.update(over)
    return keys.index_key(**args)  # type: ignore[arg-type]


def test_index_key_is_stable_for_equal_inputs() -> None:
    assert _key() == _key()
    assert len(_key()) == 24


@pytest.mark.parametrize(
    "path",
    ["cache/indexer.py", "queries/java.scm", "__init__.py"],
)
def test_editing_any_indexed_file_misses(path: str) -> None:
    changed = {**BLOBS, path: "9" * 40}
    assert _key(package_blobs=changed) != _key()


def test_adding_or_removing_an_indexed_file_misses() -> None:
    assert _key(package_blobs={**BLOBS, "cache/new_module.py": "7" * 40}) != _key()
    without = {k: v for k, v in BLOBS.items() if k != "cache/indexer.py"}
    assert _key(package_blobs=without) != _key()


def test_query_only_callers_modules_do_not_change_the_index_key() -> None:
    changed = {
        **BLOBS,
        "mcp/tools/callers_tool.py": "0" * 40,
        "mcp/tools/callers_new.py": "8" * 40,
    }
    assert _key(package_blobs=changed) == _key()


def test_a_callers_named_module_outside_mcp_tools_is_not_excluded() -> None:
    changed = {**BLOBS, "cache/callers_index.py": "8" * 40}
    assert _key(package_blobs=changed) != _key()


@pytest.mark.parametrize(
    "field,value",
    [
        ("repo", "rich"),
        ("repo_sha", "2" * 40),
        ("pyproject_blob", None),
        ("env_fingerprint", "env2"),
    ],
)
def test_every_other_input_changes_the_key(field: str, value: object) -> None:
    assert _key(**{field: value}) != _key()


def test_an_empty_package_is_refused() -> None:
    with pytest.raises(ValueError, match="empty package tree"):
        keys.index_key(
            repo="gson",
            repo_sha="1" * 40,
            package_blobs={},
            pyproject_blob=None,
            env_fingerprint="e",
        )


def test_query_only_modules_lists_the_excluded_python_modules() -> None:
    assert keys.query_only_modules(BLOBS) == [
        "tree_sitter_analyzer.mcp.tools.callers_java_overrides",
        "tree_sitter_analyzer.mcp.tools.callers_tool",
    ]


def test_env_fingerprint_ignores_only_the_analyzer_distribution() -> None:
    base = keys.env_fingerprint(
        "3.12.9", ["tree-sitter==0.26.0", "tree_sitter_analyzer==2.2.0"], {"A": "1"}
    )
    same = keys.env_fingerprint(
        "3.12.9", ["tree-sitter==0.26.0", "tree-sitter-analyzer==9.9.9"], {"A": "1"}
    )
    assert base == same
    assert keys.env_fingerprint("3.12.9", ["tree-sitter==0.26.1"], {"A": "1"}) != base
    assert keys.env_fingerprint("3.13.0", ["tree-sitter==0.26.0"], {"A": "1"}) != base
    assert keys.env_fingerprint("3.12.9", ["tree-sitter==0.26.0"], {"A": "2"}) != base


def test_query_key_depends_on_the_target_list() -> None:
    assert keys.query_key(targets_sha256="x") != keys.query_key(targets_sha256="y")
