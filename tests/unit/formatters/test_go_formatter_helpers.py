from tree_sitter_analyzer.formatters._go_formatter_helpers import (
    format_go_full_table,
)


def _noop_package(data: dict) -> str:
    return data.get("package", {}).get("name", "main")


def _noop_visibility(name: str) -> str:
    return "exported" if name and name[0].isupper() else "unexported"


def _noop_doc(text: str) -> str:
    return text.strip() if text else ""


def _noop_func_row(func: dict) -> str:
    name = func.get("name", "")
    vis = _noop_visibility(name)
    lr = func.get("line_range", {})
    return f"| {name} | sig | {vis} | {lr.get('start', 0)}-{lr.get('end', 0)} | - |"


def _noop_method_row(method: dict) -> str:
    name = method.get("name", "")
    recv = method.get("receiver", "")
    vis = _noop_visibility(name)
    lr = method.get("line_range", {})
    return f"| {recv} | {name} | sig | {vis} | {lr.get('start', 0)}-{lr.get('end', 0)} | - |"


class TestFormatGoFullTable:
    def test_file_header_with_package(self):
        data = {
            "file_path": "/pkg/handler.go",
            "package": {"name": "handler"},
            "classes": [],
            "functions": [],
            "variables": [],
        }
        result = format_go_full_table(
            data,
            _noop_package,
            _noop_visibility,
            _noop_doc,
            _noop_func_row,
            _noop_method_row,
        )
        assert "# handler/handler.go" in result

    def test_file_header_without_package(self):
        data = {
            "file_path": "main.go",
            "package": {"name": ""},
            "classes": [],
            "functions": [],
            "variables": [],
        }
        result = format_go_full_table(
            data,
            _noop_package,
            _noop_visibility,
            _noop_doc,
            _noop_func_row,
            _noop_method_row,
        )
        assert "# main.go" in result

    def test_package_info_section(self):
        data = {
            "file_path": "main.go",
            "package": {"name": "main"},
            "statistics": {"function_count": 5, "class_count": 2, "variable_count": 3},
            "classes": [],
            "functions": [],
            "variables": [],
        }
        result = format_go_full_table(
            data,
            _noop_package,
            _noop_visibility,
            _noop_doc,
            _noop_func_row,
            _noop_method_row,
        )
        assert "## Package Info" in result
        assert "| Package | main |" in result
        assert "| Functions | 5 |" in result
        assert "| Types | 2 |" in result
        assert "| Variables | 3 |" in result

    def test_imports_section(self):
        data = {
            "file_path": "main.go",
            "package": {"name": "main"},
            "imports": [
                {"import_statement": 'import "fmt"'},
                {"import_statement": 'import "net/http"'},
            ],
            "classes": [],
            "functions": [],
            "variables": [],
        }
        result = format_go_full_table(
            data,
            _noop_package,
            _noop_visibility,
            _noop_doc,
            _noop_func_row,
            _noop_method_row,
        )
        assert "## Imports" in result
        assert "```go" in result
        assert 'import "fmt"' in result
        assert 'import "net/http"' in result

    def test_imports_add_import_prefix(self):
        data = {
            "file_path": "main.go",
            "package": {"name": "main"},
            "imports": [{"raw_text": "fmt"}],
            "classes": [],
            "functions": [],
            "variables": [],
        }
        result = format_go_full_table(
            data,
            _noop_package,
            _noop_visibility,
            _noop_doc,
            _noop_func_row,
            _noop_method_row,
        )
        assert 'import "fmt"' in result

    def test_imports_no_imports_key(self):
        data = {
            "file_path": "main.go",
            "package": {"name": "main"},
            "classes": [],
            "functions": [],
            "variables": [],
        }
        result = format_go_full_table(
            data,
            _noop_package,
            _noop_visibility,
            _noop_doc,
            _noop_func_row,
            _noop_method_row,
        )
        assert "## Imports" not in result

    def test_structs_section(self):
        data = {
            "file_path": "main.go",
            "package": {"name": "main"},
            "classes": [
                {
                    "name": "Server",
                    "type": "struct",
                    "line_range": {"start": 10, "end": 30},
                    "interfaces": ["Handler"],
                    "docstring": "HTTP server",
                }
            ],
            "functions": [],
            "variables": [],
        }
        result = format_go_full_table(
            data,
            _noop_package,
            _noop_visibility,
            _noop_doc,
            _noop_func_row,
            _noop_method_row,
        )
        assert "## Structs" in result
        assert "| Server | exported | 10-30 | Handler | HTTP server |" in result

    def test_interfaces_section(self):
        data = {
            "file_path": "main.go",
            "package": {"name": "main"},
            "classes": [
                {
                    "name": "Reader",
                    "type": "interface",
                    "line_range": {"start": 5, "end": 10},
                    "docstring": "Read interface",
                }
            ],
            "functions": [],
            "variables": [],
        }
        result = format_go_full_table(
            data,
            _noop_package,
            _noop_visibility,
            _noop_doc,
            _noop_func_row,
            _noop_method_row,
        )
        assert "## Interfaces" in result
        assert "| Reader | exported | 5-10 | Read interface |" in result

    def test_type_aliases_section(self):
        data = {
            "file_path": "main.go",
            "package": {"name": "main"},
            "classes": [
                {
                    "name": "Alias",
                    "type": "type_alias",
                    "line_range": {"start": 1, "end": 1},
                }
            ],
            "functions": [],
            "variables": [],
        }
        result = format_go_full_table(
            data,
            _noop_package,
            _noop_visibility,
            _noop_doc,
            _noop_func_row,
            _noop_method_row,
        )
        assert "## Type Aliases" in result
        assert "| Alias |" in result

    def test_functions_section(self):
        data = {
            "file_path": "main.go",
            "package": {"name": "main"},
            "classes": [],
            "functions": [
                {
                    "name": "HandleRequest",
                    "line_range": {"start": 5, "end": 15},
                    "is_method": False,
                },
                {
                    "name": "processData",
                    "line_range": {"start": 20, "end": 30},
                    "is_method": False,
                },
            ],
            "variables": [],
        }
        result = format_go_full_table(
            data,
            _noop_package,
            _noop_visibility,
            _noop_doc,
            _noop_func_row,
            _noop_method_row,
        )
        assert "## Functions" in result
        assert "HandleRequest" in result
        assert "processData" in result

    def test_methods_section(self):
        data = {
            "file_path": "main.go",
            "package": {"name": "main"},
            "classes": [],
            "functions": [
                {
                    "name": "Read",
                    "line_range": {"start": 5, "end": 10},
                    "is_method": True,
                    "receiver": "Server",
                }
            ],
            "variables": [],
        }
        result = format_go_full_table(
            data,
            _noop_package,
            _noop_visibility,
            _noop_doc,
            _noop_func_row,
            _noop_method_row,
        )
        assert "## Methods" in result
        assert "Server" in result

    def test_constants_section(self):
        data = {
            "file_path": "main.go",
            "package": {"name": "main"},
            "classes": [],
            "functions": [],
            "variables": [
                {
                    "name": "MaxRetries",
                    "variable_type": "int",
                    "line_range": {"start": 3, "end": 3},
                    "is_constant": True,
                }
            ],
        }
        result = format_go_full_table(
            data,
            _noop_package,
            _noop_visibility,
            _noop_doc,
            _noop_func_row,
            _noop_method_row,
        )
        assert "## Constants" in result
        assert "MaxRetries" in result

    def test_variables_section(self):
        data = {
            "file_path": "main.go",
            "package": {"name": "main"},
            "classes": [],
            "functions": [],
            "variables": [
                {
                    "name": "timeout",
                    "variable_type": "time.Duration",
                    "line_range": {"start": 5, "end": 5},
                    "is_constant": False,
                }
            ],
        }
        result = format_go_full_table(
            data,
            _noop_package,
            _noop_visibility,
            _noop_doc,
            _noop_func_row,
            _noop_method_row,
        )
        assert "## Variables" in result
        assert "timeout" in result

    def test_constants_and_variables_separated(self):
        data = {
            "file_path": "main.go",
            "package": {"name": "main"},
            "classes": [],
            "functions": [],
            "variables": [
                {
                    "name": "Pi",
                    "variable_type": "float64",
                    "line_range": {"start": 1, "end": 1},
                    "is_constant": True,
                },
                {
                    "name": "count",
                    "variable_type": "int",
                    "line_range": {"start": 2, "end": 2},
                    "is_constant": False,
                },
            ],
        }
        result = format_go_full_table(
            data,
            _noop_package,
            _noop_visibility,
            _noop_doc,
            _noop_func_row,
            _noop_method_row,
        )
        assert "## Constants" in result
        assert "## Variables" in result
        const_idx = result.index("## Constants")
        var_idx = result.index("## Variables")
        assert const_idx < var_idx

    def test_no_trailing_blank_lines(self):
        data = {
            "file_path": "main.go",
            "package": {"name": "main"},
            "classes": [],
            "functions": [],
            "variables": [],
        }
        result = format_go_full_table(
            data,
            _noop_package,
            _noop_visibility,
            _noop_doc,
            _noop_func_row,
            _noop_method_row,
        )
        assert not result.endswith("\n\n")

    def test_struct_no_interfaces(self):
        data = {
            "file_path": "main.go",
            "package": {"name": "main"},
            "classes": [
                {
                    "name": "Config",
                    "type": "struct",
                    "line_range": {"start": 1, "end": 10},
                }
            ],
            "functions": [],
            "variables": [],
        }
        result = format_go_full_table(
            data,
            _noop_package,
            _noop_visibility,
            _noop_doc,
            _noop_func_row,
            _noop_method_row,
        )
        assert "| Config |" in result
        assert "| - |" in result

    def test_empty_structs_skipped(self):
        data = {
            "file_path": "main.go",
            "package": {"name": "main"},
            "classes": [],
            "functions": [],
            "variables": [],
        }
        result = format_go_full_table(
            data,
            _noop_package,
            _noop_visibility,
            _noop_doc,
            _noop_func_row,
            _noop_method_row,
        )
        assert "## Structs" not in result

    def test_empty_interfaces_skipped(self):
        data = {
            "file_path": "main.go",
            "package": {"name": "main"},
            "classes": [],
            "functions": [],
            "variables": [],
        }
        result = format_go_full_table(
            data,
            _noop_package,
            _noop_visibility,
            _noop_doc,
            _noop_func_row,
            _noop_method_row,
        )
        assert "## Interfaces" not in result

    def test_variable_type_fallback(self):
        data = {
            "file_path": "main.go",
            "package": {"name": "main"},
            "classes": [],
            "functions": [],
            "variables": [
                {
                    "name": "x",
                    "type": "int",
                    "line_range": {"start": 1, "end": 1},
                    "is_constant": False,
                }
            ],
        }
        result = format_go_full_table(
            data,
            _noop_package,
            _noop_visibility,
            _noop_doc,
            _noop_func_row,
            _noop_method_row,
        )
        assert "| x | int |" in result

    def test_methods_key_fallback_for_functions(self):
        data = {
            "file_path": "main.go",
            "package": {"name": "main"},
            "classes": [],
            "methods": [
                {
                    "name": "Run",
                    "line_range": {"start": 5, "end": 10},
                    "is_method": False,
                }
            ],
            "variables": [],
        }
        result = format_go_full_table(
            data,
            _noop_package,
            _noop_visibility,
            _noop_doc,
            _noop_func_row,
            _noop_method_row,
        )
        assert "Run" in result

    def test_fields_key_fallback_for_variables(self):
        data = {
            "file_path": "main.go",
            "package": {"name": "main"},
            "classes": [],
            "functions": [],
            "fields": [
                {
                    "name": "val",
                    "variable_type": "string",
                    "line_range": {"start": 1, "end": 1},
                    "is_constant": False,
                }
            ],
        }
        result = format_go_full_table(
            data,
            _noop_package,
            _noop_visibility,
            _noop_doc,
            _noop_func_row,
            _noop_method_row,
        )
        assert "val" in result
