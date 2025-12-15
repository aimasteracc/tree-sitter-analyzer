import pytest

from tree_sitter_analyzer.mcp.tools.base_tool import BaseMCPTool
from tree_sitter_analyzer.mcp.utils.path_resolver import PathResolver
from tree_sitter_analyzer.mcp.utils.shared_cache import get_shared_cache
from tree_sitter_analyzer.security.validator import SecurityValidator


class _DummyFileTool(BaseMCPTool):
    def get_tool_definition(self):
        return {"name": "dummy", "description": "dummy", "inputSchema": {}}

    async def execute(self, arguments):
        self.validate_arguments(arguments)
        resolved = self.resolve_and_validate_file_path(arguments["file_path"])
        return {"resolved_file_path": resolved}

    def validate_arguments(self, arguments):
        if "file_path" not in arguments:
            raise ValueError("file_path is required")
        return True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_security_validation_is_cached_within_same_project_root(
    tmp_path, monkeypatch
):
    get_shared_cache().clear()

    project_root = tmp_path / "proj"
    (project_root / "src").mkdir(parents=True)
    target = project_root / "src" / "main.py"
    target.write_text("print('hello')\n", encoding="utf-8")

    validate_calls = 0
    resolve_calls = 0

    original_validate = SecurityValidator.validate_file_path
    original_resolve = PathResolver.resolve

    def _validate_spy(self, file_path, base_path=None):  # noqa: ANN001
        nonlocal validate_calls
        validate_calls += 1
        return original_validate(self, file_path, base_path)

    def _resolve_spy(self, file_path):  # noqa: ANN001
        nonlocal resolve_calls
        resolve_calls += 1
        return original_resolve(self, file_path)

    tool = _DummyFileTool(project_root=str(project_root))

    # Patch class methods (instances dispatch to class implementation)
    monkeypatch.setattr(SecurityValidator, "validate_file_path", _validate_spy)
    monkeypatch.setattr(PathResolver, "resolve", _resolve_spy)

    # First call: resolve + validate
    await tool.execute({"file_path": "src/main.py"})
    # Second call: should reuse shared cache (no additional resolve/validate)
    await tool.execute({"file_path": "src/main.py"})

    assert resolve_calls == 1
    assert validate_calls == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cache_is_invalidated_on_project_root_change(tmp_path, monkeypatch):
    get_shared_cache().clear()

    root1 = tmp_path / "proj1"
    (root1 / "src").mkdir(parents=True)
    (root1 / "src" / "a.py").write_text("print('a')\n", encoding="utf-8")

    root2 = tmp_path / "proj2"
    (root2 / "src").mkdir(parents=True)
    (root2 / "src" / "a.py").write_text("print('a2')\n", encoding="utf-8")

    validate_calls = 0

    original_validate = SecurityValidator.validate_file_path

    def _validate_spy(self, file_path, base_path=None):  # noqa: ANN001
        nonlocal validate_calls
        validate_calls += 1
        return original_validate(self, file_path, base_path)

    tool = _DummyFileTool(project_root=str(root1))

    monkeypatch.setattr(SecurityValidator, "validate_file_path", _validate_spy)

    await tool.execute({"file_path": "src/a.py"})
    tool.set_project_path(str(root2))  # triggers cache clear
    await tool.execute({"file_path": "src/a.py"})

    # One validation per distinct project root after invalidation
    assert validate_calls == 2
