# BACKWARD-COMPAT SHIM
# GitHub operations logic moved to scripts/github_operations/
# This file re-exports all symbols so existing imports keep working.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from github_operations.branch_manager import create_issue_branch, get_session_branch, is_on_issue_branch  # noqa: F401
from github_operations.client import GH_TIMEOUT, MAX_OPS_PER_SESSION, _run_gh_cmd, is_gh_available  # noqa: F401
from github_operations.issue_manager import (  # noqa: F401
    _build_close_comment,
    _debug_log_gh,
    _get_flow_trace_context,
    _get_repo_root,
    _get_session_progress_context,
    _get_tool_activity_for_task,
    _slugify,
    close_github_issue,
    create_github_issue,
    extract_task_id_from_response,
)
from github_operations.labels import (  # noqa: F401
    LABEL_DEFINITIONS,
    _build_issue_labels,
    _detect_issue_type,
    _detect_scope_labels,
    _ensure_labels_exist,
    _get_priority_labels,
    _get_repo_labels,
)
from github_operations.session_integration import (  # noqa: F401
    _get_current_session_id,
    _get_mapping_file,
    _get_ops_count,
    _get_session_id,
    _increment_ops_count,
    _load_issues_mapping,
    _save_issues_mapping,
)
