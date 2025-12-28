import logging
import re
from typing import Protocol, TypeVar

from tree_sitter_analyzer.models import (
    SQLElement,
    SQLElementType,
    SQLFunction,
    SQLTrigger,
    SQLView,
)
from tree_sitter_analyzer.platform_compat.profiles import BehaviorProfile

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=SQLElement)


class AdaptationRule(Protocol):
    """Rule for adapting platform-specific behavior."""

    @property
    def rule_id(self) -> str:
        """Unique identifier for the rule."""
        ...

    @property
    def description(self) -> str:
        """Description of what the rule does."""
        ...

    def apply(self, element: SQLElement, context: dict) -> SQLElement | None:
        """
        Applies the rule to an element.

        Args:
            element: The element to adapt.
            context: Additional context (e.g. source code).

        Returns:
            The adapted element, or None if the element should be removed.
            Returns the original element if no changes are needed.
        """
        ...


class CompatibilityAdapter:
    """Applies platform-specific adaptations to SQL parsing results."""

    def __init__(self, profile: BehaviorProfile | None = None):
        self.profile = profile
        self.rules: list[AdaptationRule] = []
        self._load_rules()

    def _load_rules(self) -> None:
        """Loads adaptation rules based on the profile."""
        # In a real implementation, we might load these dynamically or from a registry.
        # For now, we'll hardcode the available rules and enable them based on the profile.

        available_rules: dict[str, AdaptationRule] = {
            "fix_function_name_keywords": FixFunctionNameKeywordsRule(),
            "fix_trigger_name_description": FixTriggerNameDescriptionRule(),
            "remove_phantom_triggers": RemovePhantomTriggersRule(),
            "remove_phantom_functions": RemovePhantomFunctionsRule(),
            "recover_views_from_errors": RecoverViewsFromErrorsRule(),
        }

        if self.profile:
            for rule_id in self.profile.adaptation_rules:
                if rule_id in available_rules:
                    self.rules.append(available_rules[rule_id])
                elif rule_id == "*":
                    # Wildcard: enable all rules (useful for testing or "safe mode")
                    self.rules = list(available_rules.values())
                    break
        else:
            # Default behavior: enable all safe recovery rules?
            # Or maybe none? Let's enable all for now as they should be safe.
            self.rules = list(available_rules.values())

    def adapt_elements(
        self, elements: list[SQLElement], source_code: str
    ) -> list[SQLElement]:
        """
        Main entry point for adapting elements.

        Args:
            elements: The list of extracted elements.
            source_code: The original source code.

        Returns:
            The list of adapted elements.
        """
        context = {"source_code": source_code}
        adapted_elements = []

        # First pass: apply rules to existing elements
        for element in elements:
            current_element = element
            keep_element = True

            for rule in self.rules:
                result = rule.apply(current_element, context)
                if result is None:
                    keep_element = False
                    break
                current_element = result

            if keep_element:
                adapted_elements.append(current_element)

        # Second pass: recover missing elements (if any rule supports it)
        # Some rules might look at the source code and generate new elements
        # For example, RecoverViewsFromErrorsRule might want to scan source code
        # independent of existing elements.
        # However, the current Protocol definition is element-centric.
        # We might need a separate method for "generation" rules or handle it differently.
        # For RecoverViewsFromErrorsRule, we can treat it as a rule that inspects
        # "ERROR" elements if we had them, or we can just run it once.

        # Let's add a special hook for generation
        for rule in self.rules:
            if hasattr(rule, "generate_elements"):
                new_elements = rule.generate_elements(context)
                adapted_elements.extend(new_elements)

        return adapted_elements


# --- Specific Rules ---


class FixFunctionNameKeywordsRule:
    """
    Rule: fix_function_name_keywords
    Detects when function name is a SQL keyword and recovers correct name from raw_text.
    """

    @property
    def rule_id(self) -> str:
        return "fix_function_name_keywords"

    @property
    def description(self) -> str:
        return "Recover correct function name when keyword is extracted"

    def apply(self, element: SQLElement, context: dict) -> SQLElement | None:
        if not isinstance(element, SQLFunction):
            return element

        # List of keywords that might be incorrectly extracted as names
        keywords = {
            "FUNCTION",
            "PROCEDURE",
            "CREATE",
            "OR",
            "REPLACE",
            "AUTO_INCREMENT",
            "KEY",
            "PRIMARY",
            "FOREIGN",
        }

        # Check if name is a keyword OR if we should verify the name generally
        # This covers cases where the name is just wrong (e.g. garbage) but not necessarily a keyword
        should_fix = False
        if element.name.upper() in keywords:
            should_fix = True
        else:
            # General verification: check if the name matches what's in the CREATE statement
            # If the extracted name doesn't match the regex-extracted name, we should fix it
            match = re.search(r"FUNCTION\s+([\w]+)", element.raw_text, re.IGNORECASE)
            if match:
                correct_name = match.group(1)
                if element.name != correct_name:
                    should_fix = True

        if should_fix:
            # Try to extract name from raw_text
            # Pattern: CREATE [OR REPLACE] FUNCTION name ...
            # Use \w+ to match unicode word characters
            match = re.search(r"FUNCTION\s+([\w]+)", element.raw_text, re.IGNORECASE)
            if match:
                element.name = match.group(1)

        return element


