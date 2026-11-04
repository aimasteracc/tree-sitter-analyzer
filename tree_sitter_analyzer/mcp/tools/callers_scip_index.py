"""Read a SCIP index (``index.scip``) with the standard library only.

SCIP is a protobuf message (sourcegraph/scip ``scip.proto``). This module
decodes the protobuf wire format directly, so the opt-in SCIP evidence layer
of ``nav action=callers`` adds no dependency. Only the fields the evidence
layer reads are decoded; every other field is skipped by its wire type.

Field numbers (upstream ``scip.proto``)::

    Index           1 metadata, 2 documents, 3 external_symbols
    Metadata        2 tool_info (1 name, 2 version)
    Document        1 relative_path, 2 occurrences, 3 symbols
    Occurrence      1 range (packed int32), 2 symbol, 3 symbol_roles,
                    7 enclosing_range (packed int32)
    SymbolInfo      1 symbol, 3 documentation, 4 relationships, 5 kind
    Relationship    1 symbol, 2 is_reference, 3 is_implementation,
                    4 is_type_definition, 5 is_definition

A file can appear in several documents (one per tsconfig project); their
occurrences are merged as a set. A malformed buffer raises
:class:`ScipFormatError`; the caller treats that as "no evidence".
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType

#: ``Occurrence.symbol_roles`` bits.
ROLE_DEFINITION = 0x1
ROLE_IMPORT = 0x2
#: ``SymbolInformation.Kind`` values the trust rules read.
KIND_CLASS = 7
KIND_INTERFACE = 21


class ScipFormatError(ValueError):
    """The buffer is not a decodable SCIP index."""


@dataclass(frozen=True)
class Occurrence:
    """One occurrence; lines and columns are 0-based as in SCIP."""

    line: int
    col: int
    end_line: int
    end_col: int
    symbol: str
    roles: int
    enclosing: tuple[int, int, int, int] | None = None

    @property
    def is_definition(self) -> bool:
        return bool(self.roles & ROLE_DEFINITION)


@dataclass(frozen=True)
class Relationship:
    symbol: str
    is_reference: bool
    is_implementation: bool
    is_type_definition: bool
    is_definition: bool


@dataclass(frozen=True)
class SymbolInfo:
    symbol: str
    kind: int
    documentation: str
    relationships: tuple[Relationship, ...]


@dataclass(frozen=True)
class ScipIndex:
    """The decoded index: documents by path, symbol information, definitions."""

    tool_name: str
    tool_version: str
    documents: Mapping[str, tuple[Occurrence, ...]]
    symbols: Mapping[str, SymbolInfo]
    #: symbol -> files holding a definition occurrence of it (sorted).
    defined_in: Mapping[str, tuple[str, ...]]
    #: symbol -> (file, occurrence) of every non-definition occurrence.
    references: Mapping[str, tuple[tuple[str, Occurrence], ...]]
    #: path -> 0-based line -> occurrences starting on that line.
    by_line: Mapping[str, Mapping[int, tuple[Occurrence, ...]]]

    def on_line(self, path: str, line: int) -> tuple[Occurrence, ...]:
        """Occurrences that start on 0-based ``line`` of ``path``."""
        return self.by_line.get(path, {}).get(line, ())


def _varint(buf: memoryview, i: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        if i >= len(buf) or shift > 63:
            raise ScipFormatError("truncated varint")
        byte = buf[i]
        i += 1
        result |= (byte & 0x7F) << shift
        if byte < 0x80:
            return result, i
        shift += 7


def _fields(
    buf: memoryview, start: int, end: int
) -> Iterator[tuple[int, int, int, int]]:
    """``(field, wire type, a, b)``: a varint value in ``a``, or a slice ``[a, b)``."""
    i = start
    while i < end:
        key, i = _varint(buf, i)
        wire, number = key & 7, key >> 3
        if wire == 0:
            value, i = _varint(buf, i)
            yield number, 0, value, 0
        elif wire == 2:
            size, i = _varint(buf, i)
            if i + size > end:
                raise ScipFormatError("length-delimited field overruns its message")
            yield number, 2, i, i + size
            i += size
        elif wire == 1:
            i += 8
        elif wire == 5:
            i += 4
        else:
            raise ScipFormatError(f"unsupported wire type {wire}")
    if i != end:
        raise ScipFormatError("message overruns its end")


def _packed(buf: memoryview, start: int, end: int) -> list[int]:
    out = []
    i = start
    while i < end:
        value, i = _varint(buf, i)
        out.append(value)
    return out


def _text(buf: memoryview, start: int, end: int) -> str:
    try:
        return bytes(buf[start:end]).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ScipFormatError("invalid UTF-8 string") from exc


def _range(values: list[int]) -> tuple[int, int, int, int] | None:
    if len(values) == 3:
        return values[0], values[1], values[0], values[2]
    if len(values) == 4:
        return values[0], values[1], values[2], values[3]
    return None


def _occurrence(buf: memoryview, start: int, end: int) -> Occurrence | None:
    span: tuple[int, int, int, int] | None = None
    symbol = ""
    roles = 0
    enclosing = None
    for number, wire, a, b in _fields(buf, start, end):
        if number == 1 and wire == 2:
            span = _range(_packed(buf, a, b))
        elif number == 2 and wire == 2:
            symbol = _text(buf, a, b)
        elif number == 3 and wire == 0:
            roles = a
        elif number == 7 and wire == 2:
            enclosing = _range(_packed(buf, a, b))
    if span is None or not symbol:
        return None
    return Occurrence(*span, symbol=symbol, roles=roles, enclosing=enclosing)


def _relationship(buf: memoryview, start: int, end: int) -> Relationship:
    symbol = ""
    flags = [False, False, False, False]
    for number, wire, a, b in _fields(buf, start, end):
        if number == 1 and wire == 2:
            symbol = _text(buf, a, b)
        elif 2 <= number <= 5 and wire == 0:
            flags[number - 2] = bool(a)
    return Relationship(symbol, *flags)


def _symbol_info(buf: memoryview, start: int, end: int) -> SymbolInfo | None:
    symbol = ""
    kind = 0
    documentation = ""
    relationships: list[Relationship] = []
    for number, wire, a, b in _fields(buf, start, end):
        if number == 1 and wire == 2:
            symbol = _text(buf, a, b)
        elif number == 3 and wire == 2 and not documentation:
            documentation = _text(buf, a, b)
        elif number == 4 and wire == 2:
            relationships.append(_relationship(buf, a, b))
        elif number == 5 and wire == 0:
            kind = a
    if not symbol:
        return None
    return SymbolInfo(symbol, kind, documentation, tuple(relationships))


def _merge_info(old: SymbolInfo | None, new: SymbolInfo) -> SymbolInfo:
    if old is None:
        return new
    rels = tuple(dict.fromkeys(old.relationships + new.relationships))
    return SymbolInfo(
        old.symbol, old.kind or new.kind, old.documentation or new.documentation, rels
    )


def _document(
    buf: memoryview, start: int, end: int
) -> tuple[str, list[Occurrence], list[SymbolInfo]]:
    path = ""
    occurrences: list[Occurrence] = []
    infos: list[SymbolInfo] = []
    for number, wire, a, b in _fields(buf, start, end):
        if number == 1 and wire == 2:
            path = _text(buf, a, b).replace("\\", "/")
        elif number == 2 and wire == 2:
            found = _occurrence(buf, a, b)
            if found is not None:
                occurrences.append(found)
        elif number == 3 and wire == 2:
            info = _symbol_info(buf, a, b)
            if info is not None:
                infos.append(info)
    return path, occurrences, infos


def _tool(buf: memoryview, start: int, end: int) -> tuple[str, str]:
    name = version = ""
    for number, wire, a, b in _fields(buf, start, end):
        if number == 2 and wire == 2:
            for inner, inner_wire, c, d in _fields(buf, a, b):
                if inner == 1 and inner_wire == 2:
                    name = _text(buf, c, d)
                elif inner == 2 and inner_wire == 2:
                    version = _text(buf, c, d)
    return name, version


def parse_index(data: bytes) -> ScipIndex:
    """Decode a whole index. Raises :class:`ScipFormatError` on malformed input."""
    buf = memoryview(data)
    tool = ("", "")
    docs: dict[str, set[Occurrence]] = {}
    symbols: dict[str, SymbolInfo] = {}
    try:
        for number, wire, a, b in _fields(buf, 0, len(buf)):
            if number == 1 and wire == 2:
                tool = _tool(buf, a, b)
            elif number == 2 and wire == 2:
                path, occurrences, infos = _document(buf, a, b)
                if not path:
                    raise ScipFormatError("document without relative_path")
                docs.setdefault(path, set()).update(occurrences)
                for info in infos:
                    symbols[info.symbol] = _merge_info(symbols.get(info.symbol), info)
            elif number == 3 and wire == 2:
                external = _symbol_info(buf, a, b)
                if external is not None and external.symbol not in symbols:
                    symbols[external.symbol] = external
    except IndexError as exc:  # pragma: no cover - guarded by the bound checks
        raise ScipFormatError("truncated index") from exc
    return _assemble(tool, docs, symbols)


def _assemble(
    tool: tuple[str, str],
    docs: dict[str, set[Occurrence]],
    symbols: dict[str, SymbolInfo],
) -> ScipIndex:
    documents: dict[str, tuple[Occurrence, ...]] = {}
    defined: dict[str, set[str]] = {}
    references: dict[str, list[tuple[str, Occurrence]]] = {}
    by_line: dict[str, Mapping[int, tuple[Occurrence, ...]]] = {}
    for path in sorted(docs):
        ordered = tuple(
            sorted(docs[path], key=lambda o: (o.line, o.col, o.symbol, o.roles))
        )
        documents[path] = ordered
        lines: dict[int, list[Occurrence]] = {}
        for occ in ordered:
            lines.setdefault(occ.line, []).append(occ)
        by_line[path] = MappingProxyType({k: tuple(v) for k, v in lines.items()})
        for occ in ordered:
            if occ.is_definition:
                defined.setdefault(occ.symbol, set()).add(path)
            else:
                references.setdefault(occ.symbol, []).append((path, occ))
    return ScipIndex(
        tool_name=tool[0],
        tool_version=tool[1],
        documents=MappingProxyType(documents),
        symbols=MappingProxyType(symbols),
        defined_in=MappingProxyType(
            {sym: tuple(sorted(files)) for sym, files in defined.items()}
        ),
        references=MappingProxyType(
            {sym: tuple(found) for sym, found in references.items()}
        ),
        by_line=MappingProxyType(by_line),
    )


__all__ = [
    "KIND_CLASS",
    "KIND_INTERFACE",
    "ROLE_DEFINITION",
    "ROLE_IMPORT",
    "Occurrence",
    "Relationship",
    "ScipFormatError",
    "ScipIndex",
    "SymbolInfo",
    "parse_index",
]
