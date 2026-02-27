"""Tests for platform_compat.adapter module."""

import pytest

from tree_sitter_analyzer.models import (
    SQLElementType,
    SQLFunction,
    SQLTrigger,
    SQLView,
)
from tree_sitter_analyzer.platform_compat.adapter import (
    CompatibilityAdapter,
    FixFunctionNameKeywordsRule,
    FixTriggerNameDescriptionRule,
    RecoverViewsFromErrorsRule,
    RemovePhantomFunctionsRule,
    RemovePhantomTriggersRule,
)
from tree_sitter_analyzer.platform_compat.profiles import BehaviorProfile


class TestFixFunctionNameKeywordsRule:
    """Tests for the FixFunctionNameKeywordsRule."""

    @pytest.mark.unit
    def test_rule_id(self):
        """Test rule_id property."""
        rule = FixFunctionNameKeywordsRule()
        assert rule.rule_id == "fix_function_name_keywords"

    @pytest.mark.unit
    def test_description(self):
        """Test description property."""
        rule = FixFunctionNameKeywordsRule()
        assert "function name" in rule.description.lower()

    @pytest.mark.unit
    def test_non_function_element_passthrough(self, sample_sql_trigger):
        """Test that non-function elements are passed through unchanged."""
        rule = FixFunctionNameKeywordsRule()
        result = rule.apply(sample_sql_trigger, {})
        assert result is sample_sql_trigger

    @pytest.mark.unit
    def test_fix_keyword_name_function(self):
        """Test fixing a function whose name is a SQL keyword."""
        func = SQLFunction(
            name="FUNCTION",
            start_line=1,
            end_line=5,
            raw_text="CREATE FUNCTION CalculateTax(amount DECIMAL) RETURNS DECIMAL BEGIN RETURN amount; END;",
            sql_element_type=SQLElementType.FUNCTION,
            element_type="function",
        )
        rule = FixFunctionNameKeywordsRule()
        result = rule.apply(func, {})
        assert result is not None
        assert result.name == "CalculateTax"

    @pytest.mark.unit
    def test_fix_auto_increment_keyword_name(self):
        """Test fixing a function whose name is AUTO_INCREMENT."""
        func = SQLFunction(
            name="AUTO_INCREMENT",
            start_line=1,
            end_line=3,
            raw_text="CREATE FUNCTION GetNextId() RETURNS INT BEGIN RETURN 1; END;",
            sql_element_type=SQLElementType.FUNCTION,
            element_type="function",
        )
        rule = FixFunctionNameKeywordsRule()
        result = rule.apply(func, {})
        assert result is not None
        assert result.name == "GetNextId"

    @pytest.mark.unit
    def test_correct_name_no_change(self, sample_sql_function):
        """Test that a function with correct name is not changed."""
        rule = FixFunctionNameKeywordsRule()
        result = rule.apply(sample_sql_function, {})
        assert result is not None
        assert result.name == "CalculateTax"

    @pytest.mark.unit
    def test_fix_mismatched_name_via_regex(self):
        """Test fixing a function whose name doesn't match the CREATE FUNCTION name."""
        func = SQLFunction(
            name="wrong_name",
            start_line=1,
            end_line=3,
            raw_text="CREATE FUNCTION RealName() RETURNS INT BEGIN RETURN 1; END;",
            sql_element_type=SQLElementType.FUNCTION,
            element_type="function",
        )
        rule = FixFunctionNameKeywordsRule()
        result = rule.apply(func, {})
        assert result is not None
        assert result.name == "RealName"

    @pytest.mark.unit
    def test_keyword_name_no_function_in_raw_text(self):
        """Test that keyword name stays if raw_text has no FUNCTION pattern."""
        func = SQLFunction(
            name="CREATE",
            start_line=1,
            end_line=3,
            raw_text="some random text with no matching create-func keyword",
            sql_element_type=SQLElementType.FUNCTION,
            element_type="function",
        )
        rule = FixFunctionNameKeywordsRule()
        result = rule.apply(func, {})
        assert result is not None
        # Name stays as CREATE since we can't extract from raw_text
        assert result.name == "CREATE"


