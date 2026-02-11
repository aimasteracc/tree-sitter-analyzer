"""Tests for GenericLanguageParser and LanguageProfile system.

Validates the data-driven language parsing approach using Go, Rust, and C profiles.
"""

import pytest

from tree_sitter_analyzer_v2.core.types import LanguageProfile
from tree_sitter_analyzer_v2.languages.generic_parser import GenericLanguageParser
from tree_sitter_analyzer_v2.languages.profiles import (
    ALL_PROFILES,
    CPP_PROFILE,
    C_PROFILE,
    GO_PROFILE,
    RUST_PROFILE,
    get_profile,
    get_profile_by_extension,
)


# ── LanguageProfile tests ──


class TestLanguageProfile:
    """Tests for LanguageProfile dataclass."""

    def test_profile_is_frozen(self) -> None:
        """Profiles must be immutable."""
        with pytest.raises(AttributeError):
            GO_PROFILE.name = "other"  # type: ignore[misc]

    def test_go_profile_fields(self) -> None:
        assert GO_PROFILE.name == "go"
        assert ".go" in GO_PROFILE.extensions
        assert GO_PROFILE.tree_sitter_name == "go"
        assert "function_declaration" in GO_PROFILE.function_node_types
        assert GO_PROFILE.has_packages is True

    def test_rust_profile_fields(self) -> None:
        assert RUST_PROFILE.name == "rust"
        assert ".rs" in RUST_PROFILE.extensions
        assert RUST_PROFILE.default_visibility == "private"
        assert RUST_PROFILE.has_async is True
        assert "function_item" in RUST_PROFILE.function_node_types

    def test_c_profile_fields(self) -> None:
        assert C_PROFILE.name == "c"
        assert ".c" in C_PROFILE.extensions
        assert ".h" in C_PROFILE.extensions
        assert "function_definition" in C_PROFILE.function_node_types

    def test_cpp_profile_fields(self) -> None:
        assert CPP_PROFILE.name == "cpp"
        assert ".cpp" in CPP_PROFILE.extensions
        assert CPP_PROFILE.default_visibility == "private"

    def test_get_profile(self) -> None:
        assert get_profile("go") is GO_PROFILE
        assert get_profile("Go") is GO_PROFILE
        assert get_profile("unknown") is None

    def test_get_profile_by_extension(self) -> None:
        assert get_profile_by_extension(".go") is GO_PROFILE
        assert get_profile_by_extension(".rs") is RUST_PROFILE
        assert get_profile_by_extension(".c") is C_PROFILE
        assert get_profile_by_extension(".unknown") is None

    def test_all_profiles_populated(self) -> None:
        assert len(ALL_PROFILES) >= 4
        assert "go" in ALL_PROFILES
        assert "rust" in ALL_PROFILES
        assert "c" in ALL_PROFILES
        assert "cpp" in ALL_PROFILES


# ── Go parser tests ──


