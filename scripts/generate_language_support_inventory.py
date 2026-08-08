#!/usr/bin/env python3
"""Render/check the canonical language support-depth inventory."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from tree_sitter_analyzer.language_inventory import CAPABILITY_COLUMNS, build_inventory

ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "docs" / "language-support-inventory.json"
README_PATHS = {
    "en": ROOT / "README.md",
    "ja": ROOT / "README_ja.md",
    "zh": ROOT / "README_zh.md",
}
README_PATH = README_PATHS["en"]
CODEMAP_PATH = ROOT / "docs" / "CODEMAPS" / "languages.md"
BEGIN = "<!-- BEGIN GENERATED LANGUAGE SUPPORT INVENTORY -->"
END = "<!-- END GENERATED LANGUAGE SUPPORT INVENTORY -->"
LABELS = {
    "plugin_discovery": "Plugin discovery",
    "extractor_loadability": "Extractor loadability",
    "index_admission": "Index admission",
    "import_dispatch": "Import dispatch",
    "call_dispatch": "Call dispatch",
    "resolver_slot": "Resolver slot",
    "framework_dispatch": "Framework dispatch",
    "cross_file_call": "Cross-file call E2E",
    "data_markup": "Data/markup",
    "scaffold": "Scaffold",
}


def render_json() -> str:
    return json.dumps(build_inventory(), indent=2, sort_keys=True) + "\n"


def render_markdown(*, compact: bool = False, locale: str = "en") -> str:
    inventory = build_inventory()
    counts = inventory["counts"]
    tiers = inventory["tier_counts"]
    summary = (
        f"**{counts['plugin_discovery']} plugins**: "
        f"{tiers['pipeline_registered']} pipeline-registered, "
        f"{tiers['index_admitted']} index-admitted, "
        f"{tiers['call_dispatch_only']} call-dispatch-only, "
        f"{tiers['data_markup']} data/markup, {tiers['scaffold']} scaffold."
    )
    if compact:
        tier_languages: dict[str, list[str]] = {}
        for row in inventory["languages"]:
            tier_languages.setdefault(row["tier"], []).append(row["display_name"])
        if locale == "en":
            intro = (
                "Generated from runtime registries; see [`docs/CODEMAPS/languages.md`](docs/CODEMAPS/languages.md) for the full capability matrix. "
                + summary
                + " `pipeline_registered` is registration evidence, not positive cross-file binding proof."
            )
            rows = [
                " | ".join(
                    f"`{tier}`: {', '.join(tier_languages.get(tier, []))}"
                    for tier in (
                        "pipeline_registered",
                        "index_admitted",
                        "call_dispatch_only",
                        "data_markup",
                        "scaffold",
                    )
                )
            ]
        elif locale == "ja":
            intro = (
                f"ランタイムレジストリから生成。**{counts['plugin_discovery']} 言語プラグイン**; "
                f"{tiers['pipeline_registered']} は `pipeline_registered`（非 E2E）、"
                f"{tiers['index_admitted']} は `index_admitted`、{tiers['data_markup']} 個は data/markup、"
                f"{tiers['scaffold']} 個はスキャフォールド。登録は正のクロスファイル束縛を保証しない。"
            )
            rows = [
                "| ティア | 言語 |",
                "|---|---|",
                f"| **`pipeline_registered`（パイプライン登録済み、非 E2E）** | {' · '.join(tier_languages['pipeline_registered'])} |",
                f"| **`index_admitted`（インデックス受け入れ済み）** | {' · '.join(tier_languages['index_admitted'])} |",
                f"| **単一ファイル解析 (CLI)** | {' · '.join(tier_languages['data_markup'])} |",
                f"| **スキャフォールド (プラグイン有 / インデクサー結線待ち)** | {' · '.join(tier_languages['scaffold'])} |",
                "",
                "Lua はインデックス受け入れ済みで call dispatch と resolver slot も持つが、import dispatch とクロスファイル E2E 証拠は未確認。",
            ]
        elif locale == "zh":
            intro = (
                f"由运行时 registry 生成。**{counts['plugin_discovery']} 个语言插件**；"
                f"{tiers['pipeline_registered']} 个为 `pipeline_registered`（非 E2E），"
                f"{tiers['index_admitted']} 个为 `index_admitted`，{tiers['data_markup']} 个 data/markup，"
                f"{tiers['scaffold']} 个脚手架。注册状态不保证跨文件正向绑定。"
            )
            rows = [
                "| 等级 | 语言 |",
                "|---|---|",
                f"| **`pipeline_registered`（管线注册态，非 E2E）** | {' · '.join(tier_languages['pipeline_registered'])} |",
                f"| **`index_admitted`（索引准入态）** | {' · '.join(tier_languages['index_admitted'])} |",
                f"| **单文件分析（CLI）** | {' · '.join(tier_languages['data_markup'])} |",
                f"| **脚手架（插件已有，索引器待接）** | {' · '.join(tier_languages['scaffold'])} |",
                "",
                "Lua 已获索引准入，并具备 call dispatch 与 resolver slot，但 import dispatch 和跨文件 E2E 证据仍未确认。",
            ]
        else:
            raise ValueError(f"unsupported locale: {locale}")
        return "\n".join([BEGIN, intro, *rows, END, ""])
    lines = [
        BEGIN,
        "Generated from runtime registries and reviewed classifications by `scripts/generate_language_support_inventory.py`; do not edit counts or rows by hand.",
        "",
        summary,
        "",
        "`pipeline_registered` means index admission plus import/call dispatch and a resolver slot. It does **not** guarantee positive cross-file binding. `Cross-file call E2E` is `unknown` until a fixture proves a call resolves to a different project file.",
        "",
        "| Language | Tier | "
        + " | ".join(LABELS[c] for c in CAPABILITY_COLUMNS)
        + " |",
        "|---|---|" + "---|" * len(CAPABILITY_COLUMNS),
    ]
    for row in inventory["languages"]:
        values = [
            row[column]
            if column == "cross_file_call"
            else ("yes" if row[column] else "—")
            for column in CAPABILITY_COLUMNS
        ]
        lines.append(
            f"| {row['display_name']} | `{row['tier']}` | " + " | ".join(values) + " |"
        )
    lines.extend([END, ""])
    return "\n".join(lines)


def _section_bounds(text: str) -> tuple[int, int]:
    """Return the sole ordered marker pair, rejecting all malformed layouts."""
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        raise ValueError("expected exactly one generated inventory marker pair")
    start = text.index(BEGIN)
    finish = text.index(END)
    if finish < start:
        raise ValueError("generated inventory end marker precedes begin marker")
    return start, finish + len(END)


def _replace_section(text: str, section: str) -> str:
    start, finish = _section_bounds(text)
    return text[:start] + section.rstrip() + text[finish:]


def write_outputs() -> None:
    JSON_PATH.write_text(render_json(), encoding="utf-8")
    sections = tuple(
        (path, render_markdown(compact=True, locale=locale))
        for locale, path in README_PATHS.items()
    ) + ((CODEMAP_PATH, render_markdown()),)
    for path, section in sections:
        path.write_text(
            _replace_section(path.read_text(encoding="utf-8"), section),
            encoding="utf-8",
        )


def check_outputs() -> int:
    failures: list[str] = []
    if not JSON_PATH.exists() or JSON_PATH.read_text(encoding="utf-8") != render_json():
        failures.append(str(JSON_PATH.relative_to(ROOT)))
    sections = tuple(
        (path, render_markdown(compact=True, locale=locale))
        for locale, path in README_PATHS.items()
    ) + ((CODEMAP_PATH, render_markdown()),)
    for path, rendered in sections:
        section = rendered.rstrip()
        text = path.read_text(encoding="utf-8")
        try:
            start, finish = _section_bounds(text)
            current = text[start:finish]
        except ValueError:
            failures.append(str(path.relative_to(ROOT)))
            continue
        if current != section:
            failures.append(str(path.relative_to(ROOT)))
    if failures:
        print("language inventory drift: " + ", ".join(failures))
        print(
            "run: uv run python scripts/generate_language_support_inventory.py --write"
        )
        return 1
    return 0


def main() -> int:
    # Inventory validation intentionally loads every extractor; keep generated
    # output machine-clean even when optional platform profiles log warnings.
    logging.disable(logging.CRITICAL)
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.write:
        write_outputs()
        return 0
    if args.check:
        return check_outputs()
    print(render_json() if args.format == "json" else render_markdown(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
