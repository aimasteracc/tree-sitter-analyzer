from hypothesis import given
from hypothesis import strategies as st

from tree_sitter_analyzer.models import SQLElementType, SQLFunction, SQLTrigger, SQLView
from tree_sitter_analyzer.platform_compat.adapter import (
    CompatibilityAdapter,
    FixFunctionNameKeywordsRule,
    FixTriggerNameDescriptionRule,
    RecoverViewsFromErrorsRule,
    RemovePhantomTriggersRule,
)


class TestAdapterProperties:
    @given(st.text(min_size=1, alphabet=st.characters(whitelist_categories=("L", "N"))))
    def test_function_name_normalization(self, name):
        """
        Property 4: Transformation normalization (function names)
        Validates: Requirements 1.2, 4.3
        """
        rule = FixFunctionNameKeywordsRule()

        # Case 1: Function name is a keyword
        bad_name = "FUNCTION"
        raw_text = f"CREATE FUNCTION {name} RETURNS INT BEGIN END;"

        element = SQLFunction(
            name=bad_name,
            start_line=1,
            end_line=1,
            raw_text=raw_text,
            sql_element_type=SQLElementType.FUNCTION,
        )

        adapted = rule.apply(element, {})
        assert adapted.name == name

        # Case 2: Function name is already correct
        element.name = name
        adapted = rule.apply(element, {})
        assert adapted.name == name

    @given(st.text(min_size=1, alphabet=st.characters(whitelist_categories=("L", "N"))))
    def test_trigger_name_normalization(self, name):
        """
        Property 4: Transformation normalization (trigger names)
        Validates: Requirements 1.2, 4.3
        """
        rule = FixTriggerNameDescriptionRule()

        # Case 1: Trigger name is "description"
        bad_name = "description"
        raw_text = (
            f"CREATE TRIGGER {name} BEFORE INSERT ON table FOR EACH ROW BEGIN END;"
        )

        element = SQLTrigger(
            name=bad_name,
            start_line=1,
            end_line=1,
            raw_text=raw_text,
            sql_element_type=SQLElementType.TRIGGER,
        )

        adapted = rule.apply(element, {})
        assert adapted.name == name

        # Case 2: Trigger name is already correct
        element.name = name
        adapted = rule.apply(element, {})
        assert adapted.name == name

    def test_phantom_element_removal(self):
        """
        Property 4: Transformation normalization (phantom removal)
        Validates: Requirements 1.2, 4.3
        """
        rule = RemovePhantomTriggersRule()

        # Case 1: Phantom trigger (no CREATE TRIGGER in raw text)
        element = SQLTrigger(
            name="phantom",
            start_line=1,
            end_line=1,
            raw_text="-- Just a comment about triggers",
            sql_element_type=SQLElementType.TRIGGER,
        )

        adapted = rule.apply(element, {})
        assert adapted is None

        # Case 2: Real trigger
        element.raw_text = "CREATE TRIGGER real_trigger ..."
        adapted = rule.apply(element, {})
        assert adapted is not None
        assert adapted.name == "phantom"

    @given(st.text(min_size=1, alphabet=st.characters(whitelist_categories=("L", "N"))))
    def test_view_recovery(self, name):
        """
        Property 4: Transformation normalization (view recovery)
        Validates: Requirements 1.2, 4.3
        """
        rule = RecoverViewsFromErrorsRule()
        source_code = f"CREATE VIEW {name} AS SELECT * FROM table;"

        context = {"source_code": source_code}
        elements = rule.generate_elements(context)

        assert len(elements) == 1
        assert isinstance(elements[0], SQLView)
        assert elements[0].name == name

    def test_adaptation_idempotence(self):
        """
        Property 15: Adaptation rule idempotence
        Validates: Requirements 4.3
        """
        adapter = CompatibilityAdapter()  # Enables all rules by default

        # Create an element that needs adaptation
        raw_text = "CREATE FUNCTION my_func RETURNS INT ..."
        element = SQLFunction(
            name="FUNCTION",  # Needs fixing
            start_line=1,
            end_line=1,
            raw_text=raw_text,
            sql_element_type=SQLElementType.FUNCTION,
        )

        # First application
        adapted_list = adapter.adapt_elements([element], raw_text)
        assert len(adapted_list) == 1
        adapted = adapted_list[0]
        assert adapted.name == "my_func"

        # Second application
        adapted_list_2 = adapter.adapt_elements([adapted], raw_text)
        assert len(adapted_list_2) == 1
        adapted_2 = adapted_list_2[0]
        assert adapted_2.name == "my_func"

        # Ensure no changes
        assert adapted == adapted_2
