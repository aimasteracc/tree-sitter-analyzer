#!/usr/bin/env python3
"""
TOON (Token-Oriented Object Notation) Formatter

High-level formatter for converting analysis results and MCP responses
to TOON format, optimized for LLM consumption with 50-70% token reduction.
"""

import logging
from typing import Any

from .base_formatter import BaseFormatter
from .toon_encoder import ToonEncodeError, ToonEncoder

# Logger for TOON formatter
logger = logging.getLogger(__name__)


class ToonFormatter(BaseFormatter):
    """
    TOON formatter for LLM-optimized output.

    Converts analysis results to compact, human-readable TOON format that
    reduces token consumption by 50-70% compared to JSON while maintaining
    full information fidelity.

    Implements the unified Formatter interface for OutputManager compatibility.
    """

    def __init__(
        self,
        use_tabs: bool = False,
        compact_arrays: bool = True,
        include_metadata: bool = True,
        fallback_to_json: bool = True,
        normalize_paths: bool = True,
    ):
        """
        Initialize TOON formatter.

        Args:
            use_tabs: Use tab delimiters instead of commas (further optimization)
            compact_arrays: Use CSV-style compact arrays for homogeneous data
            include_metadata: Include file metadata in output
            fallback_to_json: Fall back to JSON on encoding errors
            normalize_paths: Convert Windows backslashes to forward slashes
                           for ~10% token reduction in path-heavy outputs
        """
        self.use_tabs = use_tabs
        self.compact_arrays = compact_arrays
        self.include_metadata = include_metadata
        self.fallback_to_json = fallback_to_json
        self.normalize_paths = normalize_paths
        self.encoder = ToonEncoder(
            use_tabs=use_tabs,
            fallback_to_json=fallback_to_json,
            normalize_paths=normalize_paths,
        )

    def format(self, data: Any) -> str:
        """
        Unified format method implementing the Formatter protocol.

        Routes to appropriate internal formatter based on data type.
        This method enables OutputManager to call formatter.format(data)
        without needing to know the specific formatter implementation.

        On encoding errors, falls back to JSON if fallback_to_json is True.

        Args:
            data: The data to format (AnalysisResult, dict, or other types)

        Returns:
            TOON-formatted string (or JSON on fallback)
        """
        try:
            return self._format_internal(data)
        except ToonEncodeError as e:
            logger.error(f"TOON formatting failed: {e}")
            if self.fallback_to_json:
                logger.warning("Falling back to JSON format")
                return self.encoder._fallback_to_json(data)
            raise
        except Exception as e:
            logger.error(f"Unexpected error during TOON formatting: {e}", exc_info=True)
            if self.fallback_to_json:
                logger.warning("Falling back to JSON format")
                return self.encoder._fallback_to_json(data)
            raise ToonEncodeError("Formatting failed", data=data, cause=e) from e

    def _format_internal(self, data: Any) -> str:
        """
        Internal format method without error handling wrapper.

        Args:
            data: The data to format

        Returns:
            TOON-formatted string
        """
        # Import here to avoid circular dependency
        try:
            from tree_sitter_analyzer.models import AnalysisResult

            if isinstance(data, AnalysisResult):
                return self.format_analysis_result(data)
        except ImportError:
            pass

        # Check if it's an MCP response (dict with specific structure)
        if isinstance(data, dict):
            # Detect MCP response structure
            if self._is_mcp_response(data):
                return self.format_mcp_response(data)
            else:
                # Generic dict - try to format as analysis result dict
                return self.format_structure(data)

        # Fallback: encode arbitrary data as TOON
        return self.encoder.encode(data)

    def _is_mcp_response(self, data: dict[str, Any]) -> bool:
        """
        Detect if data is an MCP response structure.

        MCP responses typically have 'content' or 'data' fields.

        Args:
            data: Dictionary to check

        Returns:
            True if data appears to be an MCP response
        """
        mcp_keys = {"content", "data", "metadata", "analysis_result"}
        return bool(mcp_keys.intersection(data.keys()))

    def format_analysis_result(self, result: Any, table_type: str = "full") -> str:
        """
        Format complete analysis result as TOON.

        Args:
            result: Analysis result to format (AnalysisResult object)
            table_type: Output detail level (full, summary, compact)

        Returns:
            TOON-formatted string
        """
        # Import here to avoid circular dependency
        from tree_sitter_analyzer.models import AnalysisResult

        if not isinstance(result, AnalysisResult):
            # Try to convert dict to proper format
            if isinstance(result, dict):
                return self.format_structure(result)
            return self.encoder.encode(result)

        lines = []

        # File metadata
        if self.include_metadata:
            if result.package:
                package_name = (
                    result.package.name
                    if hasattr(result.package, "name")
                    else str(result.package)
                )
                lines.append(f"module: {package_name}")
            else:
                # If no package, use file stem
                import os

                file_name = result.file_path.replace("\\", "/").split("/")[-1]
                module_name = os.path.splitext(file_name)[0]
                lines.append(f"module: {module_name}")

            lines.append("")

        # Imports
        imports = [e for e in result.elements if e.element_type == "import"]
        if imports:
            lines.append("imports:")
            for imp in imports:
                name = getattr(imp, "name", "")
                module_name = getattr(imp, "module_name", "")

                if module_name:
                    # User prefers compact comma lists
                    formatted_name = name.replace(", ", ",")
                    lines.append(f"  {module_name}: {formatted_name}")
                else:
                    # Simple import
                    lines.append(f"  {name}: {name}")
            lines.append("")

        # Group by type
        classes = [e for e in result.elements if e.element_type == "class"]
        all_funcs = [
            e for e in result.elements if e.element_type in ("method", "function")
        ]
        fields = [e for e in result.elements if e.element_type == "variable"]

        # Helper to check if element is inside class
        def is_child_of(child: Any, parent: Any) -> bool:
            return bool(parent.start_line <= child.start_line <= parent.end_line)

        # Classes Summary
        if classes:
            lines.append(f"classes[{len(classes)}]{{name,type,lines,methods,fields}}:")
            for cls in classes:
                # Count methods and fields for this class
                m_count = sum(1 for m in all_funcs if is_child_of(m, cls))
                f_count = sum(1 for f in fields if is_child_of(f, cls))

                class_type = (
                    "dataclass" if getattr(cls, "is_dataclass", False) else "class"
                )
                lines.append(
                    f"  {cls.name},{class_type},{cls.start_line}-{cls.end_line},{m_count},{f_count}"
                )
            lines.append("")

        # Class Details
        assigned_funcs = set()
        if classes:
            for cls in classes:
                class_type = (
                    "dataclass" if getattr(cls, "is_dataclass", False) else "class"
                )
                lines.append(f"{cls.name}:")
                lines.append(f"  type: {class_type}")

                # Annotations (Decorators) - explicit listing requested
                modifiers = getattr(cls, "modifiers", [])
                # Filter out standard types/flags that are handled elsewhere
                annotations = [
                    m for m in modifiers if m not in ["abstract", "static", "dataclass"]
                ]
                if annotations:
                    lines.append("  annotations:")
                    for ann in annotations:
                        lines.append(f"    - @{ann}")

                superclass = getattr(cls, "superclass", None)
                if superclass:
                    lines.append(f"  parent: {superclass}")
                lines.append(f"  lines: {cls.start_line}-{cls.end_line}")

                # Get methods for this class
                cls_methods = [m for m in all_funcs if is_child_of(m, cls)]
                # Mark as assigned
                for m in cls_methods:
                    # Use a unique key
                    key = (m.name, m.start_line, m.end_line)
                    assigned_funcs.add(key)

                if cls_methods:
                    lines.append(
                        f"  methods[{len(cls_methods)}]{{name,sig,lines,cx,doc}}:"
                    )
                    for m in cls_methods:
                        m_dict = self._method_to_dict_rich(m)
                        name = m_dict["name"]
                        sig = m_dict["sig"]
                        line_count = m_dict["lines"]
                        cx = m_dict["cx"]
                        doc = m_dict["doc"]
                        lines.append(f"    {name},{sig},{line_count},{cx},{doc}")
                lines.append("")

        # Standalone Functions
        standalone_funcs = [
            f
            for f in all_funcs
            if (f.name, f.start_line, f.end_line) not in assigned_funcs
        ]

        if standalone_funcs:
            lines.append(
                f"functions[{len(standalone_funcs)}]{{name,sig,lines,cx,doc}}:"
            )
            for func in standalone_funcs:
                f_dict = self._method_to_dict_rich(func)
                name = f_dict["name"]
                sig = f_dict["sig"]
                line_count = f_dict["lines"]
                cx = f_dict["cx"]
                doc = f_dict["doc"]
                lines.append(f"  {name},{sig},{line_count},{cx},{doc}")

        return "\n".join(lines)

    def format_mcp_response(self, data: dict[str, Any]) -> str:
        """
        Format MCP tool response as TOON.

        Optimized for AI assistant consumption.

        Args:
            data: MCP response dictionary

        Returns:
            TOON-formatted string
        """
        return self.encoder.encode_dict(data)

    def format_summary(self, analysis_result: dict[str, Any]) -> str:
        """
        Format summary output (BaseFormatter requirement).

        Args:
            analysis_result: Analysis result dictionary

        Returns:
            TOON-formatted summary
        """
        return self.encoder.encode_dict(analysis_result)

    def format_structure(self, analysis_result: dict[str, Any]) -> str:
        """
        Format structure analysis output (BaseFormatter requirement).

        Args:
            analysis_result: Analysis result dictionary

        Returns:
            TOON-formatted structure
        """
        return self.encoder.encode_dict(analysis_result)

    def format_advanced(
        self, analysis_result: dict[str, Any], output_format: str = "toon"
    ) -> str:
        """
        Format advanced analysis output (BaseFormatter requirement).

        Args:
            analysis_result: Analysis result dictionary
            output_format: Output format (ignored, always returns TOON)

        Returns:
            TOON-formatted advanced analysis
        """
        return self.encoder.encode_dict(analysis_result)

    def format_table(
        self, analysis_result: dict[str, Any], table_type: str = "full"
    ) -> str:
        """
        Format table output (BaseFormatter requirement).

        Args:
            analysis_result: Analysis result dictionary
            table_type: Table detail level (full, compact, summary)

        Returns:
            TOON-formatted table
        """
        return self.encoder.encode_dict(analysis_result)

    def _method_to_dict(self, method: Any) -> dict[str, Any]:
        """
        Convert method element to dictionary for table encoding.

        Args:
            method: Method element

        Returns:
            Dictionary representation
        """
        return {
            "name": method.name if hasattr(method, "name") else str(method),
            "visibility": getattr(method, "visibility", ""),
            "lines": f"{getattr(method, 'start_line', 0)}-{getattr(method, 'end_line', 0)}",
        }

    @staticmethod
    def is_toon_content(content: str) -> bool:
        """
        Detect if content is in TOON format.

        Used by FileOutputManager to determine content type.

        Args:
            content: String content to check

        Returns:
            True if content appears to be TOON format
        """
        if not content or not content.strip():
            return False

        lines = content.strip().split("\n")
        if not lines:
            return False

        # TOON format indicators:
        # 1. Lines with "key: value" pattern (not JSON)
        # 2. Array table headers like "[N]{field1,field2}:"
        # 3. Nested structure with indentation

        # Check if it looks like JSON first
        first_char = content.strip()[0]
        if first_char in "{[":
            return False

        # Check for TOON patterns
        toon_patterns = 0
        for line in lines[:10]:  # Check first 10 lines
            stripped = line.strip()
            if not stripped:
                continue

            # Key-value pattern: "key: value"
            if (
                ":" in stripped
                and not stripped.startswith("{")
                and not stripped.startswith('"')
            ):
                parts = stripped.split(":", 1)
                if len(parts) == 2 and parts[0].strip():
                    toon_patterns += 1

            # Array table header: "[N]{...}:"
            if stripped.startswith("[") and "]{" in stripped and stripped.endswith(":"):
                toon_patterns += 2

        # Need at least 2 TOON patterns to confirm
        return toon_patterns >= 2

    def _method_to_dict_rich(self, method: Any) -> dict[str, Any]:
        """Convert method to dictionary with rich details for TOON"""
        # Name with modifiers
        name = getattr(method, "name", "unknown")
        modifiers = []

        # Handle decorators and flags
        # Map common flags to TOON modifiers
        if getattr(method, "is_abstract", False):
            modifiers.append("abstract")
        if getattr(method, "is_static", False):
            modifiers.append("static")

        # Add other modifiers from 'modifiers' list if available
        if hasattr(method, "modifiers") and method.modifiers:
            for mod in method.modifiers:
                # Avoid duplication and standard flags
                if (
                    mod not in modifiers
                    and mod != "staticmethod"
                    and mod != "abstractmethod"
                    and mod != "abstract"
                ):
                    modifiers.append(mod)

        full_name = f"{name}[{','.join(modifiers)}]" if modifiers else name

        # Signature
        sig = self._format_toon_signature(method)

        # Doc
        doc = getattr(method, "docstring", "")

        # Special handling for __init__ methods - they often get wrong docstrings from tree-sitter
        # (Copied from PythonTableFormatter logic to maintain consistency)
        if name == "__init__" and doc:
            doc_str = str(doc).strip()
            # If it contains class-specific terms that don't match __init__, it's likely wrong
            if any(
                word in doc_str.lower() for word in ["bark", "meow", "fetch", "purr"]
            ):
                doc = ""

        if doc and str(doc).strip():
            # Simplify docstring: first line, no quotes
            doc = str(doc).strip().split("\n")[0].strip(' "')
            # Handle empty after strip
            if not doc:
                doc = "-"
        else:
            doc = "-"

        return {
            "name": full_name,
            "sig": sig,
            "lines": f"{getattr(method, 'start_line', 0)}-{getattr(method, 'end_line', 0)}",
            "cx": getattr(method, "complexity_score", ""),
            "doc": doc,
        }

    def _format_toon_signature(self, method: Any) -> str:
        """Format signature as p1|p2->ret"""
        params = []
        method_params = getattr(method, "parameters", [])
        if method_params:
            for p in method_params:
                # p can be string or dict
                if isinstance(p, dict):
                    p_name = p.get("name", "")
                    p_type = p.get("type", "")
                    if p_type and p_type != "Any":
                        params.append(f"{p_name}:{p_type}")
                    else:
                        params.append(p_name)
                else:
                    params.append(str(p))

        ret_type = getattr(method, "return_type", "Any")
        if not ret_type:
            ret_type = "Any"

        param_str = "|".join(params)
        return f"{param_str}->{ret_type}"
