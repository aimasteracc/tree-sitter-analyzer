"""Project Brain — pre-warmed holistic model of the entire codebase.

On initialization, the Brain scans every source file, runs applicable neurons,
and builds a living perception map + impact graph. Any query is answered
instantly from the pre-computed model — no per-request scanning needed.

Two subsystems:
  1. Perception Layer: runs all analyzers, finds hotspots, computes health
  2. Impact Graph: tracks imports, calls, tests, tools — answers "what breaks if I change X?"

Usage:
    brain = ProjectBrain("/path/to/project")
    brain.warm_up()  # scans all files, builds perception + impact graph

    # Perception queries
    brain.get_file_perception("src/foo.py")
    brain.get_hotspots()
    brain.get_health_score()

    # Impact graph queries
    brain.blast_radius(["src/foo.py"])       # what's affected?
    brain.affected_tests(["src/foo.py"])      # which tests to run?
    brain.what_happens_if_i_change("src/foo.py", line=42)
"""
from __future__ import annotations

import ast
import hashlib
import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tree_sitter_analyzer.analysis.causal_chain import CausalChain, CausalResult
from tree_sitter_analyzer.analysis.neural_perception import (
    NeuralPerception,
    PerceptionMap,
)
from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

_SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".c", ".cpp",
    ".hpp", ".h", ".cs", ".kt", ".rs", ".rb", ".php", ".swift", ".scala",
    ".sh", ".css", ".html", ".json", ".jsonc", ".json5", ".yaml", ".yml",
    ".md", ".sql",
}


@dataclass(frozen=True)
class FileKnowledge:
    """Pre-computed knowledge about a single file."""
    path: str
    language: str
    line_count: int
    health_score: float
    perception_score: float
    total_findings: int
    fired_neurons: int
    total_neurons: int
    severity_distribution: dict[str, int]
    category_coverage: dict[str, int]
    critical_hotspot_lines: tuple[int, ...]
    top_issues: tuple[str, ...]


@dataclass(frozen=True)
class BlastRadius:
    """Result of an impact query: what's affected if I change these files."""

    changed: tuple[str, ...]
    files: tuple[str, ...]
    tests: tuple[str, ...]
    tools: tuple[str, ...]
    max_depth: int

    @property
    def total(self) -> int:
        return len(self.files) + len(self.tests) + len(self.tools)

    def to_text(self) -> str:
        lines: list[str] = [
            f"Blast Radius: {len(self.changed)} change(s) → {self.total} impacted"
        ]
        lines.append("=" * 55)
        for c in self.changed:
            lines.append(f"  Changed: {c}")
        if self.files:
            lines.append(f"\n  Files ({len(self.files)}):")
            for f in sorted(self.files)[:25]:
                lines.append(f"    - {f}")
            if len(self.files) > 25:
                lines.append(f"    ... +{len(self.files) - 25} more")
        if self.tests:
            lines.append(f"\n  Tests to run ({len(self.tests)}):")
            for t in sorted(self.tests)[:15]:
                lines.append(f"    - {t}")
            if len(self.tests) > 15:
                lines.append(f"    ... +{len(self.tests) - 15} more")
        if self.tools:
            lines.append(f"\n  MCP tools ({len(self.tools)}):")
            for t in sorted(self.tools):
                lines.append(f"    - {t}")
        return "\n".join(lines)