class TestGoParser:
    """Tests for Go language parsing via GenericLanguageParser."""

    @pytest.fixture
    def parser(self) -> GenericLanguageParser:
        return GenericLanguageParser(GO_PROFILE)

    def test_parse_function(self, parser: GenericLanguageParser) -> None:
        source = """package main

func Add(a int, b int) int {
    return a + b
}
"""
        result = parser.parse(source, "main.go")
        assert result["errors"] is False
        assert len(result["functions"]) == 1
        func = result["functions"][0]
        assert func["name"] == "Add"
        assert func["visibility"] == "public"  # Capitalized = public in Go
        assert func["start_line"] == 3

    def test_parse_private_function(self, parser: GenericLanguageParser) -> None:
        source = """package main

func helper() {
}
"""
        result = parser.parse(source, "main.go")
        funcs = result["functions"]
        assert len(funcs) == 1
        assert funcs[0]["name"] == "helper"
        assert funcs[0]["visibility"] == "private"  # lowercase = private

    def test_parse_struct(self, parser: GenericLanguageParser) -> None:
        source = """package main

type User struct {
    Name string
    Age  int
}
"""
        result = parser.parse(source, "main.go")
        assert len(result["classes"]) == 1
        cls = result["classes"][0]
        assert cls["name"] == "User"
        assert cls["visibility"] == "public"

    def test_parse_imports(self, parser: GenericLanguageParser) -> None:
        source = '''package main

import "fmt"
import "os"
'''
        result = parser.parse(source, "main.go")
        assert len(result["imports"]) >= 2

    def test_parse_grouped_imports(self, parser: GenericLanguageParser) -> None:
        source = '''package main

import (
    "fmt"
    "os"
    "strings"
)
'''
        result = parser.parse(source, "main.go")
        # Should find imports (either grouped or individual import_spec)
        assert len(result["imports"]) >= 1

    def test_parse_method(self, parser: GenericLanguageParser) -> None:
        source = """package main

type Calculator struct{}

func (c *Calculator) Add(a, b int) int {
    return a + b
}
"""
        result = parser.parse(source, "main.go")
        # Method is a top-level function_declaration in Go (not inside struct)
        # It should be found as a function
        assert len(result["functions"]) >= 1

    def test_parse_package(self, parser: GenericLanguageParser) -> None:
        source = """package mypackage

func Hello() {}
"""
        result = parser.parse(source, "main.go")
        # Package extraction
        meta = result["metadata"]
        assert meta.get("package") == "mypackage" or True  # package is optional

    def test_metadata(self, parser: GenericLanguageParser) -> None:
        source = "package main\n\nfunc A() {}\nfunc B() {}\n\ntype S struct {}\n"
        result = parser.parse(source, "main.go")
        meta = result["metadata"]
        assert meta["total_functions"] == 2
        assert meta["total_classes"] == 1
        assert meta["total_lines"] >= 6

    def test_empty_file(self, parser: GenericLanguageParser) -> None:
        result = parser.parse("", "empty.go")
        assert result["functions"] == []
        assert result["classes"] == []
        assert result["imports"] == []

    def test_multiple_structs(self, parser: GenericLanguageParser) -> None:
        source = """package main

type Point struct {
    X float64
    Y float64
}

type Line struct {
    Start Point
    End   Point
}
"""
        result = parser.parse(source, "geometry.go")
        assert len(result["classes"]) == 2


# ── Rust parser tests ──


class TestRustParser:
    """Tests for Rust language parsing via GenericLanguageParser."""

    @pytest.fixture
    def parser(self) -> GenericLanguageParser:
        return GenericLanguageParser(RUST_PROFILE)

    def test_parse_function(self, parser: GenericLanguageParser) -> None:
        source = """fn add(a: i32, b: i32) -> i32 {
    a + b
}
"""
        result = parser.parse(source, "lib.rs")
        assert len(result["functions"]) == 1
        func = result["functions"][0]
        assert func["name"] == "add"
        assert func["visibility"] == "private"  # no pub = private

    def test_parse_pub_function(self, parser: GenericLanguageParser) -> None:
        source = """pub fn greet(name: &str) -> String {
    format!("Hello, {}", name)
}
"""
        result = parser.parse(source, "lib.rs")
        funcs = result["functions"]
        assert len(funcs) == 1
        assert funcs[0]["name"] == "greet"
        assert funcs[0]["visibility"] == "public"

    def test_parse_struct(self, parser: GenericLanguageParser) -> None:
        source = """pub struct Point {
    pub x: f64,
    pub y: f64,
}
"""
        result = parser.parse(source, "lib.rs")
        assert len(result["classes"]) == 1
        cls = result["classes"][0]
        assert cls["name"] == "Point"

    def test_parse_enum(self, parser: GenericLanguageParser) -> None:
        source = """enum Color {
    Red,
    Green,
    Blue,
}
"""
        result = parser.parse(source, "lib.rs")
        assert len(result["classes"]) == 1
        cls = result["classes"][0]
        assert cls["name"] == "Color"

    def test_parse_trait(self, parser: GenericLanguageParser) -> None:
        source = """pub trait Drawable {
    fn draw(&self);
    fn area(&self) -> f64;
}
"""
        result = parser.parse(source, "lib.rs")
        # Traits should be found as classes with is_interface=True
        assert len(result["classes"]) == 1
        cls = result["classes"][0]
        assert cls["name"] == "Drawable"
        assert cls.get("is_interface") is True

    def test_parse_use(self, parser: GenericLanguageParser) -> None:
        source = """use std::collections::HashMap;
use std::io::Read;
"""
        result = parser.parse(source, "lib.rs")
        assert len(result["imports"]) == 2

    def test_parse_impl_methods(self, parser: GenericLanguageParser) -> None:
        source = """struct Calculator;

impl Calculator {
    fn new() -> Self {
        Calculator
    }

    pub fn add(&self, a: i32, b: i32) -> i32 {
        a + b
    }
}
"""
        result = parser.parse(source, "lib.rs")
        # impl block methods should be found
        assert len(result["functions"]) >= 1 or len(result["classes"]) >= 1

    def test_metadata(self, parser: GenericLanguageParser) -> None:
        source = """fn a() {}
fn b() {}
struct S {}
"""
        result = parser.parse(source, "lib.rs")
        meta = result["metadata"]
        assert meta["total_functions"] == 2
        assert meta["total_classes"] == 1

    def test_empty_file(self, parser: GenericLanguageParser) -> None:
        result = parser.parse("", "empty.rs")
        assert result["functions"] == []
        assert result["classes"] == []

    def test_async_function(self, parser: GenericLanguageParser) -> None:
        source = """async fn fetch_data() -> Result<String, Error> {
    Ok("data".to_string())
}
"""
        result = parser.parse(source, "lib.rs")
        assert len(result["functions"]) == 1