class TestFixTriggerNameDescriptionRule:
    """Tests for the FixTriggerNameDescriptionRule."""

    @pytest.mark.unit
    def test_rule_id(self):
        """Test rule_id property."""
        rule = FixTriggerNameDescriptionRule()
        assert rule.rule_id == "fix_trigger_name_description"

    @pytest.mark.unit
    def test_non_trigger_passthrough(self, sample_sql_function):
        """Test that non-trigger elements pass through."""
        rule = FixTriggerNameDescriptionRule()
        result = rule.apply(sample_sql_function, {})
        assert result is sample_sql_function

    @pytest.mark.unit
    def test_fix_description_name(self):
        """Test fixing a trigger whose name is 'description'."""
        trigger = SQLTrigger(
            name="description",
            start_line=1,
            end_line=5,
            raw_text="CREATE TRIGGER update_stock BEFORE UPDATE ON products FOR EACH ROW BEGIN END;",
            sql_element_type=SQLElementType.TRIGGER,
            element_type="trigger",
        )
        rule = FixTriggerNameDescriptionRule()
        result = rule.apply(trigger, {})
        assert result is not None
        assert result.name == "update_stock"

    @pytest.mark.unit
    def test_correct_trigger_name_no_change(self, sample_sql_trigger):
        """Test that a trigger with correct name is not changed."""
        rule = FixTriggerNameDescriptionRule()
        result = rule.apply(sample_sql_trigger, {})
        assert result is not None
        assert result.name == "before_order_insert"

    @pytest.mark.unit
    def test_description_name_no_trigger_in_raw_text(self):
        """Test description name stays if raw_text has no TRIGGER pattern."""
        trigger = SQLTrigger(
            name="description",
            start_line=1,
            end_line=3,
            raw_text="some random text",
            sql_element_type=SQLElementType.TRIGGER,
            element_type="trigger",
        )
        rule = FixTriggerNameDescriptionRule()
        result = rule.apply(trigger, {})
        assert result is not None
        assert result.name == "description"


class TestRemovePhantomTriggersRule:
    """Tests for the RemovePhantomTriggersRule."""

    @pytest.mark.unit
    def test_rule_id(self):
        """Test rule_id property."""
        rule = RemovePhantomTriggersRule()
        assert rule.rule_id == "remove_phantom_triggers"

    @pytest.mark.unit
    def test_non_trigger_passthrough(self, sample_sql_function):
        """Test that non-trigger elements pass through."""
        rule = RemovePhantomTriggersRule()
        result = rule.apply(sample_sql_function, {})
        assert result is sample_sql_function

    @pytest.mark.unit
    def test_remove_phantom_trigger(self):
        """Test removing a phantom trigger (no CREATE TRIGGER in raw_text)."""
        trigger = SQLTrigger(
            name="phantom",
            start_line=1,
            end_line=3,
            raw_text="-- Just a comment mentioning triggers",
            sql_element_type=SQLElementType.TRIGGER,
            element_type="trigger",
        )
        rule = RemovePhantomTriggersRule()
        result = rule.apply(trigger, {})
        assert result is None

    @pytest.mark.unit
    def test_keep_real_trigger(self, sample_sql_trigger):
        """Test that a real trigger with CREATE TRIGGER is kept."""
        rule = RemovePhantomTriggersRule()
        result = rule.apply(sample_sql_trigger, {})
        assert result is not None
        assert result.name == "before_order_insert"

    @pytest.mark.unit
    def test_keep_trigger_with_extra_whitespace(self):
        """Test that trigger with extra whitespace in CREATE  TRIGGER is kept."""
        trigger = SQLTrigger(
            name="test_trigger",
            start_line=1,
            end_line=3,
            raw_text="CREATE   TRIGGER test_trigger BEFORE INSERT ON t FOR EACH ROW BEGIN END;",
            sql_element_type=SQLElementType.TRIGGER,
            element_type="trigger",
        )
        rule = RemovePhantomTriggersRule()
        result = rule.apply(trigger, {})
        assert result is not None


