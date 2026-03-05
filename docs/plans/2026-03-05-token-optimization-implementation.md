# Token优化实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 消除TOON输出中的冗余字段，防止Token爆炸，预估节省55-60% Token

**Architecture:** 统一TOON格式处理函数，移除冗余数据字段，优化analyze_scale_tool输出结构

**Tech Stack:** Python 3.12+, pytest, tree-sitter-analyzer MCP tools

---

## Task 1: 统一TOON冗余字段常量

**Files:**
- Modify: `tree_sitter_analyzer/mcp/utils/format_helper.py:1-20`
- Test: `tests/unit/mcp/test_utils/test_format_helper_token_optimization.py`

**Step 1: Write the failing test**

Create file `tests/unit/mcp/test_utils/test_format_helper_token_optimization.py`:

```python
#!/usr/bin/env python3
"""Tests for token optimization in format_helper."""
import pytest


class TestToonRedundantFields:
    """Tests for TOON redundant field constants."""

    def test_redundant_fields_constant_exists(self):
        """TOON_REDUNDANT_FIELDS constant should be defined."""
        from tree_sitter_analyzer.mcp.utils.format_helper import TOON_REDUNDANT_FIELDS

        assert TOON_REDUNDANT_FIELDS is not None
        assert isinstance(TOON_REDUNDANT_FIELDS, frozenset)

    def test_redundant_fields_contains_expected_fields(self):
        """TOON_REDUNDANT_FIELDS should contain expected data fields."""
        from tree_sitter_analyzer.mcp.utils.format_helper import TOON_REDUNDANT_FIELDS

        expected = {
            "results",
            "matches",
            "content",
            "data",
            "items",
            "files",
            "lines",
            "detailed_analysis",
            "structural_overview",
            "summary",
        }
        assert expected.issubset(TOON_REDUNDANT_FIELDS)

    def test_metadata_fields_constant_exists(self):
        """TOON_METADATA_FIELDS constant should be defined."""
        from tree_sitter_analyzer.mcp.utils.format_helper import TOON_METADATA_FIELDS

        assert TOON_METADATA_FIELDS is not None
        assert isinstance(TOON_METADATA_FIELDS, frozenset)

    def test_metadata_fields_contains_expected_fields(self):
        """TOON_METADATA_FIELDS should contain expected metadata fields."""
        from tree_sitter_analyzer.mcp.utils.format_helper import TOON_METADATA_FIELDS

        expected = {"success", "file_path", "language", "format", "warnings"}
        assert expected.issubset(TOON_METADATA_FIELDS)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/mcp/test_utils/test_format_helper_token_optimization.py -v`
Expected: FAIL with "ImportError: cannot import name 'TOON_REDUNDANT_FIELDS'"

**Step 3: Write minimal implementation**

Add to `tree_sitter_analyzer/mcp/utils/format_helper.py` after imports:

```python
# Token optimization: Redundant fields to remove when using TOON format
TOON_REDUNDANT_FIELDS: frozenset[str] = frozenset({
    # Data fields (already encoded in toon_content)
    "results",
    "matches",
    "content",
    "partial_content_result",
    "analysis_result",
    "data",
    "items",
    "files",
    "lines",
    "table_output",
    # Detailed analysis fields
    "detailed_analysis",
    "structural_overview",
    # Derivable summary
    "summary",  # Can be derived from structural_overview array lengths
})

# Token optimization: Metadata fields to preserve in TOON response
TOON_METADATA_FIELDS: frozenset[str] = frozenset({
    "success",
    "file_path",
    "language",
    "format",
    "toon_content",
    "warnings",
    "error",
    "total_count",
    "truncated",
    "execution_time",
})
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/mcp/test_utils/test_format_helper_token_optimization.py -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add tests/unit/mcp/test_utils/test_format_helper_token_optimization.py tree_sitter_analyzer/mcp/utils/format_helper.py
git commit -m "feat: add TOON redundant and metadata field constants for token optimization"
```

---

## Task 2: 优化attach_toon_content_to_response函数

**Files:**
- Modify: `tree_sitter_analyzer/mcp/utils/format_helper.py:208-223`
- Test: `tests/unit/mcp/test_utils/test_format_helper_token_optimization.py`

