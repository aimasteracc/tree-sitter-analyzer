#!/usr/bin/env python3
"""Tests for CrossFileResolver — import-aware cross-file call edge resolution."""

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.cross_file_resolver import (
    CrossFileResolver,
    FunctionDef,
    ImportEntry,
    ResolvedEdge,
)


@pytest.fixture
def multi_file_project(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()

    (project / "services.py").write_text(
        "from models import User\n"
        "from utils import format_user, validate_input\n"
        "\n"
        "class UserService:\n"
        "    def get_user(self, user_id):\n"
        "        user = self._find_user(user_id)\n"
        "        return format_user(user)\n"
        "\n"
        "    def _find_user(self, user_id):\n"
        "        return User(user_id)\n"
        "\n"
        "def handle_request(request):\n"
        "    svc = UserService()\n"
        "    user = svc.get_user(1)\n"
        "    return user\n"
    )

    (project / "utils.py").write_text(
        "def format_user(user):\n"
        "    return str(user)\n"
        "\n"
        "def validate_input(data):\n"
        "    return bool(data)\n"
    )

    (project / "models.py").write_text(
        "class User:\n"
        "    def __init__(self, name):\n"
        "        self.name = name\n"
        "\n"
        "    def display(self):\n"
        "        return self.name\n"
    )

    (project / "main.py").write_text(
        "from services import handle_request\n"
        "\n"
        "def main():\n"
        "    result = handle_request({})\n"
        "    print(result)\n"
    )

    cache = ASTCache(str(project))
    cache.index_project(max_files=100)
    yield project, cache
    cache.close()


class TestCrossFileResolverBuild:
    def test_build_does_not_crash(self, multi_file_project):
        _project, cache = multi_file_project
        resolver = CrossFileResolver(cache)
        resolver.build()

    def test_module_map_populated(self, multi_file_project):
        _project, cache = multi_file_project
        resolver = CrossFileResolver(cache)
        resolver.build()
        assert "models" in resolver._module_to_file
        assert "utils" in resolver._module_to_file
        assert "services" in resolver._module_to_file

    def test_function_index_populated(self, multi_file_project):
        _project, cache = multi_file_project
        resolver = CrossFileResolver(cache)
        resolver.build()
        assert "format_user" in resolver._functions_by_name
        assert "handle_request" in resolver._functions_by_name
        assert len(resolver._functions_by_name["format_user"]) == 1

    def test_import_index_populated(self, multi_file_project):
        _project, cache = multi_file_project
        resolver = CrossFileResolver(cache)
        resolver.build()
        assert "services.py" in resolver._imports_by_file
        svc_imports = resolver._imports_by_file["services.py"]
        mod_paths = [e.module_path for e in svc_imports]
        assert "models" in mod_paths
        assert "utils" in mod_paths


@pytest.fixture
def mts_project(tmp_path):
    """A real indexed project whose .mts entry imports an extensionless sibling."""
    project = tmp_path / "mtsproj"
    project.mkdir()
    (project / "src").mkdir()

    (project / "src" / "util.mts").write_text(
        "export function run(value: number): number {\n    return value + 1;\n}\n"
    )
    (project / "src" / "app.mts").write_text(
        "import { run } from './util';\n"
        "\n"
        "export function main(): number {\n"
        "    return run(1);\n"
        "}\n"
    )

    cache = ASTCache(str(project))
    cache.index_project(max_files=100)
    yield project, cache
    cache.close()


class TestNodeModuleCrossFileResolution:
    """PUBLIC API: an ESM import in a .mts file must bind across files.

    Regression for the Codex finding on #1312: ``_register_module_path``
    registered ``src/util.mts`` correctly, but the LOOKUP in
    ``_resolve_module_to_file`` probed only ``("", ".py", ".js", ".ts",
    "/__init__.py")`` — so the relative ``./util`` never matched and the
    binding was dropped. Registration worked; resolution did not.
    """

    def test_esm_relative_import_binds_to_mts_sibling(self, mts_project):
        _project, cache = mts_project
        resolver = CrossFileResolver(cache)
        resolver.build()
        assert resolver._name_to_source["src/app.mts"]["run"] == "src/util.mts"

    def test_resolve_callee_finds_cross_file_mts_definition(self, mts_project):
        _project, cache = mts_project
        resolver = CrossFileResolver(cache)
        resolver.build()
        files = [
            path for path, _confidence in resolver.resolve_callee("run", "src/app.mts")
        ]
        assert "src/util.mts" in files


class TestRegisterNodeModulePaths:
    """``_register_module_path`` must strip the full Node module suffix.

    ``"src/util.mts".endswith(".ts")`` is True, so a probe table that lists
    ``.ts`` before ``.mts`` mangles the module name into ``src.util.m`` and
    every ``./util`` import against it fails to resolve.
    """

    @staticmethod
    def _register(fp: str, language: str) -> dict[str, str]:
        resolver = CrossFileResolver(None)
        resolver._register_module_path(fp, language)
        return resolver._module_to_file

    def test_mts_dotted_module_name(self):
        assert (
            self._register("src/util.mts", "typescript")["src.util"] == "src/util.mts"
        )

    def test_mts_short_module_name(self):
        assert self._register("src/util.mts", "typescript")["util"] == "src/util.mts"

    def test_cts_dotted_module_name(self):
        assert (
            self._register("src/util.cts", "typescript")["src.util"] == "src/util.cts"
        )

    def test_mjs_dotted_module_name(self):
        assert (
            self._register("src/util.mjs", "javascript")["src.util"] == "src/util.mjs"
        )

    def test_cjs_dotted_module_name(self):
        assert (
            self._register("src/util.cjs", "javascript")["src.util"] == "src/util.cjs"
        )


class TestCrossFileResolution:
    def test_resolve_same_file_callee(self, multi_file_project):
        _project, cache = multi_file_project
        resolver = CrossFileResolver(cache)
        resolver.build()
        results = resolver.resolve_callee("_find_user", "services.py")
        assert len(results) == 1
        assert any("services.py" in r[0] for r in results)
        assert results[0][1] == 1.0

    def test_resolve_imported_callee(self, multi_file_project):
        _project, cache = multi_file_project
        resolver = CrossFileResolver(cache)
        resolver.build()
        results = resolver.resolve_callee("format_user", "services.py")
        assert len(results) == 1
        assert any("utils.py" in r[0] for r in results)

    def test_resolve_callee_with_confidence(self, multi_file_project):
        _project, cache = multi_file_project
        resolver = CrossFileResolver(cache)
        resolver.build()
        results = resolver.resolve_callee("format_user", "services.py")
        assert len(results) == 1
        assert results[0][1] == 0.9

    def test_resolve_cross_file_via_import(self, multi_file_project):
        _project, cache = multi_file_project
        resolver = CrossFileResolver(cache)
        resolver.build()
        results = resolver.resolve_callee("handle_request", "main.py")
        assert len(results) == 1
        assert any("services.py" in r[0] for r in results)

    def test_find_caller_function(self, multi_file_project):
        _project, cache = multi_file_project
        resolver = CrossFileResolver(cache)
        resolver.build()
        name, line = resolver.find_caller_function(6, "services.py")
        assert name == "get_user"

    def test_find_caller_function_top_level(self, multi_file_project):
        _project, cache = multi_file_project
        resolver = CrossFileResolver(cache)
        resolver.build()
        name, line = resolver.find_caller_function(12, "services.py")
        assert name == "handle_request"

    def test_find_caller_function_past_end(self, multi_file_project):
        _project, cache = multi_file_project
        resolver = CrossFileResolver(cache)
        resolver.build()
        name, line = resolver.find_caller_function(999, "services.py")
        assert name == "handle_request"
        assert line == 12

    def test_find_caller_function_unknown_file(self, multi_file_project):
        _project, cache = multi_file_project
        resolver = CrossFileResolver(cache)
        resolver.build()
        name, line = resolver.find_caller_function(5, "nonexistent_file.py")
        assert name == ""


class TestResolveCallEdges:
    def test_resolve_edges_does_not_crash(self, multi_file_project):
        _project, cache = multi_file_project
        resolver = CrossFileResolver(cache)
        edges = resolver.resolve_call_edges()
        assert isinstance(edges, list)

    def test_resolved_edges_have_confidence(self, multi_file_project):
        _project, cache = multi_file_project
        resolver = CrossFileResolver(cache)
        edges = resolver.resolve_call_edges()
        for edge in edges:
            assert 0 < edge.confidence <= 1.0

    def test_resolved_edges_to_dict(self, multi_file_project):
        _project, cache = multi_file_project
        resolver = CrossFileResolver(cache)
        edges = resolver.resolve_call_edges()
        if edges:
            d = edges[0].to_dict()
            assert "caller_name" in d
            assert "callee_name" in d
            assert "confidence" in d


class TestASTCacheEnhancedQueries:
    def test_query_callers_enhanced(self, multi_file_project):
        _project, cache = multi_file_project
        callers = cache.query_callers_enhanced("format_user")
        assert isinstance(callers, list)
        for c in callers:
            if c.get("caller_name"):
                assert c["caller_name"] != ""

    def test_query_callees_enhanced(self, multi_file_project):
        _project, cache = multi_file_project
        callees = cache.query_callees_enhanced("get_user")
        assert isinstance(callees, list)
        for c in callees:
            assert "callee_name" in c

    def test_query_callers_enhanced_empty(self, multi_file_project):
        _project, cache = multi_file_project
        callers = cache.query_callers_enhanced("nonexistent_xyz")
        assert callers == []

    def test_get_cross_file_resolver(self, multi_file_project):
        _project, cache = multi_file_project
        resolver = cache.get_cross_file_resolver()
        assert resolver is not None
        resolver2 = cache.get_cross_file_resolver()
        assert resolver is resolver2


class TestDataclassSerialization:
    def test_import_entry_to_dict(self):
        entry = ImportEntry(
            source_file="app.py",
            module_path="models",
            imported_names=["User"],
            is_relative=False,
            language="python",
        )
        d = entry.to_dict()
        assert d["source_file"] == "app.py"
        assert d["module_path"] == "models"
        assert "User" in d["imported_names"]

    def test_function_def_key(self):
        func = FunctionDef(
            name="main",
            file="app.py",
            line=1,
            end_line=10,
            language="python",
        )
        assert func.key == "app.py:main:1"

    def test_resolved_edge_to_dict(self):
        edge = ResolvedEdge(
            caller_name="main",
            caller_file="app.py",
            caller_line=5,
            callee_name="handle",
            callee_file="svc.py",
            callee_line=10,
            callee_resolved_file="handlers.py",
            confidence=0.9,
        )
        d = edge.to_dict()
        assert d["caller_name"] == "main"
        assert d["callee_resolved_file"] == "handlers.py"
        assert d["confidence"] == 0.9