@dataclass
class ProjectBrain:
    """Pre-warmed holistic model of the entire project.

    Warm-up scans all source files once. After that, every query is
    answered from the pre-computed model — zero re-scanning.
    """
    project_root: str
    _file_map: dict[str, FileKnowledge] = field(default_factory=dict)
    _hotspots: list[dict[str, Any]] = field(default_factory=list)
    _warm_time: float = 0.0
    _warm_duration: float = 0.0
    _file_hashes: dict[str, str] = field(default_factory=dict)
    _total_files: int = 0
    _total_lines: int = 0
    _overall_health: float = 100.0
    _category_totals: dict[str, int] = field(default_factory=dict)
    _severity_totals: dict[str, int] = field(default_factory=dict)
    _language_distribution: dict[str, int] = field(default_factory=dict)
    _causal_chain: CausalChain | None = None
    _causal_result: CausalResult | None = None
    # Impact graph
    _import_graph: dict[str, set[str]] = field(default_factory=dict)
    _reverse_imports: dict[str, set[str]] = field(default_factory=dict)
    _test_to_source: dict[str, set[str]] = field(default_factory=dict)
    _source_to_tests: dict[str, set[str]] = field(default_factory=dict)
    _source_to_real_tests: dict[str, set[str]] = field(default_factory=dict)  # tests that actually call source code
    _source_stems: dict[str, str] = field(default_factory=dict)
    _tool_refs: dict[str, set[str]] = field(default_factory=dict)
    _symbol_defs: dict[str, str] = field(default_factory=dict)  # symbol_name → file_rel
    _file_hashes: dict[str, str] = field(default_factory=dict)  # rel_path → md5

    def warm_up(self) -> None:
        """Scan all project files and build the perception model."""
        start = time.monotonic()
        self._file_map = {}
        self._hotspots = []
        self._total_lines = 0
        self._language_distribution = defaultdict(int)
        self._category_totals = defaultdict(int)
        self._severity_totals = defaultdict(int)

        perception = NeuralPerception()
        files = self._collect_files()
        self._total_files = len(files)

        all_hotspots: list[dict[str, Any]] = []
        health_scores: list[float] = []

        for fpath in files:
            try:
                pmap = perception.perceive_file(fpath)
                knowledge = self._build_knowledge(fpath, pmap)
                self._file_map[fpath] = knowledge
                health_scores.append(knowledge.health_score)

                for h in pmap.hotspots:
                    all_hotspots.append({
                        "file": fpath,
                        "line": h.line,
                        "end_line": h.end_line,
                        "analyzer_count": h.analyzer_count,
                        "analyzer_names": h.analyzer_names,
                        "max_severity": h.max_severity.value,
                        "finding_types": h.finding_types,
                    })

                ext = Path(fpath).suffix.lower()
                self._language_distribution[ext] = self._language_distribution.get(ext, 0) + 1
            except Exception as e:
                logger.debug("Brain skip %s: %s", fpath, e)

        all_hotspots.sort(key=lambda h: h["analyzer_count"], reverse=True)
        self._hotspots = all_hotspots
        self._overall_health = (
            sum(health_scores) / len(health_scores) if health_scores else 100.0
        )
        self._warm_duration = time.monotonic() - start
        self._warm_time = time.time()
        self._run_causal_analysis()
        self._build_impact_graph()
        self._write_brain_state()

    def _run_causal_analysis(self) -> None:
        self._causal_chain = CausalChain(self.project_root)
        self._causal_result = self._causal_chain.build_causal_model(
            self._file_map, self._hotspots
        )

    def get_leverage_points(self) -> list[dict[str, Any]]:
        if self._causal_result is None:
            return []
        result: list[dict[str, Any]] = self._causal_result.to_dict()["leverage_points"]
        return result

    def get_the_one_thread(self) -> dict[str, Any] | None:
        if self._causal_result is None:
            return None
        thread: dict[str, Any] | None = self._causal_result.to_dict()["the_one_thread"]
        return thread

    def _write_brain_state(self) -> None:
        state_path = Path(self.project_root) / ".brain_state"
        lines: list[str] = []
        lines.append("## ⚡ BRAIN_STATE")
        lines.append(
            f"elapsed={self._warm_duration:.1f}s "
            f"files={self._total_files} "
            f"hotspots={len(self._hotspots)} "
            f"health={self.get_health_score()}"
        )
        lines.append("")
        lines.append("### FILE_PERCEPTIONS")
        for path, fk in sorted(
            self._file_map.items(), key=lambda x: x[1].health_score
        ):
            short = path.split("tree_sitter_analyzer/")[-1]
            filled = int(fk.health_score / 5)
            bar = "▓" * filled + "░" * (20 - filled)
            sev = "|".join(
                f"{k}:{v}"
                for k, v in sorted(fk.severity_distribution.items())
            )
            lines.append(
                f"  {short:35s} {bar} {fk.health_score:5.1f}h "
                f"{fk.total_findings:3d}f "
                f"{fk.fired_neurons:2d}/{fk.total_neurons:2d}n "
                f"[{sev}]"
            )
        lines.append("")
        lines.append("### SYNAPSES")
        for h in self._hotspots[:20]:
            short = h["file"].split("tree_sitter_analyzer/")[-1]
            intensity = "⚡" * min(h["analyzer_count"], 8)
            neurons = "|".join(h["analyzer_names"][:5])
            lines.append(
                f"  {intensity:8s} {short}:{h['line']:<4d} "
                f"[{h['max_severity']:8s}] ← {neurons}"
            )
        lines.append("")
        lines.append("### DIAGNOSIS")
        for path, fk in sorted(
            self._file_map.items(), key=lambda x: x[1].health_score
        ):
            if fk.health_score < 95 and fk.total_findings > 100:
                short = path.split("tree_sitter_analyzer/")[-1]
                lines.append(
                    f"  FIX: {short} {fk.health_score:.1f}h "
                    f"{fk.total_findings}f → needs attention"
                )

        if self._causal_result is not None:
            lines.append("")
            lines.append("### LEVERAGE (pull this thread → N problems disappear)")
            for lp in self._causal_result.leverage_points[:10]:
                marker = "🔴" if lp.hotspot_count >= 10 else "🟡"
                lines.append(
                    f"  {marker} {lp.action:50s} → {lp.hotspot_count:3d}⚡ "
                    f"({lp.file_count} files) [{lp.kind}]"
                )
            if self._causal_result.the_one_thread:
                one = self._causal_result.the_one_thread
                lines.append("")
                lines.append("### THE ONE THREAD")
                lines.append(f"  {one.cascade}")
        try:
            state_path.write_text("\n".join(lines))
        except OSError:
            pass

    def warm_up_incremental(self, changed_files: list[str]) -> None:
        """Re-scan only changed files. Skips unchanged."""
        perception = NeuralPerception()
        for fpath in changed_files:
            current_hash = self._file_hash(fpath)
            if (fpath in self._file_map
                    and self._file_hashes.get(fpath) == current_hash):
                continue
            try:
                pmap = perception.perceive_file(fpath)
                self._file_map[fpath] = self._build_knowledge(fpath, pmap)
                self._file_hashes[fpath] = current_hash
            except Exception as e:
                logger.debug("Brain incremental skip %s: %s", fpath, e)

    def get_file_perception(self, file_path: str) -> FileKnowledge | None:
        """Instant lookup — no re-scanning."""
        resolved = str(Path(file_path).resolve())
        return self._file_map.get(resolved) or self._file_map.get(file_path)

    def get_hotspots(self, min_analyzers: int = 2) -> list[dict[str, Any]]:
        return [h for h in self._hotspots
                if h["analyzer_count"] >= min_analyzers]

    def get_health_score(self) -> float:
        return round(self._overall_health, 1)

    def what_happens_if_i_change(
        self, file_path: str, line: int | None = None
    ) -> dict[str, Any]:
        """Predict impact of changing a file/line."""
        knowledge = self.get_file_perception(file_path)
        if knowledge is None:
            return {"error": f"Unknown file: {file_path}"}

        result: dict[str, Any] = {
            "file": file_path,
            "current_health": knowledge.health_score,
            "existing_findings": knowledge.total_findings,
            "active_neurons": knowledge.fired_neurons,
            "warnings": [],
        }

        if line is not None:
            affected = [
                h for h in self._hotspots
                if h["file"] == file_path
                and h["line"] <= line <= h["end_line"]
            ]
            if affected:
                result["line_hotspot"] = True
                result["overlapping_analyzers"] = affected[0]["analyzer_names"]
                result["severity"] = affected[0]["max_severity"]
                result["warnings"].append(
                    f"Line {line} is a compound hotspot "
                    f"({affected[0]['analyzer_count']} analyzers fire here)"
                )

        related = self._find_related_files(file_path)
        if related:
            result["related_files"] = related

        if self._causal_chain is not None:
            impact = self._causal_chain.predict_impact(file_path, line)
            result["impact"] = impact.to_dict()

        return result

    def get_summary(self) -> dict[str, Any]:
        return {
            "project_root": self.project_root,
            "total_files": self._total_files,
            "total_lines": self._total_lines,
            "total_hotspots": len(self._hotspots),
            "critical_hotspots": len(self.get_hotspots(min_analyzers=3)),
            "overall_health": self.get_health_score(),
            "language_distribution": dict(self._language_distribution),
            "warm_time": round(self._warm_duration, 2),
            "warm_timestamp": self._warm_time,
        }

    def get_context_for_file(self, file_path: str) -> dict[str, Any]:
        """One-call complete context for an LLM — no further tool calls needed."""
        knowledge = self.get_file_perception(file_path)
        if knowledge is None:
            return {"error": f"Unknown file: {file_path}"}

        file_hotspots = [
            h for h in self._hotspots if h["file"] == file_path
        ]
        related = self._find_related_files(file_path)

        return {
            "file": file_path,
            "language": knowledge.language,
            "line_count": knowledge.line_count,
            "health": knowledge.health_score,
            "findings": knowledge.total_findings,
            "fired_neurons": f"{knowledge.fired_neurons}/{knowledge.total_neurons}",
            "severity": knowledge.severity_distribution,
            "categories": knowledge.category_coverage,
            "critical_lines": list(knowledge.critical_hotspot_lines),
            "top_issues": list(knowledge.top_issues),
            "hotspots": file_hotspots[:5],
            "related_files": related,
            "project_health": self.get_health_score(),
            "project_files": self._total_files,
        }

    def _collect_files(self) -> list[str]:
        root = Path(self.project_root)
        files: list[str] = []
        skip_dirs = {
            ".git", "__pycache__", "node_modules", ".venv", ".tox",
            ".mypy_cache", ".pytest_cache", ".ruff_cache", "htmlcov",
            ".eggs", "*.egg-info", "dist", "build",
        }
        for p in root.rglob("*"):
            if any(skip in p.parts for skip in skip_dirs):
                continue
            if p.is_file() and p.suffix.lower() in _SUPPORTED_EXTENSIONS:
                files.append(str(p))
        return sorted(files)

    def _build_knowledge(
        self, file_path: str, pmap: PerceptionMap
    ) -> FileKnowledge:
        try:
            line_count = sum(
                1 for _ in open(file_path, errors="replace")
            )
        except OSError:
            line_count = 0
        self._total_lines += line_count

        ext = Path(file_path).suffix.lower()
        lang_map = {
            ".py": "python", ".js": "javascript", ".jsx": "javascript",
            ".ts": "typescript", ".tsx": "tsx", ".java": "java",
            ".go": "go", ".c": "c", ".cpp": "cpp", ".rs": "rust",
            ".rb": "ruby", ".php": "php", ".swift": "swift",
            ".kt": "kotlin", ".cs": "csharp", ".scala": "scala",
        }
        language = lang_map.get(ext, ext.lstrip("."))

        critical_lines = tuple(
            h.line for h in pmap.critical_hotspots
        )
        top_issues = tuple(
            f"[{h.max_severity.value}] L{h.line}: "
            f"{', '.join(h.analyzer_names)}"
            for h in pmap.hotspots[:5]
        )

        self._file_hashes[file_path] = self._file_hash(file_path)

        for cat, count in pmap.category_coverage.items():
            self._category_totals[cat] = self._category_totals.get(cat, 0) + count
        for sev, count in pmap.severity_distribution.items():
            self._severity_totals[sev] = self._severity_totals.get(sev, 0) + count

        return FileKnowledge(
            path=file_path,
            language=language,
            line_count=line_count,
            health_score=pmap.health_score,
            perception_score=pmap.perception_score,
            total_findings=pmap.total_findings,
            fired_neurons=pmap.fired_neurons,
            total_neurons=pmap.total_neurons,
            severity_distribution=pmap.severity_distribution,
            category_coverage=pmap.category_coverage,
            critical_hotspot_lines=critical_lines,
            top_issues=top_issues,
        )

    def _file_hash(self, file_path: str) -> str:
        try:
            content = Path(file_path).read_bytes()
            return hashlib.md5(content).hexdigest()
        except OSError:
            return ""

    def _relative(self, file_path: str) -> str:
        try:
            return str(Path(file_path).relative_to(self.project_root))
        except ValueError:
            return file_path

    def _find_related_files(self, file_path: str) -> list[str]:
        """Graph-aware: files connected via imports, then fallback to same directory."""
        rel = self._relative(file_path)
        related = self._reverse_imports.get(rel, set()) | self._import_graph.get(rel, set())
        if related:
            return sorted(related)[:10]
        # Fallback: same directory
        directory = str(Path(file_path).parent)
        related_list: list[str] = []
        for path, knowledge in self._file_map.items():
            if path == file_path:
                continue
            if str(Path(path).parent) == directory and knowledge.total_findings > 0:
                related_list.append(path)
        return sorted(related_list)[:5]

    # -- Impact Graph ----------------------------------------------------------

    def _build_impact_graph(self) -> None:
        """Build impact graph — incremental if cache exists with file hashes."""
        cache_path = Path(self.project_root) / ".brain_graph.json"

        # Try loading cache
        if cache_path.exists():
            try:
                self._load_graph(cache_path)
            except (json.JSONDecodeError, KeyError, OSError):
                self._import_graph.clear()
                self._reverse_imports.clear()
                self._test_to_source.clear()
                self._source_to_tests.clear()
                self._source_to_real_tests.clear()
                self._source_stems.clear()
                self._tool_refs.clear()
                self._symbol_defs.clear()
                self._file_hashes.clear()

        # Find all current .py files and their hashes
        current_files = self._scan_py_files()
        current_hashes = {}
        for rel in current_files:
            abs_path = Path(self.project_root) / rel
            try:
                current_hashes[rel] = hashlib.md5(abs_path.read_bytes()).hexdigest()
            except OSError:
                current_hashes[rel] = ""

        # Determine what changed
        changed = {rel for rel, h in current_hashes.items() if self._file_hashes.get(rel) != h}
        removed = {rel for rel in self._file_hashes if rel not in current_hashes}

        if not changed and not removed and self._file_hashes:
            # Nothing changed — cache is perfect
            return

        # If cache is empty or too many changes (>50%), full rebuild is faster
        if not self._file_hashes or len(changed) > 50:
            self._import_graph.clear()
            self._reverse_imports.clear()
            self._test_to_source.clear()
            self._source_to_tests.clear()
            self._source_to_real_tests.clear()
            self._source_stems.clear()
            self._tool_refs.clear()
            self._symbol_defs.clear()
            changed = current_files

        # Remove stale data for deleted/changed files
        for rel in removed | changed:
            self._remove_file_edges(rel)
            self._source_stems.pop(Path(rel).stem, None)

        # Re-parse only changed files
        for rel in changed:
            self._source_stems[Path(rel).stem] = rel
            abs_path = str(Path(self.project_root) / rel)
            if "/tests/" in rel or rel.startswith("tests/"):
                self._parse_imports(abs_path, rel)
                self._map_test_file(abs_path, rel)
            else:
                self._parse_imports(abs_path, rel)
                self._extract_symbols(abs_path, rel)

        # Rebuild test mapping and tool refs (cheap — no AST parsing)
        self._rebuild_test_and_tool_maps()

        # Update hashes
        self._file_hashes = current_hashes

        try:
            self._save_graph(cache_path)
        except OSError:
            pass

    def _scan_py_files(self) -> set[str]:
        """Scan for all project .py files, return relative paths."""
        skip_dirs = {"__pycache__", ".venv", "node_modules", ".git", ".tox", ".mypy_cache"}
        result: set[str] = set()
        for pkg in ("tree_sitter_analyzer", "tests"):
            pkg_path = Path(self.project_root) / pkg
            if not pkg_path.exists():
                continue
            for p in pkg_path.rglob("*.py"):
                if any(s in p.parts for s in skip_dirs):
                    continue
                result.add(self._relative(str(p)))
        return result

    def _remove_file_edges(self, rel: str) -> None:
        """Remove all graph edges related to a file."""
        # Remove from import graph
        old_imports = self._import_graph.pop(rel, set())
        for dep in old_imports:
            self._reverse_imports.get(dep, set()).discard(rel)
        # Remove from reverse imports
        old_reverse = self._reverse_imports.pop(rel, set())
        for dep in old_reverse:
            self._import_graph.get(dep, set()).discard(rel)
        # Remove from test mappings
        for src_set in (self._test_to_source, self._source_to_tests,
                        self._source_to_real_tests):
            src_set.pop(rel, None)
        # Remove symbols defined in this file
        self._symbol_defs = {s: f for s, f in self._symbol_defs.items() if f != rel}

    def _rebuild_test_and_tool_maps(self) -> None:
        """Rebuild derived mappings without re-parsing ASTs."""
        # Rebuild source_to_tests from test_to_source
        self._source_to_tests.clear()
        for test_rel, sources in self._test_to_source.items():
            for src in sources:
                self._source_to_tests.setdefault(src, set()).add(test_rel)
        # Rebuild tool refs
        self._tool_refs.clear()
        tools_dir = Path(self.project_root) / "tree_sitter_analyzer" / "mcp" / "tools"
        if tools_dir.exists():
            for tool_file in sorted(tools_dir.glob("*_tool.py")):
                if tool_file.name in ("base_tool.py", "__init__.py"):
                    continue
                tool_name = tool_file.stem.removesuffix("_tool")
                try:
                    source = tool_file.read_text(encoding="utf-8")
                    tree = ast.parse(source)
                except (SyntaxError, UnicodeDecodeError, OSError):
                    continue
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            resolved = self._resolve_import(alias.name)
                            if resolved and resolved not in self._test_to_source:
                                self._tool_refs.setdefault(tool_name, set()).add(resolved)
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        resolved = self._resolve_import(node.module)
                        if resolved and resolved not in self._test_to_source:
                            self._tool_refs.setdefault(tool_name, set()).add(resolved)

    def _save_graph(self, path: Path) -> None:
        """Persist impact graph + file hashes to JSON."""
        data = {
            "import_graph": {k: sorted(v) for k, v in self._import_graph.items()},
            "reverse_imports": {k: sorted(v) for k, v in self._reverse_imports.items()},
            "test_to_source": {k: sorted(v) for k, v in self._test_to_source.items()},
            "source_to_tests": {k: sorted(v) for k, v in self._source_to_tests.items()},
            "source_to_real_tests": {k: sorted(v) for k, v in self._source_to_real_tests.items()},
            "source_stems": dict(self._source_stems),
            "tool_refs": {k: sorted(v) for k, v in self._tool_refs.items()},
            "symbol_defs": dict(self._symbol_defs),
            "file_hashes": dict(self._file_hashes),
        }
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def _load_graph(self, path: Path) -> None:
        """Load impact graph + file hashes from JSON cache."""
        data = json.loads(path.read_text(encoding="utf-8"))
        self._import_graph = {k: set(v) for k, v in data["import_graph"].items()}
        self._reverse_imports = {k: set(v) for k, v in data["reverse_imports"].items()}
        self._test_to_source = {k: set(v) for k, v in data["test_to_source"].items()}
        self._source_to_tests = {k: set(v) for k, v in data["source_to_tests"].items()}
        self._source_to_real_tests = {k: set(v) for k, v in data.get("source_to_real_tests", {}).items()}
        self._source_stems = data["source_stems"]
        self._tool_refs = {k: set(v) for k, v in data["tool_refs"].items()}
        self._symbol_defs = data.get("symbol_defs", {})
        self._file_hashes = data.get("file_hashes", {})
        self._built = True

    def _build_graph_from_ast(self) -> None:
        """Build import graph, test mapping, and tool references from Python AST."""
        root = Path(self.project_root)
        skip_dirs = {
            ".git", "__pycache__", "node_modules", ".venv", ".tox",
            ".mypy_cache", ".pytest_cache", ".ruff_cache", "htmlcov",
            ".eggs", "dist", "build",
        }
        py_files: list[str] = []
        for p in root.rglob("*.py"):
            if any(skip in p.parts for skip in skip_dirs):
                continue
            py_files.append(str(p))

        for abs_path in py_files:
            rel = self._relative(abs_path)
            self._source_stems[Path(rel).stem] = rel
            self._parse_imports(abs_path, rel)
            if "/tests/" not in rel and not rel.startswith("tests/"):
                self._extract_symbols(abs_path, rel)

        for abs_path in py_files:
            rel = self._relative(abs_path)
            if "/tests/" in rel or rel.startswith("tests/"):
                self._map_test_file(abs_path, rel)

        self._map_tool_files(root)

    def _parse_imports(self, abs_path: str, rel: str) -> None:
        """Extract import edges from a Python file."""
        try:
            source = Path(abs_path).read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError, OSError):
            return

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    resolved = self._resolve_import(alias.name)
                    if resolved:
                        self._import_graph.setdefault(rel, set()).add(resolved)
                        self._reverse_imports.setdefault(resolved, set()).add(rel)
            elif isinstance(node, ast.ImportFrom) and node.module:
                resolved = self._resolve_import(node.module)
                if resolved:
                    self._import_graph.setdefault(rel, set()).add(resolved)
                    self._reverse_imports.setdefault(resolved, set()).add(rel)

    def _map_test_file(self, abs_path: str, rel: str) -> None:
        """Map a test file to the source files it tests, with real coverage detection."""
        # Convention: test_health_score.py → health_score
        test_name = Path(rel).name
        if test_name.startswith("test_") and test_name.endswith(".py"):
            source_stem = test_name[5:-3]
            if source_stem in self._source_stems:
                source_rel = self._source_stems[source_stem]
                self._test_to_source.setdefault(rel, set()).add(source_rel)
                self._source_to_tests.setdefault(source_rel, set()).add(rel)

        # Import-based: check what the test imports and actually uses
        try:
            source = Path(abs_path).read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError, OSError):
            return

        imported_symbols: set[str] = set()
        imported_modules: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                resolved = self._resolve_import(node.module)
                if resolved and "/tests/" not in resolved:
                    self._test_to_source.setdefault(rel, set()).add(resolved)
                    self._source_to_tests.setdefault(resolved, set()).add(rel)
                    imported_modules.add(resolved)
                    for alias in node.names:
                        imported_symbols.add(alias.name.split(" as ")[0])

        # Real coverage: does the test actually call/instantiate imported symbols?
        called_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    called_names.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    called_names.add(node.func.attr)

        actually_used = imported_symbols & called_names
        if actually_used:
            for sym in actually_used:
                if sym in self._symbol_defs:
                    src = self._symbol_defs[sym]
                    self._source_to_real_tests.setdefault(src, set()).add(rel)
        # If test calls any function from imported modules, count as real
        for mod in imported_modules:
            if actually_used:
                self._source_to_real_tests.setdefault(mod, set()).add(rel)

    def _map_tool_files(self, root: Path) -> None:
        """Map MCP tool files to the source files they import (not string match)."""
        tools_dir = root / "tree_sitter_analyzer" / "mcp" / "tools"
        if not tools_dir.exists():
            return
        for tool_file in sorted(tools_dir.glob("*_tool.py")):
            if tool_file.name in ("base_tool.py", "__init__.py"):
                continue
            tool_name = tool_file.stem.removesuffix("_tool")
            try:
                source = tool_file.read_text(encoding="utf-8")
                tree = ast.parse(source)
            except (SyntaxError, UnicodeDecodeError, OSError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        resolved = self._resolve_import(alias.name)
                        if resolved and resolved not in self._test_to_source:
                            self._tool_refs.setdefault(tool_name, set()).add(resolved)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    resolved = self._resolve_import(node.module)
                    if resolved and resolved not in self._test_to_source:
                        self._tool_refs.setdefault(tool_name, set()).add(resolved)

    def _extract_symbols(self, abs_path: str, rel: str) -> None:
        """Extract top-level class and function names from a source file."""
        try:
            source = Path(abs_path).read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError, OSError):
            return

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                self._symbol_defs[node.name] = rel
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._symbol_defs[node.name] = rel

    def _resolve_import(self, module_name: str) -> str | None:
        """Resolve a dot-path import to a project-relative path."""
        parts = module_name.split(".")
        candidate = Path(self.project_root)
        for part in parts:
            candidate = candidate / part
        if candidate.is_dir() and (candidate / "__init__.py").exists():
            return self._relative(str(candidate / "__init__.py"))
        py_path = candidate.with_suffix(".py")
        if py_path.exists():
            return self._relative(str(py_path))
        return None

    def blast_radius(self, files: list[str], max_depth: int = 5) -> BlastRadius:
        """BFS from changed files to find all impacted files, tests, tools."""
        if not self._import_graph:
            self._build_impact_graph()

        visited: set[str] = set()
        file_impacts: set[str] = set()
        queue: list[tuple[str, int]] = []

        for f in files:
            rel = self._relative(f)
            visited.add(rel)
            queue.append((rel, 0))

        while queue:
            current, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            for dep in self._reverse_imports.get(current, set()):
                if dep not in visited:
                    visited.add(dep)
                    file_impacts.add(dep)
                    queue.append((dep, depth + 1))

        # Collect tests
        test_impacts: set[str] = set()
        for f in files:
            rel = self._relative(f)
            test_impacts.update(self._source_to_tests.get(rel, set()))
        for fi in file_impacts:
            test_impacts.update(self._source_to_tests.get(fi, set()))

        # Collect tools
        tool_impacts: set[str] = set()
        all_impacted = {self._relative(f) for f in files} | file_impacts
        for tool_name, refs in self._tool_refs.items():
            if refs & all_impacted:
                tool_impacts.add(tool_name)

        return BlastRadius(
            changed=tuple(files),
            files=tuple(sorted(file_impacts)),
            tests=tuple(sorted(test_impacts)),
            tools=tuple(sorted(tool_impacts)),
            max_depth=max_depth,
        )

    def affected_tests(self, files: list[str]) -> list[str]:
        """Return test files that cover the given source files."""
        if not self._source_to_tests:
            self._build_impact_graph()
        tests: set[str] = set()
        for f in files:
            rel = self._relative(f)
            tests.update(self._source_to_tests.get(rel, set()))
        return sorted(tests)

    def affected_real_tests(self, files: list[str]) -> list[str]:
        """Return test files that actually call/instantiate code from the given source files."""
        if not self._source_to_real_tests:
            self._build_impact_graph()
        tests: set[str] = set()
        for f in files:
            rel = self._relative(f)
            tests.update(self._source_to_real_tests.get(rel, set()))
        return sorted(tests)

    def dependents(self, file_path: str) -> list[str]:
        """Files that import this file (reverse dependencies)."""
        rel = self._relative(file_path)
        return sorted(self._reverse_imports.get(rel, set()))

    def dependencies(self, file_path: str) -> list[str]:
        """Files that this file imports (forward dependencies)."""
        rel = self._relative(file_path)
        return sorted(self._import_graph.get(rel, set()))
