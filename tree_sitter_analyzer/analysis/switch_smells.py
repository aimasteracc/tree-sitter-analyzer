"""Switch Smell Analyzer.

Detects complex switch/match/select statements that may indicate missed
polymorphism opportunities. Counts cases, checks for defaults, and flags
statements with too many branches.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tree_sitter

from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

SUPPORTED_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go",
}

_LANGUAGE_MODULES: dict[str, str] = {
    ".py": "tree_sitter_python",
    ".js": "tree_sitter_javascript",
    ".ts": "tree_sitter_typescript",
    ".tsx": "tree_sitter_typescript",
    ".jsx": "tree_sitter_javascript",
    ".java": "tree_sitter_java",
    ".go": "tree_sitter_go",
}

_LANGUAGE_FUNCS: dict[str, str] = {
    ".ts": "language_typescript",
    ".tsx": "language_tsx",
}

RATING_GOOD = "good"
RATING_WARNING = "warning"
RATING_CRITICAL = "critical"


def _rating(case_count: int) -> str:
    if case_count <= 3:
        return RATING_GOOD
    if case_count == 4:
        return RATING_WARNING
    return RATING_CRITICAL


@dataclass(frozen=True)
class SwitchStatement:
    """A switch/match/select statement with analysis."""

    line_number: int
    case_count: int
    has_default: bool
    smell_type: str
    statement_type: str


@dataclass(frozen=True)
class SwitchSmellResult:
    """Aggregated switch smell result for a file."""

    total_switches: int
    smelly_switches: int
    switches: tuple[SwitchStatement, ...]
    file_path: str


class SwitchSmellAnalyzer:
    """Analyzes switch/match statements for code smells."""

    def __init__(self) -> None:
        self._languages: dict[str, tree_sitter.Language] = {}
        self._parsers: dict[str, tree_sitter.Parser] = {}

    def _get_parser(
        self, extension: str
    ) -> tuple[tree_sitter.Language | None, tree_sitter.Parser | None]:
        if extension not in _LANGUAGE_MODULES:
            return None, None
        if extension not in self._parsers:
            module_name = _LANGUAGE_MODULES[extension]
            try:
                lang_module = __import__(module_name)
                func_name = _LANGUAGE_FUNCS.get(extension, "language")
                language_func = getattr(lang_module, func_name)
                language = tree_sitter.Language(language_func())
                self._languages[extension] = language
                parser = tree_sitter.Parser(language)
                self._parsers[extension] = parser
            except Exception as e:
                logger.error(f"Failed to load language for {extension}: {e}")
                return None, None
        return self._languages.get(extension), self._parsers.get(extension)

    def analyze_file(self, file_path: Path | str) -> SwitchSmellResult:
        path = Path(file_path)
        if not path.exists():
            return SwitchSmellResult(
                total_switches=0,
                smelly_switches=0,
                switches=(),
                file_path=str(path),
            )

        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return SwitchSmellResult(
                total_switches=0,
                smelly_switches=0,
                switches=(),
                file_path=str(path),
            )

        return self._analyze(path, ext)

    def _analyze(self, path: Path, ext: str) -> SwitchSmellResult:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return SwitchSmellResult(
                total_switches=0,
                smelly_switches=0,
                switches=(),
                file_path=str(path),
            )

        content = path.read_bytes()
        tree = parser.parse(content)

        switch_types, case_types, default_types = _get_switch_config(ext)

        switches: list[SwitchStatement] = []

        def visit(node: tree_sitter.Node) -> None:
            if node.type in switch_types:
                sw = self._analyze_switch(node, case_types, default_types)
                switches.append(sw)
            for child in node.children:
                visit(child)

        visit(tree.root_node)

        smelly = sum(1 for s in switches if s.smell_type != "none")

        return SwitchSmellResult(
            total_switches=len(switches),
            smelly_switches=smelly,
            switches=tuple(switches),
            file_path=str(path),
        )

    def _analyze_switch(
        self,
        node: tree_sitter.Node,
        case_types: frozenset[str],
        default_types: frozenset[str],
    ) -> SwitchStatement:
        case_count = 0
        has_default = False
        is_python_wildcard = "_wildcard_default" in default_types

        def count_cases(n: tree_sitter.Node) -> None:
            nonlocal case_count, has_default
            if n.type in case_types:
                case_count += 1
                if is_python_wildcard and self._is_wildcard_case(n):
                    has_default = True
            if n.type in default_types and n.type != "_wildcard_default":
                has_default = True
                case_count += 1
            for child in n.children:
                count_cases(child)

        for child in node.children:
            count_cases(child)

        smell = "none"
        if case_count >= 5:
            smell = "too_many_cases"
        elif not has_default and case_count >= 4:
            smell = "missing_default"

        return SwitchStatement(
            line_number=node.start_point[0] + 1,
            case_count=case_count,
            has_default=has_default,
            smell_type=smell,
            statement_type=node.type,
        )

    @staticmethod
    def _is_wildcard_case(node: tree_sitter.Node) -> bool:
        """Check if a Python case_clause uses wildcard pattern (_)."""
        for child in node.children:
            if child.type == "case_pattern":
                for pattern_child in child.children:
                    if pattern_child.type == "_":
                        return True
        return False


def _get_switch_config(
    ext: str,
) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    if ext == ".py":
        return (
            frozenset({"match_statement"}),
            frozenset({"case_clause"}),
            frozenset({"_wildcard_default"}),  # Special marker
        )
    if ext in {".js", ".ts", ".tsx", ".jsx"}:
        return (
            frozenset({"switch_statement"}),
            frozenset({"switch_case"}),
            frozenset({"switch_default"}),
        )
    if ext == ".java":
        return (
            frozenset({"switch_statement", "switch_expression"}),
            frozenset({"switch_block_statement_group", "case"}),
            frozenset({"default"}),
        )
    if ext == ".go":
        return (
            frozenset({
                "expression_switch_statement",
                "type_switch_statement",
                "select_statement",
            }),
            frozenset({"expression_case", "communication_case", "type_case"}),
            frozenset({"default_case"}),
        )
    return frozenset(), frozenset(), frozenset()
