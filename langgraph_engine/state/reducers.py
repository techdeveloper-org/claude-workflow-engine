"""Reducer functions for LangGraph concurrent state updates.

These reducers handle cases where multiple parallel nodes in the StateGraph
write to the same field simultaneously, preventing INVALID_CONCURRENT_GRAPH_UPDATE errors.
"""


def _keep_first_value(current_value, update_value):
    """Reducer for immutable fields - always keep the first value.

    Used for session_id and other fields that should never change.
    This prevents LangGraph from complaining about multiple updates.
    """
    return current_value if current_value is not None else update_value


def _merge_lists(current_value, update_value):
    """Reducer for list fields that receive concurrent updates from parallel nodes.

    Merges lists instead of raising INVALID_CONCURRENT_GRAPH_UPDATE.
    Used for: pipeline, errors, warnings - fields written by multiple parallel nodes.
    """
    if current_value is None:
        return update_value if update_value is not None else []
    if update_value is None:
        return current_value
    if isinstance(current_value, list) and isinstance(update_value, list):
        return current_value + update_value
    return update_value


def _merge_dicts(current_value, update_value):
    """Reducer for dict fields that may receive concurrent updates.

    Merges dicts (update overwrites existing keys) instead of raising error.
    Used for: step3_phase_file_map and similar dict fields from parallel nodes.
    """
    if current_value is None:
        return update_value if update_value is not None else {}
    if update_value is None:
        return current_value
    if isinstance(current_value, dict) and isinstance(update_value, dict):
        merged = dict(current_value)
        merged.update(update_value)
        return merged
    return update_value
