import pytest

from tree_sitter_analyzer.mcp.utils.file_metrics import compute_file_metrics
from tree_sitter_analyzer.mcp.utils.shared_cache import get_shared_cache

_INITIAL_CONTENT = "# c\n\nprint('x')\n"
_CHANGED_CONTENT = "# c\n\nprint('y')\n"


@pytest.fixture()
def py_file(tmp_path):
    """A fresh cache + a minimal Python test file."""
    get_shared_cache().clear()
    p = tmp_path / "a.py"
    p.write_text(_INITIAL_CONTENT, encoding="utf-8")
    return p


def _spy_line_metrics(monkeypatch) -> list:
    """Patch _compute_line_metrics to count invocations; returns a [count] list."""
    from tree_sitter_analyzer.mcp.utils import file_metrics as fm

    counter = [0]
    original = fm._compute_line_metrics

    def _spy(content, language):  # noqa: ANN001
        counter[0] += 1
        return original(content, language)

    monkeypatch.setattr(fm, "_compute_line_metrics", _spy)
    return counter


@pytest.mark.unit
def test_file_metrics_schema_contains_required_fields(py_file, tmp_path):
    metrics = compute_file_metrics(
        str(py_file), language="python", project_root=str(tmp_path)
    )
    for k in (
        "total_lines",
        "code_lines",
        "comment_lines",
        "blank_lines",
        "estimated_tokens",
        "file_size_bytes",
    ):
        assert k in metrics


@pytest.mark.unit
def test_file_metrics_cache_hit_avoids_recompute(py_file, tmp_path, monkeypatch):
    counter = _spy_line_metrics(monkeypatch)
    compute_file_metrics(str(py_file), language="python", project_root=str(tmp_path))
    compute_file_metrics(str(py_file), language="python", project_root=str(tmp_path))
    # Only the first call should compute line metrics; the second should hit cache
    assert counter[0] == 1


@pytest.mark.unit
def test_file_metrics_cache_invalidates_on_content_change(
    py_file, tmp_path, monkeypatch
):
    counter = _spy_line_metrics(monkeypatch)
    compute_file_metrics(str(py_file), language="python", project_root=str(tmp_path))
    # Change content => content_hash changes => cache miss => recompute
    py_file.write_text(_CHANGED_CONTENT, encoding="utf-8")
    compute_file_metrics(str(py_file), language="python", project_root=str(tmp_path))
    assert counter[0] == 2
