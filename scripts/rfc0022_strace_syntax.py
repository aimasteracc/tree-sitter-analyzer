#!/usr/bin/env python3
"""Strict lexical helpers for hostile strace argument text."""

from __future__ import annotations

import os
import re

from rfc0022_strace_model import AuthorityError

_FD_BASE = re.compile(r"(?:AT_FDCWD|-?[0-9]+)")
_FD_WITH_ANNOTATION = re.compile(r"(?:AT_FDCWD|-?[0-9]+)<(?!<)")
_SOCKET_ENVELOPE = re.compile(
    r"(?:UNIX(?:-STREAM|-DGRAM)?|"
    r"(?:TCP|UDP|UDPLITE|DCCP|SCTP|PING|RAW)(?:v6)?|"
    r"L2TP/IP(?:v6)?|NETLINK):\["
)
_NAMED_ESCAPES = frozenset('\\"abtnvfr')
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
_OCTAL_DIGITS = frozenset("01234567")


def _escape_end(text: str, index: int) -> int:
    if index + 1 >= len(text):
        raise AuthorityError("truncated strace descriptor escape")
    escaped = text[index + 1]
    if escaped in _NAMED_ESCAPES:
        return index + 2
    if escaped in _OCTAL_DIGITS:
        end = index + 2
        while end < len(text) and end < index + 4 and text[end] in _OCTAL_DIGITS:
            end += 1
        return end
    if (
        escaped == "x"
        and index + 3 < len(text)
        and text[index + 2] in _HEX_DIGITS
        and text[index + 3] in _HEX_DIGITS
    ):
        return index + 4
    raise AuthorityError("invalid strace descriptor escape")


def _decode_unquoted(text: str) -> str:
    decoded = bytearray()
    named = {
        "a": 0x07,
        "b": 0x08,
        "t": 0x09,
        "n": 0x0A,
        "v": 0x0B,
        "f": 0x0C,
        "r": 0x0D,
        '"': 0x22,
        "\\": 0x5C,
    }
    index = 0
    while index < len(text):
        char = text[index]
        if char != "\\":
            code = ord(char)
            if code < 0x20 or code > 0x7E:
                raise AuthorityError("raw non-ASCII/control descriptor byte")
            decoded.append(code)
            index += 1
            continue
        end = _escape_end(text, index)
        escaped = text[index + 1 : end]
        if escaped[0] in named:
            decoded.append(named[escaped[0]])
        elif escaped[0] == "x":
            decoded.append(int(escaped[1:], 16))
        else:
            byte = int(escaped, 8)
            if byte > 0xFF:
                raise AuthorityError("out-of-range strace descriptor escape")
            decoded.append(byte)
        index = end
    if 0 in decoded:
        raise AuthorityError("NUL in descriptor annotation")
    raw = bytes(decoded)
    try:
        return os.fsdecode(raw)
    except UnicodeDecodeError:
        return raw.decode("utf-8", "surrogateescape")


def _validate_annotation(annotation: str, *, socket: bool) -> None:
    if not annotation:
        raise AuthorityError("empty descriptor annotation")
    _decode_unquoted(annotation)
    if socket:
        head = _SOCKET_ENVELOPE.match(annotation)
        if head is None or head.end() == len(annotation) - 1:
            raise AuthorityError("empty socket descriptor payload")


def _descriptor_boundary(text: str, index: int) -> bool:
    return index == 0 or not (text[index - 1].isalnum() or text[index - 1] == "_")


