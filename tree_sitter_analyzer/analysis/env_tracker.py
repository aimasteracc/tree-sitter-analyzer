#!/usr/bin/env python3
"""
Environment Variable Tracking Engine.

Tracks environment variable usage across codebases to help developers
understand configuration requirements and avoid missing deployment configs.

Detects environment variable references in:
- Python: os.getenv(), os.environ[], os.environ.get()
- JavaScript/TypeScript: process.env.VAR, process.env["VAR"]
- Java: System.getenv(), System.getProperty()
- Go: os.Getenv()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger
from tree_sitter_analyzer.utils.tree_sitter_compat import TreeSitterQueryCompat

if TYPE_CHECKING:
    from tree_sitter import Tree

logger = setup_logger(__name__)

SUPPORTED_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go",
}

# Python tree-sitter query patterns
# Uses '.' anchor to match only the FIRST string argument
_PYTHON_GETENV_QUERY = """
(call
    function: (attribute
        object: (identifier) @obj
        attribute: (identifier) @attr)
    arguments: (argument_list
        .
        (string (string_content) @var_name))) @ref
"""

_PYTHON_ENVIRON_INDEX_QUERY = """
(subscript
    value: (attribute
        object: (identifier) @obj
        attribute: (identifier) @attr)
    subscript: (string (string_content) @var_name)) @ref
"""

_PYTHON_ENVIRON_GET_QUERY = """
(call
    function: (attribute
        object: (attribute
            object: (identifier) @obj
            attribute: (identifier) @attr1)
        attribute: (identifier) @attr2)
    arguments: (argument_list
        .
        (string (string_content) @var_name))) @ref
"""

# JavaScript/TypeScript query patterns (no named fields)
_JS_PROPERTY_QUERY = """
(member_expression
    (member_expression
        (identifier) @obj
        (property_identifier) @prop)
    (property_identifier) @var_name) @ref
"""

_JS_SUBSCRIPT_QUERY = """
(subscript_expression
    (member_expression
        (identifier) @obj
        (property_identifier) @prop)
    (string
        (string_fragment) @var_name)) @ref
"""

# Java query pattern
_JAVA_GETENV_QUERY = """
(method_invocation
    object: (identifier) @obj
    name: (identifier) @method
    arguments: (argument_list
        (string_literal
            (string_fragment) @var_name))) @ref
"""

# Go query pattern
_GO_GETENV_QUERY = """
(call_expression
    function: (selector_expression
        operand: (identifier) @obj
        field: (field_identifier) @method)
    arguments: (argument_list
        (interpreted_string_literal
            (interpreted_string_literal_content) @var_name))) @ref
