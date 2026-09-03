"""
Tests for Java Cursor-API traversal and modern Java node extraction.

Covers:
  - Cursor-based traversal (no direct reversed(children) access)
  - _JAVA_CONTAINER_NODES completeness
  - lambda_expression -> Function(name="<lambda>")
  - static_initializer -> Function(name="<static_initializer>", is_static=True)
  - anonymous_class_body -> Class(class_type="anonymous")
  - compact_constructor_declaration -> Function(is_constructor=True)
  - sealed class permits -> Class.interfaces includes permitted types
  - Map<String, List<Integer>> return type preserved intact
  - JavaDoc from AST sibling block_comment
"""

from __future__ import annotations

import inspect

import pytest

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_parser():
    """Create and return a configured Java tree-sitter Parser."""
    import tree_sitter
    import tree_sitter_java as ts_java

    lang = tree_sitter.Language(ts_java.language())
    parser = tree_sitter.Parser()
    parser.language = lang
    return parser


def _parse(src: str):
    """Parse *src* as Java source and return (tree, parser)."""
    parser = _make_parser()
    return parser.parse(src.encode()), parser


def _find_nodes_by_type(root_node, node_type: str):
    """Full-tree cursor walk that collects every node with the given type.

    Unlike the selective descent in ``java_traverse_and_extract``, this helper
    descends into *all* nodes so it can locate deeply nested constructs for
    direct unit-testing of extraction functions.
    """
    result = []
    cursor = root_node.walk()
    reached_root = False
    while not reached_root:
        if cursor.node.type == node_type:
            result.append(cursor.node)
        if cursor.goto_first_child():
            continue
        if cursor.goto_next_sibling():
            continue
        retracing = True
        while retracing:
            if not cursor.goto_parent():
                retracing = False
                reached_root = True
            elif cursor.node == root_node:
                retracing = False
                reached_root = True
            elif cursor.goto_next_sibling():
                retracing = False
    return result


def _make_extractor(src: str):
    """Return a ``JavaElementExtractor`` pre-loaded with *src*."""
    from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor

    tree, _ = _parse(src)
    ext = JavaElementExtractor()
    ext.extract_annotations(tree, src)
    return ext, tree


# ---------------------------------------------------------------------------
# TestCursorApiTraversal
# ---------------------------------------------------------------------------


class TestCursorApiTraversal:
    def test_no_direct_children_access(self):
        """_java_traversal must not use reversed(node.children) — REQ-E-022."""
        from tree_sitter_analyzer.languages import _java_traversal

        source = inspect.getsource(_java_traversal)
        assert "reversed(" not in source, (
            "Direct reversed(children) access found in _java_traversal. "
            "The Cursor API must be used instead."
        )

    def test_container_nodes_completeness(self):
        """_JAVA_CONTAINER_NODES must contain all node types required by REQ-E-004."""
        from tree_sitter_analyzer.languages._java_traversal import _JAVA_CONTAINER_NODES

        required = {
            "compact_constructor_declaration",
            "static_initializer",
            "instance_initializer",
            "switch_block",
            "switch_block_statement_group",
            "try_with_resources_statement",
            "lambda_expression",
            "object_creation_expression",
            "anonymous_class_body",
            "module_declaration",
            "module_body",
        }
        missing = required - _JAVA_CONTAINER_NODES
        assert not missing, f"Missing container node types: {missing}"

    def test_container_nodes_minimum_count(self):
        """_JAVA_CONTAINER_NODES must have at least 23 entries (REQ-E-004)."""
        from tree_sitter_analyzer.languages._java_traversal import _JAVA_CONTAINER_NODES

        assert len(_JAVA_CONTAINER_NODES) == 33, (
            f"Expected exactly 33 container node types (REQ-E-004 + C-1 fix), got {len(_JAVA_CONTAINER_NODES)}"
        )


# ---------------------------------------------------------------------------
# TestLambdaExtraction
# ---------------------------------------------------------------------------