**Step 1: Write the failing test**

Add to `tests/unit/mcp/test_utils/test_format_helper_token_optimization.py`:

```python
class TestAttachToonContentOptimization:
    """Tests for attach_toon_content_to_response token optimization."""

    def test_removes_redundant_data_fields(self):
        """Should remove redundant data fields from TOON response."""
        from tree_sitter_analyzer.mcp.utils.format_helper import attach_toon_content_to_response

        input_data = {
            "success": True,
            "file_path": "/test/file.py",
            "results": ["item1", "item2", "item3"],
            "data": {"key": "value"},
            "structural_overview": {"classes": [], "methods": []},
            "summary": {"classes": 0, "methods": 0},
        }

        result = attach_toon_content_to_response(input_data)

        assert "results" not in result
        assert "data" not in result
        assert "structural_overview" not in result
        assert "summary" not in result

    def test_preserves_metadata_fields(self):
        """Should preserve metadata fields in TOON response."""
        from tree_sitter_analyzer.mcp.utils.format_helper import attach_toon_content_to_response

        input_data = {
            "success": True,
            "file_path": "/test/file.py",
            "language": "python",
            "warnings": ["test warning"],
            "results": ["item1"],
        }

        result = attach_toon_content_to_response(input_data)

        assert result["success"] is True
        assert result["file_path"] == "/test/file.py"
        assert result["language"] == "python"
        assert result["warnings"] == ["test warning"]
        assert result["format"] == "toon"

    def test_includes_toon_content(self):
        """Should include toon_content field."""
        from tree_sitter_analyzer.mcp.utils.format_helper import attach_toon_content_to_response

        input_data = {
            "success": True,
            "results": ["a", "b", "c"],
        }

        result = attach_toon_content_to_response(input_data)

        assert "toon_content" in result
        assert isinstance(result["toon_content"], str)
        assert len(result["toon_content"]) > 0

    def test_token_reduction_achieved(self):
        """Should achieve significant token reduction."""
        import json
        from tree_sitter_analyzer.mcp.utils.format_helper import attach_toon_content_to_response

        # Create large data structure
        large_data = {
            "success": True,
            "file_path": "/test/file.py",
            "results": [{"id": i, "name": f"item_{i}", "data": "x" * 100} for i in range(100)],
            "structural_overview": {
                "classes": [{"name": f"Class{i}", "lines": f"{i}-{i+100}"} for i in range(50)],
                "methods": [{"name": f"method{i}"} for i in range(200)],
            },
            "summary": {"classes": 50, "methods": 200},
        }

        result = attach_toon_content_to_response(large_data)

        # Original size vs optimized size
        original_size = len(json.dumps(large_data))
        optimized_size = len(json.dumps(result))

        # Should achieve at least 30% reduction (conservative estimate)
        reduction = 1 - (optimized_size / original_size)
        assert reduction >= 0.30, f"Expected >= 30% reduction, got {reduction*100:.1f}%"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/mcp/test_utils/test_format_helper_token_optimization.py::TestAttachToonContentOptimization -v`
Expected: FAIL with "AssertionError: assert 'results' not in result"

**Step 3: Write minimal implementation**

Modify `attach_toon_content_to_response` in `tree_sitter_analyzer/mcp/utils/format_helper.py`:

```python
def attach_toon_content_to_response(result: dict[str, Any]) -> dict[str, Any]:
    """
    Attach TOON formatted content, removing redundant data fields for token optimization.

    This function formats the result as TOON and removes redundant data fields
    to prevent token explosion. Only metadata fields are preserved alongside
    the toon_content field.

    Args:
        result: Original result dictionary from MCP tool

    Returns:
        Optimized dict with toon_content and metadata fields only
    """
    try:
        toon_content = format_as_toon(result)

        # Build optimized response with only metadata and TOON content
        toon_response: dict[str, Any] = {
            "format": "toon",
            "toon_content": toon_content,
        }

        # Preserve only metadata fields (not redundant data)
        for key, value in result.items():
            if key not in TOON_REDUNDANT_FIELDS:
                toon_response[key] = value

        return toon_response

    except Exception as e:
        logger.warning(f"Failed to attach TOON content, returning JSON: {e}")
        return result
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/mcp/test_utils/test_format_helper_token_optimization.py::TestAttachToonContentOptimization -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add tests/unit/mcp/test_utils/test_format_helper_token_optimization.py tree_sitter_analyzer/mcp/utils/format_helper.py
git commit -m "fix: optimize attach_toon_content_to_response to remove redundant fields"
```

