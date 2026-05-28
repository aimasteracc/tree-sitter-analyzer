"""Task-dispatch helpers for :mod:`toon_encoder`."""

from typing import Any


def build_task_handlers(
    task_type: Any,
    encoder: Any,
    stack: list[Any],
    output: list[str],
    seen_ids: set[int],
) -> dict[Any, Any]:
    """Build task handlers for the iterative TOON encoder."""
    return {
        task_type.ENCODE_DICT_START: lambda task: encoder.handle_dict_start(
            task,
            stack,
            output,
            seen_ids,
        ),
        task_type.ENCODE_DICT_KEY: lambda task: encoder.handle_dict_key(
            task,
            stack,
            output,
            seen_ids,
        ),
        task_type.ENCODE_LIST_START: lambda task: encoder.handle_list_start(
            task,
            stack,
            output,
            seen_ids,
        ),
        task_type.ENCODE_LIST_ITEM: lambda task: encoder.handle_list_item(
            task,
            stack,
            output,
            seen_ids,
        ),
        task_type.ENCODE_ARRAY_TABLE: lambda task: encoder.handle_array_table(
            task,
            output,
            seen_ids,
        ),
        task_type.ENCODE_DICT_END: lambda task: seen_ids.discard(id(task.data)),
        task_type.ENCODE_LIST_END: lambda task: seen_ids.discard(id(task.data)),
    }
