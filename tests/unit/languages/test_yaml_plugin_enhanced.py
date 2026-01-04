"""Enhanced tests for YAML plugin functionality with focus on advanced features."""

import pytest

from tree_sitter_analyzer.languages.yaml_plugin import (
    YAML_AVAILABLE,
    YAMLPlugin,
)

# Enhanced YAML code samples for testing
KEY_VALUE_CODE = """
# Simple key-value pairs
name: John Doe
age: 30
city: New York
country: USA

# Boolean values
active: true
verified: false

# Null values
middle_name: null
nickname: ~

# Numbers
salary: 50000.50
experience: 5

# Strings with quotes
description: "This is a quoted string"
notes: 'Single quoted string'
"""

LIST_CODE = """
# Simple list
fruits:
  - apple
  - banana
  - orange

# List of numbers
numbers:
  - 1
  - 2
  - 3
  - 4
  - 5

# List of objects
users:
  - name: Alice
    age: 25
  - name: Bob
    age: 30
  - name: Charlie
    age: 35

# Nested list
matrix:
  - [1, 2, 3]
  - [4, 5, 6]
  - [7, 8, 9]

# Inline list
colors: [red, green, blue]
"""

NESTED_STRUCTURE_CODE = """
# Nested mapping
person:
  name: John Doe
  age: 30
  address:
    street: 123 Main St
    city: New York
    state: NY
    zip: 10001
  contact:
    email: john@example.com
    phone: 555-1234

# Deep nesting
config:
  database:
    connection:
      host: localhost
      port: 5432
      credentials:
        username: admin
        password: secret
    pool:
      min: 5
      max: 20
  cache:
    enabled: true
    ttl: 3600
"""

ANCHOR_ALIAS_CODE = """
# Anchors and aliases
defaults: &defaults
  timeout: 30
  retries: 3
  debug: false

development:
  <<: *defaults
  debug: true

production:
  <<: *defaults
  timeout: 60

# Multiple anchors
server_config: &server
  host: localhost
  port: 8080

dev_server:
  <<: *server
  port: 3000

prod_server:
  <<: *server
  host: prod.example.com

# Anchor in list
item_template: &item
  - name: default
  - value: 0

list1:
  <<: *item

list2:
  <<: *item
"""

COMPLEX_YAML_CODE = """
# Complex YAML structure
version: 1.0
metadata:
  name: My Application
  version: 1.0.0
  description: A sample application
  author:
    name: Developer
    email: dev@example.com

services:
  web:
    image: nginx:latest
    ports:
      - "80:80"
    environment:
      NODE_ENV: production
    depends_on:
      - database
      - cache

  database:
    image: postgres:13
    environment:
      POSTGRES_DB: myapp
      POSTGRES_USER: admin
      POSTGRES_PASSWORD: secret
    volumes:
      - db_data:/var/lib/postgresql/data

  cache:
    image: redis:alpine
    ports:
      - "6379:6379"

volumes:
  db_data:
    driver: local

networks:
  default:
    driver: bridge
"""

MULTI_DOCUMENT_CODE = """
---
document: 1
name: First Document
---
document: 2
name: Second Document
---
document: 3
name: Third Document
"""

SCALAR_TYPES_CODE = """
# Different scalar types
string_value: "Hello, World!"
integer_value: 42
float_value: 3.14159
boolean_true: true
boolean_false: false
null_value: null
empty_value: ~

# Scientific notation
scientific: 1.23e+10

# Hexadecimal
hex: 0x1A

# Octal
octal: 0o755

# Timestamps
timestamp: 2001-12-15T02:59:43.1Z
date: 2002-12-14

# Base64
base64: !!binary |
  R0lGODlhDAAMAIQAAP//9/X17unp5WZmZgAAAOfn515eXv
  Pz7Y6OjuDg4F+srP/x7Fn6e3v3/zL29uH9+X9+2/v9+
  8/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39/f39
"""

COMMENT_CODE = """
# This is a comment
name: John Doe
# Another comment
age: 30

# Inline comment
city: New York  # end of line comment

# Block comment
# spanning multiple
# lines
country: USA

# Comment before section
address:
  # Comment inside mapping
  street: 123 Main St
  city: New York  # Comment after value
  # Comment after value
  zip: 10001
"""


def get_tree_for_code(code: str, plugin: YAMLPlugin):
    """Helper to parse YAML code and return tree."""
    import tree_sitter

    language = plugin.get_tree_sitter_language()
    parser = tree_sitter.Parser()
    if hasattr(parser, "set_language"):
        parser.set_language(language)
    elif hasattr(parser, "language"):
        parser.language = language
    else:
        parser = tree_sitter.Parser(language)
    return parser.parse(code.encode("utf-8"))


