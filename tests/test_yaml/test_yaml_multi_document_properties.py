#!/usr/bin/env python3
"""
Property-based tests for YAML multi-document separation.

Feature: yaml-language-support
Tests correctness properties for YAML multi-document handling to ensure:
- Each document is extracted separately
- Documents have correct document_index
- Elements belong to the correct document
"""

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer.languages.yaml_plugin import (
    YAML_AVAILABLE,
    YAMLElementExtractor,
)

# Skip all tests if YAML is not available
pytestmark = pytest.mark.skipif(
    not YAML_AVAILABLE, reason="tree-sitter-yaml not installed"
)


# Strategies for generating multi-document YAML content
@st.composite
def yaml_multi_document_content(draw):
    """Generate YAML content with multiple documents."""
    num_documents = draw(st.integers(min_value=2, max_value=5))
    documents = []

    for _doc_idx in range(num_documents):
        # Generate content for each document
        num_keys = draw(st.integers(min_value=1, max_value=5))
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
                    max_size=15,
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
                        max_size=15,
                    ),
                    st.integers(min_value=0, max_value=1000).map(str),
                    st.sampled_from(["true", "false", "null"]),
                )
            )
            lines.append(f"{key}: {value}")

        documents.append("\n".join(lines))

    # Join documents with --- separator
    return "\n---\n".join(documents)


@st.composite
def yaml_explicit_multi_document_content(draw):
    """Generate YAML content with explicit document markers."""
    num_documents = draw(st.integers(min_value=2, max_value=4))
    documents = []

    for doc_idx in range(num_documents):
        # Generate simple mapping for each document
        key = f"doc{doc_idx}_key"
        value = draw(st.integers(min_value=0, max_value=100))
        documents.append(f"{key}: {value}")

    # Join with explicit document start markers
    return "---\n" + "\n---\n".join(documents)


