"""Test helper: encode small SCIP indexes (protobuf wire format) by hand.

Only the fields :mod:`callers_scip_index` reads are written. Field numbers follow
upstream ``scip.proto``.
"""

from __future__ import annotations

from collections.abc import Iterable


def varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def field_bytes(number: int, payload: bytes) -> bytes:
    return varint(number << 3 | 2) + varint(len(payload)) + payload


def field_varint(number: int, value: int) -> bytes:
    return varint(number << 3) + varint(value)


def text(number: int, value: str) -> bytes:
    return field_bytes(number, value.encode("utf-8"))


def packed(number: int, values: Iterable[int]) -> bytes:
    return field_bytes(number, b"".join(varint(v) for v in values))


def occurrence(
    line: int,
    col: int,
    end_col: int,
    symbol: str,
    roles: int = 0,
    enclosing: tuple[int, int, int, int] | None = None,
) -> bytes:
    out = packed(1, (line, col, end_col)) + text(2, symbol)
    if roles:
        out += field_varint(3, roles)
    if enclosing:
        out += packed(7, enclosing)
    return out


def relationship(symbol: str, *, implementation: bool = False) -> bytes:
    out = text(1, symbol)
    if implementation:
        out += field_varint(3, 1)
    return out


def symbol_info(
    symbol: str, kind: int = 0, doc: str = "", rels: Iterable[bytes] = ()
) -> bytes:
    out = text(1, symbol)
    if doc:
        out += text(3, doc)
    for rel in rels:
        out += field_bytes(4, rel)
    if kind:
        out += field_varint(5, kind)
    return out


def document(
    path: str, occurrences: Iterable[bytes], symbols: Iterable[bytes] = ()
) -> bytes:
    out = text(1, path)
    for occ in occurrences:
        out += field_bytes(2, occ)
    for info in symbols:
        out += field_bytes(3, info)
    return out


def index(
    documents: Iterable[bytes],
    tool: tuple[str, str] = ("scip-typescript", "0.6.1"),
    external: Iterable[bytes] = (),
) -> bytes:
    tool_info = text(1, tool[0]) + text(2, tool[1])
    out = field_bytes(1, field_bytes(2, tool_info))
    for doc in documents:
        out += field_bytes(2, doc)
    for info in external:
        out += field_bytes(3, info)
    return out


PKG = "scip-typescript npm fx 1.0.0 "


def global_symbol(descriptors: str) -> str:
    return PKG + descriptors