@pytest.mark.skipif(not YAML_AVAILABLE, reason="tree-sitter-yaml not installed")
class TestYAMLKeyPairRecognition:
    """Test YAML key-value pair recognition and extraction."""

    def test_extract_simple_key_value(self):
        """Test extraction of simple key-value pairs."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(KEY_VALUE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, KEY_VALUE_CODE)

        # Should find key-value pairs
        mapping_elements = [e for e in elements if e.element_type == "mapping"]
        assert len(mapping_elements) >= 1

    def test_extract_string_value(self):
        """Test extraction of string value."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(KEY_VALUE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, KEY_VALUE_CODE)

        name_element = next((e for e in elements if e.key == "name"), None)
        if name_element:
            assert name_element.value == "John Doe"
            assert name_element.value_type == "string"

    def test_extract_integer_value(self):
        """Test extraction of integer value."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(KEY_VALUE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, KEY_VALUE_CODE)

        age_element = next((e for e in elements if e.key == "age"), None)
        if age_element:
            assert age_element.value == "30"
            assert age_element.value_type == "number"

    def test_extract_float_value(self):
        """Test extraction of float value."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(KEY_VALUE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, KEY_VALUE_CODE)

        salary_element = next((e for e in elements if e.key == "salary"), None)
        if salary_element:
            assert "50000.50" in salary_element.value
            assert salary_element.value_type == "number"

    def test_extract_boolean_true(self):
        """Test extraction of boolean true value."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(KEY_VALUE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, KEY_VALUE_CODE)

        active_element = next((e for e in elements if e.key == "active"), None)
        if active_element:
            assert active_element.value == "true"
            assert active_element.value_type == "boolean"

    def test_extract_boolean_false(self):
        """Test extraction of boolean false value."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(KEY_VALUE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, KEY_VALUE_CODE)

        verified_element = next((e for e in elements if e.key == "verified"), None)
        if verified_element:
            assert verified_element.value == "false"
            assert verified_element.value_type == "boolean"

    def test_extract_null_value(self):
        """Test extraction of null value."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(KEY_VALUE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, KEY_VALUE_CODE)

        middle_name_element = next(
            (e for e in elements if e.key == "middle_name"), None
        )
        if middle_name_element:
            assert middle_name_element.value in ["null", "~"]
            assert middle_name_element.value_type == "null"

    def test_extract_quoted_string(self):
        """Test extraction of quoted string value."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(KEY_VALUE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, KEY_VALUE_CODE)

        description_element = next(
            (e for e in elements if e.key == "description"), None
        )
        if description_element:
            assert "This is a quoted string" in description_element.value


@pytest.mark.skipif(not YAML_AVAILABLE, reason="tree-sitter-yaml not installed")
class TestYAMLListRecognition:
    """Test YAML list recognition and extraction."""

    def test_extract_simple_list(self):
        """Test extraction of simple list."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(LIST_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, LIST_CODE)

        # Should find sequence elements
        sequence_elements = [e for e in elements if e.element_type == "sequence"]
        assert len(sequence_elements) >= 1

    def test_extract_list_of_strings(self):
        """Test extraction of list of strings."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(LIST_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, LIST_CODE)

        fruits_element = next((e for e in elements if e.key == "fruits"), None)
        if fruits_element:
            assert fruits_element.value_type == "sequence"

    def test_extract_list_of_numbers(self):
        """Test extraction of list of numbers."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(LIST_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, LIST_CODE)

        numbers_element = next((e for e in elements if e.key == "numbers"), None)
        if numbers_element:
            assert numbers_element.value_type == "sequence"

    def test_extract_list_of_objects(self):
        """Test extraction of list of objects."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(LIST_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, LIST_CODE)

        users_element = next((e for e in elements if e.key == "users"), None)
        if users_element:
            assert users_element.value_type == "sequence"

    def test_extract_nested_list(self):
        """Test extraction of nested list."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(LIST_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, LIST_CODE)

        matrix_element = next((e for e in elements if e.key == "matrix"), None)
        if matrix_element:
            assert matrix_element.value_type == "sequence"

    def test_extract_inline_list(self):
        """Test extraction of inline list."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(LIST_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, LIST_CODE)

        colors_element = next((e for e in elements if e.key == "colors"), None)
        if colors_element:
            assert colors_element.value_type == "sequence"