class TestLambdaExtraction:
    _SRC = """\
class Foo {
    void run() {
        Runnable r = () -> System.out.println("hello");
        java.util.function.Function<String, Integer> f = s -> s.length();
        java.util.function.BiFunction<Integer, Integer, Integer> add = (x, y) -> x + y;
    }
}
"""

    def test_lambda_extracted_as_function(self):
        """extract_lambda_function returns a Function with name='<lambda>'."""
        from tree_sitter_analyzer.languages._java_element import extract_lambda_function

        tree, _ = _parse(self._SRC)
        lambda_nodes = _find_nodes_by_type(tree.root_node, "lambda_expression")
        assert lambda_nodes, "No lambda_expression nodes found in parsed tree"

        def _get_text(node):
            return node.text.decode("utf-8", errors="replace")

        result = extract_lambda_function(
            lambda_nodes[0],
            _get_text,
            self._SRC.splitlines(),
        )
        assert result is not None
        assert result.name == "<lambda>"
        assert result.is_method is True
        assert result.language == "java"

    def test_lambda_parameters_extracted(self):
        """Lambda with (x, y) should produce two parameters."""
        from tree_sitter_analyzer.languages._java_element import extract_lambda_function

        tree, _ = _parse(self._SRC)
        lambda_nodes = _find_nodes_by_type(tree.root_node, "lambda_expression")
        # Third lambda is (x, y) -> x + y
        assert len(lambda_nodes) == 3, "Expected exactly 3 lambdas in source"

        def _get_text(node):
            return node.text.decode("utf-8", errors="replace")

        lines = self._SRC.splitlines()
        result = extract_lambda_function(lambda_nodes[2], _get_text, lines)
        assert result is not None
        assert len(result.parameters) == 2, (
            f"Expected 2 parameters, got {result.parameters}"
        )


# ---------------------------------------------------------------------------
# TestStaticInitializerExtraction
# ---------------------------------------------------------------------------


class TestStaticInitializerExtraction:
    _SRC = """\
class InitDemo {
    static final int X;
    static {
        X = 1;
    }
    static {
        System.out.println("second static init");
    }
}
"""

    def test_static_initializer_extracted(self):
        """static { } produces Function(name='<static_initializer>', is_static=True)."""
        from tree_sitter_analyzer.languages._java_element import (
            extract_static_initializer,
        )

        tree, _ = _parse(self._SRC)
        nodes = _find_nodes_by_type(tree.root_node, "static_initializer")
        assert nodes, "No static_initializer nodes found"

        result = extract_static_initializer(nodes[0], self._SRC.splitlines())
        assert result is not None
        assert result.name == "<static_initializer>"
        assert result.is_static is True
        assert result.is_method is True

    def test_multiple_static_initializers(self):
        """Two static {} blocks yield two separate Function objects."""
        from tree_sitter_analyzer.languages._java_element import (
            extract_static_initializer,
        )

        tree, _ = _parse(self._SRC)
        nodes = _find_nodes_by_type(tree.root_node, "static_initializer")
        assert len(nodes) == 2, f"Expected exactly 2 static_initializer nodes, got {len(nodes)}"
        lines = self._SRC.splitlines()
        results = [extract_static_initializer(n, lines) for n in nodes]
        results = [r for r in results if r is not None]
        assert len(results) == 2
        # Each has a distinct start_line
        start_lines = {r.start_line for r in results}
        assert len(start_lines) == 2

    def test_static_initializer_via_extract_functions(self):
        """extract_functions() includes static initializers when traversal reaches them."""
        ext, tree = _make_extractor(self._SRC)
        functions = ext.extract_functions(tree, self._SRC)
        static_inits = [f for f in functions if f.name == "<static_initializer>"]
        # static_initializer is a direct child of class_body (a container),
        # so the Cursor API traversal WILL reach it.
        assert len(static_inits) == 2, (
            "Expected exactly 2 <static_initializer> Functions from extract_functions"
        )


# ---------------------------------------------------------------------------
# TestAnonymousClassExtraction
# ---------------------------------------------------------------------------


class TestAnonymousClassExtraction:
    _SRC = """\
class Demo {
    void run() {
        Runnable anon = new Runnable() {
            @Override
            public void run() { System.out.println("anonymous"); }
        };
    }
}
"""

    def test_anonymous_class_extracted(self):
        """object_creation_expression with class_body produces Class(class_type='anonymous').

        tree-sitter-java 0.23.5 represents anonymous class bodies as a
        ``class_body`` node that is a direct child of
        ``object_creation_expression``.  There is no distinct
        ``anonymous_class_body`` node type in this grammar version.
        """
        from tree_sitter_analyzer.languages._java_element import extract_anonymous_class

        tree, _ = _parse(self._SRC)
        # Find class_body nodes that are direct children of object_creation_expression
        oce_nodes = _find_nodes_by_type(tree.root_node, "object_creation_expression")
        anon_class_bodies = [
            child
            for oce in oce_nodes
            for child in oce.children
            if child.type == "class_body"
        ]
        assert anon_class_bodies, (
            "No class_body inside object_creation_expression found in parsed tree"
        )

        def _get_text(node):
            return node.text.decode("utf-8", errors="replace")

        result = extract_anonymous_class(
            anon_class_bodies[0], _get_text, self._SRC.splitlines(), ""
        )
        assert result is not None
        assert result.name == "<anonymous>"
        assert result.class_type == "anonymous"
        assert result.is_nested is True