---

## Task 3: 优化apply_toon_format_to_response函数

**Files:**
- Modify: `tree_sitter_analyzer/mcp/utils/format_helper.py:150-205`
- Test: `tests/unit/mcp/test_utils/test_format_helper_token_optimization.py`

**Step 1: Write the failing test**

Add to `tests/unit/mcp/test_utils/test_format_helper_token_optimization.py`:

```python
class TestApplyToonFormatOptimization:
    """Tests for apply_toon_format_to_response token optimization."""

    def test_removes_summary_when_structural_overview_present(self):
        """Should remove summary field when structural_overview exists."""
        from tree_sitter_analyzer.mcp.utils.format_helper import apply_toon_format_to_response

        input_data = {
            "success": True,
            "summary": {"classes": 5, "methods": 20},
            "structural_overview": {
                "classes": [{"name": "TestClass"} for _ in range(5)],
                "methods": [{"name": "testMethod"} for _ in range(20)],
            },
        }

        result = apply_toon_format_to_response(input_data, output_format="toon")

        assert "summary" not in result
        assert "structural_overview" not in result
        assert "toon_content" in result

    def test_preserves_summary_when_no_structural_overview(self):
        """Should preserve summary when structural_overview is absent."""
        from tree_sitter_analyzer.mcp.utils.format_helper import apply_toon_format_to_response

        input_data = {
            "success": True,
            "summary": {"classes": 0, "methods": 0},
        }

        result = apply_toon_format_to_response(input_data, output_format="toon")

        # summary should still be in toon_content, but removed from top level
        assert "toon_content" in result

    def test_json_format_unaffected(self):
        """JSON format should not be affected by optimization."""
        from tree_sitter_analyzer.mcp.utils.format_helper import apply_toon_format_to_response

        input_data = {
            "success": True,
            "results": ["a", "b", "c"],
            "summary": {"count": 3},
        }

        result = apply_toon_format_to_response(input_data, output_format="json")

        # JSON format should return unchanged
        assert result == input_data
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/mcp/test_utils/test_format_helper_token_optimization.py::TestApplyToonFormatOptimization -v`
Expected: FAIL

**Step 3: Update implementation**

Modify `apply_toon_format_to_response` in `tree_sitter_analyzer/mcp/utils/format_helper.py`:

```python
def apply_toon_format_to_response(
    result: dict[str, Any], output_format: str = "json"
) -> dict[str, Any]:
    """
    Apply TOON format to MCP tool response if requested.

    When output_format is 'toon', formats the result as TOON and removes
    redundant data fields (results, matches, content, etc.) to maximize
    token savings. Only metadata fields are preserved alongside toon_content.

    Args:
        result: Original result dictionary from MCP tool
        output_format: Output format ('json' or 'toon')

    Returns:
        Modified result dict with TOON content if requested, otherwise original
    """
    if output_format != "toon":
        return result

    try:
        # Format the full result as TOON
        toon_content = format_as_toon(result)

        # Build fields to remove (base redundant fields + conditional)
        fields_to_remove = set(TOON_REDUNDANT_FIELDS)

        # Remove summary when structural_overview exists (summary is derivable)
        if "structural_overview" in result:
            fields_to_remove.add("summary")

        # Create minimal response with only metadata and TOON content
        toon_response: dict[str, Any] = {
            "format": "toon",
            "toon_content": toon_content,
        }

        # Preserve only metadata fields (not redundant data)
        for key, value in result.items():
            if key not in fields_to_remove:
                toon_response[key] = value

        return toon_response

    except Exception as e:
        logger.warning(f"Failed to apply TOON format, returning JSON: {e}")
        return result
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/mcp/test_utils/test_format_helper_token_optimization.py::TestApplyToonFormatOptimization -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add tests/unit/mcp/test_utils/test_format_helper_token_optimization.py tree_sitter_analyzer/mcp/utils/format_helper.py
git commit -m "fix: optimize apply_toon_format_to_response to remove derivable summary"
```

