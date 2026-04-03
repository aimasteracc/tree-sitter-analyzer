"""Grammar Snapshot System.

记录每种语言在某一时刻的完整 grammar 状态，作为 CI 比较基线。

工作原理：
1. `take_snapshot()` — 用 AutoDiscoveryEngine 枚举当前所有 named node types，
   写入 grammar_snapshot.json
2. `load_snapshot()` — 读取快照文件
3. `diff_snapshot()` — 对比当前 grammar vs 快照，发现新增/删除的节点类型
4. `check_snapshot()` — CI 入口：发现新增节点时退出码非 0，触发告警

已知 Python 2 遗留节点（无法在 Python 3 corpus 中出现，但 grammar 中存在）：
这类节点记录在 KNOWN_LEGACY_NODES 中，CI 检查时跳过。
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..utils import log_debug, log_warning
from .auto_discovery import AutoDiscoveryEngine
from .discovery_corpus import TARGET_LANGUAGES

# 默认快照文件路径（相对于项目根目录）
DEFAULT_SNAPSHOT_PATH = Path(__file__).parent.parent.parent / "grammar_snapshot.json"

# 已知的语言版本遗留节点（这些节点存在于 grammar 中但无法在现代代码中触发）
# 当 BUILTIN_CORPUS_EXTRA 已覆盖某个遗留节点后，从此处移除。
KNOWN_LEGACY_NODES: dict[str, set[str]] = {}


@dataclass
class LanguageSnapshot:
    """单个语言的 grammar 快照."""

    language: str
    node_types: list[str]
    node_count: int
    package_version: str


@dataclass
class SnapshotDiff:
    """两个快照之间的差异."""

    language: str
    added: list[str]       # 当前 grammar 有、快照没有 → 新语法
    removed: list[str]     # 快照有、当前 grammar 没有 → 已废弃语法
    unchanged: int

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed)

    @property
    def has_new_nodes(self) -> bool:
        return bool(self.added)


def _get_package_version(language: str) -> str:
    """获取 tree-sitter 语言包版本号."""
    from ..language_loader import LanguageLoader
    module_name = LanguageLoader.LANGUAGE_MODULES.get(language, "")
    if not module_name:
        return "unknown"
    try:
        import importlib.metadata
        return importlib.metadata.version(module_name.replace("_", "-"))
    except Exception:
        try:
            mod = __import__(module_name)
            return getattr(mod, "__version__", "unknown")
        except Exception:
            return "unknown"


def take_snapshot(
    languages: list[str] | None = None,
    output_path: Path | None = None,
) -> dict[str, LanguageSnapshot]:
    """生成并保存当前 grammar 快照.

    Args:
        languages: 指定语言列表；为 None 时使用所有 TARGET_LANGUAGES
        output_path: 快照文件保存路径；为 None 时使用 DEFAULT_SNAPSHOT_PATH

    Returns:
        {language: LanguageSnapshot}
    """
    target = languages if languages is not None else TARGET_LANGUAGES
    engine = AutoDiscoveryEngine()
    snapshots: dict[str, LanguageSnapshot] = {}

    for lang in target:
        try:
            node_types = engine.get_all_node_types(lang)
            version = _get_package_version(lang)
            snap = LanguageSnapshot(
                language=lang,
                node_types=sorted(node_types),
                node_count=len(node_types),
                package_version=version,
            )
            snapshots[lang] = snap
            log_debug(f"[{lang}] snapshot: {len(node_types)} node types (v{version})")
        except (ValueError, ImportError) as e:
            log_warning(f"Skipping '{lang}': {e}")

    path = output_path or DEFAULT_SNAPSHOT_PATH
    _save_snapshot(snapshots, path)
    return snapshots


def load_snapshot(
    path: Path | None = None,
) -> dict[str, LanguageSnapshot]:
    """从文件加载 grammar 快照.

    Args:
        path: 快照文件路径；为 None 时使用 DEFAULT_SNAPSHOT_PATH

    Returns:
        {language: LanguageSnapshot}

    Raises:
        FileNotFoundError: 快照文件不存在
    """
    p = path or DEFAULT_SNAPSHOT_PATH
    if not p.exists():
        raise FileNotFoundError(
            f"Grammar snapshot not found: {p}\n"
            f"Run `python -m tree_sitter_analyzer.grammar_coverage.grammar_snapshot --update` to create it."
        )

    with open(p, encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)

    result: dict[str, LanguageSnapshot] = {}
    for lang, entry in data.items():
        result[lang] = LanguageSnapshot(
            language=lang,
            node_types=entry["node_types"],
            node_count=entry["node_count"],
            package_version=entry.get("package_version", "unknown"),
        )
    return result


def diff_snapshot(
    baseline: dict[str, LanguageSnapshot],
    languages: list[str] | None = None,
) -> dict[str, SnapshotDiff]:
    """对比当前 grammar 与基线快照的差异.

    Args:
        baseline: load_snapshot() 返回的基线快照
        languages: 检查的语言列表；为 None 时检查 baseline 中所有语言

    Returns:
        {language: SnapshotDiff}，只包含有变更的语言（+ 有基线的语言）
    """
    engine = AutoDiscoveryEngine()
    target = languages if languages is not None else list(baseline.keys())
    diffs: dict[str, SnapshotDiff] = {}

    for lang in target:
        if lang not in baseline:
            log_warning(f"Language '{lang}' not in baseline snapshot, skipping")
            continue

        try:
            current_types = set(engine.get_all_node_types(lang))
        except (ValueError, ImportError) as e:
            log_warning(f"Skipping '{lang}': {e}")
            continue

        baseline_types = set(baseline[lang].node_types)
        legacy = KNOWN_LEGACY_NODES.get(lang, set())

        added = sorted(current_types - baseline_types - legacy)
        removed = sorted(baseline_types - current_types - legacy)
        unchanged = len(current_types & baseline_types)

        diffs[lang] = SnapshotDiff(
            language=lang,
            added=added,
            removed=removed,
            unchanged=unchanged,
        )

    return diffs


def check_snapshot(
    baseline_path: Path | None = None,
    fail_on_new: bool = True,
    verbose: bool = True,
) -> int:
    """CI 入口：检查当前 grammar 是否与基线一致.

    Args:
        baseline_path: 基线快照路径
        fail_on_new: 发现新节点时返回非 0 退出码
        verbose: 打印详细信息

    Returns:
        0 = 无变更（或仅有删除），1 = 发现新节点类型
    """
    try:
        baseline = load_snapshot(baseline_path)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    diffs = diff_snapshot(baseline)
    has_new = False

    for lang, diff in sorted(diffs.items()):
        if not diff.has_changes:
            if verbose:
                print(f"  ✅  {lang}: no changes ({diff.unchanged} node types)")
            continue

        if diff.added:
            has_new = True
            print(f"\n  🚨  {lang}: {len(diff.added)} NEW node type(s) detected!")
            for nt in diff.added:
                print(f"       + {nt}")
            print(
                "       → Add corpus examples and plugin support, then run:\n"
                "         python -m tree_sitter_analyzer.grammar_coverage.grammar_snapshot --update"
            )

        if diff.removed:
            print(f"\n  ⚠️   {lang}: {len(diff.removed)} node type(s) removed from grammar:")
            for nt in diff.removed:
                print(f"       - {nt}")

    if has_new and fail_on_new:
        print("\nCI FAILED: New grammar nodes require corpus + plugin updates.", file=sys.stderr)
        return 1

    if verbose and not has_new:
        print("\n✅  All grammar node types match baseline.")
    return 0


def _save_snapshot(
    snapshots: dict[str, LanguageSnapshot],
    path: Path,
) -> None:
    """将快照序列化写入 JSON 文件."""
    data = {lang: asdict(snap) for lang, snap in snapshots.items()}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Snapshot saved to: {path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Grammar snapshot tool")
    parser.add_argument("--update", action="store_true", help="Generate/update snapshot")
    parser.add_argument("--check", action="store_true", help="Check vs baseline (CI mode)")
    parser.add_argument("--path", help="Snapshot file path")
    parser.add_argument("--language", help="Single language to process")
    args = parser.parse_args()

    snap_path = Path(args.path) if args.path else None
    langs = [args.language] if args.language else None

    if args.update:
        snaps = take_snapshot(languages=langs, output_path=snap_path)
        print(f"\nSnapshot complete: {len(snaps)} languages")
        for lang, s in sorted(snaps.items()):
            print(f"  {lang:<14} {s.node_count:>4} node types  (v{s.package_version})")
        sys.exit(0)

    elif args.check:
        sys.exit(check_snapshot(baseline_path=snap_path, verbose=True))

    else:
        parser.print_help()
        sys.exit(1)
