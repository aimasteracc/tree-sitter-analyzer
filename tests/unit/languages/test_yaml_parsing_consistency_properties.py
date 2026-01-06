#!/usr/bin/env python3
"""
Property-based tests for YAML parsing consistency.

Feature: yaml-language-support
Tests correctness properties for YAML parsing to ensure:
- Parsing produces consistent results across multiple invocations
- Same input always produces same output
- Parsing is deterministic and stable
"""

import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest
from tree_sitter_analyzer.languages.yaml_plugin import YAML_AVAILABLE, YAMLPlugin

# Skip all tests if YAML is not available
pytestmark = pytest.mark.skipif(
    not YAML_AVAILABLE, reason="tree-sitter-yaml not installed"
)


# Strategies for generating valid YAML content
@st.composite
def simple_yaml_content(draw):
    """Generate simple valid YAML content."""
    num_keys = draw(st.integers(min_value=1, max_value=10))
    lines = []
    for _i in range(num_keys):
        key = draw(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"),
                    min_codepoint=97,
                    max_codepoint=122,
                ),
                min_size=1,
                max_size=20,
            )
        )
        value = draw(
            st.one_of(
                st.text(
                    alphabet=st.characters(
                        whitelist_categories=("Lu", "Ll", "Nd"),
                        min_codepoint=97,
                        max_codepoint=122,
                    ),
                    min_size=1,
                    max_size=20,
                ),
                st.integers(min_value=0, max_value=1000).map(str),
                st.sampled_from(["true", "false", "null"]),
            )
        )
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


@st.composite
def yaml_with_sequences(draw):
    """Generate YAML content with sequences."""
    num_items = draw(st.integers(min_value=1, max_value=8))
    lines = ["items:"]
    for _i in range(num_items):
        item = draw(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"),
                    min_codepoint=97,
                    max_codepoint=122,
                ),
                min_size=1,
                max_size=15,
            )
        )
        lines.append(f"  - {item}")
    return "\n".join(lines)


@st.composite
def yaml_with_nested_structures(draw):
    """Generate YAML content with nested structures."""
    parent_key = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"),
                min_codepoint=97,
                max_codepoint=122,
            ),
            min_size=1,
            max_size=15,
        )
    )

    num_children = draw(st.integers(min_value=1, max_value=5))
    lines = [f"{parent_key}:"]

    for _i in range(num_children):
        child_key = draw(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"),
                    min_codepoint=97,
                    max_codepoint=122,
                ),
                min_size=1,
                max_size=15,
            )
        )
        child_value = draw(
            st.one_of(
                st.text(
                    alphabet=st.characters(
                        whitelist_categories=("Lu", "Ll", "Nd"),
                        min_codepoint=97,
                        max_codepoint=122,
                    ),
                    min_size=1,
                    max_size=15,
                ),
                st.integers(min_value=0, max_value=100).map(str),
            )
        )
        lines.append(f"  {child_key}: {child_value}")

    return "\n".join(lines)


@st.composite
def yaml_with_comments(draw):
    """Generate YAML content with comments."""
    num_keys = draw(st.integers(min_value=1, max_value=5))
    lines = ["# Configuration file"]

    for _i in range(num_keys):
        key = draw(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"),
                    min_codepoint=97,
                    max_codepoint=122,
                ),
                min_size=1,
                max_size=15,
            )
        )
        value = draw(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"),
                    min_codepoint=97,
                    max_codepoint=122,
                ),
                min_size=1,
                max_size=15,
            )
        )
        lines.append(f"# Comment for {key}")
        lines.append(f"{key}: {value}")

    return "\n".join(lines)