def _scan_descriptor(text: str, start: int) -> tuple[int, str]:
    head = _FD_WITH_ANNOTATION.match(text, start)
    if head is None or not _descriptor_boundary(text, start):
        raise AuthorityError("expected decoded descriptor annotation")
    body_start = head.end()
    socket = _SOCKET_ENVELOPE.match(text, body_start) is not None
    angle_depth = 1
    bracket_depth = 0
    socket_closed_at: int | None = None
    quoted = False
    index = body_start
    while index < len(text):
        char = text[index]
        if char == "\\":
            index = _escape_end(text, index)
            continue
        if quoted:
            if char == '"':
                quoted = False
            index += 1
            continue
        if char == '"':
            if not socket:
                raise AuthorityError("unescaped quote in descriptor annotation")
            quoted = True
            index += 1
            continue
        if socket and socket_closed_at is not None and char != ">":
            raise AuthorityError("trailing socket descriptor structure")
        if socket and char == "[":
            bracket_depth += 1
            index += 1
            continue
        if socket and char == "]":
            if bracket_depth == 0:
                raise AuthorityError("unbalanced socket descriptor annotation")
            bracket_depth -= 1
            if bracket_depth == 0:
                socket_closed_at = index
            index += 1
            continue
        if socket and char == "-" and index + 1 < len(text) and text[index + 1] == ">":
            index += 2
            continue
        if char == "<":
            if socket:
                raise AuthorityError("raw angle in socket descriptor annotation")
            angle_depth += 1
            index += 1
            continue
        if char == ">":
            if socket and socket_closed_at is None:
                raise AuthorityError("malformed socket descriptor annotation")
            angle_depth -= 1
            if angle_depth == 0:
                if quoted or bracket_depth:
                    raise AuthorityError("truncated socket descriptor annotation")
                if socket and socket_closed_at != index - 1:
                    raise AuthorityError("malformed socket descriptor annotation")
                annotation = text[body_start:index]
                _validate_annotation(annotation, socket=socket)
                return index + 1, annotation
            index += 1
            continue
        index += 1
    if quoted or socket:
        raise AuthorityError("truncated socket descriptor annotation")
    raise AuthorityError("truncated strace descriptor annotation")


def _scan_descriptor_token(text: str, start: int) -> tuple[int, str, bool]:
    end, annotation = _scan_descriptor(text, start)
    deleted = False
    for suffix in (" (deleted)", "(deleted)"):
        if text.startswith(suffix, end):
            end += len(suffix)
            deleted = True
            break
    boundary = end
    while boundary < len(text) and text[boundary].isspace():
        boundary += 1
    if boundary < len(text) and text[boundary] not in ",)]}":
        if not text.startswith("=>", boundary):
            raise AuthorityError("invalid descriptor token boundary")
        target = boundary + 2
        while target < len(text) and text[target].isspace():
            target += 1
        if not (
            _FD_WITH_ANNOTATION.match(text, target)
            and _descriptor_boundary(text, target)
        ):
            raise AuthorityError("descriptor transition lacks a decoded target")
    return end, annotation, deleted


def descriptor_annotation(value: str) -> str | None:
    head = _FD_BASE.match(value)
    if head is None:
        raise AuthorityError(f"expected decoded descriptor, got {value!r}")
    end = head.end()
    if end < len(value) and value[end] == "<":
        end, annotation, deleted = _scan_descriptor_token(value, 0)
        if end != len(value):
            raise AuthorityError(f"expected decoded descriptor, got {value!r}")
        if _SOCKET_ENVELOPE.match(annotation) is None:
            annotation = _decode_unquoted(annotation)
        return f"{annotation} (deleted)" if deleted else annotation
    if value[end:] in {"(deleted)", " (deleted)"}:
        raise AuthorityError("deleted suffix requires a descriptor annotation")
    if end != len(value):
        raise AuthorityError(f"expected decoded descriptor, got {value!r}")
    return None


def split_arguments(text: str) -> tuple[str, ...]:
    values: list[str] = []
    start = 0
    stack: list[str] = []
    quote = False
    escaped = False
    pairs = {"(": ")", "[": "]", "{": "}"}
    index = 0
    while index < len(text):
        char = text[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quote = False
            index += 1
            continue
        if char == '"':
            quote = True
            index += 1
            continue
        if _FD_WITH_ANNOTATION.match(text, index) and _descriptor_boundary(text, index):
            index, _, _ = _scan_descriptor_token(text, index)
            continue
        bare = _FD_BASE.match(text, index)
        if bare is not None and _descriptor_boundary(text, index):
            suffix = text[bare.end() :]
            if suffix.startswith("(deleted)") or suffix.startswith(" (deleted)"):
                raise AuthorityError("deleted suffix requires a descriptor annotation")
        if text.startswith("<<", index) or text.startswith(">>", index):
            index += 2
            continue
        if char == "<" or (char == ">" and (index == 0 or text[index - 1] != "=")):
            raise AuthorityError("unexpected angle in strace argument structure")
        if char in pairs:
            stack.append(pairs[char])
        elif char in pairs.values():
            if not stack or stack.pop() != char:
                raise AuthorityError("unbalanced strace argument structure")
        elif char == "," and not stack:
            values.append(text[start:index].strip())
            start = index + 1
        index += 1
    if quote or stack:
        raise AuthorityError("truncated strace argument structure")
    tail = text[start:].strip()
    if tail or text:
        values.append(tail)
    return tuple(values)
