# Implementation Plan

- [x] 1. Fix the SQL function extraction regex pattern and logic
  - Modify `_extract_sql_functions_enhanced` method in `tree_sitter_analyzer/languages/sql_plugin.py`
  - Add state tracking to prevent matching patterns inside function bodies
  - Improve regex pattern to require opening parenthesis after function name
  - Add "price", "quantity", "total", "amount", "count", "sum" to excluded column names list
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.5_


- [x] 1.1 Write property test for function body content exclusion
  - **Property 1: Function body content exclusion**
  - **Validates: Requirements 1.1, 1.2, 1.3**


- [x] 1.2 Write property test for regex pattern precision
  - **Property 3: Regex pattern precision**
  - **Validates: Requirements 2.1, 2.2, 2.5**

- [x] 2. Enhance identifier validation logic
  - Update `_is_valid_identifier` method or add additional validation in extraction logic
  - Ensure common column names are rejected
  - Ensure SQL reserved keywords are rejected
  - _Requirements: 2.3, 2.4_

- [x] 2.1 Write property test for identifier validation
  - **Property 4: Identifier validation**
  - **Validates: Requirements 2.3, 2.4**

- [x] 3. Verify function boundary detection
  - Review and test the END statement detection logic
  - Ensure start_line and end_line are correctly set
  - _Requirements: 1.5_

- [x] 3.1 Write property test for function boundary detection
  - **Property 2: Function boundary detection**
  - **Validates: Requirements 1.5**
-

- [x] 4. Run golden master regression test
  - Execute `pytest tests/test_golden_master_regression.py::TestGoldenMasterRegression::test_golden_master_comparison[examples/sample_database.sql-sql_sample_database-csv] -v`
  - Verify the test passes
  - Verify exactly 19 lines of CSV output
  - Verify no "price" function in output
  - Verify functions appear in correct order
  - _Requirements: 1.4, 3.1, 3.2, 3.3, 3.4_

- [x] 4.1 Write property test for extraction count consistency
  - **Property 5: Extraction count consistency**
  - **Validates: Requirements 1.4**

- [x] 4.2 Write property test for output ordering preservation
  - **Property 6: Output ordering preservation**
  - **Validates: Requirements 3.3**


- [x] 4.3 Write property test for deterministic extraction
  - **Property 7: Deterministic extraction**
  - **Validates: Requirements 3.5**

- [x] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.


- [x] 6. Verify fix across all test cases
  - Run full golden master regression test suite
  - Verify all SQL-related tests pass
  - Confirm no regressions in other language plugins
  - _Requirements: 3.1, 3.5_

- [x] 7. Final checkpoint - Ensure all tests pass



  - Ensure all tests pass, ask the user if questions arise.
