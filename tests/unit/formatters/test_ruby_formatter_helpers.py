from tree_sitter_analyzer.formatters._ruby_formatter_helpers import (
    format_compact_signature,
    format_compact_table,
    format_csv,
    format_full_table,
    format_signature,
    get_visibility_symbol,
)


class TestGetVisibilitySymbol:
    def test_public(self):
        assert get_visibility_symbol("public") == "+"

    def test_private(self):
        assert get_visibility_symbol("private") == "-"

    def test_protected(self):
        assert get_visibility_symbol("protected") == "#"

    def test_module(self):
        assert get_visibility_symbol("module") == "~"

    def test_unknown_defaults_to_public(self):
        assert get_visibility_symbol("unknown") == "+"

    def test_case_insensitive(self):
        assert get_visibility_symbol("Public") == "+"
        assert get_visibility_symbol("PRIVATE") == "-"

    def test_empty_string(self):
        assert get_visibility_symbol("") == "+"


class TestFormatSignature:
    def test_no_params_no_return(self):
        method = {"parameters": [], "return_type": ""}
        result = format_signature(method)
        assert result == "():"

    def test_single_param(self):
        method = {
            "parameters": [{"name": "x", "type": "Integer"}],
            "return_type": "",
        }
        assert format_signature(method) == "(x:Integer):"

    def test_multiple_params(self):
        method = {
            "parameters": [
                {"name": "a", "type": "String"},
                {"name": "b", "type": "Integer"},
            ],
            "return_type": "void",
        }
        assert format_signature(method) == "(a:String, b:Integer):void"

    def test_return_type(self):
        method = {"parameters": [], "return_type": "String"}
        assert format_signature(method) == "():String"

    def test_dict_param_no_name(self):
        method = {"parameters": [{"type": "Integer"}], "return_type": ""}
        assert format_signature(method) == "(Integer):"

    def test_string_param(self):
        method = {"parameters": ["raw_param"], "return_type": ""}
        assert format_signature(method) == "(raw_param):"

    def test_missing_parameters_key(self):
        method = {"return_type": "void"}
        assert format_signature(method) == "():void"


class TestFormatCompactSignature:
    def test_no_params(self):
        method = {"parameters": [], "return_type": ""}
        assert format_compact_signature(method) == "():"

    def test_dict_params(self):
        method = {
            "parameters": [
                {"name": "x", "type": "Integer"},
                {"name": "y", "type": "String"},
            ],
            "return_type": "void",
        }
        assert format_compact_signature(method) == "(Integer, String):void"

    def test_string_params(self):
        method = {"parameters": ["raw"], "return_type": ""}
        assert format_compact_signature(method) == "(raw):"

    def test_no_return_type(self):
        method = {
            "parameters": [{"name": "a", "type": "String"}],
            "return_type": "",
        }
        assert format_compact_signature(method) == "(String):"

    def test_missing_parameters(self):
        method = {"return_type": ""}
        assert format_compact_signature(method) == "():"


