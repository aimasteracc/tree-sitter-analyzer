"""The opt-in SCIP evidence layer of ``nav action=callers`` on a real scip-typescript index.

Fixture: ``tests/fixtures/scip_ts`` (see ``scip_project``). ``Target.run`` and
``Store.save`` are called through typed receivers that TSA's own graph cannot
bind (``NAME_ONLY_INBOUND``); scip-typescript can.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.mcp.tools.scip_project import (
    callers,
    install_index,
    make_project,
    tsa_index,
)
from tree_sitter_analyzer.mcp.tools.callers_compact import compact_callers
from tree_sitter_analyzer.mcp.tools.callers_scip_source import INDEX_ENV

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv(INDEX_ENV, raising=False)
    project = make_project(tmp_path / "p")
    await tsa_index(project)
    return project


def _names(result: dict) -> list[tuple[str, str]]:
    return sorted((c["name"], c["confidence_tier"]) for c in result["callers"])


async def test_without_an_index_the_answer_has_no_scip_trace(root: Path) -> None:
    result = await callers(root, "Store.save", "src/store.ts")
    assert "scip" not in result
    assert result["completeness"] == "unknown"
    assert result["completeness_checks"]["required"] == 13
    assert "not_applicable" not in result["completeness_checks"]


async def test_proven_sites_flip_to_complete(root: Path) -> None:
    install_index(root)
    result = await callers(root, "Store.save", "src/store.ts")
    assert result["completeness"] == "complete"
    assert _names(result) == [("persist", "scip")]
    assert result["callers"][0]["resolution_kind"] == "scip"
    assert result["completeness_checks"] == {"required": 14, "checked": 14}
    scip = result["scip"]
    assert scip["status"] == "used"
    assert scip["sites"] == {"proven_target": 1, "proven_other": 1, "open": 0}
    assert scip["resolved_other"][0]["classes"] == ["other_class_nominal"]
    assert scip["unlisted_references_total"] == 0
    compact = compact_callers(result)
    assert compact["completeness"] == "complete"
    assert "persist  src/app.ts:3  scip" in compact["answer"]


async def test_trust_classes_and_count_mismatch_keep_sites_open(root: Path) -> None:
    install_index(root)
    result = await callers(root, "Target.run", "src/shapes.ts")
    assert _names(result) == [("both", "scip"), ("viaTarget", "scip")]
    # A non-nominal class, an interface and a line whose text names `run` more
    # often than SCIP reports (a comment) stay open, exactly as without SCIP.
    open_lines = sorted(s["line"] for s in result["name_only_sites"])
    assert open_lines == [12, 16, 28]
    assert result["completeness"] == "incomplete"
    assert result["completeness_reasons"] == ["NAME_ONLY_INBOUND"]
    classes = sorted(c for o in result["scip"]["resolved_other"] for c in o["classes"])
    assert classes == ["other_class_nominal", "subclass_override"]


async def test_stale_manifest_gives_exactly_todays_answer(root: Path) -> None:
    before = await callers(root, "Store.save", "src/store.ts")
    install_index(root)
    (root / "src" / "app.ts").write_text(
        (root / "src" / "app.ts").read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )
    after = await callers(root, "Store.save", "src/store.ts")
    assert after["scip"] == {"status": "stale", "detail": "uncommitted files differ"}
    assert after["completeness_checks"].pop("not_applicable") == {
        "scip_agreement": "stale"
    }
    for key in ("completeness", "completeness_reasons", "callers", "name_only_sites"):
        assert after[key] == before[key]


async def test_missing_manifest_is_stale(root: Path) -> None:
    install_index(root, manifest=False)
    result = await callers(root, "Store.save", "src/store.ts")
    assert result["scip"]["status"] == "stale"
    assert result["completeness"] == "unknown"


async def test_env_var_naming_a_missing_file_is_absent(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(INDEX_ENV, "nowhere/index.scip")
    result = await callers(root, "Store.save", "src/store.ts")
    assert result["scip"]["status"] == "absent"
    assert result["completeness_checks"]["not_applicable"] == {
        "scip_agreement": "absent"
    }


async def test_env_var_points_at_an_index(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    index = install_index(root)
    monkeypatch.setenv(INDEX_ENV, str(index))
    result = await callers(root, "Store.save", "src/store.ts")
    assert result["scip"]["status"] == "used"


async def test_python_targets_are_unsupported(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (root / "mod.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    install_index(root)
    result = await callers(root, "f", "mod.py")
    assert result["scip"] == {"status": "unsupported_language"}


async def test_unmapped_target_gives_no_evidence(root: Path) -> None:
    install_index(root)
    result = await callers(root, "Store.missing", "src/store.ts")
    assert result["scip"]["target"] == {"mapped": False, "reason": "not_found"}
    assert result["completeness_checks"]["not_applicable"] == {
        "scip_agreement": "target_not_found"
    }
