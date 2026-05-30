"""
TOON rendering helpers for project_index.

Renders a ProjectIndex snapshot as TOON-format text for token-efficient
LLM consumption.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._models import ProjectIndex

_NON_CODE_LANGUAGES: frozenset[str] = frozenset(
    {"other", "markdown", "json", "yaml", "toml", "xml", "rst", "latex"}
)

_TOON_DIR_COL: int = 26


def render_toon(index: ProjectIndex, classify_dir_fn: Any) -> str:
    """Render the project index as TOON-format text.

    Format:
        project:  <name>
        what:     <readme excerpt>

        critical: (call graph PageRank top 7)
          <Name>   <module>   <score>   (<N> refs)

        scale:    <N> files — <lang1> <pct>%  <lang2> <pct>%
        entry:    <entry_point>

        core:
          <dir>/   <description>
        context:
          <dir>/   (<N> files)
        tooling:
          <dir>/   <description>

        notes:    <custom_notes>

    Args:
        index: the ProjectIndex to render.
        classify_dir_fn: callable(Path) -> Literal["core","context","tooling"]
    """
    root_path = Path(index.project_root)
    lines: list[str] = []
    _render_header(lines, root_path, index)
    _render_critical(lines, index)
    _render_scale(lines, index)
    _render_entry(lines, index)
    core_dirs, context_dirs, tooling_dirs = _classify_top_level_dirs(
        root_path, index.top_level_structure, classify_dir_fn
    )
    _render_core(lines, core_dirs, index)
    _render_context(lines, context_dirs)
    _render_tooling(lines, tooling_dirs, index)
    if index.custom_notes:
        lines.append(f"\nnotes:    {index.custom_notes}")
    return "\n".join(lines)


def _render_header(lines: list[str], root_path: Path, index: ProjectIndex) -> None:
    """Emit ``project:`` / ``what:`` lines."""
    project_name = root_path.resolve().name or root_path.name
    lines.append(f"project:  {project_name}")
    if index.readme_excerpt:
        lines.append(f"what:     {index.readme_excerpt}")


def _render_critical(lines: list[str], index: ProjectIndex) -> None:
    """Emit the ``critical:`` section (top-7 PageRank nodes)."""
    if not index.critical_nodes:
        return
    lines.append("")
    lines.append("critical:")
    for node in index.critical_nodes[:7]:
        name = node.get("name", "")
        pr = float(node.get("pagerank", 0))
        refs = int(node.get("inbound_refs", 0))
        lines.append(f"  {name:<28}  {pr:.2f}  ({refs} refs)")


def _render_scale(lines: list[str], index: ProjectIndex) -> None:
    """Emit the ``scale:`` line — total files + top-2 language shares."""
    total = max(index.file_count, 1)
    code_langs = [
        (k, v)
        for k, v in index.language_distribution.items()
        if k not in _NON_CODE_LANGUAGES and v >= 1
    ]
    code_langs.sort(key=lambda kv: -kv[1])
    if not code_langs:
        return
    lang_str = "  ".join(f"{k} {round(v * 100 / total)}%" for k, v in code_langs[:2])
    lines.append(f"\nscale:    {index.file_count:,} files — {lang_str}")


def _render_entry(lines: list[str], index: ProjectIndex) -> None:
    """Emit the ``entry:`` line from the first entry point."""
    if not index.entry_points:
        return
    ep = Path(index.entry_points[0]).name
    lines.append(f"entry:    {ep}")


def _classify_top_level_dirs(
    root_path: Path,
    structure: list[dict[str, Any]],
    classify_dir_fn: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Partition top-level dirs into (core, context, tooling) buckets."""
    core_dirs: list[dict[str, Any]] = []
    context_dirs: list[dict[str, Any]] = []
    tooling_dirs: list[dict[str, Any]] = []
    for item in structure:
        name = item["name"]
        dir_path = root_path / name
        if dir_path.is_dir():
            cls_ = classify_dir_fn(dir_path)
        else:
            cls_ = "core"
        if cls_ == "context":
            context_dirs.append(item)
        elif cls_ == "tooling":
            tooling_dirs.append(item)
        else:
            core_dirs.append(item)
    return core_dirs, context_dirs, tooling_dirs


def _render_core(
    lines: list[str],
    core_dirs: list[dict[str, Any]],
    index: ProjectIndex,
) -> None:
    """Emit ``core:`` section with first-7 dirs + first-4 subdirs each."""
    if not core_dirs:
        return
    lines.append("")
    lines.append("core:")
    for item in core_dirs[:7]:
        name = item["name"]
        _append_dir_line(lines, name, index.module_descriptions.get(name, ""))
        for sub in item.get("subdirectories", [])[:4]:
            sname = sub["name"]
            rel = f"{name}/{sname}"
            sdesc = index.module_descriptions.get(rel, "")
            if not sdesc:
                continue
            sub_label = sname + "/"
            pad2 = max(1, _TOON_DIR_COL - 2 - len(sub_label))
            lines.append(f"    {sub_label}{' ' * pad2}  {sdesc}")


def _render_context(lines: list[str], context_dirs: list[dict[str, Any]]) -> None:
    """Emit ``context:`` section with file counts only (no descriptions)."""
    if not context_dirs:
        return
    lines.append("")
    lines.append("context:  (reference projects)")
    for item in context_dirs[:6]:
        name = item["name"]
        count = item.get("file_count", 0)
        lines.append(f"  {name}/  ({count:,} files)")


def _render_tooling(
    lines: list[str],
    tooling_dirs: list[dict[str, Any]],
    index: ProjectIndex,
) -> None:
    """Emit ``tooling:`` section with first-3 dirs and descriptions."""
    if not tooling_dirs:
        return
    lines.append("")
    lines.append("tooling:")
    for item in tooling_dirs[:3]:
        name = item["name"]
        _append_dir_line(lines, name, index.module_descriptions.get(name, ""))


def _append_dir_line(lines: list[str], name: str, desc: str) -> None:
    """Append one ``<name>/  <desc>`` line to the TOON output."""
    dir_label = name + "/"
    padding = max(1, _TOON_DIR_COL - len(dir_label))
    desc_str = f"  {desc}" if desc else ""
    lines.append(f"  {dir_label}{' ' * padding}{desc_str}".rstrip())
