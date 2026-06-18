"""Round-trip oracle tests for TOON encoder + decoder.

Issue #1058: The TOON encoder is type-lossy — a string that LOOKS like a
scalar (bool/null/number) is emitted bare, so a spec-compliant decoder
reconstructs the WRONG Python type.

These tests are written RED-first (before the encoder fix and before the
decoder exists) per the CLAUDE.md TDD requirement and the exact-assertion
rule: every assertion pins an exact expected value, never a loose bound.

Test categories
---------------
1. ``TestAmbiguousStringQuoting`` — encoder conformance: scalar-looking strings
   MUST be quoted so a decoder can reconstruct the correct str type.
2. ``TestToonDecoder`` — decoder unit tests: the decoder must invert the encoder.
3. ``TestToonRoundTrip`` — oracle: ``decode_toon(encode_toon(x)) == x`` for all
   input shapes the encoder produces.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Import the decoder — this will fail with ImportError until the decoder
# module is created.  The test is intentionally RED at that point.
# ---------------------------------------------------------------------------
from tree_sitter_analyzer.formatters.toon_decoder import decode_toon
from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder

# ===========================================================================
# Section 1 — Encoder conformance: scalar-ambiguous strings must be quoted
# ===========================================================================


class TestAmbiguousStringQuoting:
    """Strings that look like TOON/JSON scalars MUST be quoted.

    Without quoting, a decoder cannot distinguish the Python ``str "true"``
    from the Python ``bool True``.  These were the exact failure cases from
    issue #1058.
    """

    def setup_method(self):
        self.enc = ToonEncoder(normalize_paths=False)

    # --- bool literals ---

    def test_string_true_is_quoted(self):
        result = self.enc.encode("true")
        assert result == '"true"'

    def test_string_false_is_quoted(self):
        result = self.enc.encode("false")
        assert result == '"false"'

    # --- null literal ---

    def test_string_null_is_quoted(self):
        result = self.enc.encode("null")
        assert result == '"null"'

    # --- integer-looking strings ---

    def test_string_integer_positive_is_quoted(self):
        result = self.enc.encode("42")
        assert result == '"42"'

    def test_string_integer_zero_is_quoted(self):
        result = self.enc.encode("0")
        assert result == '"0"'

    def test_string_integer_negative_is_quoted(self):
        result = self.enc.encode("-3")
        assert result == '"-3"'

    # --- float-looking strings ---

    def test_string_float_is_quoted(self):
        """The exact case from #1058: "100.0" decoded as float, not str."""
        result = self.enc.encode("100.0")
        assert result == '"100.0"'

    def test_string_float_no_leading_digit_is_quoted(self):
        result = self.enc.encode("3.14")
        assert result == '"3.14"'

    def test_string_negative_float_is_quoted(self):
        result = self.enc.encode("-1.5")
        assert result == '"-1.5"'

    # --- scientific notation ---

    def test_string_scientific_upper_is_quoted(self):
        result = self.enc.encode("1E5")
        assert result == '"1E5"'

    def test_string_scientific_lower_is_quoted(self):
        result = self.enc.encode("1e5")
        assert result == '"1e5"'

    def test_string_scientific_negative_exp_is_quoted(self):
        result = self.enc.encode("1.5e-3")
        assert result == '"1.5e-3"'

    # --- genuine scalars (not strings) stay unquoted ---

    def test_bool_true_stays_bare(self):
        """Python True -> bare ``true``; it is a genuine bool scalar."""
        result = self.enc.encode(True)
        assert result == "true"

    def test_bool_false_stays_bare(self):
        result = self.enc.encode(False)
        assert result == "false"

    def test_none_stays_bare(self):
        result = self.enc.encode(None)
        assert result == "null"

    def test_int_stays_bare(self):
        result = self.enc.encode(42)
        assert result == "42"

    def test_float_stays_bare(self):
        result = self.enc.encode(3.14)
        assert result == "3.14"

    # --- ordinary strings stay unquoted (no structural chars, not scalar-looking) ---

    def test_ordinary_word_stays_bare(self):
        result = self.enc.encode("hello")
        assert result == "hello"

    def test_mixed_alphanum_stays_bare(self):
        result = self.enc.encode("hello123world")
        assert result == "hello123world"

    # --- in dict values ---

    def test_dict_with_scalar_ambiguous_string_values(self):
        """All scalar-looking string VALUES in a dict must be quoted."""
        enc = ToonEncoder(normalize_paths=False)
        result = enc.encode(
            {
                "a": "true",
                "b": "false",
                "c": "null",
                "d": "42",
                "e": "100.0",
            }
        )
        assert 'a: "true"' in result
        assert 'b: "false"' in result
        assert 'c: "null"' in result
        assert 'd: "42"' in result
        assert 'e: "100.0"' in result


# ===========================================================================
# Section 2 — Decoder unit tests
# ===========================================================================


