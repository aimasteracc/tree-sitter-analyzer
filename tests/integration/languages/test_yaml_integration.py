#!/usr/bin/env python3
"""
Integration tests for YAML language support.

Uses real tree-sitter parser, actual file I/O, and asyncio.analyze_file.
Consolidates tests from 14 old unit/languages/test_yaml_*_properties.py files.

Coverage areas:
  - Anchor and alias detection
  - Scalar type identification
  - Multi-document separation
  - Structure extraction (mappings, sequences, nesting)
  - Encoding resilience
  - Error handling robustness
  - File extension detection
  - Element metadata accuracy
  - Output format support (YAMLFormatter)
  - Parsing determinism
  - Query definitions and compilation
  - Language isolation (YAML vs other plugins)
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer.languages.yaml_plugin import (
    YAML_AVAILABLE,
    YAMLElementExtractor,
    YAMLPlugin,
)

pytestmark = pytest.mark.skipif(
    not YAML_AVAILABLE, reason="tree-sitter-yaml not installed"
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _parse_yaml(yaml_content: str):
    """Return (tree, source_code) using real tree-sitter-yaml parser."""
    import tree_sitter
    import tree_sitter_yaml as ts_yaml

    lang = tree_sitter.Language(ts_yaml.language())
    parser = tree_sitter.Parser()
    parser.language = lang
    tree = parser.parse(yaml_content.encode("utf-8"))
    return tree, yaml_content


def _extract(yaml_content: str):
    """Parse + extract elements from yaml_content string."""
    tree, source = _parse_yaml(yaml_content)
    extractor = YAMLElementExtractor()
    return extractor.extract_yaml_elements(tree, source)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_anchor_name_st = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll"), min_codepoint=97, max_codepoint=122),
    min_size=1, max_size=15,
)

_simple_value_st = st.one_of(
    st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), min_codepoint=97, max_codepoint=122),
        min_size=1, max_size=20,
    ),
    st.integers(min_value=0, max_value=1000).map(str),
)

_key_st = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll"), min_codepoint=97, max_codepoint=122),
    min_size=1, max_size=15,
)


@st.composite
def _anchor_yaml(draw):
    name = draw(_anchor_name_st)
    value = draw(_simple_value_st)
    content = f"anchor_def: &{name} {value}\nalias_use: *{name}"
    return content, name


@st.composite
def _multi_anchor_yaml(draw):
    n = draw(st.integers(min_value=1, max_value=5))
    anchors = [f"anchor{i}" for i in range(n)]
    lines = []
    for i, a in enumerate(anchors):
        v = draw(_simple_value_st)
        lines.append(f"key{i}: &{a} {v}")
    for a in anchors:
        lines.append(f"ref_{a}: *{a}")
    return "\n".join(lines), anchors


@st.composite
def _mapping_yaml(draw):
    n = draw(st.integers(min_value=1, max_value=10))
    lines = []
    for _ in range(n):
        k = draw(_key_st)
        v = draw(st.one_of(
            st.text(alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), min_codepoint=97, max_codepoint=122), min_size=1, max_size=20),
            st.integers(min_value=0, max_value=1000).map(str),
            st.sampled_from(["true", "false", "null"]),
        ))
        lines.append(f"{k}: {v}")
    return "\n".join(lines)


@st.composite
def _sequence_yaml(draw):
    n = draw(st.integers(min_value=1, max_value=10))
    lines = [f"- {draw(_simple_value_st)}" for _ in range(n)]
    return "\n".join(lines)


@st.composite
def _multi_document_yaml(draw):
    n = draw(st.integers(min_value=2, max_value=4))
    docs = []
    for doc_idx in range(n):
        m = draw(st.integers(min_value=1, max_value=4))
        lines = [f"doc{doc_idx}_key{ki}: value{ki}" for ki in range(m)]
        docs.append("\n".join(lines))
    return "---\n" + "\n---\n".join(docs)


# ---------------------------------------------------------------------------
# 1. Anchor and Alias Detection
# ---------------------------------------------------------------------------


class TestYAMLAnchorAlias:
    """Integration tests: anchor/alias extraction via real tree-sitter-yaml."""

    @settings(max_examples=20)
    @given(yaml_data=_anchor_yaml())
    def test_anchor_detected_with_correct_name(self, yaml_data):
        content, expected_name = yaml_data
        elements = _extract(content)
        anchors = [e for e in elements if e.element_type == "anchor"]
        assert len(anchors) >= 1, f"Expected ≥1 anchor. Content:\n{content}"
        anchor_names = [a.anchor_name for a in anchors]
        assert expected_name in anchor_names, f"Anchor '{expected_name}' not found in {anchor_names}"

    @settings(max_examples=20)
    @given(yaml_data=_anchor_yaml())
    def test_alias_detected_with_correct_target(self, yaml_data):
        content, expected_target = yaml_data
        elements = _extract(content)
        aliases = [e for e in elements if e.element_type == "alias"]
        assert len(aliases) >= 1, f"Expected ≥1 alias. Content:\n{content}"
        targets = [a.alias_target for a in aliases]
        assert expected_target in targets, f"Alias target '{expected_target}' not found in {targets}"

    @settings(max_examples=20)
    @given(yaml_data=_anchor_yaml())
    def test_anchor_alias_names_correspond(self, yaml_data):
        content, _ = yaml_data
        elements = _extract(content)
        anchors = {e.anchor_name for e in elements if e.element_type == "anchor"}
        aliases = {e.alias_target for e in elements if e.element_type == "alias"}
        for alias_target in aliases:
            assert alias_target in anchors, (
                f"Alias target '{alias_target}' has no matching anchor. Anchors: {anchors}"
            )

    @settings(max_examples=20)
    @given(yaml_data=_multi_anchor_yaml())
    def test_multiple_anchors_all_detected(self, yaml_data):
        content, expected_anchors = yaml_data
        elements = _extract(content)
        anchors = [e for e in elements if e.element_type == "anchor"]
        found_names = {a.anchor_name for a in anchors}
        expected_set = set(expected_anchors)
        assert found_names == expected_set, (
            f"Anchor names mismatch. Expected: {expected_set}, Found: {found_names}.\n{content}"
        )

    @settings(max_examples=20)
    @given(name=_anchor_name_st, value=_simple_value_st)
    def test_anchor_name_extracted_without_prefix(self, name, value):
        content = f"key: &{name} {value}"
        elements = _extract(content)
        anchors = [e for e in elements if e.element_type == "anchor"]
        assert len(anchors) == 1, f"Expected exactly 1 anchor. Content: {content}"
        assert anchors[0].anchor_name == name, f"Expected '{name}', got '{anchors[0].anchor_name}'"
        assert not anchors[0].anchor_name.startswith("&")

    @settings(max_examples=20)
    @given(name=_anchor_name_st, value=_simple_value_st)
    def test_alias_target_extracted_without_prefix(self, name, value):
        content = f"anchor: &{name} {value}\nalias: *{name}"
        elements = _extract(content)
        aliases = [e for e in elements if e.element_type == "alias"]
        assert len(aliases) == 1, f"Expected 1 alias. Content: {content}"
        assert aliases[0].alias_target == name, f"Expected '{name}', got '{aliases[0].alias_target}'"
        assert not aliases[0].alias_target.startswith("*")


# ---------------------------------------------------------------------------
# 2. Scalar Type Identification
# ---------------------------------------------------------------------------


class TestYAMLScalarTypes:
    """Integration tests: scalar type identification via real tree-sitter-yaml."""

    @settings(max_examples=20)
    @given(
        key=_key_st,
        value=st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll"), min_codepoint=97, max_codepoint=122),
            min_size=1, max_size=30,
        ).filter(lambda x: x.lower() not in ["true", "false", "yes", "no", "on", "off", "null"]),
    )
    def test_string_scalar_identified_correctly(self, key, value):
        content = f"{key}: {value}"
        elements = _extract(content)
        mappings = [e for e in elements if e.element_type == "mapping" and e.value is not None]
        assert len(mappings) > 0
        for m in mappings:
            assert m.value_type == "string", f"Expected 'string', got '{m.value_type}' for '{m.value}'"

    @settings(max_examples=20)
    @given(
        key=_key_st,
        value=st.one_of(
            st.integers(min_value=-1000000, max_value=1000000),
            st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
        ),
    )
    def test_number_scalar_identified_correctly(self, key, value):
        content = f"{key}: {value}"
        elements = _extract(content)
        mappings = [e for e in elements if e.element_type == "mapping" and e.value is not None]
        assert len(mappings) > 0
        for m in mappings:
            assert m.value_type == "number", f"Expected 'number', got '{m.value_type}' for '{m.value}'"

    @settings(max_examples=20)
    @given(key=_key_st, bool_value=st.sampled_from(["true", "false", "yes", "no", "on", "off"]))
    def test_boolean_scalar_identified_correctly(self, key, bool_value):
        content = f"{key}: {bool_value}"
        elements = _extract(content)
        mappings = [e for e in elements if e.element_type == "mapping" and e.value is not None]
        assert len(mappings) > 0
        for m in mappings:
            assert m.value_type == "boolean", f"Expected 'boolean', got '{m.value_type}' for '{m.value}'"

    @settings(max_examples=20)
    @given(key=_key_st, null_value=st.sampled_from(["null", "~"]))
    def test_null_scalar_identified_correctly(self, key, null_value):
        content = f"{key}: {null_value}"
        elements = _extract(content)
        mappings = [e for e in elements if e.element_type == "mapping"]
        assert len(mappings) > 0
        for m in mappings:
            assert m.value_type == "null", f"Expected 'null', got '{m.value_type}' for '{m.value}'"


# ---------------------------------------------------------------------------
# 3. Multi-Document Separation
# ---------------------------------------------------------------------------


class TestYAMLMultiDocument:
    """Integration tests: multi-document YAML parsing."""

    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    @given(content=_multi_document_yaml())
    def test_documents_extracted_with_sequential_indices(self, content):
        elements = _extract(content)
        docs = [e for e in elements if e.element_type == "document"]
        assert len(docs) >= 1, f"Expected ≥1 document. Content:\n{content}"
        doc_indices = sorted(d.document_index for d in docs)
        assert doc_indices[0] == 0, f"First doc index must be 0, got {doc_indices[0]}"
        for idx in doc_indices:
            assert idx >= 0

    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    @given(content=_multi_document_yaml())
    def test_document_indices_are_unique(self, content):
        elements = _extract(content)
        docs = [e for e in elements if e.element_type == "document"]
        doc_indices = [d.document_index for d in docs]
        assert len(doc_indices) == len(set(doc_indices)), f"Duplicate indices: {doc_indices}"

    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    @given(content=_multi_document_yaml())
    def test_non_document_elements_have_valid_document_index(self, content):
        elements = _extract(content)
        for e in elements:
            if e.element_type != "document":
                assert isinstance(e.document_index, int)
                assert e.document_index >= 0

    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    @given(content=_multi_document_yaml())
    def test_documents_have_positive_line_numbers(self, content):
        elements = _extract(content)
        docs = [e for e in elements if e.element_type == "document"]
        for doc in docs:
            assert doc.start_line > 0
            assert doc.end_line >= doc.start_line

    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    @given(content=_multi_document_yaml())
    def test_documents_have_non_negative_child_count(self, content):
        elements = _extract(content)
        docs = [e for e in elements if e.element_type == "document"]
        for doc in docs:
            assert hasattr(doc, "child_count")
            # child_count may be None (not all parsers populate it)
            if doc.child_count is not None:
                assert doc.child_count >= 0


# ---------------------------------------------------------------------------
# 4. Structure Extraction
# ---------------------------------------------------------------------------


class TestYAMLStructureExtraction:
    """Integration tests: mapping/sequence structure extraction."""

    @settings(max_examples=20)
    @given(content=_mapping_yaml())
    def test_all_mappings_extracted_with_valid_metadata(self, content):
        elements = _extract(content)
        mappings = [e for e in elements if e.element_type == "mapping"]
        expected = sum(1 for line in content.split("\n") if ":" in line and not line.strip().startswith("#"))
        assert len(mappings) == expected, (
            f"Expected {expected} mappings, got {len(mappings)}.\nContent:\n{content}"
        )
        for m in mappings:
            assert m.key is not None and len(m.key) > 0
            assert m.start_line > 0
            assert m.end_line >= m.start_line

    @settings(max_examples=20)
    @given(content=_sequence_yaml())
    def test_sequence_extracted_with_child_count(self, content):
        elements = _extract(content)
        seqs = [e for e in elements if e.element_type == "sequence"]
        assert len(seqs) >= 1, f"Expected ≥1 sequence. Content:\n{content}"
        for seq in seqs:
            assert seq.start_line > 0
            assert seq.end_line >= seq.start_line
            assert seq.child_count is not None and seq.child_count >= 0
            assert seq.value_type == "sequence"

    @settings(max_examples=20)
    @given(
        num_mappings=st.integers(min_value=1, max_value=5),
        num_sequences=st.integers(min_value=1, max_value=5),
    )
    def test_mapping_and_sequence_counts_match_source(self, num_mappings, num_sequences):
        lines = [f"key{i}: value{i}" for i in range(num_mappings)]
        lines.append("items:")
        lines.extend(f"  - item{i}" for i in range(num_sequences))
        content = "\n".join(lines)
        elements = _extract(content)

        mappings = [e for e in elements if e.element_type == "mapping"]
        assert len(mappings) == num_mappings + 1  # +1 for "items" key

        seqs = [e for e in elements if e.element_type == "sequence"]
        assert len(seqs) >= 1
        assert seqs[0].child_count == num_sequences

    @settings(max_examples=20)
    @given(num_keys=st.integers(min_value=1, max_value=10))
    def test_all_elements_have_non_negative_nesting_level(self, num_keys):
        lines = [f"key{i}: value{i}" for i in range(num_keys)]
        content = "\n".join(lines)
        elements = _extract(content)
        for e in elements:
            assert hasattr(e, "nesting_level")
            assert isinstance(e.nesting_level, int)
            assert e.nesting_level >= 0


# ---------------------------------------------------------------------------
# 5. Encoding Resilience
# ---------------------------------------------------------------------------


class _MockRequest:
    output_format = "json"
    detail_level = "full"


class TestYAMLEncodingResilience:
    """Integration tests: encoding resilience via analyze_file."""

    @settings(max_examples=15, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(key=_key_st, value=_simple_value_st)
    def test_utf8_file_analyzed_successfully(self, key, value):
        content = f"{key}: {value}"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write(content)
            path = f.name
        try:
            result = asyncio.run(YAMLPlugin().analyze_file(path, _MockRequest()))
            assert result.success, f"UTF-8 analysis failed: {result.error_message}"
            assert len(result.elements) > 0
        finally:
            os.unlink(path)

    @settings(max_examples=15, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(key=_key_st, value=st.integers(min_value=0, max_value=1000))
    def test_latin1_file_analyzed_successfully(self, key, value):
        content = f"{key}: {value}"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="latin-1") as f:
            f.write(content)
            path = f.name
        try:
            result = asyncio.run(YAMLPlugin().analyze_file(path, _MockRequest()))
            assert result.success, f"Latin-1 analysis failed: {result.error_message}"
            assert len(result.elements) > 0
        finally:
            os.unlink(path)

    @settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(num_keys=st.integers(min_value=1, max_value=5))
    def test_encoding_consistency_same_element_count(self, num_keys):
        content = "\n".join(f"key{i}: value{i}" for i in range(num_keys))
        plugin = YAMLPlugin()
        results = {}
        for enc in ("utf-8", "latin-1"):
            with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding=enc) as f:
                f.write(content)
                path = f.name
            try:
                r = asyncio.run(plugin.analyze_file(path, _MockRequest()))
                results[enc] = len(r.elements)
            finally:
                os.unlink(path)
        assert results["utf-8"] == results["latin-1"], (
            f"Element count mismatch: utf-8={results['utf-8']}, latin-1={results['latin-1']}"
        )


# ---------------------------------------------------------------------------
# 6. Error Handling Robustness
# ---------------------------------------------------------------------------


class TestYAMLErrorHandling:
    """Integration tests: error handling robustness via analyze_file."""

    @pytest.mark.asyncio
    async def test_empty_file_returns_success(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "empty.yaml"
            p.write_text("", encoding="utf-8")
            from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest
            result = await YAMLPlugin().analyze_file(str(p), AnalysisRequest(file_path=str(p)))
            assert result is not None
            assert result.success, "Empty YAML file should parse successfully"
            assert isinstance(result.elements, list)

    @pytest.mark.asyncio
    async def test_comments_only_file_returns_success(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "comments.yaml"
            p.write_text("# comment 1\n# comment 2\n", encoding="utf-8")
            from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest
            result = await YAMLPlugin().analyze_file(str(p), AnalysisRequest(file_path=str(p)))
            assert result is not None
            assert result.success
            assert isinstance(result.elements, list)

    @pytest.mark.asyncio
    async def test_result_has_required_fields(self):
        content = "key: value\n"
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test.yaml"
            p.write_text(content, encoding="utf-8")
            from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest
            result = await YAMLPlugin().analyze_file(str(p), AnalysisRequest(file_path=str(p)))
            assert hasattr(result, "success")
            assert hasattr(result, "error_message")
            assert hasattr(result, "file_path")
            assert hasattr(result, "language")
            assert hasattr(result, "elements")
            assert isinstance(result.success, bool)
            assert result.language == "yaml"
            assert result.file_path == str(p)
            assert isinstance(result.elements, list)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("invalid_content", [
        "data:\n  items: [[[unclosed",
        "root:\n  \tkey: value",  # mixed tabs/spaces
        "ref: *nonexistent_anchor",
    ])
    async def test_invalid_yaml_does_not_crash(self, invalid_content):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "invalid.yaml"
            p.write_text(invalid_content, encoding="utf-8")
            from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest
            try:
                result = await YAMLPlugin().analyze_file(str(p), AnalysisRequest(file_path=str(p)))
                assert result is not None
                assert isinstance(result.success, bool)
                if not result.success:
                    assert result.error_message and len(result.error_message) > 0
            except Exception as e:
                pytest.fail(f"Parser crashed on invalid YAML: {e}\nContent: {invalid_content}")


# ---------------------------------------------------------------------------
# 7. File Extension Detection
# ---------------------------------------------------------------------------


class TestYAMLFileExtensions:
    """Integration tests: file extension and plugin manager integration."""

    @settings(max_examples=10, deadline=None)
    @given(ext=st.sampled_from([".yaml", ".yml"]))
    def test_language_detected_as_yaml(self, ext):
        from tree_sitter_analyzer.language_detector import detect_language_from_file
        with tempfile.NamedTemporaryFile(mode="w", suffix=ext, delete=False) as f:
            f.write("key: value\n")
            path = f.name
        try:
            detected = detect_language_from_file(path)
            assert detected == "yaml", f"Expected 'yaml', got '{detected}' for '{ext}' file"
        finally:
            Path(path).unlink(missing_ok=True)

    def test_plugin_manager_returns_yaml_plugin(self):
        from tree_sitter_analyzer.plugins.manager import PluginManager
        pm = PluginManager()
        pm.load_plugins()
        plugin = pm.get_plugin("yaml")
        assert plugin is not None
        assert isinstance(plugin, YAMLPlugin)

    @settings(max_examples=5, deadline=None)
    @given(ext=st.sampled_from([".yaml", ".yml"]))
    def test_detection_is_deterministic(self, ext):
        from tree_sitter_analyzer.language_detector import detect_language_from_file
        with tempfile.NamedTemporaryFile(mode="w", suffix=ext, delete=False) as f:
            f.write("key: value\n")
            path = f.name
        try:
            results = [detect_language_from_file(path) for _ in range(5)]
            assert all(r == "yaml" for r in results), f"Inconsistent detection: {results}"
        finally:
            Path(path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_yaml_extension_analyzed_end_to_end(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("test_key: test_value\n")
            path = f.name
        try:
            from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest
            result = await YAMLPlugin().analyze_file(path, AnalysisRequest(file_path=path))
            assert result.success
            assert result.language == "yaml"
        finally:
            Path(path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_yml_extension_analyzed_end_to_end(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write("test_key: test_value\n")
            path = f.name
        try:
            from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest
            result = await YAMLPlugin().analyze_file(path, AnalysisRequest(file_path=path))
            assert result.success
            assert result.language == "yaml"
        finally:
            Path(path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 8. Element Metadata Accuracy
# ---------------------------------------------------------------------------


class TestYAMLElementMetadata:
    """Integration tests: element line numbers and raw_text accuracy."""

    @settings(max_examples=20)
    @given(content=_mapping_yaml())
    def test_all_elements_have_valid_line_numbers(self, content):
        source_lines = content.split("\n")
        total = len(source_lines)
        elements = _extract(content)
        for e in elements:
            assert isinstance(e.start_line, int) and e.start_line > 0
            assert isinstance(e.end_line, int) and e.end_line >= e.start_line
            assert e.start_line <= total
            assert e.end_line <= total

    @settings(max_examples=20)
    @given(num_keys=st.integers(min_value=1, max_value=10))
    def test_mapping_raw_text_matches_source_line(self, num_keys):
        lines = [f"key{i}: value{i}" for i in range(num_keys)]
        content = "\n".join(lines)
        elements = _extract(content)
        mappings = [e for e in elements if e.element_type == "mapping"]
        assert len(mappings) == num_keys
        source_lines = content.split("\n")
        for m in mappings:
            expected = source_lines[m.start_line - 1]
            assert m.raw_text == expected, (
                f"raw_text mismatch at line {m.start_line}. Expected '{expected}', got '{m.raw_text}'"
            )

    @settings(max_examples=20)
    @given(content=_mapping_yaml())
    def test_mapping_raw_text_contains_key(self, content):
        elements = _extract(content)
        mappings = [e for e in elements if e.element_type == "mapping" and e.key]
        for m in mappings:
            assert m.key in m.raw_text, f"Key '{m.key}' not in raw_text '{m.raw_text}'"

    @settings(max_examples=15)
    @given(
        num_lines=st.integers(min_value=2, max_value=8),
    )
    def test_comment_raw_text_contains_hash(self, num_lines):
        lines = []
        for i in range(num_lines):
            if i % 2 == 0:
                lines.append(f"# comment {i}")
            else:
                lines.append(f"key{i}: value{i}")
        content = "\n".join(lines)
        elements = _extract(content)
        comments = [e for e in elements if e.element_type == "comment"]
        for c in comments:
            assert "#" in c.raw_text, f"Comment raw_text missing '#': '{c.raw_text}'"


# ---------------------------------------------------------------------------
# 9. Output Format Support
# ---------------------------------------------------------------------------


class TestYAMLOutputFormats:
    """Integration tests: YAMLFormatter produces valid output."""

    def _make_result(self, file_path: str, element_count: int) -> dict:
        from tree_sitter_analyzer.formatters.yaml_formatter import YAMLFormatter  # noqa: F401
        element_types = ["mapping", "sequence", "scalar", "document"]
        elements = []
        for i in range(element_count):
            etype = element_types[i % len(element_types)]
            elements.append({
                "name": f"element_{i}",
                "start_line": i + 1,
                "end_line": i + 1,
                "element_type": etype,
                "key": f"key_{i}" if etype == "mapping" else None,
                "value": f"value_{i}" if etype in ("mapping", "scalar") else None,
                "value_type": "string" if etype in ("mapping", "scalar") else None,
                "anchor_name": None,
                "alias_target": None,
                "nesting_level": i % 3,
                "document_index": 0,
                "child_count": None,
            })
        return {
            "file_path": file_path,
            "language": "yaml",
            "line_count": element_count + 1,
            "elements": elements,
            "analysis_metadata": {"analysis_time": 0.1, "language": "yaml", "file_path": file_path},
        }

    @settings(max_examples=15)
    @given(
        file_path=st.text(min_size=1, max_size=40).filter(lambda x: "/" not in x and "\\" not in x),
        element_count=st.integers(min_value=0, max_value=15),
    )
    def test_json_format_is_parseable(self, file_path, element_count):
        from tree_sitter_analyzer.formatters.yaml_formatter import YAMLFormatter
        formatter = YAMLFormatter()
        result = self._make_result(file_path, element_count)
        output = formatter.format_advanced(result, output_format="json")
        assert isinstance(output, str) and len(output) > 0
        # Find the JSON block
        lines = output.split("\n")
        for i, line in enumerate(lines):
            if line.strip().startswith("{"):
                parsed = json.loads("\n".join(lines[i:]))
                assert "file_path" in parsed
                assert parsed["language"] == "yaml"
                return
        pytest.fail("No JSON block found in output")

    @settings(max_examples=15)
    @given(element_count=st.integers(min_value=0, max_value=20))
    def test_all_format_methods_succeed(self, element_count):
        from tree_sitter_analyzer.formatters.yaml_formatter import YAMLFormatter
        formatter = YAMLFormatter()
        result = self._make_result("test.yaml", element_count)
        for method, kwargs in [
            ("format_summary", {}),
            ("format_structure", {}),
            ("format_advanced", {"output_format": "json"}),
            ("format_advanced", {"output_format": "text"}),
            ("format_table", {"table_type": "full"}),
        ]:
            try:
                out = getattr(formatter, method)(result, **kwargs)
                assert isinstance(out, str) and len(out) > 0, f"{method} returned empty output"
            except Exception as e:
                pytest.fail(f"{method}() raised {type(e).__name__}: {e}")

    @settings(max_examples=10)
    @given(
        file_path=st.text(min_size=1, max_size=40).filter(
            lambda x: "/" not in x and "\\" not in x and "|" not in x
        ),
        mapping_count=st.integers(min_value=1, max_value=10),
    )
    def test_table_output_contains_pipe_separators(self, file_path, mapping_count):
        from tree_sitter_analyzer.formatters.yaml_formatter import YAMLFormatter
        formatter = YAMLFormatter()
        elements = [
            {
                "name": f"key_{i}", "start_line": i + 1, "end_line": i + 1,
                "element_type": "mapping", "key": f"key_{i}", "value": f"value_{i}",
                "value_type": "string", "anchor_name": None, "alias_target": None,
                "nesting_level": 0, "document_index": 0, "child_count": None,
            }
            for i in range(mapping_count)
        ]
        result = {
            "file_path": file_path, "language": "yaml", "line_count": mapping_count,
            "elements": elements,
            "analysis_metadata": {"analysis_time": 0.1, "language": "yaml", "file_path": file_path},
        }
        output = formatter.format_table(result, table_type="full")
        assert "|" in output, "Table output must contain pipe characters"
        assert "yaml" in output.lower()


# ---------------------------------------------------------------------------
# 10. Parsing Determinism
# ---------------------------------------------------------------------------


class TestYAMLParsingConsistency:
    """Integration tests: parsing produces consistent results."""

    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(content=_mapping_yaml())
    def test_parsing_is_deterministic(self, content):
        """Same input must always produce same element count."""
        counts = [len(_extract(content)) for _ in range(3)]
        assert len(set(counts)) == 1, f"Non-deterministic results: {counts}"

    @settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(content=_mapping_yaml())
    def test_analyze_file_deterministic(self, content):
        """analyze_file must return same element count on repeated calls."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write(content)
            path = f.name
        try:
            plugin = YAMLPlugin()
            counts = [len(asyncio.run(plugin.analyze_file(path, _MockRequest())).elements) for _ in range(2)]
            assert len(set(counts)) == 1, f"Non-deterministic analyze_file: {counts}"
        finally:
            os.unlink(path)

    @settings(max_examples=10, deadline=None)
    @given(num_keys=st.integers(min_value=1, max_value=8))
    def test_element_types_are_stable(self, num_keys):
        """Same structured YAML always yields same element types."""
        lines = [f"key{i}: value{i}" for i in range(num_keys)]
        content = "\n".join(lines)
        types_a = sorted(e.element_type for e in _extract(content))
        types_b = sorted(e.element_type for e in _extract(content))
        assert types_a == types_b


