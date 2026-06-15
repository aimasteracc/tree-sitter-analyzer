"""Issue #637 — TOON encoder silently dropped fields absent from a
heterogeneous array's first row.

The array-table header was built from ``items[0].keys()`` only
(``_handle_array_table`` / ``_infer_schema``), and ``_handle_dict_key``
routed ANY first-item-is-dict list into the table path without the
homogeneity check that ``_handle_list_start`` carries.  Result: a ghost
first row without ``body`` erased every later caller's ``body`` — the
"token-efficient" format was silently LOSSY.

Fix shape (option a): the table schema is the UNION of all rows' keys in
first-seen order; rows missing a key render an empty cell.  Homogeneous
arrays are byte-identical to the pre-fix output (union of identical key
sets == first row's keys).

All pins are exact ``==`` (user-locked rule — no substring-only/loose
assertions for deterministic encoder output).
"""

from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder
from tree_sitter_analyzer.formatters.toon_formatter import ToonFormatter


class TestHeterogeneousArrayLosslessness:
    """Fields present in ANY row must appear in the TOON output."""

    def test_issue_637_minimal_repro_body_survives(self) -> None:
        """The lead-verified repro: second row's ``body`` must survive."""
        out = ToonFormatter().format(
            {"results": [{"a": 1}, {"a": 2, "body": "IMPORTANT"}]}
        )
        assert out == "results:\n  [2]{a,body}:\n    1,\n    2,IMPORTANT"

    def test_union_schema_first_seen_order(self) -> None:
        """Union keeps first-seen key order across rows."""
        out = ToonEncoder().encode({"rows": [{"b": 1}, {"a": 2}]})
        assert out == "rows:\n  [2]{b,a}:\n    1,\n    ,2"

    def test_empty_dict_first_row_no_longer_erases_table(self) -> None:
        """Pre-fix: schema from ``{}`` was empty → EVERY field of every row
        was dropped (``[2]{}:`` with blank rows). Union recovers them."""
        out = ToonEncoder().encode({"rows": [{}, {"a": 1}]})
        assert out == "rows:\n  [2]{a}:\n    \n    1"

    def test_nested_heterogeneous_array(self) -> None:
        """Heterogeneous arrays inside nested dicts go through the same
        dict-key route and must also be lossless."""
        out = ToonEncoder().encode({"outer": {"rows": [{"x": 1}, {"x": 2, "y": 3}]}})
        assert out == "outer:\n  rows:\n    [2]{x,y}:\n      1,\n      2,3"

    def test_dict_column_annotation_from_first_row_having_key(self) -> None:
        """Schema annotation (``key{subkeys}``) must come from the first row
        that HAS the key, not blindly from row 0 (which may lack it)."""
        out = ToonEncoder().encode(
            {"rows": [{"a": 1}, {"a": 2, "meta": {"x": 1, "y": 2}}]}
        )
        assert out == "rows:\n  [2]{a,meta{x,y}}:\n    1,\n    2,(1,2)"

    def test_issue_643_divergent_nested_subkeys_encode_inline(self) -> None:
        """#643: a dict cell whose subkeys DIVERGE from the header sample must
        encode self-describing ``(k:v)`` — not values-only ``(v1,v2)`` that
        would be positionally mis-read. Header samples ``meta{x,y}`` from row 0;
        row 1's ``{x,z}`` cannot reuse that annotation without losing ``z``."""
        out = ToonEncoder().encode(
            {"rows": [{"meta": {"x": 1, "y": 2}}, {"meta": {"x": 3, "z": 9}}]}
        )
        assert out == "rows:\n  [2]{meta{x,y}}:\n    (1,2)\n    (x:3,z:9)"

    def test_issue_643_matching_nested_subkeys_stay_compact(self) -> None:
        """Regression: cells whose subkeys MATCH the header sample keep the
        compact values-only form (the token-efficient common case)."""
        out = ToonEncoder().encode(
            {"rows": [{"meta": {"x": 1, "y": 2}}, {"meta": {"x": 3, "y": 4}}]}
        )
        assert out == "rows:\n  [2]{meta{x,y}}:\n    (1,2)\n    (3,4)"

    def test_mixed_dict_and_scalar_list_encodes_inline_not_crash(self) -> None:
        """A list whose first item is a dict but later items are scalars must
        NOT enter the table path (pre-fix: AttributeError → JSON fallback)."""
        out = ToonEncoder().encode({"rows": [{"a": 1}, "x"]})
        assert out == "rows: [{a:1},x]"

    def test_infer_schema_is_union(self) -> None:
        schema = ToonEncoder()._infer_schema([{"a": 1}, {"a": 2, "b": 3}])
        assert schema == ["a", "b"]

    def test_public_encode_array_table_heterogeneous(self) -> None:
        """Public convenience API infers the union schema too."""
        out = ToonEncoder().encode_array_table([{"a": 1}, {"b": 2}])
        assert out == "[2]{a,b}:\n  1,\n  ,2"


class TestHomogeneousArraysUnchanged:
    """The token-efficiency story: homogeneous tables are byte-identical."""

    def test_homogeneous_table_byte_identical_pin(self) -> None:
        """Byte-pin captured on develop dbda9a3e BEFORE the #637 fix —
        must not change by a single byte."""
        out = ToonEncoder().encode({"results": [{"a": 1, "b": 2}, {"a": 3, "b": 4}]})
        assert out == "results:\n  [2]{a,b}:\n    1,2\n    3,4"

    def test_homogeneous_formatter_entry_byte_identical_pin(self) -> None:
        out = ToonFormatter().format(
            {"results": [{"name": "f", "line": 1}, {"name": "g", "line": 2}]}
        )
        assert out == "results:\n  [2]{name,line}:\n    f,1\n    g,2"

    def test_top_level_heterogeneous_list_stays_inline(self) -> None:
        """``_handle_list_start``'s mixed-key inline form (already lossless)
        is intentionally preserved — pin so the routing doesn't drift."""
        out = ToonEncoder().encode([{"a": 1}, {"b": 2}])
        assert out == "[{a:1},{b:2}]"
