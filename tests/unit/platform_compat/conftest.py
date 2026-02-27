"""Shared fixtures for platform_compat tests."""

import json

import pytest

from tree_sitter_analyzer.models import (
    SQLElementType,
    SQLFunction,
    SQLTrigger,
    SQLView,
)
from tree_sitter_analyzer.platform_compat.detector import PlatformInfo
from tree_sitter_analyzer.platform_compat.fixtures import SQLTestFixture
from tree_sitter_analyzer.platform_compat.profiles import (
    BehaviorProfile,
    ParsingBehavior,
)


@pytest.fixture
def sample_platform_info():
    """Return a sample PlatformInfo for testing."""
    return PlatformInfo(
        os_name="linux",
        os_version="5.15.0",
        python_version="3.12",
        platform_key="linux-3.12",
    )


@pytest.fixture
def sample_behavior():
    """Return a sample ParsingBehavior."""
    return ParsingBehavior(
        construct_id="simple_table",
        node_type="program",
        element_count=1,
        attributes=["col:id", "col:username"],
        has_error=False,
        known_issues=[],
    )


@pytest.fixture
def sample_profile(sample_behavior):
    """Return a sample BehaviorProfile."""
    return BehaviorProfile(
        schema_version="1.0.0",
        platform_key="linux-3.12",
        behaviors={"simple_table": sample_behavior},
        adaptation_rules=[],
    )


@pytest.fixture
def sample_profile_with_errors():
    """Return a profile with error behaviors."""
    return BehaviorProfile(
        schema_version="1.0.0",
        platform_key="windows-3.12",
        behaviors={
            "simple_table": ParsingBehavior(
                construct_id="simple_table",
                node_type="program",
                element_count=1,
                attributes=["col:id", "col:username"],
                has_error=False,
            ),
            "function_with_select": ParsingBehavior(
                construct_id="function_with_select",
                node_type="program",
                element_count=0,
                attributes=[],
                has_error=True,
                known_issues=["windows-3.12"],
            ),
        },
        adaptation_rules=[],
    )


@pytest.fixture
def sample_profile_alt():
    """Return a second profile for comparison tests."""
    return BehaviorProfile(
        schema_version="1.0.0",
        platform_key="macos-3.12",
        behaviors={
            "simple_table": ParsingBehavior(
                construct_id="simple_table",
                node_type="program",
                element_count=1,
                attributes=["col:id", "col:email"],
                has_error=False,
            ),
        },
        adaptation_rules=[],
    )


@pytest.fixture
def sample_fixture():
    """Return a sample SQLTestFixture."""
    return SQLTestFixture(
        id="test_table",
        sql="CREATE TABLE test (id INT PRIMARY KEY);",
        description="A simple test table",
        expected_constructs=["table"],
    )


@pytest.fixture
def sample_sql_function():
    """Return a sample SQLFunction element."""
    return SQLFunction(
        name="CalculateTax",
        start_line=1,
        end_line=5,
        raw_text="CREATE FUNCTION CalculateTax(amount DECIMAL) RETURNS DECIMAL BEGIN RETURN amount * 0.15; END;",
        sql_element_type=SQLElementType.FUNCTION,
        element_type="function",
    )


@pytest.fixture
def sample_sql_trigger():
    """Return a sample SQLTrigger element."""
    return SQLTrigger(
        name="before_order_insert",
        start_line=1,
        end_line=5,
        raw_text="CREATE TRIGGER before_order_insert BEFORE INSERT ON orders FOR EACH ROW BEGIN SET NEW.order_date = NOW(); END;",
        sql_element_type=SQLElementType.TRIGGER,
        element_type="trigger",
    )


@pytest.fixture
def sample_sql_view():
    """Return a sample SQLView element."""
    return SQLView(
        name="user_orders",
        start_line=1,
        end_line=3,
        raw_text="CREATE VIEW user_orders AS SELECT * FROM users;",
        sql_element_type=SQLElementType.VIEW,
        element_type="view",
    )


@pytest.fixture
def profiles_dir(tmp_path):
    """Create a temp directory with profile JSON files."""
    profile_data = {
        "schema_version": "1.0.0",
        "platform_key": "linux-3.12",
        "behaviors": {
            "simple_table": {
                "construct_id": "simple_table",
                "node_type": "program",
                "element_count": 1,
                "attributes": ["col:id"],
                "has_error": False,
                "known_issues": [],
            }
        },
        "adaptation_rules": [],
    }

    profile_dir = tmp_path / "linux" / "3.12"
    profile_dir.mkdir(parents=True)
    profile_path = profile_dir / "profile.json"
    profile_path.write_text(json.dumps(profile_data), encoding="utf-8")

    return tmp_path
