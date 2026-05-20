"""Class-level extraction helpers for refactoring suggestions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .refactoring_suggestions_helpers import make_extraction

_GENERIC_METHOD_VERBS = {
    "add",
    "analyze",
    "build",
    "calculate",
    "check",
    "clean",
    "collect",
    "create",
    "detect",
    "execute",
    "extract",
    "find",
    "format",
    "get",
    "handle",
    "infer",
    "is",
    "load",
    "make",
    "parse",
    "process",
    "read",
    "render",
    "resolve",
    "run",
    "set",
    "update",
    "validate",
    "write",
}


def find_class_extractions(
    classes: list[dict[str, Any]],
    large_class_rule: dict[str, Any],
    prefix_group_rule: dict[str, Any],
    file_path: str | None = None,
) -> list[dict[str, Any]]:
    """Find extractable class-level patterns."""
    suggestions: list[dict[str, Any]] = []
    for cls in classes:
        responsibility_groups = group_methods_by_responsibility(cls["method_names"])
        if cls["method_count"] > large_class_rule["threshold"]:
            suggestion = make_extraction(
                large_class_rule,
                name=cls["name"],
                actual=cls["method_count"],
                threshold=large_class_rule["threshold"],
                line_range=(cls["line"], cls["end_line"]),
                priority_score=50,
            )
            recipe = build_class_split_recipe(cls, responsibility_groups, file_path)
            if recipe:
                suggestion["recipe"] = recipe
            suggestions.append(suggestion)
        if len(cls["method_names"]) < 3:
            continue
        suggestions.extend(
            find_prefix_group_extractions(
                cls,
                prefix_group_rule,
                responsibility_groups,
                file_path,
            )
        )
    return suggestions


def find_prefix_group_extractions(
    cls: dict[str, Any],
    extraction_rule: dict[str, Any],
    responsibility_groups: list[dict[str, Any]] | None = None,
    file_path: str | None = None,
) -> list[dict[str, Any]]:
    """Find method groups sharing a common prefix for class extraction."""
    suggestions: list[dict[str, Any]] = []
    groups = responsibility_groups or group_methods_by_responsibility(
        cls["method_names"]
    )
    for group_info in groups:
        prefix = group_info["responsibility"]
        group = group_info["methods"]
        if len(group) < 3:
            continue
        if _target_owner_name(cls["name"], prefix) == cls["name"]:
            continue
        suggestion = make_extraction(
            extraction_rule,
            methods=group[:5],
            class_name=cls["name"],
            prefix=prefix,
            line_range=(cls["line"], cls["end_line"]),
            priority_score=35,
        )
        suggestion["recipe"] = build_extract_class_recipe(
            cls,
            prefix,
            group,
            file_path,
        )
        suggestions.append(suggestion)
    return suggestions


def group_methods_by_responsibility(method_names: list[str]) -> list[dict[str, Any]]:
    """Group method names by likely responsibility for extraction recipes."""
    groups: dict[str, list[str]] = {}
    first_seen: dict[str, int] = {}
    for method_name in method_names:
        responsibility = _responsibility_key(method_name)
        if not responsibility:
            continue
        first_seen.setdefault(responsibility, len(first_seen))
        groups.setdefault(responsibility, []).append(method_name)

    return [
        {
            "responsibility": responsibility,
            "methods": methods[:8],
            "count": len(methods),
        }
        for responsibility, methods in sorted(
            groups.items(), key=lambda item: (-len(item[1]), first_seen[item[0]])
        )
        if len(methods) >= 2
    ]


def build_class_split_recipe(
    cls: dict[str, Any],
    responsibility_groups: list[dict[str, Any]],
    file_path: str | None,
) -> dict[str, Any] | None:
    """Build an agent-friendly recipe for splitting a large class."""
    primary = _primary_group(cls["method_names"], responsibility_groups)
    if not primary:
        return None
    recipe = build_extract_class_recipe(
        cls,
        primary["responsibility"],
        primary["methods"],
        file_path,
    )
    recipe["candidate_groups"] = responsibility_groups[:5]
    recipe["stop_condition"] = (
        f"Re-run refactoring_suggestions and confirm {cls['name']} no longer exceeds "
        "the class-size threshold."
    )
    return recipe


def build_extract_class_recipe(
    cls: dict[str, Any],
    responsibility: str,
    methods: list[str],
    file_path: str | None,
) -> dict[str, Any]:
    """Build a concrete extraction recipe for one responsibility group."""
    target_owner = _target_owner_name(cls["name"], responsibility)
    target_module = _target_module_name(cls["name"], responsibility, file_path)
    import_update = _import_update_instruction(cls["name"], target_owner, target_module)
    return {
        "action": "extract_responsibility",
        "target_owner": target_owner,
        "target_module": target_module,
        "move_methods": methods[:8],
        "import_update": import_update,
        "steps": [
            f"Create {target_module} with {target_owner}.",
            f"Move methods {methods[:8]} from {cls['name']} into {target_owner}.",
            import_update,
            "Run the scoped change-impact verification command for the edited files.",
        ],
        "tests": [
            "uv run python -m tree_sitter_analyzer <file> --refactor --format json",
            "uv run python -m tree_sitter_analyzer --change-impact --format json",
        ],
    }


def _primary_group(
    method_names: list[str], responsibility_groups: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Return the best method group to move first."""
    if responsibility_groups:
        return responsibility_groups[0]
    fallback = [name for name in method_names if not name.startswith("__")][:5]
    if not fallback:
        return None
    return {"responsibility": "helpers", "methods": fallback, "count": len(fallback)}