class TestToonDecoder:
    """Unit tests for the ``decode_toon`` function."""

    # --- scalars ---

    def test_decode_null(self):
        assert decode_toon("null") is None

    def test_decode_true(self):
        assert decode_toon("true") is True

    def test_decode_false(self):
        assert decode_toon("false") is False

    def test_decode_integer(self):
        result = decode_toon("42")
        assert result == 42
        assert type(result) is int

    def test_decode_negative_integer(self):
        result = decode_toon("-7")
        assert result == -7
        assert type(result) is int

    def test_decode_float(self):
        result = decode_toon("3.14")
        assert result == 3.14
        assert type(result) is float

    # --- quoted strings (the bug cases) ---

    def test_decode_quoted_true_gives_str(self):
        result = decode_toon('"true"')
        assert result == "true"
        assert type(result) is str

    def test_decode_quoted_false_gives_str(self):
        result = decode_toon('"false"')
        assert result == "false"
        assert type(result) is str

    def test_decode_quoted_null_gives_str(self):
        result = decode_toon('"null"')
        assert result == "null"
        assert type(result) is str

    def test_decode_quoted_number_gives_str(self):
        result = decode_toon('"100.0"')
        assert result == "100.0"
        assert type(result) is str

    def test_decode_quoted_string(self):
        assert decode_toon('"hello"') == "hello"

    def test_decode_quoted_string_with_escape_sequences(self):
        assert decode_toon('"line1\\nline2"') == "line1\nline2"

    def test_decode_quoted_string_with_tab(self):
        assert decode_toon('"value1\\tvalue2"') == "value1\tvalue2"

    def test_decode_quoted_string_with_escaped_quote(self):
        assert decode_toon('"say \\"hello\\""') == 'say "hello"'

    # --- bare strings ---

    def test_decode_bare_word_gives_str(self):
        result = decode_toon("hello")
        assert result == "hello"
        assert type(result) is str


# ===========================================================================
# Section 3 — Round-trip oracle: decode_toon(encode_toon(x)) == x
# ===========================================================================


class TestToonRoundTrip:
    """Property oracle: encode then decode must recover the original Python value.

    Only tests shapes the encoder actually produces: scalars, strings,
    dicts with scalar/string values, flat lists.  The table format used for
    lists-of-dicts is not part of this PR's decoder scope — noted in comments
    where skipped.
    """

    def _rt(self, value):
        """Encode with ToonEncoder then decode; return reconstructed value."""
        enc = ToonEncoder(normalize_paths=False, use_tabs=False)
        encoded = enc.encode_value(value)
        return decode_toon(encoded)

    # --- None / bool ---

    def test_none_roundtrip(self):
        assert self._rt(None) is None

    def test_true_roundtrip(self):
        result = self._rt(True)
        assert result is True

    def test_false_roundtrip(self):
        result = self._rt(False)
        assert result is False

    # --- integers ---

    def test_zero_roundtrip(self):
        result = self._rt(0)
        assert result == 0
        assert type(result) is int

    def test_positive_int_roundtrip(self):
        result = self._rt(42)
        assert result == 42
        assert type(result) is int

    def test_negative_int_roundtrip(self):
        result = self._rt(-7)
        assert result == -7
        assert type(result) is int

    # --- floats ---

    def test_float_roundtrip(self):
        result = self._rt(3.14)
        assert result == 3.14
        assert type(result) is float

    def test_negative_float_roundtrip(self):
        result = self._rt(-1.5)
        assert result == -1.5
        assert type(result) is float

    # --- strings that look like scalars (the #1058 bug cases) ---

    def test_str_true_roundtrip(self):
        result = self._rt("true")
        assert result == "true"
        assert type(result) is str

    def test_str_false_roundtrip(self):
        result = self._rt("false")
        assert result == "false"
        assert type(result) is str

    def test_str_null_roundtrip(self):
        result = self._rt("null")
        assert result == "null"
        assert type(result) is str

    def test_str_integer_roundtrip(self):
        result = self._rt("42")
        assert result == "42"
        assert type(result) is str

    def test_str_float_roundtrip(self):
        """The exact #1058 case: "100.0" must round-trip as str, not float."""
        result = self._rt("100.0")
        assert result == "100.0"
        assert type(result) is str

    def test_str_negative_int_roundtrip(self):
        result = self._rt("-3")
        assert result == "-3"
        assert type(result) is str

    def test_str_scientific_roundtrip(self):
        result = self._rt("1e5")
        assert result == "1e5"
        assert type(result) is str

    # --- ordinary strings ---

    def test_ordinary_str_roundtrip(self):
        result = self._rt("hello")
        assert result == "hello"
        assert type(result) is str

    def test_str_with_spaces_roundtrip(self):
        """Strings with spaces pass through bare if no structural chars."""
        result = self._rt("hello world")
        assert result == "hello world"
        assert type(result) is str

    def test_str_with_special_chars_roundtrip(self):
        result = self._rt("say,hello")
        assert result == "say,hello"
        assert type(result) is str

    def test_str_with_newline_roundtrip(self):
        result = self._rt("line1\nline2")
        assert result == "line1\nline2"
        assert type(result) is str

    def test_str_with_colon_roundtrip(self):
        result = self._rt("key:value")
        assert result == "key:value"
        assert type(result) is str
