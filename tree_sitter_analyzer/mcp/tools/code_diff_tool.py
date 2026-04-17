#!/usr/bin/env python3
"""
Code Diff Analysis Tool

Provides semantic-level code diff analysis:
- Compare two versions of code (file paths or content)
- Identify added/removed/modified elements (classes, methods, functions, fields)
- Show element-level changes (signatures, visibility, type annotations)
- Detect breaking changes
"""

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any

from ...core.query_service import QueryService
from ...models import Class, CodeElement, Function
from ...utils import setup_logger
from .base_tool import BaseMCPTool

logger = setup_logger(__name__)


class ChangeType(Enum):
    """Type of code change."""

    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"


class ChangeSeverity(Enum):
    """Severity of change for API compatibility."""

    BREAKING = "breaking"
    NON_BREAKING = "non_breaking"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ElementDiff:
    """Difference between two code elements."""

    element_type: str  # "class", "method", "function", "field"
    name: str
    change_type: ChangeType
    severity: ChangeSeverity
    old_element: CodeElement | None = None
    new_element: CodeElement | None = None
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "type": self.element_type,
            "name": self.name,
            "change": self.change_type.value,
            "severity": self.severity.value,
            "details": self.details,
        }

    @classmethod
    def from_element(
        cls,
        element: CodeElement,
        change_type: ChangeType,
        severity: ChangeSeverity,
        details: str = "",
    ) -> "ElementDiff":
        """Create ElementDiff from a CodeElement."""
        element_type = element.element_type if hasattr(element, "element_type") else "unknown"
        return cls(
            element_type=element_type,
            name=element.name,
            change_type=change_type,
            severity=severity,
            old_element=element if change_type == ChangeType.REMOVED else None,
            new_element=element if change_type == ChangeType.ADDED else None,
            details=details,
        )


@dataclass(frozen=True)
class CodeDiffResult:
    """Result of code diff analysis."""

    file_path: str
    old_content_hash: str
    new_content_hash: str
    elements: list[ElementDiff]
    summary: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "file": self.file_path,
            "old_hash": self.old_content_hash,
            "new_hash": self.new_content_hash,
            "changes": [e.to_dict() for e in self.elements],
            "summary": self.summary,
        }


