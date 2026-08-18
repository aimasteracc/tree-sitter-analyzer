"""Integrity checks for canonical Git binary-patch sections."""

from __future__ import annotations

import zlib

GIT_BASE85_ALPHABET = (
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    "!#$%&()*+-;<=>?@^_`{|}~"
)
_BASE85_VALUES = {
    character: index for index, character in enumerate(GIT_BASE85_ALPHABET)
}


class GitBinaryError(ValueError):
    """A binary section that Git cannot decode or apply."""


def _decode_line(line: str) -> bytes:
    decoded_count = (
        ord(line[0]) - ord("A") + 1
        if line[0].isupper()
        else ord(line[0]) - ord("a") + 27
    )
    encoded = line[1:]
    decoded = bytearray()
    for start in range(0, len(encoded), 5):
        value = 0
        for character in encoded[start : start + 5]:
            value = value * 85 + _BASE85_VALUES[character]
        if value > 0xFFFFFFFF:
            raise GitBinaryError("Git base85 group overflows 32 bits")
        decoded.extend(value.to_bytes(4, "big"))
    if any(decoded[decoded_count:]):
        raise GitBinaryError("nonzero Git base85 padding")
    return bytes(decoded[:decoded_count])


def _read_delta_varint(data: bytes, cursor: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while cursor < len(data) and shift <= 63:
        byte = data[cursor]
        cursor += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, cursor
        shift += 7
    raise GitBinaryError("invalid delta size header")


def _validate_delta(data: bytes, declared_size: int) -> None:
    source_size, cursor = _read_delta_varint(data, 0)
    result_size, cursor = _read_delta_varint(data, cursor)
    if result_size != declared_size:
        raise GitBinaryError("delta result size disagrees with header")
    produced = 0
    while cursor < len(data):
        command = data[cursor]
        cursor += 1
        if command & 0x80:
            offset = size = 0
            for bit, shift in zip((1, 2, 4, 8), (0, 8, 16, 24), strict=True):
                if command & bit:
                    if cursor >= len(data):
                        raise GitBinaryError("truncated delta copy offset")
                    offset |= data[cursor] << shift
                    cursor += 1
            for bit, shift in zip((0x10, 0x20, 0x40), (0, 8, 16), strict=True):
                if command & bit:
                    if cursor >= len(data):
                        raise GitBinaryError("truncated delta copy size")
                    size |= data[cursor] << shift
                    cursor += 1
            size = size or 0x10000
            if offset + size > source_size:
                raise GitBinaryError("delta copy exceeds source size")
            produced += size
        elif command:
            if cursor + command > len(data):
                raise GitBinaryError("truncated delta insert")
            cursor += command
            produced += command
        else:
            raise GitBinaryError("invalid zero delta command")
        if produced > declared_size:
            raise GitBinaryError("delta output exceeds declared size")
    if produced != declared_size:
        raise GitBinaryError("delta output is shorter than declared size")


def validate_binary_section(
    kind: str, declared_size: int, encoded_lines: list[str], max_output: int
) -> None:
    """Decode one Git binary section and verify zlib/delta integrity."""

    compressed = b"".join(_decode_line(line) for line in encoded_lines)
    inflater = zlib.decompressobj()
    try:
        data = inflater.decompress(compressed, max_output * 2 + 65)
    except zlib.error as exc:
        raise GitBinaryError("invalid zlib payload") from exc
    if len(data) > max_output * 2 + 64:
        raise GitBinaryError("inflated binary instructions exceed bound")
    if inflater.unconsumed_tail or not inflater.eof or inflater.unused_data:
        raise GitBinaryError("incomplete or concatenated zlib payload")
    if kind == "literal":
        if len(data) != declared_size:
            raise GitBinaryError("literal size disagrees with header")
        return
    _validate_delta(data, declared_size)
