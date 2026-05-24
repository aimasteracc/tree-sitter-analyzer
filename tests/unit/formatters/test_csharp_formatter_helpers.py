from tree_sitter_analyzer.formatters._csharp_formatter_helpers import (
    format_csharp_compact_table,
    format_csharp_csv,
    format_csharp_full_table,
)


def _noop_visibility(v: str) -> str:
    return v


def _noop_namespace(_data: dict) -> str:
    return "TestApp"


def _noop_modifiers(field: dict) -> str:
    mods = field.get("modifiers", [])
    return ",".join(str(m) for m in mods) if mods else ""


def _noop_class_methods(methods: list, line_range: dict) -> list:
    start = line_range.get("start", 0)
    end = line_range.get("end", 0)
    return [m for m in methods if start <= m.get("line_range", {}).get("start", 0) <= end]


def _noop_class_fields(fields: list, line_range: dict) -> list:
    start = line_range.get("start", 0)
    end = line_range.get("end", 0)
    return [f for f in fields if start <= f.get("line_range", {}).get("start", 0) <= end]


def _noop_signature(method: dict) -> str:
    params = ",".join(str(p.get("type", "Any")) for p in method.get("parameters", []))
    ret = method.get("return_type", "void")
    return f"({params}):{ret}"


def _noop_method_row(method: dict) -> str:
    name = method.get("name", "")
    vis = _noop_visibility(method.get("visibility", "public"))
    lr = method.get("line_range", {})
    return f"| {name} | {_noop_signature(method)} | {vis} | {lr.get('start', 0)}-{lr.get('end', 0)} | 1 | - |"