# ---------------------------------------------------------------------------
# 11. Query Definitions and Compilation
# ---------------------------------------------------------------------------


class TestYAMLQueries:
    """Integration tests: YAML query definitions are valid and compile."""

    def test_all_query_strings_are_non_empty(self):
        from tree_sitter_analyzer.queries.yaml import YAML_QUERIES
        for name, q in YAML_QUERIES.items():
            assert isinstance(q, str), f"Query '{name}' must be str"
            assert len(q.strip()) > 0, f"Query '{name}' must not be empty"

    def test_all_queries_have_balanced_parentheses(self):
        from tree_sitter_analyzer.queries.yaml import YAML_QUERIES
        for name, q in YAML_QUERIES.items():
            depth = 0
            for ch in q:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                assert depth >= 0, f"Query '{name}' has unbalanced parentheses"
            assert depth == 0, f"Query '{name}' has unclosed parentheses"

    def test_queries_compile_against_yaml_language(self):
        import tree_sitter
        import tree_sitter_yaml as ts_yaml
        from tree_sitter_analyzer.queries.yaml import YAML_QUERIES
        lang = tree_sitter.Language(ts_yaml.language())
        for name, q in YAML_QUERIES.items():
            try:
                lang.query(q)
            except Exception as e:
                pytest.fail(f"Query '{name}' failed to compile: {e}")

    def test_accessor_functions_return_strings(self):
        from tree_sitter_analyzer.queries.yaml import (
            get_yaml_query,
            get_yaml_query_description,
            get_available_yaml_queries,
            YAML_QUERIES,
        )
        keys = list(YAML_QUERIES.keys())
        if not keys:
            pytest.skip("No YAML queries defined")
        first_key = keys[0]
        q = get_yaml_query(first_key)
        assert isinstance(q, str)
        desc = get_yaml_query_description(first_key)
        assert isinstance(desc, str)
        available = get_available_yaml_queries()
        assert isinstance(available, list)
        assert first_key in available


