"""Tests for C#, Go, and Kotlin edge extractors."""
from __future__ import annotations

from tree_sitter_analyzer.mcp.utils.edge_extractors import REGISTRY, get_extractor
from tree_sitter_analyzer.mcp.utils.edge_extractors.csharp import CSharpEdgeExtractor
from tree_sitter_analyzer.mcp.utils.edge_extractors.go import GoEdgeExtractor
from tree_sitter_analyzer.mcp.utils.edge_extractors.kotlin import KotlinEdgeExtractor

# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


class TestRegistry:
    """Edge extractor registry correctly maps extensions."""

    def test_cs_has_extractor(self) -> None:
        assert get_extractor(".cs") is not None

    def test_go_has_extractor(self) -> None:
        assert get_extractor(".go") is not None

    def test_kt_has_extractor(self) -> None:
        assert get_extractor(".kt") is not None

    def test_unknown_returns_none(self) -> None:
        assert get_extractor(".xyz") is None

    def test_registry_covers_all_six_languages(self) -> None:
        extensions = set(REGISTRY.keys())
        assert ".java" in extensions
        assert ".py" in extensions
        assert ".ts" in extensions
        assert ".cs" in extensions
        assert ".go" in extensions
        assert ".kt" in extensions


# ---------------------------------------------------------------------------
# C# extractor
# ---------------------------------------------------------------------------


class TestCSharpEdgeExtractor:
    """C# inheritance edge extraction."""

    def test_class_inheritance(self) -> None:
        src = (
            "using System;\n"
            "public class MyController : BaseController { }\n"
        )
        ext = CSharpEdgeExtractor()
        edges = ext.extract(src, "MyController.cs", "/project")
        assert ("MyController.cs", "BaseController") in edges

    def test_interface_implementation(self) -> None:
        src = (
            "public class UserService : IUserService, IRepository { }\n"
        )
        ext = CSharpEdgeExtractor()
        edges = ext.extract(src, "UserService.cs", "/project")
        assert ("UserService.cs", "IUserService") in edges
        assert ("UserService.cs", "IRepository") in edges

    def test_system_types_filtered(self) -> None:
        src = (
            "using System;\n"
            "public class MyList : List<string> { }\n"
        )
        ext = CSharpEdgeExtractor()
        edges = ext.extract(src, "MyList.cs", "/project")
        assert len(edges) == 0

    def test_interface_inheritance(self) -> None:
        src = "public interface IRepo : IBaseRepo { }\n"
        ext = CSharpEdgeExtractor()
        edges = ext.extract(src, "IRepo.cs", "/project")
        assert ("IRepo.cs", "IBaseRepo") in edges

    def test_record_inheritance(self) -> None:
        src = "public record Person(string Name) : BaseEntity { }\n"
        ext = CSharpEdgeExtractor()
        edges = ext.extract(src, "Person.cs", "/project")
        assert ("Person.cs", "BaseEntity") in edges

    def test_empty_source(self) -> None:
        ext = CSharpEdgeExtractor()
        edges = ext.extract("", "Empty.cs", "/project")
        assert edges == []


# ---------------------------------------------------------------------------
# Go extractor
# ---------------------------------------------------------------------------


class TestGoEdgeExtractor:
    """Go import-based edge extraction."""

    def test_single_import(self) -> None:
        src = (
            'package main\n\n'
            'import "github.com/myproject/mypackage"\n\n'
            'func main() { }\n'
        )
        ext = GoEdgeExtractor()
        edges = ext.extract(src, "main.go", "/project")
        assert ("main.go", "mypackage") in edges

    def test_stdlib_filtered(self) -> None:
        src = (
            'package main\n\n'
            'import "fmt"\n'
            'import "net/http"\n\n'
            'func main() { }\n'
        )
        ext = GoEdgeExtractor()
        edges = ext.extract(src, "main.go", "/project")
        assert len(edges) == 0

    def test_multi_import_block(self) -> None:
        src = (
            'package main\n\n'
            'import (\n'
            '    "github.com/myproject/db"\n'
            '    "github.com/myproject/models"\n'
            '    "fmt"\n'
            ')\n\n'
            'func main() { }\n'
        )
        ext = GoEdgeExtractor()
        edges = ext.extract(src, "main.go", "/project")
        assert ("main.go", "db") in edges
        assert ("main.go", "models") in edges
        assert len(edges) == 2

    def test_aliased_import(self) -> None:
        src = (
            'package main\n\n'
            'import mydb "github.com/myproject/database"\n\n'
            'func main() { }\n'
        )
        ext = GoEdgeExtractor()
        edges = ext.extract(src, "main.go", "/project")
        assert ("main.go", "mydb") in edges

    def test_empty_source(self) -> None:
        ext = GoEdgeExtractor()
        edges = ext.extract("", "empty.go", "/project")
        assert edges == []


# ---------------------------------------------------------------------------
# Kotlin extractor
# ---------------------------------------------------------------------------


class TestKotlinEdgeExtractor:
    """Kotlin inheritance edge extraction."""

    def test_class_inheritance(self) -> None:
        src = (
            "package com.example\n\n"
            "class MyService : BaseService() {\n"
            "    fun doWork() { }\n"
            "}\n"
        )
        ext = KotlinEdgeExtractor()
        edges = ext.extract(src, "MyService.kt", "/project")
        assert ("MyService.kt", "BaseService") in edges

    def test_interface_implementation(self) -> None:
        src = (
            "class MyRepo : IMyRepo, Closeable {\n"
            "}\n"
        )
        ext = KotlinEdgeExtractor()
        edges = ext.extract(src, "MyRepo.kt", "/project")
        assert ("MyRepo.kt", "IMyRepo") in edges

    def test_kotlin_stdlib_filtered(self) -> None:
        src = (
            "import kotlin.collections.List\n\n"
            "class MyList : List<String> { }\n"
        )
        ext = KotlinEdgeExtractor()
        edges = ext.extract(src, "MyList.kt", "/project")
        assert len(edges) == 0

    def test_object_inheritance(self) -> None:
        src = "object Singleton : BaseSingleton() { }\n"
        ext = KotlinEdgeExtractor()
        edges = ext.extract(src, "Singleton.kt", "/project")
        assert ("Singleton.kt", "BaseSingleton") in edges

    def test_interface_extension(self) -> None:
        src = "interface IExtended : IBase { }\n"
        ext = KotlinEdgeExtractor()
        edges = ext.extract(src, "IExtended.kt", "/project")
        assert ("IExtended.kt", "IBase") in edges

    def test_empty_source(self) -> None:
        ext = KotlinEdgeExtractor()
        edges = ext.extract("", "Empty.kt", "/project")
        assert edges == []

    def test_generic_types_stripped(self) -> None:
        src = "class Container<T> : BaseHolder<T>() { }\n"
        ext = KotlinEdgeExtractor()
        edges = ext.extract(src, "Container.kt", "/project")
        assert ("Container.kt", "BaseHolder") in edges
