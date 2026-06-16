"""Tests for SemanticClassifyTool MCP tool and integration."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.tools.semantic_classify_tool import SemanticClassifyTool


@pytest.fixture
def tool():
    return SemanticClassifyTool(project_root=None)


def _run(tool_instance: SemanticClassifyTool, args: dict[str, Any]) -> dict[str, Any]:
    return asyncio.run(tool_instance.execute(args))


class TestSemanticClassifyToolDefinition:
    def test_tool_name(self, tool: SemanticClassifyTool):
        defn = tool.get_tool_definition()
        assert defn["name"] == "semantic_classify"

    def test_mode_is_optional_in_schema(self, tool: SemanticClassifyTool):
        # Wave 1b (audit edit-10): mode is resolved at runtime (defaults to
        # classify_file when file_path is given), so it must NOT be required —
        # else a strict MCP client rejects a valid {file_path: X} call.
        schema = tool.get_tool_schema()
        assert "mode" in schema["properties"]
        assert "mode" not in schema.get("required", [])

    def test_resolve_mode_defaults(self, tool: SemanticClassifyTool):
        assert tool._resolve_mode({"file_path": "x.py"}) == "classify_file"
        assert (
            tool._resolve_mode({"old_source": "a", "new_source": "b"})
            == "classify_string"
        )
        assert tool._resolve_mode({}) == "classify_string"
        # explicit mode always wins
        assert (
            tool._resolve_mode({"mode": "classify_string", "file_path": "x.py"})
            == "classify_string"
        )

    def test_file_path_only_does_not_demand_sources(self, tool: SemanticClassifyTool):
        # The edit-10 bug: classify file_path=X raised "old_source... required".
        # With the file-default it validates as classify_file instead.
        assert tool.validate_arguments({"file_path": "some/file.py"}) is True


class TestSemanticClassifyValidation:
    def test_classify_file_requires_path(self, tool: SemanticClassifyTool):
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments({"mode": "classify_file"})

    def test_classify_string_requires_sources(self, tool: SemanticClassifyTool):
        with pytest.raises(ValueError, match="old_source and new_source"):
            tool.validate_arguments({"mode": "classify_string", "language": "python"})

    def test_classify_string_requires_language(self, tool: SemanticClassifyTool):
        with pytest.raises(ValueError, match="language is required"):
            tool.validate_arguments(
                {
                    "mode": "classify_string",
                    "old_source": "x",
                    "new_source": "y",
                }
            )

    def test_valid_classify_file(self, tool: SemanticClassifyTool):
        assert tool.validate_arguments({"mode": "classify_file", "file_path": "foo.py"})


class TestSemanticClassifyExecution:
    def test_classify_string_function_added(self, tool: SemanticClassifyTool):
        result = _run(
            tool,
            {
                "mode": "classify_string",
                "old_source": "",
                "new_source": "def hello():\n    pass\n",
                "language": "python",
            },
        )
        assert result["success"] is True
        assert result["dominant_category"] == "feature_addition"
        key = "num_changes" if "num_changes" in result else "change_count"
        assert result[key] > 0

    def test_classify_string_signature_changed(self, tool: SemanticClassifyTool):
        result = _run(
            tool,
            {
                "mode": "classify_string",
                "old_source": "def greet(name):\n    pass\n",
                "new_source": "def greet(name, greeting='Hello'):\n    pass\n",
                "language": "python",
            },
        )
        assert result["success"] is True
        assert result["dominant_category"] in (
            "api_change",
            "refactor",
            "internal_change",
        )

    def test_classify_string_no_changes(self, tool: SemanticClassifyTool):
        result = _run(
            tool,
            {
                "mode": "classify_string",
                "old_source": "def foo():\n    pass\n",
                "new_source": "def foo():\n    pass\n",
                "language": "python",
            },
        )
        assert result["success"] is True
        assert result["verdict"] == "NOT_FOUND"

    def test_classify_string_function_removed(self, tool: SemanticClassifyTool):
        result = _run(
            tool,
            {
                "mode": "classify_string",
                "old_source": "def public_api():\n    return 1\n\ndef helper():\n    pass\n",
                "new_source": "",
                "language": "python",
            },
        )
        assert result["success"] is True
        assert result["dominant_category"] == "feature_removal"

    def test_classify_string_import_change(self, tool: SemanticClassifyTool):
        result = _run(
            tool,
            {
                "mode": "classify_string",
                "old_source": "import os\n",
                "new_source": "import os\nimport sys\n",
                "language": "python",
            },
        )
        assert result["success"] is True
        assert result["dominant_category"] == "import_change"

    def test_classify_string_body_change(self, tool: SemanticClassifyTool):
        result = _run(
            tool,
            {
                "mode": "classify_string",
                "old_source": "def compute(x):\n    return x + 1\n",
                "new_source": "def compute(x):\n    return x * 2\n",
                "language": "python",
            },
        )
        assert result["success"] is True
        assert result["dominant_category"] == "internal_change"

    def test_toon_format(self, tool: SemanticClassifyTool):
        result = _run(
            tool,
            {
                "mode": "classify_string",
                "old_source": "",
                "new_source": "def foo(): pass\n",
                "language": "python",
                "output_format": "toon",
            },
        )
        assert "toon_content" in result or result["success"] is True


class TestSemanticClassifyToolRegistry:
    def test_tool_registered(self):
        # Wave C2: semantic_classify is now the edit facade action=classify.
        from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry

        _, by_name = create_tool_registry(None)
        assert "edit" in by_name
        assert "classify" in by_name["edit"].action_map
        assert (
            type(by_name["edit"].action_map["classify"]).__name__
            == "SemanticClassifyTool"
        )

    def test_tool_in_cli_class_names(self):
        from tree_sitter_analyzer.cli.commands.mcp_commands import _TOOL_CLASS_NAMES

        assert "SemanticClassifyTool" in _TOOL_CLASS_NAMES


class TestSemanticClassifyChangeImpactIntegration:
    def test_change_impact_includes_semantic_when_changed(self, tmp_path):
        from tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis import (
            _classify_changed_files,
        )

        py_file = tmp_path / "example.py"
        py_file.write_text("def greet(name):\n    return f'Hello {name}'\n")

        results = _classify_changed_files(
            changed_files=["example.py"],
            project_root=str(tmp_path),
        )
        assert isinstance(results, list)

    def test_classify_changed_files_empty(self):
        from tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis import (
            _classify_changed_files,
        )

        assert _classify_changed_files([], None) == []
        assert _classify_changed_files(["x.py"], None) == []


# ── #528 byte-budget tests ────────────────────────────────────────────────────

# Shared source fixtures that reliably trigger the AST children bloat.
# classify_string mode is used so tests work without a git repo.
_SRC_V1 = (
    "import os\n"
    "import sys\n"
    "\n"
    "\n"
    "class MyService:\n"
    "    def __init__(self, name: str) -> None:\n"
    "        self.name = name\n"
    "        self.data: list[str] = []\n"
    "\n"
    "    def start(self) -> bool:\n"
    "        print(f'Starting {self.name}')\n"
    "        return True\n"
    "\n"
    "    def stop(self) -> None:\n"
    "        self.data.clear()\n"
    "\n"
    "    def process(self, item: str) -> str:\n"
    "        return item.upper()\n"
    "\n"
    "\n"
    "def helper_one(x: int) -> int:\n"
    "    return x + 1\n"
    "\n"
    "\n"
    "def helper_two(x: int, y: int) -> int:\n"
    "    return x * y\n"
)

_SRC_V2 = (
    "import os\n"
    "import sys\n"
    "import logging\n"
    "\n"
    "\n"
    "class MyService:\n"
    "    def __init__(self, name: str, timeout: int = 30) -> None:\n"
    "        self.name = name\n"
    "        self.timeout = timeout\n"
    "        self.data: list[str] = []\n"
    "\n"
    "    def start(self, retry: bool = False) -> bool:\n"
    "        logging.info(f'Starting {self.name} retry={retry}')\n"
    "        return True\n"
    "\n"
    "    def stop(self) -> None:\n"
    "        self.data.clear()\n"
    "\n"
    "    def process(self, item: str) -> str:\n"
    "        result = item.strip().upper()\n"
    "        return result\n"
    "\n"
    "    def status(self) -> dict:\n"
    "        return {'name': self.name, 'items': len(self.data)}\n"
    "\n"
    "\n"
    "def helper_one(x: int) -> int:\n"
    "    return x + 1\n"
    "\n"
    "\n"
    "def helper_two(x: int, y: int) -> int:\n"
    "    return x * y\n"
)


# Minimal git repo fixture — used for the classify_file / git-diff invariant test only.
@pytest.fixture
def git_repo_with_two_commits(tmp_path):
    """Minimal git repo with a before/after commit so classify_file can run."""
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    env = {
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "t@t.com",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "t@t.com",
        "HOME": str(tmp_path),
        "PATH": __import__("os").environ["PATH"],
    }

    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, env=env)
    subprocess.run(
        ["git", "config", "user.email", "t@t.com"],
        cwd=repo,
        check=True,
        capture_output=True,
        env=env,
    )
    subprocess.run(
        ["git", "config", "user.name", "test"],
        cwd=repo,
        check=True,
        capture_output=True,
        env=env,
    )
    (repo / "service.py").write_text(_SRC_V1)
    subprocess.run(
        ["git", "add", "service.py"], cwd=repo, check=True, capture_output=True, env=env
    )
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo,
        check=True,
        capture_output=True,
        env=env,
    )
    (repo / "service.py").write_text(_SRC_V2)
    subprocess.run(
        ["git", "add", "service.py"], cwd=repo, check=True, capture_output=True, env=env
    )
    subprocess.run(
        ["git", "commit", "-m", "add features"],
        cwd=repo,
        check=True,
        capture_output=True,
        env=env,
    )
    return repo


class TestCompactHelpers:
    """Unit tests for _compact_classification / _compact_hunk helpers (#528)."""

    def test_compact_classification_passthrough_when_include_ast_nodes(self):
        from tree_sitter_analyzer.mcp.tools.semantic_classify_tool import (
            _compact_classification,
        )

        entry = {
            "category": "refactor",
            "hunk": {"old": {"type": "fn", "children": [{"x": 1}]}},
        }
        result = _compact_classification(entry, include_ast_nodes=True)
        assert result is entry  # exact same object, no copy

    def test_compact_classification_returns_entry_when_hunk_not_dict(self):
        """Covers the defensive branch when hunk is None or missing."""
        from tree_sitter_analyzer.mcp.tools.semantic_classify_tool import (
            _compact_classification,
        )

        entry_no_hunk = {"category": "refactor"}
        result = _compact_classification(entry_no_hunk, include_ast_nodes=False)
        assert result is entry_no_hunk

        entry_null_hunk = {"category": "refactor", "hunk": None}
        result2 = _compact_classification(entry_null_hunk, include_ast_nodes=False)
        assert result2 is entry_null_hunk

    def test_compact_hunk_strips_children_from_old_and_new(self):
        from tree_sitter_analyzer.mcp.tools.semantic_classify_tool import _compact_hunk

        hunk = {
            "kind": "modified",
            "old": {"type": "fn", "line": 1, "children": [{"x": 1}, {"y": 2}]},
            "new": {"type": "fn", "line": 5, "children": [{"z": 3}]},
        }
        result = _compact_hunk(hunk)
        assert "children" not in result["old"]
        assert "children" not in result["new"]
        assert result["old"]["type"] == "fn"
        assert result["new"]["type"] == "fn"
        assert result["kind"] == "modified"

    def test_compact_hunk_passthrough_non_old_new_keys(self):
        from tree_sitter_analyzer.mcp.tools.semantic_classify_tool import _compact_hunk

        hunk = {"kind": "added", "summary": "hello", "details": {"x": 1}}
        result = _compact_hunk(hunk)
        assert result["kind"] == "added"
        assert result["summary"] == "hello"
        assert result["details"] == {"x": 1}

    def test_compact_hunk_old_new_non_dict_passthrough(self):
        """When old/new value is not a dict, pass it through unchanged."""
        from tree_sitter_analyzer.mcp.tools.semantic_classify_tool import _compact_hunk

        # 'old' and 'new' that are not dicts (e.g., None or a string)
        hunk = {"kind": "deleted", "old": None, "new": "not_a_dict"}
        result = _compact_hunk(hunk)
        assert result["old"] is None
        assert result["new"] == "not_a_dict"


class TestClassifyByteBudget:
    """#528 — default response must not inline full AST subtrees."""

    def test_schema_has_include_ast_nodes_param(self, tool: SemanticClassifyTool):
        """include_ast_nodes opt-in must be declared in schema, not required."""
        schema = tool.get_tool_schema()
        props = schema["properties"]
        assert "include_ast_nodes" in props, (
            "include_ast_nodes param missing from schema"
        )
        assert props["include_ast_nodes"]["type"] == "boolean"
        assert "include_ast_nodes" not in schema.get("required", [])

    def test_schema_has_hunk_cap_param(self, tool: SemanticClassifyTool):
        """hunk_cap opt-in must be declared in schema, not required."""
        schema = tool.get_tool_schema()
        props = schema["properties"]
        assert "hunk_cap" in props, "hunk_cap param missing from schema"
        assert props["hunk_cap"]["type"] == "integer"
        assert "hunk_cap" not in schema.get("required", [])

    def test_default_classifications_have_no_ast_children(
        self, tool: SemanticClassifyTool
    ):
        """By default, each entry in classifications must not contain hunk.old/new children.

        Uses classify_string mode — reliably triggers AST children without a git repo.
        """
        result = _run(
            tool,
            {
                "mode": "classify_string",
                "old_source": _SRC_V1,
                "new_source": _SRC_V2,
                "language": "python",
                "output_format": "json",
            },
        )
        assert result["success"] is True
        assert result.get("change_count") == 10  # _SRC_V1→_SRC_V2 fixed fixture
        for entry in result.get("classifications", []):
            hunk = entry.get("hunk", {})
            old_node = hunk.get("old", {})
            new_node = hunk.get("new", {})
            assert "children" not in old_node, (
                "hunk.old.children must not appear in default response"
            )
            assert "children" not in new_node, (
                "hunk.new.children must not appear in default response"
            )

    def test_default_response_exact_bytes_string_mode(self, tool: SemanticClassifyTool):
        """Exact byte pin (string mode, deterministic fixture).

        Pre-fix this fixture serialized to ~100KB (120× the 837-byte raw
        diff — full AST subtrees inlined). The exact post-fix pin makes ANY
        response-size drift go red and forces a conscious re-pin (locked
        exact-assertion rule; a ratio ceiling let bloat regrow silently).
        """
        import difflib
        import json

        raw_diff = "".join(
            difflib.unified_diff(
                _SRC_V1.splitlines(keepends=True),
                _SRC_V2.splitlines(keepends=True),
                fromfile="service.py",
                tofile="service.py",
            )
        )
        assert len(raw_diff.encode()) == 837

        result = _run(
            tool,
            {
                "mode": "classify_string",
                "old_source": _SRC_V1,
                "new_source": _SRC_V2,
                "language": "python",
                "output_format": "json",
            },
        )
        assert result["success"] is True
        assert len(json.dumps(result)) == 4544

    def test_default_response_leq_raw_diff_bytes_git_mode(
        self, tool: SemanticClassifyTool, git_repo_with_two_commits
    ):
        """Differential invariant (git mode): default classify_file response ≤ raw git diff bytes."""
        import json
        import subprocess

        repo = git_repo_with_two_commits
        local_tool = SemanticClassifyTool(project_root=str(repo))
        result = _run(
            local_tool,
            {
                "mode": "classify_file",
                "file_path": "service.py",
                "old_ref": "HEAD~1",
                "new_ref": "HEAD",
                "output_format": "json",
            },
        )
        assert result["success"] is True

        raw_diff = subprocess.run(
            ["git", "diff", "HEAD~1", "HEAD", "--", "service.py"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        raw_diff_bytes = len(raw_diff.encode())
        response_bytes = len(json.dumps(result))

        assert response_bytes <= raw_diff_bytes, (
            f"Default classify_file response ({response_bytes} bytes) "
            f"exceeds raw git diff ({raw_diff_bytes} bytes). "
            "Full AST subtrees must not be inlined by default."
        )

    def test_default_response_has_verdict_and_summary_fields(
        self, tool: SemanticClassifyTool
    ):
        """Default response must carry verdict, dominant_category, risk_level, change_summary,
        category_counts, diff_hunks, change_count — the essential scalar fields."""
        result = _run(
            tool,
            {
                "mode": "classify_string",
                "old_source": _SRC_V1,
                "new_source": _SRC_V2,
                "language": "python",
                "output_format": "json",
            },
        )
        for field in (
            "success",
            "verdict",
            "dominant_category",
            "risk_level",
            "change_summary",
            "category_counts",
            "diff_hunks",
            "change_count",
            "classifications",
        ):
            assert field in result, (
                f"Required field '{field}' missing from default response"
            )

    def test_truncation_honesty_fields_when_capped(self, tool: SemanticClassifyTool):
        """When hunk_cap limits the output, truncated/listed_cap/next_step must appear."""
        result = _run(
            tool,
            {
                "mode": "classify_string",
                "old_source": _SRC_V1,
                "new_source": _SRC_V2,
                "language": "python",
                "output_format": "json",
                "hunk_cap": 2,
            },
        )
        assert result["success"] is True
        # _SRC_V1→_SRC_V2 fixed fixture: 10 changes (> the cap of 2, so
        # truncation below is meaningfully exercised)
        assert result.get("change_count") == 10
        assert result.get("truncated") is True, "truncated must be True when cap is hit"
        assert "listed_cap" in result, "listed_cap must appear when truncated"
        assert "next_step" in result, "next_step must appear when truncated"
        assert len(result["classifications"]) == 2

    def test_include_ast_nodes_opt_in_adds_hunk_detail(
        self, tool: SemanticClassifyTool
    ):
        """With include_ast_nodes=True, hunk.old/new details appear in classifications."""
        result = _run(
            tool,
            {
                "mode": "classify_string",
                "old_source": _SRC_V1,
                "new_source": _SRC_V2,
                "language": "python",
                "output_format": "json",
                "include_ast_nodes": True,
            },
        )
        assert result["success"] is True
        classifications = result.get("classifications", [])
        assert len(classifications) == 10  # _SRC_V1→_SRC_V2 fixed fixture
        has_hunk_detail = any(
            "old" in entry.get("hunk", {}) or "new" in entry.get("hunk", {})
            for entry in classifications
        )
        assert has_hunk_detail, (
            "include_ast_nodes=True must populate hunk.old/new details"
        )

    def test_include_ast_nodes_delivers_children_in_hunk_nodes(
        self, tool: SemanticClassifyTool
    ):
        """Regression for #694 follow-up: include_ast_nodes=True must deliver
        the AST node children; ClassifiedHunk.to_dict() must forward
        include_children=True to ASTDiffHunk.to_dict().

        Fixture: a single-function signature change — always produces a
        signature_changed hunk with 5 children in both old and new node (the
        function's parameter list + body child nodes extracted by tree-sitter).
        """
        _OLD = "def greet(name):\n    return f'Hello {name}'\n"
        _NEW = "def greet(name, greeting='Hello'):\n    return f'{greeting} {name}'\n"

        result = _run(
            tool,
            {
                "mode": "classify_string",
                "old_source": _OLD,
                "new_source": _NEW,
                "language": "python",
                "output_format": "json",
                "include_ast_nodes": True,
            },
        )
        assert result["success"] is True

        # Find the signature_changed hunk (always present for this fixture).
        sig_entries = [
            e
            for e in result.get("classifications", [])
            if e.get("hunk", {}).get("kind") == "signature_changed"
        ]
        assert len(sig_entries) == 1, (
            "Expected exactly 1 signature_changed classification for the greet fixture"
        )

        hunk = sig_entries[0]["hunk"]
        old_node = hunk.get("old", {})
        new_node = hunk.get("new", {})

        # Children MUST be present — this is the gap that #694 broke.
        assert "children" in old_node, (
            "hunk.old must contain 'children' when include_ast_nodes=True "
            "(ClassifiedHunk.to_dict must pass include_children=True)"
        )
        assert "children" in new_node, (
            "hunk.new must contain 'children' when include_ast_nodes=True "
            "(ClassifiedHunk.to_dict must pass include_children=True)"
        )

        # Pin exact counts (5 children in both old and new for this fixture).
        assert len(old_node["children"]) == 5, (
            f"Expected 5 children in old node, got {len(old_node['children'])}"
        )
        assert len(new_node["children"]) == 5, (
            f"Expected 5 children in new node, got {len(new_node['children'])}"
        )


class TestClassifiedHunkSerializerOptIn:
    """BUG A (Codex P2 #696 follow-up): ClassifiedHunk.to_dict() must accept
    include_children param and default to lean (no children).  The PR-review
    consumer calls ch.to_dict() without opt-in → must never embed AST subtrees.
    """

    def _make_classified_hunk(self) -> Any:
        """Return a real ClassifiedHunk with a hunk whose old/new nodes have children."""
        from tree_sitter_analyzer.ast_diff import ASTDiffer
        from tree_sitter_analyzer.semantic_change_classifier import (
            SemanticChangeClassifier,
        )

        old = "def greet(name):\n    return f'Hello {name}'\n"
        new = "def greet(name, greeting='Hello'):\n    return f'{greeting} {name}'\n"
        differ = ASTDiffer()
        diff = differ.diff_strings(old, new, "python")
        classifier = SemanticChangeClassifier()
        classification = classifier.classify(diff)
        assert classification.classifications, (
            "Fixture must produce at least one ClassifiedHunk"
        )
        return classification.classifications[0]

    def test_classified_hunk_to_dict_default_is_lean(self):
        """ClassifiedHunk.to_dict() with no args must NOT include children keys.

        This is the consumer contract for codegraph_pr_review — it calls
        ch.to_dict() raw (no include_children kwarg), so the default must
        be lean.  Before the fix, to_dict() hard-coded include_children=True,
        leaking full AST subtrees into every PR-review high_risk_changes entry.
        """
        ch = self._make_classified_hunk()
        d = ch.to_dict()
        hunk = d.get("hunk", {})
        old_node = hunk.get("old", {})
        new_node = hunk.get("new", {})
        assert "children" not in old_node, (
            "hunk.old must NOT contain 'children' in default (lean) ClassifiedHunk.to_dict() — "
            "codegraph_pr_review calls ch.to_dict() raw and must not embed AST subtrees"
        )
        assert "children" not in new_node, (
            "hunk.new must NOT contain 'children' in default (lean) ClassifiedHunk.to_dict()"
        )

    def test_classified_hunk_to_dict_opt_in_delivers_children(self):
        """ClassifiedHunk.to_dict(include_children=True) must still deliver children.

        Ensures the semantic_classify opt-in path (include_ast_nodes=True) continues
        to work after the parameterization fix.
        """
        ch = self._make_classified_hunk()
        d = ch.to_dict(include_children=True)
        hunk = d.get("hunk", {})
        old_node = hunk.get("old", {})
        new_node = hunk.get("new", {})
        assert "children" in old_node, (
            "hunk.old must contain 'children' when include_children=True"
        )
        assert "children" in new_node, (
            "hunk.new must contain 'children' when include_children=True"
        )

    def test_semantic_classification_to_dict_default_is_lean(self):
        """SemanticClassification.to_dict() must thread include_children=False to each ClassifiedHunk."""
        from tree_sitter_analyzer.ast_diff import ASTDiffer
        from tree_sitter_analyzer.semantic_change_classifier import (
            SemanticChangeClassifier,
        )

        old = "def greet(name):\n    return f'Hello {name}'\n"
        new = "def greet(name, greeting='Hello'):\n    return f'{greeting} {name}'\n"
        differ = ASTDiffer()
        diff = differ.diff_strings(old, new, "python")
        classifier = SemanticChangeClassifier()
        classification = classifier.classify(diff)
        d = classification.to_dict()
        for entry in d.get("classifications", []):
            hunk = entry.get("hunk", {})
            assert "children" not in hunk.get("old", {}), (
                "SemanticClassification.to_dict() default must not embed children in hunk.old"
            )
            assert "children" not in hunk.get("new", {}), (
                "SemanticClassification.to_dict() default must not embed children in hunk.new"
            )

    def test_semantic_classification_to_dict_opt_in_delivers_children(self):
        """SemanticClassification.to_dict(include_children=True) must deliver children."""
        from tree_sitter_analyzer.ast_diff import ASTDiffer
        from tree_sitter_analyzer.semantic_change_classifier import (
            SemanticChangeClassifier,
        )

        old = "def greet(name):\n    return f'Hello {name}'\n"
        new = "def greet(name, greeting='Hello'):\n    return f'{greeting} {name}'\n"
        differ = ASTDiffer()
        diff = differ.diff_strings(old, new, "python")
        classifier = SemanticChangeClassifier()
        classification = classifier.classify(diff)
        d = classification.to_dict(include_children=True)
        found_children = False
        for entry in d.get("classifications", []):
            hunk = entry.get("hunk", {})
            if "children" in hunk.get("old", {}) or "children" in hunk.get("new", {}):
                found_children = True
                break
        assert found_children, (
            "SemanticClassification.to_dict(include_children=True) must deliver children "
            "in at least one hunk.old or hunk.new"
        )
