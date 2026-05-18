"""Performance metric comparison helpers for analyze_differences."""

from typing import Any


def compare_performance_metrics(data_a: Any, data_b: Any) -> list[dict[str, Any]]:
    """Analyze changed performance metrics."""
    differences = []
    metrics_a = extract_performance_metrics(data_a)
    metrics_b = extract_performance_metrics(data_b)

    for path, old_val in metrics_a.items():
        if path not in metrics_b:
            continue
        new_val = metrics_b[path]
        if old_val != new_val and old_val > 0:
            differences.append(_performance_change(path, old_val, new_val))

    return differences


def extract_performance_metrics(obj: Any, path: str = "") -> dict[str, int | float]:
    """Extract numeric performance-like fields from nested dictionaries."""
    metrics = {}
    if not isinstance(obj, dict):
        return metrics

    for key, value in obj.items():
        new_path = f"{path}.{key}" if path else key
        if _is_performance_metric(key, value):
            metrics[new_path] = value
        elif isinstance(value, dict):
            metrics.update(extract_performance_metrics(value, new_path))

    return metrics


def _performance_change(
    path: str,
    old_value: int | float,
    new_value: int | float,
) -> dict[str, Any]:
    change_percent = ((new_value - old_value) / old_value) * 100
    return {
        "type": "performance_change",
        "path": path,
        "old_value": old_value,
        "new_value": new_value,
        "change_percent": round(change_percent, 2),
        "severity": "low",
    }


def _is_performance_metric(key: str, value: Any) -> bool:
    return isinstance(value, int | float) and (
        key.endswith("_ms") or key.endswith("_time") or "elapsed" in key
    )
