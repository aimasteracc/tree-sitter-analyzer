"""CodeGraph map / visualize / UML / symbol / class-hierarchy argument group.

Extracted from ``_add_mcp_analysis_options`` to keep every file under 500 lines.
Called at the end of that function via ``_add_mcp_codegraph_map_options``.
"""

from __future__ import annotations

import argparse

# Keep the CLI default in lock-step with the tool's runtime default (MCP/CLI
# parity — Codex P2 on #297).
from ...mcp.tools.symbol_search_tool import (
    DEFAULT_SYMBOL_SEARCH_LIMIT as _DEFAULT_SYMBOL_SEARCH_LIMIT,
)


def _add_mcp_codegraph_map_options(parser: argparse.ArgumentParser) -> None:
    """Add sitemap, xref, complexity, symbol-search, class-hierarchy, visualize, and UML flags."""
    parser.add_argument(
        "--codegraph-sitemap",
        action="store_true",
        help="Generate hierarchical project code map: directory→file→class→function (CodeGraph parity)",
    )
    parser.add_argument(
        "--codegraph-sitemap-mode",
        choices=["full", "api", "module", "flat"],
        default="full",
        help="Mode for --codegraph-sitemap (default: full)",
    )
    parser.add_argument(
        "--codegraph-sitemap-language",
        help="Language filter for --codegraph-sitemap",
    )
    parser.add_argument(
        "--codegraph-sitemap-directory",
        help="Directory filter for --codegraph-sitemap (relative path)",
    )
    parser.add_argument(
        "--codegraph-sitemap-max-files",
        type=int,
        default=200,
        help="Max files for --codegraph-sitemap (default: 200)",
    )
    parser.add_argument(
        "--codegraph-xref",
        metavar="SYMBOL",
        help="Instant cross-reference: definition + callers + callees + import deps "
        "(CodeGraph parity). Requires ast_cache index.",
    )
    parser.add_argument(
        "--codegraph-xref-mode",
        choices=["symbol", "file"],
        default="symbol",
        help="Mode for --codegraph-xref: symbol or file (default: symbol)",
    )
    parser.add_argument(
        "--codegraph-xref-file",
        help="File path to disambiguate (symbol mode) or target (file mode)",
    )
    parser.add_argument(
        "--codegraph-complexity-heatmap",
        nargs="?",
        const="project",
        choices=["project", "file", "function"],
        help="Cyclomatic complexity heatmap (CodeGraph parity). "
        "project=full heatmap, file=per-file, function=specific function",
    )
    parser.add_argument(
        "--codegraph-complexity-file",
        help="File path for file/function mode (relative to project root)",
    )
    parser.add_argument(
        "--codegraph-complexity-function",
        help="Function name for function mode",
    )
    parser.add_argument(
        "--codegraph-complexity-language",
        help="Language filter for complexity heatmap",
    )
    parser.add_argument(
        "--codegraph-complexity-directory",
        help="Directory filter for complexity heatmap (relative path)",
    )
    parser.add_argument(
        "--codegraph-complexity-max-files",
        type=int,
        default=200,
        help="Max files to scan in project mode (default: 200)",
    )
    parser.add_argument(
        "--symbol-search-language",
        help="Language filter for --symbol-search",
    )
    parser.add_argument(
        "--symbol-search-kind",
        choices=["function", "class", "variable", "import", "any"],
        default="any",
        help="Symbol kind filter for --symbol-search (default: any)",
    )
    parser.add_argument(
        "--symbol-search-limit",
        type=int,
        default=_DEFAULT_SYMBOL_SEARCH_LIMIT,
        help=(
            "Max results for --symbol-search "
            f"(default: {_DEFAULT_SYMBOL_SEARCH_LIMIT})"
        ),
    )
    parser.add_argument(
        "--symbol-resolve",
        metavar="SYMBOL",
        help="Go-to-definition: find where a symbol is defined (CodeGraph parity). "
        "Supports dotted names like module.Class.method",
    )
    parser.add_argument(
        "--symbol-resolve-mode",
        choices=["resolve", "references"],
        default="resolve",
        help="Mode for --symbol-resolve: resolve=go-to-def, references=find-all-refs (default: resolve)",
    )
    parser.add_argument(
        "--class-hierarchy",
        action="store_true",
        help="Class inheritance hierarchy analysis: subclasses, superclasses, impact (CodeGraph parity)",
    )
    parser.add_argument(
        "--class-hierarchy-mode",
        choices=["subclasses", "superclasses", "tree", "impact", "all", "summary"],
        default="summary",
        help="Mode for --class-hierarchy (default: summary)",
    )
    parser.add_argument(
        "--class-hierarchy-class",
        help="Target class name for --class-hierarchy subclasses/superclasses/tree/impact modes",
    )
    parser.add_argument(
        "--class-hierarchy-depth",
        type=int,
        default=10,
        help="Max traversal depth for --class-hierarchy subclasses mode (default: 10)",
    )
    parser.add_argument(
        "--class-inspect",
        metavar="CLASS_NAME",
        help="Inspect a class: list its defined methods with override detection",
    )
    parser.add_argument(
        "--dependency-matrix",
        action="store_true",
        help="Module coupling analysis: pairwise dependency scores, hotspots, unstable modules (CodeGraph parity)",
    )
    parser.add_argument(
        "--dependency-matrix-mode",
        choices=["summary", "matrix", "hotspots", "file", "unstable"],
        default="summary",
        help="Mode for --dependency-matrix (default: summary)",
    )
    parser.add_argument(
        "--dependency-matrix-file",
        help="File path for --dependency-matrix file mode",
    )
    parser.add_argument(
        "--dependency-matrix-top-k",
        type=int,
        default=10,
        help="Top-K coupled pairs for --dependency-matrix hotspots mode (default: 10)",
    )
    parser.add_argument(
        "--codegraph-visualize",
        action="store_true",
        help="Export call graph as Mermaid flowchart diagram (CodeGraph parity)",
    )
    parser.add_argument(
        "--codegraph-visualize-mode",
        choices=["full", "file", "function"],
        default="full",
        help="Mode for --codegraph-visualize (default: full)",
    )
    parser.add_argument(
        "--codegraph-visualize-file",
        help="File path for --codegraph-visualize mode=file",
    )
    parser.add_argument(
        "--codegraph-visualize-function",
        help="Seed function name for --codegraph-visualize mode=function",
    )
    parser.add_argument(
        "--codegraph-visualize-depth",
        type=int,
        default=3,
        help="Max transitive depth for --codegraph-visualize mode=function (default: 3)",
    )
    parser.add_argument(
        "--codegraph-visualize-max-edges",
        type=int,
        default=150,
        help="Max edges to render for --codegraph-visualize (default: 150)",
    )
    parser.add_argument(
        "--codegraph-visualize-direction",
        choices=["TD", "LR", "BT", "RL"],
        default="TD",
        help="Mermaid flowchart direction for --codegraph-visualize (default: TD)",
    )
    parser.add_argument(
        "--uml",
        choices=["class", "package", "component", "sequence"],
        help="Export a UML-style Mermaid diagram from indexed project intelligence",
    )
    parser.add_argument(
        "--uml-source",
        help="Source function for --uml sequence",
    )
    parser.add_argument(
        "--uml-target",
        help="Target function for --uml sequence",
    )
    parser.add_argument(
        "--uml-max-edges",
        type=int,
        default=200,
        help="Max relationships to render for --uml (default: 200)",
    )
    parser.add_argument(
        "--uml-max-depth",
        type=int,
        default=8,
        help="Max call-path depth for --uml sequence (default: 8)",
    )
    parser.add_argument(
        "--uml-max-paths",
        type=int,
        default=3,
        help="Max call paths to inspect for --uml sequence (default: 3)",
    )
    parser.add_argument(
        "--uml-package-depth",
        type=int,
        default=2,
        help="Directory depth used to group packages for --uml package (default: 2)",
    )
    parser.add_argument(
        "--uml-no-external-bases",
        action="store_true",
        help="Omit common external bases such as ABC/Enum from --uml class",
    )
    parser.add_argument(
        "--dependency-matrix-threshold",
        type=float,
        default=0.7,
        help="Instability threshold for --dependency-matrix unstable mode (default: 0.7)",
    )