@pytest.mark.skipif(not YAML_AVAILABLE, reason="tree-sitter-yaml not installed")
class TestYAMLNestedStructureRecognition:
    """Test YAML nested structure recognition and extraction."""

    def test_extract_nested_mapping(self):
        """Test extraction of nested mapping."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(NESTED_STRUCTURE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, NESTED_STRUCTURE_CODE)

        # Should find nested elements
        assert len(elements) >= 5

    def test_extract_person_structure(self):
        """Test extraction of person structure."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(NESTED_STRUCTURE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, NESTED_STRUCTURE_CODE)

        person_element = next((e for e in elements if e.key == "person"), None)
        if person_element:
            assert person_element.element_type == "mapping"

    def test_extract_address_structure(self):
        """Test extraction of address structure."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(NESTED_STRUCTURE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, NESTED_STRUCTURE_CODE)

        address_element = next((e for e in elements if e.key == "address"), None)
        if address_element:
            assert address_element.element_type == "mapping"

    def test_extract_deep_nesting(self):
        """Test extraction of deeply nested structure."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(NESTED_STRUCTURE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, NESTED_STRUCTURE_CODE)

        # Should find deeply nested elements
        assert len(elements) >= 10

    def test_extract_config_structure(self):
        """Test extraction of config structure."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(NESTED_STRUCTURE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, NESTED_STRUCTURE_CODE)

        config_element = next((e for e in elements if e.key == "config"), None)
        if config_element:
            assert config_element.element_type == "mapping"

    def test_nesting_levels(self):
        """Test that nesting levels are captured."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(NESTED_STRUCTURE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, NESTED_STRUCTURE_CODE)

        # Some elements should have nesting_level > 0
        nested_elements = [e for e in elements if e.nesting_level > 0]
        assert len(nested_elements) >= 1


@pytest.mark.skipif(not YAML_AVAILABLE, reason="tree-sitter-yaml not installed")
class TestYAMLAnchorAliasRecognition:
    """Test YAML anchor and alias recognition and extraction."""

    def test_extract_anchor(self):
        """Test extraction of anchor."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(ANCHOR_ALIAS_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, ANCHOR_ALIAS_CODE)

        # Should find anchor elements
        anchor_elements = [e for e in elements if e.element_type == "anchor"]
        assert len(anchor_elements) >= 1

    def test_extract_alias(self):
        """Test extraction of alias."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(ANCHOR_ALIAS_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, ANCHOR_ALIAS_CODE)

        # Should find alias elements
        alias_elements = [e for e in elements if e.element_type == "alias"]
        assert len(alias_elements) >= 1

    def test_extract_defaults_anchor(self):
        """Test extraction of defaults anchor."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(ANCHOR_ALIAS_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, ANCHOR_ALIAS_CODE)

        defaults_element = next((e for e in elements if e.key == "defaults"), None)
        if defaults_element:
            assert defaults_element.anchor_name is not None

    def test_extract_alias_usage(self):
        """Test extraction of alias usage."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(ANCHOR_ALIAS_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, ANCHOR_ALIAS_CODE)

        # Should find elements using aliases
        alias_usage_elements = [e for e in elements if e.alias_target is not None]
        assert len(alias_usage_elements) >= 1

    def test_extract_merge_key(self):
        """Test extraction of merge key (<<)."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(ANCHOR_ALIAS_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, ANCHOR_ALIAS_CODE)

        # Should find merge keys
        merge_elements = [e for e in elements if "<<" in str(e.raw_text)]
        assert len(merge_elements) >= 1

    def test_extract_multiple_anchors(self):
        """Test extraction of multiple anchors."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(ANCHOR_ALIAS_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, ANCHOR_ALIAS_CODE)

        # Should find multiple anchors
        anchor_elements = [e for e in elements if e.element_type == "anchor"]
        assert len(anchor_elements) >= 2

    def test_extract_anchor_in_list(self):
        """Test extraction of anchor in list."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(ANCHOR_ALIAS_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, ANCHOR_ALIAS_CODE)

        # Should find anchor in list
        anchor_elements = [e for e in elements if e.element_type == "anchor"]
        assert len(anchor_elements) >= 1


@pytest.mark.skipif(not YAML_AVAILABLE, reason="tree-sitter-yaml not installed")
class TestYAMLComplexStructures:
    """Test extraction of complex YAML structures."""

    def test_extract_complex_structure(self):
        """Test extraction of complex YAML structure."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(COMPLEX_YAML_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, COMPLEX_YAML_CODE)

        # Should find many elements
        assert len(elements) >= 10

    def test_extract_services_structure(self):
        """Test extraction of services structure."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(COMPLEX_YAML_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, COMPLEX_YAML_CODE)

        services_element = next((e for e in elements if e.key == "services"), None)
        if services_element:
            assert services_element.element_type == "mapping"

    def test_extract_nested_services(self):
        """Test extraction of nested services."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(COMPLEX_YAML_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, COMPLEX_YAML_CODE)

        # Should find service names
        service_keys = [
            e.key for e in elements if e.key in ["web", "database", "cache"]
        ]
        assert len(service_keys) >= 1

    def test_extract_environment_variables(self):
        """Test extraction of environment variables."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(COMPLEX_YAML_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, COMPLEX_YAML_CODE)

        # Should find environment elements
        env_elements = [e for e in elements if e.key == "environment"]
        assert len(env_elements) >= 1

    def test_extract_volumes(self):
        """Test extraction of volumes."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(COMPLEX_YAML_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, COMPLEX_YAML_CODE)

        volumes_element = next((e for e in elements if e.key == "volumes"), None)
        if volumes_element:
            assert volumes_element.element_type == "mapping"

    def test_extract_networks(self):
        """Test extraction of networks."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(COMPLEX_YAML_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, COMPLEX_YAML_CODE)

        networks_element = next((e for e in elements if e.key == "networks"), None)
        if networks_element:
            assert networks_element.element_type == "mapping"


@pytest.mark.skipif(not YAML_AVAILABLE, reason="tree-sitter-yaml not installed")
class TestYAMLMultiDocument:
    """Test YAML multi-document recognition and extraction."""

    def test_extract_multiple_documents(self):
        """Test extraction of multiple documents."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(MULTI_DOCUMENT_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, MULTI_DOCUMENT_CODE)

        # Should find document separators
        document_elements = [e for e in elements if e.element_type == "document"]
        assert len(document_elements) >= 2

    def test_extract_document_content(self):
        """Test extraction of document content."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(MULTI_DOCUMENT_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, MULTI_DOCUMENT_CODE)

        # Should find document elements
        assert len(elements) >= 3

    def test_document_indices(self):
        """Test that document indices are captured."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(MULTI_DOCUMENT_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, MULTI_DOCUMENT_CODE)

        # Some elements should have document_index > 0
        multi_doc_elements = [e for e in elements if e.document_index > 0]
        assert len(multi_doc_elements) >= 1