def _responsibility_key(method_name: str) -> str:
    """Infer a stable responsibility key from a method name."""
    cleaned = method_name.strip("_")
    if not cleaned:
        return ""
    parts = [part for part in cleaned.split("_") if part]
    if not parts:
        return ""
    if len(parts) >= 2 and parts[0] in _GENERIC_METHOD_VERBS:
        return parts[1]
    return parts[0]


def _target_owner_name(class_name: str, responsibility: str) -> str:
    """Suggest the class/mixin that should own extracted methods."""
    base = (
        class_name.removesuffix("Extractor").removesuffix("Tool").removesuffix("Mixin")
    )
    responsibility_suffix = _pascal_case(responsibility)
    if responsibility_suffix and base.endswith(responsibility_suffix):
        return f"{base}Mixin"
    return f"{base}{responsibility_suffix}Mixin"


def _target_module_name(
    class_name: str, responsibility: str, file_path: str | None
) -> str:
    """Suggest a sibling module or owner name for extracted responsibility."""
    if not file_path:
        return f"{_snake_case(class_name)}_{responsibility}_mixin"
    path = Path(file_path)
    if path.suffix.lower() != ".py":
        return _target_owner_name(class_name, responsibility)
    source_stem = path.stem.lstrip("_") or path.stem
    module_name = f"_{source_stem}_{responsibility}_mixin.py"
    return str(path.parent / module_name)


def _import_update_instruction(
    class_name: str, target_owner: str, target_module: str
) -> str:
    """Return a concise import/composition update instruction."""
    if target_module.endswith(".py"):
        module_stem = Path(target_module).stem
        return (
            f"Import {target_owner} from {module_stem} and add it to "
            f"{class_name}'s bases or composition path."
        )
    return (
        f"Import or instantiate {target_owner}, then delegate the moved methods from "
        f"{class_name}."
    )


def _pascal_case(value: str) -> str:
    return "".join(part.capitalize() for part in value.split("_") if part)


def _snake_case(value: str) -> str:
    chars: list[str] = []
    for char in value:
        if char.isupper() and chars:
            chars.append("_")
        chars.append(char.lower())
    return "".join(chars).strip("_")