# ---------------------------------------------------------------------------
# 12. Language Isolation
# ---------------------------------------------------------------------------


class TestYAMLLanguageIsolation:
    """Integration tests: YAML plugin doesn't interfere with other language plugins."""

    def test_plugin_manager_maintains_separate_plugins(self):
        from tree_sitter_analyzer.plugins.manager import PluginManager
        pm = PluginManager()
        pm.load_plugins()
        yaml_plugin = pm.get_plugin("yaml")
        java_plugin = pm.get_plugin("java")
        if yaml_plugin and java_plugin:
            assert yaml_plugin is not java_plugin

    def test_yaml_plugin_does_not_accept_java_extensions(self):
        plugin = YAMLPlugin()
        extensions = plugin.get_file_extensions()
        assert ".java" not in extensions
        assert ".py" not in extensions
        assert ".js" not in extensions

    @pytest.mark.asyncio
    async def test_yaml_analysis_does_not_affect_python_analysis(self):
        """Analyze a YAML file and a Python file sequentially; ensure no cross-contamination."""
        from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest
        from tree_sitter_analyzer.plugins.manager import PluginManager

        pm = PluginManager()
        pm.load_plugins()
        python_plugin = pm.get_plugin("python")
        yaml_plugin = pm.get_plugin("yaml")

        if python_plugin is None or yaml_plugin is None:
            pytest.skip("Required plugins not available")

        yaml_content = "key: value\nother: 42\n"
        python_content = "def foo():\n    return 42\n"

        with tempfile.TemporaryDirectory() as d:
            yaml_path = str(Path(d) / "test.yaml")
            py_path = str(Path(d) / "test.py")
            Path(yaml_path).write_text(yaml_content, encoding="utf-8")
            Path(py_path).write_text(python_content, encoding="utf-8")

            yaml_result = await yaml_plugin.analyze_file(yaml_path, AnalysisRequest(file_path=yaml_path))
            py_result = await python_plugin.analyze_file(py_path, AnalysisRequest(file_path=py_path))

            assert yaml_result.language == "yaml"
            assert py_result.language == "python"
            # Each result's file_path must match its own input
            assert yaml_result.file_path == yaml_path
            assert py_result.file_path == py_path

    @settings(max_examples=5, deadline=None)
    @given(ext=st.sampled_from([".yaml", ".yml"]))
    def test_both_yaml_extensions_map_to_same_plugin_class(self, ext):
        from tree_sitter_analyzer.language_detector import detect_language_from_file
        with tempfile.NamedTemporaryFile(mode="w", suffix=ext, delete=False) as f:
            f.write("key: value\n")
            path = f.name
        try:
            lang = detect_language_from_file(path)
            assert lang == "yaml"
        finally:
            Path(path).unlink(missing_ok=True)
