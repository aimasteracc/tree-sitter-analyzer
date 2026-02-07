#!/usr/bin/env python3
"""
Cross-Analysis Script - v1 analyzes v2 and v2 analyzes v1.

Uses subprocess to invoke each project's tools, then compares results.
Generates ISSUES.json with actionable improvements.

Usage:
    python scripts/cross_analyze.py                # Full analysis
    python scripts/cross_analyze.py --compare-tools # Compare tool inventories only
    python scripts/cross_analyze.py --json          # JSON output
"""
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

WORKSPACE = Path(__file__).resolve().parent.parent.parent
V1_ROOT = WORKSPACE / "tree-sitter-analyzer-v1"
V2_ROOT = WORKSPACE / "tree-sitter-analyzer-v2"
V1_SRC = V1_ROOT / "tree_sitter_analyzer"
V2_SRC = V2_ROOT / "tree_sitter_analyzer_v2"


@dataclass
class ProjectStats:
    name: str
    total_files: int = 0
    total_lines: int = 0
    total_classes: int = 0
    total_functions: int = 0
    avg_file_size: float = 0.0
    max_file_size: int = 0
    max_file_name: str = ""
    files_over_300: int = 0
    files_over_500: int = 0
    test_files: int = 0
    src_files: int = 0
    mcp_tools: list[str] = field(default_factory=list)


@dataclass
class ComparisonResult:
    v1: ProjectStats = field(default_factory=lambda: ProjectStats("v1"))
    v2: ProjectStats = field(default_factory=lambda: ProjectStats("v2"))
    v1_only_tools: list[str] = field(default_factory=list)
    v2_only_tools: list[str] = field(default_factory=list)
    shared_tools: list[str] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def analyze_project(src_dir: Path, project_root: Path, name: str) -> ProjectStats:
    """Analyze a project's source code."""
    stats = ProjectStats(name=name)

    if not src_dir.exists():
        return stats

    py_files = [f for f in src_dir.rglob("*.py") if "__pycache__" not in str(f)]

    for f in py_files:
        try:
            content = f.read_text(encoding="utf-8")
            lines = len(content.splitlines())
            stats.total_files += 1
            stats.total_lines += lines

            if lines > stats.max_file_size:
                stats.max_file_size = lines
                try:
                    stats.max_file_name = str(f.relative_to(project_root))
                except ValueError:
                    stats.max_file_name = str(f)

            if lines > 300:
                stats.files_over_300 += 1
            if lines > 500:
                stats.files_over_500 += 1

            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    stats.total_classes += 1
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    stats.total_functions += 1
        except Exception:
            continue

    if stats.total_files > 0:
        stats.avg_file_size = round(stats.total_lines / stats.total_files, 1)

    # Count test files
    test_dir = project_root / "tests"
    if test_dir.exists():
        stats.test_files = len([
            f for f in test_dir.rglob("test_*.py")
            if "__pycache__" not in str(f)
        ])

    stats.src_files = stats.total_files

    return stats


def extract_mcp_tools_v1(src_dir: Path) -> list[str]:
    """Extract MCP tool names from v1's server registration."""
    tools = []
    # v1 registers tools in mcp/server.py
    server_file = src_dir / "mcp" / "server.py"
    if not server_file.exists():
        return tools

    try:
        content = server_file.read_text(encoding="utf-8")
        # Look for @mcp.tool() decorated functions or tool registration patterns
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for d in node.decorator_list:
                    # Match @mcp.tool() or @server.tool() patterns
                    if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute):
                        if d.func.attr == "tool":
                            tools.append(node.name)
                    elif isinstance(d, ast.Attribute) and d.attr == "tool":
                        tools.append(node.name)
    except Exception:
        pass

    # Fallback: search for def handle_ or known tool names
    if not tools:
        try:
            import re
            content = server_file.read_text(encoding="utf-8")
            # Pattern: function names that look like tool handlers
            matches = re.findall(r'name\s*=\s*"([^"]+)"', content)
            tools.extend(matches)
        except Exception:
            pass

    return sorted(set(tools))


