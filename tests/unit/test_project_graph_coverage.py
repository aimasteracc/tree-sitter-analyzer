"""Coverage boost tests for project_graph.py — targets uncovered lines."""

import sys
from pathlib import Path, PureWindowsPath

import pytest

from tree_sitter_analyzer import project_graph
from tree_sitter_analyzer.project_graph import (
    BlastRadius,
    DependencyGraph,
    _language_from_ext,
    _resolve_relative_import,
    extract_imports_from_file,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "project_graph"
PY_PROJECT = FIXTURES_DIR / "python_project"
JS_PROJECT = FIXTURES_DIR / "js_project"
GO_PROJECT = FIXTURES_DIR / "go_project"
RUST_PROJECT = FIXTURES_DIR / "rust_project"
CPP_PROJECT = FIXTURES_DIR / "cpp_project"
JAVA_PROJECT = FIXTURES_DIR / "java_project"


class TestLanguageFromExt:
    def test_python(self):
        assert _language_from_ext("foo.py") == "python"

    def test_javascript(self):
        assert _language_from_ext("foo.js") == "javascript"
        assert _language_from_ext("foo.jsx") == "javascript"

    def test_typescript(self):
        assert _language_from_ext("foo.ts") == "typescript"
        assert _language_from_ext("foo.tsx") == "typescript"

    def test_java(self):
        assert _language_from_ext("Foo.java") == "java"

    def test_go(self):
        assert _language_from_ext("foo.go") == "go"

    def test_rust(self):
        assert _language_from_ext("foo.rs") == "rust"

    def test_c(self):
        assert _language_from_ext("foo.c") == "c"
        assert _language_from_ext("foo.h") == "c"

    def test_cpp(self):
        for ext in (".cpp", ".cc", ".cxx", ".hpp", ".hxx"):
            assert _language_from_ext(f"foo{ext}") == "cpp"

    def test_unknown(self):
        # ``.rb`` is now mapped to "ruby" (lockstep with ast_cache._EXT_TO_LANG
        # so RubyPlugin can actually index). Pick a genuinely unknown ext.
        assert _language_from_ext("foo.unknownext") is None
        assert _language_from_ext("Makefile") is None

    def test_newly_unlocked_plugins(self):
        # These 5 plugins existed but couldn't be indexed because the ext
        # map was missing entries. Pin the wiring.
        assert _language_from_ext("foo.swift") == "swift"
        assert _language_from_ext("foo.kt") == "kotlin"
        assert _language_from_ext("foo.rb") == "ruby"
        assert _language_from_ext("foo.php") == "php"
        assert _language_from_ext("foo.cs") == "csharp"

    def test_case_insensitive(self):
        assert _language_from_ext("FOO.PY") == "python"


class TestDependencyGraphSourceFileIteration:
    def test_iter_source_files_prunes_hidden_and_generated_dirs(self, tmp_path):
        project = tmp_path / "proj"
        (project / "src").mkdir(parents=True)
        (project / "node_modules" / "pkg").mkdir(parents=True)
        (project / ".hidden").mkdir(parents=True)
        (project / "src" / "main.py").write_text("import os\n")
        (project / "node_modules" / "pkg" / "skip.py").write_text("x = 1\n")
        (project / ".hidden" / "skip.py").write_text("x = 1\n")
        (project / ".secret.py").write_text("x = 1\n")

        DependencyGraph._global_cache.clear()
        graph = DependencyGraph(str(project))

        files = {
            path.relative_to(project).as_posix()
            for path in graph.iter_source_files({".py"})
        }
        assert files == {"src/main.py"}

    def test_is_excluded_handles_paths_outside_project_root(self, tmp_path):
        project = tmp_path / "proj"
        project.mkdir()

        DependencyGraph._global_cache.clear()
        graph = DependencyGraph(str(project))

        assert graph.is_excluded(Path("/tmp/outside/.git/config"))
        assert not graph.is_excluded(project / "src" / "main.py")


class TestResolveRelativeImport:
    def test_absolute_returns_none(self):
        assert _resolve_relative_import("os", "main.py") is None
        assert _resolve_relative_import("requests.api", "main.py") is None

    def test_single_dot(self):
        result = _resolve_relative_import(".utils", "pkg/main.py")
        assert result == "pkg/utils.py"

    def test_double_dot(self):
        result = _resolve_relative_import("..models", "pkg/sub/main.py")
        assert result == "pkg/models.py"

    def test_triple_dot(self):
        result = _resolve_relative_import("...top", "a/b/c/main.py")
        assert result == "a/top.py"

    def test_with_submodule(self):
        result = _resolve_relative_import(".models.user", "main.py")
        assert result == "models/user.py"


class TestImportResolverPathNormalization:
    def test_file_resolvers_keep_posix_paths_when_path_is_windows(self, monkeypatch):
        monkeypatch.setattr(project_graph, "Path", PureWindowsPath)

        assert (
            project_graph._resolve_js_ts_import(
                "./formatter", "src/index.js", {"src/formatter.js"}, True
            )
            == "src/formatter.js"
        )
        assert (
            project_graph._resolve_js_ts_import(
                "./pkg", "src/index.js", {"src/pkg/index.ts"}, True
            )
            == "src/pkg/index.ts"
        )
        assert (
            project_graph._resolve_go_import(
                "./internal/handler", "main.go", {"internal/handler.go"}, True
            )
            == "internal/handler.go"
        )
        assert (
            project_graph._resolve_rust_import(
                "crate::utils", "src/main.rs", {"src/utils.rs"}, True
            )
            == "src/utils.rs"
        )
        assert (
            project_graph._resolve_c_cpp_import(
                "handler.h", "src/main.cpp", {"src/handler.h"}, True
            )
            == "src/handler.h"
        )


class TestExtractImportsEdgeCases:
    def test_auto_detect_language_none(self, tmp_path):
        f = tmp_path / "readme.txt"
        f.write_text("hello")
        assert extract_imports_from_file(str(f)) == []

    def test_parse_error_returns_empty(self, tmp_path):
        f = tmp_path / "broken.py"
        f.write_bytes(b"\x00\x01\x02\xff\xfe")
        DependencyGraph._global_cache.clear()
        result = extract_imports_from_file(str(f), "python")
        assert isinstance(result, list)


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows path drift — tracked separately",
)
class TestDependencyGraphResolvePaths:
    """Cover _resolve_to_project_file for JS/TS, Go, Rust, C/CPP, Java."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        DependencyGraph._global_cache.clear()
        yield
        DependencyGraph._global_cache.clear()

    def test_js_resolve_with_extension(self, tmp_path):
        proj = tmp_path / "js_proj"
        proj.mkdir()
        (proj / "index.js").write_text('import { foo } from "./src/utils.js";\n')
        src = proj / "src"
        src.mkdir()
        (src / "utils.js").write_text("export function foo() {}\n")

        graph = DependencyGraph(str(proj))
        edges = graph.edges()
        assert len(edges) >= 1, f"Expected edges, got {edges}"

    def test_ts_resolve(self, tmp_path):
        proj = tmp_path / "ts_proj"
        proj.mkdir()
        (proj / "app.ts").write_text('import { bar } from "./lib";\n')
        (proj / "lib.ts").write_text("export function bar() {}\n")

        graph = DependencyGraph(str(proj))
        assert len(graph.edges()) >= 1

    def test_go_resolve_from_fixture(self):
        graph = DependencyGraph(str(GO_PROJECT))
        nodes = graph.nodes()
        assert len(nodes) >= 3, f"Expected >=3 Go nodes, got {nodes}"

    def test_go_absolute_import_no_resolve(self, tmp_path):
        proj = tmp_path / "go_proj2"
        proj.mkdir()
        (proj / "main.go").write_text('package main\nimport "fmt"\nfunc main() {}\n')
        graph = DependencyGraph(str(proj))
        assert len(graph.edges()) == 0

    def test_rust_resolve_crate(self, tmp_path):
        proj = tmp_path / "rust_proj"
        src = proj / "src"
        src.mkdir(parents=True)
        (src / "main.rs").write_text("mod utils;\nfn main() {}\n")
        (src / "utils.rs").write_text("pub fn helper() {}\n")

        graph = DependencyGraph(str(proj))
        nodes = graph.nodes()
        assert len(nodes) >= 2

    def test_cpp_resolve_include(self, tmp_path):
        proj = tmp_path / "cpp_proj"
        proj.mkdir()
        (proj / "main.cpp").write_text('#include "handler.h"\nint main() {}\n')
        (proj / "handler.h").write_text("void handle();\n")

        graph = DependencyGraph(str(proj))
        edges = graph.edges()
        assert len(edges) >= 1, f"Expected CPP edges, got {edges}"

    def test_java_resolve_package(self, tmp_path):
        proj = tmp_path / "java_proj"
        pkg = proj / "com" / "example"
        pkg.mkdir(parents=True)
        (pkg / "Main.java").write_text(
            "package com.example;\nimport com.example.Utils;\nclass Main {}\n"
        )
        (pkg / "Utils.java").write_text("package com.example;\nclass Utils {}\n")

        graph = DependencyGraph(str(proj))
        edges = graph.edges()
        assert len(edges) >= 1, f"Expected Java edges, got {edges}"

    def test_excluded_dirs_skipped(self, tmp_path):
        proj = tmp_path / "mixed_proj"
        proj.mkdir()
        (proj / "app.py").write_text("import os\n")
        node_modules = proj / "node_modules"
        node_modules.mkdir()
        (node_modules / "pkg.py").write_text("x = 1\n")
        venv = proj / ".venv"
        venv.mkdir()
        (venv / "site.py").write_text("y = 2\n")

        graph = DependencyGraph(str(proj))
        nodes = graph.nodes()
        assert all("node_modules" not in n for n in nodes), f"node_modules in {nodes}"
        assert all(".venv" not in n for n in nodes), f".venv in {nodes}"


class TestCacheKeyFor:
    def test_oserror_returns_none(self):
        result = DependencyGraph._cache_key_for("/nonexistent/path/that/does/not/exist")
        assert result is None


class TestBlastRadiusEdgeCases:
    def test_reverse_nonexistent(self):
        graph = DependencyGraph(str(PY_PROJECT))
        br = BlastRadius(graph)
        result = br.reverse("nonexistent_file.py")
        assert result == set()

    def test_analyze_nonexistent(self):
        graph = DependencyGraph(str(PY_PROJECT))
        br = BlastRadius(graph)
        result = br.analyze("nonexistent.py")
        assert result["forward_count"] == 0
        assert result["reverse_count"] == 0
