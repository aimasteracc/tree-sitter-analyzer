from tree_sitter_analyzer.platform_compat.adapter import CompatibilityAdapter
from tree_sitter_analyzer.platform_compat.profiles import (
    PROFILE_SCHEMA_VERSION,
    BehaviorProfile,
)


class TestEquivalenceProperties:
    def test_cross_platform_equivalence(self):
        """
        Property 1: Cross-platform parsing equivalence
        Validates: Requirements 1.1
        """
        # Define mock profiles for different platforms

        # Windows Profile: Has function name keyword issue
        windows_profile = BehaviorProfile(
            schema_version=PROFILE_SCHEMA_VERSION,
            platform_key="windows-3.12",
            behaviors={},
            adaptation_rules=["fix_function_name_keywords"],
        )

        # macOS Profile: Has trigger description issue
        macos_profile = BehaviorProfile(
            schema_version=PROFILE_SCHEMA_VERSION,
            platform_key="macos-3.12",
            behaviors={},
            adaptation_rules=["fix_trigger_name_description"],
        )

        # Linux Profile: Has phantom triggers
        linux_profile = BehaviorProfile(
            schema_version=PROFILE_SCHEMA_VERSION,
            platform_key="linux-3.12",
            behaviors={},
            adaptation_rules=["remove_phantom_triggers"],
        )

        # Define SQL that triggers these issues
        # 1. Function named "BEGIN" (keyword) - Windows issue
        # 2. Trigger named "description" - macOS issue
        # 3. Phantom trigger text - Linux issue

        sql_source = """
        CREATE FUNCTION BEGIN() RETURNS INT BEGIN RETURN 1; END;

        CREATE TRIGGER description BEFORE INSERT ON table FOR EACH ROW BEGIN END;

        -- Some text that might look like a trigger to a broken parser
        CREATE TRIGGER phantom ...
        """

        # We need to mock the extractor's internal extraction to simulate platform-specific broken ASTs
        # This is hard because the real parser runs on the real platform.
        # So we have to simulate the *output* of the raw extraction before adaptation.

        # Windows Raw Output: Function name is "BEGIN"
        # macOS Raw Output: Trigger name is "description"
        # Linux Raw Output: Includes a phantom trigger element

        from tree_sitter_analyzer.models import SQLElementType, SQLFunction, SQLTrigger

        # Helper to run adaptation
        def run_adaptation(profile, raw_elements):
            adapter = CompatibilityAdapter(profile)
            return adapter.adapt_elements(raw_elements, sql_source)

        # Windows Issue: `CREATE FUNCTION my_func` -> extracted name "FUNCTION" (keyword)
        # macOS Issue: `CREATE TRIGGER my_trig` -> extracted name "description"

        raw_text_func = "CREATE FUNCTION my_func() RETURNS INT..."
        raw_text_trig = "CREATE TRIGGER my_trig BEFORE INSERT..."

        def get_windows_elements():
            return [
                SQLFunction(
                    name="FUNCTION",
                    raw_text=raw_text_func,
                    sql_element_type=SQLElementType.FUNCTION,
                    element_type="function",
                    start_line=1,
                    end_line=1,
                    parameters=[],
                ),  # Broken
                SQLTrigger(
                    name="my_trig",
                    raw_text=raw_text_trig,
                    sql_element_type=SQLElementType.TRIGGER,
                    element_type="trigger",
                    start_line=2,
                    end_line=2,
                    table_name="table",
                    trigger_timing="BEFORE",
                    trigger_event="INSERT",
                ),
            ]

        def get_macos_elements():
            return [
                SQLFunction(
                    name="my_func",
                    raw_text=raw_text_func,
                    sql_element_type=SQLElementType.FUNCTION,
                    element_type="function",
                    start_line=1,
                    end_line=1,
                    parameters=[],
                ),
                SQLTrigger(
                    name="description",
                    raw_text=raw_text_trig,
                    sql_element_type=SQLElementType.TRIGGER,
                    element_type="trigger",
                    start_line=2,
                    end_line=2,
                    table_name="table",
                    trigger_timing="BEFORE",
                    trigger_event="INSERT",
                ),  # Broken
            ]

        def get_linux_elements():
            return [
                SQLFunction(
                    name="my_func",
                    raw_text=raw_text_func,
                    sql_element_type=SQLElementType.FUNCTION,
                    element_type="function",
                    start_line=1,
                    end_line=1,
                    parameters=[],
                ),
                SQLTrigger(
                    name="my_trig",
                    raw_text=raw_text_trig,
                    sql_element_type=SQLElementType.TRIGGER,
                    element_type="trigger",
                    start_line=2,
                    end_line=2,
                    table_name="table",
                    trigger_timing="BEFORE",
                    trigger_event="INSERT",
                ),
                SQLTrigger(
                    name="phantom",
                    raw_text="CREATE FUNCTION phantom...",
                    sql_element_type=SQLElementType.TRIGGER,
                    element_type="trigger",
                    start_line=3,
                    end_line=3,
                    table_name="table",
                    trigger_timing="BEFORE",
                    trigger_event="INSERT",
                ),  # Broken
            ]

        win_result = run_adaptation(windows_profile, get_windows_elements())
        mac_result = run_adaptation(macos_profile, get_macos_elements())
        linux_result = run_adaptation(linux_profile, get_linux_elements())

        # Assertions

        # 1. Check Windows
        assert win_result[0].name == "my_func"
        assert win_result[1].name == "my_trig"

        # 2. Check macOS
        assert mac_result[0].name == "my_func"
        assert mac_result[1].name == "my_trig"

        # 3. Check Linux
        assert len(linux_result) == 2
        assert linux_result[0].name == "my_func"
        assert linux_result[1].name == "my_trig"

        # 4. Cross-platform Identity
        # We can't compare objects directly because they are different instances,
        # but we can compare their properties.

        def get_names(elements):
            return sorted([e.name for e in elements])

        assert get_names(win_result) == get_names(mac_result)
        assert get_names(mac_result) == get_names(linux_result)