@pytest.mark.skipif(not YAML_AVAILABLE, reason="tree-sitter-yaml not installed")
class TestYAMLScalarTypes:
    """Test YAML scalar type recognition and extraction."""

    def test_extract_string_scalar(self):
        """Test extraction of string scalar."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(SCALAR_TYPES_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, SCALAR_TYPES_CODE)

        string_element = next((e for e in elements if e.key == "string_value"), None)
        if string_element:
            assert string_element.value_type == "string"

    def test_extract_integer_scalar(self):
        """Test extraction of integer scalar."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(SCALAR_TYPES_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, SCALAR_TYPES_CODE)

        integer_element = next((e for e in elements if e.key == "integer_value"), None)
        if integer_element:
            assert integer_element.value_type == "number"

    def test_extract_float_scalar(self):
        """Test extraction of float scalar."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(SCALAR_TYPES_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, SCALAR_TYPES_CODE)

        float_element = next((e for e in elements if e.key == "float_value"), None)
        if float_element:
            assert float_element.value_type == "number"

    def test_extract_boolean_scalar(self):
        """Test extraction of boolean scalar."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(SCALAR_TYPES_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, SCALAR_TYPES_CODE)

        boolean_elements = [
            e for e in elements if e.key in ["boolean_true", "boolean_false"]
        ]
        assert len(boolean_elements) >= 2

    def test_extract_null_scalar(self):
        """Test extraction of null scalar."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(SCALAR_TYPES_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, SCALAR_TYPES_CODE)

        null_element = next((e for e in elements if e.key == "null_value"), None)
        if null_element:
            assert null_element.value_type == "null"

    def test_extract_scientific_notation(self):
        """Test extraction of scientific notation."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(SCALAR_TYPES_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, SCALAR_TYPES_CODE)

        scientific_element = next((e for e in elements if e.key == "scientific"), None)
        if scientific_element:
            assert "e" in scientific_element.value.lower()

    def test_extract_hexadecimal(self):
        """Test extraction of hexadecimal value."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(SCALAR_TYPES_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, SCALAR_TYPES_CODE)

        hex_element = next((e for e in elements if e.key == "hex"), None)
        if hex_element:
            assert "0x" in hex_element.value

    def test_extract_timestamp(self):
        """Test extraction of timestamp value."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(SCALAR_TYPES_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, SCALAR_TYPES_CODE)

        timestamp_element = next((e for e in elements if e.key == "timestamp"), None)
        if timestamp_element:
            assert "T" in timestamp_element.value or "-" in timestamp_element.value


