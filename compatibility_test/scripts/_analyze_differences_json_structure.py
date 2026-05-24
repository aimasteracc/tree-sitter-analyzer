"""JSON structure comparison helpers for analyze_differences."""

from typing import Any

from compatibility_test.scripts._analyze_differences_json_severity import (
    FieldSeverityFunc,
)


def compare_json_structure(
    obj_a: Any,
    obj_b: Any,
    path: str,
    field_severity: FieldSeverityFunc,
) -> list[dict[str, Any]]:
    """Recursively compare JSON structures."""
    if not isinstance(obj_a, type(obj_b)) and not isinstance(obj_b, type(obj_a)):
        return [_type_change(path, obj_a, obj_b)]

    if isinstance(obj_a, dict):
        return _compare_dict_structure(obj_a, obj_b, path, field_severity)

    if isinstance(obj_a, list):
        return _compare_list_structure(obj_a, obj_b, path, field_severity)

    return []


def _compare_dict_structure(
    obj_a: dict[str, Any],
    obj_b: dict[str, Any],
    path: str,
    field_severity: FieldSeverityFunc,
) -> list[dict[str, Any]]:
    differences = []
    keys_a = set(obj_a.keys())
    keys_b = set(obj_b.keys())

    differences.extend(_added_key_diffs(obj_b, keys_b - keys_a, path))
    differences.extend(_removed_key_diffs(obj_a, keys_a - keys_b, path))
    differences.extend(
        _common_key_diffs(obj_a, obj_b, keys_a & keys_b, path, field_severity)
    )
    return differences


def _compare_list_structure(
    obj_a: list[Any],
    obj_b: list[Any],
    path: str,
    field_severity: FieldSeverityFunc,
) -> list[dict[str, Any]]:
    differences = []
    if len(obj_a) != len(obj_b):
        differences.append(_list_length_change(obj_a, obj_b, path))

    for index in range(min(len(obj_a), len(obj_b))):
        new_path = f"{path}[{index}]"
        differences.extend(
            _list_item_diffs(obj_a[index], obj_b[index], new_path, field_severity)
        )
    return differences


def _common_key_diffs(
    obj_a: dict[str, Any],
    obj_b: dict[str, Any],
    common_keys: set[str],
    path: str,
    field_severity: FieldSeverityFunc,
) -> list[dict[str, Any]]:
    differences = []
    for key in common_keys:
        new_path = f"{path}.{key}" if path else key
        if obj_a[key] == obj_b[key]:
            continue
        differences.extend(
            _changed_common_key_diffs(obj_a, obj_b, key, new_path, field_severity)
        )
    return differences


def _changed_common_key_diffs(
    obj_a: dict[str, Any],
    obj_b: dict[str, Any],
    key: str,
    path: str,
    field_severity: FieldSeverityFunc,
) -> list[dict[str, Any]]:
    if isinstance(obj_a[key], dict | list):
        return compare_json_structure(obj_a[key], obj_b[key], path, field_severity)
    return [_value_change(key, path, obj_a[key], obj_b[key], field_severity)]


def _list_item_diffs(
    item_a: Any, item_b: Any, path: str, field_severity: FieldSeverityFunc
) -> list[dict[str, Any]]:
    if item_a == item_b:
        return []
    if isinstance(item_a, dict | list):
        return compare_json_structure(item_a, item_b, path, field_severity)
    return [
        {
            "type": "list_item_changed",
            "path": path,
            "old_value": item_a,
            "new_value": item_b,
            "severity": "medium",
        }
    ]


def _added_key_diffs(
    obj_b: dict[str, Any], added_keys: set[str], path: str
) -> list[dict[str, Any]]:
    return [
        {
            "type": "key_added",
            "path": f"{path}.{key}" if path else key,
            "value": obj_b[key],
            "severity": "low",
        }
        for key in added_keys
    ]


def _removed_key_diffs(
    obj_a: dict[str, Any], removed_keys: set[str], path: str
) -> list[dict[str, Any]]:
    return [
        {
            "type": "key_removed",
            "path": f"{path}.{key}" if path else key,
            "value": obj_a[key],
            "severity": "high",
        }
        for key in removed_keys
    ]


def _list_length_change(
    obj_a: list[Any], obj_b: list[Any], path: str
) -> dict[str, Any]:
    return {
        "type": "list_length_changed",
        "path": path,
        "old_length": len(obj_a),
        "new_length": len(obj_b),
        "severity": "medium",
    }


def _type_change(path: str, obj_a: Any, obj_b: Any) -> dict[str, Any]:
    return {
        "type": "type_change",
        "path": path,
        "old_type": type(obj_a).__name__,
        "new_type": type(obj_b).__name__,
        "severity": "high",
    }


def _value_change(
    key: str,
    path: str,
    old_value: Any,
    new_value: Any,
    field_severity: FieldSeverityFunc,
) -> dict[str, Any]:
    return {
        "type": "value_changed",
        "path": path,
        "old_value": old_value,
        "new_value": new_value,
        "severity": field_severity(key, old_value, new_value),
    }