class TestFormatCsharpFullTable:

    def test_empty_data(self):
        result = format_csharp_full_table(
            {},
            _noop_class_methods,
            _noop_class_fields,
            _noop_modifiers,
            _noop_visibility,
            _noop_method_row,
        )
        assert isinstance(result, str)

    def test_file_header(self):
        data = {"file_path": "/src/Program.cs", "classes": [], "methods": [], "fields": []}
        result = format_csharp_full_table(
            data,
            _noop_class_methods,
            _noop_class_fields,
            _noop_modifiers,
            _noop_visibility,
            _noop_method_row,
        )
        assert "# Program.cs" in result

    def test_imports_section(self):
        data = {
            "file_path": "test.cs",
            "imports": [
                {"raw_text": "using System;"},
                {"raw_text": "using System.Collections.Generic;"},
            ],
            "classes": [],
            "methods": [],
            "fields": [],
        }
        result = format_csharp_full_table(
            data,
            _noop_class_methods,
            _noop_class_fields,
            _noop_modifiers,
            _noop_visibility,
            _noop_method_row,
        )
        assert "## Imports" in result
        assert "```csharp" in result
        assert "using System;" in result

    def test_imports_skip_empty(self):
        data = {
            "file_path": "test.cs",
            "imports": [{"raw_text": ""}, {"raw_text": "using Foo;"}],
            "classes": [],
            "methods": [],
            "fields": [],
        }
        result = format_csharp_full_table(
            data,
            _noop_class_methods,
            _noop_class_fields,
            _noop_modifiers,
            _noop_visibility,
            _noop_method_row,
        )
        assert "using Foo;" in result

    def test_no_imports_section_when_empty(self):
        data = {
            "file_path": "test.cs",
            "imports": [],
            "classes": [],
            "methods": [],
            "fields": [],
        }
        result = format_csharp_full_table(
            data,
            _noop_class_methods,
            _noop_class_fields,
            _noop_modifiers,
            _noop_visibility,
            _noop_method_row,
        )
        assert "## Imports" not in result

    def test_classes_overview(self):
        data = {
            "file_path": "test.cs",
            "classes": [
                {
                    "name": "Calculator",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 5, "end": 50},
                }
            ],
            "methods": [],
            "fields": [],
            "imports": [],
        }
        result = format_csharp_full_table(
            data,
            _noop_class_methods,
            _noop_class_fields,
            _noop_modifiers,
            _noop_visibility,
            _noop_method_row,
        )
        assert "## Classes Overview" in result
        assert "| Calculator | class | public | 5-50 |" in result

    def test_class_fields(self):
        data = {
            "file_path": "test.cs",
            "classes": [
                {
                    "name": "Foo",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 50},
                }
            ],
            "methods": [],
            "fields": [
                {
                    "name": "count",
                    "type": "int",
                    "visibility": "private",
                    "line_range": {"start": 5, "end": 5},
                    "modifiers": ["readonly"],
                }
            ],
            "imports": [],
        }
        result = format_csharp_full_table(
            data,
            _noop_class_methods,
            _noop_class_fields,
            _noop_modifiers,
            _noop_visibility,
            _noop_method_row,
        )
        assert "### Fields" in result
        assert "| count | int | private | readonly |" in result

    def test_method_groups_by_visibility(self):
        data = {
            "file_path": "test.cs",
            "classes": [
                {
                    "name": "Svc",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 100},
                }
            ],
            "methods": [
                {
                    "name": ".ctor",
                    "visibility": "public",
                    "is_constructor": True,
                    "parameters": [],
                    "return_type": "void",
                    "line_range": {"start": 5, "end": 10},
                },
                {
                    "name": "DoWork",
                    "visibility": "public",
                    "parameters": [],
                    "return_type": "void",
                    "line_range": {"start": 15, "end": 20},
                },
                {
                    "name": "Helper",
                    "visibility": "private",
                    "parameters": [],
                    "return_type": "void",
                    "line_range": {"start": 25, "end": 30},
                },
            ],
            "fields": [],
            "imports": [],
        }
        result = format_csharp_full_table(
            data,
            _noop_class_methods,
            _noop_class_fields,
            _noop_modifiers,
            _noop_visibility,
            _noop_method_row,
        )
        assert "### Constructors" in result
        assert "### Public Methods" in result
        assert "### Private Methods" in result

    def test_no_trailing_blank_lines(self):
        data = {
            "file_path": "test.cs",
            "classes": [],
            "methods": [],
            "fields": [],
        }
        result = format_csharp_full_table(
            data,
            _noop_class_methods,
            _noop_class_fields,
            _noop_modifiers,
            _noop_visibility,
            _noop_method_row,
        )
        assert not result.endswith("\n\n")

    def test_multiple_classes(self):
        data = {
            "file_path": "test.cs",
            "classes": [
                {
                    "name": "A",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 20},
                },
                {
                    "name": "B",
                    "type": "struct",
                    "visibility": "internal",
                    "line_range": {"start": 21, "end": 40},
                },
            ],
            "methods": [],
            "fields": [],
            "imports": [],
        }
        result = format_csharp_full_table(
            data,
            _noop_class_methods,
            _noop_class_fields,
            _noop_modifiers,
            _noop_visibility,
            _noop_method_row,
        )
        assert "| A | class |" in result
        assert "| B | struct |" in result

    def test_field_type_fallback(self):
        data = {
            "file_path": "test.cs",
            "classes": [
                {
                    "name": "C",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 20},
                }
            ],
            "methods": [],
            "fields": [
                {
                    "name": "x",
                    "field_type": "string",
                    "visibility": "public",
                    "line_range": {"start": 5, "end": 5},
                    "modifiers": [],
                }
            ],
            "imports": [],
        }
        result = format_csharp_full_table(
            data,
            _noop_class_methods,
            _noop_class_fields,
            _noop_modifiers,
            _noop_visibility,
            _noop_method_row,
        )
        assert "| x | string |" in result

    def test_variable_type_fallback(self):
        data = {
            "file_path": "test.cs",
            "classes": [
                {
                    "name": "C",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 20},
                }
            ],
            "methods": [],
            "fields": [
                {
                    "name": "y",
                    "variable_type": "double",
                    "visibility": "public",
                    "line_range": {"start": 5, "end": 5},
                    "modifiers": [],
                }
            ],
            "imports": [],
        }
        result = format_csharp_full_table(
            data,
            _noop_class_methods,
            _noop_class_fields,
            _noop_modifiers,
            _noop_visibility,
            _noop_method_row,
        )
        assert "| y | double |" in result


