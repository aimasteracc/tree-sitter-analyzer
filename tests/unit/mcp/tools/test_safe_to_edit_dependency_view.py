"""Tests for safe-to-edit's lightweight dependency view."""

from pathlib import Path

from tree_sitter_analyzer.mcp.tools.utils import safe_to_edit_helpers
from tree_sitter_analyzer.mcp.tools.utils.safe_to_edit_helpers import (
    FileDependencyView,
    _extract_import_specs,
    _iter_dependency_source_files,
    _resolve_import_spec,
    _target_dependencies,
    _target_dependents,
    build_file_dependency_view,
    safe_dependencies,
    safe_dependents,
)


def _write(root: Path, rel_path: str, body: str) -> Path:
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_file_dependency_view_sorts_edges_and_supports_suffix_lookup() -> None:
    view = FileDependencyView(
        rel_path="pkg/main.py",
        dependencies={"pkg/z.py", "pkg/a.py"},
        dependents={"tests/test_main.py", "app.py"},
    )

    assert safe_dependencies(view, "main.py") == ["pkg/a.py", "pkg/z.py"]
    assert safe_dependents(view, "pkg/main.py") == ["app.py", "tests/test_main.py"]


def test_safe_graph_lookup_tolerates_graph_exceptions() -> None:
    class BrokenGraph:
        _nodes = {"pkg/main.py"}

        def dependencies_of(self, _file_rel: str) -> list[str]:
            raise RuntimeError("stale graph")

    assert safe_dependencies(BrokenGraph(), "pkg/main.py") == []


def test_safe_graph_lookup_does_not_match_partial_basename_suffix() -> None:
    view = FileDependencyView(
        rel_path="pkg/main.py",
        dependencies={"pkg/dep.py"},
        dependents={"tests/test_main.py"},
    )

    assert safe_dependencies(view, "main.py") == ["pkg/dep.py"]
    assert safe_dependencies(view, "ain.py") == []


def test_build_file_dependency_view_finds_python_imports_and_importers(
    tmp_path: Path,
) -> None:
    target = _write(
        tmp_path,
        "pkg/main.py",
        "import pkg.util\nfrom pkg.service import Service\nfrom .local import value\n",
    )
    _write(tmp_path, "pkg/util.py", "VALUE = 1\n")
    _write(tmp_path, "pkg/service.py", "class Service: pass\n")
    _write(tmp_path, "pkg/local.py", "value = 1\n")
    _write(tmp_path, "app/caller.py", "from pkg.main import run\n")
    _write(tmp_path, "node_modules/ignored.py", "from pkg.main import run\n")
    _write(tmp_path, ".hidden/ignored.py", "from pkg.main import run\n")

    view = build_file_dependency_view(str(target), str(tmp_path))

    assert view.dependencies_of("pkg/main.py") == [
        "pkg/local.py",
        "pkg/service.py",
        "pkg/util.py",
    ]
    assert view.dependents_of("pkg/main.py") == ["app/caller.py"]


def test_build_file_dependency_view_finds_typescript_imports(tmp_path: Path) -> None:
    target = _write(
        tmp_path,
        "src/main.ts",
        "import { dep } from './dep';\nconst legacy = require('./legacy');\n",
    )
    _write(tmp_path, "src/dep.ts", "export const dep = 1;\n")
    _write(tmp_path, "src/legacy.ts", "export const legacy = 1;\n")

    view = build_file_dependency_view(str(target), str(tmp_path))

    assert view.dependencies_of("src/main.ts") == ["src/dep.ts", "src/legacy.ts"]


def test_build_file_dependency_view_finds_java_imports(tmp_path: Path) -> None:
    target = _write(
        tmp_path,
        "src/main/java/com/example/Main.java",
        "package com.example;\nimport com.example.Util;\n",
    )
    _write(tmp_path, "com/example/Util.java", "package com.example;\n")

    view = build_file_dependency_view(str(target), str(tmp_path))

    assert view.dependencies_of("src/main/java/com/example/Main.java") == [
        "com/example/Util.java"
    ]


def test_build_file_dependency_view_detects_package_init_importers(
    tmp_path: Path,
) -> None:
    target = _write(tmp_path, "pkg/__init__.py", "VALUE = 1\n")
    _write(tmp_path, "consumer.py", "import pkg\n")

    view = build_file_dependency_view(str(target), str(tmp_path))

    assert view.dependents_of("pkg/__init__.py") == ["consumer.py"]


def test_target_dependencies_returns_empty_for_unreadable_target(
    tmp_path: Path, monkeypatch
) -> None:
    target = _write(tmp_path, "pkg/main.py", "import pkg.dep\n")
    original_read_text = Path.read_text

    def flaky_read_text(path: Path, *args, **kwargs):
        if path == target:
            raise OSError("unreadable")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", flaky_read_text)

    assert _target_dependencies(target, "pkg/main.py", tmp_path) == set()


def test_target_dependents_skips_unreadable_importers(
    tmp_path: Path, monkeypatch
) -> None:
    target = _write(tmp_path, "pkg/main.py", "VALUE = 1\n")
    broken = _write(tmp_path, "app/broken.py", "from pkg.main import VALUE\n")
    _write(tmp_path, "app/good.py", "from pkg.main import VALUE\n")
    original_read_text = Path.read_text

    def flaky_read_text(path: Path, *args, **kwargs):
        if path == broken:
            raise OSError("unreadable")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", flaky_read_text)

    assert _target_dependents(target, "pkg/main.py", tmp_path) == {"app/good.py"}


def test_target_dependents_returns_empty_without_import_needles(
    tmp_path: Path, monkeypatch
) -> None:
    target = _write(tmp_path, "pkg/main.py", "VALUE = 1\n")
    _write(tmp_path, "app/caller.py", "from pkg.main import VALUE\n")
    monkeypatch.setattr(
        safe_to_edit_helpers,
        "_import_needles_for_target",
        lambda _rel_path: set(),
    )

    assert _target_dependents(target, "pkg/main.py", tmp_path) == set()


def test_iter_dependency_source_files_skips_hidden_files(tmp_path: Path) -> None:
    _write(tmp_path, "src/main.py", "x = 1\n")
    _write(tmp_path, "src/.hidden.py", "x = 1\n")
    _write(tmp_path, "src/readme.md", "# ignored\n")

    files = _iter_dependency_source_files(tmp_path)

    assert [path.name for path in files] == ["main.py"]


def test_import_spec_helpers_cover_unsupported_and_unresolved_cases(
    tmp_path: Path,
) -> None:
    assert _extract_import_specs("package main\n", ".go") == set()
    assert _resolve_import_spec("..parent", "pkg/main.py", tmp_path) is None
    assert _resolve_import_spec("missing.module", "pkg/main.py", tmp_path) is None
