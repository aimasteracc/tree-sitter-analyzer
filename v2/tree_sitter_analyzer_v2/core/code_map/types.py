"""
Data types for ProjectCodeMap.

All dataclasses used by the code map subsystem live here.
No business logic — only data definitions and simple serialization (to_toon).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypedDict


@dataclass
class SymbolInfo:
    """A single symbol (function, class, method) in the project."""

    name: str
    kind: str  # "function", "class", "method"
    file: str  # relative path
    line_start: int
    line_end: int
    params: str = ""
    return_type: str = ""
    visibility: str = "public"
    parent_class: str = ""  # for methods
    bases: list[str] = field(default_factory=list)  # for classes: parent/base class names

    @property
    def fqn(self) -> str:
        """Fully-qualified name: file:parent.name (unique across project)."""
        if self.parent_class:
            return f"{self.file}:{self.parent_class}.{self.name}"
        return f"{self.file}:{self.name}"


@dataclass
class CodeSection:
    """A code section extracted for LLM context."""

    file_path: str
    start_line: int
    end_line: int
    content: str
    relevance: str  # "definition" / "caller" / "callee" / "import"


@dataclass
class CallFlowResult:
    """Result of trace_call_flow: bidirectional call chain."""

    target: SymbolInfo | None
    callers: list[SymbolInfo] = field(default_factory=list)
    callees: list[SymbolInfo] = field(default_factory=list)

    def to_toon(self) -> str:
        if not self.target:
            return "CALL_FLOW: target not found"
        lines: list[str] = []
        lines.append(f"CALL_FLOW: {self.target.name} ({self.target.file}:L{self.target.line_start})")
        if self.callers:
            lines.append("  CALLED_BY (upstream):")
            for s in self.callers:
                lines.append(f"    {s.name} ({s.file}:L{s.line_start})")
        else:
            lines.append("  CALLED_BY: (none - this is a root/entry point)")
        if self.callees:
            lines.append("  CALLS (downstream):")
            for s in self.callees:
                lines.append(f"    {s.name} ({s.file}:L{s.line_start})")
        else:
            lines.append("  CALLS: (none - this is a leaf function)")
        return "\n".join(lines)


@dataclass
class ImpactResult:
    """Result of impact_analysis: what breaks if you change this symbol."""

    target: SymbolInfo | None
    affected_symbols: list[SymbolInfo] = field(default_factory=list)
    affected_files: list[str] = field(default_factory=list)
    blast_radius: int = 0
    depth: int = 0
    risk_level: str = "low"

    def to_toon(self) -> str:
        if not self.target:
            return "IMPACT: target not found"
        lines: list[str] = []
        lines.append(
            f"IMPACT: {self.target.name} "
            f"[risk={self.risk_level} radius={self.blast_radius} depth={self.depth}]"
        )
        if self.affected_files:
            lines.append(f"  AFFECTED_FILES ({len(self.affected_files)}):")
            for f in self.affected_files:
                lines.append(f"    {f}")
        if self.affected_symbols:
            lines.append(f"  AFFECTED_SYMBOLS ({len(self.affected_symbols)}):")
            for s in self.affected_symbols:
                lines.append(f"    {s.name} ({s.file}:L{s.line_start}) [{s.kind}]")
        return "\n".join(lines)


@dataclass
class ContextResult:
    """Result of gather_context: all code an LLM needs to answer accurately."""

    query: str
    matched_symbols: list[SymbolInfo] = field(default_factory=list)
    code_sections: list[CodeSection] = field(default_factory=list)
    total_tokens: int = 0

    def to_toon(self) -> str:
        lines: list[str] = []
        lines.append(f"CONTEXT: query=\"{self.query}\" [{len(self.code_sections)} sections, ~{self.total_tokens} tokens]")
        if self.matched_symbols:
            lines.append("  SYMBOLS:")
            for s in self.matched_symbols:
                lines.append(f"    {s.kind} {s.name} ({s.file}:L{s.line_start})")
        for sec in self.code_sections:
            lines.append(f"  [{sec.relevance}] {sec.file_path}:L{sec.start_line}-{sec.end_line}")
            for line in sec.content.splitlines():
                lines.append(f"    {line}")
        return "\n".join(lines)


class ParsedFunction(TypedDict, total=False):
    """Type-safe schema for parsed function/method data from language parsers."""

    name: str
    line_start: int
    line_end: int
    parameters: list[str]
    return_type: str
    decorators: list[str]
    visibility: str
    is_static: bool
    is_constructor: bool


class ParsedClass(TypedDict, total=False):
    """Type-safe schema for parsed class data from language parsers."""

    name: str
    line_start: int
    line_end: int
    methods: list[ParsedFunction]
    bases: list[str]
    implements: list[str]
    extends: list[str]
    decorators: list[str]
    visibility: str


class ParsedImport(TypedDict, total=False):
    """Type-safe schema for parsed import data from language parsers."""

    module: str
    names: list[str]
    line_start: int
    line: int
    alias: str


@dataclass
class ModuleInfo:
    """Parsed information about a single module/file."""

    path: str  # relative path
    language: str
    lines: int
    classes: list[dict[str, Any]] = field(default_factory=list)
    functions: list[dict[str, Any]] = field(default_factory=list)
    imports: list[dict[str, Any]] = field(default_factory=list)
    call_sites: dict[str, list[str]] = field(default_factory=dict)
    decorated_entries: set[str] = field(default_factory=set)

    # Type-safe accessors (sugar over raw dict data)
    @property
    def typed_functions(self) -> list[ParsedFunction]:
        """Access functions with type hints (zero-copy cast)."""
        return self.functions  # type: ignore[return-value]

    @property
    def typed_classes(self) -> list[ParsedClass]:
        """Access classes with type hints (zero-copy cast)."""
        return self.classes  # type: ignore[return-value]

    @property
    def typed_imports(self) -> list[ParsedImport]:
        """Access imports with type hints (zero-copy cast)."""
        return self.imports  # type: ignore[return-value]


@dataclass
class InheritanceChain:
    """Result of trace_inheritance: full inheritance chain for a class."""

    target: SymbolInfo | None
    ancestors: list[SymbolInfo] = field(default_factory=list)
    descendants: list[SymbolInfo] = field(default_factory=list)

    def to_toon(self) -> str:
        if not self.target:
            return "INHERITANCE: target not found"
        lines: list[str] = []
        bases_str = f" extends {','.join(self.target.bases)}" if self.target.bases else ""
        lines.append(
            f"INHERITANCE: {self.target.name}{bases_str} "
            f"({self.target.file}:L{self.target.line_start})"
        )
        if self.ancestors:
            lines.append("  ANCESTORS (parent chain):")
            for s in self.ancestors:
                bases = f" extends {','.join(s.bases)}" if s.bases else ""
                lines.append(f"    {s.name}{bases} ({s.file}:L{s.line_start})")
        else:
            lines.append("  ANCESTORS: (none - root class)")
        if self.descendants:
            lines.append("  DESCENDANTS (implementing/extending):")
            for s in self.descendants:
                lines.append(f"    {s.name} ({s.file}:L{s.line_start})")
        else:
            lines.append("  DESCENDANTS: (none - leaf class)")
        return "\n".join(lines)


@dataclass
class RefactoringSuggestion:
    """A single refactoring suggestion generated from code analysis."""

    kind: str
    severity: str
    message: str
    symbol_name: str
    file_path: str
    line: int = 0
    detail: str = ""

    def to_toon(self) -> str:
        loc = f"{self.file_path}:L{self.line}" if self.line else self.file_path
        return f"[{self.severity.upper()}] {self.kind}: {self.message} ({loc})"


@dataclass
class ChangeRiskReport:
    """Result of change risk assessment for a set of files."""

    risk_level: str
    changed_files: list[str] = field(default_factory=list)
    affected_files: list[str] = field(default_factory=list)
    affected_symbols: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def to_toon(self) -> str:
        lines: list[str] = [
            f"CHANGE_RISK: {self.risk_level.upper()}",
            f"  changed: {len(self.changed_files)} files",
            f"  affected: {len(self.affected_files)} files, {len(self.affected_symbols)} symbols",
        ]
        for r in self.reasons[:10]:
            lines.append(f"  - {r}")
        return "\n".join(lines)


@dataclass
class CodeSmell:
    """A detected code smell / anti-pattern."""

    kind: str
    severity: str
    message: str
    file_path: str
    detail: str = ""

    def to_toon(self) -> str:
        return f"[{self.severity.upper()}] {self.kind}: {self.message} ({self.file_path})"


@dataclass
class ArchitectureTestReport:
    """Result of test architecture audit."""

    source_files: list[str] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    untested_files: list[str] = field(default_factory=list)
    tested_files: list[str] = field(default_factory=list)
    test_layers: dict[str, list[str]] = field(default_factory=dict)
    missing_layers: list[str] = field(default_factory=list)
    untested_tools: list[str] = field(default_factory=list)
    duplicate_coverage: list[tuple[str, list[str]]] = field(default_factory=list)
    coverage_percent: float = 0.0
    total_source_symbols: int = 0
    tested_symbols: int = 0
    symbol_coverage_percent: float = 0.0
    total_test_functions: int = 0
    test_quality: dict[str, int] = field(default_factory=dict)
    import_matched: dict[str, list[str]] = field(default_factory=dict)

    def to_toon(self) -> str:
        lines: list[str] = [
            f"TEST_AUDIT:",
            f"  FILE_COVERAGE: {self.coverage_percent:.1f}% "
            f"({len(self.tested_files)}/{len(self.source_files)} source files)",
            f"  SYMBOL_COVERAGE: {self.symbol_coverage_percent:.1f}% "
            f"({self.tested_symbols}/{self.total_source_symbols} symbols referenced by tests)",
            f"  TEST_FILES: {len(self.test_files)} "
            f"({self.total_test_functions} test functions total)",
        ]
        if self.test_layers:
            lines.append("  TEST_LAYERS:")
            for layer, files in sorted(self.test_layers.items()):
                lines.append(f"    {layer}: {len(files)} files")
        if self.missing_layers:
            lines.append(f"  MISSING_LAYERS: {', '.join(self.missing_layers)}")
        if self.untested_tools:
            lines.append(f"  UNTESTED_TOOLS ({len(self.untested_tools)}):")
            for t in self.untested_tools[:20]:
                lines.append(f"    - {t}")
            if len(self.untested_tools) > 20:
                lines.append(f"    ... ({len(self.untested_tools) - 20} more)")
        if self.untested_files:
            lines.append(f"  UNTESTED_FILES ({len(self.untested_files)}, sorted by risk):")
            for f in self.untested_files[:30]:
                lines.append(f"    - {f}")
            if len(self.untested_files) > 30:
                lines.append(f"    ... ({len(self.untested_files) - 30} more)")
        if self.duplicate_coverage:
            lines.append(f"  DUPLICATE_COVERAGE ({len(self.duplicate_coverage)}):")
            for src, tests in self.duplicate_coverage[:10]:
                lines.append(f"    {src} tested by: {', '.join(tests)}")
        thin_tests = [(f, c) for f, c in self.test_quality.items() if c <= 1]
        if thin_tests:
            lines.append(f"  THIN_TESTS ({len(thin_tests)} files with <=1 test function):")
            for f, c in thin_tests[:10]:
                lines.append(f"    {f}: {c} test(s)")
        return "\n".join(lines)


@dataclass
class _FileCache:
    """Cache entry for a parsed file (mtime-based invalidation)."""

    mtime_ns: int
    module: ModuleInfo