# ---------------------------------------------------------------------------
# TestCompactConstructorExtraction
# ---------------------------------------------------------------------------


class TestCompactConstructorExtraction:
    _SRC = """\
record Range(int min, int max) {
    Range {
        if (min > max) throw new IllegalArgumentException("min > max");
    }
}
"""

    def test_compact_constructor_extracted(self):
        """compact_constructor_declaration yields Function(is_constructor=True)."""
        from tree_sitter_analyzer.languages._java_element import (
            extract_compact_constructor,
        )

        tree, _ = _parse(self._SRC)
        nodes = _find_nodes_by_type(tree.root_node, "compact_constructor_declaration")
        assert nodes, "No compact_constructor_declaration nodes found"

        def _get_text(node):
            return node.text.decode("utf-8", errors="replace")

        result = extract_compact_constructor(
            nodes[0], _get_text, self._SRC.splitlines()
        )
        assert result is not None
        assert result.is_constructor is True
        assert result.name == "Range"

    def test_compact_constructor_via_extract_functions(self):
        """extract_functions() returns compact constructors via _extract_method_optimized."""
        ext, tree = _make_extractor(self._SRC)
        functions = ext.extract_functions(tree, self._SRC)
        ctors = [f for f in functions if f.is_constructor]
        assert len(ctors) == 1, "Expected exactly one constructor Function (compact constructor)"
        names = [f.name for f in ctors]
        assert "Range" in names


# ---------------------------------------------------------------------------
# TestSealedClassPermits
# ---------------------------------------------------------------------------


class TestSealedClassPermits:
    _SRC = """\
sealed class Shape permits Circle, Rectangle {}
final class Circle extends Shape {}
final class Rectangle extends Shape {}
"""

    def test_permits_clause_in_interfaces(self):
        """sealed class permits Foo, Bar -> Class.interfaces includes ['Circle', 'Rectangle']."""
        ext, tree = _make_extractor(self._SRC)
        classes = ext.extract_classes(tree, self._SRC)
        sealed = next((c for c in classes if c.name == "Shape"), None)
        assert sealed is not None, "Shape class not found"
        assert "Circle" in sealed.interfaces, (
            f"Expected 'Circle' in interfaces, got {sealed.interfaces}"
        )
        assert "Rectangle" in sealed.interfaces, (
            f"Expected 'Rectangle' in interfaces, got {sealed.interfaces}"
        )


# ---------------------------------------------------------------------------
# TestGenericTypeExtraction
# ---------------------------------------------------------------------------


class TestGenericTypeExtraction:
    _SRC = """\
import java.util.Map;
import java.util.List;
class GenericDemo {
    public Map<String, List<Integer>> getMap() {
        return null;
    }
    Map<String, Integer> simpleMap;
}
"""

    def test_nested_generic_type_complete_text(self):
        """Return type Map<String, List<Integer>> is preserved as a complete string."""
        ext, tree = _make_extractor(self._SRC)
        functions = ext.extract_functions(tree, self._SRC)
        get_map = next((f for f in functions if f.name == "getMap"), None)
        assert get_map is not None, "getMap method not found"
        assert get_map.return_type == "Map<String, List<Integer>>", (
            f"Expected 'Map<String, List<Integer>>', got '{get_map.return_type}'"
        )

    def test_field_generic_type_complete_text(self):
        """Field type Map<String, Integer> is preserved as a complete string."""
        ext, tree = _make_extractor(self._SRC)
        variables = ext.extract_variables(tree, self._SRC)
        simple_map = next((v for v in variables if v.name == "simpleMap"), None)
        assert simple_map is not None, "simpleMap field not found"
        assert simple_map.variable_type == "Map<String, Integer>", (
            f"Expected 'Map<String, Integer>', got '{simple_map.variable_type}'"
        )


# ---------------------------------------------------------------------------
# TestJavadocAst
# ---------------------------------------------------------------------------


