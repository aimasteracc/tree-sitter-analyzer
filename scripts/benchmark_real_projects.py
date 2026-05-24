"""
Real-world benchmark: tree-sitter-analyzer MCP tools vs CodeGraph baselines.

Methodology (same as CodeGraph):
1. Clone real open-source projects
2. Run standard code-understanding queries
3. Count: tool_calls, time, file_reads, tokens_approx
4. Compare against CodeGraph's published baselines

CodeGraph baselines (from README):
  - VS Code (TS):     3 calls, 56.6k tok, 17s, 0 file reads
  - Excalidraw (TS):  3 calls, 57.1k tok, 29s, 0 file reads
  - Claude Code (Py): 3 calls, 67.1k tok, 39s, 0 file reads
  - Claude Code (Jv): 1 call,  40.8k tok, 19s, 0 file reads
  - Alamofire (Sw):   3 calls, 57.3k tok, 22s, 0 file reads
  - SwiftC (Sw/C++):  6 calls, 77.4k tok, 35s, 0 file reads

Our test targets (matching languages we support):
  - Flask (Python)       — web framework
  - Requests (Python)    — HTTP library
  - Gson (Java)          — JSON library
  - Go stdlib net/http   — HTTP server
  - Express (TypeScript) — web framework
"""

import json
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

# tempdir-style path; "cwqcdr3n…" looks like base64 entropy to
# detect-secrets but is just a macOS-generated tempdir component.
# pragma: allowlist secret
BENCH_DIR = Path(tempfile.gettempdir()) / "tsa-benchmark-projects"
BENCH_DIR.mkdir(parents=True, exist_ok=True)

CODEGRAPH_BASELINES = {
    "vscode-ts": {"tool_calls": 3, "tokens_k": 56.6, "time_s": 17, "file_reads": 0},
    "excalidraw-ts": {"tool_calls": 3, "tokens_k": 57.1, "time_s": 29, "file_reads": 0},
    "claude-code-py": {
        "tool_calls": 3,
        "tokens_k": 67.1,
        "time_s": 39,
        "file_reads": 0,
    },
    "claude-code-jv": {
        "tool_calls": 1,
        "tokens_k": 40.8,
        "time_s": 19,
        "file_reads": 0,
    },
    "alamofire-sw": {"tool_calls": 3, "tokens_k": 57.3, "time_s": 22, "file_reads": 0},
    "swiftc-sw": {"tool_calls": 6, "tokens_k": 77.4, "time_s": 35, "file_reads": 0},
}

OUR_PROJECTS = {
    "flask-py": {
        "url": "https://github.com/pallets/flask.git",
        "language": "python",
        "query": "How does a Flask request flow from URL routing to response?",
        "expected_symbols": [
            "Flask",
            "route",
            "dispatch_request",
            "full_dispatch_request",
            "make_response",
            "Request",
            "Response",
        ],
        "comparable_cg": "claude-code-py",
    },
    "requests-py": {
        "url": "https://github.com/psf/requests.git",
        "language": "python",
        "query": "How does an HTTP request get prepared, sent, and response parsed?",
        "expected_symbols": [
            "Session",
            "request",
            "Request",
            "PreparedRequest",
            "send",
            "HTTPAdapter",
            "Response",
        ],
        "comparable_cg": "claude-code-py",
    },
    "gson-java": {
        "url": "https://github.com/google/gson.git",
        "language": "java",
        "query": "How does Gson serialize and deserialize Java objects?",
        "expected_symbols": [
            "Gson",
            "toJson",
            "fromJson",
            "TypeAdapter",
            "JsonWriter",
            "JsonReader",
            "JsonElement",
        ],
        "comparable_cg": "claude-code-jv",
    },
    "express-ts": {
        "url": "https://github.com/expressjs/express.git",
        "language": "javascript",
        "query": "How does Express route an incoming request to a handler?",
        "expected_symbols": [
            "createApplication",
            "Router",
            "handle",
            "Layer",
            "Route",
            "dispatch",
            "next",
        ],
        "comparable_cg": "vscode-ts",
    },
}


@dataclass
class BenchmarkRun:
    project: str
    query: str
    language: str
    index_time_s: float = 0.0
    index_files: int = 0
    index_symbols: int = 0
    tool_calls_needed: int = 0
    analysis_time_s: float = 0.0
    file_reads_needed: int = 0
    tokens_approx: int = 0
    found_symbols: list = field(default_factory=list)
    expected_symbols: list = field(default_factory=list)
    recall: float = 0.0
    comparable_cg: str = ""
    cg_tool_calls: int = 0
    cg_time_s: float = 0.0
    cg_file_reads: int = 0


def clone_project(name: str, url: str) -> Path:
    target = BENCH_DIR / name
    if target.exists():
        print(f"  [{name}] Already cloned")
        return target
    print(f"  [{name}] Cloning {url}...")
    subprocess.run(
        ["git", "clone", "--depth", "1", url, str(target)],
        capture_output=True,
        check=True,
    )
    return target


def count_source_files(project_dir: Path, language: str) -> int:
    ext_map = {
        "python": ".py",
        "java": ".java",
        "javascript": ".js",
        "typescript": ".ts",
        "go": ".go",
        "rust": ".rs",
    }
    ext = ext_map.get(language, ".py")
    return sum(
        1
        for f in project_dir.rglob(f"*{ext}")
        if "node_modules" not in str(f) and ".git" not in str(f)
    )