---

## Task 4: 优化analyze_scale_tool空占位符

**Files:**
- Modify: `tree_sitter_analyzer/mcp/tools/analyze_scale_tool.py:454-520`
- Test: `tests/unit/mcp/test_tools/test_analyze_scale_tool_token_optimization.py`

**Step 1: Write the failing test**

Create file `tests/unit/mcp/test_tools/test_analyze_scale_tool_token_optimization.py`:

```python
#!/usr/bin/env python3
"""Tests for token optimization in analyze_scale_tool."""
import pytest


class TestAnalyzeScaleToolTokenOptimization:
    """Tests for analyze_scale_tool token optimization."""

    @pytest.mark.asyncio
    async def test_non_java_file_no_empty_structural_overview(self):
        """Non-Java files should not include empty structural_overview."""
        from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
        import tempfile
        import os

        # Create a Python file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def hello():\n    print("hello")\n')
            temp_path = f.name

        try:
            tool = AnalyzeScaleTool()
            result = await tool.execute({
                "file_path": temp_path,
                "output_format": "json",  # Use JSON to see raw structure
            })

            # Should not have empty structural_overview
            if "structural_overview" in result:
                assert result["structural_overview"] != {}
                assert result["structural_overview"] is not None
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_result_no_empty_placeholder_fields(self):
        """Result should not contain empty placeholder fields."""
        from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
        import tempfile
        import os

        # Create a simple Python file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('# Simple file\nx = 1\n')
            temp_path = f.name

        try:
            tool = AnalyzeScaleTool()
            result = await tool.execute({
                "file_path": temp_path,
                "output_format": "json",
            })

            # Check no empty structural_overview
            if "structural_overview" in result:
                so = result["structural_overview"]
                # Should not be empty dict placeholder
                if isinstance(so, dict):
                    assert len(so) > 0, "structural_overview should not be empty dict"
        finally:
            os.unlink(temp_path)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/mcp/test_tools/test_analyze_scale_tool_token_optimization.py -v`
Expected: FAIL

**Step 3: Update implementation**

Modify `tree_sitter_analyzer/mcp/tools/analyze_scale_tool.py` around line 454-520:

```python
# Replace:
#   analysis_result = None  # Placeholder
#   structural_overview = {}  # Placeholder

# With:
# For non-Java files, we don't have structural analysis
# Don't add placeholder - only add if we have real data
analysis_result = None
structural_overview = None  # Use None instead of empty dict

# Then when building result, only add structural_overview if non-empty:
# (around line 519)
if structural_overview:  # Only add if we have real data
    result["structural_overview"] = structural_overview
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/mcp/test_tools/test_analyze_scale_tool_token_optimization.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/mcp/test_tools/test_analyze_scale_tool_token_optimization.py tree_sitter_analyzer/mcp/tools/analyze_scale_tool.py
git commit -m "fix: remove empty structural_overview placeholder in analyze_scale_tool"
```

---

## Task 5: 运行完整测试套件验证

**Files:**
- No new files

**Step 1: Run all format_helper tests**

Run: `uv run pytest tests/unit/mcp/test_utils/test_format_helper_token_optimization.py -v`
Expected: All PASS

**Step 2: Run existing TOON tests to verify no regression**

Run: `uv run pytest tests/unit/formatters/test_toon*.py -v`
Expected: All PASS

**Step 3: Run analyze_scale_tool tests**

Run: `uv run pytest tests/unit/mcp/test_tools/test_analyze_scale*.py -v`
Expected: All PASS

**Step 4: Run full test suite**

Run: `uv run pytest --tb=short -q`
Expected: All PASS or identify any regressions to fix

**Step 5: Commit if needed**

```bash
git add -A
git commit -m "test: verify token optimization does not break existing tests"
```

---

## Task 6: Token对比基准测试

**Files:**
- Create: `tests/integration/mcp/test_token_reduction_benchmark.py`

