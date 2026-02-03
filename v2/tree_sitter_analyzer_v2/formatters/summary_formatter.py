"""
Summary formatter for concise code analysis output.

Provides a quick overview of a file's structure without detailed information.
"""

from typing import Any


class SummaryFormatter:
    """
    Format analysis results as a concise summary.

    Outputs key metrics in a human-readable format:
    - File name and language
    - Line counts (total, code, comments, blank)
    - Structural elements (classes, functions, methods)
    - Import count
    - Complexity assessment

    Example output:
        File: symbols.py
        Language: python
        Lines: 357 (Code: 280, Comments: 50, Blank: 27)
        Classes: 3 (SymbolEntry, SymbolTable, SymbolTableBuilder)
        Functions: 0
        Methods: 6 (across all classes)
        Imports: 2
        Complexity: Low (avg 2.5)
    """

    def format(self, result: dict[str, Any]) -> str:
        """
        Format analysis result as summary.

        Args:
            result: Dictionary containing analysis results with keys:
                - file_path: str
                - language: str (optional)
                - classes: list
                - functions: list
                - imports: list
                - metadata: dict (optional)

        Returns:
            Formatted summary string
        """
        lines = []

        # File name (extract basename for cleaner output)
        file_path = result.get("file_path", "unknown")
        if file_path != "unknown":
            from pathlib import Path

            file_path = Path(file_path).name
        lines.append(f"File: {file_path}")

        # Language (if available)
        language = result.get("language", "unknown")
        lines.append(f"Language: {language}")

        # Line counts (from metadata if available)
        metadata = result.get("metadata", {})
        total_lines = metadata.get("total_lines", 0)
        if total_lines > 0:
            # Estimate code/comment/blank if not provided
            code_lines = metadata.get("code_lines", int(total_lines * 0.7))
            comment_lines = metadata.get("comment_lines", int(total_lines * 0.15))
            blank_lines = metadata.get("blank_lines", int(total_lines * 0.15))
            lines.append(
                f"Lines: {total_lines} "
                f"(Code: {code_lines}, Comments: {comment_lines}, Blank: {blank_lines})"
            )

        # Classes
        classes = result.get("classes", [])
        if classes:
            class_names = [c.get("name", "Unknown") for c in classes[:3]]
            if len(classes) > 3:
                class_names_str = ", ".join(class_names) + f", ... (+{len(classes) - 3} more)"
            else:
                class_names_str = ", ".join(class_names)
            lines.append(f"Classes: {len(classes)} ({class_names_str})")
        else:
            lines.append("Classes: 0")

        # Functions (top-level functions, not methods)
        functions = result.get("functions", [])
        lines.append(f"Functions: {len(functions)}")

        # Methods (across all classes)
        total_methods = sum(len(c.get("methods", [])) for c in classes)
        if total_methods > 0:
            lines.append(f"Methods: {total_methods} (across all classes)")

        # Imports
        imports = result.get("imports", [])
        lines.append(f"Imports: {len(imports)}")

        # Complexity (if available)
        complexities = []
        for func in functions:
            if "complexity" in func:
                complexities.append(func["complexity"])
        for cls in classes:
            for method in cls.get("methods", []):
                if "complexity" in method:
                    complexities.append(method["complexity"])

        if complexities:
            avg_complexity = sum(complexities) / len(complexities)
            complexity_level = self._get_complexity_level(avg_complexity)
            lines.append(f"Complexity: {complexity_level} (avg {avg_complexity:.1f})")
        else:
            lines.append("Complexity: N/A")

        return "\n".join(lines)

    def _get_complexity_level(self, avg_complexity: float) -> str:
        """
        Get human-readable complexity level.

        Args:
            avg_complexity: Average cyclomatic complexity

        Returns:
            "Low", "Medium", or "High"
        """
        if avg_complexity < 3:
            return "Low"
        elif avg_complexity < 7:
            return "Medium"
        else:
            return "High"
