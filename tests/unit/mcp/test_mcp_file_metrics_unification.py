import pytest

from tree_sitter_analyzer.mcp.utils.file_metrics import compute_file_metrics
from tree_sitter_analyzer.mcp.utils.shared_cache import get_shared_cache


@pytest.mark.unit
def test_file_metrics_schema_contains_required_fields(tmp_path):
    get_shared_cache().clear()

    p = tmp_path / "a.py"
    p.write_text("# c\n\nprint('x')\n", encoding="utf-8")

    metrics = compute_file_metrics(
        str(p), language="python", project_root=str(tmp_path)
    )

    for k in [
        "total_lines",
        "code_lines",
        "comment_lines",
        "blank_lines",
        "estimated_tokens",
        "file_size_bytes",
    ]:
        assert k in metrics


@pytest.mark.unit
def test_file_metrics_cache_hit_avoids_recompute(tmp_path, monkeypatch):
    get_shared_cache().clear()

    p = tmp_path / "a.py"
    p.write_text("# c\n\nprint('x')\n", encoding="utf-8")

    calls = 0

    from tree_sitter_analyzer.mcp.utils import file_metrics as fm

    original = fm._compute_line_metrics

    def _spy(content, language):  # noqa: ANN001
        nonlocal calls
        calls += 1
        return original(content, language)

    monkeypatch.setattr(fm, "_compute_line_metrics", _spy)

    compute_file_metrics(str(p), language="python", project_root=str(tmp_path))
    compute_file_metrics(str(p), language="python", project_root=str(tmp_path))

    # Only the first call should compute line metrics; the second should hit cache
    assert calls == 1


@pytest.mark.unit
def test_file_metrics_cache_invalidates_on_content_change(tmp_path, monkeypatch):
    get_shared_cache().clear()

    p = tmp_path / "a.py"
    p.write_text("# c\n\nprint('x')\n", encoding="utf-8")

    calls = 0

    from tree_sitter_analyzer.mcp.utils import file_metrics as fm

    original = fm._compute_line_metrics

    def _spy(content, language):  # noqa: ANN001
        nonlocal calls
        calls += 1
        return original(content, language)

    monkeypatch.setattr(fm, "_compute_line_metrics", _spy)

    compute_file_metrics(str(p), language="python", project_root=str(tmp_path))

    # Change content => content_hash changes => cache miss => recompute
    p.write_text("# c\n\nprint('y')\n", encoding="utf-8")
    compute_file_metrics(str(p), language="python", project_root=str(tmp_path))

    assert calls == 2