class TestFormatFullTable:
    def test_empty_data(self):
        result = format_full_table({})
        assert isinstance(result, str)
        assert "# " in result

    def test_single_class(self):
        data = {
            "file_path": "test.rb",
            "classes": [
                {
                    "name": "MyClass",
                    "line_range": {"start": 1, "end": 50},
                    "class_type": "class",
                    "visibility": "public",
                }
            ],
            "methods": [],
            "fields": [],
            "imports": [],
        }
        result = format_full_table(data)
        assert "# MyClass" in result
        assert "## Classes Overview" in result
        assert "| MyClass | class | public | 1-50 |" in result

    def test_multiple_classes(self):
        data = {
            "file_path": "/path/to/test.rb",
            "classes": [
                {
                    "name": "A",
                    "line_range": {"start": 1, "end": 20},
                    "class_type": "class",
                    "visibility": "public",
                },
                {
                    "name": "B",
                    "line_range": {"start": 21, "end": 40},
                    "class_type": "module",
                    "visibility": "public",
                },
            ],
            "methods": [],
            "fields": [],
            "imports": [],
        }
        result = format_full_table(data)
        assert "# test.rb" in result
        assert "| A | class |" in result
        assert "| B | module |" in result

    def test_imports_section(self):
        data = {
            "file_path": "test.rb",
            "classes": [],
            "imports": [
                {"raw_text": "require 'json'"},
                {"raw_text": "require 'net/http'"},
            ],
            "methods": [],
            "fields": [],
        }
        result = format_full_table(data)
        assert "## Imports" in result
        assert "require 'json'" in result
        assert "require 'net/http'" in result

    def test_imports_skipped_when_empty(self):
        data = {
            "file_path": "test.rb",
            "classes": [],
            "imports": [],
            "methods": [],
            "fields": [],
        }
        result = format_full_table(data)
        assert "## Imports" not in result

    def test_imports_skips_empty_raw_text(self):
        data = {
            "file_path": "test.rb",
            "classes": [],
            "imports": [
                {"raw_text": ""},
                {"raw_text": "  "},
                {"raw_text": "require 'json'"},
            ],
            "methods": [],
            "fields": [],
        }
        result = format_full_table(data)
        assert "require 'json'" in result

    def test_class_with_methods_and_fields(self):
        data = {
            "file_path": "test.rb",
            "classes": [
                {
                    "name": "Foo",
                    "line_range": {"start": 1, "end": 100},
                    "class_type": "class",
                    "visibility": "public",
                }
            ],
            "methods": [
                {
                    "name": "bar",
                    "parameters": [],
                    "return_type": "void",
                    "visibility": "public",
                    "line_range": {"start": 10, "end": 20},
                    "complexity": 1,
                }
            ],
            "fields": [
                {
                    "name": "@x",
                    "variable_type": "Integer",
                    "visibility": "private",
                    "line_range": {"start": 5, "end": 5},
                    "modifiers": [],
                }
            ],
            "imports": [],
        }
        result = format_full_table(data)
        assert "## Foo (1-100)" in result
        assert "### Fields" in result
        assert "| @x | Integer | - |" in result
        assert "### Public Methods" in result

    def test_constructor_initialize(self):
        data = {
            "file_path": "test.rb",
            "classes": [
                {
                    "name": "Foo",
                    "line_range": {"start": 1, "end": 100},
                    "class_type": "class",
                    "visibility": "public",
                }
            ],
            "methods": [
                {
                    "name": "initialize",
                    "parameters": [],
                    "return_type": "",
                    "visibility": "public",
                    "line_range": {"start": 5, "end": 10},
                    "is_constructor": True,
                },
                {
                    "name": "do_stuff",
                    "parameters": [],
                    "return_type": "",
                    "visibility": "public",
                    "line_range": {"start": 15, "end": 20},
                },
            ],
            "fields": [],
            "imports": [],
        }
        result = format_full_table(data)
        lines = result.split("\n")
        init_idx = next(i for i, ln in enumerate(lines) if "initialize" in ln)
        stuff_idx = next(i for i, ln in enumerate(lines) if "do_stuff" in ln)
        assert init_idx < stuff_idx

    def test_module_level_methods(self):
        data = {
            "file_path": "test.rb",
            "classes": [
                {
                    "name": "Inner",
                    "line_range": {"start": 10, "end": 50},
                    "class_type": "class",
                    "visibility": "public",
                }
            ],
            "methods": [
                {
                    "name": "top_level_func",
                    "parameters": [],
                    "return_type": "",
                    "visibility": "public",
                    "line_range": {"start": 3, "end": 5},
                }
            ],
            "fields": [],
            "imports": [],
        }
        result = format_full_table(data)
        assert "## Module Functions" in result
        assert "top_level_func" in result

    def test_static_method_annotation(self):
        data = {
            "file_path": "test.rb",
            "classes": [
                {
                    "name": "Foo",
                    "line_range": {"start": 1, "end": 50},
                    "class_type": "class",
                    "visibility": "public",
                }
            ],
            "methods": [
                {
                    "name": "create",
                    "parameters": [],
                    "return_type": "Foo",
                    "visibility": "public",
                    "line_range": {"start": 5, "end": 10},
                    "is_static": True,
                }
            ],
            "fields": [],
            "imports": [],
        }
        result = format_full_table(data)
        assert "[static]" in result

    def test_class_method_separator(self):
        data = {
            "file_path": "test.rb",
            "classes": [
                {
                    "name": "Foo",
                    "line_range": {"start": 1, "end": 50},
                    "class_type": "class",
                    "visibility": "public",
                }
            ],
            "methods": [
                {
                    "name": "bar",
                    "parameters": [],
                    "return_type": "",
                    "visibility": "public",
                    "line_range": {"start": 5, "end": 10},
                    "metadata": {"method_type": "class"},
                }
            ],
            "fields": [],
            "imports": [],
        }
        result = format_full_table(data)
        assert "Foo.bar" in result

    def test_instance_method_separator(self):
        data = {
            "file_path": "test.rb",
            "classes": [
                {
                    "name": "Foo",
                    "line_range": {"start": 1, "end": 50},
                    "class_type": "class",
                    "visibility": "public",
                }
            ],
            "methods": [
                {
                    "name": "baz",
                    "parameters": [],
                    "return_type": "",
                    "visibility": "public",
                    "line_range": {"start": 5, "end": 10},
                    "metadata": {"method_type": "instance"},
                }
            ],
            "fields": [],
            "imports": [],
        }
        result = format_full_table(data)
        assert "Foo#baz" in result

    def test_doc_truncation(self):
        data = {
            "file_path": "test.rb",
            "classes": [],
            "methods": [
                {
                    "name": "func",
                    "parameters": [],
                    "return_type": "",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 2},
                    "documentation": "A" * 50,
                }
            ],
            "fields": [],
            "imports": [],
        }
        result = format_full_table(data)
        assert "..." in result

    def test_doc_none_treated_as_dash(self):
        data = {
            "file_path": "test.rb",
            "classes": [],
            "methods": [
                {
                    "name": "func",
                    "parameters": [],
                    "return_type": "",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 2},
                    "documentation": None,
                }
            ],
            "fields": [],
            "imports": [],
        }
        result = format_full_table(data)
        assert "-" in result


