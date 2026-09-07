"""Issue #1376：test_benchmark_harness_source_manifest 行为模块；保留测试语义，文档中文化，编码变更单独核验。"""

from __future__ import annotations

import json
import os as os
import sys
from functools import partial
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.unit._benchmark_harness_platform import (
    mark_posix_qualification_section_tests,
)

_POSIX_QUALIFICATION_SECTION_START = sys._getframe().f_lineno
_mark_posix_qualification_section_tests = partial(
    mark_posix_qualification_section_tests, globals()
)


def test_seven_repo_inventory_lists_exactly_the_canonical_repositories() -> None:
    from benchmarks.codegraph_compare.setup_qualification_inventory import (
        load_seven_repo_inventory,
    )
    from benchmarks.codegraph_compare.setup_qualification_plan import REPOSITORIES

    payload = load_seven_repo_inventory()
    assert [entry["repo_id"] for entry in payload["repositories"]] == list(REPOSITORIES)


def test_seven_repo_inventory_commit_pins_match_repos_yaml() -> None:
    import yaml

    from benchmarks.codegraph_compare.run import REPOS_YAML
    from benchmarks.codegraph_compare.setup_qualification_inventory import (
        load_seven_repo_inventory,
    )

    payload = load_seven_repo_inventory()
    registry = yaml.safe_load(REPOS_YAML.read_text(encoding="utf-8"))
    # Codex P2 (#1260): 比较精确映射中的每个共享字段，
    # 覆盖全部七项，因此 name、language、url、approx_files 的漂移，或
    # 仓库被删除时也要让一致性测试变红，而不只检查固定提交值。
    pinned = {
        entry["repo_id"]: {
            "commit": entry["commit"],
            "name": entry["name"],
            "language": entry["language"],
            "url": entry["url"],
            "approx_files": entry["approx_files"],
        }
        for entry in payload["repositories"]
    }
    assert len(pinned) == 7
    yaml_repos = registry["repos"]
    assert len(yaml_repos) == 7
    for repo in yaml_repos:
        expected = {
            "commit": repo["commit"],
            "name": repo["name"],
            "language": repo["language"],
            "url": repo["url"],
            "approx_files": repo["approx_files"],
        }
        assert pinned[repo["id"]] == expected, repo["id"]


def test_seven_repo_inventory_extensions_match_default_source_rules() -> None:
    from benchmarks.codegraph_compare.setup_qualification_inventory import (
        load_seven_repo_inventory,
    )
    from benchmarks.codegraph_compare.setup_qualification_plan import (
        DEFAULT_SOURCE_RULES,
    )

    payload = load_seven_repo_inventory()
    for entry in payload["repositories"]:
        assert entry["source_extensions"] == list(
            DEFAULT_SOURCE_RULES.extensions(entry["repo_id"])
        ), entry["repo_id"]


def test_seven_repo_inventory_rejects_bad_commit_pin() -> None:
    from benchmarks.codegraph_compare.setup_qualification_inventory import (
        SEVEN_REPO_INVENTORY_PATH,
        _validate_inventory_entry,
    )

    payload = json.loads(SEVEN_REPO_INVENTORY_PATH.read_text(encoding="utf-8"))
    entry = dict(payload["repositories"][0])
    entry["commit"] = entry["commit"][:-1]  # 仅 39 位十六进制字符：无效的固定提交值。
    with pytest.raises(ValueError, match="bad commit pin"):
        _validate_inventory_entry(entry, 0)


def test_seven_repo_inventory_rejects_unsorted_extensions() -> None:
    from benchmarks.codegraph_compare.setup_qualification_inventory import (
        SEVEN_REPO_INVENTORY_PATH,
        _validate_inventory_entry,
    )

    payload = json.loads(SEVEN_REPO_INVENTORY_PATH.read_text(encoding="utf-8"))
    entry = dict(payload["repositories"][0])
    entry["source_extensions"] = [".tsx", ".ts"]
    with pytest.raises(ValueError, match="not sorted unique"):
        _validate_inventory_entry(entry, 0)


def test_seven_repo_inventory_rejects_duplicate_repo_id(tmp_path: Path) -> None:
    from benchmarks.codegraph_compare.setup_qualification_inventory import (
        SEVEN_REPO_INVENTORY_PATH,
        load_seven_repo_inventory,
    )

    payload = json.loads(SEVEN_REPO_INVENTORY_PATH.read_text(encoding="utf-8"))
    payload["repositories"][6] = dict(payload["repositories"][0])
    broken = tmp_path / "broken-inventory.json"
    broken.write_text(json.dumps(payload), encoding="utf-8")
    with patch(
        "benchmarks.codegraph_compare.setup_qualification_inventory"
        ".SEVEN_REPO_INVENTORY_PATH",
        broken,
    ):
        with pytest.raises(ValueError, match="duplicates repo_id"):
            load_seven_repo_inventory()


def test_seven_repo_inventory_schema_rejects_wrong_repository_count(
    tmp_path: Path,
) -> None:
    from benchmarks.codegraph_compare.setup_qualification_inventory import (
        SEVEN_REPO_INVENTORY_PATH,
        load_seven_repo_inventory,
    )

    payload = json.loads(SEVEN_REPO_INVENTORY_PATH.read_text(encoding="utf-8"))
    del payload["repositories"][-1]
    broken = tmp_path / "broken-inventory.json"
    broken.write_text(json.dumps(payload), encoding="utf-8")
    with patch(
        "benchmarks.codegraph_compare.setup_qualification_inventory"
        ".SEVEN_REPO_INVENTORY_PATH",
        broken,
    ):
        with pytest.raises(ValueError, match="violates its schema"):
            load_seven_repo_inventory()


def test_seven_repo_inventory_rejects_duplicate_json_members(
    tmp_path: Path,
) -> None:
    # Codex P2 (#1260): 重复成员（例如两个 commit 键）必须
    # 在解析前拒绝；json.loads 会静默保留最后一个值，
    # 否则 schema 只会验证折叠后的对象。

    from benchmarks.codegraph_compare.setup_qualification_inventory import (
        SEVEN_REPO_INVENTORY_PATH,
        load_seven_repo_inventory,
    )

    payload = json.loads(SEVEN_REPO_INVENTORY_PATH.read_text(encoding="utf-8"))
    first = payload["repositories"][0]
    duplicated = (
        "{"
        + '"repo_id": "gin", "commit": "'
        + first["commit"]
        + '", "commit": "'
        + first["commit"]
        + '", "name": "Gin", "language": "Go", "url": "https://github.com/gin-gonic/gin", "approx_files": 200, "source_extensions": [".go"]'
        + "}"
    )
    broken = tmp_path / "broken-duplicate.json"
    broken.write_text(
        '{"schema_version": 1, "repositories": ['
        + duplicated
        + ","
        + json.dumps(payload["repositories"][1:])[1:]
        + "}",
        encoding="utf-8",
    )
    with patch(
        "benchmarks.codegraph_compare.setup_qualification_inventory"
        ".SEVEN_REPO_INVENTORY_PATH",
        broken,
    ):
        with pytest.raises(ValueError, match="not strict JSON"):
            load_seven_repo_inventory()


_mark_posix_qualification_section_tests()
