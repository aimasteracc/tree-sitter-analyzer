"""Change Impact Analyzer — answers 'what breaks if I change this file?'."""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ImpactItem:
    """A single file affected by a change."""

    path: str
    relation: str  # "direct" | "transitive" | "tool" | "test"
    distance: int  # 0 = changed file, 1 = direct dependent, 2+ = transitive


@dataclass(frozen=True)
class ChangeImpactResult:
    """Result of change impact analysis."""

    changed_files: tuple[str, ...]
    impacted: tuple[ImpactItem, ...]
    affected_tools: tuple[str, ...]
    affected_tests: tuple[str, ...]

    @property
    def total_impact_count(self) -> int:
        return len(self.impacted) + len(self.affected_tools) + len(self.affected_tests)

    @property
    def direct_count(self) -> int:
        return sum(1 for i in self.impacted if i.distance == 1)

    @property
    def transitive_count(self) -> int:
        return sum(1 for i in self.impacted if i.distance > 1)


class ChangeImpactAnalyzer:
    """Analyzes the blast radius of file changes across the project.

    Project-level tool (exempt from BaseAnalyzer) — takes project_root,
    not single file_path.
    """

    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).resolve()

    def analyze(self, changed_files: list[str | Path]) -> ChangeImpactResult:
        changed = tuple(self._rel(str(f)) for f in changed_files)

        reverse_map = self._build_reverse_import_map()
        impacted = self._find_transitive_dependents(changed, reverse_map)
        affected_tools = self._find_affected_tools(changed, impacted)
        affected_tests = self._find_affected_tests(changed, impacted)

        return ChangeImpactResult(
            changed_files=changed,
            impacted=tuple(impacted),
            affected_tools=tuple(affected_tools),
            affected_tests=tuple(affected_tests),
        )

    # -- Import graph ----------------------------------------------------------

    def _build_reverse_import_map(self) -> dict[str, set[str]]:
        """Return {imported_path -> {importing_paths}} for all project .py files."""
        reverse: dict[str, set[str]] = {}

        for py_file in self.project_root.rglob("*.py"):
            rel = self._rel(str(py_file))
            for module_name in self._extract_imports(py_file):
                resolved = self._resolve_module(module_name)
                if resolved is not None:
                    reverse.setdefault(resolved, set()).add(rel)

        return reverse

    def _extract_imports(self, py_file: Path) -> list[str]:
        """Parse import statements from a Python file using AST."""
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError, OSError):
            return []

        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        return imports

    def _resolve_module(self, module_name: str) -> str | None:
        """Resolve a dot-path import to a project-relative .py file path."""
        parts = module_name.split(".")
        candidate = self.project_root
        for part in parts:
            candidate = candidate / part

        # Package directory with __init__.py
        if candidate.is_dir() and (candidate / "__init__.py").exists():
            return self._rel(str(candidate / "__init__.py"))

        # Module file
        py_path = candidate.with_suffix(".py")
        if py_path.exists():
            return self._rel(str(py_path))

        return None

    # -- Transitive dependents -------------------------------------------------

    def _find_transitive_dependents(
        self,
        changed: tuple[str, ...],
        reverse_map: dict[str, set[str]],
        max_depth: int = 10,
    ) -> list[ImpactItem]:
        visited: set[str] = set(changed)
        result: list[ImpactItem] = []
        queue: list[tuple[str, int]] = [(f, 1) for f in changed]

        while queue:
            current, depth = queue.pop(0)
            if depth > max_depth:
                continue
            for dep in sorted(reverse_map.get(current, set())):
                if dep not in visited:
                    visited.add(dep)
                    result.append(
                        ImpactItem(
                            path=dep,
                            relation="direct" if depth == 1 else "transitive",
                            distance=depth,
                        )
                    )
                    queue.append((dep, depth + 1))

        return result

    # -- Tool cross-reference --------------------------------------------------

    def _find_affected_tools(
        self,
        changed: tuple[str, ...],
        impacted: list[ImpactItem],
    ) -> list[str]:
        all_paths = set(changed) | {i.path for i in impacted}
        analyzer_names = {
            Path(p).stem
            for p in all_paths
            if "analysis" in p and p.endswith(".py")
        }
        if not analyzer_names:
            return []

        tools_dir = self.project_root / "tree_sitter_analyzer" / "mcp" / "tools"
        if not tools_dir.exists():
            return []

        affected: list[str] = []
        for tool_file in sorted(tools_dir.glob("*_tool.py")):
            if tool_file.name in ("base_tool.py", "__init__.py"):
                continue
            try:
                content = tool_file.read_text(encoding="utf-8")
            except OSError:
                continue

            for analyzer in sorted(analyzer_names):
                if analyzer in content:
                    tool_name = tool_file.stem.removesuffix("_tool")
                    affected.append(f"{tool_name} <- {analyzer}")
                    break

        return affected

    # -- Test cross-reference --------------------------------------------------

    def _find_affected_tests(
        self,
        changed: tuple[str, ...],
        impacted: list[ImpactItem],
    ) -> list[str]:
        all_paths = set(changed) | {i.path for i in impacted}
        tests_dir = self.project_root / "tests"
        if not tests_dir.exists():
            return []

        affected: list[str] = []
        for path in sorted(all_paths):
            stem = Path(path).stem
            for test_file in sorted(tests_dir.rglob(f"test_{stem}.py")):
                affected.append(self._rel(str(test_file)))
            # Also check broader pattern
            for test_file in sorted(tests_dir.rglob("test_*.py")):
                rel = self._rel(str(test_file))
                if stem in Path(test_file).stem and rel not in affected:
                    affected.append(rel)

        return affected

    # -- Helpers ---------------------------------------------------------------

    def _rel(self, abs_path: str) -> str:
        try:
            return str(Path(abs_path).relative_to(self.project_root)).replace("\\", "/")
        except ValueError:
            return abs_path.replace("\\", "/")
