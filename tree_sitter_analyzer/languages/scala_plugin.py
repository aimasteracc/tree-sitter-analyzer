#!/usr/bin/env python3
"""
Scala Language Plugin

Provides Scala-specific parsing and element extraction functionality.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

    from ..core.request import AnalysisRequest
    from ..models import AnalysisResult

from ..encoding_utils import extract_text_slice, safe_encode
from ..models import Class, Expression, Function, Import, Package, Variable
from ..plugins.base import ElementExtractor, LanguagePlugin
from ..utils import log_debug, log_error
from ..utils.tree_sitter_compat import count_nodes_iterative
from .shared.traversal import node_range

# ---------------------------------------------------------------------------
# Cyclomatic complexity for Scala
# ---------------------------------------------------------------------------

_SCALA_DECISION_TYPES: frozenset[str] = frozenset(
    {
        "if_expression",
        "match_expression",
        "for_expression",
        "while_expression",
        "catch_clause",
        # A ``case`` guard (``case n if cond =>``) is an extra conditional
        # branch and is counted in addition to the construct.
        "guard",
        # NOTE: ``case_clause`` is deliberately NOT counted. ``match`` counts
        # once via ``match_expression`` and ``catch`` once via ``catch_clause``
        # (construct-once), so counting each ``case_clause`` would over-count
        # both a multi-arm ``match`` and the ``case`` inside a ``catch``. A
        # standalone partial-function ``case_block`` (no enclosing match/catch)
        # is counted once via _scala_is_standalone_case_block. See #1090.
    }
)

# A ``case_block`` that is NOT the body of a ``match``/``catch`` is a partial
# function literal (``{ case ... }``) — itself one branching construct.
_SCALA_CASE_BLOCK_CONSTRUCT_PARENTS: frozenset[str] = frozenset(
    {"match_expression", "catch_clause"}
)

_SCALA_LOGIC_OP_TOKENS: frozenset[str] = frozenset({"&&", "||"})


def _safe_children(node: Any) -> list[Any]:
    """Return children list from a tree-sitter node, empty list on any error."""
    try:
        children = getattr(node, "children", None)
        if children is None:
            return []
        return list(children)
    except (TypeError, AttributeError):
        return []


def calculate_scala_complexity(node: Any) -> int:
    """Return cyclomatic complexity for a Scala function node.

    complexity = 1 + decision_points.
    Decision points: if_expression, match_expression, for_expression,
    while_expression, catch_clause, case_clause (non-leaf nodes),
    and ``&&`` / ``||`` operator_identifier leaf tokens.
    """
    decisions = 0
    stack = [node]
    while stack:
        cur = stack.pop()
        children = _safe_children(cur)
        is_leaf = len(children) == 0
        node_type = getattr(cur, "type", None)
        if not is_leaf and node_type in _SCALA_DECISION_TYPES:
            decisions += 1
        elif not is_leaf and node_type == "case_block":
            # Count a standalone partial-function ``{ case ... }`` once; the
            # ``case_block`` under a match/catch is already covered by
            # ``match_expression`` / ``catch_clause``.
            parent = getattr(cur, "parent", None)
            if (
                parent is None
                or getattr(parent, "type", None)
                not in _SCALA_CASE_BLOCK_CONSTRUCT_PARENTS
            ):
                decisions += 1
        elif is_leaf and node_type == "operator_identifier":
            try:
                text = cur.text.decode("utf-8") if cur.text else ""
            except (AttributeError, UnicodeDecodeError):
                text = ""
            if text in _SCALA_LOGIC_OP_TOKENS:
                decisions += 1
        stack.extend(children)
    return 1 + decisions


_SCALA_ELEMENT_KEYS: tuple[str, ...] = (
    "functions",
    "classes",
    "variables",
    "imports",
    "packages",
    "comments",
    "annotations",
)


def _scala_empty_result(file_path: str, file_content: str) -> AnalysisResult:
    """Build an empty ``AnalysisResult`` when the tree-sitter language is missing."""
    from ..models import AnalysisResult

    return AnalysisResult(
        file_path=file_path,
        language="scala",
        # P1: splitlines() matches wc -l (split("\n") over-counts by 1
        # when file ends with trailing \n)
        line_count=len(file_content.splitlines()),
        elements=[],
        source_code=file_content,
    )


def _scala_error_result(file_path: str, exc: Exception) -> AnalysisResult:
    """Build the failure-path ``AnalysisResult`` used by the ``except`` arm."""
    from ..models import AnalysisResult

    return AnalysisResult(
        file_path=file_path,
        language="scala",
        line_count=0,
        elements=[],
        source_code="",
        error_message=str(exc),
        success=False,
    )


def _make_scala_parser(language: Any) -> Any:
    """Construct a ``tree_sitter.Parser`` bound to ``language`` across API shapes.

    Tree-sitter 0.20 used ``parser.set_language(lang)``; 0.21 added the
    ``parser.language`` property setter; 0.23 made the constructor accept
    the language directly. Probe each in order; fall back to the
    constructor form if neither attribute exists.
    """
    import tree_sitter

    parser = tree_sitter.Parser()
    if hasattr(parser, "set_language"):
        parser.set_language(language)
        return parser
    if hasattr(parser, "language"):
        parser.language = language
        return parser
    return tree_sitter.Parser(language)


def _flatten_scala_elements(elements_dict: dict[str, list[Any]]) -> list[Any]:
    """Concatenate per-kind element lists in the canonical Scala order."""
    flat: list[Any] = []
    for key in _SCALA_ELEMENT_KEYS:
        flat.extend(elements_dict.get(key, []))
    return flat


def _parse_scaladoc_text(comment_text: str) -> str | None:
    """Convert raw ``/** ... */`` scaladoc to the cleaned multi-line string.

    Returns ``None`` when the block isn't a Scaladoc comment (must start
    with ``/**`` but not ``/***``) or yields no non-empty lines. Strips
    the opening ``/**`` and closing ``*/``, then trims each line and
    removes a leading ``*`` for the canonical multi-line Scaladoc shape.

    r37dw (dogfood): lifted from ``_extract_docstring`` to flatten the
    inner for/if chain from depth 6 to a pure transform.
    """
    if not comment_text.startswith("/**") or comment_text.startswith("/***"):
        return None
    content = comment_text[3:]
    if content.endswith("*/"):
        content = content[:-2]
    cleaned_lines: list[str] = []
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("*"):
            stripped = stripped[1:].strip()
        if stripped:
            cleaned_lines.append(stripped)
    if not cleaned_lines:
        return None
    return "\n".join(cleaned_lines)


class ScalaElementExtractor(ElementExtractor):
    """Scala-specific element extractor"""

    def __init__(self) -> None:
        """Initialize the Scala element extractor."""
        self.current_package: str = ""
        self.current_file: str = ""
        self.source_code: str = ""
        self.content_lines: list[str] = []
        self._node_text_cache: dict[tuple[int, int], str] = {}

    def extract_functions(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Function]:
        """Extract Scala function definitions and declarations"""
        self._setup(source_code)

        functions: list[Function] = []

        self._traverse_functions_with_context(tree.root_node, functions, None, None)

        log_debug(f"Extracted {len(functions)} Scala functions")
        return functions

    def extract_classes(self, tree: tree_sitter.Tree, source_code: str) -> list[Class]:
        """Extract Scala class, object, trait, enum, given, and type definitions."""
        self._setup(source_code)

        # Extract package first
        self._extract_package(tree.root_node)

        classes: list[Class] = []
        self._traverse_classes_with_context(tree.root_node, classes, parent_class=None)

        log_debug(f"Extracted {len(classes)} Scala classes/objects/traits")
        return classes

    def extract_variables(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Variable]:
        """Extract Scala val and var definitions"""
        self._setup(source_code)

        variables: list[Variable] = []

        extractors = {
            "val_definition": self._extract_val,
            "var_definition": self._extract_var,
        }

        self._traverse_and_extract(
            tree.root_node,
            extractors,
            variables,
        )

        log_debug(f"Extracted {len(variables)} Scala val/var definitions")
        return variables

    def extract_imports(self, tree: tree_sitter.Tree, source_code: str) -> list[Import]:
        """Extract Scala imports"""
        self._setup(source_code)

        imports: list[Import] = []

        extractors = {
            "import_declaration": self._extract_import,
        }

        self._traverse_and_extract(
            tree.root_node,
            extractors,
            imports,
        )

        log_debug(f"Extracted {len(imports)} Scala imports")
        return imports

    def extract_packages(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Package]:
        """Extract Scala package"""
        self._setup(source_code)

        # r37dt (dogfood): mirror of kotlin r37ds — flatten nesting 6 → 3
        # via _find_package_clause_node helper.
        packages: list[Package] = []
        self._extract_package(tree.root_node)
        if not self.current_package:
            return packages
        package_node = self._find_package_clause_node(tree.root_node)
        if package_node is None:
            return packages
        _pkg_start, _pkg_end = node_range(package_node)
        packages.append(
            Package(
                name=self.current_package,
                start_line=_pkg_start,
                end_line=_pkg_end,
                raw_text=self._get_node_text(package_node),
                language="scala",
            )
        )
        return packages

    @staticmethod
    def _find_package_clause_node(
        root_node: tree_sitter.Node,
    ) -> tree_sitter.Node | None:
        """Return the first ``package_clause`` child or ``None``."""
        for child in root_node.children:
            if child.type == "package_clause":
                return child
        return None

    def extract_comments(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Expression]:
        """Extract Scala block comments"""
        self._setup(source_code)

        comments: list[Expression] = []

        extractors = {
            "block_comment": self._extract_comment,
        }

        self._traverse_and_extract(tree.root_node, extractors, comments)

        log_debug(f"Extracted {len(comments)} Scala comments")
        return comments

    def extract_annotations(
        self, tree: tree_sitter.Tree, source_code: str
    ) -> list[Expression]:
        """Extract Scala annotations"""
        self._setup(source_code)

        annotations: list[Expression] = []

        extractors = {
            "annotation": self._extract_annotation,
        }

        self._traverse_and_extract(tree.root_node, extractors, annotations)

        log_debug(f"Extracted {len(annotations)} Scala annotations")
        return annotations

    def _setup(self, source_code: str) -> None:
        """Set source code and reset caches — called at the top of every extract_* method."""
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()

    def _reset_caches(self) -> None:
        """Reset performance caches"""
        self._node_text_cache.clear()
        if not self.source_code:
            self.current_package = ""

    def _traverse_and_extract(
        self,
        node: tree_sitter.Node,
        extractors: dict[str, Any],
        results: list[Any],
    ) -> None:
        """Iterative traversal to find and extract elements (stack-safe)."""
        stack = [node]
        while stack:
            current = stack.pop()
            if current.type in extractors:
                element = extractors[current.type](current)
                if element:
                    results.append(element)
            stack.extend(reversed(current.children))

    def _extract_package(self, node: tree_sitter.Node) -> None:
        """Extract package declaration from package_clause.

        r37dw (dogfood): flatten nesting 6 → 3 via
        ``_scala_package_name_from_clause`` (mirror of kotlin r37ds).
        """
        for child in node.children:
            if child.type != "package_clause":
                continue
            pkg_name = self._scala_package_name_from_clause(child)
            if pkg_name is not None:
                self.current_package = pkg_name
                return

    def _scala_package_name_from_clause(
        self, package_clause: tree_sitter.Node
    ) -> str | None:
        """Return the package name string from a ``package_clause`` node.

        Scala's grammar emits ``package_identifier`` for qualified names
        (``a.b.c``) or plain ``identifier`` for top-level packages; some
        forks fall back to a node whose ``type`` contains the substring
        ``"identifier"``. We accept any of those at the first match.
        """
        for grandchild in package_clause.children:
            if grandchild.type in ("package_identifier", "identifier"):
                return self._get_node_text(grandchild)
            if "identifier" in grandchild.type:
                return self._get_node_text(grandchild)
        return None

    # -----------------------------------------------------------------------
    # Context-aware class traversal (Bug #762 + #764)
    # -----------------------------------------------------------------------

    #: Node types that introduce a new named scope (class / object / trait /
    #: enum).  When the traversal descends into one of these it updates the
    #: running ``parent_class`` so that nested constructs (given, type alias,
    #: enum cases) inherit the right owner name.
    _SCOPE_INTRODUCING_TYPES: frozenset[str] = frozenset(
        {
            "class_definition",
            "object_definition",
            "trait_definition",
            "enum_definition",
        }
    )

    def _traverse_classes_with_context(
        self,
        node: tree_sitter.Node,
        results: list[Class],
        parent_class: str | None,
    ) -> None:
        """DFS traversal that extracts all class-like constructs with context.

        Unlike the generic ``_traverse_and_extract`` this walk keeps track of
        the innermost enclosing named scope so that nested ``given`` /
        ``type`` / enum-case nodes can record their ``parent_class``.

        Stack entries: ``(node, parent_class_name)``.
        """
        stack: list[tuple[tree_sitter.Node, str | None]] = [(node, parent_class)]
        while stack:
            current, current_parent = stack.pop()
            node_type = current.type

            if node_type in (
                "class_definition",
                "object_definition",
                "trait_definition",
            ):
                cls = self._extract_class_like_with_parent(
                    current, node_type.split("_")[0], current_parent
                )
                if cls:
                    results.append(cls)
                # Descend with this class as the new parent scope.
                new_parent = cls.name if cls else current_parent
                for child in reversed(current.children):
                    stack.append((child, new_parent))

            elif node_type == "enum_definition":
                # Emit the enum itself, then its cases.
                self._extract_enum_with_cases(current, current_parent, results)
                # Descend into the enum body for further nested defs (rare
                # but possible), still under the enum's name as parent.
                enum_name = self._scala_class_like_name(current)
                for child in reversed(current.children):
                    if child.type == "enum_body":
                        for sub in reversed(child.children):
                            stack.append((sub, enum_name))

            elif node_type == "given_definition":
                # #764: given inside an object/trait — carry parent_class.
                cls = self._extract_given(current, current_parent)
                if cls:
                    results.append(cls)

            elif node_type == "type_definition":
                # #764: type alias inside an object/trait — carry parent_class.
                cls = self._extract_type_alias(current, current_parent)
                if cls:
                    results.append(cls)

            elif node_type == "extension_definition":
                cls = self._extract_extension(current, current_parent)
                if cls:
                    results.append(cls)

            elif node_type in ("function_definition", "function_declaration"):
                continue

            else:
                # Generic node: descend preserving context.
                for child in reversed(current.children):
                    stack.append((child, current_parent))

    def _traverse_functions_with_context(
        self,
        node: tree_sitter.Node,
        results: list[Function],
        parent_class: str | None,
        receiver_type: str | None,
    ) -> None:
        stack: list[tuple[tree_sitter.Node, str | None, str | None]] = [
            (node, parent_class, receiver_type)
        ]
        while stack:
            current, current_parent, current_receiver = stack.pop()
            node_type = current.type

            if node_type in (
                "class_definition",
                "object_definition",
                "trait_definition",
                "enum_definition",
            ):
                new_parent = self._scala_class_like_name(current)
                for child in reversed(current.children):
                    stack.append((child, new_parent, None))
                continue

            if node_type == "given_definition":
                new_parent = self._scala_given_name(current)
                for child in reversed(current.children):
                    stack.append((child, new_parent, None))
                continue

            if node_type == "extension_definition":
                new_receiver = self._scala_extension_receiver_type(current)
                for child in reversed(current.children):
                    stack.append((child, current_parent, new_receiver))
                continue

            if node_type == "function_definition":
                fn = self._extract_function(current)
                if fn:
                    fn.parent_class = current_parent
                    fn.receiver_type = current_receiver
                    results.append(fn)
                for child in reversed(current.children):
                    stack.append((child, current_parent, current_receiver))
                continue

            if node_type == "function_declaration":
                fn = self._extract_function_declaration(current)
                if fn:
                    fn.parent_class = current_parent
                    fn.receiver_type = current_receiver
                    results.append(fn)
                for child in reversed(current.children):
                    stack.append((child, current_parent, current_receiver))
                continue

            for child in reversed(current.children):
                stack.append((child, current_parent, current_receiver))

    def _extract_class_like_with_parent(
        self,
        node: tree_sitter.Node,
        kind: str,
        parent_class: str | None,
    ) -> Class | None:
        """Like ``_extract_class_like`` but also populates ``parent_class``."""
        cls = self._extract_class_like(node, kind)
        if cls is not None and parent_class is not None:
            cls.parent_class = parent_class
        return cls

    def _extract_enum_with_cases(
        self,
        node: tree_sitter.Node,
        parent_class: str | None,
        results: list[Class],
    ) -> None:
        """Emit the enum itself and each enum case as enum_member."""
        enum_name = self._scala_class_like_name(node)
        superclass, interfaces = self._extract_scala_extends_clause(node)
        results.append(
            self._build_scala_class(
                node,
                enum_name,
                "enum",
                parent_class,
                superclass=superclass,
                interfaces=interfaces,
                docstring=self._extract_docstring(node),
            )
        )
        # Walk enum_body → enum_case_definitions → simple_enum_case / full_enum_case
        for child in node.children:
            if child.type != "enum_body":
                continue
            for case_defs in child.children:
                if case_defs.type != "enum_case_definitions":
                    continue
                for case_node in case_defs.children:
                    if case_node.type not in ("simple_enum_case", "full_enum_case"):
                        continue
                    case_superclass, case_interfaces = (
                        self._extract_scala_extends_clause(case_node)
                    )
                    results.append(
                        self._build_scala_class(
                            case_node,
                            self._scala_class_like_name(case_node),
                            "enum_member",
                            enum_name,
                            superclass=case_superclass,
                            interfaces=case_interfaces,
                        )
                    )

    def _build_scala_class(
        self,
        node: tree_sitter.Node,
        name: str,
        class_type: str,
        parent_class: str | None,
        *,
        superclass: str | None = None,
        interfaces: list[str] | None = None,
        docstring: str | None = None,
    ) -> Class:
        """Build a Class element from common Scala fields."""
        start_line, end_line = node_range(node)
        return Class(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=self._get_node_text(node),
            language="scala",
            class_type=class_type,
            visibility=self._scala_visibility(node),
            modifiers=self._scala_modifiers(node),
            package_name=self.current_package,
            parent_class=parent_class,
            superclass=superclass,
            interfaces=interfaces or [],
            docstring=docstring,
        )

    def _extract_given(
        self,
        node: tree_sitter.Node,
        parent_class: str | None,
    ) -> Class | None:
        """Extract a ``given_definition`` as a Class with class_type='given'."""
        try:
            return self._build_scala_class(
                node, self._scala_given_name(node), "given", parent_class
            )
        except Exception as e:
            log_error(f"Error extracting Scala given: {e}")
            return None

    def _extract_type_alias(
        self,
        node: tree_sitter.Node,
        parent_class: str | None,
    ) -> Class | None:
        """Extract a ``type_definition`` as a Class with class_type='type_alias'."""
        try:
            name = next(
                (
                    self._get_node_text(c)
                    for c in node.children
                    if c.type == "type_identifier"
                ),
                "unknown_type",
            )
            class_type = (
                "type_alias"
                if self._scala_type_has_alias_target(node)
                else "type_member"
            )
            return self._build_scala_class(node, name, class_type, parent_class)
        except Exception as e:
            log_error(f"Error extracting Scala type alias: {e}")
            return None

    def _extract_extension(
        self,
        node: tree_sitter.Node,
        parent_class: str | None,
    ) -> Class | None:
        """Extract an ``extension_definition`` as a Class with class_type='extension'."""
        try:
            receiver_type = self._scala_extension_receiver_type(node)
            start_line, _ = node_range(node)
            suffix = receiver_type or str(start_line)
            return self._build_scala_class(
                node, f"extension[{suffix}]", "extension", parent_class
            )
        except Exception as e:
            log_error(f"Error extracting Scala extension: {e}")
            return None

    def _extract_function(self, node: tree_sitter.Node) -> Function | None:
        """Extract function definition (with body)"""
        return self._extract_function_common(node)

    def _extract_function_declaration(self, node: tree_sitter.Node) -> Function | None:
        """Extract function declaration (abstract, without body)"""
        return self._extract_function_common(node)

    def _extract_function_common(self, node: tree_sitter.Node) -> Function | None:
        """Common extraction logic for Scala functions.

        r37dw (dogfood): flatten name-fallback (depth 6) + return-type
        scan + visibility scan into focused helpers.
        """
        try:
            name = self._scala_function_name(node)
            start_line, end_line = node_range(node)
            parameters: list[str] = []
            for child in node.children:
                if "parameter" in child.type:
                    parameters.extend(self._extract_parameters(child))
            return_type = self._scala_return_type(node)
            visibility = self._scala_visibility(node)

            # Extract docstring
            docstring = self._extract_docstring(node)
            raw_text = self._get_node_text(node)

            return Function(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="scala",
                parameters=parameters,
                return_type=return_type,
                visibility=visibility,
                modifiers=self._scala_modifiers(node),
                docstring=docstring,
                is_constructor=name == "this",
                complexity_score=calculate_scala_complexity(node),
            )

        except Exception as e:
            log_error(f"Error extracting Scala function: {e}")
            return None

    def _scala_class_like_name(self, node: tree_sitter.Node) -> str:
        """Return class/object/trait name, falling back to identifier scan."""
        name_node = node.child_by_field_name("name")
        if name_node:
            return self._get_node_text(name_node)
        for child in node.children:
            if child.type in ("identifier", "type_identifier"):
                return self._get_node_text(child)
        return "anonymous"

    def _scala_function_name(self, node: tree_sitter.Node) -> str:
        """Return the function name, falling back to the first identifier child.

        r37dw (dogfood): lifted from ``_extract_function_common`` to
        flatten its name-resolution branch from depth 6 to 3.
        """
        name_node = node.child_by_field_name("name")
        if name_node:
            return self._get_node_text(name_node)
        for child in node.children:
            if child.type == "identifier":
                return self._get_node_text(child)
        return "anonymous"

    def _scala_return_type(self, node: tree_sitter.Node) -> str:
        """Return the type annotation after a ``:`` child, default ``Unit``.

        For variable declarations use ``_scala_type_after_colon(node, "Inferred")``
        instead — function return types want ``Unit`` as the missing-type sentinel.

        Issue #594: ``def get(key: String) = "legacy"`` must not claim
        Unit — the expression body infers the type. Full inference is a
        non-goal; pin trivial literals, otherwise emit "" (unknown,
        matching the Go plugin's absent-return-type convention). Block
        bodies / abstract defs without an explicit type really are
        Unit-defaulted — keep. Mirrors the Kotlin fix for #591/#593.
        """
        if any(child.type == ":" for child in node.children):
            return self._scala_type_after_colon(node, "Unit")
        inferred = self._scala_expression_body_type(node)
        if inferred is not None:
            return inferred
        return "Unit"

    def _scala_expression_body_type(self, node: tree_sitter.Node) -> str | None:
        """Infer the return type of an expression-body def (issue #594).

        Returns:
            * ``None`` — no expression body (block body or abstract def);
              caller keeps the ``Unit`` default, which is correct there.
            * a pinned literal type (``String``/``Int``/``Boolean``/``Double``)
              for trivial literal bodies (Scala's ``string`` node covers
              raw triple-quoted strings too — live-verified node shapes).
            * ``""`` (unknown) for any other expression body — honest "no
              claim", never a fabricated ``Unit``.
        """
        children = node.children
        expr = None
        for i, child in enumerate(children):
            if child.type == "=":
                if i + 1 >= len(children):
                    return ""  # malformed: '=' with nothing after it
                expr = children[i + 1]
                break
        if expr is None:
            return None  # block body or abstract def → Unit default is correct
        if expr.type == "indented_block":
            # `def f =\n  "x"` wraps the RHS in an indented_block (Codex P2
            # on #597); a single-expression block is the same literal case.
            named = [c for c in expr.children if c.is_named and c.type != "comment"]
            if len(named) != 1:
                return ""
            expr = named[0]
        if expr.type == "string":
            return "String"
        if expr.type == "floating_point_literal":
            return "Double"
        if expr.type == "integer_literal":
            # Signed decimal literals (`-1`) are a single integer_literal node
            # and infer Int (Codex P2 on #597); 42L / 0xFF etc. stay unknown.
            text = self._get_node_text(expr)
            digits = text[1:] if text[:1] in ("-", "+") else text
            return "Int" if digits.isdigit() else ""
        if expr.type == "boolean_literal":
            return "Boolean"
        return ""

    def _scala_type_after_colon(self, node: tree_sitter.Node, default: str) -> str:
        """Scan ``node.children`` for ``:`` and return the next sibling text.

        Returns ``default`` when no ``:`` child exists or it's the last
        child (caller picks ``"Unit"`` for functions, ``"Inferred"`` for
        val/var declarations to match Scala-language conventions).
        """
        children = node.children
        for i, child in enumerate(children):
            if child.type == ":":
                if i + 1 < len(children):
                    return self._get_node_text(children[i + 1])
                return default
        return default

    def _scala_visibility(self, node: tree_sitter.Node) -> str:
        """Return ``private`` / ``protected`` / ``public`` from a modifiers child.

        Scans for the first ``modifiers`` child and checks its text for
        the explicit keywords. Defaults to ``public`` when no modifiers
        node is present or contains neither keyword.

        Qualified-access modifiers such as ``private[pkg]`` /
        ``protected[this]`` are emitted by ``_scala_modifiers`` as the
        single literal token ``private[pkg]`` (not a bare ``private``), so
        match the keyword as a prefix rather than by exact membership —
        otherwise ``private[pkg] class Secret`` is misreported as public.
        """
        modifiers = self._scala_modifiers(node)
        if any(m == "private" or m.startswith("private[") for m in modifiers):
            return "private"
        if any(m == "protected" or m.startswith("protected[") for m in modifiers):
            return "protected"
        return "public"

    def _scala_modifiers(self, node: tree_sitter.Node) -> list[str]:
        modifiers: list[str] = []
        for child in node.children:
            if child.type != "modifiers":
                continue
            for modifier in child.children:
                text = self._get_node_text(modifier)
                if text:
                    modifiers.append(text)
            if not modifiers:
                text = self._get_node_text(child)
                if text:
                    modifiers.extend(text.split())
            break
        return modifiers

    def _scala_given_name(self, node: tree_sitter.Node) -> str:
        name_node = node.child_by_field_name("name")
        if name_node:
            return self._get_node_text(name_node)
        for child in node.children:
            if child.type == "identifier":
                return self._get_node_text(child)
        type_name = self._scala_given_type_name(node)
        if type_name:
            return f"given {type_name}"
        return f"anonymous_given_{node.start_point[0] + 1}"

    def _scala_given_type_name(self, node: tree_sitter.Node) -> str | None:
        for child in node.children:
            if child.type in (
                "generic_type",
                "type_identifier",
                "stable_type_identifier",
                "tuple_type",
                "function_type",
            ):
                return self._get_node_text(child)
        return None

    @staticmethod
    def _scala_type_has_alias_target(node: tree_sitter.Node) -> bool:
        return any(child.type == "=" for child in node.children)

    def _scala_extension_receiver_type(self, node: tree_sitter.Node) -> str | None:
        for child in node.children:
            if child.type != "parameters":
                continue
            params = self._extract_parameters(child)
            if not params:
                return None
            first = params[0]
            if ":" in first:
                return first.split(":", 1)[1].strip()
            return first
        return None

    def _extract_parameters(self, param_node: tree_sitter.Node) -> list[str]:
        """Extract parameters from a parameter clause.

        r37dw (dogfood): flatten nesting 6 → 3 via _scala_parameter_pair
        (mirror of kotlin r37dt).
        """
        parameters: list[str] = []
        for child in param_node.children:
            if child.type in ("parameter", "class_parameter"):
                param_name, param_type = self._scala_parameter_pair(child)
                if param_name:
                    type_str = param_type or "Any"
                    parameters.append(f"{param_name}: {type_str}")
            elif child.type == "parameters" or "parameter" in child.type:
                # Recursively extract nested parameters
                parameters.extend(self._extract_parameters(child))
        return parameters

    def _scala_parameter_pair(
        self, parameter_node: tree_sitter.Node
    ) -> tuple[str, str]:
        """Return ``(name, type)`` from a Scala ``parameter`` / ``class_parameter``.

        Recognises ``identifier`` for the name and any node whose type
        contains ``"type"`` (including ``type_identifier``) for the type.
        Empty strings when either side is missing; caller fills ``"Any"``
        for blank types to match Scala's defaulting.
        """
        param_name = ""
        param_type = ""
        for grandchild in parameter_node.children:
            if grandchild.type == "identifier":
                param_name = self._get_node_text(grandchild)
            elif "type" in grandchild.type or grandchild.type == "type_identifier":
                param_type = self._get_node_text(grandchild)
        return param_name, param_type

    def _extract_scala_extends_clause(
        self, node: tree_sitter.Node
    ) -> tuple[str | None, list[str]]:
        """Return ``(superclass, interfaces)`` from a class/object/trait node.

        Issue #562: ``_extract_class_like`` never read ``extends_clause`` so
        all Scala classes showed empty inheritance.

        Grammar shape (from live AST dump):
            extends_clause
              'extends'
              type_identifier   ← superclass (first one, before any 'with')
              arguments?        ← constructor args (skipped)
              'with'
              type_identifier   ← mixed-in trait
              ...

        The first ``type_identifier`` child of the clause (with no preceding
        ``with``) is the superclass.  Each ``type_identifier`` following a
        ``with`` keyword is a mixed-in trait.
        """
        superclass: str | None = None
        interfaces: list[str] = []

        for child in node.children:
            if child.type != "extends_clause":
                continue
            seen_with = False
            for sub in child.children:
                if sub.type in ("extends", "arguments"):
                    continue
                if sub.type == "with":
                    seen_with = True
                    continue
                if sub.type in (
                    "type_identifier",
                    # Codex P2 on #585: Base[String] parses as generic_type,
                    # pkg.M as stable_type_identifier — accept all three and
                    # strip type arguments from the generic form.
                    "generic_type",
                    "stable_type_identifier",
                ):
                    raw = self._get_node_text(sub)
                    name_text = raw.split("[")[0].strip()
                    if superclass is None and not seen_with:
                        superclass = name_text
                    else:
                        interfaces.append(name_text)
            break  # at most one extends_clause per declaration

        return superclass, interfaces

    def _extract_class_like(self, node: tree_sitter.Node, kind: str) -> Class | None:
        """Generic extraction for class/object/trait (issue #562: includes extends)."""
        try:
            superclass, interfaces = self._extract_scala_extends_clause(node)
            return self._build_scala_class(
                node,
                self._scala_class_like_name(node),
                kind,
                None,
                superclass=superclass,
                interfaces=interfaces,
                docstring=self._extract_docstring(node),
            )
        except Exception as e:
            log_error(f"Error extracting Scala {kind}: {e}")
            return None

    def _extract_val(self, node: tree_sitter.Node) -> Variable | None:
        """Extract val definition (immutable)"""
        return self._extract_variable(node, is_val=True)

    def _extract_var(self, node: tree_sitter.Node) -> Variable | None:
        """Extract var definition (mutable)"""
        return self._extract_variable(node, is_val=False)

    def _extract_variable(
        self, node: tree_sitter.Node, is_val: bool = True
    ) -> Variable | None:
        """Common extraction logic for val/var"""
        try:
            # Extract name (handles plain ``identifier`` and ``pattern_list``
            # forms). r37ca: extracted to drop ``_extract_variable`` nesting
            # from 7 to ≤3.
            name = self._extract_scala_variable_name(node)

            start_line, end_line = node_range(node)

            # r37dw (dogfood): reuse _scala_type_after_colon + _scala_visibility.
            var_type = self._scala_type_after_colon(node, "Inferred")
            visibility = self._scala_visibility(node)
            docstring = self._extract_docstring(node)
            raw_text = self._get_node_text(node)

            var = Variable(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="scala",
                variable_type=var_type,
                visibility=visibility,
                docstring=docstring,
            )
            var.is_val = is_val
            var.is_var = not is_val

            return var

        except Exception as e:
            log_error(f"Error extracting Scala variable: {e}")
            return None

    def _extract_scala_variable_name(self, node: tree_sitter.Node) -> str:
        """Scala val/var binds a name either as a direct ``identifier`` child
        or as the first identifier inside a ``pattern_list``.

        r37ca (dogfood): extracted from ``_extract_variable`` to flatten its
        7-deep nesting (for-elif-for-if-break).
        r37dw: pattern_list inner scan moved into ``_first_identifier_in``
        helper to drop nesting from 6 to 3.
        """
        for child in node.children:
            if child.type == "identifier":
                return str(self._get_node_text(child))
            if child.type == "pattern_list":
                inner = self._first_identifier_in(child)
                if inner is not None:
                    return inner
        return "unknown"

    def _first_identifier_in(self, node: tree_sitter.Node) -> str | None:
        """Return the first ``identifier`` child's text or ``None``."""
        for grandchild in node.children:
            if grandchild.type == "identifier":
                return str(self._get_node_text(grandchild))
        return None

    def _last_nearby_block_comment(
        self, node: tree_sitter.Node
    ) -> tree_sitter.Node | None:
        """Return the last ``block_comment`` sibling within 2 lines of ``node``.

        Walks left-to-right through ``node.parent.children`` up to (but
        not including) ``node`` itself; tracks the most recent
        ``block_comment`` and only returns it when it ends ≤ 2 lines
        before ``node`` starts. ``None`` when no eligible comment exists
        (Scaladoc must be adjacent for the binding to be unambiguous).
        """
        last_close: tree_sitter.Node | None = None
        if node.parent is None:
            return None
        for sibling in node.parent.children:
            if sibling == node:
                break
            if sibling.type == "block_comment":
                if node.start_point[0] - sibling.end_point[0] <= 2:
                    last_close = sibling
        return last_close

    def _extract_import(self, node: tree_sitter.Node) -> Import | None:
        """Extract import declaration"""
        try:
            raw_text = self._get_node_text(node)
            start_line, end_line = node_range(node)

            # Parse import path
            # import_declaration -> 'import' import_expression
            name = "unknown"
            for child in node.children:
                if child.type != "import":
                    # Take the import expression text
                    name = self._get_node_text(child)
                    break

            return Import(
                name=name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="scala",
                import_statement=raw_text,
            )
        except Exception as e:
            log_error(f"Error extracting Scala import: {e}")
            return None

    def _extract_comment(self, node: tree_sitter.Node) -> Expression | None:
        """Extract Scala block comment"""
        try:
            raw_text = self._get_node_text(node)
            start_line, end_line = node_range(node)

            # Get preview (first 50 chars)
            preview = raw_text[:50] if len(raw_text) > 50 else raw_text

            return Expression(
                name="block_comment",
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="scala",
                expression_kind="block_comment",
                preview=preview,
            )
        except Exception as e:
            log_error(f"Error extracting Scala comment: {e}")
            return None

    def _extract_annotation(self, node: tree_sitter.Node) -> Expression | None:
        """Extract Scala annotation"""
        try:
            raw_text = self._get_node_text(node)
            start_line, end_line = node_range(node)

            # Extract annotation name from the tree
            # annotation -> @ stable_type_identifier
            annotation_name = "unknown"
            for child in node.children:
                if child.type in (
                    "stable_type_identifier",
                    "type_identifier",
                    "identifier",
                ):
                    annotation_name = self._get_node_text(child)
                    break
                # Handle simple identifier after @
                if child.type == "identifier":
                    annotation_name = self._get_node_text(child)
                    break

            return Expression(
                name=annotation_name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                language="scala",
                expression_kind="annotation",
                node_type="annotation",
            )
        except Exception as e:
            log_error(f"Error extracting Scala annotation: {e}")
            return None

    def _get_node_text(self, node: tree_sitter.Node) -> str:
        """Get node text with caching using position-based keys"""
        cache_key = (node.start_byte, node.end_byte)
        if cache_key in self._node_text_cache:
            return self._node_text_cache[cache_key]

        try:
            start_byte = node.start_byte
            end_byte = node.end_byte
            encoding = "utf-8"
            content_bytes = safe_encode("\n".join(self.content_lines), encoding)
            text = extract_text_slice(content_bytes, start_byte, end_byte, encoding)
            self._node_text_cache[cache_key] = text
            return text
        except Exception:
            return ""

    def _extract_docstring(self, node: tree_sitter.Node) -> str | None:
        """Extract Scaladoc comments (/** ... */)"""
        # Scala uses /** ... */ for documentation comments
        # Look for block_comment nodes that immediately precede this node
        if not node.parent:
            return None

        # Find the immediately preceding block_comment sibling
        prev_comment = None
        prev_sibling = None

        for sibling in node.parent.children:
            if sibling == node:
                break
            prev_sibling = sibling

        # r37dw (dogfood): flatten nesting 6 → 3 via _last_nearby_block_comment.
        if prev_sibling and prev_sibling.type == "block_comment":
            prev_comment = prev_sibling
        elif prev_sibling and prev_sibling.type != "block_comment":
            prev_comment = self._last_nearby_block_comment(node)

        # r37dw (dogfood): scaladoc parsing抽到 _parse_scaladoc_text.
        if prev_comment is None:
            return None
        return _parse_scaladoc_text(self._get_node_text(prev_comment))


class ScalaPlugin(LanguagePlugin):
    """Scala language plugin implementation"""

    def __init__(self) -> None:
        """Initialize the Scala language plugin."""
        super().__init__()
        self.extractor = ScalaElementExtractor()
        self.language = "scala"
        self.supported_extensions = self.get_file_extensions()
        self._cached_language: Any | None = None

    def get_language_name(self) -> str:
        """Get the language name."""
        return "scala"

    def get_file_extensions(self) -> list[str]:
        """Get supported file extensions."""
        return [".scala", ".sc"]

    def create_extractor(self) -> ElementExtractor:
        """Create a new element extractor instance."""
        return ScalaElementExtractor()

    async def analyze_file(
        self, file_path: str, request: AnalysisRequest
    ) -> AnalysisResult:
        """Analyze Scala code and return structured results.

        r37ed (dogfood): 85 lines → ~15 of orchestration. Per-phase helpers
        (``_scala_empty_result`` / ``_make_scala_parser`` / ``_flatten_scala_elements``
        / ``_scala_analysis_result`` / ``_scala_error_result``) own the
        individual steps; this body is just dispatch.
        """

        try:
            from ..encoding_utils import read_file_safe

            file_content, _detected_encoding = read_file_safe(file_path)

            language = self.get_tree_sitter_language()
            if language is None:
                return _scala_empty_result(file_path, file_content)

            parser = _make_scala_parser(language)
            tree = parser.parse(file_content.encode("utf-8"))
            elements_dict = self.extract_elements(tree, file_content)
            return self._scala_analysis_result(
                file_path, file_content, tree, elements_dict
            )
        except Exception as e:
            log_error(f"Error analyzing Scala file {file_path}: {e}")
            return _scala_error_result(file_path, e)

    def _scala_analysis_result(
        self,
        file_path: str,
        file_content: str,
        tree: Any,
        elements_dict: dict[str, list[Any]],
    ) -> AnalysisResult:
        """Build the success-path ``AnalysisResult`` from parsed tree + elements."""
        from ..models import AnalysisResult

        all_elements = _flatten_scala_elements(elements_dict)
        node_count = (
            count_nodes_iterative(tree.root_node) if tree and tree.root_node else 0
        )
        packages = elements_dict.get("packages", [])
        package = packages[0] if packages else None
        return AnalysisResult(
            file_path=file_path,
            language="scala",
            # P1: splitlines() matches wc -l (split("\n") over-counts by 1
            # when file ends with trailing \n)
            line_count=len(file_content.splitlines()),
            elements=all_elements,
            node_count=node_count,
            source_code=file_content,
            package=package,
        )

    def _count_tree_nodes(self, node: Any) -> int:
        """Count all nodes in the subtree. Delegates to count_nodes_iterative."""
        if node is None:
            return 0
        return count_nodes_iterative(node)

    def get_tree_sitter_language(self) -> Any | None:
        """Get the tree-sitter language for Scala."""
        if self._cached_language is not None:
            return self._cached_language

        try:
            import tree_sitter
            import tree_sitter_scala

            caps_or_lang = tree_sitter_scala.language()

            if hasattr(caps_or_lang, "__class__") and "Language" in str(
                type(caps_or_lang)
            ):
                self._cached_language = caps_or_lang
                return self._cached_language

            try:
                self._cached_language = tree_sitter.Language(caps_or_lang)
            except Exception as e:
                log_error(f"Failed to create Language object: {e}")
                return None

            return self._cached_language
        except ImportError as e:
            log_error(f"tree-sitter-scala not available: {e}")
            return None
        except Exception as e:
            log_error(f"Failed to load tree-sitter language for Scala: {e}")
            return None

    def extract_elements(self, tree: Any | None, source_code: str) -> dict[str, Any]:
        """Extract all elements."""
        _empty: dict[str, Any] = {k: [] for k in _SCALA_ELEMENT_KEYS}
        if tree is None:
            return _empty
        try:
            extractor = self.create_extractor()
            return {
                "functions": extractor.extract_functions(tree, source_code),
                "classes": extractor.extract_classes(tree, source_code),
                "variables": extractor.extract_variables(tree, source_code),
                "imports": extractor.extract_imports(tree, source_code),
                "packages": extractor.extract_packages(tree, source_code),
                "comments": extractor.extract_comments(tree, source_code),  # type: ignore[attr-defined]
                "annotations": extractor.extract_annotations(tree, source_code),
            }
        except Exception as e:
            log_error(f"Error extracting elements: {e}")
            return _empty