class TestFormatCompactTable:
    def test_empty_data(self):
        result = format_compact_table({})
        assert "# " in result
        assert "## Info" in result

    def test_with_methods(self):
        data = {
            "file_path": "test.rb",
            "methods": [
                {
                    "name": "hello",
                    "parameters": [],
                    "return_type": "",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 5},
                }
            ],
            "fields": [],
            "statistics": {"method_count": 1, "field_count": 0},
        }
        result = format_compact_table(data)
        assert "## Methods" in result
        assert "hello" in result

    def test_compact_info_with_statistics(self):
        data = {
            "file_path": "test.rb",
            "methods": [],
            "fields": [{"name": "x"}],
            "statistics": {"method_count": 5, "field_count": 3},
        }
        result = format_compact_table(data)
        assert "| Methods | 5 |" in result
        assert "| Fields | 3 |" in result

    def test_compact_info_without_statistics(self):
        data = {
            "file_path": "test.rb",
            "methods": [
                {"name": "a"},
                {"name": "b"},
            ],
            "fields": [],
        }
        result = format_compact_table(data)
        assert "| Methods | 2 |" in result

    def test_compact_method_with_parent_class(self):
        data = {
            "file_path": "test.rb",
            "methods": [
                {
                    "name": "foo",
                    "parent_class": "Bar",
                    "parameters": [],
                    "return_type": "",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 5},
                    "metadata": {"method_type": "instance"},
                }
            ],
            "fields": [],
        }
        result = format_compact_table(data)
        assert "Bar#foo" in result


class TestFormatCsv:
    def test_header_row(self):
        result = format_csv({})
        assert result.startswith("Type,Name,Signature,Visibility,Lines,Complexity,Doc")

    def test_fields(self):
        data = {
            "fields": [
                {
                    "name": "x",
                    "variable_type": "Integer",
                    "visibility": "public",
                    "line_range": {"start": 5, "end": 5},
                    "parent_class": "Foo",
                }
            ],
            "methods": [],
        }
        result = format_csv(data)
        assert "Field,Foo::x,Foo::x:Integer,public,5-5,," in result

    def test_methods(self):
        data = {
            "fields": [],
            "methods": [
                {
                    "name": "hello",
                    "parameters": [],
                    "return_type": "void",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 10},
                    "complexity": 2,
                }
            ],
        }
        result = format_csv(data)
        assert "Method,hello," in result
        assert ",public,1-10,2," in result

    def test_constructor_in_csv(self):
        data = {
            "fields": [],
            "methods": [
                {
                    "name": "initialize",
                    "parameters": [],
                    "return_type": "",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 5},
                    "is_constructor": True,
                }
            ],
        }
        result = format_csv(data)
        assert "Constructor,initialize," in result

    def test_csv_static_method(self):
        data = {
            "fields": [],
            "methods": [
                {
                    "name": "create",
                    "parameters": [],
                    "return_type": "Foo",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 5},
                    "is_static": True,
                }
            ],
        }
        result = format_csv(data)
        assert "[static]" in result

    def test_csv_field_without_parent(self):
        data = {
            "fields": [
                {
                    "name": "y",
                    "variable_type": "String",
                    "visibility": "public",
                    "line_range": {"start": 3, "end": 3},
                }
            ],
            "methods": [],
        }
        result = format_csv(data)
        assert "Field,y,y:String,public,3-3,," in result

    def test_csv_method_with_parent_class(self):
        data = {
            "fields": [],
            "methods": [
                {
                    "name": "foo",
                    "parameters": [],
                    "return_type": "",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 5},
                    "parent_class": "Bar",
                    "metadata": {"method_type": "instance"},
                }
            ],
        }
        result = format_csv(data)
        assert "Bar#foo" in result

    def test_csv_class_method_prefix(self):
        data = {
            "fields": [],
            "methods": [
                {
                    "name": "bar",
                    "parameters": [],
                    "return_type": "",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 5},
                    "parent_class": "Baz",
                    "metadata": {"method_type": "class"},
                }
            ],
        }
        result = format_csv(data)
        assert "Baz.bar" in result