"""

class AccessType(Enum):
    """Type of environment variable access."""

    GETENV_CALL = "getenv_call"
    ENVIRON_INDEX = "environ_index"
    ENVIRON_GET = "environ_get"
    PROPERTY_ACCESS = "property_access"
    SYSTEM_GETENV = "system_getenv"
    SYSTEM_GETPROPERTY = "system_getproperty"
    GO_GETENV = "go_getenv"

@dataclass(frozen=True)
class EnvVarReference:
    """A single environment variable reference."""

    var_name: str
    file_path: str
    line: int
    column: int
    access_type: str
    context: str
    has_default: bool = False

@dataclass
class EnvVarUsage:
    """Aggregated usage information for a single environment variable."""

    var_name: str
    references: list[EnvVarReference] = field(default_factory=list)
    file_count: int = 0
    total_references: int = 0
    has_default_count: int = 0
    access_types: dict[str, int] = field(default_factory=dict)

    def add_reference(self, ref: EnvVarReference) -> None:
        """Add a reference and update counts."""
        self.references.append(ref)
        self.total_references += 1
        if ref.has_default:
            self.has_default_count += 1

        files = {r.file_path for r in self.references}
        self.file_count = len(files)

        self.access_types[ref.access_type] = (
            self.access_types.get(ref.access_type, 0) + 1
        )

@dataclass
class EnvTrackingResult:
    """Result of environment variable tracking on a file or project."""

    total_references: int = 0
    unique_vars: int = 0
    by_file: dict[str, int] = field(default_factory=dict)
    by_var: dict[str, EnvVarUsage] = field(default_factory=dict)

    def add_reference(self, ref: EnvVarReference) -> None:
        """Add a reference and update aggregations."""
        self.total_references += 1

        self.by_file[ref.file_path] = (
            self.by_file.get(ref.file_path, 0) + 1
        )

        if ref.var_name not in self.by_var:
            self.by_var[ref.var_name] = EnvVarUsage(var_name=ref.var_name)
            self.unique_vars += 1
        self.by_var[ref.var_name].add_reference(ref)

class EnvVarTracker(BaseAnalyzer):
    """Track environment variable usage in code."""

    def __init__(
        self,
        project_root: str | Path,
        include_defaults: bool = True,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.include_defaults = include_defaults
        super().__init__()

    def _run_query(
        self,
        language: Any,
        query_string: str,
        root_node: Any,
    ) -> list[tuple[Any, str]]:
        """Execute a tree-sitter query using the compat layer."""
        return TreeSitterQueryCompat.execute_query(
            language, query_string, root_node
        )

    @staticmethod
    def _has_default_value(ref_node: Any) -> bool:
        """Check if a call node has more than one argument (has default)."""
        for child in ref_node.children:
            if child.type in ("arguments", "argument_list"):
                args = [
                    c for c in child.children
                    if c.type not in ("(", ")", ",", "[", "]")
                ]
                return len(args) > 1
        return False

    def track_file(self, file_path: str | Path) -> EnvTrackingResult:
        """Track environment variables in a single file."""
        file_path = Path(file_path).resolve()
        result = EnvTrackingResult()

        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return result

        if file_path.suffix not in SUPPORTED_EXTENSIONS:
            logger.debug(f"Unsupported file type: {file_path.suffix}")
            return result

        language, parser = self._get_parser(file_path.suffix)
        if language is None or parser is None:
            logger.debug(f"No language found for extension: {file_path.suffix}")
            return result

        try:
            content = file_path.read_text(encoding="utf-8")
            tree = parser.parse(content.encode("utf-8"))

            if file_path.suffix == ".py":
                refs = self._track_python(file_path, tree, content, language)
            elif file_path.suffix in (".js", ".ts", ".tsx", ".jsx"):
                refs = self._track_javascript(file_path, tree, content, language)
            elif file_path.suffix == ".java":
                refs = self._track_java(file_path, tree, content, language)
            elif file_path.suffix == ".go":
                refs = self._track_go(file_path, tree, content, language)
            else:
                refs = []

            for ref in refs:
                if not ref.has_default or self.include_defaults:
                    result.add_reference(ref)

        except Exception as e:
            logger.error(f"Error tracking file {file_path}: {e}")

        return result

    def track_directory(
        self, dir_path: str | Path
    ) -> EnvTrackingResult:
        """Track environment variables across all files in a directory."""
        dir_path = Path(dir_path).resolve()
        result = EnvTrackingResult()

        if not dir_path.is_dir():
            logger.warning(f"Directory not found: {dir_path}")
            return result

        for ext in SUPPORTED_EXTENSIONS:
            for file_path in dir_path.rglob(f"*{ext}"):
                file_result = self.track_file(file_path)
                for _var_name, usage in file_result.by_var.items():
                    for ref in usage.references:
                        result.add_reference(ref)

        return result

    def _track_python(
        self,
        file_path: Path,
        tree: Tree,
        content: str,
        language: tree_sitter.Language,
    ) -> list[EnvVarReference]:
        """Track env vars in Python code."""
        refs: list[EnvVarReference] = []
        root = tree.root_node

        # Pattern 1: os.getenv("VAR") or os.getenv("VAR", "default")
        captures = self._run_query(language, _PYTHON_GETENV_QUERY, root)
        for node, tag in captures:
            if tag != "var_name":
                continue
            var_name = node.text.decode("utf-8").strip('"\'')
            line = node.start_point[0] + 1
            col = node.start_point[1] + 1
            context = self._get_context(content, line, col)

            # Find the @ref parent to check for default value
            ref_node = self._find_parent_capture(captures, node, "ref")
            has_default = (
                ref_node is not None and self._has_default_value(ref_node)
            )

            # Verify this is os.getenv via obj/attr captures
            if not self._verify_obj_attr(captures, node, "os", "getenv"):
                continue

            refs.append(EnvVarReference(
                var_name=var_name,
                file_path=str(file_path),
                line=line,
                column=col,
                access_type=AccessType.GETENV_CALL.value,
                context=context,
                has_default=has_default,
            ))

        # Pattern 2: os.environ["VAR"]
        captures2 = self._run_query(
            language, _PYTHON_ENVIRON_INDEX_QUERY, root
        )
        for node, tag in captures2:
            if tag != "var_name":
                continue
            var_name = node.text.decode("utf-8").strip('"\'')
            line = node.start_point[0] + 1
            col = node.start_point[1] + 1
            context = self._get_context(content, line, col)

            if not self._verify_obj_attr(captures2, node, "os", "environ"):
                continue

            refs.append(EnvVarReference(
                var_name=var_name,
                file_path=str(file_path),
                line=line,
                column=col,
                access_type=AccessType.ENVIRON_INDEX.value,
                context=context,
                has_default=False,
            ))

        # Pattern 3: os.environ.get("VAR") or os.environ.get("VAR", "default")
        captures3 = self._run_query(
            language, _PYTHON_ENVIRON_GET_QUERY, root
        )
        for node, tag in captures3:
            if tag != "var_name":
                continue
            var_name = node.text.decode("utf-8").strip('"\'')
            line = node.start_point[0] + 1
            col = node.start_point[1] + 1
            context = self._get_context(content, line, col)

            ref_node = self._find_parent_capture(captures3, node, "ref")
            has_default = (
                ref_node is not None and self._has_default_value(ref_node)
            )

            if not self._verify_obj_attr(captures3, node, "os", "environ"):
                continue

            refs.append(EnvVarReference(
                var_name=var_name,
                file_path=str(file_path),
                line=line,
                column=col,
                access_type=AccessType.ENVIRON_GET.value,
                context=context,
                has_default=has_default,
            ))

        return refs

    def _track_javascript(
        self,
        file_path: Path,
        tree: Tree,
        content: str,
        language: tree_sitter.Language,
    ) -> list[EnvVarReference]:
        """Track env vars in JavaScript/TypeScript code."""
        refs: list[EnvVarReference] = []
        root = tree.root_node

        # Pattern 1: process.env.VAR_NAME
        captures = self._run_query(language, _JS_PROPERTY_QUERY, root)
        for node, tag in captures:
            if tag != "var_name":
                continue
            var_name = node.text.decode("utf-8")
            line = node.start_point[0] + 1
            col = node.start_point[1] + 1
            context = self._get_context(content, line, col)

            if not self._verify_obj_prop(captures, node, "process", "env"):
                continue

            refs.append(EnvVarReference(
                var_name=var_name,
                file_path=str(file_path),
                line=line,
                column=col,
                access_type=AccessType.PROPERTY_ACCESS.value,
                context=context,
                has_default=False,
            ))

        # Pattern 2: process.env["VAR_NAME"]
        captures2 = self._run_query(language, _JS_SUBSCRIPT_QUERY, root)
        for node, tag in captures2:
            if tag != "var_name":
                continue
            var_name = node.text.decode("utf-8").strip('"\'')
            line = node.start_point[0] + 1
            col = node.start_point[1] + 1
            context = self._get_context(content, line, col)

            if not self._verify_obj_prop(captures2, node, "process", "env"):
                continue

            refs.append(EnvVarReference(
                var_name=var_name,
                file_path=str(file_path),
                line=line,
                column=col,
                access_type=AccessType.ENVIRON_INDEX.value,
                context=context,
                has_default=False,
            ))

        return refs

    def _track_java(
        self,
        file_path: Path,
        tree: Tree,
        content: str,
        language: tree_sitter.Language,
    ) -> list[EnvVarReference]:
        """Track env vars in Java code."""
        refs: list[EnvVarReference] = []
        root = tree.root_node

        captures = self._run_query(language, _JAVA_GETENV_QUERY, root)
        for node, tag in captures:
            if tag != "var_name":
                continue
            var_name = node.text.decode("utf-8").strip('"\'')
            line = node.start_point[0] + 1
            col = node.start_point[1] + 1
            context = self._get_context(content, line, col)

            # Determine access type from method node
            method_node = self._find_tagged_node(captures, "method", node)
            if method_node is not None:
                method_text = method_node.text.decode("utf-8")
                if "getenv" in method_text:
                    access_type = AccessType.SYSTEM_GETENV.value
                else:
                    access_type = AccessType.SYSTEM_GETPROPERTY.value
            else:
                access_type = AccessType.SYSTEM_GETENV.value

            # Verify System class
            obj_node = self._find_tagged_node(captures, "obj", node)
            if obj_node is not None and obj_node.text.decode("utf-8") != "System":
                continue

            refs.append(EnvVarReference(
                var_name=var_name,
                file_path=str(file_path),
                line=line,
                column=col,
                access_type=access_type,
                context=context,
                has_default=False,
            ))

        return refs

    def _track_go(
        self,
        file_path: Path,
        tree: Tree,
        content: str,
        language: tree_sitter.Language,
    ) -> list[EnvVarReference]:
        """Track env vars in Go code."""
        refs: list[EnvVarReference] = []
        root = tree.root_node

        captures = self._run_query(language, _GO_GETENV_QUERY, root)
        for node, tag in captures:
            if tag != "var_name":
                continue
            var_name = node.text.decode("utf-8").strip('"\'')
            line = node.start_point[0] + 1
            col = node.start_point[1] + 1
            context = self._get_context(content, line, col)

            # Verify os.Getenv
            obj_node = self._find_tagged_node(captures, "obj", node)
            if obj_node is not None and obj_node.text.decode("utf-8") != "os":
                continue

            refs.append(EnvVarReference(
                var_name=var_name,
                file_path=str(file_path),
                line=line,
                column=col,
                access_type=AccessType.GO_GETENV.value,
                context=context,
                has_default=False,
            ))

        return refs

    @staticmethod
    def _find_parent_capture(
        captures: list[tuple[Any, str]],
        child_node: Any,
        parent_tag: str,
    ) -> Any | None:
        """Find the parent capture node that contains child_node."""
        for node, tag in captures:
            if tag == parent_tag and node.start_point <= child_node.start_point and node.end_point >= child_node.end_point:
                return node
        return None

    @staticmethod
    def _find_tagged_node(
        captures: list[tuple[Any, str]],
        target_tag: str,
        nearby_node: Any,
    ) -> Any | None:
        """Find a tagged node near the given node (same parent context)."""
        for node, tag in captures:
            if tag == target_tag and abs(node.start_point[0] - nearby_node.start_point[0]) <= 5:
                return node
        return None

    @staticmethod
    def _verify_obj_attr(
        captures: list[tuple[Any, str]],
        nearby_node: Any,
        expected_obj: str,
        expected_attr: str,
    ) -> bool:
        """Verify that obj and attr captures match expected values."""
        obj_match = False
        attr_match = False
        for node, tag in captures:
            if tag == "obj" and node.text.decode("utf-8") == expected_obj:
                if abs(node.start_point[0] - nearby_node.start_point[0]) <= 5:
                    obj_match = True
            if tag == "attr" and node.text.decode("utf-8") == expected_attr:
                if abs(node.start_point[0] - nearby_node.start_point[0]) <= 5:
                    attr_match = True
            if tag in ("attr1", "attr2") and node.text.decode("utf-8") in (expected_attr, "get"):
                if abs(node.start_point[0] - nearby_node.start_point[0]) <= 5:
                    attr_match = True
        return obj_match and attr_match

    @staticmethod
    def _verify_obj_prop(
        captures: list[tuple[Any, str]],
        nearby_node: Any,
        expected_obj: str,
        expected_prop: str,
    ) -> bool:
        """Verify that obj and prop captures match expected values."""
        obj_match = False
        prop_match = False
        for node, tag in captures:
            if tag == "obj" and node.text.decode("utf-8") == expected_obj:
                if abs(node.start_point[0] - nearby_node.start_point[0]) <= 5:
                    obj_match = True
            if tag == "prop" and node.text.decode("utf-8") == expected_prop:
                if abs(node.start_point[0] - nearby_node.start_point[0]) <= 5:
                    prop_match = True
        return obj_match and prop_match

    def _get_context(
        self,
        content: str,
        line: int,
        col: int,
        context_lines: int = 2,
    ) -> str:
        """Get surrounding code context for a reference."""
        lines = content.split("\n")
        start = max(0, line - context_lines - 1)
        end = min(len(lines), line + context_lines)
        context_lines_list = lines[start:end]
        return "\n".join(
            f"{i + start + 1}: {line_content}"
            for i, line_content in enumerate(context_lines_list)
        )

def track_env_vars(
    file_path: str | Path,
    project_root: str | Path | None = None,
    include_defaults: bool = True,
) -> EnvTrackingResult:
    """Track environment variables in a file."""
    if project_root is None:
        project_root = Path(file_path).parent
    tracker = EnvVarTracker(project_root, include_defaults)
    return tracker.track_file(file_path)

def group_by_var_name(
    references: list[EnvVarReference],
) -> dict[str, EnvVarUsage]:
    """Group references by variable name."""
    by_var: dict[str, EnvVarUsage] = {}
    for ref in references:
        if ref.var_name not in by_var:
            by_var[ref.var_name] = EnvVarUsage(var_name=ref.var_name)
        by_var[ref.var_name].add_reference(ref)
    return by_var

def find_unused_declarations(
    declarations: set[str],
    usages: dict[str, EnvVarUsage],
) -> set[str]:
    """Find declared but unused environment variables."""
    used_vars = set(usages.keys())
    return declarations - used_vars
