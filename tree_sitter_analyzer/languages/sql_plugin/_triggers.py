"""SQL element extraction mixin — triggers."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tree_sitter

from ...models import (
    Function,
    SQLElement,
    SQLTrigger,
)
from ...utils import log_debug
from ._base import _SQLExtractorBase


class TriggersMixin(_SQLExtractorBase):

    def _extract_triggers(
        self, root_node: tree_sitter.Node, functions: list[Function]
    ) -> None:
        """
        Extract CREATE TRIGGER statements from SQL AST.

        Since tree-sitter-sql doesn't fully support TRIGGER syntax, these
        appear as ERROR nodes. We search for ERROR nodes containing both
        keyword_create and keyword_trigger, then extract the trigger name
        from the first object_reference > identifier that appears after
        keyword_trigger.

        Args:
            root_node: Root node of the SQL AST
            functions: List to append extracted trigger Function elements to
        """
        for node in self._traverse_nodes(root_node):
            if node.type == "ERROR":
                # Check if this ERROR node contains CREATE TRIGGER
                # Since multiple triggers might be lumped into one ERROR node,
                # we need to scan all children or use regex.
                # Using regex on the node text is more robust for ERROR nodes.

                node_text = self._get_node_text(node)
                if not node_text:
                    continue

                node_text_upper = node_text.upper()
                if "CREATE" in node_text_upper and "TRIGGER" in node_text_upper:
                    import re

                    # Regex to find CREATE TRIGGER statements
                    # Matches: CREATE TRIGGER [IF NOT EXISTS] trigger_name
                    matches = re.finditer(
                        r"CREATE\s+TRIGGER\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z_][a-zA-Z0-9_]*)",
                        node_text,
                        re.IGNORECASE,
                    )

                    for match in matches:
                        trigger_name = match.group(1)

                        if trigger_name and self._is_valid_identifier(trigger_name):
                            # Skip common SQL keywords
                            if trigger_name.upper() in (
                                "KEY",
                                "AUTO_INCREMENT",
                                "PRIMARY",
                                "FOREIGN",
                                "INDEX",
                                "UNIQUE",
                                "PRICE",
                                "QUANTITY",
                                "TOTAL",
                                "SUM",
                                "COUNT",
                                "AVG",
                                "MAX",
                                "MIN",
                                "CONSTRAINT",
                                "CHECK",
                                "DEFAULT",
                                "REFERENCES",
                                "ON",
                                "UPDATE",
                                "DELETE",
                                "INSERT",
                                "BEFORE",
                                "AFTER",
                                "INSTEAD",
                                "OF",
                            ):
                                continue

                            try:
                                # Calculate start line based on match position
                                newlines_before = node_text[: match.start()].count("\n")
                                start_line = node.start_point[0] + 1 + newlines_before
                                end_line = node.end_point[0] + 1

                                # Use the whole error node text as raw text for now
                                raw_text = node_text

                                func = Function(
                                    name=trigger_name,
                                    start_line=start_line,
                                    end_line=end_line,
                                    raw_text=raw_text,
                                    language="sql",
                                )
                                functions.append(func)
                            except Exception as e:
                                log_debug(f"Failed to extract trigger: {e}")

    def _extract_sql_triggers(
        self, root_node: tree_sitter.Node, sql_elements: list[SQLElement]
    ) -> None:
        """Extract CREATE TRIGGER statements with enhanced metadata."""
        import re

        # Use self.source_code which is set by parent method _extract_sql_elements
        # This is more reliable than _get_node_text(root_node) which may fail
        # on some platforms due to encoding or byte offset issues
        source_code = self.source_code

        if not source_code:
            log_debug("WARNING: source_code is empty in _extract_sql_triggers")
            return

        # Track processed triggers by name to avoid duplicates
        processed_triggers = set()

        # Use regex on the full source to find all triggers with accurate positions
        trigger_pattern = re.compile(
            r"CREATE\s+TRIGGER\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE | re.MULTILINE
        )

        trigger_matches = list(trigger_pattern.finditer(source_code))
        log_debug(f"Found {len(trigger_matches)} CREATE TRIGGER statements in source")

        for match in trigger_matches:
            trigger_name = match.group(1)

            # Skip if already processed
            if trigger_name in processed_triggers:
                continue

            if not self._is_valid_identifier(trigger_name):
                continue

            # Skip invalid trigger names (too short or common SQL keywords)
            if len(trigger_name) <= 2:
                continue

            # Skip common SQL keywords that might be incorrectly identified
            if trigger_name.upper() in (
                "KEY",
                "AUTO_INCREMENT",
                "PRIMARY",
                "FOREIGN",
                "INDEX",
                "UNIQUE",
            ):
                continue

            # Mark as processed
            processed_triggers.add(trigger_name)

            # Calculate start line (1-indexed)
            start_line = source_code[: match.start()].count("\n") + 1

            # Find the end of this trigger statement (looking for the END keyword followed by semicolon)
            trigger_start_pos = match.start()
            # Search for END; after the trigger definition
            end_pattern = re.compile(r"\bEND\s*;", re.IGNORECASE)
            end_match = end_pattern.search(source_code, trigger_start_pos)

            if end_match:
                end_line = source_code[: end_match.end()].count("\n") + 1
                trigger_text = source_code[trigger_start_pos : end_match.end()]
            else:
                # Fallback: use a reasonable default
                end_line = start_line + 20
                trigger_text = source_code[trigger_start_pos : trigger_start_pos + 500]

            # Extract trigger metadata from the extracted text
            trigger_timing, trigger_event, table_name = self._extract_trigger_metadata(
                trigger_text
            )

            try:
                trigger = SQLTrigger(
                    name=trigger_name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=trigger_text,
                    language="sql",
                    table_name=table_name,
                    trigger_timing=trigger_timing,
                    trigger_event=trigger_event,
                    dependencies=[table_name] if table_name else [],
                )
                sql_elements.append(trigger)
            except Exception as e:
                log_debug(f"Failed to extract enhanced trigger: {e}")

    def _extract_trigger_metadata(
        self,
        trigger_text: str,
    ) -> tuple[str | None, str | None, str | None]:
        """Extract trigger timing, event, and target table."""
        import re

        timing = None
        event = None
        table_name = None

        # Extract timing (BEFORE/AFTER)
        timing_match = re.search(r"(BEFORE|AFTER)", trigger_text, re.IGNORECASE)
        if timing_match:
            timing = timing_match.group(1).upper()

        # Extract event (INSERT/UPDATE/DELETE)
        event_match = re.search(r"(INSERT|UPDATE|DELETE)", trigger_text, re.IGNORECASE)
        if event_match:
            event = event_match.group(1).upper()

        # Extract target table
        table_match = re.search(
            r"ON\s+([a-zA-Z_][a-zA-Z0-9_]*)", trigger_text, re.IGNORECASE
        )
        if table_match:
            table_name = table_match.group(1)

        return timing, event, table_name
