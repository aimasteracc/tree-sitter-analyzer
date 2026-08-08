"""Contracts for the canonical language pipeline inventory."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.generate_language_support_inventory import BEGIN, END, _section_bounds
from tree_sitter_analyzer.import_extractors import IMPORT_DISPATCH
from tree_sitter_analyzer.language_inventory import (
    CAPABILITY_COLUMNS,
    _load_builtin_plugins,
    _tier,
    build_inventory,
)
from tree_sitter_analyzer.plugins import manager as manager_module
from tree_sitter_analyzer.plugins.manager import PluginManager
from tree_sitter_analyzer.route_detector import ROUTE_LANGUAGE_DISPATCH


def test_language_inventory_pins_capability_counts() -> None:
    assert build_inventory()["counts"] == {
        "plugin_discovery": 22,
        "extractor_loadability": 22,
        "index_admission": 16,
        "import_dispatch": 13,
        "call_dispatch": 14,
        "resolver_slot": 16,
        "framework_dispatch": 5,
        "data_markup": 5,
        "scaffold": 1,
        "cross_file_call": {"verified": 0, "unknown": 13, "not_applicable": 9},
    }


def test_language_inventory_pins_product_tiers() -> None:
    assert build_inventory()["tier_counts"] == {
        "pipeline_registered": 13,
        "index_admitted": 2,
        "call_dispatch_only": 1,
        "data_markup": 5,
        "scaffold": 1,
    }


def test_cross_file_claims_remain_unknown_without_e2e_fixtures() -> None:
    # Incident NO1-005A (2026-08-08): dispatch intersections were called E2E proof.
    rows = build_inventory()["languages"]
    assert {
        row["language"] for row in rows if row["cross_file_call"] == "verified"
    } == set()


def test_inventory_fails_closed_when_a_discovered_plugin_cannot_load(
    monkeypatch,
) -> None:
    # Incident NO1-005A (2026-08-08): basename discovery was treated as extraction proof.
    original = PluginManager.get_plugin

    def fail_bash(self, language):
        if language == "bash":
            return None
        return original(self, language)

    monkeypatch.setattr(PluginManager, "get_plugin", fail_bash)
    with pytest.raises(RuntimeError, match="failed to load built-in plugin: bash"):
        _load_builtin_plugins()


def test_inventory_rejects_discovery_set_drift(monkeypatch) -> None:
    original = PluginManager.load_plugins

    def omit_bash(self) -> None:
        original(self)
        self._plugin_modules.pop("bash")

    monkeypatch.setattr(PluginManager, "load_plugins", omit_bash)
    with pytest.raises(RuntimeError, match=r"missing=\['bash'\]"):
        _load_builtin_plugins()


def test_inventory_rejects_plugin_with_wrong_language_name(monkeypatch) -> None:
    original = PluginManager.get_plugin

    class WrongNamePlugin:
        def get_language_name(self) -> str:
            return "not-bash"

    def wrong_bash(self, language):
        if language == "bash":
            return WrongNamePlugin()
        return original(self, language)

    monkeypatch.setattr(PluginManager, "get_plugin", wrong_bash)
    with pytest.raises(RuntimeError, match="failed to load built-in plugin: bash"):
        _load_builtin_plugins()


def test_inventory_wraps_extractor_creation_failure(monkeypatch) -> None:
    original = PluginManager.get_plugin

    def broken_bash(self, language):
        plugin = original(self, language)
        if language == "bash":

            def fail():
                raise ValueError("broken extractor")

            plugin.create_extractor = fail
        return plugin

    monkeypatch.setattr(PluginManager, "get_plugin", broken_bash)
    with pytest.raises(RuntimeError, match="failed to create extractor: bash"):
        _load_builtin_plugins()


def test_inventory_rejects_plugin_returning_no_extractor(monkeypatch) -> None:
    original = PluginManager.get_plugin

    def empty_bash(self, language):
        plugin = original(self, language)
        if language == "bash":
            plugin.create_extractor = lambda: None
        return plugin

    monkeypatch.setattr(PluginManager, "get_plugin", empty_bash)
    with pytest.raises(RuntimeError, match="plugin returned no extractor: bash"):
        _load_builtin_plugins()


def test_inventory_rejects_unclassified_plugin_capabilities() -> None:
    capabilities = {
        "scaffold": False,
        "data_markup": False,
        "index_admission": False,
        "import_dispatch": False,
        "call_dispatch": False,
        "resolver_slot": False,
    }
    with pytest.raises(ValueError, match="no classified product tier"):
        _tier(capabilities)


def test_inventory_rejects_entry_point_masking_a_failed_local_plugin(
    monkeypatch,
) -> None:
    # Incident NO1-005A (2026-08-08): entry-point fallback masked local load failure.
    original_local_loader = manager_module.lazy_load_local_plugin
    original_entry_point_loader = manager_module.lazy_load_entry_point_plugin

    class ShadowBashPlugin:
        def get_language_name(self) -> str:
            return "bash"

        def create_extractor(self) -> object:
            return object()

    def fail_only_local_bash(language, *args, **kwargs):
        if language == "bash":
            return None
        return original_local_loader(language, *args, **kwargs)

    def fallback_only_bash(language, *args, **kwargs):
        if language == "bash":
            return ShadowBashPlugin()
        return original_entry_point_loader(language, *args, **kwargs)

    monkeypatch.setattr(manager_module, "lazy_load_local_plugin", fail_only_local_bash)
    monkeypatch.setattr(
        manager_module, "lazy_load_entry_point_plugin", fallback_only_bash
    )
    with pytest.raises(RuntimeError, match="wrong origin for built-in plugin bash"):
        _load_builtin_plugins()


def test_import_dispatch_registry_is_immutable() -> None:
    with pytest.raises(TypeError):
        IMPORT_DISPATCH["new-language"] = lambda *args: None  # type: ignore[index]


def test_route_dispatch_registry_is_immutable() -> None:
    with pytest.raises(TypeError):
        ROUTE_LANGUAGE_DISPATCH["new-language"] = "python"  # type: ignore[index]


def test_import_evidence_uses_executable_dispatch_registry() -> None:
    rows = build_inventory()["languages"]
    assert {row["language"] for row in rows if row["import_dispatch"]} == set(
        IMPORT_DISPATCH
    )


def test_framework_evidence_uses_executable_dispatch_registry() -> None:
    rows = build_inventory()["languages"]
    assert {row["language"] for row in rows if row["framework_dispatch"]} == set(
        ROUTE_LANGUAGE_DISPATCH
    )


def test_inventory_rows_have_exact_capability_schema() -> None:
    rows = build_inventory()["languages"]
    expected = {"language", "display_name", "tier", *CAPABILITY_COLUMNS}
    assert {frozenset(row) for row in rows} == {frozenset(expected)}


def test_generated_section_rejects_missing_markers() -> None:
    # Incident NO1-005A (2026-08-08): generator checks must fail closed.
    with pytest.raises(ValueError, match="exactly one"):
        _section_bounds("ordinary text")


def test_generated_section_rejects_duplicate_markers() -> None:
    # Incident NO1-005A (2026-08-08): duplicate generated sections passed --check.
    with pytest.raises(ValueError, match="exactly one"):
        _section_bounds(f"{BEGIN}{END}{BEGIN}{END}")


def test_generated_section_rejects_reversed_markers() -> None:
    # Incident NO1-005A (2026-08-08): generator checks must reject marker order.
    with pytest.raises(ValueError, match="precedes"):
        _section_bounds(f"{END}{BEGIN}")


def test_generated_section_rejects_nested_markers() -> None:
    # Incident NO1-005A (2026-08-08): nested marker pairs must not be ambiguous.
    with pytest.raises(ValueError, match="exactly one"):
        _section_bounds(f"{BEGIN}{BEGIN}{END}{END}")


@pytest.mark.parametrize(
    ("readme", "plugin_fact", "lua_fact", "stale_count", "stale_lua_claim"),
    (
        (
            "README_ja.md",
            "22 言語プラグイン",
            "Lua は公開済みの本番プラグイン",
            "21 言語プラグイン",
            "未実装の主流コード言語は **Dart, Vue, Svelte, Lua**",
        ),
        (
            "README_zh.md",
            "22 个语言插件",
            "Lua 已作为生产插件发布",
            "21 个语言插件",
            "还未发布的主流代码语言只有 **Dart、Vue、Svelte、Lua**",
        ),
    ),
)
def test_translated_readmes_pin_plugin_count_and_lua_tier(
    readme: str,
    plugin_fact: str,
    lua_fact: str,
    stale_count: str,
    stale_lua_claim: str,
) -> None:
    text = Path(readme).read_text(encoding="utf-8")
    assert plugin_fact in text
    assert lua_fact in text
    assert "call-dispatch-only" in text
    assert stale_count not in text
    assert stale_lua_claim not in text


@pytest.mark.parametrize(
    ("readme", "registration_fact", "non_e2e_fact", "stale_claims"),
    (
        (
            "README_ja.md",
            "13 言語は `pipeline_registered`（パイプライン登録済み、非 E2E",
            "これは登録・配線の証拠",
            (
                "13 言語のフルコールグラフ インデックス",
                "13 言語はパイプライン登録済み（Python",
            ),
        ),
        (
            "README_zh.md",
            "13 种语言为 `pipeline_registered`（管线注册态，非 E2E",
            "这只是注册与接线证据",
            (
                "13 种语言全量调用图索引",
                "13 种语言已注册到完整管线",
            ),
        ),
    ),
)
def test_translated_readme_headlines_reject_full_call_graph_overclaim(
    readme: str,
    registration_fact: str,
    non_e2e_fact: str,
    stale_claims: tuple[str, ...],
) -> None:
    # Incident NO1-005A (2026-08-08): registrations were described as E2E proof.
    text = Path(readme).read_text(encoding="utf-8")
    assert registration_fact in text
    assert non_e2e_fact in text
    for stale_claim in stale_claims:
        assert stale_claim not in text


@pytest.mark.parametrize(
    (
        "readme",
        "section_heading",
        "next_heading",
        "pipeline_row",
        "index_row",
        "lua_row",
        "stale_tier_labels",
    ),
    (
        (
            "README_ja.md",
            "## サポート言語",
            "## 設定",
            "| **`pipeline_registered`（パイプライン登録済み、非 E2E）** | Python · Java · JavaScript · TypeScript · Go · Rust · C · C++ · C# · Swift · Kotlin · Ruby · PHP |",
            "| **`index_admitted`（インデックス受け入れ済み）** | Bash · Scala |",
            "| **call-dispatch-only（本番プラグイン）** | Lua |",
            ("完全インデックス", "フルコールグラフ", "フル コール グラフ"),
        ),
        (
            "README_zh.md",
            "## 支持的语言",
            "## 配置",
            "| **`pipeline_registered`（管线注册态，非 E2E）** | Python · Java · JavaScript · TypeScript · Go · Rust · C · C++ · C# · Swift · Kotlin · Ruby · PHP |",
            "| **`index_admitted`（索引准入态）** | Bash · Scala |",
            "| **call-dispatch-only（生产插件）** | Lua |",
            ("完整索引", "全量调用图", "完整调用图"),
        ),
    ),
)
def test_translated_support_tables_pin_evidence_tiers_without_e2e_overclaim(
    readme: str,
    section_heading: str,
    next_heading: str,
    pipeline_row: str,
    index_row: str,
    lua_row: str,
    stale_tier_labels: tuple[str, ...],
) -> None:
    # Incident NO1-005A (2026-08-08): translated tiers overstated registrations.
    text = Path(readme).read_text(encoding="utf-8")
    support_section = text.split(section_heading, 1)[1].split(next_heading, 1)[0]
    assert pipeline_row in support_section
    assert index_row in support_section
    assert lua_row in support_section
    for stale_tier_label in stale_tier_labels:
        assert stale_tier_label not in support_section


@pytest.mark.parametrize("readme", ("README_ja.md", "README_zh.md"))
def test_translated_readmes_reject_unregistered_quantitative_marketing(
    readme: str,
) -> None:
    # Incident NO1-005A (2026-08-08): translations retained withdrawn E<4 claims.
    text = Path(readme).read_text(encoding="utf-8")
    withdrawn_patterns = (
        "~390",
        "約 390",
        "约 390",
        "1,259",
        "50-70",
        "50–70",
        "0.52",
        "40k",
        "~400",
        "約 400",
        "约 400",
        "3-4",
        "20+",
        "100%",
        "100 %",
        "7557×",
        "9016×",
        "96.3%",
        "181 秒",
    )
    assert [pattern for pattern in withdrawn_patterns if pattern in text] == []


@pytest.mark.parametrize(
    ("readme", "controlled_facts"),
    (
        (
            "README_ja.md",
            (
                "Python 3.10 以上",
                "8 MCP ツール",
                "### 323 の CLI フラグ",
                "22 言語プラグイン",
                "13 は `pipeline_registered`",
                "2 は `index_admitted`",
                "Lua は本番プラグインとして call-dispatch-only",
            ),
        ),
        (
            "README_zh.md",
            (
                "需要 Python 3.10+",
                "8 个 MCP 工具",
                "### 323 个 CLI flag",
                "22 个语言插件",
                "13 个为 `pipeline_registered`",
                "2 个为 `index_admitted`",
                "Lua 是生产可用的 call-dispatch-only 插件",
            ),
        ),
    ),
)
def test_translated_readmes_pin_contract_controlled_facts(
    readme: str,
    controlled_facts: tuple[str, ...],
) -> None:
    # Incident NO1-005A (2026-08-08): only contract-backed counts may remain.
    text = Path(readme).read_text(encoding="utf-8")
    assert [fact for fact in controlled_facts if fact not in text] == []


def test_generated_language_inventory_has_no_drift() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/generate_language_support_inventory.py", "--check"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
