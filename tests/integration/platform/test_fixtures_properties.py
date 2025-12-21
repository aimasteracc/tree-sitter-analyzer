from tree_sitter_analyzer.platform_compat.fixtures import ALL_FIXTURES


def test_fixture_library_coverage():
    """
    Property 12: Fixture library coverage
    Validates: Requirements 6.1, 6.2, 6.3
    """
    construct_types = {"table", "view", "function", "procedure", "trigger", "index"}

    covered_standard = set()
    covered_edge_cases = set()

    for fixture in ALL_FIXTURES:
        for construct in fixture.expected_constructs:
            if construct in construct_types:
                if fixture.is_edge_case:
                    covered_edge_cases.add(construct)
                else:
                    covered_standard.add(construct)

    # Check that we have at least one standard fixture for each type
    missing_standard = construct_types - covered_standard
    assert not missing_standard, f"Missing standard fixtures for: {missing_standard}"

    # Check that we have at least one edge case fixture for each type
    missing_edge_cases = construct_types - covered_edge_cases
    assert (
        not missing_edge_cases
    ), f"Missing edge case fixtures for: {missing_edge_cases}"