@st.composite
def yaml_with_multi_documents(draw):
    """Generate YAML content with multiple documents."""
    num_docs = draw(st.integers(min_value=2, max_value=4))
    documents = []

    for _doc_idx in range(num_docs):
        num_keys = draw(st.integers(min_value=1, max_value=3))
        lines = ["---"]

        for _i in range(num_keys):
            key = draw(
                st.text(
                    alphabet=st.characters(
                        whitelist_categories=("Lu", "Ll", "Nd"),
                        min_codepoint=97,
                        max_codepoint=122,
                    ),
                    min_size=1,
                    max_size=15,
                )
            )
            value = draw(
                st.text(
                    alphabet=st.characters(
                        whitelist_categories=("Lu", "Ll", "Nd"),
                        min_codepoint=97,
                        max_codepoint=122,
                    ),
                    min_size=1,
                    max_size=15,
                )
            )
            lines.append(f"{key}: {value}")

        documents.append("\n".join(lines))

    return "\n".join(documents)


class TestYAMLParsingConsistencyProperties:
    """Property-based tests for YAML parsing consistency."""

    @pytest.mark.asyncio
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
        ],
    )
    @given(yaml_content=simple_yaml_content())
    async def test_property_1_parsing_round_trip_consistency_simple(
        self, yaml_content: str
    ):
        """
        Feature: yaml-language-support, Property 1: Parsing Round-Trip Consistency

        For any valid YAML content with simple mappings, parsing SHALL produce
        consistent results across multiple invocations.

        Validates: Requirements 1.1
        """
        # Create temporary YAML file
        with tempfile.TemporaryDirectory() as tmp_dir:
            yaml_file = Path(tmp_dir) / "test.yaml"
            yaml_file.write_text(yaml_content, encoding="utf-8")

            plugin = YAMLPlugin()
            request = AnalysisRequest(file_path=str(yaml_file))

            # Parse the file multiple times
            result1 = await plugin.analyze_file(str(yaml_file), request)
            result2 = await plugin.analyze_file(str(yaml_file), request)
            result3 = await plugin.analyze_file(str(yaml_file), request)

            # Property: All parsing attempts must succeed
            assert result1.success, f"First parse failed: {result1.error}"
            assert result2.success, f"Second parse failed: {result2.error}"
            assert result3.success, f"Third parse failed: {result3.error}"

            # Property: Number of elements must be consistent
            assert len(result1.elements) == len(result2.elements), (
                f"Element count mismatch between parse 1 ({len(result1.elements)}) "
                f"and parse 2 ({len(result2.elements)})"
            )
            assert len(result1.elements) == len(result3.elements), (
                f"Element count mismatch between parse 1 ({len(result1.elements)}) "
                f"and parse 3 ({len(result3.elements)})"
            )

            # Property: Element types must be consistent
            types1 = [e.element_type for e in result1.elements]
            types2 = [e.element_type for e in result2.elements]
            types3 = [e.element_type for e in result3.elements]

            assert types1 == types2, (
                f"Element types mismatch between parse 1 and 2.\n"
                f"Parse 1: {types1}\nParse 2: {types2}"
            )
            assert types1 == types3, (
                f"Element types mismatch between parse 1 and 3.\n"
                f"Parse 1: {types1}\nParse 3: {types3}"
            )

            # Property: Element names must be consistent
            names1 = [e.name for e in result1.elements]
            names2 = [e.name for e in result2.elements]
            names3 = [e.name for e in result3.elements]

            assert names1 == names2, (
                f"Element names mismatch between parse 1 and 2.\n"
                f"Parse 1: {names1}\nParse 2: {names2}"
            )
            assert names1 == names3, (
                f"Element names mismatch between parse 1 and 3.\n"
                f"Parse 1: {names1}\nParse 3: {names3}"
            )

            # Property: Line numbers must be consistent
            for i, (e1, e2, e3) in enumerate(
                zip(result1.elements, result2.elements, result3.elements, strict=False)
            ):
                assert e1.start_line == e2.start_line == e3.start_line, (
                    f"Element {i} start_line mismatch: "
                    f"{e1.start_line}, {e2.start_line}, {e3.start_line}"
                )
                assert e1.end_line == e2.end_line == e3.end_line, (
                    f"Element {i} end_line mismatch: "
                    f"{e1.end_line}, {e2.end_line}, {e3.end_line}"
                )

    @pytest.mark.asyncio
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
        ],
    )
    @given(yaml_content=yaml_with_sequences())
    async def test_property_1_parsing_round_trip_consistency_sequences(
        self, yaml_content: str
    ):
        """
        Feature: yaml-language-support, Property 1: Parsing Round-Trip Consistency

        For any valid YAML content with sequences, parsing SHALL produce
        consistent results across multiple invocations.

        Validates: Requirements 1.1
        """
        # Create temporary YAML file
        with tempfile.TemporaryDirectory() as tmp_dir:
            yaml_file = Path(tmp_dir) / "sequences.yaml"
            yaml_file.write_text(yaml_content, encoding="utf-8")

            plugin = YAMLPlugin()
            request = AnalysisRequest(file_path=str(yaml_file))

            # Parse the file multiple times
            result1 = await plugin.analyze_file(str(yaml_file), request)
            result2 = await plugin.analyze_file(str(yaml_file), request)

            # Property: Both parsing attempts must succeed
            assert result1.success, f"First parse failed: {result1.error}"
            assert result2.success, f"Second parse failed: {result2.error}"

            # Property: Sequence elements must be consistent
            sequences1 = [e for e in result1.elements if e.element_type == "sequence"]
            sequences2 = [e for e in result2.elements if e.element_type == "sequence"]

            assert len(sequences1) == len(
                sequences2
            ), f"Sequence count mismatch: {len(sequences1)} vs {len(sequences2)}"

            # Property: Sequence child counts must be consistent
            for seq1, seq2 in zip(sequences1, sequences2, strict=False):
                assert seq1.child_count == seq2.child_count, (
                    f"Sequence child_count mismatch at line {seq1.start_line}: "
                    f"{seq1.child_count} vs {seq2.child_count}"
                )

    @pytest.mark.asyncio
    @settings(
        max_examples=50,
        deadline=None,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
        ],
    )
    @given(yaml_content=yaml_with_nested_structures())
    async def test_property_1_parsing_round_trip_consistency_nested(
        self, yaml_content: str
    ):
        """
        Feature: yaml-language-support, Property 1: Parsing Round-Trip Consistency

        For any valid YAML content with nested structures, parsing SHALL produce
        consistent hierarchy information across multiple invocations.

        Validates: Requirements 1.1
        """
        # Create temporary YAML file
        with tempfile.TemporaryDirectory() as tmp_dir:
            yaml_file = Path(tmp_dir) / "nested.yaml"
            yaml_file.write_text(yaml_content, encoding="utf-8")

            plugin = YAMLPlugin()
            request = AnalysisRequest(file_path=str(yaml_file))

            # Parse the file multiple times
            result1 = await plugin.analyze_file(str(yaml_file), request)
            result2 = await plugin.analyze_file(str(yaml_file), request)

            # Property: Both parsing attempts must succeed
            assert result1.success, f"First parse failed: {result1.error}"
            assert result2.success, f"Second parse failed: {result2.error}"

            # Property: Nesting levels must be consistent
            nesting1 = [e.nesting_level for e in result1.elements]
            nesting2 = [e.nesting_level for e in result2.elements]

            assert (
                nesting1 == nesting2
            ), f"Nesting levels mismatch.\nParse 1: {nesting1}\nParse 2: {nesting2}"

            # Property: Element hierarchy must be consistent
            for e1, e2 in zip(result1.elements, result2.elements, strict=False):
                assert (
                    e1.element_type == e2.element_type
                ), f"Element type mismatch at line {e1.start_line}"
                assert (
                    e1.nesting_level == e2.nesting_level
                ), f"Nesting level mismatch at line {e1.start_line}"

    @pytest.mark.asyncio
    @settings(
        max_examples=50,
        deadline=None,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
        ],
    )
    @given(yaml_content=yaml_with_comments())
    async def test_property_1_parsing_round_trip_consistency_comments(
        self, yaml_content: str
    ):
        """
        Feature: yaml-language-support, Property 1: Parsing Round-Trip Consistency

        For any valid YAML content with comments, parsing SHALL produce
        consistent results including comment extraction across multiple invocations.

        Validates: Requirements 1.1
        """
        # Create temporary YAML file
        with tempfile.TemporaryDirectory() as tmp_dir:
            yaml_file = Path(tmp_dir) / "comments.yaml"
            yaml_file.write_text(yaml_content, encoding="utf-8")

            plugin = YAMLPlugin()
            request = AnalysisRequest(file_path=str(yaml_file))

            # Parse the file multiple times
            result1 = await plugin.analyze_file(str(yaml_file), request)
            result2 = await plugin.analyze_file(str(yaml_file), request)

            # Property: Both parsing attempts must succeed
            assert result1.success, f"First parse failed: {result1.error}"
            assert result2.success, f"Second parse failed: {result2.error}"

            # Property: Comment elements must be consistent
            comments1 = [e for e in result1.elements if e.element_type == "comment"]
            comments2 = [e for e in result2.elements if e.element_type == "comment"]

            assert len(comments1) == len(
                comments2
            ), f"Comment count mismatch: {len(comments1)} vs {len(comments2)}"

            # Property: Comment content must be consistent
            for c1, c2 in zip(comments1, comments2, strict=False):
                assert (
                    c1.raw_text == c2.raw_text
                ), f"Comment text mismatch at line {c1.start_line}"

    @pytest.mark.asyncio
    @settings(
        max_examples=50,
        deadline=None,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
        ],
    )
    @given(yaml_content=yaml_with_multi_documents())
    async def test_property_1_parsing_round_trip_consistency_multi_document(
        self, yaml_content: str
    ):
        """
        Feature: yaml-language-support, Property 1: Parsing Round-Trip Consistency

        For any valid YAML content with multiple documents, parsing SHALL produce
        consistent document separation across multiple invocations.

        Validates: Requirements 1.1
        """
        # Create temporary YAML file
        with tempfile.TemporaryDirectory() as tmp_dir:
            yaml_file = Path(tmp_dir) / "multi_doc.yaml"
            yaml_file.write_text(yaml_content, encoding="utf-8")

            plugin = YAMLPlugin()
            request = AnalysisRequest(file_path=str(yaml_file))

            # Parse the file multiple times
            result1 = await plugin.analyze_file(str(yaml_file), request)
            result2 = await plugin.analyze_file(str(yaml_file), request)

            # Property: Both parsing attempts must succeed
            assert result1.success, f"First parse failed: {result1.error}"
            assert result2.success, f"Second parse failed: {result2.error}"

            # Property: Document indices must be consistent
            doc_indices1 = [e.document_index for e in result1.elements]
            doc_indices2 = [e.document_index for e in result2.elements]

            assert doc_indices1 == doc_indices2, (
                f"Document indices mismatch.\n"
                f"Parse 1: {doc_indices1}\nParse 2: {doc_indices2}"
            )

            # Property: Document elements must be consistent
            documents1 = [e for e in result1.elements if e.element_type == "document"]
            documents2 = [e for e in result2.elements if e.element_type == "document"]

            assert len(documents1) == len(
                documents2
            ), f"Document count mismatch: {len(documents1)} vs {len(documents2)}"

    @pytest.mark.asyncio
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
        ],
    )
    @given(
        yaml_content=st.one_of(
            simple_yaml_content(),
            yaml_with_sequences(),
            yaml_with_nested_structures(),
            yaml_with_comments(),
        )
    )
    async def test_property_1_parsing_round_trip_consistency_deterministic(
        self, yaml_content: str
    ):
        """
        Feature: yaml-language-support, Property 1: Parsing Round-Trip Consistency

        For any valid YAML content, parsing SHALL be deterministic - the same input
        always produces the exact same output structure.

        Validates: Requirements 1.1
        """
        # Create temporary YAML file
        with tempfile.TemporaryDirectory() as tmp_dir:
            yaml_file = Path(tmp_dir) / "deterministic.yaml"
            yaml_file.write_text(yaml_content, encoding="utf-8")

            plugin = YAMLPlugin()
            request = AnalysisRequest(file_path=str(yaml_file))

            # Parse the file 5 times to ensure determinism
            results = []
            for i in range(5):
                result = await plugin.analyze_file(str(yaml_file), request)
                assert result.success, f"Parse {i + 1} failed: {result.error}"
                results.append(result)

            # Property: All results must have identical structure
            reference = results[0]
            for i, result in enumerate(results[1:], start=2):
                # Check element count
                assert len(result.elements) == len(reference.elements), (
                    f"Parse {i} element count ({len(result.elements)}) differs from "
                    f"reference ({len(reference.elements)})"
                )

                # Check each element matches
                for j, (ref_elem, test_elem) in enumerate(
                    zip(reference.elements, result.elements, strict=False)
                ):
                    assert (
                        ref_elem.element_type == test_elem.element_type
                    ), f"Parse {i}, element {j}: type mismatch"
                    assert (
                        ref_elem.name == test_elem.name
                    ), f"Parse {i}, element {j}: name mismatch"
                    assert (
                        ref_elem.start_line == test_elem.start_line
                    ), f"Parse {i}, element {j}: start_line mismatch"
                    assert (
                        ref_elem.end_line == test_elem.end_line
                    ), f"Parse {i}, element {j}: end_line mismatch"
                    assert (
                        ref_elem.nesting_level == test_elem.nesting_level
                    ), f"Parse {i}, element {j}: nesting_level mismatch"

    @pytest.mark.asyncio
    @settings(
        max_examples=50,
        deadline=None,
        suppress_health_check=[
            HealthCheck.function_scoped_fixture,
            HealthCheck.too_slow,
        ],
    )
    @given(
        yaml_content=simple_yaml_content(),
        num_parses=st.integers(min_value=2, max_value=10),
    )
    async def test_property_1_parsing_round_trip_consistency_stability(
        self, yaml_content: str, num_parses: int
    ):
        """
        Feature: yaml-language-support, Property 1: Parsing Round-Trip Consistency

        For any valid YAML content and any number of parsing invocations, all results
        SHALL be identical, demonstrating parsing stability.

        Validates: Requirements 1.1
        """
        # Create temporary YAML file
        with tempfile.TemporaryDirectory() as tmp_dir:
            yaml_file = Path(tmp_dir) / "stability.yaml"
            yaml_file.write_text(yaml_content, encoding="utf-8")

            plugin = YAMLPlugin()
            request = AnalysisRequest(file_path=str(yaml_file))

            # Parse the file multiple times
            results = []
            for _ in range(num_parses):
                result = await plugin.analyze_file(str(yaml_file), request)
                assert result.success, f"Parse failed: {result.error}"
                results.append(result)

            # Property: All results must be identical
            reference = results[0]
            for i, result in enumerate(results[1:], start=2):
                # Create comparable representations
                ref_repr = [
                    (e.element_type, e.name, e.start_line, e.end_line, e.nesting_level)
                    for e in reference.elements
                ]
                test_repr = [
                    (e.element_type, e.name, e.start_line, e.end_line, e.nesting_level)
                    for e in result.elements
                ]

                assert ref_repr == test_repr, (
                    f"Parse {i} differs from reference.\n"
                    f"Reference: {ref_repr}\n"
                    f"Parse {i}: {test_repr}"
                )
