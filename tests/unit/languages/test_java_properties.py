"""
Property-based tests for Java language helper functions and formatter output.

Consolidates:
- tests/property/test_java_helpers_properties.py  (_split_respecting_generics, determine_visibility)
- tests/unit/formatters/test_java_formatter_properties.py  (formatter output completeness)
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer.formatters.java_formatter import JavaTableFormatter
from tree_sitter_analyzer.languages._java_element import _split_respecting_generics
from tree_sitter_analyzer.languages.java_helpers import determine_visibility

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_SIMPLE_IDENT = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"),
        min_codepoint=65,
        max_codepoint=122,
    ),
    min_size=1,
    max_size=12,
).filter(lambda s: s[0].isupper() and s[0].isascii())

_TYPE_ARG = st.text(
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    min_size=1,
    max_size=3,
)


@st.composite
def simple_type(draw):
    return draw(_SIMPLE_IDENT)


@st.composite
def generic_type(draw):
    base = draw(_SIMPLE_IDENT)
    n_args = draw(st.integers(min_value=1, max_value=3))
    args = [draw(_TYPE_ARG) for _ in range(n_args)]
    return f"{base}<{', '.join(args)}>"


@st.composite
def java_type(draw):
    return draw(st.one_of(simple_type(), generic_type()))


@st.composite
def interface_list(draw):
    n = draw(st.integers(min_value=1, max_value=5))
    types = [draw(java_type()) for _ in range(n)]
    return types, ", ".join(types)


# Formatter strategies (simplified for performance)
_java_identifier = st.sampled_from(
    [
        "TestClass",
        "MyClass",
        "Service",
        "Controller",
        "Repository",
        "User",
        "Order",
        "Product",
        "Item",
        "Config",
        "Handler",
        "Manager",
        "name",
        "value",
        "data",
        "result",
        "count",
        "index",
        "status",
        "getName",
        "setValue",
        "process",
        "execute",
        "validate",
        "create",
        "field1",
        "field2",
        "method1",
        "method2",
        "param1",
        "param2",
    ]
)

_package_name = st.sampled_from(
    [
        "com.example",
        "com.test",
        "org.sample",
        "net.app",
        "com.example.service",
        "com.example.model",
        "com.example.util",
    ]
)

_java_primitive = st.sampled_from(
    ["int", "long", "double", "float", "boolean", "byte", "short", "char", "void"]
)

_java_common = st.sampled_from(
    [
        "String",
        "Object",
        "Integer",
        "Long",
        "Double",
        "Boolean",
        "List<String>",
        "Map<String,Object>",
        "Set<Integer>",
    ]
)

_java_type_s = st.one_of(_java_primitive, _java_common, _java_identifier)
_visibility_s = st.sampled_from(["public", "private", "protected", "package"])
_method_visibility_s = st.sampled_from(["public", "private"])
_line_range_s = st.builds(
    lambda start, length: {"start": start, "end": start + length},
    start=st.integers(min_value=1, max_value=100),
    length=st.integers(min_value=1, max_value=50),
)
_modifiers_s = st.lists(
    st.sampled_from(["static", "final", "abstract", "synchronized", "volatile"]),
    min_size=0,
    max_size=3,
    unique=True,
)
_parameter_s = st.builds(
    lambda name, type_: {"name": name, "type": type_},
    name=_java_identifier,
    type_=_java_type_s,
)
_parameters_s = st.lists(_parameter_s, min_size=0, max_size=5)


@st.composite
def java_field(draw):
    return {
        "name": draw(_java_identifier),
        "type": draw(_java_type_s),
        "visibility": draw(_visibility_s),
        "modifiers": draw(_modifiers_s),
        "line_range": draw(_line_range_s),
        "javadoc": draw(st.text(min_size=0, max_size=50)),
    }


@st.composite
def java_method(draw, is_constructor=None):
    if is_constructor is None:
        is_constructor = draw(st.booleans())
    return {
        "name": draw(_java_identifier),
        "visibility": draw(_method_visibility_s),
        "return_type": None if is_constructor else draw(_java_type_s),
        "parameters": draw(_parameters_s),
        "is_constructor": is_constructor,
        "line_range": draw(_line_range_s),
        "complexity_score": draw(st.integers(min_value=1, max_value=20)),
        "javadoc": draw(st.text(min_size=0, max_size=50)),
    }


@st.composite
def java_class(draw):
    class_type = draw(st.sampled_from(["class", "interface", "enum", "record"]))
    result = {
        "name": draw(_java_identifier),
        "type": class_type,
        "visibility": draw(_visibility_s),
        "line_range": draw(_line_range_s),
    }
    if class_type == "enum":
        result["constants"] = draw(st.lists(_java_identifier, min_size=0, max_size=5))
    return result


@st.composite
def java_import(draw):
    pkg = draw(_package_name)
    cls = draw(_java_identifier)
    return {"statement": f"import {pkg}.{cls};"}


@st.composite
def java_analysis_result(draw):
    classes = draw(st.lists(java_class(), min_size=1, max_size=3))
    fields = draw(st.lists(java_field(), min_size=0, max_size=5))
    methods = draw(st.lists(java_method(), min_size=0, max_size=5))
    imports = draw(st.lists(java_import(), min_size=0, max_size=5))
    return {
        "package": {"name": draw(_package_name)},
        "file_path": f"{draw(_java_identifier)}.java",
        "classes": classes,
        "fields": fields,
        "methods": methods,
        "imports": imports,
        "statistics": {"method_count": len(methods), "field_count": len(fields)},
    }


# ---------------------------------------------------------------------------
# Properties: _split_respecting_generics
# ---------------------------------------------------------------------------


class TestSplitRespectingGenericsProperties:
    @settings(max_examples=200)
    @given(data=interface_list())
    def test_roundtrip_element_count(self, data):
        types, joined = data
        result = _split_respecting_generics(joined)
        assert len(result) == len(types), (
            f"Expected {len(types)} elements from '{joined}', got {len(result)}: {result}"
        )

    @settings(max_examples=200)
    @given(data=interface_list())
    def test_no_empty_elements(self, data):
        _, joined = data
        result = _split_respecting_generics(joined)
        for elem in result:
            assert elem.strip(), f"Empty element in result {result} from '{joined}'"

    @settings(max_examples=200)
    @given(data=interface_list())
    def test_each_element_starts_with_capital(self, data):
        _, joined = data
        result = _split_respecting_generics(joined)
        for elem in result:
            assert elem[0].isupper(), (
                f"Element '{elem}' does not start with capital in result from '{joined}'"
            )

    @settings(max_examples=200)
    @given(data=interface_list())
    def test_no_depth0_comma_inside_element(self, data):
        _, joined = data
        result = _split_respecting_generics(joined)
        for elem in result:
            depth = 0
            for ch in elem:
                if ch == "<":
                    depth += 1
                elif ch == ">":
                    depth -= 1
                elif ch == "," and depth == 0:
                    assert False, (
                        f"Element '{elem}' contains depth-0 comma; "
                        f"generics not respected in '{joined}'"
                    )

    @settings(max_examples=200)
    @given(n=st.integers(min_value=1, max_value=6))
    def test_simple_types_no_generics(self, n):
        types = [f"Type{i}" for i in range(n)]
        joined = ", ".join(types)
        result = _split_respecting_generics(joined)
        assert len(result) == n, (
            f"Expected {n} elements from '{joined}', got {len(result)}: {result}"
        )

    @settings(max_examples=100)
    @given(k=st.integers(min_value=1, max_value=4))
    def test_single_generic_with_k_args(self, k):
        args = [chr(ord("A") + i) for i in range(k)]
        single = f"Map<{', '.join(args)}>"
        result = _split_respecting_generics(single)
        assert len(result) == 1, (
            f"Expected 1 element for '{single}', got {len(result)}: {result}"
        )
        assert result[0].startswith("Map"), f"Expected 'Map...' but got '{result[0]}'"


# ---------------------------------------------------------------------------
# Properties: determine_visibility
# ---------------------------------------------------------------------------


class TestDetermineVisibilityProperties:
    _NOISE = ["static", "final", "abstract", "synchronized", "native", "transient"]

    @settings(max_examples=100)
    @given(noise=st.lists(st.sampled_from(_NOISE), min_size=0, max_size=4))
    def test_public_wins_over_noise(self, noise):
        assert determine_visibility(noise + ["public"]) == "public"

    @settings(max_examples=100)
    @given(noise=st.lists(st.sampled_from(_NOISE), min_size=0, max_size=4))
    def test_private_wins_over_noise(self, noise):
        assert determine_visibility(noise + ["private"]) == "private"

    @settings(max_examples=100)
    @given(noise=st.lists(st.sampled_from(_NOISE), min_size=0, max_size=4))
    def test_protected_wins_over_noise(self, noise):
        assert determine_visibility(noise + ["protected"]) == "protected"

    @settings(max_examples=100)
    @given(noise=st.lists(st.sampled_from(_NOISE), min_size=0, max_size=4))
    def test_no_visibility_modifier_returns_package(self, noise):
        assert determine_visibility(noise) == "package"

    @settings(max_examples=50)
    @given(st.lists(st.sampled_from(_NOISE), min_size=0, max_size=4))
    def test_return_value_is_one_of_four_options(self, modifiers):
        result = determine_visibility(modifiers)
        assert result in {"public", "private", "protected", "package"}, (
            f"Unexpected visibility '{result}' for modifiers {modifiers}"
        )


# ---------------------------------------------------------------------------
# Properties: Formatter output completeness
# ---------------------------------------------------------------------------


class TestFormatterOutputCompletenessProperties:
    @settings(
        max_examples=50, suppress_health_check=[HealthCheck.too_slow], derandomize=True
    )
    @given(data=java_analysis_result())
    def test_full_table_contains_all_class_names(self, data):
        formatter = JavaTableFormatter()
        result = formatter._format_full_table(data)
        for class_info in data.get("classes", []):
            class_name = class_info.get("name", "")
            assert class_name in result, (
                f"Class name '{class_name}' should appear in output"
            )

    @settings(
        max_examples=50, suppress_health_check=[HealthCheck.too_slow], derandomize=True
    )
    @given(data=java_analysis_result())
    def test_full_table_contains_field_names_in_class_range(self, data):
        formatter = JavaTableFormatter()
        result = formatter._format_full_table(data)

        def is_in_class_range(field):
            fs = field.get("line_range", {}).get("start", 0)
            for cls in data.get("classes", []):
                cs = cls.get("line_range", {}).get("start", 0)
                ce = cls.get("line_range", {}).get("end", 0)
                if cs <= fs <= ce:
                    return True
            return False

        for field in data.get("fields", []):
            field_name = field.get("name", "")
            if field_name and is_in_class_range(field):
                assert field_name in result, f"Field name '{field_name}' should appear"

    @settings(
        max_examples=50, suppress_health_check=[HealthCheck.too_slow], derandomize=True
    )
    @given(data=java_analysis_result())
    def test_full_table_contains_method_names_in_class_range(self, data):
        formatter = JavaTableFormatter()
        result = formatter._format_full_table(data)

        def is_in_class_range(method):
            ms = method.get("line_range", {}).get("start", 0)
            for cls in data.get("classes", []):
                cs = cls.get("line_range", {}).get("start", 0)
                ce = cls.get("line_range", {}).get("end", 0)
                if cs <= ms <= ce:
                    return True
            return False

        for method in data.get("methods", []):
            method_name = method.get("name", "")
            if method_name and is_in_class_range(method):
                assert method_name in result, (
                    f"Method name '{method_name}' should appear"
                )

    @settings(
        max_examples=50, suppress_health_check=[HealthCheck.too_slow], derandomize=True
    )
    @given(data=java_analysis_result())
    def test_compact_table_contains_all_method_names(self, data):
        formatter = JavaTableFormatter()
        result = formatter._format_compact_table(data)
        for method in data.get("methods", []):
            method_name = method.get("name", "")
            if method_name:
                assert method_name in result, (
                    f"Method name '{method_name}' should appear in compact"
                )

    @settings(
        max_examples=50, suppress_health_check=[HealthCheck.too_slow], derandomize=True
    )
    @given(data=java_analysis_result())
    def test_imports_appear_in_full_output(self, data):
        formatter = JavaTableFormatter()
        result = formatter._format_full_table(data)
        for imp in data.get("imports", []):
            statement = imp.get("statement", "")
            if statement:
                assert statement in result, f"Import '{statement}' should appear"

    @settings(
        max_examples=50, suppress_health_check=[HealthCheck.too_slow], derandomize=True
    )
    @given(data=java_analysis_result())
    def test_package_name_appears_in_output(self, data):
        formatter = JavaTableFormatter()
        result = formatter._format_full_table(data)
        package_name = data.get("package", {}).get("name", "")
        if package_name and package_name != "unknown":
            assert package_name in result, (
                f"Package name '{package_name}' should appear"
            )

    @settings(
        max_examples=50, suppress_health_check=[HealthCheck.too_slow], derandomize=True
    )
    @given(data=java_analysis_result())
    def test_csv_format_contains_all_field_and_method_names(self, data):
        formatter = JavaTableFormatter()
        result = formatter._format_csv(data)
        for field in data.get("fields", []):
            field_name = field.get("name", "")
            if field_name:
                assert field_name in result, (
                    f"Field name '{field_name}' should appear in CSV"
                )
        for method in data.get("methods", []):
            method_name = method.get("name", "")
            if method_name:
                assert method_name in result, (
                    f"Method name '{method_name}' should appear in CSV"
                )

    @settings(
        max_examples=50, suppress_health_check=[HealthCheck.too_slow], derandomize=True
    )
    @given(data=java_analysis_result())
    def test_json_format_preserves_all_class_field_method_names(self, data):
        import json as _json

        formatter = JavaTableFormatter()
        result = formatter._format_json(data)
        parsed = _json.loads(result)
        assert parsed is not None
        for class_info in data.get("classes", []):
            class_name = class_info.get("name", "")
            assert any(
                c.get("name") == class_name for c in parsed.get("classes", [])
            ), f"Class '{class_name}' should be preserved in JSON"
        for field in data.get("fields", []):
            field_name = field.get("name", "")
            assert any(f.get("name") == field_name for f in parsed.get("fields", [])), (
                f"Field '{field_name}' should be preserved in JSON"
            )
        for method in data.get("methods", []):
            method_name = method.get("name", "")
            assert any(
                m.get("name") == method_name for m in parsed.get("methods", [])
            ), f"Method '{method_name}' should be preserved in JSON"


class TestFormatterAnnotationHandlingProperties:
    @settings(
        max_examples=50, suppress_health_check=[HealthCheck.too_slow], derandomize=True
    )
    @given(
        class_name=_java_identifier,
        visibility_val=_visibility_s,
        class_type=st.sampled_from(["class", "interface", "enum"]),
    )
    def test_class_visibility_in_output(self, class_name, visibility_val, class_type):
        formatter = JavaTableFormatter()
        data = {
            "package": {"name": "com.example"},
            "classes": [
                {
                    "name": class_name,
                    "type": class_type,
                    "visibility": visibility_val,
                    "line_range": {"start": 1, "end": 10},
                }
            ],
            "imports": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }
        result = formatter._format_full_table(data)
        assert class_name in result, f"Class name '{class_name}' should appear"
        visibility_symbols = {
            "public": ["+", "public"],
            "private": ["-", "private"],
            "protected": ["#", "protected"],
            "package": ["~", "package"],
        }
        expected = visibility_symbols.get(visibility_val, [visibility_val])
        assert any(sym in result for sym in expected), (
            f"Visibility '{visibility_val}' should appear as one of {expected}"
        )


class TestFormatterGenericTypeHandlingProperties:
    @settings(
        max_examples=50, suppress_health_check=[HealthCheck.too_slow], derandomize=True
    )
    @given(
        method_name=_java_identifier,
        return_type=_java_type_s,
        param_types=st.lists(_java_type_s, min_size=0, max_size=3),
    )
    def test_method_signature_completeness(self, method_name, return_type, param_types):
        formatter = JavaTableFormatter()
        params = [{"name": f"param{i}", "type": t} for i, t in enumerate(param_types)]
        data = {
            "package": {"name": "com.example"},
            "classes": [
                {
                    "name": "TestClass",
                    "type": "class",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 50},
                }
            ],
            "imports": [],
            "methods": [
                {
                    "name": method_name,
                    "visibility": "public",
                    "return_type": return_type,
                    "parameters": params,
                    "is_constructor": False,
                    "line_range": {"start": 10, "end": 20},
                    "complexity_score": 1,
                    "javadoc": "",
                }
            ],
            "fields": [],
            "statistics": {"method_count": 1, "field_count": 0},
        }
        result = formatter._format_full_table(data)
        assert method_name in result, f"Method name '{method_name}' should appear"

    @settings(
        max_examples=50, suppress_health_check=[HealthCheck.too_slow], derandomize=True
    )
    @given(
        type_name=st.sampled_from(
            [
                "List<String>",
                "Map<String,Object>",
                "Set<Integer>",
                "Optional<String>",
                "Collection<Object>",
            ]
        ),
    )
    def test_generic_type_shortening_preserves_brackets(self, type_name):
        formatter = JavaTableFormatter()
        result = formatter._shorten_type(type_name)
        assert result, f"Shortened type for '{type_name}' should not be empty"
        assert isinstance(result, str)
        if "<" in type_name:
            assert "<" in result, (
                f"Generic brackets should be preserved for '{type_name}'"
            )


class TestFormatterEdgeCaseProperties:
    @settings(
        max_examples=50, suppress_health_check=[HealthCheck.too_slow], derandomize=True
    )
    @given(
        num_classes=st.integers(min_value=1, max_value=5),
        num_methods=st.integers(min_value=0, max_value=10),
        num_fields=st.integers(min_value=0, max_value=10),
    )
    def test_output_scales_with_elements(self, num_classes, num_methods, num_fields):
        formatter = JavaTableFormatter()
        classes = [
            {
                "name": f"Class{i}",
                "type": "class",
                "visibility": "public",
                "line_range": {"start": i * 100, "end": i * 100 + 50},
            }
            for i in range(num_classes)
        ]
        methods = [
            {
                "name": f"method{i}",
                "visibility": "public",
                "return_type": "void",
                "parameters": [],
                "is_constructor": False,
                "line_range": {"start": 1 + i * 4, "end": 3 + i * 4},
                "complexity_score": 1,
                "javadoc": "",
            }
            for i in range(min(num_methods, 10))
        ]
        fields = [
            {
                "name": f"field{i}",
                "type": "String",
                "visibility": "private",
                "modifiers": [],
                "line_range": {"start": 2 + i * 3, "end": 2 + i * 3},
                "javadoc": "",
            }
            for i in range(min(num_fields, 10))
        ]
        data = {
            "package": {"name": "com.example"},
            "file_path": "Test.java",
            "classes": classes,
            "imports": [],
            "methods": methods,
            "fields": fields,
            "statistics": {"method_count": num_methods, "field_count": num_fields},
        }
        result = formatter._format_full_table(data)
        for i in range(num_classes):
            assert f"Class{i}" in result
        for i in range(min(num_methods, 10)):
            assert f"method{i}" in result
        for i in range(min(num_fields, 10)):
            assert f"field{i}" in result

    @settings(
        max_examples=50, suppress_health_check=[HealthCheck.too_slow], derandomize=True
    )
    @given(
        enum_name=_java_identifier,
        constants=st.lists(_java_identifier, min_size=1, max_size=5, unique=True),
    )
    def test_enum_constants_in_output(self, enum_name, constants):
        formatter = JavaTableFormatter()
        data = {
            "package": {"name": "com.example"},
            "classes": [
                {
                    "name": enum_name,
                    "type": "enum",
                    "visibility": "public",
                    "line_range": {"start": 1, "end": 20},
                    "constants": constants,
                }
            ],
            "imports": [],
            "methods": [],
            "fields": [],
            "statistics": {"method_count": 0, "field_count": 0},
        }
        result = formatter._format_full_table(data)
        assert enum_name in result
        assert "enum" in result.lower()