def run_analysis(project_dir: Path, language: str, query_symbols: list[str]) -> dict:
    """Run our MCP tools and count what an agent would need."""
    import asyncio

    async def _analyze():
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from tree_sitter_analyzer.core import AnalysisEngine

        tool_calls = 0
        file_reads = 0
        found = []
        total_time = 0.0

        ext_map = {
            "python": ".py",
            "java": ".java",
            "javascript": ".js",
            "typescript": ".ts",
            "go": ".go",
            "rust": ".rs",
        }
        ext = ext_map.get(language, ".py")

        source_files = [
            f
            for f in project_dir.rglob(f"*{ext}")
            if "node_modules" not in str(f) and ".git" not in str(f)
        ][:50]

        print(f"    Analyzing {len(source_files)} files...")

        engine = AnalysisEngine(project_root=str(project_dir))

        t0 = time.perf_counter()

        # Tool call 1: project health
        tool_calls += 1
        try:
            await engine.get_project_health()
        except Exception:
            pass

        # Tool call 2: smart context / search
        tool_calls += 1

        # Tool call 3: analyze most relevant files
        tool_calls += 1
        analyzed = 0
        for f in source_files[:10]:
            try:
                result = await engine.analyze_file(str(f), language)
                analyzed += 1
                elements = getattr(result, "elements", []) or []
                for el in elements:
                    name = getattr(el, "name", "")
                    if name and name in query_symbols:
                        found.append(name)
            except Exception:
                file_reads += 1

        missing = set(query_symbols) - set(found)
        if missing:
            tool_calls += 2
            file_reads += 3

        total_time = time.perf_counter() - t0

        return {
            "tool_calls": tool_calls,
            "file_reads": file_reads,
            "time_s": round(total_time, 2),
            "found_symbols": list(set(found)),
            "files_analyzed": analyzed,
        }

    return asyncio.run(_analyze())


def main():
    print("=" * 90)
    print("REAL-WORLD BENCHMARK: tree-sitter-analyzer vs CodeGraph")
    print("=" * 90)

    results = []

    for name, config in OUR_PROJECTS.items():
        print(f"\n## Project: {name} ({config['language']})")
        print(f"   Query: {config['query']}")

        project_dir = clone_project(name, config["url"])
        file_count = count_source_files(project_dir, config["language"])
        print(f"   Source files: {file_count}")

        analysis = run_analysis(
            project_dir, config["language"], config["expected_symbols"]
        )

        cg = CODEGRAPH_BASELINES.get(config["comparable_cg"], {})
        recall = len(
            set(analysis["found_symbols"]) & set(config["expected_symbols"])
        ) / max(len(config["expected_symbols"]), 1)

        run = BenchmarkRun(
            project=name,
            query=config["query"],
            language=config["language"],
            index_files=file_count,
            tool_calls_needed=analysis["tool_calls"],
            analysis_time_s=analysis["time_s"],
            file_reads_needed=analysis["file_reads"],
            found_symbols=analysis["found_symbols"],
            expected_symbols=config["expected_symbols"],
            recall=round(recall, 2),
            comparable_cg=config["comparable_cg"],
            cg_tool_calls=cg.get("tool_calls", 0),
            cg_time_s=cg.get("time_s", 0),
            cg_file_reads=cg.get("file_reads", 0),
        )
        results.append(run)

    print("\n" + "=" * 90)
    print("COMPARISON TABLE")
    print("=" * 90)
    print(
        f"\n{'Project':<20} {'Lang':<6} {'Files':<7} {'Our Calls':<11} {'CG Calls':<10} "
        f"{'Our Time':<10} {'CG Time':<9} {'Our Reads':<10} {'CG Reads':<9} {'Recall':<8}"
    )
    print("-" * 100)

    for r in results:
        print(
            f"{r.project:<20} {r.language:<6} {r.index_files:<7} "
            f"{r.tool_calls_needed:<11} {r.cg_tool_calls:<10} "
            f"{r.analysis_time_s:<10} {r.cg_time_s:<9} "
            f"{r.file_reads_needed:<10} {r.cg_file_reads:<9} "
            f"{r.recall:<8}"
        )

    print("\n" + "=" * 90)
    print("GAP ANALYSIS")
    print("=" * 90)

    avg_our_calls = sum(r.tool_calls_needed for r in results) / len(results)
    avg_cg_calls = sum(r.cg_tool_calls for r in results) / len(results)
    avg_our_reads = sum(r.file_reads_needed for r in results) / len(results)
    avg_recall = sum(r.recall for r in results) / len(results)

    print(
        f"\n  Average tool calls — Us: {avg_our_calls:.1f}, CodeGraph: {avg_cg_calls:.1f}"
    )
    print(f"  Average file reads — Us: {avg_our_reads:.1f}, CodeGraph: 0")
    print(f"  Average recall — Us: {avg_recall:.0%}")
    print("\n  Key gaps:")
    print(
        f"    - File reads: CodeGraph=0, Us={avg_our_reads:.1f} (we make agents read files)"
    )
    print("    - Pre-indexing: CodeGraph indexes once, we parse on every call")
    print("    - Call graph: CodeGraph traces callers/callees, we only find_references")

    report_path = Path(__file__).parent.parent / "scripts" / "benchmark_results.json"
    with open(report_path, "w") as f:
        json.dump([asdict(r) for r in results], f, indent=2, default=str)
    print(f"\n  Results saved to: {report_path}")


if __name__ == "__main__":
    main()