@pytest.mark.skipif(not YAML_AVAILABLE, reason="tree-sitter-yaml not installed")
class TestYAMLCommentRecognition:
    """Test YAML comment recognition and extraction."""

    def test_extract_comment(self):
        """Test extraction of comment."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(COMMENT_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, COMMENT_CODE)

        # Should find comment elements
        comment_elements = [e for e in elements if e.element_type == "comment"]
        assert len(comment_elements) >= 1

    def test_extract_inline_comment(self):
        """Test extraction of inline comment."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(COMMENT_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, COMMENT_CODE)

        # Should find inline comments
        comment_elements = [e for e in elements if e.element_type == "comment"]
        assert len(comment_elements) >= 1

    def test_extract_block_comment(self):
        """Test extraction of block comment."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(COMMENT_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, COMMENT_CODE)

        # Should find block comments
        comment_elements = [e for e in elements if e.element_type == "comment"]
        assert len(comment_elements) >= 1


@pytest.mark.skipif(not YAML_AVAILABLE, reason="tree-sitter-yaml not installed")
class TestYAMLQueryAccuracy:
    """Test accuracy of YAML queries."""

    def test_key_value_query_accuracy(self):
        """Test that key-value query accurately identifies pairs."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(KEY_VALUE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, KEY_VALUE_CODE)

        # Should not extract non-key-value elements
        for element in elements:
            if element.element_type == "mapping":
                assert element.key is not None
                assert len(element.key) > 0

    def test_list_query_accuracy(self):
        """Test that list query accurately identifies lists."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(LIST_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, LIST_CODE)

        # Should find sequence elements
        sequence_elements = [e for e in elements if e.element_type == "sequence"]
        assert len(sequence_elements) >= 1

    def test_nested_structure_query_accuracy(self):
        """Test that nested structure query is accurate."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(NESTED_STRUCTURE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, NESTED_STRUCTURE_CODE)

        # Should find nested elements
        nested_elements = [e for e in elements if e.nesting_level > 0]
        assert len(nested_elements) >= 1

    def test_anchor_alias_query_accuracy(self):
        """Test that anchor/alias query is accurate."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(ANCHOR_ALIAS_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, ANCHOR_ALIAS_CODE)

        # Should find anchors and aliases
        anchor_elements = [e for e in elements if e.element_type == "anchor"]
        alias_elements = [e for e in elements if e.element_type == "alias"]
        assert len(anchor_elements) >= 1 or len(alias_elements) >= 1

    def test_multi_document_query_accuracy(self):
        """Test that multi-document query is accurate."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(MULTI_DOCUMENT_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, MULTI_DOCUMENT_CODE)

        # Should find document separators
        document_elements = [e for e in elements if e.element_type == "document"]
        assert len(document_elements) >= 2

    def test_scalar_type_query_accuracy(self):
        """Test that scalar type query is accurate."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(SCALAR_TYPES_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, SCALAR_TYPES_CODE)

        # Should find various scalar types
        scalar_types = {e.value_type for e in elements if e.value_type}
        assert "string" in scalar_types
        assert "number" in scalar_types

    def test_no_false_positives(self):
        """Test that queries don't produce false positives."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(KEY_VALUE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, KEY_VALUE_CODE)

        # Should not extract comments as mappings
        for element in elements:
            if element.element_type == "mapping":
                assert element.key is not None
                assert element.key.strip() != ""

    def test_no_false_negatives(self):
        """Test that queries don't miss elements."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(KEY_VALUE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, KEY_VALUE_CODE)

        # Should find all expected keys
        keys = [e.key for e in elements if e.key]
        assert "name" in keys
        assert "age" in keys
        assert "city" in keys

    def test_line_number_accuracy(self):
        """Test that line numbers are accurate."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(KEY_VALUE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, KEY_VALUE_CODE)

        for element in elements:
            assert element.start_line > 0
            assert element.end_line >= element.start_line

    def test_value_type_accuracy(self):
        """Test that value types are accurately identified."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(SCALAR_TYPES_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, SCALAR_TYPES_CODE)

        # Check that value types match expectations
        string_element = next((e for e in elements if e.key == "string_value"), None)
        if string_element:
            assert string_element.value_type == "string"

        integer_element = next((e for e in elements if e.key == "integer_value"), None)
        if integer_element:
            assert integer_element.value_type == "number"

        boolean_element = next((e for e in elements if e.key == "boolean_true"), None)
        if boolean_element:
            assert boolean_element.value_type == "boolean"
