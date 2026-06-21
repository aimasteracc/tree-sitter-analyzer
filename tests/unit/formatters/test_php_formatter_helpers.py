from tree_sitter_analyzer.formatters._php_formatter_helpers import (
    extract_namespace,
    format_compact_signature,
    format_compact_table,
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

    def test_unknown(self):
        assert get_visibility_symbol("internal") == "+"

    def test_case_insensitive(self):
        assert get_visibility_symbol("PUBLIC") == "+"

    def test_empty(self):
        assert get_visibility_symbol("") == "+"


class TestFormatSignature:
    def test_no_params(self):
        method = {"parameters": [], "return_type": "void"}
        assert format_signature(method) == "():void"

    def test_single_param(self):
        method = {
            "parameters": [{"name": "id", "type": "int"}],
            "return_type": "void",
        }
        assert format_signature(method) == "($id:int):void"

    def test_multiple_params(self):
        method = {
            "parameters": [
                {"name": "name", "type": "string"},
                {"name": "age", "type": "int"},
            ],
            "return_type": "bool",
        }
        assert format_signature(method) == "($name:string, $age:int):bool"

    def test_dollar_sign_stripped(self):
        method = {
            "parameters": [{"name": "$id", "type": "int"}],
            "return_type": "void",
        }
        result = format_signature(method)
        assert result == "($id:int):void"

    def test_param_no_name(self):
        method = {
            "parameters": [{"type": "string"}],
            "return_type": "void",
        }
        assert format_signature(method) == "(string):void"

    def test_string_param(self):
        method = {"parameters": ["raw_param"], "return_type": "void"}
        assert format_signature(method) == "(raw_param):void"

    def test_empty_return_type(self):
        method = {"parameters": [], "return_type": ""}
        assert format_signature(method) == "():"

    def test_missing_return_type_key(self):
        method = {"parameters": []}
        result = format_signature(method)
        assert result == "():void"


class TestFormatCompactSignature:
    def test_dict_params(self):
        method = {
            "parameters": [{"name": "x", "type": "int"}],
            "return_type": "string",
        }
        assert format_compact_signature(method) == "(int):string"

    def test_string_params(self):
        method = {"parameters": ["raw"], "return_type": "int"}
        assert format_compact_signature(method) == "(raw):int"

    def test_no_return_type(self):
        method = {
            "parameters": [{"name": "x", "type": "int"}],
            "return_type": "",
        }
        assert format_compact_signature(method) == "(int):"

    def test_no_params(self):
        method = {"parameters": [], "return_type": "void"}
        assert format_compact_signature(method) == "():void"


class TestExtractNamespace:
    def test_from_full_qualified_name(self):
        data = {"classes": [{"full_qualified_name": "App\\Services\\UserService"}]}
        assert extract_namespace(data) == "App\\Services"

    def test_from_metadata(self):
        data = {
            "classes": [
                {
                    "full_qualified_name": "UserService",
                    "metadata": {"namespace": "App\\Models"},
                }
            ]
        }
        assert extract_namespace(data) == "App\\Models"

    def test_no_namespace(self):
        data = {"classes": [{"name": "Foo"}]}
        assert extract_namespace(data) == ""

    def test_empty_classes(self):
        assert extract_namespace({"classes": []}) == ""

    def test_prefers_fqn_over_metadata(self):
        data = {
            "classes": [
                {
                    "full_qualified_name": "App\\Entities\\User",
                    "metadata": {"namespace": "Wrong"},
                }
            ]
        }
        assert extract_namespace(data) == "App\\Entities"


class TestFormatFullTable:
    def test_empty_data(self):
        result = format_full_table({})
        assert isinstance(result, str)
        assert "# " in result

    def test_single_class(self):
        data = {
            "file_path": "test.php",
            "classes": [
                {
                    "name": "UserService",
                    "line_range": {"start": 10, "end": 100},
                    "class_type": "class",
                    "visibility": "public",
                }
            ],
            "methods": [],
            "fields": [],
            "imports": [],
        }
        result = format_full_table(data)
        assert "# test.php" in result
        assert "## Classes Overview" in result
        assert "UserService" in result

    def test_imports_section(self):
        data = {
            "file_path": "test.php",
            "classes": [],
            "imports": [
                {"raw_text": "use App\\Models\\User;"},
                {"raw_text": "  use App\\Services\\Cache;  "},
            ],
            "methods": [],
            "fields": [],
        }
        result = format_full_table(data)
        assert "## Imports" in result
        assert "```php" in result
        assert "use App\\Models\\User;" in result

    def test_empty_imports_skipped(self):
        data = {
            "file_path": "test.php",
            "classes": [],
            "imports": [],
            "methods": [],
            "fields": [],
        }
        result = format_full_table(data)
        assert "## Imports" not in result

    def test_imports_skip_empty_raw_text(self):
        data = {
            "file_path": "test.php",
            "classes": [],
            "imports": [{"raw_text": ""}, {"raw_text": "use Foo;"}],
            "methods": [],
            "fields": [],
        }
        result = format_full_table(data)
        assert "use Foo;" in result

    def test_class_with_fields(self):
        data = {
            "file_path": "test.php",
            "classes": [
                {
                    "name": "Foo",
                    "line_range": {"start": 1, "end": 50},
                    "class_type": "class",
                    "visibility": "public",
                }
            ],
            "methods": [],
            "fields": [
                {
                    "name": "id",
                    "variable_type": "int",
                    "visibility": "private",
                    "line_range": {"start": 5, "end": 5},
                    "is_static": False,
                    "is_readonly": True,
                }
            ],
            "imports": [],
        }
        result = format_full_table(data)
        assert "### Fields" in result
        assert "| Foo::id | int |" in result
        assert "readonly" in result

    def test_class_with_constructors(self):
        data = {
            "file_path": "test.php",
            "classes": [
                {
                    "name": "Bar",
                    "line_range": {"start": 1, "end": 50},
                    "class_type": "class",
                    "visibility": "public",
                }
            ],
            "methods": [
                {
                    "name": "__construct",
                    "parameters": [],
                    "return_type": "void",
                    "visibility": "public",
                    "line_range": {"start": 5, "end": 10},
                    "is_constructor": True,
                }
            ],
            "fields": [],
            "imports": [],
        }
        result = format_full_table(data)
        assert "### Constructors" in result
        assert "Bar::__construct" in result

    def test_method_visibility_groups(self):
        data = {
            "file_path": "test.php",
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
                    "name": "pub",
                    "parameters": [],
                    "return_type": "void",
                    "visibility": "public",
                    "line_range": {"start": 10, "end": 20},
                },
                {
                    "name": "prot",
                    "parameters": [],
                    "return_type": "void",
                    "visibility": "protected",
                    "line_range": {"start": 25, "end": 35},
                },
                {
                    "name": "priv",
                    "parameters": [],
                    "return_type": "void",
                    "visibility": "private",
                    "line_range": {"start": 40, "end": 50},
                },
            ],
            "fields": [],
            "imports": [],
        }
        result = format_full_table(data)
        assert "### Public Methods" in result
        assert "### Protected Methods" in result
        assert "### Private Methods" in result

    def test_static_method(self):
        data = {
            "file_path": "test.php",
            "classes": [
                {
                    "name": "Util",
                    "line_range": {"start": 1, "end": 20},
                    "class_type": "class",
                    "visibility": "public",
                }
            ],
            "methods": [
                {
                    "name": "create",
                    "parameters": [],
                    "return_type": "self",
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

    def test_module_level_functions(self):
        data = {
            "file_path": "test.php",
            "classes": [
                {
                    "name": "Inner",
                    "line_range": {"start": 20, "end": 50},
                    "class_type": "class",
                    "visibility": "public",
                }
            ],
            "methods": [
                {
                    "name": "helper",
                    "parameters": [],
                    "return_type": "void",
                    "visibility": "public",
                    "line_range": {"start": 5, "end": 10},
                }
            ],
            "fields": [],
            "imports": [],
        }
        result = format_full_table(data)
        assert "## Functions" in result
        assert "helper" in result

    def test_qualified_class_name_backslash(self):
        data = {
            "file_path": "test.php",
            "classes": [
                {
                    "name": "App\\Models\\User",
                    "line_range": {"start": 1, "end": 50},
                    "class_type": "class",
                    "visibility": "public",
                }
            ],
            "methods": [
                {
                    "name": "getName",
                    "parameters": [],
                    "return_type": "string",
                    "visibility": "public",
                    "line_range": {"start": 10, "end": 20},
                }
            ],
            "fields": [],
            "imports": [],
        }
        result = format_full_table(data)
        assert "User::getName" in result

    def test_top_level_functions_rendered_without_classes(self):
        # Regression: when classes=[], top-level functions MUST still produce a
        # "## Functions" section (the old code had `if not classes: return`).
        data = {
            "file_path": "test.php",
            "classes": [],
            "methods": [
                {
                    "name": "standalone",
                    "parameters": [],
                    "return_type": "void",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 5},
                    "complexity_score": 1,
                }
            ],
            "fields": [],
            "imports": [],
        }
        result = format_full_table(data)
        assert "## Functions" in result
        assert "standalone" in result

    def test_top_level_functions_exact_row_format(self):
        # Pin exact row content for binary_search_iterative (cx=4) and greet (cx=1)
        # so any formatter regression turns red immediately.
        data = {
            "file_path": "php_fns.php",
            "classes": [],
            "methods": [
                {
                    "name": "binary_search_iterative",
                    "parameters": [
                        {"name": "list", "type": "mixed"},
                        {"name": "target", "type": "mixed"},
                    ],
                    "return_type": "mixed",
                    "visibility": "public",
                    "line_range": {"start": 2, "end": 11},
                    "complexity_score": 4,
                },
                {
                    "name": "greet",
                    "parameters": [{"name": "name", "type": "mixed"}],
                    "return_type": "mixed",
                    "visibility": "public",
                    "line_range": {"start": 12, "end": 12},
                    "complexity_score": 1,
                },
            ],
            "fields": [],
            "imports": [],
        }
        result = format_full_table(data)
        # Header row
        assert "## Functions" in result
        assert "| Method | Signature | Vis | Lines | Cx | Doc |" in result
        # binary_search_iterative: exact complexity pin = 4
        assert (
            "| binary_search_iterative | ($list:mixed, $target:mixed):mixed | + | 2-11 | 4 | - |"
            in result
        )
        # greet: exact complexity pin = 1
        assert "| greet | ($name:mixed):mixed | + | 12-12 | 1 | - |" in result


class TestFormatCompactTable:
    def test_empty_data(self):
        result = format_compact_table({})
        assert "# " in result
        assert "## Info" in result

    def test_with_methods(self):
        data = {
            "file_path": "test.php",
            "methods": [
                {
                    "name": "foo",
                    "parameters": [],
                    "return_type": "void",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 5},
                }
            ],
            "fields": [],
            "statistics": {"method_count": 1, "field_count": 0},
            "classes": [
                {
                    "full_qualified_name": "App\\Test",
                }
            ],
        }
        result = format_compact_table(data)
        assert "## Methods" in result
        assert "foo" in result
        assert "App" in result

    def test_compact_method_with_parent(self):
        data = {
            "file_path": "test.php",
            "methods": [
                {
                    "name": "bar",
                    "parent_class": "Foo",
                    "parameters": [],
                    "return_type": "",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 5},
                }
            ],
            "fields": [],
        }
        result = format_compact_table(data)
        assert "Foo::bar" in result

    def test_compact_info_statistics(self):
        data = {
            "file_path": "test.php",
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 10, "field_count": 5},
            "classes": [],
        }
        result = format_compact_table(data)
        assert "| Methods | 10 |" in result
        assert "| Fields | 5 |" in result

    def test_doc_truncation(self):
        data = {
            "file_path": "test.php",
            "methods": [
                {
                    "name": "func",
                    "parameters": [],
                    "return_type": "",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 5},
                    "documentation": "A" * 30,
                }
            ],
            "fields": [],
        }
        result = format_compact_table(data)
        assert "..." in result
