"""Class/object/trait/enum/given/type-alias/extension extraction for Scala."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tree_sitter

from ...models import Class
from ...utils import log_error
from ..shared.traversal import node_range


class ScalaClassExtractionMixin:
    """Class-like construct extraction, mixed into ``ScalaElementExtractor``."""

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

    def _scala_class_like_name(self, node: tree_sitter.Node) -> str:
        """Return class/object/trait name, falling back to identifier scan."""
        name_node = node.child_by_field_name("name")
        if name_node:
            return self._get_node_text(name_node)
        for child in node.children:
            if child.type in ("identifier", "type_identifier"):
                return self._get_node_text(child)
        return "anonymous"

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