class TestRemovePhantomFunctionsRule:
    """Tests for the RemovePhantomFunctionsRule."""

    @pytest.mark.unit
    def test_rule_id(self):
        """Test rule_id property."""
        rule = RemovePhantomFunctionsRule()
        assert rule.rule_id == "remove_phantom_functions"

    @pytest.mark.unit
    def test_non_function_passthrough(self, sample_sql_trigger):
        """Test that non-function elements pass through."""
        rule = RemovePhantomFunctionsRule()
        result = rule.apply(sample_sql_trigger, {})
        assert result is sample_sql_trigger

    @pytest.mark.unit
    def test_remove_phantom_function(self):
        """Test removing a phantom function (no CREATE FUNCTION in raw_text)."""
        func = SQLFunction(
            name="phantom",
            start_line=1,
            end_line=3,
            raw_text="-- Just a comment about functions",
            sql_element_type=SQLElementType.FUNCTION,
            element_type="function",
        )
        rule = RemovePhantomFunctionsRule()
        result = rule.apply(func, {})
        assert result is None

    @pytest.mark.unit
    def test_keep_real_function(self, sample_sql_function):
        """Test that a real function with CREATE FUNCTION is kept."""
        rule = RemovePhantomFunctionsRule()
        result = rule.apply(sample_sql_function, {})
        assert result is not None
        assert result.name == "CalculateTax"


class TestRecoverViewsFromErrorsRule:
    """Tests for the RecoverViewsFromErrorsRule."""

    @pytest.mark.unit
    def test_rule_id(self):
        """Test rule_id property."""
        rule = RecoverViewsFromErrorsRule()
        assert rule.rule_id == "recover_views_from_errors"

    @pytest.mark.unit
    def test_apply_passthrough(self, sample_sql_function):
        """Test that apply() passes through all elements unchanged."""
        rule = RecoverViewsFromErrorsRule()
        result = rule.apply(sample_sql_function, {})
        assert result is sample_sql_function

    @pytest.mark.unit
    def test_generate_elements_finds_views(self):
        """Test that generate_elements finds CREATE VIEW statements in source."""
        rule = RecoverViewsFromErrorsRule()
        source_code = """
CREATE VIEW user_orders AS
SELECT u.username, o.order_date
FROM users u JOIN orders o ON u.id = o.user_id;
"""
        result = rule.generate_elements({"source_code": source_code})
        assert len(result) == 1
        assert result[0].name == "user_orders"
        assert isinstance(result[0], SQLView)

    @pytest.mark.unit
    def test_generate_elements_finds_multiple_views(self):
        """Test that generate_elements finds multiple CREATE VIEW statements."""
        rule = RecoverViewsFromErrorsRule()
        source_code = """
CREATE VIEW view1 AS SELECT * FROM t1;
CREATE VIEW view2 AS SELECT * FROM t2;
"""
        result = rule.generate_elements({"source_code": source_code})
        assert len(result) == 2
        names = {e.name for e in result}
        assert "view1" in names
        assert "view2" in names

    @pytest.mark.unit
    def test_generate_elements_no_views(self):
        """Test generate_elements with source code containing no views."""
        rule = RecoverViewsFromErrorsRule()
        result = rule.generate_elements({"source_code": "CREATE TABLE t (id INT);"})
        assert len(result) == 0

    @pytest.mark.unit
    def test_generate_elements_empty_source(self):
        """Test generate_elements with empty source code."""
        rule = RecoverViewsFromErrorsRule()
        result = rule.generate_elements({"source_code": ""})
        assert len(result) == 0

    @pytest.mark.unit
    def test_generate_elements_view_with_if_not_exists(self):
        """Test generate_elements handles IF NOT EXISTS."""
        rule = RecoverViewsFromErrorsRule()
        source_code = "CREATE VIEW IF NOT EXISTS my_view AS SELECT 1;"
        result = rule.generate_elements({"source_code": source_code})
        assert len(result) == 1
        assert result[0].name == "my_view"

    @pytest.mark.unit
    def test_generate_elements_correct_line_number(self):
        """Test that generate_elements computes correct start_line."""
        rule = RecoverViewsFromErrorsRule()
        source_code = "line1\nline2\nCREATE VIEW v1 AS SELECT 1;"
        result = rule.generate_elements({"source_code": source_code})
        assert len(result) == 1
        assert result[0].start_line == 3