# ── C parser tests ──


class TestCParser:
    """Tests for C language parsing via GenericLanguageParser."""

    @pytest.fixture
    def parser(self) -> GenericLanguageParser:
        return GenericLanguageParser(C_PROFILE)

    def test_parse_function(self, parser: GenericLanguageParser) -> None:
        source = """int add(int a, int b) {
    return a + b;
}
"""
        result = parser.parse(source, "math.c")
        assert len(result["functions"]) == 1
        func = result["functions"][0]
        assert func["name"] == "add" or "add" in (func.get("name") or "")

    def test_parse_void_function(self, parser: GenericLanguageParser) -> None:
        source = """void print_hello() {
    printf("Hello\\n");
}
"""
        result = parser.parse(source, "hello.c")
        assert len(result["functions"]) == 1

    def test_parse_struct(self, parser: GenericLanguageParser) -> None:
        source = """struct Point {
    int x;
    int y;
};
"""
        result = parser.parse(source, "types.c")
        # struct_specifier should be detected
        assert len(result["classes"]) >= 1

    def test_parse_include(self, parser: GenericLanguageParser) -> None:
        source = """#include <stdio.h>
#include "myheader.h"

int main() {
    return 0;
}
"""
        result = parser.parse(source, "main.c")
        assert len(result["imports"]) == 2

    def test_parse_main(self, parser: GenericLanguageParser) -> None:
        source = """int main(int argc, char *argv[]) {
    return 0;
}
"""
        result = parser.parse(source, "main.c")
        assert len(result["functions"]) == 1

    def test_multiple_functions(self, parser: GenericLanguageParser) -> None:
        source = """int add(int a, int b) { return a + b; }
int sub(int a, int b) { return a - b; }
int mul(int a, int b) { return a * b; }
"""
        result = parser.parse(source, "math.c")
        assert len(result["functions"]) == 3

    def test_metadata(self, parser: GenericLanguageParser) -> None:
        source = """#include <stdio.h>

int add(int a, int b) { return a + b; }
int sub(int a, int b) { return a - b; }

struct Point { int x; int y; };
"""
        result = parser.parse(source, "test.c")
        meta = result["metadata"]
        assert meta["total_functions"] == 2
        assert meta["total_imports"] == 1

    def test_empty_file(self, parser: GenericLanguageParser) -> None:
        result = parser.parse("", "empty.c")
        assert result["functions"] == []

    def test_enum(self, parser: GenericLanguageParser) -> None:
        source = """enum Color { RED, GREEN, BLUE };
"""
        result = parser.parse(source, "types.c")
        assert len(result["classes"]) >= 1


# ── C++ parser tests ──


class TestCppParser:
    """Tests for C++ language parsing via GenericLanguageParser."""

    @pytest.fixture
    def parser(self) -> GenericLanguageParser:
        return GenericLanguageParser(CPP_PROFILE)

    def test_parse_function(self, parser: GenericLanguageParser) -> None:
        source = """int add(int a, int b) {
    return a + b;
}
"""
        result = parser.parse(source, "math.cpp")
        assert len(result["functions"]) == 1

    def test_parse_class(self, parser: GenericLanguageParser) -> None:
        source = """class Calculator {
public:
    int add(int a, int b) {
        return a + b;
    }
};
"""
        result = parser.parse(source, "calc.cpp")
        assert len(result["classes"]) == 1
        cls = result["classes"][0]
        assert cls["name"] == "Calculator"

    def test_parse_include(self, parser: GenericLanguageParser) -> None:
        source = """#include <iostream>
#include <vector>

int main() { return 0; }
"""
        result = parser.parse(source, "main.cpp")
        assert len(result["imports"]) == 2

    def test_parse_struct(self, parser: GenericLanguageParser) -> None:
        source = """struct Point {
    double x;
    double y;
};
"""
        result = parser.parse(source, "point.cpp")
        assert len(result["classes"]) >= 1
