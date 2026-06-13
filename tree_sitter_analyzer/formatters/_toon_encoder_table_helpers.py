"""Shared table-encoding helpers for :mod:`toon_encoder`."""

from collections.abc import Callable
from typing import Any

EncodeValue = Callable[[Any, set[int]], str]
InferSchema = Callable[[list[dict[str, Any]]], list[str]]


def union_schema(items: list[dict[str, Any]]) -> list[str]:
    """Union of all rows' keys, in first-seen order (issue #637).

    A header built from only the first row's keys silently drops every
    field that later rows carry (e.g. 49 caller ``body`` fields behind a
    ghost first row).  The union keeps the table lossless; rows missing a
    key render an empty cell — same representation the row encoder already
    used for schema keys absent from a row.
    """
    schema: list[str] = []
    seen: set[str] = set()
    for item in items:
        for key in item:
            if key not in seen:
                seen.add(key)
                schema.append(key)
    return schema


def encode_public_array_table(
    items: list[dict[str, Any]],
    schema: list[str] | None,
    indent: int,
    delimiter: str,
    encode_value: EncodeValue,
    infer_schema: InferSchema,
) -> str:
    """Encode the public ``ToonEncoder.encode_array_table`` payload."""
    if not items:
        return "[]"

    resolved_schema = infer_schema(items) if schema is None else schema
    indent_str = "  " * indent
    seen_ids: set[int] = set()
    return "\n".join(
        encode_array_table_lines(
            items,
            resolved_schema,
            delimiter,
            indent_str,
            encode_value,
            seen_ids,
        )
    )


def encode_array_table_lines(
    items: list[dict[str, Any]],
    schema: list[str],
    delimiter: str,
    indent_str: str,
    encode_value: EncodeValue,
    seen_ids: set[int],
) -> list[str]:
    """Encode an array of dictionaries as TOON table lines."""
    schema_parts = build_table_schema_parts(items, schema, delimiter)
    schema_str = delimiter.join(schema_parts)
    lines = [f"{indent_str}[{len(items)}]{{{schema_str}}}:"]
    lines.extend(
        encode_table_rows(
            items,
            schema,
            delimiter,
            indent_str,
            encode_value,
            seen_ids,
        )
    )
    return lines


def build_table_schema_parts(
    items: list[dict[str, Any]],
    schema: list[str],
    delimiter: str,
) -> list[str]:
    """Build TOON table schema labels with compact nested value annotations.

    The annotation sample for each key comes from the first row that HAS
    the key — with a union schema (#637) the first row may lack it.
    """
    schema_parts: list[str] = []
    for key in schema:
        sample_value = next((item[key] for item in items if key in item), None)
        if isinstance(sample_value, tuple | list) and len(sample_value) == 2:
            schema_parts.append(f"{key}(a,b)")
        elif isinstance(sample_value, dict):
            dict_keys = delimiter.join(sample_value.keys())
            schema_parts.append(f"{key}{{{dict_keys}}}")
        else:
            schema_parts.append(key)
    return schema_parts


def encode_table_rows(
    items: list[dict[str, Any]],
    schema: list[str],
    delimiter: str,
    indent_str: str,
    encode_value: EncodeValue,
    seen_ids: set[int],
) -> list[str]:
    """Encode table rows using an existing value encoder and circular-ref set."""
    return [
        f"{indent_str}  "
        + delimiter.join(
            _encode_table_cell(item.get(key, ""), delimiter, encode_value, seen_ids)
            for key in schema
        )
        for item in items
    ]


def _encode_table_cell(
    value: Any,
    delimiter: str,
    encode_value: EncodeValue,
    seen_ids: set[int],
) -> str:
    """Encode a single TOON table cell."""
    if isinstance(value, tuple | list) and len(value) == 2:
        return f"({value[0]},{value[1]})"
    if isinstance(value, dict):
        dict_values = delimiter.join(
            str(encode_value(v, seen_ids)) for v in value.values()
        )
        return f"({dict_values})"
    return encode_value(value, seen_ids)
