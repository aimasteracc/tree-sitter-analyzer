"""MCP cold start (#1675): tools/list without the registry, one facade per call."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp import tool_definition_cache as cache
from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer

# These tests build the real 8-facade registry (about 100 inner tools) on
# purpose: the property under test is what tools/list and tools/call avoid
# building. That is several seconds on a loaded Windows runner.
pytestmark = pytest.mark.slow_ok


@pytest.fixture
def definition_cache(tmp_path, monkeypatch):
    directory = tmp_path / "tool-definition-cache"
    monkeypatch.setenv(cache.CACHE_DIR_ENV, str(directory))
    return directory


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    return str(root)


def _live_definitions(project_root: str) -> list[dict]:
    server = TreeSitterAnalyzerMCPServer(project_root)
    return [tool.get_tool_definition() for _, tool in server.tool_instances]


def test_cache_hit_serves_identical_definitions_without_building_tools(
    definition_cache, project
):
    first = TreeSitterAnalyzerMCPServer(project)
    built = first.tool_definitions()
    assert first._registry_built is True
    assert len(list(definition_cache.glob("tool-definitions-*.json"))) == 1

    second = TreeSitterAnalyzerMCPServer(project)
    served = second.tool_definitions()

    assert second._registry_built is False
    assert second._facades == {}
    assert json.dumps(served) == json.dumps(built)
    assert json.dumps(served) == json.dumps(_live_definitions(project))


def test_cache_disabled_builds_live(monkeypatch, project):
    monkeypatch.setenv(cache.CACHE_DIR_ENV, "off")
    server = TreeSitterAnalyzerMCPServer(project)
    assert json.dumps(server.tool_definitions()) == json.dumps(
        _live_definitions(project)
    )
    assert server._registry_built is True


def test_corrupt_or_foreign_cache_file_is_rebuilt(definition_cache, project):
    fingerprint = cache.source_fingerprint()
    definition_cache.mkdir(parents=True)
    target = definition_cache / f"tool-definitions-{fingerprint}.json"
    for payload in ("{not json", json.dumps({"fingerprint": "other"})):
        target.write_text(payload, encoding="utf-8")
        server = TreeSitterAnalyzerMCPServer(project)
        assert json.dumps(server.tool_definitions()) == json.dumps(
            _live_definitions(project)
        )
        assert server._registry_built is True
        stored = json.loads(target.read_text(encoding="utf-8"))
        assert stored["fingerprint"] == fingerprint


def test_fingerprint_tracks_source_size_mtime_and_files(tmp_path):
    package = tmp_path / "pkg"
    (package / "sub").mkdir(parents=True)
    module = package / "sub" / "mod.py"
    module.write_text("A = 1\n", encoding="utf-8")
    (package / "notes.txt").write_text("ignored", encoding="utf-8")
    base = cache.source_fingerprint(package)
    assert cache.source_fingerprint(package) == base

    (package / "notes.txt").write_text("still ignored", encoding="utf-8")
    assert cache.source_fingerprint(package) == base

    module.write_text("A = 22\n", encoding="utf-8")
    changed_size = cache.source_fingerprint(package)
    assert changed_size != base

    info = module.stat()
    os.utime(module, ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000_000))
    assert cache.source_fingerprint(package) != changed_size

    (package / "new.py").write_text("", encoding="utf-8")
    assert cache.source_fingerprint(package) not in {base, changed_size}


def test_prune_keeps_only_recent_cache_files(definition_cache):
    definition_cache.mkdir(parents=True)
    for index in range(cache._KEEP + 3):
        path = definition_cache / f"tool-definitions-{index:040x}.json"
        path.write_text("{}", encoding="utf-8")
        os.utime(path, ns=(index * 10**9, index * 10**9))
    cache.store("f" * 40, json.dumps([]))
    remaining = sorted(p.name for p in definition_cache.glob("tool-definitions-*.json"))
    assert len(remaining) == cache._KEEP
    assert f"tool-definitions-{'f' * 40}.json" in remaining


def test_first_call_builds_only_the_called_facade(project):
    server = TreeSitterAnalyzerMCPServer(project)
    nav = server.facade("nav")

    assert nav is not None
    assert set(server._facades) == {"nav"}
    assert server._registry_built is False
    assert server.facade("nav") is nav
    assert server.facade("not-a-facade") is None
    # The full registry, when it is needed later, reuses the same instance.
    assert server.tools["nav"] is nav
    assert [name for name, _ in server.tool_instances] == [
        "search",
        "nav",
        "structure",
        "health",
        "edit",
        "project",
        "index",
        "viz",
    ]


@pytest.mark.asyncio
async def test_call_tool_dispatches_through_the_single_facade(project):
    server = TreeSitterAnalyzerMCPServer(project)
    result = await server.call_tool("nav", {"action": "help"})

    assert isinstance(result, dict)
    assert set(server._facades) == {"nav"}
    assert server._registry_built is False


def test_cache_dir_defaults_under_home(monkeypatch, tmp_path):
    monkeypatch.delenv(cache.CACHE_DIR_ENV, raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert cache.cache_dir() == tmp_path / ".tsa" / "cache"