**Step 1: Write benchmark test**

```python
#!/usr/bin/env python3
"""Token reduction benchmark tests."""
import json
import pytest


class TestTokenReductionBenchmark:
    """Benchmark tests to verify token reduction."""

    def test_toon_vs_json_token_reduction(self):
        """TOON format should achieve significant token reduction."""
        from tree_sitter_analyzer.mcp.utils.format_helper import (
            apply_toon_format_to_response,
            format_as_json,
            format_as_toon,
        )

        # Create realistic large response
        large_response = {
            "success": True,
            "file_path": "/project/src/main/java/com/example/Service.java",
            "language": "java",
            "file_metrics": {
                "total_lines": 500,
                "code_lines": 400,
                "comment_lines": 50,
                "blank_lines": 50,
                "estimated_tokens": 2500,
            },
            "summary": {
                "classes": 5,
                "methods": 50,
                "fields": 20,
                "imports": 15,
            },
            "structural_overview": {
                "classes": [
                    {
                        "name": f"Class{i}",
                        "type": "class",
                        "start_line": i * 100,
                        "end_line": i * 100 + 80,
                        "line_span": 80,
                        "visibility": "public",
                    }
                    for i in range(5)
                ],
                "methods": [
                    {
                        "name": f"method{i}",
                        "start_line": i * 10,
                        "end_line": i * 10 + 5,
                        "line_span": 5,
                        "visibility": "public" if i % 2 == 0 else "private",
                        "complexity": i % 10,
                    }
                    for i in range(50)
                ],
            },
        }

        # Measure JSON size
        json_output = format_as_json(large_response)
        json_size = len(json_output)

        # Measure optimized TOON response size
        toon_response = apply_toon_format_to_response(large_response, output_format="toon")
        toon_size = len(json.dumps(toon_response))

        # Calculate reduction
        reduction = 1 - (toon_size / json_size)

        print(f"\nJSON size: {json_size:,} chars")
        print(f"TOON optimized size: {toon_size:,} chars")
        print(f"Reduction: {reduction*100:.1f}%")

        # Should achieve at least 40% reduction
        assert reduction >= 0.40, f"Expected >= 40% reduction, got {reduction*100:.1f}%"

    def test_redundant_fields_removed(self):
        """Verify all redundant fields are removed in TOON response."""
        from tree_sitter_analyzer.mcp.utils.format_helper import (
            apply_toon_format_to_response,
            TOON_REDUNDANT_FIELDS,
        )

        # Create response with all possible redundant fields
        response = {
            "success": True,
            "file_path": "/test.py",
            "language": "python",
        }

        # Add all redundant fields with data
        for field in TOON_REDUNDANT_FIELDS:
            response[field] = {"data": f"value_for_{field}"}

        toon_response = apply_toon_format_to_response(response, output_format="toon")

        # Verify no redundant fields in response
        for field in TOON_REDUNDANT_FIELDS:
            assert field not in toon_response, f"Redundant field '{field}' should be removed"

        # Verify metadata preserved
        assert toon_response["success"] is True
        assert toon_response["file_path"] == "/test.py"
        assert "toon_content" in toon_response
```

**Step 2: Run benchmark**

Run: `uv run pytest tests/integration/mcp/test_token_reduction_benchmark.py -v -s`
Expected: PASS with printed reduction percentages

**Step 3: Commit**

```bash
git add tests/integration/mcp/test_token_reduction_benchmark.py
git commit -m "test: add token reduction benchmark tests"
```

---

## Summary

| Task | Description | Files Modified |
|------|-------------|----------------|
| 1 | 添加TOON冗余字段常量 | format_helper.py |
| 2 | 优化attach_toon_content_to_response | format_helper.py |
| 3 | 优化apply_toon_format_to_response | format_helper.py |
| 4 | 移除analyze_scale_tool空占位符 | analyze_scale_tool.py |
| 5 | 运行完整测试验证 | - |
| 6 | Token对比基准测试 | test_token_reduction_benchmark.py |

**Expected Outcome:**
- Token使用量减少 >= 50%
- 所有现有测试通过
- TOON响应不包含冗余数据字段
