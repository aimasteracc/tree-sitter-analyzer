"""Golden-master regression tests for every language plugin.

For each language we exercise ``plugin.analyze_file()`` against a fixture
under ``examples/`` and snapshot a stable summary (element counts + sorted
name lists, NOT raw AST geometry which is too brittle). The snapshot lives
under ``tests/golden_masters/plugins/<lang>.json``.

Why this exists: commit e1a024c unified all 18 language plugins, and
``KI-R5`` later showed how easy it is for a single-line change in one
plugin to silently break others' byte-level extraction. These tests
catch the next regression before it ships. See TEST-P5 in
the project's internal quality tracker.

To accept a deliberate change (e.g. you added a new element category),
set ``TSA_UPDATE_GOLDEN=1`` and run the test once; the new JSON snapshot
is written and committed in the same change as the code that motivated
it.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer.core.request import AnalysisRequest
from tree_sitter_analyzer.plugins.manager import PluginManager

pytestmark = pytest.mark.full_language

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = PROJECT_ROOT / "examples"
GOLDEN_DIR = PROJECT_ROOT / "tests" / "golden_masters" / "plugins"

# (language, fixture_path). One row per supported plugin. Skip lines for
# languages that don't yet have a stable fixture — track them in TEST-P5
# follow-ups rather than failing CI on a missing snapshot.
_FIXTURES: list[tuple[str, str]] = [
    ("java", "Sample.java"),
    ("python", "sample.py"),
    ("javascript", "ModernJavaScript.js"),
    ("typescript", "ComprehensiveTypeScript.ts"),
    ("csharp", "Sample.cs"),
    ("kotlin", "Sample.kt"),
    ("php", "Sample.php"),
    ("ruby", "Sample.rb"),
    ("c", "sample.c"),
    ("cpp", "sample.cpp"),
    ("go", "sample.go"),
    ("rust", "sample.rs"),
    ("swift", "sample.swift"),
    ("sql", "sample_database.sql"),
    ("markdown", "test_markdown.md"),
    ("yaml", "sample_config.yaml"),
    ("html", "comprehensive_sample.html"),
    ("css", "comprehensive_sample.css"),
]


def _summary(elements: list[Any]) -> dict[str, Any]:
    """Build a stable, version-tolerant summary of an analysis result.

    We deliberately do NOT snapshot byte offsets, line numbers, or raw AST
    shape — those churn on grammar upgrades. We DO snapshot:
      * element counts per type label
      * sorted unique names per type label
      * the union of element type labels emitted by the plugin
    """
    by_type: dict[str, list[str]] = {}
    for elem in elements:
        type_label = type(elem).__name__
        name = (
            getattr(elem, "name", None)
            or getattr(elem, "identifier", None)
            or "<anonymous>"
        )
        by_type.setdefault(type_label, []).append(str(name))
    counts = {t: len(names) for t, names in by_type.items()}
    names = {t: sorted(set(filter(lambda n: n, names))) for t, names in by_type.items()}
    return {
        "element_total": len(elements),
        "types": sorted(by_type),
        "counts_by_type": dict(sorted(counts.items())),
        "names_by_type": {k: names[k] for k in sorted(names)},
    }


def _analyze(language: str, fixture: Path) -> dict[str, Any]:
    mgr = PluginManager()
    plugin = mgr.get_plugin(language)
    assert plugin is not None, f"plugin for {language} not found"
    request = AnalysisRequest(
        file_path=str(fixture),
        language=language,
        include_complexity=False,
        include_details=False,
    )
    result = asyncio.run(plugin.analyze_file(str(fixture), request))
    return _summary(list(result.elements or []))


@pytest.mark.parametrize("language,fixture_name", _FIXTURES)
def test_plugin_golden_master(language: str, fixture_name: str) -> None:
    fixture = EXAMPLES / fixture_name
    if not fixture.exists():
        pytest.skip(f"fixture missing: {fixture}")
    actual = _analyze(language, fixture)

    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    golden = GOLDEN_DIR / f"{language}.json"
    actual_text = json.dumps(actual, indent=2, ensure_ascii=False, sort_keys=True)

    if os.environ.get("TSA_UPDATE_GOLDEN"):
        golden.write_text(actual_text + "\n", encoding="utf-8")
        pytest.skip(f"updated golden: {golden.relative_to(PROJECT_ROOT)}")

    if not golden.exists():
        golden.write_text(actual_text + "\n", encoding="utf-8")
        pytest.fail(
            f"golden master created for {language} — review and commit "
            f"{golden.relative_to(PROJECT_ROOT)} (re-run will pass)"
        )

    expected = json.loads(golden.read_text(encoding="utf-8"))
    if actual != expected:
        # Render a compact diff so the failure is actionable without
        # piping into difflib.
        diffs: list[str] = []
        for key in sorted(set(actual) | set(expected)):
            if actual.get(key) != expected.get(key):
                diffs.append(
                    f"  {key}:\n    expected: {expected.get(key)}\n    actual:   {actual.get(key)}"
                )
        pytest.fail(
            f"{language} plugin output drifted from golden master:\n"
            + "\n".join(diffs)
            + "\n\nAccept with TSA_UPDATE_GOLDEN=1 if intentional."
        )


def test_all_supported_languages_have_a_fixture_row() -> None:
    """Surface drift between the plugin roster and the regression matrix."""
    from tree_sitter_analyzer.plugins.manager import PluginManager

    mgr = PluginManager()
    mgr.load_plugins()
    supported = set()
    for plugin in mgr._loaded_plugins.values():
        supported.add(plugin.get_language_name().lower())
    matrix = {lang for lang, _ in _FIXTURES}
    missing = supported - matrix
    extra = matrix - supported
    assert not missing, (
        f"Languages supported by PluginManager but missing from the golden-master "
        f"matrix in test_plugin_golden_masters.py: {sorted(missing)}"
    )
    # `extra` is informational only — a fixture for a language not yet
    # supported gets skipped at runtime anyway.
    _ = extra
