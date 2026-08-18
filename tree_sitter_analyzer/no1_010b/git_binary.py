"""Integrity checks for canonical Git binary-patch sections."""

from __future__ import annotations

import re
import zlib

GIT_BASE85_ALPHABET = (
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    "!#$%&()*+-;<=>?@^_`{|}~"
)
FULL_INDEX_HEADER_RE = re.compile(
    r"^index ([0-9a-f]{40})\.\.([0-9a-f]{40})(?: [0-7]{6})?$"
)
_BINARY_SIZE_RE = re.compile(r"^(?:literal|delta) ([0-9]+)$")
_BASE85_VALUES = {
    character: index for index, character in enumerate(GIT_BASE85_ALPHABET)
}


class GitBinaryError(ValueError):
    """A binary section that Git cannot decode or apply."""


class GitBinaryBoundError(GitBinaryError):
    """A decoded binary result that exceeds the registered output bound."""


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


def _validate_delta(data: bytes, max_output: int) -> None:
    source_size, cursor = _read_delta_varint(data, 0)
    result_size, cursor = _read_delta_varint(data, cursor)
    if result_size > max_output:
        raise GitBinaryBoundError("delta result exceeds output bound")
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
        if produced > result_size:
            raise GitBinaryError("delta output exceeds declared size")
    if produced != result_size:
        raise GitBinaryError("delta output is shorter than declared size")


def validate_binary_section(
    kind: str, declared_size: int, encoded_lines: list[str], max_output: int
) -> None:
    """Decode one Git binary section and verify zlib/delta integrity."""

    compressed = b"".join(_decode_line(line) for line in encoded_lines)
    inflater = zlib.decompressobj()
    try:
        data = inflater.decompress(compressed, max_output + 1)
    except zlib.error as exc:
        raise GitBinaryError("invalid zlib payload") from exc
    if len(data) > max_output:
        raise GitBinaryError("inflated binary instructions exceed bound")
    if inflater.unconsumed_tail or not inflater.eof or inflater.unused_data:
        raise GitBinaryError("incomplete or concatenated zlib payload")
    if len(data) != declared_size:
        raise GitBinaryError("binary section size disagrees with header")
    if kind == "literal":
        return
    _validate_delta(data, max_output)


def _data_line_is_canonical(line: str) -> bool:
    if not line or not line[0].isalpha() or not line[0].isascii():
        return False
    decoded_count = (
        ord(line[0]) - ord("A") + 1
        if line[0].isupper()
        else ord(line[0]) - ord("a") + 27
    )
    encoded_count = ((decoded_count + 3) // 4) * 5
    return len(line) == encoded_count + 1 and all(
        character in _BASE85_VALUES for character in line[1:]
    )


def binary_patch_state(lines: list[str], max_output: int) -> tuple[set[int], bool]:
    """Validate and locate bounded canonical ``git diff --binary`` payloads."""

    indexes: set[int] = set()
    git_header_seen = full_index_seen = False
    cursor = 0
    while cursor < len(lines):
        line = lines[cursor]
        if line.startswith("diff --git "):
            git_header_seen = True
            full_index_seen = False
            cursor += 1
            continue
        if FULL_INDEX_HEADER_RE.fullmatch(line):
            full_index_seen = True
            cursor += 1
            continue
        if line != "GIT binary patch":
            cursor += 1
            continue
        if not git_header_seen:
            raise GitBinaryError("binary patch has no Git header")
        if not full_index_seen:
            raise GitBinaryError("binary patch requires a full index line")
        indexes.add(cursor)
        cursor += 1
        section_count = 0
        while cursor < len(lines) and not lines[cursor].startswith("diff --git "):
            size_match = _BINARY_SIZE_RE.fullmatch(lines[cursor])
            if size_match is None:
                raise GitBinaryError("non-canonical binary patch size")
            raw_size = size_match.group(1)
            if len(raw_size) > len(str(max_output)):
                raise GitBinaryBoundError("binary patch size exceeds numeric bound")
            declared_size = int(raw_size)
            if declared_size > max_output:
                raise GitBinaryBoundError("binary patch output exceeds max bytes")
            kind = lines[cursor].split(" ", 1)[0]
            indexes.add(cursor)
            section_count += 1
            cursor += 1
            data_lines: list[str] = []
            while cursor < len(lines) and lines[cursor]:
                if not _data_line_is_canonical(lines[cursor]):
                    raise GitBinaryError("non-canonical binary patch payload")
                data_lines.append(lines[cursor])
                indexes.add(cursor)
                cursor += 1
            if not data_lines or cursor >= len(lines):
                raise GitBinaryError("incomplete binary patch payload")
            try:
                validate_binary_section(kind, declared_size, data_lines, max_output)
            except GitBinaryBoundError:
                raise
            except GitBinaryError as exc:
                raise GitBinaryError("corrupt binary patch payload") from exc
            indexes.add(cursor)
            cursor += 1
        if section_count == 0:
            raise GitBinaryError("binary patch has no payload")
    return indexes, bool(indexes)