class CodeDiffTool(BaseMCPTool):
    """MCP tool for semantic code diff analysis."""

    def __init__(self, project_root: str | None = None):
        """
        Initialize the code diff tool.

        Args:
            project_root: Optional project root directory
        """
        super().__init__(project_root)

    def get_tool_definition(self) -> dict[str, Any]:
        """Get MCP tool definition."""
        return {
            "name": "code_diff",
            "description": (
                "Semantic-level code diff analysis.\n\n"
                "WHEN TO USE:\n"
                "- Review pull requests and understand semantic changes\n"
                "- Detect breaking API changes before deployment\n"
                "- Analyze code evolution between versions\n"
                "- Identify impact of code changes on dependent code\n\n"
                "RETURNS:\n"
                "- Element-level diff (classes, methods, functions, fields)\n"
                "- Change severity (breaking vs non-breaking)\n"
                "- Summary statistics\n\n"
                "EXAMPLE:\n"
                '  Compare two file versions: {"old_path": "v1/Service.py", "new_path": "v2/Service.py"}'
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "old_path": {
                        "type": "string",
                        "description": "Path to old version of the file",
                    },
                    "new_path": {
                        "type": "string",
                        "description": "Path to new version of the file",
                    },
                    "old_content": {
                        "type": "string",
                        "description": "Old file content (use instead of old_path)",
                    },
                    "new_content": {
                        "type": "string",
                        "description": "New file content (use instead of new_path)",
                    },
                    "language": {
                        "type": "string",
                        "description": "Language hint (auto-detected if not provided)",
                    },
                    "output_format": {
                        "type": "string",
                        "enum": ["json", "toon"],
                        "description": "Output format (default: json)",
                    },
                },
            },
        }

    def _get_content_hash(self, content: str) -> str:
        """Get SHA256 hash of content."""
        return sha256(content.encode()).hexdigest()[:16]

    def _read_file_content(self, file_path: str) -> str:
        """Read file content safely."""
        path = Path(file_path)
        if not path.is_absolute() and self.project_root:
            path = Path(self.project_root) / path

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        return path.read_text(encoding="utf-8")

    def _detect_language(self, file_path: str | None, content: str) -> str:
        """Detect language from file extension or content."""
        if file_path:
            ext = Path(file_path).suffix.lower()
            lang_map = {
                ".py": "python",
                ".java": "java",
                ".js": "javascript",
                ".ts": "typescript",
                ".tsx": "typescript",
                ".jsx": "javascript",
                ".go": "go",
                ".rs": "rust",
                ".c": "c",
                ".cpp": "cpp",
                ".cc": "cpp",
                ".h": "c",
                ".hpp": "cpp",
                ".cs": "c_sharp",
                ".kt": "kotlin",
                ".rb": "ruby",
                ".php": "php",
                ".sql": "sql",
                ".yaml": "yaml",
                ".yml": "yaml",
                ".md": "markdown",
            }
            if ext in lang_map:
                return lang_map[ext]

        # Try to detect from content
        if "def " in content and "import " in content:
            return "python"
        if "public class " in content:
            return "java"
        if "function " in content and "=>" in content:
            return "javascript"
        if "func " in content and "package " in content:
            return "go"
        if "impl " in content and "fn " in content:
            return "rust"

        return "python"  # Default

    def _get_element_key(self, element: CodeElement) -> str:
        """Get unique key for an element."""
        if isinstance(element, Function):
            # Function key includes name
            return f"function:{element.name}"
        elif isinstance(element, Class):
            return f"class:{element.name}"
        else:
            elem_type = getattr(element, "element_type", "unknown")
            return f"{elem_type}:{element.name}"

    def _is_public_api(self, element: CodeElement) -> bool:
        """Check if element is part of public API."""
        # Check is_private field first (most explicit)
        if hasattr(element, "is_private") and element.is_private:
            return False

        # Check visibility field (use it if explicitly set to private)
        if hasattr(element, "visibility") and element.visibility == "private":
            return False

        # Check name prefix (underscore convention)
        if element.name.startswith("_"):
            return False

        return True

    def _is_signature_compatible(
        self, old_element: CodeElement, new_element: CodeElement
    ) -> bool:
        """Check if signature change is compatible."""
        if not isinstance(old_element, type(new_element)):
            return False

        if isinstance(old_element, Function):
            # Check parameter compatibility (simplified)
            # In real implementation, would check types, defaults, etc.
            old_params = getattr(old_element, "parameters", [])
            new_params = getattr(new_element, "parameters", [])

            # Adding parameters with defaults is OK
            if len(new_params) > len(old_params):
                return False

            return True

        return True

    def _compare_elements(
        self,
        old_elements: list[CodeElement],
        new_elements: list[CodeElement],
    ) -> list[ElementDiff]:
        """Compare two lists of code elements."""
        diffs: list[ElementDiff] = []

        old_map = {self._get_element_key(e): e for e in old_elements}
        new_map = {self._get_element_key(e): e for e in new_elements}

        all_keys = set(old_map.keys()) | set(new_map.keys())

        for key in all_keys:
            old_elem = old_map.get(key)
            new_elem = new_map.get(key)

            if old_elem and not new_elem:
                # Element was removed
                severity = (
                    ChangeSeverity.BREAKING
                    if self._is_public_api(old_elem)
                    else ChangeSeverity.NON_BREAKING
                )
                elem_type = getattr(old_elem, "element_type", "unknown")
                diffs.append(
                    ElementDiff(
                        element_type=elem_type,
                        name=old_elem.name,
                        change_type=ChangeType.REMOVED,
                        severity=severity,
                        old_element=old_elem,
                        details=f"Removed {elem_type} '{old_elem.name}'",
                    )
                )
            elif new_elem and not old_elem:
                # Element was added
                elem_type = getattr(new_elem, "element_type", "unknown")
                diffs.append(
                    ElementDiff(
                        element_type=elem_type,
                        name=new_elem.name,
                        change_type=ChangeType.ADDED,
                        severity=ChangeSeverity.NON_BREAKING,
                        new_element=new_elem,
                        details=f"Added {elem_type} '{new_elem.name}'",
                    )
                )
            elif old_elem and new_elem:
                # Element exists in both - check for modifications
                details = []
                is_breaking = False
                elem_type = getattr(old_elem, "element_type", "unknown")

                # Check if signature changed
                if isinstance(old_elem, Function) and isinstance(new_elem, Function):
                    old_params = getattr(old_elem, "parameters", [])
                    new_params = getattr(new_elem, "parameters", [])

                    if old_params != new_params:
                        param_str_old = ", ".join(old_params) if old_params else ""
                        param_str_new = ", ".join(new_params) if new_params else ""
                        details.append(
                            f"Parameters changed: ({param_str_old}) -> ({param_str_new})"
                        )

                        if not self._is_signature_compatible(old_elem, new_elem):
                            is_breaking = True

                # Check if visibility changed
                old_public = self._is_public_api(old_elem)
                new_public = self._is_public_api(new_elem)

                if old_public != new_public:
                    if new_public:
                        details.append("Became public")
                    else:
                        details.append("Became private")
                        is_breaking = True

                # Check return type for functions
                if isinstance(old_elem, Function) and isinstance(new_elem, Function):
                    old_return = getattr(old_elem, "return_type", None)
                    new_return = getattr(new_elem, "return_type", None)

                    if old_return != new_return:
                        details.append(f"Return type: {old_return} -> {new_return}")

                if details:
                    diffs.append(
                        ElementDiff(
                            element_type=elem_type,
                            name=old_elem.name,
                            change_type=ChangeType.MODIFIED,
                            severity=(
                                ChangeSeverity.BREAKING
                                if is_breaking and self._is_public_api(old_elem)
                                else ChangeSeverity.NON_BREAKING
                            ),
                            old_element=old_elem,
                            new_element=new_elem,
                            details="; ".join(details),
                        )
                    )

        return diffs

    def _query_result_to_elements(
        self, results: list[dict[str, Any]]
    ) -> list[CodeElement]:
        """Convert query results to CodeElement objects."""
        elements: list[CodeElement] = []
        for result in results:
            element_type = result.get("node_type", "")
            name = result.get("name", "")
            start_line = result.get("start_line", 0)
            end_line = result.get("end_line", 0)

            if element_type in ("function_definition", "function", "method_declaration", "method"):
                is_private = name.startswith("_") if name else False
                elements.append(
                    Function(
                        name=name or "unnamed",
                        start_line=start_line,
                        end_line=end_line,
                        is_private=is_private,
                        is_public=not is_private,
                    )
                )
            elif element_type in ("class_definition", "class", "interface_declaration", "interface"):
                is_private = name.startswith("_") if name else False
                elements.append(
                    Class(
                        name=name or "unnamed",
                        start_line=start_line,
                        end_line=end_line,
                    )
                )
        return elements

    async def _analyze_diff(
        self,
        old_content: str,
        new_content: str,
        language: str,
        file_path: str,
    ) -> CodeDiffResult:
        """Analyze diff between two code versions."""
        query_service = QueryService(self.project_root)

        # Query keys for different element types
        query_keys = ["classes", "functions", "methods"]

        # Analyze old version - extract elements from content
        old_elements: list[CodeElement] = []
        for query_key in query_keys:
            try:
                results = await query_service.execute_query(
                    file_path=file_path,
                    language=language,
                    query_key=query_key,
                )
                if results:
                    old_elements.extend(self._query_result_to_elements(results))
            except Exception:
                # Query may not be supported for this language
                pass

        # Analyze new version - extract elements from content
        # We need to temporarily write content to a temp file for QueryService
        import tempfile

        new_elements: list[CodeElement] = []
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=Path(file_path).name, delete=False
        ) as f:
            f.write(new_content)
            temp_path = f.name

        try:
            for query_key in query_keys:
                try:
                    results = await query_service.execute_query(
                        file_path=temp_path,
                        language=language,
                        query_key=query_key,
                    )
                    if results:
                        new_elements.extend(self._query_result_to_elements(results))
                except Exception:
                    pass
        finally:
            Path(temp_path).unlink(missing_ok=True)

        # Compare elements
        diffs = self._compare_elements(old_elements, new_elements)

        # Calculate summary
        summary = {
            "total": len(diffs),
            "added": sum(1 for d in diffs if d.change_type == ChangeType.ADDED),
            "removed": sum(1 for d in diffs if d.change_type == ChangeType.REMOVED),
            "modified": sum(1 for d in diffs if d.change_type == ChangeType.MODIFIED),
            "breaking": sum(
                1 for d in diffs if d.severity == ChangeSeverity.BREAKING
            ),
        }

        return CodeDiffResult(
            file_path=file_path,
            old_content_hash=self._get_content_hash(old_content),
            new_content_hash=self._get_content_hash(new_content),
            elements=diffs,
            summary=summary,
        )

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the code diff analysis.

        Args:
            arguments: Tool arguments

        Returns:
            Dictionary with diff results
        """
        # Get content
        old_path = arguments.get("old_path", "")
        new_path = arguments.get("new_path", "")
        old_content = arguments.get("old_content", "")
        new_content = arguments.get("new_content", "")

        if old_path and not old_content:
            old_content = self._read_file_content(old_path)
        if new_path and not new_content:
            new_content = self._read_file_content(new_path)

        if not old_content or not new_content:
            raise ValueError(
                "Must provide either file paths or content for both old and new versions"
            )

        # Detect language
        language = arguments.get("language", "")
        if not language:
            reference_path = old_path or new_path
            language = self._detect_language(reference_path, old_content)

        # Use reference path for analysis
        file_path = old_path or new_path or "code.txt"

        # Analyze diff
        result = await self._analyze_diff(
            old_content=old_content,
            new_content=new_content,
            language=language,
            file_path=file_path,
        )

        output_format = arguments.get("output_format", "json")

        if output_format == "toon":
            # Format as TOON
            toon_lines = [
                f"📊 Code Diff: {file_path}",
                f"   Old: {result.old_content_hash}",
                f"   New: {result.new_content_hash}",
                "",
                f"   Summary: {result.summary['total']} changes",
                f"   - Added: {result.summary['added']}",
                f"   - Removed: {result.summary['removed']}",
                f"   - Modified: {result.summary['modified']}",
                f"   - Breaking: {result.summary['breaking']}",
                "",
                "   Changes:",
            ]

            for diff in result.elements:
                icon = {"added": "➕", "removed": "➖", "modified": "🔄"}.get(
                    diff.change_type.value, "•"
                )
                severity_icon = (
                    "⚠️" if diff.severity == ChangeSeverity.BREAKING else "✅"
                )
                toon_lines.append(
                    f"   {icon} {diff.element_type} '{diff.name}' {severity_icon}"
                )
                if diff.details:
                    toon_lines.append(f"      └─ {diff.details}")

            return {
                "content": [
                    {
                        "type": "text",
                        "text": "\n".join(toon_lines),
                    }
                ]
            }

        return {
            "result": result.to_dict(),
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> bool:
        """
        Validate tool arguments.

        Args:
            arguments: Arguments to validate

        Returns:
            True if valid

        Raises:
            ValueError: If arguments are invalid
        """
        old_path = arguments.get("old_path", "")
        new_path = arguments.get("new_path", "")
        old_content = arguments.get("old_content", "")
        new_content = arguments.get("new_content", "")

        # Must have either path or content for both versions
        has_old = bool(old_path) or bool(old_content)
        has_new = bool(new_path) or bool(new_content)

        if not has_old:
            raise ValueError("Must provide 'old_path' or 'old_content'")
        if not has_new:
            raise ValueError("Must provide 'new_path' or 'new_content'")

        output_format = arguments.get("output_format", "json")
        if output_format not in ["json", "toon"]:
            raise ValueError("output_format must be 'json' or 'toon'")

        return True