class TestCompatibilityAdapter:
    """Tests for the CompatibilityAdapter class."""

    @pytest.mark.unit
    def test_init_without_profile_loads_all_rules(self):
        """Test that adapter without profile loads all default rules."""
        adapter = CompatibilityAdapter(profile=None)
        assert len(adapter.rules) > 0
        rule_ids = {r.rule_id for r in adapter.rules}
        assert "fix_function_name_keywords" in rule_ids
        assert "remove_phantom_triggers" in rule_ids
        assert "recover_views_from_errors" in rule_ids

    @pytest.mark.unit
    def test_init_with_empty_rules_profile(self):
        """Test that adapter with profile with empty rules loads no rules."""
        profile = BehaviorProfile(
            schema_version="1.0.0",
            platform_key="linux-3.12",
            behaviors={},
            adaptation_rules=[],
        )
        adapter = CompatibilityAdapter(profile=profile)
        assert len(adapter.rules) == 0

    @pytest.mark.unit
    def test_init_with_specific_rules(self):
        """Test that adapter loads only specified rules from profile."""
        profile = BehaviorProfile(
            schema_version="1.0.0",
            platform_key="linux-3.12",
            behaviors={},
            adaptation_rules=["fix_function_name_keywords"],
        )
        adapter = CompatibilityAdapter(profile=profile)
        assert len(adapter.rules) == 1
        assert adapter.rules[0].rule_id == "fix_function_name_keywords"

    @pytest.mark.unit
    def test_init_with_wildcard_rule(self):
        """Test that wildcard '*' enables all rules."""
        profile = BehaviorProfile(
            schema_version="1.0.0",
            platform_key="linux-3.12",
            behaviors={},
            adaptation_rules=["*"],
        )
        adapter = CompatibilityAdapter(profile=profile)
        assert len(adapter.rules) >= 5

    @pytest.mark.unit
    def test_adapt_elements_removes_phantom_trigger(self):
        """Test that adapt_elements removes phantom triggers."""
        adapter = CompatibilityAdapter(profile=None)
        phantom_trigger = SQLTrigger(
            name="phantom",
            start_line=1,
            end_line=3,
            raw_text="-- Comment mentioning trigger",
            sql_element_type=SQLElementType.TRIGGER,
            element_type="trigger",
        )
        result = adapter.adapt_elements([phantom_trigger], "")
        # Phantom should be removed (no CREATE TRIGGER in raw_text)
        trigger_results = [e for e in result if isinstance(e, SQLTrigger)]
        assert len(trigger_results) == 0

    @pytest.mark.unit
    def test_adapt_elements_keeps_real_elements(self, sample_sql_function):
        """Test that adapt_elements keeps valid elements."""
        adapter = CompatibilityAdapter(profile=None)
        result = adapter.adapt_elements([sample_sql_function], "")
        assert len(result) >= 1
        func_results = [e for e in result if isinstance(e, SQLFunction)]
        assert len(func_results) == 1

    @pytest.mark.unit
    def test_adapt_elements_recovers_views_from_source(self):
        """Test that adapt_elements recovers views from source code."""
        adapter = CompatibilityAdapter(profile=None)
        source = "CREATE VIEW recovered_view AS SELECT 1;"
        result = adapter.adapt_elements([], source)
        view_results = [e for e in result if isinstance(e, SQLView)]
        assert len(view_results) == 1
        assert view_results[0].name == "recovered_view"

    @pytest.mark.unit
    def test_adapt_elements_fixes_function_name(self):
        """Test that adapt_elements fixes incorrect function names."""
        adapter = CompatibilityAdapter(profile=None)
        func = SQLFunction(
            name="FUNCTION",
            start_line=1,
            end_line=3,
            raw_text="CREATE FUNCTION RealFunc() RETURNS INT BEGIN RETURN 1; END;",
            sql_element_type=SQLElementType.FUNCTION,
            element_type="function",
        )
        result = adapter.adapt_elements([func], "")
        func_results = [e for e in result if isinstance(e, SQLFunction)]
        assert len(func_results) == 1
        assert func_results[0].name == "RealFunc"

    @pytest.mark.unit
    def test_init_with_unknown_rule_id(self):
        """Test that unknown rule IDs in profile are ignored."""
        profile = BehaviorProfile(
            schema_version="1.0.0",
            platform_key="linux-3.12",
            behaviors={},
            adaptation_rules=["nonexistent_rule", "fix_function_name_keywords"],
        )
        adapter = CompatibilityAdapter(profile=profile)
        assert len(adapter.rules) == 1
        assert adapter.rules[0].rule_id == "fix_function_name_keywords"
