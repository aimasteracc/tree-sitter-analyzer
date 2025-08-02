#!/usr/bin/env python3
"""
LLM Code Quality Checker

This script provides specialized quality checks for AI/LLM-generated code
to ensure it meets the Tree-sitter Analyzer project standards.

Usage:
    python llm_code_checker.py [file_or_directory]
    python llm_code_checker.py --check-all
    python llm_code_checker.py --help
"""

import argparse
import ast
import re
import sys
from pathlib import Path


# Color codes for output
class Colors:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    END = "\033[0m"


class LLMCodeChecker:
    """Specialized code quality checker for LLM-generated code."""

    def __init__(self):
        self.issues: list[dict[str, str]] = []
        self.files_checked = 0
        self.total_issues = 0

    def check_file(self, file_path: Path) -> bool:
        """Check a single Python file for LLM-specific issues.

        Args:
            file_path: Path to the Python file to check

        Returns:
            True if no issues found, False otherwise
        """
        if not file_path.suffix == ".py":
            return True

        self.files_checked += 1
        print(f"{Colors.BLUE}Checking: {file_path}{Colors.END}")

        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            self._add_issue(file_path, "file_read", f"Cannot read file: {e}")
            return False

        # Parse AST
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            self._add_issue(file_path, "syntax_error", f"Syntax error: {e}")
            return False

        # Run all checks
        self._check_type_hints(file_path, tree, content)
        self._check_docstrings(file_path, tree)
        self._check_error_handling(file_path, tree)
        self._check_imports(file_path, tree, content)
        self._check_naming_conventions(file_path, tree)
        self._check_anti_patterns(file_path, tree, content)
        self._check_project_patterns(file_path, tree, content)

        return (
            len([issue for issue in self.issues if issue["file"] == str(file_path)])
            == 0
        )

    def _add_issue(
        self, file_path: Path, issue_type: str, message: str, line: int | None = None
    ):
        """Add an issue to the list."""
        self.issues.append(
            {
                "file": str(file_path),
                "type": issue_type,
                "message": message,
                "line": line,
            }
        )
        self.total_issues += 1

    def _check_type_hints(self, file_path: Path, tree: ast.AST, content: str):
        """Check for missing type hints."""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Skip private methods and test methods for now
                if node.name.startswith("_") or node.name.startswith("test_"):
                    continue

                # Check return type annotation
                if node.returns is None:
                    self._add_issue(
                        file_path,
                        "missing_return_type",
                        f"Function '{node.name}' missing return type annotation",
                        node.lineno,
                    )

                # Check parameter type annotations
                for arg in node.args.args:
                    if arg.annotation is None and arg.arg != "self":
                        self._add_issue(
                            file_path,
                            "missing_param_type",
                            f"Parameter '{arg.arg}' in function '{node.name}' missing type annotation",
                            node.lineno,
                        )

    def _check_docstrings(self, file_path: Path, tree: ast.AST):
        """Check for missing docstrings."""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.ClassDef):
                # Skip private methods
                if node.name.startswith("_") and not node.name.startswith("__"):
                    continue

                docstring = ast.get_docstring(node)
                if not docstring:
                    node_type = (
                        "Function" if isinstance(node, ast.FunctionDef) else "Class"
                    )
                    self._add_issue(
                        file_path,
                        "missing_docstring",
                        f"{node_type} '{node.name}' missing docstring",
                        node.lineno,
                    )
                elif len(docstring.strip()) < 10:
                    self._add_issue(
                        file_path,
                        "inadequate_docstring",
                        f"Docstring for '{node.name}' is too brief",
                        node.lineno,
                    )

    def _check_error_handling(self, file_path: Path, tree: ast.AST):
        """Check for proper error handling."""
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                # Check for bare except clauses
                if node.type is None:
                    self._add_issue(
                        file_path,
                        "bare_except",
                        "Bare except clause found - use specific exception types",
                        node.lineno,
                    )

                # Check for empty except blocks
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    self._add_issue(
                        file_path,
                        "empty_except",
                        "Empty except block - should handle or re-raise",
                        node.lineno,
                    )

    def _check_imports(self, file_path: Path, tree: ast.AST, content: str):
        """Check import organization and usage."""
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import | ast.ImportFrom):
                imports.append((node.lineno, node))

        # Check if imports are at the top (basic check)
        if imports:
            first_import_line = imports[0][0]
            lines = content.split("\n")

            # Look for non-import, non-comment, non-docstring code before imports
            for _i, line in enumerate(lines[: first_import_line - 1], 1):
                stripped = line.strip()
                if (
                    stripped
                    and not stripped.startswith("#")
                    and not stripped.startswith('"""')
                    and not stripped.startswith("'''")
                    and not stripped.startswith('"""')
                    and "encoding" not in stripped
                ):
                    self._add_issue(
                        file_path,
                        "import_order",
                        "Imports should be at the top of the file",
                        first_import_line,
                    )
                    break

    def _check_naming_conventions(self, file_path: Path, tree: ast.AST):
        """Check naming conventions."""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Check snake_case for functions
                if not re.match(
                    r"^[a-z_][a-z0-9_]*$", node.name
                ) and not node.name.startswith("test"):
                    self._add_issue(
                        file_path,
                        "naming_convention",
                        f"Function '{node.name}' should use snake_case",
                        node.lineno,
                    )

            elif isinstance(node, ast.ClassDef):
                # Check PascalCase for classes
                if not re.match(r"^[A-Z][a-zA-Z0-9]*$", node.name):
                    self._add_issue(
                        file_path,
                        "naming_convention",
                        f"Class '{node.name}' should use PascalCase",
                        node.lineno,
                    )

    def _check_anti_patterns(self, file_path: Path, tree: ast.AST, content: str):
        """Check for common anti-patterns."""
        # Check for mutable default arguments
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for default in node.args.defaults:
                    if isinstance(default, ast.List | ast.Dict | ast.Set):
                        self._add_issue(
                            file_path,
                            "mutable_default",
                            f"Mutable default argument in function '{node.name}'",
                            node.lineno,
                        )

        # Check for string concatenation in loops (basic pattern)
        if "+=" in content and "for " in content:
            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                if "+=" in line and any(
                    "for " in lines[j]
                    for j in range(max(0, i - 5), min(len(lines), i + 5))
                ):
                    self._add_issue(
                        file_path,
                        "string_concatenation",
                        "Potential string concatenation in loop - consider using join()",
                        i,
                    )
                    break

    def _check_project_patterns(self, file_path: Path, tree: ast.AST, content: str):
        """Check for project-specific patterns."""
        # Check for proper exception usage
        if "tree_sitter_analyzer" in str(file_path):
            for node in ast.walk(tree):
                if isinstance(node, ast.Raise):
                    if isinstance(node.exc, ast.Call) and isinstance(
                        node.exc.func, ast.Name
                    ):
                        if node.exc.func.id in ["AnalysisError", "ValidationError"]:
                            pass
                        elif node.exc.func.id in ["Exception", "RuntimeError"]:
                            self._add_issue(
                                file_path,
                                "generic_exception",
                                "Use project-specific exceptions instead of generic ones",
                                node.lineno,
                            )

        # Check for logging usage
        if (
            "log_info" not in content
            and "logger" not in content
            and "print(" in content
        ):
            if not str(file_path).endswith("test_*.py"):
                self._add_issue(
                    file_path,
                    "print_statement",
                    "Use logging instead of print statements",
                )

    def print_summary(self):
        """Print a summary of all issues found."""
        print(f"\n{Colors.BOLD}=== LLM Code Quality Check Summary ==={Colors.END}")
        print(f"Files checked: {self.files_checked}")
        print(f"Total issues: {self.total_issues}")

        if self.total_issues == 0:
            print(
                f"{Colors.GREEN}{Colors.BOLD}✅ All checks passed! Code quality is excellent.{Colors.END}"
            )
            return True

        # Group issues by type
        issues_by_type: dict[str, list[dict]] = {}
        for issue in self.issues:
            issue_type = issue["type"]
            if issue_type not in issues_by_type:
                issues_by_type[issue_type] = []
            issues_by_type[issue_type].append(issue)

        # Print issues by type
        for issue_type, type_issues in issues_by_type.items():
            print(
                f"\n{Colors.RED}{Colors.BOLD}{issue_type.replace('_', ' ').title()} ({len(type_issues)} issues):{Colors.END}"
            )
            for issue in type_issues:
                line_info = f":{issue['line']}" if issue["line"] else ""
                print(
                    f"  {Colors.YELLOW}{issue['file']}{line_info}{Colors.END} - {issue['message']}"
                )

        print(
            f"\n{Colors.MAGENTA}💡 Tip: Review the LLM_CODING_GUIDELINES.md for detailed guidance.{Colors.END}"
        )
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="LLM Code Quality Checker")
    parser.add_argument(
        "path", nargs="?", default=".", help="File or directory to check"
    )
    parser.add_argument(
        "--check-all", action="store_true", help="Check all Python files in the project"
    )

    args = parser.parse_args()

    checker = LLMCodeChecker()

    if args.check_all:
        target_path = Path(".")
    else:
        target_path = Path(args.path)

    if not target_path.exists():
        print(f"{Colors.RED}Error: Path {target_path} does not exist{Colors.END}")
        sys.exit(1)

    # Collect files to check
    if target_path.is_file():
        files_to_check = [target_path]
    else:
        files_to_check = list(target_path.rglob("*.py"))
        # Exclude certain directories
        files_to_check = [
            f
            for f in files_to_check
            if not any(part.startswith(".") for part in f.parts)
            and "venv" not in str(f)
            and "__pycache__" not in str(f)
        ]

    print(f"{Colors.CYAN}{Colors.BOLD}🤖 LLM Code Quality Checker{Colors.END}")
    print(f"Checking {len(files_to_check)} Python files...\n")

    for file_path in files_to_check:
        if not checker.check_file(file_path):
            pass

    success = checker.print_summary()

    if not success:
        sys.exit(1)

    print(f"\n{Colors.GREEN}🎉 Code quality check completed successfully!{Colors.END}")


if __name__ == "__main__":
    main()