def extract_mcp_tools_v2(src_dir: Path) -> list[str]:
    """Extract MCP tool names from v2's tool classes."""
    tools = []
    tools_dir = src_dir / "mcp" / "tools"
    if not tools_dir.exists():
        return tools

    for py_file in tools_dir.glob("*.py"):
        if py_file.name in ("__init__.py", "base.py", "registry.py"):
            continue
        try:
            content = py_file.read_text(encoding="utf-8")
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == "get_name":
                    # Extract the return value
                    for stmt in node.body:
                        if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Constant):
                            tools.append(stmt.value.value)
        except Exception:
            continue

    return sorted(set(tools))


def compare_tools(v1_tools: list[str], v2_tools: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Compare tool sets."""
    v1_set = set(v1_tools)
    v2_set = set(v2_tools)
    return (
        sorted(v1_set - v2_set),
        sorted(v2_set - v1_set),
        sorted(v1_set & v2_set),
    )


def run_quality_gate() -> dict | None:
    """Run quality_gate.py and parse JSON output."""
    try:
        result = subprocess.run(
            [sys.executable, "scripts/quality_gate.py", "--json"],
            cwd=str(V2_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except Exception:
        pass
    return None


def generate_issues(comparison: ComparisonResult, quality: dict | None) -> list[dict]:
    """Generate actionable issues from analysis."""
    issues = []

    # Issues from quality gate
    if quality and quality.get("issues"):
        for qi in quality["issues"]:
            if qi["severity"] == "CRITICAL":
                issues.append({
                    "source": "quality_gate",
                    "severity": "CRITICAL",
                    "file": qi["file"],
                    "line": qi["line"],
                    "category": qi["category"],
                    "message": qi["message"],
                    "action": qi.get("suggestion", "Fix the issue"),
                })

    # Issues from comparison
    v2 = comparison.v2
    if v2.files_over_500 > 0:
        issues.append({
            "source": "cross_analysis",
            "severity": "WARNING",
            "file": "",
            "line": 0,
            "category": "architecture",
            "message": f"v2 has {v2.files_over_500} files over 500 lines",
            "action": "Split large files into focused modules",
        })

    if v2.test_files < v2.src_files * 0.5:
        issues.append({
            "source": "cross_analysis",
            "severity": "WARNING",
            "file": "",
            "line": 0,
            "category": "test_coverage",
            "message": f"v2 test ratio is low: {v2.test_files} tests for {v2.src_files} source files",
            "action": "Add more tests, especially for PARTIAL tools",
        })

    # v1 tools not in v2 (capability gap)
    for tool in comparison.v1_only_tools:
        issues.append({
            "source": "cross_analysis",
            "severity": "INFO",
            "file": "",
            "line": 0,
            "category": "capability_gap",
            "message": f"v1 tool '{tool}' has no equivalent in v2",
            "action": f"Evaluate if '{tool}' should be added to v2",
        })

    return issues


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_analysis() -> ComparisonResult:
    """Run full cross-analysis."""
    result = ComparisonResult()

    # Analyze both projects
    result.v1 = analyze_project(V1_SRC, V1_ROOT, "v1")
    result.v2 = analyze_project(V2_SRC, V2_ROOT, "v2")

    # Extract and compare tools
    v1_tools = extract_mcp_tools_v1(V1_SRC)
    v2_tools = extract_mcp_tools_v2(V2_SRC)
    result.v1.mcp_tools = v1_tools
    result.v2.mcp_tools = v2_tools

    result.v1_only_tools, result.v2_only_tools, result.shared_tools = compare_tools(
        v1_tools, v2_tools
    )

    # Run quality gate on v2
    quality = run_quality_gate()

    # Generate issues
    result.issues = generate_issues(result, quality)

    return result


def print_report(result: ComparisonResult) -> None:
    """Print human-readable report."""
    print("=" * 60)
    print("  CROSS-ANALYSIS REPORT: v1 vs v2")
    print("=" * 60)

    print("\n  PROJECT STATISTICS")
    print("-" * 60)
    fmt = "  {:<25} {:>10} {:>10}"
    print(fmt.format("Metric", "v1", "v2"))
    print(fmt.format("-" * 25, "-" * 10, "-" * 10))
    print(fmt.format("Source files", str(result.v1.total_files), str(result.v2.total_files)))
    print(fmt.format("Total lines", str(result.v1.total_lines), str(result.v2.total_lines)))
    print(fmt.format("Classes", str(result.v1.total_classes), str(result.v2.total_classes)))
    print(fmt.format("Functions", str(result.v1.total_functions), str(result.v2.total_functions)))
    print(fmt.format("Avg file size", str(result.v1.avg_file_size), str(result.v2.avg_file_size)))
    print(fmt.format("Max file size", str(result.v1.max_file_size), str(result.v2.max_file_size)))
    print(fmt.format("Files > 300 lines", str(result.v1.files_over_300), str(result.v2.files_over_300)))
    print(fmt.format("Files > 500 lines", str(result.v1.files_over_500), str(result.v2.files_over_500)))
    print(fmt.format("Test files", str(result.v1.test_files), str(result.v2.test_files)))
    print(fmt.format("MCP tools", str(len(result.v1.mcp_tools)), str(len(result.v2.mcp_tools))))

    print(f"\n  Max file (v1): {result.v1.max_file_name}")
    print(f"  Max file (v2): {result.v2.max_file_name}")

    print("\n  TOOL COMPARISON")
    print("-" * 60)
    print(f"  v1-only tools ({len(result.v1_only_tools)}):")
    for t in result.v1_only_tools:
        print(f"    - {t}")
    print(f"  v2-only tools ({len(result.v2_only_tools)}):")
    for t in result.v2_only_tools[:20]:
        print(f"    - {t}")
    if len(result.v2_only_tools) > 20:
        print(f"    ... and {len(result.v2_only_tools) - 20} more")
    print(f"  Shared tools ({len(result.shared_tools)}):")
    for t in result.shared_tools:
        print(f"    - {t}")

    if result.issues:
        print(f"\n  ISSUES ({len(result.issues)})")
        print("-" * 60)
        critical = [i for i in result.issues if i["severity"] == "CRITICAL"]
        warning = [i for i in result.issues if i["severity"] == "WARNING"]
        info = [i for i in result.issues if i["severity"] == "INFO"]

        if critical:
            print(f"\n  CRITICAL ({len(critical)}):")
            for i in critical:
                print(f"    [{i['category']}] {i['message']}")
                print(f"      -> {i['action']}")
        if warning:
            print(f"\n  WARNING ({len(warning)}):")
            for i in warning:
                print(f"    [{i['category']}] {i['message']}")
                print(f"      -> {i['action']}")
        if info:
            print(f"\n  INFO ({len(info)}):")
            for i in info:
                print(f"    [{i['category']}] {i['message']}")


def to_json(result: ComparisonResult) -> dict:
    """Convert to JSON-serializable dict."""
    def stats_to_dict(s: ProjectStats) -> dict:
        return {
            "total_files": s.total_files,
            "total_lines": s.total_lines,
            "total_classes": s.total_classes,
            "total_functions": s.total_functions,
            "avg_file_size": s.avg_file_size,
            "max_file_size": s.max_file_size,
            "max_file_name": s.max_file_name,
            "files_over_300": s.files_over_300,
            "files_over_500": s.files_over_500,
            "test_files": s.test_files,
            "mcp_tools_count": len(s.mcp_tools),
            "mcp_tools": s.mcp_tools,
        }

    return {
        "v1": stats_to_dict(result.v1),
        "v2": stats_to_dict(result.v2),
        "tool_comparison": {
            "v1_only": result.v1_only_tools,
            "v2_only": result.v2_only_tools,
            "shared": result.shared_tools,
        },
        "issues": result.issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Cross-analysis: v1 vs v2")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--compare-tools", action="store_true", help="Compare tool inventories only")
    parser.add_argument("--save-issues", type=str, default=None, help="Save issues to ISSUES.json")
    args = parser.parse_args()

    if not V1_ROOT.exists():
        print(f"WARNING: v1 project not found at {V1_ROOT}", file=sys.stderr)
    if not V2_ROOT.exists():
        print(f"ERROR: v2 project not found at {V2_ROOT}", file=sys.stderr)
        return 1

    result = run_analysis()

    if args.json:
        print(json.dumps(to_json(result), indent=2, ensure_ascii=False))
    else:
        print_report(result)

    # Save issues
    save_path = args.save_issues or str(V2_ROOT / "ISSUES.json")
    if result.issues:
        Path(save_path).write_text(
            json.dumps(result.issues, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        if not args.json:
            print(f"\n  Issues saved to: {save_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