class TestJavadocAst:
    _SRC_WITH_JAVADOC = """\
class Documented {
    /** Returns the answer. */
    public int getAnswer() {
        return 42;
    }

    public String noDoc() {
        return "x";
    }
}
"""

    def test_javadoc_from_ast_sibling(self):
        """/** block directly before a method is returned as the docstring."""
        from tree_sitter_analyzer.languages._java_element import (
            _extract_javadoc_from_node,
        )

        tree, _ = _parse(self._SRC_WITH_JAVADOC)
        method_nodes = _find_nodes_by_type(tree.root_node, "method_declaration")
        assert method_nodes, "No method_declaration nodes found"

        def _get_text(node):
            return node.text.decode("utf-8", errors="replace")

        # Find getAnswer — it has a JavaDoc preceding it
        get_answer = next(
            (
                n
                for n in method_nodes
                if any(
                    c.type == "identifier"
                    and _get_text(c) == "getAnswer"
                    for c in n.children
                )
            ),
            None,
        )
        assert get_answer is not None, "getAnswer method not found in AST"
        doc = _extract_javadoc_from_node(get_answer, _get_text)
        assert doc is not None, "Expected JavaDoc for getAnswer but got None"
        assert "Returns the answer" in doc

    def test_javadoc_fallback_when_no_block_comment(self):
        """Methods without a preceding block_comment fall back to line-scan."""
        ext, tree = _make_extractor(self._SRC_WITH_JAVADOC)
        functions = ext.extract_functions(tree, self._SRC_WITH_JAVADOC)
        no_doc = next((f for f in functions if f.name == "noDoc"), None)
        assert no_doc is not None
        # noDoc has no JavaDoc — docstring should be None (line scan also finds nothing)
        assert no_doc.docstring is None


# ---------------------------------------------------------------------------
# TestAnonymousClassViaExtractClasses (C-1 end-to-end)
# ---------------------------------------------------------------------------


class TestAnonymousClassViaExtractClasses:
    """End-to-end test: extract_classes() must return anonymous classes.

    tree-sitter-java 0.23.5 does not emit an ``anonymous_class_body`` node;
    instead it emits a ``class_body`` child of ``object_creation_expression``.
    The extractor key must therefore match ``class_body`` and filter by parent
    type to avoid matching regular class bodies.
    """

    _SRC = """\
public class Outer {
    Runnable r = new Runnable() {
        public void run() {}
    };
}
"""

    def test_anonymous_class_via_extract_classes(self):
        """extract_classes() returns a Class with class_type='anonymous'."""
        ext, tree = _make_extractor(self._SRC)
        classes = ext.extract_classes(tree, self._SRC)
        anon = [c for c in classes if c.class_type == "anonymous"]
        assert anon, (
            f"No anonymous class found in extract_classes() output. "
            f"Got: {[c.name for c in classes]}"
        )
        assert anon[0].name == "<anonymous>"
        assert anon[0].is_nested is True

    def test_regular_classes_not_affected(self):
        """Regular class bodies are NOT extracted as anonymous classes."""
        ext, tree = _make_extractor(self._SRC)
        classes = ext.extract_classes(tree, self._SRC)
        outer = [c for c in classes if c.name == "Outer"]
        assert outer, "Outer class missing from extract_classes() output"
        assert outer[0].class_type == "class"


# ---------------------------------------------------------------------------
# TestModuleDeclarationExtraction (C-2 end-to-end)
# ---------------------------------------------------------------------------


class TestModuleDeclarationExtraction:
    """End-to-end test: extract_packages() must return module_declaration nodes.

    Java 9+ module-info.java files begin with a ``module_declaration`` node.
    The ``extract_java_packages`` helper must recognise this and return a
    :class:`Package` element with the module name.
    """

    _SRC_MODULE = "module com.example { }"

    def test_module_declaration_extracted(self):
        """extract_packages() returns Package(name='com.example') for module_declaration."""
        from tree_sitter_analyzer.languages.java_plugin import JavaPlugin

        plugin = JavaPlugin()
        lang = plugin.get_tree_sitter_language()
        assert lang is not None, "tree-sitter-java language not available"

        import tree_sitter

        parser = tree_sitter.Parser()
        parser.language = lang
        tree = parser.parse(self._SRC_MODULE.encode())

        from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor

        ext = JavaElementExtractor()
        packages = ext.extract_packages(tree, self._SRC_MODULE)
        names = [p.name for p in packages]
        assert "com.example" in names, (
            f"Expected 'com.example' in package names, got {names}"
        )

    def test_module_declaration_language_field(self):
        """Returned Package has language='java'."""
        from tree_sitter_analyzer.languages.java_plugin import (
            JavaElementExtractor,
            JavaPlugin,
        )

        plugin = JavaPlugin()
        lang = plugin.get_tree_sitter_language()
        if lang is None:
            pytest.skip("tree-sitter-java not available")

        import tree_sitter

        parser = tree_sitter.Parser()
        parser.language = lang
        tree = parser.parse(self._SRC_MODULE.encode())

        ext = JavaElementExtractor()
        packages = ext.extract_packages(tree, self._SRC_MODULE)
        module_pkgs = [p for p in packages if p.name == "com.example"]
        assert module_pkgs, "Module package not found"
        assert module_pkgs[0].language == "java"