class TestFormatCsharpCompactTable:

    def test_basic(self):
        data = {
            "file_path": "Program.cs",
            "statistics": {"method_count": 3, "field_count": 1},
            "methods": [
                {
                    "name": "Main",
                    "parameters": [],
                    "return_type": "void",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 10},
                }
            ],
        }
        result = format_csharp_compact_table(
            data, _noop_namespace, _noop_signature, _noop_visibility
        )
        assert "# Program.cs" in result
        assert "## Info" in result
        assert "| Methods | 3 |" in result
        assert "## Methods" in result
        assert "Main" in result

    def test_empty_methods(self):
        data = {
            "file_path": "Empty.cs",
            "statistics": {"method_count": 0, "field_count": 0},
            "methods": [],
        }
        result = format_csharp_compact_table(
            data, _noop_namespace, _noop_signature, _noop_visibility
        )
        assert "## Methods" not in result

    def test_namespace_in_info(self):
        data = {
            "file_path": "test.cs",
            "statistics": {},
            "methods": [],
        }
        result = format_csharp_compact_table(
            data, _noop_namespace, _noop_signature, _noop_visibility
        )
        assert "| Package | TestApp |" in result

    def test_no_trailing_blanks(self):
        data = {
            "file_path": "test.cs",
            "statistics": {},
            "methods": [],
        }
        result = format_csharp_compact_table(
            data, _noop_namespace, _noop_signature, _noop_visibility
        )
        assert not result.endswith("\n\n")


class TestFormatCsharpCsv:

    def test_header_row(self):
        result = format_csharp_csv({}, _noop_signature)
        assert result.startswith("Type,Name,Signature,Visibility,Lines,Complexity,Doc")

    def test_fields(self):
        data = {
            "fields": [
                {
                    "name": "count",
                    "type": "int",
                    "visibility": "private",
                    "line_range": {"start": 5, "end": 5},
                }
            ],
            "methods": [],
        }
        result = format_csharp_csv(data, _noop_signature)
        assert "Field,count,count:int,private,5-5,,-" in result

    def test_methods(self):
        data = {
            "fields": [],
            "methods": [
                {
                    "name": "Calculate",
                    "parameters": [],
                    "return_type": "int",
                    "visibility": "public",
                    "line_range": {"start": 10, "end": 20},
                }
            ],
        }
        result = format_csharp_csv(data, _noop_signature)
        assert "Method,Calculate," in result
        assert ",public,10-20," in result

    def test_constructor(self):
        data = {
            "fields": [],
            "methods": [
                {
                    "name": ".ctor",
                    "is_constructor": True,
                    "parameters": [],
                    "return_type": "void",
                    "visibility": "public",
                    "line_range": {"start": 5, "end": 10},
                }
            ],
        }
        result = format_csharp_csv(data, _noop_signature)
        assert "Constructor,.ctor," in result

    def test_static_method(self):
        data = {
            "fields": [],
            "methods": [
                {
                    "name": "Create",
                    "is_static": True,
                    "parameters": [],
                    "return_type": "void",
                    "visibility": "public",
                    "line_range": {"start": 5, "end": 10},
                }
            ],
        }
        result = format_csharp_csv(data, _noop_signature)
        assert "[static]" in result

    def test_field_type_fallbacks(self):
        data = {
            "fields": [
                {
                    "name": "x",
                    "field_type": "string",
                    "visibility": "private",
                    "line_range": {"start": 1, "end": 1},
                }
            ],
            "methods": [],
        }
        result = format_csharp_csv(data, _noop_signature)
        assert "Field,x,x:string,private," in result

    def test_field_variable_type_fallback(self):
        data = {
            "fields": [
                {
                    "name": "y",
                    "variable_type": "bool",
                    "visibility": "private",
                    "line_range": {"start": 1, "end": 1},
                }
            ],
            "methods": [],
        }
        result = format_csharp_csv(data, _noop_signature)
        assert "Field,y,y:bool,private," in result

    def test_csv_comma_in_signature_quoted(self):
        def sig_with_comma(method: dict) -> str:
            return "(int,string):void"

        data = {
            "fields": [],
            "methods": [
                {
                    "name": "Multi",
                    "parameters": [],
                    "return_type": "void",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 5},
                }
            ],
        }
        result = format_csharp_csv(data, sig_with_comma)
        assert '"(int,string):void"' in result

    def test_empty_data(self):
        result = format_csharp_csv({}, _noop_signature)
        lines = result.strip().split("\n")
        assert len(lines) == 1
        assert lines[0].startswith("Type,")