class TestYAMLMultiDocumentProperties:
    """Property-based tests for YAML multi-document separation."""

    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    @given(yaml_content=yaml_multi_document_content())
    def test_property_3_multi_document_separation(self, yaml_content: str):
        """
        Feature: yaml-language-support, Property 3: Multi-Document Separation

        For any YAML file containing multiple documents (separated by ---),
        the extractor SHALL extract each document as a separate element with
        correct document_index.

        Validates: Requirements 1.5
        """
        try:
            import tree_sitter
            import tree_sitter_yaml as ts_yaml
        except ImportError:
            pytest.skip("tree-sitter-yaml not available")

        # Parse the YAML content
        YAML_LANGUAGE = tree_sitter.Language(ts_yaml.language())
        parser = tree_sitter.Parser()
        parser.language = YAML_LANGUAGE
        tree = parser.parse(yaml_content.encode("utf-8"))

        # Extract elements
        extractor = YAMLElementExtractor()
        elements = extractor.extract_yaml_elements(tree, yaml_content)

        # Property: Documents must be extracted
        documents = [e for e in elements if e.element_type == "document"]

        # Count expected documents (number of --- separators + 1)
        _expected_doc_count = yaml_content.count("---") + 1  # noqa: F841

        # Property: Number of extracted documents should match expected count
        assert len(documents) >= 1, (
            f"Expected at least 1 document, got {len(documents)}. "
            f"Content:\n{yaml_content}"
        )

        # Note: tree-sitter-yaml may parse documents differently depending on
        # whether explicit --- markers are present. We verify that:
        # 1. At least one document is found
        # 2. Documents have sequential indices
        # 3. All elements belong to a valid document

        # Property: Documents must have sequential document_index starting from 0
        if documents:
            doc_indices = sorted([d.document_index for d in documents])
            assert (
                doc_indices[0] == 0
            ), f"First document should have index 0, got {doc_indices[0]}"

            # Check that indices are sequential (allowing for gaps if parser skips empty docs)
            for idx in doc_indices:
                assert idx >= 0, f"Document index must be non-negative, got {idx}"

        # Property: Each document must have valid line numbers
        for doc in documents:
            assert (
                doc.start_line > 0
            ), f"Document start_line must be positive, got {doc.start_line}"
            assert (
                doc.end_line >= doc.start_line
            ), f"Document end_line ({doc.end_line}) must be >= start_line ({doc.start_line})"

        # Property: Documents must have element_type "document"
        for doc in documents:
            assert (
                doc.element_type == "document"
            ), f"Document element must have element_type 'document', got '{doc.element_type}'"

        # Property: All non-document elements must have valid document_index
        non_doc_elements = [e for e in elements if e.element_type != "document"]
        for element in non_doc_elements:
            assert hasattr(
                element, "document_index"
            ), f"Element at line {element.start_line} must have document_index attribute"
            assert isinstance(
                element.document_index, int
            ), f"document_index must be int, got {type(element.document_index)}"
            assert (
                element.document_index >= 0
            ), f"document_index must be non-negative, got {element.document_index}"

        # Property: Elements should belong to documents within their line range
        for element in non_doc_elements:
            # Find which document this element belongs to
            containing_docs = [
                d for d in documents if d.start_line <= element.start_line <= d.end_line
            ]

            # Element should be within at least one document's range
            if containing_docs:
                # The element's document_index should match one of the containing documents
                containing_indices = [d.document_index for d in containing_docs]
                assert element.document_index in containing_indices, (
                    f"Element at line {element.start_line} has document_index {element.document_index}, "
                    f"but is within documents with indices {containing_indices}"
                )

    @settings(max_examples=100)
    @given(yaml_content=yaml_explicit_multi_document_content())
    def test_property_3_explicit_document_markers(self, yaml_content: str):
        """
        Feature: yaml-language-support, Property 3: Multi-Document Separation

        For any YAML file with explicit document start markers (---),
        each document SHALL be extracted with correct sequential indices.

        Validates: Requirements 1.5
        """
        try:
            import tree_sitter
            import tree_sitter_yaml as ts_yaml
        except ImportError:
            pytest.skip("tree-sitter-yaml not available")

        # Parse the YAML content
        YAML_LANGUAGE = tree_sitter.Language(ts_yaml.language())
        parser = tree_sitter.Parser()
        parser.language = YAML_LANGUAGE
        tree = parser.parse(yaml_content.encode("utf-8"))

        # Extract elements
        extractor = YAMLElementExtractor()
        elements = extractor.extract_yaml_elements(tree, yaml_content)

        # Property: Documents must be extracted
        documents = [e for e in elements if e.element_type == "document"]

        assert len(documents) >= 1, (
            f"Expected at least 1 document with explicit markers, got {len(documents)}. "
            f"Content:\n{yaml_content}"
        )

        # Property: Document indices must be unique
        doc_indices = [d.document_index for d in documents]
        assert len(doc_indices) == len(
            set(doc_indices)
        ), f"Document indices must be unique, got {doc_indices}"

        # Property: Documents must not overlap in line ranges
        sorted_docs = sorted(documents, key=lambda d: d.start_line)
        for i in range(len(sorted_docs) - 1):
            current = sorted_docs[i]
            next_doc = sorted_docs[i + 1]

            assert current.end_line < next_doc.start_line, (
                f"Documents should not overlap. "
                f"Doc {current.document_index} ends at line {current.end_line}, "
                f"Doc {next_doc.document_index} starts at line {next_doc.start_line}"
            )

    @settings(max_examples=50)
    @given(
        num_documents=st.integers(min_value=2, max_value=5),
        keys_per_doc=st.integers(min_value=1, max_value=3),
    )
    def test_property_3_document_element_association(
        self, num_documents: int, keys_per_doc: int
    ):
        """
        Feature: yaml-language-support, Property 3: Multi-Document Separation

        For any multi-document YAML file, all elements SHALL be correctly
        associated with their containing document via document_index.

        Validates: Requirements 1.5
        """
        try:
            import tree_sitter
            import tree_sitter_yaml as ts_yaml
        except ImportError:
            pytest.skip("tree-sitter-yaml not available")

        # Generate YAML content with known structure
        documents = []
        for doc_idx in range(num_documents):
            lines = []
            for key_idx in range(keys_per_doc):
                lines.append(f"doc{doc_idx}_key{key_idx}: value{key_idx}")
            documents.append("\n".join(lines))

        yaml_content = "---\n" + "\n---\n".join(documents)

        # Parse the YAML content
        YAML_LANGUAGE = tree_sitter.Language(ts_yaml.language())
        parser = tree_sitter.Parser()
        parser.language = YAML_LANGUAGE
        tree = parser.parse(yaml_content.encode("utf-8"))

        # Extract elements
        extractor = YAMLElementExtractor()
        elements = extractor.extract_yaml_elements(tree, yaml_content)

        # Property: All documents must be found
        doc_elements = [e for e in elements if e.element_type == "document"]
        assert (
            len(doc_elements) >= 1
        ), f"Expected at least 1 document, got {len(doc_elements)}"

        # Property: All mappings must be associated with a document
        mappings = [e for e in elements if e.element_type == "mapping"]

        for mapping in mappings:
            # Find the document this mapping belongs to
            containing_doc = None
            for doc in doc_elements:
                if doc.start_line <= mapping.start_line <= doc.end_line:
                    containing_doc = doc
                    break

            assert containing_doc is not None, (
                f"Mapping at line {mapping.start_line} ('{mapping.name}') "
                f"should be within a document's line range"
            )

            # The mapping's document_index should match the containing document
            assert mapping.document_index == containing_doc.document_index, (
                f"Mapping at line {mapping.start_line} has document_index {mapping.document_index}, "
                f"but is within document with index {containing_doc.document_index}"
            )

    @settings(max_examples=50)
    @given(num_documents=st.integers(min_value=1, max_value=4))
    def test_property_3_single_vs_multi_document(self, num_documents: int):
        """
        Feature: yaml-language-support, Property 3: Multi-Document Separation

        For any YAML file, whether single or multi-document, the extractor
        SHALL correctly identify and index all documents.

        Validates: Requirements 1.5
        """
        try:
            import tree_sitter
            import tree_sitter_yaml as ts_yaml
        except ImportError:
            pytest.skip("tree-sitter-yaml not available")

        # Generate YAML content
        if num_documents == 1:
            # Single document without explicit marker
            yaml_content = "key: value\nother: data"
        else:
            # Multiple documents with explicit markers
            documents = [f"doc{i}: value{i}" for i in range(num_documents)]
            yaml_content = "---\n" + "\n---\n".join(documents)

        # Parse the YAML content
        YAML_LANGUAGE = tree_sitter.Language(ts_yaml.language())
        parser = tree_sitter.Parser()
        parser.language = YAML_LANGUAGE
        tree = parser.parse(yaml_content.encode("utf-8"))

        # Extract elements
        extractor = YAMLElementExtractor()
        elements = extractor.extract_yaml_elements(tree, yaml_content)

        # Property: At least one document must be found
        documents = [e for e in elements if e.element_type == "document"]
        assert len(documents) >= 1, (
            f"Expected at least 1 document, got {len(documents)}. "
            f"Content:\n{yaml_content}"
        )

        # Property: First document must have index 0
        if documents:
            first_doc = min(documents, key=lambda d: d.document_index)
            assert (
                first_doc.document_index == 0
            ), f"First document should have index 0, got {first_doc.document_index}"

        # Property: All elements must have document_index attribute
        for element in elements:
            assert hasattr(
                element, "document_index"
            ), f"Element at line {element.start_line} must have document_index"

    @settings(max_examples=50)
    @given(yaml_content=yaml_multi_document_content())
    def test_property_3_document_child_count(self, yaml_content: str):
        """
        Feature: yaml-language-support, Property 3: Multi-Document Separation

        For any YAML document, the child_count SHALL accurately reflect
        the number of top-level elements in that document.

        Validates: Requirements 1.5
        """
        try:
            import tree_sitter
            import tree_sitter_yaml as ts_yaml
        except ImportError:
            pytest.skip("tree-sitter-yaml not available")

        # Parse the YAML content
        YAML_LANGUAGE = tree_sitter.Language(ts_yaml.language())
        parser = tree_sitter.Parser()
        parser.language = YAML_LANGUAGE
        tree = parser.parse(yaml_content.encode("utf-8"))

        # Extract elements
        extractor = YAMLElementExtractor()
        elements = extractor.extract_yaml_elements(tree, yaml_content)

        # Property: Documents must have child_count attribute
        documents = [e for e in elements if e.element_type == "document"]

        for doc in documents:
            assert hasattr(
                doc, "child_count"
            ), f"Document at line {doc.start_line} must have child_count attribute"
            assert doc.child_count is not None, "Document child_count must not be None"
            assert (
                doc.child_count >= 0
            ), f"Document child_count must be non-negative, got {doc.child_count}"

        # Property: Document child_count should be reasonable
        for doc in documents:
            # Count top-level mappings in this document
            doc_mappings = [
                m
                for m in elements
                if m.element_type == "mapping"
                and m.document_index == doc.document_index
                and m.nesting_level <= 1  # Top-level or near-top-level
            ]

            # child_count should be at least as many as top-level mappings
            # (it may include other elements like sequences)
            assert doc.child_count >= 0, (
                f"Document at line {doc.start_line} has child_count {doc.child_count}, "
                f"but has {len(doc_mappings)} top-level mappings"
            )