class FixTriggerNameDescriptionRule:
    """
    Rule: fix_trigger_name_description
    Detects when trigger name is incorrectly set to "description".
    """

    @property
    def rule_id(self) -> str:
        return "fix_trigger_name_description"

    @property
    def description(self) -> str:
        return "Recover correct trigger name when 'description' is extracted"

    def apply(self, element: SQLElement, context: dict) -> SQLElement | None:
        if not isinstance(element, SQLTrigger):
            return element

        if element.name.lower() == "description":
            # Try to extract name from raw_text
            # Pattern: CREATE TRIGGER name ...
            # Use \w+ to match unicode word characters
            match = re.search(r"TRIGGER\s+([\w]+)", element.raw_text, re.IGNORECASE)
            if match:
                element.name = match.group(1)

        return element


class RemovePhantomTriggersRule:
    """
    Rule: remove_phantom_triggers
    Detects elements where type doesn't match content (phantom triggers).
    """

    @property
    def rule_id(self) -> str:
        return "remove_phantom_triggers"

    @property
    def description(self) -> str:
        return "Remove phantom triggers with mismatched content"

    def apply(self, element: SQLElement, context: dict) -> SQLElement | None:
        if isinstance(element, SQLTrigger):
            # Check if raw_text actually contains CREATE TRIGGER
            # Phantom triggers often appear in comments or unrelated code
            # Use regex to handle variable whitespace
            if not re.search(r"CREATE\s+TRIGGER", element.raw_text, re.IGNORECASE):
                # It might be a phantom
                logger.debug(
                    f"Removing phantom trigger: {element.name} (raw_text: {element.raw_text[:50]}...)"
                )
                return None
        return element


class RemovePhantomFunctionsRule:
    """
    Rule: remove_phantom_functions
    Detects elements where type doesn't match content (phantom functions).
    """

    @property
    def rule_id(self) -> str:
        return "remove_phantom_functions"

    @property
    def description(self) -> str:
        return "Remove phantom functions with mismatched content"

    def apply(self, element: SQLElement, context: dict) -> SQLElement | None:
        if isinstance(element, SQLFunction):
            # Check if raw_text actually contains CREATE FUNCTION
            # Phantom functions often appear in comments or unrelated code
            # Use regex to handle variable whitespace
            if not re.search(r"CREATE\s+FUNCTION", element.raw_text, re.IGNORECASE):
                # It might be a phantom
                return None
        return element


class RecoverViewsFromErrorsRule:
    """
    Rule: recover_views_from_errors
    Scans source code for CREATE VIEW statements that might have been missed (e.g. in ERROR nodes).
    """

    @property
    def rule_id(self) -> str:
        return "recover_views_from_errors"

    @property
    def description(self) -> str:
        return "Recover views from ERROR nodes"

    def apply(self, element: SQLElement, context: dict) -> SQLElement | None:
        # This rule doesn't modify existing elements, it generates new ones.
        return element

    def generate_elements(self, context: dict) -> list[SQLElement]:
        source_code = context.get("source_code", "")
        new_elements: list[SQLElement] = []

        # Simple regex to find CREATE VIEW statements
        # This is a fallback mechanism
        # Use \w+ to match unicode word characters
        # Updated to handle IF NOT EXISTS and multiline matching
        view_pattern = re.compile(
            r"^\s*CREATE\s+VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w]+)\s+AS",
            re.IGNORECASE | re.MULTILINE,
        )

        for match in view_pattern.finditer(source_code):
            view_name = match.group(1)
            # We need to check if this view is already extracted?
            # For now, let's assume the caller handles duplicates or we just return it.
            # Ideally we should check if 'view_name' is already in the elements list passed to adapt_elements.
            # But generate_elements doesn't see the list.
            # We'll return it and let the merger handle it, or we can improve the architecture.

            # Calculate line number (rough approximation)
            start_pos = match.start()
            line_number = source_code.count("\n", 0, start_pos) + 1

            view = SQLView(
                name=view_name,
                start_line=line_number,
                end_line=line_number,  # We don't know end line easily
                raw_text=match.group(0),  # Partial text
                sql_element_type=SQLElementType.VIEW,
                element_type="view",
            )
            new_elements.append(view)

        return new_elements
